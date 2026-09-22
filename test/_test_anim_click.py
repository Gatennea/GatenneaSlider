# -*- coding: utf-8 -*-
"""动画播放窗口里的鼠标输入：不能凭空多走一步。

症状（用户报告的「鼠标只是点一下/轻拖一下想选中，滑块自己滑走了」）：
移动动画有 300ms，这期间 _init_drag_follow 因 animating 直接返回 False，
MOUSEMOTION 于是把 st['moved'] 置位；松手时 _drag_slide 没有任何 animating
闸门，于是拿 selected_gap（或 8 区角度）重新定向，把「还没提交的那一手」
整组替换掉——画面上的滑块先滑出去、又跳回起点朝另一个方向滑。虚拟键盘
一直有「动画播放中，无法移动」这道闸门，鼠标三条路径（拖拽松手、跟随
提交、米字格第二下）全漏了。

执行：python test/_test_anim_click.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_mi import mi_key, side_of  # noqa: E402

_failures = []
_gui = {'g': None}
DRAG = 25          # 超过 drag_threshold(14)，又不到半格（一格上百像素）
HALF = 150         # 动画窗口内取半程


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def fire(e):
    pygame.event.post(e)
    _gui['g'].handle_events()


def build(form='square', **kw):
    gui = SliderGUI(m=6, n=6, step=1)
    gui.save_readonly_flag = False       # 无头只读陷阱
    gui.animation_enabled = True
    gui.animation_duration = 300
    if form == 'square':
        # 忽略 config/temp_history.json 的残留状态
        gui.new_puzzle(6, 6, 1)
    elif form == 'mi':
        gui.new_mi_puzzle(6, 6, 1)
    elif form == 'triangle':
        gui.new_triangle_puzzle(5, 1)
    _gui['g'] = gui
    return gui


def snap(gui):
    return {tuple(b.location) for b in gui.game.blocks}


def block_at(gui, pred):
    """找一块屏幕上点得中的滑块。"""
    for b in gui.game.blocks:
        if not pred(b):
            continue
        if getattr(gui, 'mi_mode', False):
            cx, cy = gui._mi_view().piece_center(*mi_key(b))
        else:
            cx, cy = b.location[0] + 0.5, b.location[1] + 0.5
        sx, sy = gui.world_to_screen(cx, cy)
        if gui.get_block_at_pos(int(sx), int(sy)) is b:
            return b, int(sx), int(sy)
    return None


def start_square_move(gui):
    """选一条横向缝隙 + 一组滑块，发起一次向右的移动（进入动画）。"""
    for line in range(0, 6):
        gui.selected_gap = ('h', line)
        for blk in gui.game.blocks:
            gui.game.opt('h', line, blk)
            sel = [b for b in gui.game.blocks if b.be_opted]
            if sel and len(sel) < len(gui.game.blocks):
                if gui.move_selected_blocks('d'):
                    return ('h', line)
            for b in gui.game.blocks:
                b.be_opted = False
    return None


def mid_anim(gui):
    """把动画推到半程（倒退起始时间骗过 get_ticks）。"""
    gui.anim_start_time -= HALF
    gui.update_animation()


# ================================================================ 方形
print("== 方形：动画窗口里的拖拽松手 ==")
gui = build('square')
gap = start_square_move(gui)
check("方形找到可用的第一步", gap is not None, f"gap={gap}")
check("第一步进入动画", gui.animating is True)
before = snap(gui)
mid_anim(gui)
progress0 = gui.anim_progress
check("动画已在半程", 0.4 < progress0 < 0.6, f"progress={progress0:.2f}")

hit = block_at(gui, lambda b: True)
check("点得到滑块", hit is not None)
if hit is not None:
    blk, sx, sy = hit
    cell_px = (gui.cell_size + gui.gap_width) * gui.zoom
    check("拖拽距离超过阈值又不到半格（否则是正常滑动）",
          14 <= DRAG < cell_px * 0.5, f"cell_px={cell_px:.0f}")
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (sx, sy)}))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (sx + DRAG, sy), 'rel': (DRAG, 0),
                             'buttons': (1, 0, 0)}))
    st = gui._mouse_drag_state
    check("超过阈值后 moved 置位（复现条件：跟随便因动画没起来）",
          st is not None and st.get('moved') is True)
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {'button': 1, 'pos': (sx + DRAG, sy)}))
    check("动画没被打回起点", abs(gui.anim_progress - progress0) < 0.01,
          f"progress={gui.anim_progress:.2f}")
    check("提示动画播放中", gui.macro_notify_msg == "动画播放中，无法移动",
          gui.macro_notify_msg or '')
    gui.commit_animation()
    check("松手没有多提交一步", gui.step_count == 1, f"step_count={gui.step_count}")
    check("最终位置就是原方向的唯一一步",
          snap(gui) != before and gui.selected_gap == gap)

# 同一套输入在动画结束后必须照旧生效（不能把拖拽整体禁掉）
print("== 方形：动画结束后的拖拽不受影响 ==")
check("动画已结束", gui.animating is False)
hit = block_at(gui, lambda b: True)
if hit is not None:
    blk, sx, sy = hit
    after_move = snap(gui)
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (sx, sy)}))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (sx + DRAG, sy), 'rel': (DRAG, 0),
                             'buttons': (1, 0, 0)}))
    check("动画外仍然进跟随", gui.drag_following is True)
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP,
                            {'button': 1, 'pos': (sx + DRAG, sy)}))
    check("半格以内的轻拖不移动", snap(gui) == after_move)
    # 拖满一格必然移动
    cell_px = (gui.cell_size + gui.gap_width) * gui.zoom
    hit2 = block_at(gui, lambda b: True)
    if hit2 is not None:
        blk2, tx, ty = hit2
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (tx, ty)}))
        fire(pygame.event.Event(pygame.MOUSEMOTION,
                                {'pos': (tx + int(cell_px), ty),
                                 'rel': (int(cell_px), 0),
                                 'buttons': (1, 0, 0)}))
        fire(pygame.event.Event(pygame.MOUSEBUTTONUP,
                                {'button': 1, 'pos': (tx + int(cell_px), ty)}))
        gui.commit_animation()
        check("拖满一格照旧滑动", snap(gui) != after_move)

# ================================================================ 跟随提交
print("== 方形：跟随期间起动画 → 松手不提交 ==")
gui = build('square')
check("方形找到可用的第一步", start_square_move(gui) is not None)
check("动画在播", gui.animating is True)
hit = block_at(gui, lambda b: True)
if hit is not None:
    blk, sx, sy = hit
    before = snap(gui)
    # 手工造出「跟随中」状态：先关动画让跟随便起得来，再手动置回 animating
    gui.animating = False
    gui._mouse_drag_state = None
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (sx, sy)}))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (sx + DRAG, sy), 'rel': (DRAG, 0),
                             'buttons': (1, 0, 0)}))
    check("跟随便已进入", gui.drag_following is True)
    gui.animating = True          # 模拟「按住左键时另一只手按了方向键」
    gui.commit_animation()        # 那一步落地
    landed = snap(gui)
    step1 = gui.step_count
    check("animating 时 _commit_drag_move 只收尾不移动",
          gui._commit_drag_move() is None and gui.drag_following is False
          and gui.step_count == step1 and snap(gui) == landed,
          f"step_count={gui.step_count}（期望 {step1}）")

# ================================================================ 三角
print("== 三角：回退不能走方形 8 区路径 ==")
gui = build('triangle')
check("三角棋盘没有 is_valid_h_line（方形专属）",
      not hasattr(gui.game, 'is_valid_h_line'))
before = snap(gui)
blk = gui.game.blocks[0]
try:
    moved = gui._drag_slide(blk, 25, 0)
    check("三角 _drag_slide 直接回 False，不崩也不移",
          moved is False and snap(gui) == before)
except AttributeError as exc:
    check("三角 _drag_slide 直接回 False，不崩也不移", False, f"抛了 {exc!r}")

# ================================================================ 米字格
print("== 米字格：动画窗口里的第二下触控 ==")
gui = build('mi')
view = gui._mi_view()


def mi_pair(gap_type, line):
    """给一条缝找「锚点 + 可定向的滑块」。锚点取缝线段 30% 处。

    线段中点常落在格角/格心（多条单位边等距 0），那时命中的是平手裁决而
    不是这条缝本身（实测 h/1 的中点命中 d1/-2）；取 30% 处则既在缝上、
    又在凸包内，第一下一定选得到这条缝。
    """
    hull = view.board_hull(gui.game.positions())
    seg = view.gap_segment(gap_type, line, hull)
    if seg is None:
        return None
    ax = seg[0][0] + (seg[1][0] - seg[0][0]) * 0.3
    ay = seg[0][1] + (seg[1][1] - seg[0][1]) * 0.3
    for b in gui.game.blocks:
        key = mi_key(b)
        wx, wy = view.piece_center(*key)
        # 偏移方向与「第一下点缝、第二下点块」一致：点的那块减锚点
        if gui._mi_tap_direction(gap_type, line, b, (wx - ax, wy - ay)) is None:
            continue
        return (ax, ay), b, key
    return None


# 第一条可用的横向缝：选中组沿 a/d 之一滑得动
chosen = None
for line in range(1, 6):
    pair = mi_pair('h', line)
    if pair is None:
        continue
    anchor, blk, key = pair
    asx, asy = gui.world_to_screen(*anchor)
    if gui.get_gap_at_pos(int(asx), int(asy)) != ('h', line):
        continue
    gui.game.opt('h', line, blk)
    movable = any(gui.game.try_move_ex(d, gui.current_step)[0]
                  for d in ('a', 'd'))
    gui.game._clear_selection()
    if movable:
        chosen = (line, anchor, blk, key)
        break
check("米字格找到可用的缝＋块＋锚点", chosen is not None)
if chosen is not None:
    line, anchor, blk, key = chosen
    asx, asy = gui.world_to_screen(*anchor)
    bsx, bsy = gui.world_to_screen(*view.piece_center(*key))
    check("锚点点得中这条缝", gui.get_gap_at_pos(int(asx), int(asy)) == ('h', line))
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(asx), int(asy))}))
    check("第一下选中缝隙并记下锚点",
          gui.selected_gap == ('h', line) and gui._mi_gap_point is not None)
    before = snap(gui)
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (int(bsx), int(bsy))}))
    check("第二下提交移动（进入动画）",
          gui.animating is True and gui.step_count == 0 and snap(gui) == before)
    check("锚点已被用掉", gui._mi_gap_point is None)
    mid_anim(gui)
    progress0 = gui.anim_progress
    # 同一状态再来一轮：取消选中（再点同一条缝）→ 重新点选 → 第二下落在
    # 动画窗口里。锚点按当前局面重算：动画中途 block.location 还没变，但
    # 上一手的落点已经写进 selected_gap，重算只是为了保证仍点得中这条缝
    pair2 = mi_pair('h', line)
    check("移后仍点得中这条缝", pair2 is not None)
    if pair2 is not None:
        anchor2, blk2, key2 = pair2
        asx2, asy2 = gui.world_to_screen(*anchor2)
        check("重算的锚点命中的就是同一条缝",
              gui.get_gap_at_pos(int(asx2), int(asy2)) == ('h', line))
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (int(asx2), int(asy2))}))
        check("再点同一条缝取消选中", gui.selected_gap is None)
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (int(asx2), int(asy2))}))
        check("重新点选后有新锚点",
              gui.selected_gap == ('h', line) and gui._mi_gap_point is not None)
        tx, ty = gui.world_to_screen(*view.piece_center(*key2))
        check("第二下的落点点得到滑块",
              gui.get_block_at_pos(int(tx), int(ty)) is not None)
        gui.macro_notify_msg = ''
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (int(tx), int(ty))}))
        check("动画中的第二下不提交移动",
              abs(gui.anim_progress - progress0) < 0.01 and gui.step_count == 0,
              f"progress={gui.anim_progress:.2f}")
        check("提示动画播放中", gui.macro_notify_msg == "动画播放中，无法移动",
              gui.macro_notify_msg or '')
        check("锚点仍被用掉", gui._mi_gap_point is None)
        check("选中组留下来（只选组，等动画结束后再给方向）",
              len([b for b in gui.game.blocks if b.be_opted]) > 0)
        gui.commit_animation()
        check("提交后仍只有最初那一步", gui.step_count == 1,
              f"step_count={gui.step_count}")

print()
if _failures:
    print(f"FAILED {len(_failures)} 项：")
    for name in _failures:
        print("  -", name)
    sys.exit(1)
print("anim-click 回归 PASS")
