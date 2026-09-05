# -*- coding: utf-8 -*-
"""
调试面板 Mixin

提供可拖动、独立浮动的「调试面板」，实时显示当前游戏状态的：
- 聚拢度 score（0~1）
- 重叠块数
- 边界盒（高×宽）
- 填充率

面板打开时，同时在棋盘上高亮画出「洞」和「凸起」的位置。
面板通过标题栏拖动，点击右上角 × 关闭。
"""

import pygame


class MetricsPanelMixin:
    """调试面板（渲染 + 事件处理）"""

    # ---- 布局常量 ----
    _MP_TITLE_H = 26
    _MP_PAD = 10
    _MP_ROW_H = 22
    _MP_WIDTH = 190

    def _mp_init_state(self):
        """初始化指标面板状态（在 GUI.__init__ 中调用）"""
        self.show_metrics_panel = False #調試面板默認關閉
        self.mp_pos = [10, self.menu_bar_height + 10]
        self.mp_dragging = False
        self.mp_drag_offset = (0, 0)
        self.mp_panel_rect = None
        self.mp_title_rect = None
        self.mp_close_rect = None
        self.selected_hole = None  # 标记学习：当前选中的洞

    def _mp_panel_size(self):
        """计算面板宽高（6 行指标：聚拢度/重叠/边界盒/填充率/目标角点/mod 状态）。"""
        height = (self._MP_TITLE_H + self._MP_PAD * 2 + self._MP_ROW_H * 6)
        return self._MP_WIDTH, height

    def _mp_build_layout(self):
        """根据当前 mp_pos 计算面板矩形。"""
        x, y = self.mp_pos
        width, height = self._mp_panel_size()
        self.mp_panel_rect = pygame.Rect(x, y, width, height)
        self.mp_title_rect = pygame.Rect(x, y, width, self._MP_TITLE_H)
        close_w = 20
        self.mp_close_rect = pygame.Rect(
            x + width - self._MP_PAD - close_w,
            y + (self._MP_TITLE_H - close_w) // 2,
            close_w, close_w,
        )

    def _mp_clamp_position(self):
        """将面板限制在屏幕范围内。"""
        w, h = self._mp_panel_size()
        self.mp_pos[0] = max(0, min(self.mp_pos[0], self.screen_width - w))
        self.mp_pos[1] = max(self.menu_bar_height,
                             min(self.mp_pos[1], self.screen_height - self.status_bar_height - h))

    def _mp_current_metrics(self):
        """实时计算当前游戏状态的聚拢度指标。"""
        from solver.ml.gather_solver import gather_metrics
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return {'score': 0.0, 'overlap': 0, 'bbox': (0, 0), 'fill_rate': 0.0}
        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        return gather_metrics(coords, game.m, game.n)

    # ------------------------------------------------------------------
    # 目標窗口（調試基準）——洞/缺口/凸起與畫出的目標框共用同一窗口
    # ------------------------------------------------------------------
    def _compute_target_region(self):
        """mod-aware 計算「聚攏度最高」的目標窗口。

        先以着色不變量 detect_target_corner 預判約束維度，再在整個
        邊界盒內枚舉 m×n / n×m 窗口，取覆蓋方塊數（= 聚攏度）最高者。
        返回 (r0, c0, (rh, cw)) 或 None。
        """
        from solver.ml.gather_solver import find_best_window, _game_coords
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return None
        step = getattr(self, 'current_step', 1)
        coords = _game_coords(game)
        r0, c0, (rh, cw), _ = find_best_window(coords, game.m, game.n, step)
        self._target_region = (r0, c0, (rh, cw))
        return self._target_region

    def _draw_debug_holes(self):
        """以目標窗口為基準繪製調試標記（與綠色目標框同一窗口）。

        標記規則：
            目標窗口內、被方塊包圍的空格（孔洞）  = 圓圈
            目標窗口內、連通窗口邊緣的空格（缺口）= 三角形
            目標窗口外的方塊（凸起）              = 斜方形（菱形）
        顏色：大孔洞/缺口 = 紅色，小 = 藍色；凸起 = 黃色。
        """
        from solver.ml.hole_detector import detect_holes
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return
        region = getattr(self, '_target_region', None)
        if region is None:
            region = self._compute_target_region()
        if region is None:
            return

        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        step_len = getattr(self, 'current_step', 1)
        holes, protrusions, _ = detect_holes(coords, game.m, game.n, step_len,
                                             region=region)

        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom
        cell_step = scaled_cell + scaled_gap
        half = scaled_cell / 2
        radius = max(3, int(scaled_cell * 0.35))
        line_w = max(2, int(2 * self.zoom))

        def _cell_center(r, c):
            return (c * cell_step + self.camera_x + half,
                    r * cell_step + self.camera_y + half)

        # 目標窗口內的空位：孔洞→圓圈、缺口→三角形
        for h in holes:
            is_selected = (self.selected_hole is not None and
                           set(h['cells']) == set(self.selected_hole.get('cells', [])))
            color = (255, 80, 80) if h['size'] == 'large' else (80, 160, 255)
            for r, c in h['cells']:
                cx, cy = _cell_center(r, c)
                if h['type'] == 'hole':
                    pygame.draw.circle(self.screen, color, (int(cx), int(cy)),
                                       radius, line_w)
                else:  # gap → 三角形
                    pts = [(cx, cy - radius),
                           (cx - radius, cy + radius),
                           (cx + radius, cy + radius)]
                    pygame.draw.polygon(self.screen, color, pts, line_w)
                if is_selected:
                    pygame.draw.circle(self.screen, (255, 255, 255),
                                       (int(cx), int(cy)),
                                       max(2, radius // 2), 0)

        # 目標窗口外的方塊（凸起）→ 斜方形
        for r, c in protrusions:
            cx, cy = _cell_center(r, c)
            d = radius
            pts = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
            pygame.draw.polygon(self.screen, (255, 210, 60), pts, line_w)

    def _draw_target_window(self):
        """繪製目標窗口預告框（無填充、綠色邊框）。

        窗口位置由 _compute_target_region 計算（mod 約束 + 聚攏度最高），
        與 _draw_debug_holes 共用同一 region，保證標記系統與畫框一致。
        """
        region = self._compute_target_region()
        if region is None:
            return None
        r0, c0, (rh, cw) = region

        board_x = getattr(self, '_board_x', 0)
        board_y = getattr(self, '_board_y', 0)
        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom
        cell_step = scaled_cell + scaled_gap
        x = board_x + c0 * cell_step + self.camera_x
        y = board_y + r0 * cell_step + self.camera_y
        w = cw * scaled_cell + (cw - 1) * scaled_gap
        h = rh * scaled_cell + (rh - 1) * scaled_gap
        pygame.draw.rect(self.screen, (80, 220, 100),
                         (int(x), int(y), int(w), int(h)),
                         max(2, int(2 * self.zoom)))
        return region

    def get_hole_at_pos(self, screen_x, screen_y):
        """返回屏幕坐标处的洞（若点击在洞格子上），否则 None。

        與調試面板使用同一個目標窗口，確保可點的洞 = 畫出的標記。
        """
        from solver.ml.hole_detector import detect_holes
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return None
        region = getattr(self, '_target_region', None)
        if region is None:
            region = self._compute_target_region()
        if region is None:
            return None
        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        step_len = getattr(self, 'current_step', 1)
        holes, _, _ = detect_holes(coords, game.m, game.n, step_len, region=region)

        world_x, world_y = self.screen_to_world(screen_x, screen_y)
        cell = self.cell_size + self.gap_width
        for h in holes:
            for r, c in h['cells']:
                bx = c * cell
                by = r * cell
                if bx <= world_x < bx + self.cell_size and by <= world_y < by + self.cell_size:
                    return h
        return None

    def _record_hole_selection(self):
        """保存一条「选洞」训练样本（当前状态洞列表 + 选中洞）。"""
        import os
        import json
        from solver.ml.hole_detector import detect_holes
        game = getattr(self, 'game', None)
        if game is None:
            return
        if self.selected_hole is None:
            self.macro_notify_msg = "未选中洞：先点击棋盘上的一个洞"
            self.macro_notify_timer = 120
            return

        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        region = getattr(self, '_target_region', None)
        if region is None:
            region = self._compute_target_region()
        if region is None:
            return
        holes, protrusions, region = detect_holes(coords, game.m, game.n,
                                                  self.current_step, region=region)

        selected_index = -1
        for i, h in enumerate(holes):
            if set(h['cells']) == set(self.selected_hole.get('cells', [])):
                selected_index = i
                break

        record = {
            'm': game.m,
            'n': game.n,
            'step': self.current_step,
            'region': list(region[0:2]) + list(region[2]),
            'holes': [{
                'type': h['type'],
                'bbox': list(h['bbox']),
                'size': h['size'],
                'n_cells': len(h['cells']),
                'cells': [list(c) for c in h['cells']],
            } for h in holes],
            'protrusions': [list(c) for c in protrusions],
            'selected_hole_index': selected_index,
        }

        out_dir = os.path.join('save', '选洞样本')
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, 'samples.jsonl')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        self.macro_notify_msg = f"已记录选洞样本（第{selected_index}个洞，共{len(holes)}个洞）"
        self.macro_notify_timer = 120

    def draw_metrics_panel(self):
        """绘制聚拢度指标面板。"""
        if not getattr(self, 'show_metrics_panel', False):
            return

        x, y = self.mp_pos
        width, height = self._mp_panel_size()
        self._mp_build_layout()
        mouse_pos = pygame.mouse.get_pos()
        met = self._mp_current_metrics()

        # 半透明背景
        bg = pygame.Surface((width, height), pygame.SRCALPHA)
        bg.fill((40, 40, 48, 235))
        self.screen.blit(bg, (x, y))
        pygame.draw.rect(self.screen, self.colors['dialog_border'],
                         self.mp_panel_rect, 1, border_radius=6)

        # 标题栏
        title_bg = pygame.Surface((width, self._MP_TITLE_H), pygame.SRCALPHA)
        title_bg.fill((60, 60, 72, 235))
        self.screen.blit(title_bg, (x, y))
        title_surface = self.status_font.render("调试面板", True, (220, 220, 220))
        self.screen.blit(title_surface, (
            x + self._MP_PAD,
            y + (self._MP_TITLE_H - title_surface.get_height()) // 2
        ))

        # 关闭按钮 ×
        close_hovered = self.mp_close_rect.collidepoint(mouse_pos)
        close_color = self.colors['button_hover'] if close_hovered else self.colors['button_bg']
        pygame.draw.rect(self.screen, close_color, self.mp_close_rect, border_radius=3)
        close_surface = self.status_font.render("×", True, (255, 255, 255))
        self.screen.blit(close_surface, close_surface.get_rect(center=self.mp_close_rect.center))

        # 指标行（目标框行顯示與畫框同一窗口的實際位置）
        from solver.ml.gather_solver import detect_target_corner, _game_coords
        game = self.game
        step = getattr(self, 'current_step', 1)
        tc = detect_target_corner(_game_coords(game), game.m, game.n, step)
        region = getattr(self, '_target_region', None)
        if region is None:
            region = self._compute_target_region()
        rows = [
            ("聚拢度", f"{met['score'] * 100:.1f}%"),
            ("重叠", f"{met['overlap']}/{game.m * game.n}"),
            ("边界盒", f"{met['bbox'][0]}×{met['bbox'][1]}"),
            ("填充率", f"{met['fill_rate'] * 100:.1f}%"),
            ("目标框", f"({region[0]},{region[1]}) {region[2][0]}×{region[2][1]}"
             if region else "—"),
            ("mod 状态", "有约束" if tc else ("无约束" if step > 1 else "step=1")),
        ]
        row_y = y + self._MP_TITLE_H + self._MP_PAD
        for label, value in rows:
            label_surf = self.status_font.render(label, True, (170, 170, 180))
            value_surf = self.status_font.render(value, True, (240, 240, 240))
            self.screen.blit(label_surf, (x + self._MP_PAD, row_y))
            self.screen.blit(value_surf, (
                x + width - self._MP_PAD - value_surf.get_width(), row_y
            ))
            row_y += self._MP_ROW_H

    def handle_metrics_panel_event(self, event):
        """处理指标面板事件（拖动 + 关闭），返回 True 表示事件已消费。"""
        if not getattr(self, 'show_metrics_panel', False):
            return False

        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self._mp_build_layout()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.mp_panel_rect and self.mp_panel_rect.collidepoint(mx, my):
                if self.mp_close_rect and self.mp_close_rect.collidepoint(mx, my):
                    self.show_metrics_panel = False
                    return True
                if self.mp_title_rect and self.mp_title_rect.collidepoint(mx, my):
                    self.mp_dragging = True
                    self.mp_drag_offset = (mx - self.mp_pos[0], my - self.mp_pos[1])
                    return True
                # 面板空白处：消费事件，避免穿透到地图
                return True

        elif event.type == pygame.MOUSEMOTION:
            if self.mp_dragging:
                self.mp_pos[0] = event.pos[0] - self.mp_drag_offset[0]
                self.mp_pos[1] = event.pos[1] - self.mp_drag_offset[1]
                self._mp_clamp_position()
                return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.mp_dragging:
                self.mp_dragging = False
                return True

        return False
