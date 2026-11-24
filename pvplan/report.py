"""把计算结果填进润恒城方案模版，生成 Word 文档。

模版是固定的（pvplan/assets/template.docx），按正文元素的位置找到每一页，
并用页标题核对位置没有错，所以模版结构不变时可以精确替换每一段文字，
原有的字体、颜色、表格和图片都保持不变。
"""
from __future__ import annotations

import copy
import io
import os

import docx
from docx.oxml.ns import qn
from docx.table import Table

from . import charts
from .calc import fmt, wan

TEMPLATE = os.path.join(os.path.dirname(__file__), "assets", "template.docx")

W_P = qn("w:p")
W_R = qn("w:r")
W_T = qn("w:t")
W_TR = qn("w:tr")

# 正文元素位置（下标）以及用来核对的页标题
IDX = {
    "client": 1, "title": 2, "company": 4, "biz_area": 7, "biz_mode": 8,
    "overview": 17, "usage_head": 18, "usage": 19,
    "advice": 21, "advice1": 22, "advice2": 23,
    "module": 25, "inverter": 30,
    "match_head": 33, "match": 34, "gen": 36,
    "invest_head": 37, "invest": 38, "benefit_head": 39, "benefit": 40,
    "flow": 42, "coop1": 44, "coop2": 45, "coop3": 46,
}
CHECK = {
    16: "项目概况", 20: "项目建议", 24: "分布式光伏电站 · 光伏组件选型",
    29: "分布式光伏电站 · 逆变器选型", 35: "发电量测算", 41: "合作模式与实施流程",
    47: "运维与服务保障",
}
# 需要重画的图（关系 ID）
RID_USAGE, RID_MATCH, RID_BENEFIT = "rId17", "rId25", "rId26"


class TemplateError(RuntimeError):
    pass


# ---------------------------------------------------------------- 工具函数
def _ptext(p):
    return "".join(t.text or "" for t in p.iter(W_T))


def _paras(el):
    """元素里有文字的段落（不含嵌套表格里的）。"""
    if el.tag == W_P:
        return [el]
    return [p for p in el.iter(W_P) if _ptext(p).strip()]


def set_p(p, text):
    """替换段落文字，保留第一个文字 run 的格式。"""
    ts = list(p.iter(W_T))
    if not ts:
        raise TemplateError("段落里没有文字，无法替换")
    ts[0].text = text
    ts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for t in ts[1:]:
        t.text = ""


def set_list(protos, items):
    """用已有的几段作为样板，换成 items 列表（每项为文字，或 (文字, 是否用最后一段的格式)）。

    protos 是原文中连续的几段；普通项用第一段的格式，标记为 True 的项用最后一段的格式。
    多余的原段落会删除。
    """
    normal, special = protos[0], protos[-1]
    anchor = protos[-1]
    new = []
    for it in items:
        txt, sp = (it if isinstance(it, tuple) else (it, False))
        el = copy.deepcopy(special if sp else normal)
        set_p(el, txt)
        new.append(el)
    for el in reversed(new):
        anchor.addnext(el)
    for p in protos:
        p.getparent().remove(p)


def _replace_everywhere(root, old, new):
    if not old or old == new:
        return
    for p in root.iter(W_P):
        if old in _ptext(p):
            ts = list(p.iter(W_T))
            full = "".join(t.text or "" for t in ts)
            # 同一个 run 内能直接替换的直接替换（保留格式），否则合并到第一个 run
            if all(old not in (t.text or "") for t in ts):
                set_p(p, full.replace(old, new))
            else:
                for t in ts:
                    if t.text and old in t.text:
                        t.text = t.text.replace(old, new)


def _set_table_rows(tbl, rows):
    """嵌套的「名称 | 数值」两列表格：按 rows 重建行（以第一行为样板）。"""
    trs = tbl.findall(W_TR)
    proto = trs[0]
    for tr in trs:
        tbl.remove(tr)
    for label, value in rows:
        tr = copy.deepcopy(proto)
        cells = tr.findall(qn("w:tc"))
        set_p(_paras(cells[0])[0], label)
        set_p(_paras(cells[1])[0], value)
        tbl.append(tr)


