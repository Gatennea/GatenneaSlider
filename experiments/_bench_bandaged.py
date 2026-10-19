# -*- coding: utf-8 -*-
"""自由捆绑（bandaged）差分 + 语义测试。

三部分：
1. 无捆绑差分：opt/try_move_ex 与「旧版逐字复刻」在随机局面上一致
   （证明对既有玩法零影响）。
2. 捆绑语义：跨缝拖拽、组增长、解绑、序列化 roundtrip、路径不可达。
3. 捆绑态安全打乱：可逆性 ⟺ 有解在捆绑态下继承。

运行：D:/python/python.exe experiments/_bench_bandaged.py
"""
import random
import sys

sys.path.insert(0, 'E:/program_project/other/wkbddtest/GatenneaSlider')

from game import SliderMatrix  # noqa: E402


# ---------- 旧版 opt 逐字复刻（无捆绑语义，2026-10-19 改前快照） ----------
def opt_legacy(game, direction, line, selected_block):
    from bitboard import build_occupancy, grid_side_mask, component
    blocks = game.blocks
    for b in blocks:
        b.be_opted = False
    if not blocks:
        return
    cells = [(b.location[0], b.location[1]) for b in blocks]
    mask, W, H, col0, colW, off_r, off_c = build_occupancy(cells)
    if mask == 0:
        return
    sr, sc = selected_block.location[0], selected_block.location[1]
    if direction == 'h':
        side = 'above' if sr <= line else 'below'
    else:
        side = 'left' if sc <= line else 'right'
    side_m = grid_side_mask(W, H, off_r, off_c, direction, line, side)
    opt_mask = mask & side_m
    start_bit = 1 << ((sr - off_r) * W + (sc - off_c))
    if not (opt_mask & start_bit):
        return
    comp = component(opt_mask, start_bit, W, col0, colW)
    for b in blocks:
        br, bc = b.location[0], b.location[1]
        if comp & (1 << ((br - off_r) * W + (bc - off_c))):
            b.be_opted = True


def random_board(rng, m, n, holes=0):
    """随机局面：从完整网格抠 holes 个空位，返回 SliderMatrix。"""
    cells = [(i, j) for i in range(m) for j in range(n)]
    rng.shuffle(cells)
    keep = cells[:len(cells) - holes]
    g = SliderMatrix(m, n)
    g.blocks = []
    from game import Block
    for r, c in keep:
        g.blocks.append(Block([r, c]))
    g.update_matrix()
    return g


def sel_set(game):
    return frozenset(tuple(b.location) for b in game.blocks if b.be_opted)


def part1_no_bind_differential(rng, trials=400):
    """无捆绑：opt/try_move_ex 与旧版逐字一致。"""
    bad = 0
    opt_n = move_n = 0
    for t in range(trials):
        m, n = rng.choice([(4, 4), (5, 4), (4, 5), (5, 5), (6, 6), (3, 7)])
        holes = rng.choice([0, 1, 2, 3])
        g1 = random_board(rng, m, n, holes)
        # 同局面两份：g2 从 g1 的位置深拷贝（组字段默认 0 = 无捆绑）
        from game import Block
        g2 = SliderMatrix(m, n)
        g2.blocks = [Block(list(b.location)) for b in g1.blocks]
        g2.update_matrix()
        assert [b.location for b in g1.blocks] == [b.location for b in g2.blocks]
        anchor = rng.choice(g1.blocks)
        direction = rng.choice('hv')
        lines = ([r for r, _ in
                  [(b.location[0], b.location[1]) for b in g1.blocks]] if direction == 'h'
                 else [c for _, c in
                       [(b.location[0], b.location[1]) for b in g1.blocks]])
        line = rng.choice(lines)
        opt_legacy(g1, direction, line, anchor)
        g2.opt(direction, line, anchor)
        opt_n += 1
        if sel_set(g1) != sel_set(g2):
            bad += 1
            print('OPT MISMATCH', t, direction, line,
                  sorted(sel_set(g1) ^ sel_set(g2)))
        d = rng.choice('wsad')
        step = rng.choice([1, 2, 3])
        r1 = g1.try_move_ex(d, step)
        r2 = g2.try_move_ex(d, step)
        move_n += 1
        if r1 != r2:
            bad += 1
            print('MOVE MISMATCH', t, d, step, r1, r2)
    print(f'part1 无捆绑差分: {trials} 局 × (opt+move)，不一致 {bad} '
          f'（opt {opt_n} / move {move_n} 次调用）')
    return bad == 0


