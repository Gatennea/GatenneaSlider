# -*- coding: utf-8 -*-
"""回归：renderer 防偏移相机偏移（无显示，直接单测）。

验证：
  A. 演示开启 + macro_executing：首帧原点=当前质心，偏移=0；盘平移后偏移
     恰好抵消质心漂移（质心被锁回起点）；多步累积仍锁原点。
  B. 关闭 anti_drift_enabled：任何状态都返回 (0,0)。
  C. 非 macro_executing：返回 (0,0) 且清空 origin 缓存。
  D. 演示重新开始（macro_executing False→True）会重新定锚。
  E. ★动画插值期间偏移逐帧连续、commit 前后无跳变。
     ⚠️ 旧实现按 b.location 离散计算：动画期间 location 恒为起点 → 偏移
     恒 0、commit 一瞬整盘跳一格（用户实测「每步之后强制居中」抖动）。
     本用例让 location 全程保持起点、只让渲染插值前进，旧实现必转红。
  F. _cam_anti_drift_px 在非演示态恒 (0,0)，演示态回传本帧缓存。
  G. draw_board 的接线：相机偏移与滑块循环共用同一份 pos_map（防止以后
     有人把渲染位置改回按 b.location 算，E 组单测抓不到这种集成层回退）。
"""
import os
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)

from gui.renderer import RendererMixin  # noqa: E402


class _Block:
    def __init__(self, r, c):
        self.location = [r, c]
        self.be_opted = False


class _Fake:
    """最小替身：只提供防偏移相关方法读取的属性。"""

    def __init__(self, blocks, enabled=True, executing=True):
        self.game = type('G', (), {'blocks': blocks})()
        self.anti_drift_enabled = enabled
        self.macro_executing = executing
        self.macro_selecting_base = False
        self._anti_drift_origin = None
        self._anti_drift_cam = (0, 0)
        self._anti_drift_active_prev = False
        self.animating = False
        self.anim_blocks = []
        self.anim_start_pos = []
        self.anim_progress = 0.0
        self._anim_dr = 0.0
        self._anim_dc = 0.0
        self.drag_following = False
        self.drag_follow_offset = (0.0, 0.0)

    def ease_out(self, t):
        return t

    def _anti_drift_cam_offset(self, step_px, pos_map=None):
        return RendererMixin._anti_drift_cam_offset.__get__(self)(step_px,
                                                                 pos_map)

    def _frame_render_positions(self):
        return RendererMixin._frame_render_positions.__get__(self)()

    def _cam_anti_drift_px(self):
        return RendererMixin._cam_anti_drift_px.__get__(self)()


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


def _static_cases(step_px):
    # A. 开启 + 演示：首帧原点=质心，偏移=0
    blocks = [_Block(r, c) for r in range(3) for c in range(3)]
    f = _Fake(list(blocks))
    ox, oy = f._anti_drift_cam_offset(step_px)
    c0 = _centroid(blocks)
    check(ox == 0 and oy == 0, 'A1 首帧偏移为 0（原点=当前质心）',
          'ox=%s oy=%s' % (ox, oy))
    check(f._anti_drift_origin == c0, 'A2 origin 缓存=初始质心',
          'c0=%s origin=%s' % (c0, f._anti_drift_origin))

    # 盘整体平移 +2 行 +1 列 → 死区 1 格：只补超出部分（行补 1 格、列在死区内不动）
    for b in blocks:
        b.location[0] += 2
        b.location[1] += 1
    ox, oy = f._anti_drift_cam_offset(step_px)
    check(ox == 0 and oy == -1 * step_px,
          'A3 只补偿超出死区的部分（行 -1 格、列 0）', 'ox=%s oy=%s' % (ox, oy))
    c1 = _centroid(blocks)
    check(abs((c1[0] + ox / step_px) - c0[0]) <= 1.0 + 1e-9
          and abs((c1[1] + oy / step_px) - c0[1]) <= 1.0 + 1e-9,
          'A4 屏幕漂移被限制在死区内（≤1 格）')
    for b in blocks:
        b.location[0] += 1
    ox, oy = f._anti_drift_cam_offset(step_px)
    c2 = _centroid(blocks)
    check(abs((c2[0] + ox / step_px) - c0[0]) <= 1.0 + 1e-9
          and abs((c2[1] + oy / step_px) - c0[1]) <= 1.0 + 1e-9,
          'A5 多步累积仍限制在死区内')

    # C. 非演示态：返回 0 且清空 origin
    f2 = _Fake(list(blocks), executing=False)
    check(f2._anti_drift_cam_offset(step_px) == (0, 0),
          'C1 非 macro_executing 返回 0')
    check(f2._anti_drift_origin is None, 'C2 非演示态清空 origin 缓存')

    # B. 关闭开关：演示中也返回 0
    f3 = _Fake(list(blocks), enabled=False, executing=True)
    check(f3._anti_drift_cam_offset(step_px) == (0, 0),
          'B1 关闭 anti_drift_enabled 返回 0')
    check(f3._anti_drift_origin is None, 'B2 关闭开关不留 origin')

    # D. 演示重新开始会重新定锚（不复用上一轮的旧原点）
    f4 = _Fake(list(blocks))
    f4._anti_drift_cam_offset(step_px)
    f4.macro_executing = False
    f4._anti_drift_cam_offset(step_px)
    f4.macro_executing = True
    check(f4._anti_drift_cam_offset(step_px) == (0, 0),
          'D 演示重新开始重新定锚')


