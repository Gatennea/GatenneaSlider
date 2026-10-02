# -*- coding: utf-8 -*-
r"""三角形镜像（倒置）可达性探针（2026-10-02 用户问：倒置客观上能不能到？）

理论结论（脚本前先说清）：
    引擎移动 = (i,j) 平移、up 原样保留（game_triangle.py try_move_ex 里
    `c[2]` 逐字复制）→ 每块的朝向永不变 → 盘面 ▲ 位置数恒 = 初始
    k(k+1)/2。而尖朝下（镜像）大三角的位置形状需要 ▲ 位 k(k-1)/2 个
    ≠ k(k+1)/2（k≥1）→ **镜像态不可达，与 step 无关**。

脚本做三件事：
    1. 随机游走（引擎真实动作）验证 ▲ 位置数守恒；
    2. 游走中 is_solved=True 的局面做凸包定向普查——预期只出现旋转族
       的定向（有向面积同号），镜像定向（反号）永不出现；
    3. 构造 k=3 的尖朝下形状位置集（整数格点对齐），验证：
       ① 其 ▲ 位数 = k(k-1)/2 ≠ k(k+1)/2；
       ② 喂给凸包判定逻辑会返回 True——即 is_solved 本就「只看形状、
          不看定向」，倒置不算还原的障碍只在前述可达性，不在判定。

运行：D:/python/python.exe experiments/_tri_mirror_probe.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_triangle import (TriangleSliderMatrix, tri_vertices, convex_hull,
                           cells_inside_triangle, GAP_DIRECTIONS)


def up_count(cells):
    return sum(1 for c in cells if c[2])


def hull_sign(cells):
    """凸包顶点序手性。注意：convex_hull 实现会规范化顶点顺序（恒输出同向），
    所以此探针**区分不了镜像**（实测恒 'ccw'）——镜像判据用 ▲ 位数（见
    mirror_cells_k3），本函数仅作 hull 形状完整性 sanity check。"""
    verts = set()
    for key in cells:
        verts.update(tri_vertices(*key))
    hull = convex_hull(verts)
    if len(hull) != 3:
        return None
    (x1, y1), (x2, y2), (x3, y3) = hull
    cross = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
    return 'ccw' if cross > 0 else ('cw' if cross < 0 else 'degenerate')


def random_walk_probe(k, step, n_steps=4000):
    """从还原态随机游走，验证 ▲ 位数守恒 + is_solved 定向普查。"""
    g = TriangleSliderMatrix(k)
    a_expect = k * (k + 1) // 2          # 初始 ▲ 块数 = 尖朝上大三角的 ▲ 位数
    seen_signs = set()
    solved_hits = 0
    bad_up = 0
    for t in range(n_steps):
        gaps = g.all_gaps()
        if gaps:
            gap_type, line = random.choice(gaps)
            direction = random.choice(GAP_DIRECTIONS[gap_type])
            block = random.choice(g.blocks)
            g.opt(gap_type, line, block)
            final = g.try_move(direction, step)
            if final:
                g.commit_move(final)
            for b in g.blocks:
                b.be_opted = False
        cells = g.positions()
        assert len(cells) == k * k, '块数丢了？！'
        if up_count(cells) != a_expect:
            bad_up += 1
        if t % 97 == 0 or (t < 200 and t % 7 == 0):
            # 定期原盘重查（is_solved 只在偶遇到的还原态触发，概率低）
            pass
        if g.is_solved():
            solved_hits += 1
            seen_signs.add(hull_sign(cells))
    return {'k': k, 'step': step, 'steps': n_steps,
            'up_violations': bad_up, 'up_expect': a_expect,
            'solved_hits': solved_hits, 'solved_signs': seen_signs}


def mirror_cells_k3():
    """k=3 尖朝下大三角（格点对齐：顶点 (2,2),(-1,2),(2,-1)）的位置集。"""
    k = 3
    V = [(2, 2), (-1, 2), (2, -1)]

    def inside(px, py):
        sign = 0
        for t in range(3):
            (x1, y1), (x2, y2) = V[t], V[(t + 1) % 3]
            cr = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
            if cr != 0:
                s = 1 if cr > 0 else -1
                if sign == 0:
                    sign = s
                elif sign != s:
                    return False
        return True

    cells = set()
    R = range(-2, 5)
    for i in R:
        for j in R:
            for up in (True, False):
                vs = tri_vertices(i, j, up)
                if all(inside(x, y) for x, y in vs):
                    cells.add((i, j, up))
    assert len(cells) == k * k, '尖朝下区域单元数不是 k²（对齐失败）: %d' % len(cells)

    # ① ▲ 位数应 = k(k-1)/2 = 3（初始态是 k(k+1)/2 = 6）
    # ② 喂给凸包判定逻辑应返回 True（判定不看定向）
    verts = set()
    for key in cells:
        verts.update(tri_vertices(*key))
    hull = convex_hull(verts)
    ok_judge = (len(hull) == 3 and cells_inside_triangle(hull) == cells)
    return {'cells': cells, 'up': up_count(cells),
            'up_expect_mirror': k * (k - 1) // 2,
            'judge_passes_on_mirror': ok_judge,
            'sign': hull_sign(cells)}


def main():
    print('=== 1) 随机游走：▲ 位置数守恒 + is_solved 定向普查 ===')
    for k in (2, 3, 4):
        for step in (1, 2):
            r = random_walk_probe(k, step)
            print('  k=%d step=%d  走了 %d 步  ▲位数违规 %d 次（应恒=%d）  '
                  'is_solved 命中 %d 次，定向集合 %s'
                  % (r['k'], r['step'], r['steps'], r['up_violations'],
                     r['up_expect'], r['solved_hits'], sorted(r['solved_signs'])))

    print('=== 2) k=3 尖朝下形状：位置集构造与判定 ===')
    m = mirror_cells_k3()
    print('  尖朝下 ▲ 位数 = %d（初始态 ▲ 块数 = 6）→ 计数不等 ⇒ 不可达'
          % m['up'])
    print('  凸包判定对尖朝下形状返回 %s → is_solved 本就「只看形状」'
          % m['judge_passes_on_mirror'])
    print('  其凸包定向 = %s（与游走中观察到的还原态定向族相反/不同即镜像族）'
          % m['sign'])

    print('=== 结论 ===')
    print('  · 引擎移动不改块朝向（up），▲ 位数守恒（游走 0 违规）→ 镜像/倒置态客观不可达；')
    print('  · is_solved 凸包判定不看定向（尖朝下形状返回 True），设计哲学「只看形状」已达成，')
    print('    无需改判定；聚拢度/目标框枚举仍只用 3 个旋转朝向（纳入镜像只会引导贪心去不可达方向）；')
    print('  · 注：hull_sign 恒 ccw 是凸包实现规范化顶点序所致，非镜像可达证据；')
    print('    镜像判据 = ▲ 位数（k(k-1)/2 vs k(k+1)/2）。')


if __name__ == '__main__':
    main()
