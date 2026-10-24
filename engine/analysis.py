# -*- coding: utf-8 -*-
"""规则检查（analysis）——引擎对「这谜题能不能玩」的自检层。

回答用户方向里的核心诉求：**定义新谜题时，引擎先回答三个问题**——
  1. 有没有锁死的缝？（米字双重晶格错位态下横竖缝整条穿过块内部，
     就是这类；判据挂在板型的 seam_clear 钩子上）
  2. 会不会冻形？（一个合法移动都没有，保存前必须拦截）
  3. 能不能打乱？（从还原态出发的可达形状太少 = 这规则打不开；
     以及可逆打乱——每步可逆 ⟺ 整条路径反转即解法，终态保证有解）

全部纯逻辑零 pygame；复杂度说明见各函数 docstring（P1 再做位棋盘化）。
"""

from .board import Board, Move, _add, _dot  # noqa: F401  （_dot 供本模块复用）


def locked_seams(board: Board):
    """列出被几何锁死的缝（seam_clear 返回 False 的缝实例）。

    返回 [{'family': 族名, 't': 缝位置, 'reason': 原因}]。
    板型没有 seam_clear 钩子时返回 []（该板型不存在锁死缝概念）。
    缝坐标走 ``SeamFamily.rank_of(point, orient)``（P2 硬骨 9：米字
    四族的 rank 带朝向修正，点部线性泛函只够方形/立方）。
    """
    spec = board.spec
    if spec.seam_clear is None:
        return []
    out = []
    for fam in spec.seam_families:
        vals = [fam.rank_of(b.point, b.orient) for b in board.blocks]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        for t in range(lo + 1, hi + 1):
            if not spec.seam_clear(fam, t, board):
                out.append({'family': fam.name, 't': t,
                            'reason': 'seam_clear'})
    return out


def frozen(board: Board, step: int) -> bool:
    """冻形：一个合法移动都没有（保存/开局前必须拦截）。"""
    return not board.legal_moves(step)


def shape_reachability(board: Board, step: int, cap: int = 20000,
                       target_key=None) -> dict:
    """从 board 出发、按规范形归并的可达形状数（BFS）。

    用途 = 「能否打乱」的静态探针：可达形状太少说明这规则/这形态
    打不开（比如冻形附近、或规则过紧）。cap 封顶防爆。
    target_key 非 None 时顺带回答「target 的可达性」（用于实证
    「可逆打乱的终态确实有解」）；**capped=True 时 count 与
    target_reachable 都只是「未搜完」的下界，不可解读为不可达**；
    找到 target 后立即收尾（count 随之定格）。
    返回 {'count': int, 'capped': bool,
          'target_reachable': bool|None（未给 target 时为 None）}。
    """
    start = board.canonical_key()
    seen = {start}
    frontier = [board]
    capped = False
    found = (start == target_key) if target_key is not None else None
    while frontier and not capped and found is not True:
        nxt = []
        for b in frontier:
            for m in b.legal_moves(step):
                nb = b.apply(m)
                k = nb.canonical_key()
                if k not in seen:
                    seen.add(k)
                    nxt.append(nb)
                    if target_key is not None and k == target_key:
                        found = True
                    if len(seen) >= cap:
                        capped = True
                        break
            if capped or found is True:
                break
        frontier = nxt
    return {'count': len(seen), 'capped': capped,
            'target_reachable': found}


def _find_inverse(board: Board, move, step: int):
    """找 move 的逆移动：走完这步后，**精确回到走前局面**的那个合法移动。

    与 game.can_undo_shuffle_step（2026-10-18 安全打乱）同标准——绝对
    坐标集合精确相等，不是规范形相等。

    判定走 ``Board.move_ok``：逆移动选中片 = 原选中片沿 move.direction 平移
    一步的落点，沿相反方向推回。它本来就是走前那一次合法点击的产物（同缝、
    同侧、同一连通分量——平移平行于缝、rank 不变，落点仍整片落在与原移动
    相同的缝侧）；``move_ok`` 既校验「推得动、不断开、不撞锁死缝」，又要求
    「选中片在 nxt 上是缝某一侧的连通分量闭包（极大分量）」——这后一道正是
    适配器 opt / GUI 点击的语义（opt 只选极大分量）：少了它，逆移动落点并到
    同侧邻块（刚性并拢）或并到更大分量（swing 式滑动）时，适配器只会把那
    更大片当作选中片，重放偏离引擎 apply。旧实现遍历 nxt.legal_moves 取
    apply==board 的 move，本质也是取「极大分量」那条；这里走 move_ok 直接
    验，避免 O(步数²) 整树枚举（引擎性能铁律「不许拿 legal_moves 判成员」）。

    找到返回逆 Move，找不到（逆移动不是 nxt 上的合法极大分量，或推不动）
    返回 None——与旧语义一致：那种步不会被 safe_scramble 选中，终态仍由
    其它可逆步保证有解（swing 谜题逆移动本就不必都是极大分量）。
    """
    nxt = board.apply(move)
    d = move.direction
    opp = tuple(-x for x in d)
    moved_nxt = tuple(sorted((_add(p, d), o) for (p, o) in move.moved))
    inv = Move(move.family, move.t, move.side, opp, step, moved_nxt)
    # move_ok 权威校验：逆移动在 nxt 上是合法极大分量且推得动 ⟺ 它是游戏
    # 可执行的精确逆移动（保证 safe_scramble 产出的撤销路径逐条反转后真能
    # 由游戏/适配器按「点击极大分量」的语义重放）。
    if not nxt.move_ok(inv):
        return None
    return inv


def safe_scramble(board: Board, step: int, attempts: int, rng,
                  record: list = None):
    """可逆打乱：每步只走「存在合法移动能精确回到移动前」的走法。

    于是记录下来的撤销路径逐条反转、就是一条**字面意义的合法解法**
    （每步都精确可逆，不靠规范形近似）。终态保证有解：指示 / 自动
    求解 / 关卡生成永远有答案，也撞不上死局（死局态不可逆可达）。
    与 game 安全打乱的差异仅在于候选范围更宽（见 _find_inverse）。

    返回 (终态 Board, 前进路径 tuple[Move], 撤销路径 tuple[Move])；
    record 非 None 时把前进路径追加进去。
    """
    cur = board
    path = []
    undo_path = []
    for _ in range(attempts):
        cands = []
        for m in cur.legal_moves(step):
            inv = _find_inverse(cur, m, step)
            if inv is not None:
                cands.append((m, inv))
        if not cands:
            break  # 锁死/冻形：没有可逆走法可走
        m, inv = rng.choice(cands)
        path.append(m)
        undo_path.append(inv)
        cur = cur.apply(m)
    if record is not None:
        record.extend(path)
    return cur, tuple(path), tuple(undo_path)


def verify_path(board: Board, path) -> Board:
    """按路径顺序重放（用于校验 safe_scramble 的路径确实导向终态）。"""
    cur = board
    for m in path:
        cur = cur.apply(m)
    return cur
