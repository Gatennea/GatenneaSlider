# -*- coding: utf-8 -*-
r"""
随机「拔块打乱」生成器（人工标注模式的起點来源②）

从还原态（m×n 实心矩形，锚定原点）出发，迭代 void_number 次：
    1. 随機選中一顆「仍在核心矩形內」的滑塊 x，記下位置；
    2. 檢查把 x 從形狀中移除後整體仍連通（避免拆成兩個分量）；
    3. 在形狀外圍一圈（與形狀正交相鄰的空格）中隨機選一個
       與 x 同 mod-step 組的位置 y，把該格 0→1、x 格 1→0。

不變量（本遊戲所有合法移動都保持）：
    · 單一連通分量
    · 每顆滑塊的 (row mod step, col mod step) 分組計數不變
      —— 每步移動是整個連通分量沿一軸平移恰好 step，故同餘組計數
      永遠等於還原態 m×n（錨定 (0,0)）的分組計數。

產生的狀態 ≈ 還原態挖掉 void_number 個洞、貼上同數量的外圍凸起，
理論上比隨機滑動打亂更接近還原，適合人工標註「填洞/收斂空位」步驟。

運行測試：
    D:\python\python.exe -m solver.ml.ann_gen [m n step void_number]
"""

import random
import sys
from collections import Counter

from solver.table_core import is_single_connected

_NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def solved_coords(m, n):
    """還原態（錨定原點）座標集合。"""
    return frozenset((r, c) for r in range(m) for c in range(n))


def solved_class_counts(m, n, step):
    """還原態的 (row mod step, col mod step) 分組計數。"""
    step = max(1, step)
    return Counter((r % step, c % step)
                   for r in range(m) for c in range(n))


def validate_state(coords, m, n, step):
    """檢查給定狀態是否可作為本遊戲的合法棋盤。

    返回 (ok: bool, msg: str)。
    """
    if not coords:
        return False, '空狀態'
    if len(coords) != m * n:
        return False, f'滑塊數 {len(coords)} != {m}×{n}'
    if not is_single_connected(coords):
        return False, '不是單一連通分量'
    if Counter((r % max(1, step), c % max(1, step)) for r, c in coords) \
            != solved_class_counts(m, n, step):
        return False, 'mod-step 同餘組計數與還原態不一致'
    return True, 'ok'


def _outer_ring_candidates(shape, cls, step):
    """形狀外圍一圈中，與給定同餘組相符的空格（正交相鄰於形狀）。"""
    out = []
    for r, c in shape:
        for dr, dc in _NEIGHBORS:
            p = (r + dr, c + dc)
            if p not in shape and (p[0] % step, p[1] % step) == cls:
                out.append(p)
    return out


def _removal_keeps_connected(shape, x):
    if len(shape) <= 1:
        return True
    return is_single_connected(shape - {x})


def generate_random_void(m, n, step, void_number, rng=None, max_attempts=600):
    """迭代拔块，生成帶 void_number 個洞、靠近還原的打亂狀態。

    參數：
        m, n, step : 謎題尺寸與移動等級
        void_number: 想要挖出的空位格數（0 = 直接返回還原態）
        rng        : random.Random 實例（可空，傳種子控制復現）
        max_attempts: 每個空位最多嘗試次數（找不到同組外圍位置就重選）

    返回：
        (coords, holes)：
            coords : frozenset[(row, col)] 生成狀態（絕對座標）
            holes  : frozenset[(row, col)] 被挖掉的格（核心矩形內的空位）

    異常：
        ValueError — 參數不合理 / 在 max_attempts 內生成失敗
    """
    step = max(1, int(step))
    if m < 2 or n < 2:
        raise ValueError('m、n 必須 >= 2')
    if step >= max(m, n):
        raise ValueError(f'等級必須 < {max(m, n)}')
    if void_number < 0:
        raise ValueError('空位數不能為負')
    rng = rng or random.Random()

    core = {(r, c) for r in range(m) for c in range(n)}
    shape = set(core)
    holes = set()

    for _ in range(void_number):
        placed = False
        for _attempt in range(max_attempts):
            # 只挖「還處在核心矩形內」的滑塊；挖掉後整體仍須連通
            removable = [x for x in shape
                         if x in core and _removal_keeps_connected(shape, x)]
            if not removable:
                break
            x = rng.choice(removable)
            cls = (x[0] % step, x[1] % step)
            candidates = [p for p in _outer_ring_candidates(shape, cls, step)
                          if p not in holes]
            if not candidates:
                continue
            y = rng.choice(candidates)
            shape.remove(x)
            shape.add(y)
            holes.add(x)
            placed = True
            break
        if not placed:
            raise ValueError(
                f'生成失敗：無法在 {void_number} 個空位內保持同餘/連通'
                f'（已完成 {len(holes)}/{void_number}）')

    return frozenset(shape), frozenset(holes)


