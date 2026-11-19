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

#: 法向 → 明暗系数（旧版固定光，保留给外部/旧调用；真实渲染走 face_shade）。
#: 只影响「哪面亮」，不参与任何状态表达——状态色（选中变绿）由渲染层另行处理。
SHADE = {
    (1.0, 0.0, 0.0): 0.84,
    (-1.0, 0.0, 0.0): 0.62,
    (0.0, 1.0, 0.0): 1.0,
    (0.0, -1.0, 0.0): 0.5,
    (0.0, 0.0, 1.0): 0.74,
    (0.0, 0.0, -1.0): 0.56,
}

#: 棚拍式打光：环境光把每个可见面托到 0.68 以上，主光只负责「哪面更亮」，
#: 再叠一点朝向相机的补光。旧 SHADE 的背光面只有 0.5，乘在本来就偏深的
#: 蓝色块上会直接糊成黑块——用户 2026-11-19 报「一半亮、一半纯暗」。
_SHADE_AMBIENT = 0.68
_SHADE_KEY = 0.28
_SHADE_FILL = 0.10


def face_shade(normal, camera) -> float:
    """单面明暗系数：环境光 + 相机相对主光 + 相机补光。

    主光不固定在世界里，而是跟着相机取「屏幕左上」方向：
    ``L = normalize(-0.55·right + 0.75·up + 0.35·view)``。
    这样无论转到哪一面，三个可见面都保持同一种「上亮、侧暗」的层次；
    环境光 0.68 保证背光面仍有颜色，不会出现「一半纯黑」。
    """
    right = camera.right_axis()
    up = camera.up_axis()
    view = camera.view_axis()
    light = tuple(-0.55 * right[i] + 0.75 * up[i] + 0.35 * view[i]
                  for i in range(3))
    length = sum(v * v for v in light) ** 0.5
    if length > 1e-12:
        light = tuple(v / length for v in light)
    key = max(0.0, sum(float(n) * l for n, l in zip(normal, light)))
    fill = max(0.0, sum(float(n) * v for n, v in zip(normal, view)))
    return min(1.0, _SHADE_AMBIENT + _SHADE_KEY * key + _SHADE_FILL * fill)

#: 默认拆分（相邻两块表面之间空多少「格」）。0 = 未拆分，块贴死成一整块，
#: 投影上只有一层外轮廓、前後遮挡无从判读；给一点缝，缝里的面和前后关系才
#: 看得出来（块大小不变，只把中心距从 1 格拉到 1+gap）。
DEFAULT_GAP = 0.12


def layout_anchor(blocks) -> tuple:
    """当前块堆的**包围盒中心**（世界坐标 X/Y/Z）。

    拆分以它为中心向外散：两组块的位置/数量不变时，拉开间距只会让整堆
    对称变胖，不会把整盘往某一侧顶出去，也不会逼相机重新取景。
    """
    locs = locations_of(blocks)
    if not locs:
        return (0.5, 0.5, 0.5)
    # 逻辑 (r, c, d) → 世界 (X, Y, Z) = (c, d, r)
    world = [(p[1], p[2], p[0]) for p in locs]
    lo = [min(p[i] for p in world) for i in range(3)]
    hi = [max(p[i] for p in world) + 1 for i in range(3)]
    return tuple((lo[i] + hi[i]) / 2.0 for i in range(3))


def block_min_corner(location, gap: float = 0.0,
                     anchor=None) -> tuple:
    """逻辑坐标 (r, c, d) → 该块最小角的世界坐标 (x, y, z)。

    gap = **拆分**：滑块**大小不变**（始终 1 格边长），只把相邻块的中心距
    从 1 格拉开到 ``1 + gap``，于是两个相邻块表面之间正好空出 gap。
    anchor = 拆分中心（世界坐标，默认 ``(0.5, 0.5, 0.5)``，即第一格中心；
    渲染/拾取都传 `layout_anchor(blocks)` 的包围盒中心，整堆对称散开）。

    gap=0 = 完全未拆分（块贴死，投影上只是一个大方块，前後遮挡无从判读）；
    上限 <1.0（再大块与块之间就隔出一整个块身，超出当前滑条范围）。
    """
    if not 0.0 <= gap < 1.0:
        raise ValueError(f'拆分 gap 须在 [0, 1) 内，收到 {gap!r}')
    r, c, d = location[0], location[1], location[2]
    if anchor is None:
        anchor = (0.5, 0.5, 0.5)
    pitch = 1.0 + gap
    half = gap / 2.0
    # min = k·(1+gap) + gap/2 − anchor·gap：中心距变 1+gap，整堆以 anchor 对称散开。
    return (float(c) * pitch + half - float(anchor[0]) * gap,
            float(d) * pitch + half - float(anchor[1]) * gap,
            float(r) * pitch + half - float(anchor[2]) * gap)


