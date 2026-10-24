# -*- coding: utf-8 -*-
"""模型文件的物理公理校验（A0–A3）。

为什么不能只靠加载器
--------------------
加载器组装 BoardSpec 时也写了 `overlap` / `components` / `seam_lines` 钩子。
如果校验器直接调这些钩子，那等于「用同一段代码证明自己没错」——钩子写错
（比如只查首尾不查中途）时校验照样通过。

所以本模块**从模型文档（doc）独立重建几何真值**：自己按 `basis` / `pos_scale`
/ `orientations` 算整数顶点与平面多边形，自己写重叠与连通判定，然后才去驱动
引擎（Board）走棋。两边独立算出的结论一致，才叫验过。

公理
----
| # | 含义 | 判据 |
|---|---|---|
| A0 | 还原态自洽 | 块数对得上、两两无重叠、单一连通、`is_solved()` 为真 |
| A1 | 缝是真缝 | 每条缝整条落在块边上，不劈开任何块；不漏报也不多报 |
| A2 | 缝可滑 | 沿缝平移，**逐格**验中途位置不重叠、不断开（不止查首尾） |
| A3 | 每步可逆 | 每一步都能沿反方向精确推回；两侧非空 |

用法
----
    from engine.model_validate import validate, assert_valid
    problems = validate(loaded)      # 返回全部问题（error / warn）
    assert_valid(loaded)             # 有 error 就抛 ModelError

CLI 见 `validate_model.py`。
"""
from . import geometry_ops as gops
from .board import Board


class Problem:
    """一条校验结论。`level` = 'error'（不可运行）或 'warn'（可疑但可玩）。"""

    __slots__ = ('level', 'code', 'where', 'msg')

    def __init__(self, level, code, where, msg):
        self.level = level
        self.code = code
        self.where = where
        self.msg = msg

    def __repr__(self):
        return f'<{self.level} {self.code} {self.where}: {self.msg}>'

    def __str__(self):
        tag = '错误' if self.level == 'error' else '警告'
        return f'[{tag}] {self.code} {self.where}：{self.msg}'

    def as_dict(self):
        return {'level': self.level, 'code': self.code,
                'where': self.where, 'msg': self.msg}


# ----------------------------------------------------------------------
# 从文档独立重建的几何真值
# ----------------------------------------------------------------------
class _Truth:
    """按 doc 独立算几何，刻意不复用加载器的闭包。"""

    def __init__(self, doc):
        self.basis = tuple(tuple(float(x) for x in row) for row in doc['basis'])
        self.scale = int(doc['pos_scale'])
        self.offsets = {label: tuple(tuple(int(x) for x in v)
                                     for v in item['off'])
                        for label, item in doc['orientations'].items()}
        self._iv = {}
        self._poly = {}

    def iv(self, point, orient):
        """整数顶点（= pos_scale × 真实格坐标，全整数）。"""
        key = (point, orient)
        got = self._iv.get(key)
        if got is None:
            offs = self.offsets[orient]
            got = tuple((point[0] + ox, point[1] + oy) for ox, oy in offs)
            self._iv[key] = got
        return got

    def poly(self, point, orient):
        """平面顶点（几何判定用）。"""
        key = (point, orient)
        got = self._poly.get(key)
        if got is None:
            b = self.basis
            s = self.scale
            out = []
            for vx, vy in self.iv(point, orient):
                a, c = vx / s, vy / s
                out.append((a * b[0][0] + c * b[1][0],
                            a * b[0][1] + c * b[1][1]))
            got = tuple(out)
            self._poly[key] = got
        return got

    # -- 几何判定（独立实现，不走 spec 钩子）--
    def overlaps(self, keys_a, keys_b, *, skip_same=False):
        """两簇块是否有正面积重叠。返回第一对冲突的键，无则 None。"""
        pa = [(k, self.poly(k[0], k[1])) for k in keys_a]
        pb = [(k, self.poly(k[0], k[1])) for k in keys_b]
        ba = [(k, gops.bbox(p)) for k, p in pa]
        bb = [(k, gops.bbox(p)) for k, p in pb]
        for k1, b1 in ba:
            for k2, b2 in bb:
                if skip_same and k1 == k2:
                    continue
                if not gops.boxes_overlap(b1, b2):
                    continue
                if gops.convex_overlap(dict(pa)[k1], dict(pb)[k2]):
                    return (k1, k2)
        return None

    def self_overlap(self, keys):
        """整盘自重叠（两两，含同位置不同朝向的错位态）。"""
        keys = tuple(keys)
        polys = [self.poly(k[0], k[1]) for k in keys]
        boxes = [gops.bbox(p) for p in polys]
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if not gops.boxes_overlap(boxes[i], boxes[j]):
                    continue
                if gops.convex_overlap(polys[i], polys[j]):
                    return (keys[i], keys[j])
        return None

    def components(self, keys):
        return gops.components(keys, lambda k: self.iv(k[0], k[1]))

    def connected(self, keys):
        return len(self.components(frozenset(keys))) <= 1

    def edge_pairs(self, keys):
        """跨块共用的**整条边** → ((边, (块1, 块2)), ...)。"""
        vmap = {k: self.iv(k[0], k[1]) for k in keys}
        out = []
        for edge, owners in gops.shared_edge_owners(vmap).items():
            for i in range(len(owners)):
                for j in range(i + 1, len(owners)):
                    out.append((edge, (owners[i], owners[j])))
        return out


