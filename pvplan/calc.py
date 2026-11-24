"""光伏方案的全部计算。

只依赖标准库，输入是表单整理后的字典，输出是一个结果字典，
供网页预览和 Word 生成共用，保证两边数字一致。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# 北方地区光伏月度发电占比（来自模版中的月度发电曲线，合计为 1）
MONTH_PROFILE = [9.7, 10.5, 12.9, 15.3, 16.9, 16.1, 16.9, 16.1, 12.1, 11.3, 9.7, 8.9]
_s = sum(MONTH_PROFILE)
MONTH_PROFILE = [x / _s for x in MONTH_PROFILE]

MODELS = {
    "emc": "投资方全额投资（合同能源管理）",
    "self": "业主自投",
    "rent": "屋顶租赁",
}
GRID_MODES = ["自发自用，余电上网", "全额上网", "全部自发自用"]
RENT_BASIS = {"panel": "元/块/年", "kw": "元/kW/年", "fixed": "元/年（固定）"}


class InputError(ValueError):
    """表单数据有误，消息直接显示给用户。"""


def _num(d, key, label, default=None, lo=None, hi=None, integer=False):
    raw = d.get(key, "")
    if raw is None or str(raw).strip() == "":
        if default is None:
            raise InputError(f"请填写「{label}」")
        return default
    try:
        v = float(str(raw).strip().replace(",", "").replace("，", ""))
    except ValueError:
        raise InputError(f"「{label}」应填写数字，现在是「{raw}」")
    if math.isnan(v) or math.isinf(v):
        raise InputError(f"「{label}」应填写数字")
    if lo is not None and v < lo:
        raise InputError(f"「{label}」不能小于 {lo:g}")
    if hi is not None and v > hi:
        raise InputError(f"「{label}」不能大于 {hi:g}")
    return int(round(v)) if integer else v


def _text(d, key, default=""):
    v = d.get(key)
    v = "" if v is None else str(v).strip()
    return v or default


def parse_monthly(text: str):
    """把「每行一个月」的用电量文本解析成列表，空行、- 或 缺 表示缺失（None）。"""
    vals = []
    if not text:
        return vals
    parts = [p.strip() for p in text.replace("，", ",").replace(",", "\n").splitlines()]
    # 去掉末尾的空行
    while parts and parts[-1] == "":
        parts.pop()
    for p in parts:
        if p in ("", "-", "—", "缺", "无", "/"):
            vals.append(None)
            continue
        try:
            v = float(p)
        except ValueError:
            raise InputError(f"月用电量「{p}」不是数字（每行填一个月的用电量，单位万度；缺的月份填 - ）")
        if v < 0:
            raise InputError("月用电量不能是负数")
        vals.append(v)
    if len(vals) > 36:
        raise InputError("月用电量最多填 36 个月")
    return vals


def _parse_ym(s: str):
    s = (s or "").strip().replace("年", "-").replace("月", "").replace("/", "-").replace(".", "-")
    try:
        y, m = s.split("-")[:2]
        y, m = int(y), int(m)
        if not (2000 <= y <= 2100 and 1 <= m <= 12):
            raise ValueError
        return y, m
    except ValueError:
        raise InputError("「账单起始月份」请按 2025-01 这样的格式填写")


@dataclass
class Month:
    year: int
    month: int
    value: float | None

    @property
    def label(self):
        return f"{self.year}年{self.month}月"


def wan(x, nd=1):
    """度 -> 万度，或 元 -> 万元，保留 nd 位小数的字符串。"""
    return f"{x / 10000:.{nd}f}"


def fmt(x, nd=2):
    s = f"{x:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def compute(form: dict) -> dict:
    d = form
    r: dict = {}
    ptype = _text(d, "project_type", "工商业")
    if ptype not in ("工商业", "户用"):
        raise InputError("项目类型只能是「工商业」或「户用」")
    r["project_type"] = ptype
    r["client_name"] = _text(d, "client_name")
    if not r["client_name"]:
        raise InputError("请填写「客户名称」")
    r["term"] = _text(d, "client_term", "工厂" if ptype == "工商业" else "业主")
    r["address"] = _text(d, "address")
    if not r["address"]:
        raise InputError("请填写「项目地址」")
    r["roof_area"] = _text(d, "roof_area", "")
    r["install_method"] = _text(d, "install_method", "阵列式安装")

    # ---------- 系统配置 ----------
    w = _num(d, "module_power", "组件功率（W）", lo=100, hi=1000)
    r["module_power"] = w
    r["module_name"] = _text(d, "module_name", "隆基HPBC三防")
    n_raw = _text(d, "module_count")
    if n_raw:
        n = _num(d, "module_count", "组件数量（块）", lo=1, hi=200000, integer=True)
    else:
        cap_target = _num(d, "capacity_kw", "规划装机容量（kWp）", lo=0.5, hi=100000)
        n = max(1, int(round(cap_target * 1000 / w)))
    r["module_count"] = n
    kwp = n * w / 1000.0
    r["kwp"] = kwp
    r["kwp_text"] = fmt(kwp, 2)  # 1500.6
    r["mw_text"] = fmt(kwp / 1000, 2)  # 1.5
    # 标题里的规模：1MW 以上写 MW，否则写 kW
    r["scale_title"] = f"{fmt(kwp / 1000, 2)}MW" if kwp >= 1000 else f"{fmt(kwp, 1)}kW"
    r["scale_p"] = f"{fmt(kwp / 1000, 2)}MWp" if kwp >= 1000 else f"{fmt(kwp, 1)}kWp"

    inv_kw = _num(d, "inverter_kw", "逆变器单台功率（kW）", lo=1, hi=10000)
    r["inverter_kw"] = inv_kw
    inv_n_raw = _text(d, "inverter_count")
    if inv_n_raw:
        inv_n = _num(d, "inverter_count", "逆变器数量（台）", lo=1, hi=10000, integer=True)
    else:
        # 按容配比约 1.1 配置，且不超过 1.35
        inv_n = max(1, round(kwp / 1.1 / inv_kw))
        while kwp / (inv_n * inv_kw) > 1.35:
            inv_n += 1
    r["inverter_count"] = inv_n
    r["inverter_type"] = _text(d, "inverter_type", "组串逆变器")
    r["dc_ac_ratio"] = kwp / (inv_n * inv_kw)

    grid_mode = _text(d, "grid_mode", GRID_MODES[0])
    if grid_mode not in GRID_MODES:
        raise InputError("并网方式不正确")
    r["grid_mode"] = grid_mode

    # ---------- 发电参数 ----------
    hours = _num(d, "hours", "首年等效利用小时数（h）", lo=300, hi=2500)
    d1 = _num(d, "decay_first", "首年衰减率（%）", default=1.0, lo=0, hi=10)
    dn = _num(d, "decay_annual", "之后每年衰减率（%）", default=0.4, lo=0, hi=5)
    years = _num(d, "years", "测算年限（年）", default=25, lo=1, hi=30, integer=True)
    r.update(hours=hours, decay_first=d1, decay_annual=dn, years=years)
    if grid_mode == "全额上网":
        ratio = 0.0
    elif grid_mode == "全部自发自用":
        ratio = 100.0
    else:
        ratio = _num(d, "self_ratio", "自发自用比例（%）", lo=0, hi=100)
    r["self_ratio"] = ratio
    ef = _num(d, "emission_factor", "排放因子（kgCO₂/kWh）", default=0.5306, lo=0, hi=2)
    r["emission_factor"] = ef

    y1 = kwp * hours * (1 - d1 / 100)  # 度
    gen = [y1 * (1 - dn / 100) ** i for i in range(years)]
    r["gen"] = gen
    r["gen_y1"] = y1
    r["gen_total"] = sum(gen)
    r["gen_daily"] = y1 / 365
    r["self_y1"] = y1 * ratio / 100
    r["co2_t"] = r["gen_total"] * ef / 1000
    r["monthly_pv"] = [y1 * p for p in MONTH_PROFILE]

    # ---------- 用电情况 ----------
    r["has_usage"] = False
    if ptype == "工商业" and _text(d, "usage_monthly"):
        vals = parse_monthly(_text(d, "usage_monthly"))
        if not any(v is not None for v in vals):
            raise InputError("月用电量至少要填一个月")
        y, m = _parse_ym(_text(d, "usage_start"))
        months = []
        for v in vals:
            months.append(Month(y, m, v))
            m += 1
            if m > 12:
                y, m = y + 1, 1
        known = [x for x in months if x.value is not None]
        missing = [x for x in months if x.value is None]
        total = sum(x.value for x in known) * 10000
        avg = total / len(known)
        r["has_usage"] = True
        r["usage_months"] = months
        r["usage_known_n"] = len(known)
        r["usage_missing"] = missing
        r["usage_total"] = total
        r["usage_avg"] = avg
        r["usage_annual"] = avg * 12
        r["usage_period"] = f"{months[0].label}—{months[-1].label}"
        # 按自然月汇总（同一月份多次出现取平均；缺的月份用平均值估算）
        by_m = {}
        for x in known:
            by_m.setdefault(x.month, []).append(x.value * 10000)
        cal = []
        est = []
        for mm in range(1, 13):
            if mm in by_m:
                cal.append(sum(by_m[mm]) / len(by_m[mm]))
            else:
                cal.append(avg)
                est.append(mm)
        r["usage_calendar"] = cal
        r["usage_estimated_months"] = est
        r["usage_share"] = y1 / r["usage_annual"] * 100 if r["usage_annual"] else 0
        r["usage_desc"] = _text(d, "usage_type")
        r["usage_notes"] = [ln.strip() for ln in _text(d, "usage_notes").splitlines() if ln.strip()]

    # ---------- 商业模式与收益 ----------
    model = _text(d, "model", "emc")
    if model not in MODELS:
        raise InputError("商业模式不正确")
    r["model"] = model
    r["model_name"] = MODELS[model]
    sell = [g * (1 - ratio / 100) for g in gen]
    selfuse = [g * ratio / 100 for g in gen]
    r["selfuse"] = selfuse
    r["sell"] = sell

    need_grid = ratio > 0 or model == "emc"
    r["grid_price"] = _num(d, "grid_price", "现行用电电价（元/度）", lo=0, hi=5) if need_grid else _num(
        d, "grid_price", "现行用电电价（元/度）", default=0.0, lo=0, hi=5)
    r["contract_years"] = _num(d, "contract_years", "合同期限（年）", default=years, lo=1, hi=30, integer=True)

    if model == "emc":
        if ratio <= 0:
            raise InputError("合同能源管理模式需要有自发自用电量，请把并网方式改为「自发自用，余电上网」或「全部自发自用」")
        ppa = _num(d, "ppa_price", "光伏结算电价（元/度）", lo=0, hi=5)
        if ppa >= r["grid_price"]:
            raise InputError("光伏结算电价应低于现行用电电价，否则客户没有节省")
        r["ppa_price"] = ppa
        yearly = [s * (r["grid_price"] - ppa) for s in selfuse]
        r["benefit_label"] = "节省电费"
        r["investment"] = 0.0
    elif model == "self":
        unit = _num(d, "invest_unit", "投资单价（元/W）", lo=0.5, hi=20)
        feed = _num(d, "feed_price", "上网电价（元/度）", lo=0, hi=5) if ratio < 100 else 0.0
        om = _num(d, "om_unit", "运维费用（元/W/年）", default=0.03, lo=0, hi=2)
        r.update(invest_unit=unit, feed_price=feed, om_unit=om)
        r["investment"] = kwp * 1000 * unit
        r["om_cost"] = kwp * 1000 * om
        yearly = [s * r["grid_price"] + e * feed - r["om_cost"] for s, e in zip(selfuse, sell)]
        r["benefit_label"] = "净收益"
        r["benefit_y1_save"] = selfuse[0] * r["grid_price"]
        r["benefit_y1_sell"] = sell[0] * feed
        cum = 0.0
        payback = None
        for i, v in enumerate(yearly):
            if v > 0 and cum + v >= r["investment"]:
                payback = i + (r["investment"] - cum) / v
                break
            cum += v
        r["payback"] = payback
        tot = sum(yearly)
        r["roi_total"] = (tot - r["investment"]) / r["investment"] * 100 if r["investment"] else 0
    else:  # rent
        basis = _text(d, "rent_basis", "kw")
        if basis not in RENT_BASIS:
            raise InputError("租金计算方式不正确")
        price = _num(d, "rent_price", "租金标准", lo=0, hi=1e7)
        if basis == "panel":
            annual = price * n
        elif basis == "kw":
            annual = price * kwp
        else:
            annual = price
        r.update(rent_basis=basis, rent_price=price, rent_unit=RENT_BASIS[basis])
        yearly = [annual] * r["contract_years"]
        r["benefit_label"] = "屋顶租金"
        r["investment"] = 0.0

    # 收益年限：EMC/租赁 按合同期，自投按测算年限
    if model in ("emc",):
        yearly = yearly[: r["contract_years"]]
    r["yearly"] = yearly
    r["benefit_y1"] = yearly[0]
    r["benefit_total"] = sum(yearly)
    r["benefit_years"] = len(yearly)
    cum = []
    c = 0.0
    for v in yearly:
        c += v
        cum.append(c)
    r["benefit_cum"] = cum
    return r


def money(x):
    """元 -> 「12.3 万元」，不足 1 万显示「1380 元」。"""
    return f"{x / 10000:.2f} 万元" if abs(x) >= 10000 else f"{x:.0f} 元"


def summary(r: dict) -> list[tuple[str, str]]:
    """网页预览用的关键指标。"""
    out = [
        ("装机容量", f"{r['kwp_text']} kWp（{r['module_count']} 块 × {fmt(r['module_power'], 0)}W）"),
        ("逆变器", f"{r['inverter_count']} 台 × {fmt(r['inverter_kw'], 1)}kW（容配比 {r['dc_ac_ratio']:.2f}）"),
        ("首年发电量", f"{wan(r['gen_y1'])} 万度（日均约 {r['gen_daily']:.0f} 度）"),
        (f"{r['years']}年累计发电", f"{wan(r['gen_total'], 0)} 万度"),
    ]
    if r["self_ratio"] > 0:
        out.append(("首年自发自用", f"{wan(r['self_y1'])} 万度（{fmt(r['self_ratio'], 1)}%）"))
    if r.get("has_usage"):
        out.append(("客户年用电量", f"约 {wan(r['usage_annual'], 0)} 万度，光伏约占 {r['usage_share']:.0f}%"))
    if r["model"] == "self":
        out.append(("总投资", money(r["investment"])))
        pb = r["payback"]
        out.append(("静态回收期", f"约 {pb:.1f} 年" if pb else f"{r['years']} 年内无法回收"))
    out.append((f"首年{r['benefit_label']}", money(r["benefit_y1"])))
    out.append((f"{r['benefit_years']}年累计{r['benefit_label']}", money(r["benefit_total"])))
    out.append(("累计减排二氧化碳", f"约 {r['co2_t'] / 10000:.1f} 万吨" if r["co2_t"] >= 10000 else f"约 {r['co2_t']:.0f} 吨"))
    return out
