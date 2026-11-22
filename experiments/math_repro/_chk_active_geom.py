"""「哪一類會活」的幾何假設檢驗：活著的類，是不是剛好含有「同色的 2×2 方塊」
（s=2 時：格子 (r,c),(r,c+2),(r+2,c),(r+2,c+2) 全在類裡）？

做法：讀 sweep CSV，對判定不是平凡的形狀跑帶標籤 BFS，取回原形的置換，
看哪些格被搬動 → 得到「活的類」與「死的類」，再逐類檢查有沒有同色 2×2。

用法：D:\\python\\python.exe _chk_active_geom.py <csv> <s>
"""
import csv
import sys
from collections import Counter, deque

HERE = 'C:\\Users\\guo\\AppData\\Local\\Doubao\\User Data\\Default\\.doubao\\agent_mode\\workspace\\.sessions\\38455534466539522\\agents\\m_0cweYVOleyW\\math_lab\\branch\\experiments\\math_repro'
sys.path.insert(0, HERE)
import moves as mv


def parse(txt):
    return {(r, c) for r, row in enumerate(txt.split('/')) for c, ch in enumerate(row) if ch == '#'}


def perms_of(S, s):
    base = mv.normalize(S)
    order = sorted(base)
    start = frozenset((r, c, i) for i, (r, c) in enumerate(order))

    def norm(lab):
        r0 = min(p[0] for p in lab); c0 = min(p[1] for p in lab)
        return tuple(sorted((r - r0, c - c0, i) for (r, c, i) in lab))

    dist = {norm(start): 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        kc = norm(cur)
        Ss = {(r, c) for (r, c, _) in cur}
        for seam, side, comp, unit in mv.legal_moves(Ss, s):
            if mv.apply_move(Ss, comp, unit, s) is None:
                continue
            nxt = frozenset((r + unit[0] * s, c + unit[1] * s, i) if (r, c) in comp else (r, c, i)
                            for (r, c, i) in cur)
            k = norm(nxt)
            if k not in dist:
                dist[k] = dist[kc] + 1
                q.append(k)
    out = []
    for k in dist:
        if {(r, c) for (r, c, _) in k} != base:
            continue
        out.append({i: (r, c) for (r, c, i) in k})
    return out, order


def has_2x2(cells, s):
    """同色 2×2：以 s 為間距的四格"""
    return any((r, c) in cells and (r, c + s) in cells and (r + s, c) in cells and (r + s, c + s) in cells
               for (r, c) in cells)


def main(path, s):
    rows = list(csv.DictReader(open(path, encoding='utf-8')))
    table = Counter()
    bad = []
    for row in rows:
        S = parse(row['shape'])
        G = int(row['G'])
        if G == 1:
            continue
        perms, order = perms_of(S, s)
        moved = set()
        for p in perms:
            for i, dst in p.items():
                if order[i] != dst:
                    moved.add(order[i])
        classes = {}
        for (r, c) in mv.normalize(S):
            classes.setdefault((r % s, c % s), set()).add((r, c))
        active = {k for k, cells in classes.items() if cells & moved}
        for k, cells in classes.items():
            if len(cells) < 2:
                continue
            a = k in active
            b = has_2x2(cells, s)
            table[('活' if a else '死', '有同色2x2' if b else '無2x2')] += 1
            if a and not b:
                bad.append((row['shape'], sorted(cells)))
    print('類別統計（只算大小 ≥2 的類）:')
    for k, v in sorted(table.items()):
        print('   %s / %s : %d' % (k[0], k[1], v))
    if bad:
        print('\n「活著但沒有同色 2×2」的例子（前 8）:')
        for b in bad[:8]:
            print('   %-24s 類格=%s' % b)
    print('\n中間值形狀的逐類明細（活／死 + 類格數 + 跨度）:')
    for row in rows:
        S = parse(row['shape'])
        G, bound = int(row['G']), int(row['bound'])
        if G == 1 or G == bound:
            continue
        perms, order = perms_of(S, s)
        moved = set()
        for p in perms:
            for i, dst in p.items():
                if order[i] != dst:
                    moved.add(order[i])
        classes = {}
        for (r, c) in mv.normalize(S):
            classes.setdefault((r % s, c % s), set()).add((r, c))
        parts = []
        for k, cells in sorted(classes.items(), key=lambda x: -len(x[1])):
            a = '活' if cells & moved else '死'
            rspan = max(p[0] for p in cells) - min(p[0] for p in cells)
            cspan = max(p[1] for p in cells) - min(p[1] for p in cells)
            parts.append('%s|%d格|跨度(%d,%d)' % (a, len(cells), rspan, cspan))
        print('   %-22s G=%-3d 上界=%-3d  %s' % (row['shape'], G, bound, ' '.join(parts)))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
