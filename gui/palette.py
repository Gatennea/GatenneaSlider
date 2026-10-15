# -*- coding: utf-8 -*-
"""命令面板（Ctrl+K）——功能可发现性的主入口。

玩家用口语（「着色」「怎么撤销」「三角 求解」）唤起后直接检索功能清单
（`gui/feature_index`），结果会回答四件事：

    有没有 · 在哪 · 怎么用 · 当前形态/模式下能不能用

回车即「一键到位」（复用 `EventsMixin._activate_feature`，与帮助框检索同一套
动作），因此命令面板与帮助框检索是同一份数据的两个入口：帮助框是「先翻文档、
顺手搜一下」，命令面板是「我就想找这个功能」。

与帮助框的分工（重要，别再长成一个东西）：
    · 帮助框：读操作说明全文为主，检索是附属能力，结果混在文档流里。
    · 命令面板：只做检索与跳转，不承载文档全文，键盘优先（上下选 + 回车）。

层级约定：命令面板是**最上层 UI**——事件分发里最先消费（见 `events.handle_events`
开头的分支），绘制在主循环最后（所有模态之后）。一旦它开着，其余 UI 都不该再
收到键鼠事件，否则会出现「面板浮在最上、点击却穿到下面的棋盘」这类错位。

作者：貓九
"""

import pygame

from gui.text_input import TextInput
from gui.scrollbar import Scrollbar
from gui import feature_index as _fi
from gui import feature_ai as _ai


# 结果列表几何（固定值：高度可预测，滚动条才不会每帧抖动）
_ROW_H = 52          # 单项高度：名称 24 + 说明 18 + 间距 10
_ROW_GAP = 4
_MAX_ROWS = 7        # 一屏最多显示几条
_INPUT_H = 40
_FOOT_H = 28


