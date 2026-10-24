# -*- coding: utf-8 -*-
"""模型文件加载器：JSON → BoardSpec。

设计要点
--------
1. **加载即校验**：结构错、尺寸错、朝向缺失、放置重复、缝族不在候选里，
   一律抛错并指出是哪一项，绝不让坏模型进入运行。
2. **两套坐标各司其职**（沿用碎三角验证过的做法）：
   · 整数坐标（`p + off`，即 3× 顶点）用于**身份判定**——共边、去重、缝线，
     精确比对，不吃浮点误差；
   · 平面坐标（basis·(整数/pos_scale)）用于**几何判定**——重叠。
3. **零 pygame、零形状字面量**：几何全走 `engine/geometry_ops`。
4. 连通性、缝线、重叠、格子多边形全部由数据 + 通用算法推出，模型文件里
   不写任何「算法」。

文件格式见 `docs/spec/模型文件_2026-10-24.md`。
"""
import json
import os

from . import geometry_ops as gops
from .board import Block, BoardSpec, SeamFamily
from .lattice import Lattice

SCHEMA_BOARD = 'gatenna.board/1'
SCHEMA_SHAPES = 'gatenna.shapes/1'

DEFAULT_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models')


class ModelError(ValueError):
    """模型文件不合法（结构 / 语义 / 物理公理）。"""


# ----------------------------------------------------------------------
# 结构校验小工具
# ----------------------------------------------------------------------
def _need(doc, key, types, where):
    if key not in doc:
        raise ModelError(f'{where} 缺少字段 {key!r}')
    val = doc[key]
    if not isinstance(val, types) or isinstance(val, bool):
        raise ModelError(f'{where} 的 {key!r} 类型不对：{val!r}')
    return val


def _int_pair(v, where):
    if (not isinstance(v, (list, tuple)) or len(v) != 2
            or not all(type(x) is int for x in v)):
        raise ModelError(f'{where} 须为两个整数，收到 {v!r}')
    return (v[0], v[1])


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ----------------------------------------------------------------------
# 加载
# ----------------------------------------------------------------------
class LoadedModel:
    """加载结果：板型 + 供 GUI/存档使用的元信息。"""

    __slots__ = ('spec', 'name', 'title', 'engine', 'view', 'doc', 'path')

    def __init__(self, spec, doc, path=None):
        self.spec = spec
        self.doc = doc
        self.path = path
        self.name = spec.name
        self.title = doc.get('title') or spec.name
        self.engine = doc.get('engine', 'geometric')
        view = doc.get('view') or {}
        self.view = {
            'rotate': int(view.get('rotate', 0)) % 360,
            'mirror': bool(view.get('mirror', False)),
        }

    def __repr__(self):
        return (f'<LoadedModel {self.name!r} engine={self.engine} '
                f'blocks={len(self.spec.goal_blocks)} '
                f'seams={len(self.spec.seam_families)}>')


