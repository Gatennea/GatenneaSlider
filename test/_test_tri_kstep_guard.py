# -*- coding: utf-8 -*-
"""三角形谜题「可动性门槛」：性质 + 建局守卫双向锁定。

性质（用户 2026-10-12 发现，本脚本穷举验证）：
    三角形谜题存在任何合法移动 ⟺ 边长 k − 等级 step ≥ 2

机理：缝隙把棋盘切成两片，切片沿缝的平行方向滑动；每推一格都要求
「无碰撞 + 整体仍连通」，所以切片与剩余部分的接触面长度 L 必须满足
L ≥ step + 1。边长 k 的实心三角形，同族切口接触面最长只有 k−1，
于是 k−1 ≥ step+1 ⟺ k−step ≥ 2。

旧守卫只挡了 step ≥ k，放过 step = k−1：这种配置一步都动不了，按打乱
会静默回到还原态，玩家只会以为「打乱坏了」。本脚本锁死「建局前就拒绝」。

执行：``D:/python/python.exe -u test/_test_tri_kstep_guard.py``
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from game_triangle import TriangleSliderMatrix, GAP_DIRECTIONS  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def legal_move_count(k, step):
    """还原态下穷举（缝隙 × 方向 × 锚块），返回合法移动数。"""
    g = TriangleSliderMatrix(k)
    count = 0
    for gap_type, line in g.all_gaps():
        for direction in GAP_DIRECTIONS[gap_type]:
            for block in g.blocks:
                g.opt(gap_type, line, block)
                if g.try_move(direction, step):
                    count += 1
    return count


print("\n--- 性质：可动 ⟺ k − step ≥ 2（k=2..5 穷举）---")
for k in range(2, 6):
    for step in range(1, k):
        cnt = legal_move_count(k, step)
        want = (k - step) >= 2
        check(f"k={k} step={step} 合法移动 {cnt}", (cnt > 0) == want,
              f"预测可动={want}")

print("\n--- 建局守卫：死配置必须被拒 ---")
gui = SliderGUI(m=4, n=4, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False
for k, step in [(2, 1), (3, 2), (4, 3), (5, 4), (6, 5)]:
    check(f"拒绝 k={k} step={step}（k−step<2）",
          gui.new_triangle_puzzle(k, step) is False)
for k, step in [(3, 1), (4, 1), (4, 2), (5, 3), (6, 2), (8, 2)]:
    check(f"接受 k={k} step={step}（k−step≥2）",
          gui.new_triangle_puzzle(k, step) is True)

print("\n--- 菜单预设全部合规 ---")
_sub = getattr(gui, 'puzzle_sub_presets', {}) or {}
tri = [p for p in _sub.get('exotic', [])
       if len(p) >= 5 and p[4] == 'triangle']
check("存在三角预设", len(tri) > 0, f"共 {len(tri)} 项")
for p in tri:
    check(f"预设「{p[0]}」 k={p[1]} step={p[3]}",
          gui.new_triangle_puzzle(p[1], p[3]) is True)

print()
if _failures:
    print(f"FAILED: {len(_failures)} 项")
    for f in _failures:
        print("  -", f)
    sys.exit(1)
print("ALL PASS")
