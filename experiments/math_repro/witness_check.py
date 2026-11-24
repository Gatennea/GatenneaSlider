# -*- coding: utf-8 -*-
"""独立重放证人档并校验：每步走法合法、终点形状与标签复原、生成群阶。
用法：python _k1_witness_check.py <json> [期望阶]
"""
import json
import math
import sys

sys.path.insert(0, r"E:\program_project\other\doubaotest\slider\math_lab\branch\experiments\math_repro")
import moves as M


def norm_cells(st):
    rmin = min(r for r, _, _ in st)
    cmin = min(c for _, c, _ in st)
    return tuple(sorted((r - rmin, c - cmin, t) for r, c, t in st))


def shift(st, comp, unit):
    lab = {(r, c): t for r, c, t in st}
    out = {}
    for (r, c), t in lab.items():
        if (r, c) in comp:
            out[(r + unit[0], c + unit[1])] = t
        else:
            out[(r, c)] = t
    return norm_cells(tuple((r, c, t) for (r, c), t in out.items()))


data = json.load(open(sys.argv[1], encoding="utf-8"))
m, n, K = data["m"], data["n"], data["K"]
st = norm_cells(tuple((r, c, t) for r, c, t in data["start"]))
shape0 = frozenset((r, c) for r, c, _ in st)
print(f"[{m}x{n}] K={K} 回路 {len(data['loops'])} 条，重放校验开始")

bad = 0
perms = []
for li, loop in enumerate(data["loops"]):
    cur = st
    ok = True
    for si, step in enumerate(loop["steps"]):
        S = frozenset((r, c) for r, c, _ in cur)
        hit = None
        for seam, side, comp, unit in M.legal_moves(S, 1):
            if seam != step["seam"] or side != step["side"] or list(unit) != step["unit"]:
                continue
            if sorted(list(c) for c in comp) != step["comp"]:
                continue
            hit = comp
            break
        if hit is None:
            print(f"  回路 {li} 第 {si} 步不合法/不匹配: {step}")
            ok = False
            bad += 1
            break
        cur = shift(cur, hit, step["unit"])
    if not ok:
        continue
    sh = frozenset((r, c) for r, c, _ in cur)
    got = [[r, c, t] for r, c, t in cur]
    want = [[r, c, t] for t, r, c in loop["perm"]]
    if sh != shape0:
        print(f"  回路 {li} 终点不是满盘形状")
        bad += 1
    elif sorted(got) != sorted(want):
        print(f"  回路 {li} 标签与记录不符")
        bad += 1
    else:
        pl = sorted(loop["perm"], key=lambda x: x[0])
        perms.append(tuple(n * r + c for t, r, c in pl))

print(f"  校验通过 {len(perms)} 条，失败 {bad} 条")
if perms:
    from sympy.combinatorics import Permutation, PermutationGroup
    # perm 记录是 [t, r, c]：标签 t 在位置 (r,c) → 位置编码
    grp = PermutationGroup([Permutation(list(p)) for p in perms if p != tuple(range(K))])
    print(f"  重算群阶 = {grp.order()}（K! = {math.factorial(K)}，等于 K! = {grp.order() == math.factorial(K)}）")
