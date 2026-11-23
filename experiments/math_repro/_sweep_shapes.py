"""形狀全集普查（O-17 的資料）：枚舉 ≤ N 格的自由多聯骨牌，對每個形狀問

  1) 從完成態有幾條合法走法（0 條 = 凍結）
  2) 丟標籤的可達棋形數 R0（＝「跑道」的長度）
  3) 若 R0 ≥ --lab-min，才算帶標籤 BFS，得出群階 G 與判定（滿／平凡）

用法：D:\\python\\python.exe _sweep_shapes.py <N> <s> [--lab-min K]
"""
import sys
from collections import deque

HERE = 'C:\\Users\\guo\\AppData\\Local\\Doubao\\User Data\\Default\\.doubao\\agent_mode\\workspace\\.sessions\\38455534466539522\\agents\\m_0cweYVOleyW\\math_lab\\branch\\experiments\\math_repro'
sys.path.insert(0, HERE)
import moves as mv


def d4_canon(cs):
    """自由多聯骨牌的正規形：平移 + 8 個正交變換取字典序最小"""
    out = None
    for k in range(4):
        rot = [(c, -r) for (r, c) in cs] if k else list(cs)
        for t in (rot, [(r, -c) for (r, c) in rot]):
            n = mv.normalize(t)
            key = tuple(sorted(n))
            if out is None or key < out:
                out = key
    return frozenset(out)


def enumerate_shapes(n):
    cur = {frozenset([(0, 0)])}
    for _ in range(n - 1):
        nxt = set()
        for sh in cur:
            for (r, c) in sh:
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    p = (r + dr, c + dc)
                    if p not in sh:
                        nxt.add(d4_canon(sh | {p}))
        cur = nxt
    return cur


def reach_unlabeled(S, s):
    start = mv.normalize(S)
    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for seam, side, comp, unit in mv.legal_moves(cur, s):
            nxt = mv.apply_move(cur, comp, unit, s)
            if nxt is None:
                continue
            nxt = mv.normalize(nxt)
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return seen


def n_moves(S, s):
    return sum(1 for mv_ in mv.legal_moves(S, s) if mv.apply_move(S, mv_[2], mv_[3], s) is not None)


CAP = 600_000  # 單一形狀的帶標籤狀態上限；超過就放棄（記憶體不夠，回傳 None）


def labels_group(S, s):
    """帶標籤 BFS（標籤用 id，只正規化格子）：回傳 (可達標籤狀態數, 保色置換數, 上界, 未過濾置換數)

    為什麼要「保色」過濾：格子整體平移 1 格時，最小座標的殘餘會翻轉，這個被平移過的
    副本在正規化後看起來就像「同一個棋形、另一種標籤」。只有每塊都落回**自己顏色的格子**
    （order[i] 的 (r% s, c% s) 等於落點的殘餘）才是真正回到原位、且符合作弊不變式的排列。
    未過濾的數字會多出 2～4 倍，別用。
    """
    from math import factorial
    base = mv.normalize(S)
    order = sorted(base)
    start = frozenset((r, c, i) for i, (r, c) in enumerate(order))

    def norm(lab):
        r0 = min(p[0] for p in lab); c0 = min(p[1] for p in lab)
        # 用整數打包（每塊一個 byte）省記憶體：dr 4 bit、dc 4 bit
        code = 0
        for (r, c, i) in lab:
            code |= (((r - r0) << 4 | (c - c0)) << (8 * i))
        return code

    keys = {norm(start): 0}
    q = deque([start])
    perms = 1  # 起始態本身就是「回原形」且保色
    strict = 1
    try:
        while q:
            cur = q.popleft()
            kk = norm(cur)
            d = keys[kk]
            Ss = {(r, c) for (r, c, _) in cur}
            for seam, side, comp, unit in mv.legal_moves(Ss, s):
                if mv.apply_move(Ss, comp, unit, s) is None:
                    continue
                nxt = frozenset((r + unit[0] * s, c + unit[1] * s, i) if (r, c) in comp else (r, c, i)
                                for (r, c, i) in cur)
                nk = norm(nxt)
                if nk not in keys:
                    keys[nk] = d + 1
                    if len(keys) > CAP:
                        return None
                    if mv.normalize({(r, c) for (r, c, _) in nxt}) == base:
                        perms += 1
                        if all((order[i][0] % s, order[i][1] % s) == (r % s, c % s) for (r, c, i) in nxt):
                            strict += 1
                    q.append(nxt)
    except MemoryError:
        return None
    classes = {}
    for (r, c) in S:
        classes[(r % s, c % s)] = classes.get((r % s, c % s), 0) + 1
    bound = 1
    for v in classes.values():
        bound *= factorial(v)
    return len(keys), strict, bound, perms


