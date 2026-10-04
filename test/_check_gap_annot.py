# -*- coding: utf-8 -*-
"""校验 S1-4 的方向标注在**三种谜题**上都能算出来，且锚点跟随选中切片。

前身的三个毛病：只在方形生效、只按整条缝/棋盘边界定位、图层被滑块压住。
本脚本不看图层（那是调用顺序，要在真渲染里验），只验几何与非方形可用性。

执行：``D:/python/python.exe test/_check_gap_annot.py``
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI  # noqa: E402


def probe(gui, tag):
    """打印当前 selected_gap + 选中切片算出来的两端标注。"""
    annot = gui._get_gap_direction_annotation()
    chosen = [b for b in gui.game.blocks if b.be_opted]
    print(f'\n[{tag}] gap={gui.selected_gap} 选中切片 {len(chosen)} 块')
    if not annot:
        print('   → 无标注（None）')
        return False
    ux, uy = annot['vec']
    print(f'   单位位移向量 ({ux:+.3f}, {uy:+.3f}) '
          f' cell*zoom={gui.cell_size * gui.zoom:.1f}px '
          f' 标记半径={annot["marker_r"]:.0f}px')
    for i, (d, (ax, ay), ms, uv) in enumerate(annot['ends']):
        inside = 0 <= ax <= gui.screen_width and 0 <= ay <= gui.screen_height
        print(f'   端{i}: 方向 {d}  可走 {ms} 格  锚点 ({ax:.0f}, {ay:.0f})  '
              f'箭头向量 ({uv[0]:+.2f}, {uv[1]:+.2f})  '
              f'在屏内={inside}')
    return True


gui = SliderGUI(m=5, n=5, step=1)
gui.animation_enabled = False
gui.ui_mode = 'enhanced'

# ------------------------------------------------------------------ 方形
gui.new_puzzle(5, 5, 1)
# 选一条横缝，锚点取某个块：opt(gap_type, line, anchor_block)
# 方形 game.opt 的缝索引语义见 game.py；这里取中间那条
anchor = gui.game.blocks[0]
gui.game.opt('h', 2, anchor)
gui.selected_gap = ('h', 2)
ok_sq = probe(gui, '方形 5×5 横缝 h=2')
gui.game.opt('v', 2, anchor)
gui.selected_gap = ('v', 2)
ok_sq = probe(gui, '方形 5×5 竖缝 v=2') and ok_sq

# ------------------------------------------------------------------ 三角
gui.new_triangle_puzzle(3, 1)
gui._fit_triangle_zoom() if hasattr(gui, '_fit_triangle_zoom') else None
gui._center_triangle()
tri_blocks = gui.game.blocks
# 先随便挑一条有效的 n 族缝（gap_index_range 保证两侧非空）
from game_triangle import gap_index_range  # noqa: E402

cells = gui.game.positions()
rng = gap_index_range('n', cells)
line = rng[len(rng) // 2]
gui.game.opt('n', line, tri_blocks[len(tri_blocks) // 2])
gui.selected_gap = ('n', line)
ok_tri = probe(gui, f'三角 k=3 斜缝 n={line}')

# ------------------------------------------------------------------ 米字
gui.new_mi_puzzle(3, 3, 1)
gui._fit_mi_zoom()
gui._center_mi()
mi_blocks = gui.game.blocks
gui.game.opt('d1', 0, mi_blocks[len(mi_blocks) // 2])
gui.selected_gap = ('d1', 0)
ok_mi = probe(gui, '米字 3×3 对角缝 d1=0')

print('\n===== 结论 =====')
print(f'方形 {"OK" if ok_sq else "FAIL"} / 三角 {"OK" if ok_tri else "FAIL"} '
      f'/ 米字 {"OK" if ok_mi else "FAIL"}')

# ---------------------------------------------------- 同一条缝、不同锚点块
# bug-b 的验收：缝是刀，同一条缝点上半和点下半带走完全不同的两片，
# 端点必须跟着**那一整片**走，而不是按整条缝/棋盘边界定位。
print('\n===== bug-b 验收：同一条缝 × 不同锚点 =====')
gui.new_puzzle(5, 5, 1)
gui.selected_gap = ('h', 2)
seen = []
for anchor in (gui.game.blocks[0], gui.game.blocks[-1]):
    gui.game.opt('h', 2, anchor)
    chosen = [b for b in gui.game.blocks if b.be_opted]
    annot = gui._get_gap_direction_annotation()
    rows = sorted({b.location[0] for b in chosen})
    cols = sorted({b.location[1] for b in chosen})
    if not annot:
        print('   无标注')
        continue
    ends = {d: (round(ax), round(ay)) for d, (ax, ay), _ms, _uv in annot['ends']}
    print(f'   锚点块 @{anchor.location} → 带走 {len(chosen)} 块 '
          f'行{rows[0]}..{rows[-1]} 列{cols[0]}..{cols[-1]} → 端点 {ends}')
    seen.append(tuple(sorted(ends.items())))

if len(seen) == 2:
    same_line_ok = seen[0] != seen[1]
    print(f'   → 两片端点{"不同（跟随切片 ✓）" if same_line_ok else "相同（仍在用整条缝 ✗）"}')
else:
    print('   → 样本不足，未能对照')

# ---------------------------------------------------- S1-2 边框配色
print('\n===== S1-2 边框配色 =====')
gui.new_puzzle(5, 5, 1)
gui._sel_anim_timer = 30
gui._sel_anim_is_undo = True
gui.ui_mode = 'enhanced'
print(f'   增强 + 撤销 : {gui._sel_anim_border()}')
gui._sel_anim_is_undo = False
print(f'   增强 + 重做 : {gui._sel_anim_border()}')
gui._sel_anim_timer = 0
print(f'   高亮窗口结束: {gui._sel_anim_border()}')
gui.ui_mode = 'plain'
gui._sel_anim_timer = 30
print(f'   朴素模式    : {gui._sel_anim_border()}')
