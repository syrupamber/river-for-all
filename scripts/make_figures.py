"""data/ の CSV から figures/ の SVG を作り直すスクリプト。

使い方（リポジトリのいちばん上のフォルダで）:
    python3 scripts/make_figures.py

外部ライブラリは使わず、SVG を文字で組み立てている。
色はライト／ダークの両方を用意していて、見る人の設定で切り替わる。
"""

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIG = ROOT / "figures"

STYLE = """<style>
svg { --bg:#ffffff; --ink:#191919; --ink2:#666666; --grid:#e6e6e6; --band:#f2f2f2;
      --up:#257de0; --down:#f47230; --stop:#7a7a7a; --curve:#191919; --water:#257de0; }
@media (prefers-color-scheme: dark) {
  svg { --bg:#191919; --ink:#efefef; --ink2:#9c9c9c; --grid:#333333; --band:#262626;
        --up:#338ced; --down:#e76624; --stop:#9c9c9c; --curve:#efefef; --water:#338ced; }
}
.bg { fill:var(--bg); }
.t { fill:var(--ink); font-family:-apple-system,"Hiragino Sans","Noto Sans JP","Yu Gothic",sans-serif; }
.t2 { fill:var(--ink2); font-family:-apple-system,"Hiragino Sans","Noto Sans JP","Yu Gothic",sans-serif; }
.grid { stroke:var(--grid); stroke-width:1; }
.axis { stroke:var(--ink2); stroke-width:1; }
.band { fill:var(--band); }
.curve { fill:none; stroke:var(--curve); stroke-width:2; stroke-linejoin:round; }
.turn { stroke:var(--ink2); stroke-width:1; stroke-dasharray:4 4; }
.up { fill:var(--up); stroke:var(--bg); stroke-width:2; }
.down { fill:var(--down); stroke:var(--bg); stroke-width:2; }
.stop { fill:var(--bg); stroke:var(--stop); stroke-width:2.5; }
.mix { fill:var(--stop); stroke:var(--bg); stroke-width:2; }
.dot { fill:var(--ink); stroke:var(--bg); stroke-width:2; }
.river { fill:none; stroke:var(--water); stroke-width:10; stroke-linecap:round; opacity:.35; }
.reach { fill:none; stroke:var(--water); stroke-width:3; }
.arrowline { fill:none; stroke:var(--ink2); stroke-width:1.5; }
</style>"""


def svg_open(w, h, title):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{title}">',
        f"<title>{title}</title>",
        STYLE,
        f'<rect class="bg" x="0" y="0" width="{w}" height="{h}" rx="8"/>',
    ]


def text(x, y, s, cls="t", size=13, anchor="start", weight="normal"):
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{s}</text>'


def marker(kind, x, y, r=7):
    """流れの向きを形と色の両方で表す（色だけに頼らない）。"""
    if kind == "上流へ":
        return f'<path class="up" d="M{x:.1f},{y - r - 1:.1f} L{x + r:.1f},{y + r - 2:.1f} L{x - r:.1f},{y + r - 2:.1f} Z"/>'
    if kind == "下流へ":
        return f'<path class="down" d="M{x:.1f},{y + r + 1:.1f} L{x + r:.1f},{y - r + 2:.1f} L{x - r:.1f},{y - r + 2:.1f} Z"/>'
    if kind == "止まる" or kind == "ゆるやか":
        return f'<circle class="stop" cx="{x:.1f}" cy="{y:.1f}" r="{r - 1}"/>'
    if kind == "混在":
        return f'<path class="mix" d="M{x:.1f},{y - r:.1f} L{x + r:.1f},{y:.1f} L{x:.1f},{y + r:.1f} L{x - r:.1f},{y:.1f} Z"/>'
    return f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="{r - 2}"/>'


def legend(x, y):
    out = []
    items = [("上流へ", "上流へ"), ("下流へ", "下流へ"), ("止まる", "止まる"), ("混在", "手前と奥で逆")]
    for kind, label in items:
        out.append(marker(kind, x, y - 4))
        out.append(text(x + 12, y, label, "t2", 12))
        x += 26 + 13 * len(label)
    return out


