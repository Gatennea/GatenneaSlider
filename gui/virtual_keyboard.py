# -*- coding: utf-8 -*-
"""
虚拟键盘 Mixin

提供可拖动、独立浮动的虚拟键盘面板：
- 方向键：方形 上/下/左/右；三角形 六向（↖↗ / ←→ / ↙↘）；米字格 八向（3×3 方向盘）
- 编辑键：撤销 / 重做

面板通过标题栏拖动，点击右上角 × 关闭。
"""

import pygame


class VirtualKeyboardMixin:
    """虚拟键盘相关方法（渲染 + 事件处理）"""

    # ---- 布局常量 ----
    _VK_TITLE_H = 26          # 标题栏高度
    _VK_PAD = 8               # 内边距
    _VK_BTN = 44              # 方向键按钮边长
    _VK_BTN_GAP = 6           # 按钮间距
    _VK_ACTION_BTN_W = 62     # 撤销/重做按钮宽度
    _VK_ACTION_BTN_H = 32     # 撤销/重做按钮高度
    _VK_STICKY_W = 54         # 粘滞开关按钮宽度
    _VK_JUMP_H = 30           # “跳到某步”行高
    _VK_JUMP_INPUT_W = 84     # 步数输入框宽度
    _VK_JUMP_BTN_W = 48       # “跳到”按钮宽度

    def _vk_init_state(self):
        """初始化虚拟键盘状态（在 GUI.__init__ 中调用）"""
        self.show_virtual_keyboard = True
        self.vk_pos = [self.screen_width - 200, self.menu_bar_height + 60]
        self.vk_dragging = False
        self.vk_drag_offset = (0, 0)
        self.vk_rects = {}            # action_name -> Rect
        self.vk_title_rect = None
        self.vk_close_rect = None
        self.vk_panel_rect = None
        self.vk_jump_buffer = ''      # “跳到某步”输入缓冲
        self.vk_jump_focus = False    # 输入框是否聚焦
        self.vk_jump_input_rect = None
        self.vk_jump_btn_rect = None
        self.vk_sticky = True     # 粘滞开关：开=撤销/重做连续播放；关=撤销/重做单步

    def _vk_panel_size(self):
        """计算面板宽高"""
        dir_rows = self._vk_direction_rows()
        width = self._VK_PAD * 2 + self._VK_ACTION_BTN_W * 2 + self._VK_STICKY_W + self._VK_BTN_GAP * 2
        height = (self._VK_TITLE_H + self._VK_PAD
                  + self._VK_BTN * dir_rows + self._VK_BTN_GAP * dir_rows
                  + self._VK_ACTION_BTN_H + self._VK_BTN_GAP
                  + self._VK_JUMP_H + self._VK_PAD)
        return width, height

    def _vk_direction_rows(self) -> int:
        """方向键行数：方形 2 行（上 / 左下右）；三角/米字 3 行（六向 / 八向）"""
        if getattr(self, 'mi_mode', False) or getattr(self, 'triangle_mode', False):
            return 3
        return 2

    def _vk_build_triangle_dirs(self, top_row_y, center_x) -> dict:
        """三角形六向：按屏幕方向排三行两列，与键盘 W/E/A/D/Z/X 的六边形对应。"""
        btn, gap = self._VK_BTN, self._VK_BTN_GAP
        left_x = center_x - gap // 2 - btn
        right_x = center_x + gap // 2
        rects = {}
        for row, (left_action, right_action) in enumerate(
                (('move_ul', 'move_ur'), ('move_l', 'move_r'), ('move_dl', 'move_dr'))):
            ry = top_row_y + row * (btn + gap)
            rects[left_action] = pygame.Rect(left_x, ry, btn, btn)
            rects[right_action] = pygame.Rect(right_x, ry, btn, btn)
        return rects

    def _vk_build_mi_dirs(self, top_row_y, center_x) -> dict:
        """米字格八向：3×3 方向盘，正中间留空（没有「不动」这个方向）。

        按键朝向就是屏幕方向：↑=w ↓=s ←=a →=d，四个斜向按米字格两条
        对角缝族排：d1（"\\"）给 ↖=q / ↘=x，d2（"/"）给 ↗=e / ↙=z。
        """
        btn, gap = self._VK_BTN, self._VK_BTN_GAP
        left_x = center_x - btn - gap - btn // 2
        mid_x = center_x - btn // 2
        right_x = center_x + gap + btn // 2
        rows = (
            ('move_ul', 'move_up', 'move_ur'),
            ('move_left', None, 'move_right'),
            ('move_dl', 'move_down', 'move_dr'),
        )
        rects = {}
        for row, actions in enumerate(rows):
            ry = top_row_y + row * (btn + gap)
            for col, action in enumerate(actions):
                if action is None:
                    continue
                rects[action] = pygame.Rect(left_x + col * (btn + gap), ry, btn, btn)
        return rects

    def _vk_build_layout(self):
        """根据当前 vk_pos 计算所有按钮矩形"""
        x, y = self.vk_pos
        width, _ = self._vk_panel_size()
        center_x = x + width // 2

        self.vk_panel_rect = pygame.Rect(x, y, width, self._vk_panel_size()[1])

        # 标题栏
        self.vk_title_rect = pygame.Rect(x, y, width, self._VK_TITLE_H)

        # 关闭按钮
        close_w = 20
        self.vk_close_rect = pygame.Rect(
            x + width - self._VK_PAD - close_w,
            y + (self._VK_TITLE_H - close_w) // 2,
            close_w, close_w
        )

        rects = {}

        # 方向键区（行数随形态变：方形 2 行 / 三角形 3 行 / 米字 3 行）
        top_row_y = y + self._VK_TITLE_H + self._VK_PAD
        if getattr(self, 'mi_mode', False):
            rects.update(self._vk_build_mi_dirs(top_row_y, center_x))
        elif getattr(self, 'triangle_mode', False):
            rects.update(self._vk_build_triangle_dirs(top_row_y, center_x))
        else:
            rects['move_up'] = pygame.Rect(
                center_x - self._VK_BTN // 2, top_row_y,
                self._VK_BTN, self._VK_BTN
            )

            # 方向键：左 / 下 / 右（第2行）
            mid_row_y = top_row_y + self._VK_BTN + self._VK_BTN_GAP
            rects['move_left'] = pygame.Rect(
                center_x - self._VK_BTN - self._VK_BTN_GAP - self._VK_BTN // 2, mid_row_y,
                self._VK_BTN, self._VK_BTN
            )
            rects['move_down'] = pygame.Rect(
                center_x - self._VK_BTN // 2, mid_row_y,
                self._VK_BTN, self._VK_BTN
            )
            rects['move_right'] = pygame.Rect(
                center_x + self._VK_BTN_GAP + self._VK_BTN // 2, mid_row_y,
                self._VK_BTN, self._VK_BTN
            )

        # 粘滞开关 + 撤销 / 重做（方向键区下面一行）
        action_row_y = (top_row_y
                        + (self._VK_BTN + self._VK_BTN_GAP) * self._vk_direction_rows())
        total_action_w = self._VK_STICKY_W + self._VK_ACTION_BTN_W * 2 + self._VK_BTN_GAP * 2
        action_start_x = center_x - total_action_w // 2
        rects['sticky'] = pygame.Rect(
            action_start_x, action_row_y,
            self._VK_STICKY_W, self._VK_ACTION_BTN_H
        )
        rects['undo'] = pygame.Rect(
            action_start_x + self._VK_STICKY_W + self._VK_BTN_GAP, action_row_y,
            self._VK_ACTION_BTN_W, self._VK_ACTION_BTN_H
        )
        rects['redo'] = pygame.Rect(
            action_start_x + self._VK_STICKY_W + self._VK_ACTION_BTN_W + self._VK_BTN_GAP * 2, action_row_y,
            self._VK_ACTION_BTN_W, self._VK_ACTION_BTN_H
        )

        # 跳到某步（第4行）：步数输入框 + “跳到”按钮
        jump_row_y = action_row_y + self._VK_ACTION_BTN_H + self._VK_BTN_GAP
        jump_total_w = self._VK_JUMP_INPUT_W + self._VK_BTN_GAP + self._VK_JUMP_BTN_W
        jump_start_x = center_x - jump_total_w // 2
        self.vk_jump_input_rect = pygame.Rect(
            jump_start_x, jump_row_y,
            self._VK_JUMP_INPUT_W, self._VK_JUMP_H
        )
        self.vk_jump_btn_rect = pygame.Rect(
            jump_start_x + self._VK_JUMP_INPUT_W + self._VK_BTN_GAP, jump_row_y,
            self._VK_JUMP_BTN_W, self._VK_JUMP_H
        )

        self.vk_rects = rects
        return rects

    def _vk_clamp_position(self):
        """将面板限制在屏幕范围内"""
        w, h = self._vk_panel_size()
        self.vk_pos[0] = max(0, min(self.vk_pos[0], self.screen_width - w))
        self.vk_pos[1] = max(self.menu_bar_height,
                             min(self.vk_pos[1], self.screen_height - self.status_bar_height - h))

    def draw_virtual_keyboard(self):
        """绘制虚拟键盘面板"""
        if not getattr(self, 'show_virtual_keyboard', False):
            return

        x, y = self.vk_pos
        width, height = self._vk_panel_size()
        rects = self._vk_build_layout()
        mouse_pos = pygame.mouse.get_pos()

        # 半透明背景
        bg = pygame.Surface((width, height), pygame.SRCALPHA)
        bg.fill((40, 40, 48, 235))
        self.screen.blit(bg, (x, y))
        pygame.draw.rect(self.screen, self.colors['dialog_border'],
                         self.vk_panel_rect, 1, border_radius=6)

        # 标题栏
        title_bg = pygame.Surface((width, self._VK_TITLE_H), pygame.SRCALPHA)
        title_bg.fill((60, 60, 72, 235))
        self.screen.blit(title_bg, (x, y))
        title_surface = self.status_font.render("虚拟键盘", True, (220, 220, 220))
        self.screen.blit(title_surface, (
            x + self._VK_PAD,
            y + (self._VK_TITLE_H - title_surface.get_height()) // 2
        ))

        # 关闭按钮 ×
        close_hovered = self.vk_close_rect.collidepoint(mouse_pos)
        close_color = self.colors['button_hover'] if close_hovered else self.colors['button_bg']
        pygame.draw.rect(self.screen, close_color, self.vk_close_rect, border_radius=3)
        close_surface = self.status_font.render("×", True, (255, 255, 255))
        self.screen.blit(close_surface, close_surface.get_rect(center=self.vk_close_rect.center))

        # 按钮
        if getattr(self, 'mi_mode', False):
            labels = {
                'move_ul': '↖', 'move_up': '↑', 'move_ur': '↗',
                'move_left': '←', 'move_right': '→',
                'move_dl': '↙', 'move_down': '↓', 'move_dr': '↘',
                'sticky': '粘滞', 'undo': '撤销', 'redo': '重做',
            }
        elif getattr(self, 'triangle_mode', False):
            labels = {
                'move_ul': '↖', 'move_ur': '↗',
                'move_l': '←', 'move_r': '→',
                'move_dl': '↙', 'move_dr': '↘',
                'sticky': '粘滞', 'undo': '撤销', 'redo': '重做',
            }
        else:
            labels = {
                'move_up': '↑', 'move_down': '↓',
                'move_left': '←', 'move_right': '→',
                'sticky': '粘滞', 'undo': '撤销', 'redo': '重做',
            }
        for action, rect in rects.items():
            hovered = rect.collidepoint(mouse_pos)
            if action == 'sticky':
                # 粘滞开关：开启时高亮边框提示「连续」状态
                color = self.colors['button_hover'] if (self.vk_sticky or hovered) else self.colors['button_bg']
                pygame.draw.rect(self.screen, color, rect, border_radius=4)
                if self.vk_sticky:
                    pygame.draw.rect(self.screen, (255, 205, 60), rect, 2, border_radius=4)
                text = '粘滞' + ('开' if self.vk_sticky else '关')
                text_surface = self.dialog_font.render(text, True, (255, 255, 255))
                self.screen.blit(text_surface, text_surface.get_rect(center=rect.center))
                continue
            color = self.colors['button_hover'] if hovered else self.colors['button_bg']
            pygame.draw.rect(self.screen, color, rect, border_radius=4)
            text_surface = self.dialog_font.render(labels[action], True, (255, 255, 255))
            self.screen.blit(text_surface, text_surface.get_rect(center=rect.center))

        # 跳到某步：步数输入框 + “跳到”按钮
        input_rect = self.vk_jump_input_rect
        if input_rect:
            draw_text = self.vk_jump_buffer or '步数'
            pygame.draw.rect(self.screen, self.colors['input_bg'], input_rect, border_radius=4)
            border_color = (self.colors['button_hover']
                            if self.vk_jump_focus else self.colors['dialog_border'])
            pygame.draw.rect(self.screen, border_color, input_rect, 1, border_radius=4)
            tcolor = self.colors['input_text'] if self.vk_jump_buffer else (150, 150, 150)
            txt = self.status_font.render(draw_text, True, tcolor)
            self.screen.blit(txt, txt.get_rect(center=input_rect.center))

        btn_rect = self.vk_jump_btn_rect
        if btn_rect:
            hovered = btn_rect.collidepoint(mouse_pos)
            color = self.colors['button_hover'] if hovered else self.colors['button_bg']
            pygame.draw.rect(self.screen, color, btn_rect, border_radius=4)
            btxt = self.dialog_font.render("跳到", True, (255, 255, 255))
            self.screen.blit(btxt, btxt.get_rect(center=btn_rect.center))

    def handle_virtual_keyboard_event(self, event):
        """处理虚拟键盘事件，返回 True 表示事件已消费"""
        if not getattr(self, 'show_virtual_keyboard', False):
            return False

        # 先构建布局（确保矩形已更新到当前位置）
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self._vk_build_layout()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.vk_panel_rect and self.vk_panel_rect.collidepoint(mx, my):
                # 关闭按钮
                if self.vk_close_rect and self.vk_close_rect.collidepoint(mx, my):
                    self.show_virtual_keyboard = False
                    return True
                # 标题栏 → 拖动
                if self.vk_title_rect and self.vk_title_rect.collidepoint(mx, my):
                    self.vk_dragging = True
                    self.vk_drag_offset = (mx - self.vk_pos[0], my - self.vk_pos[1])
                    return True
                # 跳到某步：输入框（获得焦点） / “跳到”按钮
                if self.vk_jump_input_rect and self.vk_jump_input_rect.collidepoint(mx, my):
                    self.vk_jump_focus = True
                    return True
                if self.vk_jump_btn_rect and self.vk_jump_btn_rect.collidepoint(mx, my):
                    self.vk_jump_focus = False
                    self._vk_do_jump()
                    return True
                # 功能按钮
                for action, rect in self.vk_rects.items():
                    if rect.collidepoint(mx, my):
                        self._vk_trigger_action(action)
                        return True
                # 面板空白处：消费事件，避免穿透到地图
                self.vk_jump_focus = False
                return True
            # 点击面板外：输入框失焦（事件仍放行给下方游戏）
            self.vk_jump_focus = False

        elif event.type == pygame.KEYDOWN:
            if not getattr(self, 'vk_jump_focus', False):
                return False
            k = event.key
            if pygame.K_0 <= k <= pygame.K_9:
                if len(self.vk_jump_buffer) < 4:
                    self.vk_jump_buffer += chr(k)
                return True
            if k in (pygame.K_BACKSPACE, pygame.K_DELETE):
                self.vk_jump_buffer = self.vk_jump_buffer[:-1]
                return True
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._vk_do_jump()
                return True
            if k == pygame.K_ESCAPE:
                self.vk_jump_focus = False
                self.vk_jump_buffer = ''
                return True
            # 其他按键：失焦，放行给游戏
            self.vk_jump_focus = False
            return False

        elif event.type == pygame.MOUSEMOTION:
            if self.vk_dragging:
                self.vk_pos[0] = event.pos[0] - self.vk_drag_offset[0]
                self.vk_pos[1] = event.pos[1] - self.vk_drag_offset[1]
                self._vk_clamp_position()
                return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.vk_dragging:
                self.vk_dragging = False
                return True

        return False

    def _vk_trigger_action(self, action):
        """触发虚拟键盘按钮对应的操作"""
        # 教程解法播放中：锁定棋盘操作（撤销/重做/移动/粘滞）
        if self._tut_board_locked():
            return
        if action == 'sticky':
            # 粘滞开关：切换撤销/重做 连续/单步
            self.vk_sticky = not self.vk_sticky
            if not self.vk_sticky:
                # 关闭粘滞时若正在连续播放则停止，保证切换到单步后状态干净
                self._stop_continuous_undo_redo()
            self.macro_notify_msg = "粘滞：连续" if self.vk_sticky else "粘滞：单步"
            self.macro_notify_timer = 90
        elif action == 'undo':
            if self.vk_sticky:
                self._toggle_continuous('undo')
            else:
                self.undo()
        elif action == 'redo':
            if self.vk_sticky:
                self._toggle_continuous('redo')
            else:
                self.redo()
        elif action in ('move_up', 'move_down', 'move_left', 'move_right',
                        'move_ul', 'move_ur', 'move_l', 'move_r',
                        'move_dl', 'move_dr'):
            mi = getattr(self, 'mi_mode', False)
            if mi:
                # 米字格八向與三角形六向的按鍵朝向相同、晶格方向字母不同：
                # ↖ 在米字格是 q（d1 族），三角版才是 w。用錯表的症狀是
                # 選著對角縫按 ↖ 報「方向不匹配」，選著豎直縫則默默走上。
                direction = {
                    'move_up': 'w', 'move_down': 's',
                    'move_left': 'a', 'move_right': 'd',
                    'move_ul': 'q', 'move_ur': 'e',
                    'move_l': 'a', 'move_r': 'd',
                    'move_dl': 'z', 'move_dr': 'x',
                }[action]
            else:
                direction = {
                    'move_up': 'w', 'move_down': 's',
                    'move_left': 'a', 'move_right': 'd',
                    'move_ul': 'w', 'move_ur': 'e',
                    'move_l': 'a', 'move_r': 'd',
                    'move_dl': 'z', 'move_dr': 'x',
                }[action]

            if self.animating:
                self.macro_notify_msg = "动画播放中，无法移动"
                self.macro_notify_timer = 90
                return

            if not self.selected_gap or (not mi and not self.selected_block):
                # 米字格只要先选缝隙：滑块没点过时 _mi_prepare_move 会退回
                # 第一块，方向由按键给定，不必强制二次点选
                self.macro_notify_msg = "请先选中缝隙和滑块" if not mi \
                    else "请先点选缝隙"
                self.macro_notify_timer = 90
                return

            gap_type, _ = self.selected_gap
            # 方向必须与选中缝隙平行：方形 h→a/d、v→w/s；
            # 三角形 h→a/d、p→e/z、n→w/x；米字格 h→a/d、v→w/s、
            # d1→q/x、d2→e/z（全部表驱动，换形态只改表）
            if mi:
                from game_mi import GAP_DIRECTIONS as MI_GAP_DIRECTIONS
                allowed = MI_GAP_DIRECTIONS.get(gap_type, ())
            elif getattr(self, 'triangle_mode', False):
                from game_triangle import GAP_DIRECTIONS
                allowed = GAP_DIRECTIONS.get(gap_type, ())
            else:
                allowed = ('w', 's') if gap_type == 'v' else ('a', 'd')

            if direction in allowed:
                self.move_selected_blocks(direction)
            else:
                self.macro_notify_msg = "移动方向与缝隙方向不匹配"
                self.macro_notify_timer = 90

    def _vk_do_jump(self):
        """虚拟键盘“跳到某步”：输入的数字对应历史记录第 N 步的状态"""
        if self._tut_board_locked():
            return  # 教程解法播放中：锁定棋盘操作
        if not self.vk_jump_buffer:
            self.vk_jump_focus = False
            return
        try:
            target = int(self.vk_jump_buffer)
        except ValueError:
            self.vk_jump_buffer = ''
            self.vk_jump_focus = False
            return
        self.vk_jump_buffer = ''
        self.vk_jump_focus = False

        n = len(self.game_history.history)
        if n == 0 or target < 0:
            return
        if target >= n:
            target = n - 1
            self.macro_notify_msg = f"超出范围，已跳到第 {target} 步"
        else:
            self.macro_notify_msg = f"跳到第 {target} 步"
        self.macro_notify_timer = 90
        self.jump_to_history_index(target)
