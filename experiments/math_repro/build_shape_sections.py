#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
生成「形状指标」系列图解（⑩⑪⑫⑬⑭），写回官网 math_graph.html，并导出轻量 CSV 数据集。

依赖（同目录）：
    shape_stats_4_4_2.json / shape_stats_4_4_3.json / shape_stats_3_4_2.json ...
    phi_samples_4_4_2.json

用法：
    D:\python\python.exe build_shape_sections.py
"""
import os, sys, json, math, io, re

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = r"E:\program_project\other\wkbddtest\GatenneaSliderWeb"
DATA = os.path.join(WEB, "data")

# ---------------------------------------------------------------- 配色
BG = "#0d0d0f"
C_TEXT = "#e6e6e6"
C_DIM = "#8a8a8a"
C_FAINT = "#6f6f78"
C_GRID = "#2a2a32"
C_AXIS = "#3a3a42"
C_GREEN = "#87cf92"
C_BLUE = "#4696c8"
C_PURPLE = "#a98bd8"
C_RED = "#ff5a4a"
C_ORANGE = "#e08a4a"
C_YELLOW = "#e0c46a"
C_BLOCK = "#3c96c8"          # 游戏真实滑块色
C_BLOCK_DEAD = "#8a4a52"


def rate_color(p):
    if p >= 99.5:
        return C_GREEN
    if p >= 98.0:
        return C_YELLOW
    if p >= 50.0:
        return C_ORANGE
    return C_RED


def fmt(n):
    return f"{n:,}"


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def board_cells(rows):
    """返回 (cells, h, w)，cells 为 [(r,c)] 相对坐标。"""
    nzr = [i for i, v in enumerate(rows) if v]
    if not nzr:
        return [], 0, 0
    rmin, rmax = min(nzr), max(nzr)
    cmax = 0
    for v in rows:
        if v:
            cmax = max(cmax, v.bit_length() - 1)
    cmin = 16
    for v in rows:
        if v:
            c = 0
            while not ((v >> c) & 1):
                c += 1
            cmin = min(cmin, c)
    cells = [(r - rmin, c - cmin)
             for r in range(rmin, rmax + 1)
             for c in range(cmin, cmax + 1) if (rows[r] >> c) & 1]
    return cells, (rmax - rmin + 1), (cmax - cmin + 1)


def draw_board(x, y, box_w, box_h, rows, cell_fill=C_BLOCK, gap=0.6):
    """在 (x,y) 处的 box_w × box_h 区域内居中画棋盘，返回 svg 片段。"""
    cells, h, w = board_cells(rows)
    if not cells:
        return ""
    cs = min((box_w - 2) / max(w, 1), (box_h - 2) / max(h, 1))
    cs = max(cs, 1.2)
    gw, gh = cs * w, cs * h
    ox = x + (box_w - gw) / 2
    oy = y + (box_h - gh) / 2
    out = []
    for (r, c) in cells:
        out.append(f'<rect x="{ox + c*cs + gap/2:.1f}" y="{oy + r*cs + gap/2:.1f}" '
                   f'width="{cs - gap:.1f}" height="{cs - gap:.1f}" rx="{min(1.2, cs/5):.1f}" fill="{cell_fill}"/>')
    return "".join(out)


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h = w, h
        self.b = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">']

    def add(self, s):
        self.b.append(s)

    def text(self, x, y, s, size=11, fill=C_TEXT, anchor="start", weight="normal"):
        self.b.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
                      f'fill="{fill}" font-weight="{weight}">{esc(s)}</text>')

    def rect(self, x, y, w, h, fill, rx=2, stroke=None, sw=1.0, extra=""):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.b.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w,0.1):.1f}" height="{max(h,0.1):.1f}" '
                      f'rx="{rx}" fill="{fill}"{st}{extra}/>')

    def line(self, x1, y1, x2, y2, stroke=C_AXIS, sw=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.b.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                      f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def out(self):
        return "\n".join(self.b) + "\n</svg>"


# ---------------------------------------------------------------- 重叠校验
def check_overlap(svg_text, name):
    items = []
    for m in re.finditer(r"<text x=\"([-\d.]+)\" y=\"([-\d.]+)\" text-anchor=\"(\w+)\" "
                         r"font-size=\"([\d.]+)\"[^>]*>(.*?)</text>", svg_text):
        x, y = float(m.group(1)), float(m.group(2))
        anchor, fs = m.group(3), float(m.group(4))
        s = m.group(5)
        wid = sum(1.0 if ord(ch) > 0x2E80 else 0.55 for ch in s) * fs
        if anchor == "middle":
            x0 = x - wid / 2
        elif anchor == "end":
            x0 = x - wid
        else:
            x0 = x
        items.append((x0, y - fs * 0.82, x0 + wid, y + fs * 0.18, s))
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_text)
    W, H = float(vb.group(1)), float(vb.group(2))
    bad = 0
    for it in items:
        if it[0] < -0.5 or it[2] > W + 0.5 or it[1] < -0.5 or it[3] > H + 0.5:
            print(f"  [越界] {name}: {it[4]!r} box=({it[0]:.1f},{it[1]:.1f},{it[2]:.1f},{it[3]:.1f})")
            bad += 1
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5 and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5:
                print(f"  [重叠] {name}: {a[4]!r} × {b[4]!r}")
                bad += 1
    print(f"  校验 {name}: 文字 {len(items)} 个，重叠/越界 {bad} 处")
    return bad


# ---------------------------------------------------------------- 数据
def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    st2 = load("shape_stats_4_4_2.json")
    st3 = load("shape_stats_4_4_3.json")
    smp = load("phi_samples_4_4_2.json")["buckets"]

    # ---------------- ⑩ 体检图：挑一个典型局面 ----------------
    cand = None
    best_score = -1
    for ph, lst in smp.items():
        for r in lst:
            if not r["solvable"] or r["dist"] is None:
                continue
            if not (4 <= r["h"] <= 7 and 4 <= r["w"] <= 7):
                continue
            if not (9 <= r["overlap"] <= 11):
                continue
            sc = -abs(r["dist"] - 9) * 2 - abs(r["phi"] - 16) * 0.3
            if sc > best_score:
                best_score, cand = sc, r
    if cand is None:
        cand = smp["16"][0]
    print("体检图选用局面:", {k: cand[k] for k in ("phi", "overlap", "adj", "h", "w", "dist")})

    # 最佳 4×4 窗口位置
    rows = cand["rows"]
    cells, Hh, Ww = board_cells(rows)
    nzr = [i for i, v in enumerate(rows) if v]
    rmin = min(nzr)
    cmax = 0
    for v in rows:
        cmax = max(cmax, v.bit_length() - 1)
    cmin = 16
    for v in rows:
        if v:
            c = 0
            while not ((v >> c) & 1):
                c += 1
            cmin = min(cmin, c)
    bestw, bestv = None, -1
    for r0 in range(rmin - 3, rmax := max(nzr) + 1):
        for c0 in range(cmin - 3, cmax + 1):
            v = sum(1 for r in range(r0, r0 + 4) for c in range(c0, c0 + 4)
                    if 0 <= r < 16 and 0 <= c < 16 and (rows[r] >> c) & 1)
            if v > bestv:
                bestv, bestw = v, (r0, c0)
    print("最佳窗口", bestw, bestv)

    svgs = {}

    # ================= ⑩ 体检 =================
    s = Svg(680, 356, "给一个局面做体检：边界盒、聚拢度、剖面缺陷三个指标")
    s.text(20, 26, "同一个局面，用三种方式「体检」", 13.5, C_TEXT)
    s.text(20, 44, "下面三幅图用的是同一个真实局面（4×4 二级），只是量的角度不同", 11, C_DIM)
    panel_y = 58
    panel_h = 275
    BH = 130                      # 棋盘绘制区高度
    # --- 面板 1：边界盒
    px, pw = 14, 212
    s.rect(px, panel_y, pw, panel_h, "#121217", rx=10, stroke="#1e1e26")
    s.text(px + 12, panel_y + 24, "① 边界盒：它占了多大地方", 12, C_GREEN)
    s.add(draw_board(px + 12, panel_y + 30, pw - 24, BH, rows))
    csz = min((pw - 24 - 2) / max(Ww, 1), (BH - 2) / max(Hh, 1))
    csz = max(csz, 1.2)
    ox = px + 12 + (pw - 24 - csz * Ww) / 2
    oy = panel_y + 30 + (BH - csz * Hh) / 2
    s.rect(ox - 3, oy - 3, csz * Ww + 6, csz * Hh + 6, "none", rx=3,
           stroke=C_BLUE, sw=1.4, extra=' stroke-dasharray="5 3"')
    s.text(px + 12, panel_y + 214, f"高 {cand['h']} × 宽 {cand['w']}", 11.5, C_BLUE)
    s.text(px + 12, panel_y + 232, "＝ 能框住它的最小矩形", 10.5, C_DIM)
    s.text(px + 12, panel_y + 250, "框越大、越瘦长，说明越散", 10.5, C_DIM)
    # --- 面板 2：聚拢度
    px2 = px + pw + 12
    s.rect(px2, panel_y, pw, panel_h, "#121217", rx=10, stroke="#1e1e26")
    s.text(px2 + 12, panel_y + 24, "② 聚拢度：离「整块」有多近", 12, C_GREEN)
    s.add(draw_board(px2 + 12, panel_y + 30, pw - 24, BH, rows))
    ox2 = px2 + 12 + (pw - 24 - csz * Ww) / 2
    oy2 = panel_y + 30 + (BH - csz * Hh) / 2
    if bestw:
        wx = ox2 + (bestw[1] - cmin) * csz
        wy = oy2 + (bestw[0] - rmin) * csz
        s.rect(wx - 2, wy - 2, 4 * csz + 4, 4 * csz + 4, "none", rx=3, stroke=C_GREEN, sw=1.8)
    # 图例放在棋盘下方，避免压住棋盘
    s.rect(px2 + 12, panel_y + 180, 13, 13, "none", rx=2, stroke=C_GREEN, sw=1.6)
    s.text(px2 + 31, panel_y + 190, "绿框＝4×4 窗口", 9.5, C_DIM)
    s.text(px2 + 12, panel_y + 214, f"{cand['overlap']} / 16 = 聚拢度", 11.5, C_GREEN)
    s.text(px2 + 12, panel_y + 232, "＝ 一个 4×4 的框最多能盖住几格", 10.5, C_DIM)
    s.text(px2 + 12, panel_y + 250, "盖满 16 格，就正好是还原态", 10.5, C_DIM)
    # --- 面板 3：剖面缺陷
    px3 = px2 + pw + 12
    s.rect(px3, panel_y, pw, panel_h, "#121217", rx=10, stroke="#1e1e26")
    s.text(px3 + 12, panel_y + 24, "③ 剖面缺陷 Φ：行列歪不歪", 12, C_GREEN)
    s.add(draw_board(px3 + 10, panel_y + 30, 80, BH, rows))
    # 行计数条
    rowcnt = [bin(v).count("1") for v in rows]
    rc = [rowcnt[i] for i in range(rmin, max(nzr) + 1)]
    bx = px3 + 96
    by = panel_y + 52
    ru = 30.0 / max(max(rc) if rc else 4, 4)          # 行条比例：4 格 = 30px
    for i, v in enumerate(rc):
        s.rect(bx, by + i * 14, v * ru, 8, C_BLUE, rx=1.5)
        s.text(bx + v * ru + 6, by + i * 14 + 7.5, str(v), 9, C_DIM)
    s.line(bx + 4 * ru, by - 4, bx + 4 * ru, by + len(rc) * 14 + 2, C_GREEN, 1.0, "3 3")
    s.text(bx, by - 9, "每行格数（虚线=4）", 9.5, C_DIM)
    # 列计数条
    colcnt = [sum((rows[r] >> c) & 1 for r in range(16)) for c in range(16)]
    cc = [colcnt[c] for c in range(cmin, cmax + 1)]
    cx0 = px3 + 10
    cy0 = panel_y + 172
    cu = 20.0 / max(max(cc) if cc else 4, 4)          # 列条比例：4 格 = 20px
    for j, v in enumerate(cc):
        cxx = cx0 + 4 + j * 15
        s.rect(cxx, cy0 + (20 - v * cu), 11, max(v * cu, 1.5), C_PURPLE, rx=1.5)
        s.text(cxx + 5.5, cy0 + 32, str(v), 8.5, C_DIM, anchor="middle")
    s.line(cx0, cy0 + 20 - 4 * cu, cx0 + 4 + len(cc) * 15, cy0 + 20 - 4 * cu, C_GREEN, 1.0, "3 3")
    s.text(cx0 + 4 + len(cc) * 15 + 8, cy0 + 24 - 4 * cu, "列", 9, C_DIM)
    s.text(px3 + 12, panel_y + 232, "每行每列离「整齐」差多少", 10.5, C_DIM)
    s.text(px3 + 12, panel_y + 252, f"全部加起来 ＝ Φ ＝ {cand['phi']}", 11.5, C_PURPLE)
    svgs["checkup"] = s.out()

    # ================= ⑪ 聚拢度 =================
    def gather_chart(st, y0, title, note):
        rows_ = sorted(st["gather"], key=lambda r: r["overlap"])
        K = st["K"]
        x0, x1 = 76, 656
        base = y0 + 150
        top = y0 + 20
        n = len(rows_)
        bw = (x1 - x0) / n * 0.72
        pitch = (x1 - x0) / n
        out = []
        for i, r in enumerate(rows_):
            p = 100 * r["solvable"] / r["count"]
            cx = x0 + pitch * (i + 0.5)
            hgt = (base - top) * p / 100
            col = rate_color(p)
            out.append(f'<rect x="{cx - bw/2:.1f}" y="{base - hgt:.1f}" width="{bw:.1f}" '
                       f'height="{hgt:.1f}" rx="2" fill="{col}"/>')
            out.append(f'<text x="{cx:.1f}" y="{base - hgt - 5:.1f}" text-anchor="middle" '
                       f'font-size="9" fill="{col}">{p:.0f}%</text>')
            out.append(f'<text x="{cx:.1f}" y="{base + 14:.1f}" text-anchor="middle" '
                       f'font-size="10" fill="{C_DIM}">{r["overlap"]}</text>')
            out.append(f'<text x="{cx:.1f}" y="{base + 28:.1f}" text-anchor="middle" '
                       f'font-size="8.5" fill="{C_FAINT}">{r["count"]}</text>')
        return dict(rows=rows_, x0=x0, x1=x1, base=base, top=top, parts=out, K=K)

    s = Svg(680, 524, "聚拢度越高的局面越容易还原")
    s.text(20, 28, "聚拢度 vs 可还原率（柱越高＝越容易还原）", 13.5, C_TEXT)
    # 上：4×4 二级
    s.text(20, 52, "4×4 二级（559,832 个局面）", 12, C_BLUE)
    g1 = gather_chart(st2, 58, "", "")
    for pct in (0, 25, 50, 75, 100):
        yy = g1["base"] - (g1["base"] - g1["top"]) * pct / 100
        s.line(g1["x0"], yy, g1["x1"], yy, C_GRID)
        s.text(g1["x0"] - 8, yy + 4, f"{pct}%", 10, C_DIM, anchor="end")
    s.line(g1["x0"], g1["base"], g1["x1"], g1["base"], C_AXIS, 1.2)
    for p in g1["parts"]:
        s.add(p)
    s.text(20, g1["base"] + 46, "柱下方：聚拢度（5~16）　·　再下一行：这一档有多少个局面", 10.5, C_DIM)
    # 下：4×4 三级
    s.text(20, g1["base"] + 78, "4×4 三级（24,605 个局面）：整体都更难，但「越散越危险」同样成立", 12, C_BLUE)
    g2 = gather_chart(st3, g1["base"] + 84, "", "")
    for pct in (0, 25, 50, 75, 100):
        yy = g2["base"] - (g2["base"] - g2["top"]) * pct / 100
        s.line(g2["x0"], yy, g2["x1"], yy, C_GRID)
        s.text(g2["x0"] - 8, yy + 4, f"{pct}%", 10, C_DIM, anchor="end")
    s.line(g2["x0"], g2["base"], g2["x1"], g2["base"], C_AXIS, 1.2)
    for p in g2["parts"]:
        s.add(p)
    s.text(20, 504, "两图横轴都是聚拢度（16 = 正好是还原态那块 4×4 实心矩形）；纵轴是这一档局面里能还原回去的比例。", 11, C_DIM)
    svgs["gather"] = s.out()

    # ================= ⑫ Φ 生死线 =================
    def phi_chart(st, y0, title, h=178):
        rows_ = sorted(st["phi"], key=lambda r: r["phi"])
        x0, x1 = 78, 656
        base = y0 + h - 34
        top = y0 + 26
        n = len(rows_)
        pitch = (x1 - x0) / n
        bw = pitch * 0.68
        mx = max(math.log10(r["count"] + 1) for r in rows_)
        parts = []
        for i, r in enumerate(rows_):
            p = 100 * r["solvable"] / r["count"]
            cx = x0 + pitch * (i + 0.5)
            hv = (base - top) * math.log10(r["count"] + 1) / mx
            col = rate_color(p)
            parts.append(f'<rect x="{cx - bw/2:.1f}" y="{base - hv:.1f}" width="{bw:.1f}" '
                         f'height="{hv:.1f}" rx="2" fill="{col}"/>')
            parts.append(f'<text x="{cx:.1f}" y="{base + 13:.1f}" text-anchor="middle" '
                         f'font-size="9.5" fill="{C_DIM}">{r["phi"]}</text>')
        return dict(rows=rows_, x0=x0, x1=x1, base=base, top=top, parts=parts, mx=mx, pitch=pitch)

    s = Svg(680, 470, "剖面缺陷 Φ 到 32 时，可还原率断崖式崩塌")
    s.text(20, 28, "剖面缺陷 Φ vs 可还原率（4×4 二级）——一条几乎完美的生死线", 13.5, C_TEXT)
    s.text(20, 46, "柱高＝这一档有多少个局面（纵轴每格 ×10）　·　柱色＝这一档能还原回去的比例", 10.5, C_DIM)
    c1 = phi_chart(st2, 66, "", h=182)
    # 对数刻度线
    for v in (1, 10, 100, 1000, 10000, 100000):
        yy = c1["base"] - (c1["base"] - c1["top"]) * math.log10(v + 1) / c1["mx"]
        s.line(c1["x0"], yy, c1["x1"], yy, C_GRID)
        s.text(c1["x0"] - 8, yy + 4, ("1" if v == 1 else fmt(v)), 9.5, C_DIM, anchor="end")
    s.line(c1["x0"], c1["base"], c1["x1"], c1["base"], C_AXIS, 1.2)
    for p in c1["parts"]:
        s.add(p)
    # 生死线
    idx = [i for i, r in enumerate(c1["rows"]) if r["phi"] == 32]
    if idx:
        lx = c1["x0"] + c1["pitch"] * (idx[0] + 0.5) - c1["pitch"] / 2
        s.line(lx, c1["top"] - 6, lx, c1["base"], C_RED, 1.6, "6 4")
        s.text(lx - 6, c1["top"] + 10, "生死线 Φ=31", 10.5, C_RED, anchor="end")
    lo = [r for r in c1["rows"] if r["phi"] <= 30]
    hi = [r for r in c1["rows"] if r["phi"] >= 32]
    lt = sum(r["count"] for r in lo)
    lb = sum(r["count"] - r["solvable"] for r in lo)
    ht = sum(r["count"] for r in hi)
    hb = sum(r["count"] - r["solvable"] for r in hi)
    s.text(c1["x1"], c1["top"] - 26,
           f"Φ≤30：{lt:,} 个里只有 {lb:,} 个回不来（{100*(lt-lb)/lt:.2f}%）", 10.5, C_GREEN, anchor="end")
    s.text(c1["x1"], c1["top"] - 10,
           f"Φ≥32：{ht:,} 个里 {hb:,} 个回不来（只剩 {100*(ht-hb)/ht:.1f}%）", 10.5, C_RED, anchor="end")
    s.text(20, c1["base"] + 32, "Φ（剖面缺陷）＝ 每行、每列的格子数离「整齐的 4×4」差多少，全部加起来；0＝正好是还原态那块矩形。", 11, C_DIM)
    # 三级对照
    s.text(20, c1["base"] + 74, "反例：4×4 三级里这条线失灵了——整体都难，Φ 就分不出高下了", 12, C_BLUE)
    c2 = phi_chart(st3, c1["base"] + 80, "", h=150)
    mx2 = c2["mx"]
    for v in (1, 10, 100, 1000, 10000):
        yy = c2["base"] - (c2["base"] - c2["top"]) * math.log10(v + 1) / mx2
        s.line(c2["x0"], yy, c2["x1"], yy, C_GRID)
        s.text(c2["x0"] - 8, yy + 4, ("1" if v == 1 else fmt(v)), 9.5, C_DIM, anchor="end")
    s.line(c2["x0"], c2["base"], c2["x1"], c2["base"], C_AXIS, 1.2)
    for p in c2["parts"]:
        s.add(p)
    s.text(20, 462, "同一块板，一次推得越远（s 越大），「形状好不好」就越说了不算——困难另有来源。", 11, C_DIM)
    svgs["phi"] = s.out()

    # ================= ⑬ 边界盒地图 =================
    cells = {(r["h"], r["w"]): r for r in st2["bbox"]}
    hs = sorted({h for h, w in cells})
    ws = sorted({w for h, w in cells})
    gx0, gy0 = 74, 80
    cw = (654 - gx0) / len(ws)
    ch = 32.0
    gridH = ch * len(hs)
    ax_lab_y = gy0 + gridH + 17          # 「宽」轴标签
    ann_y = gy0 + gridH + 36             # 宽 2 格 标注
    ly = gy0 + gridH + 80                # 色带图例
    y2 = ly + 50                         # 第二幅标题
    btop = y2 + 32
    bh2 = 74.0
    bbase = btop + bh2
    cap_y = bbase + 46
    s = Svg(680, int(cap_y + 22), "边界盒热力图：格子颜色是这类外形能还原回去的比例，2 格宽那一列整列全红")
    s.text(20, 28, "边界盒热力图：一格＝一种「高×宽」外形，颜色＝这类局面能还原回去的比例", 13.5, C_TEXT)
    s.text(20, 45, "「4×4 二级」指还原态是 4×4 的 16 格、一次推 2 格；打乱后会摊成各种尺寸的外形", 10.5, C_DIM)
    s.text(20, 59, "格内上一行是比例、下一行是这种外形的局面数；深色空格＝这种外形根本不存在", 10.5, C_DIM)
    for j, w in enumerate(ws):
        s.text(gx0 + cw * (j + 0.5), gy0 - 7, str(w), 10, C_DIM, anchor="middle")
        for i, h in enumerate(hs):
            r = cells.get((h, w))
            x = gx0 + cw * j
            y = gy0 + ch * i
            if r is None:
                s.rect(x + 1.5, y + 1.5, cw - 3, ch - 3, "#15151b", rx=3)
                continue
            p = 100 * r["solvable"] / r["count"]
            col = rate_color(p)
            s.rect(x + 1.5, y + 1.5, cw - 3, ch - 3, col, rx=3)
            s.text(x + cw / 2, y + ch / 2 - 1.5, f"{p:.2f}%", 9.8, "#101014", anchor="middle")
            s.text(x + cw / 2, y + ch / 2 + 10.5, fmt(r["count"]), 7.8, "#101014", anchor="middle")
            if p < 1:
                s.rect(x + 1.5, y + 1.5, cw - 3, ch - 3, "none", rx=3, stroke=C_RED, sw=2.2)
    for i, h in enumerate(hs):
        s.text(gx0 - 9, gy0 + ch * (i + 0.5) + 3.5, str(h), 10, C_DIM, anchor="end")
    s.text(20, gy0 + gridH / 2, "高", 11, C_DIM)
    s.text(gx0 + cw * len(ws) / 2, ax_lab_y, "宽（格）", 11, C_DIM, anchor="middle")
    # 标注 2 宽列
    if 2 in ws:
        j2 = ws.index(2)
        x2 = gx0 + cw * j2
        s.rect(x2 - 1, gy0 - 3, cw + 2, gridH + 6, "none", rx=5, stroke=C_RED, sw=2.2)
        s.text(x2 + cw / 2, ann_y, "宽 2 格：264 个局面", 10.5, C_RED, anchor="middle")
    # 色带图例（分段；宽度只为了看得清，刻度标的是真实阈值）
    bar_x, bar_w, bar_h = gx0, 372, 13
    segs = [(0, 50, C_RED, 0.30), (50, 98, C_ORANGE, 0.30),
            (98, 99.5, C_YELLOW, 0.20), (99.5, 100, C_GREEN, 0.20)]
    cx = bar_x
    for lo, hi, col, frac in segs:
        wseg = bar_w * frac
        s.rect(cx, ly - bar_h, wseg, bar_h, col, rx=2)
        cx += wseg
    for t, lab in [(0, "0%"), (0.30, "50%"), (0.60, "98%"), (0.80, "99.5%"), (1.0, "100%")]:
        if t == 0:
            s.text(bar_x, ly + 15, lab, 9.5, C_DIM, anchor="middle")
        elif t == 1.0:
            s.text(bar_x + bar_w, ly + 15, lab, 9.5, C_DIM, anchor="middle")
        else:
            s.text(bar_x + bar_w * t, ly + 15, lab, 9.5, C_DIM, anchor="middle")
    s.text(bar_x + bar_w + 16, ly - 1, "格子的颜色，按这把尺子读", 10.5, C_DIM)

    # 按最窄边汇总
    import collections
    agg = collections.defaultdict(lambda: [0, 0])
    for r in st2["bbox"]:
        k = min(r["h"], r["w"])
        agg[k][0] += r["count"]
        agg[k][1] += r["count"] - r["solvable"]
    s.text(20, y2, "换个看法：只看边界盒「最窄的那条边」有几格，规律最干净", 12.5, C_TEXT)
    ks = sorted(agg)
    bx0 = 60
    pitch = (656 - bx0) / len(ks)
    bw2 = pitch * 0.74
    for i, k in enumerate(ks):
        tot, bad = agg[k]
        p = 100 * (tot - bad) / tot
        x = bx0 + pitch * i
        col = rate_color(p)
        s.rect(x, btop, bw2, bh2, col, rx=3)
        s.text(x + bw2 / 2, btop + bh2 / 2 - 1, ("0%" if p == 0 else f"{p:.2f}%"),
               12, "#101014", anchor="middle")
        s.text(x + bw2 / 2, btop + bh2 / 2 + 14, fmt(tot), 9, "#101014", anchor="middle")
        s.text(x + bw2 / 2, bbase + 16, f"{k} 格", 10.5, C_DIM, anchor="middle")
        s.text(x + bw2 / 2, bbase + 30, f"{tot:,} 个", 9, C_FAINT, anchor="middle")
        if p < 1:
            s.rect(x, btop, bw2, bh2, "none", rx=3, stroke=C_RED, sw=2.2)
            s.text(x + bw2 / 2, btop - 7, "一个都回不去", 9.5, C_RED, anchor="middle")
    s.text(20, cap_y, "每一段＝最窄边是这个格数的全部局面；颜色同上一条尺子，段内数字＝可还原比例／局面数", 11, C_DIM)
    svgs["bbox"] = s.out()

    # ================= ⑭ 真实形状画廊 =================
    picks = [0, 4, 8, 12, 16, 20, 24, 30, 32, 34]
    s = Svg(680, 430, "真实局面画廊：从最整齐到最歪，2 格宽的蛇形必死")
    s.text(20, 28, "真实局面画廊：按 Φ 从「最整齐」排到「最歪」", 13.5, C_TEXT)
    s.text(20, 46, "每一个都是完整枚举里真实存在的局面；蓝块是滑块，红框＝回不来", 10.5, C_DIM)
    n2 = 5
    pwid = 128
    phgt = 128
    for i, ph in enumerate(picks):
        lst = smp.get(str(ph))
        if not lst:
            continue
        # 优先展示「回不来」的（更能说明问题），否则取可还原的
        rec = next((x for x in lst if not x["solvable"]), lst[0])
        col = i % n2
        row = i // n2
        x = 14 + col * pwid
        y = 56 + row * 176
        dead = not rec["solvable"]
        s.rect(x, y, pwid - 8, phgt, "#121217", rx=8,
               stroke=(C_RED if dead else "#1e1e26"), sw=(1.6 if dead else 1.0))
        s.add(draw_board(x + 8, y + 8, pwid - 24, phgt - 26, rec["rows"],
                         cell_fill=(C_BLOCK_DEAD if dead else C_BLOCK)))
        s.text(x + 6, y + phgt + 16, f"Φ = {rec['phi']}", 11, C_TEXT)
        s.text(x + 6, y + phgt + 31, f"聚拢 {rec['overlap']}/16　边盒 {rec['h']}×{rec['w']}", 9.5, C_DIM)
        tag = "回不来" if dead else (f"{rec['dist']} 步还原")
        s.text(x + 6, y + phgt + 45, tag, 10.5, (C_RED if dead else C_GREEN))
    s.text(20, 424, "Φ 到 32 以后出现的全是「2 格宽的蛇」：它们一个都回不去，也没有一步可走的路。", 11.5, C_DIM)
    svgs["gallery"] = s.out()

    # ---------------- 校验 ----------------
    print("\n=== SVG 文字重叠校验 ===")
    tot_bad = 0
    for k, v in svgs.items():
        tot_bad += check_overlap(v, k)
    print(f"合计问题 {tot_bad} 处")

    # ---------------- 导出轻量数据集 ----------------
    os.makedirs(DATA, exist_ok=True)
    import csv
    files = {
        "shape_phi.csv": ["puzzle", "phi", "count", "solvable", "mean_dist"],
        "shape_gather.csv": ["puzzle", "overlap", "count", "solvable", "mean_dist"],
        "shape_bbox.csv": ["puzzle", "h", "w", "count", "solvable", "mean_dist"],
    }
    all_stats = {}
    for fn in os.listdir(HERE):
        if fn.startswith("shape_stats_") and fn.endswith(".json"):
            d = load(fn)
            all_stats[d["puzzle"]] = d
    with open(os.path.join(DATA, "shape_phi.csv"), "w", newline="", encoding="utf-8") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(files["shape_phi.csv"])
        for pz, d in sorted(all_stats.items()):
            for r in sorted(d["phi"], key=lambda x: x["phi"]):
                wcsv.writerow([pz, r["phi"], r["count"], r["solvable"], r["mean_dist"]])
    with open(os.path.join(DATA, "shape_gather.csv"), "w", newline="", encoding="utf-8") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(files["shape_gather.csv"])
        for pz, d in sorted(all_stats.items()):
            for r in sorted(d["gather"], key=lambda x: x["overlap"]):
                wcsv.writerow([pz, r["overlap"], r["count"], r["solvable"], r["mean_dist"]])
    with open(os.path.join(DATA, "shape_bbox.csv"), "w", newline="", encoding="utf-8") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(files["shape_bbox.csv"])
        for pz, d in sorted(all_stats.items()):
            for r in sorted(d["bbox"], key=lambda x: (x["h"], x["w"])):
                wcsv.writerow([pz, r["h"], r["w"], r["count"], r["solvable"], r["mean_dist"]])
    with open(os.path.join(DATA, "phi_samples_4x4x2.json"), "w", encoding="utf-8") as f:
        json.dump({"puzzle": "4x4x2", "note": "按剖面缺陷 Φ 分档的真实棋盘样本；rows 为 16 个 u16 行位掩码",
                   "buckets": {k: smp[k] for k in sorted(smp, key=lambda x: int(x))}},
                  f, ensure_ascii=False, separators=(",", ":"))
    print("\n数据集已写出到", DATA)

    # ---------------- 组装 HTML ----------------
    def wrap(label, svg, caption=""):
        return (f'        <div class="diag">\n          {svg}\n        </div>\n')

    g = st2["gather"][0]
    frag = f'''      <!-- SHAPE_SECTIONS_BEGIN -->
      <!-- 10. 三个形状指标 -->
      <div class="card">
        <h2>⑩ 给局面做个体检：三个能算出来的形状指标</h2>
        <p>
          前面说的都是「局面之间怎么走」。现在换个角度：<strong>光看一个局面的形状，能不能猜出它危不危险？</strong>
          我们给全部 559,832 个局面各算了三个指标——它们都不看走法，只看外形：
        </p>
        <div class="diag">
          {svgs["checkup"]}
        </div>
        <p>
          <strong>边界盒</strong>＝能框住它的最小矩形有多大；<strong>聚拢度</strong>＝拿一个 4×4 的框去套，最多能盖住几格（16 格盖满就是还原态）；
          <strong>剖面缺陷（记作 Φ）</strong>＝数一数每行每列有几个格子，看它们离「整齐的 4×4」偏了多少，把偏差全部加起来，0 就表示形状正好是还原态那块矩形。
          这三个数都不依赖位置，纯粹是「这个形状长得怎么样」。
        </p>
      </div>

      <!-- 11. 聚拢度 -->
      <div class="card">
        <h2>⑪ 聚拢度：越「团」的局面越安全，散到一定程度就开始掉队</h2>
        <p>
          把全部局面按聚拢度分成 12 档，看看每一档里有多少能还原回去：
        </p>
        <div class="diag">
          {svgs["gather"]}
        </div>
        <p>
          规律很清楚：聚拢度<strong>中等以上（7 格往上）几乎全体安全</strong>，可还原率稳定在 99% 上下；
          真正掉队的是最散的两档——聚拢度 6 格的那 <strong>1,438</strong> 个局面只回来 90.96%，
          聚拢度 5 格的 <strong>25</strong> 个局面只回来 60%。
          不过这两档加起来也不过全部局面的<strong>千分之三</strong>，所以日常几乎遇不到：
          「散得越开越危险」是真的，但危险区小得可怜。
        </p>
      </div>

      <!-- 12. Φ 生死线 -->
      <div class="card">
        <h2>⑫ 剖面缺陷 Φ：一条几乎完美的生死线</h2>
        <p>
          换成 Φ 这个指标，画面一下子锋利起来。横轴是 Φ（0 到 38），柱高是这一档有多少个局面（纵轴每格 ×10），
          柱子的<strong>颜色</strong>是这一档能还原回去的比例：
        </p>
        <div class="diag">
          {svgs["phi"]}
        </div>
        <p>
          从 Φ=0 一路到 Φ=30，可还原率一直稳在 <strong>99% 以上</strong>——甚至 Φ=30 那一档 1,030 个局面是 <strong>100% 都能回来</strong>。
          可是一跨过 <strong style="color:{C_RED};">Φ=31 这条线</strong>，立刻崩塌：Φ=32 掉到 18.77%，Φ=34 只剩 11.43%，
          Φ=36 和 Φ=38 那 8 个局面<strong>一个都回不去</strong>。
          这是全部数据里最锐利的一条分界——一共只有 320 个局面在线的右边，其中 264 个回不来。
        </p>
        <p class="note">
          这条线不是万能的：4×4 三级（一次推 3 格）里，整体难度本来就高，Φ 就分不出高下了（见图中下半幅）。
          把同一块 4×4 板的三档放一起看最清楚——<strong>滑动距离 1</strong>：Φ 一直到 42 都还是 100% 可还原（13,079,255 个局面里只有 1 个回不来）；
          <strong>滑动距离 2</strong>：生死线落在 32；<strong>滑动距离 3</strong>：这条线干脆消失。
          换句话说，<strong>「推得越远」带来的困难，不是形状能解释的</strong>——那属于另一个问题。
        </p>
      </div>

      <!-- 13. 边界盒 -->
      <div class="card">
        <h2>⑬ 边界盒：挤成「2 格宽」的局面，一个都回不去</h2>
        <p>
          第三个指标最直观。把每个局面的边界盒尺寸（高×宽）铺成一张<strong>热力图</strong>：
          每一格是一种外形，格子的颜色就是这类局面能还原回去的比例，越绿越安全、越红越危险。
        </p>
        <div class="diag">
          {svgs["bbox"]}
        </div>
        <p>
          整张图几乎是绿的——绝大多数外形都很安全。唯一的例外在<strong style="color:{C_RED};">最左边那一列</strong>：
          边界盒宽只有 <strong style="color:{C_RED};">2 格</strong>的 264 个局面，<strong style="color:{C_RED};">可还原率是 0%，一个例外都没有</strong>。
          换句话说，在 4×4 二级里，<strong>只要你的 16 个格子被挤成一条 2 格宽的蛇，就已经没救了</strong>。
        </p>
        <p>
          下半幅把「最窄的那条边」单独拎出来，规律更干净：最窄边 2 格 → <strong style="color:{C_RED};">0%</strong>；
          3 格 → 99.22%；4 格及以上 → 99.7% 起跳，越粗越安全。
          这也解释了 Φ 的生死线为什么刚好落在 32：一个 2 格宽的形状，行列剖面必然歪得离谱，Φ 一定 ≥32——
          <strong>两条规律其实是同一件事的两副面孔</strong>。
        </p>
      </div>

      <!-- 14. 形状画廊 -->
      <div class="card">
        <h2>⑭ 真实局面画廊：从最整齐到最歪</h2>
        <p>
          最后看实物。下面每一个都是从完整枚举里取出来的<strong>真实局面</strong>，按 Φ 从小到大排；
          红框表示这个局面回不去：
        </p>
        <div class="diag">
          {svgs["gallery"]}
        </div>
        <p>
          最左边是 Φ=0——那就是还原态本身，一块整整齐齐的 4×4。往右逐渐松散、出现缺口和细长的枝杈，
          但一直到 Φ=30 都还能走回来。到 Φ=32、Φ=34，画面忽然变成<strong>一条 2 格宽的蛇</strong>，
          格子还都连着，却已经再也回不去了。
        </p>
        <p class="note">
          形状指标数据可下载：<a href="data/shape_phi.csv">Φ 分档统计</a>　·　<a href="data/shape_gather.csv">聚拢度分档统计</a>　·　
          <a href="data/shape_bbox.csv">边界盒分档统计</a>　·　<a href="data/phi_samples_4x4x2.json">真实棋盘样本</a>
        </p>
      </div>
      <!-- SHAPE_SECTIONS_END -->
'''

    path = os.path.join(WEB, "math_graph.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    if "<!-- SHAPE_SECTIONS_BEGIN -->" in html:
        html = re.sub(r"      <!-- SHAPE_SECTIONS_BEGIN -->.*?      <!-- SHAPE_SECTIONS_END -->\n",
                      frag, html, flags=re.S)
    else:
        html = html.replace('      <!-- 10. 一眼数字 -->', frag + '\n      <!-- 15. 一眼数字 -->')
        html = html.replace('<h2>⑩ 几个一眼记住的数字</h2>', '<h2>⑮ 几个一眼记住的数字</h2>')
    # ⑨ 的数据下载链接补上新文件
    old = '<a href="data/subgraph_4x4x2.json">真实子图</a>　·　<a href="data/README.md">字段说明</a>'
    new = ('<a href="data/subgraph_4x4x2.json">真实子图</a>　·　<a href="data/shape_phi.csv">Φ 分档统计</a>　·　'
           '<a href="data/shape_bbox.csv">边界盒统计</a>　·　<a href="data/README.md">字段说明</a>')
    if old in html:
        html = html.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("\n已写回", path, f"（{len(html)/1024:.1f} KB）")


if __name__ == "__main__":
    main()
