# -*- coding: utf-8 -*-
"""动画播放窗口里的鼠标输入：不能凭空多走一步。

症状（用户报告的「鼠标只是点一下/轻拖一下想选中，滑块自己滑走了」）：
移动动画有 300ms，这期间 _init_drag_follow 因 animating 直接返回 False，
MOUSEMOTION 于是把 st['moved'] 置位；松手时 _drag_slide 没有任何 animating
闸门，于是拿 selected_gap（或 8 区角度）重新定向，把「还没提交的那一手」
整组替换掉——画面上的滑块先滑出去、又跳回起点朝另一个方向滑。虚拟键盘
一直有「动画播放中，无法移动」这道闸门，鼠标三条路径（方形拖拽松手、跟随
提交、米字格第二下的拖动）全漏了。

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
print("== 米字格：动画窗口里的第二次触控 ==")
gui = build('mi')
view = gui._mi_view()
from game_mi import DIRECTIONS as MI_DIRS  # noqa: E402


def mi_candidates(limit=6):
    """当前局面里「第一下点缝、第二下按住这块拖一格能提交」的组合。

    落点取缝线段 30% 处：线段中点常落在格角/格心（多条单位边等距 0），
    那时命中的是平手裁决而不是这条缝本身（实测 h/1 的中点命中 d1/-2）。
    另要求屏幕上真点得中这条缝、且该侧真滑得动——组合必须是玩家做得出来
    的，否则测的是不存在的路径。
    """
    out = []
    hull = view.board_hull(gui.game.positions())
    for gt in ('h', 'v', 'd1', 'd2'):
        for line in sorted({l for (g, l) in gui.game.all_gaps() if g == gt}):
            seg = view.gap_segment(gt, line, hull)
            if seg is None:
                continue
            anchor = (seg[0][0] + (seg[1][0] - seg[0][0]) * 0.3,
                      seg[0][1] + (seg[1][1] - seg[0][1]) * 0.3)
            asx, asy = gui.world_to_screen(*anchor)
            if gui.get_gap_at_pos(int(asx), int(asy)) != (gt, line):
                continue
            for b in gui.game.blocks:
                for d in (gui.MI_GAP_AXES[gt][2], gui.MI_GAP_AXES[gt][3]):
                    gui.game.opt(gt, line, b)
                    movable = bool(gui.game.try_move_ex(d, gui.current_step)[0])
                    gui.game._clear_selection()
                    if movable:
                        out.append(((gt, line), anchor, b, d))
                        break
                else:
                    continue
                break
            if len(out) >= limit:
                return out
    return out


def mi_drag_vec(letter, cells=1.0):
    """沿方向字母拖 cells 格的屏幕位移（横竖 1 格、斜向 ½ 格）。"""
    dr, dc = MI_DIRS[letter]
    s = view.cell_size * gui.zoom
    return (dc * s * cells, dr * s * cells)


def mi_press_seam(gap, anchor):
    """第一下触控：点中这条缝。回传是否选中。

    已选中别条缝时第一下只是把它取消掉，得再点一次才选上（照玩家的做法）。
    """
    asx, asy = gui.world_to_screen(*anchor)
    asx, asy = int(round(asx)), int(round(asy))
    for _ in range(2):
        if gui.selected_gap == gap:
            return True
        fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (asx, asy)}))
    return gui.selected_gap == gap


def mi_press_block(blk):
    """第二下触控的「按下」：只该选中滑块组，不该提交移动。

    回传 (选中的是不是这块, 提示, 当时步数)。落点每回都按块的当前位置
    重算——上一手移动之后块已经不在原来的格里了。
    """
    bsx, bsy = gui.world_to_screen(*view.piece_center(*mi_key(blk)))
    bsx, bsy = int(round(bsx)), int(round(bsy))
    fire(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'button': 1, 'pos': (bsx, bsy)}))
    return gui.selected_block is blk, gui.macro_notify_msg, gui.step_count


def mi_drag(blk, direction, cells=1.0):
    """按住滑块沿 direction 拖 cells 格。回传 (是否进了跟随, 松手落点)。"""
    bsx, bsy = gui.world_to_screen(*view.piece_center(*mi_key(blk)))
    bsx, bsy = int(round(bsx)), int(round(bsy))
    vx, vy = mi_drag_vec(direction, cells)
    tx, ty = int(round(bsx + vx)), int(round(bsy + vy))
    fire(pygame.event.Event(pygame.MOUSEMOTION,
                            {'pos': (tx, ty), 'rel': (0, 0),
                             'buttons': (1, 0, 0)}))
    return gui.drag_following, (tx, ty)


def mi_release(end):
    fire(pygame.event.Event(pygame.MOUSEBUTTONUP, {'button': 1, 'pos': end}))


cands = mi_candidates()
check("找到可用的缝＋滑块＋方向", bool(cands),
      f"{len(cands)} 组，如 {[(g, d) for g, _a, _b, d in cands][:3]}")

if cands:
    gap, anchor, blk, direction = cands[0]
    # ---- 动画外：完整手势照旧提交一格（也是下面窗口测试的铺垫）
    check(f"第一下点缝选中 {gap}", mi_press_seam(gap, anchor))
    before = snap(gui)
    hit, msg, steps = mi_press_block(blk)
    check(f"第二下按下只选中滑块组（提示：{msg}）",
          hit and msg.startswith('选中滑块组'), msg or '')
    check("第二下按下不提交移动", steps == 0 and snap(gui) == before,
          f"step_count={steps}")
    following, end = mi_drag(blk, direction)
    check("拖动后进入跟随", following is True)
    mi_release(end)
    check("松手把这一步交给动画（步数等动画播完才记）",
          gui.animating is True and gui.step_count == 0, f"step_count={gui.step_count}")
    # 动画落点：anim_blocks 走到 anim_end_pos，其余块原地不动
    anim_set = set(gui.anim_blocks)
    landed = ({tuple(p) for p in gui.anim_end_pos}
              | {tuple(b.location) for b in gui.game.blocks
                 if b not in anim_set})
    check("动画落点确实动了（不是空动画）", landed != before)

    # ---- 动画窗口里：第二下只能选组，拖动进不了跟随
    mid_anim(gui)
    progress0 = gui.anim_progress
    check("动画已在半程", 0.4 < progress0 < 0.6, f"progress={progress0:.2f}")
    steps0 = gui.step_count
    hit, msg, steps = mi_press_block(blk)
    check(f"动画中第二下按下仍只选中滑块组（提示：{msg}）",
          hit and msg.startswith('选中滑块组'), msg or '')
    check("动画中第二下按下没有多走一步",
          steps == steps0 and snap(gui) == before, f"step_count={steps}")
    following, end = mi_drag(blk, direction)
    check("动画中拖动进不了跟随", following is False)
    check("动画中拖动给出动画提示",
          gui.macro_notify_msg == "动画播放中，无法移动",
          gui.macro_notify_msg or '')
    st = gui._mouse_drag_state
    check("拖动位移被记下（跟随便没起来 → 走 moved 兜底）",
          st is not None and st.get('moved') is True)
    mi_release(end)
    check("松手没有提交第二步、也没打断动画",
          gui.animating is True and gui.step_count == steps0,
          f"animating={gui.animating} step_count={gui.step_count}（期望 {steps0}）")
    gui.commit_animation()
    check("动画播完后仍只有那一步", gui.step_count == 1,
          f"step_count={gui.step_count}")
    check("局面就是那一步的落点", snap(gui) == landed)

    # ---- 动画结束后：同一套手势照旧生效（闸门不能把米字格拖拽整体禁掉）。
    # 上一手之后旧缝可能已经失效，重新探一组当前真做得出来的组合
    check("动画已结束", gui.animating is False)
    won = False
    for gap2, anchor2, blk2, direction2 in mi_candidates():
        base_steps = gui.step_count
        base_pos = snap(gui)
        if not mi_press_seam(gap2, anchor2):
            continue
        mi_press_block(blk2)
        following, end = mi_drag(blk2, direction2)
        mi_release(end)
        if following:
            gui.commit_animation()
            if gui.step_count == base_steps + 1 and snap(gui) != base_pos:
                won = True
                break
    check("动画结束后同一套手势又提交了一步", won,
          f"step_count={gui.step_count}")


print()
if _failures:
    print(f"FAILED {len(_failures)} 项：")
    for name in _failures:
        print("  -", name)
    sys.exit(1)
print("anim-click 回归 PASS")
