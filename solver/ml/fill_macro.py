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
                 h=None, p=None, require_solved=True, cancel_check=None):
        self.g = game
        self.m, self.n, self.step = m, n, step
        self.verbose = verbose
        self.keep_partial = keep_partial
        self.require_solved = require_solved
        self._cc = cancel_check
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
            _chk(self._cc)
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
            _chk(self._cc)
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


class _Cancelled(Exception):
    """停止请求：cancel_check() 为 True 时由 _chk 抛出，逐层穿透长循环，
    由 GUI 入口（solve_fill_macro / solve_gap_macro）统一捕获转失败协议。"""


def _chk(cc):
    """取消检查点：cc() 为 True 立即抛 _Cancelled（cc=None 零开销）。"""
    if cc is not None and cc():
        raise _Cancelled()


def solve_single_void(coords, m, n, step, hole=None, anchor=None,
                      verbose=False, max_moves=200, keep_partial=False,
                      force_rot=None, cancel_check=None):
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
    cancel_check：停止请求（_chk 注入 Runner 的 A/B 段循环）。
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
                                  require_solved=not couple,
                                  cancel_check=cancel_check).run()
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
                              require_solved=not couple,
                              cancel_check=cancel_check).run()
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
                      max_nodes=150, couple_hook=None, cancel_check=None):
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
        _chk(cancel_check)
        nxt = deque()
        while frontier:
            s, prefix = frontier.popleft()
            _chk(cancel_check)
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


# ---------------------------------------------------------------------------
# 并行 couple 探测（2026-10-01 用户「并行轮询」思想落地）
# ---------------------------------------------------------------------------
# 用户洞察：轮询串行试 A(20s,不可解)→B(20s,不可解)→…→D(2s,可解) 时，
# 光等 A、B 就烧掉 40s。同一局面下各组 couple 并无依赖，应同时开算——
# 任一组通过聚拢度闸门立即采纳，其余丢弃；轮询一轮的耗时从「各尝试之和」
# 降为「最慢单尝试」。失败诊断（07）：第二个缺口大部分时间在等粘上接走，
# 而先处理另一个缺口剩下的洞就是完美洞——并行让可行顺序更快暴露。
_PROC_POOL = {}
# 并行开关（默认关）：实测轮询层 hook 调用毫秒~秒级，进程池 spawn(~5s)+序列化
# 开销为负收益；真正烧时间的 DFS 整形边（convoy 53s/次、粘补 15s/次）尚未
# 并行化——待接入后打开此开关（或环境变量 GATENNEA_PARALLEL=1）。
_PARALLEL_ENABLED = os.environ.get('GATENNEA_PARALLEL') == '1'


def _parallel_pool():
    """惰性常驻进程池（CPU 密集，GIL 下线程无效）。失败 → None 串行回退。"""
    if 'pool' in _PROC_POOL:
        return _PROC_POOL['pool']
    try:
        import multiprocessing as _mp
        if _mp.current_process().name != 'MainProcess':
            _PROC_POOL['pool'] = None
            return None
        pool = _mp.Pool(processes=min(8, _mp.cpu_count() or 4))
        _PROC_POOL['pool'] = pool
        return pool
    except Exception:
        _PROC_POOL['pool'] = None
        return None


def _reset_parallel_pool():
    """取消/切盘时弃掉整批任务：terminate 清孤儿，下次调用重建池。"""
    pool = _PROC_POOL.pop('pool', None)
    if pool is not None:
        try:
            pool.terminate()
        except Exception:
            pass


def _couple_worker(job):
    """子进程入口：单次 couple 尝试 + 聚拢度闸门。通过 → (h,p,acts,st)。"""
    (kind, gap_only), coords, m, n, step, h, p = job
    try:
        if kind == 'vacancy':
            from solver.ml.gap_solver import _vacancy_couple_hook
            hook = _vacancy_couple_hook(gap_only=gap_only)
            acts, st = hook(coords, m, n, step, h, p)
        else:
            acts, st = solve_single_void(coords, m, n, step, hole=h,
                                         anchor=p, keep_partial=True)
        if acts is None or not _overlap_raised(coords, m, n, step, acts):
            return None
        st = dict(st) if isinstance(st, dict) else {}
        st.pop('fail_world', None)      # 前缀动作可能不可 pickle，不回传
        return (h, p, list(acts), st)
    except Exception:
        return None


def _run_couples_parallel(tasks, hook_spec, coords, m, n, step,
                           cancel_check=None, first_only=True):
    """并发跑一批 couple 尝试。

    tasks: [(h, p), ...]（同 mod 已过滤）。
    hook_spec: ('vacancy', gap_only) 走多空位分发器；None 走填洞宏。
    first_only=True：任一通过闸门立即返回 (h,p,acts,st)，其余丢弃——
      贪心轮询语义（接受第一个可行组，下一轮重评局面）。
    first_only=False：等全部结束，收集所有通过者——DFS 节点枚举全分支
      语义（节点成本从各尝试之和降为最慢单尝试）。
    返回 (got, ran)：ran=False 表示池不可用/任务<2，调用方串行回退。
    cancel 触发 → 弃池抛 _Cancelled（不等批次烧完）。
    """
    if not (_PARALLEL_ENABLED and len(tasks) >= 2):
        return (None if first_only else []), False
    pool = _parallel_pool()
    if pool is None:
        return (None if first_only else []), False
    kind, gap_only = hook_spec if hook_spec else (None, False)
    # 单批总闸（秒）：worker 挂死/预算异常时不拖死主进程，弃池串行回退。
    # 上限 ≈ convoy 单试 2500 节点(~55s) + 粘补 15s + worker 冷启动余量。
    batch_deadline = time.time() + 100.0
    try:
        results = [pool.apply_async(
            _couple_worker,
            (((kind, gap_only), coords, m, n, step, h, p),))
            for (h, p) in tasks]
        if first_only:
            pending = list(results)
            while pending:
                _chk(cancel_check)
                if time.time() > batch_deadline:
                    _reset_parallel_pool()
                    return (None if first_only else []), False
                for ar in list(pending):
                    if not ar.ready():
                        continue
                    pending.remove(ar)
                    got = ar.get()
                    if got is not None:
                        if pending:
                            # 采纳成功即推进；同批慢任务已成孤儿占 worker，
                            # 会拖累下一批 → 弃池（下次惰性重建，spawn ~2s
                            # 远比 convoy 孤儿 50s 便宜）
                            _reset_parallel_pool()
                        return got, True
                time.sleep(0.02)
            return None, True
        out = []
        for ar in results:
            while not ar.ready():
                _chk(cancel_check)
                if time.time() > batch_deadline:
                    _reset_parallel_pool()
                    return (None if first_only else []), False
                time.sleep(0.02)
            got = ar.get()
            if got is not None:
                out.append(got)
        return out, True
    except _Cancelled:
        _reset_parallel_pool()
        raise
    except Exception:
        import traceback
        print('[并行轮询] 进程池异常，串行回退：%s'
              % traceback.format_exc(limit=1).strip().splitlines()[-1],
              file=sys.stderr)
        return (None if first_only else []), False


