# -*- coding: utf-8 -*-
"""防偏移（anti-drift）：利用「聚攏目標平移不變」的對稱性，把滑動序列改寫成
視覺居中的等價序列；或計算每步質心偏移供顯示時抵消。

前提（solver/ml/invariants.profile_defect 與 auto_solver._phi_of 已確認）：
* 聚攏成功判據只認「形狀」，與絕對位置無關（Φ=0 ⟺ 還原，平移不變）。
* 整盤（含空格）整體平移 v 是規則的對稱：平移後的每一步滑動在原盤都有對應
  的合法滑動。因此一段序列可整體重標籤而不改其相對解——這正是魔方「整體轉體
  可消去」在本謎題的對應（整體平移 = 整體轉體，是零代價的對稱分量）。

兩種用法（都不增不減步數）：
* 顯示抵消（零風險，主路）：逐幀按**本幀真實渲染位置**（含動畫插值）扣掉
  質心偏移，把質心鎖在初始位置；只動相機，不動解法、不動盤面（見
  ``gui.renderer.RendererMixin._anti_drift_cam_offset``）。
  ⚠️ 必須逐幀連續：動畫期間 ``b.location`` 恆為起點（``commit_animation``
  才寫終態），若按 location 離散計算，整段動畫偏移恆 0、commit 一瞬整盤
  跳一格，就是「每步之後強制居中」的台階式抖動（2026-11-11 用戶實測）。
  連續補償的淨效果＝等價改寫的視覺：一大片幾乎不動、少數塊相對滑動，
  與打亂的錨點式防偏移同一觀感。
* 序列改寫（可複用 / 存檔）：把「初始盤面」與「每步 act」按累積質心偏移的負值
  整體平移，得到自洽、居中、步數相同的序列（transform_sequence_square）。
  方形網格坐標為整數，質心偏移可能是分數——取整四捨五入後殘差 ≤ 0.5 格，
  相對排列不變；顯示抵消用浮點相機，精確無殘差。
"""
from solver.ml.fill_macro import build_game, _replay_apply, _capture_apply
from solver.table_core import _side_components

# 与 anchor_shuffle.MAX_DRIFT 同量级：改写后的残余漂移目标（格）
DRIFT_TARGET = 1.0

_OPP_DIR = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}
_OPP_SIDE = {'above': 'below', 'below': 'above',
             'left': 'right', 'right': 'left'}
_DIR_VEC = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}


def _coords_of(game):
    return frozenset((b.location[0], b.location[1]) for b in game.blocks)


def _shape_of(coords):
    """形状（平移归一）：只保留相对排列，与绝对坐标无关。"""
    if not coords:
        return frozenset()
    mr = min(r for r, c in coords)
    mc = min(c for r, c in coords)
    return frozenset((r - mr, c - mc) for r, c in coords)


def _selected_piece(coords, gap, line, side, rep):
    """opt 会选中的连通片（该侧含 rep 的分量）；无 rep 时仅当该侧唯一分量。"""
    comps = [c for c in _side_components(set(coords), gap, line, side) if c]
    if rep is None:
        return comps[0] if len(comps) == 1 else None
    return next((c for c in comps if (rep[0], rep[1]) in c), None)


def _flip_act(coords, act, step):
    """把「推 A」换成「推补集」的动作（整体平移消去）；不可行返回 None。

    依据：一次滑动的效果是「连通片 A 平移 δ，其余不动」。复原判定只认形状
    （``game.is_solved`` 取外接矩形，平移不变），故

        A 平移 δ   ≡   补集平移 −δ   ∘ 整体平移 δ

    后者在画面上是「大片不动、小片滑」。补集必须能被**单步**选出（恰好是
    某条缝某一侧的一个连通分量），否则一步动不了，只能放弃（保留原动作，
    把整体平移记进 ``off`` 由后续步吸收）。

    仅当被推动的片超过全盘一半时才值得换（否则本来就是小片在滑）。
    """
    gap, line, side, d, rep = act
    cur = set(coords)
    if len(cur) < 2:
        return None
    piece = _selected_piece(cur, gap, line, side, rep)
    if not piece or len(piece) * 2 <= len(cur):
        return None
    desire = cur - piece
    if not desire:
        return None
    rows = [r for r, _c in cur]
    cols = [c for _r, c in cur]
    for gap2 in ('h', 'v'):
        lo, hi = ((min(rows) - 1, max(rows)) if gap2 == 'h'
                  else (min(cols) - 1, max(cols)))
        sides2 = ('above', 'below') if gap2 == 'h' else ('left', 'right')
        for ln in range(lo, hi + 1):
            for s2 in sides2:
                for comp in _side_components(cur, gap2, ln, s2):
                    if comp and comp == desire:
                        return (gap2, ln, s2, _OPP_DIR[d], sorted(comp)[0])
    return None


