# -*- coding: utf-8 -*-
"""三維聚攏 MVP 回歸（P2）。

A. 3D 前綴和 / 目標盒重疊：與暴力枚舉逐值一致；
B. 還原態 score=1；平移後的實心盒仍 score=1；
C. `gather_solve_unified` 對 cubic 分派到 `cubic_gather_solve`；
D. 打亂 4×4×4 跑一輪短聚攏：動作可逐步重放，終態與返回的 end 指標一致，
   聚攏度不低於起點（停在歷史最優）；
E. GUI 播放轉換：三維 rep 必須保留三個分量；
F. 候選枚舉（逐分量 + rep_cell）：候選數等於引擎 legal_moves，每個候選
   的「落點座標預測」必須與真實執行結果一致；實心盒快速還原判定與
   自訂目標回落。

跑法：D:/python/python.exe test/_test_cubic_gather.py
"""
import os
import random
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from solver.ml.cubic_gather import (  # noqa: E402
    cubic_metrics, cubic_mod_constraints, _prefix3, _box_count,
    _apply_cubic_action, cubic_candidates, _solid_goal_signature,
    _solved_fast,
)

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return bool(cond)


def brute_metrics(coords, dims):
    """暴力：盒起點只需枚舉到碰到任一佔用格，與求解器口徑無關地直接數。"""
    import itertools
    if not coords:
        return 0, 0
    lo = (min(p[0] for p in coords), min(p[1] for p in coords),
          min(p[2] for p in coords))
    hi = (max(p[0] for p in coords), max(p[1] for p in coords),
          max(p[2] for p in coords))
    best = 0
    best_vol = 0
    for a, b, c in set(itertools.permutations(dims)):
        for x0 in range(lo[0] - a + 1, hi[0] + 1):
            for y0 in range(lo[1] - b + 1, hi[1] + 1):
                for z0 in range(lo[2] - c + 1, hi[2] + 1):
                    n = sum(1 for p in coords
                            if x0 <= p[0] < x0 + a
                            and y0 <= p[1] < y0 + b
                            and z0 <= p[2] < z0 + c)
                    if n > best or (n == best and a * b * c > best_vol):
                        best, best_vol = n, a * b * c
    return best, best_vol


print('=' * 60)
print('A. 3D 前綴和 vs 暴力')
random.seed(11)
for trial in range(20):
    pts = set()
    while len(pts) < 20:
        pts.add((random.randint(-3, 4), random.randint(-2, 5),
                 random.randint(-1, 4)))
    coords = sorted(pts)
    dims = (random.randint(2, 4), random.randint(2, 4), random.randint(2, 4))
    lo = (min(p[0] for p in coords), min(p[1] for p in coords),
          min(p[2] for p in coords))
    hi = (max(p[0] for p in coords), max(p[1] for p in coords),
          max(p[2] for p in coords))
    span = (hi[0] - lo[0] + 1, hi[1] - lo[1] + 1, hi[2] - lo[2] + 1)
    pref, _, _ = _prefix3(coords, lo, span)
    for _ in range(30):
        a = random.randint(1, 4)
        b = random.randint(1, 4)
        c = random.randint(1, 4)
        x0 = random.randint(lo[0] - 2, hi[0] + 1)
        y0 = random.randint(lo[1] - 2, hi[1] + 1)
        z0 = random.randint(lo[2] - 2, hi[2] + 1)
        got = _box_count(pref, lo, span, (x0, y0, z0, a, b, c))
        want = sum(1 for p in coords
                   if x0 <= p[0] < x0 + a and y0 <= p[1] < y0 + b
                   and z0 <= p[2] < z0 + c)
        check(got == want, f'trial{trial} box 計數 {got}={want}', (got, want))

    met = cubic_metrics(coords, dims)
    want_n, want_vol = brute_metrics(coords, dims)
    check(met['overlap'] == want_n,
          f'trial{trial} 最大重疊 {met["overlap"]}={want_n}',
          (met['overlap'], want_n))
    check(met['volume'] == want_vol,
          f'trial{trial} 最優盒體積 {met["volume"]}={want_vol}',
          (met['volume'], want_vol))

print('=' * 60)
print('A2. 三維 mod 不變量約束')
_full3 = [(i, j, k) for i in range(3) for j in range(3) for k in range(3)]
_mod3 = cubic_mod_constraints(_full3, (3, 3, 3), 2)
check(_mod3 is not None, '3×3×3 / step2 有客觀 mod 約束', _mod3)
check(_mod3 and _mod3.get((3, 3, 3)) == (
    frozenset({0}), frozenset({0}), frozenset({0})),
      '3×3×3 / step2 的起點餘數被鎖在 (0,0,0)', _mod3)
