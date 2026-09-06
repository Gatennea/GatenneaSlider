# -*- coding: utf-8 -*-
r"""
填洞宏（fill_macro）「死代码」— game 引擎版（无搜索、无 AI）

单洞：A-B-A' 共轭子宏一次整盘还原。
多洞无缺口：贪心驱动逐 couple（洞, 同 mod 凸起）调用单洞填洞，
成功一次重扫、全败停机（部分多洞局面为算法固有缺陷，会失败）。

复用游戏本体宏机制：
    · 每步动作 = 沿缝切、选侧、点一个「目标块」→ game.opt 扩散为同侧连通
      分量 → try_move 验证 step 步 → commit_move。与 GUI 宏执行同一语义。
    · setup/A/B 阶段点「凸起 p」为目标块（= 人类录制时点击凸起）；
      A' 阶段复用「逆序宏」：A 动作逆序重放（同缝同侧、方向取反），目标块
      取该侧首块（与 GUI 逆序播放一致）。
    · 窗口固定、凸起坐标跟踪、B 终止 = p 与洞 h 重合。

运行：
    D:\python\python.exe -m solver.ml.fill_macro --sample
    D:\python\python.exe -m solver.ml.fill_macro --gen 6 6 2 40 5        # 单洞量产
    D:\python\python.exe -m solver.ml.fill_macro --genmulti 5 5 2 3 30 5 # 多洞无缺口量产
"""
import json
import os
import random
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from solver.ml.gather_solver import find_best_window  # noqa: E402
from solver.ml import view_rotate  # noqa: E402

_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
_INV = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------
def build_game(coords, m, n):
    from game import Block, SliderMatrix
    g = SliderMatrix(m, n)
    g.m, g.n = m, n
    g.blocks = [Block([r, c]) for r, c in sorted(coords)]
    g.matrix = None
    g.update_matrix()
    return g


def gcoords(g):
    return frozenset(tuple(b.location) for b in g.blocks)


def solved_game(g):
    return g.is_solved()


def window_of(coords, m, n, step):
    """→ ((r0,c0,(rh,cw)), overlap, holes, outside)"""
    r0, c0, (rh, cw), ov = find_best_window(coords, m, n, step)
    inside = {(r, c) for r in range(r0, r0 + rh)
              for c in range(c0, c0 + cw)}
    return (r0, c0, (rh, cw)), ov, inside - coords, coords - inside


