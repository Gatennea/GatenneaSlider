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

import os
import json
import pygame
from datetime import datetime
from records import format_time
from puzzle_types import create_puzzle, puzzle_key


class RecordsPanelMixin:
    """成绩记录面板（渲染 + 事件处理）"""

    # ---- 布局常量 ----
    _RP_TITLE_H = 26
    _RP_PAD = 10
    _RP_ROW_H = 26
    _RP_HEADER_H = 22
    _RP_WIDTH = 320
    _RP_SUMMARY_H = 64   # 统计摘要区高度（允许自动换行）
    _RP_MAX_VISIBLE = 8
    _RP_DETAIL_FIXED_H = 160  # 详情区固定高度（矩阵完整显示，超高自动缩字号）
    _RP_MATRIX_MIN_FS = 8     # 初始矩阵最小字号（低于此仍放不下则裁剪）

    # 列 x 偏移（相对面板左边）
    _RP_COL_IDX = 10
    _RP_COL_SINGLE = 40
    _RP_COL_AO5 = 104
    _RP_COL_AO12 = 172

    def _rp_init_state(self):
        """初始化成绩面板状态（在 GUI.__init__ 中调用）"""
        self.show_records_panel = True  # 默认开启（无 config 时）
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
        self.rp_matrix_rect = None       # 详情区左侧矩阵可点击区域（点击弹出操作菜单）
        self.rp_matrix_menu_open = False # 初始状态操作菜单是否打开
        self.rp_matrix_menu_rects = []   # [(rect, action_key)] 菜单项区域
        self._rp_fonts = {}              # 自适应字号字体缓存

    def _rp_current_key(self):
        return puzzle_key(self.current_step, self.current_m, self.current_n,
                          kind=self._current_kind(),
                          triangle_side=self.game.k if getattr(self, 'triangle_mode', False) else None)

    def _rp_detail_record(self):
        """返回当前展开详情的记录，不存在则置空返回 None"""
        if not self.rp_detail_id:
            return None
        for r in self.records.get_records(self._rp_current_key()):
            if r['id'] == self.rp_detail_id:
                return r
        self.rp_detail_id = None
        return None

    def _rp_base_height(self):
        """不含详情区时面板高度（固定部分）"""
        return (self._RP_TITLE_H + self._RP_SUMMARY_H + self._RP_HEADER_H +
                self._RP_PAD + self._RP_ROW_H * self._RP_MAX_VISIBLE + self._RP_PAD)

    def _rp_detail_height(self):
        """详情展开时占用的额外高度：固定高度，且不超过屏幕可用空间（收起为 0）"""
        if self._rp_detail_record() is None:
            return 0
        max_avail = (self.screen_height - self.status_bar_height - self.menu_bar_height - 20
                     - self._rp_base_height())
        return max(60, min(self._RP_DETAIL_FIXED_H, max_avail))

    def _rp_panel_size(self):
        height = self._rp_base_height() + self._rp_detail_height()
        return self._RP_WIDTH, height

    def _rp_build_layout(self):
        x, y = self.rp_pos
        w, h = self._rp_panel_size()
        self.rp_panel_rect = pygame.Rect(x, y, w, h)
        # 详情展开时矩阵点击区域（布局阶段即计算，事件处理不依赖绘制）
        detail_h = self._rp_detail_height()
        if detail_h > 0:
            self.rp_matrix_rect = pygame.Rect(x + self._RP_PAD, y + h - detail_h + 4, 132, detail_h - 8)
        else:
            self.rp_matrix_rect = None
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
    def _rp_value_style(val, best, worst):
        """列数值样式：最好标绿、最差标红（DNF按最差计）、其他默认色"""
        if val is None:
            return '-', (110, 110, 120)
        if val == 'DNF':
            return 'DNF', (255, 90, 90)
        if best is not None and val == best:
            return format_time(val), (120, 220, 120)
        if worst is not None and val == worst:
            return format_time(val), (255, 90, 90)
        return format_time(val), (210, 210, 210)

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
        series = self.records.series(key)

        def _fmt(v):
            if v is None:
                return '-'
            if v == 'DNF':
                return 'DNF'
            return format_time(v)

        # 平均最好：整组 Ao5 中的最小值（None/'DNF' 不计）
        best_ao5 = None
        for _, a5, _ in series:
            if isinstance(a5, (int, float)) and (best_ao5 is None or a5 < best_ao5):
                best_ao5 = a5

        summary1 = f"{key}  共 {st['count']} 次"
        sy = y + self._RP_TITLE_H + 6
        self.screen.blit(self.status_font.render(summary1, True, (170, 200, 255)), (x + self._RP_PAD, sy))
        # 第二行：单次最好（绿）、平均最好（绿）、总平均（默认），超宽自动换行
        segments = [
            (f"单次最好 {_fmt(st['best'])}",
             (120, 220, 120) if st['best'] is not None else (200, 200, 200)),
            (f"平均最好 {_fmt(best_ao5)}",
             (120, 220, 120) if best_ao5 is not None else (200, 200, 200)),
            (f"总平均 {_fmt(st['mean'])}", (200, 200, 200)),
        ]
        sx = x + self._RP_PAD
        sy2 = sy + 18
        for text, color in segments:
            surf = self.status_font.render(text, True, color)
            if sx + surf.get_width() > x + w - self._RP_PAD and sx > x + self._RP_PAD:
                sx = x + self._RP_PAD
                sy2 += 16
            self.screen.blit(surf, (sx, sy2))
            sx += surf.get_width() + 14

        # 列头
        hy = y + self._RP_TITLE_H + self._RP_SUMMARY_H
        for text, cx in (("#", self._RP_COL_IDX), ("单次", self._RP_COL_SINGLE),
                         ("Ao5", self._RP_COL_AO5), ("Ao12", self._RP_COL_AO12)):
            head = self.status_font.render(text, True, (150, 160, 180))
            self.screen.blit(head, (x + cx, hy + 4))

        # 成绩列表（倒序显示：最新在前），每行 单次 / Ao5 / Ao12
        self._rp_clamp_scroll(len(series))
        shown = series[::-1][self.rp_scroll:self.rp_scroll + self._RP_MAX_VISIBLE]

        # 各列最好/最差（整组统计：单次用有效成绩；AoN 忽略 None/'DNF'）
        valid_times = [r2['time_ms'] for r2, _, _ in series if not r2['dnf']]
        best_t = min(valid_times) if valid_times else None
        worst_t = max(valid_times) if valid_times else None
        a5_nums = [a for _, a, _ in series if isinstance(a, (int, float))]
        best_a5 = min(a5_nums) if a5_nums else None
        worst_a5 = max(a5_nums) if a5_nums else None
        a12_nums = [a for _, _, a in series if isinstance(a, (int, float))]
        best_a12 = min(a12_nums) if a12_nums else None
        worst_a12 = max(a12_nums) if a12_nums else None

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
                    if best_t is not None and r['time_ms'] == best_t:
                        time_color = (120, 220, 120)  # 单次最好
                    elif worst_t is not None and r['time_ms'] == worst_t:
                        time_color = (255, 90, 90)    # 单次最差
                    else:
                        time_color = (210, 210, 210)  # 默认色
                ao5_text, ao5_color = self._rp_value_style(ao5, best_a5, worst_a5)
                ao12_text, ao12_color = self._rp_value_style(ao12, best_a12, worst_a12)

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

        # 初始状态操作菜单（绘制在面板之上）
        self._rp_draw_matrix_menu(x, y, w)

    def _rp_get_font(self, size):
        """按字号获取缓存的字体（用于初始矩阵自适应缩放）"""
        fnt = self._rp_fonts.get(size)
        if fnt is None:
            try:
                fnt = pygame.font.Font('C:/Windows/Fonts/msyh.ttc', size)
            except Exception:
                fnt = pygame.font.Font(None, size)
            self._rp_fonts[size] = fnt
        return fnt

    def _rp_matrix_font_size(self, line_count, col_count, avail_w, avail_h):
        """选择能完整放下矩阵的最大字号（从默认字号递减到下限）"""
        base = min(12, self.status_font.get_height())
        for fs in range(base, self._RP_MATRIX_MIN_FS - 1, -1):
            if line_count * (fs + 2) <= avail_h and col_count * fs <= avail_w:
                return fs
        return self._RP_MATRIX_MIN_FS

    def _rp_draw_detail(self, x, y, w, h, rec):
        """绘制行详情：左侧初始矩阵（完整显示，自适应字号，可点击弹出操作菜单），右侧信息每条一行"""
        detail_rect = pygame.Rect(x + self._RP_PAD, y, w - self._RP_PAD * 2, h)
        pygame.draw.rect(self.screen, (46, 50, 62), detail_rect, border_radius=4)
        pygame.draw.rect(self.screen, (110, 120, 150), detail_rect, 1, border_radius=4)

        # 左：初始矩阵（完整显示，行数多时自动缩小字号）
        left_w = 132
        label = self.status_font.render("初始状态（点击）", True, (140, 160, 200))
        self.screen.blit(label, (x + self._RP_PAD + 8, y + 6))
        matrix = rec['initial_matrix'].replace('1', '█').replace('0', '·')
        raw_lines = matrix.split('\n')
        lines = [ln for ln in raw_lines if ln]
        cols = max((len(ln) for ln in lines), default=0)
        avail_w = left_w - 16
        avail_h = h - 24 - 4
        fs = self._rp_matrix_font_size(len(lines), cols, avail_w, avail_h)
        fnt = self._rp_get_font(fs)
        line_h = fs + 2
        my = y + 24
        old_clip = self.screen.get_clip()
        self.screen.set_clip(detail_rect)  # 极端情况下裁掉超出详情区部分，避免盖住其他内容
        for line in lines:
            line_surf = fnt.render(line, True, (160, 210, 255))
            self.screen.blit(line_surf, (x + self._RP_PAD + 8, my))
            my += line_h
        self.screen.set_clip(old_clip)
        self.rp_matrix_rect = pygame.Rect(x + self._RP_PAD, y + 4, left_w, h - 8)

        # 右：信息每条一行（生成时间含年份与秒，超宽时值换行显示）
        info_x = x + self._RP_PAD + left_w + 4
        info_w = w - self._RP_PAD * 2 - left_w - 8
        if rec['dnf']:
            time_text = "DNF"
        else:
            time_text = format_time(rec['time_ms'])
        tps = rec['moves'] / (rec['time_ms'] / 1000.0) if rec['time_ms'] > 0 else 0.0
        ts_str = datetime.fromtimestamp(rec['ts']).strftime('%Y-%m-%d %H:%M:%S')
        info_lines = [
            ("时间", time_text),
            ("步数", str(rec['moves'])),
            ("TPS", f"{tps:.2f}"),
            ("成绩生成时间", ts_str),
        ]
        info_line_h = self.status_font.get_height() + 2
        iy = y + 6
        for i, (lbl, val) in enumerate(info_lines):
            if i == len(info_lines) - 1:
                # 生成时间：标签一行、值一行（含年份+秒，宽度充足）
                self.screen.blit(self.status_font.render(lbl, True, (150, 160, 180)),
                                 (info_x, iy))
                iy += info_line_h
                val_surf = self.status_font.render(val, True, (210, 210, 210))
                if val_surf.get_width() > info_w:
                    # 极端窄面板兜底：截断加省略号
                    while val_surf.get_width() > info_w and len(val) > 4:
                        val = val[:-1]
                        val_surf = self.status_font.render(val + '…', True, (210, 210, 210))
                self.screen.blit(val_surf, (info_x, iy))
                iy += info_line_h
            else:
                info_surf = self.status_font.render(f"{lbl} {val}", True, (210, 210, 210))
                if info_surf.get_width() > info_w:
                    info_surf = self.status_font.render(f"{lbl}…", True, (210, 210, 210))
                self.screen.blit(info_surf, (info_x, iy))
                iy += info_line_h

    def _rp_copy_matrix(self, text: str) -> bool:
        """复制初始状态到系统剪贴板：优先 Windows API（可靠），失败回退 pygame.scrap"""
        try:
            import ctypes
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            GMEM_ZEROINIT = 0x0040
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(0):
                try:
                    user32.EmptyClipboard()
                    data = text.encode('utf-16-le') + b'\x00\x00'
                    h = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(data))
                    if not h:
                        return False
                    ptr = kernel32.GlobalLock(h)
                    if ptr:
                        ctypes.memmove(ptr, data, len(data))
                        kernel32.GlobalUnlock(h)
                        if user32.SetClipboardData(CF_UNICODETEXT, h):
                            h = None  # 成功后由系统接管
                finally:
                    if h:
                        kernel32.GlobalFree(h)
                    user32.CloseClipboard()
                return True
        except Exception:
            pass
        # 兜底：pygame.scrap
        try:
            try:
                pygame.scrap.init()
            except Exception:
                pass
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode('utf-8'))
            return True
        except Exception:
            return False

    def _rp_record_map_str(self, rec) -> str:
        """记录初始矩阵（0/1）转回地图字符串（#/_）"""
        return rec['initial_matrix'].replace('1', '#').replace('0', '_')

    def _rp_save_as_puzzle(self, rec) -> str:
        """把该打乱另存为 .json 存档（结构同普通存档，可直接「文件-打开」载入）"""
        try:
            numbered = bool(rec.get('numbered')) or str(rec.get('puzzle_key', '')).endswith('#num')
            game = create_puzzle(rec['m'], rec['n'], rec['step'])
            if not game.import_map(self._rp_record_map_str(rec)):
                return ''
            game.update_matrix()
            if numbered:
                for i, block in enumerate(sorted(game.blocks, key=lambda b: (b.location[0], b.location[1]))):
                    block.number = i + 1
            snap = {
                'matrix': [r[:] for r in game.matrix],
                'bounds': dict(game.matrix_bounds),
                'move_info': None,
            }
            if numbered:
                bounds = dict(game.matrix_bounds)
                num_map = {tuple(b.location): b.number for b in game.blocks}
                snap['numbers'] = [
                    [num_map.get((bounds['min_row'] + ri, bounds['min_col'] + ci), 0) if v else 0
                     for ci, v in enumerate(row)]
                    for ri, row in enumerate(game.matrix)
                ]
            data = {
                'version': 2 if numbered else 1,
                'puzzle': {'m': rec['m'], 'n': rec['n'], 'step': rec['step']},
                'step_count': 0,
                'history': {'history_index': 0, 'snapshots': [snap]},
            }
            if numbered:
                data['puzzle']['type'] = 'numbered'
            ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            name = f"{rec['step']}-{rec['m']}-{rec['n']}-{ts}.json"
            os.makedirs(self.save_dir, exist_ok=True)
            path = os.path.join(self.save_dir, name)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return path
        except Exception:
            return ''

    def _rp_load_into_practice(self, rec):
        """把该打乱载入为当前谜题（练习模式），立即复现"""
        if self.animating:
            self.cancel_animation()
        numbered = bool(rec.get('numbered')) or str(rec.get('puzzle_key', '')).endswith('#num')
        self.current_m = rec['m']
        self.current_n = rec['n']
        self.current_step = rec['step']
        self.step_count = 0
        self.numbered = numbered
        self.game = create_puzzle(rec['m'], rec['n'], rec['step'])
        self.game.import_map(self._rp_record_map_str(rec))
        self.game.update_matrix()
        if numbered:
            for i, block in enumerate(sorted(self.game.blocks, key=lambda b: (b.location[0], b.location[1]))):
                block.number = i + 1
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self.ensure_blocks_visible()
        self.selected_gap = None
        self.selected_block = None
        self.game_mode = 'practice'
        self._timer_cancel()
        self.current_file_path = None

    def _rp_run_menu_action(self, action: str):
        """执行初始状态操作菜单的动作"""
        rec = self._rp_detail_record()
        if rec is None:
            return
        if action == 'copy':
            ok = self._rp_copy_matrix(rec['initial_matrix'])
            self.macro_notify_msg = "已复制初始状态" if ok else "复制失败（剪贴板不可用）"
        elif action == 'save':
            path = self._rp_save_as_puzzle(rec)
            self.macro_notify_msg = (f"已另存为存档：{os.path.basename(path)}"
                                     if path else "另存为存档失败")
        elif action == 'load':
            self._rp_load_into_practice(rec)
            self.macro_notify_msg = "已载入练习模式，可开始复原"
        self.macro_notify_timer = 120

    def _rp_draw_matrix_menu(self, x, y, w):
        """绘制初始状态操作菜单（复制/另存为存档/载入练习模式）"""
        if not self.rp_matrix_menu_open:
            self.rp_matrix_menu_rects = []
            return
        items = [("复制到剪贴板", 'copy'), ("另存为存档", 'save'), ("载入练习模式", 'load')]
        item_h = 24
        mw = 150
        mh = len(items) * item_h + 8
        mx = x + w - self._RP_PAD - 8 - mw
        my = y + 4
        # 钳制到窗口内（菜单可能超出面板底部）
        mx = max(4, min(mx, self.screen_width - mw - 4))
        my = max(self.menu_bar_height,
                 min(my, self.screen_height - self.status_bar_height - mh - 4))
        bg = pygame.Surface((mw, mh), pygame.SRCALPHA)
        bg.fill((52, 52, 62, 245))
        self.screen.blit(bg, (mx, my))
        pygame.draw.rect(self.screen, (110, 120, 150), (mx, my, mw, mh), 1, border_radius=4)
        mouse_pos = pygame.mouse.get_pos()
        self.rp_matrix_menu_rects = []
        yy = my + 4
        for label, action in items:
            item_rect = pygame.Rect(mx + 4, yy, mw - 8, item_h)
            if item_rect.collidepoint(mouse_pos):
                pygame.draw.rect(self.screen, (70, 80, 100), item_rect, border_radius=3)
            surf = self.status_font.render(label, True, (220, 220, 220))
            self.screen.blit(surf, (item_rect.x + 8,
                                    item_rect.y + (item_h - surf.get_height()) // 2))
            self.rp_matrix_menu_rects.append((item_rect, action))
            yy += item_h

    def handle_records_panel_event(self, event):
        """处理成绩面板事件（拖动/关闭/滚动/删除/详情），返回 True 表示事件已消费。"""
        if not getattr(self, 'show_records_panel', False):
            return False

        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self._rp_build_layout()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if not self.rp_panel_rect.collidepoint(mx, my):
                # 点击面板外：取消删除确认、关闭操作菜单
                self.rp_confirm_delete_id = None
                self.rp_matrix_menu_open = False
                self.rp_matrix_menu_rects = []
                return False

            # 初始状态操作菜单：优先处理菜单项点击
            if self.rp_matrix_menu_open:
                hit = None
                for rect, action in self.rp_matrix_menu_rects:
                    if rect.collidepoint(mx, my):
                        hit = action
                        break
                self.rp_matrix_menu_open = False
                self.rp_matrix_menu_rects = []
                if hit is not None:
                    self._rp_run_menu_action(hit)
                    return True
                # 点击菜单外：关闭后继续处理面板其他区域

            if self.rp_close_rect.collidepoint(mx, my):
                self.show_records_panel = False
                self.rp_confirm_delete_id = None
                self.rp_detail_id = None
                self.rp_matrix_menu_open = False
                self.rp_matrix_menu_rects = []
                return True

            if self.rp_title_rect.collidepoint(mx, my):
                self.rp_dragging = True
                self.rp_drag_offset = (mx - self.rp_pos[0], my - self.rp_pos[1])
                self.rp_matrix_menu_open = False
                self.rp_matrix_menu_rects = []
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

            # 点击详情区左侧矩阵：弹出操作菜单（复制/另存为存档/载入练习模式）
            if getattr(self, 'rp_matrix_rect', None) and self.rp_matrix_rect.collidepoint(mx, my):
                if self._rp_detail_record() is not None:
                    self.rp_matrix_menu_open = not self.rp_matrix_menu_open
                    self.rp_matrix_menu_rects = []
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
