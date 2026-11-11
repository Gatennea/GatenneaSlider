# -*- coding: utf-8 -*-
"""重启器可视动画窗口（看门进程本体）。

游戏点击重启 → gui.restart.request_restart() 拉起本进程，以 ``--_restart_watch``
模式启动；main.py 拦截该模式后调用本模块的 ``run()``。

本窗口在「旧进程已退出、新进程未起」的空窗期显示一段可见的「重启中」动画，动画
归重启器所有（与游戏冷启动的开机封面无关）。流程：
1. 动画淡入 + 旋转 spinner + 「重启中…」提示；
2. 轮询旧进程是否退出，退出后重拉起游戏（带 ``--_restarted <token>`` 跳过冷启动
   开机封面）；
3. 等游戏写就绪哨兵（首帧绘出）后，动画淡出并退出，把屏幕交还给新游戏。

可点击 / 任意键 / QUIT 跳过（立即退出，让新游戏窗口直接顶上来）。
"""
import os
import sys
import time
import subprocess

from gui.restart import ready_path, pid_alive


def build_relaunch(relaunch_cmd, token):
    """构造新游戏命令行：在原始 relaunch 后补 --_restarted <token>，
    让新进程跳过冷启动开机封面（那段动画归重启器所有）。纯函数，便于测试。"""
    return list(relaunch_cmd) + ['--_restarted', token]


def _font(size):
    """加载中文字体（优先 simhei.ttf 直读，避免 pygame SysFont 注册表扫描的坑）。"""
    import pygame
    p = 'C:/Windows/Fonts/simhei.ttf'
    if os.path.exists(p):
        try:
            return pygame.font.Font(p, size)
        except Exception:
            pass
    try:
        return pygame.font.SysFont('simhei', size)
    except Exception:
        return pygame.font.Font(None, size)


def _make_cover(w, h):
    """重启动画封面：弱化棋盘底纹 + 标题 + 副标题（与开机封面同源风格）。"""
    import pygame
    surf = pygame.Surface((w, h))
    surf.fill((30, 30, 30))
    grid = max(16, w // 60)
    faint = (255, 255, 255, 18)
    for x in range(0, w, grid):
        pygame.draw.line(surf, faint, (x, 0), (x, h))
    for y in range(0, h, grid):
        pygame.draw.line(surf, faint, (0, y), (w, y))
    try:
        zh = _font(58).render('貓九的滑块游戏', True, (238, 242, 248))
        en = _font(22).render('GATENNEA SLIDER', True, (150, 205, 235))
        surf.blit(zh, zh.get_rect(center=(w // 2, h // 2 - 30)))
        surf.blit(en, en.get_rect(center=(w // 2, h // 2 + 24)))
    except Exception:
        pass
    return surf


def _paint(screen, cover, alpha, now, w, h, font_hint, cy):
    """绘制一帧：封面（按 alpha）+ 旋转 spinner + 动态省略号提示。"""
    import pygame
    screen.fill((30, 30, 30))
    img = pygame.transform.scale(cover, (w, h))
    img.set_alpha(int(255 * alpha))
    screen.blit(img, (0, 0))
    # 旋转 spinner
    r = 16
    cx, cyy = w // 2, cy
    ang = (now / 600.0) % (2 * 3.14159265)
    try:
        pygame.draw.arc(screen, (150, 205, 235),
                        (cx - r, cyy - r, r * 2, r * 2),
                        ang, ang + 3.14159265 * 0.75, 4)
    except Exception:
        pass
    # 「重启中…」带动态省略号
    dots = '.' * (1 + (now // 400) % 3)
    try:
        t = font_hint.render('重启中' + dots, True, (170, 178, 188))
        screen.blit(t, t.get_rect(center=(w // 2, cyy + 36)))
    except Exception:
        pass


def _fade_out(screen, cover, w, h, font_hint, cy):
    """退场淡出。"""
    import pygame
    for i in range(20):
        a = 1.0 - i / 20.0
        _paint(screen, cover, a, pygame.time.get_ticks(), w, h, font_hint, cy)
        pygame.display.flip()
        pygame.time.delay(16)


def _window_size_and_pos():
    """尽量贴合游戏上次窗口尺寸/位置，缺省 960x540 居中。"""
    w, h = 960, 540
    pos = 'center'
    try:
        base = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                else os.path.dirname(os.path.abspath(__file__)))
        cfg = os.path.join(base, 'config', 'config.json')
        if os.path.exists(cfg):
            import json
            with open(cfg, 'r', encoding='utf-8') as f:
                c = json.load(f)
            ws = c.get('window_size')
            if isinstance(ws, list) and len(ws) == 2:
                w = max(640, int(ws[0]))
                h = max(480, int(ws[1]))
            wp = c.get('window_pos')
            if isinstance(wp, list) and len(wp) == 2:
                pos = f'{int(wp[0])},{int(wp[1])}'
    except Exception:
        pass
    return w, h, pos


def run(parent_pid, relaunch_cmd, token):
    """重启器主入口：可见动画窗口覆盖空窗期，旧进程退出后重拉起游戏并等其就绪。

    parent_pid    : 旧游戏进程 pid（等它退出再拉起新的）
    relaunch_cmd  : 新游戏命令行（不含 --_restarted，本函数会补上 token）
    token         : 一次性令牌，用于就绪哨兵文件名
    """
    import pygame

    w, h, pos = _window_size_and_pos()
    os.environ['SDL_VIDEO_WINDOW_POS'] = pos
    pygame.init()
    screen = pygame.display.set_mode((w, h))
    pygame.display.set_caption('貓九的滑块游戏 · 重启中')
    clock = pygame.time.Clock()

    cover = _make_cover(w, h)
    font_hint = _font(20)
    cy = h // 2 + 92

    spawned = False
    child = None
    start = pygame.time.get_ticks()
    FADE_IN = 350
    FADE_OUT = 500
    MAX_WAIT = 9000
    ready = False
    mark_t = 0

    try:
        while True:
            now = pygame.time.get_ticks()
            elapsed = now - start

            # 跳过：点击 / 任意键 / QUIT
            skip = False
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    skip = True
                elif ev.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    skip = True
            if skip:
                break

            if not spawned:
                # 旧进程退出后再拉起新游戏，避免两进程并发读写存档/配置
                if not pid_alive(parent_pid):
                    cmd = build_relaunch(relaunch_cmd, token)
                    try:
                        child = subprocess.Popen(cmd, cwd=os.getcwd(),
                                                 env=dict(os.environ),
                                                 creationflags=0x00000010)
                    except Exception:
                        child = None
                    spawned = True
                    mark_t = now
            else:
                if not ready and os.path.exists(ready_path(token)):
                    ready = True
                    mark_t = now

            alpha = min(1.0, elapsed / FADE_IN)
            _paint(screen, cover, alpha, now, w, h, font_hint, cy)
            pygame.display.flip()

            # 游戏就绪后淡出一小段；或总超时保护后退出
            if ready and (now - mark_t) > FADE_OUT:
                break
            if elapsed > MAX_WAIT:
                break
            clock.tick(60)
    finally:
        _fade_out(screen, cover, w, h, font_hint, cy)
        try:
            from gui.restart import clear_ready
            clear_ready(token)
        except Exception:
            pass
        pygame.quit()
    # 新游戏是独立进程（NEW_CONSOLE），本进程退出不会牵连它
    return 0
