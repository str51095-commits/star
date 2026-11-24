"""命令行入口。

  python3 -m pvplan serve [--port 8600]      启动网页
  python3 -m pvplan adduser 用户名 姓名 密码 [--admin]
"""
import argparse
import sys

from . import app as appmod


def main(argv=None):
    p = argparse.ArgumentParser(prog="pvplan")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8600)
    u = sub.add_parser("adduser")
    u.add_argument("username")
    u.add_argument("name")
    u.add_argument("password")
    u.add_argument("--admin", action="store_true")
    r = sub.add_parser("passwd")
    r.add_argument("username")
    r.add_argument("password")
    a = p.parse_args(argv)
    appmod.init_db()
    if a.cmd == "serve":
        from waitress import serve
        print(f"光伏方案设计已启动：http://{a.host}:{a.port}", flush=True)
        serve(appmod.app, host=a.host, port=a.port, threads=4)
    elif a.cmd == "adduser":
        appmod.create_user(a.username, a.name, a.password, a.admin)
        print(f"已添加账号 {a.username}")
    elif a.cmd == "passwd":
        import sqlite3
        from werkzeug.security import generate_password_hash
        con = sqlite3.connect(appmod.DB_PATH)
        n = con.execute("UPDATE users SET pw=? WHERE username=?", (generate_password_hash(a.password), a.username)).rowcount
        con.commit()
        print("密码已重置" if n else "没有这个用户名")
        return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