def solve_multi_void(coords, m, n, step, verbose=False, max_rounds=80,
                     max_attempts=400, max_shaping=2, max_nodes=150,
                     rng=None, couple_hook=None, cancel_check=None,
                     segment_cb=None, hook_spec=None):
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
    streamed = [0]

    def _stop(extra):
        """停机出口：有成果(total 非空) → 回传 partial；完全失败 → None。"""
        extra = dict(extra, end_coords=gcoords(g), streamed=streamed[0])
        if total:
            return list(total), dict(extra, partial=True)
        return None, dict(extra)

    while not g.is_solved():
        _chk(cancel_check)
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
        # 遍历 couple：洞序随机，同 mod 凸起随机序（=「随机找一组」的展开）。
        # 并行轮询优先（2026-10-01 用户思想）：全部 (h,p) 同时开算，任一通过
        # 闸门立即采纳；不可解的组不再挡住几秒内可解的组。
        h_list = list(holes)
        rng.shuffle(h_list)
        progressed = False
        tasks = [(h, p) for h in h_list for p in outside
                 if (p[0] - h[0]) % step == 0 and (p[1] - h[1]) % step == 0]
        h = p = None
        acts = stats = None
        got, ran = _run_couples_parallel(tasks, hook_spec, cur, m, n, step,
                                         cancel_check=cancel_check,
                                         first_only=True)
        if ran:
            attempts += len(tasks)
            if got is not None:
                h, p, acts, stats = got
        else:
            # 串行回退（池不可用 / 单任务）：挨个试，失败就放弃换组
            for h in h_list:
                cands = [q for q in outside
                         if (q[0] - h[0]) % step == 0
                         and (q[1] - h[1]) % step == 0]
                rng.shuffle(cands)
                for p in cands:
                    attempts += 1
                    _chk(cancel_check)
                    if couple_hook is not None:
                        acts, stats = couple_hook(cur, m, n, step, h, p)
                    else:
                        acts, stats = solve_single_void(cur, m, n, step,
                                                        hole=h, anchor=p,
                                                        keep_partial=True)
                    if acts is None:
                        acts = None
                        continue   # 该 couple 完全失败（macro 一步未动）
                    # 聚拢度闸门：只接受「回放后最佳窗口方块数提升」的产物
                    # （含 partial 有成果）；未提升视为无成果失败，无副作用换组
                    if not _overlap_raised(cur, m, n, step, acts):
                        acts = None
                        continue
                    break
                else:
                    acts = None
                    continue
                break
        # 有成果（完整填洞或 partial 提升都算）：推进到活盘
        if acts is not None:
            if not _replay_apply(g, acts, m, n, step):
                return _stop({'reason': '多洞停机：推进活盘失败',
                              'rounds': rounds,
                              'steps': len(total)})
            total.extend(acts)
            progressed = True
            if segment_cb is not None:
                try:
                    if stats.get('partial'):
                        seg = ('round%d 有成果partial(%s) 洞%s←凸%s'
                               % (rounds, stats.get('reason', '?'), h, p))
                    else:
                        seg = ('round%d 填洞 洞%s←凸%s'
                               % (rounds, h, p))
                    segment_cb(seg, list(acts))
                    streamed[0] += len(acts)
                except Exception:
                    pass   # 流式回调失败不拖垮求解
            if stats.get('partial'):
                partial_accepted += 1
                if verbose:
                    print('   round%d 有成果partial(%s) h=%s p=%s → %d 步'
                          % (rounds, stats.get('reason', '?'), h, p,
                             len(acts)))
            elif verbose:
                print('   round%d 填洞 %s 用凸起 %s → %d 步'
                      % (rounds, h, p, len(acts)))
        if progressed:
            continue
        if not progressed:
            # 贴边缺口 setup 轨道（2026-10-02 用户手解归纳）：直接 couple 全败
            # 且有洞贴窗口边缘时，走「往返捎带」机构——先推带腾通道、窗外源块
            # 就位、回程捎进洞、还原腾位；全链过段级聚拢度闸门才接受。
            for h in h_list:
                _chk(cancel_check)
                acts_e, info_e = _edge_setup_chain(
                    cur, m, n, step, h, time_budget=_EDGE_SETUP_BUDGET,
                    verbose=verbose, cancel_check=cancel_check)
                if acts_e is None:
                    if verbose:
                        print('   round%d 贴边setup 洞%s: %s'
                              % (rounds, h, info_e))
                    continue
                if not _overlap_raised(cur, m, n, step, acts_e):
                    continue
                if not _replay_apply(g, acts_e, m, n, step):
                    return _stop({'reason': '多洞停机：贴边setup推进活盘失败',
                                  'rounds': rounds, 'steps': len(total)})
                total.extend(acts_e)
                progressed = True
                p = None
                if segment_cb is not None:
                    try:
                        segment_cb('round%d 贴边setup(往返捎带) 洞%s' % (rounds, h),
                                   list(acts_e))
                        streamed[0] += len(acts_e)
                    except Exception:
                        pass   # 流式回调失败不拖垮求解
                if verbose:
                    print('   round%d 贴边setup 洞%s → %d 步'
                          % (rounds, h, len(acts_e)))
                break
            if progressed:
                continue
        if not progressed:
            # 带移让位＋粘上接走链（2026-10-02 用户手解 07 归纳＋幽灵块
            # 追踪提案）：普通 couple 与贴边 setup 全败后，对每对 (h,p)
            # 试三段机构——洞带让位（幽灵块追踪洞身份）→ 源接应平移 →
            # 带回位把源捎进原洞。内部已含真盘整链重放 + 聚拢度闸门。
            for h, p in tasks:
                _chk(cancel_check)
                acts_b, info_b = _band_shift_chain(
                    cur, m, n, step, h, p, verbose=verbose,
                    cancel_check=cancel_check)
                if acts_b is None:
                    if verbose:
                        print('   round%d 带移链 洞%s←凸%s: %s'
                              % (rounds, h, p, info_b))
                    continue
                if not _replay_apply(g, acts_b, m, n, step):
                    return _stop({'reason': '多洞停机：带移链推进活盘失败',
                                  'rounds': rounds, 'steps': len(total)})
                total.extend(acts_b)
                progressed = True
                if segment_cb is not None:
                    try:
                        segment_cb('round%d 带移让位(幽灵块追踪) 洞%s←凸%s'
                                   % (rounds, h, p), list(acts_b))
                        streamed[0] += len(acts_b)
                    except Exception:
                        pass   # 流式回调失败不拖垮求解
                if verbose:
                    print('   round%d 带移链 洞%s←凸%s → %d 步'
                          % (rounds, h, p, len(acts_b)))
                break
            if progressed:
                continue
        if not progressed and max_shaping:
            # couple 全败 → 有限中性整形预演：≤max_shaping 步不降聚拢度的
            # 整带动作后直接提升 / 解锁 couple（覆盖「需先揉形再填」卡点）
            plan = _shaping_progress(cur, m, n, step, rng, _ov,
                                     max_shaping, max_nodes,
                                     couple_hook=couple_hook,
                                     cancel_check=cancel_check)
            if plan is not None:
                if not _replay_apply(g, plan, m, n, step):
                    return _stop({'reason': '多洞停机：整形预演推进活盘失败',
                                  'rounds': rounds,
                                  'steps': len(total)})
                total.extend(plan)
                shaping_used += 1
                progressed = True
                if segment_cb is not None:
                    try:
                        segment_cb('round%d 中性整形预演' % rounds,
                                   list(plan))
                        streamed[0] += len(plan)
                    except Exception:
                        pass
                if verbose:
                    print('   round%d 中性整形预演(%d步) → 收下'
                          % (rounds, len(plan)))
        if not progressed:
            # 完美洞诊断（用户框架）：8 邻有缺口=不完美洞，标准切割必败
            imp = [h for h in holes if hole_gaps(cur, h)]
            why = ('多洞停机：所有couple与≤%d步整形预演均无成果'
                   '(算法固有缺陷)' % max_shaping)
            if imp:
                why += '；不完美洞%d个(8邻有缺口,需临时粘补/setup)：%s' % (
                    len(imp), sorted(imp))
            return _stop({'reason': why,
                          'rounds': rounds, 'attempts': attempts,
                          'holes_left': len(holes),
                          'outside_left': len(outside),
                          'imperfect_holes': len(imp),
                          'steps': len(total)})
    if not g.is_solved():
        return _stop({'reason': '多洞停机：窗内无洞但未还原(含缺口形态?)',
                      'rounds': rounds, 'steps': len(total)})
    return (total, {'steps': len(total), 'rounds': rounds,
                    'partial_accepted': partial_accepted,
                    'shaping_used': shaping_used,
                    'streamed': streamed[0],
                    'end_coords': gcoords(g),
                    'secs': round(time.time() - t0, 3), 'multi': True})