def load_model(doc, *, shapes=None, path=None):
    """模型字典 → LoadedModel（含 BoardSpec）。

    `shapes` 为形状库字典（`{名字: {verts: [...]}}`）；给了只做身份校验，
    几何以每个朝向自带的整数偏移 `off` 为准。
    """
    where = f'模型 {doc.get("name")!r}'
    schema = _need(doc, 'schema', str, where)
    if schema != SCHEMA_BOARD:
        raise ModelError(f'{where} 的 schema 未识别：{schema!r}')
    name = _need(doc, 'name', str, where)
    if not name or not all(c.isalnum() or c in '_-' for c in name):
        raise ModelError(f'{where} 的 name 只能含字母数字与 _ -，收到 {name!r}')

    basis = _need(doc, 'basis', (list, tuple), where)
    if len(basis) != 2 or any(len(row) != 2 for row in basis):
        raise ModelError(f'{where} 的 basis 须为 2×2 矩阵，收到 {basis!r}')
    basis = tuple(tuple(float(x) for x in row) for row in basis)
    if (basis[0][0] * basis[1][1] - basis[0][1] * basis[1][0]) == 0:
        raise ModelError(f'{where} 的 basis 退化（行列式为 0），无法映射到平面')
    scale = _need(doc, 'pos_scale', int, where)
    if scale < 1:
        raise ModelError(f'{where} 的 pos_scale 须为正整数，收到 {scale!r}')

    # ---- 朝向表 ----
    orients_doc = _need(doc, 'orientations', dict, where)
    if not orients_doc:
        raise ModelError(f'{where} 的 orientations 为空')
    offsets = {}
    for label, item in orients_doc.items():
        if not isinstance(label, str) or not label:
            raise ModelError(f'{where} 的朝向标签须为非空字符串，收到 {label!r}')
        if not isinstance(item, dict):
            raise ModelError(f'{where} 的朝向 {label!r} 须为对象')
        shape_name = item.get('shape')
        if shapes is not None and shape_name not in shapes:
            raise ModelError(
                f'{where} 的朝向 {label!r} 引用了未定义的形状 {shape_name!r}')
        offs = item.get('off')
        if (not isinstance(offs, (list, tuple)) or len(offs) < 3):
            raise ModelError(
                f'{where} 的朝向 {label!r} 须给出 ≥3 个顶点偏移 off')
        offsets[label] = tuple(_int_pair(v, f'{where} 朝向 {label!r} 的 off')
                               for v in offs)
        if gops.polygon_area(list(offsets[label])) == 0:
            raise ModelError(f'{where} 的朝向 {label!r} 顶点共线（面积为 0）')

    # ---- 放置表 ----
    tiles = _need(doc, 'tiles', (list, tuple), where)
    if not tiles:
        raise ModelError(f'{where} 的 tiles 为空')
    goal = []
    seen = set()
    for i, t in enumerate(tiles):
        if not isinstance(t, dict):
            raise ModelError(f'{where} 的 tiles[{i}] 须为对象')
        p = _int_pair(t.get('p'), f'{where} 的 tiles[{i}].p')
        o = t.get('o')
        if o not in offsets:
            raise ModelError(
                f'{where} 的 tiles[{i}] 引用了未定义的朝向 {o!r}')
        if (p, o) in seen:
            raise ModelError(f'{where} 的 tiles[{i}] 与前面重复：(p={p}, o={o!r})')
        seen.add((p, o))
        gid = t.get('g', 0)
        if type(gid) is not int or gid < 0:
            raise ModelError(
                f'{where} 的 tiles[{i}].g（捆绑组号）须为非负整数，收到 {gid!r}')
        goal.append(Block(p, o, gid))

    # ---- 缝族 ----
    seams = _need(doc, 'seams', (list, tuple), where)
    if not seams:
        raise ModelError(f'{where} 的 seams 为空（永冻板型）')
    families = []
    seen_names = set()
    for i, s in enumerate(seams):
        if not isinstance(s, dict):
            raise ModelError(f'{where} 的 seams[{i}] 须为对象')
        fname = s.get('name')
        if not isinstance(fname, str) or not fname:
            raise ModelError(f'{where} 的 seams[{i}].name 须为非空字符串')
        if fname in seen_names:
            raise ModelError(f'{where} 的缝族名重复：{fname!r}')
        seen_names.add(fname)
        coeffs = _int_pair(s.get('coeffs'), f'{where} 缝族 {fname!r} 的 coeffs')
        step = _int_pair(s.get('step'), f'{where} 缝族 {fname!r} 的 step')
        if step == (0, 0):
            raise ModelError(f'{where} 缝族 {fname!r} 的 step 为零向量')
        if coeffs[0] * step[0] + coeffs[1] * step[1] != 0:
            raise ModelError(
                f'{where} 缝族 {fname!r} 的 step 不沿缝（与 coeffs 不正交）：'
                f'coeffs={coeffs}, step={step}')
        families.append(SeamFamily(fname, coeffs, (step, (-step[0], -step[1]))))

    return _assemble(name, doc, basis, scale, offsets, goal, families,
                     shapes, path)


