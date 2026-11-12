# -*- coding: utf-8 -*-
"""重启动画生成器（无头、离屏）。

生成一段「打乱 → 还原」的**真引擎**演示帧序列：

- 自己造一个盘面（尺寸来自命令行，由游戏空闲调度器按「上次盘面尺寸」传入），
  与游戏此刻在玩什么**零耦合**——不读存档、不读游戏 record、不碰任何运行态；
- 用 ``game.shuffle(record=...)`` 真打乱（安全打乱保证逆序合法），再按 record
  逆序回放得到「乱 → 齐」；
- 逐帧取真实块坐标 → 离屏绘制棋盘 + 烤入「正在重启」字与图标 → 写出 PNG
  序列 + meta.json；
- 动画做成 **ping-pong 无缝循环**（乱→齐→乱），恰好当「加载进度」用：还原完成
  即加载完成；
- 可带不同 ``--seed``，故**每次重启动画都不重样**（用户创意）。

看门进程（重启播放器）读取这段动画覆盖「旧进程退出 → 新进程就绪」的空窗。

与 tools/gen_boot_assets.py 同哲学、复用其离屏范式与配色（build_logo /
font_from / pixel_text / pixel_text_shadow），保持与游戏调色板一致。
"""
import argparse
import json
import os
import random
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # 离屏渲染

from gen_boot_assets import (  # noqa: E402
    build_logo, font_from, pixel_text, pixel_text_shadow,
    BG, BLOCK, EDGE, DIM, INK, SUB, SHADOW,
)

DESIGN_W, DESIGN_H = 854, 480
FPS = 30
SLIDE = 3                # 每步滑动的子帧数（越多越顺，但帧数/体积增大）
HOLD_SOLVED = 8          # 到达「还原」后停留帧数（ping-pong 在乱态无缝衔接）
LOGO_BOX = 96

CACHE_ROOT = os.path.join(ROOT, 'assets', 'picture', 'restart')
ACTIVE_DIR = 'active'


def build_keyframes(make_game, record):
    """用引擎**正序**重放（opt / try_move / commit_move），与打乱同源，块数恒正确。

    record 的每一步只描述「选中组 + 平移」，同组内可能存在「块未真正平移」的
    重叠位置，纯数据重放容易丢块；直接用引擎逐步重演可保证每帧块数 ==
    初始块数、且终态正是打乱态。

    返回 (order, keyframes)：keyframes[0] = 还原态，keyframes[-1] = 打乱态
    （按 record 正序走完）。动画时反向遍历即得「乱→齐」，再正向回去即无缝
    ping-pong 循环。
    """
    game = make_game()
    def capture():
        return {id(b): (int(b.location[0]), int(b.location[1])) for b in game.blocks}
    keyframes = [capture()]
    for e in record:
        gt, line = e['gap']
        # 用该步「移动前」任一位置定位被选中的块（opt 会选中整组，种子任取）
        target = (int(e['moved'][0][0]), int(e['moved'][0][1]))
        blk = None
        for b in game.blocks:
            if (int(b.location[0]), int(b.location[1])) == target:
                blk = b
                break
        if blk is None:
            continue  # 容错：理论上不会发生
        game.opt(gt, line, blk)
        res = game.try_move(e['direction'], e['step'])
        if res:
            game.commit_move(res)
        for b in game.blocks:
            b.be_opted = False
        keyframes.append(capture())
    return list(game.blocks), keyframes


def _render_transition(order, kf_from, kf_to, progress):
    """两个关键帧之间按进度插值，返回全部块的坐标(float)列表。

    未移动的块两帧坐标相同 → 静止；移动块按刚性平移插值。
    """
    tiles = []
    for b in order:
        r0, c0 = kf_from[id(b)]
        r1, c1 = kf_to[id(b)]
        r = r0 + (r1 - r0) * progress
        c = c0 + (c1 - c0) * progress
        tiles.append((float(r), float(c)))
    return tiles


def _board_geometry(union_min_r, union_max_r, union_min_c, union_max_c):
    """按**整体并集**（还原态 ∪ 打乱态所有帧）尺寸计算固定格子边长，使内容
    恰好适配「标题/提示之间的安全带」，既不裁切也不压字。格子取安全带可用
    比例的较小者。
    """
    w_cells = (union_max_c - union_min_c + 1)
    h_cells = (union_max_r - union_min_r + 1)
    safe_w = DESIGN_W * 0.80
    safe_h = DESIGN_H * 0.55
    cell = int(min(safe_w / w_cells, safe_h / h_cells))
    return max(14, cell)