# ---------------------------------------------------------------------------
# 移形换位宏（紧凑盘专用，2026-10-01 用户「2-4-4」三档教学参数化）
# ---------------------------------------------------------------------------
def _swap_fill(coords, m, n, step, max_nodes=40000, verbose=False,
               cancel_check=None):
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
        _chk(cancel_check)
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


def _compact_rescue(coords, m, n, step, why='', progress_callback=None,
                    cancel_check=None):
    """紧凑盘移形换位救援：常规链全败后的最后手段（2026-10-01）。"""
    if not (m <= 2 * step and n <= 2 * step):
        return None
    _emit(progress_callback, '移形换位', 0,
          '紧凑盘双向BFS（常规链失败:%s）' % why[:30])
    import time as _t
    _T0[0] = _t.time()
    acts = _swap_fill(coords, m, n, step, cancel_check=cancel_check)
    if acts is None:
        return None
    print('[移形换位] 常规链失败(%s)，换位机动 %d 步全解'
          % (why[:40], len(acts)))
    return _split_actions(acts)


# ---------------------------------------------------------------------------
# 带移盖洞宏
# ---------------------------------------------------------------------------
def _step_split_plan(coords0, m, n, step, plan):
    """「距离语义」plan（5 元组第 5 位=移动格数）→ 标准 step 动作序列
    （第 5 位=rep_cell 坐标，每步 step 距离）。

    带移盖洞宏的内部产物用 try_move_ex(dir, 格数) 表达 1~2*step 位移，
    与宏回放/GUI 的「step 距离+代表格」语义冲突（2-6-7 回归实证：
    rep_cell=int 使 GUI 解包崩溃、2*step 步回放走错）。这里逐段分解：
    整段先在副本上执行拿移动集与终局，再按 step 子步逐个引擎验证重放，
    终局与整段不一致即放弃（返回 None，调用方换下一候选）。
    """
    _DIRV = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
    g = build_game(coords0, m, n)          # 子步执行主副本
    out = []
    for gap, line, side, d, dist in plan:
        n_sub = max(1, int(dist) // step)
        st = ((lambda r, c: r <= line) if side == 'above'
              else (lambda r, c: r > line)) if gap == 'h' else \
             ((lambda r, c: c <= line) if side == 'left'
              else (lambda r, c: c > line))
        # 整段参照：独立副本拿 moved 集与终局
        gr = build_game(gcoords(g), m, n)
        tgt = None
        for blk in gr.blocks:
            if st(*blk.location):
                tgt = blk
                break
        if tgt is None:
            return None
        gr.opt(gap, line, tgt)
        final, _why = gr.try_move_ex(d, dist)
        if not final:
            return None
        moved_pre = frozenset(tuple(b.location) for b in gr.blocks
                              if b.be_opted)
        gr.commit_move(final)
        end_ref = frozenset(gcoords(gr))
        # 子步执行（在主副本上）
        rep0 = min(moved_pre)
        dr, dcn = _DIRV[d]
        for k in range(n_sub):
            rr, cc = rep0[0] + dr * step * k, rep0[1] + dcn * step * k
            tb = None
            for blk in g.blocks:
                if tuple(blk.location) == (rr, cc):
                    tb = blk
                    break
            if tb is None:
                return None
            g.opt(gap, line, tb)
            fin = g.try_move(d, step)
            if not fin:
                for b in g.blocks:
                    b.be_opted = False
                return None
            g.commit_move(fin)
            out.append((gap, line, side, d, (rr, cc)))
        if frozenset(gcoords(g)) != end_ref:
            return None
    return out


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
                # 动作列表：a1 暴力试出的参数回填；出口统一转标准 step
                # 动作（第 5 位=rep_cell；距离语义在回放/GUI 端不兼容）
                acts = []
                if need_a1:
                    acts.append((gap1, line1, side1, dc1, rep1))
                acts.append((gap2, line2, side2, dc2, rep2))
                acts.append((gap2, line3, side3, dc3, rep2))
                std = _step_split_plan(coords, m, n, step, acts)
                if std is None:
                    continue
                return std, s_net
    return None, None


def _convoy_fill(coords, m, n, step, h, p, max_prep=2, max_pickup=4,
                 max_depth=16, max_nodes=2500, max_comp=None, verbose=False,
                 progress_callback=None, cancel_check=None):
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
        _chk(cancel_check)
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
                allow_appr=None, verbose=False, progress_callback=None,
                cancel_check=None):
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
        # 契约与全函数一致：主路径一律 (动作或None, 节点数) 元组——
        # 裸 None 会让调用方 `racts, used = _rigid_fill(...)` 解包炸
        return None, 0                       # 形状不全等 → 刚体填不进
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
        _chk(cancel_check)
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


# ---------------------------------------------------------------------------
# 临时粘一下（共轭让位，2026-10-01 用户框架）
#
# 洞能否直接填要看周围 8 格（不只 4 邻）：8 邻有空位（缺口）= 不完美洞，
# 沿洞侧切割时一侧断成两个分量，标准宏必败。对策 = 「临时粘一下」：
# 把挡路的带子让位（粘上缺口），腾出通道做标准填入，再原路复位——
# 复位回来的带子往往顺带填掉大片洞（2-7-8 实证，13 步全解）。
# ---------------------------------------------------------------------------
_PASTE_DIRS = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}
_OPP_DIR = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}


def hole_gaps(coords, hole):
    """洞的 8 邻空位（缺口）。非空 = 不完美洞：标准切割/选中必败，
    需要先「临时粘一下」。用户 2026-10-01 框架的实现。"""
    r, c = hole
    return [(r + dr, c + dc)
            for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            if (dr or dc) and (r + dr, c + dc) not in coords]


# ---------------------------------------------------------------------------
# 贴边缺口 setup 轨道（2026-10-02，用户手解失败06 段2 归纳的机构）
#
# 洞贴窗口边缘时，直接补缺链/填洞宏会产出「填上缺口但整批块搬出窗外」的
# 灾难方案。用户正解的机构（往返捎带）：
#   pre    腾位前缀（0~1 个平移，可选）：给骨架清路
#   T_last 骨架平移：带内块整体推向源侧，腾出带上通道（产物与就位源相邻
#          则并入同分量）
#   P      就位：把窗外源块推到带端点 slot（洞沿带轴向源侧 dist 处）
#   C      回程：T_last 的逆（同缝同侧反向同距离）——源块随分量被捎进洞
#   R      还原：腾位前缀逆序逆动作
# 全链按段级聚拢度闸门验收（用户 2026-10-01 原则：结束比开始提升即有效，
# 中途不管）。
# ---------------------------------------------------------------------------

