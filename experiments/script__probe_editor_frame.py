"""无头复现：编辑器会话里点击盘面的完整帧路径（对拍用户 1003x666 窗口）。"""
import os
import sys
import time
import traceback

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402


def one_frame(gui, tag):
    t = {}
    t0 = time.perf_counter()
    gui.handle_events()
    t['events'] = time.perf_counter() - t0
    t0 = time.perf_counter()
    gui.draw_board()
    t['board'] = time.perf_counter() - t0
    t0 = time.perf_counter()
    gui.draw_right_panel()
    gui.draw_status_bar()
    t['chrome'] = time.perf_counter() - t0
    t0 = time.perf_counter()
    gui.draw_annotation_mode()
    t['ann'] = time.perf_counter() - t0
    t0 = time.perf_counter()
    gui._med_draw_overlay()
    t['overlay'] = time.perf_counter() - t0
    t0 = time.perf_counter()
    pygame.display.flip()
    t['flip'] = time.perf_counter() - t0
    tot = sum(t.values())
    print(f'[{tag}] total={tot*1000:7.1f}ms  ' +
          '  '.join(f'{k}={v*1000:.1f}' for k, v in t.items()))
    return tot


def main():
    from GUI import SliderGUI
    gui = SliderGUI()
    print('window =', gui.screen_width, 'x', gui.screen_height)
    one_frame(gui, 'plain')

    gui._med_open()
    print('editor open, placed =', len(gui._med['placed']))
    one_frame(gui, 'editor-idle')

    # 用户式点击：盘面中心（= 初始块所在）与旁边空白，交替点 6 次
    spots = [(500, 340), (560, 340), (620, 300), (500, 400), (440, 380), (560, 400)]
    for i, pos in enumerate(spots):
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {'button': 1, 'pos': pos}))
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEBUTTONUP, {'button': 1, 'pos': pos}))
        try:
            one_frame(gui, f'click{i} {pos}')
        except Exception:
            traceback.print_exc()
            return 1
        med = gui._med
        print(f'   -> placed={len(med["placed"]) if med else "-"} '
              f'groups={len([g for g in (med or {}).get("groups", {}).values() if g])}')
    gui.running = False
    return 0


if __name__ == '__main__':
    sys.exit(main())
