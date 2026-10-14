"""共享垂直滚动条（像素内容面板用）。

帮助对话框与设置对话框都用它滚动长内容——这是唯一一套像素面板的滚动
交互实现，集中了旋钮几何、拖拽跟手、轨道点击跳转、滚轮与键盘滚动，以及
绘制。统一后两处行为/外观一致，也消除了帮助框原先「拖拽分母写死 20」
导致的滑块不跟手（卡顿）问题。

设计要点：
- 组件自己持有 scroll/content_size/viewport_size，调用方只给几何与尺寸。
- 拖拽保留抓取偏移（grab offset），并用「真实旋钮高度」做比例换算，
  保证旋钮顶端严格跟随鼠标，1:1 不漂移。
- layout() 每帧调用（检索结果/全文切换时内容高度会变），重算旋钮并夹紧。
"""

import pygame


class Scrollbar:
    def __init__(self, track_w=8, knob_min=20):
        self.track_w = track_w
        self.knob_min = knob_min
        self.track_rect = None
        self.knob_rect = None
        self.scroll = 0  # 内容向上偏移的像素量
        self.content_size = 0
        self.viewport_size = 0
        self._dragging = False
        self._grab = 0  # 抓取时鼠标距旋钮顶端的偏移

    # ── 几何 ──────────────────────────────────────────────
    def need_scroll(self):
        """内容是否需要滚动（即是否画出滚动条）。"""
        return self.knob_rect is not None

    def layout(self, track_x, track_y, track_h, content_size, viewport_size):
        """依据当前面板几何与内容尺寸重算轨道/旋钮。每帧调用。"""
        self.content_size = max(0, int(content_size))
        self.viewport_size = max(0, int(viewport_size))
        self.track_rect = pygame.Rect(track_x, track_y, self.track_w, track_h)
        self._recompute_knob()
        self.clamp()

    def _max_scroll(self):
        return max(0, self.content_size - self.viewport_size)

    def clamp(self):
        if self.knob_rect is None:
            self.scroll = 0
            return
        self.scroll = max(0, min(self.scroll, self._max_scroll()))

    def _recompute_knob(self):
        if self.viewport_size <= 0 or self.content_size <= self.viewport_size:
            self.knob_rect = None
            return
        track_h = self.track_rect.height
        knob_h = max(self.knob_min, int(track_h * self.viewport_size / self.content_size))
        ms = self._max_scroll()
        ratio = (self.scroll / ms) if ms else 0
        knob_y = self.track_rect.top + int((track_h - knob_h) * ratio)
        self.knob_rect = pygame.Rect(self.track_rect.x, knob_y, self.track_w, knob_h)

    def set_scroll(self, value):
        self.scroll = int(value)
        self.clamp()
        self._recompute_knob()

    # ── 交互 ──────────────────────────────────────────────
    def on_mouse_down(self, pos):
        """返回 True 表示事件被滚动条消费。"""
        if not self.track_rect:
            return False
        if self.knob_rect and self.knob_rect.collidepoint(pos):
            self._dragging = True
            self._grab = pos[1] - self.knob_rect.top
            return True
        if self.track_rect.collidepoint(pos):
            self._jump_to(pos[1])
            self._dragging = True
            self._grab = pos[1] - self.knob_rect.top if self.knob_rect else 0
            return True
        return False

    def _jump_to(self, my):
        if not self.knob_rect:
            return
        track_h = self.track_rect.height
        knob_h = self.knob_rect.height
        target = max(self.track_rect.top,
                     min(my - knob_h // 2, self.track_rect.top + track_h - knob_h))
        denom = (track_h - knob_h) if (track_h - knob_h) else 1
        ratio = (target - self.track_rect.top) / denom
        self.set_scroll(int(ratio * self._max_scroll()))

    def on_mouse_motion(self, pos):
        if not self._dragging or not self.knob_rect:
            return
        track_h = self.track_rect.height
        knob_h = self.knob_rect.height
        knob_top = pos[1] - self._grab
        knob_top = max(self.track_rect.top,
                       min(knob_top, self.track_rect.top + track_h - knob_h))
        denom = (track_h - knob_h) if (track_h - knob_h) else 1
        ratio = (knob_top - self.track_rect.top) / denom
        self.set_scroll(int(ratio * self._max_scroll()))

    def on_mouse_up(self):
        self._dragging = False

    def on_wheel(self, dy, step=30):
        if not self.knob_rect:
            return
        self.set_scroll(self.scroll - dy * step)

    def on_key(self, key, step=30, page=200):
        """处理 ↑↓ / PageUp/PageDown。返回 True 表示已消费该键。"""
        if not self.knob_rect:
            return False
        if key == pygame.K_UP:
            self.set_scroll(self.scroll - step)
        elif key == pygame.K_DOWN:
            self.set_scroll(self.scroll + step)
        elif key == pygame.K_PAGEUP:
            self.set_scroll(self.scroll - page)
        elif key == pygame.K_PAGEDOWN:
            self.set_scroll(self.scroll + page)
        else:
            return False
        return True

    # ── 绘制 ──────────────────────────────────────────────
    def draw(self, screen, track_color=(60, 60, 65), knob_color=(120, 130, 140),
             hover_color=(150, 160, 170), radius=4):
        if not self.track_rect:
            return
        pygame.draw.rect(screen, track_color, self.track_rect, border_radius=radius)
        if self.knob_rect:
            color = hover_color if self._dragging else knob_color
            pygame.draw.rect(screen, color, self.knob_rect, border_radius=radius)
