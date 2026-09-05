# -*- coding: utf-8 -*-
r"""
单洞「死代码」填洞宏（fill_macro）— game 引擎版（无搜索、无 AI）

复用游戏本体宏机制：
    · 每步动作 = 沿缝切、选侧、点一个「目标块」→ game.opt 扩散为同侧连通
      分量 → try_move 验证 step 步 → commit_move。与 GUI 宏执行同一语义。
    · setup/A/B 阶段点「凸起 p」为目标块（= 人类录制时点击凸起）；
      A' 阶段复用「逆序宏」：A 动作逆序重放（同缝同侧、方向取反），目标块
      取该侧首块（与 GUI 逆序播放一致）。
    · 窗口固定、凸起坐标跟踪、B 终止 = p 与洞 h 重合。

运行：
    D:\python\python.exe -m solver.ml.fill_macro --sample
    D:\python\python.exe -m solver.ml.fill_macro --gen 6 6 2 40 5
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
    """在一局 SliderMatrix 上执行共轭子宏，与 GUI 宏同语义。"""

    def __init__(self, game, m, n, step, verbose=False, keep_partial=False):
        self.g = game
        self.m, self.n, self.step = m, n, step
        self.verbose = verbose
        self.keep_partial = keep_partial
        self.acts = []                 # 已执行动作 (gap,line,side,dir,rep)
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
            if solved_game(self.g):
                break
        if solved_game(self.g):
            return self.acts, {'steps': len(self.acts),
                               'secs': round(time.time() - t0, 3)}
        return self._bail({'reason': 'A′逆序宏后未还原(需细化)',
                           'p': self.p, 'h': self.h,
                           'moves': len(self.acts)})


def solve_single_void(coords, m, n, step, hole=None, anchor=None,
                      verbose=False, max_moves=200, keep_partial=False,
                      force_rot=None):
    """确定性单洞填洞宏（视图旋转归一化版）。

    · 找洞/凸起：本函数只负责「旋转到凸起在右侧 → 解 → 逆旋输出」。若
      hole/anchor 未给出，则用 window_of 自检单洞单凸；给出则以调用方为准
      （多洞/多凸时由调用方逐对喂入，本函数不再负责挑选）。
    · 返回 (actions, stats)；actions=None 表示失败（keep_partial=False）。
      keep_partial=True：规则中断但已执行合法动作时返回 (部分actions, stats)，
      stats['partial']=True、stats['reason'] 为中断原因，供观察断点。
    """
    coords = frozenset(coords)
    if len(coords) != m * n:
        return None, {'error': f'格数 {len(coords)} != {m * n}'}
    g = build_game(coords, m, n)
    if g.is_solved():
        return [], {'steps': 0, 'secs': 0.0}
    try:
        # 定位窗口与洞/凸起（世界坐标）
        (r0, c0, _wh), _ov, holes, outside = window_of(coords, m, n, step)
        if hole is None or anchor is None:
            assert len(holes) == 1 and len(outside) == 1, '非单洞单凸起'
            h_w = tuple(next(iter(holes)))
            p_w = tuple(next(iter(outside)))
        else:
            h_w, p_w = tuple(hole), tuple(anchor)
        if ((h_w[0] - p_w[0]) % step or (h_w[1] - p_w[1]) % step):
            raise ValueError('洞凸不同mod')

        name = force_rot or view_rotate.choose_rot(
            p_w[0] - r0, p_w[1] - c0, m, n)
        if name == 'id':
            return _Runner(g, m, n, step, verbose,
                           keep_partial=keep_partial).run()

        # 旋转到「凸起在右侧」再求解
        vc = frozenset(view_rotate.rotate_xy(name, r - r0, c - c0, m, n)
                       for r, c in coords)
        mv, nv = view_rotate.view_dims(name, m, n)
        vg = build_game(vc, mv, nv)
        acts, stats = _Runner(vg, mv, nv, step, verbose,
                              keep_partial=keep_partial).run()
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

        if stats.get('partial'):
            return wacts, dict(stats, rot=name)
        # 非 partial：必须能在世界棋盘整局回放还原
        if not replay_and_verify(coords, m, n, step, wacts):
            return None, {'reason': f'逆映射回放未还原(rot={name})',
                          'rot': name}
        return wacts, dict(stats, rot=name)
    except ValueError as e:
        return None, {'reason': str(e)}


# ---------------------------------------------------------------------------
# GUI 求解器入口（与 SOLVER_ALGORITHMS 统一签名）
# ---------------------------------------------------------------------------
def solve_fill_macro(game, step, cancel_check=None, progress_callback=None,
                     **kwargs):
    """填洞宏求解：仅处理「单洞 + 单凸起」局面。

    返回 (actions, rep_cells)（actions 为四元组列表）供 GUI 宏播放；
    失败返回 {'type': 'fill_fail', 'reason': str}，GUI 用于显示失败原因。
    """
    coords = frozenset(tuple(b.location) for b in game.blocks)
    m, n = game.m, game.n
    acts, stats = solve_single_void(coords, m, n, step, keep_partial=True)
    if acts is None:
        reason = stats.get('reason', stats.get('error', '未知'))
        print('[填洞宏] 无解：%s' % reason)
        return {'type': 'fill_fail', 'reason': reason}
    if stats.get('partial'):
        reason = stats.get('reason', '中断')
        print('[填洞宏] 部分(断在：%s)，已播放 %d 步供观察'
              % (reason, len(acts)))
        return {'type': 'fill_partial', 'actions': [a[:4] for a in acts],
                'rep_cells': [a[4] for a in acts], 'reason': reason}
    return ([a[:4] for a in acts], [a[4] for a in acts])


# ---------------------------------------------------------------------------
# 数据源 / CLI
# ---------------------------------------------------------------------------
def replay_and_verify(coords, m, n, step, actions):
    """整局回放验证最终还原。每步优先按 rep_cell 精确定位分量。"""
    g = build_game(coords, m, n)
    for a in actions:
        if len(a) == 5:
            gap, line, side, d, rep = a
        else:
            gap, line, side, d = a
            rep = None
        r = _Runner.__new__(_Runner)
        r.g, r.m, r.n, r.step = g, m, n, step
        r.p = None
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
    return g.is_solved()


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
        out_dir = os.path.join(_ROOT, 'save', '單孔洞失敗_%s'
                               % time.strftime('%Y%m%d-%H%M%S'))
        saved = 0
        for i in range(N):
            coords, _holes = generate_random_void(m, n, step, 1, rng=rng)
            acts, stats = solve_single_void(coords, m, n, step)
            if acts is None:
                r = stats.get('reason', '?')
                fails[r] = fails.get(r, 0) + 1
                save_case_json(out_dir, f'{step}-{m}-{n}-{i:03d}.json',
                               coords, m, n, step,
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
                save_case_json(out_dir, f'{step}-{m}-{n}-{i:03d}.json',
                               coords, m, n, step,
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
    print(__doc__)


if __name__ == '__main__':
    _main()