def _draw_board(surf, tiles, cell, cx, cy, ref_r, ref_c):
    """以固定 cell、相机对准并集中心把瓦片画在安全带上。

    还原态与打乱态都落在安全带内（标题/提示互不重叠），方块始终一致大小。
    """
    clip = pygame.Rect(0, int(DESIGN_H * 0.365), DESIGN_W, int(DESIGN_H * 0.55))
    old = surf.get_clip()
    surf.set_clip(clip)
    for (r, c) in tiles:
        x = cx + (c - ref_c) * cell
        y = cy + (r - ref_r) * cell
        rect = pygame.Rect(x + 3, y + 3, cell - 6, cell - 6)
        pygame.draw.rect(surf, BLOCK, rect, border_radius=3)
        pygame.draw.rect(surf, EDGE, rect, 2, border_radius=3)
    surf.set_clip(old)


def _build_title():
    """标题/图标/提示（一次生成，所有帧共用）。中文缺失降级英文，绝不画方框。"""
    en_font = font_from(('consola.ttf', 'cour.ttf'), 11)
    zh_font = font_from(('simhei.ttf', 'msyh.ttc', 'simsun.ttc'), 16,
                        allow_default=False)
    hint_font = font_from(('simhei.ttf', 'msyh.ttc'), 12, allow_default=False)
    en = pixel_text_shadow('GATENNEA SLIDER', en_font, INK, 4, 4)
    zh = (pixel_text_shadow('貓九的滑块游戏', zh_font, SUB, 3, 3, shadow=BG)
          if zh_font is not None else None)
    hint_text = '正在重启' if hint_font is not None else 'RESTARTING'
    hint_font = hint_font or font_from(('consola.ttf',), 10)
    return en, zh, hint_font, hint_text