# ---------------------------------------------------------------------------
# 按「孔洞 / 缺口」计数生成
# ---------------------------------------------------------------------------
def generate_classified(m, n, step, n_hole, n_dent, rng=None, max_trials=400):
    """生成「恰好 n_hole 个孔洞 + n_dent 个缺口」的打乱状态。

    拔块（generate_random_void）本身不区分洞的种类；这里用 reject-sampling：
    每次生成 n_hole+n_dent 个空位后用 hole_detector 统计 孔洞(hole)/缺口(dent)
    的数量，命中目标才返回（孔洞/缺口按检测器的「连通簇」计数）。

    返回 (coords, holes)，holes 为被挖掉的核心格；
    max_trials 内未命中 → 抛 ValueError。
    """
    step = max(1, int(step))
    rng = rng or random.Random()
    if n_hole < 0 or n_dent < 0 or n_hole + n_dent < 1:
        raise ValueError('孔洞/缺口数不能为负，且至少一个 ≥ 1')
    if n_hole + n_dent > (m * n) // 4:
        raise ValueError(f'空位总数需 ≤ {(m * n) // 4}')

    from solver.ml.hole_detector import detect_holes
    last = None
    for _ in range(max_trials):
        coords, holes = generate_random_void(m, n, step, n_hole + n_dent,
                                             rng=rng)
        hlist, _proto, _reg = detect_holes(coords, m, n, step)
        hc = sum(1 for h in hlist if h['type'] == 'hole')
        dc = sum(1 for h in hlist if h['type'] == 'dent')
        if hc == n_hole and dc == n_dent:
            return coords, holes
        last = (hc, dc)
    raise ValueError(
        f'生成失败：{max_trials} 次内未命中 孔洞{n_hole}/缺口{n_dent}'
        f'（末次孔洞{last[0]}/缺口{last[1]}）')


# ---------------------------------------------------------------------------
# 自測
# ---------------------------------------------------------------------------
def _self_test(m, n, step, void_number, seed=20260904):
    ok, msg = True, ''
    try:
        coords, holes = generate_random_void(m, n, step, void_number,
                                             rng=random.Random(seed))
        ok, msg = validate_state(coords, m, n, step)
        assert len(holes) == void_number, \
            f'挖出 {len(holes)} 個洞 != {void_number}'
        assert all(h not in coords for h in holes), '洞仍被佔據'
        # 洞都落在核心矩形內
        core = {(r, c) for r in range(m) for c in range(n)}
        assert holes <= core, '有洞在核心矩形外'
        print(f'  {m}×{n} step{step} void={void_number}: '
              f'{len(coords)}格 OK, 洞{len(holes)}'
              f'{("  | " + msg) if not ok else ""}')
    except ValueError as e:
        ok, msg = False, str(e)
        print(f'  {m}×{n} step{step} void={void_number}: {msg}')
    return ok


def main():
    args = [int(a) for a in sys.argv[1:]]
    if len(args) == 4:
        m, n, step, v = args
        if not _self_test(m, n, step, v):
            sys.exit(1)
        return

    print('自測：各種尺寸 / 空位數的生成 + 合法性檢查')
    all_ok = True
    cases = [
        (4, 4, 2, 1), (4, 4, 2, 3), (4, 4, 2, 6),
        (5, 5, 2, 1), (5, 5, 2, 2), (5, 5, 2, 4),
        (6, 6, 2, 2), (7, 7, 2, 3), (7, 7, 3, 3),
        (8, 8, 2, 2), (9, 9, 2, 3), (10, 10, 3, 4),
    ]
    for case in cases:
        all_ok &= _self_test(*case)
    print('全部通過' if all_ok else '存在失敗')
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