# ---------------------------------------------------------------------------
# 单洞宏
# ---------------------------------------------------------------------------
class _Runner:
    """在一局 SliderMatrix 上执行共轭子宏，与 GUI 宏同语义。

    h / p 缺省时按「单洞单凸」自检推导；多洞无缺口场景由调用方显式喂入
    (h, p)（本局坐标系），此时 require_solved=False：成功 = 目标洞格被填，
    不要求整盘还原（驱动层会在整体上继续填其余洞）。
    """

    def __init__(self, game, m, n, step, verbose=False, keep_partial=False,
                 h=None, p=None, require_solved=True):
        self.g = game
        self.m, self.n, self.step = m, n, step
        self.verbose = verbose
        self.keep_partial = keep_partial
        self.require_solved = require_solved
        self.acts = []                 # 已执行动作 (gap,line,side,dir,rep)
        if h is not None and p is not None:
            self.h, self.p = tuple(h), tuple(p)   # 调用方已保证同 mod
            return
        coords = gcoords(game)
        (self.r0, self.c0, _wh), _ov, holes, outside = window_of(
            coords, m, n, step)
        assert len(holes) == 1 and len(outside) == 1, '非单洞单凸起'
        self.h = tuple(next(iter(holes)))
        self.p = tuple(next(iter(outside)))
        if ((self.h[0] - self.p[0]) % step or
                (self.h[1] - self.p[1]) % step):
            raise ValueError('洞凸不同mod')

    def _bail(self, info):
        """失败出口：keep_partial=True 且有动作时返回已执行部分供观察。"""
        info = dict(info)
        if self.keep_partial and self.acts:
            return list(self.acts), dict(info, partial=True, solved=False)
        return None, info

    def _block_at(self, pos):
        for b in self.g.blocks:
            if tuple(b.location) == pos:
                return b
        return None

    def _side_first_block(self, gap, line, side):
        for b in self.g.blocks:
            r, c = b.location
            if gap == 'h':
                if side == 'above' and r <= line:
                    return b
                if side == 'below' and r > line:
                    return b
            else:
                if side == 'left' and c <= line:
                    return b
                if side == 'right' and c > line:
                    return b
        return None

    def _do(self, gap, line, side, d, target_pos=None, require_p=False):
        """执行一步（选择目标块 → opt → try_move → commit）。
        target_pos=None 时取该侧首块（= GUI 逆序播放语义）。
        require_p=True 时目标必须是凸起 p（= 人类录制点击凸起）。
        """
        from game import Block
        g = self.g
        bounds = g.get_boundaries()
        if gap == 'h' and not (bounds['min_row'] <= line < bounds['max_row']):
            return False
        if gap == 'v' and not (bounds['min_col'] <= line < bounds['max_col']):
            return False
        if require_p:
            tgt = self._block_at(self.p)
        elif target_pos is not None:
            tgt = self._block_at(target_pos)
        else:
            tgt = self._side_first_block(gap, line, side)
        if tgt is None:
            return False
        g.opt(gap, line, tgt)
        pre_sel = {tuple(b.location) for b in g.blocks if b.be_opted}
        if require_p and self.p not in pre_sel:
            for b in g.blocks:
                b.be_opted = False
            return False
        final = g.try_move(d, self.step)
        if not final:
            for b in g.blocks:
                b.be_opted = False
            return False
        rep_pre = tuple(tgt.location)   # 移动前位置（commit 会改动 location）
        g.commit_move(final)
        dr, dc = _DIRS[d]
        self.p = (self.p[0] + dr * self.step, self.p[1] + dc * self.step)
        # 记录动作 + 该步移动分量的代表格（移动前位置，供精确回放）
        self.acts.append((gap, line, side, d, rep_pre))
        if self.verbose:
            print('    (%s,%d,%s,%s) p=%s' % (gap, line, side, d,
                                              tuple(self.p)))
        return True

    def _acands(self, want):
        """A 段候选：洞边缝，凸起所在侧（人类式整带）。"""
        hr, _hc = self.h
        if self.p[0] > hr:
            return [('h', hr, 'below', want), ('h', hr - 1, 'above', want)]
        if self.p[0] < hr:
            return [('h', hr - 1, 'above', want), ('h', hr, 'below', want)]
        r, c = self.p
        return [('h', r, 'above', want), ('h', r - 1, 'below', want)]

    def _v_cands(self, want):
        """B/setup 候选：竖直推动凸起。

        顺序即优先级：先选「凸起与窗口主体之间的缝、凸起所在侧」——该侧
        通常只含凸起本身（或它那一窄列），保证 B 只推动凸起、不连带把 A 的
        带拖走；两候选都动不了才轮到跨整带。
        """
        _r, c = self.p
        return [('v', c - 1, 'right', want), ('v', c, 'left', want)]

    def _h_cands(self, want):
        r, c = self.p
        return [('h', r, 'above', want), ('h', r - 1, 'below', want)]

    def run(self):
        """返回 (actions, stats) 或 (None, {reason...})。"""
        t0 = time.time()
        # ---- setup：同行错开 ----
        if self.p[0] == self.h[0]:
            done = False
            for d in ('s', 'w'):
                for c in self._v_cands(d):
                    if self._do(*c, require_p=True):
                        done = True
                        break
                if done:
                    break
            if not done:
                return self._bail({'reason': '同行上下均不可动'})

        # ---- A 段：把凸起送到洞列（每次移动含凸起的带）----
        a_acts = []
        a_moves = 0
        while self.p[1] != self.h[1]:
            want = 'a' if self.p[1] > self.h[1] else 'd'
            done = None
            for c in self._acands(want):
                if self._do(*c, require_p=True):
                    a_acts.append(c)
                    done = c
                    break
            if done is None:
                return self._bail({'reason': 'A段受阻(需双层)', 'p': self.p,
                                   'h': self.h, 'moves': len(self.acts)})
            a_moves += 1
            if a_moves > 200:
                return self._bail({'reason': 'A段超限', 'p': self.p,
                                   'moves': len(self.acts)})

        # ---- B 段：竖直把凸起推进洞，直到重合 ----
        b_moves = 0
        while not (self.p[0] == self.h[0] and self.p[1] == self.h[1]):
            want = 'w' if self.p[0] > self.h[0] else 's'
            done = False
            for c in self._v_cands(want):
                if self._do(*c, require_p=True):
                    done = True
                    break
            if not done:
                return self._bail({'reason': 'B段撞停且洞未填(需双层)',
                                   'p': self.p, 'h': self.h,
                                   'moves': len(self.acts)})
            b_moves += 1
            if b_moves > 200:
                return self._bail({'reason': 'B段超限', 'p': self.p,
                                   'moves': len(self.acts)})

        if solved_game(self.g):
            return self.acts, {'steps': len(self.acts),
                               'secs': round(time.time() - t0, 3)}

        # ---- A' 段：A 逆序宏（同缝同侧、方向取反、目标取侧首块）----
        for gap, line, side, d in reversed(a_acts):
            if not self._do(gap, line, side, _INV[d]):
                break
            if self.require_solved and solved_game(self.g):
                break
        if self.require_solved:
            if solved_game(self.g):
                return self.acts, {'steps': len(self.acts),
                                   'secs': round(time.time() - t0, 3)}
            return self._bail({'reason': 'A′逆序宏后未还原(需细化)',
                               'p': self.p, 'h': self.h,
                               'moves': len(self.acts)})
        # target 模式（多洞喂 couple）：成功 = 目标洞格 h 已被填上
        if self._block_at(self.h) is not None:
            return self.acts, {'steps': len(self.acts),
                               'secs': round(time.time() - t0, 3)}
        return self._bail({'reason': 'couple未填中目标洞(多洞干扰/需双层)',
                           'p': self.p, 'h': self.h,
                           'moves': len(self.acts)})


