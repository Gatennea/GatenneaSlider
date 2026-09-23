# -*- coding: utf-8 -*-
"""米字格斜向單步的示意圖：現狀整格 vs 提案「一半距離」（討論用，非測試）。

單位塊（直角等腰三角）的三條邊：
    斜邊 = 一條格邊 = 長度 1      → 橫豎一步走一條斜邊，屏幕距離 1
    直角邊 = 半條對角線 = √2/2    → 提案的斜向一步走一條直角邊，屏幕距離 √2/2
沿對角縫滑動時方向平行縫線，被選中的那一側整體留在原來的半平面內，不會插進
另一側——重疊與否由多邊形相交精算，見 main() 輸出。

四個面板：
  1. 復原態：實心 2×2，d1 縫把 16 塊切成 8/8
  2. 現狀：斜向一步 = 整格 (1,1)，屏幕距離 √2；四族縫隙全照舊
  3. 提案：斜向一步 = 半格 (0.5,0.5)，屏幕距離 √2/2；不重疊、仍連通
  4. 提案之後：橫縫錯開半格，一延伸進靜止側就切開別人的塊
     → 橫／豎兩族縫隙在這半局面下直接消失，只剩兩族對角縫
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from game_mi import mi_vertices, side_of

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'MS Gothic']
plt.rcParams['axes.unicode_minus'] = False

N = 2                          # 2×2 = 16 塊
QS = ('N', 'E', 'S', 'W')
GAP = ('d1', 0)                # 「\」對角線，2×2 上正是貫穿整盤那條
LEG = math.sqrt(2.0) / 2.0     # 直角邊長 = √2/2

EPS = 1e-9


# ---------------------------------------------------------------- 幾何
def norm(poly):
    """統一成「有向面積 > 0」的環繞方向，後續半平面裁剪才成立。"""
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return list(poly) if s > 0 else list(poly)[::-1]


def side_val(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def clip_half(poly, a, b, keep_nonneg):
    out = []
    for i in range(len(poly)):
        cur, nxt = poly[i], poly[(i + 1) % len(poly)]
        dc, dn = side_val(a, b, cur), side_val(a, b, nxt)
        ic = dc >= -EPS if keep_nonneg else dc <= EPS
        inxt = dn >= -EPS if keep_nonneg else dn <= EPS
        if ic != inxt:
            t = dc / (dc - dn)
            out.append((cur[0] + t * (nxt[0] - cur[0]),
                        cur[1] + t * (nxt[1] - cur[1])))
        if inxt:
            out.append(nxt)
    return out


def poly_intersect(p, q):
    r = list(p)
    for i in range(len(q)):
        r = clip_half(r, q[i], q[(i + 1) % len(q)], True)
        if not r:
            return []
    return r


def poly_area(poly):
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def centroid(poly):
    return (sum(p[0] for p in poly) / len(poly),
            sum(p[1] for p in poly) / len(poly))


def shift(poly, dx, dy):
    return [(x + dx, y + dy) for (x, y) in poly]


def edges(poly):
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


def shared_len(pa, pb):
    """兩條共線邊的重疊長度（不共線回 0）。"""
    best = 0.0
    for (a1, b1) in edges(pa):
        for (a2, b2) in edges(pb):
            for (A, B, C, D) in ((a1, b1, a2, b2), (a2, b2, a1, b1)):
                dx, dy = B[0] - A[0], B[1] - A[1]
                L = math.hypot(dx, dy)
                if L < EPS:
                    continue
                ux, uy = dx / L, dy / L
                if abs((C[0] - A[0]) * uy - (C[1] - A[1]) * ux) > 1e-6:
                    continue
                if abs((D[0] - A[0]) * uy - (D[1] - A[1]) * ux) > 1e-6:
                    continue
                t1 = (C[0] - A[0]) * ux + (C[1] - A[1]) * uy
                t2 = (D[0] - A[0]) * ux + (D[1] - A[1]) * uy
                lo, hi = min(t1, t2), max(t1, t2)
                best = max(best, max(0.0, min(hi, L) - max(lo, 0.0)))
    return best


# ------------------------------------------------- 縫隙候選線（四族）
def edge_line_value(a, b):
    """邊 (a,b) 落在哪條族線上 → (族, 值)；水平/垂直/兩種 45° 之外回 None。"""
    if abs(a[1] - b[1]) < 1e-9:
        return ('h', a[1])
    if abs(a[0] - b[0]) < 1e-9:
        return ('v', a[0])
    if abs((a[1] - a[0]) - (b[1] - b[0])) < 1e-9:
        return ('d1', a[1] - a[0])
    if abs((a[0] + a[1]) - (b[0] + b[1])) < 1e-9:
        return ('d2', a[0] + a[1])
    return None


def line_points(fam, v):
    """族線上取兩點，供半平面裁剪用。"""
    if fam == 'h':
        return (-9.0, v), (9.0, v)
    if fam == 'v':
        return (v, -9.0), (v, 9.0)
    if fam == 'd1':
        return (0.0, v), (9.0, 9.0 + v)
    return (0.0, v), (v, 0.0)          # d2


def line_side(fam, p, v):
    """點 p 在族線的哪一側（<0 / >0）。"""
    if fam == 'h':
        return p[1] - v
    if fam == 'v':
        return p[0] - v
    if fam == 'd1':
        return (p[1] - p[0]) - v
    return (p[0] + p[1]) - v


def valid_gaps(pieces):
    """合法縫隙 = 候選線不切開任何塊內部、且兩側都至少有一塊。

    候選線取所有塊的邊的支撐線（半格局面下移動側的邊落在半整數坐標上，
    現狀的整數 rank 枚舉表達不了，所以這裡純按幾何重算一遍）。
    """
    out = {}
    for fam in ('h', 'v', 'd1', 'd2'):
        vals = set()
        for poly in pieces.values():
            for a, b in edges(poly):
                got = edge_line_value(a, b)
                if got and got[0] == fam:
                    vals.add(round(got[1], 6))
        ok = []
        for v in sorted(vals):
            p0, p1 = line_points(fam, v)
            if any(poly_area(clip_half(p, p0, p1, True)) > 1e-9
                   and poly_area(clip_half(p, p0, p1, False)) > 1e-9
                   for p in pieces.values()):
                continue                      # 切開了某個塊
            sides = {1 if line_side(fam, centroid(p), v) > 0 else -1
                     for p in pieces.values()}
            if sides == {-1, 1}:
                ok.append(v)
        out[fam] = ok
    return out


# ---------------------------------------------------------------- 局面
def build(dx=0.0, dy=0.0):
    """{(r,c,q): 多邊形}；dx/dy 只加在被選中那一側。"""
    gap_type, line = GAP
    out = {}
    for r in range(N):
        for c in range(N):
            for q in QS:
                key = (r, c, q)
                poly = norm(mi_vertices(r, c, q))
                if side_of(gap_type, line, key) == 1:
                    poly = shift(poly, dx, dy)
                out[key] = poly
    return out


def split_sides(pieces):
    gap_type, line = GAP
    moved = {k for k in pieces if side_of(gap_type, line, k) == 1}
    return moved, set(pieces) - moved


def connected(pieces):
    """邊相鄰（共享正長度邊）連通性，DFS。"""
    keys = list(pieces)
    adj = {k: [] for k in keys}
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if shared_len(pieces[ka], pieces[kb]) > 1e-6:
                adj[ka].append(kb)
                adj[kb].append(ka)
    seen, stack = set(), [keys[0]]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj[cur])
    return len(seen) == len(keys)


def overlap_between_sides(pieces):
    moved, still = split_sides(pieces)
    total = 0.0
    for km in moved:
        for ks in still:
            inter = poly_intersect(pieces[km], pieces[ks])
            if inter:
                total += poly_area(inter)
    return total


def contact_between_sides(pieces):
    moved, still = split_sides(pieces)
    return sum(shared_len(pieces[km], pieces[ks])
               for km in moved for ks in still)


def cut_by_h(poly, y):
    a, b = (-9.0, y), (9.0, y)
    return (poly_area(clip_half(poly, a, b, True)) > 1e-9
            and poly_area(clip_half(poly, a, b, False)) > 1e-9)


# ---------------------------------------------------------------- 繪圖
C_STILL = '#bcd4ea'
C_MOVED = '#f6c89a'
C_MOVED_AFTER = '#e8963c'
C_GHOST = '#e3e9ef'
XLIM = (-1.2, 3.4)
YLIM = (-4.4, 1.2)


def plot_pieces(ax, pieces, fill, edge, alpha=1.0, lw=1.2, only=None, z=2):
    for key, poly in pieces.items():
        if only is not None and key not in only:
            continue
        pts = [(x, -y) for (x, y) in poly]      # 螢幕 y 向下 → 翻成數學向上
        ax.add_patch(MplPolygon(pts, closed=True, facecolor=fill,
                                edgecolor=edge, alpha=alpha, lw=lw, zorder=z))


def board_outline(ax):
    ax.add_patch(MplPolygon([(0, 0), (N, 0), (N, -N), (0, -N)], closed=True,
                            fill=False, edgecolor='#2c3e50', lw=1.6, zorder=6))


def finish(ax, title):
    ax.set_aspect('equal')
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.set_title(title, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def check_inside(name, pieces):
    xs, ys = [], []
    for poly in pieces.values():
        xs += [p[0] for p in poly]
        ys += [-p[1] for p in poly]
    ok = (min(xs) >= XLIM[0] and max(xs) <= XLIM[1]
          and min(ys) >= YLIM[0] and max(ys) <= YLIM[1])
    print(f'[範圍自查] {name}: x [{min(xs):.3f}, {max(xs):.3f}] '
          f'y [{min(ys):.3f}, {max(ys):.3f}] → {"OK" if ok else "超出範圍！"}')


def check_texts(fig, ax, name, texts):
    """精查每段文字都落在自己的子圖內（matplotlib 不自動裁文字）。"""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    abox = ax.get_window_extent(rend)
    bad = []
    for t in texts:
        if t is None:
            continue
        bb = t.get_window_extent(rend)
        if (bb.x0 < abox.x0 - 1 or bb.x1 > abox.x1 + 1
                or bb.y0 < abox.y0 - 1 or bb.y1 > abox.y1 + 1):
            bad.append(t.get_text().split('\n')[0]
                       + f'（右溢 {(bb.x1 - abox.x1):.0f}px / '
                       f'下溢 {(abox.y0 - bb.y0):.0f}px）')
    print(f'[文字自查] {name}: {"OK" if not bad else "；".join(bad)}')


def main():
    before = build(0.0, 0.0)
    lattice = build(1.0, 1.0)            # 現狀：整格斜步
    half = build(0.5, 0.5)               # 提案：一半距離（半格斜步）
    moved_keys, still_keys = split_sides(before)

    print('=== 重疊 / 連通（多邊形相交，精確面積）===')
    for name, st in (('整格 (1,1)', lattice), ('半格 (0.5,0.5)', half)):
        print(f'{name:14s} 兩側重疊面積 = {overlap_between_sides(st):.6f}，'
              f'兩側接觸邊長 = {contact_between_sides(st):.4f}，'
              f'整體單一連通 = {connected(st)}')
    print(f'斜邊長 = 1.0，直角邊長 = {LEG:.4f}')
    print('=== 四族合法縫隙（候選線不切開任何塊、兩側都有塊）===')
    for name, st in (('現狀（對齊）', lattice), ('半格（錯位）', half)):
        gaps = valid_gaps(st)
        print(f'{name:12s} ' + '，'.join(
            f'{fam}: {gaps[fam]}' for fam in ('h', 'v', 'd1', 'd2')))
    e11 = half[(1, 1, 'E')]
    print(f'半格後 y=1.5（移動側的橫縫）切開靜止側 E(1,1)：'
          f'{cut_by_h(e11, 1.5)}（切成 '
          f'{poly_area(clip_half(e11, (-9, 1.5), (9, 1.5), True)):.4f} + '
          f'{poly_area(clip_half(e11, (-9, 1.5), (9, 1.5), False)):.4f}）')
    # 圖③宣稱「橙塊頂點正好落回原格線頂點」：原格線頂點只有整數點與格心兩種，
    # 平移 (0.5,0.5) 把整數點映到格心、格心映到整數點，所以宣稱成立。
    on_grid = all(abs(v * 2 - round(v * 2)) < 1e-9
                  for poly in half.values() for p in poly for v in p)
    print(f'半格後所有頂點仍在「整數點 ∪ 格心」上：{on_grid}')
    print(f'半格接觸邊長 {contact_between_sides(half):.4f} = '
          f'{contact_between_sides(half) / LEG:.0f} 條整直角邊')

    fig, axes = plt.subplots(2, 2, figsize=(14.0, 13.2))
    ax1, ax2, ax3, ax4 = axes.ravel()
    texts = {1: [], 2: [], 3: [], 4: []}
    e0, e1 = -0.55, N + 0.55

    def grid(ax, color='#9aa7b1', hlw=0.7, vlw=0.7, dlw=0.7, d1ls='-',
             d2ls='--', hls=':', vls=':'):
        for k in range(-2, N + 3):
            ax.plot([e0, e1], [k - e0, k - e1], color=color, lw=dlw, ls=d1ls,
                    zorder=0)                       # 「\」：Y−X = −k
            ax.plot([e0, e1], [e0 - (k + 1), e1 - (k + 1)], color=color,
                    lw=dlw, ls=d2ls, zorder=0)      # 「/」：X+Y = k+1
            ax.plot([e0, e1], [-k, -k], color=color, lw=hlw, ls=hls, zorder=0)
            ax.plot([k, k], [-e0, -e1], color=color, lw=vlw, ls=vls, zorder=0)

    # ---------------- 面板 1：復原態
    plot_pieces(ax1, before, C_STILL, '#4a6c8c', only=still_keys)
    plot_pieces(ax1, before, C_MOVED, '#a8702a', only=moved_keys)
    for key, poly in before.items():
        cx, cy = centroid(poly)
        ax1.text(cx, -cy, key[2], ha='center', va='center', fontsize=9,
                 color='#2c3e50', zorder=7)
    ax1.plot([0, N], [0, -N], color='#c0392b', lw=2.8, zorder=5)
    texts[1].append(ax1.text(0.24, -0.36, 'd1 縫', color='#c0392b', fontsize=11,
                             rotation=-45, ha='left', va='bottom', zorder=8))
    board_outline(ax1)
    texts[1].append(ax1.text(0.05, -2.40, '藍 8 塊＝0 側（不動）\n'
                                          '橙 8 塊＝1 側（被選中）',
                             fontsize=9.5, va='top'))
    texts[1].append(ax1.text(0.05, -3.35,
                             '單位塊三條邊：\n'
                             '斜邊 = 格邊 = 1（橫豎一步）\n'
                             '直角邊 = 半對角線 = √2/2（斜向一步）',
                             fontsize=9.5, color='#2c3e50', va='top'))
    finish(ax1, '① 復原態：實心 2×2，d1 縫把 16 塊切成 8 / 8\n兩側各 8 塊，滑動方向平行縫線')
    check_inside('面板1', before)

    # ---------------- 面板 2：現狀
    plot_pieces(ax2, before, C_GHOST, '#aab4bf', alpha=0.8, only=moved_keys)
    plot_pieces(ax2, lattice, C_STILL, '#4a6c8c', only=still_keys)
    plot_pieces(ax2, lattice, C_MOVED_AFTER, '#8a5a1e', only=moved_keys)
    grid(ax2)
    ax2.plot([0, N], [0, -N], color='#c0392b', lw=2.8, zorder=5)
    ax2.annotate('', xy=(2.42, -2.42), xytext=(1.42, -1.42),
                 arrowprops=dict(arrowstyle='-|>', color='#c0392b', lw=2))
    board_outline(ax2)
    texts[2].append(ax2.text(0.05, -3.35,
                             '斜向一步 = 整格 (1, 1)，屏幕距離 √2 ≈ 1.414\n'
                             '橙塊仍严丝合缝落在灰格線上\n'
                             '四族缝隙全部照旧，不需要新判定',
                             fontsize=9.5, color='#c0392b', va='top'))
    finish(ax2, '② 現狀：斜向一步走一整格\n不出錯、不需要新判定，但一步的距離是橫豎的 √2 倍')
    check_inside('面板2', lattice)

    # ---------------- 面板 3：提案（一半距離）
    plot_pieces(ax3, before, C_GHOST, '#aab4bf', alpha=0.8, only=moved_keys)
    plot_pieces(ax3, half, C_STILL, '#4a6c8c', only=still_keys)
    plot_pieces(ax3, half, C_MOVED_AFTER, '#8a5a1e', only=moved_keys)
    ax3.plot([0, N], [0, -N], color='#c0392b', lw=2.8, zorder=5)
    ax3.annotate('', xy=(1.38, -1.38), xytext=(0.88, -0.88),
                 arrowprops=dict(arrowstyle='-|>', color='#c0392b', lw=2))
    board_outline(ax3)
    texts[3].append(ax3.text(0.05, -3.15,
                             '斜向一步 = 半格 (0.5, 0.5)\n'
                             '屏幕距離 √2/2 ≈ 0.707，是橫豎一步的一半\n'
                             '兩側重疊面積 = 0，仍相貼、仍單一連通\n'
                             '橙塊頂點落回原格線頂點\n'
                             '接觸是整整一條直角邊',
                             fontsize=9.5, color='#c0392b', va='top'))
    finish(ax3, '③ 提案：斜向一步走半格（一條直角邊）\n距離減半、不重疊、不散架，但離開了原晶格')
    check_inside('面板3', half)

    # ---------------- 面板 4：提案之後的縫隙
    plot_pieces(ax4, half, C_STILL, '#4a6c8c', only=still_keys)
    plot_pieces(ax4, half, C_MOVED_AFTER, '#8a5a1e', only=moved_keys)
    grid(ax4, color='#7f8c8d', dlw=0.9)
    ax4.plot([0, N], [0, -N], color='#c0392b', lw=2.8, zorder=5)
    # 移動側的橫縫 y=1.5：一延伸進靜止側就切開 E(1,1)
    ax4.plot([e0, e1], [-1.5, -1.5], color='#8e44ad', lw=1.8, ls='--', zorder=4)
    ax4.add_patch(MplPolygon([(x, -y) for (x, y) in half[(1, 1, 'E')]],
                             closed=True, fill=False, edgecolor='#8e44ad',
                             lw=2.2, zorder=7))
    texts[4].append(ax4.text(2.02, -1.24, '紫線切開\nE(1,1)', color='#8e44ad',
                             fontsize=9.5, va='top'))
    board_outline(ax4)
    texts[4].append(ax4.text(0.05, -3.15,
                             '灰線 = 原格線：橙塊只有「\\」族還压在灰線上\n'
                             '橫縫錯開半格 → 一延伸就切開藍側的塊\n'
                             '核算：這個半局面下 h / v 兩族合法縫隙為 0 條',
                             fontsize=9.5, color='#c0392b', va='top'))
    finish(ax4, '④ 提案之後：橫／豎縫隙在這半局面下直接消失\n只剩兩族對角縫還能貫穿整盤')
    check_inside('面板4', half)

    for i, ax in enumerate((ax1, ax2, ax3, ax4), start=1):
        check_texts(fig, ax, f'面板{i}', texts[i])

    fig.suptitle('米字格斜向單步：現狀整格 (1,1) vs 提案半格 (0.5,0.5)', fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_mi_slide.png')
    fig.savefig(out, dpi=110)
    print(f'已輸出 {out}')


if __name__ == '__main__':
    main()