def block_center(location, gap: float = 0.0, anchor=None) -> tuple:
    """块心世界坐标（跟随质心/切面分侧共用同一口径）。"""
    x0, y0, z0 = block_min_corner(location, gap, anchor)
    return (x0 + 0.5, y0 + 0.5, z0 + 0.5)


def block_corners(location, gap: float = 0.0, anchor=None) -> tuple:
    """单位立方体的 8 个世界角点（拆分只拉间距，边长恒为 1）。"""
    x0, y0, z0 = block_min_corner(location, gap, anchor)
    x1 = x0 + 1.0
    y1 = y0 + 1.0
    z1 = z0 + 1.0
    return (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    )


def _face_quad(location, axis: int, sign: int, gap: float = 0.0,
               anchor=None) -> tuple:
    """某个面的 4 个世界角点（从该面外侧看是逆时针，fill 不依赖朝向）。"""
    x0, y0, z0 = block_min_corner(location, gap, anchor)
    x1 = x0 + 1.0
    y1 = y0 + 1.0
    z1 = z0 + 1.0
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


def screen_to_plane(screen, camera: CubicCamera, scale: float, origin,
                    axis: int, coord: float):
    """屏幕点 → 指定轴对齐平面上的世界点（正交投影的逆解）。

    用途：把「玩家上一次点击的位置」钉回世界坐标。方向箭头要贴着点击处，
    但世界几何要跟着盘转，不能存屏幕坐标；于是把点击射线投到当前切面上，
    得到平面上的世界点。平面与视线平行时无解，返回 None。
    """
    if scale <= 1e-9:
        return None
    rows = camera.rows()
    vx = (float(screen[0]) - float(origin[0])) / float(scale)
    vy = (float(origin[1]) - float(screen[1])) / float(scale)
    base = [vx * rows[0][i] + vy * rows[1][i] for i in range(3)]
    denom = rows[2][axis]
    if abs(denom) < 1e-9:
        return None
    vz = (float(coord) - base[axis]) / denom
    return tuple(base[i] + vz * rows[2][i] for i in range(3))


def stable_frame(blocks, camera: CubicCamera, width: int, height: int, *,
                 margin: int = 40, zoom: float = 1.0, gap: float = 0.0,
                 center=None, frame_scale=None) -> tuple:
    """不随朝向、也不随拆分变形的装画面：返回 (scale, origin)。

    为什么另有一套：`fit_view` 按**当前朝向的投影包围盒**拟合，一旋转投影范围
    就变，scale 跟着变——实测就是「拖一下画面忽大忽小」。这里把比例只由
    **未拆分的逻辑块身**（每块 1 格、gap 恒按 0 算）的包围球半径决定，于是：
    旋转只转不缩放；拆分只把块往外拉开，既不缩块也不动相机；每个块在屏幕上
    显示多大**只**由 zoom（缩放滑条 / Ctrl+滚轮）决定。

    center：装画面的参考点（方案 §2.2「居中 = 质心落在屏幕中心」）。给了就用它
    ——「跟随质心」把滑块组的质心锁在屏幕中心，整盘滑动时不会慢慢漂走；
    不给仍用包围盒中心（换局/读档时的过场口径）。

    frame_scale：外部冻结的**未缩放**比例（不含 zoom）。三维打乱期间边界会
    临时胀大，若每帧照包围球重算，块会跟着一起忽大忽小；调用方传一次冻结值，
    这里只乘当前 zoom，缩放滑条仍然有效。
    """
    # 拆分不参与装画面：半径用 gap=0 的块身算，块的位置仍按逻辑坐标。
    pts = [p for loc in locations_of(blocks) for p in block_corners(loc, 0.0)]
    if not pts:
        return 40.0 * zoom, (width / 2.0, height / 2.0)
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    if center is None:
        center = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
    else:
        center = tuple(float(v) for v in center)
    if frame_scale is not None:
        scale = max(0.05, float(frame_scale)) * max(0.05, float(zoom))
    else:
        # 比例只跟**几何外框**有关（包围盒中心到最远角），与 origin 用的参考点无关：
        # 否则跟随质心时块一动半径就变，缩放跟着跳，「旋转/滑动画面忽大忽小」的旧病
        # 会以另一种形式回来。
        bbox_center = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
        radius = max(1e-6, max(
            sum((p[i] - bbox_center[i]) ** 2 for i in range(3)) ** 0.5 for p in pts))
        avail_w = max(1.0, width - 2 * margin)
        avail_h = max(1.0, height - 2 * margin)
        scale = min(avail_w, avail_h) / (2.0 * radius) * max(0.05, float(zoom))
    cvx, cvy, _ = camera.to_camera(center)
    return scale, (width / 2.0 - scale * cvx, height / 2.0 + scale * cvy)


