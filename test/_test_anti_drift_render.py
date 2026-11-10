# -*- coding: utf-8 -*-
"""回归：renderer._anti_drift_cam_offset 的相机偏移数学（无显示，直接单测）。

验证：
  A. 演示开启 + macro_executing：第一步原点=当前质心，偏移=0；盘平移后
     偏移恰好抵消质心漂移（质心被锁回起点）。
  B. 关闭 anti_drift_enabled：任何状态都返回 (0,0)。
  C. 非 macro_executing：返回 (0,0) 且清空 origin 缓存。
  D. 反复平移仍锁原点（多步累积偏移 = −当前质心漂移）。
"""
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from gui.renderer import RendererMixin  # noqa: E402


class _Block:
    def __init__(self, r, c):
        self.location = [r, c]


class _Fake:
    """最小替身：只提供 _anti_drift_cam_offset 读取的属性。"""

    def __init__(self, blocks, enabled=True, executing=True):
        self.game = type('G', (), {'blocks': blocks})()
        self.anti_drift_enabled = enabled
        self.macro_executing = executing
        self.macro_selecting_base = False
        self._anti_drift_origin = None

    def _anti_drift_cam_offset(self, step_px):
        return RendererMixin._anti_drift_cam_offset.__get__(self)(step_px)


def _centroid(blocks):
    n = len(blocks)
    return (sum(b.location[1] for b in blocks) / n,
            sum(b.location[0] for b in blocks) / n)


_ok, _fail = [0], []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print('  ok: ' + msg)
    else:
        _fail.append(msg)
        print('  FAIL: ' + msg + ' ' + extra)


def run():
    step_px = 50  # 每格 50px
    # 3×3 实心盘
    blocks = [_Block(r, c) for r in range(3) for c in range(3)]

    # A. 开启 + 演示：第一步原点=质心，偏移=0
    f = _Fake(list(blocks))
    ox, oy = f._anti_drift_cam_offset(step_px)
    c0 = _centroid(blocks)
    check(ox == 0 and oy == 0, '第一步偏移为 0（原点=当前质心）',
          'ox=%s oy=%s' % (ox, oy))
    check(f._anti_drift_origin == c0, 'origin 缓存=初始质心',
          'c0=%s origin=%s' % (c0, f._anti_drift_origin))

    # 模拟盘整体平移 +2 行 +1 列（解法/回放造成的漂移）
    for b in blocks:
        b.location[0] += 2
        b.location[1] += 1
    ox, oy = f._anti_drift_cam_offset(step_px)
    # 期望偏移 = −(质心漂移) * step_px = −(2,1)*50
    check(ox == -1 * step_px and oy == -2 * step_px,
          '盘平移后偏移恰好抵消质心漂移', 'ox=%s oy=%s' % (ox, oy))
    # 质心被锁回起点：屏幕质心 = (质心 + 偏移/step_px) == 原点
    c1 = _centroid(blocks)
    sx = c1[0] + ox / step_px
    sy = c1[1] + oy / step_px
    check(abs(sx - c0[0]) < 1e-9 and abs(sy - c0[1]) < 1e-9,
          '屏幕质心锁回起点', 'screen_centroid=(%s,%s) origin=(%s,%s)'
          % (sx, sy, c0[0], c0[1]))

    # D. 继续平移仍锁原点（再 +1 行）
    for b in blocks:
        b.location[0] += 1
    ox, oy = f._anti_drift_cam_offset(step_px)
    c2 = _centroid(blocks)
    # 注意 ox=列(x)偏移、oy=行(y)偏移：屏幕质心 = 质心 + 偏移/step_px
    check(abs((c2[0] + ox / step_px) - c0[0]) < 1e-9
          and abs((c2[1] + oy / step_px) - c0[1]) < 1e-9,
          '多步累积仍锁原点', 'screen_centroid=(%s,%s)'
          % (c2[0] + ox / step_px, c2[1] + oy / step_px))

    # C. 非演示态：返回 0 且清空 origin
    f2 = _Fake(list(blocks), executing=False)
    ox, oy = f2._anti_drift_cam_offset(step_px)
    check(ox == 0 and oy == 0, '非 macro_executing 返回 0')
    check(f2._anti_drift_origin is None, '非演示态清空 origin 缓存')

    # B. 关闭开关：演示中也返回 0
    f3 = _Fake(list(blocks), enabled=False, executing=True)
    ox, oy = f3._anti_drift_cam_offset(step_px)
    check(ox == 0 and oy == 0, '关闭 anti_drift_enabled 返回 0')
    check(f3._anti_drift_origin is None, '关闭开关不清留 origin')


if __name__ == '__main__':
    run()
    print('\n通过 %d 项，失败 %d 项' % (_ok[0], len(_fail)))
    if _fail:
        for m in _fail:
            print('  ✗', m)
        sys.exit(1)
    print('ALL PASS')
