# -*- coding: utf-8 -*-
"""实验10：尺寸无关的「缺口 setup 搜索」求解器。

思路（源自新手第4关双层共轭）：
  对近矩形态，识别 凸起块 P 与 边缺口 H；
  BFS 搜索短 setup A，使 P 与 H 对齐、并能沿一条走廊连续滑入；
  B = 把 P 连续滑进 H；A' = setup 的逆（分量选择在重放时确定）。
不依赖任何距离表，故可放大到任意尺寸。
"""
import argparse
import itertools

from solver.table_core import _side_components, is_single_connected, canonicalize
from experiments import harness as H
from experiments.exp9_rep import replay_steps

DCHAR = {(0, 1): 'd', (0, -1): 'a', (1, 0): 's', (-1, 0): 'w'}
DDIR = {v: k for k, v in DCHAR.items()}


# ---------- 纯坐标逐分量展开 ----------
def expand(coords, step):
    B = set(coords)
    total = len(B)
    out = []
    rows = [r for r, _ in B]
    cols = [c for _, c in B]

    def go(comp, gt, L, side, D):
        du = (D[0] // step if D[0] else 0, D[1] // step if D[1] else 0)
        non = B - set(comp)
        cur = set(comp)
        for _ in range(step):
            cur = {(r + du[0], c + du[1]) for r, c in cur}
            if cur & non or not is_single_connected(cur | non):
                return
        res = frozenset(non | cur)
        if len(res) == total:
            out.append((res, (gt, L, side, DCHAR[du]), next(iter(comp))))

    for L in range(min(rows), max(rows)):
        for side in ('above', 'below'):
            for comp in _side_components(B, 'h', L, side):
                for sgn in (-1, 1):
                    go(comp, 'h', L, side, (0, sgn * step))
    for L in range(min(cols), max(cols)):
        for side in ('left', 'right'):
            for comp in _side_components(B, 'v', L, side):
                for sgn in (-1, 1):
                    go(comp, 'v', L, side, (sgn * step, 0))
    return out


# ---------- 最佳窗口 / 缺口 / 凸起 ----------
def best_window(coords, m, n):
    B = set(coords)
    rs = [r for r, _ in B]
    cs = [c for _, c in B]
    best = None
    for h, w in ((m, n), (n, m)):
        for r0 in range(min(rs) - 1, max(rs) - h + 2):
            for c0 in range(min(cs) - 1, max(cs) - w + 2):
                win = set((r, c) for r in range(r0, r0 + h)
                          for c in range(c0, c0 + w))
                inside = len(win & B)
                holes = win - B
                protr = B - win
                # 目标：入窗最多；其次窗口紧贴（外接面积小）
                score = (inside, -(abs(r0 - min(rs)) + abs(c0 - min(cs))))
                if best is None or score > best[0]:
                    best = (score, (r0, c0, h, w), holes, protr)
    return best[1], best[2], best[3]


def is_edge_hole(h, win):
    r0, c0, hh, ww = win
    r, c = h
    return r in (r0, r0 + hh - 1) or c in (c0, c0 + ww - 1)


def fast_window(coords, m, n):
    """启发用快速窗口：在外接框左上角附近尝试少量放置（近矩形态足够）。
    任何情况下都保证返回 (win, holes, protr)，不返回 None。"""
    B = set(coords)
    rs = [r for r, _ in B]
    cs = [c for _, c in B]
    minr, maxr, minc, maxc = min(rs), max(rs), min(cs), max(cs)
    best = None
    for h, w in ((m, n), (n, m)):
        # 候选左上角：外接框左上附近，并保证区间非空
        rlo, rhi = minr - 1, max(maxr - h + 2, minr + 1)
        clo, chi = minc - 1, max(maxc - w + 2, minc + 1)
        for r0 in range(rlo, min(rhi, rlo + 5)):
            for c0 in range(clo, min(chi, clo + 5)):
                win = set((r, c) for r in range(r0, r0 + h)
                          for c in range(c0, c0 + w))
                inside = len(win & B)
                if best is None or inside > best[0]:
                    best = (inside, (r0, c0, h, w), win - B, B - win)
    if best is not None:
        return best[1], best[2], best[3]
    # 兜底：直接以外接框为窗口
    win = set((r, c) for r in range(minr, maxr + 1)
              for c in range(minc, maxc + 1))
    return (minr, minc, maxr - minr + 1, maxc - minc + 1), win - B, B - win


# ---------- P 跟踪 ----------
def _shifted(P, action, rep, step):
    """若 P 在被移动分量（含 rep 的分量由 action 决定），返回新 P。"""
    gt, L, side, d = action
    du = DDIR[d]
    # 该分量是否含 P：用 side 判定 + rep 同分量近似——调用方保证 rep 与 P 同分量时
    if gt == 'h':
        on_side = (side == 'above') == (P[0] <= L)
    else:
        on_side = (side == 'left') == (P[1] <= L)
    if not on_side:
        return P
    # rep 与 P 是否同属一个被移动分量，难以纯坐标判定，保守按 side 同即移动
    return (P[0] + du[0] * step, P[1] + du[1] * step)


# ---------- 沿走廊把 P 滑进 H ----------
def slide_in(coords, P, H, step, max_rep=12):
    cur = frozenset(coords)
    Bsteps = []
    guard = 0
    while P != H:
        guard += 1
        if guard > max_rep:
            return None
        want = (H[0] - P[0], H[1] - P[1])
        cands = []
        for new, act, rep in expand(cur, step):
            if rep not in cur:
                continue
            # P 是否在该移动分量：分量含 rep；判断 P 与 rep 是否在同分量
            comp = _comp_of(cur, act, rep)
            if comp is None or P not in comp:
                continue
            Pnew = (P[0] + (DDIR[act[3]][0] * step),
                    P[1] + (DDIR[act[3]][1] * step))
            dv = (H[0] - Pnew[0], H[1] - Pnew[1])
            # 必须朝 H 靠近且保持共线
            if (abs(dv[0]) + abs(dv[1])) < (abs(want[0]) + abs(want[1])) \
               and (dv[0] == 0 or dv[1] == 0) \
               and (Pnew[0] == H[0] or Pnew[1] == H[1]):
                cands.append((new, act, rep, Pnew))
        if not cands:
            return None
        new, act, rep, Pnew = cands[0]
        cur, P = new, Pnew
        Bsteps.append((act, rep))
    return Bsteps


def _comp_of(coords, action, rep):
    gt, L, side, d = action
    comps = _side_components(set(coords), gt, L, side)
    return next((c for c in comps if rep in c), None)


# ---------- setup BFS（枚举候选，逐个验证逆共轭） ----------
def iter_setups(coords, P, H, step, K=3):
    """按 setup 深度递增，yield (setup, B, cur, after_B)。

    仅 slide_in 成功还不够（可能拼乱其余块），交由调用方用 build_inverse
    判断是否存在能还原矩形的 A'。
    """
    start = frozenset(coords)
    seen = {canonicalize(start)}
    frontier = [(start, [], P)]
    for depth in range(K + 1):
        nxt = []
        for cur, path, Pcur in frontier:
            if path:
                b = slide_in(cur, Pcur, H, step)
                if b is not None:
                    after = cur
                    ok = True
                    for act, rep in b:
                        comp = _comp_of(after, act, rep)
                        if comp is None:
                            ok = False
                            break
                        du = DDIR[act[3]]
                        shifted = {(r + du[0] * step, c + du[1] * step)
                                   for r, c in comp}
                        after = frozenset((set(after) - set(comp)) | shifted)
                    if ok:
                        yield path, b, cur, after
            if depth == K:
                continue
            for new, act, rep in expand(cur, step):
                ck = canonicalize(new)
                if ck in seen:
                    continue
                comp = _comp_of(cur, act, rep)
                Pnew = Pcur
                if comp is not None and Pcur in comp:
                    du = DDIR[act[3]]
                    Pnew = (Pcur[0] + du[0] * step, Pcur[1] + du[1] * step)
                seen.add(ck)
                nxt.append((new, path + [(act, rep)], Pnew))
        frontier = nxt


# ---------- 逆 setup（A'）分量选择，要求最终复原 ----------
def build_inverse(coords_after, setup_path, step):
    """从 coords_after 出发，逆序撤销 setup；多分量时 DFS，返回 (steps, final)。"""
    inv = []
    for act, rep in reversed(setup_path):
        gt, L, side, d = act
        idir = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}[d]
        inv.append((gt, L, side, idir))

    def dfs(cur, i, acc):
        if i == len(inv):
            return acc if _rectangle(cur) else None
        act = inv[i]
        opts = [e for e in expand(cur, step) if e[1] == act]
        # 去重
        uniq = {}
        for new, a, rep in opts:
            uniq.setdefault(new, (a, rep))
        for new, (a, rep) in uniq.items():
            r = dfs(new, i + 1, acc + [(a, rep)])
            if r is not None:
                return r
        return None

    return dfs(frozenset(coords_after), 0, [])