def fit_view(blocks, camera: CubicCamera, width: int, height: int, *,
             margin: int = 40, zoom: float = 1.0, gap: float = 0.0) -> tuple:
    """把整盘装进画面：返回 (scale, origin)。

    scale = 每个立方体边长多少像素；origin 让相机空间包围盒的中心落在屏幕中心
    （方案 §2.2「居中 = 质心落在屏幕中心」，这里先用几何包围盒中心，跟随质心
    是第 3 步的事）。拆分不参与装画面：比例按未拆分的逻辑块身算，改拆分不会
    改变缩放（与 `stable_frame` 同口径）。
    """
    pts = [p for loc in locations_of(blocks) for p in block_corners(loc, 0.0)]
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


def collect_faces(blocks, camera: CubicCamera, *, scale: float, origin,
                  gap: float = 0.0, offsets=None, anchor=None) -> list:
    """算出**当前可见**的面（背面剔除 + 内部面剔除 + 画家排序）。

    gap = 拆分距离（见 block_min_corner）。**gap>0 时不再剔除内部面**：块与块
    之间空出了一条缝，站在斜视角度正好能看见缝里的那一面——这时候还按「邻块
    存在就当内部面」去删，画面会出现「该有的面不见了」的漏块感。
    gap=0（未拆分）才按邻块剔除内部面。**三维动画有 offsets 时**，移动块及其
    相邻块不剔除：动画把贴死的块拉开，旧判据会把刚露出的面当内部面删掉，
    背景就从缺口里透出来（黑块）。anchor 默认取当前块堆的包围盒中心。

    返回列表，每项：
        {'pts': [(sx, sy) × 4], 'depth': 相机深度（大 = 近）,
         'shade': 明暗系数, 'normal': 世界法向, 'loc': (r, c, d),
         'axis': 轴下标, 'sign': ±1}
    排序：depth 从小到大（远的先画、近的后画 → 前面的块盖住后面的块）。
    """
    locations = locations_of(blocks)
    if anchor is None:
        anchor = layout_anchor(blocks)
    view_z = camera.view_axis()
    solid = gap < 1e-9
    # 三维动画期间，移动块（及其相邻块）之间原本贴死的内部面会被拉开。
    # 未拆分（gap=0）时仍按「邻块存在」剔除这些面，就会在滑开的一瞬露出
    # 背景黑块（用户 2026-11-18「无限打乱 + 关选中动画 + 开滑动动画，偶尔
    # 某些地方变黑」）。这里只在**两边都不在移动集合**时才剔除内部面：
    # 静止区仍走零成本剔除，移动带上的面全部画出来。
    moving = frozenset(offsets.keys()) if offsets else frozenset()
    out = []
    for loc in locations:
        for axis, sign, normal in FACE_DEFS:
            neighbor = tuple(neighbor_location(loc, axis, sign))
            if solid and loc not in moving and neighbor not in moving \
                    and neighbor in locations:
                continue                       # 两边都静止：内部面画出来只会漏底
            if sum(n * v for n, v in zip(normal, view_z)) <= 1e-9:
                continue                       # 背面：法向朝里，看不见
            quad = _face_quad(loc, axis, sign, gap, anchor)
            if offsets:
                # 三维动画（§54 第 6 步）：逻辑已提交，渲染层给「刚动过的块」
                # 一个还在收尾的位移，画面上就是滑过去的一段。
                off = offsets.get(loc)
                if off is not None:
                    quad = tuple((w[0] + off[0], w[1] + off[1], w[2] + off[2])
                                 for w in quad)
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
                'shade': face_shade(normal, camera),
                'normal': normal,
                'loc': loc,
                'axis': axis,
                'sign': sign,
            })
    out.sort(key=lambda f: f['depth'])
    return out