def solve_single_void(coords, m, n, step, hole=None, anchor=None,
                      verbose=False, max_moves=200, keep_partial=False,
                      force_rot=None):
    """确定性「填一个洞」宏（视图旋转归一化版）。

    两种调用语义：
    · 不带 hole/anchor（单洞局面）：整盘求解，成功 = 全盘还原。
    · 带 hole/anchor（couple 模式，供多洞无缺口驱动层逐对喂入）：本函数
      把「该凸起填进该洞」的动作旋出；产物原样交还（可能整段成功、也可能
      keep_partial 的部分推进），是否「有成果」由调用方按回放后聚拢度验收。
      失败不产生任何副作用。

    返回 (actions, stats)；actions=None 表示失败。
    keep_partial=True：规则中断但已执行合法动作时返回 (部分actions, stats)，
    stats['partial']=True、stats['reason'] 为中断原因，供观察断点。
    """
    coords = frozenset(coords)
    if len(coords) != m * n:
        return None, {'error': f'格数 {len(coords)} != {m * n}'}
    g = build_game(coords, m, n)
    if g.is_solved():
        return [], {'steps': 0, 'secs': 0.0}
    couple = hole is not None and anchor is not None
    try:
        # 定位窗口与洞/凸起（世界坐标）
        (r0, c0, _wh), _ov, holes, outside = window_of(coords, m, n, step)
        if couple:
            h_w, p_w = tuple(hole), tuple(anchor)
            if h_w not in holes or p_w not in outside:
                return None, {'reason': 'couple坐标不是窗内空位/窗外凸起'}
        else:
            assert len(holes) == 1 and len(outside) == 1, '非单洞单凸起'
            h_w = tuple(next(iter(holes)))
            p_w = tuple(next(iter(outside)))
        if ((h_w[0] - p_w[0]) % step or (h_w[1] - p_w[1]) % step):
            raise ValueError('洞凸不同mod')

        name = force_rot or view_rotate.choose_rot(
            p_w[0] - r0, p_w[1] - c0, m, n)
        if name == 'id':
            # 世界坐标即 runner 坐标（窗口平移不影响宏）；直接在原局上跑
            acts, stats = _Runner(g, m, n, step, verbose,
                                  keep_partial=keep_partial,
                                  h=h_w, p=p_w,
                                  require_solved=not couple).run()
            if acts is None:
                return None, stats
            return acts, stats

        # 旋转到「凸起在右侧」再求解；洞/凸起同样旋入 view 坐标喂给 runner
        vc = frozenset(view_rotate.rotate_xy(name, r - r0, c - c0, m, n)
                       for r, c in coords)
        mv, nv = view_rotate.view_dims(name, m, n)
        vg = build_game(vc, mv, nv)
        vh = view_rotate.rotate_xy(name, h_w[0] - r0, h_w[1] - c0, m, n)
        vp = view_rotate.rotate_xy(name, p_w[0] - r0, p_w[1] - c0, m, n)
        acts, stats = _Runner(vg, mv, nv, step, verbose,
                              keep_partial=keep_partial,
                              h=vh, p=vp,
                              require_solved=not couple).run()
        if acts is None:
            stats = dict(stats, rot=name)
            return None, stats

        # 逆旋转：view 动作 → origin 空间 → 平移回世界绝对坐标
        wacts = []
        for gap, line, side, d, rep in acts:
            gap2, line2, side2, d2 = view_rotate.act_to_world(
                name, gap, line, side, d, m, n)
            if gap2 == 'h':
                line2 = line2 + r0
            else:
                line2 = line2 + c0
            rr, cc = view_rotate.rep_to_world(name, rep[0], rep[1], m, n)
            wacts.append((gap2, line2, side2, d2, (rr + r0, cc + c0)))

        if couple:
            # 是否「有成果」由调用方（多洞驱动 / 整形扫描）按聚拢度验收；
            # 这里原样交还 macro 产物（含 keep_partial 的部分推进与停点 reason）。
            return wacts, dict(stats, rot=name)
        # 单洞（非 couple）
        if stats.get('partial'):
            return wacts, dict(stats, rot=name)
        if not replay_and_verify(coords, m, n, step, wacts):
            return None, {'reason': f'逆映射回放未还原(rot={name})',
                          'rot': name}
        return wacts, dict(stats, rot=name)
    except ValueError as e:
        return None, {'reason': str(e)}


