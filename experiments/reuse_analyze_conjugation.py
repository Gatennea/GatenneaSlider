# -*- coding: utf-8 -*-
"""分析教程存档的共轭嵌套结构。

- 从 beginner_archive/*.json 的 snapshots.move_info 提取 Action；
- 全链路重放验证；
- 递归识别「前缀 A + 中段 + 逆序逆动作 A'」的共轭结构；
- 标注外层转换前后，洞在窗口上是「缺口(贴边)」还是「洞(内部)」。
"""
import argparse
import json
import os

from experiments import harness as H

ARCH = 'beginner_archive'


def inverse(a):
    gd, gl, side, md = a
    inv = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}[md]
    return (gd, gl, side, inv)


def infer_side(gap_type, gap_line, moved):
    if gap_type == 'v':
        return 'right' if min(p[1] for p in moved) > gap_line else 'left'
    return 'below' if min(p[0] for p in moved) > gap_line else 'above'


def snap_coords(s):
    b = s['bounds']
    return [(b['min_row'] + i, b['min_col'] + j)
            for i, row in enumerate(s['matrix'])
            for j, v in enumerate(row) if v]


def extract_actions(archive):
    """逐快照暴力匹配：枚举合法动作，找精确产生下一快照者。"""
    from solver.actions import enumerate_valid_actions
    from solver.state import snapshot as snap_game, restore as restore_game
    snaps = archive['history']['snapshots']
    coord_list = [snap_coords(s) for s in snaps]
    step = archive['puzzle']['step']
    actions = []
    for i in range(len(snaps) - 1):
        snap_i = {'m': archive['puzzle']['m'], 'n': archive['puzzle']['n'],
                  'step': step, 'coords': sorted(coord_list[i])}
        g = H.load_game(snap_i)
        target = frozenset(coord_list[i + 1])
        found = None
        for a in enumerate_valid_actions(g, step):
            s = snap_game(g)
            if H.apply_action(g, a, step) and H.coords_of(g) == target:
                found = a
                restore_game(g, s)
                break
            restore_game(g, s)
        actions.append(found)
    return actions, snaps, coord_list


def initial_coords(snaps):
    m0 = snaps[0]['matrix']
    b = snaps[0]['bounds']
    return [(b['min_row'] + i, b['min_col'] + j)
            for i, row in enumerate(m0) for j, v in enumerate(row) if v]


def parse_conj(actions, depth=0):
    n = len(actions)
    for k in range(n // 2, 0, -1):
        expected = [inverse(a) for a in actions[:k]][::-1]
        if actions[n - k:] == expected:
            inner = actions[k:n - k]
            return {'kind': 'conj', 'k': k,
                    'inner': parse_conj(inner, depth + 1) if inner else None}
    return {'kind': 'seq', 'n': n}


def show(tree, ind=0):
    pad = '  ' * ind
    if tree['kind'] == 'conj':
        print(f"{pad}共轭 (外层 {tree['k']} 步 + 逆 {tree['k']} 步)")
        if tree['inner']:
            print(f"{pad}  └ 中段:")
            show(tree['inner'], ind + 2)
    else:
        print(f"{pad}直接序列 {tree['n']} 步")


def hole_kind(coords, m, n, step):
    """最佳窗口内每个洞：贴边=缺口，否则=洞。"""
    from solver.ml.fill_macro import window_of
    win, ov, holes, outside = window_of(frozenset(coords), m, n, step)
    r0, c0, (rh, cw) = win
    kinds = []
    for (r, c) in holes:
        edge = (r == r0 or r == r0 + rh - 1 or c == c0 or c == c0 + cw - 1)
        kinds.append('缺口' if edge else '洞')
    return sorted(holes), kinds, sorted(outside)


def analyze(path):
    archive = json.load(open(path, encoding='utf-8'))
    m = archive['puzzle']['m']
    n = archive['puzzle']['n']
    step = archive['puzzle']['step']
    actions, snaps, coord_list = extract_actions(archive)

    # 重放验证（每个 transition 已在提取时匹配；这里再整体重放一次）
    snap0 = {'m': m, 'n': n, 'step': step,
             'coords': sorted(coord_list[0])}
    missing = [i for i, a in enumerate(actions) if a is None]
    ok = not missing
    if ok:
        ok, _ = H.replay(snap0, actions)

    print(f"\n=== {os.path.basename(path)}  {m}x{n} step{step} "
          f"{len(actions)}步 重放={'通过' if ok else '失败'} ===")
    if missing:
        print(f"  无法匹配的过渡索引: {missing}")

    h0, k0, o0 = hole_kind(snap0['coords'], m, n, step)
    print(f"  初始: 洞/缺口 {list(zip(h0,k0))} 凸起 {o0}")

    if not ok:
        return ok
    tree = parse_conj(actions)
    show(tree)

    # 外层转换后（若识别到共轭）洞的性质
    if tree['kind'] == 'conj':
        g = H.load_game(snap0)
        for a in actions[:tree['k']]:
            H.apply_action(g, a, step)
        h1, k1, o1 = hole_kind(H.coords_of(g), m, n, step)
        print(f"  外层A后: {list(zip(h1,k1))} 凸起 {o1}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*')
    args = ap.parse_args()
    if args.files:
        files = [f if f.endswith('.json') else os.path.join(ARCH, f + '.json')
                 for f in args.files]
    else:
        files = [os.path.join(ARCH, f) for f in sorted(os.listdir(ARCH))
                 if f.startswith('4.')]
    n_ok = sum(analyze(f) for f in files)
    print(f"\n重放通过 {n_ok}/{len(files)}")


if __name__ == '__main__':
    main()