def _money(x):
    """元 -> 「xx.x万元」或「xxx元」。"""
    if abs(x) >= 10000:
        return f"{x / 10000:.1f}万元"
    return f"{x:.0f}元"


def _kwh(x):
    """度 -> 「xx.x万度」，不足 10 万度时写「12,345度」。"""
    return f"{x / 10000:.1f}万度" if x >= 100000 else f"{x:,.0f}度"


def _price(x):
    return f"{fmt(x, 4)}元/度"


def _months_list(ms):
    """[9, 10] -> 「9、10月」"""
    return "、".join(str(m) for m in ms) + "月"


# ---------------------------------------------------------------- 主流程
def build(r: dict, settings: dict) -> bytes:
    doc = docx.Document(TEMPLATE)
    body = doc.element.body
    els = list(body.iterchildren())
    for i, title in CHECK.items():
        if _ptext(els[i]).strip() != title:
            raise TemplateError(f"模版结构和程序不一致（第 {i} 段应为「{title}」），请检查模版文件")

    term = r["term"]
    company = settings.get("company_name") or "星昊光电"
    # 先做全局替换：模版里的「工厂」「星昊光电」
    _replace_everywhere(body, "工厂", term)
    _replace_everywhere(body, "星昊光电", company)

    def E(name):
        return els[IDX[name]]

    def P(name, k=None):
        ps = _paras(E(name))
        return ps if k is None else ps[k]

    ratio = r["self_ratio"]
    full_feed = ratio <= 0
    model = r["model"]
    years = r["years"]
    investor = f"{company}全额投资" if model == "emc" else f"{term}自主投资"

    # ---- 封面
    set_p(P("client", 0), r["client_name"])
    set_p(P("title", 0), f"{r['scale_title']}{r.get('plan_suffix') or '分布式光伏发电项目前期方案'}")
    set_p(P("company", 0), f"编制单位：{company}")
    if settings.get("business_area"):
        set_p(P("biz_area", 0), f"业务领域：{settings['business_area']}")
    if settings.get("business_mode"):
        set_p(P("biz_mode", 0), f"业务模式：{settings['business_mode']}")

    # ---- 项目概况
    roof = f"拟利用屋顶面积{r['roof_area']}（以现场勘察为准）；" if r["roof_area"] else "拟利用屋顶建设（面积以现场勘察为准）；"
    s = (f"本项目位于{r['address']}（{r['client_name']}），{roof}"
         f"安装{r['module_name']}{fmt(r['module_power'], 0)}W光伏组件{r['module_count']}块，采用{r['install_method']}，"
         f"装机容量为{r['kwp_text']}kWp，该系统为{r['grid_mode']}。")
    if full_feed:
        s += "光伏电站所发电量全部接入公共电网，按约定上网电价结算，电站与电网并网运行，不影响用户原有用电。"
    else:
        s += (f"发电量供给{term}日常用电，光伏电站和电网为并网连接，光伏电站所发电能和电网频率相同，"
              "若光伏电站功率及所发电量不够日常使用，则电网即时补充缺失的功率及其电量，不存在切换过程，"
              "不会对设备造成任何影响及波动。")
    ov = P("overview")
    set_p(ov[0], s)
    set_p(ov[1], f"首年发电量预计为{_kwh(r['gen_y1'])}，全年平均每天发电量约{r['gen_daily']:.0f}度；"
                 "春、夏、秋季阳光充足、有效照射时间较长，日发电量高于全年平均。")

    # ---- 用电现状
    if r.get("has_usage"):
        n = r["usage_known_n"]
        miss = r["usage_missing"]
        set_p(P("usage_head", 0), f"用电现状：{term}用电情况（{r['usage_period']}电费账单）")
        us = P("usage")
        note = f"单位：万度（根据{r['usage_period']}共{n}个月电费账单整理"
        if miss:
            note += "，缺" + "、".join(m.label for m in miss) + "账单"
        set_p(us[0], note + "）")
        items = [f"{n}个月用电合计{wan(r['usage_total'])}万度，月均{wan(r['usage_avg'])}万度，"
                 f"折合全年约{wan(r['usage_annual'], 0)}万度。"]
        price_txt = f"平均电价约{fmt(r['grid_price'], 3)}元/度。"
        items.append(f"{r['usage_desc']}，{price_txt}" if r.get("usage_desc") else price_txt)
        items += r.get("usage_notes", [])
        items.append((f"本方案按{term}实际用电量测算光伏消纳。", True))
        set_list(us[1:], items)
        doc.part.related_parts[RID_USAGE]._blob = charts.usage_chart(
            r["usage_months"], r["usage_avg"] / 10000)
    else:
        for name in ("usage_head", "usage"):
            body.remove(E(name))

    # ---- 项目建议
    set_p(P("advice", 0), f"利用{term}屋顶，建设分布式光伏发电项目")
    if full_feed:
        set_p(P("advice1", 0), "1、增加收益：光伏电量全部上网销售，获得长期稳定的发电收益；")

    # ---- 组件 / 逆变器
    mp = P("module")
    set_p(mp[1], f"本项目综合考虑采用{r['module_name']}{fmt(r['module_power'], 0)}W组件。")
    if settings.get("partner_line") is not None:
        if settings["partner_line"].strip():
            set_p(mp[3], settings["partner_line"].strip())
        else:
            mp[3].getparent().remove(mp[3])
    set_p(P("inverter", 1), f"本项目计划使用{r['inverter_count']}台{fmt(r['inverter_kw'], 1)}kW{r['inverter_type']}。")

    # ---- 用电与发电匹配
    if r.get("has_usage"):
        set_p(P("match_head", 0), f"{term}用电与光伏发电量匹配")
        mt = P("match")
        note = f"单位：万度（光伏月度发电量按首年{fmt(r['hours'], 0)}小时估算"
        if r["usage_estimated_months"]:
            note += f"；{_months_list(r['usage_estimated_months'])}用电量按月均值估算"
        set_p(mt[0], note + "）")
        lower = all(p < u for p, u in zip(r["monthly_pv"], r["usage_calendar"]))
        tail = ("全部发电量上网销售。" if full_feed else
                f"约{fmt(ratio, 1)}%的发电量由{term}就地消纳" + ("。" if ratio >= 100 else "，其余余电上网。"))
        items = [
            f"本项目光伏装机规模约为{r['scale_p']}，由{investor}建设。",
            f"光伏电站首年发电量约为{wan(r['gen_y1'])}万度，约占{term}年用电量的{r['usage_share']:.0f}%。",
            ("各月光伏发电量均低于" if lower else "多数月份光伏发电量低于") + f"{term}月用电量；" + tail,
        ]
        set_list(mt[1:], items)
        est = r["usage_estimated_months"]
        ulabel = f"{term}月用电量" + (f"（{_months_list(est)}为估算）" if est else "")
        doc.part.related_parts[RID_MATCH]._blob = charts.match_chart(
            r["usage_calendar"], r["monthly_pv"], ulabel, "光伏月发电量（首年估算）")
    else:
        for name in ("match_head", "match"):
            body.remove(E(name))

    # ---- 发电量测算
    gp = P("gen")
    cond = gp[:7]
    set_p(cond[1], f"（1）单片光伏组件峰值功率{fmt(r['module_power'], 0)}Wp")
    set_p(cond[2], f"（2）光伏组件装机容量为{r['scale_p']}")
    set_p(cond[3], f"（3）首年等效利用小时数按{fmt(r['hours'], 0)}h计算")
    if full_feed:
        set_p(cond[4], "（4）所发电量全部上网销售")
    else:
        set_p(cond[4], f"（4）{term}就地消纳比例约{fmt(ratio, 1)}%")
    set_p(cond[5], f"（5）光伏组件衰减率按运行寿命周期内第一年{fmt(r['decay_first'], 2)}%，"
                   f"之后平均每年衰减{fmt(r['decay_annual'], 2)}%计算。")
    set_p(cond[6], f"{years}年累计发电量约{_kwh(r['gen_total'])}。")
    gtbl = Table(E("gen"), doc._body).rows[0].cells[1].tables[0]._tbl
    trs = gtbl.findall(W_TR)
    head_proto, val_proto = trs[0], trs[1]
    for tr in trs:
        gtbl.remove(tr)
    small = r["kwp"] < 100
    if small:
        for tr in (val_proto,):
            set_p(_paras(tr.findall(qn("w:tc"))[0])[0], "发电量（度）")
    gv = (lambda x: f"{x:,.0f}") if small else wan
    blocks = (years + 4) // 5
    for b in range(blocks):
        h = copy.deepcopy(head_proto)
        v = copy.deepcopy(val_proto)
        hc = h.findall(qn("w:tc"))
        vc = v.findall(qn("w:tc"))
        for k in range(5):
            yi = b * 5 + k
            set_p(_paras(hc[k + 1])[0], f"第{yi + 1}年" if yi < years else "")
            set_p(_paras(vc[k + 1])[0], gv(r["gen"][yi]) if yi < years else "")
        gtbl.append(h)
        gtbl.append(v)

    # ---- 投资方案
    _fill_invest(doc, E("invest_head"), E("invest"), r, term, company)

    # ---- 收益测算与环保效益
    _fill_benefit(doc, E("benefit_head"), E("benefit"), r, term, company)

    # ---- 合作模式与实施流程
    _fill_flow(E("flow"), [E("coop1"), E("coop2"), E("coop3")], r, term, company)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _fill_invest(doc, head, tbl_el, r, term, company):
    model = r["model"]
    full_feed = r["self_ratio"] <= 0
    years = r["years"]
    cy = r["contract_years"]
    gen1 = f"约{_kwh(r['gen_y1'])}"
    t = Table(tbl_el, doc._body)
    left, right = t.rows[0].cells
    nested = left.tables[0]._tbl
    # 左侧表格下方的说明（不在嵌套表格里）
    lnote = [p for p in left._tc.findall(W_P) if _ptext(p).strip()][-1]
    rps = _paras(right._tc)

    if model == "emc":
        set_p(_paras(head)[0], f"项目投资方案：由我方全额投资，{term}享受{fmt(r['ppa_price'], 4)}元/度固定电价")
        rows = [
            (f"{term}投资", "0元"),
            ("合同期限", f"{cy}年"),
            ("发电量/年", gen1),
            (f"自发自用电量/年（约{fmt(r['self_ratio'], 1)}%消纳）", f"约{_kwh(r['self_y1'])}"),
            (f"{term}现行电价", f"约{fmt(r['grid_price'], 3)}元/度"),
            ("光伏结算电价", _price(r["ppa_price"])),
            ("节省电费/年", f"约{_money(r['benefit_y1'])}"),
            (f"{r['benefit_years']}年总节省电费约", f"约{_money(r['benefit_total'])}"),
        ]
        note = (f"（{term}现行电价按约{fmt(r['grid_price'], 3)}元/度，光伏电量按固定{fmt(r['ppa_price'], 4)}元/度结算；"
                f"按约{fmt(r['self_ratio'], 1)}%就地消纳测算。）")
        items = [
            f"投资方全额投资建设，{term}提供屋顶以及临时用水用电、配合乙方勘察，提供发改局项目备案以及供电局接入申请所需的各项资料文件。",
            f"电站运维由投资方负责，{term}无需承担运维费用。",
            f"本项目建设完成后并入{term}配电系统，并网方案以供电局出具的接入方案为准。",
            f"本项目经供电局验收合格正式运营后，所发电量优先供给{term}用电所需，若有剩余电量直接并网出售供电局；"
            f"光伏发电和国家电网为双电源模式，自动优先使用光伏电能，若光伏电能不足则国网自动补充，不会对{term}用电造成任何不利影响。",
            f"{company}供给{term}用电，光伏电站验收后供电局会安装2块计量表：第一块安装在光伏电站侧，用以计量光伏总发电量；"
            f"第二块安装在公网侧，用以计量{term}使用供电局电量和电站出售供电局电量。甲乙双方电费月结；卖给供电局的电量，供电局与我司直接结算。",
            (f"光伏寿命30年，{term}与投资方签署能源管理合同为{cy}年。", True),
        ]
    elif model == "self":
        mode_txt = "全额上网" if full_feed else ("全部自发自用" if r["self_ratio"] >= 100 else "自发自用、余电上网")
        set_p(_paras(head)[0], f"项目投资方案：{term}自主投资，{mode_txt}")
        pb = r["payback"]
        rows = [
            ("项目总投资", f"约{_money(r['investment'])}"),
            ("投资单价", f"{fmt(r['invest_unit'], 2)}元/W"),
            ("发电量/年", gen1),
        ]
        if not full_feed:
            rows.append((f"自发自用电量/年（约{fmt(r['self_ratio'], 1)}%）", f"约{_kwh(r['self_y1'])}"))
            rows.append(("首年节省电费", f"约{_money(r['benefit_y1_save'])}"))
        if r["self_ratio"] < 100:
            rows.append(("首年售电收入", f"约{_money(r['benefit_y1_sell'])}"))
        rows += [
            ("年运维费用", f"约{_money(r['om_cost'])}"),
            ("首年净收益", f"约{_money(r['benefit_y1'])}"),
            ("静态投资回收期", f"约{pb:.1f}年" if pb else f"{years}年内未回收"),
            (f"{years}年累计净收益", f"约{_money(r['benefit_total'])}"),
        ]
        parts = []
        if not full_feed:
            parts.append(f"自用电量按现行电价约{fmt(r['grid_price'], 3)}元/度折算节省电费")
        if r["self_ratio"] < 100:
            parts.append(f"上网电量按{fmt(r['feed_price'], 4)}元/度结算")
        parts.append(f"运维费按{fmt(r['om_unit'], 3)}元/W/年计")
        note = "（" + "；".join(parts) + "；回收期为静态测算，未考虑贷款利息与税费。）"
        items = [
            f"{term}自主投资建设，我方负责项目设计、设备采购、安装施工及并网手续办理（EPC总包）。",
            "本项目建设完成后并入配电系统，并网方案以供电局出具的接入方案为准。",
        ]
        if full_feed:
            items.append("所发电量全部接入公共电网，由供电局按上网电价按月结算电费。")
        else:
            items.append(f"所发电量优先供给{term}用电所需，若有剩余电量直接并网出售供电局；"
                         f"光伏发电和国家电网为双电源模式，若光伏电能不足则国网自动补充，不会对{term}用电造成任何不利影响。")
        items += [
            "光伏电站验收后供电局会安装计量表，分别计量光伏总发电量和上网电量，作为结算依据。",
            f"我方可提供运维服务（远程监控、定期巡检与清洗），保障电站长期稳定发电。",
            (f"光伏组件寿命30年，本方案按{years}年测算收益。", True),
        ]
    _set_table_rows(nested, rows)
    set_p(lnote, note)
    set_list(rps, items)