_EDGE_SETUP_BUDGET = 6.0   # 单洞 setup 搜索时间预算（秒）

# 宏级 DFS 兜底的总时间预算（秒）。2026-10-02 用户拍板：算不出来的局面
# 尽早发现、发现就停——死局不在整形边（粘上接走/刚体/粘补）上磨到
# 200+ 秒。可解但贪心选错序的局通常远快于此；死局到点即止损。
_SEARCH_TIME_BUDGET = 60.0


def _es_side_blocks(g, gap, line, side):
    """缝 line 某侧的全部块（按坐标判定，不分量）。"""
    if gap == 'v':
        sel = (lambda p: p[1] > line) if side == 'right' \
            else (lambda p: p[1] <= line)
    else:
        sel = (lambda p: p[0] > line) if side == 'below' \
            else (lambda p: p[0] <= line)
    return [x for x in g.blocks if sel(tuple(x.location))]


def _es_probe_run(g, gap, line, side, rep0, d, times, step, cancel_check=None):
    """在 g 上从 rep0 块选中分量连滑 times 个 step（多格滑的忠实语义：
    同一分量连续平移）。成功返回 (True, sub_acts)；中途任一步失败返回
    (False, [])——g 已部分推进，调用方必须弃盘（本函数只用于副本）。"""
    blk = None
    for x in g.blocks:
        if tuple(x.location) == tuple(rep0):
            blk = x
            break
    if blk is None:
        return False, []
    sub = []
    for _ in range(times):
        _chk(cancel_check)
        g.opt(gap, line, blk)
        fin = g.try_move(d, step)
        if not fin:
            return False, []
        sub.append((gap, line, side, d, tuple(blk.location)))   # 移动前坐标
        g.commit_move(fin)
    return True, sub


def _es_slide(g, gap, line, side, d, times, step, acts,
              cancel_check=None, prefer=None):
    """整段原子滑动：从侧内挑一个能连滑 times 个 step 的分量（先在副本上
    试探，成功才提交真盘），逐 step 记录带 rep_cell 的动作。
    成功 True；无可滑分量 False（g 不动）。prefer：优先尝试的代表块。"""
    _chk(cancel_check)
    cands = _es_side_blocks(g, gap, line, side)
    if prefer is not None:
        cands.sort(key=lambda x: 0 if tuple(x.location) == tuple(prefer) else 1)
    tried_comps = set()
    for x in cands:
        g.opt(gap, line, x)
        comp = frozenset(tuple(b.location) for b in g.blocks if b.be_opted)
        for b in g.blocks:
            b.be_opted = False
        if comp in tried_comps:
            continue
        tried_comps.add(comp)
        # 副本试探：该分量能否连滑全程
        gt = build_game(gcoords(g), g.m, g.n)
        ok, sub = _es_probe_run(gt, gap, line, side,
                                tuple(x.location), d, times, step)
        if not ok:
            continue
        # 真盘逐 step 重放
        good = True
        for a5 in sub:
            tg = None
            for bb in g.blocks:
                if tuple(bb.location) == a5[4]:
                    tg = bb
                    break
            if tg is None:
                good = False
                break
            g.opt(gap, line, tg)
            fin = g.try_move(d, step)
            if not fin:
                good = False
                break
            g.commit_move(fin)
            acts.append(a5)
        if good:
            return True
    return False


def _edge_setup_chain(coords, m, n, step, hole, time_budget=_EDGE_SETUP_BUDGET,
                      verbose=False, cancel_check=None):
    """贴边缺口「往返捎带」setup 轨道。返回 (acts5, info) 或 (None, reason)。

    洞贴窗口边缘、直接填会灾难时：先把带内块整体推向源侧腾出通道
    （T_last），窗外源块就位到带端点 slot（P），再以骨架的逆动作回程把
    源块捎进洞（C），最后还原腾位（R）。全链过段级聚拢度闸门才返回。
    """
    coords = frozenset(coords)
    reg, ov0, holes0, out0 = window_of(coords, m, n, step)
    r0, c0, (wh, ww) = reg
    r1, c1 = r0 + wh - 1, c0 + ww - 1
    dirs = []
    if hole[0] == r0:
        dirs.append('w')
    if hole[0] == r1:
        dirs.append('s')
    if hole[1] == c0:
        dirs.append('a')
    if hole[1] == c1:
        dirs.append('d')
    if not dirs:
        return None, '洞不贴边'
    deadline = time.time() + time_budget
    opp = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}
    tried = 0
    for d in dirs:
        horizontal = d in ('w', 's')
        band_fixed = hole[0] if horizontal else hole[1]
        band_var0 = hole[1] if horizontal else hole[0]
        b_lo, b_hi = (c0, c1) if horizontal else (r0, r1)
        gap_band = 'h' if horizontal else 'v'
        # 骨架缝（side → line 配对，保证带行/列在侧内）：
        #   h above: rows≤L 含带行 → L=band_fixed；h below: rows>L → L=band_fixed-1
        #   v left : cols≤L 含带列 → L=band_fixed；v right: cols>L → L=band_fixed-1
        side_lines = ((('above', band_fixed), ('below', band_fixed - 1))
                      if horizontal else
                      (('left', band_fixed), ('right', band_fixed - 1)))
        for bd in (('d', 'a') if horizontal else ('s', 'w')):
            # bd = 源侧方向（洞沿带轴向 bd 出窗外）
            for k in (1, 2, 3, 4):
                dist_c = k * step
                v_slot = band_var0 + (dist_c if bd in ('d', 's') else -dist_c)
                if b_lo <= v_slot <= b_hi:
                    continue    # slot 未出窗外，源位不成立
                slot = (band_fixed, v_slot) if horizontal \
                    else (v_slot, band_fixed)
                for side, sline in side_lines:
                    _chk(cancel_check)
                    if time.time() > deadline:
                        return None, ('贴边setup：%.0fs 预算内未找到'
                                      '（试 %d 组）' % (time_budget, tried))
                    tried += 1
                    g = build_game(coords, m, n)
                    acts = []
                    # ---- T1：垂直推出带行路径段（把洞到源侧窗缘的带内块
                    #      整列推出带，产物落在窗外邻带）----
                    if horizontal:
                        t1 = ('v', band_var0,
                              'right' if bd == 'd' else 'left', 'w', 1)
                    else:
                        t1 = ('h', band_var0,
                              'below' if bd == 's' else 'above', 'a', 1)
                    did_t1 = _es_slide(g, t1[0], t1[1], t1[2], t1[3], t1[4],
                                       step, acts, cancel_check)
                    # ---- T2：T1 产物横移对齐（可选）——使 C 时产物与带行块
                    #      同分量、R1 能对齐还原。T1 成功而 T2 失败 → C 拉不
                    #      回，弃该骨架。----
                    did_t2 = False
                    if did_t1:
                        if horizontal:
                            t2 = ('h', band_fixed - 1, 'above',
                                  'a' if bd == 'd' else 'd', 1)
                        else:
                            t2 = ('v', band_fixed - 1, 'left',
                                  'w' if bd == 's' else 's', 1)
                        did_t2 = _es_slide(g, t2[0], t2[1], t2[2], t2[3],
                                           t2[4], step, acts, cancel_check)
                        if not did_t2:
                            continue
                    # ---- T_last：带行块推向源侧 dist_c（腾出通道）----
                    if not _es_slide(g, gap_band, sline, side, bd,
                                     k, step, acts, cancel_check):
                        continue
                    snap = gcoords(g)
                    # ---- P：窗外源块就位到 slot（与 slot 同垂直轴）----
                    if horizontal:
                        src_axis, other = 1, 0
                    else:
                        src_axis, other = 0, 1
                    srcs = [q for q in snap
                            if q[src_axis] == v_slot
                            and q[other] != band_fixed]
                    for src in srcs:
                        if horizontal:
                            dist_p = abs(src[0] - band_fixed)
                            if dist_p < step or dist_p % step:
                                continue
                            pd = 's' if src[0] < band_fixed else 'w'
                            seams = ((('v', v_slot - 1, 'right')
                                      if v_slot > b_hi else
                                      ('v', v_slot, 'left')),)
                        else:
                            dist_p = abs(src[1] - band_fixed)
                            if dist_p < step or dist_p % step:
                                continue
                            pd = 'd' if src[1] < band_fixed else 'a'
                            seams = ((('h', v_slot - 1, 'below')
                                      if v_slot > b_hi else
                                      ('h', v_slot, 'above')),)
                        for pseam in seams:
                            # P/C/R 全部在「骨架前段后」的副本上试
                            g2 = build_game(snap, m, n)
                            acts2 = list(acts)
                            if not _es_slide(g2, pseam[0], pseam[1],
                                             pseam[2], pd, dist_p // step,
                                             step, acts2, cancel_check,
                                             prefer=src):
                                continue
                            if slot not in gcoords(g2):
                                continue
                            # ---- C：骨架逆，把源捎进洞 ----
                            if not _es_slide(g2, gap_band, sline, side,
                                             opp[bd], k, step, acts2,
                                             cancel_check, prefer=slot):
                                continue
                            if hole not in gcoords(g2):
                                continue
                            # ---- R1/R2：T2、T1 逆序还原 ----
                            okr = True
                            if did_t2:
                                if not _es_slide(g2, t2[0], t2[1], t2[2],
                                                 opp[t2[3]], t2[4], step,
                                                 acts2, cancel_check):
                                    okr = False
                            if okr and did_t1:
                                if not _es_slide(g2, t1[0], t1[1], t1[2],
                                                 opp[t1[3]], t1[4], step,
                                                 acts2, cancel_check):
                                    okr = False
                            if not okr:
                                continue
                            # ---- 段级聚拢度闸门 ----
                            if not _overlap_raised(coords, m, n, step,
                                                   acts2):
                                continue
                            if verbose:
                                print('   [贴边setup] 洞%s edge=%s '
                                      'T1=%s T2=%s 骨架=%s·L%s·%s·%s·%d格 '
                                      'P=%s %s %d格 → %d 步'
                                      % (hole, d,
                                         t1 if did_t1 else None,
                                         t2 if did_t2 else None,
                                         gap_band, sline, side, bd, dist_c,
                                         pseam, pd, dist_p, len(acts2)))
                            return list(acts2), {
                                'hole': hole, 'edge': d,
                                'skeleton': (gap_band, sline, side, bd,
                                             dist_c),
                                'T1': t1 if did_t1 else None,
                                'T2': t2 if did_t2 else None,
                                'ov0': ov0, 'tries': tried}
    return None, '贴边setup：预算 %d 组内未找到' % tried


