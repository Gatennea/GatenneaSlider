# -*- coding: utf-8 -*-
"""回归：求解运行期（_auto_solve_running）应能移动相机视角（拖拽平移）。

历史 bug：events.py 的 `if self._auto_solve_running:` 守卫把游戏区的
MOUSEBUTTONDOWN 用 continue 直接吞掉（只放行菜单 / 右侧面板），导致
`is_dragging` 永远无法置位——相机拖拽平移在求解过程中失效（滚轮缩放在
守卫之外、仍可用，但拖拽平移不行）。

本测试锁两个不变量：
  A. 求解运行期，游戏区左键按下能起拖相机（is_dragging 变 True）；
  B. 随后的 MOUSEMOTION 真正改变 camera_x / camera_y；松手后 is_dragging 复位。

反向验证：把 events.py 守卫里的 `if event.button == 1: is_dragging=True`
改回原 `continue`（不置 is_dragging），本测试 A 必然 FAIL——护栏能转红。
"""
import os
import queue
import sys

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print('  ok: ' + msg)
    else:
        _fail.append(msg)
        print('  FAIL: ' + msg + ' ' + extra)
    return cond


def make_gui(port):
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': port})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False
    gui.animation_duration = 0.0
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_shatter_puzzle(1)
    gui.center_map()
    return gui


def run():
    print('\n== 求解运行期移动相机 ==')
    gui = make_gui(7181)
    gui._auto_solve_running = True  # 模拟求解器运行（含后台计算 + 流式播放）

    cam0 = (gui.camera_x, gui.camera_y)
    print('  初始相机=({:.1f},{:.1f})'.format(cam0[0], cam0[1]))

    # 游戏区中点（避开菜单栏 / 右侧面板 / 任何下拉菜单）
    px, py = 400, 300

    # A. 游戏区左键按下应起拖相机（修复前此处事件被 continue 吞掉）
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(px, py)))
    gui.handle_events()
    check(gui.is_dragging, '求解期游戏区左键按下起拖相机 (is_dragging=True)',
          'is_dragging=%r' % getattr(gui, 'is_dragging', None))
    check(gui.drag_offset == cam0,
          '起拖时记录相机偏移作为拖拽基准',
          'drag_offset=%r cam0=%r' % (getattr(gui, 'drag_offset', None), cam0))

    # B. 拖动应改变相机位置
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=(px + 60, py + 40)))
    gui.handle_events()
    dx = gui.camera_x - cam0[0]
    dy = gui.camera_y - cam0[1]
    check(abs(dx - 60) < 1.0 and abs(dy - 40) < 1.0,
          '求解期拖拽真正平移相机 (Δ=%+.0f,%+.0f)' % (dx, dy),
          'camera=(%r,%r)' % (gui.camera_x, gui.camera_y))

    # 松手复位
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=(px + 60, py + 40)))
    gui.handle_events()
    check(not getattr(gui, 'is_dragging', False),
          '松手后 is_dragging 复位')


if __name__ == '__main__':
    run()
    print('\n通过 %d 项，失败 %d 项' % (_ok[0], len(_fail)))
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')
