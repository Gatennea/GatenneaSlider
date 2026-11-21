# -*- coding: utf-8 -*-
"""§67 捆綁態安全打亂漏 group 回歸測試（2026-11-21）。

用戶實測：5×5、step2、中心 3×3 四對捆綁的樣式，從還原態正向玩時中心
「拆不開」，可自動打亂把它拆開後，撤銷路徑走不回還原態。

本測試用**可生成的幾何典例**（不依賴玩家 config 裡的 bondage.json）釘死
三件事：

A. 判據：位置相同、group 歸屬不同的「逆向」必須判不可逆；舊的只比位置
   寫法會把它放行（本檔在舊代碼上 A 會紅）。
B. 證書：打亂 record 逐條反轉，位置 + group 都精確回到每步前狀態；
   record 的 trigger 必須記錄，否則同縫兩側各是一個分量，撤銷時點錯側
   就換了一組塊（naive「final 第一塊」在 seed=6 上走不通，trigger 可以）。
C. 不變量：還原態枚舉所有合法步，中心 3×3 九塊的相對形狀不被切開；
   打亂後各捆綁組自身仍剛體（組內相對偏移不變）。

D. 引擎通道：`safe_scramble` 每步逆移動 apply 後，`_exact_key`（含 group）
   與走前逐塊相等。
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix  # noqa: E402
from engine import Board, Block, safe_scramble, square_spec  # noqa: E402
from engine.analysis import _exact_key, _find_inverse  # noqa: E402

M = N = 5
STEP = 2
CELLS = [(r, c) for r in range(M) for c in range(N)]
GROUPS = {(1, 1): 1, (2, 1): 1,      # 竖对
          (1, 2): 2, (1, 3): 2,      # 横对
          (2, 3): 3, (3, 3): 3,      # 竖对
          (3, 1): 4, (3, 2): 4}      # 横对
CENTER = {(r, c) for r in range(1, 4) for c in range(1, 4)}
GOAL_SHAPE = sorted((r, c) for r in range(3) for c in range(3))


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + (f'  {detail}' if detail else ''))
    return ok


def build():
    """按文檔坐標生成等價盤面（5×5，四對捆綁圍中心）。"""
    g = SliderMatrix(M, N)
    g.apply_pattern(CELLS, GROUPS)
    g.set_goal_pattern(CELLS)
    return g


def state(g):
    """完整局面（位置 → group）；group 0 的塊位形相同即同態。"""
    return {(b.location[0], b.location[1]): b.group for b in g.blocks}


def sel_state(g):
    return {(b.location[0], b.location[1]): b.group
            for b in g.blocks if b.be_opted}


def clear(g):
    for b in g.blocks:
        b.be_opted = False


def dirs_of(gap_type):
    return ('a', 'd') if gap_type == 'h' else ('w', 's')


def shape_of(blocks):
    pts = sorted((b.location[0], b.location[1]) for b in blocks)
    mr = min(p[0] for p in pts)
    mc = min(p[1] for p in pts)
    return sorted((r - mr, c - mc) for r, c in pts)


def find_group_move():
    """找一條「選中片含非零組且同 trigger 精確可逆」的合法步。"""
    bounds = build().get_boundaries()
    for gap_type in ('h', 'v'):
        lines = (range(bounds['min_row'] + 1, bounds['max_row'])
                 if gap_type == 'h'
                 else range(bounds['min_col'] + 1, bounds['max_col']))
        for line in lines:
            for anchor in build().blocks:
                g = build()
                trig = next(b for b in g.blocks
                            if tuple(b.location) == tuple(anchor.location))
                g.opt(gap_type, line, trig)
                if not any(b.be_opted for b in g.blocks):
                    continue
                before = sel_state(g)
                if not any(before.values()):
                    clear(g)
                    continue
                final = None
                for d in dirs_of(gap_type):
                    final = g.try_move(d, STEP)
                    if final:
                        break
                if not final:
                    clear(g)
                    continue
                g.commit_move(final)
                if g_can_undo(g, gap_type, line, trig, before):
                    return g, gap_type, line, trig, before
    raise AssertionError('找不到含非零組的可逆步（典例構造有誤）')


def g_can_undo(g, gap_type, line, trig, before):
    from game import can_undo_shuffle_step
    ok = can_undo_shuffle_step(g, gap_type, line, trig, STEP,
                               dirs_of(gap_type), before)
    clear(g)
    return ok


# ----------------------------------------------------------------------
# A. 判據：位置同、group 異必須拒絕
# ----------------------------------------------------------------------
def case_a():
    g, gap_type, line, trig, before = find_group_move()
    ok_right = g_can_undo(g, gap_type, line, trig, before)
    # 同位置、不同的 group 歸屬（非零組全部錯一位；0 保持 0）
    wrong = {((r, c), (gid % 4) + 1 if gid else 0)
             for (r, c), gid in before.items()}
    ok_wrong = g_can_undo(g, gap_type, line, trig, wrong)
    # 舊口徑（只給位置）仍向後兼容
    ok_legacy = g_can_undo(g, gap_type, line, trig,
                           {pos for pos in before})
    ok = check('A1 位置+group 正確 → 可逆', ok_right,
               f'{gap_type}{line} 選中 {len(before)} 塊')
    ok &= check('A2 位置同、group 異 → 不可逆（舊寫法會放行）',
                not ok_wrong)
    ok &= check('A3 舊位置集合口徑仍兼容（實驗腳本）', ok_legacy)
    return ok


# ----------------------------------------------------------------------
# B. 端到端證書 + D. 引擎
# ----------------------------------------------------------------------
def replay_and_undo(seed, attempts=200):
    random.seed(seed)
    g = build()
    recs = []
    g.shuffle(attempts, STEP, min_score=None, record=recs)
    if not recs:
        return False, '無記錄'
    # 證書必須從**打亂前**狀態正放；shuffle 已把 g 推到終態
    g = build()

    pre_full = []
    pre_sel = []
    for k, rec in enumerate(recs):
        if rec.get('trigger') is None:
            return False, f'rec#{k} 缺 trigger'
        trig = next((b for b in g.blocks
                     if tuple(b.location) == tuple(rec['trigger'])), None)
        if trig is None:
            return False, f'rec#{k} 正向 trigger 找不到 {rec["trigger"]}'
        pre_full.append(state(g))
        g.opt(*rec['gap'], trig)
        pre_sel.append(sel_state(g))
        got = {tuple(b.location) for b in g.blocks if b.be_opted}
        if got != {tuple(p) for p in rec['moved']}:
            return False, f'rec#{k} 正向選中片不等 record.moved'
        back = g.try_move(rec['direction'], STEP)
        if not back or {tuple(p) for p in back} != \
                {tuple(p) for p in rec['final']}:
            return False, f'rec#{k} 正向落點不等 record.final'
        g.commit_move(back)
        clear(g)

    # 逆序撤銷：用 record.trigger 對應的塊（位置隨 moved/final 索引走）
    for k in range(len(recs) - 1, -1, -1):
        rec = recs[k]
        gt, line = rec['gap']
        idx = next((i for i, p in enumerate(rec['moved'])
                    if tuple(p) == tuple(rec['trigger'])), None)
        if idx is None:
            return False, f'rec#{k} trigger 不在 moved'
        trig = next((b for b in g.blocks
                     if tuple(b.location) == tuple(rec['final'][idx])), None)
        if trig is None:
            return False, f'rec#{k} 撤銷 trigger 找不到'
        g.opt(gt, line, trig)
        ok = False
        for d in dirs_of(gt):
            back = g.try_move(d, STEP)
            if not back:
                continue
            sel = [b for b in g.blocks if b.be_opted]
            back_state = {(p[0], p[1]): b.group
                          for b, p in zip(sel, back)}
            if back_state == pre_sel[k]:
                g.commit_move(back)
                ok = True
                break
        clear(g)
        if not ok:
            return False, f'rec#{k} 無位置+group 精確逆'
        if state(g) != pre_full[k]:
            return False, f'rec#{k} 撤銷後局面不精確'
    return state(g) == pre_full[0], f'{len(recs)} 步'


def case_b():
    ok = True
    for seed in range(6):
        good, detail = replay_and_undo(seed)
        ok &= check(f'B seed={seed} 證書逐條反轉（位置+group）',
                    good, detail)
    # trigger 仍是证书重放的确定性入口：每条 record 必须带，且能在
    # moved 里定位（同缝两侧各一个分量时，只靠 final 第一块会点错侧）。
    random.seed(6)
    src = build()
    recs = []
    src.shuffle(200, STEP, min_score=None, record=recs)
    bad = []
    for k, rec in enumerate(recs):
        trig = rec.get('trigger')
        if trig is None:
            bad.append(f'rec#{k} 缺 trigger')
            continue
        if not any(tuple(p) == tuple(trig) for p in rec['moved']):
            bad.append(f'rec#{k} trigger 不在 moved')
    ok &= check('B6 record 必帶 trigger 且可在 moved 定位',
                bool(recs) and not bad,
                f'{len(recs)} 步' if not bad else bad[0])
    return ok


def case_goal_no_split():
    """還原態：枚舉所有合法步，中心九塊的相對形狀必須不變。"""
    g = build()
    center = [b for b in g.blocks
              if (b.location[0], b.location[1]) in CENTER]
    bounds = g.get_boundaries()
    moves = 0
    split = []
    for gap_type in ('h', 'v'):
        lines = (range(bounds['min_row'] + 1, bounds['max_row'])
                 if gap_type == 'h'
                 else range(bounds['min_col'] + 1, bounds['max_col']))
        for line in lines:
            for anchor in g.blocks:
                g.opt(gap_type, line, anchor)
                if not any(b.be_opted for b in g.blocks):
                    continue
                for d in dirs_of(gap_type):
                    back = g.try_move(d, STEP)
                    if not back:
                        continue
                    moves += 1
                    sel = [b for b in g.blocks if b.be_opted]
                    new = {id(b): tuple(b.location) for b in center}
                    for b, p in zip(sel, back):
                        new[id(b)] = (p[0], p[1])
                    pts = sorted(new[id(b)] for b in center)
                    mr = min(p[0] for p in pts)
                    mc = min(p[1] for p in pts)
                    shape = sorted((r - mr, c - mc) for r, c in pts)
                    if shape != GOAL_SHAPE:
                        split.append((gap_type, line, d))
                clear(g)
    ok = check('C1 還原態有合法步且中心 3×3 不被切開',
               moves > 0 and not split,
               f'{moves} 步，切開 {len(split)}')
    return ok


def case_group_rigid():
    """打亂後每個捆綁組自身仍剛體（組內相對偏移不變）。"""
    random.seed(2)
    g = build()
    before = {gid: [b for b in g.blocks if b.group == gid] for gid in GROUPS.values()}
    goals = {gid: shape_of(bs) for gid, bs in before.items()}
    g.shuffle(200, STEP, min_score=None)
    return check('C2 打亂後各捆綁組仍剛體',
                 all(shape_of(bs) == goals[gid]
                     for gid, bs in before.items()))


# ----------------------------------------------------------------------
# D. 引擎通道
# ----------------------------------------------------------------------
def case_engine():
    spec = square_spec(4, 4)
    hole = (3, 3)
    blocks = tuple(Block((r, c), '', gid)
                   for r in range(4) for c in range(4)
                   if (r, c) != hole
                   for gid in [({(0, 0): 1, (0, 1): 1,
                                 (1, 1): 2, (2, 1): 2,
                                 (2, 2): 3, (2, 3): 3}.get((r, c), 0))])
    board = Board(spec, blocks)
    final, path, _undo = safe_scramble(board, STEP, 40,
                                       random.Random(11))
    ok = bool(path)
    cur = board
    for i, m in enumerate(path):
        inv = _find_inverse(cur, m, STEP)
        if inv is None:
            ok = False
            break
        nxt = cur.apply(m)
        if _exact_key(nxt.apply(inv)) != _exact_key(cur):
            ok = False
            break
        cur = nxt
    ok &= check('D1 safe_scramble 每步逆移動位置+group 精確',
                ok and cur == final, f'{len(path)} 步')
    # group 敏感：只改一顆塊的 group，精確鍵必須變
    alt = list(blocks)
    idx = next(i for i, b in enumerate(alt) if b.group == 1)
    alt[idx] = Block(alt[idx].point, alt[idx].orient, 4)
    alt = Board(spec, tuple(alt))
    ok2 = check('D2 _exact_key 對 group 敏感',
                _exact_key(alt) != _exact_key(board))
    return ok & ok2


def main():
    ok = True
    ok &= case_a()
    ok &= case_b()
    ok &= case_goal_no_split()
    ok &= case_group_rigid()
    ok &= case_engine()
    print(('[OK] §67 捆綁態打亂 group 回歸全部通過'
           if ok else '[FAILED] §67 存在失敗項'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