def _couple_scan_state(coords, m, n, step, rng):
    """当前状态遍历全部 couple，返回首个能提升聚拢度的动作片段（含 partial 有成果）。"""
    _reg, _ov, holes, outside = window_of(coords, m, n, step)
    h_list = list(holes)
    rng.shuffle(h_list)
    for h in h_list:
        cands = [p for p in outside
                 if (p[0] - h[0]) % step == 0 and (p[1] - h[1]) % step == 0]
        rng.shuffle(cands)
        for p in cands:
            acts, _s = solve_single_void(coords, m, n, step, hole=h,
                                         anchor=p, keep_partial=True)
            # 此处替 solve_single_void 把关聚拢度：只认「回放后窗口方块数提升」
            if acts is not None and _overlap_raised(coords, m, n, step, acts):
                return acts
    return None


def _nondrop_moves(coords, m, n, step, ov0):
    """所有「最佳窗口方块数不下降」的单步动作 → [(action, 新局面)]。

    0 增益（=ov0）留给下一步整形；提升（>ov0）的是可直接收下的成果。
    """
    from solver.actions import enumerate_valid_actions, apply_action
    g = build_game(coords, m, n)
    out = []
    for act in enumerate_valid_actions(g, step):
        g2 = build_game(coords, m, n)
        if not apply_action(g2, act, step):
            continue
        s2 = frozenset(gcoords(g2))
        if window_of(s2, m, n, step)[1] >= ov0:
            out.append((act, s2))
    return out


def _shaping_progress(coords, m, n, step, rng, ov0, max_shaping=2,
                      max_nodes=150):
    """有限中性整形预演：≤max_shaping 步「不降聚拢度」动作后收成果。

    couple 宏的最小原子是「一次完整 A-B-A′」；有些卡点要先花 0 增益的整带
    步（揉形）把洞/凸起摆到可直接填的几何，宏才肯动。这里在 couple 全败时
    提供 ≤k 步不降聚拢度的整形路径：路径终点只要 ① 聚拢度提升，或
    ② 整形后的新状态有 couple 能填 → 就回传完整动作序列。

    返回动作列表或 None（确定性、有节点上限，不是求解搜索）。
    """
    from collections import deque
    root = frozenset(coords)
    frontier = deque([(root, [])])
    seen = {root}
    nodes = 0
    for _depth in range(max_shaping):
        nxt = deque()
        while frontier:
            s, prefix = frontier.popleft()
            if window_of(s, m, n, step)[1] > ov0:
                return prefix            # 纯整形已提升（窗口重定位）
            cacts = _couple_scan_state(s, m, n, step, rng)
            if cacts is not None:
                return prefix + cacts    # 整形后解锁 couple
            for act, s2 in _nondrop_moves(s, m, n, step, ov0):
                if window_of(s2, m, n, step)[1] > ov0:
                    return prefix + [act]   # 单步已提升
                if s2 in seen:
                    continue
                seen.add(s2)
                nodes += 1
                if nodes > max_nodes:
                    return None
                nxt.append((s2, prefix + [act]))
        frontier = nxt
    return None