# ---------------------------------------------------------------------------
# 带移让位＋粘上接走链（2026-10-02 用户手解 07 归纳 + 幽灵块追踪提案）
# ---------------------------------------------------------------------------
_BAND_SHIFT_BUDGET = 6.0   # 单洞带移链搜索时间预算（秒）

_SIDE_SEAMS = (   # (gap, line, side) 组合：side 含 line+1 那行/列
    ('v', lambda q: (('v', q[1], 'left'), ('v', q[1] - 1, 'right'))),
    ('h', lambda q: (('h', q[0], 'above'), ('h', q[0] - 1, 'below'))),
)


def _hole_band_seams(hole):
    """过洞的 4 条带缝候选（side 均含洞所在行/列）。"""
    return [('v', hole[1], 'left'), ('v', hole[1] - 1, 'right'),
            ('h', hole[0], 'above'), ('h', hole[0] - 1, 'below')]


def _src_seams(p, axis):
    """源接应的缝候选：p 的行/列贴缝两选，side 取含 p 的那侧。

    axis=0 → 垂直平移（v 缝）；axis=1 → 水平平移（h 缝）。
    返回 [(gap, line, side)]。"""
    if axis == 1:
        return [('h', p[0], 'above'), ('h', p[0] - 1, 'below')]
    return [('v', p[1], 'left'), ('v', p[1] - 1, 'right')]


