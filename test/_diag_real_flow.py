# -*- coding: utf-8 -*-
"""真实鼠标事件端到端模拟（碎三角）：点缝 → 点块 → 箭头 → 打乱。

全部走 gui.handle_events() 的真实事件路径，pygame.image.save 落盘真实画面。
回答用户三条投诉：选中缝有没有效果 / 选中块有没有箭头 / 能不能打乱。
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


def shot(gui, name):
    gui.draw_board()
    path = os.path.join(_PROJ, 'test', name)
    pygame.image.save(gui.screen, path)
    print(f"  截图 -> {name}")
    return path


def click(gui, sx, sy):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {'pos': (int(sx), int(sy)), 'button': 1}))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {'pos': (int(sx), int(sy)), 'button': 1}))
    gui.handle_events()


def main():
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 5053})
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.animation_enabled = False
    gui.ui_mode = 'enhanced'
    gui.arrows_enabled = True
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_shatter_puzzle(1)
    gui.center_map()

    g = gui.game
    spec = g.spec
    view = gui._polygon_view()
    origin = gui._poly_view_origin(view)

    # 找一条活缝 + 缝段中点（屏幕坐标）
    pick = None
    for fam in spec.seam_families:
        for line in range(-40, 41):
            if not (g.is_valid_gap(fam.name, line) and g.is_live_gap(fam.name, line)):
                continue
            segs = view.seam_segments(g.board, fam.name, line, origin)
            blk = gui._find_block_on_side(fam.name, line, 0)
            if segs and blk is not None:
                pick = (fam.name, line, segs[0], blk)
                break
        if pick:
            break
    fam_name, line, seg, side_blk = pick
    (ax, ay), (bx, by) = seg
    smx, smy = gui.world_to_screen((ax + bx) / 2.0, (ay + by) / 2.0)
    print(f"活缝 {(fam_name, line)} 缝中点屏幕=({smx:.0f},{smy:.0f})")

    # ① 真实点击缝
    click(gui, smx, smy)
    print(f"  点击后 selected_gap = {gui.selected_gap}")
    shot(gui, 'real_flow_1_seam.png')

    # ② 真实点击该侧的块（_key_center 直接返回屏幕坐标，别再 world_to_screen）
    bsx, bsy = gui._key_center(tuple(side_blk.location))
    click(gui, bsx, bsy)
    n_opt = sum(1 for b in g.blocks if b.be_opted)
    annot = gui._get_gap_direction_annotation()
    print(f"  点块后 selected_block={tuple(side_blk.location)} 选中={n_opt} "
          f"箭头={None if annot is None else len(annot['buttons'])} 个")
    if annot:
        print(f"    箭头位置: {[(d, (round(p[0]), round(p[1])), ok) for d, p, r, ok in annot['buttons']]}")
    shot(gui, 'real_flow_2_block.png')

    # ③ 真滑动一步（「能不能玩」的最终判据），再撤销回来
    letters = gui._gap_dir_letters(fam_name)
    letter = letters[-1]
    moved = gui.move_selected_blocks(letter)
    print(f"  滑动 letter={letter!r} moved={moved} 步数={gui.step_count} "
          f"已还原={g.is_solved()}")
    shot(gui, 'real_flow_4_moved.png')
    gui.game_history.undo(g)
    print(f"  Undo 后 已还原={g.is_solved()}")
    shot(gui, 'real_flow_5_undo.png')

    # ④ 打乱（走菜单同一条 session.shuffle_puzzle）
    before = {tuple(b.location) for b in g.blocks}
    gui.shuffle_puzzle()
    after = {tuple(b.location) for b in g.blocks}
    print(f"  打乱: changed={before != after}  msg={gui.macro_notify_msg!r}")
    shot(gui, 'real_flow_3_shuffled.png')
    print("DONE")


if __name__ == '__main__':
    main()