def solve_multi_void(coords, m, n, step, verbose=False, max_rounds=80,
                     max_attempts=400, max_shaping=2, max_nodes=150,
                     rng=None):
    """多洞无缺口贪心驱动（确定性死代码，无求解搜索）。

    流程：
        1. 取当前窗口内一个洞 h，随机找同 mod 的窗外凸起 p → 一个 couple；
        2. 调 solve_single_void(couple, keep_partial=True) 尝试：
           · 完全失败 → 无副作用换组；
           · 有成果（提升聚拢度但未必还原，partial 也算）→ 接受、推进；
        3. 一轮 couple 全败时，做有限中性整形预演（≤max_shaping 步不降
           聚拢度的整带动作后再试 couple / 直接提升）——覆盖「需先揉形再填」
           的卡点（例如 2-7-7-test 残局）；
        4. 整形也全败 → 停机（算法固有缺陷）。

    每步接受都保证窗内方块数单调提升，故轮数有上界。

    返回 (actions, stats)：
    · 还原成功 → actions 全量；
    · 有成果的失败 → actions=已提升片段，stats['partial']=True；
    · 完全失败（全程零提升）→ actions=None，stats['reason'] 说明。
    """
    coords = frozenset(coords)
    if len(coords) != m * n:
        return None, {'error': f'格数 {len(coords)} != {m * n}'}
    rng = rng or random.Random()
    g = build_game(coords, m, n)
    if g.is_solved():
        return [], {'steps': 0, 'secs': 0.0, 'multi': True, 'rounds': 0}
    t0 = time.time()
    total = []
    rounds = 0
    attempts = 0
    partial_accepted = 0
    shaping_used = 0

    def _stop(extra):
        """停机出口：有成果(total 非空) → 回传 partial；完全失败 → None。"""
        if total:
            return list(total), dict(extra, partial=True)
        return None, dict(extra)

    while not g.is_solved():
        rounds += 1
        if rounds > max_rounds:
            return _stop({'reason': '多洞停机：超过最大轮数',
                          'rounds': rounds, 'steps': len(total)})
        cur = gcoords(g)
        _reg, _ov, holes, outside = window_of(cur, m, n, step)
        if not holes:
            break  # 窗内无空位但仍未还原 → 非多洞无缺口形态，交给停机判定
        if attempts > max_attempts:
            return _stop({'reason': '多洞停机：尝试数超限',
                          'rounds': rounds, 'attempts': attempts,
                          'holes_left': len(holes),
                          'steps': len(total)})
        # 遍历 couple：洞序随机，同 mod 凸起随机序（=「随机找一组」的展开）
        h_list = list(holes)
        rng.shuffle(h_list)
        progressed = False
        for h in h_list:
            cands = [p for p in outside
                     if (p[0] - h[0]) % step == 0 and (p[1] - h[1]) % step == 0]
            rng.shuffle(cands)
            for p in cands:
                attempts += 1
                acts, stats = solve_single_void(cur, m, n, step,
                                                hole=h, anchor=p,
                                                keep_partial=True)
                if acts is None:
                    continue   # 该 couple 完全失败（macro 一步未动）
                # 聚拢度闸门：只接受「回放后最佳窗口方块数提升」的产物
                # （含 partial 有成果）；未提升视为无成果失败，无副作用换组
                if not _overlap_raised(cur, m, n, step, acts):
                    continue
                # 有成果（完整填洞或 partial 提升都算）：推进到活盘
                if not _replay_apply(g, acts, m, n, step):
                    return _stop({'reason': '多洞停机：推进活盘失败',
                                  'rounds': rounds,
                                  'steps': len(total)})
                total.extend(acts)
                progressed = True
                if stats.get('partial'):
                    partial_accepted += 1
                    if verbose:
                        print('   round%d 有成果partial(%s) h=%s p=%s → %d 步'
                              % (rounds, stats.get('reason', '?'), h, p,
                                 len(acts)))
                elif verbose:
                    print('   round%d 填洞 %s 用凸起 %s → %d 步'
                          % (rounds, h, p, len(acts)))
                break
            if progressed:
                break
        if not progressed and max_shaping:
            # couple 全败 → 有限中性整形预演：≤max_shaping 步不降聚拢度的
            # 整带动作后直接提升 / 解锁 couple（覆盖「需先揉形再填」卡点）
            plan = _shaping_progress(cur, m, n, step, rng, _ov,
                                     max_shaping, max_nodes)
            if plan is not None:
                if not _replay_apply(g, plan, m, n, step):
                    return _stop({'reason': '多洞停机：整形预演推进活盘失败',
                                  'rounds': rounds,
                                  'steps': len(total)})
                total.extend(plan)
                shaping_used += 1
                progressed = True
                if verbose:
                    print('   round%d 中性整形预演(%d步) → 收下'
                          % (rounds, len(plan)))
        if not progressed:
            return _stop({'reason': '多洞停机：所有couple与≤%d步整形预演均无成果'
                                    '(算法固有缺陷)' % max_shaping,
                          'rounds': rounds, 'attempts': attempts,
                          'holes_left': len(holes),
                          'outside_left': len(outside),
                          'steps': len(total)})
    if not g.is_solved():
        return _stop({'reason': '多洞停机：窗内无洞但未还原(含缺口形态?)',
                      'rounds': rounds, 'steps': len(total)})
    return (total, {'steps': len(total), 'rounds': rounds,
                    'partial_accepted': partial_accepted,
                    'shaping_used': shaping_used,
                    'secs': round(time.time() - t0, 3), 'multi': True})


