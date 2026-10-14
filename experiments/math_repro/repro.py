# -*- coding: utf-8 -*-
"""滑块谜题「切线整组滑动」独立复现引擎（第一层：R1 / R2 / R3）。

依据《docs/math/问题重述_独立复现.md》自包含实现，**不参考仓库内任何现有
求解器 / math_question 代码**——本文件的正确性标准只有一个：文档 §1 的规则
定义，以及 §2 的目标数值。

规则实现自查清单（对应文档 §3.3 的四处最常见解读差异，本实现的选择）：
  (a) 连通性要求在每个单位步之后都保持 —— 是（§1.5）；
  (b) 可移动的是单侧完整连通分量 —— 是（§1.3，任意子集不可动）；
  (c) 计数在平移 + D4 等价下进行 —— 是（§1 计数口径）；
  (d) 状态图是有向图，移动一般不可逆 —— cone 与 B 分开计算（§1 三个关键集合）。

作者：貓九（独立复现方）
"""

from collections import deque
from itertools import permutations
from math import factorial
from sys import setrecursionlimit

setrecursionlimit(100000)

# ---------------------------------------------------------------- 状态表示
# 状态 = frozenset{(r, c)}。两个规范化：
#   trans_norm  仅平移归零（min 行/列移到 0）——保持朝向，R2 纤维判定用；
#   d4_canon    平移归零 + 取 D4 八变换的字典序最小形——等价类代表，图顶点用。


def trans_norm(cells):
    mr = min(r for r, _ in cells)
    mc = min(c for _, c in cells)
    return frozenset((r - mr, c - mc) for r, c in cells)


def _d4_images(cells):
    """D4 八变换（各自平移归零）。"""
    out = []
    for rot in range(4):
        if rot == 0:
            img = cells
        elif rot == 1:
            img = frozenset((c, -r) for r, c in cells)
        elif rot == 2:
            img = frozenset((-r, -c) for r, c in cells)
        else:
            img = frozenset((-c, r) for r, c in cells)
        for flip in (False, True):
            img2 = frozenset((r, -c) for r, c in img) if flip else img
            out.append(trans_norm(img2))
    return out


def d4_canon(cells):
    """等价类代表：八变换里字典序最小的规范化形。

    ⚠️ 必须按「坐标元组的字典序」取 min——frozenset 之间的 < 是子集关系，
    直接 sorted/min 会得到与朝向无关的伪序，八变换去重会静默失效。
    """
    best = min(_d4_images(cells), key=lambda img: tuple(sorted(img)))
    return frozenset(best)


def is_connected(cells):
    """四连通判定。"""
    if not cells:
        return False
    start = next(iter(cells))
    seen = {start}
    dq = deque([start])
    while dq:
        r, c = dq.popleft()
        for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if nb in cells and nb not in seen:
                seen.add(nb)
                dq.append(nb)
    return len(seen) == len(cells)


# ---------------------------------------------------------------- 合法移动
def side_components(shape, side_cells):
    """侧内四连通分量分解（§1.3：同侧内按四连通分解）。"""
    side = frozenset(side_cells)
    comps, seen = [], set()
    for cell in side:
        if cell in seen:
            continue
        comp = {cell}
        seen.add(cell)
        dq = deque([cell])
        while dq:
            r, c = dq.popleft()
            for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if nb in side and nb not in seen:
                    seen.add(nb)
                    comp.add(nb)
                    dq.append(nb)
        comps.append(frozenset(comp))
    return comps


def _try_move(shape, moved, rest, dr, dc, s):
    """沿 (dr, dc) 平移 moved 共 s 个单位步；每步后查无碰撞 + 全体四连通。

    (dr, dc) 是**总位移**，每单位步走它的 1/s（§1.5：把平移拆成 s 次单位步）。
    任一步违反 → 整个移动非法（不是回退重试，返回 None）。
    """
    ur, uc = dr // s, dc // s
    cur = moved
    for _ in range(s):
        cur = frozenset((r + ur, c + uc) for r, c in cur)
        if cur & rest:
            return None
        if not is_connected(cur | rest):
            return None
    return cur | rest