def _band_shift_chain(coords, m, n, step, hole, p_src,
                      time_budget=_BAND_SHIFT_BUDGET,
                      verbose=False, cancel_check=None):
    """带移让位＋粘上接走链。返回 (acts5, info) 或 (None, reason)。

    适用：洞 h 与窗外凸起 p 同 mod、但普通填洞过不去（途中块/缺口挡路）。
    用户机构（失败07 步1-4 解码实测）：
      1) 洞带让位：含洞邻块的整带沿缝法线平移 k*step——洞被挤到带外缘
         h'，身份随带走。追踪用「幽灵块」（用户 2026-10-02 提案）：在洞位
         临时放一个只在内存中的块，跟分量移动，段末撤掉——把空格身份
         推理变成引擎原生的实体移动追踪，且幽灵块占位天然防止让位途中
         洞被误填。
      2) 源接应平移：p 所在带沿法线平移 |h'-p|，把 p 送进 h'——p 落位即
         与洞带连通（＝「粘上」，无需显式粘补）。
      3) 洞带回位：让位的逆平移——p 随分量被捎进原洞。
    幽灵块只当追踪器、永不当裁判（用户风险提醒 2026-10-02）：幽灵盘只
    用于让位段读洞身份；让位/接应/回位三段全部在真盘执行，最终整链在
    干净盘重放验证。成功判据 = 原洞位被填 ＋ 聚拢度闸门（防搅盘解；
    链终态窗内块数比链前恰多 1 = 填上的那洞）。
    """
    coords = frozenset(coords)
    deadline = time.time() + time_budget
    opp = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}
    perp = {'v': ('s', 'w'), 'h': ('d', 'a')}
    tried = 0
    for gap_b, line_b, side_b in _hole_band_seams(hole):
        # 洞带分量代表块：洞的 4 邻实块（它们必属洞带），逐个当 rep0 试
        nbs = [q for q in ((hole[0] - 1, hole[1]), (hole[0] + 1, hole[1]),
                           (hole[0], hole[1] - 1), (hole[0], hole[1] + 1))
               if q in coords]
        for d in perp[gap_b]:
            for k in (1, 2, 3, 4):
                _chk(cancel_check)
                if time.time() > deadline:
                    return None, ('带移链：%.0fs 预算内未找到（试 %d 组）'
                                  % (time_budget, tried))
                # ---- 幽灵盘：让位段追踪洞身份 ----
                gg = build_game(coords | {hole}, m, n)
                ghost = None
                for b in gg.blocks:
                    if tuple(b.location) == tuple(hole):
                        ghost = b
                        break
                if ghost is None:
                    continue
                rep0 = None
                ok_g, _sub_g = False, []
                for nb in nbs:   # 邻块逐个试：命中含幽灵块的分量即成
                    ok_g, _sub_g = _es_probe_run(
                        gg, gap_b, line_b, side_b, nb, d, k, step,
                        cancel_check)
                    if ok_g:
                        rep0 = nb
                        break
                    gg = build_game(coords | {hole}, m, n)   # 弃半推进盘
                    for b in gg.blocks:
                        if tuple(b.location) == tuple(hole):
                            ghost = b
                            break
                if not ok_g or rep0 is None:
                    continue
                h_new = tuple(ghost.location)
                if h_new == tuple(hole):
                    continue          # 幽灵块没动 → 洞不在该带运动路径上
                # ---- 真盘让位（幽灵块只在追踪盘存在，真盘从无幽灵）----
                g1 = build_game(coords, m, n)
                ok1, sub1 = _es_probe_run(g1, gap_b, line_b, side_b,
                                          rep0, d, k, step, cancel_check)
                if not ok1:
                    continue          # 幽灵盘能走真盘不能 → 保守拒绝
                tried += 1
                # ---- 源接应（粘上接走）：p 净位移 delta 到 h' ----
                # 模式A（已粘连）：p 所在分量直接平移 delta；
                # 模式B（用户 07 手解步2-3）：p 独立分量时，邻近分量先沿
                #   -delta 平移「贴」上 p（p 粘进该分量），再沿 +delta 平移
                #   「带回」——p 随分量被送到 h'。
                delta = (h_new[0] - p_src[0], h_new[1] - p_src[1])
                axis = 0 if delta[0] else (1 if delta[1] else None)
                if axis is None or delta[axis] % step or abs(delta[axis]) > 6 * step:
                    continue
                k2 = abs(delta[axis]) // step
                d2 = ('s' if delta[0] > 0 else 'w') if axis == 0 else \
                     ('d' if delta[1] > 0 else 'a')
                dr2, dc2 = _DIRS[d2]
                got2 = None
                for gap2, line2, side2 in _src_seams(p_src, axis):
                    _chk(cancel_check)
                    # 模式A：p 所在分量直接平移（rep=p → opt 选中 p 的分量）
                    gA = build_game(gcoords(g1), m, n)
                    okA, subA = _es_probe_run(gA, gap2, line2, side2,
                                              tuple(p_src), d2, k2, step,
                                              cancel_check)
                    if okA and (p_src[0] + dr2 * k2 * step,
                                p_src[1] + dc2 * k2 * step) == h_new:
                        got2 = ('A', gA, subA, tuple(p_src))
                        break
                    # 模式B：邻近分量反向平移贴上 p → 正向平移带回
                    # （枚举侧内连通分量为 C，复用分量去重）
                    side_sel = (lambda q: q[0] <= line2 if side2 == 'above'
                                else q[0] > line2) if gap2 == 'h' else \
                               (lambda q: q[1] <= line2 if side2 == 'left'
                                else q[1] > line2)
                    tried_comps = set()
                    for repC0 in sorted({tuple(b.location)
                                         for b in g1.blocks
                                         if side_sel(tuple(b.location))
                                         and tuple(b.location) != tuple(p_src)}):
                        _chk(cancel_check)
                        gB = build_game(gcoords(g1), m, n)
                        blkC0 = None
                        for b in gB.blocks:
                            if tuple(b.location) == repC0:
                                blkC0 = b
                                break
                        if blkC0 is None:
                            continue
                        gB.opt(gap2, line2, blkC0)
                        comp0 = frozenset(tuple(b.location) for b in gB.blocks
                                          if b.be_opted)
                        for b in gB.blocks:
                            b.be_opted = False
                        if comp0 in tried_comps or tuple(p_src) in comp0:
                            continue   # 重复分量 / 已含 p（模式 A 已试）
                        tried_comps.add(comp0)
                        ok_t, sub_t = _es_probe_run(gB, gap2, line2, side2,
                                                    repC0, opp[d2], k2, step,
                                                    cancel_check)
                        if not ok_t:
                            continue
                        # 贴上判定：p 与被移分量连通（p 在其 opt 分量内）
                        drT, dcT = _DIRS[opp[d2]]
                        cand = (repC0[0] + drT * k2 * step,
                                repC0[1] + dcT * k2 * step)
                        blkC = None
                        for b in gB.blocks:
                            if tuple(b.location) == cand:
                                blkC = b
                                break
                        if blkC is None:
                            continue
                        gB.opt(gap2, line2, blkC)
                        stuck = any(b.be_opted
                                    and tuple(b.location) == tuple(p_src)
                                    for b in gB.blocks)
                        for b in gB.blocks:
                            b.be_opted = False
                        if not stuck:
                            continue    # 没贴上 p → 换分量
                        # 带回：从 C 新代表位沿 d2 平移 k2 → p 落 h'
                        ok_b, sub_b = _es_probe_run(gB, gap2, line2, side2,
                                                    cand, d2, k2, step,
                                                    cancel_check)
                        if ok_b:
                            got2 = ('B', gB, list(sub_t) + list(sub_b), cand)
                            break
                    if got2 is not None:
                        break
                if got2 is None:
                    continue
                mode2, g2, sub2, repC_end = got2
                # ---- 洞带回位：p 随分量捎进原洞 ----
                g3 = build_game(gcoords(g2), m, n)
                ok3, sub3 = _es_probe_run(g3, gap_b, line_b, side_b,
                                          tuple(hole), opp[d], k, step,
                                          cancel_check)
                if not ok3:
                    continue
                if not any(tuple(b.location) == tuple(hole)
                           for b in g3.blocks):
                    continue      # 原洞位没被填上 → 该组参数无效
                all_acts = list(sub1) + list(sub2) + list(sub3)
                # ---- 终裁：干净盘整链重放 + 聚拢度闸门 ----
                gfull = build_game(coords, m, n)
                if not _replay_apply(gfull, all_acts, m, n, step):
                    continue
                if not _overlap_raised(coords, m, n, step, all_acts):
                    continue
                if verbose:
                    print('   [带移链] 洞%s←凸%s: 让位(%s,%d,%s,%s,%d格)'
                          '→洞%s 接应%s(%s,%d,%s,%s,%d格) 回位 → %d 步'
                          % (hole, p_src, gap_b, line_b, side_b, d,
                             k * step, h_new, mode2, gap2, line2, side2, d2,
                             k2 * step, len(all_acts)))
                return all_acts, {
                    'hole': hole, 'src': p_src, 'h_shifted': h_new,
                    'band': (gap_b, line_b, side_b, d, k * step),
                    'relay': (mode2, gap2, line2, side2, d2, k2 * step),
                    'tries': tried}
    return None, '带移链：预算 %d 组内未找到' % tried


def _enum_paste_moves(coords, m, n, step, min_size=3):
    """枚举全部合法单步让位（含同缝多分量）→ [(act5, comp, mv, nxt)]。

    comp=被移分量坐标集，mv=移动后坐标集，nxt=让位后整盘坐标。
    """
    out = []
    rows = [r for r, _c in coords]
    cols = [c for _r, c in coords]
    for gap in ('h', 'v'):
        lines = (range(min(rows) - 2, max(rows) + 3) if gap == 'h'
                 else range(min(cols) - 2, max(cols) + 3))
        dirs = ('a', 'd') if gap == 'h' else ('w', 's')
        for line in lines:
            for side in (('above', 'below') if gap == 'h'
                         else ('left', 'right')):
                if gap == 'h':
                    sel = frozenset(
                        q for q in coords
                        if (q[0] <= line if side == 'above' else q[0] > line))
                else:
                    sel = frozenset(
                        q for q in coords
                        if (q[1] <= line if side == 'left' else q[1] > line))
                if not sel or sel == coords:
                    continue
                for comp in _comps_ml(sel):
                    rest = coords - comp
                    if not rest or len(comp) < min_size:
                        continue
                    for d in dirs:
                        dr, dc = _PASTE_DIRS[d]
                        ok = True
                        for k in range(1, step + 1):
                            mvk = frozenset((q[0] + dr * k, q[1] + dc * k)
                                            for q in comp)
                            if mvk & rest or not _connected_ml(rest | mvk):
                                ok = False
                                break
                        if not ok:
                            continue
                        mv = frozenset((q[0] + dr * step, q[1] + dc * step)
                                       for q in comp)
                        out.append(((gap, line, side, d, min(comp)),
                                    comp, mv, rest | mv))
    return out