def render(S):
    R = max(r for r, _ in S); C = max(c for _, c in S)
    return '/'.join(''.join('#' if (r, c) in S else '.' for c in range(C + 1)) for r in range(R + 1))


def main(N, s, lab_min):
    shapes = enumerate_shapes(N)
    print('≤%d 格自由多聯骨牌: %d 個（s=%d）' % (N, len(shapes), s))
    rows = []
    for S in sorted(shapes, key=lambda x: (len(x), sorted(x))):
        K = len(S)
        nm = n_moves(S, s)
        R0 = reach_unlabeled(S, s)
        rows.append((K, nm, len(R0), S))
    frozen = [r for r in rows if r[1] == 0]
    print('凍結（0 條合法走法）: %d / %d' % (len(frozen), len(rows)))
    print('有走法但 R0 = 2～3: %d' % len([r for r in rows if r[1] > 0 and r[2] <= 3]))
    print('\nR0 分佈（有走法的形狀）:')
    from collections import Counter
    dist = Counter(min(r[2], 100) for r in rows if r[1] > 0)
    for k in sorted(dist):
        print('   R0 %s%s: %d' % ('≤' if k == 100 else '=', '3' if k == 100 else k, dist[k]))
    print('\n帶標籤檢查（只做 R0 ≥ %d 的）:' % lab_min)
    verdicts = {}
    rows_out = []
    for K, nm, r0, S in rows:
        if nm == 0 or r0 < lab_min:
            continue
        L, perms, bound, raw = labels_group(S, s)
        if L is None:
            print('   %-22s K=%-2d 走法=%-3d R0=%-4d 跳過（狀態數 > %d，記憶體不足）' % (render(S), K, nm, r0, CAP))
            continue
        if perms == bound:
            verdict = '滿'
        elif perms == 1:
            verdict = '平凡'
        else:
            verdict = '中間值'
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        print('   %-22s K=%-2d 走法=%-3d R0=%-4d 標籤=%-6d 保色=%-5d 未濾=%-5d 上界=%-6d %s 每形%.4f'
              % (render(S), K, nm, r0, L, perms, raw, bound, verdict, L / r0))
        rows_out.append((K, render(S), nm, r0, L, perms, bound, verdict, L / r0, raw))
    print('\n判定統計: %s' % verdicts)
    if rows_out:
        import csv
        out = HERE + '\\_work\\sweep_shapes_%d_s%d.csv' % (N, s)
        with open(out, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['K', 'shape', 'moves', 'R0', 'labeled', 'G', 'bound', 'verdict', 'labels_per_shape', 'G_unfiltered'])
            w.writerows(rows_out)
        print('CSV → %s' % out)
    print('\n凍結形狀一覽:')
    for K, nm, r0, S in frozen:
        print('   %-22s K=%d R0=%d' % (render(S), K, r0))


if __name__ == '__main__':
    N = int(sys.argv[1]); s = int(sys.argv[2])
    lab_min = 20
    if '--lab-min' in sys.argv:
        lab_min = int(sys.argv[sys.argv.index('--lab-min') + 1])
    main(N, s, lab_min)