def block_boxes(blocks, gap: float = 0.0, offsets=None, anchor=None) -> list:
    """每个块的世界 AABB（(x0, y0, z0, x1, y1, z1)），含拆分间距。

    拆分只改相邻块中心距，块边长恒为 1，整堆以 anchor（默认包围盒中心）
    对称散开；offsets 给了就给该块的盒子整体平移（动画渲染期用；判定/拾取
    仍用原位）。
    """
    out = []
    edge = 1.0
    if anchor is None:
        anchor = layout_anchor(blocks)
    for loc in locations_of(blocks):
        x0, y0, z0 = block_min_corner(loc, gap, anchor)
        if offsets:
            off = offsets.get(loc)
            if off is not None:
                x0, y0, z0 = x0 + off[0], y0 + off[1], z0 + off[2]
        out.append((x0, y0, z0, x0 + edge, y0 + edge, z0 + edge))
    return out


def _ray_hits_box(origin, direction, box, eps: float = 1e-6) -> bool:
    """射线（从 origin 沿 direction 朝相机）是否穿过轴对齐盒子。"""
    t_enter, t_exit = -1e18, 1e18
    for i in range(3):
        d = direction[i]
        if abs(d) < 1e-12:
            if origin[i] < box[i] or origin[i] > box[i + 3]:
                return False
            continue
        t1 = (box[i] - origin[i]) / d
        t2 = (box[i + 3] - origin[i]) / d
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > t_enter:
            t_enter = t1
        if t2 < t_exit:
            t_exit = t2
        if t_enter > t_exit:
            return False
    return t_exit > eps and t_enter > -1e18