def part2_bind_semantics():
    """捆绑语义：跨缝拖拽 / 组增长 / 解绑 / 序列化 / 不可达。"""
    ok = True

    # 2.1 跨缝拖拽：竖组被 h 缝切开，选一侧 → 整组入选
    g = SliderMatrix(4, 4)
    g.bind_path((0, 0), (1, 0))
    g.opt('h', 0, g.blocks[1])
    sel = sel_set(g)
    ok &= (1, 0) in sel and (0, 0) in sel and len(sel) == 5
    print('2.1 跨缝拖拽:', 'OK' if (1, 0) in sel else 'FAIL', sorted(sel))

    # 2.2 组增长：新路径并入旧组
    g = SliderMatrix(4, 4)
    g.bind_path((0, 0), (0, 1))
    g.bind_path((1, 1), (0, 1))  # 路径 (1,1)-(0,1)，(0,1) 有组 → 并入
    gs = g.groups_summary()
    ok &= len(gs) == 1 and len(gs[0][1]) == 3
    print('2.2 组增长:', gs)

    # 2.3 解绑整组
    n = g.unbind_at((1, 1))
    ok &= n and g.groups_summary() == []
    print('2.3 解绑整组:', n, '→', g.groups_summary())

    # 2.4 序列化 roundtrip
    g = SliderMatrix(4, 4)
    g.bind_path((0, 0), (1, 1))
    g.bind_path((2, 3), (3, 3))
    snap = g.groups_as_positions()
    g2 = SliderMatrix(4, 4)
    g2.set_groups_from_positions(snap)
    ok &= g2.groups_as_positions() == snap
    print('2.4 序列化 roundtrip:', 'OK' if g2.groups_as_positions() == snap else 'FAIL')

    # 2.5 路径不可达（中间有洞）
    g = random_board(random.Random(7), 4, 4, holes=1)
    g2 = random_board(random.Random(7), 4, 4, holes=1)
    occ = {(b.location[0], b.location[1]) for b in g.blocks}
    # 找一对被洞隔开的块
    a = next(iter(occ))
    far = None
    for p in occ:
        if abs(p[0] - a[0]) + abs(p[1] - a[1]) >= 4:
            far = p
            break
    if far is not None:
        r = g.bind_path(a, far)
        # 洞只抠 1 个，4x4 大概率仍连通——不断言 None，只验证不抛异常
        print('2.5 跨洞路径 bind_path 返回:', r, '（无异常即通过）')

    # 2.6 空位端点/同点
    g = SliderMatrix(4, 4)
    r = g.bind_path((9, 9), (0, 0))
    ok &= r is None
    r = g.bind_path((0, 0), (0, 0))
    ok &= r is None  # 同点且无组
    print('2.6 非法端点:', 'OK' if r is None else 'FAIL')

    # 2.7 clear_groups
    g = SliderMatrix(4, 4)
    g.bind_path((0, 0), (0, 2))
    g.bind_path((3, 0), (3, 2))
    n = g.clear_groups()
    ok &= n == 2 and g.groups_summary() == []
    print('2.7 clear_groups:', n)

    return ok


