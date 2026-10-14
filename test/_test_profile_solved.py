# -*- coding: utf-8 -*-
"""階段1 驗證：is_solved_by_profile 與 game.is_solved() 完全一致。

策略：多方格 × 多 step，從還原態隨機走訪（保連通），在每個局面同時用兩種
判定比對。隨機走訪天然覆蓋「還原(True)」與「非還原(False)」兩類局面。
"""

import random
import sys

sys.path.insert(0, ".")

from solver.ml.fill_macro import build_game  # noqa: E402
from solver.actions import enumerate_valid_actions, apply_action  # noqa: E402
from solver.ml.invariants import is_solved_by_profile, profile_defect  # noqa: E402


def coords_of(g):
    return frozenset((b.location[0], b.location[1]) for b in g.blocks)


def run_case(m, n, step, n_steps, seed):
    random.seed(seed)
    solved = set((r, c) for r in range(m) for c in range(n))
    g = build_game(solved, m, n)
    # 還原態：兩者皆 True
    assert g.is_solved() is True, "start must be solved"
    assert is_solved_by_profile(solved, m, n) is True, "profile must agree (solved)"
    # 平移不變：搬到別處仍是還原
    shifted = set((r + 7, c + 11) for r, c in solved)
    assert is_solved_by_profile(shifted, m, n) is True, "profile must be position-independent"

    agree = 0
    checked = 0
    for _ in range(n_steps):
        cands = enumerate_valid_actions(g, step)
        if not cands:
            break
        act = random.choice(cands)
        if not apply_action(g, act, step):
            continue
        coords = coords_of(g)
        a = g.is_solved()
        b = is_solved_by_profile(coords, m, n)
        checked += 1
        if a == b:
            agree += 1
        else:
            print("MISMATCH m=%d n=%d step=%d coords=%s game=%s profile=%s"
                  % (m, n, step, sorted(coords)[:5], a, b))
    return checked, agree


def main():
    cases = [
        (4, 4, 2, 400, 1),
        (5, 5, 2, 400, 2),
        (6, 6, 2, 300, 3),
        (8, 8, 2, 200, 4),
        (4, 6, 3, 300, 5),
        (4, 4, 2, 400, 6),
    ]
    total_checked = 0
    total_agree = 0
    for m, n, step, n_steps, seed in cases:
        c, a = run_case(m, n, step, n_steps, seed)
        total_checked += c
        total_agree += a
        print("case m=%d n=%d step=%d: %d/%d agree" % (m, n, step, a, c))
    print("TOTAL: %d/%d agree" % (total_agree, total_checked))
    assert total_checked > 0
    assert total_agree == total_checked, "is_solved_by_profile 與 game.is_solved 不一致！"
    # profile_defect 形態守衛：必須是單一標量，且還原態為 0
    solved = set((r, c) for r in range(8) for c in range(8))
    phi = profile_defect(solved, 8, 8)
    assert isinstance(phi, (int, float)), "profile_defect 必須返回標量"
    assert phi == 0, "還原態 Φ 必須為 0"
    print("profile_defect 標量/還原=0 guard OK")
    print("ALL PASS")


if __name__ == "__main__":
    main()