def _convex_hull(points) -> list:
    """二维凸包（Andrew monotone chain）。点按 (u, v) 传入，返回逆时针顶点。"""
    pts = sorted(set((round(p[0], 9), round(p[1], 9)) for p in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def seam_shadow_polygons(quad, boxes, view_dir, eps: float = 1e-6):
    """每个**挡在切面前面**的块，在切面上投下的影子多边形（精确，不是栅格）。

    为什么需要：切面活在块与块的缝里，按格采样只能得到「格子级」的可见性，
    边缘就被切成锯齿（用户 2026-11-18「遮擋畫的毛毛糙糙」）。这里是解析解：
    沿视线把块的 AABB 投到切面上，得到的凸包（一般是六边形）就是它挡住的
    那块面积，边界是平滑的直线。

    返回 (shadows, n)：
        shadows —— [(世界点 × N)]，都在切面平面上，按屏幕坐标可直接填充
        n       —— 平面法向轴下标；视线与该轴近似平行（切面接近侧对）时返回
                   (None, axis)，交给调用方走逐格采样兜底
    """
    axis = None
    for i in range(3):
        if all(abs(p[i] - quad[0][i]) < 1e-9 for p in quad):
            axis = i
            break
    if axis is None:
        return None, None
    fixed = quad[0][axis]
    d = view_dir[axis]
    if abs(d) < 1e-3:
        # 视线与切面平行：投影求交退化（分母趋零），而这种姿态下切面在屏幕上
        # 只剩一条线、本来就没有可见面积，直接当作「没有可见部分」。
        return [], axis
    others = [i for i in range(3) if i != axis]
    shadows = []
    for box in boxes:
        # 只有「朝相机那一侧」的块能挡住切面。相机在 +axis 一侧时看 box 上限，
        # 在 −axis 一侧时看下限（切面可以被从上下任意一侧看，不能写死方向）。
        if d > 0.0:
            if box[axis + 3] <= fixed + eps:
                continue
        else:
            if box[axis] >= fixed - eps:
                continue
        pts = []
        for xi in (box[0], box[3]):
            for yi in (box[1], box[4]):
                for zi in (box[2], box[5]):
                    corner = (xi, yi, zi)
                    t = (corner[axis] - fixed) / d
                    if t <= eps:
                        continue   # 该角在切面背后，不参与投影
                    p = [corner[k] - t * view_dir[k] for k in range(3)]
                    p[axis] = fixed
                    pts.append(tuple(p))
        if len(pts) < 3:
            continue
        hull2d = _convex_hull([(p[others[0]], p[others[1]]) for p in pts])
        if len(hull2d) < 3:
            continue
        world = []
        for (u, v) in hull2d:
            p = [0.0, 0.0, 0.0]
            p[axis] = fixed
            p[others[0]] = u
            p[others[1]] = v
            world.append(tuple(p))
        shadows.append(world)
    return shadows, axis


def screen_hull_of_box(box, camera: CubicCamera, scale: float, origin) -> list:
    """一个轴对齐盒子在屏幕上的凸包（用于判断「这个屏幕位置有没有块」）。

    用途：三维方向箭头要贴在切面缝口上，而缝口在斜视下会投影到**别的块**的
    脸上。光判「锚点沿视线没被挡住」不够——锚点可能恰好在块前面，画上去却像
    贴纸糊在人家脸上。所以再判一次：锚点的屏幕位置是否落在「更靠近相机的块」
    的投影轮廓里；在里面就不画。
    """
    pts = []
    for xi in (box[0], box[3]):
        for yi in (box[1], box[4]):
            for zi in (box[2], box[5]):
                sx, sy, _sz = project_point((xi, yi, zi), camera, scale, origin)
                pts.append((sx, sy))
    return _convex_hull([(round(p[0], 6), round(p[1], 6)) for p in pts])


def point_in_hull(x, y, hull) -> bool:
    """点是否在凸多边形内（顶点逆时针）。"""
    if len(hull) < 3:
        return False
    for i in range(len(hull)):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % len(hull)]
        if (bx - ax) * (y - ay) - (by - ay) * (x - ax) < 0:
            return False
    return True


def point_visible(point, boxes, view_dir, eps: float = 1e-6) -> bool:
    """世界点沿视线朝相机走，是否被某个块挡住（被挡住 = 不该画出来）。

    为什么不用画家序一条排序了事：切面在块与块的缝隙里，一张面按 1/3 块宽
    粗切时，一格会同时压住「该被挡」和「该露出来」两个区域，只能按格心深度
    一刀切 → 出现红边爬过前面块（用户 2026-11-18「边界线被遮住还画出来」）。
    这里对每个采样点精确求交，所见即真实。

    剪枝：只测「比该点更靠近相机」的块（更远的块挡不住它）。缝隙里的采样点
    本来只有一半方块在它前方，先把名单砍掉一半再逐个求交。
    """
    base = sum(point[i] * view_dir[i] for i in range(3))
    for box in boxes:
        # 盒子沿视线方向的投影区间 [lo, hi]；hi < base - eps 表示整块在该点后面
        proj = [0.0] * 8
        idx = 0
        for xi in (box[0], box[3]):
            for yi in (box[1], box[4]):
                for zi in (box[2], box[5]):
                    proj[idx] = xi * view_dir[0] + yi * view_dir[1] + zi * view_dir[2]
                    idx += 1
        if max(proj) < base - eps:
            continue
        if _ray_hits_box(point, view_dir, box, eps):
            return False
    return True


def build_scene(blocks, camera: CubicCamera, width: int, height: int, *,
                margin: int = 40, zoom: float = 1.0,
                origin_offset=(0.0, 0.0), gap: float = 0.0,
                offsets=None, center=None, frame_scale=None) -> dict:
    """一步到位：装画面 + 算可见面。渲染层只要拿 'faces' 去画。

    ⚠️ 装画面用 `stable_frame`（包围球定比例），不是 `fit_view`（按当前朝向的
    投影包围盒拟合）。后者每帧跟着朝向变 → 拖动时画面忽大忽小；三维的「多大」
    只该由缩放参数决定。

    center：装画面的参考点（「跟随质心」传块质心；None = 包围盒中心）。
    """
    scale, origin = stable_frame(blocks, camera, width, height,
                                 margin=margin, zoom=zoom, gap=gap,
                                 center=center, frame_scale=frame_scale)
    origin = (origin[0] + origin_offset[0], origin[1] + origin_offset[1])
    # 幽灵预览必须和真盘共用同一个拆分锚点：只拿目标单块调 collect_faces
    # 时，默认 anchor 会变成那块自己的中心，gap>0 下投影整体偏一格。
    anchor = layout_anchor(blocks)
    faces = collect_faces(blocks, camera, scale=scale, origin=origin, gap=gap,
                          offsets=offsets, anchor=anchor)
    return {
        'faces': faces,
        'scale': scale,
        'origin': origin,
        'camera': camera,
        'gap': gap,
        'anchor': anchor,
        'offsets': offsets,
        'block_count': len(locations_of(blocks)),
    }