def _rank(coeffs, iv):
    return coeffs[0] * iv[0] + coeffs[1] * iv[1]


def _rank_profile(truth, keys, coeffs):
    """每块在缝泛函下的 (min_rank, max_rank, 各边两端 rank)。"""
    out = {}
    for k in keys:
        vs = truth.iv(k[0], k[1])
        n = len(vs)
        rs = [_rank(coeffs, v) for v in vs]
        out[k] = (min(rs), max(rs),
                  tuple((rs[i], rs[(i + 1) % n]) for i in range(n)))
    return out


def _splits_block(profile, t):
    """直线 {rank=t} 是否穿过块的**内部**。

    判据 = 存在一条边，两端 rank **严格**分居 t 两侧。不能用「t 落在
    min..max 之间」——顶点 rank 恰好等于 t 时直线只经过那个顶点，块没被
    劈开（碎三角的等腰三角就有 rank 为 {0,3,6} 这类情况）。
    """
    for a, b in profile[2]:
        if (a < t < b) or (b < t < a):
            return True
    return False


def _axiom_seam_lines(truth, keys, fam):
    """独立算某族在当前局面下的真缝。

    真缝 = 存在**跨块共用的整条边**、两端 rank 相等（=t），且该直线
    不劈开任何块。
    返回 (report, split, (lo, hi))：report = t 集合，
    split = {t: 被劈的块}（这些 t 有共边但穿块，是假缝）。
    """
    prof = _rank_profile(truth, keys, fam.coeffs)
    lo = min(p[0] for p in prof.values())
    hi = max(p[1] for p in prof.values())
    ts = set()
    for (pa, pb), _owners in truth.edge_pairs(keys):
        ra, rb = _rank(fam.coeffs, pa), _rank(fam.coeffs, pb)
        if ra == rb and lo < ra <= hi:
            ts.add(ra)
    report, split = set(), {}
    for t in sorted(ts):
        hit = [k for k, p in prof.items() if _splits_block(p, t)]
        if hit:
            split[t] = hit
        else:
            report.add(t)
    return report, split, (lo, hi)