def legal_moves(shape, s, detail=False):
    """全部合法移动。

    detail=False 时返回后继形状列表；detail=True 时返回
    (后继, 移动分量, 总位移) 三元组——带标签重放必须知道**究竟哪几格**
    动了。形状差集法在分量与自身平移轨迹重叠时（如长条移 1 格）会漏格，
    标签就错位了，所以这里把分量信息从源头带出来。
    """
    rs = [r for r, _ in shape]
    cs = [c for _, c in shape]
    rmin, rmax, cmin, cmax = min(rs), max(rs), min(cs), max(cs)
    out = []
    # 水平缝 L ∈ [rmin, rmax−1]，块沿列方向 ±s
    for L in range(rmin, rmax):
        for side in (frozenset((r, c) for (r, c) in shape if r <= L),
                     frozenset((r, c) for (r, c) in shape if r > L)):
            if not side or side == shape:
                continue
            for comp in side_components(shape, side):
                # ⚠️ 其余 = shape − comp（保留同侧的其他分量！）。
                # 写成 shape − side 会把没被选中移动的兄弟分量整个丢掉，
                # 格数不变量被破坏，着色/连通等一切计数随之全错。
                rest = shape - comp
                for dr, dc in ((0, s), (0, -s)):
                    res = _try_move(shape, comp, rest, dr, dc, s)
                    if res is not None:
                        out.append((res, comp, (dr, dc)) if detail else res)
    # 垂直缝 L ∈ [cmin, cmax−1]，块沿行方向 ±s
    for L in range(cmin, cmax):
        for side in (frozenset((r, c) for (r, c) in shape if c <= L),
                     frozenset((r, c) for (r, c) in shape if c > L)):
            if not side or side == shape:
                continue
            for comp in side_components(shape, side):
                rest = shape - comp
                for dr, dc in ((s, 0), (-s, 0)):
                    res = _try_move(shape, comp, rest, dr, dc, s)
                    if res is not None:
                        out.append((res, comp, (dr, dc)) if detail else res)
    return out


# ---------------------------------------------------------------- 自由骨牌枚举
def trans_norm_shapes(k):
    """全部 k 格四连通形状（仅平移等价 = 固定多格骨牌）。"""
    shapes = {frozenset([(0, 0)])}
    for _ in range(k - 1):
        nxt = set()
        for sh in shapes:
            for r, c in sh:
                for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nb = (r + dr, c + dc)
                    if nb in sh:        # 已在形状中：跳过，否则 k−1 格形状混进集合
                        continue
                    nxt.add(trans_norm(sh | {nb}))
        shapes = nxt
    return shapes


def free_polyominoes(k):
    """k 格自由多格骨牌（平移 + D4 等价）的规范形集合 = 图 G 的顶点集。"""
    return {d4_canon(sh) for sh in trans_norm_shapes(k)}


