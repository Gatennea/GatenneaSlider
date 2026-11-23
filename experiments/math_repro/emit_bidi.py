"""從 solver_bidi 的傾倒還原每一對的最短路徑，生成 verify_swap 可吃的 JSON。

原則：C++ 只負責給「邊序 + 交會點」，每一步的合法性與分量圖案一律用
moves.py 複判；任何一步找不到同側／同方向／同圖案的合法走法就報錯退出。
"""
import os, sys, json, struct

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = HERE
DATA = os.path.join(HERE, "_work")
sys.path.insert(0, REPRO)
import moves as mv

M, N, S = 4, 3, 2
K = 12
BAD = 0xFFFFFFFF
G = frozenset((r, c) for r in range(M) for c in range(N))
LABELS = sorted(G)


def load_all():
    shapes = []
    with open(os.path.join(DATA, "_bidi_shapes.bin"), "rb") as f:
        n = struct.unpack("<I", f.read(4))[0]
        for _ in range(n):
            rows = struct.unpack("<16H", f.read(32))
            shapes.append(sorted((r, c) for r in range(16) for c in range(16)
                                 if (rows[r] >> c) & 1))
    edges = []
    with open(os.path.join(DATA, "_bidi_edges.bin"), "rb") as f:
        ne = struct.unpack("<I", f.read(4))[0]
        for _ in range(ne):
            dest = struct.unpack("<I", f.read(4))[0]
            ur, uc, side, vert, seam = struct.unpack("<bbbbb", f.read(5))
            cmask = struct.unpack("<H", f.read(2))[0]
            mp = list(struct.unpack("<12b", f.read(12)))
            edges.append(dict(dest=dest, ur=ur, uc=uc, side=side, vert=vert,
                              seam=seam, cmask=cmask, map=mp))
    return shapes, edges


def load_target(ti):
    p = os.path.join(DATA, "_bidi_t%d.bin" % ti)
    with open(p, "rb") as f:
        depth, meetF, meetB, nF, nB, lf, lb, _ = struct.unpack("<8I", f.read(32))
        F, B = [], []
        for _ in range(nF):
            shape, arr, parent, pedge, d = struct.unpack("<IQIII", f.read(24))
            F.append(dict(shape=shape, arr=arr, parent=parent, pedge=pedge, depth=d))
        for _ in range(nB):
            shape, arr, parent, pedge, d = struct.unpack("<IQIII", f.read(24))
            B.append(dict(shape=shape, arr=arr, parent=parent, pedge=pedge, depth=d))
    return dict(depth=depth, meetF=meetF, meetB=meetB, F=F, B=B, lf=lf, lb=lb)


def decode(ap):
    return [(ap >> (4 * i)) & 15 for i in range(K)]


def chain_edges(t):
    """回傳 forward 順序的 (srcShapeId, edgeId) 列表。"""
    # 前向段：從起點到交會點
    seg_f = []
    cur = t["meetF"]
    while t["F"][cur]["parent"] != BAD:
        seg_f.append((t["F"][t["F"][cur]["parent"]]["shape"], t["F"][cur]["pedge"]))
        cur = t["F"][cur]["parent"]
    seg_f.reverse()
    # 後向段：交會點 -> 目標。BP[u] 是「u 的父節點」（更靠近目標那一側），
    # 而 B[u]["pedge"] 是 u -> BP[u] 這條前向邊，故源形狀取 u 自己的 shape。
    seg_b = []
    cur = t["meetB"]
    while t["B"][cur]["parent"] != BAD:
        seg_b.append((t["B"][cur]["shape"], t["B"][cur]["pedge"]))
        cur = t["B"][cur]["parent"]
    return seg_f + seg_b