# ---------------------------------------------------------------------------
# GUI 求解器入口（与 SOLVER_ALGORITHMS 统一签名）
# ---------------------------------------------------------------------------
def solve_fill_macro(game, step, cancel_check=None, progress_callback=None,
                     **kwargs):
    """填洞宏求解（GUI 入口）。

    单洞单凸局面 → 单洞整盘求解（keep_partial 观察断点）；
    多洞/多空位局面 → solve_multi_void 贪心驱动（逐 couple 填，全败停机）。

    返回 (actions, rep_cells)（actions 为四元组列表）供 GUI 宏播放；
    失败返回 {'type': 'fill_fail', 'reason': str}。
    """
    coords = frozenset(tuple(b.location) for b in game.blocks)
    m, n = game.m, game.n
    _region, _ov, holes, outside = window_of(coords, m, n, step)
    if len(holes) == 1 and len(outside) == 1:
        acts, stats = solve_single_void(coords, m, n, step, keep_partial=True)
        if acts is None:
            reason = stats.get('reason', stats.get('error', '未知'))
            print('[填洞宏] 单洞无解：%s' % reason)
            return {'type': 'fill_fail', 'reason': reason}
        if stats.get('partial'):
            reason = stats.get('reason', '中断')
            print('[填洞宏] 单洞部分(断在：%s)，已播放 %d 步供观察'
                  % (reason, len(acts)))
            return {'type': 'fill_partial', 'actions': [a[:4] for a in acts],
                    'rep_cells': [a[4] for a in acts], 'reason': reason}
        return ([a[:4] for a in acts], [a[4] for a in acts])
    if not holes:
        return [], []   # 已还原
    acts, stats = solve_multi_void(coords, m, n, step)
    if acts is None:
        reason = stats.get('reason', stats.get('error', '未知'))
        print('[填洞宏] 多洞完全失败：%s' % reason)
        return {'type': 'fill_fail', 'reason': reason,
                'stats': {k: v for k, v in stats.items() if k != 'reason'}}
    if stats.get('partial'):
        reason = stats.get('reason', '中断')
        print('[填洞宏] 多洞有成果停机(断在：%s)，已播放 %d 步（保留提升）'
              % (reason, len(acts)))
        return {'type': 'fill_partial', 'actions': [a[:4] for a in acts],
                'rep_cells': [a[4] for a in acts], 'reason': reason,
                'stats': {k: v for k, v in stats.items()
                          if k not in ('reason', 'partial')}}
    print('[填洞宏] 多洞还原：%d 步 / %d 轮' % (len(acts),
                                             stats.get('rounds', '?')))
    return ([a[:4] for a in acts], [a[4] for a in acts])


