"""光伏方案设计网页：员工登录 → 填写 → 一键导出 Word。"""
from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import calc, report

DATA_DIR = os.environ.get("PVPLAN_DATA", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
DB_PATH = os.path.join(DATA_DIR, "pvplan.db")
FILES = os.path.join(DATA_DIR, "files")

DEFAULT_SETTINGS = {
    "company_name": "星昊光电",
    "business_area": "分布式、BIPV、离微网系统等",
    "business_mode": "项目咨询、项目开发、EPC总包、合同能源管理、电站运维等",
    "partner_line": "（我司为隆基宁夏区域金牌EPC、唯一授权代理三金合作商）",
}
SETTING_LABELS = {
    "company_name": "公司名称（编制单位）",
    "business_area": "业务领域",
    "business_mode": "业务模式",
    "partner_line": "组件页合作资质说明（留空则不显示）",
}

KEEP_PLANS = int(os.environ.get("PVPLAN_KEEP", "3"))  # 服务器上最多保留的方案份数

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024


# ---------------------------------------------------------------- 数据库
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def _close(_exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  pw TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plans(
  id INTEGER PRIMARY KEY, client TEXT NOT NULL, ptype TEXT NOT NULL, kwp REAL NOT NULL,
  model TEXT NOT NULL, form TEXT NOT NULL, user_id INTEGER NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def init_db():
    os.makedirs(FILES, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    key_file = os.path.join(DATA_DIR, "secret.key")
    if not os.path.exists(key_file):
        with open(key_file, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(key_file, 0o600)
    with open(key_file) as f:
        app.secret_key = f.read().strip()


def get_settings():
    s = dict(DEFAULT_SETTINGS)
    for row in db().execute("SELECT key, value FROM settings"):
        s[row["key"]] = row["value"]
    return s


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def create_user(username, name, password, is_admin=False):
    con = sqlite3.connect(DB_PATH)
    con.execute("INSERT INTO users(username,name,pw,is_admin,created) VALUES(?,?,?,?,?)",
                (username, name, generate_password_hash(password), 1 if is_admin else 0, now()))
    con.commit()
    con.close()


# ---------------------------------------------------------------- 登录与安全
_fails: dict[str, list[float]] = {}


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    if "user" not in g:
        g.user = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return g.user


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return w


def admin_required(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if not current_user()["is_admin"]:
            abort(403)
        return f(*a, **k)
    return w


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["current_user"] = current_user


@app.before_request
def _check_csrf():
    if request.method == "POST":
        tok = request.form.get("_csrf") or request.headers.get("X-CSRF")
        if not tok or tok != session.get("csrf"):
            abort(400, "页面已过期，请刷新后重试")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
        recent = [t for t in _fails.get(ip, []) if time.time() - t < 600]
        _fails[ip] = recent
        if len(recent) >= 8:
            flash("密码错误次数过多，请 10 分钟后再试")
            return render_template("login.html"), 429
        u = db().execute("SELECT * FROM users WHERE username=?", (request.form.get("username", "").strip(),)).fetchone()
        if u and check_password_hash(u["pw"], request.form.get("password", "")):
            session.clear()
            session["uid"] = u["id"]
            session.permanent = True
            nxt = request.args.get("next") or "/"
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
        recent.append(time.time())
        flash("用户名或密码错误")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- 方案
DEFAULTS = dict(client_term="工厂", module_name="隆基HPBC三防", module_power="655",
                inverter_kw="150", inverter_type="组串逆变器", install_method="阵列式安装",
                grid_mode="自发自用，余电上网", hours="1400", self_ratio="90", decay_first="1", decay_annual="0.4",
                years="25", emission_factor="0.5306", model="emc", contract_years="25", ppa_price="0.45",
                invest_unit="2.8", om_unit="0.03", usage_start="",
                plan_suffix="分布式光伏发电项目前期方案")
FIELDS = sorted(set(DEFAULTS) | {
    "client_name", "address", "roof_area", "module_count", "capacity_kw", "inverter_count", "grid_price",
    "feed_price", "usage_monthly", "usage_type", "usage_notes"})


def _form_from_request():
    return {k: request.form.get(k, "").strip() for k in FIELDS}


def _filename(client, kwp):
    safe = re.sub(r'[\\/:*?"<>|\s]+', "", client)[:40] or "光伏方案"
    scale = f"{calc.fmt(kwp / 1000, 2)}MW" if kwp >= 1000 else f"{kwp:.0f}kW"
    return f"{safe}{scale}光伏方案.docx"


def prune():
    """只保留最新的 KEEP_PLANS 份方案，更早的连同 Word 文件一起删除。"""
    old = db().execute("SELECT id FROM plans ORDER BY id DESC LIMIT -1 OFFSET ?", (KEEP_PLANS,)).fetchall()
    for row in old:
        db().execute("DELETE FROM plans WHERE id=?", (row["id"],))
        try:
            os.remove(os.path.join(FILES, f"{row['id']}.docx"))
        except FileNotFoundError:
            pass
    db().commit()


@app.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    sql = ("SELECT plans.*, users.name AS author FROM plans JOIN users ON users.id = plans.user_id")
    args = []
    if q:
        sql += " WHERE plans.client LIKE ?"
        args.append(f"%{q}%")
    sql += " ORDER BY plans.id DESC LIMIT 200"
    rows = db().execute(sql, args).fetchall()
    return render_template("index.html", rows=rows, q=q, models=calc.MODELS, keep=KEEP_PLANS)


@app.route("/new", methods=["GET", "POST"])
@login_required
def new():
    error = None
    if request.method == "POST":
        form = _form_from_request()
        try:
            r = calc.compute(form)
            r["plan_suffix"] = form.get("plan_suffix")
            data = report.build(r, get_settings())
        except calc.InputError as e:
            error = str(e)
        else:
            cur = db().execute(
                "INSERT INTO plans(client,ptype,kwp,model,form,user_id,created) VALUES(?,?,?,?,?,?,?)",
                (r["client_name"], r["project_type"], r["kwp"], r["model"], json.dumps(form, ensure_ascii=False),
                 current_user()["id"], now()))
            db().commit()
            with open(os.path.join(FILES, f"{cur.lastrowid}.docx"), "wb") as f:
                f.write(data)
            prune()
            return redirect(url_for("plan", pid=cur.lastrowid, new=1))
    else:
        src = request.args.get("from", type=int)
        form = dict(DEFAULTS)
        if src:
            row = db().execute("SELECT form FROM plans WHERE id=?", (src,)).fetchone()
            if row:
                form.update(json.loads(row["form"]))
    return render_template("form.html", form=form, error=error,
                           grid_modes=calc.GRID_MODES, models=calc.MODELS)


@app.route("/api/preview", methods=["POST"])
@login_required
def preview():
    try:
        r = calc.compute(_form_from_request())
    except calc.InputError as e:
        return jsonify(ok=False, error=str(e))
    return jsonify(ok=True, items=calc.summary(r))


def _get_plan(pid):
    row = db().execute("SELECT plans.*, users.name AS author FROM plans JOIN users ON users.id=plans.user_id "
                       "WHERE plans.id=?", (pid,)).fetchone()
    if not row:
        abort(404)
    return row


@app.route("/p/<int:pid>")
@login_required
def plan(pid):
    row = _get_plan(pid)
    form = json.loads(row["form"])
    try:
        items = calc.summary(calc.compute(form))
    except calc.InputError:
        items = []
    return render_template("plan.html", row=row, items=items, models=calc.MODELS, is_new=request.args.get("new"))


@app.route("/p/<int:pid>/download")
@login_required
def download(pid):
    row = _get_plan(pid)
    path = os.path.join(FILES, f"{pid}.docx")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=_filename(row["client"], row["kwp"]),
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.route("/p/<int:pid>/delete", methods=["POST"])
@login_required
def delete(pid):
    row = _get_plan(pid)
    u = current_user()
    if not (u["is_admin"] or u["id"] == row["user_id"]):
        abort(403)
    db().execute("DELETE FROM plans WHERE id=?", (pid,))
    db().commit()
    try:
        os.remove(os.path.join(FILES, f"{pid}.docx"))
    except FileNotFoundError:
        pass
    flash(f"已删除「{row['client']}」的方案")
    return redirect(url_for("index"))


# ---------------------------------------------------------------- 设置与账号
@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "company":
            for k in DEFAULT_SETTINGS:
                db().execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                             (k, request.form.get(k, "").strip()))
            db().commit()
            flash("公司信息已保存，之后生成的方案会使用新信息")
        elif action == "add_user":
            un = request.form.get("username", "").strip()
            nm = request.form.get("name", "").strip() or un
            pw = request.form.get("password", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", un):
                flash("用户名只能用字母、数字，2～32 位")
            elif len(pw) < 6:
                flash("密码至少 6 位")
            elif db().execute("SELECT 1 FROM users WHERE username=?", (un,)).fetchone():
                flash("这个用户名已经存在")
            else:
                db().execute("INSERT INTO users(username,name,pw,is_admin,created) VALUES(?,?,?,?,?)",
                             (un, nm, generate_password_hash(pw), 1 if request.form.get("is_admin") else 0, now()))
                db().commit()
                flash(f"已添加账号 {un}")
        elif action in ("del_user", "reset_pw"):
            uid = request.form.get("uid", type=int)
            if uid == current_user()["id"]:
                flash("不能对自己的账号进行这个操作")
            elif action == "del_user":
                db().execute("DELETE FROM users WHERE id=?", (uid,))
                db().commit()
                flash("账号已删除（该员工生成的方案仍然保留）")
            else:
                pw = request.form.get("password", "")
                if len(pw) < 6:
                    flash("新密码至少 6 位")
                else:
                    db().execute("UPDATE users SET pw=? WHERE id=?", (generate_password_hash(pw), uid))
                    db().commit()
                    flash("密码已重置")
        return redirect(url_for("settings"))
    users = db().execute("SELECT * FROM users ORDER BY id").fetchall()
    return render_template("settings.html", s=get_settings(), labels=SETTING_LABELS, users=users)


@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        u = current_user()
        if not check_password_hash(u["pw"], request.form.get("old", "")):
            flash("原密码不正确")
        elif len(request.form.get("new", "")) < 6:
            flash("新密码至少 6 位")
        elif request.form.get("new") != request.form.get("new2"):
            flash("两次输入的新密码不一致")
        else:
            db().execute("UPDATE users SET pw=? WHERE id=?", (generate_password_hash(request.form["new"]), u["id"]))
            db().commit()
            flash("密码已修改")
            return redirect(url_for("index"))
    return render_template("password.html")


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def _err(e):
    msg = {403: "没有权限", 404: "找不到这个页面"}.get(e.code, e.description)
    return render_template("error.html", msg=msg), e.code
