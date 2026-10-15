# -*- coding: utf-8 -*-
"""增量更新器的 UI 混入：版本检查、左上角更新按钮、下载进度框。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第一步）。
更新机制本身在 gui/updater.py（.cmd + 系统 robocopy 就地替换、保留玩家数据），
本文件只负责「游戏内怎么触发、怎么显示」。

仅安装版（is_frozen）生效；开发版全程只弹一句提示、不联网、不退出，
方便源码调试。轮询节流 24h，见 _auto_update_poll。
"""
import threading
import time

import pygame

from gui import updater as updater_module
from gui.log_writer import _gui_log_error


class UpdateMixin:
    """更新器状态与方法（原 GUI.py 内联代码，整体搬迁）。"""

    def _init_update_state(self):
        """更新器状态属性初始化（由 SliderGUI.__init__ 在原位置调用）。

        仅冻结/安装版生效；开发版全程不激活（各方法入口有 is_frozen 守卫）。
        """
        self.update_available = False          # 是否已发现新版本
        self._update_manifest = None           # 最新版本清单（含 url/sha256）
        self._update_check_in_progress = False # 后台查更新是否进行中
        self._update_in_progress = False       # 后台下载/替换是否进行中
        self._last_update_check_ts = 0.0       # 上次自动轮询时间戳（节流用）
        self.update_progress = 0.0             # 下载进度 0..1
        self.update_status_msg = ''            # 更新状态文案
        self._update_btn_rect = None           # 左上角「更新」按钮矩形（每帧重算）

    # ==================================================================
    # 增量更新器（就地更新，保留玩家数据；仅安装版生效）
    # ==================================================================
    def _start_update_check(self):
        """后台查一次 GitHub 有没有新版本。开发版 / 已在进行 / 已发现则直接返回。"""
        if not updater_module.is_frozen():
            self.macro_notify_msg = '当前为开发模式，更新仅对安装版（exe）生效'
            self.macro_notify_timer = 120
            return
        if self._update_check_in_progress or self.update_available:
            return
        self._update_check_in_progress = True
        def _cb(newer, manifest, err):
            self._update_check_in_progress = False
            if err is not None:
                # 网络 / 解析错误：静默忽略（下次轮询再试），不弹错误打扰玩家
                _gui_log_error('update check failed: {}'.format(err))
                return
            if newer and manifest:
                self.update_available = True
                self._update_manifest = manifest
                self._announce_update_available()
        updater_module.check_for_update(_cb)
        self.macro_notify_msg = '正在检查更新...'
        self.macro_notify_timer = 90

    def _announce_update_available(self):
        """发现新版本：给一条短提示（常驻提示靠左上角「更新」按钮）。"""
        ver = (self._update_manifest or {}).get('version', '')
        self.macro_notify_msg = '发现新版本 {}：点左上角「更新」按钮一键升级'.format(ver)
        self.macro_notify_timer = 300  # 5 秒

    def _auto_update_poll(self):
        """每 24 小时自动轮询一次（节流在内部）。启动时（_last_update_check_ts=0）
        立即查一次，满足「每次打开自动轮询」；之后隔一天再查。"""
        if not updater_module.is_frozen():
            return
        if self._update_check_in_progress or self.update_available:
            return
        now = time.time()
        if now - self._last_update_check_ts < 86400:
            return
        self._last_update_check_ts = now
        self._start_update_check()

    def _update_progress_cb(self, got, total):
        """下载进度回调（在后台线程被调用，主线程读这两个字段绘制进度条）。"""
        if total:
            self.update_progress = got / total
        kb = got // 1024
        self.update_status_msg = ('下载中 {}KB / {}KB'.format(kb, total // 1024)
                                  if total else '下载中 {}KB'.format(kb))

    def _start_update_now(self):
        """立即更新：先确认有可用版本，再起后台线程下载→替换→退出游戏。"""
        if not updater_module.is_frozen():
            self.macro_notify_msg = '当前为开发模式，更新仅对安装版（exe）生效'
            self.macro_notify_timer = 120
            return
        if self._update_in_progress:
            return
        if not self.update_available or not self._update_manifest:
            # 还没查过 / 没发现：先查，查到后玩家再点一次即可
            self._start_update_check()
            self.macro_notify_msg = '先检查一下有没有更新...'
            self.macro_notify_timer = 90
            return
        self._update_in_progress = True
        self.update_progress = 0.0
        self.update_status_msg = '准备下载...'
        def _run():
            try:
                # perform_update 成功会写 .cmd 并 os._exit(0) 杀掉本进程；
                # 失败则抛异常，这里捕获后仅提示，不退出游戏。
                updater_module.perform_update(self._update_manifest,
                                              self._update_progress_cb)
            except Exception as e:  # pragma: no cover - 网络/解压失败路径
                self._update_in_progress = False
                self.update_status_msg = '更新失败：{}'.format(e)
                self.macro_notify_msg = '更新失败：{}'.format(e)
                self.macro_notify_timer = 240
                _gui_log_error('update failed: {}'.format(e), level='error')
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def draw_update_banner(self):
        """发现新版本时在左上角画一个常驻「更新」按钮（点它走 _start_update_now）。"""
        if not self.update_available:
            self._update_btn_rect = None
            return
        ver = (self._update_manifest or {}).get('version', '')
        label = '● 新版本 {} 点此更新'.format(ver) if ver else '● 有新版本 点此更新'
        font = getattr(self, 'status_font', None)
        if font is None:
            self._update_btn_rect = None
            return
        ts = font.render(label, True, (255, 255, 255))
        pad_x, pad_y = 10, 5
        bw = ts.get_width() + pad_x * 2
        bh = ts.get_height() + pad_y * 2
        bx = 10
        by = getattr(self, 'menu_bar_height', 28) + 6
        rect = pygame.Rect(bx, by, bw, bh)
        self._update_btn_rect = rect
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill((60, 140, 60, 235))
        pygame.draw.rect(bg, (120, 220, 120, 235), bg.get_rect(), 1, border_radius=6)
        self.screen.blit(bg, (bx, by))
        self.screen.blit(ts, (bx + pad_x, by + pad_y))

    def draw_update_progress(self):
        """更新下载中画一个居中进度框（模态层之上；下载完游戏会自行退出重启）。"""
        if not self._update_in_progress:
            return
        sw, sh = self.screen_width, self.screen_height
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        bw, bh = 420, 130
        bx, by = (sw - bw) // 2, (sh - bh) // 2
        box = pygame.Rect(bx, by, bw, bh)
        pygame.draw.rect(self.screen, (40, 40, 40), box, border_radius=10)
        pygame.draw.rect(self.screen, (120, 120, 120), box, 1, border_radius=10)
        font = getattr(self, 'status_font', None)
        if font is None:
            return
        title = font.render('正在更新 Gatennea Slider...', True, (255, 255, 255))
        self.screen.blit(title, title.get_rect(centerx=bx + bw // 2, top=by + 16))
        pct = int(self.update_progress * 100)
        status = '{}  ({}%)'.format(self.update_status_msg, pct)
        st_surf = font.render(status, True, (210, 210, 210))
        self.screen.blit(st_surf, st_surf.get_rect(centerx=bx + bw // 2, top=by + 44))
        # 进度条
        bar_x, bar_y, bar_w, bar_h = bx + 30, by + 78, bw - 60, 18
        pygame.draw.rect(self.screen, (70, 70, 70),
                         pygame.Rect(bar_x, bar_y, bar_w, bar_h), border_radius=4)
        fill_w = max(0, min(bar_w, int(bar_w * self.update_progress)))
        pygame.draw.rect(self.screen, (90, 200, 120),
                         pygame.Rect(bar_x, bar_y, fill_w, bar_h), border_radius=4)
        hint = font.render('完成后游戏会自动重启，请勿手动关闭', True, (160, 160, 160))
        self.screen.blit(hint, hint.get_rect(centerx=bx + bw // 2, top=by + 100))