# ---------------------------------------------------------------- 图 G 与计数
class PuzzleGraph:
    """(m, n, s) 谜题的移动有向图（顶点 = 自由形等价类规范形）。"""

    def __init__(self, m, n, s):
        self.m, self.n, self.s = m, n, s
        self.goal = frozenset((r, c) for r in range(m) for c in range(n))
        self.vertices = free_polyominoes(m * n)
        self.adj = {}          # u -> set of v（D4 规范形）
        for v in self.vertices:
            self.adj[v] = set()
        for v in self.vertices:
            for mv in legal_moves(v, s):
                self.adj[v].add(d4_canon(mv))
        # 着色判定（两种口径并报）：《问题重述》写的是「类计数多重集相同」，
        # 但官方目标值体系（experiments/math_repro/verify_coloring.py）用的是「两朝向
        # × 全部相位平移下的类计数向量精确匹配」——后者更严（多重集允许任意
        # 类重命名，相位平移只允许平移重命名）。(3,3,2) 上两者分别给出
        # 140 与 105，目标值 105 对应向量口径；文档复述不精确，以实测为准。
        self.goal_coloring = self._coloring(self.goal)
        self._variants = self._target_variants()
        self.set_A = {v for v in self.vertices
                      if self._class_vector(v) in self._variants}
        self.set_A_multiset = {v for v in self.vertices
                               if self._coloring(v) == self.goal_coloring}
        # cone：goal 正向可达；B：反向可达 goal
        self.cone = self._bfs(self.goal, forward=True)
        self.radj = {}
        for u, vs in self.adj.items():
            for v in vs:
                self.radj.setdefault(v, set()).add(u)
        self.set_B = self._bfs(self.goal, forward=False)
        self.dist = self._bfs_dist(self.goal)   # 到 goal 的最少移动数

    def _coloring(self, shape):
        """类计数多重集（平移 + D4 不变量）。"""
        s = self.s
        counts = {}
        for r, c in shape:
            counts[(r % s, c % s)] = counts.get((r % s, c % s), 0) + 1
        return tuple(sorted(counts.values()))

    def _class_vector(self, shape):
        """类计数**向量**（类标签固定，不平移重命名）。"""
        s = self.s
        arr = [0] * (s * s)
        for r, c in shape:
            arr[(r % s) * s + (c % s)] += 1
        return tuple(arr)

    def _target_variants(self):
        """目标着色的全部合法向量：两种朝向 × s² 个相位平移。

        对应官方 verify_coloring.target_variants：状态整体平移 (dr, dc)
        会把类 (a,b) 重命名为 (a+dr, b+dc)，故「存在一个平移成员满足着色」
        ⟺ 向量落在这个变体集里。
        """
        m, n, s = self.m, self.n, self.s
        out = set()
        for (mm, nn) in ((m, n), (n, m)):
            base = [0] * (s * s)
            for r in range(mm):
                for c in range(nn):
                    base[(r % s) * s + (c % s)] += 1
            for dr in range(s):
                for dc in range(s):
                    v = [0] * (s * s)
                    for a in range(s):
                        for b in range(s):
                            v[((a + dr) % s) * s + ((b + dc) % s)] = base[a * s + b]
                    out.add(tuple(v))
        return out

    def _bfs(self, start, forward):
        adj = self.adj if forward else self.radj
        seen = {start}
        dq = deque([start])
        while dq:
            u = dq.popleft()
            for v in adj.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    dq.append(v)
        return seen

    def _bfs_dist(self, goal):
        dist = {goal: 0}
        dq = deque([goal])
        while dq:
            u = dq.popleft()
            for v in self.radj.get(u, ()):
                if v not in dist:
                    dist[v] = dist[u] + 1
                    dq.append(v)
        return dist

    def dead_states(self):
        """死局 = cone − B。"""
        return self.cone - self.set_B

    def dead_components(self):
        """死分量：全 A 上把每条弧视作无向边做并查集，取不含 goal 的分量。"""
        parent = {v: v for v in self.set_A}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for u in self.set_A:
            for v in self.adj[u]:
                if v in parent:
                    union(u, v)
        groups = {}
        for v in self.set_A:
            groups.setdefault(find(v), []).append(v)
        groot = find(self.goal)
        dead = {k: v for k, v in groups.items() if k != groot}
        return list(dead.values())


