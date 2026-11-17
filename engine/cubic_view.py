# -*- coding: utf-8 -*-
"""三维投影层：逻辑坐标 + 相机姿态 → 屏幕可见面多边形与深度（§54 第 1 步）。

职责边界（方案 §2.1）
    本模块**只算多边形和深度**，一律不 import pygame；渲染层拿 `pts` 交给
    `pygame.draw.polygon`。整条链路只新增这一环，其余（HUD / 面板 / 打包）复用。

世界坐标映射（与 `engine/cubic_camera.py` 同一套约定，别另立）
    block(location=(r, c, d)) 占一个单位立方体：
        X = c .. c+1  （向右）
        Y = d .. d+1  （向上）
        Z = r .. r+1  （朝观察者）
    所以「正对前方」= 从 Z 增大的一侧往回看（r 越大越靠近观察者）。

可见性（为什么够用）
    · 轴对齐单位立方体堆成长方体，没有曲面 / 纹理；
    · **背面剔除**：面法向与相机 z 轴（指向观察者）同向才画；
    · **内部面直接丢掉**：相邻块存在的那一面根本不该画（省多边形，也避免
      画家算法把内部面漏出来）；
    · **画家算法**：剩余面按面心相机深度从远到近画。轴对齐等尺寸立方体在
      正交投影下这条排序稳定（半透明混色才会出错——那正是透明度滑块缓后的原因）。
"""

from .cubic_camera import CubicCamera
#: 六个面：(轴下标, 符号, 法向)。轴 0=X(c) / 1=Y(d) / 2=Z(r)。
FACE_DEFS = (
    (0, 1, (1.0, 0.0, 0.0)),
    (0, -1, (-1.0, 0.0, 0.0)),
    (1, 1, (0.0, 1.0, 0.0)),
    (1, -1, (0.0, -1.0, 0.0)),
    (2, 1, (0.0, 0.0, 1.0)),
    (2, -1, (0.0, 0.0, -1.0)),
)

#: 法向 → 明暗系数（光从上、左、前打来）。只影响「哪面亮」，不参与任何状态
#: 表达——状态色（选中变绿）由渲染层另行处理（UI 铁律 §1 同一条精神）。
SHADE = {
    (1.0, 0.0, 0.0): 0.84,
    (-1.0, 0.0, 0.0): 0.62,
    (0.0, 1.0, 0.0): 1.0,
    (0.0, -1.0, 0.0): 0.5,
    (0.0, 0.0, 1.0): 0.74,
    (0.0, 0.0, -1.0): 0.56,
}


def block_min_corner(location) -> tuple:
    """逻辑坐标 (r, c, d) → 该块最小角的世界坐标 (x, y, z)。"""
    r, c, d = location[0], location[1], location[2]
    return (float(c), float(d), float(r))


def block_corners(location) -> tuple:
    """单位立方体的 8 个世界角点（顺序固定，供 fit / 测试用）。"""
    x0, y0, z0 = block_min_corner(location)
    x1, y1, z1 = x0 + 1.0, y0 + 1.0, z0 + 1.0
    return (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    )


def _face_quad(location, axis: int, sign: int) -> tuple:
    """某个面的 4 个世界角点（从该面外侧看是逆时针，fill 不依赖朝向）。"""
    x0, y0, z0 = block_min_corner(location)
    x1, y1, z1 = x0 + 1.0, y0 + 1.0, z0 + 1.0
    if axis == 0:
        x = x1 if sign > 0 else x0
        return ((x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1))
    if axis == 1:
        y = y1 if sign > 0 else y0
        return ((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1))
    z = z1 if sign > 0 else z0
    return ((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z))


def neighbor_location(location, axis: int, sign: int) -> tuple:
    """该面另一侧邻块的位置（用于判定「内部面」）。"""
    r, c, d = int(location[0]), int(location[1]), int(location[2])
    if axis == 0:
        return (r, c + sign, d)
    if axis == 1:
        return (r, c, d + sign)
    return (r + sign, c, d)