def _fill_benefit(doc, head, tbl_el, r, term, company):
    model = r["model"]
    ps = _paras(tbl_el)
    note, bullets = ps[0], ps[1:]
    co2 = r["co2_t"]
    co2_txt = f"约{co2 / 10000:.1f}万吨" if co2 >= 10000 else f"约{co2:.0f}吨"
    years = r["years"]
    green = (f"{years}年累计发电约{_kwh(r['gen_total'])}，按全国电网平均排放因子{fmt(r['emission_factor'], 4)}kgCO₂/kWh"
             f"（生态环境部2023年数据）估算，累计减少二氧化碳排放{co2_txt}。")
    if model == "emc":
        set_p(_paras(head)[0], f"{term}收益测算与环保效益")
        set_p(note, "注：年节省按各年发电量衰减后折算，具体以合同及实际结算为准。")
        items = [
            f"{term}零投资、零运维，首年节省电费约{_money(r['benefit_y1'])}，{r['benefit_years']}年累计约{_money(r['benefit_total'])}。",
            f"电价按{fmt(r['ppa_price'], 4)}元/度固定结算，低于{term}现行平均电价约{fmt(r['grid_price'], 3)}元/度，合同期内按约定执行，具体以合同为准。",
            green,
            f"光伏发电为{term}提供绿色电力，助力企业节能减排和绿色制造。",
        ]
        bar, line = "年节省电费（{unit}）", "累计节省（{unit}）"
    else:
        set_p(_paras(head)[0], f"{term}收益测算与环保效益")
        set_p(note, "注：年净收益按各年发电量衰减后折算，已扣除运维费用，具体以实际发电和结算为准。")
        pb = r["payback"]
        items = [
            f"项目总投资约{_money(r['investment'])}，首年净收益约{_money(r['benefit_y1'])}，"
            + (f"静态投资回收期约{pb:.1f}年。" if pb else f"{years}年内未能收回投资。"),
            f"{years}年累计净收益约{_money(r['benefit_total'])}，扣除投资后净赚约{_money(r['benefit_total'] - r['investment'])}。",
            green,
            f"光伏发电为{term}提供绿色电力，节能减排，提升企业形象。",
        ]
        bar, line = "年净收益（{unit}）", "累计净收益（{unit}）"
    set_list(bullets, items)
    doc.part.related_parts[RID_BENEFIT]._blob = charts.benefit_chart(r["yearly"], r["benefit_cum"], bar, line)