def _animation_case(step_px):
    """★ 抖动护栏：小漂移时相机必须**完全不动**（像打乱一样静止）；
    大漂移只平滑补偿超出死区（1 格）的部分。"""
    # 场景 1：24 块右移 1 列（漂移 24/25 = 0.96 格 ≤ 死区 1）→ 相机全程不动
    blocks = [_Block(r, c) for r in range(5) for c in range(5)]
    f = _Fake(list(blocks))
    check(f._anti_drift_cam_offset(step_px) == (0, 0), 'E1 首帧偏移 0')
    moving = [b for b in blocks if not (b.location[0] == 0
                                       and b.location[1] == 0)]
    f.animating = True
    f.anim_blocks = list(moving)
    f.anim_start_pos = [[b.location[0], b.location[1]] for b in moving]
    f._anim_dr = 0.0
    f._anim_dc = 1.0
    offs = []
    for t in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        f.anim_progress = t
        offs.append(f._anti_drift_cam_offset(step_px))
    check(all(o == (0, 0) for o in offs),
          'E2 小漂移（<死区）相机全程不动（静止大片真静止）', 'offs=%s' % (offs,))

    # 场景 2：24 块右移 2 列（漂移 1.92 格 > 死区）→ 只补超出 1 格的部分
    blocks2 = [_Block(r, c) for r in range(5) for c in range(5)]
    f2 = _Fake(list(blocks2))
    c0b = _centroid(blocks2)
    f2._anti_drift_cam_offset(step_px)   # 定锚
    moving2 = [b for b in blocks2 if not (b.location[0] == 0
                                          and b.location[1] == 0)]
    f2.animating = True
    f2.anim_blocks = list(moving2)
    f2.anim_start_pos = [[b.location[0], b.location[1]] for b in moving2]
    f2._anim_dr = 0.0
    f2._anim_dc = 2.0
    offs2, capped = [], True
    for t in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        f2.anim_progress = t
        pos_map = f2._frame_render_positions()
        sx = sum(pos_map.get(id(b), (b.location[0], b.location[1]))[1]
                 for b in blocks2) / len(blocks2)
        ox, oy = f2._anti_drift_cam_offset(step_px)
        offs2.append((ox, oy))
        if abs((sx + ox / step_px) - c0b[0]) > 1.0 + 0.02:
            capped = False
    check(capped, 'E3 大漂移时可见漂移被限制在死区内', 'offs=%s' % (offs2,))
    check(len(set(offs2)) >= 4, 'E4 补偿逐帧连续而非台阶跳变',
          'distinct=%d' % len(set(offs2)))
    expect = int(round(-(2 * 24.0 / 25 - 1.0) * step_px))
    check(offs2[-1][0] == expect, 'E5 t=1 只补超出死区的部分 = -(1.92-1) 格',
          'got=%s expect=%s' % (offs2[-1][0], expect))

    # commit：偏移与 t=1 一致（无跳变）
    for b in moving2:
        b.location[1] += 2
    f2.animating = False
    after = f2._anti_drift_cam_offset(step_px)
    check(after == offs2[-1], 'E6 commit 前后偏移一致（无跳变）',
          'before=%s after=%s' % (offs2[-1], after))


def _cache_case():
    f = _Fake([_Block(0, 0)], executing=False)
    f._anti_drift_cam = (-12, 7)
    check(f._cam_anti_drift_px() == (0, 0), 'F1 非演示态缓存偏移为 0')
    f.macro_executing = True
    check(f._cam_anti_drift_px() == (-12, 7), 'F2 演示态回传本帧缓存')
    f.macro_selecting_base = True
    check(f._cam_anti_drift_px() == (0, 0), 'F3 选基准阶段不生效')


def _integration_case():
    import inspect
    src = inspect.getsource(RendererMixin.draw_board)
    check('_anti_drift_cam_offset(step_px, pos_map)' in src,
          'G1 draw_board 把本帧 pos_map 传给相机偏移')
    check('pos_map.get(id(block)' in src,
          'G2 滑块循环用同一份 pos_map（与相机同源）')
    check('self._frame_render_positions()' in src,
          'G3 pos_map 由统一的渲染位置映射构建')


def run():
    step_px = 50  # 每格 50px
    _static_cases(step_px)
    _animation_case(step_px)
    _cache_case()
    _integration_case()


if __name__ == '__main__':
    run()
    print('\n通过 %d 项，失败 %d 项' % (_ok[0], len(_fail)))
    if _fail:
        for m in _fail:
            print('  x', m)
        sys.exit(1)
    print('ALL PASS')
