"""統一驗算器（v2/10 專用）。

用法：python verify_swap.py <sequence.json> [--log <logpath>]

接受的 JSON 形態：
  A) 單一案例 dict：{"m","n","s","target":[[r,c],[r,c]],"path":[step,...]}
  B) 案例 list：[caseA, caseB, ...]

step 的寫法（與 _wide_B_verify.py 一致）：
  {"seam":"H_3","side":"上","unit":[0,1],"pattern":[[0,0],[0,1],...],"moved":[[r,c],...](可選)}

四項驗算（缺一不算通過）：
  1 合法：每步都能在 moves.legal_moves 找到同側／同方向／同分量圖案的合法走法，
         且 apply_move 非 None；
  2 同形：最終格集正規化 == 完成態正規化；
  3 恰兩格對換：正規化後，目標兩標籤互換、其餘每個標籤逐格回原位；
  4 同色類守恆：每個標籤沿途 r% s、c % s 不變。
任一案例任一項失敗 → 結束碼 1。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = os.path.dirname(HERE)
sys.path.insert(0, REPRO)
import moves as mv  # noqa: E402

DIRS = {(0, 1): '右', (0, -1): '左', (1, 0): '下', (-1, 0): '上'}


def solid(m, n):
    return frozenset((r, c) for r in range(m) for c in range(n))


def norm_set(S):
    r0 = min(r for r, _ in S)
    c0 = min(c for _, c in S)
    return frozenset((r - r0, c - c0) for r, c in S)


def comp_pattern(comp):
    r0 = min(r for r, _ in comp)
    c0 = min(c for _, c in comp)
    return tuple(sorted((r - r0, c - c0) for r, c in comp))


def replay(case):
    m, n, s = case['m'], case['n'], case['s']
    G = solid(m, n)
    labels = sorted(G)
    state = {lab: lab for lab in labels}
    steps = []
    legal_ok = True
    residue_viol = []

    for i, desc in enumerate(case['path'], 1):
        S = frozenset(state.values())
        unit = tuple(desc['unit'])
        pat = tuple(tuple(x) for x in desc.get('pattern', []))

        cands = []
        for seam, side, comp, u in mv.legal_moves(S, s):
            if side != desc['side'] or u != unit:
                continue
            if pat and comp_pattern(comp) != pat:
                continue
            if mv.apply_move(S, comp, u, s) is not None:
                cands.append((seam, side, comp, u))

        match = None
        if cands:
            moved_rec = {tuple(x) for x in desc.get('moved', [])}
            if moved_rec:
                pref = [c for c in cands if {state[lab] for lab in moved_rec} == c[2]]
                match = pref[0] if pref else None
            else:
                match = cands[0]

        nxt = mv.apply_move(S, match[2], unit, s) if match else None
        ok = match is not None and nxt is not None
        if not ok:
            legal_ok = False
        steps.append({'i': i, 'seam_rec': desc.get('seam', '-'),
                      'seam_match': match[0] if match else '-', 'side': desc['side'],
                      'unit': unit, 'ncomp': len(match[2]) if match else 0, 'legal': ok})
        if nxt is None:
            break

        for lab, p in state.items():
            if p in match[2]:
                state[lab] = (p[0] + unit[0] * s, p[1] + unit[1] * s)
        for lab in labels:
            rr, cc = state[lab]
            if rr % s != lab[0] % s or cc % s != lab[1] % s:
                residue_viol.append((i, lab))

    final_cells = frozenset(state.values())
    shape_ok = norm_set(final_cells) == norm_set(G)

    allr = [r for r, _ in state.values()]
    allc = [c for _, c in state.values()]
    r0, c0 = min(allr), min(allc)
    norm_state = {lab: (p[0] - r0, p[1] - c0) for lab, p in state.items()}
    offset = (r0, c0)

    a, b = tuple(case['target'][0]), tuple(case['target'][1])
    swap_ok = (len(norm_state) == len(labels)
               and norm_state.get(a) == b and norm_state.get(b) == a
               and all(norm_state[x] == x for x in labels if x not in (a, b)))
    residue_ok = not residue_viol

    return {'m': m, 'n': n, 's': s, 'target': (a, b), 'steps': len(case['path']),
            'replayed': len(steps), 'legal_ok': legal_ok, 'shape_ok': shape_ok,
            'swap_ok': swap_ok, 'residue_ok': residue_ok,
            'residue_viol': residue_viol[:8], 'offset': offset,
            'final_state': {str(k): v for k, v in norm_state.items()},
            'steps_log': steps}


def main():
    if len(sys.argv) < 2:
        print('用法：python verify_swap.py <sequence.json> [--log <log>]')
        return 2
    src = sys.argv[1]
    logpath = None
    if '--log' in sys.argv:
        logpath = sys.argv[sys.argv.index('--log') + 1]
    data = json.load(open(src, encoding='utf-8'))
    cases = data if isinstance(data, list) else [data]

    results, lines, all_pass = [], [], True
    for c in cases:
        r = replay(c)
        results.append(r)
        checks = [('合法', r['legal_ok']), ('同形', r['shape_ok']),
                  ('恰兩格對換', r['swap_ok']), ('同色類守恆', r['residue_ok'])]
        passed = all(ok for _, ok in checks)
        all_pass = all_pass and passed
        lines.append('== (%d,%d,%d) 目標 %s <-> %s ==' % (r['m'], r['n'], r['s'],
                                                          r['target'][0], r['target'][1]))
        lines.append('步數：%d（實際回放 %d）  收尾平移：%s' % (r['steps'], r['replayed'], r['offset']))
        for name, ok in checks:
            lines.append('  [%s] %s' % ('通過' if ok else '失敗', name))
        if not r['residue_ok']:
            lines.append('  殘餘類違例：%s' % (r['residue_viol'],))
        lines.append('  逐步明細：')
        for st in r['steps_log']:
            lines.append('   %4d. 紀錄 %s｜比對 %s｜%s側｜往%s %d 格｜%d 格｜合法=%s'
                         % (st['i'], st['seam_rec'], st['seam_match'], st['side'],
                            DIRS.get(st['unit'], '?'), r['s'], st['ncomp'], st['legal']))
        lines.append('')

    print('=== 摘要 ===')
    for r in results:
        print('(%d,%d,%d) 步數=%d 合法=%s 同形=%s 對換=%s 守恆=%s'
              % (r['m'], r['n'], r['s'], r['steps'], r['legal_ok'], r['shape_ok'],
                 r['swap_ok'], r['residue_ok']))
    print('總判定：', '全過' if all_pass else '有失敗')
    if logpath:
        with open(logpath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print('明細寫入', logpath)
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
