# -*- coding: utf-8 -*-
"""回归：碎三角撤销/重做的动画（用户 2026-10-24「撤销没有动画，重做动画完全错误」）。

根因在 **GUI 动画层**，不是几何：
  · ``animation._move_delta`` 对引擎板型退回方形四向表（'d' → (0,1)），
    而碎三角的块坐标是 P 空间（一步是 (12,0) 量级）；
  · 撤销时用错位移找不到块 → `_start_undo_redo_animation` 返回 False →
    静默退化成瞬时撤销（“没有动画”）；
  · 重做时块找得到，但终点算错 → 朝错方向爬一格（“动画完全错误”）。

本测试断言三件事：
  A. 撤销真的起动画（animating=True，_undo_redo_type='undo'），且回到还原态；
  B. 重做真的起动画，且 ``anim_end_pos`` 等于重做前记录的目标位置；
  C. 动画期间**未参与移动的块**视觉位置不动（偏移只作用在 anim_blocks）。
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


def pump(gui, limit=600):
    """推进动画：必须让时间真的走（update_animation 按 ticks 算进度）。"""
    n = 0
    while getattr(gui, 'animating', False) and n < limit:
        gui.update_animation()
        n += 1
        time.sleep(0.004)
    return n


def pick_move(gui):
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
                    if not any(b.be_opted for b in g.blocks):
                        continue
                    if gui.move_selected_blocks(letter):
                        return True
    return False


def main():
    gui = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5110})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = True
    gui.animation_duration = 80  # 毫秒（不是秒）
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_shatter_puzzle(1)
    gui.center_map()
    g = gui.game

    check(pick_move(gui), '先走一步（带动画）')
    check(gui.animating, '移动动画已启动')
    check(gui._pending_move_info.get('delta') is not None,
          'move_info 带上了实际位移 delta',
          f"delta={gui._pending_move_info.get('delta')}")
    frames = pump(gui)
    check(not gui.animating and frames >= 3, f'移动动画正常收尾（{frames} 帧）')
    post = {id(b): tuple(b.location) for b in g.blocks}
    check(not g.is_solved(), '走一步后非还原态')

    # ---- 撤销：必须真的有动画 ----
    gui.undo()
    check(gui.animating is True,
          '撤销**起动画**（旧实现直接瞬时完成）')
    check(getattr(gui, '_undo_redo_type', None) == 'undo',
          '撤销动画类型 = undo', f'type={getattr(gui, "_undo_redo_type", None)}')
    # 动画途中：未参与移动的块视觉位置不动
    in_anim = {id(b) for b in (getattr(gui, 'anim_blocks', None) or ())}
    bad = [b for b in g.blocks
           if id(b) not in in_anim
           and tuple(gui._visual_key(b))!= tuple(b.location)]
    check(not bad, '撤销动画期间未移动的块视觉位置不动',
          f'{len(bad)} 块被整体偏移')
    frames = pump(gui)
    check(not gui.animating and frames >= 3, f'撤销动画正常收尾（{frames} 帧）')
    check(g.is_solved(), '撤销回到还原态')

    # ---- 重做：必须朝正确方向、到正确终点 ----
    gui.redo()
    check(gui.animating is True, '重做起动画')
    check(getattr(gui, '_undo_redo_type', None) == 'redo',
          '重做动画类型 = redo')
    ends = {tuple(p) for p in (getattr(gui, 'anim_end_pos', None) or ())}
    # 撤销可能重建块对象（id 会变），故按“位置集合”比较：动画终点必须
    # 全部落在“走一步后”的盘面位置里，且数量等于参与移动的块数。
    want_set = set(post.values())
    check(bool(ends) and ends <= want_set,
          '重做动画终点 = 该步应到达的位置',
          f'终点 {len(ends)} 个，越界 {sorted(ends - want_set)[:2]}')
    bad = [b for b in g.blocks
           if id(b) not in {id(x) for x in (gui.anim_blocks or ())}
           and tuple(gui._visual_key(b))!= tuple(b.location)]
    check(not bad, '重做动画期间未移动的块视觉位置不动',
          f'{len(bad)} 块被整体偏移')
    frames = pump(gui)
    check(not gui.animating and frames >= 3, f'重做动画正常收尾（{frames} 帧）')
    now = sorted(tuple(b.location) for b in g.blocks)
    want_state = sorted(post.values())
    check(now == want_state, '重做后回到走一步后的状态',
          f'差集 {sorted(set(now) ^ set(want_state))[:2]}')

    print(f'\n通过 {_ok[0]} 项，失败 {len(_fail)} 项')
    if _fail:
        for m in _fail:
            print('  ✗', m)
        print('FAILED')
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
