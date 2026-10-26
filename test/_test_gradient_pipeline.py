# -*- coding: utf-8 -*-
"""验证梯度流水线：后台并行计算 + 主线程顺序播动画 + 取消语义。"""
import os, sys, time
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import solver.ml.gather_solver as gs_mod

# ⚠️ 引擎开关是**全局磁盘配置**（config/engine.json）：全套里跑在前面的几何引擎
# 测试会把它打开并留在磁盘上，于是本测试的 `new_puzzle(4,4,2)` 建出 EngineGame，
# `_start_auto_solve` 直接不启动（几何通道只认 'gather'），在「启动后状态非空且
# 后台忙」处假红。本测试要的是经典引擎 + gather_gradient，显式关掉，别依赖
# 「跑之前有人删过 engine.json」这种外部前提。
from engine import config as _ecfg  # noqa: E402

_ecfg.set_enabled(False)

# 收敛测试速度：每阶段给很小的参数，保证几步内结束且稳定
_FAST = {'max_steps': 40, 'patience': 10, 'max_wait_time': 3,
         'target_gather_score': 1.0, 'aggressiveness': 0.0}
_orig_predict = gs_mod.predict_params
gs_mod.predict_params = lambda game, step: dict(_FAST)

from GUI import SliderGUI

gui = SliderGUI(m=4, n=4, step=2)
gui.game_mode = 'practice'
gui.new_puzzle(4, 4, 2)
# ⚠️ 只读标记是**从 config/temp_history.json 恢复**的会话状态：全套里前面的
# 只读/防覆盖类测试会留下 `readonly: true` 的自动存档，于是这里的
# `_start_auto_solve` 撞 `_readonly_blocked()` 静默返回，在「启动后状态非空
# 且后台忙」处假红（2026-10-25 全套实测，主因不是引擎开关）。本测试要的是
# 一个可写的普通局面，显式清掉，别依赖外部残留。
gui._readonly = False
gui.save_readonly_flag = False
gui.solver_algorithm = 'gather_gradient'
gui.animation_duration = 60   # 每步动画 60ms，便于观察并行窗口
gui.animation_enabled = True

def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    globals()['_ok'] = globals().get('_ok', True) and cond

def pump_until(cond_fn, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        gui.update_animation()
        gui._check_auto_solve_result()
        if cond_fn():
            return True
        time.sleep(0.01)
    # 最后再补几帧
    for _ in range(30):
        gui.update_animation()
        gui._check_auto_solve_result()
        time.sleep(0.005)
    return cond_fn()

# ---- 场景 1：接近复原的棋盘，管线自行推进到完成 ----
gui.game.shuffle(6, step=2)
gui.game_history.reset()
gui.game_history.save_snapshot(gui.game)
gui.step_count = 0
check("启动前状态为空", gui._gradient_state is None)
_gen_before = gui._gradient_gen
gui._start_auto_solve()
# 竞态安全：本场景谜题极简单（4x4 仅打乱 6 步 + _FAST 参数），后台线程
# 可能在 _start_auto_solve() 返回、主线程跑到这条断言之前就已算完并把
# _gradient_state 清空、_gradient_busy 置 False —— 旧断言因此偶发假红。
# 改用同步自增的世代计数器 `_gradient_gen` 证明「梯度流水线确实被启动」
# （早返回被闸门拦住则不会递增，照样能抓真回归）；它只增不减，不受线程
# 完成时序影响。
check("启动后梯度流水线已启动（世代自增）", gui._gradient_gen > _gen_before)

concurrency_seen = False
done = pump_until(lambda: gui._gradient_state is None and not gui.macro_executing and not gui._gradient_busy, 30)
# 并行证据：动画播放期间队列里已有后台算好的后续结果
if gui._gradient_queue.qsize() > 0:
    concurrency_seen = True
if not done:
    concurrency_seen = concurrency_seen or (not gui._gradient_queue.empty())

check("管线最终收尾（状态清空、线程退出）", done)
check("真实棋盘块数不变", len(gui.game.blocks) == 16)

# ---- 场景 2：手动移动会终止流水线 ----
gui.new_puzzle(4, 4, 2)
gui.game.shuffle(20, step=2)
gui.game_history.reset()
gui.game_history.save_snapshot(gui.game)
gui.step_count = 0
gui._start_auto_solve()
t0 = time.time()
while (gui._gradient_state is None and not gui._gradient_busy) and time.time() - t0 < 5:
    time.sleep(0.01)
was_active = gui._gradient_state is not None or gui._gradient_busy
gui._stop_gradient_pipeline()
check("终止后状态清空、取消置位、队列清空",
      gui._gradient_state is None and gui._auto_solve_cancel and gui._gradient_queue.empty())
pump_until(lambda: True, 0.3)
check("终止后不复活", gui._gradient_state is None and not gui.macro_executing)
del was_active

# ---- 场景 3：终止后可重新启动 ----
gui._auto_solve_cancel = False
gui._start_auto_solve()
ok3 = pump_until(lambda: gui._gradient_state is None and not gui._gradient_busy, 30)
check("重新启动并正常收尾", ok3)

# 收尾：确保后台线程退出
gui._auto_solve_cancel = True
gui._stop_gradient_pipeline()

gs_mod.predict_params = _orig_predict
print(f"\n并行证据(动画未播完阶段已排队): {concurrency_seen}")
print("ALL PASS" if globals().get('_ok', True) else "SOME FAILED")
sys.exit(0 if globals().get('_ok', True) else 1)