def build_case(ti, t, edges, shapes, targets):
    a, b = targets[ti]
    pos = {lab: lab for lab in LABELS}
    steps = []
    side_h = {0: "上", 1: "下"}
    side_v = {0: "左", 1: "右"}
    cur = frozenset(G)
    r0 = c0 = 0

    for (src_shape, ei) in chain_edges(t):
        e = edges[ei]
        # 當前狀態必須正規化為 src_shape
        rr = [p[0] for p in pos.values()]; cc = [p[1] for p in pos.values()]
        r0, c0 = min(rr), min(cc)
        cur_shape = tuple(sorted((p[0] - r0, p[1] - c0) for p in pos.values()))
        if cur_shape != tuple(shapes[src_shape]):
            print("SHAPE MISMATCH at step", len(steps), "target", ti)
            sys.exit(1)
        src_arr = decode(t["F"][0]["arr"]) if False else None
        # 由 C++ 的 slot 佈局重建 arr（槽位 = src_shape 的 row-major 格）
        slots = shapes[src_shape]
        # 分量格：cmask 對應的槽位
        comp_cells = [slots[j] for j in range(K) if (e["cmask"] >> j) & 1]
        comp_abs = frozenset((r + r0, c + c0) for r, c in comp_cells)
        unit = (e["ur"], e["uc"])
        want_side = side_h[e["side"]] if e["vert"] == 0 else side_v[e["side"]]
        pat = tuple(sorted((r - min(x[0] for x in comp_cells), c - min(x[1] for x in comp_cells))
                           for r, c in comp_cells))
        match = None
        for seam, side, comp0, u in mv.legal_moves(cur, S):
            if side != want_side or u != unit:
                continue
            if comp0 != comp_abs:
                continue
            if mv.apply_move(cur, comp0, u, S) is not None:
                match = (seam, side, comp0, u)
                break
        if match is None:
            print("NO LEGAL MOVE at step", len(steps), "target", ti)
            sys.exit(1)
        seam, side, comp0, u = match
        nxt = mv.apply_move(cur, comp0, u, S)
        moved_labels = sorted(lab for lab, p in pos.items() if p in comp0)
        steps.append({"seam": seam, "side": side, "unit": list(u),
                      "pattern": [list(x) for x in pat],
                      "moved": [list(x) for x in moved_labels]})
        for lab in moved_labels:
            p = pos[lab]
            pos[lab] = (p[0] + u[0] * S, p[1] + u[1] * S)
        cur = frozenset(pos.values())

    rr = [p[0] for p in pos.values()]; cc = [p[1] for p in pos.values()]
    nr0, nc0 = min(rr), min(cc)
    norm = {lab: (p[0] - nr0, p[1] - nc0) for lab, p in pos.items()}
    ok = (norm[a] == b and norm[b] == a and
          all(norm[x] == x for x in LABELS if x not in (a, b)))
    return {"m": M, "n": N, "s": S,
            "target": [list(a), list(b)], "steps": len(steps), "path": steps}, ok


def main():
    shapes, edges = load_all()
    targets = []

    # 槽位 -> (r,c)
    targets = [((i // N, i % N), (j // N, j % N))
               for i in range(K) for j in range(i + 1, K)
               if (i // N) % S == (j // N) % S and (i % N) % S == (j % N) % S]
    outdir = os.path.join(REPRO, "sequences")
    made = []
    only = None
    if len(sys.argv) > 1:
        only = [int(x) for x in sys.argv[1].split(",")]
    for ti in range(len(targets)):
        if only is not None and ti not in only:
            continue
        t = load_target(ti)
        if t["depth"] == BAD:
            print("target", ti, "unreached, skip")
            continue
        case, ok = build_case(ti, t, edges, shapes, targets)
        a, b = targets[ti]
        name = "swap_432_%d%d-%d%d_%dstep.json" % (a[0], a[1], b[0], b[1], len(case["path"]))
        with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False)
        print("target %d %s -> %s  steps=%d swap_ok=%s" % (ti, a, b, len(case["path"]), ok))
        made.append((ti, a, b, len(case["path"]), ok, name))
    with open(os.path.join(HERE, "sequences", "swap_432_all14_cases.json"), "w", encoding="utf-8") as f:
        json.dump([json.load(open(os.path.join(DATA, m[5]), encoding="utf-8")) for m in made],
                  f, ensure_ascii=False)
    print("wrote sequences/swap_432_all14_cases.json with", len(made), "cases")


if __name__ == "__main__":
    main()