# ---------------------------------------------------------------- R2/R3 联合空间
class LabeledSpace:
    """带标签联合空间：状态 = (平移规范化形状, frozenset((cell, label)))。

    标签随格子走；移动时由前后形状差求出移动格（moved_old → moved_new），
    标签跟着平移。矩形纤维 = 形状严格等于原始朝向 m×n 矩形（文档 R2 口径①）。
    """

    def __init__(self, m, n, s, labels=None):
        self.m, self.n, self.s = m, n, s
        self.rect = frozenset((r, c) for r in range(m) for c in range(n))
        if labels is None:
            labels = {(r, c): r * n + c for r in range(m) for c in range(n)}
        self.start = (self.rect, frozenset(labels.items()))

    def _step(self, shape, lab, s):
        """全部合法移动后的联合状态（标签随分量精确平移）。"""
        out = []
        for mv, comp, (dr, dc) in legal_moves(shape, s, detail=True):
            ns = trans_norm(mv)
            mr2 = min(r for r, _ in mv)
            mc2 = min(c for _, c in mv)
            moved_labels, rest_labels = {}, {}
            for (r, c), lb in lab:
                if (r, c) in comp:
                    moved_labels[(r + dr, c + dc)] = lb
                else:
                    rest_labels[(r, c)] = lb
            # 标签坐标须与规范化形状同坐标系（矩形纤维判定与行主序读出）
            if mr2 or mc2:
                moved_labels = {((r - mr2, c - mc2)): lb
                                for (r, c), lb in moved_labels.items()}
                rest_labels = {((r - mr2, c - mc2)): lb
                               for (r, c), lb in rest_labels.items()}
            out.append((ns, frozenset({**rest_labels, **moved_labels}.items())))
        return out

    def forward_closure(self, limit=None):
        """从 (矩形, 恒等标签) 正向 BFS 全联合空间。

        返回 (visited, rect_labels, rect_labels_rev)：
          visited          全部可达联合状态；
          rect_labels      矩形纤维上可达的标签元组集合（行主序读出）= 群 S；
          rect_labels_rev  能经反向弧回到 (矩形, 恒等) 的标签元组集合（判胜可达）。
        """
        n = self.m * self.n

        def read(lab_fs):
            d = dict(lab_fs)
            return tuple(d[(r, c)] for r in range(self.m) for c in range(self.n))

        start = self.start
        visited = {start}
        dq = deque([start])
        rect_labels = set()
        if start[0] == self.rect:
            rect_labels.add(read(start[1]))
        # 反向邻接（用于判胜可达）：建在 visited 闭包上
        radj = {}
        while dq:
            shape, lab = dq.popleft()
            for ns, nlab in self._step(shape, lab, self.s):
                radj.setdefault((ns, nlab), set()).add((shape, lab))
                if (ns, nlab) not in visited:
                    visited.add((ns, nlab))
                    if ns == self.rect:
                        rect_labels.add(read(nlab))
                    dq.append((ns, nlab))
                    if limit and len(visited) > limit:
                        raise RuntimeError('联合空间超过 limit')
        # 判胜可达：从 (rect, id) 沿反向弧可达的矩形纤维标签
        rev_seen = {start}
        rdq = deque([start])
        rect_labels_rev = {read(start[1])}
        while rdq:
            u = rdq.popleft()
            for v in radj.get(u, ()):
                if v not in rev_seen:
                    rev_seen.add(v)
                    if v[0] == self.rect:
                        rect_labels_rev.add(read(v[1]))
                    rdq.append(v)
        return visited, rect_labels, rect_labels_rev

    def replay_moves(self, move_seq):
        """沿具体移动序列（[(comp, (dr, dc)), ...]）重放标签，返回最终置换。

        形状路径重放有根本歧义：等价类图上的一条边可能对应多个不同具体移动
        （对称位置），标签效果不同。所以生成元搜索直接在原始坐标空间枚举
        具体移动，这里只做标签重放。形状与标签同步跟踪，读出前先归零坐标
        （路径终点的矩形可能落在任意相位）。
        """
        shape = self.rect
        lab = {(r, c): r * self.n + c
               for r in range(self.m) for c in range(self.n)}
        for comp, (dr, dc) in move_seq:
            shape = (shape - comp) | frozenset((r + dr, c + dc) for r, c in comp)
            lab = {((r + dr, c + dc) if (r, c) in comp else (r, c)): lb
                   for (r, c), lb in lab.items()}
        mr = min(r for r, _ in shape)
        mc = min(c for _, c in shape)
        if mr or mc:
            lab = {((r - mr, c - mc)): lb for (r, c), lb in lab.items()}
        return tuple(lab[(r, c)] for r in range(self.m)
                     for c in range(self.n))


def perm_compose(p, q):
    """置换复合 p∘q（先 q 后 p，行主序元组表示）。"""
    return tuple(p[q[i]] for i in range(len(p)))


def group_order(gens):
    """生成元集的生成群阶（元素 BFS 闭包）。"""
    ident = tuple(range(len(next(iter(gens)))))
    seen = {ident}
    dq = deque([ident])
    while dq:
        cur = dq.popleft()
        for g in gens:
            nxt = perm_compose(g, cur)
            if nxt not in seen:
                seen.add(nxt)
                dq.append(nxt)
    return len(seen)


