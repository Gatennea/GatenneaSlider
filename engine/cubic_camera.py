# -*- coding: utf-8 -*-
"""三维相机姿态（四元数）——§54 第 1 步。

为什么是四元数（方案 §2.2）
    正对六面时「哪条边朝屏幕上」是 roll 自由度，纯 yaw/pitch 在俯仰 ±90° 会退化
    （万向锁），而正对化要插值吸附到最近的正对方向。四元数能精确表达 24 个
    轴对齐姿态（六面 × 四种 roll），也不退化的旋转插值。

坐标与基的约定（本模块就是「唯一真源」，别在别处另立一套）
    · 世界轴 X/Y/Z 对应逻辑坐标 (c, d, r)：X 向右、Y 向上、Z 朝观察者。
      于是「正对前方」= 从 +Z（即 r 增大的一侧）看过去。
    · 相机基 (x, y, z)：x 屏幕向右、y 屏幕向上、z **指向观察者**（右手系
      x × y = z）。
    · 姿态四元数 q 对应的旋转矩阵 R 把**世界向量转到相机坐标**：v_cam = R·v_world
      （R 的三行分别是相机 x/y/z 轴在世界中的方向）。

本模块纯数学，不 import pygame：`engine/cubic_view.py` 与它一起被渲染层和
测试直接调用（与 game.py 不准 import pygame 同一条纪律）。
"""

import math

#: 六正对视角的基：每项 = (相机 x 轴, 相机 y 轴, 相机 z 轴)，都是世界轴方向。
#: z 轴 = 「哪一面正对观察者」（+X/+Y/+Z 或它们的反向）。
#: roll 取规范：竖直方向永远是 +Y，除非正对的就是 ±Y（此时屏幕向上取 −Z / +Z，
#: 保证「从上往下看时，r 增大的方向朝屏幕下方」这张图能一眼认出来）。
FACE_BASIS = (
    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),     # 正面（+Z）
    ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)),   # 背面（-Z）
    ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),    # 右面（+X）
    ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),    # 左面（-X）
    ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),    # 顶面（+Y）
    ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),    # 底面（-Y）
)

#: 六个「朝向」的名称。基准姿态取自 FACE_BASIS（相机 z 轴正对该面方向），
#: 再绕**相机自己的右轴**倾斜一个 residue（见 face_view_rotation）。
FACE_VIEW_LABELS = ('前 +Z', '后 −Z', '右 +X', '左 −X', '上 +Y', '下 −Y')

#: 六朝向的默认倾斜（度）：(绕相机上轴, 绕相机右轴)。用户口径（2026-11-17）：
#: 六个朝向都**不该正对**——正对时实心 3×3×3 在屏幕上与二维 3×3 一模一样，
#: 深度全靠猜。两轴都给一点，才同时露出另外两个邻面（各一条细边）；只给一条
#: 轴的话第三个面正好侧过去（面积为零），看着就像只画了两面。
DEFAULT_VIEW_RESIDUE = (14.0, 14.0)

#: 默认斜视（第 1 步就在用的那一档）。
OBLIQUE_ANGLES = (-32.0, 24.0, 0.0)


def face_view_rotation(index: int, tilt_deg: float = DEFAULT_VIEW_RESIDUE):
    """第 index 个朝向的姿态：正对该面 + 绕相机右轴的统一倾斜。

    倾斜只转 `up`/`toward`、**不动 right**，所以主面的某一边永远贴着屏幕横/
    竖（六张图各自规整、朝向一致），另一条边也仍在屏幕竖向上（只是透视缩短），
    同时露出相邻一面的细边——深度与遮挡就读得出来。用户口径（2026-11-17）：
    六个朝向都不该正对（正对时实心 3×3×3 与二维 3×3 长得一模一样）。
    """
    if not 0 <= index < len(FACE_BASIS):
        raise ValueError(f'视角序号越界: {index}')
    # 两轴偏角都绕**原始**的 up / right 轴，且三根基矢量走同一个复合旋转
    # R = Rx(tilt)·Ry(yaw)：主面的两条世界边随后在相机空间里仍各自落在一条
    # 屏幕轴上（横/竖），六张图才规整、朝向一致；两个邻面同时斜进来一点（各
    # 一条细边），三个面都可见 → 深度读得出来。
    right0, up0, toward0 = FACE_BASIS[index]
    yaw_off, tilt_off = (tilt_deg if isinstance(tilt_deg, tuple)
                         else (tilt_deg * 0.7, tilt_deg))

    def _turn(v):
        return _rodrigues(_rodrigues(v, up0, yaw_off), right0, tilt_off)

    return CubicCamera.from_basis(_turn(right0), _turn(up0), _turn(toward0))