# ---------------------------------------------------------------------------
# 数据源 / CLI
# ---------------------------------------------------------------------------
def _replay_apply(g, actions, m, n, step):
    """把动作列表逐条执行到 g 上（原地修改），任一步非法返回 False。

    每步优先按 rep_cell 精确定位分量，找不到时退回「该侧首块」。
    """
    r = _Runner.__new__(_Runner)
    r.g, r.m, r.n, r.step = g, m, n, step
    r.p = None
    for a in actions:
        gap, line, side, d = a[:4]
        rep = a[4] if len(a) == 5 else None
        tgt = r._block_at(rep) if rep is not None else None
        if tgt is None:
            tgt = r._side_first_block(gap, line, side)
        if tgt is None:
            return False
        g.opt(gap, line, tgt)
        final = g.try_move(d, step)
        if not final:
            return False
        g.commit_move(final)
    return True


def replay_and_verify(coords, m, n, step, actions):
    """整局回放验证最终还原。"""
    g = build_game(coords, m, n)
    return _replay_apply(g, actions, m, n, step) and g.is_solved()


def _overlap_raised(coords, m, n, step, actions):
    """couple 成果判定：从 coords 回放 actions 后「最佳窗口内方块数」提升。

    对应「有成果的失败」——能提升聚拢度（多覆盖一格/填上一个空位）但未必
    整盘还原；只要提升就接受为一步进展。回放失败视为无成果。
    """
    _reg, ov0, _holes, _out = window_of(coords, m, n, step)
    g = build_game(coords, m, n)
    if not _replay_apply(g, actions, m, n, step):
        return False
    _reg2, ov1, _holes2, _out2 = window_of(gcoords(g), m, n, step)
    return ov1 > ov0


def sample_states():
    path = os.path.join(_ROOT, 'save', '标注样本', 'annotations.jsonl')
    states = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            ep = json.loads(line)
            pz = ep['puzzle']
            st = ep['start']
            mr, mc = st['bounds']['min_row'], st['bounds']['min_col']
            coords = frozenset((i + mr, j + mc)
                               for i, row in enumerate(st['matrix'])
                               for j, v in enumerate(row) if v)
            states.append((ep['episode_id'], pz['m'], pz['n'], pz['step'],
                           coords))
    return states


def save_case_json(folder, name, coords, m, n, step, extra=None):
    """把一局（状态+附加信息）存成 hole.json 同款 schema。"""
    os.makedirs(folder, exist_ok=True)
    rs = [r for r, _c in coords]
    cs = [c for _r, c in coords]
    mnr, mxr, mnc, mxc = min(rs), max(rs), min(cs), max(cs)
    matrix = [[1 if (r, c) in coords else 0
               for c in range(mnc, mxc + 1)]
              for r in range(mnr, mxr + 1)]
    doc = {
        'version': 1,
        'puzzle': {'m': m, 'n': n, 'step': step},
        'step_count': 0,
        'history': {'history_index': 0, 'snapshots': [{
            'matrix': matrix,
            'bounds': {'min_row': mnr, 'max_row': mxr,
                       'min_col': mnc, 'max_col': mxc},
        }]},
    }
    if extra:
        doc['_fill'] = extra
    path = os.path.join(folder, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False)
    return path


