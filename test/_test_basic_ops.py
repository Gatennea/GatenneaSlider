# -*- coding: utf-8 -*-
"""基本操作冒烟测试：滑动 / 逆滑复原 / 撤回 / 重做 / 打乱 / 重置。

三形态（方形 / 三角 / 米字）各走一遍同一条玩家操作路径，锁两件事：
  1. 每个基本操作不抛异常、返回符合预期（功能确实可用）；
  2. 状态确实按预期变化（局面、步数、单一连通、还原判定）。

与 test/ 下其它「功能点测试」的分工：那些锁单个功能的边界行为
（带序号保留、合并快照、米字命中……），本文件锁「整条操作路径串起来
不崩」——大重构 / 混合改动后的第一道防线，也是新玩家的「游戏能不能玩」。

覆盖路径（每形态）：
  开局即还原态 → 滑动一次（局面变/步数1/非还原/仍单连通）
  → 逆滑一次完全复原 → 撤回 → 重做 → 打乱（非还原/仍单连通）
  → 重置回初始态。

执行：D:/python/python.exe -u test/_test_basic_ops.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import queue  # noqa: E402

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from game_triangle import GAP_DIRECTIONS as TRI_GAP  # noqa: E402
from game_mi import GAP_DIRECTIONS as MI_GAP  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def snap(gui):
    """局面的规范化快照：全部滑块坐标的多重集（三形态通用）。"""
    return sorted(tuple(b.location) for b in gui.game.blocks)


def connected(gui):
    """全盘是否单一连通（is_single_connected 是静态方法，吃位置集合）。

    三角/米字引擎有 positions()；方形从 blocks 提（语义等价）。
    """
    g = gui.game
    if hasattr(g, 'positions'):
        positions = g.positions()
    else:
        positions = {tuple(b.location) for b in g.blocks}
    return g.is_single_connected(positions)


# ---------------------------------------------------------------- 形态适配
# 方形引擎没有导出 GAP_DIRECTIONS 常量，按同构口径手写（与 game_mi 一致）。
_SQ_GAP = {'h': ('a', 'd'), 'v': ('w', 's')}
_GAP_TABLE = {'square': _SQ_GAP, 'triangle': TRI_GAP, 'mi': MI_GAP}


def gap_dirs(form, gap_type):
    """该形态该缝族允许的移动方向对——同族两个方向互为逆，逆滑直接取另一个。"""
    return _GAP_TABLE[form][gap_type]


def other_dir(form, gap_type, d):
    """同族里的另一个方向（= d 的逆方向）。"""
    pair = gap_dirs(form, gap_type)
    return pair[1] if d == pair[0] else pair[0]


def iter_gaps(gui):
    """穷举当前形态全部合法缝 (gap_type, line)。"""
    g = gui.game
    if hasattr(g, 'all_gaps'):          # 三角 / 米字
        yield from g.all_gaps()
    else:                                # 方形：内部缝线 0..m-2 / 0..n-2
        for line in range(g.m - 1):
            yield ('h', line)
        for line in range(g.n - 1):
            yield ('v', line)


def find_moves(gui, form):
    """每个缝族取一个合法移动（step=1 预演，不提交）。

    返回 [(gap_type, line, block, direction), ...]——方形 2 族、三角 3 族、
    米字 4 族各一条。这样滑动/逆滑路径对全部缝族都有覆盖，而不是只碰
    穷举顺序撞见的第一族。穷举过程会反复 opt（弄乱选中态），调用方
    拿到结果后需重新 opt 一次。
    """
    found = {}
    for gap_type, line in iter_gaps(gui):
        if gap_type in found:
            continue
        for blk in list(gui.game.blocks):
            gui.game.opt(gap_type, line, blk)
            for d in gap_dirs(form, gap_type):
                _pos, reason = gui.game.try_move_ex(d, 1)
                if reason == '':
                    found[gap_type] = (gap_type, line, blk, d)
                    break
            if gap_type in found:
                break
    return list(found.values())


# ---------------------------------------------------------------- 主流程
def run_form(gui, form, label):
    """一个形态走完整条操作路径。"""
    # 开局：干净历史 + 还原态
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0
    gui.selected_gap = None
    gui.selected_block = None
    check(f'[{label}] 开局即还原态', gui.game.is_solved())
    check(f'[{label}] 开局步数为 0', gui.step_count == 0)
    m0 = snap(gui)

    # ---- 滑动→逆滑：每个缝族各走一遍 ----
    moves = find_moves(gui, form)
    n_families = len(_GAP_TABLE[form])
    check(f'[{label}] 每个缝族都找到合法移动（{n_families} 族）',
          len(moves) == n_families,
          f'实得 {len(moves)} 族: {[m[0] for m in moves]}')
    for idx, (gap_type, line, blk, d) in enumerate(moves, 1):
        tag = f'{label} 动作{idx}[{gap_type}{line} {d}]'
        gui.selected_gap = (gap_type, line)
        gui.game.opt(gap_type, line, blk)
        gui.selected_block = blk
        gui._bump_move_session()
        before = gui.step_count
        check(f'[{tag}] 滑动一次提交成功', gui.move_selected_blocks(d))
        m1 = snap(gui)
        check(f'[{tag}] 滑动后局面改变', m1 != m0)
        check(f'[{tag}] 滑动后步数 +1', gui.step_count == before + 1,
              f'step={gui.step_count}')
        check(f'[{tag}] 滑动后非还原态', not gui.game.is_solved())
        check(f'[{tag}] 滑动后全盘单一连通', connected(gui))
        # 逆滑一次复原（同缝同块反方向；bump 保证是独立快照）
        back = other_dir(form, gap_type, d)
        gui._bump_move_session()
        before = gui.step_count
        check(f'[{tag}] 逆滑一次提交成功（{back}）',
              gui.move_selected_blocks(back))
        check(f'[{tag}] 逆滑后完全复原（局面回到开局）', snap(gui) == m0)
        check(f'[{tag}] 逆滑后判定为已还原', gui.game.is_solved())
        check(f'[{tag}] 逆滑后步数 +1', gui.step_count == before + 1,
              f'step={gui.step_count}')

    if not moves:
        return

    # ---- 撤回 / 重做（撤销最近一步 = 最后一次逆滑 → 回它的滑动态） ----
    gui.undo()
    check(f'[{label}] 撤回一步后回到滑动后的局面（撤销的是逆滑）',
          not gui.game.is_solved())
    gui.redo()
    check(f'[{label}] 重做后回复原态', gui.game.is_solved() and snap(gui) == m0)

    # ---- 打乱（非还原 + 仍单连通；极小概率洗完仍还原 → 重试） ----
    for _ in range(5):
        gui.shuffle_puzzle()
        if not gui.game.is_solved():
            break
    check(f'[{label}] 打乱后非还原态', not gui.game.is_solved())
    check(f'[{label}] 打乱后全盘单一连通', connected(gui))
    check(f'[{label}] 打乱后局面确已改变', snap(gui) != m0)

    # ---- 重置（同参重建 → 标准形确定生成，回初始态） ----
    gui.reset_puzzle()
    check(f'[{label}] 重置回初始态', snap(gui) == m0 and gui.game.is_solved())


def main():
    pygame.init()
    gui = SliderGUI(m=5, n=5, step=1, cmd_queue=queue.Queue())
    # 关动画：移动/撤销/重做走立即提交路径，断言才真正落到 game 状态
    gui.animation_enabled = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False

    forms = [
        ('square', '方形 5x5', lambda _g: gui.new_puzzle(5, 5, 1)),
        ('triangle', '三角 k=4', lambda _g: gui.new_triangle_puzzle(4, 1)),
        ('mi', '米字 3x3', lambda _g: gui.new_mi_puzzle(3, 3, 1)),
    ]
    for form, label, setup in forms:
        print(f"\n===== {label} =====")
        setup(gui)
        run_form(gui, form, label)

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} 项")
        for name in _failures:
            print("  -", name)
        sys.exit(1)
    print("ALL PASS")


if __name__ == '__main__':
    main()