def _rodrigues(vec, axis, angle_deg: float):
    """罗德里格斯公式：把 vec 绕单位轴 axis 转 angle_deg 度。"""
    vx, vy, vz = vec
    kx, ky, kz = axis
    cos_a = math.cos(math.radians(angle_deg))
    sin_a = math.sin(math.radians(angle_deg))
    dot = vx * kx + vy * ky + vz * kz
    cross = (ky * vz - kz * vy,
             kz * vx - kx * vz,
             kx * vy - ky * vx)
    return (vx * cos_a + cross[0] * sin_a + kx * dot * (1 - cos_a),
            vy * cos_a + cross[1] * sin_a + ky * dot * (1 - cos_a),
            vz * cos_a + cross[2] * sin_a + kz * dot * (1 - cos_a))


class CubicCamera:
    """相机姿态：只存一个单位四元数 (w, x, y, z)。"""

    __slots__ = ('q',)

    def __init__(self, quat=(1.0, 0.0, 0.0, 0.0)):
        w, x, y, z = (float(v) for v in quat)
        n = math.sqrt(w * w + x * x + y * y + z * z)
        if n < 1e-12:
            raise ValueError(f'四元数长度为零: {quat!r}')
        self.q = (w / n, x / n, y / n, z / n)

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------
    @classmethod
    def identity(cls):
        """默认姿态：正对 +Z（从 r 增大的一侧看），屏幕上方是 +Y。"""
        return cls()

    @classmethod
    def from_basis(cls, right, up, toward):
        """三根互相垂直的世界方向（相机 x/y/z 轴）→ 姿态。"""
        rows = (tuple(right), tuple(up), tuple(toward))
        return cls(_quat_from_rows(rows))

    @classmethod
    def from_yaw_pitch(cls, yaw_deg: float, pitch_deg: float,
                       roll_deg: float = 0.0):
        """拖动用的连续姿态：先绕世界 Y（竖直轴）转向，再绕世界 X 抬头/低头。

        只供「看」的自由旋转用；正对化另有 nearest_face_view()。
        默认斜视取 yaw=-30、pitch=22 一档（三面可见，最容易看出前后遮挡）。
        """
        qy = _axis_angle((0.0, 1.0, 0.0), math.radians(yaw_deg))
        qx = _axis_angle((1.0, 0.0, 0.0), math.radians(pitch_deg))
        qr = _axis_angle((0.0, 0.0, 1.0), math.radians(roll_deg))
        return cls(_qmul(qr, _qmul(qx, qy)))

    @classmethod
    def oblique_default(cls):
        """第 1 步的默认视角（斜视，三面可见）。"""
        return cls.from_yaw_pitch(*OBLIQUE_ANGLES)

    @classmethod
    def from_view_angles(cls, index: int, tilt_deg=DEFAULT_VIEW_RESIDUE):
        """六朝向之一（带倾斜偏角）的姿态。"""
        return face_view_rotation(index, tilt_deg)

    @classmethod
    def face_views(cls):
        """六个正对视角（顺序与 FACE_BASIS 一致）。"""
        return tuple(cls.from_basis(*basis) for basis in FACE_BASIS)

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------
    def rows(self):
        """旋转矩阵的三行 = 相机 x/y/z 轴在世界中的方向（单位向量）。"""
        w, x, y, z = self.q
        return (
            (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
            (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
            (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
        )

    def to_camera(self, vec):
        """世界向量 → 相机坐标（R·v）。"""
        return tuple(row[0] * vec[0] + row[1] * vec[1] + row[2] * vec[2]
                     for row in self.rows())

    def view_axis(self):
        """指向观察者那一轴在世界中的方向（= R 的第三行）。"""
        return self.rows()[2]

    def up_axis(self):
        return self.rows()[1]

    def right_axis(self):
        return self.rows()[0]

    def is_axis_aligned(self, tol: float = 1e-9) -> bool:
        """姿态是否已正对某一面（三轴都与世界轴平行）。"""
        for row in self.rows():
            if max(abs(v) for v in row) < 1 - tol:
                return False
        return True

    def nearest_face_view(self):
        """离当前姿态最近的「正对」姿态（吸附用）。

        判据 = 相机 z 轴与六个正对方向的点积，取最大者（正对视角的 z 轴就是
        那一面的法向）；这正是「转回最近的一面」的直觉定义。
        """
        z = self.view_axis()
        best, best_dot = None, -2.0
        for cam in self.face_views():
            dot = sum(a * b for a, b in zip(z, cam.view_axis()))
            if dot > best_dot:
                best, best_dot = cam, dot
        return best

    def slerp(self, other, t: float):
        """四元数插值（t∈[0,1]）：给「吸附回正对视角」的过渡动画用。"""
        t = max(0.0, min(1.0, float(t)))
        a, b = self.q, other.q
        dot = sum(x * y for x, y in zip(a, b))
        if dot < 0:                      # 取短弧：反号等价的姿态视作同一个
            b = tuple(-v for v in b)
            dot = -dot
        dot = min(1.0, max(-1.0, dot))
        if dot > 0.9995:                 # 几乎重合：退回线性插值，避免除零
            out = tuple(x + (y - x) * t for x, y in zip(a, b))
            return CubicCamera(out)
        theta = math.acos(dot)
        sin_t = math.sin(theta)
        wa = math.sin((1 - t) * theta) / sin_t
        wb = math.sin(t * theta) / sin_t
        return CubicCamera(tuple(x * wa + y * wb for x, y in zip(a, b)))

    def rotated(self, axis, angle_deg: float):
        """绕**世界轴**再转一个角度（拖动旋转用；方向按世界轴给，手感一致）。"""
        dq = _axis_angle(axis, math.radians(angle_deg))
        return CubicCamera(_qmul(dq, self.q))

    def spin(self, axis, angle_deg: float):
        """绕**世界轴**转，但直接转三根基矢量（不依赖四元数乘序的约定）。

        拖动手势与六朝向倾斜都走这里：三根轴一起转，得到的仍是一组正交基，
        与 `from_basis` 同源，符号不会因为乘序（q·dq 还是 dq·q）翻掉。
        """
        axis = tuple(float(v) for v in axis)
        n = math.sqrt(sum(v * v for v in axis))
        if n < 1e-12:
            raise ValueError('旋转轴长度为零')
        axis = tuple(v / n for v in axis)
        base = self.rows()
        rows = [_rodrigues(v, axis, angle_deg) for v in base]
        return CubicCamera(_quat_from_rows(rows))

    def decompose(self):
        """当前姿态 → (yaw, pitch, roll)，与 ``from_yaw_pitch`` 互逆。

        相机 z 轴在本模块约定下是 z = (−cos p·sin y, sin p, cos p·cos y)，先由它
        解出 yaw/pitch；剩下的「面内旋转」用实际 up 轴在参考姿态的 (right, up)
        平面里量相位得到 roll。拖动旋转只用 yaw/pitch，六朝向切过来必须能把
        同一姿态还原成这三个角，否则一切视角画面就会跳。
        """
        z = self.view_axis()
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, z[1]))))
        yaw = math.degrees(math.atan2(-z[0], z[2]))
        ref = CubicCamera.from_yaw_pitch(yaw, pitch)
        up = self.up_axis()
        rx, ry = ref.right_axis(), ref.up_axis()
        roll = math.degrees(math.atan2(
            sum(a * b for a, b in zip(up, rx)),
            sum(a * b for a, b in zip(up, ry))))
        return (yaw, pitch, roll)

    def as_tuple(self):
        return self.q

    def __repr__(self):  # pragma: no cover - 调试用
        return f'CubicCamera(q={tuple(round(v, 4) for v in self.q)})'


# ----------------------------------------------------------------------
# 四元数小工具（内部用，纯函数）
# ----------------------------------------------------------------------
def _qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _axis_angle(axis, angle):
    ax, ay, az = axis
    n = math.sqrt(ax * ax + ay * ay + az * az)
    if n < 1e-12:
        raise ValueError('旋转轴长度为零')
    ax, ay, az = ax / n, ay / n, az / n
    s = math.sin(angle / 2.0)
    return (math.cos(angle / 2.0), ax * s, ay * s, az * s)


def _quat_from_rows(rows):
    """旋转矩阵（世界→相机，行为相机三轴）→ 四元数。"""
    m00, m01, m02 = rows[0]
    m10, m11, m12 = rows[1]
    m20, m21, m22 = rows[2]
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    return (w, x, y, z)