class PaletteMixin:
    """命令面板的状态、绘制与事件处理。

    作为 Mixin 混入 `SliderGUI`：本文件只碰 `self` 上的面板相关字段，不依赖
    棋盘/菜单等具体业务，便于单独测试。
    """

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def _pal_init_state(self):
        """面板状态初值。与虚拟键盘/指标面板等同样在 GUI.__init__ 里调用一次。"""
        self.palette_active = False
        self.palette_input = TextInput('')
        self.palette_input.active = True
        self.palette_sel = 0            # 选中项索引（键盘上下键操作）
        self.palette_results = []       # [(entry, available)]，与结果行一一对应
        self.palette_result_rects = []  # [(rect, entry)]，鼠标点击命中用
        self.palette_scrollbar = Scrollbar()
        self.palette_rect = pygame.Rect(0, 0, 0, 0)
        self.palette_input_rect = pygame.Rect(0, 0, 0, 0)
        self.palette_hover = -1         # 鼠标悬停项索引，-1 = 无

    # ------------------------------------------------------------------
    # 打开 / 关闭 / 检索
    # ------------------------------------------------------------------
    def open_command_palette(self):
        """打开面板：清空上一轮查询与选择，避免上次的残留串味。"""
        self.close_all_menus()
        self.palette_active = True
        self.palette_input.set_text('')
        self.palette_input.active = True
        self.palette_sel = 0
        self.palette_hover = -1
        self.palette_scrollbar.set_scroll(0)
        self._pal_run_search()

    def close_command_palette(self):
        """关闭面板。清空结果的点击矩形——留着会让面板外的点击命中到隐形条目。"""
        self.palette_active = False
        self.palette_input.active = False
        self.palette_results = []
        self.palette_result_rects = []
        self.palette_hover = -1

    def _pal_run_search(self):
        """按当前输入重算结果，并把选择夹回合法范围。

        空查询时改走 ``list_all``，把面板变成可浏览的「功能地图」——
        玩家不输任何字也能逛到全部功能（功能可发现性的治本补强）。
        """
        query = self.palette_input.text
        form = self._feature_form()
        mode = getattr(self, 'game_mode', 'practice')
        if query.strip():
            hits = _fi.search(query, form=form, mode=mode, limit=20)
            pairs = [(entry, available) for _s, entry, available in hits]
            # 零命中时改走 suggest 做相近推荐（结果同样可点击直达）
            if not pairs:
                pairs = _fi.suggest(query, form=form, mode=mode, k=5)
            # 仍零命中且 AI 兜底已配置 → 最后一道大模型兜底（离线未配置则静默跳过）
            if not pairs and _ai.is_configured():
                pairs = _ai.resolve(query, form=form, mode=mode,
                                   features=_fi.FEATURES, k=5)
            self.palette_results = pairs
        else:
            self.palette_results = _fi.list_all(form=form, mode=mode, limit=20)
        # 换词后条数会变，旧索引可能越界；夹回范围内而不是重置为 0——
        # 让玩家多删一个字时仍停在同一条上，符合直觉。
        if self.palette_results:
            self.palette_sel = max(0, min(self.palette_sel, len(self.palette_results) - 1))
        else:
            self.palette_sel = 0
        self.palette_scrollbar.set_scroll(self.palette_scrollbar.scroll)

    def _pal_activate(self, entry):
        """执行选中项：先关面板，再交给 _activate_feature 跳转。

        顺序不能反——`_activate_feature` 会打开设置框/菜单等，若面板还开着，
        它会盖在这些界面之上（面板是最上层），玩家看不到刚打开的设置页。
        """
        self.close_command_palette()
        self._activate_feature(entry)

    # ------------------------------------------------------------------
    # 文本截断（列表里不换行，超宽加省略号，保证行高可预测）
    # ------------------------------------------------------------------
    @staticmethod
    def _pal_clip(text, font, max_width):
        s = str(text or '')
        if not s or font.size(s)[0] <= max_width:
            return s
        ellipsis = '…'
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.size(s[:mid] + ellipsis)[0] <= max_width:
                lo = mid
            else:
                hi = mid - 1
        return s[:lo] + ellipsis

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def draw_command_palette(self):
        """绘制命令面板（主循环最后一步，位于所有模态之上）。"""
        screen = self.screen
        w = min(640, self.screen_width - 80)
        # 命令面板惯例：靠屏幕上方，不挡住棋盘中央
        top = max(40, int(self.screen_height * 0.16))
        rows_shown = min(_MAX_ROWS, max(1, len(self.palette_results)))
        list_h = (rows_shown * _ROW_H + (rows_shown - 1) * _ROW_GAP) if self.palette_results else 46
        h = _INPUT_H + 12 + list_h + _FOOT_H
        x = (self.screen_width - w) // 2
        self.palette_rect = pygame.Rect(x, top, w, h)

        # 遮罩：整屏变暗，点遮罩即关闭（与模态对话框同款）
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        pygame.draw.rect(screen, self.colors['dialog_bg'], self.palette_rect, border_radius=8)
        pygame.draw.rect(screen, self.colors['dialog_border'], self.palette_rect, 2, border_radius=8)

        # ---- 输入框 ----
        input_rect = pygame.Rect(x + 14, top + 12, w - 28, _INPUT_H - 12)
        self.palette_input_rect = input_rect
        self.palette_input.draw(screen, self.dialog_font, input_rect, self.colors)
        if not self.palette_input.text:
            ph = self.dialog_font.render(
                '搜索功能：着色 / 撤销 / 求解 / 三角 / 米字 / 怎么用 …', True, (140, 140, 140))
            screen.blit(ph, (input_rect.x + 6, input_rect.centery - ph.get_height() // 2))
        # 光标：TextInput.draw 只画背景与文本，闪烁光标由各调用方自行补
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            cx = input_rect.x + 6 + self.palette_input.get_cursor_offset(self.dialog_font)
            pygame.draw.line(screen, self.colors['input_text'],
                             (cx, input_rect.y + 6), (cx, input_rect.bottom - 6), 1)

        # ---- 结果列表 ----
        list_top = top + _INPUT_H + 12
        list_bottom = list_top + list_h
        mouse_pos = pygame.mouse.get_pos()

        if not self.palette_results:
            query = self.palette_input.text.strip()
            if query:
                msg = self.status_font.render(
                    f'没有功能匹配「{query}」。换个说法试试：着色 / 撤销 / 打乱 / 求解 / 三角 / 米字',
                    True, (150, 150, 150))
            else:
                msg = self.status_font.render(
                    '输入关键词开始搜索；↑↓ 选择，回车 直接到位，Esc 关闭', True, (150, 150, 150))
            screen.blit(msg, (x + 16, list_top + 14))
            self.palette_result_rects = []
            self._pal_draw_footer(x, top, w, h)
            return

        form = self._feature_form()
        mode = getattr(self, 'game_mode', 'practice')

        # 内容总高度：用于滚动条布局（所有结果行的总高）
        total_h = (len(self.palette_results) * _ROW_H
                   + (len(self.palette_results) - 1) * _ROW_GAP)
        sb = self.palette_scrollbar
        sb.layout(x + w - 16, list_top, list_h, total_h, list_h)
        scroll = sb.scroll

        clip = pygame.Rect(x + 10, list_top, w - 30, list_h)
        screen.set_clip(clip)

        rects = []
        hover_idx = -1
        for index, (entry, available) in enumerate(self.palette_results):
            row_y = list_top - scroll + index * (_ROW_H + _ROW_GAP)
            row = pygame.Rect(x + 12, row_y, w - 44, _ROW_H)
            rects.append((row, entry))
            # 悬停优先于键盘选择：鼠标指到哪就预览哪条，回车仍执行键盘选中项
            if row.collidepoint(mouse_pos):
                hover_idx = index
            highlighted = (index == self.palette_sel) or (index == hover_idx)
            if highlighted:
                pygame.draw.rect(screen, self.colors['button_hover'], row, border_radius=4)
                pygame.draw.rect(screen, self.colors['dialog_border'], row, 1, border_radius=4)

            # 第一行：名称 —— 位置。可不可用**不用符号前缀标记**（游戏字体对
            # ▶/✕ 这类符号缺字形，会画成空心豆腐块），靠颜色区分：可用=正常
            # 白，不可用=灰；说明行再给出原因，双保险。
            place = _fi.place_text(entry['place'])
            name_color = self.colors['dialog_text'] if available else (150, 150, 150)
            head_surf = self.dialog_font.render(
                self._pal_clip(entry['name'], self.dialog_font, w - 200),
                True, name_color)
            screen.blit(head_surf, (row.x + 10, row.y + 3))
            place_surf = self.status_font.render(self._pal_clip(place, self.status_font, 170),
                                                 True, (140, 180, 220))
            screen.blit(place_surf, (row.right - place_surf.get_width() - 8, row.y + 6))

            # 第二行：怎么用（不可用则改为显示为什么用不了，红色更醒目）
            if available:
                detail = entry.get('howto', '')
                dcolor = (160, 160, 160)
            else:
                detail = '当前不可用：' + _fi.unsupported_reason(entry, form, mode)
                dcolor = (210, 120, 120)
            d_surf = self.status_font.render(
                self._pal_clip(detail, self.status_font, row.width - 20), True, dcolor)
            screen.blit(d_surf, (row.x + 10, row.y + 28))

        screen.set_clip(None)
        self.palette_result_rects = rects
        self.palette_hover = hover_idx
        if sb.need_scroll():
            sb.draw(screen)

        self._pal_draw_footer(x, top, w, h)

    def _pal_draw_footer(self, x, top, w, h):
        """底部按键提示。"""
        tip = self.status_font.render(
            '↑↓ 选择 · 回车 直接到位 · Esc 或点击面板外 关闭', True, (150, 150, 150))
        self.screen.blit(tip, (x + 16, top + h - _FOOT_H + 4))

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _palette_handle_event(self, event) -> bool:
        """处理一个事件；返回 True 表示已消费，调用方应 continue。

        面板开着时它吃掉全部键鼠事件：它是最上层 UI，穿透会让玩家「看着面板、
        操作却落到棋盘上」。
        """
        etype = event.type

        # 中文/IME 组字结果：必须由 TEXTINPUT 处理（KEYDOWN.unicode 对 IME 无效）
        if etype == pygame.TEXTINPUT:
            self.palette_input.handle_event(event, self.dialog_font, self.palette_input_rect)
            self._pal_run_search()
            return True

        if etype == pygame.KEYDOWN:
            key = getattr(event, 'key', None)
            mods = getattr(event, 'mod', 0)
            if key == pygame.K_ESCAPE:
                self.close_command_palette()
                return True
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.palette_results:
                    self._pal_activate(self.palette_results[self.palette_sel][0])
                return True
            if key == pygame.K_DOWN:
                if self.palette_results:
                    self.palette_sel = (self.palette_sel + 1) % len(self.palette_results)
                    self._pal_scroll_to_sel()
                return True
            if key == pygame.K_UP:
                if self.palette_results:
                    self.palette_sel = (self.palette_sel - 1) % len(self.palette_results)
                    self._pal_scroll_to_sel()
                return True
            if key == pygame.K_PAGEDOWN:
                self.palette_scrollbar.on_key(pygame.K_PAGEDOWN)
                return True
            if key == pygame.K_PAGEUP:
                self.palette_scrollbar.on_key(pygame.K_PAGEUP)
                return True
            # 其余按键交给输入框（含 Ctrl+A/C/V、Backspace、左右移光标）
            consumed = self.palette_input.handle_event(
                event, self.dialog_font, self.palette_input_rect)
            if consumed and key not in (pygame.K_LCTRL, pygame.K_RCTRL,
                                        pygame.K_LSHIFT, pygame.K_RSHIFT,
                                        pygame.K_LALT, pygame.K_RALT):
                self._pal_run_search()
            return True

        if etype == pygame.MOUSEBUTTONDOWN and getattr(event, 'button', None) == 1:
            mx, my = getattr(event, 'pos', (0, 0))
            sb = self.palette_scrollbar
            if sb.need_scroll() and sb.track_rect.collidepoint(mx, my):
                sb.on_mouse_down((mx, my))
                return True
            for row, entry in self.palette_result_rects:
                if row.collidepoint(mx, my):
                    self._pal_activate(entry)
                    return True
            # 面板外 → 关闭；面板内其余位置 → 吃掉但不做事（避免穿透）
            if not self.palette_rect.collidepoint(mx, my):
                self.close_command_palette()
            return True

        if etype == pygame.MOUSEBUTTONUP and getattr(event, 'button', None) == 1:
            self.palette_scrollbar.on_mouse_up()
            return True

        if etype == pygame.MOUSEMOTION:
            mx, my = getattr(event, 'pos', (0, 0))
            self.palette_scrollbar.on_mouse_motion((mx, my))
            return True

        if etype == pygame.MOUSEWHEEL:
            dy = getattr(event, 'y', 0)
            self.palette_scrollbar.on_wheel(dy)
            return True

        # 其余事件（窗口事件等）不拦，交回主循环
        return False

    def _pal_scroll_to_sel(self):
        """键盘上下选中项时，把它滚进可见区。"""
        if not self.palette_results:
            return
        sb = self.palette_scrollbar
        if not sb.need_scroll():
            return
        sel = self.palette_sel
        top = sel * (_ROW_H + _ROW_GAP)
        bottom = top + _ROW_H
        viewport = sb.viewport_size
        if top < sb.scroll:
            sb.set_scroll(top)
        elif bottom > sb.scroll + viewport:
            sb.set_scroll(bottom - viewport)