def _draw_overlay(surf, logo, en, zh, hint_font, hint_text, frame_idx):
    # 上下两条像素 HUD 线（呼应开机封面风格）
    pygame.draw.rect(surf, (60, 150, 200, 120), (0, 0, DESIGN_W, 3))
    pygame.draw.rect(surf, (60, 150, 200, 120), (0, DESIGN_H - 3, DESIGN_W, 3))
    bob = 0 if (frame_idx // 4) % 2 == 0 else 1
    surf.blit(logo, logo.get_rect(center=(DESIGN_W // 2, 42 + bob)))
    en_y = 100
    surf.blit(en, en.get_rect(center=(DESIGN_W // 2, en_y + bob)))
    if zh is not None:
        surf.blit(zh, zh.get_rect(center=(DESIGN_W // 2, en_y + 48 + bob)))
    dots = (frame_idx // 6) % 4
    hint = pixel_text(hint_text + ('.' * dots), hint_font, DIM, 2)
    surf.blit(hint, hint.get_rect(center=(DESIGN_W // 2, DESIGN_H - 40)))


def build_frames(out_dir, m, n, step, kind, triangle_side, seed):
    """生成全部帧到 out_dir，返回 (frame_paths, meta)。"""
    from game import default_shuffle_attempts  # 轻量（不引 solver）
    from puzzle_types import create_puzzle

    # 随机种子：默认随机（每次不同），可指定用于测试复现。
    # game.shuffle 内部用模块级 random 全局状态，故 seed 全局即可复现。
    if seed is None:
        seed = random.randrange(1 << 30)
    random.seed(seed)

    if kind == 'triangle':
        def make_game():
            return create_puzzle(m, n, step, kind='triangle',
                                 triangle_side=triangle_side)
    else:
        def make_game():
            return create_puzzle(m, n, step, kind=kind)

    # 先用一个临时局拿打乱 record（不依赖它的终态）。
    # 动画不需要是真·难局，用更轻的打乱让画面紧凑好看（真实打乱会把块推得
    # 过散，整盘缩小、块像小点）。attempts 取默认公式的约 1/3 并夹在 [16,40]。
    tmp = make_game()
    attempts = default_shuffle_attempts(m, n, kind=kind)
    anim_attempts = max(16, min(40, attempts // 3))
    record = []
    tmp.shuffle(anim_attempts, step, record=record)

    order, keyframes = build_keyframes(make_game, record)
    # keyframes[0]=还原态, keyframes[-1]=打乱态
    # 固定格子边长按整体并集（所有帧）适配安全带；相机对准并集中心
    all_cells = set()
    for kf in keyframes:
        all_cells |= set(kf.values())
    ars = [r for r, _ in all_cells]
    acs = [c for _, c in all_cells]
    cell = _board_geometry(min(ars), max(ars), min(acs), max(acs))
    ref_r = (min(ars) + max(ars)) / 2.0
    ref_c = (min(acs) + max(acs)) / 2.0
    cx, cy = DESIGN_W / 2.0, (DESIGN_H * 0.365 + DESIGN_H * 0.915) / 2.0

    en, zh, hint_font, hint_text = _build_title()
    logo = build_logo(size=LOGO_BOX)

    os.makedirs(out_dir, exist_ok=True)

    K = len(keyframes) - 1  # 过渡步数 = len(record)
    seq = []
    # 动画正向：乱 → 齐（反向遍历 keyframes）
    for t in range(K, 0, -1):
        for s in range(1, SLIDE + 1):
            seq.append(_render_transition(order, keyframes[t],
                                         keyframes[t - 1], s / SLIDE))
    # 在「还原」态停留几帧
    for _ in range(HOLD_SOLVED):
        seq.append(_render_transition(order, keyframes[0], keyframes[0], 1.0))
    # 动画反向：齐 → 乱（回到循环起点，无缝衔接）
    for t in range(0, K):
        for s in range(1, SLIDE + 1):
            seq.append(_render_transition(order, keyframes[t],
                                         keyframes[t + 1], s / SLIDE))
    if not seq:
        # 极端：无成功打乱步，静态还原态循环
        seq = [_render_transition(order, keyframes[0], keyframes[0], 1.0)
               for _ in range(FPS * 2)]

    total = len(seq)
    frames = []
    for idx, tiles in enumerate(seq):
        surf = pygame.Surface((DESIGN_W, DESIGN_H), pygame.SRCALPHA)
        surf.fill(BG)
        _draw_board(surf, tiles, cell, cx, cy, ref_r, ref_c)
        _draw_overlay(surf, logo, en, zh, hint_font, hint_text, idx)
        path = os.path.join(out_dir, 'frame_%04d.png' % idx)
        pygame.image.save(surf, path)
        frames.append(path)

    meta = {
        'design_w': DESIGN_W, 'design_h': DESIGN_H, 'fps': FPS,
        'frame_count': total, 'seed': seed, 'm': m, 'n': n, 'step': step,
        'kind': kind, 'triangle_side': triangle_side,
    }
    with open(os.path.join(out_dir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return frames, meta


def _atomic_commit(tmp_dir, seed):
    """原子提交：删除旧 active → 重命名 tmp 为 active。"""
    active = os.path.join(CACHE_ROOT, ACTIVE_DIR)
    if os.path.exists(active):
        shutil.rmtree(active)
    os.rename(tmp_dir, active)
    return active


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--m', type=int, required=True)
    ap.add_argument('--n', type=int, required=True)
    ap.add_argument('--step', type=int, required=True)
    ap.add_argument('--kind', default='square')
    ap.add_argument('--triangle-side', type=int, default=None)
    ap.add_argument('--seed', type=int, default=None,
                    help='随机种子；不指定则每次不同（动画不重样）')
    ap.add_argument('--out', default=None,
                    help='直接输出到此目录（跳过原子提交，便于测试）')
    args = ap.parse_args()

    pygame.init()
    pygame.display.set_mode((1, 1), pygame.NOFRAME)  # 离屏哑显示

    if args.out:
        out_dir = args.out
    else:
        tmp = os.path.join(CACHE_ROOT,
                          'tmp_%d' % (args.seed if args.seed is not None
                                      else os.getpid()))
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        out_dir = tmp

    t0 = time.perf_counter()
    frames, meta = build_frames(out_dir, args.m, args.n, args.step, args.kind,
                               args.triangle_side, args.seed)
    dt = time.perf_counter() - t0

    if not args.out:
        active = _atomic_commit(out_dir, args.seed)
        print('restart anim: %d frames -> %s (seed=%s, %.2fs)'
              % (len(frames), active, meta.get('seed'), dt))
    else:
        print('restart anim: %d frames -> %s (seed=%s, %.2fs)'
              % (len(frames), out_dir, meta.get('seed'), dt))


if __name__ == '__main__':
    main()
