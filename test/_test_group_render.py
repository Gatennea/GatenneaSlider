# -*- coding: utf-8 -*-
"""捆绑组渲染逻辑测试（离屏 Surface，无需显示器）。

验证 gui.group_render.draw_group_chunks 与 renderer._draw_bandaged_groups_play：
同组滑块确实被画成一整块实心矩形（填色 + 内部缝隙桥接 + 外轮廓），
且非组格不被污染。

关键回归点（对应三条用户反馈）：
  1. 不引入任何新颜色 —— 复用传入的 fill / fill_sel / outline（来自现有
     游戏画风色），测试用显式色验证「没有任何橙色/蓝色等新色」。
  2. 选中组包含捆绑块时，捆绑块应透出选中色 fill_sel（不被覆盖）。
  3. 内部缝隙桥接 → 同组相邻格之间无缝。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

pygame.init()

from gui.group_render import draw_group_chunks, _darker

# 显式色（仅测试用，模拟游戏现有画风：普通块色 / 选中块色 / 边框色）
# 注意：测试里 BORDER 取亮色，使 OUTLINE 与 BG 拉开差距，便于像素断言；
# 真实游戏里 BORDER 是深色，呈现效果由截图人工复核。
FILL = (60, 150, 200)       # 模拟 colors['block']（主题蓝）
FILL_SEL = (220, 120, 60)   # 模拟 colors['block_selected']（橙，选中态）
BORDER = (200, 200, 200)
OUTLINE = _darker(BORDER, 0.55)   # (110,110,110)，明显区别于 BG
OW = 3

BG = (20, 20, 20)
CELL = 40
GAP = 8


def _surf():
    s = pygame.Surface((320, 320))
    s.fill(BG)
    return s


def _rect(r, c):
    return (10 + c * (CELL + GAP), 10 + r * (CELL + GAP), CELL)


def _check(cond, msg):
    print(("  ok: " if cond else "FAIL: ") + msg)
    if not cond:
        _check.failed += 1
_check.failed = 0


def _center(surf, r, c, fx=0.5, fy=0.5):
    x = 10 + c * (CELL + GAP) + int(CELL * fx)
    y = 10 + r * (CELL + GAP) + int(CELL * fy)
    return surf.get_at((x, y))[:3]


print("== A draw_group_chunks：2x2 方块 + 横向条（无新色，纯 fill）==")
surf = _surf()
groups = {1: [(0, 0), (0, 1), (1, 0), (1, 1)],
          2: [(0, 3), (0, 4)]}
draw_group_chunks(surf, groups, _rect, GAP, FILL, FILL_SEL, OUTLINE, OW)
_check(_center(surf, 0, 0) == FILL, "组1填色（左上格中心=fill，无新色）")
_check(_center(surf, 1, 1) == FILL, "组1填色（右下格中心=fill）")
_check(_center(surf, 0, 3) == FILL, "组2填色（横条左格=fill）")
_check(_center(surf, 0, 4) == FILL, "组2填色（横条右格=fill）")
# 内部缝隙桥接：(0,0) 与 (0,1) 之间的缝隙中心应为 fill（无缝）
gap_x = 10 + CELL + GAP // 2
gap_y = 10 + CELL // 2
_check(surf.get_at((gap_x, gap_y))[:3] == FILL, "组1内部横向缝隙被桥接（无缝）")
# 非组格保持背景
_check(_center(surf, 0, 2) == BG, "非组格（(0,2)）保持背景色")
_check(_center(surf, 2, 0) == BG, "非组格（(2,0)）保持背景色")
# 外轮廓：组1右外缘（cell(0,1) 右侧 x=98）画有加粗描边，采样点取描边带中线
edge_x = 10 + 1 * (CELL + GAP) + CELL       # = 98，描边中心线
_check(surf.get_at((edge_x, 25))[:3] == OUTLINE, "组1外轮廓描边出现")
# 回归①：确认没有引入任何「新色」——所有非背景像素要么是 fill 要么是 OUTLINE
def _assert_no_new_color(surf, allowed):
    bad = 0
    for y in range(0, 320, 4):
        for x in range(0, 320, 4):
            px = surf.get_at((x, y))[:3]
            if px == BG:
                continue
            if px not in allowed:
                bad += 1
    return bad
_newcol = _assert_no_new_color(surf, {FILL, OUTLINE})
_check(_newcol == 0, f"回归①：除 fill/outline 外无任何新色（违规像素={_newcol}）")

print("== B 单格组 → 一个正方形块 ==")
surf = _surf()
draw_group_chunks(surf, {5: [(3, 3)]}, _rect, GAP, FILL, FILL_SEL, OUTLINE, OW)
_check(_center(surf, 3, 3) == FILL, "单格组填色（中心=fill）")
_check(_center(surf, 3, 3, 0.15, 0.15) == FILL, "单格内部（避开外描边）填色")
_check(_center(surf, 3, 2) == BG, "相邻非组格保持背景")

print("== B2 选中透出 fill_sel（回归③：选中组含捆绑块时应变选中色）==")
surf = _surf()
draw_group_chunks(surf, {1: [(0, 0), (0, 1)]}, _rect, GAP, FILL, FILL_SEL, OUTLINE, OW,
                  is_selected=lambda r, c: (r, c) == (0, 1))
_check(_center(surf, 0, 0) == FILL, "未选中格用 fill")
_check(_center(surf, 0, 1) == FILL_SEL, "选中格(0,1)透出 fill_sel（不被覆盖）")

print("== C 游玩渲染方法的坐标准换（假对象） ==")
from gui.renderer import RendererMixin


class _FakeBlock:
    def __init__(self, r, c, group=0):
        self.location = [r, c]
        self.group = group
        self.be_opted = False


class _FakeGame:
    def __init__(self, blocks):
        self.blocks = blocks


class _FakeRenderer(RendererMixin):
    def __init__(self):
        self.triangle_mode = False
        self.mi_mode = False
        self.animating = False
        self.anim_blocks = None
        self.drag_following = False
        self.drag_follow_offset = (0, 0)
        self.camera_x = 5
        self.camera_y = 7
        self.cell_size = CELL
        self.gap_width = GAP
        self.zoom = 1
        self.colors = {'block': FILL, 'block_selected': FILL_SEL,
                       'border': BORDER, 'line': (80, 80, 80), 'gap': (50, 50, 50)}
        self.game = _FakeGame([
            _FakeBlock(0, 0, 1), _FakeBlock(0, 1, 1),   # 组1 横条（逻辑坐标）
            _FakeBlock(2, 2, 0),                         # 非组
        ])

    def ease_out(self, t):
        return t


fr = _FakeRenderer()
surf = _surf()
fr.screen = surf
fr._draw_bandaged_groups_play(CELL, GAP)
# 组1 逻辑 (0,0): 屏幕 x = 0*(CELL+GAP)+5 = 5, y=7 → 中心 (25,27) 应=fill
_check(surf.get_at((25, 27))[:3] == FILL, "游玩：组1逻辑(0,0)映射到屏(5,7)填色")
# 组1 逻辑(0,1)：屏幕 x = 5 + 1*(CELL+GAP) = 53，中心 = 73
_check(surf.get_at((73, 27))[:3] == FILL, "游玩：组1逻辑(0,1)同步填色")
_check(surf.get_at((5 + 2 * (CELL + GAP) + 20, 7 + 2 * (CELL + GAP) + 20))[:3]
       == BG, "游玩：非组格(2,2)保持背景")

print("== D 三角/米字跳过（无 group 字段，不报错） ==")
surf = _surf()
fr2 = _FakeRenderer()
fr2.triangle_mode = True
fr2.screen = surf
fr2._draw_bandaged_groups_play(CELL, GAP)
_check(True, "三角模式调用不抛错")

print()
if _check.failed:
    print(f"FAILED: {_check.failed} 项")
    sys.exit(1)
print("ALL PASS")
