# -*- coding: utf-8 -*-
"""生成开机动画资源（预渲染帧序列 + PyInstaller splash 启动图）。

2026-11-07 换代，换掉最初那套「占位」画面：
- 标题改成**硬边像素字**：小字号 `antialias=False` 渲染 → 最近邻整数倍放大。
  字形**不是手绘点阵字库、也不从 assets 读**：脚本按绝对路径打开**开发机的
  Windows 系统字体**（英文 `consola.ttf`、中文 `simhei.ttf` 等），不联网、
  仓库里也不放字体文件。字体只在**重新生成帧**时用到；产物是 PNG，游戏运行时
  与打包版都只读 PNG，目标机器装了什么字体都不影响画面。
  缺中文字体时中文那行整行降级为英文，绝不画一排方框。
  视觉参照 `video/html_storyboard/index.html` 的 `.pixel` / `.neon` 标题
  （那套用 Press Start 2P + Google Fonts CDN，网页能用，打包版用不上）。
- 背景不再是 `assets/picture/cover.png` 那张机械魔方图标暗化铺满（太单调，
  而且 logo 本来就不该当全屏底图）。改成程序化棋盘：配色取游戏调色板
  （背景 30 / 蓝块 60,150,200 / 缝 80 / 描边 100），空位随帧补齐，
  从「打乱」走向「还原」。
- 但 Logo 本身要留着：从封面线稿**抽出主体**做成独立小图标（去白底、
  平滑缩放、浅色线），放在标题上方，不再铺满全屏。⚠️ 封面是一张精细的
  白底黑线稿，**不要故意做成像素风**：2px 颗粒化 + NEAREST 放大 + 蓝色硬描边
  缩到 148px 只会糊成一团（2026-11-07 试过，效果不行，已去掉）。
  标题和棋盘保持像素风，封面按原样清晰呈现，两者不冲突。
  源码就是 `assets/picture/cover.png`，clone 仓库后就能重生成，不读 video/。
- 所有颜色都取自 `GUI.py::SliderGUI.__init__` 的 `self.colors`；这里不另造色相。
  改游戏主题色时，改完这张表再重跑，开机画面才不会跟游戏里对不上。

产物（作者要换动画就改这个脚本再重跑，不要手改某一帧）：
- `assets/picture/boot/frame_000.png … frame_023.png` : 854×480 RGBA，
  运行时由 `GUI.py::_load_boot_frames` 按文件名排序载入，垫 (30,30,30) 底色。
- `assets/picture/splash.bmp` : 640×360 暗底 + 低调 Logo，盖住 exe 自解压段，
  接到应用内标题更顺。

运行：D:/python/python.exe tools/gen_boot_assets.py
依赖：pygame（离屏渲染）、Pillow + numpy（封面线稿抠图）。
      都只在开发机重生成时用；打包版不含这两个依赖也没关系。
"""
import os

import numpy as np
import pygame
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOT_DIR = os.path.join(ROOT, 'assets', 'picture', 'boot')
SPLASH = os.path.join(ROOT, 'assets', 'picture', 'splash.bmp')
COVER_SRC = os.path.join(ROOT, 'assets', 'picture', 'cover.png')

DESIGN_W, DESIGN_H = 854, 480
N_FRAMES = 24
CELL = 58                       # 棋盘格边长（设计像素）
LOGO_BOX = 148                  # Logo 边长（设计像素）

# ⚠️ 全部照抄 GUI.py 的 self.colors，别在这里另造颜色。
#    左侧注释写明对应的键，改主题色时两边一起改。
BG = (30, 30, 30)              # background
BLOCK = (60, 150, 200)         # block          —— 棋盘方块 / HUD 线
SEAM = (80, 80, 80)            # gap
EDGE = (100, 100, 100)         # border
INK = (255, 255, 255)          # text           —— 英文主标题
SUB = (90, 150, 200)           # button_hover   —— 中文副标题
DIM = (200, 200, 200)          # status_text    —— 加载提示
SHADOW = (50, 80, 160)         # selection_bg   —— 主标题的蓝色硬阴影
NEON = BLOCK                   # block          —— 上下 HUD 像素线
LOGO_LINE = (220, 220, 220)    # menu_text      —— Logo 线稿主体


# ⚠️ 不用 pygame.font.SysFont / match_font：本機 Windows 字體註冊表裡混了 int 值，
#    pygame-ce 的 initsysfonts_win32() 會直接 TypeError，SysFont 退化成自帶的
#    freesansbold（不含中文）→ 中文全渲染成方框。直接按檔案路徑開最穩。
_FONT_DIRS = (
    'C:/Windows/Fonts',
    os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts'),
)
_ZH_FONTS = ('simhei.ttf', 'msyh.ttc', 'simsun.ttc', 'NotoSansCJK-Regular.ttc')
_EN_FONTS = ('consola.ttf', 'cour.ttf', 'DejaVuSansMono.ttf')


