"""定位 EngineGame 上求解失败的那一刻：同状态比动作空间 + 抓失败动作。"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import engine.config as ecfg  # noqa: E402
import puzzle_types  # noqa: E402
import solver  # noqa: E402
from solver.actions import apply_action, enumerate_valid_actions  # noqa: E402

m, n, step = 3, 3, 1


def fresh(cells, enabled, kind='square'):
    ecfg.set_enabled(enabled)
    g = puzzle_types.create_puzzle(m, n, step, kind)
    if enabled:
        Blk = type(g.blocks[0])
        g.blocks = [Blk(list(p), None) for p in cells]
    else:
        g.blocks = [type(g.blocks[0])(list(p)) for p in cells]
    g.update_matrix()
    return g


# --- 起始局面（同一个）---
ecfg.set_enabled(False)
old0 = puzzle_types.create_puzzle(m, n, 1, 'square')
random.seed(20261021)
old0.shuffle(4, step, bias=0.0, min_score=0.7)
START = sorted(tuple(b.location) for b in old0.blocks)

print("-- 同状态动作空间对照（起点）--")
o = fresh(START, False)
e = fresh(START, True)
oa = sorted(enumerate_valid_actions(o, step))
ea = sorted(enumerate_valid_actions(e, step))
print("旧:", len(oa), "引擎:", len(ea))
print("仅旧有:", sorted(set(oa) - set(ea)))
print("仅引擎有:", sorted(set(ea) - set(oa)))

# --- 沿旧引擎的解逐态对照 ---
random.seed(1)
r_old = solver.gather_solve_unified(fresh(START, False), step=step) or {}
acts = r_old.get('actions') or []
print("\n旧引擎解:", acts)

cur = list(START)
for i, a in enumerate(acts):
    o = fresh(cur, False)
    e = fresh(cur, True)
    oa = sorted(enumerate_valid_actions(o, step))
    ea = sorted(enumerate_valid_actions(e, step))
    diff_only_old = sorted(set(oa) - set(ea))
    diff_only_eng = sorted(set(ea) - set(oa))
    if diff_only_old or diff_only_eng:
        print(f"\n[{i}] 动作空间分歧 @ {sorted(cur)}")
        print("   仅旧有:", diff_only_old)
        print("   仅引擎有:", diff_only_eng)
        print("   all_gaps 旧:", sorted(o.all_gaps()),
              "引擎:", sorted(e.all_gaps()))
    ok = apply_action(e, a, step)
    if not ok:
        print(f"\n[{i}] 引擎走不动 {a} @ {sorted(cur)}")
        break
    cur = sorted(tuple(b.location) for b in e.blocks)

# --- 引擎自己求解，抓失败 ---
print("\n-- 引擎自己跑求解器 --")
random.seed(1)
g = fresh(START, True)
before_states = []
_orig = apply_action


def _spy(game, action, step_):
    before_states.append(sorted(tuple(b.location) for b in game.blocks))
    ok = _orig(game, action, step_)
    if not ok:
        print(f"  失败动作 {action} @ {before_states[-1]}")
    return ok


import solver.ml.gather_solver as gs  # noqa: E402

gs.apply_action = _spy
r = gs.gather_solve(g, step=step)
print("reason:", r.get('reason'), "步:", len(r.get('actions') or []),
      "solved:", r.get('solved'))
print("动作:", r.get('actions'))