def _main():
    args = sys.argv[1:]
    if args and args[0] == '--sample':
        states = sample_states()
        n_solved = n_replay = 0
        for eid, m, n, step, coords in states:
            acts, stats = solve_single_void(coords, m, n, step)
            if acts is None:
                print('FAIL %-22s %s' % (eid, stats))
                continue
            ok = replay_and_verify(coords, m, n, step, acts)
            n_solved += 1
            n_replay += ok
            print('OK   %-22s steps=%-3d replay=%s' % (eid, len(acts), ok))
        print('\n样例：宏生成 %d/%d，回放还原 %d/%d'
              % (n_solved, len(states), n_replay, len(states)))
        return
    if args and args[0] == '--gen':
        m, n, step, N = (int(x) for x in args[1:5])
        seed = int(args[5]) if len(args) > 5 else 0
        rng = random.Random(seed)
        from solver.ml.ann_gen import generate_random_void
        ok = replay_ok = 0
        t = time.time()
        fails = {}
        out_dir = os.path.join(_ROOT, 'save')   # Ctrl+O 直接可见
        stamp = time.strftime('%Y%m%d-%H%M%S')
        saved = 0
        for i in range(N):
            coords, _holes = generate_random_void(m, n, step, 1, rng=rng)
            acts, stats = solve_single_void(coords, m, n, step)
            name = f'{step}-{m}-{n}-{stamp}-{i:03d}.json'
            if acts is None:
                r = stats.get('reason', '?')
                fails[r] = fails.get(r, 0) + 1
                save_case_json(out_dir, name, coords, m, n, step,
                               extra={'result': 'no_solution',
                                      'reason': r, 'stats': stats})
                saved += 1
                continue
            ok += 1
            if replay_and_verify(coords, m, n, step, acts):
                replay_ok += 1
            else:
                fails['逆映射/回放未还原'] = \
                    fails.get('逆映射/回放未还原', 0) + 1
                save_case_json(out_dir, name, coords, m, n, step,
                               extra={'result': 'replay_fail',
                                      'stats': stats,
                                      'steps': len(acts)})
                saved += 1
        print('\n单洞量产 %d 局：宏生成 %d，回放还原 %d（%.1f%%）  %.0fs'
              % (N, ok, replay_ok, 100.0 * replay_ok / N, time.time() - t))
        for r, cnt in sorted(fails.items(), key=lambda x: -x[1])[:8]:
            print('  FAIL原因 %s × %d' % (r, cnt))
        if saved:
            print('  已存失败档案 %d 个 → %s' % (saved, out_dir))
        return
    if args and args[0] == '--genmulti':
        # --genmulti m n step hole N [seed]  → 批量「多洞无缺口」验收
        m, n, step, hole, N = (int(x) for x in args[1:6])
        seed = int(args[6]) if len(args) > 6 else 0
        rng = random.Random(seed)
        from solver.ml.ann_gen import generate_classified
        ok = replay_ok = 0
        t = time.time()
        fails = {}
        out_dir = os.path.join(_ROOT, 'save')
        stamp = time.strftime('%Y%m%d-%H%M%S')
        saved = rounds_total = gen_fail = partial_sum = part_out = 0
        for i in range(N):
            try:
                coords, _holes = generate_classified(m, n, step, hole, 0,
                                                     rng=rng)
            except ValueError as e:
                gen_fail += 1
                print('GENFAIL %d/%d %s' % (i, N, e))
                continue
            acts, stats = solve_multi_void(coords, m, n, step, rng=rng)
            name = 'multi-h%d-%dx%d-step%d-%s-%03d.json' \
                   % (hole, m, n, step, stamp, i)
            if acts is None:
                r = stats.get('reason', '?')
                fails[r] = fails.get(r, 0) + 1
                save_case_json(out_dir, name, coords, m, n, step,
                               extra={'result': 'no_solution',
                                      'hole': hole, 'reason': r,
                                      'stats': stats})
                saved += 1
                continue
            rounds_total += stats.get('rounds', 0)
            partial_sum += stats.get('partial_accepted', 0)
            if stats.get('partial'):
                part_out += 1    # 有成果的失败：提升了聚拢度但未还原
                if replay_and_verify(coords, m, n, step, acts):
                    ok += 1
                    replay_ok += 1
                continue
            ok += 1
            if replay_and_verify(coords, m, n, step, acts):
                replay_ok += 1
            else:
                fails['多洞回放未还原'] = fails.get('多洞回放未还原', 0) + 1
                save_case_json(out_dir, name, coords, m, n, step,
                               extra={'result': 'replay_fail',
                                      'hole': hole, 'stats': stats,
                                      'steps': len(acts)})
                saved += 1
        avg_r = (rounds_total / ok) if ok else 0.0
        tried = N - gen_fail
        print('\n多洞量产 m%d×n%d step%d 孔洞=%d：%d 局'
              '（生成未命中 %d），求解 %d 局：还原 %d，'
              '回放还原 %d（%.1f%%），均 %d 轮，partial收容 %d 次，'
              '有成果停机 %d 局  %.0fs'
              % (m, n, step, hole, N, gen_fail, tried, ok, replay_ok,
                 100.0 * replay_ok / tried if tried else 0.0,
                 avg_r, partial_sum, part_out, time.time() - t))
        for r, cnt in sorted(fails.items(), key=lambda x: -x[1])[:8]:
            print('  FAIL原因 %s × %d' % (r, cnt))
        if saved:
            print('  已存失败档案 %d 个 → %s' % (saved, out_dir))
        return
    print(__doc__)


if __name__ == '__main__':
    _main()
