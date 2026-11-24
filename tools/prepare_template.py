"""把原始方案（含真实客户数据）处理成程序用的模版。

用法：python3 tools/prepare_template.py 原始方案.docx pvplan/assets/template.docx

客户名称、地址、用电量、发电量、收益等会被换成「示例」文字，三张数据图
换成空白图。段落和表格结构保持不变，生成方案时程序会重新填写这些位置。
"""
import io
import re
import sys

import docx
from docx.oxml.ns import qn
from PIL import Image

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])
from pvplan.report import RID_BENEFIT, RID_MATCH, RID_USAGE, _paras, _ptext, set_p  # noqa: E402

# 这些元素里的文字全部换成示例
FULL = [1, 2, 17, 18, 19, 34, 37, 38, 40]
NUM = re.compile(r"^[\d.]+$")


def blank_png(w, h):
    b = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(b, "PNG")
    return b.getvalue()


def main(src, dst):
    d = docx.Document(src)
    els = list(d.element.body.iterchildren())
    for i in FULL:
        for p in els[i].iter(qn("w:p")):
            if _ptext(p).strip() and _ptext(p).strip() != "光伏系统结构简图":
                set_p(p, "（示例）")
    # 发电量测算：条件说明和数字
    for p in els[36].iter(qn("w:p")):
        t = _ptext(p).strip()
        if NUM.match(t):
            set_p(p, "0.0")
        elif t.startswith("（") or "累计发电量" in t:
            set_p(p, "（示例）")
    for rid in (RID_USAGE, RID_MATCH, RID_BENEFIT):
        part = d.part.related_parts[rid]
        w, h = Image.open(io.BytesIO(part.blob)).size
        part._blob = blank_png(w, h)
    d.save(dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
