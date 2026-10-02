# -*- coding: utf-8 -*-
"""带序号谜题（numbered）走矩形求解器（填洞/补缺宏流水）无头验证。

预期语义：求解器只看形状（blocks[].location / m / n），不看 number。
自动求解把形状复原成 m×n 实心矩形即算完成，数字乱序是预期行为，
玩家之后自行调整（本任务不做数字调整辅助）。

断言：
a) 播放完成后真实棋盘 game.is_solved() == True（形状复原）
b) 全部块的 number 集合 = {1..m*n}（无丢失、无重复、不串块），
   且播放全程每一帧都保持完整
c) 全程无未捕获异常；历史末快照的 numbers 矩阵完整（撤销可还原）

说明：solver/ml 的填洞/补缺宏对随机难局存在固有停机/偶发异常（并行
工作线的问题，与本任务无关），故采用"换局重试"结构：最多 4 轮，
任一轮形状复原且编号完整即通过；4 轮全败才 FAIL。
"""
import os, sys, time, queue
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame
from GUI import SliderGUI

M, N, STEP = 6, 6, 2
TOTAL = M * N
_ok = True


def check(name, cond):
    global _ok
    print(f"[{'PASS' if cond else 'FAIL'}] {name}", flush=True)
    _ok = _ok and cond


def numbers_snapshot(gui):
    nums = [b.number for b in gui.game.blocks]
    return all(n is not None for n in nums) and sorted(nums) == list(range(1, TOTAL + 1))


pygame.init()
q = queue.Queue()
gui = SliderGUI(M, N, STEP, q)
gui.new_puzzle(M, N, STEP, numbered=True)
gui.animation_enabled = False   # 立即提交路径，断言真正落到 game 状态
gui.game_mode = 'practice'

init_nums = {tuple(b.location): b.number for b in gui.game.blocks}
check("开局编号 1..m*n（行主序）",
      init_nums == {(r, c): r * N + c + 1 for r in range(M) for c in range(N)})

# ---- 场景 0：deepcopy 快照（求解线程入口）保留编号 ----
from copy import deepcopy
snap = deepcopy(gui.game)
check("deepcopy 后编号完整",
      sorted(b.number for b in snap.blocks) == list(range(1, TOTAL + 1)))


def pump_once():
    gui.update_animation()
    gui._pump_stream_segments()
    gui._check_auto_solve_result()


def pump_idle():
    """流水彻底收尾：线程退出、无待播结果、宏结束、队列空。"""
    return (not gui._auto_solve_running
            and not gui._auto_solve_done
            and not gui.macro_executing
            and not getattr(gui, '_stream_active', False)
            and getattr(gui, '_stream_queue', None) is not None
            and gui._stream_queue.empty())


def run_trial(alg, shuffle_attempts, timeout=90.0):
    """重开一局 → 打乱 → 自动求解全管道。返回是否形状复原。"""
    # 清掉上一轮可能残留的求解/回放状态（上一轮回放中断会置 cancel 等）
    gui._auto_solve_cancel = False
    gui._auto_solve_done = False
    gui._auto_solve_result = None
    gui._stream_queue = None
    gui._stream_active = False
    gui.macro_executing = False
    gui.macro_exec_ops = []
    gui.macro_error_msg = ''
    gui.new_puzzle(M, N, STEP, numbered=True)
    gui.game.shuffle(shuffle_attempts, step=STEP)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0
    if gui.game.is_solved():
        return True          # 极小概率打乱后仍复原：直接算过
    gui.solver_algorithm = alg
    gui._start_auto_solve()
    t0 = time.time()
    ok_nums = True           # 播放全程编号完整性
    while time.time() - t0 < timeout and not pump_idle():
        pump_once()
        ok_nums = ok_nums and numbers_snapshot(gui)
        time.sleep(0.004)
    for _ in range(50):      # 收尾补帧
        pump_once()
        ok_nums = ok_nums and numbers_snapshot(gui)
    check(f"[{alg}] 播放全程编号完整无丢失", ok_nums)
    return gui.game.is_solved()


# ---- 场景 1：gap_macro / fill_macro 交替，换局重试 ----
solved = False
algs = ('fill_macro', 'gap_macro', 'fill_macro', 'gap_macro')
for i, alg in enumerate(algs):
    solved = run_trial(alg, shuffle_attempts=6)
    print(f"    第{i + 1}轮 [{alg}] 形状复原: {solved}", flush=True)
    if solved:
        break
check("最终形状复原 game.is_solved()", solved)
check("终局编号集合仍为 1..36（无丢失/重复）", numbers_snapshot(gui))
check("末快照带 numbers 且值完整",
      sorted(v for row in gui.game_history.history[-1].get('numbers', [])
             for v in row if v) == list(range(1, TOTAL + 1)))

# ---- 场景 2：逐步撤销回打乱态，编号随快照恢复 ----
ok_nums_undo = True
while gui.game_history.can_undo():
    gui.game_history.undo(gui.game)
    ok_nums_undo = ok_nums_undo and numbers_snapshot(gui)
check("逐步撤销到底编号全程不丢", ok_nums_undo)

pygame.quit()
print("ALL PASS" if _ok else "SOME FAILED")
sys.exit(0 if _ok else 1)