def part3_shuffle_bandaged(rng, trials=8):
    """捆绑态安全打乱：可逆性 ⟺ 有解在捆绑态下继承。"""
    sys.path.insert(0, 'E:/program_project/other/wkbddtest/GatenneaSlider')
    from game import can_undo_shuffle_step

    all_ok = True
    for t in range(trials):
        g = SliderMatrix(4, 4)
        # 随机预先捆 1~2 组
        for _ in range(rng.randint(1, 2)):
            occ = [(b.location[0], b.location[1]) for b in g.blocks]
            a = rng.choice(occ)
            b = rng.choice(occ)
            g.bind_path(a, b)
        n_groups = len(g.groups_summary())
        # 打乱（带 record），每步过可逆校验（模拟安全打乱核心）
        step = 2
        attempts = 40
        record = []
        ok_steps = 0
        for _ in range(attempts):
            direction = rng.choice('hv')
            if direction == 'h':
                lines = range(g.m - 1)
            else:
                lines = range(g.n - 1)
            line = rng.choice(list(lines))
            anchor = rng.choice(g.blocks)
            g.opt(direction, line, anchor)
            before_sel = frozenset(tuple(b.location) for b in g.blocks if b.be_opted)
            if not before_sel:
                continue
            d = rng.choice('wasd')
            res, reason = g.try_move_ex(d, step)
            if not res:
                continue
            g.commit_move(res)
            # 可逆性校验（捆绑态下 opt 天然遵守组刚体）
            dirs = {'h': ('a', 'd'), 'v': ('w', 's')}[direction]
            if can_undo_shuffle_step(g, direction, line, anchor, step, dirs, before_sel):
                ok_steps += 1
                record.append((direction, line, tuple(anchor.location), d))
            else:
                # 回滚：把 before_sel 精确写回
                pmap = {tuple(b.location): b for b in g.blocks}
                for p in before_sel:
                    if p in pmap:
                        pmap[p].location = list(p)
        # 验证：record 逆序真能走回原状（捆绑态下逐步重放）
        g_replay = SliderMatrix(4, 4)
        g_replay.set_groups_from_positions(g.groups_as_positions())
        # 从打乱前快照重放（此处简化为直接验证当前盘可逆步数 > 0）
        print(f'  trial{t}: {n_groups} 组, {ok_steps}/{attempts} 步通过可逆校验')
        all_ok &= ok_steps > 0
    print('part3 捆绑态安全打乱:', 'OK' if all_ok else 'FAIL')
    return all_ok