def font_from(candidates, size, allow_default=True):
    """按絕對路徑開字體；中文找不到時回傳 None（呼叫端降級成英文，不出方框）。"""
    for d in _FONT_DIRS:
        for name in candidates:
            p = os.path.join(d, name)
            if os.path.exists(p):
                try:
                    return pygame.font.Font(p, size)
                except Exception:
                    continue
    if allow_default:
        return pygame.font.Font(pygame.font.get_default_font(), size)
    return None


def pixel_text(text, font, color, scale):
    """小字号无抗锯齿渲染，再最近邻整数倍放大 → 硬边点阵字。

    `antialias=False` 是关键：得到的 alpha 只有 0 / 255，放大后没有灰边，
    才是 8-bit 点阵字的质感；用 smoothscale 或 antialias=True 都会糊。
    """
    small = font.render(text, False, color).convert_alpha()
    return pygame.transform.scale(
        small, (small.get_width() * scale, small.get_height() * scale))


def pixel_text_shadow(text, font, color, scale, offset=4, shadow=SHADOW):
    """硬阴影叠一层，呼应 storyboard 的 neon 标题；偏移按整像素走。"""
    fg = pixel_text(text, font, color, scale)
    bg = pixel_text(text, font, shadow, scale)
    w, h = fg.get_size()
    out = pygame.Surface((w + offset, h + offset), pygame.SRCALPHA)
    out.blit(bg, (offset, offset))
    out.blit(fg, (0, 0))
    return out


def build_logo(size=LOGO_BOX, line=LOGO_LINE):
    """从封面线稿抠出独立 Logo：白底→透明、黑线→浅色，平滑缩放保留细节。

    cover.png 是白底黑色机械魔方线稿、四周一大圈白边。先按亮度反相算 alpha
    并裁掉白边，居中贴进正方形；再用 LANCZOS 平滑缩放到目标尺寸。
    ⚠️ 封面**不刻意做像素风**：试过 2px 颗粒化（BOX 降采样 + NEAREST 放大）
    再叠一层蓝色硬描边，缩到 148px 后细线糊成一团、认不出是魔方。像素风
    只留给标题字和棋盘；封面按它本来的线稿样子清晰呈现，只做「抠图 + 染色
    + 平滑缩放」，不拿它当全屏底图。
    alpha 保留 2 倍增益：原图线条很细，直接线性反相在 7 倍缩小后会淡到看不见，
    增益只补可见度，不做二值化，边缘仍是平滑灰阶。
    """
    gray = np.asarray(Image.open(COVER_SRC).convert('L'), dtype=np.int16)
    alpha = np.clip((252 - gray) * 2, 0, 255).astype('uint8')
    ys, xs = np.where(alpha > 16)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    crop = Image.fromarray(alpha[y0:y1 + 1, x0:x1 + 1], 'L')
    side = max(crop.size)
    square = Image.new('L', (side, side), 0)
    square.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))

    mask = square.resize((size, size), Image.LANCZOS)
    layer = Image.new('RGBA', (size, size), line + (0,))
    layer.putalpha(mask)
    return pygame.image.frombytes(layer.tobytes(),
                                  layer.size, 'RGBA').convert_alpha()


def _filled(r, c, t):
    """这一格当前是否有方块：起始约 30% 是空位，t→0.9 时逐个补齐。

    用整数哈希给每格固定的「补齐顺序」，不随机，重跑脚本每帧都一致。
    """
    h = ((r * 73856093) ^ (c * 19349663)) & 0xFFFF
    rank = (h % 100) / 100.0
    return rank >= 0.30 or t >= 0.9 * (rank / 0.30)


def draw_board(surf, t, cell=CELL, dark=85):
    """铺一层暗化棋盘并缓慢平移；t 从 0（打乱）到 1（还原）。

    dark 别调回 115 以上：蓝块会亮到把蓝色副标题吃掉，标题可读性靠这一层拉开。
    """
    w, h = surf.get_size()
    board = pygame.Surface((w, h), pygame.SRCALPHA)
    ox = -int(t * cell * 0.6)
    oy = -int(t * cell * 0.3)
    cols, rows = w // cell + 3, h // cell + 3
    for r in range(rows):
        for c in range(cols):
            rect = pygame.Rect(c * cell + ox + 3, r * cell + oy + 3,
                               cell - 6, cell - 6)
            if _filled(r, c, t):
                pygame.draw.rect(board, (*BLOCK, 255), rect, border_radius=3)
                pygame.draw.rect(board, (*EDGE, 255), rect, 2, border_radius=3)
            else:
                pygame.draw.rect(board, (*SEAM, 255), rect, 2, border_radius=3)
    board.set_alpha(dark)
    surf.blit(board, (0, 0))