def project_point(world, camera: CubicCamera, scale: float, origin) -> tuple:
    """世界点 → (屏幕 x, 屏幕 y, 相机深度)。屏幕上 y 轴向下，故取负。"""
    vx, vy, vz = camera.to_camera(world)
    return (origin[0] + scale * vx, origin[1] - scale * vy, vz)


def fit_view(blocks, camera: CubicCamera, width: int, height: int, *,
             margin: int = 40, zoom: float = 1.0) -> tuple:
    """把整盘装进画面：返回 (scale, origin)。

    scale = 每个立方体边长多少像素；origin 让相机空间包围盒的中心落在屏幕中心
    （方案 §2.2「居中 = 质心落在屏幕中心」，这里先用几何包围盒中心，跟随质心
    是第 3 步的事）。
    """
    pts = [p for loc in locations_of(blocks) for p in block_corners(loc)]
    if not pts:
        return 40.0 * zoom, (width / 2.0, height / 2.0)
    cam_pts = [camera.to_camera(p) for p in pts]
    xs = [p[0] for p in cam_pts]
    ys = [p[1] for p in cam_pts]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    avail_w = max(1.0, width - 2 * margin)
    avail_h = max(1.0, height - 2 * margin)
    sx = avail_w / span_x if span_x > 1e-9 else avail_w
    sy = avail_h / span_y if span_y > 1e-9 else avail_h
    scale = min(sx, sy) * max(0.05, float(zoom))
    cx = (max(xs) + min(xs)) / 2.0
    cy = (max(ys) + min(ys)) / 2.0
    return scale, (width / 2.0 - scale * cx, height / 2.0 + scale * cy)


def locations_of(blocks) -> set:
    """块列表 → 整数三元组位置集合。

    同时接受两种输入：带 `.location` 的块对象（EngineGame / game.Block）与裸
    位置元组——测试和将来的渲染缓存都会用到后者。
    """
    out = set()
    for b in blocks:
        loc = b.location if hasattr(b, 'location') else b
        out.add((int(loc[0]), int(loc[1]), int(loc[2])))
    return out


def collect_faces(blocks, camera: CubicCamera, *, scale: float, origin) -> list:
    """算出**当前可见**的面（背面剔除 + 内部面剔除 + 画家排序）。

    返回列表，每项：
        {'pts': [(sx, sy) × 4], 'depth': 相机深度（大 = 近）,
         'shade': 明暗系数, 'normal': 世界法向, 'loc': (r, c, d),
         'axis': 轴下标, 'sign': ±1}
    排序：depth 从小到大（远的先画、近的后画 → 前面的块盖住后面的块）。
    """
    locations = locations_of(blocks)
    view_z = camera.view_axis()
    out = []
    for loc in locations:
        for axis, sign, normal in FACE_DEFS:
            if tuple(neighbor_location(loc, axis, sign)) in locations:
                continue                       # 内部面：两边都有块，画出来只会漏底
            if sum(n * v for n, v in zip(normal, view_z)) <= 1e-9:
                continue                       # 背面：法向朝里，看不见
            quad = _face_quad(loc, axis, sign)
            pts = []
            depth = 0.0
            for w in quad:
                sx, sy, sz = project_point(w, camera, scale, origin)
                pts.append((sx, sy))
                depth += sz
            depth /= len(quad)                 # 面心深度（画家算法只用它排序）
            out.append({
                'pts': pts,
                'depth': depth,
                'shade': SHADE[normal],
                'normal': normal,
                'loc': loc,
                'axis': axis,
                'sign': sign,
            })
    out.sort(key=lambda f: f['depth'])
    return out


def build_scene(blocks, camera: CubicCamera, width: int, height: int, *,
                margin: int = 40, zoom: float = 1.0,
                origin_offset=(0.0, 0.0)) -> dict:
    """一步到位：装画面 + 算可见面。渲染层只要拿 'faces' 去画。"""
    scale, origin = fit_view(blocks, camera, width, height,
                             margin=margin, zoom=zoom)
    origin = (origin[0] + origin_offset[0], origin[1] + origin_offset[1])
    faces = collect_faces(blocks, camera, scale=scale, origin=origin)
    return {
        'faces': faces,
        'scale': scale,
        'origin': origin,
        'camera': camera,
        'block_count': len(locations_of(blocks)),
    }