def _shift_act(act, off):
    """把 4/5 元组动作整体平移 off（后续步跟着被消去的那次整体平移走）。"""
    a = translate_act_square(act, off)
    return tuple(a) + (None,) if len(a) < 5 else tuple(a)


class BulkStaticRewriter:
    """有状态改写器：把求解序列改写成「大片不动、小片滑」的等价序列。

    跨段使用（流式求解逐段上报时同一实例连续调用）：内部维持影子盘面与
    累计整体平移 ``off``。改写不增不删步数，终态只是整体平移了一个整格
    向量——复原判定平移不变，故仍算还原。

    用法::

        rw = BulkStaticRewriter(coords0, m, n, step)
        acts2, end2 = rw.feed(acts5)      # 逐段喂，end2 = 本段改写后的终态
    """

    def __init__(self, coords0, m, n, step):
        self.g = build_game(coords0, m, n)
        self.step = step
        self.m, self.n = m, n
        self.off = (0, 0)
        self.c0 = centroid_offset(coords0)
        self.flips = 0
        self.flip_idx = []      # 发生过换侧的步号（全局，供护栏/调试用）
        self.n_seen = 0

    # -- 内部 ---------------------------------------------------------
    def _dist(self, coords):
        if self.c0 is None or not coords:
            return 0.0
        c = centroid_offset(coords)
        return ((c[0] - self.c0[0]) ** 2 + (c[1] - self.c0[1]) ** 2) ** 0.5

    # -- 对外 ---------------------------------------------------------
    def feed(self, acts5):
        """改写一段动作（世界绝对坐标，长度为 len(acts5) 不变）。

        返回 (new_acts5, coords_end)。影子盘面按本段终态前进。
        """
        out = []
        for raw in acts5:
            act = tuple(raw[:4])
            idx = self.n_seen
            self.n_seen += 1
            rep = raw[4] if len(raw) > 4 and raw[4] is not None else None
            a_cur = _shift_act(act + ((rep,) if rep else ()), self.off)
            pre = _coords_of(self.g)
            a_flip = _flip_act(pre, a_cur, self.step)

            okN, _ = _capture_apply(self.g, a_cur, self.step)
            if not okN:
                # 平移是规则对称，理论不会走到这里；保守起见原样保留，
                # 影子盘面不前进（避免把后续步算到错的盘上）。
                out.append(a_cur)
                continue
            cN = _coords_of(self.g)
            chosen_act = a_cur
            if a_flip is not None:
                gF = build_game(pre, self.m, self.n)
                okF, _ = _capture_apply(gF, a_flip, self.step)
                if okF and _shape_of(_coords_of(gF)) == _shape_of(cN):
                    cF = _coords_of(gF)
                    if self._dist(cF) + 1e-9 < self._dist(cN):
                        # 记录两次落点之间的整体平移，供后续步吸收
                        mrN = min(r for r, _c in cN)
                        mcN = min(c for _r, c in cN)
                        mrF = min(r for r, _c in cF)
                        mcF = min(c for _r, c in cF)
                        self.off = (self.off[0] + (mrF - mrN),
                                    self.off[1] + (mcF - mcN))
                        self.g = gF
                        chosen_act = a_flip
                        self.flips += 1
                        self.flip_idx.append(idx)
            out.append(chosen_act)
        return out, _coords_of(self.g)


def rewrite_bulk_static(coords0, m, n, step, acts5):
    """一次性改写整条序列 → (acts5, coords_end, flips)。

    与 ``BulkStaticRewriter`` 同源，用于非流式调用方（测试 / 存档回放）。
    """
    rw = BulkStaticRewriter(coords0, m, n, step)
    new_acts, end = rw.feed(acts5)
    return new_acts, end, rw.flips