def read_obs():
    with open(DATA / "observations.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_tide():
    tide = {}
    with open(DATA / "harbor_tide_hourly.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tide.setdefault(r["日付"], []).append((int(r["時"]) * 60, float(r["港の推算潮位cm"])))
    return tide


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def smooth_path(pts):
    """点を Catmull-Rom でなめらかにつなぐ。"""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


# ---------------------------------------------------------------- 図1 境目
def fig_threshold(obs):
    W, H = 760, 300
    L, R, T, B = 80, 30, 70, 60
    rows = ["満", "浅い", "干潟"]
    xmin, xmax = 0, 260
    sx = lambda v: L + (v - xmin) / (xmax - xmin) * (W - L - R)
    rowy = {r: T + 20 + i * ((H - T - B - 40) / 2) for i, r in enumerate(rows)}

    out = svg_open(W, H, "港の潮位と、階段で見た水位の関係")
    out.append(text(20, 30, "港の潮位と、階段で見た水位", "t", 16, weight="bold"))
    out.append(text(20, 50, "干潟が出るか沈むかの境目は、港の推算潮位で 116〜132cm のあいだ", "t2", 12))
    out.append(f'<rect class="band" x="{sx(116):.1f}" y="{T}" width="{sx(132) - sx(116):.1f}" height="{H - T - B}"/>')
    out.append(text((sx(116) + sx(132)) / 2, T - 6, "境目", "t2", 11, "middle"))
    for v in range(0, 261, 50):
        out.append(f'<line class="grid" x1="{sx(v):.1f}" y1="{T}" x2="{sx(v):.1f}" y2="{H - B}"/>')
        out.append(text(sx(v), H - B + 18, str(v), "t2", 11, "middle"))
    out.append(text((L + W - R) / 2, H - 14, "港の推算潮位（cm）", "t2", 12, "middle"))
    for r in rows:
        out.append(text(L - 12, rowy[r] + 4, r, "t", 13, "end"))

    seen = {}
    for o in obs:
        if o["地点"] != "階段" or not o["水位の見た目"] in rows:
            continue
        v = float(o["港の推算潮位cm"])
        key = (o["水位の見た目"], round(v / 6))
        n = seen.get(key, 0)
        seen[key] = n + 1
        y = rowy[o["水位の見た目"]] + (n % 3 - 1) * 10
        out.append(f'<circle class="dot" cx="{sx(v):.1f}" cy="{y:.1f}" r="5"><title>{o["日付"]} {o["時刻"]}  {int(v)}cm  {o["水位の見た目"]}</title></circle>')
    out.append(text(sx(144) + 8, rowy["満"] + 18, "144（区分は仮）", "t2", 11))
    out.append("</svg>")
    (FIG / "threshold.svg").write_text("\n".join(out), encoding="utf-8")


# ---------------------------------------------------------------- 図2 折り返し
TURNS = {
    "2026-11-25": ("干潮", 12 * 60 + 4, 97),
    "2026-11-26": ("干潮", 12 * 60 + 46, 102),
    "2026-11-27": ("満潮", 8 * 60 + 1, 237),
}
WINDOWS = {
    "2026-11-25": (11 * 60 + 15, 13 * 60 + 45),
    "2026-11-26": (11 * 60 + 45, 14 * 60 + 15),
    "2026-11-27": (7 * 60 + 15, 9 * 60 + 45),
}
NOTES = {
    "2026-11-25": "流れが下流→上流に変わったのは、港の干潮の24〜46分後",
    "2026-11-26": "12:54は手前だけ上流へ（階段の影の渦かも）",
    "2026-11-27": "川全体が下流へ変わったのは、港の満潮の約27分後",
}


def fig_turns(obs, tide):
    W = 760
    PH = 200  # 1日ぶんの高さ
    L, R = 70, 30
    top = 90
    H = top + PH * len(TURNS) + 30
    span = 150

    out = svg_open(W, H, "港の潮の折り返しと、階段の流れの向き")
    out.append(text(20, 30, "港の潮が折り返してから、階段の流れが変わるまで", "t", 16, weight="bold"))
    out.append(text(20, 50, "線は港の推算潮位。下の列は、その時刻に階段で見た流れの向き（港の水位ではない）", "t2", 12))
    out += legend(24, 74)

    for i, (day, (kind, tmin, tval)) in enumerate(TURNS.items()):
        y0 = top + i * PH
        ct, cb = y0 + 24, y0 + PH - 82  # 潮位グラフの上下
        fy = y0 + PH - 50  # 流れの列
        w0, w1 = WINDOWS[day]
        sx = lambda m: L + (m - w0) / span * (W - L - R)
        vmin, vmax = 0, 260
        sy = lambda v: cb - (v - vmin) / (vmax - vmin) * (cb - ct)

        md = day[5:].replace("-", "/")
        out.append(text(20, y0 + 12, f"{md}（港の{kind} {tmin // 60}:{tmin % 60:02d}・{int(tval)}cm）", "t", 13, weight="bold"))
        out.append(text(W - R, y0 + 12, NOTES[day], "t2", 11.5, "end"))
        for v in (0, 100, 200):
            out.append(f'<line class="grid" x1="{L}" y1="{sy(v):.1f}" x2="{W - R}" y2="{sy(v):.1f}"/>')
            out.append(text(L - 8, sy(v) + 4, f"{v}", "t2", 10, "end"))
        for m in range(w0 - w0 % 30 + 30, w1 + 1, 30):
            out.append(f'<line class="grid" x1="{sx(m):.1f}" y1="{ct}" x2="{sx(m):.1f}" y2="{fy + 12}"/>')
            out.append(text(sx(m), fy + 36, f"{m // 60}:{m % 60:02d}", "t2", 10, "middle"))
        out.append(text(L - 8, fy + 4, "階段", "t2", 11, "end"))

        pts = [(m, v) for m, v in tide[day] if w0 - 60 <= m <= w1 + 60] + [(tmin, tval)]
        pts.sort()
        # 窓の外にはみ出した分は clipPath で切る
        cid = f"c{i}"
        out.append(f'<clipPath id="{cid}"><rect x="{L}" y="{ct - 4}" width="{W - L - R}" height="{cb - ct + 8}"/></clipPath>')
        out.append(f'<path class="curve" clip-path="url(#{cid})" d="{smooth_path([(sx(m), sy(v)) for m, v in pts])}"/>')
        out.append(f'<line class="turn" x1="{sx(tmin):.1f}" y1="{ct}" x2="{sx(tmin):.1f}" y2="{fy + 12}"/>')
        out.append(text(sx(tmin) + 4, (ct + 10) if kind == "干潮" else (cb - 4), f"港の{kind}", "t2", 10))

        k = 0
        for o in obs:
            if o["日付"] != day or o["地点"] != "階段" or not o["流れ（要約）"]:
                continue
            m = hm(o["時刻"])
            if not (w0 <= m <= w1):
                continue
            k += 1
            out.append(f'<g><title>{o["時刻"]} {o["流れの向き（くわしく）"]}</title>{marker(o["流れ（要約）"], sx(m), fy)}</g>')
            out.append(text(sx(m), fy - 12 if k % 2 else fy + 20, o["時刻"], "t2", 9.5, "middle"))

    out.append("</svg>")
    (FIG / "turns.svg").write_text("\n".join(out), encoding="utf-8")


# ---------------------------------------------------------------- 図3 見取り図
def fig_river():
    W, H = 760, 300
    y = 150
    xs = {"港": 50, "階段": 320, "青い橋": 420, "早瀬": 510, "上の滝": 620}
    out = svg_open(W, H, "みんなの川の見取り図（縮尺はでたらめ）")
    out.append(text(20, 30, "見取り図", "t", 16, weight="bold"))
    out.append(text(20, 50, "縮尺はでたらめ。港から上の滝まではおよそ13km、階段から上の滝までは歩いて700mくらい", "t2", 12))

    fx = xs["上の滝"]
    out.append(f'<path class="river" d="M{xs["港"]},{y} L{fx + 90},{y}"/>')
    for dx in (0, 10):
        out.append(f'<path class="arrowline" d="M{180 + dx},{y - 14} l-8,28"/>')
    out.append(text(185, y + 34, "…約12km…", "t2", 11, "middle"))
    out.append(f'<path class="arrowline" d="M{fx},{y - 26} L{fx},{y + 26}" stroke-width="3"/>')

    # 潮が届く範囲
    out.append(f'<path class="reach" d="M{xs["港"]},{y - 50} L{fx - 4},{y - 50}"/>')
    out.append(f'<path class="reach" d="M{fx - 4},{y - 56} L{fx - 4},{y - 44}"/>')
    out.append(text((xs["港"] + fx) / 2, y - 60, "満潮のとき、潮がとどく範囲（上の滝の足元まで）", "t", 12, "middle"))

    # (名前, 説明の行, 説明のそろえ方)
    labels = {
        "港": ("港", ["潮位の基準"], "middle"),
        "階段": ("階段", ["いつもの定位置", "湧き口のそば"], "middle"),
        "青い橋": ("青い橋", [], "middle"),
        "早瀬": ("早瀬", ["干潮で白く波立ち", "満潮で沈む"], "middle"),
        "上の滝": ("上の滝", ["潮はここを", "越えない"], "start"),
    }
    for k, x in xs.items():
        name, subs, anchor = labels[k]
        if k != "上の滝":
            out.append(f'<circle class="dot" cx="{x}" cy="{y}" r="6"/>')
        tx = x if anchor == "middle" else x + 10
        out.append(text(tx, y + 28, name, "t", 13, anchor, "bold"))
        for j, sub in enumerate(subs):
            out.append(text(tx, y + 46 + j * 15, sub, "t2", 10.5, anchor))

    # 上流から来る水（滝を越えて落ちてくる）
    out.append(f'<path class="arrowline" d="M{fx + 80},{y - 14} L{fx + 8},{y - 14}"/>')
    out.append(f'<path class="arrowline" d="M{fx + 14},{y - 19} L{fx + 8},{y - 14} L{fx + 14},{y - 9}"/>')
    out.append(text(fx + 84, y - 10, "上流の川", "t2", 10.5))
    # 送られてくる水（滝の少し下で出てくる）
    ax = fx - 30
    out.append(f'<path class="arrowline" d="M{ax},{y + 95} L{ax},{y + 10}"/>')
    out.append(f'<path class="arrowline" d="M{ax - 5},{y + 16} L{ax},{y + 10} L{ax + 5},{y + 16}"/>')
    out.append(text(ax, y + 112, "送られてくる水（出口は候補）", "t2", 10.5, "middle"))
    out.append("</svg>")
    (FIG / "river.svg").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    FIG.mkdir(exist_ok=True)
    obs = read_obs()
    tide = read_tide()
    fig_threshold(obs)
    fig_turns(obs, tide)
    fig_river()
    print("figures/ を作り直しました")