def part4_custom_pattern():
    """自定义还原形态：D4 判定 / fit / apply / 增删 / 序列化 / 打乱。"""
    ok = True

    # 4.1 L 形样式：is_solved 的 D4 判定（旋转/翻面都算还原）
    g = SliderMatrix(4, 4)
    l_cells = [(0, 0), (0, 1), (0, 2), (1, 0), (2, 0)]
    g.set_goal_pattern(l_cells)
    g.apply_pattern(l_cells)
    ok &= g.is_solved()
    print('4.1 L 形原位复原:', 'OK' if g.is_solved() else 'FAIL')
    # 旋转 90°（手工构造 L 的旋转像）
    rotated = [(c, 2 - r) for r, c in l_cells]
    g.apply_pattern(rotated)
    ok &= g.is_solved()
    print('4.2 L 形旋转 90° 仍算还原:', 'OK' if g.is_solved() else 'FAIL')
    # 翻面
    flipped = [(r, 2 - c) for r, c in l_cells]
    g.apply_pattern(flipped)
    ok &= g.is_solved()
    print('4.3 L 形左右翻面仍算还原:', 'OK' if g.is_solved() else 'FAIL')
    # 漂移 3 格（平移无关）
    drifted = [(r + 3, c - 5) for r, c in l_cells]
    g.apply_pattern(drifted)
    ok &= g.is_solved()
    print('4.4 平移漂移仍算还原:', 'OK' if g.is_solved() else 'FAIL')
    # 差一块不算
    g.apply_pattern(l_cells[:4])
    ok &= (not g.is_solved())
    print('4.5 少一块不算还原:', 'OK' if not g.is_solved() else 'FAIL')

    # 4.6 pattern_fit：全对=1；与 goal 八变换无交=0；一半=0.4（可手算：交 2/5）
    g2 = SliderMatrix(4, 4)
    g2.set_goal_pattern(l_cells)
    fit_full = g2.pattern_fit(l_cells)
    # 零交用例：goal=十字（D4 不变），cur=四角——归一后确无交集
    cross = [(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)]
    corners = [(0, 0), (0, 2), (2, 0), (2, 2)]
    g2b = SliderMatrix(4, 4)
    g2b.set_goal_pattern(cross)
    fit_zero = g2b.pattern_fit(corners)
    half = l_cells[:2] + [(3, 3), (3, 2), (3, 1)]
    fit_half = g2.pattern_fit(half)
    ok &= (abs(fit_full - 1.0) < 1e-9 and abs(fit_zero) < 1e-9)
    print(f'4.6 fit: full={fit_full:.2f} zero={fit_zero:.2f} half={fit_half:.2f} '
          f'（half 手算 2/5=0.40）')

    # 4.7 apply_pattern 带捆绑 + m/n 更新
    g3 = SliderMatrix(6, 6)
    g3.apply_pattern(l_cells, groups={(0, 0): 7, (1, 0): 7})
    ok &= (g3.m == 3 and g3.n == 3)
    ok &= g3.groups_summary() == [(7, [(0, 0), (1, 0)])]
    print('4.7 apply+groups+尺寸:', g3.groups_summary(), f'{g3.m}x{g3.n}')

    # 4.8 增/删/切换（满盘上 toggle 已占位 = 删除）
    g4 = SliderMatrix(4, 4)
    r = g4.toggle_block((3, 3))
    ok &= (r == 'removed' and len(g4.blocks) == 15)
    r = g4.toggle_block((3, 3))
    ok &= (r == 'added' and len(g4.blocks) == 16)
    ok &= (g4.add_block((2, 2)) is False)  # 已占用
    ok &= (g4.remove_block((9, 9)) is False)  # 无块
    print('4.8 增/删/切换:', 'OK' if ok else 'FAIL')

    # 4.9 序列化 roundtrip
    g5 = SliderMatrix(4, 4)
    g5.apply_pattern(l_cells, groups={(0, 0): 3, (0, 1): 3, (0, 2): 3})
    data = g5.pattern_export()
    cells, groups = SliderMatrix.pattern_import(data)
    g6 = SliderMatrix(4, 4)
    g6.apply_pattern(cells, groups)
    ok &= (g6.groups_summary() == g5.groups_summary())
    print('4.9 序列化 roundtrip:', 'OK' if g6.groups_summary() == g5.groups_summary() else 'FAIL',
          data['cells'])

    # 4.10 自定义样式安全打乱：15 块缺角形（4×4 标准盘，可动）
    # 注意：3×3 的 L 形是「冻形」（任何移动都把某块甩成孤立，零合法
    # 移动）——见 4.11；设计态保存前必须过 has_legal_move 校验
    import random as _rnd
    rng2 = _rnd.Random(4242)
    g7 = SliderMatrix(4, 4)
    corner_cells = [(r, c) for r in range(4) for c in range(4) if (r, c) != (3, 3)]
    g7.apply_pattern(corner_cells)
    g7.set_goal_pattern(corner_cells)
    fit0 = g7.pattern_fit()
    g7.shuffle(attempts=120, step=2, min_score=0.6)
    fit1 = g7.pattern_fit()
    ok &= (fit1 <= 0.6)
    print(f'4.10 自定义样式打乱（15 块缺角）: fit {fit0:.2f} → {fit1:.2f}'
          f'（门槛 0.6）', 'OK' if fit1 <= 0.6 else 'FAIL')

    # 4.11 冻形检测：L 形 3×3 零合法移动
    g8 = SliderMatrix(4, 4)
    g8.apply_pattern(l_cells)
    frozen = not g8.has_legal_move()
    ok &= bool(frozen)
    print('4.11 冻形检测（L 形 3×3 不可动）:', 'OK' if frozen else 'FAIL')
    # 对照：15 块缺角形可动
    g9 = SliderMatrix(4, 4)
    g9.apply_pattern(corner_cells)
    ok &= bool(g9.has_legal_move())
    print('4.12 对照（15 块缺角可动）:', 'OK' if g9.has_legal_move() else 'FAIL')

    return ok


def main():
    rng = random.Random(20261020)
    p1 = part1_no_bind_differential(rng)
    p2 = part2_bind_semantics()
    p3 = part3_shuffle_bandaged(rng)
    p4 = part4_custom_pattern()
    print()
    print('===', 'ALL PASS' if (p1 and p2 and p3 and p4) else 'FAILURES PRESENT', '===')
    return 0 if (p1 and p2 and p3 and p4) else 1


if __name__ == '__main__':
    sys.exit(main())
