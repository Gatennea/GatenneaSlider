# -*- coding: utf-8 -*-
"""生成开机动画资源（预渲染帧序列 + PyInstaller splash 启动图）。

2026-11-07 换代，换掉最初那套「占位」画面：
- 标题改成**硬边像素字**：小字号 `antialias=False` 渲染 → 最近邻整数倍放大。
  中文、英文都走同一条路，不依赖字体文件、不联网，离线打包版效果一致。
  视觉参照 `video/html_storyboard/index.html` 的 `.pixel` / `.neon` 标题
  （那套用 Press Start 2P + Google Fonts CDN，网页能用，打包版用不上，
  所以这里用系统字体自己造点阵，不读 video/）。
- 背景不再是 `assets/picture/cover.png` 那张机械魔方图标暗化铺满（太单调，
  而且 logo 本来就不该当全屏底图）。改成程序化棋盘：配色直接取游戏调色板
  （背景 30 / 蓝块 60,150,200 / 缝 80 / 描边 100），空位随帧补齐，
  从「打乱」走向「还原」。`video/materials/cover_shuf.png`、
  `video/materials/cover_rest.png` 只是视觉参照，脚本不读 video/，
  clone 仓库后没有它也能重生成。

产物（作者要换动画就改这个脚本再重跑，不要手改某一帧）：
- `assets/picture/boot/frame_000.png … frame_023.png` : 854×480 RGBA，
  运行时由 `GUI.py::_load_boot_frames` 按文件名排序载入，垫 (30,30,30) 底色。
- `assets/picture/splash.bmp` : 640×360 无文字暗底，盖住 exe 自解压段，
  接到应用内标题更顺。

运行：D:/python/python.exe tools/gen_boot_assets.py
依赖：pygame（仅离屏渲染，不需要显示窗口）
"""
import os

import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOT_DIR = os.path.join(ROOT, 'assets', 'picture', 'boot')
SPLASH = os.path.join(ROOT, 'assets', 'picture', 'splash.bmp')

DESIGN_W, DESIGN_H = 854, 480
N_FRAMES = 24
CELL = 58                       # 棋盘格边长（设计像素）

# 与 renderer 的棋盘同一套色，别在这里另造颜色
BG = (30, 30, 30)
BLOCK = (60, 150, 200)
SEAM = (80, 80, 80)
EDGE = (100, 100, 100)
INK = (240, 248, 255)          # 主标题白
SUB = (150, 205, 235)          # 中文副标题浅蓝
DIM = (192, 202, 214)          # 加载提示灰（深底上要看得见）
SHADOW = (16, 62, 96)          # 像素字硬阴影（霓虹描边感）
NEON = (120, 226, 255)


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


def pixel_text_shadow(text, font, color, scale, offset=4):
    """硬阴影叠一层，呼应 storyboard 的 neon 标题；偏移按整像素走。"""
    fg = pixel_text(text, font, color, scale)
    bg = pixel_text(text, font, SHADOW, scale)
    w, h = fg.get_size()
    out = pygame.Surface((w + offset, h + offset), pygame.SRCALPHA)
    out.blit(bg, (offset, offset))
    out.blit(fg, (0, 0))
    return out


def _filled(r, c, t):
    """这一格当前是否有方块：起始约 30% 是空位，t→0.9 时逐个补齐。

    用整数哈希给每格固定的「补齐顺序」，不随机，重跑脚本每帧都一致。
    """
    h = ((r * 73856093) ^ (c * 19349663)) & 0xFFFF
    rank = (h % 100) / 100.0
    return rank >= 0.30 or t >= 0.9 * (rank / 0.30)


def draw_board(surf, t, cell=CELL, dark=115):
    """铺一层暗化棋盘并缓慢平移；t 从 0（打乱）到 1（还原）。"""
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
    zh = (pixel_text_shadow('貓九的滑块游戏', zh_font, SUB, 3, 3)
          if zh_font is not None else None)
    hint_text = '加载中' if hint_font is not None else 'LOADING'
    hint_font = hint_font or font_from(_EN_FONTS, 10)
    return en, zh, hint_font, hint_text


def build_frames():
    os.makedirs(BOOT_DIR, exist_ok=True)
    en, zh, hint_font, hint_text = build_title()
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

        # 标题：从第 0 帧起就完整显示（避免 init 静态帧与动画帧之间跳变），
        # 只做整像素的轻微上下浮动，不缩放（缩放会把像素块插值糊掉）
        bob = 0 if i % 8 < 4 else 1
        en_y = DESIGN_H // 2 - 34 if zh is not None else DESIGN_H // 2 - 10
        surf.blit(en, en.get_rect(center=(DESIGN_W // 2, en_y + bob)))
        if zh is not None:
            surf.blit(zh, zh.get_rect(center=(DESIGN_W // 2, DESIGN_H // 2 + 40 + bob)))

        # 加载中：点号循环，像素小字
        dots = (i // 5) % 4
        hint = pixel_text(hint_text + ('.' * dots), hint_font, DIM, 2)
        surf.blit(hint, hint.get_rect(center=(DESIGN_W // 2, DESIGN_H // 2 + 96)))

        path = os.path.join(BOOT_DIR, 'frame_%03d.png' % i)
        pygame.image.save(surf, path)
        paths.append(path)
    return paths


def build_splash():
    """PyInstaller 启动图：同款棋盘、无文字、整体压暗，接到应用内标题更顺。"""
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