# ----------------------------------------------------------------------
# 主校验
# ----------------------------------------------------------------------
def validate(model, *, deep=True, a3_samples=8, max_report=6):
    """对 LoadedModel 跑 A0–A3，返回 Problem 列表（可空 = 全过）。

    `deep=False` 跳过 A3（A3 要对每条合法移动求一次新局面）。
    `a3_samples` 额外用「完整 legal_moves」复核多少条反向移动（0 = 全量）。
    """
    doc = model.doc
    spec = model.spec
    out = []
    err = lambda code, where, msg: out.append(Problem('error', code, where, msg))
    warn = lambda code, where, msg: out.append(Problem('warn', code, where, msg))

    try:
        truth = _Truth(doc)
    except (KeyError, TypeError, ValueError) as exc:
        err('A0', '几何', f'无法从文档重建几何：{exc}')
        return out

    board = Board(spec, spec.goal_blocks)
    keys = board.keys

    # ---------------- A0 还原态自洽 ----------------
    n_tiles = len(doc.get('tiles') or ())
    if len(keys) != n_tiles:
        err('A0', 'tiles',
            f'放置 {n_tiles} 条，但还原态只有 {len(keys)} 块（有重复位置+朝向）')
    if len(spec.goal_blocks) != n_tiles:
        err('A0', 'goal_blocks',
            f'还原态块数 {len(spec.goal_blocks)} ≠ tiles 条数 {n_tiles}')

    clash = truth.self_overlap(keys)
    if clash is not None:
        err('A0', '还原态',
            f'两块重叠：{clash[0]!r} 与 {clash[1]!r}（同一位置放了互相压住的块）')

    comps = truth.components(keys)
    if len(comps) > 1:
        biggest = max(comps, key=len)
        loose = sorted(set(keys) - set(biggest))[:max_report]
        err('A0', '还原态',
            f'不是单一连通：{len(comps)} 个连通分量，脱离主体的块如 {loose}')

    try:
        solved = board.is_solved()
    except Exception as exc:                # noqa: BLE001 - 校验器要如实报，不吞
        err('A0', '还原态', f'is_solved() 抛错：{exc}')
    else:
        if not solved:
            err('A0', '还原态',
                'is_solved() 为假：还原态不等于自己（goal_canonical 或 '
                'solved_check 有问题）')

    # ---------------- A1 缝是真缝 ----------------
    live_by_family = {}
    for fam in spec.seam_families:
        report, split, (lo, hi) = _axiom_seam_lines(truth, keys, fam)
        live_by_family[fam.name] = sorted(report)
        where = f'缝族 {fam.name!r}'
        got = ({t for t, _line in spec.seam_lines(board, fam)}
               if spec.seam_lines is not None else None)
        if not report:
            warn('A1', where,
                 f'还原态下没有可用的缝（rank 区间 {lo}..{hi}）：该族恒锁死。'
                 f'若这是有意为之可忽略；若不该死，检查 coeffs 与 step')
        for t, hit in split.items():
            if got is None or t in got:
                err('A1', where,
                    f'缝 t={t} 会劈开 {len(hit)} 块（如 {hit[0]!r}）：'
                    f'直线穿过该块某条边的内部，整条线没有落在块边上')
        # 与引擎给的缝线表对拍
        if got is not None:
            missing = report - got
            extra = got - report
            if missing:
                err('A1', where,
                    f'引擎漏报真缝 t={sorted(missing)}（几何上这些线确实'
                    f'沿块边且不劈块）')
            if extra:
                err('A1', where,
                    f'引擎多报缝 t={sorted(extra)}（几何上找不到对应的整条'
                    f'共边，是假缝）')

    if not any(live_by_family.values()):
        err('A1', '缝族', '所有缝族在还原态都没有可用的缝：板型是死的')

    # ---------------- A2 缝可滑（逐格） ----------------
    moves = board.legal_moves(1)
    if not moves:
        err('A2', '还原态', '一条合法移动都没有：盘面冻死')

    for mv in moves:
        moved = frozenset(mv.moved)
        rest = keys - moved
        d = mv.direction
        cur = moved
        bad = None
        for step_i in range(1, mv.step + 1):
            cur = frozenset(((p[0] + d[0], p[1] + d[1]), o) for p, o in cur)
            pair = truth.overlaps(cur, rest)
            if pair is not None:
                bad = (step_i, 'overlap', pair)
                break
            if not truth.connected(cur | rest):
                bad = (step_i, 'disconnect', None)
                break
        if bad is not None:
            where = f'缝族 {mv.family!r} t={mv.t} 侧 {mv.side}'
            if bad[1] == 'overlap':
                err('A2', where,
                    f'第 {bad[0]}/{mv.step} 格与 {bad[2][1]!r} 正面积重叠：'
                    f'引擎却判合法（overlap 钩子与几何不一致）')
            else:
                err('A2', where,
                    f'第 {bad[0]}/{mv.step} 格途中断开成多个部分：'
                    f'整片平移会造成悬空')

    # ---------------- A3 每步可逆 ----------------
    if deep:
        seen_keys = {keys}
        n_check = len(moves) if a3_samples <= 0 else min(a3_samples, len(moves))
        for idx, mv in enumerate(moves):
            after = board.apply(mv)
            # 精确重算「移动后的选中片键」
            delta = (mv.step * mv.direction[0], mv.step * mv.direction[1])
            moved_after = frozenset(((p[0] + delta[0], p[1] + delta[1]), o)
                                    for p, o in mv.moved)
            back = (-mv.direction[0], -mv.direction[1])
            where = f'缝族 {mv.family!r} t={mv.t} 侧 {mv.side}'
            if after.can_slide(moved_after, back, mv.step) is None:
                err('A3', where,
                    f'走完后沿 {back} 推不回去：该步不可逆，'
                    f'玩家会走进无法还原的分支')
                continue
            if idx < n_check:
                # 抽样：用完整 legal_moves 确认「玩家真的点得出来」
                ok = False
                for rev in after.legal_moves(1):
                    if rev.direction != back:
                        continue
                    if after.apply(rev).keys == keys:
                        ok = True
                        break
                if not ok:
                    err('A3', where,
                        '几何上推得回去，但新局面里找不到对应的合法点击'
                        '（反向移动不是任何一条缝的连通分量闭包）')

    return out


def summarize(problems):
    """(错误数, 警告数)。"""
    e = sum(1 for p in problems if p.level == 'error')
    return e, len(problems) - e


def assert_valid(model, **kw):
    """有 error 就抛 ModelError；返回 (错误数, 警告数)。仅 warn 时放行。"""
    from .model_loader import ModelError
    problems = validate(model, **kw)
    errs = [p for p in problems if p.level == 'error']
    if errs:
        head = '；'.join(str(p) for p in errs[:3])
        more = f'（共 {len(errs)} 条）' if len(errs) > 3 else ''
        raise ModelError(f'模型 {model.name!r} 未通过物理公理：{head}{more}')
    return summarize(problems)
