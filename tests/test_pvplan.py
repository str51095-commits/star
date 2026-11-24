"""运行：python3 -m pytest -q tests"""
import io
import os
import sys

import docx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pvplan import calc, report  # noqa: E402

BASE = dict(module_name="隆基HPBC三防", module_power="655", inverter_kw="150", hours="1200")

# 原模版（西北机器厂）的数据
EMC = dict(BASE, project_type="工商业", client_name="西北机器有限公司西北机器厂", address="陕西省宝鸡市岐山县",
           module_count="2291", inverter_count="9", grid_mode="自发自用，余电上网", hours="1050", self_ratio="93",
           model="emc", grid_price="0.67", ppa_price="0.45", usage_start="2025-01",
           usage_monthly="64.2\n64.3\n60.5\n45.7\n46.4\n51.9\n72.0\n63.9\n-\n-\n47.9\n54.0\n58.5")


def text(b):
    d = docx.Document(io.BytesIO(b))
    out = []
    for p in d.element.body.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
        out.append(p.text or "")
    return "".join(out)


def test_emc_matches_template():
    r = calc.compute(EMC)
    assert r["kwp"] == pytest.approx(1500.605)
    assert r["gen_y1"] / 1e4 == pytest.approx(155.99, abs=0.01)   # 模版 155.9
    assert r["gen_total"] / 1e4 == pytest.approx(3717, abs=2)      # 模版 3717
    assert r["gen"][24] / 1e4 == pytest.approx(141.6, abs=0.1)     # 模版第25年 141.6
    assert r["benefit_total"] / 1e4 == pytest.approx(761, abs=3)   # 模版 763（按 0.67 元）
    assert r["co2_t"] / 1e4 == pytest.approx(2.0, abs=0.05)
    assert r["usage_known_n"] == 11 and r["usage_estimated_months"] == [9, 10]


def test_emc_report_has_client_and_numbers():
    r = calc.compute(EMC)
    t = text(report.build(r, {"company_name": "星昊光电"}))
    for s in ["西北机器有限公司西北机器厂", "1.5MW分布式光伏发电项目前期方案", "2291块", "1500.61kWp",
              "9台150kW组串逆变器", "用电现状：工厂用电情况", "缺2025年9月、2025年10月账单", "0.45元/度"]:
        assert s in t, s
    assert "（示例）" not in t


@pytest.mark.parametrize("form,expect,absent", [
    (dict(BASE, project_type="户用", client_name="张三", address="宁夏吴忠", capacity_kw="30", inverter_kw="30",
          grid_mode="全额上网", model="rent", rent_basis="panel", rent_price="30", contract_years="20"),
     ["业主出租屋顶", "30元/块/年", "约1380元", "发电量（度）"], ["用电现状", "工厂"]),
    (dict(BASE, project_type="工商业", client_name="某食品厂", address="银川", capacity_kw="500",
          grid_mode="自发自用，余电上网", self_ratio="80", model="self", grid_price="0.62", feed_price="0.2595",
          invest_unit="2.8"),
     ["工厂自主投资", "静态投资回收期", "首年售电收入"], ["用电现状", "合同能源管理（EMC）"]),
])
def test_other_models(form, expect, absent):
    r = calc.compute(form)
    t = text(report.build(r, {"company_name": "测试光电"}))
    assert "编制单位：测试光电" in t and "星昊光电" not in t
    for s in expect:
        assert s in t, s
    for s in absent:
        assert s not in t, s
    assert "（示例）" not in t


def test_payback():
    r = calc.compute(dict(BASE, project_type="工商业", client_name="a", address="b", capacity_kw="100",
                          grid_mode="全部自发自用", model="self", grid_price="0.6", invest_unit="3", om_unit="0"))
    # 首年收益约等于年均收益，回收期约为 投资 ÷ 首年收益
    y1 = r["yearly"][0]
    assert r["payback"] == pytest.approx(300000 / y1, rel=0.05)


@pytest.mark.parametrize("bad,msg", [
    (dict(capacity_kw="abc"), "应填写数字"),
    (dict(capacity_kw="100", model="emc", grid_mode="全额上网", grid_price="0.6", ppa_price="0.4"), "合同能源管理"),
    (dict(capacity_kw="100", model="emc", grid_price="0.4", ppa_price="0.5", self_ratio="80"), "应低于"),
    (dict(capacity_kw="100", usage_start="2025-13", usage_monthly="1\n2", self_ratio="80", grid_price="0.6",
          ppa_price="0.4"), "账单起始月份"),
])
def test_input_errors(bad, msg):
    f = dict(BASE, project_type="工商业", client_name="a", address="b", hours="1100")
    f.update(bad)
    with pytest.raises(calc.InputError, match=msg):
        calc.compute(f)


def test_web_flow(tmp_path, monkeypatch):
    from pvplan import app as appmod
    monkeypatch.setattr(appmod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(appmod, "DB_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setattr(appmod, "FILES", str(tmp_path / "files"))
    appmod.init_db()
    appmod.create_user("admin", "管理员", "secret123", True)
    c = appmod.app.test_client()
    assert c.get("/").status_code == 302  # 未登录跳转
    c.get("/login")
    with c.session_transaction() as s:
        tok = s["csrf"]
    assert c.post("/login", data={"_csrf": "bad", "username": "admin", "password": "secret123"}).status_code == 400
    assert c.post("/login", data={"_csrf": tok, "username": "admin", "password": "secret123"}).status_code == 302
    c.get("/new")
    with c.session_transaction() as s:
        tok = s["csrf"]
    rv = c.post("/new", data=dict(EMC, _csrf=tok))
    assert rv.status_code == 302 and "/p/1" in rv.headers["Location"]
    rv = c.get("/p/1/download")
    assert rv.status_code == 200 and len(rv.data) > 100000
    assert "1.5MW" in rv.headers["Content-Disposition"]
    j = c.post("/api/preview", data=dict(EMC), headers={"X-CSRF": tok}).get_json()
    assert j["ok"] and j["items"][0][0] == "装机容量"