_mc0 = cubic_metrics(_full3, (3, 3, 3), step=2)
check(_mc0['window'] == (0, 0, 0, 3, 3, 3) and _mc0['score'] == 1.0,
      '套 mod 約束後仍能找到唯一滿分窗口', _mc0)
# 人為只允許 (1,1,1)：若過濾真的生效，3×3×3 全盤只剩 2×2×2=8 塊
_cmc = cubic_metrics(
    _full3, (3, 3, 3), step=2,
    mod_constraints={(3, 3, 3): (
        frozenset({1}), frozenset({1}), frozenset({1}))})
check(_cmc['overlap'] == 8
      and all(_cmc['window'][i] % 2 == 1 for i in range(3)),
      'mod 約束真的排掉不符合的窗口起點（只剩餘數 1）', _cmc)
check(cubic_mod_constraints(_full3, (3, 3, 3), 1) is None,
      'step=1 無約束', cubic_mod_constraints(_full3, (3, 3, 3), 1))
check(cubic_mod_constraints(
          [(i, j, k) for i in range(4) for j in range(4) for k in range(4)],
          (4, 4, 4), 2) is None,
      '三軸都被 step 整除時無約束')

print('=' * 60)
print('B. 還原態 / 平移盒')
_solved = [(i, j, k) for i in range(2) for j in range(3) for k in range(4)]
_m = cubic_metrics(_solved, (2, 3, 4))
check(_m['score'] == 1.0 and _m['overlap'] == 24,
      '還原態 score=1 / overlap=24', _m)
_shifted = [(i + 3, j - 2, k + 5) for i, j, k in _solved]
_m2 = cubic_metrics(_shifted, (2, 3, 4))
check(_m2['score'] == 1.0,
      '整體平移後仍 score=1（不依賴絕對原點）', _m2)
# 軸置換：2×3×4 換成 4×2×3 也該算滿
_rot = [(i, j, k) for i in range(4) for j in range(2) for k in range(3)]
_m3 = cubic_metrics(_rot, (2, 3, 4))
check(_m3['score'] == 1.0,
      '6 種軸排列都認（4×2×3 vs 2×3×4 也滿分）', _m3)

print('=' * 60)
print('C. 統一入口分派')
from solver import solver_supports, gather_solve_unified  # noqa: E402
from solver.ml.cubic_gather import cubic_gather_solve  # noqa: E402

check(solver_supports('gather', 'cubic'), 'gather 支持 cubic')
check(not solver_supports('hybrid', 'cubic'),
      'hybrid 仍明確不支持 cubic（不靜默套二維）')
check(gather_solve_unified is not None, 'gather_solve_unified 可 import')

print('=' * 60)
print('D. 打亂 4×4×4 短聚攏 + 逐步重放')
pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_gather_')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.tutorial_active = False
gui.tut_show_prompt = False
gui._cubic_camera_prefs = {}
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui.new_cubic_puzzle(4, 4, 4, 1)
gui.cubic_gap = 0.12
# 直接走引擎 shuffle：GUI 的 shuffle_puzzle 会受用戶 config（infinite_shuffle
# 等）影响，測試不該改用戶配置，也不該把「首次打亂=開始無限打亂」吃進來。
random.seed(21)
gui.game.shuffle(300, 1, record=[])
gui.game_history.reset()
gui.step_count = 0

_start_snap = gui.game.snapshot_state()
_start_score = cubic_metrics([tuple(b.location[:3]) for b in gui.game.blocks],
                             (4, 4, 4))['score']
_result = gather_solve_unified(gui.game, step=1, max_steps=24, patience=10,
                               max_wait_time=8, target_gather_score=None)
check(_result.get('form') == 'cubic', '統一入口回 form=cubic', _result.get('form'))
check(isinstance(_result.get('actions'), list) and len(_result['actions']) > 0,
      f'有可播放動作（{len(_result.get("actions", []))} 步）')
check(_result.get('ignored_kwargs') == [], '無多餘 kwargs 被吞（本次不傳參數）')
_end_score = _result['end']['score']
check(_end_score >= _start_score - 1e-9,
      f'聚攏度不低於起點（{_start_score:.3f}→{_end_score:.3f}）',
      (_start_score, _end_score))

# 用起點快照重放返回的 actions，逐步必須成功，終態要等於返回 end。
gui.game.restore_state(_start_snap)
for i, act in enumerate(_result['actions']):
    res = _apply_cubic_action(gui.game, act, 1)
    if res is None:
        check(False, f'第{i}步動作在起點快照上不可重放', act)
        break
else:
    check(True, '全部動作可在起點快照上逐步重放')
    _replay = cubic_metrics([tuple(b.location[:3]) for b in gui.game.blocks],
                            (4, 4, 4))
    check(_replay['overlap'] == _result['end']['overlap'],
          '重放終態 overlap 與返回 end 一致',
          (_replay['overlap'], _result['end']['overlap']))

