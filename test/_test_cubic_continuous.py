"""三维粘滞撤销/重做：一键连续播放（原版为二维 commit 后事件驱动推进）。

复现路径（用户实测）：
  1. 虚拟键盘「粘滞」保持开；
  2. 点【撤销】或【重做】；
  3. 应每步播完动画后自动接下一步，直到边界，而不是只走一步。

三维撤销/重做只挂 `cubic_anim` 渲染计时，不进 `animating`/动画队列，
所以原版二维的 `_advance_continuous_undo_redo()` 永远等不到提交回调。
本测试盯的就是这条链路：主循环 `update_animation()` 每帧推进。
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from _cubic_test_util import internal_seam_point  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f"  ok: {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL: {label}" + (f"  <- {extra}" if extra is not None else ''))


def make_gui():
    cfg = tempfile.mkdtemp(prefix='cubic_cont_')
    g = SliderGUI(m=4, n=4, step=1)
    g.config_dir = cfg
    g.config_path = os.path.join(cfg, 'config.json')
    g.temp_history_path = os.path.join(cfg, 'temp_history.json')
    g.tutorial_active = False
    pygame.display.set_mode((g.screen_width, g.screen_height))
    g.screen = pygame.display.get_surface()
    g._cubic_camera_prefs = {}
    return g


def click(g, pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    g.handle_events()
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    g.handle_events()


def click_vk(g, action):
    """直接点虚拟键盘按钮命中盒（走和真实鼠标相同的入口）。"""
    rect = g.vk_rects.get(action)
    if not rect:
        return False
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                            pos=rect.center)
    return g.handle_virtual_keyboard_event(ev)


def select_front(g):
    g._cubic_view(0)
    g.draw_cubic_board()
    pt, seam, face = internal_seam_point(g, families=('r', 'd'))
    check(pt is not None and seam is not None,
          '找到可见的内部墙点（表面右键已禁选）', extra=str(face))
    g._cubic_seam_click(*pt)
    click(g, pt)


def build_history(g, steps=2):
    """推 2 步，得到可连续撤销/重做的三维历史。

    同方向推两步就会贴墙，所以 2 步足够验证“连续”而不是单步；
    每次推完选中组会被清掉（§55 防回滑），每步前重新选同一组。
    """
    n = 0
    for i in range(steps):
        select_front(g)
        if g._cubic_push_letter('C'):
            n += 1
    return n


def wait_step(g, ms=60, pad=0.05):
    """等一步动画播完，再走真实主循环那一句 update_animation()。"""
    time.sleep((ms / 1000.0) + pad)
    g.update_animation()


def main():
    print('=' * 60)
    print('A. 粘滞撤销：点一次，连续撤到第一步')
    g = make_gui()
    g.new_cubic_puzzle(3, 3, 3, 1)
    g.animation_enabled = True
    g.cubic_anim_ms = 60
    pushed = build_history(g, 2)
    check(pushed == 2, f'准备 2 步历史（{pushed}）')
    start_idx = g.game_history.history_index
    check(start_idx == 2, f'历史索引在 2（{start_idx}）')

    g.vk_sticky = False
    g.show_virtual_keyboard = True
    g._vk_build_layout()
    check(click_vk(g, 'sticky'), '点中虚拟键盘【粘滞】按钮')
    check(g.vk_sticky, '粘滞切到开（连续播放）')
    check(click_vk(g, 'undo'), '点中虚拟键盘【撤销】按钮')
    check(g._continuous_undo, '进入连续撤销模式')
    check(g.game_history.history_index == 1,
          f'立刻播放第一步（{g.game_history.history_index}）')
    check(isinstance(getattr(g, 'cubic_anim', None), dict),
          '第一步带有三维滑动动画（不是瞬间跳）')

    # 动画没播完，不应抢跑下一步
    g.update_animation()
    check(g.game_history.history_index == 1,
          f'动画未到期时不推进（{g.game_history.history_index}）')

    wait_step(g)
    check(g.game_history.history_index == 0,
          f'第一步播完后自动接到第二步（{g.game_history.history_index}）')
    wait_step(g)
    check(not g._continuous_undo, '到边界自动停止连续撤销')
    check(g.macro_notify_msg == '已撤销到第一步',
          f'边界提示正确（{g.macro_notify_msg}）')
    check(g.game_history.history_index == 0,
          f'停在第一步（{g.game_history.history_index}）')

    print('B. 粘滞重做：点一次，连续重做到最后一步')
    g._vk_trigger_action('redo')
    check(g._continuous_redo, '进入连续重做模式')
    check(g.game_history.history_index == 1,
          f'立刻播放第一步重做（{g.game_history.history_index}）')
    wait_step(g)
    check(g.game_history.history_index == 2,
          f'重做第二步（{g.game_history.history_index}）')
    wait_step(g)
    check(not g._continuous_redo, '到边界自动停止连续重做')
    check(g.macro_notify_msg == '已重做到最后一步',
          f'边界提示正确（{g.macro_notify_msg}）')
    check(g.game_history.history_index == 2,
          f'停最后一步（{g.game_history.history_index}）')

    print('C. 粘滞关：撤销只走单步，不续播')
    g.vk_sticky = False
    g._vk_trigger_action('undo')
    check(g.game_history.history_index == 1,
          f'单步撤销（{g.game_history.history_index}）')
    check(not g._continuous_undo and not g._continuous_redo,
          '单步模式不打开连续旗标')
    wait_step(g)
    check(g.game_history.history_index == 1,
          f'等一步时长后仍停在 1（{g.game_history.history_index}）')

    print('D. 动画关闭：仍能连续推到底（同原版 no-anim 口径）')
    g2 = make_gui()
    g2.new_cubic_puzzle(3, 3, 3, 1)
    g2.animation_enabled = False
    g2.cubic_anim_ms = 60
    build_history(g2, 2)
    g2.vk_sticky = True
    g2._vk_trigger_action('undo')
    g2.update_animation()
    check(g2.game_history.history_index == 0,
          f'一帧内连续撤到 0（{g2.game_history.history_index}）')
    check(not g2._continuous_undo, '无动画路径到边界后停止')

    print('=' * 60)
    if FAILED:
        print(f'结果：{len(FAILED)} 项失败（{PASSED[0]} 项通过）')
        for f_ in FAILED:
            print('  -', f_)
        return 1
    print(f'结果：全部通过（{PASSED[0]} 项通过，0 项失败）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
