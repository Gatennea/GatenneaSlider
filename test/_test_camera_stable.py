# -*- coding: utf-8 -*-
"""回归：走棋不得让盘面在屏幕上跳（用户 2026-10-24「每次滑動必移動相機」）。

上一版测试只断言 camera_x/camera_y 不变 —— 那是**错的判据**：真正的病根
是 `_poly_view_origin` 按「当前块集合的包围盒」重新锚定世界原点，于是
移动的那一半被原点补偿“原地不动”，没动的那一半整体平移一格。
相机数值从头到尾没变过，所以那种测试必然绿灯。

本测试断言真正该成立的不变量：
  A. 一局之内世界原点恒定（走棋 / 打乱都不变）；
  B. 未移动的块，屏幕坐标在走棋前后完全一致；
  C. 相机数值不变；
  D. 默认口径（建局/读档/打乱）仍能把整盘拉回视口。
"""
import os
import queue
import sys
import time

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
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return cond


def make_gui(port, anim=False):
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': port})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = anim
    gui.animation_duration = 0.06
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_shatter_puzzle(1)
    gui.center_map()
    return gui


def screen_of(gui, view, blk):
    """块质心的屏幕坐标（走真实世界→屏幕链路）。"""
    o = gui._poly_view_origin(view)
    poly = view.world_polygon((blk.location[0], blk.location[1]),
                              blk.location[2], o)
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return gui.world_to_screen(cx, cy)


def try_one_move(gui):
    """暴力找一条能走通的缝＋方向；成功返回被移动的块 id 集合，失败 None。

    被拒的移动不改盘面（先全量校验再提交），故可安全试探。
    """
    g = gui.game
    for fam in g.spec.seam_families:
        letters = gui._gap_dir_letters(fam.name) or ()
        for line in range(-60, 61):
            if not (g.is_valid_gap(fam.name, line)
                    and g.is_live_gap(fam.name, line)):
                continue
            for side in (0, 1):
                blk = gui._find_block_on_side(fam.name, line, side)
                if blk is None:
                    continue
                for letter in letters:
                    g._clear_selection()
                    gui.selected_gap = (fam.name, line)
                    gui.selected_block = blk
                    g.opt(fam.name, line, blk)
                    moved_ids = {id(b) for b in g.blocks if b.be_opted}
                    if not moved_ids:
                        continue
                    if gui.move_selected_blocks(letter):
                        return moved_ids
    return None


def pump(gui):
    """推进动画：必须让时间真的走（update_animation 按 ticks 算进度）。"""
    for _ in range(400):
        gui.update_animation()
        if not getattr(gui, 'animating', False):
            break
        time.sleep(0.004)


def run(anim, label, port):
    print(f'\n== {label} ==')
    gui = make_gui(port, anim)
    g = gui.game
    view = gui._polygon_view()
    origin0 = gui._poly_view_origin(view)
    cam0 = (gui.camera_x, gui.camera_y)

    for step in range(1, 5):
        # 先拍全量屏幕快照；移动后再按“实际移动集合”排除
        before = {id(b): screen_of(gui, view, b) for b in g.blocks}

        moved_ids = try_one_move(gui)
        if moved_ids is None:
            check(False, f'{label} 第{step}步：找不到可行走法')
            break
        if anim:
            pump(gui)
        o = gui._poly_view_origin(view)

        drift = 0.0
        n_unmoved = 0
        for b in g.blocks:
            if id(b) in moved_ids:
                continue
            n_unmoved += 1
            sx, sy = screen_of(gui, view, b)
            bx, by = before[id(b)]
            drift = max(drift, abs(sx - bx) + abs(sy - by))
        check(drift < 0.01,
              f'{label} 第{step}步：未移动的 {n_unmoved} 块屏幕位置不变',
              f'最大漂移={drift:.2f}px')
        check(o == origin0,
              f'{label} 第{step}步：世界原点不变',
              f'{origin0} -> {o}')
        check((gui.camera_x, gui.camera_y) == cam0,
              f'{label} 第{step}步：相机数值不变',
              f'{cam0} -> {(gui.camera_x, gui.camera_y)}')

    # 打乱后原点仍不变（世界坐标系属于板型，不属于局面）
    gui.shuffle_puzzle()
    if anim:
        pump(gui)
    check(gui._poly_view_origin(view) == origin0,
          f'{label} 打乱后世界原点仍不变',
          f'{origin0} -> {gui._poly_view_origin(view)}')


def run_default_path():
    print('\n== 默认口径（建局/读档/打乱）==')
    gui = make_gui(5093)
    # 把相机推到盘面完全看不见，再走默认口径，应能拉回
    gui.camera_x, gui.camera_y = -9000, -9000
    gui.ensure_blocks_visible()
    check(gui._is_camera_valid(), '默认口径能把整盘拉回视口',
          f'camera=({gui.camera_x:.0f},{gui.camera_y:.0f})')

    # 居中：盘面中心应落在游戏区中心
    gui.center_map()
    bb = gui._poly_world_bbox()
    cx = (bb[0] + bb[2]) / 2.0
    cy = (bb[1] + bb[3]) / 2.0
    sx, sy = gui.world_to_screen(cx, cy)
    want_x = (gui.screen_width - gui.right_panel_width) / 2
    check(abs(sx - want_x) < 2.0, '居中后盘面中心在游戏区水平中心',
          f'{sx:.1f} vs {want_x:.1f}')
    check(gui._is_camera_valid(), '居中后整盘在视口内')


if __name__ == '__main__':
    run(False, '无动画走棋', 5090)
    run(True, '有动画走棋', 5091)
    run_default_path()
    print(f'\n通过 {_ok[0]} 项，失败 {len(_fail)} 项')
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')