def _assemble(name, doc, basis, scale, offsets, goal, families, shapes, path):
    """把校验过的数据组装成 BoardSpec（几何钩子全部由数据 + 通用算法推出）。"""

    def int_verts(point, orient):
        """整数坐标顶点（= 3× 真实顶点，恒为整数；身份判定用）。"""
        return tuple((point[0] + ox, point[1] + oy) for ox, oy in offsets[orient])

    def plane_of(point, orient):
        """平面坐标顶点（几何判定与渲染用）。"""
        out = []
        for vx, vy in int_verts(point, orient):
            a, b = vx / scale, vy / scale
            out.append((a * basis[0][0] + b * basis[1][0],
                        a * basis[0][1] + b * basis[1][1]))
        return tuple(out)

    def cell_polygon(point, orient):
        return plane_of(tuple(point), orient)

    def components(keys):
        return gops.components(keys, lambda k: int_verts(k[0], k[1]))

    def overlap(moved_keys, rest_keys):
        mp = [plane_of(*k) for k in moved_keys]
        rp = [plane_of(*k) for k in rest_keys]
        mb = [gops.bbox(p) for p in mp]
        rb = [gops.bbox(p) for p in rp]
        for i, a in enumerate(mp):
            for j, b in enumerate(rp):
                if not gops.boxes_overlap(mb[i], rb[j]):
                    continue
                if gops.convex_overlap(a, b):
                    return True
        return False

    def _vertex_rank(coeffs, iv):
        return coeffs[0] * iv[0] + coeffs[1] * iv[1]

    def seam_lines(board, fam):
        """该族在当前局面下的真实缝线 ((t, line), ...)。

        判据与碎三角同：存在**跨块接触边**，两端点 rank 相等 → {rank=t} 是
        一条沿块边的直线；再硬过滤「不得劈开任何块」（块被劈 ⟺ 三顶点 rank
        跨 t 两侧）。不过滤时会出现「局部贴边、别处穿块」的假缝。
        """
        keys = frozenset(board.keys)
        vmap = {k: int_verts(k[0], k[1]) for k in keys}
        ts = set()
        # 只看**被两块共用的整条边**：边的两个端点 rank 相等 → 该边整条落在
        # {rank=t} 上。不能拿「两个块之间任意一对公共顶点」去试——顶点对不
        # 一定是边（可能是两个块各自的尖角），会凑出并不存在的缝线。
        for (a, b) in gops.shared_edge_owners(vmap):
            ra = _vertex_rank(fam.coeffs, a)
            if ra == _vertex_rank(fam.coeffs, b):
                ts.add(ra)
        spans = []
        for k in keys:
            rs = [_vertex_rank(fam.coeffs, v) for v in vmap[k]]
            spans.append((min(rs), max(rs)))
        out = [t for t in sorted(ts) if not any(lo < t < hi for lo, hi in spans)]
        return tuple((t, t - 1) for t in out)

    def seam_clear(fam, t, board):
        return any(tt == t for tt, _line in seam_lines(board, fam))

    orients = tuple(sorted(offsets))
    # orient_dirs：仅用于「动作字母 ↔ 方向」双射，要求互异非零即可
    orient_dirs = tuple((i % 6 + 1, i // 6 + 1) for i in range(len(orients)))
    directions = tuple(d for fam in families for d in fam.parallel)

    # orient_steps 纯占位：本板型的连通性由 components 钩子（几何共边）给，
    # 邻接查表不参与移动。但 BoardSpec 要求「表内朝向集 == orientations 且
    # 封闭」，故每个朝向给一条自环（自身 → 自身），满足校验且不误导。
    orient_steps = tuple((o, (((1, 0), o),)) for o in orients)

    spec = BoardSpec(
        name=name,
        lattice=Lattice(dim=2, scale=1,
                        neighbor_steps=(),   # 与 orient_steps 二选一（带朝向板型）
                        symmetry='trivial',
                        orient_steps=orient_steps),
        directions=directions,
        seam_families=tuple(families),
        orientations=orients,
        goal_blocks=tuple(sorted(goal, key=lambda b: (b.point, b.orient))),
        orient_dirs=orient_dirs,
        seam_clear=seam_clear,
        solved_check=None,
        overlap=overlap,
        cell_polygon=cell_polygon,
        components=components,
        seam_lines=seam_lines,
    )
    return LoadedModel(spec, doc, path)


# ----------------------------------------------------------------------
# 目录加载
# ----------------------------------------------------------------------
def load_file(path, *, shapes_dir=None):
    """读一个模型文件（同目录下的 shapes.json 会自动作为形状库）。"""
    doc = read_json(path)
    shapes_doc = None
    ref = doc.get('shapes_ref')
    if ref:
        shape_path = os.path.join(shapes_dir or os.path.dirname(path), ref)
        if os.path.exists(shape_path):
            loaded = read_json(shape_path)
            if loaded.get('schema') != SCHEMA_SHAPES:
                raise ModelError(f'形状库 {shape_path} 的 schema 未识别')
            shapes_doc = loaded.get('shapes') or {}
    return load_model(doc, shapes=shapes_doc, path=path)


def load_dir(model_dir=None):
    """加载目录下全部模型文件，返回 {名字: LoadedModel}。"""
    model_dir = model_dir or DEFAULT_MODEL_DIR
    out = {}
    if not os.path.isdir(model_dir):
        return out
    for fname in sorted(os.listdir(model_dir)):
        if not fname.endswith('.json') or fname == 'shapes.json':
            continue
        loaded = load_file(os.path.join(model_dir, fname))
        if loaded.name in out:
            raise ModelError(f'模型名重复：{loaded.name!r}（{fname}）')
        out[loaded.name] = loaded
    return out
