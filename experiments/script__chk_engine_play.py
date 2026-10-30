"""几何引擎下的「求解体验是否一致」对照。

问法不是「引擎内部对不对」，而是**同一个打乱局面，旧引擎与几何引擎跑同一
个求解器，结果是否同形**——这才是玩家按「指示/求解」时的体感。

做法：固定随机种子打乱旧引擎 → 把同一份位置灌给 EngineGame → 两边各跑
`solver.gather_solve_unified`（默认确定性）→ 比对 reason / 步数 / solved。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import engine.config as ecfg  # noqa: E402
import puzzle_types  # noqa: E402
import solver  # noqa: E402

CASES = [
    ('square', 4, 4, 2, None, 6),
    ('square', 3, 3, 1, None, 4),
    ('triangle', 3, 3, 1, 3, 6),
    ('mi', 3, 3, 1, None, 6),
]

_fails = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        _fails.append(msg)


def build_old(kind, m, n, tri_k):
    ecfg.set_enabled(False)
    return puzzle_types.create_puzzle(m, n, 1, kind, triangle_side=tri_k)


def play(kind, m, n, step, tri_k, attempts):
    old = build_old(kind, m, n, tri_k)
    random.seed(20261021)
    old.shuffle(attempts, step, bias=0.0, min_score=0.7)
    cells = sorted(tuple(b.location) for b in old.blocks)

    # 同一个局面灌给引擎（geometry 侧按 kind 建局再覆盖位置）
    ecfg.set_enabled(True)
    eng = puzzle_types.create_puzzle(m, n, step, kind, triangle_side=tri_k)
    assert type(eng).__name__ == 'EngineGame', f"没走引擎 {type(eng).__name__}"
    Blk = type(eng.blocks[0])
    eng.blocks = [Blk(list(p), None) for p in cells]
    eng.update_matrix()

    check(eng.positions() == set(cells), f"{kind} 灌入位置一致（{len(cells)} 块）")

    # 两边跑同一个求解器（确定性）
    random.seed(1)
    r_old = solver.gather_solve_unified(old, step=step) or {}
    random.seed(1)
    r_eng = solver.gather_solve_unified(eng, step=step) or {}
    a_old = r_old.get('actions') or []
    a_eng = r_eng.get('actions') or []
    print(f"    旧: reason={r_old.get('reason')} 步={len(a_old)} "
          f"solved={r_old.get('solved')}")
    print(f"    引擎: reason={r_eng.get('reason')} 步={len(a_eng)} "
          f"solved={r_eng.get('solved')}")
    check(len(a_old) == len(a_eng),
          f"{kind} 解法步数一致（{len(a_old)} vs {len(a_eng)}）")
    check(bool(r_old.get('solved')) == bool(r_eng.get('solved')),
          f"{kind} solved 判定一致"
          f"（{r_old.get('solved')} vs {r_eng.get('solved')}）")
    check(a_old == a_eng, f"{kind} 解法动作逐项一致")
    # 走完解后两边局面同形
    check(old.is_solved() == eng.is_solved(),
          f"{kind} 走完解 is_solved 一致"
          f"（{old.is_solved()} vs {eng.is_solved()}）")
    ecfg.set_enabled(False)


if __name__ == '__main__':
    for kind, m, n, step, tri_k, att in CASES:
        print(f"== {kind} {m}x{n} s{step} ==")
        try:
            play(kind, m, n, step, tri_k, att)
        except Exception as e:
            import traceback
            print(f"  !! {kind} 抛异常 {type(e).__name__}: {e}")
            traceback.print_exc()
            _fails.append(f"{kind} 异常 {e}")
            ecfg.set_enabled(False)
    print()
    if _fails:
        print(f"失败 {len(_fails)} 项：")
        for f in _fails:
            print("  -", f)
        sys.exit(1)
    print("全部通過")
