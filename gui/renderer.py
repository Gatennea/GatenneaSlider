# -*- coding: utf-8 -*-
"""
渲染相关 Mixin

包含：
- draw_board: 绘制游戏主界面（网格、缝隙、滑块）
- draw_infinite_grid: 绘制无限网格背景
- draw_menu_bar: 绘制顶部菜单栏
- draw_status_bar: 绘制底部状态栏
- draw_right_panel: 绘制右侧动画控制面板
- 各下拉菜单绘制方法
"""

import pygame


class RendererMixin:
    """渲染相关方法 Mixin"""

    def draw_infinite_grid(self):
        """绘制无限网格背景"""
        world_left, world_top = self.screen_to_world(0, 0)
        world_right, world_bottom = self.screen_to_world(
            self.screen_width - self.right_panel_width, self.screen_height)

        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom

        start_col = int(world_left // (scaled_cell + scaled_gap)) - 1
        end_col = int(world_right // (scaled_cell + scaled_gap)) + 2
        start_row = int(world_top // (scaled_cell + scaled_gap)) - 1
        end_row = int(world_bottom // (scaled_cell + scaled_gap)) + 2

        for row in range(start_row, end_row):
            for col in range(start_col, end_col):
                x = col * (scaled_cell + scaled_gap)
                y = row * (scaled_cell + scaled_gap)

                screen_x, screen_y = self.world_to_screen(x, y)

                rect = pygame.Rect(screen_x, screen_y, scaled_cell, scaled_cell)
                pygame.draw.rect(self.screen, self.colors['grid'], rect, 1)

    def draw_board(self):
        """绘制游戏主界面"""
        self.screen.fill(self.colors['background'])

        board_x = 0
        board_y = 0

        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom

        bounds = self.game.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']

        # 绘制选中的横向分割线
        for i in range(min_row, max_row + 2):
            gap_y = board_y + i * (scaled_cell + scaled_gap) - scaled_gap // 2
            screen_gap_y = gap_y + self.camera_y

            if self.selected_gap == ('h', i - 1):
                pygame.draw.line(self.screen, self.colors['line'],
                               (0, screen_gap_y), (self.screen_width, screen_gap_y), 3)

        # 绘制选中的纵向分割线
        for j in range(min_col, max_col + 2):
            gap_x = board_x + j * (scaled_cell + scaled_gap) - scaled_gap // 2
            screen_gap_x = gap_x + self.camera_x

            if self.selected_gap == ('v', j - 1):
                pygame.draw.line(self.screen, self.colors['line'],
                               (screen_gap_x, 0), (screen_gap_x, self.screen_height), 3)

        # 绘制未选中的横向缝隙
        for i in range(min_row, max_row + 2):
            gap_y = board_y + i * (scaled_cell + scaled_gap) - scaled_gap // 2
            screen_gap_y = gap_y + self.camera_y

            board_right = board_x + (max_col - min_col + 1) * (scaled_cell + scaled_gap) + min_col * (scaled_cell + scaled_gap)
            screen_start_x = board_x + min_col * (scaled_cell + scaled_gap) + self.camera_x - 20
            screen_end_x = board_right + self.camera_x + 20

            if self.selected_gap != ('h', i - 1):
                pygame.draw.line(self.screen, self.colors['gap'],
                               (screen_start_x, screen_gap_y),
                               (screen_end_x, screen_gap_y),
                               max(1, int(scaled_gap)))

        # 绘制未选中的纵向缝隙
        for j in range(min_col, max_col + 2):
            gap_x = board_x + j * (scaled_cell + scaled_gap) - scaled_gap // 2
            screen_gap_x = gap_x + self.camera_x

            board_bottom = board_y + (max_row - min_row + 1) * (scaled_cell + scaled_gap) + min_row * (scaled_cell + scaled_gap)
            screen_start_y = board_y + min_row * (scaled_cell + scaled_gap) + self.camera_y - 20
            screen_end_y = board_bottom + self.camera_y + 20

            if self.selected_gap != ('v', j - 1):
                pygame.draw.line(self.screen, self.colors['gap'],
                               (screen_gap_x, screen_start_y),
                               (screen_gap_x, screen_end_y),
                               max(1, int(scaled_gap)))

        # 构建动画方块位置映射（使用统一偏移量，确保整组平移视觉一致）
        anim_map = {}
        if self.animating and self.anim_blocks:
            t = self.ease_out(self.anim_progress)
            dr = self._anim_dr * t
            dc = self._anim_dc * t
            for i, block in enumerate(self.anim_blocks):
                sr, sc = self.anim_start_pos[i]
                anim_map[id(block)] = (sr + dr, sc + dc)

        # 绘制所有滑块
        for block in self.game.blocks:
            if id(block) in anim_map:
                lr, lc = anim_map[id(block)]
                x = board_x + lc * (scaled_cell + scaled_gap)
                y = board_y + lr * (scaled_cell + scaled_gap)
            else:
                x = board_x + block.location[1] * (scaled_cell + scaled_gap)
                y = board_y + block.location[0] * (scaled_cell + scaled_gap)

            screen_x = x + self.camera_x
            screen_y = y + self.camera_y

            if screen_x < -scaled_cell or screen_x > self.screen_width + scaled_cell:
                continue
            if screen_y < -scaled_cell or screen_y > self.screen_height + scaled_cell:
                continue

            if block.be_opted:
                color = self.colors['block_selected']
            else:
                color = self.colors['block']

            rect = pygame.Rect(screen_x, screen_y, scaled_cell, scaled_cell)
            pygame.draw.rect(self.screen, color, rect, border_radius=int(5 * self.zoom))
            pygame.draw.rect(self.screen, self.colors['border'], rect, max(1, int(2 * self.zoom)), border_radius=int(5 * self.zoom))

        # 宏基准位置标记（固定坐标，无论该格有无滑块）
        base = getattr(self, 'macro_record_base_point', None)
        if base is not None:
            br, bc = base
            bx = board_x + bc * (scaled_cell + scaled_gap) + self.camera_x
            by = board_y + br * (scaled_cell + scaled_gap) + self.camera_y
            hl_rect = pygame.Rect(bx - 3, by - 3, scaled_cell + 6, scaled_cell + 6)
            pygame.draw.rect(self.screen, (255, 200, 50), hl_rect, max(1, int(3 * self.zoom)), border_radius=int(5 * self.zoom))

        # 调试面板打开时，在棋盘上画出洞的位置
        if getattr(self, 'show_metrics_panel', False):
            self._draw_debug_holes()

    def draw_menu_bar(self):
        """绘制顶部菜单栏"""
        menu_rect = pygame.Rect(0, 0, self.screen_width, self.menu_bar_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], menu_rect)
        pygame.draw.line(self.screen, self.colors['border'],
                        (0, self.menu_bar_height - 1),
                        (self.screen_width, self.menu_bar_height - 1))

        x_offset = 10
        self.menu_item_rects = []
        for i, item in enumerate(self.menu_items):
            text_surface = self.menu_font.render(item, True, self.colors['menu_text'])
            text_rect = text_surface.get_rect()
            text_rect.x = x_offset
            text_rect.centery = self.menu_bar_height // 2

            item_rect = pygame.Rect(x_offset - 6, 0, text_rect.width + 12, self.menu_bar_height)
            self.menu_item_rects.append(item_rect)

            is_highlighted = (i == self.menu_hovered) or \
                           (i == 0 and self.show_file_menu) or \
                           (i == 1 and self.show_edit_menu) or \
                           (i == 2 and self.show_puzzle_menu) or \
                           (i == 3 and self.show_macro_menu) or \
                           (i == 4 and self.show_settings_menu)
            if is_highlighted:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            self.screen.blit(text_surface, text_rect)
            x_offset += text_rect.width + 20

        if self.show_file_menu:
            self.draw_file_menu()
        if self.show_edit_menu:
            self.draw_edit_menu()
        if self.show_puzzle_menu:
            self.draw_puzzle_menu()
        if self.show_macro_menu:
            self.draw_macro_menu()
        if self.show_settings_menu:
            self.draw_settings_menu()

    def draw_file_menu(self):
        """绘制文件下拉菜单"""
        file_rect = self.menu_item_rects[0]
        menu_x = file_rect.x
        menu_y = self.menu_bar_height

        item_height = 28
        menu_width = 160
        menu_height = item_height * len(self.file_menu_items)

        dropdown_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], dropdown_rect)
        pygame.draw.rect(self.screen, self.colors['border'], dropdown_rect, 1)

        self.file_menu_rects = []
        for i, item in enumerate(self.file_menu_items):
            item_rect = pygame.Rect(menu_x, menu_y + i * item_height, menu_width, item_height)
            self.file_menu_rects.append(item_rect)

            if i == self.file_menu_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            text_surface = self.menu_font.render(item, True, self.colors['menu_text'])
            text_rect = text_surface.get_rect()
            text_rect.x = menu_x + 12
            text_rect.centery = menu_y + i * item_height + item_height // 2
            self.screen.blit(text_surface, text_rect)

    def draw_edit_menu(self):
        """绘制编辑下拉菜单"""
        edit_rect = self.menu_item_rects[1]
        menu_x = edit_rect.x
        menu_y = self.menu_bar_height

        item_height = 28
        menu_width = 160
        menu_height = item_height * len(self.edit_menu_items)

        dropdown_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], dropdown_rect)
        pygame.draw.rect(self.screen, self.colors['border'], dropdown_rect, 1)

        self.edit_menu_rects = []
        for i, item in enumerate(self.edit_menu_items):
            item_rect = pygame.Rect(menu_x, menu_y + i * item_height, menu_width, item_height)
            self.edit_menu_rects.append(item_rect)

            if item == '---':
                pygame.draw.line(self.screen, self.colors['separator'],
                               (menu_x + 8, menu_y + i * item_height + item_height // 2),
                               (menu_x + menu_width - 8, menu_y + i * item_height + item_height // 2))
                continue

            if i == self.edit_menu_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            text_surface = self.menu_font.render(item, True, self.colors['menu_text'])
            text_rect = text_surface.get_rect()
            text_rect.x = menu_x + 12
            text_rect.centery = menu_y + i * item_height + item_height // 2
            self.screen.blit(text_surface, text_rect)

    def draw_puzzle_menu(self):
        """绘制谜题下拉菜单"""
        puzzle_rect = self.menu_item_rects[2]
        menu_x = puzzle_rect.x
        menu_y = self.menu_bar_height

        item_height = 28
        menu_width = 180

        total_items = len(self.puzzle_presets)
        menu_height = item_height * total_items

        dropdown_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], dropdown_rect)
        pygame.draw.rect(self.screen, self.colors['border'], dropdown_rect, 1)

        self.puzzle_menu_rects = []
        for i, preset in enumerate(self.puzzle_presets):
            y_pos = menu_y + i * item_height
            item_rect = pygame.Rect(menu_x, y_pos, menu_width, item_height)
            self.puzzle_menu_rects.append(item_rect)

            if len(preset) == 1 and preset[0] == '---':
                pygame.draw.line(self.screen, self.colors['separator'],
                               (menu_x + 8, y_pos + item_height // 2),
                               (menu_x + menu_width - 8, y_pos + item_height // 2))
                continue

            if i == self.puzzle_menu_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            is_current = False
            if len(preset) == 4:
                _, pm, pn, ps = preset
                if pm == self.current_m and pn == self.current_n and ps == self.current_step:
                    is_current = True
                name = preset[0]
            elif len(preset) == 1 and preset[0] == '__mode__':
                # 计时/练习模式切换项：显示当前模式并打勾
                is_current = True
                name = "计时模式" if self.game_mode == 'timed' else "练习模式"
            else:
                name = preset[0]

            color = self.colors['menu_selected'] if is_current else self.colors['menu_text']
            text_surface = self.menu_font.render(name, True, color)
            text_rect = text_surface.get_rect()
            text_rect.x = menu_x + 12
            text_rect.centery = y_pos + item_height // 2
            self.screen.blit(text_surface, text_rect)

            if is_current:
                check_surface = self.menu_font.render('✓', True, self.colors['menu_selected'])
                check_rect = check_surface.get_rect()
                check_rect.right = menu_x + menu_width - 10
                check_rect.centery = y_pos + item_height // 2
                self.screen.blit(check_surface, check_rect)

    def draw_macro_menu(self):
        """绘制宏定义下拉菜单"""
        macro_rect = self.menu_item_rects[3]  # "宏定义"是第4个菜单项
        menu_x = macro_rect.x
        menu_y = self.menu_bar_height

        item_height = 28
        menu_width = 180

        # 动态构建菜单项
        macro_names = self.macro_manager.list_names()
        items = []
        items.append('管理宏...')
        shortcut = self._format_menu_shortcut('macro_record')
        items.append(f'停止录制 {shortcut}' if self.macro_recording else f'录制宏 {shortcut}')
        items.append('逆序播放：开' if self.macro_reverse_mode else '逆序播放：关')
        items.append('---')  # 分隔线
        for name in macro_names:
            items.append(name)
        if not macro_names:
            items.append('(无已保存的宏)')

        menu_height = item_height * len(items)

        dropdown_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], dropdown_rect)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], dropdown_rect, 1)

        self.macro_menu_rects = []
        for i, item in enumerate(items):
            y_pos = menu_y + i * item_height
            item_rect = pygame.Rect(menu_x, y_pos, menu_width, item_height)
            self.macro_menu_rects.append(item_rect)

            if item == '---':
                pygame.draw.line(self.screen, self.colors['separator'],
                               (menu_x + 8, y_pos + item_height // 2),
                               (menu_x + menu_width - 8, y_pos + item_height // 2))
                continue

            if i == self.macro_menu_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            # 录制中时"停止录制"显示为红色
            if item == '停止录制':
                color = (255, 100, 100)
            elif item == '逆序播放：开':
                color = (255, 200, 50)  # 开启时黄色高亮
            elif item == '(无已保存的宏)':
                color = (130, 130, 130)
            else:
                color = self.colors['menu_text']

            text_surface = self.menu_font.render(item, True, color)
            text_rect = text_surface.get_rect()
            text_rect.x = menu_x + 12
            text_rect.centery = y_pos + item_height // 2
            self.screen.blit(text_surface, text_rect)

    def draw_status_bar(self):
        """绘制底部状态栏"""
        status_y = self.screen_height - self.status_bar_height

        status_rect = pygame.Rect(0, status_y, self.screen_width, self.status_bar_height)
        pygame.draw.rect(self.screen, self.colors['status_bg'], status_rect)
        pygame.draw.line(self.screen, self.colors['border'],
                        (0, status_y), (self.screen_width, status_y))

        text_y = status_y + (self.status_bar_height - 14) // 2

        # 左侧：复原状态
        solved = self.game.is_solved()
        status_text = "状态：复原" if solved else "状态：未复原"
        status_color = self.colors['solved'] if solved else self.colors['unsolved']
        status_surface = self.status_font.render(status_text, True, status_color)
        self.screen.blit(status_surface, (10, text_y))

        # 左侧：步数
        step_text = f"步数：{self.step_count}"
        step_surface = self.status_font.render(step_text, True, self.colors['status_text'])
        step_x = 10 + status_surface.get_width() + 30
        self.screen.blit(step_surface, (step_x, text_y))

        # 左侧：计时器 / 模式（始终显示，颜色随模式与状态变化）
        timer_text = self._timer_status_text()
        if timer_text:
            if self.timer_state == 'running':
                timer_color = (255, 200, 90)
            elif self.timer_state == 'stopped':
                timer_color = self.colors['solved']
            elif self.timer_state == 'dnf':
                timer_color = (255, 90, 90)
            elif self.game_mode == 'practice':
                timer_color = (150, 150, 160)
            else:
                timer_color = (170, 200, 255)
            timer_surface = self.status_font.render(timer_text, True, timer_color)
            timer_x = step_x + step_surface.get_width() + 30
            self.screen.blit(timer_surface, (timer_x, text_y))

        # 中间：当前谜题信息
        puzzle_text = f"谜题：{self.current_step}~{self.current_m}*{self.current_n}"
        puzzle_surface = self.status_font.render(puzzle_text, True, self.colors['status_text'])
        puzzle_x = (self.screen_width - puzzle_surface.get_width()) // 2
        self.screen.blit(puzzle_surface, (puzzle_x, text_y))

        # 右侧：缩放比例
        zoom_text = f"缩放：{int(self.zoom * 100)}%"
        zoom_surface = self.status_font.render(zoom_text, True, self.colors['status_text'])
        zoom_x = self.screen_width - zoom_surface.get_width() - self.right_panel_width - 10
        self.screen.blit(zoom_surface, (zoom_x, text_y))

        # 宏状态指示
        if self.macro_recording:
            macro_text = f"🔴 录制中 ({len(self.macro_recording_steps)}步)"
            macro_color = (255, 80, 80)
            macro_surface = self.status_font.render(macro_text, True, macro_color)
            macro_x = zoom_x - macro_surface.get_width() - 20
            self.screen.blit(macro_surface, (macro_x, text_y))
        elif self.macro_executing:
            macro_text = f"执行宏: {self.macro_exec_name} ({self.macro_exec_index}/{len(self.macro_exec_ops)})"
            macro_color = (100, 200, 255)
            macro_surface = self.status_font.render(macro_text, True, macro_color)
            macro_x = zoom_x - macro_surface.get_width() - 20
            self.screen.blit(macro_surface, (macro_x, text_y))

    def draw_settings_menu(self):
        """绘制设置下拉菜单"""
        settings_rect = self.menu_item_rects[4]  # "设置"是第5个菜单项
        menu_x = settings_rect.x
        menu_y = self.menu_bar_height

        item_height = 28
        menu_width = 140
        menu_height = item_height * len(self.settings_menu_items)

        dropdown_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], dropdown_rect)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], dropdown_rect, 1)

        self.settings_menu_rects = []
        for i, item in enumerate(self.settings_menu_items):
            y_pos = menu_y + i * item_height
            item_rect = pygame.Rect(menu_x, y_pos, menu_width, item_height)
            self.settings_menu_rects.append(item_rect)

            if i == self.settings_menu_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            text_surface = self.menu_font.render(item, True, self.colors['menu_text'])
            text_rect = text_surface.get_rect()
            text_rect.x = menu_x + 12
            text_rect.centery = y_pos + item_height // 2
            self.screen.blit(text_surface, text_rect)

    def draw_settings_dialog(self):
        """绘制设置对话框"""
        # 半透明遮罩
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        # 对话框尺寸
        dialog_width = 500
        dialog_height = 460
        dialog_x = (self.screen_width - dialog_width) // 2
        dialog_y = (self.screen_height - dialog_height) // 2

        # 对话框背景
        dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_width, dialog_height)
        pygame.draw.rect(self.screen, self.colors['dialog_bg'], dialog_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], dialog_rect, 2, border_radius=8)

        # 标题
        title_surface = self.dialog_title_font.render("设置", True, self.colors['dialog_title'])
        self.screen.blit(title_surface, (dialog_x + 20, dialog_y + 15))

        # 分割线
        line_y = dialog_y + 50
        pygame.draw.line(self.screen, self.colors['dialog_border'],
                        (dialog_x + 15, line_y), (dialog_x + dialog_width - 15, line_y))

        # Tab 按钮区域
        tab_y = dialog_y + 58
        tab_height = 30
        tab_width = 90

        # 快捷键设置 Tab
        tab_kb_rect = pygame.Rect(dialog_x + 15, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'keybindings':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_kb_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_kb_rect, border_radius=4)
        tab_kb_text = self.status_font.render("快捷键", True, self.colors['input_text'])
        tab_kb_text_rect = tab_kb_text.get_rect(center=tab_kb_rect.center)
        self.screen.blit(tab_kb_text, tab_kb_text_rect)

        # 动画速度 Tab
        tab_anim_rect = pygame.Rect(dialog_x + 15 + tab_width + 5, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'animation':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_anim_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_anim_rect, border_radius=4)
        tab_anim_text = self.status_font.render("动画速度", True, self.colors['input_text'])
        tab_anim_text_rect = tab_anim_text.get_rect(center=tab_anim_rect.center)
        self.screen.blit(tab_anim_text, tab_anim_text_rect)

        # 求解器 Tab
        tab_solver_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 2, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'solver':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_solver_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_solver_rect, border_radius=4)
        tab_solver_text = self.status_font.render("求解器", True, self.colors['input_text'])
        tab_solver_text_rect = tab_solver_text.get_rect(center=tab_solver_rect.center)
        self.screen.blit(tab_solver_text, tab_solver_text_rect)

        # 存储 tab rect 用于点击检测
        self._settings_tab_kb_rect = tab_kb_rect
        self._settings_tab_anim_rect = tab_anim_rect
        self._settings_tab_solver_rect = tab_solver_rect

        # 内容区域
        content_y = tab_y + tab_height + 10
        content_height = dialog_height - (content_y - dialog_y) - 55

        # 计算总内容高度以决定是否需要滚动条
        total_content_height = self._calc_settings_content_height(content_height)
        max_scroll = max(0, total_content_height - content_height)
        self._settings_max_scroll = max_scroll
        scroll = getattr(self, '_settings_scroll', 0)
        scroll = max(0, min(max_scroll, scroll))
        self._settings_scroll = scroll

        # 内容区域裁剪
        content_rect = pygame.Rect(dialog_x + 5, content_y, dialog_width - 20, content_height)
        self.screen.set_clip(content_rect)
        try:
            if self.settings_active_tab == 'keybindings':
                self._draw_settings_keybindings(dialog_x, content_y - scroll, dialog_width - 30, total_content_height if max_scroll > 0 else content_height)
            elif self.settings_active_tab == 'animation':
                self._draw_settings_animation(dialog_x, content_y, dialog_width - 30, content_height)
            else:
                self._draw_settings_solver(dialog_x, content_y, dialog_width - 30, content_height)
        finally:
            self.screen.set_clip(None)

        # 绘制滚动条
        if max_scroll > 0:
            self._draw_settings_scrollbar(dialog_x + dialog_width - 18, content_y, content_height, scroll, max_scroll)

        # 底部按钮
        btn_width = 80
        btn_height = 32
        btn_y = dialog_y + dialog_height - 48

        # 确定按钮
        ok_btn_x = dialog_x + dialog_width // 2 - btn_width - 10
        self._settings_ok_btn = pygame.Rect(ok_btn_x, btn_y, btn_width, btn_height)
        mouse_pos = pygame.mouse.get_pos()
        btn_color = self.colors['button_hover'] if self._settings_ok_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, self._settings_ok_btn, border_radius=4)
        ok_text = self.input_font.render("确定", True, (255, 255, 255))
        ok_rect = ok_text.get_rect(center=self._settings_ok_btn.center)
        self.screen.blit(ok_text, ok_rect)

        # 取消按钮
        cancel_btn_x = dialog_x + dialog_width // 2 + 10
        self._settings_cancel_btn = pygame.Rect(cancel_btn_x, btn_y, btn_width, btn_height)
        btn_color = self.colors['button_hover'] if self._settings_cancel_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, self._settings_cancel_btn, border_radius=4)
        cancel_text = self.input_font.render("取消", True, (255, 255, 255))
        cancel_rect = cancel_text.get_rect(center=self._settings_cancel_btn.center)
        self.screen.blit(cancel_text, cancel_rect)

        # 恢复默认按钮
        reset_btn_x = dialog_x + 20
        self._settings_reset_btn = pygame.Rect(reset_btn_x, btn_y, btn_width + 10, btn_height)
        btn_color = self.colors['button_hover'] if self._settings_reset_btn.collidepoint(mouse_pos) else (120, 80, 80)
        pygame.draw.rect(self.screen, btn_color, self._settings_reset_btn, border_radius=4)
        reset_text = self.input_font.render("恢复默认", True, (255, 255, 255))
        reset_rect = reset_text.get_rect(center=self._settings_reset_btn.center)
        self.screen.blit(reset_text, reset_rect)

    def _draw_settings_keybindings(self, x, y, width, height):
        """绘制快捷键设置内容"""
        # 存储每个动作的按键区域用于点击检测
        self._settings_key_rects = {}

        row_y = y + 5
        row_height = 28
        key_col_x = x + 230  # 按键显示列的 x 坐标

        for group_name, actions in self.keybinding_groups:
            # 分组标题
            group_surface = self.status_font.render(group_name, True, (100, 200, 255))
            self.screen.blit(group_surface, (x + 10, row_y + 2))
            row_y += row_height

            for action in actions:
                label = self.keybinding_labels.get(action, action)
                label_surface = self.menu_font.render(label, True, self.colors['dialog_text'])
                self.screen.blit(label_surface, (x + 25, row_y + 3))

                # 按键显示区域
                key_text = self._format_keybinding(action)
                key_rect = pygame.Rect(key_col_x, row_y, 200, row_height - 2)
                self._settings_key_rects[action] = key_rect

                # 高亮正在编辑的项
                if self.settings_editing_action == action:
                    pygame.draw.rect(self.screen, self.colors['input_active'], key_rect, border_radius=4)
                    recording_text = self.status_font.render("请按键...", True, (255, 200, 100))
                    text_rect = recording_text.get_rect(center=key_rect.center)
                    self.screen.blit(recording_text, text_rect)
                else:
                    pygame.draw.rect(self.screen, self.colors['input_bg'], key_rect, border_radius=4)
                    key_surface = self.menu_font.render(key_text, True, self.colors['input_text'])
                    text_rect = key_surface.get_rect(center=key_rect.center)
                    self.screen.blit(key_surface, text_rect)

                pygame.draw.rect(self.screen, self.colors['dialog_border'], key_rect, 1, border_radius=4)
                row_y += row_height

            row_y += 5  # 组间距

        # 提示
        hint_text = self.status_font.render("点击按键区域后按任意键修改快捷键", True, (150, 150, 150))
        self.screen.blit(hint_text, (x + 10, y + height - 20))

    def _draw_settings_animation(self, x, y, width, height):
        """绘制动画速度设置内容"""
        # 动画开关
        toggle_y = y + 20
        toggle_label = self.dialog_font.render("启用动画：", True, self.colors['dialog_text'])
        self.screen.blit(toggle_label, (x + 15, toggle_y))

        # 开关按钮
        btn_w = 60
        btn_h = 28
        btn_x = x + 180
        self._settings_anim_toggle_rect = pygame.Rect(btn_x, toggle_y, btn_w, btn_h)

        if self.animation_enabled:
            btn_color = self.colors['button_bg']
            btn_text = "ON"
            text_color = (255, 255, 255)
        else:
            btn_color = self.colors['input_bg']
            btn_text = "OFF"
            text_color = (150, 150, 150)

        pygame.draw.rect(self.screen, btn_color, self._settings_anim_toggle_rect, border_radius=4)
        text_surface = self.status_font.render(btn_text, True, text_color)
        text_rect = text_surface.get_rect(center=self._settings_anim_toggle_rect.center)
        self.screen.blit(text_surface, text_rect)

        # 动画速度滑动条
        speed_y = y + 70
        speed_label = self.dialog_font.render("动画时长：", True, self.colors['dialog_text'])
        self.screen.blit(speed_label, (x + 15, speed_y))

        # 当前值显示
        value_text = f"{self.animation_duration} ms"
        value_surface = self.input_font.render(value_text, True, self.colors['input_text'])
        self.screen.blit(value_surface, (x + 350, speed_y))

        # 滑动条轨道
        track_x = x + 130
        track_y = speed_y + 12
        track_width = 200
        self._settings_slider_track_rect = pygame.Rect(track_x, track_y, track_width, 4)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self._settings_slider_track_rect)

        # 滑动条位置
        normalized = (self.animation_duration - 100) / 900.0
        normalized = max(0.0, min(1.0, normalized))
        knob_x = int(track_x + normalized * track_width)
        self._settings_slider_knob_rect = pygame.Rect(knob_x - 8, track_y - 6, 16, 16)

        knob_color = self.colors['button_hover'] if self._settings_slider_dragging else self.colors['button_bg']
        pygame.draw.rect(self.screen, knob_color, self._settings_slider_knob_rect, border_radius=8)

        # 刻度标签
        min_label = self.status_font.render("100ms", True, (150, 150, 150))
        max_label = self.status_font.render("1000ms", True, (150, 150, 150))
        self.screen.blit(min_label, (track_x, track_y + 20))
        self.screen.blit(max_label, (track_x + track_width - min_label.get_width(), track_y + 20))

    def _draw_settings_solver(self, x, y, width, height):
        """绘制求解器算法选择内容"""
        from solver import SOLVER_ALGORITHMS

        row_y = y + 20
        row_height = 36
        option_x = x + 40  # 选项缩进

        # 标题
        title = self.dialog_font.render("选择求解算法：", True, (100, 200, 255))
        self.screen.blit(title, (x + 15, row_y))
        row_y += row_height + 10

        self._settings_solver_rects = {}  # algorithm_key -> rect

        for algo_key, (algo_name, _) in SOLVER_ALGORITHMS.items():
            # 单选按钮
            radio_size = 12
            radio_x = x + 25
            radio_y = row_y + row_height // 2 - radio_size
            radio_rect = pygame.Rect(radio_x, radio_y, radio_size * 2, radio_size * 2)
            self._settings_solver_rects[algo_key] = pygame.Rect(
                radio_x, row_y, width - 40, row_height
            )

            # 外圈
            pygame.draw.circle(self.screen, self.colors['dialog_border'],
                             (radio_x + radio_size, radio_y + radio_size), radio_size)
            # 选中状态
            if self.solver_algorithm == algo_key:
                pygame.draw.circle(self.screen, self.colors['button_bg'],
                                 (radio_x + radio_size, radio_y + radio_size), radio_size - 4)

            # 算法名
            name_surface = self.dialog_font.render(algo_name, True, self.colors['dialog_text'])
            self.screen.blit(name_surface, (option_x, row_y + row_height // 2 - name_surface.get_height() // 2))

            row_y += row_height

        # 说明文字（自动换行）
        desc_y = y + height - 60
        descriptions = {
            'ida_star': '使用 IDA* 迭代加深搜索，尽量找到最少步数解。速度非常慢。',
            'fast': 'IDA* 优化模式：加大搜索步进，放宽节点/时间限制，优先聚拢，速度中等。不能保证求解成功。',
            'greedy': '贪心爬山法：每步选当前最佳动作，速度中等但不保证最优。不能保证求解成功。',
            'table':'根据数据库的数据快速找到最优算法（一般1s内），只对已有数据库的谜题有效。',
            #'intelligence': 'AI求解：基于预训练评分模型，每步自动选最佳动作。需先用 solver.ml.train_ranker 训练模型。',
            #'emd': 'EMD求解：用 EMD 距离贪心搜索，速度快但不保证成功。',
            #'strategy': '策略求解：EMD 贪心 + 循环检测 + 随机扰动，成功率高于纯 EMD。',
            #'distance': '距离求解：用神经网络预测剩余步数做贪心搜索，需先用 solver.ml.train_distance 训练模型。',
            'gather': '聚拢：提升聚拢度（缩小边界盒、降低EMD），不保证还原，实时显示进展。',
        }
        desc = descriptions.get(self.solver_algorithm, '')
        max_w = width - 20
        wrapped = self._wrap_text(desc, self.status_font, max_w)
        for i, line in enumerate(wrapped):
            line_surf = self.status_font.render(line, True, (160, 160, 160))
            self.screen.blit(line_surf, (x + 15, desc_y + i * 18))

    def _calc_settings_content_height(self, visible_height: int) -> int:
        """计算设置内容的总高度（当前tab）"""
        if self.settings_active_tab == 'keybindings':
            row_height = 28
            groups = self.keybinding_groups
            total = 0
            for group_name, actions in groups:
                total += row_height  # group header
                total += row_height * len(actions)  # action rows
                total += 5  # group spacing
            return total + 25  # extra for hint text
        elif self.settings_active_tab == 'animation':
            return 200  # fixed small content
        else:
            return 250  # solver tab

    def _draw_settings_scrollbar(self, x, y, height, scroll, max_scroll):
        """绘制设置对话框滚动条"""
        # 轨道
        track_w = 8
        track_rect = pygame.Rect(x, y, track_w, height)
        pygame.draw.rect(self.screen, (60, 60, 65), track_rect, border_radius=4)
        self._settings_scrollbar_rect = track_rect

        # 滑块
        if max_scroll > 0:
            ratio = scroll / max_scroll
            knob_h = max(20, int(height * height / (height + max_scroll)))
            knob_y = y + int((height - knob_h) * ratio)
            knob_rect = pygame.Rect(x, knob_y, track_w, knob_h)
            self._settings_scrollbar_knob = knob_rect
            pygame.draw.rect(self.screen, (120, 130, 140), knob_rect, border_radius=4)
        else:
            self._settings_scrollbar_knob = None

    def _wrap_text(self, text: str, font, max_width: int) -> list[str]:
        """自动换行：按给定宽度将文本拆分为多行"""
        if not text:
            return ['']
        lines = []
        current = ''
        for ch in text:
            test = current + ch
            if font.size(test)[0] > max_width:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
        return lines

    def _format_keybinding(self, action):
        """格式化快捷键显示文本"""
        kb = self.keybindings.get(action)
        if not kb:
            return "未设置"

        modifiers = kb.get('modifiers', [])
        key = kb.get('key', '')

        parts = []
        for mod in modifiers:
            if mod == 'ctrl':
                parts.append('Ctrl')
            elif mod == 'alt':
                parts.append('Alt')
            elif mod == 'shift':
                parts.append('Shift')

        # 键名显示映射
        key_display = {
            'space': 'Space',
            'up': '↑',
            'down': '↓',
            'left': '←',
            'right': '→',
            'return': 'Enter',
            'escape': 'Esc',
            'tab': 'Tab',
            'backspace': 'Backspace',
            'delete': 'Delete',
            'home': 'Home',
            'end': 'End',
            'pageup': 'PageUp',
            'pagedown': 'PageDown',
            'insert': 'Insert',
            'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4',
            'f5': 'F5', 'f6': 'F6', 'f7': 'F7', 'f8': 'F8',
            'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
        }
        display_key = key_display.get(key, key.upper() if len(key) == 1 else key)
        parts.append(display_key)

        return '+'.join(parts)

    def draw_macro_manager_dialog(self):
        """绘制宏管理对话框"""
        # 半透明遮罩
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        # 对话框尺寸
        dialog_width = 420
        dialog_height = 360
        dialog_x = (self.screen_width - dialog_width) // 2
        dialog_y = (self.screen_height - dialog_height) // 2
        self.macro_manager_dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_width, dialog_height)

        # 对话框背景
        pygame.draw.rect(self.screen, self.colors['dialog_bg'], self.macro_manager_dialog_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self.macro_manager_dialog_rect, 2, border_radius=8)

        # 标题
        title_surface = self.dialog_title_font.render("宏管理", True, self.colors['dialog_title'])
        self.screen.blit(title_surface, (dialog_x + 20, dialog_y + 15))

        # 分割线
        line_y = dialog_y + 50
        pygame.draw.line(self.screen, self.colors['dialog_border'],
                        (dialog_x + 15, line_y), (dialog_x + dialog_width - 15, line_y))

        # 宏列表区域
        list_y = line_y + 10
        list_x = dialog_x + 15
        list_width = dialog_width - 30
        item_height = 40
        visible_count = self._macro_mgr_visible_count

        macro_names = self.macro_manager.list_names()

        # 滚动按钮
        scroll_btn_size = 24
        scroll_btn_x = list_x + list_width - scroll_btn_size - 2

        self._macro_mgr_scroll_up_rect = pygame.Rect(scroll_btn_x, list_y, scroll_btn_size, scroll_btn_size)
        up_color = self.colors['button_bg'] if self._macro_mgr_scroll > 0 else self.colors['input_bg']
        pygame.draw.rect(self.screen, up_color, self._macro_mgr_scroll_up_rect, border_radius=4)
        up_text = self.status_font.render("▲", True, (255, 255, 255))
        self.screen.blit(up_text, up_text.get_rect(center=self._macro_mgr_scroll_up_rect.center))

        scroll_down_y = list_y + scroll_btn_size + 4 + visible_count * item_height
        self._macro_mgr_scroll_down_rect = pygame.Rect(scroll_btn_x, scroll_down_y, scroll_btn_size, scroll_btn_size)
        can_down = self._macro_mgr_scroll + visible_count < len(macro_names)
        down_color = self.colors['button_bg'] if can_down else self.colors['input_bg']
        pygame.draw.rect(self.screen, down_color, self._macro_mgr_scroll_down_rect, border_radius=4)
        down_text = self.status_font.render("▼", True, (255, 255, 255))
        self.screen.blit(down_text, down_text.get_rect(center=self._macro_mgr_scroll_down_rect.center))

        # 绘制可见的宏条目
        self._macro_mgr_item_rects = []
        visible_names = macro_names[self._macro_mgr_scroll:self._macro_mgr_scroll + visible_count]
        mouse_pos = pygame.mouse.get_pos()
        for i, name in enumerate(visible_names):
            y_pos = list_y + scroll_btn_size + 4 + i * item_height
            item_rect = pygame.Rect(list_x, y_pos, list_width - scroll_btn_size - 6, item_height)

            # 背景
            pygame.draw.rect(self.screen, self.colors['input_bg'], item_rect, border_radius=4)

            # 宏名称
            macro = self.macro_manager.get_macro(name)
            step_count = len(macro.steps) if macro else 0
            label = f"{name}  ({step_count}步)"
            name_surface = self.menu_font.render(label, True, self.colors['dialog_text'])
            name_rect = name_surface.get_rect()
            name_rect.x = item_rect.x + 10
            name_rect.centery = item_rect.centery
            self.screen.blit(name_surface, name_rect)

            # 操作按钮：重命名、删除
            btn_size = 24
            del_btn_x = item_rect.right - btn_size - 6
            del_btn_rect = pygame.Rect(del_btn_x, item_rect.centery - btn_size // 2, btn_size, btn_size)
            del_color = (200, 80, 80) if del_btn_rect.collidepoint(mouse_pos) else (150, 60, 60)
            pygame.draw.rect(self.screen, del_color, del_btn_rect, border_radius=4)
            del_text = self.status_font.render("D", True, (255, 255, 255))
            self.screen.blit(del_text, del_text.get_rect(center=del_btn_rect.center))

            rename_btn_x = del_btn_x - btn_size - 4
            rename_btn_rect = pygame.Rect(rename_btn_x, item_rect.centery - btn_size // 2, btn_size, btn_size)
            rename_color = self.colors['button_hover'] if rename_btn_rect.collidepoint(mouse_pos) else self.colors['button_bg']
            pygame.draw.rect(self.screen, rename_color, rename_btn_rect, border_radius=4)
            rename_text = self.status_font.render("R", True, (255, 255, 255))
            self.screen.blit(rename_text, rename_text.get_rect(center=rename_btn_rect.center))

            # 逆序播放按钮
            inv_btn_x = rename_btn_x - btn_size - 4
            inv_btn_rect = pygame.Rect(inv_btn_x, item_rect.centery - btn_size // 2, btn_size, btn_size)
            inv_color = self.colors['button_hover'] if inv_btn_rect.collidepoint(mouse_pos) else self.colors['button_bg']
            pygame.draw.rect(self.screen, inv_color, inv_btn_rect, border_radius=4)
            inv_text = self.status_font.render("逆", True, (255, 255, 255))
            self.screen.blit(inv_text, inv_text.get_rect(center=inv_btn_rect.center))

            # 逆序按钮悬浮提示
            if inv_btn_rect.collidepoint(mouse_pos):
                tooltip_surface = self.status_font.render("Reverse逆序播放", True, (255, 255, 255))
                tooltip_rect = tooltip_surface.get_rect()
                tooltip_rect.bottomleft = (inv_btn_rect.right + 5, inv_btn_rect.centery)
                pygame.draw.rect(self.screen, (50, 50, 50), tooltip_rect.inflate(8, 4), border_radius=4)
                self.screen.blit(tooltip_surface, tooltip_rect.move(4, 2))

            # 删除按钮悬浮提示
            if del_btn_rect.collidepoint(mouse_pos):
                tooltip_surface = self.status_font.render("Delete删除宏", True, (255, 255, 255))
                tooltip_rect = tooltip_surface.get_rect()
                tooltip_rect.bottomleft = (del_btn_rect.right + 5, del_btn_rect.centery)
                pygame.draw.rect(self.screen, (50, 50, 50), tooltip_rect.inflate(8, 4), border_radius=4)
                self.screen.blit(tooltip_surface, tooltip_rect.move(4, 2))

            # 重命名按钮悬浮提示
            if rename_btn_rect.collidepoint(mouse_pos):
                tooltip_surface = self.status_font.render("Rename重命名", True, (255, 255, 255))
                tooltip_rect = tooltip_surface.get_rect()
                tooltip_rect.bottomleft = (rename_btn_rect.right + 5, rename_btn_rect.centery)
                pygame.draw.rect(self.screen, (50, 50, 50), tooltip_rect.inflate(8, 4), border_radius=4)
                self.screen.blit(tooltip_surface, tooltip_rect.move(4, 2))

            # 存储 rect 用于事件检测
            self._macro_mgr_item_rects.append({
                'row': item_rect,
                'rename': rename_btn_rect,
                'delete': del_btn_rect,
                'inverse': inv_btn_rect,
                'index': self._macro_mgr_scroll + i,
            })

        if not macro_names:
            empty_surface = self.dialog_font.render("暂无保存的宏", True, (130, 130, 130))
            empty_rect = empty_surface.get_rect(center=(list_x + (list_width - scroll_btn_size - 6) // 2,
                                                         list_y + scroll_btn_size + 4 + visible_count * item_height // 2))
            self.screen.blit(empty_surface, empty_rect)

        # 底部关闭按钮
        btn_width = 80
        btn_height = 32
        btn_y = dialog_y + dialog_height - 48
        close_btn_x = dialog_x + (dialog_width - btn_width) // 2
        close_btn = pygame.Rect(close_btn_x, btn_y, btn_width, btn_height)
        btn_color = self.colors['button_hover'] if close_btn.collidepoint(pygame.mouse.get_pos()) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, close_btn, border_radius=4)
        close_text = self.input_font.render("关闭", True, (255, 255, 255))
        self.screen.blit(close_text, close_text.get_rect(center=close_btn.center))
        self._macro_mgr_close_btn = close_btn

    def draw_macro_name_dialog(self):
        """绘制宏命名/重命名对话框"""
        # 半透明遮罩
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        dialog_width = 340
        dialog_height = 160
        dialog_x = (self.screen_width - dialog_width) // 2
        dialog_y = (self.screen_height - dialog_height) // 2
        dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_width, dialog_height)

        pygame.draw.rect(self.screen, self.colors['dialog_bg'], dialog_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], dialog_rect, 2, border_radius=8)

        # 标题
        is_renaming = isinstance(getattr(self, 'macro_renaming_index', None), str) and self.macro_renaming_index
        title = "重命名宏" if is_renaming else "保存宏"
        title_surface = self.dialog_title_font.render(title, True, self.colors['dialog_title'])
        self.screen.blit(title_surface, (dialog_x + 20, dialog_y + 15))

        # 输入框
        input_y = dialog_y + 60
        input_rect = pygame.Rect(dialog_x + 20, input_y, dialog_width - 40, 30)
        bg_color = self.colors['input_active'] if self.macro_name_active else self.colors['input_bg']
        pygame.draw.rect(self.screen, bg_color, input_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], input_rect, 1, border_radius=4)

        self._macro_name_input_rect = input_rect
        
        text_input = getattr(self, 'macro_name_text_input', None)
        if text_input:
            display_text, cursor_visible = text_input.get_display_text(
                self.input_font, input_rect.width - 16, "请输入宏名称...", getattr(self, 'macro_name_active', False)
            )
            text_color = self.colors['input_text'] if text_input.text else (130, 130, 130)
            text_surface = self.input_font.render(display_text, True, text_color)

            # 先绘制选中高亮
            sel_offsets = text_input.get_selection_offsets(self.input_font)
            if sel_offsets is not None:
                s_off, e_off = sel_offsets
                sel_rect = pygame.Rect(input_rect.x + 8 + s_off, input_rect.y + 3,
                                       max(e_off - s_off, 2), input_rect.height - 6)
                pygame.draw.rect(self.screen,
                                 self.colors.get('selection_bg', (50, 80, 160)),
                                 sel_rect)

            # 绘制文本
            self.screen.blit(text_surface, (input_rect.x + 8, input_rect.centery - text_surface.get_height() // 2))
            # 绘制光标
            if getattr(self, 'macro_name_active', False) and cursor_visible:
                cursor_x = input_rect.x + 8 + text_input.get_cursor_offset(self.input_font)
                pygame.draw.line(self.screen, self.colors['input_text'],
                                 (cursor_x, input_rect.y + 4),
                                 (cursor_x, input_rect.bottom - 4), 1)
        else:
            # 降级显示
            display_text = "请输入宏名称..."
            text_surface = self.input_font.render(display_text, True, (130, 130, 130))
            self.screen.blit(text_surface, (input_rect.x + 8, input_rect.centery - text_surface.get_height() // 2))

        # 底部按钮
        btn_width = 70
        btn_height = 28
        btn_y = dialog_y + dialog_height - 45

        ok_btn = pygame.Rect(dialog_x + dialog_width // 2 - btn_width - 10, btn_y, btn_width, btn_height)
        btn_color = self.colors['button_hover'] if ok_btn.collidepoint(pygame.mouse.get_pos()) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, ok_btn, border_radius=4)
        ok_text = self.input_font.render("确定", True, (255, 255, 255))
        self.screen.blit(ok_text, ok_text.get_rect(center=ok_btn.center))
        self._macro_name_ok_btn = ok_btn

        cancel_btn = pygame.Rect(dialog_x + dialog_width // 2 + 10, btn_y, btn_width, btn_height)
        btn_color = self.colors['button_hover'] if cancel_btn.collidepoint(pygame.mouse.get_pos()) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, cancel_btn, border_radius=4)
        cancel_text = self.input_font.render("取消", True, (255, 255, 255))
        self.screen.blit(cancel_text, cancel_text.get_rect(center=cancel_btn.center))
        self._macro_name_cancel_btn = cancel_btn

    def draw_macro_notify(self):
        """绘制宏执行结果通知（右下角浮窗，自动消失）"""
        if getattr(self, 'macro_notify_timer', 0) <= 0:
            return
        msg = getattr(self, 'macro_notify_msg', '')
        if not msg:
            return

        # 渲染文本
        text_surface = self.status_font.render(msg, True, (220, 220, 220))
        text_w = text_surface.get_width()
        text_h = text_surface.get_height()

        pad_x, pad_y = 10, 6
        box_w = text_w + pad_x * 2
        box_h = text_h + pad_y * 2

        # 位于状态栏上方、右侧面板左侧的右下角
        box_x = self.screen_width - self.right_panel_width - box_w - 12
        box_y = self.screen_height - self.status_bar_height - box_h - 8

        # 淡入淡出：持久模式不走淡出，否則前15帧淡入，后30帧淡出
        persistent = getattr(self, 'macro_notify_persistent', False)
        alpha = 220
        timer = self.macro_notify_timer
        if persistent:
            alpha = 220
        elif timer > 150:       # 前10帧淡入 (180→170)
            alpha = int(220 * (180 - timer) / 10.0)
        elif timer < 30:      # 后30帧淡出
            alpha = int(220 * timer / 30.0)
        alpha = max(0, min(220, alpha))

        # 半透明背景
        bg_surface = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        bg_surface.fill((40, 40, 40, alpha))
        pygame.draw.rect(bg_surface, (100, 100, 100, alpha), bg_surface.get_rect(), 1, border_radius=6)
        self.screen.blit(bg_surface, (box_x, box_y))

        # 文本（带透明度）
        text_alpha = max(0, min(255, int(alpha * 255 / 220)))
        text_surf_alpha = pygame.Surface((text_w, text_h), pygame.SRCALPHA)
        # 根据成功/中断选择颜色
        if '执行成功' in msg:
            color = (100, 230, 100, text_alpha)
        else:
            color = (255, 160, 80, text_alpha)
        text_surf_alpha.blit(self.status_font.render(msg, True, color), (0, 0))
        self.screen.blit(text_surf_alpha, (box_x + pad_x, box_y + pad_y))

    def draw_right_panel(self):
        """绘制右侧动画控制面板"""
        panel_x = self.screen_width - self.right_panel_width
        panel_rect = pygame.Rect(panel_x, 0, self.right_panel_width, self.screen_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], panel_rect)
        pygame.draw.line(self.screen, self.colors['border'],
                        (panel_x, 0), (panel_x, self.screen_height))

        track_x = panel_x + self.right_panel_width // 2
        speed_text = self.status_font.render("速度", True, self.colors['status_text'])
        text_rect = speed_text.get_rect(center=(track_x, self.menu_bar_height + 15))
        self.screen.blit(speed_text, text_rect)

        track_top = self.menu_bar_height + 35
        track_bottom = self.screen_height - self.status_bar_height - 55
        track_height = track_bottom - track_top

        if track_height > 0:
            pygame.draw.line(self.screen, self.colors['border'],
                            (track_x, track_top), (track_x, track_bottom), 2)

            normalized = (self.animation_duration - 100) / 900.0
            normalized = max(0.0, min(1.0, normalized))
            knob_y = int(track_top + normalized * track_height)
            self.slider_rect = pygame.Rect(panel_x + 2, track_top, self.right_panel_width - 4, track_height)

            knob_color = self.colors['button_hover'] if self.slider_dragging else self.colors['button_bg']
            self.slider_knob_rect = pygame.Rect(track_x - 10, knob_y - 6, 20, 12)
            pygame.draw.rect(self.screen, knob_color, self.slider_knob_rect, border_radius=4)

        btn_y = self.screen_height - self.status_bar_height - 42
        btn_w = 32
        btn_h = 24
        self.anim_toggle_rect = pygame.Rect(
            panel_x + (self.right_panel_width - btn_w) // 2,
            btn_y, btn_w, btn_h
        )

        if self.animation_enabled:
            btn_color = self.colors['button_bg']
            btn_text = "ON"
            text_color = (255, 255, 255)
        else:
            btn_color = self.colors['input_bg']
            btn_text = "OFF"
            text_color = (150, 150, 150)

        pygame.draw.rect(self.screen, btn_color, self.anim_toggle_rect, border_radius=4)
        text_surface = self.status_font.render(btn_text, True, text_color)
        text_rect = text_surface.get_rect(center=self.anim_toggle_rect.center)
        self.screen.blit(text_surface, text_rect)
