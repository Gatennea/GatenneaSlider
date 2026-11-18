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
    # 玩家配置可能把「无限打乱」常开；本文件验的是有限打乱演示的动画，
    # 显式关掉，避免 shuffle_puzzle 走无限游走分支（2026-11-18）。
    g.infinite_shuffle = False
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
    g._cubic_seam_click(*pt)      # 右键选缝
    click(g, pt)                  # 左键选块


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

    print('F. 打乱演示在三维里也有位移（用户 2026-11-18 第 1 条）')
    g4 = make_gui()
    g4.new_cubic_puzzle(3, 3, 3, 1)
    g4.animation_enabled = True
    # 三维打乱演示必须跟 cubic_anim_ms 同源（以前借二维 animation_duration，
    # 右侧「速度」拖了没反应）。这里故意把二维值设成 80、三维设成 60，
    # 断言本次动画用的是三维值。
    g4.animation_duration = 80
    g4.cubic_anim_ms = 60
    g4.shuffle_puzzle(confirm=False)
    check(getattr(g4, '_shuffle_demo_active', False), '打乱进入演示')
    check(getattr(g4, '_anim_duration_override', None) == 60,
          '演示动画用的是 cubic_anim_ms（60），不是二维 80',
          getattr(g4, '_anim_duration_override', None))
    check(g4.animation_duration == 80, '三维演示不改二维 animation_duration')
    # 演示中途拖速度：当前这一步也要立刻变速（重锚 start_time），不是等下一步
    import time as _t_live_sleep
    _t_live_sleep.sleep(0.02)
    g4.draw_right_panel()
    _t_live = g4.anim_start_time
    g4._update_slider_from_mouse(g4.slider_rect.bottom)   # 最慢 400
    check(g4.cubic_anim_ms == 400 and g4._anim_duration_override == 400,
          '演示中拖到最慢：当前步改用 400ms',
          (g4.cubic_anim_ms, g4._anim_duration_override))
    check(g4.anim_start_time != _t_live, '当前步已按进度重锚，不是等下一步')
    g4._update_slider_from_mouse(g4.slider_rect.top)      # 回到最快 60
    check(g4.cubic_anim_ms == 60 and g4._anim_duration_override == 60,
          '再拖回最快：当前步改回 60ms')
    check(getattr(g4, 'animating', False) and bool(getattr(g4, 'anim_blocks', None)),
          '演示靠 start_animation 推进（有自己的块列表）')
    import time as _t2
    _t2.sleep(0.03)
    g4.update_animation()          # 真实循环里每帧都走这一句，进度才会前进
    offs4 = g4._cubic_anim_offsets()
    check(offs4 is not None and any(v != (0.0, 0.0, 0.0) for v in offs4.values()),
          '演示中有非零位移（画面真的在滑，而不是一步一跳）', offs4)
    if offs4:
        first = next(iter(offs4.values()))
        check(max(abs(v) for v in first) < 1.0,
              f'位移还在半路上（{first}），不是已经跳到落点')
    _t2.sleep(0.10)
    g4.update_animation()
    check(getattr(g4, '_shuffle_demo_done', 0) >= 1, '演示确实在往前走')

    print('G. 跟随质心是「滑过去」，不是滑完弹一下（第 3 条）')
    g5 = make_gui()
    g5.new_cubic_puzzle(3, 3, 3, 1)
    g5.animation_enabled = False
    g5.draw_cubic_board()
    for b in g5.game.blocks:
        b.location[0] += 1          # 整盘挪一格：质心世界坐标 +1（只看跟随）
    centers = []
    for _i in range(10):
        g5.draw_cubic_board()
        centers.append(tuple(g5._cubic_follow_center))
    total = abs(centers[-1][2] - centers[0][2]) if centers else 0.0
    firsts = abs(centers[1][2] - centers[0][2]) if len(centers) > 1 else 0.0
    check(total > 0.5, f'参考点确实跟着走（{total:.2f} 格）')
    check(firsts < 0.35 * total, f'首帧只走一小段，不是瞬移（{firsts:.2f}/{total:.2f}）')
    check(all(abs(centers[i + 1][2] - centers[i][2]) <= firsts + 1e-6
              for i in range(len(centers) - 1)), '每帧位移不增（平滑收敛）')

    print('H. 未拆分动画：移动块的内部面不再被剔除（防黑块）')
    cube3 = [(r, c, d) for r in range(3) for c in range(3) for d in range(3)]
    cam3 = cubic_view.CubicCamera.oblique_default()
    base3 = cubic_view.collect_faces(cube3, cam3, scale=30.0,
                                     origin=(200.0, 200.0), gap=0.0)
    anim3 = cubic_view.collect_faces(
        cube3, cam3, scale=30.0, origin=(200.0, 200.0), gap=0.0,
        offsets={(0, 0, 0): (0.3, 0.0, 0.0)})
    keys_base3 = {(f['loc'], f['axis'], f['sign']) for f in base3}
    keys_anim3 = {(f['loc'], f['axis'], f['sign']) for f in anim3}
    check(len(anim3) > len(base3),
          f'有位移时补出内部面（{len(base3)} → {len(anim3)}）')
    check((((0, 0, 0), 0, 1) in keys_anim3)
          and (((0, 0, 0), 0, 1) not in keys_base3),
          '移动块贴死时被剔除的那一面，动画中重新画出来')

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
