# -*- coding: utf-8 -*-
"""路徑壓縮原型（僅實驗，不改求解器）：精確逆對抵消 + 最終盤面一致性校驗。

背景：當前 optimize_path（shape_gather.py）是「整盤狀態哈希去環」——只刪
「回到見過的整盤狀態」的步。但大量廢步是「局部淨零」：某組塊被移走、之後被
移回，中間夾著**其他塊**的移動，整盤狀態從未重複 → 去環器永遠看不見。

本原型在「動作代數」層面抓這類：

  精確逆對：move a 把集合 S 由 P 移到 Q；move b 恰好把 Q 移回 P
  （b.source == a.target 且 b.target == a.source，純集合條件，無需方向語義），
  且 a、b 之間沒有任何一步的 source 碰 Q → (a,b) 是 S 上的封閉環。
  刪掉二者後，中間各步的適用性與效果均不變，後續盤面逐步全等（有證明）。

安全性由兩層保證：
  1. 上述刪除條件本身可證（中間步 source 與 Q 不交 ⇒ 中間步照樣適用、效果相同）。
  2. 重放壓縮後序列，斷言最終盤面 == 原始最終盤面。

資料來源：save 存檔的 move_info.moved_positions（source，絕對坐標）+
  相鄰快照差。⚠️ 滑片剛體平移內部有「塊落到同片其他塊原位」的重疊，
  集合差只含淨空出/淨到達的塊，故目標集必須用
  target = added ∪ (source − removed) 推導，不能拿差集硬當 source/target。

用法：D:/python/python.exe experiments/optimize_cancel.py [存檔路徑]
"""
import json
import sys
from collections import Counter

SAVE = sys.argv[1] if len(sys.argv) > 1 else 'save/gathertest2-8-8-20261010-170304.json'


def decode(snap):
    """快照 → 絕對坐標集合（與 history.restore_snapshot 同一口徑）。"""
    b = snap['bounds']
    m = snap['matrix']
    ro, co = b['min_row'], b['min_col']
    return set((ro + r, co + c)
               for r, row in enumerate(m)
               for c, cell in enumerate(row) if cell)


def load(path):
    d = json.load(open(path, encoding='utf-8'))
    snaps = d['history']['snapshots']
    S = [decode(s) for s in snaps]
    moves = []
    for i in range(1, len(S)):
        ml = snaps[i].get('moves') or []
        assert len(ml) == 1, f'snap{i}: 合併快照 {len(ml)} 步，本原型不支援'
        src = set(tuple(p) for p in ml[0]['moved_positions'])
        removed = S[i - 1] - S[i]
        added = S[i] - S[i - 1]
        assert src <= S[i - 1], f'snap{i}: source 不在上一快照（對齊失敗）'
        tgt = added | (src - removed)
        assert len(tgt) == len(src), f'snap{i}: target 數量 {len(tgt)}≠{len(src)}'
        moves.append({'idx': i, 'source': src, 'target': tgt,
                      'gt': ml[0].get('gap_type'), 'gl': ml[0].get('gap_line'),
                      'dir': ml[0].get('direction'), 'n': len(src)})
    return S, moves


def cancel_inverse_pairs(seq):
    """在當前序列上反覆找精確逆對並刪除，直到不動點。"""
    removed_log = []
    changed = True
    while changed:
        changed = False
        n = len(seq)
        for a in range(n - 1):
            ma = seq[a]
            for b in range(a + 1, n):
                mb = seq[b]
                if mb['source'] == ma['target'] and mb['target'] == ma['source']:
                    blocked = any(not seq[k]['source'].isdisjoint(ma['target'])
                                  for k in range(a + 1, b))
                    if not blocked:
                        removed_log.append((ma['idx'], mb['idx'], ma['gt'],
                                            ma['gl'], ma['dir'], mb['dir'],
                                            ma['n']))
                        del seq[b]
                        del seq[a]
                        changed = True
                        break
            if changed:
                break
    return seq, removed_log


def simulate(S0, seq):
    state = set(S0)
    for m in seq:
        assert state >= m['source'], \
            'step %s: source not in current board (bug)' % m['idx']
        state = (state - m['source']) | m['target']
    return state


def main():
    S, moves = load(SAVE)
    print(f'存檔: {SAVE}')
    print(f'原始步數: {len(moves)}  盤面塊數={len(S[0])}')

    seq = [dict(m) for m in moves]
    kept, log = cancel_inverse_pairs(seq)
    final = simulate(S[0], kept)
    ok = (final == S[-1])

    print(f'\n抵消移除: {len(log) * 2} 步 ({len(log)} 對)')
    print(f'壓縮後步數: {len(kept)}  (減少 {len(moves) - len(kept)} 步, '
          f'{100 * (len(moves) - len(kept)) / len(moves):.1f}%)')
    print(f'最終盤面 == 原始最終盤面: {ok}  ← 安全性斷言'
          + ('' if ok else '  *** 失敗，演算法有誤 ***'))
    if log:
        print('\n--- 被移除的逆對 (步i, 步j, 縫, 線, i方向→j方向, 塊數) ---')
        for p in log:
            print('   步%3d ↔ 步%3d  %s線=%s  %s→%s  %d塊' % p)

    # 剩餘步的軌道統計：同一 (gap_type,gap_line) 反覆出現 = 合併型壓縮候選
    track = Counter((m['gt'], m['gl']) for m in kept)
    hot = sorted([(k, v) for k, v in track.items() if v >= 3], key=lambda x: -x[1])
    if hot:
        print('\n--- 剩餘步中出現 ≥3 次的軌道（合併型壓縮候選，僅報告） ---')
        for (gt, gl), v in hot:
            print(f'   {gt}線={gl}: {v} 步')


if __name__ == '__main__':
    main()
