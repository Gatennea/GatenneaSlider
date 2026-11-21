# -*- coding: utf-8 -*-
"""§67 补：封閉捆綁環不能被拆開（5x5test 回歸，2026-11-21）。

用戶口徑：5×5test 中心 3×3 的四對捆綁 + 中心單塊共 5 個剛體，
「打亂時必定不會散開」。這不是給該樣式加的 flag，而是由
「8 周邊格全屬捆綁組、中心格無組」的幾何 + 遊戲規則推出的封閉環；
一旦環被切開，中心塊就會漏出，自動打亂/拖動都會把局面打散。

本檔釘死：
A. `apply_pattern` 能識別且只識別出中心這個環（組號 {1,2,3,4}）。
B. 自動打亂每一步（用 record 重放）環都仍是完整 3×3。
C. 鍵盤路徑 `try_move_ex` 對會拆環的步返回 `locked_ring`。
D. 拖拽共用同一道閘：`_probe_max_cells` 不會把可拆環的步放進上限。
E. 用戶新存檔前 3 步合法、第 4 步（v2,s）被拒。
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game import SliderMatrix  # noqa: E402
from gui.drag import DragMixin  # noqa: E402

CELLS = [(r, c) for r in range(5) for c in range(5)]
GROUPS = {(1, 1): 1, (1, 2): 1,
          (1, 3): 2, (2, 3): 2,
          (3, 2): 3, (3, 3): 3,
          (2, 1): 4, (3, 1): 4}
RING_GIDS = {1, 2, 3, 4}


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + (f'  {detail}' if detail else ''))
    return ok


def build():
    g = SliderMatrix(5, 5)
    g.apply_pattern(CELLS, GROUPS)
    g.set_goal_pattern(CELLS)
    return g


def clear(g):
    for b in g.blocks:
        b.be_opted = False


def ring_solid(g):
    """8 個組塊是否正好圍住一個有無組塊的 3×3 中心。"""
    pts = {(b.location[0], b.location[1])
           for b in g.blocks if b.group in RING_GIDS}
    if len(pts) != 8:
        return False, f'ring {len(pts)}'
    r0 = min(p[0] for p in pts)
    c0 = min(p[1] for p in pts)
    r1 = max(p[0] for p in pts)
    c1 = max(p[1] for p in pts)
    if (r1 - r0, c1 - c0) != (2, 2):
        return False, f'bbox {(r1 - r0, c1 - c0)}'
    center = (r0 + 1, c0 + 1)
    expected = {(r, c) for r in (r0, r0 + 1, r0 + 2)
                for c in (c0, c0 + 1, c0 + 2)} - {center}
    if pts != expected:
        return False, 'perimeter'
    at_center = [b for b in g.blocks
                 if (b.location[0], b.location[1]) == center]
    if len(at_center) != 1 or at_center[0].group != 0:
        return False, 'center-free'
    return True, ''


def apply_opt_move(g, gt, line, anchor, direction, step):
    trig = next(b for b in g.blocks
                if tuple(b.location) == tuple(anchor))
    g.opt(gt, line, trig)
    res, reason = g.try_move_ex(direction, step)
    if res:
        g.commit_move(res)
    clear(g)
    return res, reason


def case_locks():
    g = build()
    ok = check('A 只識別出中心封閉環 {1,2,3,4}',
               g.locked_rings == (frozenset(RING_GIDS),),
               f'{g.locked_rings}')
    # 讀檔/歷史快照走 set_groups_from_positions；組歸屬變了鎖也必須重算
    g.set_groups_from_positions({})
    ok &= check('A2 清空組 → 鎖定環同步清空', g.locked_rings == (),
                f'{g.locked_rings}')
    g.set_groups_from_positions(GROUPS)
    ok &= check('A3 灌回組 → 鎖定環同步恢復',
                g.locked_rings == (frozenset(RING_GIDS),),
                f'{g.locked_rings}')
    return ok


def case_shuffle_keeps_ring():
    ok = True
    for seed in range(4):
        random.seed(seed)
        src = build()
        recs = []
        src.shuffle(60, 1, min_score=None, record=recs)
        g = build()
        bad = None
        for k, rec in enumerate(recs):
            trig = next((b for b in g.blocks
                         if tuple(b.location) == tuple(rec['trigger'])),
                        None)
            g.opt(*rec['gap'], trig)
            res, _reason = g.try_move_ex(rec['direction'], 1)
            if not res:
                bad = f'rec#{k} 重放被拒'
                break
            g.commit_move(res)
            clear(g)
            solid, why = ring_solid(g)
            if not solid:
                bad = f'rec#{k} {why}'
                break
        ok &= check(f'B seed={seed} 打亂逐步不拆環',
                    bool(recs) and bad is None,
                    f'{len(recs)} 步' if bad is None else bad)
    return ok


def case_save_step4():
    g = build()
    ok = True
    for label, gt, line, anchor, d, step in (
            ('1 h0,d4', 'h', 0, (0, 0), 'd', 4),
            ('2 v3,s1', 'v', 3, (2, 0), 's', 1),
            ('3 h4,d4', 'h', 4, (5, 0), 'd', 4)):
        res, reason = apply_opt_move(g, gt, line, anchor, d, step)
        ok &= check(f'E {label} 仍合法', bool(res) and not reason,
                    reason or f'{len(res)} 塊')
    res, reason = apply_opt_move(g, 'v', 2, (0, 4), 's', 1)
    ok &= check('E 第4步 v2,s1 被 locked_ring 拒', not res
                and reason == 'locked_ring', reason)
    return ok


def case_drag_gate():
    g = build()
    for gt, line, anchor, d, step in (
            ('h', 0, (0, 0), 'd', 4),
            ('v', 3, (2, 0), 's', 1),
            ('h', 4, (5, 0), 'd', 4)):
        apply_opt_move(g, gt, line, anchor, d, step)
    # 重新选中第 4 步会拆环的那一片，拖拽探针必须停在 0
    trig = next(b for b in g.blocks if tuple(b.location) == (0, 4))
    g.opt('v', 2, trig)

    class _Fake:
        current_step = 1

    fake = _Fake()
    fake.game = g
    max_cells = DragMixin._probe_max_cells(fake, 's')
    clear(g)
    return check('D 拖拽 _probe_max_cells 對拆環步停在 0',
                 max_cells == 0, f'max={max_cells}')


def case_control_without_lock():
    """对照组：同一局面关掉环锁 → 第 4 步真的会拆环、拖拽上限真的 >0。

    没有这一组，D/E 只证明「拒绝」，证明不了拒绝是环锁而不是别的理由。
    """
    g = build()
    for gt, line, anchor, d, step in (
            ('h', 0, (0, 0), 'd', 4),
            ('v', 3, (2, 0), 's', 1),
            ('h', 4, (5, 0), 'd', 4)):
        apply_opt_move(g, gt, line, anchor, d, step)
    g.locked_rings = ()
    res, reason = apply_opt_move(g, 'v', 2, (0, 4), 's', 1)
    ok = check('F 關鎖對照：第4步被接受且環被拆開',
               bool(res) and not reason and not ring_solid(g)[0],
               reason or f'{len(res)} 塊')
    # 同一局面回滾重建後，關鎖時拖拽探針應 >0
    h = build()
    for gt, line, anchor, d, step in (
            ('h', 0, (0, 0), 'd', 4),
            ('v', 3, (2, 0), 's', 1),
            ('h', 4, (5, 0), 'd', 4)):
        apply_opt_move(h, gt, line, anchor, d, step)
    h.locked_rings = ()
    trig = next(b for b in h.blocks if tuple(b.location) == (0, 4))
    h.opt('v', 2, trig)

    class _Fake2:
        current_step = 1

    fake = _Fake2()
    fake.game = h
    mv = DragMixin._probe_max_cells(fake, 's')
    clear(h)
    ok &= check('F 關鎖對照：拖拽探針 >0', mv > 0, f'max={mv}')
    return ok


def main():
    ok = True
    ok &= case_locks()
    ok &= case_shuffle_keeps_ring()
    ok &= case_save_step4()
    ok &= case_drag_gate()
    ok &= case_control_without_lock()
    print(('[OK] §67 封閉捆綁環回歸全部通過'
           if ok else '[FAILED] §67 封閉捆綁環存在失敗項'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
