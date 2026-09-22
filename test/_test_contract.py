# -*- coding: utf-8 -*-
"""契约测试：SliderMatrix（方形）與 TriangleSliderMatrix（三角）的共同契约（Stage M0）。

B1 宣稱兩者「實現相同契約」，但此前沒有任何東西強制它；米字格進來時
契約漂移要在測試層被抓到，所以這裡把共同契約寫成可執行規範。

共同契約（兩種形態都必須滿足）：
  positions/get_boundaries/update_matrix/get_matrix/opt/try_move_ex/
  commit_move/is_single_connected/is_solved/compute_score/export_map/import_map/
  shuffle(min_score)
形態擴展（有則測，方形沒有 is_valid_gap/all_gaps/block_at）：
  is_valid_gap/all_gaps/block_at

兩種形態的差異全部收在 ADAPTERS 裡，其餘斷言完全共用。

執行：python test/_test_contract.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game as game_square  # noqa: E402
import game_triangle  # noqa: E402
from game import SliderMatrix  # noqa: E402
from game_triangle import TriangleSliderMatrix  # noqa: E402

failures = []


def check(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        failures.append(msg)


ADAPTERS = {
    'square': {
        'make': lambda: SliderMatrix(4, 5),
        'module': game_square,
        'gap_dirs': {'h': ('w', 's'), 'v': ('a', 'd')},   # 垂直於縫隙線
        'n_blocks': 20,
    },
    'triangle': {
        'make': lambda: TriangleSliderMatrix(4),
        'module': game_triangle,
        'gap_dirs': {'h': ('a', 'd'), 'p': ('e', 'z'), 'n': ('w', 'x')},  # 平行於縫隙線
        'n_blocks': 16,
    },
}


def key_of(b):
    return tuple(b.location)


def gap_lines(g, ad, gap_type):
    """某個縫隙族的候選線。

    有 all_gaps 的形態（三角）直接复用它的有效性判定；方形按邊界枚舉。
    """
    if hasattr(g, 'all_gaps'):
        return [line for (t, line) in g.all_gaps() if t == gap_type]
    if gap_type == 'h':
        return list(range(ad['axis']['h'][0], ad['axis']['h'][1]))
    if gap_type == 'v':
        return list(range(ad['axis']['v'][0], ad['axis']['v'][1]))
    return []


def with_hole(ad, hole):
    """複製一個新局並移除指定位置的一塊（用來製造可滑的缺口）。"""
    g = ad['make']()
    g.blocks = [x for x in g.blocks if key_of(x) != hole]
    g.update_matrix()
    return g


def run_shared_contract(name, ad):
    print(f"== {name}：共同契約 ==")
    directions = ad['module'].DIRECTIONS
    g = ad['make']()
    keys = {key_of(b) for b in g.blocks}
    check(len(keys) == len(g.blocks) == ad['n_blocks'],
          f"初始 {ad['n_blocks']} 塊且位置唯一（實得 {len(g.blocks)}）")

    # get_boundaries 與實際位置一致
    b = g.get_boundaries()
    rs = [k[0] for k in keys]
    cs = [k[1] for k in keys]
    check(set(b) == {'min_row', 'max_row', 'min_col', 'max_col'}
          and b['min_row'] == min(rs) and b['max_row'] == max(rs)
          and b['min_col'] == min(cs) and b['max_col'] == max(cs),
          "get_boundaries 四鍵與實際極值一致")
    ad['axis'] = {'h': (b['min_row'], b['max_row']),
                  'v': (b['min_col'], b['max_col'])}

    # update_matrix / get_matrix：形狀對得上、總佔用位數 == 塊數
    g.update_matrix()
    mat = g.get_matrix()
    rows = b['max_row'] - b['min_row'] + 1
    cols = b['max_col'] - b['min_col'] + 1
    check(len(mat) == rows and all(len(r) == cols for r in mat),
          f"矩陣形狀 {rows}×{cols}")
    total = 0
    for r in mat:
        for v in r:
            total += bin(v).count('1') if isinstance(v, int) else int(bool(v))
    check(total == ad['n_blocks'], f"矩陣佔用位數 == 塊數（{total}）")

    # is_single_connected
    check(g.is_single_connected(keys), "初始局面單一連通")
    check(g.is_single_connected(set()), "空集合視為連通")

    # ---- opt：選中集非空、真子集、單連通、含錨點本身 ----
    ok_opt = True
    tried = 0
    for gt in ad['gap_dirs']:
        for line in gap_lines(g, ad, gt):
            g.opt(gt, line, g.blocks[0])
            sel = {key_of(x) for x in g.blocks if x.be_opted}
            if not sel:
                continue
            tried += 1
            if len(sel) >= len(keys):
                ok_opt = False
            if not g.is_single_connected(sel):
                ok_opt = False
            if key_of(g.blocks[0]) not in sel:
                ok_opt = False
            break
    check(ok_opt and tried >= len(ad['gap_dirs']),
          f"每個縫隙族都能選出非空真子集、單連通且含錨點（試了 {tried} 條線）")

    # ---- try_move_ex 無選中 → 拒絕 ----
    for blk in g.blocks:
        blk.be_opted = False
    pos, reason = g.try_move_ex('w', 1)
    check(pos == [] and reason == 'no_selection', "無選中時 try_move_ex 拒絕")

    # ---- 每個縫隙族都存在一步合法移動，且 commit 落位與 DIRECTIONS
    #      增量一致。注意：實心盤上沿縫移動必然整體斷開（這是規則，不是
    #      bug），所以先挖一個孔再滑；縫隙兩側都要試（錨點決定選哪側）。 ----
    ok_move = True
    per_family = {}
    holes = [key_of(x) for x in g.blocks]
    for gt, dirs in ad['gap_dirs'].items():
        found = False
        for hole in holes:
            if found:
                break
            g2 = with_hole(ad, hole)
            for line in gap_lines(g2, ad, gt):
                if found:
                    break
                for d in dirs:
                    for anchor in g2.blocks:
                        g3 = with_hole(ad, hole)
                        g3.opt(gt, line, anchor)
                        sel = [x for x in g3.blocks if x.be_opted]
                        if not sel:
                            continue
                        before = [key_of(x) for x in sel]
                        final, why = g3.try_move_ex(d, 1)
                        if why != '' or len(final) != len(sel):
                            continue
                        g3.commit_move(final)
                        after = [key_of(x) for x in sel]
                        if [tuple(p) for p in final] != after:
                            ok_move = False
                            continue
                        di, dj = directions[d]
                        if any(p1[0] - p0[0] != di or p1[1] - p0[1] != dj
                               for p0, p1 in zip(before, after)):
                            ok_move = False
                            continue
                        if len({key_of(x) for x in g3.blocks}) != len(g3.blocks):
                            ok_move = False
                        continue
                    found = True
        per_family[gt] = found
    check(ok_move and all(per_family.values()),
          f"各縫隙族挖孔後均有合法一步移動且 commit 落位正確（{per_family}）")

    # ---- 失敗原因只在已知集合內 ----
    g = ad['make']()
    g.opt(*_first_gap(g, ad), g.blocks[0])
    if not any(x.be_opted for x in g.blocks):
        check(True, "（錨點所在側為空，跳過失敗原因檢查）")
    else:
        pos, reason = g.try_move_ex('?', 1)
        check(pos == [] and reason == 'no_selection', "未知方向字母被拒")
        pos, reason = g.try_move_ex(_other_dir(ad), 99)
        check(reason in ('', 'collision', 'disconnected', 'no_selection'),
              f"大步數移動回饋已知原因（{reason!r}）")

    # ---- is_solved：初始為真；整體平移後仍為真；缺一塊後為假 ----
    g = ad['make']()
    check(g.is_solved(), "初始局面 is_solved 為真")
    for blk in g.blocks:
        blk.location = [blk.location[0] + 3, blk.location[1] + 7] + \
            list(blk.location[2:])
    check(g.is_solved(), "整體平移後 is_solved 仍為真")
    g.blocks.pop()
    g.update_matrix()
    check(not g.is_solved(), "缺塊後 is_solved 為假")

    # ---- compute_score：復原態 1.0 ----
    g = ad['make']()
    check(abs(g.compute_score() - 1.0) < 1e-9, "復原態 compute_score == 1.0")

    # ---- export_map ∘ import_map 往返 ----
    g = ad['make']()
    text = g.export_map()
    g_import = ad['make']()
    check(g_import.import_map(text), "import_map 接受 export_map 輸出")

    def norm(game):
        bs = game.get_boundaries()
        return {tuple(v - (bs['min_row'] if i == 0 else bs['min_col'])
                      for i, v in enumerate(key_of(x)))
                for x in game.blocks}

    check(norm(g) == norm(g_import), "地圖往返後位置集合一致")
    check(not g_import.import_map(""), "空串導入失敗")

    # ---- shuffle(attempts, step, min_score) ----
    g = ad['make']()
    g.shuffle(attempts=80, step=2, min_score=0.75)
    ks = {key_of(x) for x in g.blocks}
    check(len(g.blocks) == ad['n_blocks'] and len(ks) == ad['n_blocks'],
          "shuffle 後塊數與唯一性保持")
    check(g.compute_score() <= 0.75 + 1e-9,
          f"shuffle(min_score=0.75) 後聚攏度達標（{g.compute_score():.3f}）")
    check(not any(x.be_opted for x in g.blocks), "shuffle 後清空選中")


def _first_gap(g, ad):
    """返回一個能選出非空子集的 (gap_type, line)。"""
    for gt in ad['gap_dirs']:
        for line in gap_lines(g, ad, gt):
            g.opt(gt, line, g.blocks[0])
            if any(x.be_opted for x in g.blocks):
                return gt, line
    return ('h', 0)


def _other_dir(ad):
    """一個未必合法的方向字母（用來檢查大步數/異常輸入的容錯）。"""
    for d in 'wsad':
        if d not in {x for ds in ad['gap_dirs'].values() for x in ds}:
            return d
    return 'w'


def run_optional(name, ad):
    print(f"== {name}：形態擴展 ==")
    g = ad['make']()
    if hasattr(g, 'all_gaps'):
        gaps = g.all_gaps()
        check(len(gaps) > 0 and all(g.is_valid_gap(*x) for x in gaps)
              and all(x[0] in ad['gap_dirs'] for x in gaps),
              f"all_gaps 返回有效縫隙 {len(gaps)} 條")
        check(not g.is_valid_gap('?', 0), "未知族 is_valid_gap 為假")
    else:
        print("  --   方形無 is_valid_gap/all_gaps（形態擴展，跳過）")
    if hasattr(g, 'block_at'):
        k = key_of(g.blocks[0])
        check(g.block_at(k) is not None and key_of(g.block_at(k)) == k,
              "block_at 命中")
        check(g.block_at((-99, -99) + k[2:]) is None, "block_at 未命中回 None")
    else:
        print("  --   方形無 block_at（形態擴展，跳過）")


for _name, _ad in ADAPTERS.items():
    run_shared_contract(_name, _ad)
    run_optional(_name, _ad)

print()
if failures:
    print(f"共 {len(failures)} 項失敗:")
    for n in failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
