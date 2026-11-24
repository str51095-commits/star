"""按模版样式重新绘制方案里的三张图（红色柱状图）。"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

RED = "#E60012"
GREY = "#BFBFBF"
DARK = "#333333"

_FONT_CANDIDATES = [
    "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "Source Han Sans CN",
    "WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "Microsoft YaHei", "SimHei", "PingFang SC",
]


def _setup_font():
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in _FONT_CANDIDATES:
        if name in have:
            plt.rcParams["font.sans-serif"] = [name] + list(plt.rcParams["font.sans-serif"])
            break
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False


_setup_font()


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#EEEEEE", linewidth=0.8)
    ax.set_axisbelow(True)


def _png(fig, w_px, h_px):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    return buf.getvalue()


def usage_chart(months, avg_wan):
    """用电现状：逐月用电量（万度），缺的月份不画柱子。"""
    n = len(months)
    fig, ax = plt.subplots(figsize=(17.2, 8.6))
    labels = [f"{m.year}年\n{m.month}月" if (i == 0 or m.month == 1) else f"{m.month}月" for i, m in enumerate(months)]
    xs = list(range(n))
    vals = [m.value if m.value is not None else 0 for m in months]
    bars = ax.bar(xs, vals, width=0.6, color=RED)
    for x, m, b in zip(xs, months, bars):
        if m.value is None:
            ax.text(x, avg_wan * 0.03, "缺账单", ha="center", va="bottom", fontsize=13, color="#999999")
        else:
            ax.text(x, b.get_height(), f"{m.value:.1f}", ha="center", va="bottom", fontsize=16)
    ax.axhline(avg_wan, color=DARK, linestyle="--", linewidth=1.2)
    ax.text(-0.45, avg_wan, f"月均 {avg_wan:.1f}", ha="left", va="bottom", fontsize=14, color=DARK,
            bbox=dict(facecolor="white", edgecolor="none", pad=1))
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=15)
    ax.tick_params(axis="y", labelsize=16)
    ax.set_ylabel("万度", fontsize=18)
    top = max(vals) if max(vals) > 0 else 1
    ax.set_ylim(0, top * 1.15)
    _style(ax)
    fig.tight_layout()
    return _png(fig, 1720, 860)


def match_chart(usage_cal, pv_monthly, usage_label, pv_label):
    """工厂用电与光伏发电量匹配：灰色=用电，红色=光伏（万度）。"""
    fig, ax = plt.subplots(figsize=(17.2, 8.6))
    xs = list(range(12))
    u = [v / 10000 for v in usage_cal]
    p = [v / 10000 for v in pv_monthly]
    wdt = 0.4
    ax.bar([x - wdt / 2 for x in xs], u, width=wdt, color=GREY, label=usage_label)
    ax.bar([x + wdt / 2 for x in xs], p, width=wdt, color=RED, label=pv_label)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{i}月" for i in range(1, 13)], fontsize=18)
    ax.tick_params(axis="y", labelsize=18)
    ax.set_ylabel("万度", fontsize=18)
    ax.set_ylim(0, max(u + p) * 1.25)
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=18)
    _style(ax)
    fig.tight_layout()
    return _png(fig, 1720, 860)


def benefit_chart(yearly, cum, bar_label, line_label):
    """收益测算：柱=每年收益，线=累计。累计不足 10 万元时用「元」作单位，否则用「万元」。"""
    fig, ax = plt.subplots(figsize=(10.8, 6.3))
    xs = list(range(1, len(yearly) + 1))
    div, unit = (10000, "万元") if max(abs(v) for v in cum) >= 100000 else (1, "元")
    bar_label = bar_label.format(unit=unit)
    line_label = line_label.format(unit=unit)
    y = [v / div for v in yearly]
    c = [v / div for v in cum]
    ax.bar(xs, y, width=0.7, color=RED, label=bar_label)
    ax.set_xlabel("运营年份", fontsize=14)
    ax.set_ylabel(bar_label, fontsize=14)
    lo = min(0, min(y))
    ax.set_ylim(lo * 1.25 if lo < 0 else 0, max(max(y), 0.01) * 1.25)
    ax2 = ax.twinx()
    ax2.plot(xs, c, color=DARK, linewidth=2, label=line_label)
    ax2.set_ylabel(line_label, fontsize=14)
    clo = min(0, min(c))
    ax2.set_ylim(clo * 1.2 if clo < 0 else 0, max(max(c), 0.01) * 1.18)
    if clo < 0:
        ax2.axhline(0, color="#999999", linewidth=0.8)
    ax2.annotate(f"{c[-1]:.0f}{unit}", (xs[-1], c[-1]), textcoords="offset points", xytext=(-60, 18), fontsize=13)
    ticks = [1] + [t for t in range(5, len(xs) + 1, 5)]
    ax.set_xticks(ticks)
    ax.grid(axis="y", color="#EEEEEE", linewidth=0.8)
    ax.set_axisbelow(True)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", ncol=2, frameon=False, fontsize=13)
    fig.tight_layout()
    return _png(fig, 1080, 630)
