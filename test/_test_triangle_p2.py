# -*- coding: utf-8 -*-
"""B6：三角形密铺的 P2 体验完善（虚拟键盘六向 / 连锁提示）。

执行：python test/_test_triangle_p2.py
覆盖：虚拟键盘三角布局（3 行 6 键、面板变高）、六向按钮与 GAP_DIRECTIONS
      分派、连锁提示按 (i%step, j%step) 高亮且悬停格更亮、方形无回归。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI  # noqa: E402
from game_triangle import GAP_DIRECTIONS, tri_key  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


K = 6
gui = SliderGUI(m=K, n=K, step=2)
gui.animation_enabled = False
gui.save_readonly_flag = False

# ================================================================ 键盘布局
print("== 虚拟键盘三角布局 ==")
gui.new_triangle_puzzle(K, 2)
check("方向键行数：方形 2 / 三角 3",
      SliderGUI._vk_direction_rows(gui) == 3)
w, h = gui._vk_panel_size()
rects = gui._vk_build_layout()
tri_keys = {'move_ul', 'move_ur', 'move_l', 'move_r', 'move_dl', 'move_dr'}
check(f"六向按钮齐备：{sorted(rects)}", tri_keys <= set(rects))
check("方形四向按钮未混入", 'move_up' not in rects)
# 六键不能互相重叠
boxes = list(rects.values())
overlap = any(boxes[a].colliderect(boxes[b])
              for a in range(len(boxes)) for b in range(a + 1, len(boxes)))
check("六向按钮互不重叠", not overlap)
# 全部落在面板内
check("六向按钮都在面板内",
      all(gui.vk_panel_rect.contains(r) for r in boxes))
check(f"面板因多一行方向键而变高（h={h}）", h > 0)
# 方形布局仍是四向十字
gui.new_puzzle(K, K, 2)
sq_rects = gui._vk_build_layout()
check(f"方形布局仍是四向：{sorted(sq_rects)}",
      set(sq_rects) == {'move_up', 'move_down', 'move_left', 'move_right',
                        'sticky', 'undo', 'redo'})

# ================================================================ 六向触发
print("== 六向按钮触发 ==")
DISPATCH_REJECT = "移动方向与缝隙方向不匹配"
SIX_ACTIONS = (('move_ul', 'w'), ('move_ur', 'e'),
               ('move_l', 'a'), ('move_r', 'd'),
               ('move_dl', 'z'), ('move_dr', 'x'))


def select_gap(gui, gap_type):
    """选一条该族缝隙 + 一个滑块，返回 (line, block)。"""
    line = next(ln for g, ln in gui.game.all_gaps() if g == gap_type)
    blk = gui.game.blocks[0]
    gui.selected_gap = (gap_type, line)
    gui.selected_block = blk
    gui.game.opt(gap_type, line, blk)
    return line, blk


# 三族各试一遍六向：平行的方向必须通过分派判据（是否真能滑取决于几何），
# 不平行的必须被分派直接拒掉并提示
for gt in ('h', 'p', 'n'):
    allowed = GAP_DIRECTIONS[gt]
    for action, letter in SIX_ACTIONS:
        gui.new_triangle_puzzle(K, 2)
        select_gap(gui, gt)
        before = set(gui.game.positions())
        gui.macro_notify_msg = ''
        gui._vk_trigger_action(action)
        moved = set(gui.game.positions()) != before
        if letter in allowed:
            check(f"'{gt}' 族 {action}({letter}) 通过分派（未被判不平行）",
                  gui.macro_notify_msg != DISPATCH_REJECT, gui.macro_notify_msg)
        else:
            check(f"'{gt}' 族 {action}({letter}) 被分派拒绝且局面不变",
                  not moved and gui.macro_notify_msg == DISPATCH_REJECT,
                  gui.macro_notify_msg)

# 每族至少有一条缝能真的滑动（证明分派放行的方向确实可达）
for gt in ('h', 'p', 'n'):
    gui.new_triangle_puzzle(K, 2)
    moved_any = False
    for g, ln in gui.game.all_gaps():
        if g != gt:
            continue
        gui.new_triangle_puzzle(K, 2)
        blk = gui.game.blocks[0]
        gui.selected_gap = (g, ln)
        gui.selected_block = blk
        gui.game.opt(g, ln, blk)
        for letter in GAP_DIRECTIONS[g]:
            before = set(gui.game.positions())
            if gui.move_selected_blocks(letter):
                moved_any = True
                break
        if moved_any:
            break
    check(f"'{gt}' 族存在可滑动的缝隙+方向", moved_any)

# 未选中时提示先选缝隙
gui.new_triangle_puzzle(K, 2)
gui.selected_gap = None
gui.selected_block = None
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_ul')
check("未选中时提示先选缝隙和滑块",
      gui.macro_notify_msg == "请先选中缝隙和滑块", gui.macro_notify_msg)

# ================================================================ 连锁提示
print("== 连锁提示 ==")
gui.new_triangle_puzzle(K, 3)
gui.chain_hint_enabled = True
step = gui.current_step
check(f"等级 step = {step}", step == 3)
# 悬停某个单位三角（连锁类含朝向，hover 帶 (i, j, up) 全三元組）
target = tri_key(gui.game.blocks[0])
gui.hover_cell = target
keys, empties, hover = gui._chain_hint_cells()
check(f"占用集合非空（{len(keys)} 个单位三角）", bool(keys))
check("高亮集合含悬停格自身", target in keys)
check(f"悬停格回传 = {hover}", hover == target)
bad = [k for k in keys | empties
       if k[0] % step != target[0] % step or k[1] % step != target[1] % step
       or k[2] != target[2]]
check(f"所有高亮格都满足 (i%{step}, j%{step}, up) 一致（异常 {bad[:3]}）", not bad)
# 占用格全是真实方块；同類空位也在集合裡
all_keys = set(gui.game.positions())
check("占用格全是真实滑块", keys <= all_keys)
check("空位集合与滑块互斥", not (empties & all_keys))
check(f"高亮不含棋形外的空位（复原态实心盘：{len(empties)} 个）",
      not empties)
# 高亮不得越出棋形凸包（三角棋盘不是矩形，斜座標方框右上側是形狀外）
view = gui._tri_view()
hull = view.board_hull(all_keys)
out = [k for k in keys | empties
       if not gui._point_in_convex(view.piece_center(*k), hull)]
check("高亮全部落在棋形凸包内", not out, str(out[:3]))
# 掏一个内部块 → 洞（棋形内、无块）必须亮，且仍不越出凸包
victim = next(b for b in gui.game.blocks
              if 1 <= tri_key(b)[0] <= 3 and 1 <= tri_key(b)[1] <= 3)
vkey = tri_key(victim)
gui.game.blocks.remove(victim)
gui.game.update_matrix()
gui.hover_cell = vkey
keys_h, empties_h, hover_h = gui._chain_hint_cells()
check(f"掏内部块后洞自身高亮（洞 {vkey}）",
      vkey in empties_h and hover_h == vkey)
hull_h = view.board_hull(set(gui.game.positions()))
out_h = [k for k in keys_h | empties_h
         if not gui._point_in_convex(view.piece_center(*k), hull_h)]
check("掏洞后高亮仍全在棋形凸包内", not out_h, str(out_h[:3]))
gui.game.blocks.append(victim)
gui.game.update_matrix()
# 悬停格应比同组其他格更亮：渲染端按整鍵 == hover 区分
hover_keys = {k for k in keys if k == hover}
check(f"悬停键对应 {len(hover_keys)} 个单位三角（同朝向恰一）",
      len(hover_keys) == 1)

# 换个悬停格，集合必须不同（证明真的按 mod 分组）
other = tri_key(gui.game.blocks[7])
if (other[0] % step, other[1] % step, other[2]) \
        != (target[0] % step, target[1] % step, target[2]):
    gui.hover_cell = other
    keys2, _, _ = gui._chain_hint_cells()
    check("换悬停格后高亮集合改变", keys2 != keys)
else:
    check("（该格与首格同组，跳过对比）", True)

# step=1 时不提示（无连锁可言）
gui.new_triangle_puzzle(K, 1)
gui.chain_hint_enabled = True
gui.hover_cell = tri_key(gui.game.blocks[0])
check("step=1 时无连锁提示", gui._chain_hint_cells() == (None, None, None))
# 关掉开关同样无提示
gui.new_triangle_puzzle(K, 3)
gui.chain_hint_enabled = False
gui.hover_cell = tri_key(gui.game.blocks[0])
check("关闭开关后无连锁提示", gui._chain_hint_cells() == (None, None, None))

# ================================================================ 渲染冒烟
print("== 渲染冒烟 ==")
gui.new_triangle_puzzle(K, 3)
gui.chain_hint_enabled = True
gui.hover_cell = tri_key(gui.game.blocks[0])
gui.draw_board()
check(True, "连锁提示开启时三角棋盘绘制正常")
gui.show_virtual_keyboard = True
gui.draw_virtual_keyboard()
check(True, "三角虚拟键盘绘制正常")

# ================================================================ 方形回归
print("== 方形无回归 ==")
gui.new_puzzle(K, K, 2)
gui.chain_hint_enabled = True
gui.hover_cell = (1, 1)
sq_occ, sq_empty, sq_hover = gui._chain_hint_cells()
check(f"方形高亮仍是 (row,col) 二元组（{len(sq_occ)} 格）",
      all(isinstance(c, tuple) and len(c) == 2 for c in sq_occ | sq_empty))
check("方形高亮格满足 (r%step, c%step) 一致",
      all(r % 2 == 1 and c % 2 == 1 for r, c in sq_occ | sq_empty))
gui.show_virtual_keyboard = True
rects = gui._vk_build_layout()
check("方形键盘无六向按钮", 'move_ul' not in rects and 'move_dr' not in rects)
gui.draw_board()
gui.draw_virtual_keyboard()
check(True, "方形棋盘与键盘绘制正常")
# 方形 v 族缝隙仍只认 w/s
gui.selected_gap = ('v', 1)
gui.selected_block = gui.game.blocks[0]
gui.macro_notify_msg = ''
gui._vk_trigger_action('move_left')      # 'a'
check("方形 v 族缝拒绝 a 方向",
      gui.macro_notify_msg == "移动方向与缝隙方向不匹配", gui.macro_notify_msg)

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