def _fill_flow(tbl_el, coop, r, term, company):
    model = r["model"]
    ps = _paras(tbl_el)
    titles, descs = ps[:6], ps[6:12]
    cy = r["contract_years"]
    if model == "emc":
        d = ["签订合同能源管理（EMC）协议，明确电价、期限、双方责任",
             "屋顶结构复核、现场勘察，确定最终布置方案",
             f"办理项目备案和电网接入申请，{term}配合提供资料",
             "设备采购、安装施工，分区安排，不影响正常生产",
             "电网验收合格后并网发电",
             "我方负责运维，按月抄表结算电费"]
        c = [f"合作模式：由我方全额投资、建设和运维，{term}提供屋顶及临时水电，按约定电价结算，无需任何投资。",
             f"合作期限：{cy}年（光伏电站设计寿命30年）；合作期满后电站的处置方式由双方协商确定。"]
        t6 = "6  运营结算"
    else:
        d = ["签订EPC总包合同，明确工程范围、价格、工期及质保",
             "屋顶结构复核、现场勘察，确定最终布置方案",
             f"办理项目备案和电网接入申请，{term}配合提供资料",
             "设备采购、安装施工，分区安排，不影响正常生产",
             "电网验收合格后并网发电",
             "移交电站，提供运维服务与发电数据查询"]
        c = [f"合作模式：{term}自主投资，我方提供设计、采购、施工及并网的一站式EPC服务，并可提供长期运维。",
             f"收益测算：按{r['years']}年计算（光伏电站设计寿命30年），回收期后发电收益全部归{term}所有。"]
        t6 = "6  运维服务"
    for p, txt in zip(descs, d):
        set_p(p, txt)
    set_p(titles[5], t6)
    set_p(_paras(coop[0])[0], c[0])
    set_p(_paras(coop[1])[0], c[1])
    set_p(_paras(coop[2])[0], f"预计工期：备案及接入审批约1～2个月，施工安装约{'2～3个月' if r['kwp'] >= 500 else '1～4周'}"
                              f"（受审批、天气和{term}生产安排影响，以实际为准）。")
