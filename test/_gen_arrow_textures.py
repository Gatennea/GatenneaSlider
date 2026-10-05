"""S1-4 箭头按键 —— 透明底贴图素材生成器。

输出 assets/ui/arrows/：
    arrow_{样式}_{方向}.png            可走态（半透明灰）
    arrow_{样式}_{方向}_disabled.png   不可走态（更淡 + 斜杠）
    样式 A/B/C/D × 8 方向，256×256，设计半径 R=96
另出预览（仅浏览用，非素材）：
    experiments/out/arrow_preview_all.png      全样式 × 8 方向总览
    experiments/out/arrow_preview_onboard.png  真实棋盘上按 C 样式叠放的效果

样式定义（全部为「灰色半透明粗线条」，数字格数由代码另画，不烘焙进贴图）：
    A  实心三角头 + 圆头粗杆（标准）
    B  V 形双翼（轻量，无独立箭杆）
    C  A + 淡圆底托（按钮感最强）
    D  敦实版：更粗的杆 + 更大的头（按键感强、远看也清楚）
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

SIZE = 256          # 贴图边长
R = 96              # 设计半径：箭头 tip 距中心 0.95R
ALPHA_ON = 150      # 可走态整体不透明度
ALPHA_OFF = 90      # 不可走态整体不透明度
GREY = (212, 214, 218)

DIRS = {            # 屏幕方向（y 向下）：e 右 / n 上 ...
    'e': (1, 0), 'ne': (0.7071, -0.7071), 'n': (0, -1), 'nw': (-0.7071, -0.7071),
    'w': (-1, 0), 'sw': (-0.7071, 0.7071), 's': (0, 1), 'se': (0.7071, 0.7071),
}

STYLE_SPEC = {
    #            线宽系数   翼展    杆尾     头底     圆托
    'A': dict(w=0.26, wing=0.52, tail=-0.78, base=0.15, pad=False),
    'B': dict(w=0.28, wing=0.56, tail=-0.75, base=0.15, pad=False, v=True),
    'C': dict(w=0.26, wing=0.52, tail=-0.78, base=0.15, pad=True),
    'D': dict(w=0.36, wing=0.62, tail=-0.70, base=0.10, pad=True),
}


def render_tex(style, movable, ux, uy):
    """渲染一张透明底贴图，箭头指向 (ux, uy)。"""
    sp = STYLE_SPEC[style]
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    cx = cy = SIZE / 2.0
    px, py = -uy, ux
    a = ALPHA_ON if movable else ALPHA_OFF
    col = (*GREY, a)
    w = max(3, int(R * sp['w']))
    tip = (cx + ux * R * 0.95, cy + uy * R * 0.95)
    tail = (cx + ux * R * sp['tail'], cy + uy * R * sp['tail'])
    base_c = (cx + ux * R * sp['base'], cy + uy * R * sp['base'])
    wing = R * sp['wing']

    if sp['pad']:
        pygame.draw.circle(surf, (*GREY, int(a * 0.18)), (int(cx), int(cy)), int(R * 0.95))

    if sp.get('v'):
        # 纯 V 双翼：两条粗翼线交于 tip，无中杆（中杆会与翼线挤成一团）
        for sgn in (1, -1):
            end = (tip[0] - ux * R * 0.78 + px * wing * sgn,
                   tip[1] - uy * R * 0.78 + py * wing * sgn)
            pygame.draw.line(surf, col, tip, end, w)
    else:
        pygame.draw.line(surf, col, tail, base_c, w)
        pygame.draw.circle(surf, col, (int(tail[0]), int(tail[1])), w // 2)
        pygame.draw.polygon(surf, col, [
            tip,
            (base_c[0] + px * wing, base_c[1] + py * wing),
            (base_c[0] - px * wing, base_c[1] - py * wing),
        ])

    if not movable:
        # 斜杠：沿箭头的垂直方向穿过中心（与箭杆正交，随方向旋转）
        d = R * 0.80
        sl = (*GREY, min(255, int(a * 2.4)))
        pygame.draw.line(surf, sl,
                         (cx + px * d, cy + py * d),
                         (cx - px * d, cy - py * d), max(3, w))
    return surf


def load_cjk(size):
    for p in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf'):
        if os.path.exists(p):
            return pygame.font.Font(p, size)
    return pygame.font.Font(None, size)


def preview_all():
    cell = 148
    pad_x, pad_y = 190, 84
    W = 8 * cell + pad_x + 20
    H = 4 * cell + pad_y + 46
    surf = pygame.display.set_mode((W, H))
    surf.fill((24, 24, 26))
    f = load_cjk(17)
    flab = load_cjk(15)
    surf.blit(f.render('箭头按键贴图 · 总览（灰色半透明，深底近似游戏棋盘）',
                       True, (235, 235, 235)), (16, 10))
    names = ['右 e', '右上 ne', '上 n', '左上 nw', '左 w', '左下 sw', '下 s', '右下 se']
    for di, dn in enumerate(DIRS):
        surf.blit(flab.render(names[di], True, (185, 185, 185)),
                  (pad_x + di * cell + cell // 2 - 24, 46))
    for si, style in enumerate(STYLE_SPEC):
        desc = {'A': 'A 实心头+粗杆', 'B': 'B V形双翼',
                'C': 'C A+淡圆底托', 'D': 'D 敦实加粗'}[style]
        surf.blit(flab.render(desc, True, (185, 185, 185)),
                  (14, pad_y + si * cell + cell // 2 - 9))
        for di, (name, (ux, uy)) in enumerate(DIRS.items()):
            tex = pygame.transform.smoothscale(
                render_tex(style, True, ux, uy), (cell - 8, cell - 8))
            surf.blit(tex, (pad_x + di * cell + 4, pad_y + si * cell + 4))
    note = load_cjk(13)
    surf.blit(note.render('素材为透明底 PNG（256×256，R=96）；此图深色底仅便于浏览。'
                          '不可走态见 *_disabled.png（更淡 + 正交斜杠）',
                          True, (140, 140, 140)), (14, H - 26))
    return surf


def preview_onboard():
    """真实棋盘 + C 样式贴图，检验尺寸与可读性。"""
    from GUI import SliderGUI
    gui = SliderGUI(m=6, n=6, step=1)
    gui.animation_enabled = False
    gui.ui_mode = 'plain'          # 关掉旧 draw 版标注，改叠贴图
    mid = gui.game.blocks[len(gui.game.blocks) // 2]
    gui.game.opt('h', 2, mid)
    gui.selected_gap = ('h', 2)
    surf = pygame.display.get_surface()
    surf.fill((30, 30, 30))
    gui.draw_board()
    tex = render_tex('C', True, 1, 0)
    tex_dis = render_tex('C', False, 1, 0)
    f = load_cjk(16)
    # 在选中切片外沿右侧叠两个箭头（可走 / 不可走），尺寸按块尺寸近似真实锚定
    chosen = [b for b in gui.game.blocks if b.be_opted]
    step_px = gui.cell_size * gui.zoom + gui.gap_width * gui.zoom
    ys = [gui._key_center(tuple(b.location))[1] for b in chosen]
    xs = [gui._key_center(tuple(b.location))[0] for b in chosen]
    cy = (min(ys) + max(ys)) / 2
    ax = max(xs) + step_px * 0.9
    scaled = pygame.transform.smoothscale(tex, (int(step_px * 1.1),) * 2)
    scaled_dis = pygame.transform.smoothscale(tex_dis, (int(step_px * 1.1),) * 2)
    surf.blit(scaled, scaled.get_rect(center=(int(ax), int(cy))))
    surf.blit(scaled_dis, scaled_dis.get_rect(center=(int(ax), int(cy + step_px * 1.6))))
    surf.blit(f.render('真实棋盘叠放预览（C 样式）：上=可走 下=不可走',
                       True, (220, 220, 220)), (16, 12))
    return surf


def main():
    pygame.init()
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'assets', 'ui', 'arrows')
    os.makedirs(out, exist_ok=True)
    n = 0
    for style in STYLE_SPEC:
        for di, (name, (ux, uy)) in enumerate(DIRS.items()):
            tex = render_tex(style, True, ux, uy)
            pygame.image.save(tex, os.path.join(out, f'arrow_{style}_{name}.png'))
            pygame.image.save(render_tex(style, False, ux, uy),
                              os.path.join(out, f'arrow_{style}_{name}_disabled.png'))
            n += 2
    print('SAVED', n, 'textures ->', out)
    prev = preview_all()
    pygame.image.save(prev, 'experiments/out/arrow_preview_all.png')
    print('SAVED experiments/out/arrow_preview_all.png', prev.get_size())
    try:
        pob = preview_onboard()
        pygame.image.save(pob, 'experiments/out/arrow_preview_onboard.png')
        print('SAVED experiments/out/arrow_preview_onboard.png', pob.get_size())
    except Exception as e:  # 真实棋盘预览失败不影响素材
        print('onboard preview FAILED:', e)


if __name__ == '__main__':
    main()
