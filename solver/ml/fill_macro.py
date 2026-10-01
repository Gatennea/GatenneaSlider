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


def _emit(cb, stage, nodes=None, note=''):
    """向 GUI progress_callback 发进度（cb 为 None 时零开销）。

    info = {'stage': 阶段名, 'nodes': 节点数, 'path_preview': 描述}，
    正好落在 GUI 主循环的通用显示分支：[阶段] 节点N 描述 | 用时。
    """
    if cb is None:
        return
    try:
        cb({'stage': stage, 'nodes': nodes or 0, 'path_preview': note})
    except Exception:
        pass  # 进度显示失败绝不拖垮求解


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


def _couple_scan_state(coords, m, n, step, rng, couple_hook=None):
    """当前状态遍历全部 couple，返回首个能提升聚拢度的动作片段（含 partial 有成果）。

    couple_hook：可选 (coords, m, n, step, h, p) → (acts, stats) 的统一
    求解器（多空位驱动层注入：洞→填洞宏、缺口→补缺链）。为 None 时
    走原填洞宏 couple。"""
    _reg, _ov, holes, outside = window_of(coords, m, n, step)
    h_list = list(holes)
    rng.shuffle(h_list)
    for h in h_list:
        cands = [p for p in outside
                 if (p[0] - h[0]) % step == 0 and (p[1] - h[1]) % step == 0]
        rng.shuffle(cands)
        for p in cands:
            if couple_hook is not None:
                acts, _s = couple_hook(coords, m, n, step, h, p)
            else:
                acts, _s = solve_single_void(coords, m, n, step, hole=h,
                                             anchor=p, keep_partial=True)
            # 此处替 solve_single_void 把关聚拢度：只认「回放后窗口方块数提升」
            if acts is not None and _overlap_raised(coords, m, n, step, acts):
                return acts
    return None


def _nondrop_moves(coords, m, n, step, ov0):
    """所有「最佳窗口方块数不下降」的单步动作 → [(action5, 新局面)]。

    0 增益（=ov0）留给下一步整形；提升（>ov0）的是可直接收下的成果。
    每步都经 _capture_apply 生成，动作带代表格（5 元组），保证与回放同语义。
    """
    from solver.actions import enumerate_valid_actions
    g = build_game(coords, m, n)
    out = []
    for act in enumerate_valid_actions(g, step):
        g2 = build_game(coords, m, n)
        ok, act5 = _capture_apply(g2, act, step)
        if not ok:
            continue
        s2 = frozenset(gcoords(g2))
        if window_of(s2, m, n, step)[1] >= ov0:
            out.append((act5, s2))
    return out


