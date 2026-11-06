# -*- coding: utf-8 -*-
"""生成开机动画占位资源（预渲染帧序列 + PyInstaller splash 启动图）。

这是「占位」资源：先程序化产一组「动起来的标题卡」把整套机制跑通，
作者之后用任意工具做出的真动画替换 assets/picture/boot/ 下的帧即可（文件名保持
frame_000.png ... frame_NNN.png，按顺序播放）。

- assets/picture/boot/frame_*.png : RGBA 帧序列（封面暗底 + 标题 + 加载中…），
  启动时按时间逐帧 blit；背景透明，运行时垫 (30,30,30) 同游戏背景，
  淡出时只把覆盖层 alpha 归零，无缝接到游戏画面。
- assets/picture/splash.bmp : PyInstaller 启动图（盖住 exe 自解压/Python 启动那段，
  应用内动画够不著的最前段）。无文字，纯品牌暗底，接到应用内标题画面更顺。

运行：python tools/gen_boot_assets.py
依赖：pygame（仅需离屏渲染，不需要显示窗口）。
"""
import os
import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVER = os.path.join(ROOT, 'assets', 'picture', 'cover.png')
BOOT_DIR = os.path.join(ROOT, 'assets', 'picture', 'boot')
SPLASH = os.path.join(ROOT, 'assets', 'picture', 'splash.bmp')

DESIGN_W, DESIGN_H = 854, 480
N_FRAMES = 24
FPS = 25  # 仅用于注释参考；真实播放时长由运行时 timing 决定


def cover_cropped(cover, cw, ch, zoom):
    """封面按 cover 方式缩放并中心裁剪到 (cw,ch)；zoom>1 轻微放大产生缓推。"""
    iw, ih = cover.get_size()
    base = max(cw / iw, ch / ih) * zoom
    w, h = int(iw * base), int(ih * base)
    img = pygame.transform.smoothscale(cover, (w, h))
    x = (w - cw) // 2
    y = (h - ch) // 2
    return img.subsurface((x, y, cw, ch)).copy()


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def build_frames(cover, zh_font, en_font, hint_font):
    os.makedirs(BOOT_DIR, exist_ok=True)
    paths = []
    for i in range(N_FRAMES):
        t = i / (N_FRAMES - 1)
        surf = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)

        # 封面：缓推缩放（1.0 -> 1.06），暗底
        cov = cover_cropped(cover, DESIGN_W, DESIGN_H, 1.0 + 0.06 * t)
        cov.set_alpha(50)
        surf.blit(cov, (0, 0))

        # 暗化蒙层，保证标题可读
        scrim = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        scrim.fill((15, 15, 20, 150))
        surf.blit(scrim, (0, 0))

        # 标题：从第 0 帧起就完整显示（避免 init 静态帧与动画帧之间跳变），
        # 仅做极轻微的呼吸缩放增加生气
        pulse = 1.0 + 0.02 * smoothstep(0.0, 1.0, t) * (1 - 0.5 * t)
        zh = zh_font.render('貓九的滑块游戏', True, (240, 244, 250))
        if pulse != 1.0:
            zw, zh_ = zh.get_size()
            zh = pygame.transform.smoothscale(zh, (int(zw * pulse), int(zh_ * pulse)))
        surf.blit(zh, zh.get_rect(center=(DESIGN_W // 2, DESIGN_H // 2 - 20)))

        en = en_font.render('Gatennea Slider', True, (150, 205, 235))
        surf.blit(en, en.get_rect(center=(DESIGN_W // 2, DESIGN_H // 2 + 36)))

        # 加载中…：点号循环 + 轻微呼吸，提示「正在载入」
        dots = (i // 5) % 4
        hint_txt = '加载中' + ('.' * dots)
        hint_a = int(150 + 80 * abs(__import__('math').sin(t * 3.14159 * 2)))
        hint = hint_font.render(hint_txt, True, (175, 183, 192))
        hint.set_alpha(hint_a)
        surf.blit(hint, hint.get_rect(center=(DESIGN_W // 2, DESIGN_H // 2 + 86)))

        path = os.path.join(BOOT_DIR, 'frame_%03d.png' % i)
        pygame.image.save(surf, path)
        paths.append(path)
    return paths


def build_splash(cover):
    """PyInstaller 启动图：品牌暗底、无文字，接到应用内标题更顺。"""
    cw, ch = 640, 360
    surf = pygame.Surface((cw, ch))
    surf.fill((30, 30, 30))
    cov = cover_cropped(cover, cw, ch, 1.0)
    cov.set_alpha(45)
    surf.blit(cov, (0, 0))
    scrim = pygame.Surface((cw, ch), pygame.SRCALPHA)
    scrim.fill((15, 15, 20, 150))
    surf.blit(scrim, (0, 0))
    pygame.image.save(surf, SPLASH)
    return SPLASH


def main():
    pygame.init()
    # 离屏哑显示：让 convert_alpha / 格式相关操作有参照，无需真正弹窗
    pygame.display.set_mode((1, 1), pygame.NOFRAME)
    cover = pygame.image.load(COVER)
    zh_font = pygame.font.Font('C:/Windows/Fonts/simhei.ttf', 72)
    en_font = pygame.font.Font('C:/Windows/Fonts/simhei.ttf', 26)
    hint_font = pygame.font.Font('C:/Windows/Fonts/simhei.ttf', 18)
    frames = build_frames(cover, zh_font, en_font, hint_font)
    splash = build_splash(cover)
    print('frames: %d -> %s' % (len(frames), BOOT_DIR))
    print('splash: %s' % splash)


if __name__ == '__main__':
    main()