def _paste_relay(coords, m, n, step, max_pairs=400, budget=15.0, min_w=3,
                 verbose=False, progress_callback=None, cancel_check=None):
    """「临时粘一下」整段搜索：让位 → 标准填入 →（原路复位）。

    枚举让位动作（分量 ≥min_w），在让位后局面跑现有 couple 宏；
    两种产物都验收：①复位版本（带子回来常顺带填洞）②不复位版本。
    整段回放后聚拢度严格提升才收。返回 (acts, used)（acts=None 无推进）。
    """
    t0 = time.time()
    _reg, ov0, _h0, _o0 = window_of(coords, m, n, step)
    W = _enum_paste_moves(coords, m, n, step, min_size=min_w)
    if verbose:
        print('  [临时粘补] 让位候选 %d（分量≥%d）' % (len(W), min_w))
    best = None
    tried = 0
    for (a5w, comp, mv, st1) in W:
        if cancel_check is not None and cancel_check():
            raise _Cancelled()
        if time.time() - t0 > budget or tried >= max_pairs:
            break
        _r1, _ov1, holes, outside = window_of(st1, m, n, step)
        for h in sorted(holes):
            for p in sorted(outside):
                if tried >= max_pairs or time.time() - t0 > budget:
                    break
                if ((p[0] - h[0]) % step or (p[1] - h[1]) % step):
                    continue
                tried += 1
                cacts, _st = solve_single_void(st1, m, n, step, hole=h,
                                               anchor=p, keep_partial=True)
                if not cacts:
                    continue
                g1 = build_game(st1, m, n)
                if not _replay_apply(g1, cacts, m, n, step):
                    continue
                after_c = frozenset(gcoords(g1))
                # ② 不复位版本（段级验收：段末聚拢度 > 段首）
                ov1b = window_of(after_c, m, n, step)[1]
                if ov1b > ov0 and (best is None or ov1b > best[1]):
                    best = ([a5w] + list(cacts), ov1b, after_c)
                # ① 复位版本：原路退回让位步
                g2 = build_game(coords, m, n)
                full_inv = ([a5w] + list(cacts)
                            + [(a5w[0], a5w[1], a5w[2], _OPP_DIR[a5w[3]],
                                min(mv))])
                if _replay_apply(g2, full_inv, m, n, step):
                    after2 = frozenset(gcoords(g2))
                    ov2 = window_of(after2, m, n, step)[1]
                    if ov2 > ov0 and (best is None or ov2 > best[1]):
                        best = (full_inv, ov2, after2)
    if verbose:
        print('  [临时粘补] %.1fs 尝试 %d → %s'
              % (time.time() - t0, tried,
                 ('ov→%d (%d步)' % (best[1], len(best[0]))) if best
                 else '无推进'))
    if best:
        if progress_callback is not None:
            _emit(progress_callback, '临时粘补', tried,
                  '推进：聚拢度→%d（%d 步）' % (best[1], len(best[0])))
        return best[0], tried
    return None, tried


def solve_multi_search(coords, m, n, step, couple_hook=None,
                       node_budget=400, reshape_budget=3, verbose=False,
                       progress_callback=None, cancel_check=None,
                       hook_spec=None, time_budget=None):
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
    time_budget：总时间预算（秒，2026-10-02 用户拍板「算不出来尽早发现、
    发现就停」）——死局不在整形边上磨到天荒地老；超时即停，返回已有
    成果。None = 用 _SEARCH_TIME_BUDGET 默认值。

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
    if time_budget is None:
        time_budget = _SEARCH_TIME_BUDGET
    t0 = time.time()

    def _default_hook(cur, m_, n_, s_, h, p):
        return solve_single_void(cur, m_, n_, s_, hole=h, anchor=p,
                                 keep_partial=True)
    hook = couple_hook or _default_hook

    def _couples(cur):
        _reg, _ov, holes, outside = window_of(cur, m, n, step)
        out = []
        tasks = [(h, p) for h in holes for p in outside
                 if (p[0] - h[0]) % step == 0 and (p[1] - h[1]) % step == 0]
        # 并行枚举（2026-10-01）：DFS 每节点要对全 couple 跑 hook，串行时
        # 单节点成本=各尝试之和（数十秒），并行后=最慢单尝试。
        got, ran = _run_couples_parallel(tasks, hook_spec, cur, m, n, step,
                                         cancel_check=cancel_check,
                                         first_only=False)
        if ran:
            return [g[2] for g in got]
        for h, p in tasks:
            if _tb_over():
                state['timeout'] = True
                break
            acts, _st = hook(cur, m, n, step, h, p)
            if acts is None:
                continue
            if not _overlap_raised(cur, m, n, step, acts):
                continue
            out.append(acts)
        return out

    state = {'nodes': 0, 'best': [], 'exhausted': False, 'seen': set(),
             'convoy_left': 8000, 'paste_left': 2, 'timeout': False}

    def _tb_over():
        """总时间预算检查（尽早发现就停，2026-10-02 用户拍板）。"""
        return time.time() - t0 >= time_budget

    def _reshape_edges(cur):
        """整形边（惰性）：①带移盖洞 ②粘上接走 ③刚体挤入。

        convoy 共享总预算 state['convoy_left']：固有缺陷局面不在无效
        原语上无限烧时间。总时间预算到点同样停（尽早发现就停）。
        """
        if _tb_over():
            state['timeout'] = True
            return []
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
                        progress_callback=progress_callback,
                        cancel_check=cancel_check)
                    state['convoy_left'] -= used
                    if racts:
                        out.append(racts)
        # ④ 临时粘一下（共轭让位）：只在存在不完美洞（8 邻有缺口）时
        # 探测——完美洞的局面让位基本无意义，省钱。整段=让位+标准填入
        # +复位，聚拢度提升才收。每次求解最多探测 paste_left 次。
        if state['paste_left'] > 0 and any(
                hole_gaps(cur, h) for h in holes_c):
            state['paste_left'] -= 1
            _emit(progress_callback, '临时粘补', state['nodes'],
                  '不完美洞，让位-填-复位探测')
            pacts, used_p = _paste_relay(
                cur, m, n, step,
                progress_callback=progress_callback,
                cancel_check=cancel_check)
            state['convoy_left'] -= used_p
            if pacts:
                out.append(pacts)
        for h_c in sorted(holes_c):
            _emit(progress_callback, '带移盖洞', state['nodes'],
                  '洞%s 整形探测' % (h_c,))
            bacts, _bn = _belt_shift_fill(cur, m, n, step, h_c)
            if bacts is not None:
                out.append(bacts)
            for p_c in sorted(out_c):
                if state['convoy_left'] <= 0 or _tb_over():
                    if _tb_over():
                        state['timeout'] = True
                    return out
                if ((p_c[0] - h_c[0]) % step
                        or (p_c[1] - h_c[1]) % step):
                    continue
                _emit(progress_callback, '粘上接走', state['nodes'],
                      '洞%s←凸%s 行军搜索' % (h_c, p_c))
                cacts, used = _convoy_fill(
                    cur, m, n, step, h_c, p_c,
                    max_nodes=min(2500, state['convoy_left']),
                    progress_callback=progress_callback,
                    cancel_check=cancel_check)
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
        if _tb_over():
            state['timeout'] = True
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
                 'timeout': state['timeout'],
                 'secs': round(time.time() - t0, 3)})
    why = ('搜索：时间预算 %.0fs 到点，尽早停机（发现就停）'
           % time_budget) if state['timeout'] \
        else '搜索：预算内无可行 couple 路径'
    return None, {'reason': why,
                  'nodes': state['nodes'], 'search': True,
                  'cancelled': state.get('cancelled', False),
                  'timeout': state['timeout'],
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
                     segment_cb=None, **kwargs):
    """填洞宏求解（GUI 入口）。

    单洞单凸局面 → 单洞整盘求解（keep_partial 观察断点）；
    多洞/多空位局面 → solve_multi_void 贪心驱动（逐 couple 填，全败停机）。

    segment_cb：流式播放回调（label, actions5）——多洞贪心每接受一个
    couple 即回调一次，GUI 边算边播；返回协议变为 fill_stream dict
    （streamed=已实时播的步数，actions=未播剩余部分）。

    返回 (actions, rep_cells)（actions 为四元组列表）供 GUI 宏播放；
    失败返回 {'type': 'fill_fail', 'reason': str}。
    """
    coords = frozenset(tuple(b.location) for b in game.blocks)
    m, n = game.m, game.n
    _region, _ov, holes, outside = window_of(coords, m, n, step)
    _emit(progress_callback, '填洞宏', 0,
          '判型：洞%d 凸%d' % (len(holes), len(outside)))
    try:
        return _solve_fill_macro_inner(coords, m, n, step, holes, outside,
                                       cancel_check, progress_callback,
                                       segment_cb)
    except _Cancelled:
        print('[填洞宏] 已停止（cancel）')
        return {'type': 'fill_fail', 'reason': '已停止', 'cancelled': True}


