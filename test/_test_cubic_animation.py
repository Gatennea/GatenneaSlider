"""三维（立方）第 6 步：推一步的滑动（§54）。

口径：**动画只动渲染层**——逻辑位置在推的瞬间就提交好了，动画给刚动过的那组
一个逐渐归零的反向位移，画面上看起来是滑过去。所以：
  A. 推一步后立刻看：逻辑位置已到位（可继续操作），但渲染偏移还在（画面在滑）。
  B. 偏移随时间单调收敛到 0，时长到点后彻底清掉（不多算一帧）。
  C. 偏移只作用在「刚动过的那组」，别处的块不动（不是整盘抖）。
  D. 投影层面：动画中同一块面的屏幕坐标确实在变，且收敛到最终位置。
  E. 关掉动画（animation_enabled=False）时不留尾巴。
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from engine import cubic_view  # noqa: E402

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
    cfg = tempfile.mkdtemp(prefix='cubic_anim_')
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


def select_front(g):
    g._cubic_view(0)
    g.draw_cubic_board()
    f = g._cubic_scene['faces'][-1]
    pt = (int(sum(p[0] for p in f['pts']) / 4.0),
          int(sum(p[1] for p in f['pts']) / 4.0))
    click(g, pt)
    click(g, pt)


def main():
    print('=' * 60)
    print('A. 推一步：逻辑立刻到位，渲染还在滑')
    g = make_gui()
    g.new_cubic_puzzle(3, 3, 3, 1)
    g.cubic_gap = 0.12
    g.animation_enabled = True
    select_front(g)
    check(bool(g.selected_gap), '先选出一组')
    moved = g._cubic_push_letter('C')
    check(moved, '推一步成功')
    anim = getattr(g, 'cubic_anim', None)
    check(isinstance(anim, dict), '推完立刻有动画状态')
    check(len(anim['group']) == 9, f'动画组就是刚动过的 9 块（{len(anim["group"])}）')
    check(anim['delta'] == (1.0, 0.0, 0.0),
          f'方向 C 的世界位移是 +X（{anim["delta"]}）')
    offs = g._cubic_anim_offsets()
    check(offs is not None and all(v != (0.0, 0.0, 0.0) for v in offs.values()),
          '动画刚开始时有非零位移')
    check(set(offs) == set(anim['group']), '位移只落在刚动过的那组上')

    print('B. 偏移随时间收敛并清空')
    import time as _t
    _t.sleep(0.05)
    mid = g._cubic_anim_offsets()
    check(mid is not None and abs(mid[list(mid)[0]][0]) < abs(offs[list(offs)[0]][0]),
          '中途位移比开始时小（在收尾）')
    _t.sleep(0.12)
    end = g._cubic_anim_offsets()
    check(end is None, '时长到了就彻底清掉（不留尾巴）')
    check(g.cubic_anim is None, '动画状态已释放')

    print('C. 绘制用到位移并收敛到最终画面')
    g.draw_cubic_board()
    scene_end = g._cubic_scene['faces']
    face = next(f for f in scene_end if f['loc'] in
                {tuple(int(v) for v in b.location[:3]) for b in g.game.blocks})
    check(len(face['pts']) == 4, '面还是四边形（位移只平移不改形）')
    # 同一姿态下、有位移 vs 无位移：面片坐标确实不同
    blocks = list(g.game.blocks)
    base_faces = cubic_view.collect_faces(blocks, g.cubic_camera,
                                          scale=g._cubic_scene['scale'],
                                          origin=g._cubic_scene['origin'],
                                          gap=g.cubic_gap)
    loc = face['loc']
    moved_faces = cubic_view.collect_faces(
        blocks, g.cubic_camera, scale=g._cubic_scene['scale'],
        origin=g._cubic_scene['origin'], gap=g.cubic_gap,
        offsets={loc: (0.4, 0.0, 0.0)})
    bf = next(f for f in base_faces if f['loc'] == loc)
    mf = next(f for f in moved_faces if f['loc'] == loc)
    d0 = abs(mf['pts'][0][0] - bf['pts'][0][0])
    check(d0 > 1.0, f'给 0.4 格位移，屏幕横坐标真的挪了（{d0:.1f}px）')

    print('D. 动画关掉：不留尾巴')
    g2 = make_gui()
    g2.new_cubic_puzzle(3, 3, 3, 1)
    g2.cubic_gap = 0.12
    g2.animation_enabled = False
    select_front(g2)
    moved = g2._cubic_push_letter('c')
    check(moved and getattr(g2, 'cubic_anim', None) is None,
          '关动画时推一步不留动画状态')
    check(g2._cubic_anim_offsets() is None, '取位移返回 None')

    print('E. 动画中仍可继续推（逻辑不被渲染挡住）')
    g3 = make_gui()
    g3.new_cubic_puzzle(3, 3, 3, 1)
    g3.cubic_gap = 0.12
    g3.animation_enabled = True
    select_front(g3)
    g3._cubic_push_letter('C')
    idx1 = g3.game_history.history_index
    ok2 = g3._cubic_push_letter('C')
    check(ok2 and g3.game_history.history_index == idx1 + 1,
          f'动画没播完也能再推一步（历史 {g3.game_history.history_index}）')
    g3.undo()
    check(g3.game_history.history_index == idx1, '撤销照旧生效')

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