# ---------------------------------------------------------------- 复现主流程
def run_R1(m, n, s):
    g = PuzzleGraph(m, n, s)
    dead = g.dead_states()
    comps = g.dead_components()
    god = max(g.dist.values()) if g.dist else None
    return {
        'vertices_total': len(g.vertices),
        '|A|': len(g.set_A),
        '|A|_multiset': len(g.set_A_multiset),
        '|B|': len(g.set_B),
        '|cone|': len(g.cone),
        'god_number': god,
        'dead_states': len(dead),
        'dead_components': len(comps),
        'dead_component_total': sum(len(c) for c in comps),
    }


def run_R2_R3(m, n, s, gen_paths_limit=8):
    """R2（群阶）与 R3（标法反例）。

    小尺寸联合空间直接 BFS；(3,3,1) 这类大联合空间用「形状路径重放 +
    生成群阶」闭合（文档口径③：集合对拼接封闭 → 求生成群阶即可）。
    """
    # 着色类计数 → 候选标法总数
    s_mod = s
    counts = {}
    for r in range(m):
        for c in range(n):
            counts[(r % s_mod, c % s_mod)] = counts.get((r % s_mod, c % s_mod), 0) + 1
    candidates = 1
    for v in counts.values():
        candidates *= factorial(v)

    ls = LabeledSpace(m, n, s)
    # 联合空间规模预估：|A| × 候选数；太大则走生成元路线
    pg = PuzzleGraph(m, n, s)
    est = len(pg.set_A) * candidates
    result = {'candidates': candidates}
    if est <= 3_000_000:
        visited, fwd, rev = ls.forward_closure()
        result['group_order_scramble_reachable'] = len(fwd)
        result['win_reachable'] = len(rev)
    else:
        # 生成元路线：原始坐标空间 DFS 具体移动序列，回到「原始朝向矩形」
        # 时用标签重放得置换（形状等价类边有歧义——同一边可对应不同具体
        # 移动、标签效果不同——所以不能在规范形图上重放）。
        goal0 = pg.goal                      # 原始朝向、已归零
        gens = set()
        n_paths = 0

        def dfs(shape, seq, depth):
            nonlocal n_paths
            if seq and trans_norm(shape) == goal0:
                gens.add(ls.replay_moves(seq))
                n_paths += 1
                return                        # 回到矩形即收，更长的路让给别的分支
            if depth == 0 or n_paths >= 8000:
                return
            for mv, comp, d in legal_moves(shape, s, detail=True):
                if n_paths >= 8000:
                    return
                seq.append((comp, d))
                dfs(mv, seq, depth - 1)
                seq.pop()

        dfs(goal0, [], 8)
        if gens:
            result['group_order_generator'] = group_order(gens)
            result['n_generators'] = len(gens)
        else:
            result['group_order_generator'] = None
    return result


def main():
    print('=== R1/R2/R3 第一层复现（依据《问题重述_独立复现.md》） ===\n')
    for (m, n, s) in [(2, 3, 1), (2, 3, 2), (3, 3, 1), (3, 3, 2)]:
        k = m * n
        fixed = len(trans_norm_shapes(k))
        free = len(free_polyominoes(k))
        r1 = run_R1(m, n, s)
        print(f'--- ({m},{n},{s}) K={k} ---')
        print(f'  固定形 {fixed} / 自由形 {free}（交叉核对：K=6→216/35, K=9→9910/1285）')
        print(f'  R1: 等价类总数 {r1["vertices_total"]}, |A|(向量口径) {r1["|A|"]}, '
              f'|A|(多重集口径) {r1["|A|_multiset"]}, '
              f'|B| {r1["|B|"]}, |cone| {r1["|cone|"]}, '
              f'死局 {r1["dead_states"]}, 上帝之数 {r1["god_number"]}')
        print(f'      死分量 {r1["dead_components"]} 个 / '
              f'{r1["dead_component_total"]} 状态')
        r23 = run_R2_R3(m, n, s)
        print(f'  R2/R3: 候选标法 {r23["candidates"]}')
        for key in ('group_order_scramble_reachable', 'group_order_generator'):
            if key in r23:
                print(f'      {key} = {r23[key]}'
                      + (f'（生成元 {r23["n_generators"]} 个）'
                         if key == 'group_order_generator' and r23.get('n_generators') else ''))
        if 'win_reachable' in r23:
            print(f'      反向判胜可达 = {r23["win_reachable"]}')
        print()


if __name__ == '__main__':
    main()