def _rectangle(coords):
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    return len(coords) == (max(rs) - min(rs) + 1) * (max(cs) - min(cs) + 1)


# ---------- 对一个近矩形态求解缺口 ----------
def solve_notch_state(coords, m, n, step, K=3):
    win, holes, protr = best_window(coords, m, n)
    if not holes:
        return []
    edge_holes = [h for h in holes if is_edge_hole(h, win)]
    targets = edge_holes or list(holes)
    for P in protr:
        for Hh in targets:
            for setup, B, cur, after in iter_setups(coords, P, Hh, step, K):
                inv_steps = build_inverse(after, setup, step)
                if inv_steps is not None:
                    return setup + B + inv_steps
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='1000,1001,1002,1003')
    ap.add_argument('--configs', default='4x4x2')
    ap.add_argument('--K', type=int, default=3)
    ap.add_argument('--diag', action='store_true')
    args = ap.parse_args()
    m, n, st = (int(x) for x in args.configs.split('x'))

    from solver.ml.gather_solver import gradient_gather
    for seed in (int(s) for s in args.seeds.split(',')):
        snap = H.gen_state(m, n, st, seed)
        g = H.load_game(snap)
        r = gradient_gather(g, st)
        gsteps = [(a, None) for a in r['actions']]
        _ok, g2 = replay_steps(snap, gsteps)
        coords = H.coords_of(g2)
        win, holes, protr = best_window(coords, m, n)
        print(f"seed{seed} 聚拢后 holes={sorted(holes)} protr={sorted(protr)}")
        if args.diag:
            continue
        notch = solve_notch_state(coords, m, n, st, args.K)
        if notch is None:
            print("   setup 搜索失败")
            continue
        allsteps = gsteps + notch
        ok, _ = replay_steps(snap, allsteps)
        print(f"   解={ok} 总步={len(allsteps)} (缺口段{len(notch)})")


if __name__ == '__main__':
    main()
