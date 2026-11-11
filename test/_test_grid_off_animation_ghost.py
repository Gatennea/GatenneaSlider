# -*- coding: utf-8 -*-
"""关闭「绘制网格」后高速播放动画的网格残影 — 行为护栏（含真刀反向验证）。

用户 2026-11-12 报：设置里关掉绘制网格，高速播放动画时有网格残影，很容易复现。

**根因**（离屏截图对比确认，不是缓存 / 没擦背景）：关网格后缝线改为
「只画相邻滑块相接处」，那一层缝线原本一律取 ``game.positions()``（＝
``b.location``）。动画期间 ``b.location`` 恒为起点（``commit_animation``
才写终态），滑块却按插值位置画，于是整片缝线留在原地、滑块滑走 ——
空白处留下一整框灰线，看着就是上一帧的网格没擦掉。开网格时画的是固定
晶格（本来就不该跟着块走），所以只有关网格这条路径出问题。

修法：缝线与滑块共用同一份「本帧渲染位置」——方形/数字走 ``pos_map``，
三角/米字走 ``_seam_visual_cells()``（按 id 只给正在移动的块加插值偏移）。
相邻判据仍是整数格偏移，所以一起平移的那组缝线跟着走，一片在滑、一片
没动的那一对自然不再成缝。

**判据不查源码字串**，只盯真实 ``draw_*_board`` 里 gap 色的绘制调用坐标：
  A. 关网格 + 整盘平移 1 格（渲染层人造动画态）：动画帧缝线集合与静态帧
     **零交集**（全跟着走了）；旧行为是 100% 重合（缝线原地不动＝残影）。
  B. 开网格：晶格固定，动画帧与静态帧集合相同（行为不变）。
  C. 部分滑动：移动组跟着走、静止组留在原地（防「不分青红皂白整体平移」）。
  D. 真刀反向验证：运行时把修复中和（``_seam_visual_cells`` 退回静态
     positions、``_frame_render_positions`` 退回空）＝撤掉修复，四种盘的
     零交集必须回到 100% 重合。若 A 组的绿是别的机制给的，这里就复现不出
     残影 → 转红。中和只改当前进程实例属性，不碰源文件，无需还原保护。
  E. 静态帧 ``_seam_visual_cells`` 与 ``game.positions()`` 完全相同（画风不变）。

用法：D:/python/python.exe test/_test_grid_off_animation_ghost.py
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from game_mi import mi_key  # noqa: E402
from game_triangle import tri_key  # noqa: E402

_FAILS = []
_OK = [0]

FORMS = (
    ('square', 'draw_board', None),
    ('numbered', 'draw_board', None),
    ('triangle', 'draw_triangle_board', tri_key),
    ('mi', 'draw_mi_board', mi_key),
)


def check(name, cond, detail=''):
    if cond:
        _OK[0] += 1
        print('  ok  : ' + name)
    else:
        _FAILS.append(name)
        print('  FAIL: ' + name + ('  ' + detail if detail else ''))
    return bool(cond)


def make(kind):
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    if kind == 'triangle':
        gui.new_triangle_puzzle(5, 1)
    elif kind == 'mi':
        gui.new_mi_puzzle(4, 4, 1)
    elif kind == 'numbered':
        gui.new_puzzle(4, 4, 1, numbered=True)
    gui.center_map()
    return gui


def arm(g, half=False):
    """架一段渲染层动画：整组沿 c 轴平移 1 格、插值 0.5。

    ⚠️ 这里只造渲染状态，不走 try_move / commit_move（整盘平移在真实对局里
    被显式拒绝）。要验的就是「缝线跟不跟着 pos_map 走」，与走步合法性无关。
    """
    blocks = list(g.game.blocks)
    if half:
        blocks = blocks[:len(blocks) // 2]
    g.animating = True
    g.anim_blocks = blocks
    g.anim_start_pos = [list(b.location) for b in blocks]
    g.anim_end_pos = [list(b.location) for b in blocks]
    g._anim_dr, g._anim_dc = 0.0, 1.0
    g.anim_progress = 0.5


def disarm(g):
    g.animating = False
    g.anim_blocks = []
    g.anim_start_pos = []
    g._anim_dr = g._anim_dc = 0.0
    g.anim_progress = 0.0


def seam_calls(g, draw_name):
    """记录这一帧所有 gap 色缝线的屏幕坐标（rect 左上角 / line 两端点）。"""
    rec = []
    orig_rect, orig_line = pygame.draw.rect, pygame.draw.line

    def wrapped_rect(surf, color, rect, *a, **kw):
        if color == g.colors['gap']:
            rec.append(tuple(int(v) for v in rect))
        return orig_rect(surf, color, rect, *a, **kw)

    def wrapped_line(surf, color, p1, p2, *a, **kw):
        if color == g.colors['gap']:
            rec.append((int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1])))
        return orig_line(surf, color, p1, p2, *a, **kw)

    pygame.draw.rect, pygame.draw.line = wrapped_rect, wrapped_line
    try:
        getattr(g, draw_name)()
    finally:
        pygame.draw.rect, pygame.draw.line = orig_rect, orig_line
    return set(rec)


def neutralise(g):
    """撤掉修复（运行时中和）：缝线退回静态 b.location，滑块渲染位置也退回静态。"""
    g._seam_visual_cells = lambda key_of: frozenset(g.game.positions())
    g._frame_render_positions = lambda: {}


def group_forward():
    print('[A] 关网格：动画中缝线必须整批跟着滑块走（零交集）')
    for kind, name, _key in FORMS:
        g = make(kind)
        g.draw_grid = False
        still = seam_calls(g, name)
        arm(g)
        moving = seam_calls(g, name)
        check('A %s 静态帧确实画了缝线' % kind, len(still) > 0,
              'n=%d' % len(still))
        check('A %s 动画帧缝线全跟着走（与静态帧零交集）' % kind,
              bool(moving) and not (still & moving),
              'still=%d moving=%d overlap=%d'
              % (len(still), len(moving), len(still & moving)))
        check('A %s 缝线数量不因动画而变（整盘平移）' % kind,
              len(moving) == len(still),
              '%d vs %d' % (len(still), len(moving)))

    print('[B] 开网格：固定晶格不跟着块走（行为不变）')
    for kind, name, _key in FORMS:
        g = make(kind)
        g.draw_grid = True
        still = seam_calls(g, name)
        arm(g)
        moving = seam_calls(g, name)
        check('B %s 开网格动画前后缝线集合相同' % kind,
              bool(still) and still == moving,
              'still=%d moving=%d overlap=%d'
              % (len(still), len(moving), len(still & moving)))

    print('[C] 部分滑动：移动组跟着走、静止组留在原地')
    for kind, name, _key in FORMS:
        g = make(kind)
        g.draw_grid = False
        still = seam_calls(g, name)
        arm(g, half=True)
        moving = seam_calls(g, name)
        overlap = len(still & moving)
        check('C %s 一部分缝线跟着走了、一部分没动' % kind,
              moving != still and 0 < overlap < len(still),
              'still=%d moving=%d overlap=%d'
              % (len(still), len(moving), overlap))
        disarm(g)

    print('[E] 静态帧：_seam_visual_cells 与 game.positions() 等价（画风不变）')
    for kind, _name, key in FORMS:
        if key is None:
            continue
        g = make(kind)
        g.draw_grid = False
        check('E %s 静态帧视觉格键 == 逻辑格键' % kind,
              g._seam_visual_cells(key) == frozenset(g.game.positions()))


def group_reverse():
    print('[D] 反向验证：中和修复（等价撤修复）→ 残影必须能再被制造出来')
    for kind, name, _key in FORMS:
        g = make(kind)
        g.draw_grid = False
        still = seam_calls(g, name)
        arm(g)
        neutralise(g)
        ghost = seam_calls(g, name)
        check('D %s 撤掉修复后缝线原地不动（残影重现）' % kind,
              ghost == still and len(ghost) == len(still),
              'still=%d ghost=%d overlap=%d'
              % (len(still), len(ghost), len(still & ghost)))


def main():
    group_forward()
    group_reverse()
    print('\n结果：%s（%d 项通过）' % (
        '全部通过' if not _FAILS else '%d 项失败' % len(_FAILS), _OK[0]))
    if _FAILS:
        for m in _FAILS:
            print('  · 失败：', m)
        sys.exit(1)


if __name__ == '__main__':
    main()