def _solve_fill_macro_inner(coords, m, n, step, holes, outside,
                            cancel_check, progress_callback, segment_cb):
    """solve_fill_macro 主体（cancel 异常由外层捕获）。"""
    if len(holes) == 1 and len(outside) == 1:
        acts, stats = solve_single_void(coords, m, n, step, keep_partial=True,
                                        cancel_check=cancel_check)
        if acts is None:
            reason = stats.get('reason', stats.get('error', '未知'))
            print('[填洞宏] 单洞无解：%s' % reason)
            resc = _compact_rescue(coords, m, n, step, reason,
                                   progress_callback=progress_callback,
                                   cancel_check=cancel_check)
            if resc is not None:
                return resc
            return {'type': 'fill_fail', 'reason': reason}
        if stats.get('partial'):
            reason = stats.get('reason', '中断')
            resc = _compact_rescue(coords, m, n, step,
                                   '单洞partial:%s' % reason,
                                   progress_callback=progress_callback,
                                   cancel_check=cancel_check)
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
    acts, stats = solve_multi_void(coords, m, n, step,
                                   cancel_check=cancel_check,
                                   segment_cb=segment_cb)
    streamed = stats.get('streamed', 0)
    if not (acts is not None and not stats.get('partial')):
        # 贪心未全解 → 宏级 DFS 回溯兜底（整形边：带移/粘上接走/刚体/
        # 临时粘补）。贪心 partial 已流式播放的段从 end_coords 续算，
        # GUI 播放序列 = 已播段 + 未播剩余 + DFS 段，与真实验证一致。
        base = frozenset(stats.get('end_coords', coords))
        _emit(progress_callback, '宏级搜索', 0, '贪心未全解，DFS 回溯兜底')
        dacts, dstats = solve_multi_search(
            base, m, n, step,
            progress_callback=progress_callback, cancel_check=cancel_check)
        if dacts is not None and not dstats.get('partial'):
            full = list(acts[streamed:] if acts else []) + list(dacts)
            print('[填洞宏] DFS 兜底全解：贪心 %d 步 + 搜索 %d 步'
                  % (len(acts) if acts else 0, len(dacts)))
            if segment_cb is not None:
                acts4, reps = _split_actions(full)
                return {'type': 'fill_stream', 'streamed': streamed,
                        'actions': acts4, 'rep_cells': reps, 'solved': True}
            return _split_actions(full)
        # DFS 也无全解 → 走原贪心产物路径（fail / partial）
    if acts is None:
        reason = stats.get('reason', stats.get('error', '未知'))
        print('[填洞宏] 多洞完全失败：%s' % reason)
        resc = _compact_rescue(coords, m, n, step, reason,
                               progress_callback=progress_callback,
                               cancel_check=cancel_check)
        if resc is not None:
            return resc
        return {'type': 'fill_fail', 'reason': reason,
                'stats': {k: v for k, v in stats.items() if k != 'reason'}}
    if stats.get('partial'):
        reason = stats.get('reason', '中断')
        resc = _compact_rescue(coords, m, n, step, '多洞partial:%s' % reason,
                               progress_callback=progress_callback,
                               cancel_check=cancel_check)
        if resc is not None:
            return resc
        print('[填洞宏] 多洞有成果停机(断在：%s)，已播放 %d 步（保留提升）'
              % (reason, len(acts)))
        rest = acts[streamed:]
        acts4, reps = _split_actions(rest)
        if segment_cb is not None:
            return {'type': 'fill_stream', 'streamed': streamed,
                    'actions': acts4, 'rep_cells': reps,
                    'solved': False, 'reason': reason}
        return {'type': 'fill_partial', 'actions': acts4,
                'rep_cells': reps, 'reason': reason,
                'stats': {k: v for k, v in stats.items()
                          if k not in ('reason', 'partial')}}
    print('[填洞宏] 多洞还原：%d 步 / %d 轮' % (len(acts),
                                             stats.get('rounds', '?')))
    rest = acts[streamed:]
    if segment_cb is not None:
        acts4, reps = _split_actions(rest)
        return {'type': 'fill_stream', 'streamed': streamed,
                'actions': acts4, 'rep_cells': reps, 'solved': True}
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


def _ov_at(coords, rh, cw, r0, c0):
    """锁框覆盖数：在指定框（r0,c0,rh,cw）内数方块，不重新选框。

    备用工具（2-6-7 类"固定目标框"评价用）：动态选框会让框跟着搬运
    的块跑，外层共轭途中"目标框移动"只是求解器视角假象（用户 2026-10-01）。
    """
    return sum(1 for q in coords
               if r0 <= q[0] < r0 + rh and c0 <= q[1] < c0 + cw)


def _overlap_raised(coords, m, n, step, actions):
    """couple 成果判定（段级验收，2026-10-01 用户原则）。

    填洞/补缺都是公式生成器：验收只看公式段**结束后**的聚拢度是否
    比开始前提升，**中途完全不用管**（外层共轭/搬运类操作中途聚拢度
    必然波动，不作为拒绝理由）。聚拢度 = 最佳窗口覆盖数（段首段末
    各自按定义取）。对应「有成果的失败」——提升即接受为一步进展；
    回放失败视为无成果。
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
