# -*- coding: utf-8 -*-
"""生成六边形负面测试的示意图（experiments 脚本，非交付物）。

面板①：蜂巢的砖墙错位——竖直直缝只吻合一行竖边、切穿下一行块心；
h 族 rank 线（水平）穿过整行块心。面板②：剪切一步的半程与邻行
咬合（红），而终点恰好只接触不重叠——端点判据的盲区。
"""

import math

RT3 = math.sqrt(3.0)
VERT_OFF = ((0.5, 0.5), (0.0, 1.0), (-0.5, 0.5),
            (-0.5, -0.5), (0.0, -1.0), (0.5, -0.5))

W = 680
S = 19.0              # 每单位像素
CX_A, CY_A = 378, 218  # 面板①中心（屏幕）
CX_B, CY_B = 378, 512  # 面板②中心（屏幕）

INK = '#2c3e50'
SUB = '#5d6d7e'
STATIC_F = '#eef2f7'
STATIC_S = '#8a94a6'
CRACK = '#2471a3'
BAD = '#c0392b'
GHOST = '#aab2bc'


def center(q, r):
    return (q + r / 2.0, 1.5 * r)


def hex_path(q, r, s, cx, cy, dx=0.0):
    A, B = center(q, r)
    pts = []
    for da, db in VERT_OFF:
        pts.append((cx + s * RT3 * (A + da + dx), cy - s * (B + db)))
    return 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x, y in pts) + ' Z'


def to_screen(A, B, cx, cy, s):
    return (cx + s * RT3 * A, cy - s * B)


def hex_blocks(k):
    return [(q, r) for q in range(-k, k + 1) for r in range(-k, k + 1)
            if abs(q) <= k and abs(r) <= k and abs(q + r) <= k]


out = []
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 650" '
           f'font-family="system-ui,sans-serif" role="img">')
out.append('<title>六边形密铺负面测试示意</title>')
out.append('<desc>砖墙错位无干净缝；rank 线切块心；剪切半程咬合而终点干净</desc>')

# ---------------- 面板① ----------------
out.append(f'<text x="{W/2}" y="28" text-anchor="middle" font-size="14" '
           f'font-weight="500" fill="{INK}">① 蜂巢没有干净缝：竖边砖墙错位，直线缝必切块</text>')
blocks = hex_blocks(2)
bset = set(blocks)

for (q, r) in blocks:
    out.append(f'<path d="{hex_path(q, r, S, CX_A, CY_A)}" fill="{STATIC_F}" '
               f'stroke="{STATIC_S}" stroke-width="1"/>')

# 真实竖裂纹（同行共享竖边）——蓝
for (q, r) in blocks:
    if (q + 1, r) in bset:
        A, B = center(q, r)
        x1, y1 = to_screen(A + 0.5, B - 0.5, CX_A, CY_A, S)
        x2, y2 = to_screen(A + 0.5, B + 0.5, CX_A, CY_A, S)
        out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" '
                   f'y2="{y2:.2f}" stroke="{CRACK}" stroke-width="3" '
                   f'opacity="0.85"/>')

# 竖直直缝尝试：A = 1/2（x = √3/2）
x_v, y_top = to_screen(0.5, 2.5, CX_A, CY_A, S)
x_v2, y_bot = to_screen(0.5, -2.5, CX_A, CY_A, S)
out.append(f'<line x1="{x_v:.2f}" y1="{y_top:.2f}" x2="{x_v2:.2f}" '
           f'y2="{y_bot:.2f}" stroke="{BAD}" stroke-width="1.6" '
           f'stroke-dasharray="7 5"/>')
# h 族 rank 线 t=0：B = 0
x_l, y_l = to_screen(-4.4, 0.0, CX_A, CY_A, S)
x_r, _ = to_screen(4.4, 0.0, CX_A, CY_A, S)
out.append(f'<line x1="{x_l:.2f}" y1="{y_l:.2f}" x2="{x_r:.2f}" '
           f'y2="{y_l:.2f}" stroke="{BAD}" stroke-width="1.6" '
           f'stroke-dasharray="7 5"/>')

# 左侧图例（不骑图形）
out.append(f'<text x="12" y="112" font-size="11.5" fill="{BAD}">'
           f'红虚线 = 引擎的候选直线缝（每条都切块）</text>')
out.append(f'<text x="12" y="131" font-size="11.5" fill="{BAD}">'
           f'· 竖直 x=√3/2：吻合同行竖边，切穿下一行块心</text>')
out.append(f'<text x="12" y="150" font-size="11.5" fill="{BAD}">'
           f'· 水平（h 族 rank 线 t=0）：穿过整行块心</text>')
out.append(f'<text x="12" y="184" font-size="11.5" fill="{CRACK}">'
           f'蓝 = 真实竖裂纹（同行共享边，行行错开半格）</text>')

# ---------------- 面板② ----------------
out.append(f'<text x="{W/2}" y="372" text-anchor="middle" font-size="14" '
           f'font-weight="500" fill="{INK}">② 剪切一步：半程咬合（红），终点却恰好只接触</text>')
out.append(f'<text x="{W/2}" y="392" text-anchor="middle" font-size="11.5" '
           f'fill="{SUB}">H₂ 下端行 (0,−2),(1,−2),(2,−2) 沿缝右滑 1 单位；'
           f'图示半程（√3/2）</text>')

for (q, r) in blocks:
    out.append(f'<path d="{hex_path(q, r, S, CX_B, CY_B)}" fill="{STATIC_F}" '
               f'stroke="{STATIC_S}" stroke-width="1"/>')

moved = [(0, -2), (1, -2), (2, -2)]
for (q, r) in moved:   # 原位鬼影
    out.append(f'<path d="{hex_path(q, r, S, CX_B, CY_B)}" fill="none" '
               f'stroke="{GHOST}" stroke-width="1" stroke-dasharray="4 4"/>')
for (q, r) in moved:   # 半程位置（红）
    out.append(f'<path d="{hex_path(q, r, S, CX_B, CY_B, dx=0.5)}" '
               f'fill="{BAD}" fill-opacity="0.30" stroke="{BAD}" '
               f'stroke-width="1.6"/>')
# 被咬合的静止块
out.append(f'<path d="{hex_path(0, -1, S, CX_B, CY_B)}" fill="none" '
           f'stroke="{BAD}" stroke-width="2.2"/>')

# 方向箭头
A0, B0 = center(0, -2)
ax, ay = to_screen(A0 - 1.05, B0, CX_B, CY_B, S)
bx, by = to_screen(A0 + 0.5, B0, CX_B, CY_B, S)
out.append(f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{bx:.2f}" y2="{by:.2f}" '
           f'stroke="{BAD}" stroke-width="1.8"/>')
out.append(f'<path d="M {bx:.2f} {by:.2f} l -7 -4 l 0 8 z" fill="{BAD}"/>')

out.append(f'<text x="{W/2}" y="612" text-anchor="middle" font-size="11.5" '
           f'fill="{BAD}">红 = 半程位置：与上一行 (0,−1) 正面积重叠（咬合）</text>')
out.append(f'<text x="{W/2}" y="631" text-anchor="middle" font-size="11.5" '
           f'fill="{SUB}">灰虚线 = 原位；终点两块距恰好 √3——只接触不重叠，'
           f'端点 SAT 判据全盲</text>')

out.append('</svg>')

with open('experiments/_svg_hex.svg', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('written experiments/_svg_hex.svg')
