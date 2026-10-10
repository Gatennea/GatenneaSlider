# -*- coding: utf-8 -*-
"""階段0 守衛：度量函數必須顯式接收 (m,n)，禁止依賴模塊級常量。

鎖住求解器優化發現.md §六 的事故教訓：跨模組復用寫死尺寸的度量函數會對
非 4×4 盤面靜默回傳 0（等於「免費」且「引導=隨機走」）。
"""

import sys

sys.path.insert(0, ".")

from solver.ml.gather_solver import max_overlap, gather_score  # noqa: E402
from solver.ml.invariants import profile_defect  # noqa: E402


def test_max_overlap_explicit_size():
    # 4×4 還原態
    solved4 = set((r, c) for r in range(4) for c in range(4))
    assert max_overlap(solved4, 4, 4) == 16
    assert gather_score(solved4, 4, 4) == 1.0
    # 4×4 非還原態：得分必須在 (0,1) 之間
    scrambled4 = set(solved4)
    scrambled4.discard((0, 0))
    scrambled4.add((10, 10))  # 移一格到框外
    s4 = gather_score(scrambled4, 4, 4)
    assert 0.0 < s4 < 1.0, "非還原 4×4 聚攏度必須非平凡，得到 %r" % s4

    # 8×8 還原態
    solved8 = set((r, c) for r in range(8) for c in range(8))
    assert max_overlap(solved8, 8, 8) == 64
    assert gather_score(solved8, 8, 8) == 1.0
    # 8×8 非還原態：必須非平凡（不能因為沒傳尺寸而回傳 0）
    scrambled8 = set(solved8)
    scrambled8.discard((0, 0))
    scrambled8.add((20, 20))
    s8 = gather_score(scrambled8, 8, 8)
    assert 0.0 < s8 < 1.0, "非還原 8×8 聚攏度必須非平凡，得到 %r（靜默回傳 0？）" % s8


def test_profile_defect_explicit_size():
    solved8 = set((r, c) for r in range(8) for c in range(8))
    # 還原態 Φ = 0
    assert profile_defect(solved8, 8, 8) == 0
    # 非還原態 Φ > 0 且是單一標量（不是矩陣/向量）
    scrambled8 = set(solved8)
    scrambled8.discard((0, 0))
    scrambled8.add((20, 20))
    phi = profile_defect(scrambled8, 8, 8)
    assert isinstance(phi, (int, float)), "profile_defect 必須返回標量"
    assert phi > 0, "非還原 8×8 Φ 必須 > 0，得到 %r" % phi

    # 4×4 也必須非平凡
    scrambled4 = set((r, c) for r in range(4) for c in range(4))
    scrambled4.discard((0, 0))
    scrambled4.add((9, 9))
    assert profile_defect(scrambled4, 4, 4) > 0


def main():
    test_max_overlap_explicit_size()
    test_profile_defect_explicit_size()
    print("ALL PASS: 度量函數介面守衛通過（顯式帶尺寸、8×8 不靜默回傳 0）")


if __name__ == "__main__":
    main()
