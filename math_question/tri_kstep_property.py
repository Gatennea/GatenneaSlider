# -*- coding: utf-8 -*-
"""三角形谜题「可动性」门槛：验证是否必须「边长 − 等级 ≥ 2」。

背景（用户 2026-10-12 发现）：TriangleSliderMatrix(3).shuffle(n, 2) 恒回还原态，
推测三角形谜题存在「k − step ≥ 2」的可动性门槛，本脚本穷举验证之。

机理假设：缝隙把棋盘切成两片，切片沿缝的平行方向滑动；每推一格都要求
「无碰撞 + 整体仍连通」，所以切片与剩下部分的接触面长度 L 必须满足
L − step ≥ 1，即 L ≥ step + 1。边长 k 的实心三角形，同族切口长度依次为
1..k−1，最长 L = k−1，于是「存在合法移动」⟺ k − 1 ≥ step + 1
⟺ k − step ≥ 2。

验证方式：
  1) 穷举：从还原态枚举全部（缝隙 × 方向 × 锚块）组合，统计合法移动数；
  2) 交叉：用 shuffle 反复打乱，看能否真的离开还原态。
两者都只关心「还原态下是否存在合法移动」——不存在则打乱无从起步，
该 (k, step) 组合实际上是开不出局的死配置。

用法：D:/python/python.exe -u math_question/tri_kstep_property.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_triangle import TriangleSliderMatrix, GAP_DIRECTIONS  # noqa: E402

K_MAX = 8             # 边长上限（含）
SHUFFLE_TRIES = 3     # 每个组合重复打乱次数（随机性取「存在即算能打乱」）
SHUFFLE_ATTEMPTS = 60  # 每次打乱的随机移动步数

# 打乱校验必须传 min_score=None：默认口径下 shuffle 会为「聚拢度不够散」反复重洗
# （最多 attempts*3 轮 × 每轮 attempts 步），对不可动组合必然跑满 12 万步，
# 单个组合就要几分钟。而本脚本只问「能否离开还原态」，不需要重洗。


def legal_move_count(k, step):
    """还原态下穷举（缝隙 × 方向 × 锚块），返回 (合法移动数, 首个可行组合)。"""
    g = TriangleSliderMatrix(k)
    count = 0
    sample = None
    for gap_type, line in g.all_gaps():
        for direction in GAP_DIRECTIONS[gap_type]:
            for block in g.blocks:
                g.opt(gap_type, line, block)
                if g.try_move(direction, step):
                    count += 1
                    if sample is None:
                        sample = (gap_type, line, direction)
    return count, sample


def can_shuffle(k, step):
    """反复打乱，出现任意一次非还原态即算能打乱。"""
    for _ in range(SHUFFLE_TRIES):
        g = TriangleSliderMatrix(k)
        g.shuffle(SHUFFLE_ATTEMPTS, step, min_score=None)
        if not g.is_solved():
            return True
    return False


def predicted_movable(k, step):
    """机理假设的预测：k − step ≥ 2。"""
    return k - step >= 2


def main():
    print(f'{"k":>2} {"step":>4} {"k-step":>6} {"穷举合法移动":>12} '
          f'{"能打乱":>6} {"预测可动":>8} {"一致":>4}')
    print('-' * 52)
    mismatch = []
    for k in range(2, K_MAX + 1):
        for step in range(1, k):
            count, _sample = legal_move_count(k, step)
            movable = count > 0
            shuffled = can_shuffle(k, step)
            pred = predicted_movable(k, step)
            ok = (movable == pred) and (shuffled == pred)
            if not ok:
                mismatch.append((k, step, movable, shuffled, pred))
            print(f'{k:>2} {step:>4} {k - step:>6} {count:>12} '
                  f'{str(shuffled):>6} {str(pred):>8} {"OK" if ok else "不符":>4}')
    print()
    if mismatch:
        print(f'[不符] 与「k − step ≥ 2」不一致的组合共 {len(mismatch)} 个：')
        for k, step, movable, shuffled, pred in mismatch:
            print(f'  k={k} step={step} 穷举可动={movable} 能打乱={shuffled} 预测={pred}')
        return 1
    print(f'[一致] k=2..{K_MAX}、step=1..k−1 全部组合都与「k − step ≥ 2」吻合。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
