"""两个「还原态设计」编辑器共用的界面骨架（2026-10-25）。

为什么需要这一层
----------------
创造模式下的「还原态设计」有两个实现，功能近似、都是「在盘面上点格 / 点缝，
把「还原成什么样」摆出来」：

* **格子画布**（``gui/annotation.py`` 的 ``design`` 视图）——在方 / 三角 / 米字
  标准棋盘上点格增删滑块，产出存 ``design_styles`` 样式库；
* **搭积木**（``gui/model_editor.py``）——在三角晶格上自由拼块，产出存
  ``models/<name>.json`` 模型文件。

两者原本各自长了一版外观（一个右下悬浮圆角条，一个整宽通栏；按钮色板、
圆角、hover 规则各写一遍），用户要求「尽量同一套 UI」。这里抽出**只有绘制**
的最小骨架，两边都调它，保证位置 / 尺寸 / 色板 / 圆角一致；命中判定仍留在
各模块自己的 rect 字典里（不在此处掺逻辑，免得测试热区跟着漂）。

约定
----
* 只用 ``gui`` 上已有的 ``screen / colors / status_font / menu_font /
  screen_width / screen_height / status_bar_height / right_panel_width``，
  不 import 任何具体 GUI 类——纯绘制，零状态。
* 颜色全部取自 ``gui.colors``；本模块只固化两个编辑器共用的两种半透明底
  （与既有画布工具条同色，保持一致）。
"""

import pygame

# 工具条底与描边（与 gui/annotation.py 原画布工具条同色，改动会两边一起变）
_BAR_BG = (35, 35, 48, 235)
_BAR_BORDER = (110, 110, 130)
# 左面板底与描边
_PANEL_BG = (28, 28, 38, 220)
_PANEL_BORDER = (100, 100, 120)
# 按钮 hover 提亮量
_HOVER_ADD = 25


def bar_width(gui, max_w=820, left=0):
    """工具条可用宽度：不超过 ``max_w``，且让出右侧面板、左面板与留白。

    ``left`` = 左侧被占用的宽度（搭积木有左面板，要让它；格子画布传 0）。
    """
    avail = gui.screen_width - getattr(gui, 'right_panel_width', 0) - 24 - left
    return max(240, min(max_w, avail))


def bar_rect(gui, h, max_w=820, left=0):
    """右下角悬浮工具条矩形（含状态栏）：两个编辑器用同一条算式。

    ``y`` 与画布工具条完全一致（``status_bar_height`` 上沿再留 8px），
    所以切两个编辑器时工具条不会上下跳。
    """
    w = bar_width(gui, max_w, left)
    x = gui.screen_width - getattr(gui, 'right_panel_width', 0) - w - 10
    y = gui.screen_height - gui.status_bar_height - h - 8
    return pygame.Rect(x, y, w, h)


def shell(gui, rect, title=None, font=None):
    """画工具条底：半透明深色 + 圆角描边 + 条上方的灰色小标题。"""
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(_BAR_BG)
    gui.screen.blit(bg, (rect.x, rect.y))
    pygame.draw.rect(gui.screen, _BAR_BORDER, rect, 1, border_radius=8)
    if title:
        f = font or gui.status_font
        s = f.render(title, True, (200, 200, 210))
        gui.screen.blit(s, (rect.x + 6, rect.y - 18))


def btn(gui, rect, text, color=None, font=None):
    """统一按钮：``color`` 缺省取 ``colors['button_bg']``；hover 提亮 25。"""
    c = color or gui.colors['button_bg']
    if rect.collidepoint(pygame.mouse.get_pos()):
        c = (min(255, c[0] + _HOVER_ADD), min(255, c[1] + _HOVER_ADD),
             min(255, c[2] + _HOVER_ADD))
    pygame.draw.rect(gui.screen, c, rect, border_radius=6)
    f = font or gui.menu_font
    s = f.render(text, True, (255, 255, 255))
    gui.screen.blit(s, s.get_rect(center=rect.center))


def btn_width(text, font, pad=18):
    """按钮应有的宽度（文字宽 + 左右内边距）。"""
    return font.size(text)[0] + pad


def panel_rect(gui, x, y, w, h):
    """左面板矩形（两编辑器共用位置与尺寸口径）。"""
    return pygame.Rect(x, y, w, h)


def panel_bg(gui, rect):
    """画左面板底：半透明深色 + 圆角描边。"""
    s = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    s.fill(_PANEL_BG)
    gui.screen.blit(s, rect.topleft)
    pygame.draw.rect(gui.screen, _PANEL_BORDER, rect, 1, border_radius=6)


def section(gui, x, y, w, title, font, line_color=None):
    """分节标题（小字标题 + 一条细线），返回下一行可用的 ``y``。

    两个编辑器的左面板都按「标题 → 行」的节奏排版，共用这个节奏就不会
    一个密一个疏。
    """
    s = font.render(title, True, (170, 180, 200))
    gui.screen.blit(s, (x, y))
    ly = y + s.get_height() - 2
    pygame.draw.line(gui.screen, line_color or (70, 72, 88),
                     (x, ly), (x + w, ly), 1)
    return ly + 4