def centroid_offset(coords):
    """coords: iterable of (r, c[, ...])。回傳平均位置（質心，浮點）。"""
    s = None
    n = 0
    for p in coords:
        if s is None:
            s = [float(x) for x in p]
        else:
            for i, v in enumerate(p):
                s[i] += float(v)
        n += 1
    if n == 0:
        return None
    return tuple(x / n for x in s)


def drift_offsets(initial_coords, transitions):
    """transitions: list of 盤面（frozenset/set of coords）在每步之後的狀態。
    回傳長度 len(transitions)+1 的列表，offsets[i] = 質心_i − 質心_0。
    offsets[0] = 全 0。顯示時把 offsets[i] 從第 i 步的渲染位置扣掉即可鎖質心。
    """
    c0 = centroid_offset(initial_coords)
    out = [tuple(0.0 for _ in c0)]
    for st in transitions:
        c = centroid_offset(st)
        out.append(tuple(a - b for a, b in zip(c, c0)))
    return out


def translate_act_square(act, vec):
    """方形 act=(gap,line,side,d[,rep...]) 整體平移 vec=(vr,vc)：
    gap=='h' 的縫是「行」，line 沿行號 +vr；'v' 是「列」，+vc；rep 整體平移。
    結構量 gap/side/d 不變。
    """
    vr, vc = vec[0], vec[1]
    gap, line, side, d = act[0], act[1], act[2], act[3]
    line2 = line + (vr if gap == 'h' else vc)
    tail = tuple(act[4:])
    if tail and tail[0] is not None:
        rep = tail[0]
        new_rep = tuple(r + v for r, v in zip(rep, (vr, vc)))
        return (gap, line2, side, d, new_rep) + tuple(tail[1:])
    return (gap, line2, side, d) + tail


def transform_sequence_square(initial_coords, acts4, reps, m, n, step):
    """把 (初始盤面, 4元組act, 平行rep) 改寫成質心居中的自洽序列。

    回傳 (initial_coords, shifted_acts4, shifted_reps, per_step_offsets)。
      · initial_coords 不動（d0=0，初始即居中）。
      · shifted_acts4[i] 是 act i 整體平移 per_step_offsets[i] 後的結果。
      · per_step_offsets[i] 是「第 i 步之前」的累積質心偏移（整數四捨五入）；
        回放時須在播第 i 步前把盤面整體平移 (offsets[i] − offsets[i-1]) 才自洽。

    證明：在「初始盤面逐幀按 offsets 重平移」的盤上回放 shifted 序列，終態 =
    原終態平移 −offsets[k]（k=步數），故終態質心 == 原初態質心（居中）。
    可複用於 headless 批處理 / 存檔；GUI 主路直接用顯示抵消（見
    ``RendererMixin._anti_drift_cam_offset``），不走本函數的盤面重平移。
    """
    g = build_game(initial_coords, m, n)
    states = [frozenset(initial_coords)]
    for i, a in enumerate(acts4):
        rep = reps[i] if (reps and i < len(reps) and reps[i]) else None
        a5 = tuple(a) + ((tuple(rep),) if rep else (None,))
        if not _replay_apply(g, [a5], m, n, step):
            return initial_coords, acts4, reps, [tuple(0 for _ in (0, 0))] * (len(acts4) + 1)
        states.append(frozenset(tuple(b.location) for b in g.blocks))
    c0 = centroid_offset(initial_coords)
    per_step = [tuple(0 for _ in c0)]
    for st in states[1:]:
        c = centroid_offset(st)
        per_step.append(tuple(ci - b for ci, b in zip(c, c0)))
    shifted_acts, shifted_reps = [], []
    for i, a in enumerate(acts4):
        # 負向平移：把第 i 步整體平移 −per_step[i]（與回放時「每步後再平移
        # per_step[i]−per_step[i+1]」配合，累積恰好把終態質心拉回初態）。
        veci = tuple(-int(round(x)) for x in per_step[i])
        sh = translate_act_square(a, veci)
        shifted_acts.append(tuple(sh[:4]))
        shifted_reps.append(sh[4] if len(sh) > 4 else None)
    return initial_coords, shifted_acts, shifted_reps, per_step
