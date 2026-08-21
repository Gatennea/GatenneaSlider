# -*- coding: utf-8 -*-
"""
成绩记录面板 Mixin

提供可拖动、独立浮动的「成绩记录」面板，展示当前谜题分组的成绩列表与统计：
- 统计摘要：最好 / 最差 / Ao5 / Ao12 / DNF
- 三列布局（模仿魔方计时器）：每行展示 单次成绩 / Ao5 / Ao12
- 右侧可拖动滑块滚动条（复用「设置-动画时长」滑动条的交互样式）
- 点击行在面板内展开详情：打乱后初始状态、成绩生成时间、步数、TPS
- 支持删除（二次确认），不支持编辑
- 标题栏拖动，右上角 × 关闭
"""

import pygame
from datetime import datetime
from records import format_time


class RecordsPanelMixin:
    """成绩记录面板（渲染 + 事件处理）"""

    # ---- 布局常量 ----
    _RP_TITLE_H = 26
    _RP_PAD = 10
    _RP_ROW_H = 26
    _RP_HEADER_H = 22
    _RP_WIDTH = 480
    _RP_SUMMARY_H = 50   # 统计摘要区高度
    _RP_MAX_VISIBLE = 8
    _RP_DETAIL_BASE_H = 54   # 详情区基础高度（不含矩阵）
    _RP_DETAIL_LINE_H = 15   # 初始矩阵每行高度
    _RP_DETAIL_MAX_LINES = 8 # 初始矩阵最多显示行数

    # 列 x 偏移（相对面板左边）
    _RP_COL_IDX = 12
    _RP_COL_SINGLE = 56
    _RP_COL_AO5 = 152
    _RP_COL_AO12 = 252

    def _rp_init_state(self):
        """初始化成绩面板状态（在 GUI.__init__ 中调用）"""
        self.show_records_panel = False
        self.rp_pos = [self.screen_width - self.right_panel_width - self._RP_WIDTH - 10,
                       self.menu_bar_height + 10]
        self.rp_dragging = False
        self.rp_drag_offset = (0, 0)
        self.rp_scroll = 0
        self.rp_panel_rect = None
        self.rp_title_rect = None
        self.rp_close_rect = None
        self.rp_list_rect = None
        self.rp_row_rects = []           # [(rect, record_id)]
        self.rp_delete_rects = []        # [(rect, record_id)]
        self.rp_scrollbar_track_rect = None
        self.rp_scrollbar_knob_rect = None
        self.rp_scrollbar_dragging = False
        self.rp_confirm_delete_id = None   # 二次确认待删除的记录 id
        self.rp_detail_id = None         # 当前展开详情的记录 id（None=收起）

    def _rp_current_key(self):
        return f"{self.current_step}~{self.current_m}*{self.current_n}"

    def _rp_detail_record(self):
        """返回当前展开详情的记录，不存在则置空返回 None"""
        if not self.rp_detail_id:
            return None
        for r in self.records.get_records(self._rp_current_key()):
            if r['id'] == self.rp_detail_id:
                return r
        self.rp_detail_id = None
        return None

    def _rp_detail_height(self):
        """详情展开时占用的额外高度（收起为 0）"""
        rec = self._rp_detail_record()
        if rec is None:
            return 0
        lines = rec['initial_matrix'].count('\n') + 1
        lines = min(lines, self._RP_DETAIL_MAX_LINES)
        return self._RP_DETAIL_BASE_H + lines * self._RP_DETAIL_LINE_H

    def _rp_panel_size(self):
        height = (self._RP_TITLE_H + self._RP_SUMMARY_H + self._RP_HEADER_H +
                  self._RP_PAD + self._RP_ROW_H * self._RP_MAX_VISIBLE + self._RP_PAD +
                  self._rp_detail_height())
        return self._RP_WIDTH, height

    def _rp_build_layout(self):
        x, y = self.rp_pos
        w, h = self._rp_panel_size()
        self.rp_panel_rect = pygame.Rect(x, y, w, h)
        self.rp_title_rect = pygame.Rect(x, y, w, self._RP_TITLE_H)
        close_w = 20
        self.rp_close_rect = pygame.Rect(
            x + w - self._RP_PAD - close_w,
            y + (self._RP_TITLE_H - close_w) // 2,
            close_w, close_w,
        )
        # 列表区（含列头下方）
        list_top = y + self._RP_TITLE_H + self._RP_SUMMARY_H + self._RP_HEADER_H
        list_h = self._RP_ROW_H * self._RP_MAX_VISIBLE
        self.rp_list_rect = pygame.Rect(x, list_top, w, list_h)
        # 滚动条轨道（列表区右侧）
        track_x = x + w - self._RP_PAD - 8
        self.rp_scrollbar_track_rect = pygame.Rect(track_x, list_top + 4, 4, list_h - 8)
        self.rp_scrollbar_knob_rect = pygame.Rect(track_x - 6, list_top + 4, 16, 24)

    def _rp_clamp_position(self):
        w, h = self._rp_panel_size()
        self.rp_pos[0] = max(0, min(self.rp_pos[0], self.screen_width - w))
        self.rp_pos[1] = max(self.menu_bar_height,
                             min(self.rp_pos[1], self.screen_height - self.status_bar_height - h))

    def _rp_clamp_scroll(self, total):
        max_scroll = max(0, total - self._RP_MAX_VISIBLE)
        self.rp_scroll = max(0, min(self.rp_scroll, max_scroll))

    def _rp_update_scrollbar(self, mouse_y):
        """根据鼠标 Y 坐标更新列表滚动位置（滑块滚动条）"""
        track = self.rp_scrollbar_track_rect
        if not track or track.height <= 0:
            return
        total = len(self.records.get_records(self._rp_current_key()))
        max_scroll = max(0, total - self._RP_MAX_VISIBLE)
        ratio = (mouse_y - track.y) / track.height
        self.rp_scroll = int(max(0.0, min(1.0, ratio)) * max_scroll)

    @staticmethod
    def _rp_ao_style(ao):
        """Ao5/Ao12 显示样式：(文本, 颜色)"""
        if ao is None:
            return '-', (110, 110, 120)
        if ao == 'DNF':
            return 'DNF', (255, 120, 120)
        return format_time(ao), (190, 190, 200)

    def draw_records_panel(self):
        """绘制成绩记录面板。"""
        if not getattr(self, 'show_records_panel', False):
            return

        x, y = self.rp_pos
        w, h = self._rp_panel_size()
        self._rp_build_layout()
        mouse_pos = pygame.mouse.get_pos()
        key = self._rp_current_key()

        # 半透明背景
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        bg.fill((40, 40, 48, 235))
        self.screen.blit(bg, (x, y))
        pygame.draw.rect(self.screen, self.colors['dialog_border'],
                         self.rp_panel_rect, 1, border_radius=6)

        # 标题栏
        title_bg = pygame.Surface((w, self._RP_TITLE_H), pygame.SRCALPHA)
        title_bg.fill((60, 60, 72, 235))
        self.screen.blit(title_bg, (x, y))
        title_surface = self.status_font.render("成绩记录", True, (220, 220, 220))
        self.screen.blit(title_surface, (
            x + self._RP_PAD,
            y + (self._RP_TITLE_H - title_surface.get_height()) // 2
        ))

        # 关闭按钮 ×
        close_hovered = self.rp_close_rect.collidepoint(mouse_pos)
        close_color = self.colors['button_hover'] if close_hovered else self.colors['button_bg']
        pygame.draw.rect(self.screen, close_color, self.rp_close_rect, border_radius=3)
        close_surface = self.status_font.render("×", True, (255, 255, 255))
        self.screen.blit(close_surface, close_surface.get_rect(center=self.rp_close_rect.center))

        # 统计摘要区
        st = self.records.stats(key)

        def _fmt(v):
            if v is None:
                return '-'
            if v == 'DNF':
                return 'DNF'
            return format_time(v)

        summary1 = f"{key}  共 {st['count']} 次"
        summary2 = (f"最好 {_fmt(st['best'])}  最差 {_fmt(st['worst'])}  "
                    f"Ao5 {_fmt(st['ao5'])}  Ao12 {_fmt(st['ao12'])}  DNF {st['dnf_count']}")
        sy = y + self._RP_TITLE_H + 6
        self.screen.blit(self.status_font.render(summary1, True, (170, 200, 255)), (x + self._RP_PAD, sy))
        self.screen.blit(self.status_font.render(summary2, True, (200, 200, 200)), (x + self._RP_PAD, sy + 22))

        # 列头
        hy = y + self._RP_TITLE_H + self._RP_SUMMARY_H
        for text, cx in (("#", self._RP_COL_IDX), ("单次", self._RP_COL_SINGLE),
                         ("Ao5", self._RP_COL_AO5), ("Ao12", self._RP_COL_AO12)):
            head = self.status_font.render(text, True, (150, 160, 180))
            self.screen.blit(head, (x + cx, hy + 4))

        # 成绩列表（倒序显示：最新在前），每行 单次 / Ao5 / Ao12
        series = self.records.series(key)
        self._rp_clamp_scroll(len(series))
        shown = series[::-1][self.rp_scroll:self.rp_scroll + self._RP_MAX_VISIBLE]

        self.rp_row_rects = []
        self.rp_delete_rects = []
        list_top = self.rp_list_rect.y
        row_y = list_top
        global_index = len(series) - self.rp_scroll  # 倒序显示的第一条对应的原始序号

        if not shown:
            empty = self.status_font.render("暂无成绩", True, (130, 130, 130))
            self.screen.blit(empty, (x + self._RP_PAD, row_y + 10))
        else:
            for i, (r, ao5, ao12) in enumerate(shown):
                idx = global_index - i
                row_rect = pygame.Rect(x + 4, row_y, w - 8, self._RP_ROW_H)
                self.rp_row_rects.append((row_rect, r['id']))

                # 行高亮：详情展开行 / 悬停行
                if r['id'] == self.rp_detail_id:
                    pygame.draw.rect(self.screen, (62, 82, 118), row_rect, border_radius=4)
                elif row_rect.collidepoint(mouse_pos):
                    pygame.draw.rect(self.screen, (54, 57, 70), row_rect, border_radius=4)

                if r['dnf']:
                    time_text = "DNF"
                    time_color = (255, 90, 90)
                else:
                    time_text = format_time(r['time_ms'])
                    time_color = (120, 220, 120)
                ao5_text, ao5_color = self._rp_ao_style(ao5)
                ao12_text, ao12_color = self._rp_ao_style(ao12)

                idx_surf = self.status_font.render(f"#{idx}", True, (150, 150, 160))
                time_surf = self.status_font.render(time_text, True, time_color)
                ao5_surf = self.status_font.render(ao5_text, True, ao5_color)
                ao12_surf = self.status_font.render(ao12_text, True, ao12_color)

                self.screen.blit(idx_surf, (x + self._RP_COL_IDX, row_y + 4))
                self.screen.blit(time_surf, (x + self._RP_COL_SINGLE, row_y + 4))
                self.screen.blit(ao5_surf, (x + self._RP_COL_AO5, row_y + 4))
                self.screen.blit(ao12_surf, (x + self._RP_COL_AO12, row_y + 4))

                # 删除按钮 ×
                del_w = 22
                del_rect = pygame.Rect(x + w - self._RP_PAD - 8 - del_w, row_y + 2, del_w, self._RP_ROW_H - 4)
                self.rp_delete_rects.append((del_rect, r['id']))
                is_confirm = (r['id'] == self.rp_confirm_delete_id)
                del_color = (220, 80, 80) if is_confirm else (120, 60, 60)
                if del_rect.collidepoint(mouse_pos):
                    del_color = (255, 120, 120)
                pygame.draw.rect(self.screen, del_color, del_rect, border_radius=3)
                del_text = "确认?" if is_confirm else "×"
                del_surf = self.status_font.render(del_text, True, (255, 255, 255))
                self.screen.blit(del_surf, del_surf.get_rect(center=del_rect.center))

                row_y += self._RP_ROW_H

        # 滑块滚动条
        total = len(series)
        if total > self._RP_MAX_VISIBLE:
            track = self.rp_scrollbar_track_rect
            pygame.draw.rect(self.screen, (80, 80, 92), track)
            max_scroll = total - self._RP_MAX_VISIBLE
            ratio = self.rp_scroll / max_scroll if max_scroll > 0 else 0.0
            knob_h = max(20, int(track.height * (self._RP_MAX_VISIBLE / total)))
            knob_y = track.y + int(ratio * (track.height - knob_h))
            self.rp_scrollbar_knob_rect = pygame.Rect(track.x - 6, knob_y, 16, knob_h)
            knob_color = self.colors['button_hover'] if self.rp_scrollbar_dragging else self.colors['button_bg']
            if self.rp_scrollbar_knob_rect.collidepoint(mouse_pos):
                knob_color = self.colors['button_hover']
            pygame.draw.rect(self.screen, knob_color, self.rp_scrollbar_knob_rect, border_radius=8)
        else:
            self.rp_scrollbar_knob_rect = pygame.Rect(0, 0, 0, 0)

        # 详情区（面板内展开）
        rec = self._rp_detail_record()
        if rec is not None:
            self._rp_draw_detail(x, y + h - self._rp_detail_height(), w, self._rp_detail_height(), rec)

    def _rp_draw_detail(self, x, y, w, h, rec):
        """绘制行详情：初始矩阵、生成时间、步数、TPS"""
        detail_rect = pygame.Rect(x + self._RP_PAD, y, w - self._RP_PAD * 2, h)
        pygame.draw.rect(self.screen, (46, 50, 62), detail_rect, border_radius=4)
        pygame.draw.rect(self.screen, (110, 120, 150), detail_rect, 1, border_radius=4)

        if rec['dnf']:
            time_text = "DNF"
        else:
            time_text = format_time(rec['time_ms'])
        tps = rec['moves'] / (rec['time_ms'] / 1000.0) if rec['time_ms'] > 0 else 0.0
        ts_str = datetime.fromtimestamp(rec['ts']).strftime('%Y-%m-%d %H:%M:%S')
        info = f"时间 {time_text}   步数 {rec['moves']}   TPS {tps:.2f}"
        info_surf = self.status_font.render(info, True, (220, 220, 220))
        self.screen.blit(info_surf, (x + self._RP_PAD + 8, y + 5))
        ts_surf = self.status_font.render(f"生成于 {ts_str}", True, (170, 170, 180))
        ts_x = x + w - self._RP_PAD - 8 - ts_surf.get_width()
        self.screen.blit(ts_surf, (ts_x, y + 5))

        label = self.status_font.render("打乱后初始状态：", True, (140, 160, 200))
        self.screen.blit(label, (x + self._RP_PAD + 8, y + 24))

        matrix = rec['initial_matrix'].replace('1', '█').replace('0', '·')
        lines = matrix.split('\n')[:self._RP_DETAIL_MAX_LINES]
        my = y + 42
        for line in lines:
            line_surf = self.status_font.render(line, True, (160, 210, 255))
            self.screen.blit(line_surf, (x + self._RP_PAD + 20, my))
            my += self._RP_DETAIL_LINE_H

        #tip = self.status_font.render("再点该行收起", True, (130, 130, 140))
        #self.screen.blit(tip, (x + self._RP_PAD + 8, y + h - 20))

    def handle_records_panel_event(self, event):
        """处理成绩面板事件（拖动/关闭/滚动/删除/详情），返回 True 表示事件已消费。"""
        if not getattr(self, 'show_records_panel', False):
            return False

        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self._rp_build_layout()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if not self.rp_panel_rect.collidepoint(mx, my):
                # 点击面板外：取消删除确认
                self.rp_confirm_delete_id = None
                return False

            if self.rp_close_rect.collidepoint(mx, my):
                self.show_records_panel = False
                self.rp_confirm_delete_id = None
                self.rp_detail_id = None
                return True

            if self.rp_title_rect.collidepoint(mx, my):
                self.rp_dragging = True
                self.rp_drag_offset = (mx - self.rp_pos[0], my - self.rp_pos[1])
                return True

            # 滑块滚动条
            if self.rp_scrollbar_knob_rect and self.rp_scrollbar_knob_rect.width > 0 and \
               (self.rp_scrollbar_knob_rect.collidepoint(mx, my) or
                (self.rp_scrollbar_track_rect and self.rp_scrollbar_track_rect.collidepoint(mx, my))):
                self.rp_scrollbar_dragging = True
                self._rp_update_scrollbar(my)
                return True

            # 删除按钮
            for rect, rid in self.rp_delete_rects:
                if rect.collidepoint(mx, my):
                    if self.rp_confirm_delete_id == rid:
                        self.records.delete_record(self._rp_current_key(), rid)
                        self.rp_confirm_delete_id = None
                        if self.rp_detail_id == rid:
                            self.rp_detail_id = None
                        self.macro_notify_msg = "已删除一条成绩"
                        self.macro_notify_timer = 90
                    else:
                        self.rp_confirm_delete_id = rid
                    return True

            # 点击行：切换详情展开
            for rect, rid in self.rp_row_rects:
                if rect.collidepoint(mx, my):
                    if self.rp_detail_id == rid:
                        self.rp_detail_id = None
                    else:
                        self.rp_detail_id = rid
                    self.rp_confirm_delete_id = None
                    return True

            # 面板空白处：消费事件，避免穿透
            self.rp_confirm_delete_id = None
            return True

        elif event.type == pygame.MOUSEMOTION:
            if self.rp_dragging:
                self.rp_pos[0] = event.pos[0] - self.rp_drag_offset[0]
                self.rp_pos[1] = event.pos[1] - self.rp_drag_offset[1]
                self._rp_clamp_position()
                return True
            if self.rp_scrollbar_dragging:
                self._rp_update_scrollbar(event.pos[1])
                return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.rp_dragging or self.rp_scrollbar_dragging:
                self.rp_dragging = False
                self.rp_scrollbar_dragging = False
                return True

        elif event.type == pygame.MOUSEWHEEL:
            # pygame-ce 的 MOUSEWHEEL 事件没有 pos 属性，用鼠标当前位置判断
            self._rp_build_layout()
            mx, my = pygame.mouse.get_pos()
            if self.rp_panel_rect and self.rp_panel_rect.collidepoint(mx, my):
                key = self._rp_current_key()
                total = len(self.records.get_records(key))
                self.rp_scroll -= event.y
                self._rp_clamp_scroll(total)
                return True

        return False