def _shaping_progress(coords, m, n, step, rng, ov0, max_shaping=2,
                      max_nodes=150, couple_hook=None):
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
            cacts = _couple_scan_state(s, m, n, step, rng,
                                       couple_hook=couple_hook)
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
                     rng=None, couple_hook=None):
    """多洞无缺口贪心驱动（确定性死代码，无求解搜索）。

    couple_hook：可选统一 couple 求解器 (coords,m,n,step,h,p)→(acts,stats)。
    None = 只填洞（原行为）；注入多空位分发器后即为「洞+缺口统一驱动」：
    缺口 couple 走补缺链（双层共轭），洞 couple 走填洞宏，验收闸门同一把
    （回放后最佳窗口方块数提升）。

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
                if couple_hook is not None:
                    acts, stats = couple_hook(cur, m, n, step, h, p)
                else:
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
                                     max_shaping, max_nodes,
                                     couple_hook=couple_hook)
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
# 移形换位宏（紧凑盘专用，2026-10-01 用户「2-4-4」三档教学参数化）
# ---------------------------------------------------------------------------
def _swap_fill(coords, m, n, step, max_nodes=40000, verbose=False):
    """移形换位宏：紧凑盘（m<=2*step 且 n<=2*step）单缺口/散块构型求解。

    用户解法：滑块按 2x2 整组互换位置机动（「移形换位」，对其他谜题
    也有效），把边缘缺口逐步围成孔洞后顺势收拢还原。

    实现 = step 级组移动作的全量双向 BFS：
      · 正向从当前局面、反向从全部还原态（面积界内实心 m×n 矩形）
        出发，小侧优先扩展，中间相遇；
      · 动作枚举与引擎同语义：选缝一侧的连通分量平移 step 格，逐格
        无碰撞且每个中间位置整体连通（= try_move 预测-验证序列）；
      · 只发 k=step 动作（回放器 _capture_apply 固定 step 距离）；
        动作关系对称（逐格验证序列正逆相同）→ 反向扩展复用同一枚举器；
      · 面积界 [-2, m+1]×[-2, n+1]（教学解的机动范围）；
      · rep = 移动前选块位置（min(分量)），与宏回放语义一致。
    BFS 最短性 → 动作数不劣于用户手解。
    返回动作列表（5 元组）或 None。
    """
    from collections import deque
    coords = frozenset(coords)
    if len(coords) != m * n:
        return None
    if build_game(coords, m, n).is_solved():
        return []
    area = (-2, m + 1, -2, n + 1)

    def _connected(S):
        it = iter(S)
        p0 = next(it)
        sn = {p0}
        stk = [p0]
        while stk:
            r, c = stk.pop()
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if nb in S and nb not in sn:
                    sn.add(nb)
                    stk.append(nb)
        return len(sn) == len(S)

    def _moves(cur):
        """全部合法 step 级动作 [(gap,line,side,d,rep,nxt)]。"""
        rows = [r for r, _ in cur]
        cols = [c for _, c in cur]
        out = []
        for gap in ('h', 'v'):
            lo = (min(rows) - step) if gap == 'h' else (min(cols) - step)
            hi = (max(rows) + step) if gap == 'h' else (max(cols) + step)
            for line in range(lo, hi + 1):
                for side in (('above', 'below') if gap == 'h'
                             else ('left', 'right')):
                    if gap == 'h':
                        keep = ((lambda q: q[0] <= line) if side == 'above'
                                else (lambda q: q[0] > line))
                    else:
                        keep = ((lambda q: q[1] <= line) if side == 'left'
                                else (lambda q: q[1] > line))
                    sel = frozenset(q for q in cur if keep(q))
                    if not sel or sel == cur:
                        continue
                    seen_c = set()
                    for q0 in sel:
                        if q0 in seen_c:
                            continue
                        comp, stk = {q0}, [q0]
                        while stk:
                            r, c = stk.pop()
                            for nb in ((r - 1, c), (r + 1, c),
                                       (r, c - 1), (r, c + 1)):
                                if nb in sel and nb not in comp:
                                    comp.add(nb)
                                    stk.append(nb)
                        seen_c |= comp
                        comp = frozenset(comp)
                        rest = cur - comp
                        if not rest:
                            continue
                        for d, (dr, dc) in (('w', (-1, 0)), ('s', (1, 0)),
                                            ('a', (0, -1)), ('d', (0, 1))):
                            mv = comp
                            ok = True
                            for _cell in range(step):
                                mv = frozenset((q[0] + dr, q[1] + dc)
                                               for q in mv)
                                if mv & rest or not _connected(rest | mv):
                                    ok = False
                                    break
                            if not ok:
                                continue
                            final = frozenset((q[0] + dr * step,
                                               q[1] + dc * step)
                                              for q in comp)
                            if any(not (area[0] <= r <= area[1]
                                        and area[2] <= c <= area[3])
                                   for r, c in final):
                                continue
                            out.append((gap, line, side, d, min(comp),
                                        rest | final))
        return out

    goals = [frozenset((r0 + i, c0 + j) for i in range(m) for j in range(n))
             for r0 in range(area[0], area[1] - m + 2)
             for c0 in range(area[2], area[3] - n + 2)]
    fw = {coords: None}
    bw = {g: None for g in goals}
    f_q, b_q = deque([coords]), deque(goals)
    nodes = 0
    meet = None
    while f_q and b_q and meet is None and nodes < max_nodes:
        # 小侧优先扩展一个节点
        if len(f_q) <= len(b_q):
            q, vis, other = f_q, fw, bw
        else:
            q, vis, other = b_q, bw, fw
        cur = q.popleft()
        nodes += 1
        for _gap, _line, _side, _d, _rep, nxt in _moves(cur):
            if nxt in vis:
                continue
            vis[nxt] = cur
            if nxt in other:
                meet = nxt
                break
            q.append(nxt)
    if meet is None:
        if verbose:
            print('[移形换位] BFS 未命中（节点 %d）' % nodes)
        return None
    # 状态路径：fw 侧 meet→start 逆链 + bw 侧 meet→goal 逆链
    path = [meet]
    s = meet
    while fw.get(s) is not None:
        s = fw[s]
        path.append(s)
    path.reverse()
    s = meet
    while bw.get(s) is not None:
        s = bw[s]
        path.append(s)
    # 相邻状态对 → 引擎动作（回扫枚举，避免选块语义推导出错）
    acts = []
    for a, b in zip(path, path[1:]):
        hit = [mv for mv in _moves(a) if mv[5] == b]
        if not hit:
            return None
        acts.append((hit[0][0], hit[0][1], hit[0][2], hit[0][3], hit[0][4]))
    if verbose:
        print('[移形换位] %d 步（节点 %d，%.1fs）'
              % (len(acts), nodes, time.time() - _T0[0]))
    return acts


_T0 = [0.0]


def _compact_rescue(coords, m, n, step, why='', progress_callback=None):
    """紧凑盘移形换位救援：常规链全败后的最后手段（2026-10-01）。"""
    if not (m <= 2 * step and n <= 2 * step):
        return None
    _emit(progress_callback, '移形换位', 0,
          '紧凑盘双向BFS（常规链失败:%s）' % why[:30])
    import time as _t
    _T0[0] = _t.time()
    acts = _swap_fill(coords, m, n, step)
    if acts is None:
        return None
    print('[移形换位] 常规链失败(%s)，换位机动 %d 步全解'
          % (why[:40], len(acts)))
    return _split_actions(acts)


# ---------------------------------------------------------------------------
# 带移盖洞宏
# ---------------------------------------------------------------------------
def _belt_shift_fill(coords, m, n, step, h, verbose=False):
    """带移盖洞宏（2026-10-01 失败02 教学「拆东墙补西墙」参数化）。

    洞 h 无同 mod 凸起可配时的填洞法，用户三步结构：
      ① 补料 a1：一步平移把料搬进带尾上游空位；
      ② 带移 a2：含 h 的整条连通带平移，h 被错位块盖住；
      ③ 还原 a3：带的多余段逆移复位（消掉带移的副作用）。
    净效果：ov +1（h 被填，a2/a3 新增的窗内洞被 a1 预补的料顶住）。

    定向搜索：坐标层粗筛 a2（盖得住 h）→ 枚举 a3（a2 的部分逆移）
    得净局面与「新窗内洞」→ 反推 a1 目标段与源组 → 引擎逐段验证。
    返回 (动作列表, 终局coords)；失败 (None, None)。
    """
    coords = frozenset(coords)
    _DIRV = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
    _INV = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}
    rows = [r for r, c in coords]
    cols = [c for r, c in coords]
    rmin, rmax, cmin, cmax = min(rows), max(rows), min(cols), max(cols)
    _reg, ov0, holes0, _oo = window_of(coords, m, n, step)

    def _side_test(gap, line, side):
        if gap == 'h':
            return (lambda r, c: r <= line) if side == 'above' \
                else (lambda r, c: r > line)
        return (lambda r, c: c <= line) if side == 'left' \
            else (lambda r, c: c > line)

    def _comp_of(S, st):
        sel = {p for p in S if st(*p)}
        out, seen = [], set()
        for p0 in sel:
            if p0 in seen:
                continue
            comp, stack = set(), [p0]
            while stack:
                q = stack.pop()
                if q in comp:
                    continue
                comp.add(q)
                seen.add(q)
                r, c = q
                for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if nb in sel and nb not in comp:
                        stack.append(nb)
            out.append(frozenset(comp))
        return out

    def _conn_ok(S):
        S = set(S)
        p0 = next(iter(S))
        seen, stack = {p0}, [p0]
        while stack:
            r, c = stack.pop()
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if nb in S and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return len(seen) == len(S)

    def _try(g, a5, sel_set):
        """执行一步 5 元组动作；选块 = sel_set 中属缝侧的首块。"""
        gap, line, side, dc, rep = a5
        st = _side_test(gap, line, side)
        tgt = None
        for blk in g.blocks:
            r, c = blk.location
            if (r, c) in sel_set and st(r, c):
                tgt = blk
                break
        if tgt is None:
            return False
        try:
            g.opt(gap, line, tgt)
            final, _why = g.try_move_ex(dc, rep)
            if not final:
                return False
            g.commit_move(final)
        except Exception:
            return False
        return True

    # ---- ① 粗筛 a2：单步带移后 h 被盖 ----
    a2_cands = []
    for gap2 in ('h', 'v'):
        lines = (range(rmin - 2, rmax + 3) if gap2 == 'h'
                 else range(cmin - 2, cmax + 3))
        for line2 in lines:
            for side2 in (('above', 'below') if gap2 == 'h'
                          else ('left', 'right')):
                for comp2 in _comp_of(coords, _side_test(gap2, line2, side2)):
                    rest2 = coords - comp2
                    for dc2, (dr2, dcn2) in _DIRV.items():
                        for rep2 in (step, 2 * step):
                            delta2 = (dr2 * rep2, dcn2 * rep2)
                            moved2 = frozenset(
                                (p[0] + delta2[0], p[1] + delta2[1])
                                for p in comp2)
                            if moved2 & rest2 or h not in moved2:
                                continue
                            a2_cands.append((gap2, line2, side2, dc2, rep2,
                                             comp2, delta2, moved2, rest2))

    # ---- ② 每个 a2：枚举 a3（部分逆移）→ 净局面 → 反推 a1 ----
    for gap2, line2, side2, dc2, rep2, comp2, delta2, moved2, rest2 in a2_cands:
        s_a2 = rest2 | moved2
        if not _conn_ok(s_a2):
            continue
        dc3 = _INV[dc2]
        # a3 与 a2 同侧、不同分界线：还原移动组中 line3 一侧的子段
        side3 = side2
        lines3 = (range(rmin - 2, rmax + 3) if gap2 == 'h'
                  else range(cmin - 2, cmax + 3))
        for line3 in lines3:
            st3 = _side_test(gap2, line3, side3)
            R = frozenset(p for p in moved2 if st3(*p))
            if not R or R == moved2:
                continue                       # a3 必须还原「一段」
            back = frozenset((p[0] - delta2[0], p[1] - delta2[1])
                             for p in R)
            s_net = (s_a2 - R) | back
            if not _conn_ok(s_net) or h not in s_net:
                continue
            _rg, ov_net, holes_net, _o = window_of(s_net, m, n, step)
            if ov_net >= ov0 + 1:
                need_a1 = False
                T = None
            elif ov_net < ov0:
                need_a1 = True
                new_holes = set(holes_net) - set(holes0)
                if not 1 <= len(new_holes) <= 3:
                    continue
                # T = 新洞的带移前像（当前须为空；02 教学例：新洞 (4,2)(4,3)
                # ← T=(4,0)(4,1)，a1 从 (6,0)(6,1) 补两块）
                T = frozenset((p[0] - delta2[0], p[1] - delta2[1])
                              for p in new_holes)
                if not all(q not in coords for q in T):
                    continue
            else:
                continue
            # ---- ③ a1 反推 + 引擎验证 ----
            a1_cands = [(None, None, None, None, None, None, None)] \
                if not need_a1 else []
            if need_a1:
                for dc1, (dr1, dcn1) in _DIRV.items():
                    for rep1 in (step, 2 * step):
                        delta1 = (dr1 * rep1, dcn1 * rep1)
                        src = frozenset((q[0] - delta1[0],
                                         q[1] - delta1[1]) for q in T)
                        if not src <= coords:
                            continue
                        moved1 = frozenset(
                            (q[0] + delta1[0], q[1] + delta1[1])
                            for q in src)
                        if moved1 & (coords - src):
                            continue
                        s1 = (coords - src) | moved1
                        if not _conn_ok(s1):
                            continue
                        gap1 = 'v' if dc1 in ('w', 's') else 'h'
                        a1_cands.append((gap1, dc1, rep1, src, moved1, s1,
                                         delta1))
            for a1 in a1_cands:
                g = build_game(coords, m, n)
                if need_a1:
                    gap1, dc1, rep1, src, moved1, s1, delta1 = a1
                    done = False
                    if gap1 == 'v':
                        rng1 = (range(cmin - 2, cmax + 3), ('left', 'right'))
                    else:
                        rng1 = (range(rmin - 2, rmax + 3),
                                ('above', 'below'))
                    for line1 in rng1[0]:
                        for side1 in rng1[1]:
                            g2 = build_game(coords, m, n)
                            if _try(g2, (gap1, line1, side1, dc1, rep1),
                                    src) \
                                    and frozenset(gcoords(g2)) == s1:
                                g = g2
                                done = True
                                break
                        if done:
                            break
                    if not done:
                        continue
                    # 重算含 a1 的净局面：a1 补的料属带移组、随带移动
                    st2 = _side_test(gap2, line2, side2)
                    comp2_all = comp2 | frozenset(
                        p for p in moved1 if st2(*p))
                    s1_rest = s1 - comp2_all
                    moved2_all = frozenset(
                        (p[0] + delta2[0], p[1] + delta2[1])
                        for p in comp2_all)
                    if moved2_all & s1_rest:
                        continue
                    s_a2 = s1_rest | moved2_all
                    R = frozenset(p for p in moved2_all if st3(*p))
                    back = frozenset((p[0] - delta2[0], p[1] - delta2[1])
                                     for p in R)
                    s_net = (s_a2 - R) | back
                    if not _conn_ok(s_net) or h not in s_net:
                        continue
                if not _try(g, (gap2, line2, side2, dc2, rep2), comp2):
                    continue
                sel3 = frozenset(p for p in gcoords(g) if st3(*p))
                if not _try(g, (gap2, line3, side3, dc3, rep2), sel3):
                    continue
                if frozenset(gcoords(g)) != s_net:
                    continue
                _rg, ov_f, _hf, _of = window_of(s_net, m, n, step)
                if ov_f != ov0 + 1:
                    continue
                if verbose:
                    print('  带移盖洞: 洞%s 原语成立 a2=%s@%d%s%s%d '
                          'a3=%s@%d%s%s%d%s'
                          % (h, gap2, line2, side2, dc2, rep2,
                             gap2, line3, side3, dc3, rep2,
                             '' if not need_a1 else ' +补料'))
                # 动作列表：a1 暴力试出的参数回填
                acts = []
                if need_a1:
                    acts.append((gap1, line1, side1, dc1, rep1))
                acts.append((gap2, line2, side2, dc2, rep2))
                acts.append((gap2, line3, side3, dc3, rep2))
                return acts, s_net
    return None, None


def _convoy_fill(coords, m, n, step, h, p, max_prep=2, max_pickup=4,
                 max_depth=16, max_nodes=2500, max_comp=None, verbose=False,
                 progress_callback=None):
    r"""粘上接走宏（2026-10-01 失败03 教学「粘上接走」参数化）。

    标准 couple 宏解不动时的另一条填洞路：载运带靠上孤立凸起「粘上」
    （相邻即合并为同一连通分量），再整组搬运把凸起送进洞。
    03 用户解（15 步中前 5 步）：底带西移清场 → 载运带北移×2 靠上凸起
    粘成整体 → 合并组南下、整侧东移把凸起 (0,0) 送进洞 (4,4)，底带同时
    复位，净效果 ov+1；余下部分标准 couple 可直接收尾。

    定向腿搜索（坐标层集合运算逐格模拟 + 终局引擎验收）：
      · carry 腿：移动含凸起分量，p→h 曼哈顿距离严格下降；
      · approach 腿：移动不含 p 的分量且该分量与 p 的最小距离下降
        （靠上去粘住）；
      · prep 腿：其余单步，仅当移动分量与 p→h 包围盒相交且能清空走廊，
        全程 ≤max_prep。
    阶段纪律：先接应（appr/prep，≤max_pickup 步）后搬运（carry），carry
    开始后不再接应；分量尺寸 >max_comp 的「搬主体」动作一律剔除（junk：
    终局位移残留必然过不了 ov 闸门，纯烧节点）。
    所有动作均为 step 距离单步（5 元组带选块坐标，与回放语义一致；
    任意距离动作可精确分解为若干 step 单步——引擎逐格验证保证）。
    终点：p 落在 h 且回放后窗口方块数 +1（_overlap_raised 同闸门）。
    返回 (动作列表或 None, 实际消耗节点数)。
    """
    coords = frozenset(coords)
    h, p = tuple(h), tuple(p)
    if max_comp is None:
        max_comp = max(8, len(coords) // 2)
    if (p[0] - h[0]) % step or (p[1] - h[1]) % step:
        return None                      # p 要逐 step 落到 h 上，必须同 mod
    if p not in coords or h in coords:
        return None
    bb_r = (min(p[0], h[0]), max(p[0], h[0]))
    bb_c = (min(p[1], h[1]), max(p[1], h[1]))

    def _comps(S):
        S = set(S)
        out, seen = [], set()
        for q0 in S:
            if q0 in seen:
                continue
            comp, stack = set(), [q0]
            while stack:
                q = stack.pop()
                if q in comp:
                    continue
                comp.add(q)
                seen.add(q)
                r, c = q
                for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if nb in S and nb not in comp:
                        stack.append(nb)
            out.append(frozenset(comp))
        return out

    def _connected(S):
        S = set(S)
        if not S:
            return False
        p0 = next(iter(S))
        seen, stack = {p0}, [p0]
        while stack:
            r, c = stack.pop()
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if nb in S and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return len(seen) == len(S)

    def _mindist(S, q):
        return min(abs(r - q[0]) + abs(c - q[1]) for r, c in S)

    def _legal_steps(cur):
        """全部合法 step 单步 → [(act5, comp, delta, nxt)]。

        逐 1 格子步模拟（碰撞 + 全盘连通），与引擎 try_move 语义一致。
        排除整盘平移（rest 为空）：相对位置不变，纯浪费节点。
        """
        out = []
        rows = [r for r, _c in cur]
        cols = [c for _r, c in cur]
        for gap in ('h', 'v'):
            lines = (range(min(rows) - 2, max(rows) + 3) if gap == 'h'
                     else range(min(cols) - 2, max(cols) + 3))
            for line in lines:
                for side in (('above', 'below') if gap == 'h'
                             else ('left', 'right')):
                    if gap == 'h':
                        st = (lambda q: q[0] <= line) if side == 'above' \
                            else (lambda q: q[0] > line)
                    else:
                        st = (lambda q: q[1] <= line) if side == 'left' \
                            else (lambda q: q[1] > line)
                    sel = frozenset(q for q in cur if st(q))
                    if not sel or sel == cur:
                        continue
                    for comp in _comps(sel):
                        rest = cur - comp
                        if not rest:
                            continue
                        if len(comp) > max_comp:
                            continue          # 搬主体 = junk，剔除
                        rep = min(comp)          # 选块坐标（分量任一格）
                        for d, (dr, dc) in _DIRS.items():
                            ok = True
                            for k in range(1, step + 1):
                                mv_k = frozenset(
                                    (q[0] + dr * k, q[1] + dc * k)
                                    for q in comp)
                                if (mv_k & rest
                                        or not _connected(rest | mv_k)):
                                    ok = False
                                    break
                            if not ok:
                                continue
                            mv = frozenset(
                                (q[0] + dr * step, q[1] + dc * step)
                                for q in comp)
                            out.append(((gap, line, side, d, rep), comp,
                                        (dr * step, dc * step), rest | mv))
        return out

    state = {'nodes': 0}
    seen = {(coords, p)}

    def _corridor_occ(S):
        """p→h 十字走廊（p 列/h 行在包围盒内的段）占用数。"""
        n = 0
        for r, c in S:
            if ((c == p[1] or c == h[1]) and bb_r[0] <= r <= bb_r[1]) or \
               ((r == p[0] or r == h[0]) and bb_c[0] <= c <= bb_c[1]):
                n += 1
        return n

    def _on_cross(q):
        """p 是否在十字走廊上（L 形路径的合法位置）。"""
        return (q[1] == p[1] and bb_r[0] <= q[0] <= bb_r[1]) or \
               (q[0] == h[0] and bb_c[0] <= q[1] <= bb_c[1])

    def dfs(cur, pcur, prep_used, prefix, carried=False, last_march=None):
        if state['nodes'] >= max_nodes:
            return None
        state['nodes'] += 1
        if verbose and state['nodes'] % 100 == 0:
            print('   [convoy节点%d] 深度%d prep已用%d p=%s'
                  % (state['nodes'], len(prefix), prep_used, pcur))
        if progress_callback is not None and state['nodes'] % 100 == 0:
            _emit(progress_callback, '粘上接走', state['nodes'],
                  '洞%s←凸%s 深度%d' % (h, p, len(prefix)))
        if pcur == h:
            return list(prefix) if _overlap_raised(coords, m, n, step,
                                                   prefix) else None
        if len(prefix) >= max_depth:
            return None
        pickup_left = max_pickup - len(prefix)
        d0 = abs(pcur[0] - h[0]) + abs(pcur[1] - h[1])
        carry, appr, prep = [], [], []
        for act5, comp, delta, nxt in _legal_steps(cur):
            if pcur in comp:
                np_ = (pcur[0] + delta[0], pcur[1] + delta[1])
                if abs(np_[0] - h[0]) + abs(np_[1] - h[1]) < d0:
                    carry.append((0 if _on_cross(np_) else 1, 0,
                                  act5, nxt, np_, prep_used, None))
            elif not carried and pickup_left > 0:
                # 阶段纪律：开始搬运（carry）后不再接应——先粘上后送到位
                moved = frozenset((q[0] + delta[0], q[1] + delta[1])
                                  for q in comp)
                md_c, md_m = _mindist(comp, pcur), _mindist(moved, pcur)
                if md_m < md_c:
                    # 行军纪律：只许 ①一步贴上（移完即与 p 相邻=粘上）
                    # ②同一分量连续行军（含起步：last_march 为空时可起步）
                    # ——掐断「换分量各挪一步」的乱逛组合
                    if md_m == 1:
                        appr.append((md_c - md_m, len(comp), act5, nxt,
                                     pcur, prep_used, None))
                    elif last_march is None or comp == last_march:
                        appr.append((md_c - md_m, len(comp), act5, nxt,
                                     pcur, prep_used, moved))
                elif prep_used < max_prep:
                    freed = _corridor_occ(comp) - _corridor_occ(moved)
                    if freed > 0 and any(
                            bb_r[0] <= r <= bb_r[1]
                            and bb_c[0] <= c <= bb_c[1] for r, c in comp):
                        prep.append((freed, 0, act5, nxt, pcur,
                                     prep_used + 1, None))
        appr.sort(key=lambda x: (-x[0], x[1]))
        prep.sort(key=lambda x: -x[0])
        carry.sort(key=lambda x: x[0])
        # appr 优先：先把载运带靠上凸起（粘上），再整组搬运——
        # 直接搬含 p 的大主体多为 junk（终局位移残留在闸门被拒）
        for group in (appr, prep, carry):
            for _k, _s, act5, nxt, np_, pu, lm in group:
                if (nxt, np_) in seen:
                    continue
                seen.add((nxt, np_))
                r = dfs(nxt, np_, pu, prefix + [act5],
                        carried=carried or (group is carry),
                        last_march=lm if group is appr else None)
                if r is not None:
                    if verbose:
                        print('  粘上接走: 洞%s←凸%s %d步成立(节点%d)'
                              % (h, p, len(r), state['nodes']))
                    return r
        return None

    r = dfs(coords, p, 0, [])
    return r, state['nodes']


# ---------------------------------------------------------------------------
# 刚体挤入宏（教程第 5 关「二连刚体凸起」参数化，2026-10-01）
# ---------------------------------------------------------------------------
def _adj_clusters(cells):
    """格集 → 相邻连通簇列表（4 邻接，仅返回 ≥2 格的簇）。"""
    S = set(cells)
    out, seen = [], set()
    for q0 in sorted(S):
        if q0 in seen:
            continue
        cc, stk = {q0}, [q0]
        while stk:
            r, c = stk.pop()
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if nb in S and nb not in cc:
                    cc.add(nb)
                    stk.append(nb)
        cc = frozenset(cc)
        seen |= cc
        if len(cc) >= 2:
            out.append(cc)
    return out


def _connected_ml(S):
    """S 是否 4 邻接连通（模块级，供各宏共用）。"""
    S = set(S)
    if not S:
        return False
    p0 = next(iter(S))
    seen, stk = {p0}, [p0]
    while stk:
        r, c = stk.pop()
        for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if nb in S and nb not in seen:
                seen.add(nb)
                stk.append(nb)
    return len(seen) == len(S)


def _comps_ml(S):
    """格集 → 4 邻接连通分量列表（模块级）。"""
    S = set(S)
    out, seen = [], set()
    for q0 in sorted(S):
        if q0 in seen:
            continue
        cc, stk = {q0}, [q0]
        while stk:
            r, c = stk.pop()
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if nb in S and nb not in cc:
                    cc.add(nb)
                    stk.append(nb)
        cc = frozenset(cc)
        seen |= cc
        out.append(cc)
    return out


def _rigid_fill(coords, m, n, step, H, P, max_prep=2, max_rest=4,
                max_depth=20, max_nodes=3000, max_k=4, max_comp=None,
                allow_appr=None, verbose=False, progress_callback=None):
    """刚体挤入宏：k 格刚体凸起整体填入同形状洞（教程 5.1「直接挤进去」）。

    与粘上接走（_convoy_fill）同构，但：
    · H/P 是格集（相邻 k 格，形状须全等——刚体不可旋转/拆分）；
    · P 随含它的分量刚性平移（跟踪 P 本身而非锚点单格）；
    · 动作距离任意 1..max_k 格（引擎逐格验证；step 距离原语表达不了
      奇数位移——5.1 实证，这是 couple 模型对刚体局失效的根因之一）；
    · P 落上 H 后允许 ≤max_rest 步「带复位」（不含 P 的带移），使
      ov 闸门通过（5.1 用户 4 步中第 4 步即复位）。

    返回 (动作列表或 None, 消耗节点数)。
    """
    coords = frozenset(coords)
    H, P = frozenset(H), frozenset(P)
    k = len(P)
    if len(H) != k:
        return None, 0
    h0, p0 = min(H), min(P)
    off = sorted((r - p0[0], c - p0[1]) for r, c in P)   # P 的相对形状
    if sorted((r - h0[0], c - h0[1]) for r, c in H) != off:
        return None                          # 形状不全等 → 刚体填不进
    if max_comp is None:
        max_comp = max(8, len(coords) // 2)

    # P 已连着主体（与非 P 块相邻）→ 无需接应行军，纯 carry+prep
    attached = any(nb not in P for q in P
                   for nb in ((q[0]-1, q[1]), (q[0]+1, q[1]),
                              (q[0], q[1]-1), (q[0], q[1]+1))
                   if nb in coords)
    if allow_appr is None:
        allow_appr = not attached

    state = {'nodes': 0}
    seen = {(coords, P)}

    def _pset(Pcur, delta):
        d = delta
        return frozenset((q[0] + d[0], q[1] + d[1]) for q in Pcur)

    def _legal_steps(cur):
        """(act5, comp, delta, nxt)——delta 为 1..max_k 格的距离。"""
        out = []
        rows = [r for r, _ in cur]
        cols = [c for _, c in cur]
        for gap in ('h', 'v'):
            lines = (range(min(rows) - 1, max(rows) + 2) if gap == 'h'
                     else range(min(cols) - 1, max(cols) + 2))
            for line in lines:
                for side in (('above', 'below') if gap == 'h'
                             else ('left', 'right')):
                    if gap == 'h':
                        st = (lambda q: q[0] <= line) if side == 'above' \
                            else (lambda q: q[0] > line)
                    else:
                        st = (lambda q: q[1] <= line) if side == 'left' \
                            else (lambda q: q[1] > line)
                    sel = frozenset(q for q in cur if st(q))
                    if not sel or sel == cur:
                        continue
                    for comp in _comps_ml(sel):
                        rest = cur - comp
                        if not rest or len(comp) > max_comp:
                            continue
                        rep = min(comp)
                        for d, (dr, dc) in _DIRS.items():
                            # 距离恒为 step：回放管线（_capture_apply）按
                            # step 移动，act5 第 5 位是代表格——
                            # 5.1 胜利路径全是 step 距离，够用
                            mv = frozenset((q[0] + dr * step, q[1] + dc * step)
                                           for q in comp)
                            ok = True
                            for u in range(1, step + 1):
                                mku = frozenset((q[0] + dr * u, q[1] + dc * u)
                                                for q in comp)
                                if (mku & rest
                                        or not _connected_ml(rest | mku)):
                                    ok = False
                                    break
                            if not ok:
                                continue
                            out.append(((gap, line, side, d, rep),
                                        comp, (dr * step, dc * step),
                                        rest | mv))
        return out

    def _mdist(A, B):
        """集合 A 到集合 B 的最小曼哈顿距离。"""
        return min(abs(ra - rb) + abs(ca - cb) for ra, ca in A
                   for rb, cb in B)

    bb_r = (min(p0[0], h0[0]) - k, max(p0[0], h0[0]) + k)
    bb_c = (min(p0[1], h0[1]) - k, max(p0[1], h0[1]) + k)
    ov0 = window_of(coords, m, n, step)[1]

    def _corridor_occ(S):
        """锚点十字走廊（p 列/h 行在包围盒内的段）占用数。"""
        n = 0
        for r, c in S:
            if ((c == p0[1] or c == h0[1]) and bb_r[0] <= r <= bb_r[1]) or \
               ((r == p0[0] or r == h0[0]) and bb_c[0] <= c <= bb_c[1]):
                n += 1
        return n

    def dfs(cur, Pcur, prep_used, prefix, carried=False, last_march=None,
            rest_used=0):
        if state['nodes'] >= max_nodes:
            return None
        state['nodes'] += 1
        if progress_callback is not None and state['nodes'] % 100 == 0:
            _emit(progress_callback, '刚体挤入', state['nodes'],
                  '洞%s←刚体%d格 深度%d' % (h0, k, len(prefix)))
        docked = Pcur == H
        if docked and rest_used >= max_rest:
            return None
        if len(prefix) >= max_depth:
            return None
        # 终局判定逐边做：任一动作使窗口方块数 > 初局 → 候选完成，
        # 回放验收后即收（胜利路径未必经过「P 落洞」——5.1 实证：
        # 并排北移后一带移即用常规块填洞，P 只是搭车）
        moves = _legal_steps(cur)
        for act5, comp, delta, nxt in moves:
            if nxt == cur:
                continue
            if window_of(nxt, m, n, step)[1] > ov0:
                full = prefix + [act5]
                if _overlap_raised(coords, m, n, step, full):
                    if verbose:
                        print('  刚体挤入: %d步成立(节点%d)'
                              % (len(full), state['nodes']))
                    return full
        # P 落上洞但 ov 闸门未过 → 带复位阶段（≤max_rest 步不含 P 的带移）
        if docked:
            for act5, comp, delta, nxt in moves:
                if comp & Pcur:
                    continue
                if (nxt, Pcur) in seen:
                    continue
                seen.add((nxt, Pcur))
                r = dfs(nxt, Pcur, prep_used, prefix + [act5],
                        carried=True, rest_used=rest_used + 1)
                if r is not None:
                    return r
            return None
        pickup_left = max_pickup = 6 - len(prefix) - rest_used
        carry, appr, prep = [], [], []
        for act5, comp, delta, nxt in moves:
            if Pcur <= comp:
                nP = _pset(Pcur, delta)
                if _mdist(nP, H) < _mdist(Pcur, H):
                    carry.append((0, len(comp), act5, nxt, nP,
                                  prep_used, comp))
            elif allow_appr and not carried and pickup_left > 0:
                moved = frozenset((q[0] + delta[0], q[1] + delta[1])
                                  for q in comp)
                md_c, md_m = _mdist(comp, Pcur), _mdist(moved, Pcur)
                if md_m < md_c:
                    # 行军纪律：一步贴上（与 P 相邻）或同分量连续行军
                    if md_m == 1:
                        appr.append((md_c - md_m, len(comp), act5, nxt,
                                     Pcur, prep_used, None))
                    elif last_march is None or comp == last_march:
                        appr.append((md_c - md_m, len(comp), act5, nxt,
                                     Pcur, prep_used, moved))
                elif prep_used < max_prep:
                    freed = _corridor_occ(comp) - _corridor_occ(moved)
                    if freed > 0:
                        prep.append((0, len(comp), act5, nxt, Pcur,
                                     prep_used + 1, comp))
        appr.sort(key=lambda x: (-x[0], x[1]))
        for group in (appr, prep, carry):
            for _k, _s, act5, nxt, nP, pu, lm in group:
                if (nxt, nP) in seen:
                    continue
                seen.add((nxt, nP))
                r = dfs(nxt, nP, pu, prefix + [act5],
                        carried=carried or (group is carry),
                        last_march=lm if group is appr else None,
                        rest_used=rest_used)
                if r is not None:
                    if verbose:
                        print('  刚体挤入: 洞%s←刚体%d格 %d步成立(节点%d)'
                              % (h0, k, len(r), state['nodes']))
                    return r
        return None

    r = dfs(coords, P, 0, [])
    return r, state['nodes']


def solve_multi_search(coords, m, n, step, couple_hook=None,
                       node_budget=400, reshape_budget=3, verbose=False,
                       progress_callback=None, cancel_check=None):
    """宏级 DFS：对 couple 选择回溯，状态图上找「填满窗口」的宏序列。

    背景：贪心驱动存在顺序依赖——同一盘面换个候选随机序，一个能全解一
    个停机（2026-10-01 失败05/08/09 实证）。这证明「解存在但贪心序列选
    错」，对 couple 选择做 DFS 回溯即可补完备性。

    状态图：节点=盘面，边=一次「hook 成功且闸门通过」的 couple。每条边
    窗口方块数严格 +1 → 深度 ≤ 空位数、无环；不同顺序到达的同一中间态
    用 seen 去重（该状态之下子树相同，败过一次不必再败）。

    整形动作（带移盖洞 / 粘上接走）同样进回溯（2026-10-01）：不再只在
    「零 couple」死端触发——本节点 couple 子树全败后，回溯到本节点改试
    整形边（惰性探测：couple 有戏就不花整形探测的钱）。reshape_budget
    限制每条根→叶路径上整形次数，防组合爆炸。

    couple_hook：(coords,m,n,step,h,p)→(acts,stats)。None = 只填洞。
    node_budget：DFS 节点上限（每节点要对全 couple 跑 hook，代价高）。

    返回 (actions, stats)：
    · 全解 → actions 全量，stats['search']=True；
    · 预算耗尽 → 最深有成果前缀，stats['partial']=True；
    · 零成果 → (None, stats)。
    """
    coords = frozenset(coords)
    if len(coords) != m * n:
        return None, {'error': f'格数 {len(coords)} != {m * n}'}
    if build_game(coords, m, n).is_solved():
        return [], {'steps': 0, 'search': True}
    t0 = time.time()

    def _default_hook(cur, m_, n_, s_, h, p):
        return solve_single_void(cur, m_, n_, s_, hole=h, anchor=p,
                                 keep_partial=True)
    hook = couple_hook or _default_hook

    def _couples(cur):
        _reg, _ov, holes, outside = window_of(cur, m, n, step)
        out = []
        for h in holes:
            for p in outside:
                if (p[0] - h[0]) % step == 0 and (p[1] - h[1]) % step == 0:
                    acts, _st = hook(cur, m, n, step, h, p)
                    if acts is None:
                        continue
                    if not _overlap_raised(cur, m, n, step, acts):
                        continue
                    out.append(acts)
        return out

    state = {'nodes': 0, 'best': [], 'exhausted': False, 'seen': set(),
             'convoy_left': 8000}

    def _reshape_edges(cur):
        """整形边（惰性）：①带移盖洞 ②粘上接走 ③刚体挤入。

        convoy 共享总预算 state['convoy_left']：固有缺陷局面不在无效
        原语上无限烧时间。
        """
        out = []
        _rg, _ovc, holes_c, out_c = window_of(cur, m, n, step)
        # ③ 刚体挤入优先（k≥2 簇对，先于单格原语——多格局面单格 couple
        # 从根上不适配，先烧它纯浪费预算）
        h_clusters = _adj_clusters(holes_c)
        if h_clusters:
            p_clusters = [c for c in _comps_ml(out_c) if len(c) >= 2]
            for Hc in h_clusters:
                for Pc in p_clusters:
                    if len(Hc) != len(Pc):
                        continue
                    _emit(progress_callback, '刚体挤入', state['nodes'],
                          '洞%s←刚体%d格' % (min(Hc), len(Pc)))
                    racts, used = _rigid_fill(
                        cur, m, n, step, Hc, Pc,
                        max_nodes=min(6000, state['convoy_left']),
                        progress_callback=progress_callback)
                    state['convoy_left'] -= used
                    if racts:
                        out.append(racts)
        for h_c in sorted(holes_c):
            _emit(progress_callback, '带移盖洞', state['nodes'],
                  '洞%s 整形探测' % (h_c,))
            bacts, _bn = _belt_shift_fill(cur, m, n, step, h_c)
            if bacts is not None:
                out.append(bacts)
            for p_c in sorted(out_c):
                if state['convoy_left'] <= 0:
                    return out
                if ((p_c[0] - h_c[0]) % step
                        or (p_c[1] - h_c[1]) % step):
                    continue
                _emit(progress_callback, '粘上接走', state['nodes'],
                      '洞%s←凸%s 行军搜索' % (h_c, p_c))
                cacts, used = _convoy_fill(
                    cur, m, n, step, h_c, p_c,
                    max_nodes=min(2500, state['convoy_left']),
                    progress_callback=progress_callback)
                state['convoy_left'] -= used
                if cacts:
                    out.append(cacts)
        return out

    def dfs(cur, prefix, reshape_left):
        if cancel_check is not None and cancel_check():
            state['cancelled'] = True
            return None
        if state['nodes'] >= node_budget:
            state['exhausted'] = True
            return None
        state['nodes'] += 1
        if progress_callback is not None and state['nodes'] % 20 == 0:
            _emit(progress_callback, '宏级搜索', state['nodes'],
                  '深度%d/预算%d' % (len(prefix), node_budget))
        if build_game(cur, m, n).is_solved():
            return list(prefix)
        if len(prefix) > len(state['best']):
            state['best'] = list(prefix)
        for acts in _couples(cur):
            g2 = build_game(cur, m, n)
            if not _replay_apply(g2, acts, m, n, step):
                continue
            nxt = frozenset(gcoords(g2))
            if nxt == cur or nxt in state['seen']:
                continue
            state['seen'].add(nxt)
            r = dfs(nxt, prefix + list(acts), reshape_left)
            if r is not None:
                return r
        # couple 子树全败 → 回溯到本节点改试整形边（整形进回溯）；
        # 「零 couple 死端」是 reshape_left>0 时的自然特例
        if reshape_left > 0:
            for acts in _reshape_edges(cur):
                g2 = build_game(cur, m, n)
                if not _replay_apply(g2, acts, m, n, step):
                    continue
                nxt = frozenset(gcoords(g2))
                if nxt == cur or nxt in state['seen']:
                    continue
                state['seen'].add(nxt)
                r = dfs(nxt, prefix + list(acts), reshape_left - 1)
                if r is not None:
                    return r
        return None

    r = dfs(coords, [], reshape_budget)
    if r is not None:
        return (r, {'steps': len(r), 'nodes': state['nodes'],
                    'search': True, 'secs': round(time.time() - t0, 3)})
    if state['best']:
        return (state['best'],
                {'steps': len(state['best']), 'nodes': state['nodes'],
                 'search': True, 'partial': True,
                 'cancelled': state.get('cancelled', False),
                 'budget_exhausted': state['exhausted'],
                 'secs': round(time.time() - t0, 3)})
    return None, {'reason': '搜索：预算内无可行 couple 路径',
                  'nodes': state['nodes'], 'search': True,
                  'cancelled': state.get('cancelled', False),
                  'secs': round(time.time() - t0, 3)}


# ---------------------------------------------------------------------------
# GUI 求解器入口（与 SOLVER_ALGORITHMS 统一签名）
# ---------------------------------------------------------------------------
def _split_actions(actions):
    """动作列表 → (四元组列表, 代表格列表)。

    兼容两种动作：5 元组 (gap,line,side,dir,rep) 带代表格；
    4 元组（整形/找洞等无代表格步骤）记 None，回放时退回「该侧首块」语义。
    """
    return ([a[:4] for a in actions],
            [a[4] if len(a) == 5 else None for a in actions])


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
    _emit(progress_callback, '填洞宏', 0,
          '判型：洞%d 凸%d' % (len(holes), len(outside)))
    if len(holes) == 1 and len(outside) == 1:
        acts, stats = solve_single_void(coords, m, n, step, keep_partial=True)
        if acts is None:
            reason = stats.get('reason', stats.get('error', '未知'))
            print('[填洞宏] 单洞无解：%s' % reason)
            resc = _compact_rescue(coords, m, n, step, reason,
                                   progress_callback=progress_callback)
            if resc is not None:
                return resc
            return {'type': 'fill_fail', 'reason': reason}
        if stats.get('partial'):
            reason = stats.get('reason', '中断')
            resc = _compact_rescue(coords, m, n, step,
                                   '单洞partial:%s' % reason,
                                   progress_callback=progress_callback)
            if resc is not None:
                return resc
            print('[填洞宏] 单洞部分(断在：%s)，已播放 %d 步供观察'
                  % (reason, len(acts)))
            acts4, reps = _split_actions(acts)
            return {'type': 'fill_partial', 'actions': acts4,
                    'rep_cells': reps, 'reason': reason}
        return _split_actions(acts)
    if not holes:
        return [], []   # 已还原
    _emit(progress_callback, '多洞驱动', 0, '贪心逐couple填')
    acts, stats = solve_multi_void(coords, m, n, step)
    if acts is None:
        reason = stats.get('reason', stats.get('error', '未知'))
        print('[填洞宏] 多洞完全失败：%s' % reason)
        resc = _compact_rescue(coords, m, n, step, reason,
                               progress_callback=progress_callback)
        if resc is not None:
            return resc
        return {'type': 'fill_fail', 'reason': reason,
                'stats': {k: v for k, v in stats.items() if k != 'reason'}}
    if stats.get('partial'):
        reason = stats.get('reason', '中断')
        resc = _compact_rescue(coords, m, n, step, '多洞partial:%s' % reason,
                               progress_callback=progress_callback)
        if resc is not None:
            return resc
        print('[填洞宏] 多洞有成果停机(断在：%s)，已播放 %d 步（保留提升）'
              % (reason, len(acts)))
        acts4, reps = _split_actions(acts)
        return {'type': 'fill_partial', 'actions': acts4,
                'rep_cells': reps, 'reason': reason,
                'stats': {k: v for k, v in stats.items()
                          if k not in ('reason', 'partial')}}
    print('[填洞宏] 多洞还原：%d 步 / %d 轮' % (len(acts),
                                             stats.get('rounds', '?')))
    return _split_actions(acts)


# ---------------------------------------------------------------------------
# 数据源 / CLI
# ---------------------------------------------------------------------------
def _capture_apply(g, a, step):
    """单步执行并返回 (ok, action5)。

    action5 = (gap, line, side, d, rep_pre)，rep_pre 为目标块移动前的位置，
    供精确回放（commit 后 location 已变）。目标选择：优先 a[4] 代表格；
    没有则取该侧首块（= 宏回放语义）。
    """
    gap, line, side, d = a[:4]
    rep = a[4] if len(a) == 5 else None
    r = _Runner.__new__(_Runner)
    r.g, r.m, r.n, r.step = g, g.m, g.n, step
    r.p = None
    tgt = r._block_at(rep) if rep is not None else None
    if tgt is None:
        tgt = r._side_first_block(gap, line, side)
    if tgt is None:
        return False, None
    g.opt(gap, line, tgt)
    final = g.try_move(d, step)
    if not final:
        for b in g.blocks:
            b.be_opted = False
        return False, None
    rep_pre = tuple(tgt.location)   # 移动前位置
    g.commit_move(final)
    return True, (gap, line, side, d, rep_pre)


def _replay_apply(g, actions, m, n, step):
    """把动作列表逐条执行到 g 上（原地修改），任一步非法返回 False。

    全部动作都会附带代表格（5 元组）；回放时按代表格精确定位分量。
    """
    for a in actions:
        ok, _ = _capture_apply(g, a, step)
        if not ok:
            return False
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