print('=' * 60)
print('E. GUI 播放轉換：三維 rep 必須保留三個分量')
gui.game.restore_state(_start_snap)
gui.current_step = 1
gui._auto_solve_start_time = __import__('time').time()
check(gui._current_kind() == 'cubic' and not gui._is_model_kind(),
      '三維局不被誤判成模型板型（求解器 gate 不會提前拒）',
      (gui._current_kind(), gui._is_model_kind()))
_real_next = gui._execute_next_macro_step
gui._execute_next_macro_step = lambda: None   # 只看轉換，不真的播完整串
try:
    gui._handle_gather_result(_result)
finally:
    gui._execute_next_macro_step = _real_next
check(gui.macro_executing is True, '三維聚攏結果真的進入宏播放態')
check(len(gui.macro_exec_ops) == len(_result['actions']),
      'op 數量與 actions 一致', (len(gui.macro_exec_ops), len(_result['actions'])))
check(all(len(op.get('rep_cell', ())) == 3 for op in gui.macro_exec_ops),
      '每個 op 的 rep_cell 都是三元組（沒被 2D 分支截成兩分量）',
      [op.get('rep_cell') for op in gui.macro_exec_ops[:2]])
check(all(op.get('kind') is None or op.get('kind') == 'cubic'
          for op in gui.macro_exec_ops),
      '三維 op 走 gap_type r/c/d，不需硬塞 kind 也會被 _execute_next_macro_step 認')
# 播放期两条文案都必须走三元 bbox：_update_gather_notify 每步刷、_finish_gather
# 收尾刷。二维解包会直接 ValueError（2026-11-19 实测）。
gui._update_gather_notify()
check('×' in gui.macro_notify_msg and '聚拢' in gui.macro_notify_msg,
      '三維播放中的聚攏提示可用三元邊界盒', gui.macro_notify_msg)
gui._finish_gather()
check('边界盒' in gui.macro_notify_msg and '×' in gui.macro_notify_msg,
      '三維聚攏收尾文案不被二元 bbox 打斷', gui.macro_notify_msg)

print('=' * 60)
print('F. 候選枚舉：逐分量 + rep_cell + 落點預測')
_sig = _solid_goal_signature(gui.game.spec, (4, 4, 4))
check(_sig == (64, (4, 4, 4)),
      '4×4×4 實心目標有快判簽名（64 塊 / 邊長有序 4,4,4）', _sig)
check(_solid_goal_signature(gui.game.spec, (4, 4, 3)) is None,
      '目標體積與 board 體積不符時不給快判簽名（回落引擎 48 對稱判據）')
_box = [(i, j, k) for i in range(4) for j in range(4) for k in range(4)]
check(_solved_fast(_box, cubic_metrics(_box, (4, 4, 4)), _sig) is True,
      '還原態快判為 True')
gui.game.restore_state(_start_snap)
_scr = [tuple(b.location[:3]) for b in gui.game.blocks]
check(_solved_fast(_scr, cubic_metrics(_scr, (4, 4, 4)), _sig) is False,
      '打亂態快判為 False（不誤報還原）')

gui.game.restore_state(_start_snap)
_moves = gui.game.board.legal_moves(1)
_cands = cubic_candidates(gui.game, 1)
check(len(_cands) == len(_moves),
      f'候選數等於引擎 legal_moves（{len(_cands)}={len(_moves)}）')
check(all(len(a) == 5 and len(a[4]) == 3 for a, _c, _m in _cands),
      '每個候選動作都帶三元 rep_cell（第五分量）')
_groups = {}
for _a, _c, _m in _cands:
    _groups[_a[:3]] = _groups.get(_a[:3], 0) + 1
check(any(v > 2 for v in _groups.values()),
      '同一 (縫, 側) 出現多個分量動作（舊枚舉只取首塊所在分量）',
      max(_groups.values()) if _groups else 0)
_snap = gui.game.snapshot_state()
_bad = []
for _idx, (_a, _coords, _m) in enumerate(_cands):
    _res = _apply_cubic_action(gui.game, _a, 1)
    if _res is None:
        _bad.append((_idx, 'apply_none', _a))
    else:
        _after = sorted(tuple(b.location[:3]) for b in gui.game.blocks)
        if _after != sorted(_coords):
            _bad.append((_idx, 'pred_mismatch', _a))
    gui.game.restore_state(_snap)
check(not _bad,
      f'全部 {len(_cands)} 個候選可執行，且落點座標預測與真實執行一致',
      _bad[:3])
gui.game.restore_state(_start_snap)

print('=' * 60)
print(f'{_ok[0]} ok, {len(_fail)} failed')
if _fail:
    for msg in _fail:
        print('FAIL:', msg)
    raise SystemExit(1)