def build_title():
    """标题只生成一次，24 帧共用（避免每帧重排字）。

    中文字体缺席时整行降级为英文，绝不画一排方框（豆腐块）当像素风。
    """
    en_font = font_from(_EN_FONTS, 11)
    zh_font = font_from(_ZH_FONTS, 16, allow_default=False)
    hint_font = font_from(_ZH_FONTS, 12, allow_default=False)
    en = pixel_text_shadow('GATENNEA SLIDER', en_font, INK, 5, 4)
    zh = (pixel_text_shadow('貓九的滑块游戏', zh_font, SUB, 3, 3, shadow=BG)
          if zh_font is not None else None)
    hint_text = '加载中' if hint_font is not None else 'LOADING'
    hint_font = hint_font or font_from(_EN_FONTS, 10)
    return en, zh, hint_font, hint_text


def build_frames():
    os.makedirs(BOOT_DIR, exist_ok=True)
    en, zh, hint_font, hint_text = build_title()
    logo = build_logo()
    paths = []
    for i in range(N_FRAMES):
        t = i / (N_FRAMES - 1)
        surf = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)

        # 背景：棋盘从打乱走向还原 + 轻微平移
        draw_board(surf, t)
        # 只压一层薄暗色：棋盘要看得见「打乱→还原」，压太狠就又变回一片暗底。
        # 标题靠自己的硬阴影拉开对比，不再叠一条中央暗带（那条横带会把棋盘割裂）。
        shade = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        shade.fill((15, 15, 20, 55))
        surf.blit(shade, (0, 0))

        # 上下两条像素 HUD 线（呼应 storyboard 的角标风格）
        pygame.draw.rect(surf, (*NEON, 120), (0, 0, DESIGN_W, 3))
        pygame.draw.rect(surf, (*NEON, 120), (0, DESIGN_H - 3, DESIGN_W, 3))

        # Logo + 标题：从第 0 帧起就完整显示（避免 init 静态帧与动画帧之间跳变），
        # 只做整像素的轻微上下浮动，不缩放（标题像素字缩放会被插值糊掉）
        bob = 0 if i % 8 < 4 else 1
        surf.blit(logo, logo.get_rect(center=(DESIGN_W // 2, 104 + bob)))
        en_y = DESIGN_H // 2 - 18 if zh is not None else DESIGN_H // 2 + 0
        surf.blit(en, en.get_rect(center=(DESIGN_W // 2, en_y + bob)))
        if zh is not None:
            surf.blit(zh, zh.get_rect(center=(DESIGN_W // 2, DESIGN_H // 2 + 50 + bob)))

        # 加载中：点号循环，像素小字
        dots = (i // 5) % 4
        hint = pixel_text(hint_text + ('.' * dots), hint_font, DIM, 2)
        hint_y = DESIGN_H // 2 + 112 if zh is not None else DESIGN_H // 2 + 70
        surf.blit(hint, hint.get_rect(center=(DESIGN_W // 2, hint_y)))

        path = os.path.join(BOOT_DIR, 'frame_%03d.png' % i)
        pygame.image.save(surf, path)
        paths.append(path)
    return paths


def build_splash():
    """PyInstaller 启动图：同款棋盘 + 压暗 Logo，无文字，接到应用内标题更顺。"""
    cw, ch = 640, 360
    surf = pygame.Surface((cw, ch))
    surf.fill(BG)
    cell = 44
    for r in range(ch // cell + 2):
        for c in range(cw // cell + 2):
            rect = pygame.Rect(c * cell + 3, r * cell + 3, cell - 6, cell - 6)
            filled = _filled(r, c, 0.45)
            base = BLOCK if filled else SEAM
            col = tuple(int(v * 0.32) for v in base)
            pygame.draw.rect(surf, col, rect, 0 if filled else 2, border_radius=3)
    logo = build_logo(size=112)
    logo.set_alpha(110)
    surf.blit(logo, logo.get_rect(center=(cw // 2, ch // 2)))
    pygame.image.save(surf, SPLASH)
    return SPLASH


def main():
    pygame.init()
    # 离屏哑显示：让 convert_alpha / 格式相关操作有参照，无需真正弹窗
    pygame.display.set_mode((1, 1), pygame.NOFRAME)
    frames = build_frames()
    splash = build_splash()
    print('frames: %d -> %s' % (len(frames), BOOT_DIR))
    print('splash: %s' % splash)


if __name__ == '__main__':
    main()
