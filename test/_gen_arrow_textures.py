"""S1-4 箭头按键 —— 透明底贴图素材生成器（**单图 + 运行时旋转**）。

输出 assets/ui/arrows/：
    arrow_{样式}.png    每样式**一张**、朝右(+x)的基础图，256×256，R=96

运行时不按方向出图，而是：
    pygame.transform.rotate(base, angle_for(ux, uy))
    # angle_for = degrees(atan2(-uy, ux))，屏幕坐标 y 向下

为什么改：原先「每个方向独立画一张」，8 张图各自取整、各自铺BL像素，
pygame 画斜线又不做抗锯齿 —— 结果 45° 的箭头和 0°/90° 形状肉眼不一致
（V 形双翼最明显）。改一张图旋转后，8 个方向形状严格一致。

禁用态**不画箭头**（用户定），故不再生成 *_disabled.png 与斜杠。

样式定义（全部为「灰色半透明粗线条」，数字格数由代码另画，不烘焙进贴图）：
    A  实心三角头 + 圆头粗杆（无框）
    B  V 形双翼 + 正方形框（← 用户选项）
    C  A + 正方形框（对照）
    D  敦实版 + 正方形框（更粗的杆、更大的头）
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
ALPHA_ON = 150      # 线条整体不透明度
GREY = (212, 214, 218)

DIRS = {            # 屏幕方向（y 向下）：e 右 / n 上 ...
    'e': (1, 0), 'ne': (0.7071, -0.7071), 'n': (0, -1), 'nw': (-0.7071, -0.7071),
    'w': (-1, 0), 'sw': (-0.7071, 0.7071), 's': (0, 1), 'se': (0.7071, 0.7071),
}

STYLE_SPEC = {
    #            线宽系数   翼展    杆尾     头底     外框
    'A': dict(w=0.26, wing=0.52, tail=-0.78, base=0.15, frame=None),
    'B': dict(w=0.28, half=0.55, frame='box', v=True),
    'C': dict(w=0.26, wing=0.52, tail=-0.78, base=0.15, frame='box'),
    'D': dict(w=0.36, wing=0.62, tail=-0.70, base=0.10, frame='box'),
}

STYLE_DESC = {
    'A': 'A 实心头+粗杆（无框）',
    'B': 'B V形双翼 + 方框',
    'C': 'C A + 方框（对照）',
    'D': 'D 敦实加粗 + 方框',
}


def frame_rect():
    """方框尺寸（所有样式共用）：边长取偶数，保证关于中心严格对称。"""
    side = int(round(R * 0.95 * 2))
    side += side % 2
    top_left = int(SIZE / 2.0 - side / 2)
    return pygame.Rect(top_left, top_left, side, side)


def render_frame(style=None):
    """只画外框（正方形，轴对齐）。单独一层：运行时可选择不跟着旋转。"""
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    rect = frame_rect()
    br = max(4, int(rect.width * 0.10))
    pygame.draw.rect(surf, (*GREY, int(ALPHA_ON * 0.10)), rect, 0, border_radius=br)
    pygame.draw.rect(surf, (*GREY, int(ALPHA_ON * 0.55)), rect,
                     max(3, int(rect.width * 0.045)), border_radius=br)
    return surf


def render_tex(style, with_frame=True):
    """渲染一张透明底贴图，**箭头恒朝右(+x)**；方向交给运行时旋转。"""
    sp = STYLE_SPEC[style]
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    cx = cy = SIZE / 2.0
    col = (*GREY, ALPHA_ON)
    w = max(3, int(R * sp['w']))

    if with_frame and sp['frame'] == 'box':
        surf.blit(render_frame(), (0, 0))

    # 以下全部沿 +x 绘制：杆水平、头三角底边竖直
    if sp.get('v'):
        # 纯 V 双翼：两条粗翼线交于 tip，无中杆（中杆会与翼线挤成一团）。
        # **包围盒以贴图中心对称**（前后各 half、顶角 90°）：尖端不顶框边，
        # 视觉重心居中，旋转后也稳。旧版 tip 顶到 0.95R 导致整体偏右。
        half = R * sp['half']
        tip = (cx + half, cy)
        for sgn in (1, -1):
            end = (cx - half, cy + half * sgn)
            pygame.draw.line(surf, col, tip, end, w)
    else:
        tip = (cx + R * 0.95, cy)
        base_x = cx + R * sp['base']
        wing = R * sp['wing']
        tail = (cx + R * sp['tail'], cy)
        pygame.draw.line(surf, col, tail, (base_x, cy), w)
        pygame.draw.circle(surf, col, (int(tail[0]), int(tail[1])), w // 2)
        pygame.draw.polygon(surf, col, [tip, (base_x, cy + wing), (base_x, cy - wing)])
    return surf


def sprite(style, ux, uy, size=None, rot_frame=True):
    """运行时取某个方向的贴图：同一张基础图旋转 + 缩放。

    rot_frame=True  框跟着转（45° 方向呈菱形）
    rot_frame=False 框恒正（按键外壳感），只箭头旋转
    """
    if rot_frame or STYLE_SPEC[style]['frame'] is None:
        tex = render_tex(style)
        if size and size != SIZE:
            tex = pygame.transform.smoothscale(tex, (size, size))
        return pygame.transform.rotate(tex, angle_for(ux, uy))
    s = size or SIZE
    out = pygame.Surface((s, s), pygame.SRCALPHA)
    out.blit(pygame.transform.smoothscale(render_frame(), (s, s)), (0, 0))
    head = pygame.transform.smoothscale(render_tex(style, with_frame=False), (s, s))
    head = pygame.transform.rotate(head, angle_for(ux, uy))
    out.blit(head, head.get_rect(center=(s / 2, s / 2)))
    return out


def angle_for(ux, uy):
    """屏幕单位向量 -> pygame.transform.rotate 角度。

    rotate 正角度在屏幕上是逆时针；(1,0) 经 rotate(90) 变 (0,-1)（朝上 n），
    故 θ 满足 cosθ=ux, -sinθ=uy。
    """
    return math.degrees(math.atan2(-uy, ux))


def overlay(base, angle, size=None, rot_frame=True):
    """某个方向的预览图（预览与游戏使用同一条路径）。"""
    return sprite(base, *DIRS[angle], size, rot_frame=rot_frame)


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
    surf.blit(f.render('箭头按键贴图 · 总览（同一张基础图旋转，深底便于浏览）',
                       True, (235, 235, 235)), (16, 10))
    surf.blit(load_cjk(13).render(
        '每格 = 基础图 256px 缩放显示；8 个方向由同一张 PNG 旋转得到，形状严格一致',
        True, (140, 140, 140)), (300, 14))
    names = ['右 e', '右上 ne', '上 n', '左上 nw', '左 w', '左下 sw', '下 s', '右下 se']
    for di, dn in enumerate(names):
        surf.blit(flab.render(dn, True, (185, 185, 185)),
                  (pad_x + di * cell + cell // 2 - 24, 46))
    for si, style in enumerate(STYLE_SPEC):
        surf.blit(flab.render(STYLE_DESC[style], True, (185, 185, 185)),
                  (14, pad_y + si * cell + cell // 2 - 9))
        for di, name in enumerate(DIRS):
            tex = pygame.transform.smoothscale(overlay(style, name),
                                               (cell - 8, cell - 8))
            surf.blit(tex, (pad_x + di * cell + 4, pad_y + si * cell + 4))
    note = load_cjk(13)
    surf.blit(note.render('素材为透明底 PNG（256×256，R=96）；方向由运行时 rotate 得到。'
                          '禁用态按约定不画箭头，故无 *_disabled.png；'
                          '此图「框跟随旋转」，45° 方向呈菱形，另见 arrow_preview_frame.png',
                          True, (140, 140, 140)), (14, H - 26))
    return surf


def preview_frame():
    """方框两种处理方式的对比：跟随旋转（菱形） vs 框恒正（按键外壳）。"""
    cell = 148
    pad_x, pad_y = 150, 84
    W = 8 * cell + pad_x + 20
    H = 2 * cell + pad_y + 60
    surf = pygame.display.set_mode((W, H))
    surf.fill((24, 24, 26))
    surf.blit(load_cjk(17).render('方框处理方式对比（B 样式）', True, (235, 235, 235)), (16, 10))
    names = ['右 e', '右上 ne', '上 n', '左上 nw', '左 w', '左下 sw', '下 s', '右下 se']
    for di, dn in enumerate(names):
        surf.blit(load_cjk(15).render(dn, True, (185, 185, 185)),
                  (pad_x + di * cell + cell // 2 - 24, 46))
    row = ['上排：框跟随旋转 → 45° 方向是菱形（一张图整体转，最省事）',
           '下排：框恒正、只箭头转 → 八个方向都是正方形按键外壳']
    for ri, desc in enumerate(row):
        surf.blit(load_cjk(15).render(desc, True, (185, 185, 185)), (14, pad_y + ri * cell + 6))
        for di, name in enumerate(DIRS):
            tex = pygame.transform.smoothscale(overlay('B', name, rot_frame=(ri == 0)),
                                               (cell - 8, cell - 8))
            surf.blit(tex, (pad_x + di * cell + 4, pad_y + ri * cell + 26))
    return surf


def preview_onboard():
    """真实棋盘 + B 样式贴图，检验尺寸与可读性（禁用态不画）。"""
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
    chosen = [b for b in gui.game.blocks if b.be_opted]
    step_px = gui.cell_size * gui.zoom + gui.gap_width * gui.zoom
    ys = [gui._key_center(tuple(b.location))[1] for b in chosen]
    xs = [gui._key_center(tuple(b.location))[0] for b in chosen]
    cy = (min(ys) + max(ys)) / 2
    ax = max(xs) + step_px * 0.9
    for i, d in enumerate(('e', 'w')):
        scaled = pygame.transform.smoothscale(
            overlay('B', d), (int(step_px * 1.1),) * 2)
        surf.blit(scaled, scaled.get_rect(
            center=(int(ax - i * step_px * 1.5), int(cy))))
    surf.blit(load_cjk(16).render('真实棋盘叠放预览（B 样式）：左端/右端两个按键',
                                  True, (220, 220, 220)), (16, 12))
    return surf


def main():
    pygame.init()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, 'assets', 'ui', 'arrows')
    os.makedirs(out, exist_ok=True)
    # 旧版「每方向一张 + disabled」全部作废
    for fn in os.listdir(out):
        if fn.startswith('arrow_') and fn.endswith('.png'):
            os.remove(os.path.join(out, fn))
    for style in STYLE_SPEC:
        pygame.image.save(render_tex(style), os.path.join(out, f'arrow_{style}.png'))
        if STYLE_SPEC[style]['frame'] == 'box':
            pygame.image.save(render_tex(style, with_frame=False),
                              os.path.join(out, f'arrow_{style}_head.png'))
    n = len(os.listdir(out))
    print('SAVED', n, 'textures ->', out)

    # 一致性自检：①90° 旋转像素精确；②8 方向的内容量（面积/包围盒）应当一致
    base = render_tex('B')
    q = base
    for _ in range(4):
        q = pygame.transform.rotate(q, 90)
    d = pygame.surfarray.array_alpha(q).astype(int) - \
        pygame.surfarray.array_alpha(base).astype(int)
    print('ROTATE-4x90 identical =', bool(abs(d).max() == 0))
    areas, boxes = [], []
    for name, (ux, uy) in DIRS.items():
        s = overlay('B', name)
        a = pygame.surfarray.array_alpha(s)
        areas.append(int((a > 8).sum()))
        ys, xs = (a > 8).nonzero()
        boxes.append((int(xs.max() - xs.min()), int(ys.max() - ys.min())))
    print('AREAS  ', areas, 'spread =', (max(areas) - min(areas)) / max(areas))
    print('BOXES  ', boxes)

    os.makedirs(os.path.join(root, 'experiments', 'out'), exist_ok=True)
    prev = preview_all()
    pygame.image.save(prev, os.path.join(root, 'experiments', 'out',
                                         'arrow_preview_all.png'))
    print('SAVED experiments/out/arrow_preview_all.png', prev.get_size())
    pf = preview_frame()
    pygame.image.save(pf, os.path.join(root, 'experiments', 'out',
                                       'arrow_preview_frame.png'))
    print('SAVED experiments/out/arrow_preview_frame.png', pf.get_size())
    try:
        pob = preview_onboard()
        pygame.image.save(pob, os.path.join(root, 'experiments', 'out',
                                            'arrow_preview_onboard.png'))
        print('SAVED experiments/out/arrow_preview_onboard.png', pob.get_size())
    except Exception as e:  # 真实棋盘预览失败不影响素材
        print('onboard preview FAILED:', e)


if __name__ == '__main__':
    main()
