# -*- coding: utf-8 -*-
"""
事件处理 Mixin

处理用户输入事件（鼠标、键盘）和终端命令队列。
"""

import os
import webbrowser
import pygame
import queue
import traceback
from gui.text_input import TextInput
from puzzle_types import puzzle_key

# 米字格在物理键盘上要「认出」的移动类动作名。
# 米字格按冻结决策不给方向键绑定（8 向会用掉 W/A/S/D，与撤销/重做等既有
# 快捷键冲突），这里只用来在按到这些键时给出提示，让玩家改用虚拟键盘。
MI_KEY_ACTIONS = (
    'move_up', 'move_down', 'move_left', 'move_right',
    'tri_up_right', 'tri_down_left', 'tri_down_right',
)


def parse_mi_coord(text: str):
    """命令行座標解析：整數或半整數（米字格錯位態的行/列/縫線都是半的）。

    斜向一格把棋盤錯成半整數座標，此時絳線號、錨點行列都不再是整數，
    終端指令與 HTTP 轉發進來的字串必須兩種都吃得下。解析成 int 或 float
    都不影響與 location 比較（Python 的 1 == 1.0）。認不出回 None。
    """
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return None


class EventsMixin:
    """事件处理相关方法"""
    
    def handle_events(self):
        """处理用户输入事件"""
        for event in pygame.event.get():
            try:
                # 左键单击反馈：先于所有界面分支记录，保证棋盘/菜单/面板/对话框
                # 任意位置的左键单击都有涟漪（不受各分支 continue 影响）
                if (event.type == pygame.MOUSEBUTTONDOWN
                        and getattr(event, 'button', None) == 1):
                    self.spawn_click_feedback(getattr(event, 'pos', None))

                if event.type == pygame.QUIT:
                    self.running = False
                    continue
                
                elif event.type == pygame.VIDEORESIZE:
                    new_width = max(event.w, self.min_width)
                    new_height = max(event.h, self.min_height)
                    self.screen_width = new_width
                    self.screen_height = new_height
                    self.screen = pygame.display.set_mode(
                        (self.screen_width, self.screen_height),
                        pygame.RESIZABLE
                    )
                    continue
                
                # 新手教程：首次启动弹窗（模态，点击按钮消费事件）
                if getattr(self, 'tut_show_prompt', False):
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self._tut_handle_prompt_click(*event.pos):
                            continue
                # 新手教程：教学引导面板（点中按钮消费事件；滚轮/滚动条滚动也消费）
                if getattr(self, 'tutorial_active', False):
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self._tut_handle_panel_click(*event.pos):
                            continue
                    if self._tut_handle_panel_scroll(event):
                        continue

                # 标注/创造模式事件（标注模式含 B/Z/M/S 隐藏入口；其余事件快速放行）
                if self.handle_annotation_event(event):
                    continue

                # 文件对话框事件（最高优先级）
                if self.file_dialog.active:
                    self.file_dialog.handle_event(event)
                    continue

                # 复原成功悬浮窗：Esc 关闭 / Enter 保存 / 点击关闭（其余事件放行）
                if getattr(self, '_solved_popup_active', False):
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self._solved_popup_active = False
                            continue
                        if event.key == pygame.K_RETURN:
                            self._solved_popup_active = False
                            self.save_to_file()
                            continue
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        rect = getattr(self, '_solved_popup_rect', None)
                        if rect and rect.collidepoint(event.pos):
                            self._solved_popup_active = False
                            continue

                # 宏命名对话框事件
                if getattr(self, 'show_macro_name_dialog', False):
                    if self.handle_macro_name_dialog_events(event):
                        continue

                # 宏基准选择模式（录制基准或执行基准）
                if getattr(self, 'macro_selecting_base', False) or \
                   (getattr(self, 'macro_recording', False) and getattr(self, 'macro_record_base_point', None) is None):
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.handle_macro_base_selection_click(*event.pos):
                            continue
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        # ESC 取消宏操作
                        self.macro_recording = False
                        self.macro_recording_steps = []
                        self.macro_record_base_point = None
                        self.macro_executing = False
                        self.macro_selecting_base = False
                        self.macro_exec_ops = []
                        self.macro_notify_persistent = False
                        continue
                    continue  # 拦截所有其他事件

                # 宏执行中（已选好基准，正在逐步播放）：ESC 中止
                if getattr(self, 'macro_executing', False):
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.macro_executing = False
                        self.macro_exec_ops = []
                        self.macro_exec_index = 0
                        self.macro_notify_msg = f'[{self.macro_exec_name}] 已取消'
                        self.macro_notify_timer = 120
                        self.macro_notify_persistent = False
                        continue

                # 宏管理对话框
                if getattr(self, 'show_macro_manager_dialog', False):
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        self.show_macro_manager_dialog = False
                        continue
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self._handle_macro_manager_click(*event.pos):
                            continue
                    continue
                
                # 自定义对话框事件
                if self.show_custom_dialog:
                    self.handle_custom_dialog_events(event)
                    continue
                
                # 帮助对话框
                if self.show_help:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        # 检查滚动条拖动
                        sb_rect = getattr(self, 'help_scrollbar_rect', None)
                        sb_knob = getattr(self, 'help_scrollbar_knob_rect', None)
                        if sb_rect and sb_knob and sb_knob.collidepoint(event.pos):
                            self.help_scrollbar_dragging = True
                            self.help_scrollbar_drag_start_y = event.pos[1] - sb_knob.top
                        elif sb_rect and sb_rect.collidepoint(event.pos):
                            # 点击滚动条空白区域：跳转到对应位置
                            content_height = getattr(self, '_help_content_height', 1)
                            total_content = getattr(self, '_help_total_height', 1)
                            ratio = (event.pos[1] - sb_rect.top) / sb_rect.height
                            max_scroll = max(0, total_content - content_height)
                            self.help_scroll_offset = int(ratio * max_scroll)
                        else:
                            # 点击对话框外部关闭
                            dialog_rect = getattr(self, 'help_dialog_rect', None)
                            if dialog_rect and not dialog_rect.collidepoint(event.pos):
                                self.show_help = False
                            elif not dialog_rect:
                                self.show_help = False
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self.help_scrollbar_dragging = False
                    elif event.type == pygame.MOUSEMOTION:
                        if getattr(self, 'help_scrollbar_dragging', False):
                            sb_rect = getattr(self, 'help_scrollbar_rect', None)
                            if sb_rect:
                                content_height = getattr(self, '_help_content_height', 1)
                                total_content = getattr(self, '_help_total_height', 1)
                                drag_offset = getattr(self, 'help_scrollbar_drag_start_y', 0)
                                rel_y = event.pos[1] - sb_rect.top - drag_offset
                                ratio = max(0, min(1, rel_y / (sb_rect.height - 20)))
                                max_scroll = max(0, total_content - content_height)
                                self.help_scroll_offset = int(ratio * max_scroll)
                    elif event.type == pygame.MOUSEWHEEL:
                        # 滚轮滚动帮助内容
                        self.help_scroll_offset = getattr(self, 'help_scroll_offset', 0) - event.y * 30
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.show_help = False
                        elif event.key == pygame.K_UP:
                            self.help_scroll_offset = getattr(self, 'help_scroll_offset', 0) - 30
                        elif event.key == pygame.K_DOWN:
                            self.help_scroll_offset = getattr(self, 'help_scroll_offset', 0) + 30
                        elif event.key == pygame.K_PAGEUP:
                            self.help_scroll_offset = getattr(self, 'help_scroll_offset', 0) - 200
                        elif event.key == pygame.K_PAGEDOWN:
                            self.help_scroll_offset = getattr(self, 'help_scroll_offset', 0) + 200
                    continue
                
                # 设置对话框事件
                if self.show_settings_dialog:
                    self._handle_settings_dialog_event(event)
                    continue

                # 虚拟键盘事件（浮动面板：拖动 + 按钮点击）
                if self.handle_virtual_keyboard_event(event):
                    continue

                # 聚拢度指标面板事件（浮动面板：拖动 + 关闭）
                if self.handle_metrics_panel_event(event):
                    continue

                # 成绩记录面板事件（浮动面板：拖动/关闭/删除/滚动）
                if self.handle_records_panel_event(event):
                    continue

                # 动画期间阻止游戏键盘输入（但允许撤销/重做/自动求解，及连续播放时的空格打断）
                if self.animating and event.type == pygame.KEYDOWN:
                    if not self._is_action_triggered(event, 'undo') and \
                       not self._is_action_triggered(event, 'redo') and \
                       not self._is_action_triggered(event, 'auto_solve') and \
                       not (event.key == pygame.K_SPACE and
                            (self._continuous_undo or self._continuous_redo)):
                        continue

                # 求解器运行期间阻止用户改動滑塊（只能停止求解）
                if self._auto_solve_running:
                    if event.type == pygame.KEYDOWN:
                        # 允许停止求解
                        if self._is_action_triggered(event, 'auto_solve'):
                            self._start_auto_solve()
                        # 允许开关悬浮面板（只读，不修改滑块）
                        elif self._is_action_triggered(event, 'virtual_keyboard'):
                            self.show_virtual_keyboard = not getattr(self, 'show_virtual_keyboard', False)
                            status = '开' if self.show_virtual_keyboard else '关'
                            self.macro_notify_msg = f"虚拟键盘：{status}"
                            self.macro_notify_timer = 90
                        elif self._is_action_triggered(event, 'metrics_panel'):
                            self.show_metrics_panel = not getattr(self, 'show_metrics_panel', False)
                            status = '开' if self.show_metrics_panel else '关'
                            self.macro_notify_msg = f"调试面板：{status}"
                            self.macro_notify_timer = 90
                        elif self._is_action_triggered(event, 'records_panel'):
                            self.show_records_panel = not getattr(self, 'show_records_panel', False)
                            self.rp_confirm_delete_id = None
                            status = '开' if self.show_records_panel else '关'
                            self.macro_notify_msg = f"成绩面板：{status}"
                            self.macro_notify_timer = 90
                        continue
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        # 允许菜单栏、下拉菜单和右侧面板操作
                        mx, my = event.pos
                        # 检查是否在任何下拉菜单内
                        in_dropdown = False
                        if self.show_file_menu and hasattr(self, 'file_menu_rects'):
                            for rect in self.file_menu_rects:
                                if rect.collidepoint(mx, my):
                                    in_dropdown = True
                                    break
                        if not in_dropdown and self.show_edit_menu and hasattr(self, 'edit_menu_rects'):
                            for rect in self.edit_menu_rects:
                                if rect.collidepoint(mx, my):
                                    in_dropdown = True
                                    break
                        if not in_dropdown and self.show_puzzle_menu and hasattr(self, 'puzzle_menu_rects'):
                            for rect in self.puzzle_menu_rects:
                                if rect.collidepoint(mx, my):
                                    in_dropdown = True
                                    break
                        if not in_dropdown and self.show_macro_menu and hasattr(self, 'macro_menu_rects'):
                            for rect in self.macro_menu_rects:
                                if rect.collidepoint(mx, my):
                                    in_dropdown = True
                                    break
                        if not in_dropdown and self.show_settings_menu and hasattr(self, 'settings_menu_rects'):
                            for rect in self.settings_menu_rects:
                                if rect.collidepoint(mx, my):
                                    in_dropdown = True
                                    break
                        # 如果不在菜单栏、下拉菜单或右侧面板，跳过事件
                        if my >= self.menu_bar_height and mx < self.screen_width - self.right_panel_width and not in_dropdown:
                            continue
                
                # 鼠标移动
                if event.type == pygame.MOUSEMOTION:
                    mx, my = event.pos

                    # 棋盘悬停格（连锁提示用；含空格，越界置空）
                    self.hover_cell = None
                    if getattr(self, 'chain_hint_enabled', False) \
                            and not getattr(self, 'mi_mode', False):
                        try:
                            # 注意：shuffle 后棋盘坐标可为负，用 bounds 判定而非 0 起索引
                            b = self.game.get_boundaries()
                            if getattr(self, 'triangle_mode', False):
                                # 三角形：悬停的是单位三角 (i, j, up)，取 (i, j) 参与 mod 判定
                                wx, wy = self.screen_to_world(mx, my)
                                cell = self._tri_view().world_to_cell(wx, wy)
                                if cell is not None:
                                    c = (cell[0], cell[1])
                                else:
                                    c = None
                            else:
                                c = self.get_cell_at_pos(mx, my)
                            if c is not None and (
                                b['min_row'] - 1 <= c[0] <= b['max_row'] + 1 and
                                b['min_col'] - 1 <= c[1] <= b['max_col'] + 1
                            ):
                                self.hover_cell = c
                        except Exception:
                            self.hover_cell = None

                    # 菜单栏悬停
                    self.menu_hovered = -1
                    if my < self.menu_bar_height:
                        for i, rect in enumerate(self.menu_item_rects):
                            if rect.collidepoint(mx, my):
                                self.menu_hovered = i
                                break
                    
                    # 文件菜单悬停
                    self.file_menu_hovered = -1
                    if self.show_file_menu:
                        for i, rect in enumerate(self.file_menu_rects):
                            if rect.collidepoint(mx, my):
                                self.file_menu_hovered = i
                                break
                    
                    # 编辑菜单悬停
                    self.edit_menu_hovered = -1
                    if self.show_edit_menu:
                        for i, rect in enumerate(self.edit_menu_rects):
                            if rect.collidepoint(mx, my):
                                if self.edit_menu_items[i] != '---':
                                    self.edit_menu_hovered = i
                                break
                    
                    # 谜题菜单悬停
                    self.puzzle_menu_hovered = -1
                    if self.show_puzzle_menu:
                        for i, rect in enumerate(self.puzzle_menu_rects):
                            if rect.collidepoint(mx, my):
                                preset = self.puzzle_presets[i]
                                if not (len(preset) == 1 and preset[0] == '---'):
                                    self.puzzle_menu_hovered = i
                                break
                    
                    # 宏定义菜单悬停
                    self.macro_menu_hovered = -1
                    if self.show_macro_menu:
                        for i, rect in enumerate(self.macro_menu_rects):
                            if rect.collidepoint(mx, my):
                                self.macro_menu_hovered = i
                                break

                    # 设置菜单悬停
                    self.settings_menu_hovered = -1
                    if self.show_settings_menu:
                        for i, rect in enumerate(self.settings_menu_rects):
                            if rect.collidepoint(mx, my):
                                self.settings_menu_hovered = i
                                break

                    # 滑动条拖拽（缩放/速度）
                    if getattr(self, 'zoom_slider_dragging', False):
                        self._update_zoom_slider_from_mouse(my)
                    elif self.slider_dragging:
                        self._update_slider_from_mouse(my)
                    
                    # 拖拽地图
                    if self.is_dragging:
                        dx = event.pos[0] - self.drag_start[0]
                        dy = event.pos[1] - self.drag_start[1]
                        self.camera_x = self.drag_offset[0] + dx
                        self.camera_y = self.drag_offset[1] + dy

                    # 拖拽滑动：累计位移（超过阈值才标记为拖拽，避免与点击冲突）
                    if self._mouse_drag_state is not None and not self.is_dragging:
                        st = self._mouse_drag_state
                        st['dx'] = event.pos[0] - st['sx']
                        st['dy'] = event.pos[1] - st['sy']
                        th = getattr(self, 'drag_threshold', 14)
                        if abs(st['dx']) >= th or abs(st['dy']) >= th:
                            # 首次超过阈值：进入跟随状态
                            if not st.get('follow_active'):
                                st['follow_active'] = True
                                block = st.get('block')
                                if block is not None and self._init_drag_follow(block, st['dx'], st['dy']):
                                    st['follow_active'] = True
                                    self.drag_follow_start_screen = (st['sx'], st['sy'])
                                else:
                                    # 跟随初始化失败：回退到旧路径
                                    st['follow_active'] = False
                                    st['moved'] = True
                        # 跟随中：每帧更新偏移（不受阈值限制——拖回起点附近时位移会小于阈值，
                        # 若受阈值门控，偏移会冻结在旧值，导致松手后仍按旧偏移移动）
                        if self.drag_following:
                            cell_px = self.cell_size + self.gap_width
                            px_dx = event.pos[0] - self.drag_follow_start_screen[0]
                            px_dy = event.pos[1] - self.drag_follow_start_screen[1]
                            max_cells = getattr(self, 'drag_follow_max_cells', 0)
                            if getattr(self, 'triangle_mode', False):
                                # 三角：把螢幕位移投影到鎖定方向的單位向量上，得到沿該
                                # 晶格方向走了幾格；再換算回斜座標 (di, dj) 偏移
                                from game_triangle import DIRECTIONS, DIRECTION_SCREEN
                                sx, sy = DIRECTION_SCREEN[self.drag_follow_direction]
                                scale = cell_px * self.zoom
                                proj = (px_dx * sx + px_dy * sy) / scale
                                clamped = max(0.0, min(proj, float(max_cells)))
                                di, dj = DIRECTIONS[self.drag_follow_direction]
                                self.drag_follow_offset = (di * clamped, dj * clamped)
                                # 觸點越過可達上限 → 提示不可繼續（容差 0.05 格覆蓋像素取整誤差）
                                self.drag_follow_invalid = (proj > max_cells + 0.05)
                            else:
                                dc = px_dx / (cell_px * self.zoom)
                                dr = px_dy / (cell_px * self.zoom)
                                # 沿主方向轴取屏幕位移分量
                                gap_type = self.drag_follow_gap[0] if self.drag_follow_gap else 'h'
                                raw = dc if gap_type == 'h' else dr
                                # 投影到锁定方向的「前进」轴上：'d'/'s' 是屏幕正方向，'a'/'w' 是屏幕负方向。
                                # 方向在 _init_drag_follow 时已锁定，故必须乘方向符号；否则上/左拖拽
                                # （屏幕位移为负）会被下面的夹紧吃掉，表现为「完全无法上下/向左拖动」。
                                forward = raw if self.drag_follow_direction in ('d', 's') else -raw
                                # 夹紧：反向拖回起点后停在原位；向前不超过可达上限
                                clamped = max(0.0, min(forward, float(max_cells)))
                                if self.drag_follow_direction == 'd':
                                    self.drag_follow_offset = (0.0, clamped)
                                elif self.drag_follow_direction == 'a':
                                    self.drag_follow_offset = (0.0, -clamped)
                                elif self.drag_follow_direction == 's':
                                    self.drag_follow_offset = (clamped, 0.0)
                                else:  # 'w'
                                    self.drag_follow_offset = (-clamped, 0.0)
                                # 触点越过可达上限 → 提示不可继续
                                # 容差 0.05 格：覆盖像素取整误差（1px ≈ 0.016 格），恰好贴边时不误报
                                self.drag_follow_invalid = (forward > max_cells + 0.05)
                
                # 鼠标点击
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    x, y = event.pos
                    
                    if event.button == 1:
                        # 文件菜单项点击
                        if self.show_file_menu:
                            file_clicked = False
                            for i, rect in enumerate(self.file_menu_rects):
                                if rect.collidepoint(x, y):
                                    if i == 0:
                                        self.load_from_file()
                                    elif i == 1:
                                        self.save_to_file()
                                    elif i == 2:
                                        self.save_as()
                                    file_clicked = True
                                    break
                            self.close_all_menus()
                            if file_clicked:
                                continue
                        
                        # 编辑菜单项点击
                        if self.show_edit_menu:
                            edit_clicked = False
                            for i, rect in enumerate(self.edit_menu_rects):
                                if rect.collidepoint(x, y):
                                    if self.edit_menu_items[i] == '---':
                                        continue
                                    if i == 0:
                                        self.undo()
                                    elif i == 1:
                                        self.redo()
                                    elif i == 2:
                                        self.shuffle_puzzle()
                                    elif i == 3:
                                        self.reset_puzzle()
                                    elif i == 5:
                                        self._start_auto_solve()
                                    edit_clicked = True
                                    break
                            self.close_all_menus()
                            if edit_clicked:
                                continue
                        
                        # 谜题菜单项点击
                        if self.show_puzzle_menu:
                            puzzle_clicked = False
                            puzzle_keep_open = False
                            for i, rect in enumerate(self.puzzle_menu_rects):
                                if rect.collidepoint(x, y):
                                    preset = self.puzzle_presets[i]
                                    if ((len(preset) == 1 and preset[0] == '__current__')
                                            or (len(preset) == 2
                                                and preset[0] == '__group__')):
                                        # 分组标题和底部状态行：点了不该关掉菜单
                                        puzzle_keep_open = True
                                    elif len(preset) == 1 and preset[0] == '自定义...':
                                        self.show_custom_dialog = True
                                        kind = self._current_kind()
                                        self.custom_kind = ('triangle' if kind == 'triangle'
                                                            else 'mi' if kind == 'mi'
                                                            else 'numbered' if kind == 'numbered'
                                                            else 'rect')
                                        self.custom_fields = {
                                            'm': str(self.current_m),
                                            'n': str(self.current_n),
                                            'step': str(self.current_step)
                                        }
                                        self.custom_active_field = 'm'
                                        self.custom_error = ''
                                        puzzle_clicked = True
                                    elif len(preset) >= 4:
                                        _, pm, pn, ps = preset[:4]
                                        kind = preset[4] if len(preset) > 4 else 'square'
                                        if kind == 'triangle':
                                            self.new_triangle_puzzle(pm, ps)
                                        elif kind == 'mi':
                                            self.new_mi_puzzle(pm, pn, ps)
                                        elif kind == 'numbered':
                                            self.new_puzzle(pm, pn, ps, numbered=True)
                                        else:
                                            self.new_puzzle(pm, pn, ps)
                                        puzzle_clicked = True
                                    break
                            if puzzle_keep_open:
                                continue
                            self.close_all_menus()
                            if puzzle_clicked:
                                continue

                        # 宏定义菜单项点击
                        if self.show_macro_menu:
                            macro_clicked = False
                            for i, rect in enumerate(self.macro_menu_rects):
                                if rect.collidepoint(x, y):
                                    macro_clicked = True
                                    self._handle_macro_menu_click(i)
                                    break
                            self.close_all_menus()
                            if macro_clicked:
                                continue

                        # 菜单栏点击
                        if y < self.menu_bar_height:
                            for i, rect in enumerate(self.menu_item_rects):
                                if rect.collidepoint(x, y):
                                    if self.menu_items[i] == '帮助':
                                        self.close_all_menus()
                                        self.show_help = True
                                        self.help_scroll_offset = 0
                                    elif self.menu_items[i] == '文件':
                                        self.show_edit_menu = False
                                        self.show_puzzle_menu = False
                                        self.show_settings_menu = False
                                        self.show_macro_menu = False
                                        self.show_file_menu = not self.show_file_menu
                                    elif self.menu_items[i] == '编辑':
                                        self.show_file_menu = False
                                        self.show_puzzle_menu = False
                                        self.show_settings_menu = False
                                        self.show_macro_menu = False
                                        self.show_edit_menu = not self.show_edit_menu
                                    elif self.menu_items[i] == '谜题':
                                        self.show_file_menu = False
                                        self.show_edit_menu = False
                                        self.show_settings_menu = False
                                        self.show_macro_menu = False
                                        self.show_puzzle_menu = not self.show_puzzle_menu
                                    elif self.menu_items[i] == '宏定义':
                                        self.show_file_menu = False
                                        self.show_edit_menu = False
                                        self.show_puzzle_menu = False
                                        self.show_settings_menu = False
                                        self.show_macro_menu = not self.show_macro_menu
                                    elif self.menu_items[i] == '设置':
                                        self.close_all_menus()
                                        self.show_settings_dialog = True
                                        self.settings_active_tab = 'keybindings'
                                        self.settings_editing_action = None
                                        self._settings_scroll = 0
                                        self._settings_backup_keybindings = dict(self.keybindings)
                                        self._settings_backup_gather = dict(self.gather_params)
                                        self._settings_backup_gather_enabled = dict(self.gather_enabled)
                                    elif self.menu_items[i] == '教程':
                                        # “帮助”右侧：新手教程入口（开始/继续/回顾）
                                        self.close_all_menus()
                                        self._tut_start()
                                    elif self.menu_items[i] == '官网':
                                        # 用默认浏览器打开 Web 版主页
                                        self.close_all_menus()
                                        webbrowser.open('https://gatennea.github.io/GatenneaSliderWeb/')
                                    else:
                                        self.close_all_menus()
                                    break
                            continue
                        else:
                            self.close_all_menus()
                        
                        # 右侧面板点击：5 个快捷开关 / 缩放滑条 / 速度滑条
                        if x >= self.screen_width - self.right_panel_width:
                            switches = getattr(self, 'right_panel_switch_rects', {})
                            sw_clicked = None
                            for skey, srect in switches.items():
                                if srect.collidepoint(x, y):
                                    sw_clicked = skey
                                    break
                            if sw_clicked:
                                self._handle_right_panel_switch(sw_clicked)
                            elif getattr(self, 'zoom_slider_rect', None) and self.zoom_slider_rect.collidepoint(x, y):
                                self.zoom_slider_dragging = True
                                self._update_zoom_slider_from_mouse(y)
                            elif self.slider_rect and self.slider_rect.collidepoint(x, y):
                                self.slider_dragging = True
                                self._update_slider_from_mouse(y)
                            continue
                        
                        # 状态栏区域
                        if y > self.screen_height - self.status_bar_height:
                            continue
                        
                        # 游戏区域点击
                        # 教程解法播放中：锁定棋盘操作（点选缝隙/滑块、拖拽滑动）
                        if self._tut_board_locked():
                            gap = block = None
                        elif getattr(self, 'mi_mode', False):
                            # 米字格两次触控：第一下点缝隙、第二下点滑块提交。
                            # 缝隙与滑块都要 editable（走与方形/三角相同的
                            # gap_at/block_at 命中），差别只在第二下触控的
                            # 定向——由两下的世界位移投影到缝隙切向定方向。
                            gap = self.get_gap_at_pos(x, y)
                            block = self.get_block_at_pos(x, y)
                        else:
                            gap = self.get_gap_at_pos(x, y)
                            block = self.get_block_at_pos(x, y)

                        # 控制模式开关（独立布尔，可任意组合）
                        two_touch_on = getattr(self, 'control_two_touch', True)
                        mouse_kb_on = getattr(self, 'control_mouse_kb', True)
                        # 可选中：鼠标键盘模式也需要通过点击选中缝隙/滑块组，否则方向键无物可移
                        selectable = two_touch_on or mouse_kb_on

                        # 拖拽滑动：记录起点（按下滑块时记录；最终由 MOUSEBUTTONUP 判定点击/拖拽）
                        # 单次/两次触控都关闭时拖拽无意义，不记录起点，避免残留中间态
                        # 米字格禁拖拽，连起点都不记（否则松手会走 _drag_slide 的
                        # 8 区角度路径，把三坐标滑块当成两坐标解包）
                        if block is not None and not getattr(self, 'mi_mode', False) \
                                and not self._readonly_blocked() and \
                                (getattr(self, 'control_single_touch', True) or two_touch_on):
                            self._mouse_drag_state = {
                                'sx': x, 'sy': y, 'block': block, 'moved': False,
                            }

                        if gap is not None:
                            # 跟随中点击缝隙 → 清除跟随，不执行移动
                            if self.drag_following:
                                self.clear_drag_follow()
                            if selectable:
                                # 选中变化 → 结束上一次选中会话（后续移动另起快照）
                                self._bump_move_session()
                                if self.selected_gap == gap:
                                    self.selected_gap = None
                                    if getattr(self, 'mi_mode', False):
                                        self._mi_gap_point = None
                                else:
                                    self.selected_gap = gap
                                    for b in self.game.blocks:
                                        b.be_opted = False
                                    self.selected_block = None
                                    # 米字格：记下第一下触控的落点（世界坐标），
                                    # 第二下触控用它算偏移、投影到切向定方向
                                    if getattr(self, 'mi_mode', False):
                                        self._mi_gap_point = self.screen_to_world(x, y)
                                    # 操作提示：选中缝隙
                                    gap_type, line = gap
                                    self.macro_notify_msg = (
                                        f"选中{self._gap_type_name(gap_type)}缝隙")
                                    self.macro_notify_timer = 120
                                    # 新手教程：步骤1 选中缝隙 → 步骤2
                                    self._tut_on_gap_clicked()
                            # 不可选中（两次触控+鼠标键盘都关）：吞掉点击，不选中、不平移
                        elif getattr(self, 'mi_mode', False) and block is not None \
                                and self.selected_gap is not None and selectable:
                            # 米字格第二下触控：选组 + 定向 + 提交一次到位。
                            # 方向只由「第二下 − 第一下」在缝隙切向上的符号决定，
                            # 法向只做校验（点的块必须与偏移同侧）。
                            if self.drag_following:
                                self.clear_drag_follow()
                            self._bump_move_session()
                            gap_type, line = self.selected_gap
                            self.game.opt(gap_type, line, block)
                            self.selected_block = block
                            anchor = getattr(self, '_mi_gap_point', None)
                            if anchor is None:
                                # 缝隙不是这一回合点出来的（读档恢复选中/HTTP 选中）：
                                # 没有参考点就无法定向，先只选组，等虚拟键盘给方向
                                n_blocks = len(
                                    [b for b in self.game.blocks if b.be_opted])
                                self.macro_notify_msg = (
                                    f"选中滑块组 共{n_blocks}个"
                                    "（用虚拟键盘给方向）")
                                self.macro_notify_timer = 120
                            else:
                                wx, wy = self.screen_to_world(x, y)
                                direction = self._mi_tap_direction(
                                    gap_type, line, block, (wx - anchor[0], wy - anchor[1]))
                                if direction is not None:
                                    # 动画播放中：上一手还没落地，这一手只选组
                                    # 不提交，否则会把正在播的动画整组替换掉
                                    # （起点被改写、上一手被丢掉）。虚拟键盘
                                    # 同样在动画期间拒绝移动
                                    if self.animating:
                                        self.macro_notify_msg = "动画播放中，无法移动"
                                        self.macro_notify_timer = 90
                                    else:
                                        self.move_selected_blocks(direction)
                            # 第一下的落點只服務這一次第二下：用掉就清。否則選中態
                            # 會一直留著，之後每次單擊滑塊都拿這個舊錨點重新定向，
                            # 出現「只是點了幾下、滑塊自己滑走了」的幽靈移動。
                            self._mi_gap_point = None
                        elif block is not None and self.selected_gap is not None and selectable:
                            # 跟随中点击滑块 → 清除跟随
                            if self.drag_following:
                                self.clear_drag_follow()
                            # 重新选中滑块组 → 结束上一次选中会话（后续移动另起快照）
                            self._bump_move_session()
                            direction, line = self.selected_gap
                            self.game.opt(direction, line, block)
                            self.selected_block = block
                            # 操作提示：选中滑块组
                            n_blocks = len([b for b in self.game.blocks if b.be_opted])
                            self.macro_notify_msg = f"选中滑块组 共{n_blocks}个"
                            self.macro_notify_timer = 120
                            # 新手教程：步骤2 选中滑块组 → 步骤3
                            self._tut_on_block_clicked()
                        elif self.is_blank_area(x, y):
                            # 跟随中点击空白 → 清除跟随，允许平移地图
                            if self.drag_following:
                                self.clear_drag_follow()
                            # 调试面板打开时，点击洞选中（标记学习）
                            if getattr(self, 'show_metrics_panel', False):
                                hole = self.get_hole_at_pos(x, y)
                                if hole is not None:
                                    if (self.selected_hole is not None and
                                            set(hole['cells']) == set(self.selected_hole.get('cells', []))):
                                        # 再点一次已选中的洞 = 取消选中
                                        self.selected_hole = None
                                        self.macro_notify_msg = "已取消选中洞"
                                    else:
                                        self.selected_hole = hole
                                        self.macro_notify_msg = f"选中洞：{hole['type']} {hole['size']}（{len(hole['cells'])}格）"
                                    self.macro_notify_timer = 120
                                    continue
                            self.is_dragging = True
                            self.drag_start = (x, y)
                            self.drag_offset = (self.camera_x, self.camera_y)
                    
                    elif event.button == 3:
                        # 右键取消选中
                        if self.drag_following:
                            self.clear_drag_follow()
                        self._bump_move_session()
                        self.selected_gap = None
                        self.selected_block = None
                        self._mi_gap_point = None
                        for b in self.game.blocks:
                            b.be_opted = False
                        self.macro_notify_msg = "已取消选中"
                        self.macro_notify_timer = 90
                
                # 鼠标释放
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        # 拖拽滑动判定：按下过滑块且位移超过阈值 → 执行一次拖拽滑动
                        if self._mouse_drag_state is not None:
                            st = self._mouse_drag_state
                            self._mouse_drag_state = None
                            # 跟随模式由 _commit_drag_move 处理，不走旧路径
                            if not self.drag_following:
                                if st.get('moved') and st.get('block') is not None:
                                    self._drag_slide(st['block'], st.get('dx', 0), st.get('dy', 0))
                            # 跟随模式释放：提交移动
                            if self.drag_following:
                                self._commit_drag_move()
                        self.is_dragging = False
                        self.slider_dragging = False
                        self.zoom_slider_dragging = False
                
                # 鼠标滚轮
                elif event.type == pygame.MOUSEWHEEL:
                    if pygame.key.get_mods() & pygame.KMOD_CTRL:
                        zoom_factor = 1.1 if event.y > 0 else 0.9
                        new_zoom = self.zoom * zoom_factor
                        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
                        
                        mouse_x, mouse_y = pygame.mouse.get_pos()
                        # 记录缩放前鼠标指向的世界坐标
                        world_x = (mouse_x - self.camera_x) / self.zoom
                        world_y = (mouse_y - self.camera_y) / self.zoom

                        self.zoom = new_zoom

                        # 反推新 camera，使同一世界点仍位于鼠标下方（以鼠标为中心缩放）
                        self.camera_x = mouse_x - world_x * self.zoom
                        self.camera_y = mouse_y - world_y * self.zoom
                
                # 键盘事件
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        # 连续撤销/重做播放中：空格 = 打断
                        if self._space_interrupts_continuous():
                            continue
                        # 空格作为计时器开始/DNF 键
                        self._timer_on_space()
                        continue
                    if event.key == pygame.K_RETURN and getattr(self, 'show_metrics_panel', False):
                        self._record_hole_selection()
                    elif self._is_action_triggered(event, 'save'):
                        self.save_to_file()
                    
                    elif self._is_action_triggered(event, 'load'):
                        self.load_from_file()
                    
                    elif self._is_action_triggered(event, 'undo') and not self._tut_board_locked():
                        self.undo()
                        self.undo_held = True
                        self.undo_first = True
                        self.undo_timer = pygame.time.get_ticks()
                    
                    elif self._is_action_triggered(event, 'redo') and not self._tut_board_locked():
                        self.redo()
                        self.redo_held = True
                        self.redo_first = True
                        self.redo_timer = pygame.time.get_ticks()
                    
                    elif self._is_action_triggered(event, 'shuffle') and not self._tut_board_locked():
                        self.shuffle_puzzle()
                    
                    elif self._is_action_triggered(event, 'reset') and not self._tut_board_locked():
                        self.reset_puzzle()
                    
                    elif self._is_action_triggered(event, 'auto_solve') and not self._tut_board_locked():
                        self._start_auto_solve()
                    
                    elif self._is_action_triggered(event, 'macro_record'):
                        if self.macro_recording:
                            self._stop_macro_recording()
                        else:
                            self._start_macro_recording()
                    
                    elif self._is_action_triggered(event, 'virtual_keyboard'):
                        self.show_virtual_keyboard = not getattr(self, 'show_virtual_keyboard', False)
                        status = '开' if self.show_virtual_keyboard else '关'
                        self.macro_notify_msg = f"虚拟键盘：{status}"
                        self.macro_notify_timer = 90
                    
                    elif self._is_action_triggered(event, 'metrics_panel'):
                        self.show_metrics_panel = not getattr(self, 'show_metrics_panel', False)
                        status = '开' if self.show_metrics_panel else '关'
                        self.macro_notify_msg = f"调试面板：{status}"
                        self.macro_notify_timer = 90
                    
                    elif self._is_action_triggered(event, 'records_panel'):
                        self.show_records_panel = not getattr(self, 'show_records_panel', False)
                        self.rp_confirm_delete_id = None
                        status = '开' if self.show_records_panel else '关'
                        self.macro_notify_msg = f"成绩面板：{status}"
                        self.macro_notify_timer = 90
                    
                    else:
                        # 教程解法播放中：锁定棋盘操作（方向键移动）
                        if self._tut_board_locked():
                            continue
                        # 米字格按冻结决策不綁物理鍵盤（8 向鍵位會與撤銷/重做等
                        # 既有快捷鍵爭 W/A/S/D）：按到移動鍵只提示用虛擬鍵盤，
                        # 其他按鍵照舊放行（對話框輸入、快捷鍵都靠後續分支處理）
                        if getattr(self, 'mi_mode', False):
                            move_actions = MI_KEY_ACTIONS
                            for action_name in move_actions:
                                if self._is_action_triggered(event, action_name):
                                    self.macro_notify_msg = (
                                        "米字格：方向请用虚拟键盘（先点缝隙，再点滑块定向）")
                                    self.macro_notify_timer = 90
                                    break
                            continue
                        # 三角形密铺：6 向键盘映射（W E / A D / Z X，围住 S 成六边形）
                        if getattr(self, 'triangle_mode', False):
                            self._triangle_keyboard_move(event)
                            continue
                        # 方向键移动（需要匹配配置且无修饰键冲突；由 control_mouse_kb 开关控制）
                        if getattr(self, 'control_mouse_kb', True):
                            move_actions = {
                                'move_up': 'w', 'move_down': 's',
                                'move_left': 'a', 'move_right': 'd'
                            }
                            for action_name, direction in move_actions.items():
                                if self._is_action_triggered(event, action_name):
                                    if self.selected_gap and self.selected_block:
                                        gap_type, line = self.selected_gap
                                        can_move = False
                                        if gap_type == 'v' and direction in ('w', 's'):
                                            can_move = True
                                        elif gap_type == 'h' and direction in ('a', 'd'):
                                            can_move = True
                                        if can_move:
                                            self.move_selected_blocks(direction)
                                    break
                
                # 键盘释放
                elif event.type == pygame.KEYUP:
                    if event.key == pygame.K_z:
                        self.undo_held = False
                        self.undo_first = False
                    elif event.key == pygame.K_x:
                        self.redo_held = False
                        self.redo_first = False
                    elif event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                        self.undo_held = False
                        self.undo_first = False
                        self.redo_held = False
                        self.redo_first = False
                        
            except Exception:
                # 事件处理异常属非致命：仅输出到控制台（带完整堆栈），不中断游戏
                traceback.print_exc()
                print("Event error (non-fatal)")
    
    def _cmd_reply(self, resp_q, ok, message, data=None):
        """统一回复：有 resp_q 则通过队列回复（HTTP），否则打印到终端"""
        if resp_q:
            result = {"ok": ok, "message": message}
            if data:
                result.update(data)
            resp_q.put(result)
        else:
            prefix = "[OK]" if ok else "[ERR]"
            print(f"{prefix} {message}")

    def _get_game_status(self):
        """获取游戏状态字典（用于 HTTP JSON 响应）

        旧字段（puzzle/step_count/solved/matrix/selected_gap/selected_block/
        animating）保持原义不变；新增 m/n/step/game_mode/timer_state/readonly/
        blocks（含 mod 分组）/macro/solver，供 AI 一次取齐决策信息。
        """
        self.game.update_matrix()
        step = self.current_step
        tri = getattr(self, 'triangle_mode', False)
        mi = getattr(self, 'mi_mode', False)
        blocks = [
            {"row": b.location[0], "col": b.location[1],
             "mod": [b.location[0] % step, b.location[1] % step],
             "num": getattr(b, 'number', None)}
            for b in self.game.blocks
        ]
        if tri:
            # 三角形密铺：附带 up 朝向（▲/▼），供调用方还原密铺结构
            for blk, b in zip(blocks, self.game.blocks):
                blk['up'] = bool(b.location[2])
        if mi:
            # 米字格：附带 q 朝向（N/E/S/W，斜边朝向哪条格边）。平移不改 q，
            # 因此同一格可能缺块（导入/打乱后），调用方要靠 q 才能定位单元
            for blk, b in zip(blocks, self.game.blocks):
                blk['q'] = b.location[2] if len(b.location) >= 3 else None
        solver_state = self._get_solver_state()
        if mi:
            kind = 'mi'
        elif tri:
            kind = 'triangle'
        elif getattr(self, 'numbered', False):
            kind = 'numbered'
        else:
            kind = 'square'
        return {
            "puzzle": puzzle_key(step, self.current_m, self.current_n, kind=kind,
                                 triangle_side=self.game.k if tri else None),
            "step_count": self.step_count,
            "solved": self.is_solved(),
            "matrix": self.game.matrix,
            "selected_gap": list(self.selected_gap) if self.selected_gap else None,
            "selected_block": self.selected_block.location if self.selected_block else None,
            "animating": self.animating,
            # —— 新增字段 ——
            "m": self.current_m,
            "n": self.current_n,
            "step": step,
            "game_mode": self.game_mode,
            "timer_state": self.timer_state,
            "readonly": bool(getattr(self, '_readonly', False)),
            "blocks": blocks,
            "macro": {
                "recording": bool(getattr(self, 'macro_recording', False)),
                "executing": bool(getattr(self, 'macro_executing', False)),
            },
            "solver": {
                "state": solver_state["state"],
                "algorithm": solver_state["algorithm"],
            },
        }

    # ------------------------------------------------------------------
    # API 辅助：结构化求解状态 / 局面分析 / 设置与参数校验
    # ------------------------------------------------------------------
    def _get_solver_state(self):
        """结构化求解器状态（HTTP /solver/status 与 /status 的 solver 字段共用）。

        state: running（后台计算中或解法正在通过宏管道播放）/ solved / failed /
               cancelled / idle。终态靠 _api_solve_latch（GUI.py 求解流程写入）
               与 _auto_solve_cancel 标志判定。
        """
        import time
        running = bool(getattr(self, '_auto_solve_running', False)
                       or getattr(self, '_gradient_busy', False))
        exec_name = getattr(self, 'macro_exec_name', '') or ''
        playing = bool(getattr(self, 'macro_executing', False)
                       and not getattr(self, 'macro_recording', False)
                       and (exec_name in ('自动求解', '聚拢')
                            or exec_name.startswith('填洞宏')))
        latch = getattr(self, '_api_solve_latch', None)

        if running or playing:
            state = 'running'
        elif getattr(self, '_auto_solve_cancel', False):
            state = 'cancelled'
        elif latch is None:
            state = 'idle'
        elif latch.get('ok'):
            state = 'solved'
        else:
            state = 'failed'

        progress = getattr(self, '_auto_solve_progress', None)
        gradient = None
        gs = getattr(self, '_gradient_state', None)
        if isinstance(gs, dict) and gs.get('max_stages'):
            gradient = {'stage': gs.get('stage'), 'total': gs.get('max_stages')}
        if isinstance(progress, dict) and progress.get('stage') == 'gradient_stage':
            gradient = {'stage': progress.get('idx'), 'total': progress.get('total')}

        # elapsed：running 实时增长；终态（solved/failed/cancelled）用锁存值冻结
        elapsed_ms = None
        if state in ('solved', 'failed', 'cancelled') and latch \
                and latch.get('elapsed_ms') is not None:
            elapsed_ms = latch['elapsed_ms']
        else:
            start = getattr(self, '_auto_solve_start_time', 0)
            if start:
                elapsed_ms = int((time.time() - start) * 1000)

        return {
            'state': state,
            'algorithm': getattr(self, 'solver_algorithm', 'ida_star'),
            'progress': progress,
            'gradient': gradient,
            'result_steps': latch.get('steps') if (latch and state == 'solved') else None,
            'elapsed_ms': elapsed_ms,
        }

    def _analysis_coords(self):
        """当前方块坐标集合（frozenset），先刷新矩阵。"""
        self.game.update_matrix()
        return frozenset((b.location[0], b.location[1]) for b in self.game.blocks)

    def _analysis_window(self):
        """目标窗口（与调试面板绿框同源 find_best_window）。"""
        from solver.ml.gather_solver import find_best_window
        coords = self._analysis_coords()
        if not coords:
            return None
        r0, c0, (rh, cw), overlap = find_best_window(
            coords, self.game.m, self.game.n, self.current_step)
        return {'r0': r0, 'c0': c0, 'rh': rh, 'cw': cw, 'overlap': overlap}

    def _analysis_holes(self):
        """洞/缺口/凸起（与 metrics_panel._draw_debug_holes 同一次 detect_holes）。"""
        from solver.ml.hole_detector import detect_holes
        coords = self._analysis_coords()
        if not coords:
            return None, [], []
        window = self._analysis_window()
        region = (window['r0'], window['c0'], (window['rh'], window['cw']))
        holes, protrusions, _ = detect_holes(
            coords, self.game.m, self.game.n, self.current_step, region=region)
        holes_out = [
            {'type': h.get('type'), 'size': h.get('size'),
             'cells': [[r, c] for r, c in h.get('cells', [])]}
            for h in holes
        ]
        return window, holes_out, [[r, c] for r, c in protrusions]

    def _analysis_actions(self):
        """合法动作枚举（solver.actions.enumerate_valid_actions）。"""
        from solver.actions import enumerate_valid_actions
        acts = enumerate_valid_actions(self.game, self.current_step)
        return [{'gap_type': a[0], 'gap_line': a[1], 'side': a[2], 'move_dir': a[3]}
                for a in acts]

    # settings 白名单：布尔键 + 动画速度（映射 self.animation_duration）
    _SETTINGS_BOOL_KEYS = (
        'coloring_enabled', 'chain_hint_enabled', 'show_metrics_panel',
        'animation_enabled', 'selection_animation_enabled',
        'control_single_touch', 'control_two_touch', 'control_mouse_kb',
        'macro_reverse_mode', 'save_readonly_flag', 'prevent_overwrite_flag',
    )
    _SETTINGS_INT_KEYS = ('animation_duration_ms',)
    _ANIM_DURATION_RANGE = (50, 1000)

    def _settings_get(self):
        """返回全部白名单设置键的当前值。"""
        data = {k: bool(getattr(self, k, False)) for k in self._SETTINGS_BOOL_KEYS}
        data['animation_duration_ms'] = int(getattr(self, 'animation_duration', 300))
        return data

    def _settings_apply(self, updates):
        """校验并应用设置（整体校验：任一非法则不应用任何项）。

        返回 (ok, message)。updates: dict。
        """
        if not isinstance(updates, dict) or not updates:
            return False, "缺少设置项"
        bool_keys = set(self._SETTINGS_BOOL_KEYS)
        int_keys = set(self._SETTINGS_INT_KEYS)
        pending = []
        for key, val in updates.items():
            if key in bool_keys:
                if not isinstance(val, bool):
                    return False, f"{key} 必须是 true/false"
                pending.append((key, val))
            elif key in int_keys:
                if isinstance(val, bool) or not isinstance(val, int):
                    return False, f"{key} 必须是整数"
                lo, hi = self._ANIM_DURATION_RANGE
                if not (lo <= val <= hi):
                    return False, f"{key} 必须在 {lo}–{hi} 之间"
                pending.append(('animation_duration', val))
            else:
                return False, f"未知设置键: {key}"
        for attr, val in pending:
            setattr(self, attr, val)
        return True, f"已更新 {len(pending)} 项设置"

    def _solver_params_get(self):
        """返回 gather 参数值与启用标志。"""
        out = {}
        for k, v in self.gather_params.items():
            out[k] = {'value': v, 'enabled': bool(self.gather_enabled.get(k, True))}
        return out

    def _solver_params_apply(self, updates):
        """校验并应用 gather 参数（整体校验）。返回 (ok, message)。"""
        if not isinstance(updates, dict) or not updates:
            return False, "缺少参数项"
        specs = {key: spec for key, spec in getattr(self, '_gather_param_specs', [])}
        pending = []
        for key, val in updates.items():
            base = key[:-8] if key.endswith('_enabled') else key
            if base not in self.gather_params:
                return False, f"未知参数: {key}"
            if key.endswith('_enabled'):
                if not isinstance(val, bool):
                    return False, f"{key} 必须是 true/false"
                pending.append(('enabled', base, val))
            else:
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    return False, f"{key} 必须是数值"
                _name, _default, lo, hi, _step, _desc = specs[base]
                if not (lo <= val <= hi):
                    return False, f"{key} 必须在 {lo}–{hi} 之间"
                pending.append(('value', base, val))
        for kind, base, val in pending:
            if kind == 'enabled':
                self.gather_enabled[base] = val
            else:
                self.gather_params[base] = val
        return True, f"已更新 {len(pending)} 项求解参数"

    def _do_solve(self, algorithm=None):
        """启动/取消求解。返回 (ok, message)。

        注意：拒绝条件必须在调用 _start_auto_solve() 之前判定——极小局面上
        求解线程可能在主线程「启动后回查标志」前就已完成并把
        _auto_solve_running 置回 False（启动即完成的竞态）。
        """
        from solver import SOLVER_ALGORITHMS
        if algorithm:
            if algorithm not in SOLVER_ALGORITHMS:
                return False, f"未知算法: {algorithm}（可选: {', '.join(SOLVER_ALGORITHMS)}）"
            self.solver_algorithm = algorithm
        active = self._get_solver_state()['state'] == 'running'
        if not active:
            # 与 _start_auto_solve 同一组启动前置条件
            if self._timer_blocked():
                return False, "计时模式中无法使用求解器"
            if self._readonly_blocked():
                return False, "只读存档无法使用求解器"
            if getattr(self, '_ann_recording', False):
                return False, "标注录制中无法使用求解器"
            # 三角形密铺：求解器未实现。必须在 _start_auto_solve() 之前判定，
            # 否则按钮路径的拦截只落在 macro_notify，这里仍会回「已启动」
            if self._triangle_blocked('自动求解'):
                return False, self.macro_notify_msg
            # 米字格同理：8 向/4 族缝隙的求解器同样未实现
            if self._mi_blocked('自动求解'):
                return False, self.macro_notify_msg
        self._start_auto_solve()
        if active:
            return True, "已请求停止求解"
        return True, f"已启动自动求解（算法: {self.solver_algorithm}）"

    def _do_cancel_solve(self):
        """显式请求取消求解。返回 (ok, message)。"""
        if self._get_solver_state()['state'] != 'running':
            return False, "当前未在求解"
        self._start_auto_solve()  # 运行中调用 = 取消
        return True, "已请求停止求解"

    def _do_macro_execute(self, name, base_row, base_col, reverse=False):
        """执行宏（可逆序）。返回 (ok, message)。"""
        if not name:
            return False, "需要宏名称"
        if base_row is None or base_col is None:
            return False, "需要 base_row 和 base_col"
        if getattr(self, 'macro_recording', False):
            return False, "正在录制中，无法执行宏"
        if getattr(self, 'macro_executing', False):
            return False, "正在执行其他宏"
        # 米字格：宏按方形 h/v 缝隙语义录制，四族缝隙/八向的米字局面回放无意义
        if self._mi_blocked('宏执行'):
            return False, self.macro_notify_msg
        self._start_macro_execute(name, reverse=bool(reverse))
        if getattr(self, 'macro_executing', False) and getattr(self, 'macro_selecting_base', False):
            self._confirm_macro_execute(base_row, base_col)
            label = '（逆序）' if reverse else ''
            return True, f"开始执行宏 '{name}'{label}，基准 ({base_row}, {base_col})"
        return False, getattr(self, 'macro_error_msg', '') or f"无法执行宏 '{name}'"

    def _do_save_file(self, path):
        """保存到指定路径并核验落盘（_save_to_path 内部吞异常仅 print）。
        返回 (ok, message)。"""
        if not path:
            return False, "需要 path"
        try:
            self._save_to_path(path)
        except Exception as e:
            return False, f"保存失败: {e}"
        if os.path.isfile(path):
            return True, f"已保存到 {path}"
        return False, f"保存失败：无法写入 {path}（路径为目录或无权限）"

    def _do_load_map(self, map_str, step=None):
        """从地图字符串导入局面（无对话框）。返回 (ok, message)。"""
        if not isinstance(map_str, str) or not map_str.strip():
            return False, "地图字符串为空"
        normalized = map_str.replace(';', '\n')
        lines = [ln.strip() for ln in normalized.split('\n') if ln.strip()]
        if not lines:
            return False, "地图字符串为空"
        # 米字格的錯位態地圖帶 `mi8` 標記行（每格兩個十六進位位元，見
        # game_mi.export_map），先摘掉再查各行等寬，否則標記行會被誤判
        # 成寬度不齊
        if getattr(self, 'mi_mode', False) and lines[0].lower() == 'mi8':
            lines = lines[1:]
        if not lines:
            return False, "地图字符串为空"
        width = len(lines[0])
        if any(len(ln) != width for ln in lines):
            return False, "地图各行长度不一致"
        # 「有方块」判据按形态分：方形只认 '#'；三角还能是纯 '^'（仅▲）或纯 'v'（仅▼）；
        # 米字格是每格一个十六进制位（4 块各自的掩码），可能一个 '#' 都没有
        joined = ''.join(lines)
        tri = getattr(self, 'triangle_mode', False)
        mi = getattr(self, 'mi_mode', False)
        if mi:
            if not any(ch not in '0_.' for ch in joined):
                return False, "地图中没有方块"
        else:
            needed = ('#', '^', 'v') if tri else ('#',)
            if not any(ch in joined for ch in needed):
                return False, "地图中没有方块（#）"
        if step is not None:
            if not isinstance(step, int) or step < 1 or step >= max(len(lines), width):
                return False, f"step 必须是 1–{max(len(lines), width) - 1} 的整数"
        # 与切换谜题相同的收尾动作
        self._stop_gradient_pipeline()
        self._stop_continuous_undo_redo()
        self._last_timed_result = None
        if hasattr(self, '_ann_cancel_session'):
            self._ann_cancel_session('导入地图')
        if self.timer_state == 'running':
            return False, "计时中无法导入地图"
        if getattr(self, '_readonly', False):
            return False, "只读存档无法导入地图"
        if not self.game.import_map(normalized):
            return False, "地图解析失败"
        self.current_m = self.game.m
        self.current_n = self.game.n
        if step is not None:
            self.current_step = step
        # 带序号谜题导入地图后按行主序重排号（地图串只记录形状，不带身份）
        if getattr(self, 'numbered', False):
            for i, block in enumerate(sorted(self.game.blocks, key=lambda b: (b.location[0], b.location[1]))):
                block.number = i + 1
        self.selected_gap = None
        self.selected_block = None
        self._mi_gap_point = None
        self.animating = False
        self.anim_blocks = []
        self.step_count = 0
        self.game_history.reset()
        if getattr(self, 'triangle_mode', False):
            # 导入的地图包围盒可能与原局不同 → 重新适配缩放（存档不保存 zoom）
            self.zoom = self._fit_triangle_zoom()
        elif getattr(self, 'mi_mode', False):
            self.zoom = self._fit_mi_zoom()
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        if mi:
            return True, (f"已导入米字地图：{self.game.m}×{self.game.n}，"
                          f"{len(self.game.blocks)} 个单位三角")
        if tri:
            return True, (f"已导入三角地图：边长 {self.game.k}，"
                          f"{len(self.game.blocks)} 个单位三角")
        return True, f"已导入地图：{self.game.m}×{self.game.n}，{len(self.game.blocks)} 块"

    def _do_set_mode(self, mode):
        """切换练习/竞速/创造模式（幂等）。返回 (ok, message)。"""
        names = {'practice': '练习', 'timed': '竞速', 'create': '创造'}
        if mode not in names:
            return False, "mode 必须是 practice / timed / create"
        if self.timer_state == 'running':
            return False, "计时中无法切换模式"
        if not self.set_game_mode(mode):
            return False, "模式切换失败"
        return True, f"已切换为{names[mode]}模式"

    def _dispatch_payload_action(self, action, payload, resp_q):
        """HTTP 富 JSON body 通道：动作名与 CLI 同名，参数从 dict 取。"""
        try:
            if action == 'load_map':
                ok, msg = self._do_load_map(payload.get('map'), payload.get('step'))
                self._cmd_reply(resp_q, ok, msg)
            elif action == 'save_file':
                ok, msg = self._do_save_file(payload.get('path', ''))
                self._cmd_reply(resp_q, ok, msg)
            elif action == 'load_file':
                path = payload.get('path', '')
                if not path:
                    self._cmd_reply(resp_q, False, "需要 path")
                    return
                before = self.game.export_map()
                self._do_load_from_path(path)
                # _do_load_from_path 失败时仅 print；以局面是否变化/路径属性判定
                if os.path.abspath(getattr(self, 'current_file_path', '') or '') == os.path.abspath(path) \
                        or self.game.export_map() != before:
                    self._cmd_reply(resp_q, True, f"已从 {path} 加载")
                else:
                    self._cmd_reply(resp_q, False, f"加载失败：{path}（文件不存在或格式错误，或计时中被拒绝）")
            elif action == 'mode':
                ok, msg = self._do_set_mode(payload.get('mode', ''))
                self._cmd_reply(resp_q, ok, msg)
            elif action == 'settings':
                ok, msg = self._settings_apply(payload)
                self._cmd_reply(resp_q, ok, msg)
            elif action == 'solver_params':
                ok, msg = self._solver_params_apply(payload)
                self._cmd_reply(resp_q, ok, msg)
            elif action == 'solve':
                ok, msg = self._do_solve(payload.get('algorithm'))
                self._cmd_reply(resp_q, ok, msg)
            elif action == 'macro_execute':
                ok, msg = self._do_macro_execute(
                    payload.get('name', ''), payload.get('base_row'),
                    payload.get('base_col'), bool(payload.get('reverse', False)))
                self._cmd_reply(resp_q, ok, msg)
            else:
                self._cmd_reply(resp_q, False, f"不支持 JSON body 的指令: {action}")
        except Exception as e:
            self._cmd_reply(resp_q, False, f"执行 '{action}' 时出错: {e}")

    def process_commands(self):
        """处理命令队列中的终端/HTTP指令"""
        if self.cmd_queue is None:
            return
        
        while not self.cmd_queue.empty():
            try:
                item = self.cmd_queue.get_nowait()
            except queue.Empty:
                break
            
            # 支持三种格式：
            #   纯字符串（终端 stdin）
            #   (cmd, resp_q) 二元组（HTTP 传统指令）
            #   (cmd, resp_q, payload) 三元组（HTTP 富 JSON body：多行地图/设置等）
            resp_q = None
            payload = None
            if isinstance(item, tuple):
                if len(item) >= 3:
                    cmd, resp_q, payload = item[0], item[1], item[2]
                else:
                    cmd, resp_q = item
            else:
                cmd = item

            parts = cmd.split()
            if not parts:
                continue

            action = parts[0].lower()

            # 富 payload 通道：动作语义同名，但参数取自 JSON dict 而非空白分词
            if payload is not None:
                self._dispatch_payload_action(action, payload, resp_q)
                continue
            
            try:
                if action == 'shuffle':
                    self.shuffle_puzzle()
                    self._cmd_reply(resp_q, True, "已打乱")
                
                elif action == 'reset':
                    self.reset_puzzle()
                    self._cmd_reply(resp_q, True, f"已重置为 {self.current_step}~{self.current_m}*{self.current_n}")
                
                elif action == 'move':
                    tri = getattr(self, 'triangle_mode', False)
                    mi = getattr(self, 'mi_mode', False)
                    if len(parts) < 2:
                        usage = ("用法: move w/e/a/d/z/x" if tri
                                 else "用法: move w/s/a/d/e/z/q/x" if mi
                                 else "用法: move w/s/a/d")
                        self._cmd_reply(resp_q, False, usage)
                        continue
                    direction = parts[1].lower()
                    if mi:
                        # 米字格：8 向（q/w/e/a/d/z/s/x）。方向必须平行于已选
                        # 缝隙（GAP_DIRECTIONS 四族）；滑块参考块没点过时
                        # _mi_prepare_move 退回第一块，与虚拟键盘同源
                        from game_mi import DIRECTIONS as MI_DIRECTIONS
                        from game_mi import GAP_DIRECTIONS as MI_GAP_DIRECTIONS
                        if direction not in MI_DIRECTIONS:
                            self._cmd_reply(
                                resp_q, False,
                                f"方向必须是 {'/'.join(MI_DIRECTIONS.keys())}")
                            continue
                        if not (self.selected_gap and self.selected_block):
                            self._cmd_reply(resp_q, False, "未选中缝隙和滑块",
                                            {'reason': 'not_selected'})
                            continue
                        gap_type, _line = self.selected_gap
                        if direction not in MI_GAP_DIRECTIONS.get(gap_type, ()):
                            self._cmd_reply(
                                resp_q, False,
                                f"当前缝隙不允许 {direction} 方向移动",
                                {'reason': 'wrong_direction'})
                            continue
                        # 只读存档 / 计时就绪态禁止滑动
                        if self._readonly_blocked() or (
                                self.game_mode == 'timed'
                                and self.timer_state == 'ready'):
                            self._cmd_reply(
                                resp_q, False,
                                "当前状态禁止滑动（计时就绪态或只读存档）",
                                {'reason': 'timer_blocked'})
                            continue
                        moved = self.move_selected_blocks(direction)
                        if moved:
                            self._cmd_reply(resp_q, True, f"已移动 {direction}")
                        else:
                            self._cmd_reply(resp_q, False, "移动未生效",
                                            {'reason': 'no_move'})
                        continue
                    if tri:
                        # 三角形：6 向（wedxza 六邊形）。selected_block 必需；
                        # selected_gap 可選——有則鎖定該縫，無則由 resolve_drag
                        # 按「縫隙線穿過手指」規則決定（與單次觸控拖動同源）
                        from game_triangle import DIRECTIONS, GAP_DIRECTIONS
                        if direction not in DIRECTIONS:
                            self._cmd_reply(
                                resp_q, False,
                                f"方向必须是 {'/'.join(DIRECTIONS.keys())}")
                            continue
                        if self.selected_block is None:
                            self._cmd_reply(resp_q, False, "未选中滑块",
                                            {'reason': 'not_selected'})
                            continue
                        if self.selected_gap is not None:
                            gap_type, _line = self.selected_gap
                            if direction not in GAP_DIRECTIONS[gap_type]:
                                self._cmd_reply(
                                    resp_q, False,
                                    f"当前缝隙不允许 {direction} 方向移动",
                                    {'reason': 'wrong_direction'})
                                continue
                        # 只读存档 / 计时就绪态禁止滑动
                        if self._readonly_blocked() or (
                                self.game_mode == 'timed'
                                and self.timer_state == 'ready'):
                            self._cmd_reply(
                                resp_q, False,
                                "当前状态禁止滑动（计时就绪态或只读存档）",
                                {'reason': 'timer_blocked'})
                            continue
                        moved = self.move_selected_blocks(direction)
                        if moved:
                            self._cmd_reply(resp_q, True, f"已移动 {direction}")
                        else:
                            self._cmd_reply(resp_q, False, "移动未生效",
                                            {'reason': 'no_move'})
                        continue
                    if direction not in ('w', 's', 'a', 'd'):
                        self._cmd_reply(resp_q, False, "方向必须是 w/s/a/d")
                        continue
                    # 失败原因（reason）与 GUI 右下角提示同源：
                    # not_selected / wrong_direction / timer_blocked /
                    # disconnected（断开）/ collision（重叠）
                    if not (self.selected_gap and self.selected_block):
                        self._cmd_reply(resp_q, False, "未选中缝隙和滑块",
                                        {'reason': 'not_selected'})
                        continue
                    gap_type, line = self.selected_gap
                    can_move = ((gap_type == 'v' and direction in ('w', 's'))
                                or (gap_type == 'h' and direction in ('a', 'd')))
                    if not can_move:
                        self._cmd_reply(resp_q, False,
                                        f"当前缝隙不允许 {direction} 方向移动",
                                        {'reason': 'wrong_direction'})
                        continue
                    # 只读存档 / 计时就绪态禁止滑动
                    if self._readonly_blocked() or (
                            self.game_mode == 'timed' and self.timer_state == 'ready'):
                        self._cmd_reply(resp_q, False,
                                        "当前状态禁止滑动（计时就绪态或只读存档）",
                                        {'reason': 'timer_blocked'})
                        continue
                    # 纯逻辑预演（不提交）：取断开/重叠原因
                    _positions, fail_reason = self.game.try_move_ex(direction, self.current_step)
                    if not _positions:
                        reason_map = {
                            'disconnected': ('disconnected', "滑动失败：移动后滑块会断开"),
                            'collision': ('collision', "滑动失败：移动后滑块会重叠"),
                            'no_selection': ('not_selected', "未选中滑块组"),
                        }
                        r_code, r_msg = reason_map.get(
                            fail_reason, ('disconnected', f"移动不合法（{fail_reason}）"))
                        self._cmd_reply(resp_q, False, r_msg, {'reason': r_code})
                        continue
                    moved = self.move_selected_blocks(direction)
                    if moved:
                        self._cmd_reply(resp_q, True, f"已移动 {direction}")
                    else:
                        self._cmd_reply(resp_q, False, "移动未生效",
                                        {'reason': 'timer_blocked'})
                
                elif action == 'new':
                    if len(parts) < 4:
                        self._cmd_reply(resp_q, False,
                                        "用法: new m n step [num|tri|mi]")
                        continue
                    try:
                        nm = int(parts[1])
                        nn = int(parts[2])
                        ns = int(parts[3])
                    except ValueError:
                        self._cmd_reply(resp_q, False, "参数必须是整数")
                        continue
                    # 第 4 参：num = 带序号方形；tri = 三角形密铺（用 m 作边长 k）；
                    # mi = 米字格（m 行 n 列，每格 4 个单元三角）
                    numbered = len(parts) >= 5 and parts[4] in ('1', 'num', 'true')
                    is_tri = len(parts) >= 5 and parts[4] in ('tri', 'triangle')
                    is_mi = len(parts) >= 5 and parts[4] in ('mi', 'mizi')
                    if is_mi:
                        if self.new_mi_puzzle(nm, nn, ns):
                            self._cmd_reply(resp_q, True, f"新谜题 {ns}~mi{nm}*{nn}")
                        else:
                            self._cmd_reply(
                                resp_q, False,
                                f"米字格行列必须 >=2 且等级 < max({nm}, {nn})")
                        continue
                    if is_tri:
                        if self.new_triangle_puzzle(nm, ns):
                            self._cmd_reply(resp_q, True, f"新谜题 {ns}~tri{nm}")
                        else:
                            self._cmd_reply(resp_q, False,
                                            f"三角形边长必须 >=2 且等级 < 边长（{nm}）")
                        continue
                    if self.new_puzzle(nm, nn, ns, numbered=numbered):
                        label = f"{ns}~{nm}*{nn}"
                        if numbered:
                            label += '#num'
                        self._cmd_reply(resp_q, True, f"新谜题 {label}")
                    else:
                        self._cmd_reply(resp_q, False, f"等级必须小于 max({nm}, {nn})")
                
                elif action == 'export':
                    self.export_map()
                
                elif action == 'import':
                    self.import_map()
                
                elif action == 'select_gap':
                    tri = getattr(self, 'triangle_mode', False)
                    mi = getattr(self, 'mi_mode', False)
                    if len(parts) < 3:
                        self._cmd_reply(
                            resp_q, False,
                            "用法: select_gap h/p/n line" if tri
                            else "用法: select_gap h/v/d1/d2 line" if mi
                            else "用法: select_gap h/v line")
                        continue
                    gap_type = parts[1].lower()
                    if mi:
                        # 錯位態的絳線號是半整數（如 h 1.5），這裡要放寬到 float
                        line = parse_mi_coord(parts[2])
                    else:
                        try:
                            line = int(parts[2])
                        except ValueError:
                            line = None
                    if line is None:
                        self._cmd_reply(
                            resp_q, False,
                            "line 必须是整数或半整数" if mi else "line 必须是整数")
                        continue
                    if mi:
                        # 米字格：4 族縫（h=橫邊 / v=豎邊 / d1="\" / d2="/"）。
                        # is_valid_gap 自己判 line 是否落在棋形內
                        from game_mi import GAP_DIRECTIONS
                        if gap_type not in GAP_DIRECTIONS:
                            self._cmd_reply(resp_q, False,
                                            "类型必须是 h、v、d1 或 d2")
                            continue
                        if not self.game.is_valid_gap(gap_type, line):
                            self._cmd_reply(
                                resp_q, False,
                                f"{self._gap_type_name(gap_type)}缝隙 {line} 不合法")
                            continue
                    elif tri:
                        # 三角形：3 族縫（h=水平 / p=i 常數 / n=i+j 常數）
                        from game_triangle import GAP_DIRECTIONS
                        if gap_type not in GAP_DIRECTIONS:
                            self._cmd_reply(resp_q, False,
                                            "类型必须是 h、p 或 n")
                            continue
                        if not self.game.is_valid_gap(gap_type, line):
                            self._cmd_reply(
                                resp_q, False,
                                f"{self._gap_type_name(gap_type)}缝隙 {line} 不合法")
                            continue
                    else:
                        if gap_type not in ('h', 'v'):
                            self._cmd_reply(resp_q, False, "类型必须是 h 或 v")
                            continue
                        if gap_type == 'h' and not self.game.is_valid_h_line(line):
                            self._cmd_reply(resp_q, False, f"横向分割线 {line} 不合法")
                            continue
                        if gap_type == 'v' and not self.game.is_valid_v_line(line):
                            self._cmd_reply(resp_q, False, f"纵向分割线 {line} 不合法")
                            continue
                    self.selected_gap = (gap_type, line)
                    for b in self.game.blocks:
                        b.be_opted = False
                    self.selected_block = None
                    # 不是「点在缝隙上」选中，米字格的定向锚点作废：
                    # 之后点滑块只选组，方向交给虚拟键盘或下一轮两次触控
                    self._mi_gap_point = None
                    self._cmd_reply(resp_q, True, f"已选中缝隙: {gap_type} {line}")
                
                elif action == 'select_block':
                    tri = getattr(self, 'triangle_mode', False)
                    mi = getattr(self, 'mi_mode', False)
                    if mi:
                        # 米字格：select_block r c q（q = N/E/S/W）
                        if len(parts) < 3:
                            self._cmd_reply(resp_q, False,
                                            "用法: select_block r c [N/E/S/W]")
                            continue
                        # 錯位態的錨點行列也是半整數（如 0.5 -1.5）
                        row = parse_mi_coord(parts[1])
                        col = parse_mi_coord(parts[2])
                        if row is None or col is None:
                            self._cmd_reply(resp_q, False,
                                            "r/c 必须是整数或半整数")
                            continue
                        want_q = parts[3].upper() if len(parts) >= 4 else None
                        if want_q is not None and want_q not in ('N', 'E', 'S', 'W'):
                            self._cmd_reply(resp_q, False, "q 必须是 N/E/S/W")
                            continue
                        from game_mi import mi_key
                        block = None
                        for b in self.game.blocks:
                            if mi_key(b) == (row, col, want_q):
                                block = b
                                break
                        if block is None:
                            # q 省略，或该朝向不在这格里（打乱后会缺块）→ 退回
                            # 该格现存的第一块，和方形版「只按 (row,col) 定位」同义
                            for b in self.game.blocks:
                                if mi_key(b)[:2] == (row, col):
                                    block = b
                                    break
                        if block is None:
                            self._cmd_reply(
                                resp_q, False,
                                f"位置 ({row}, {col}, {want_q or ''}) 没有滑块")
                            continue
                        if self.selected_gap is not None:
                            gap_type, line = self.selected_gap
                            self.game.opt(gap_type, line, block)
                        self.selected_block = block
                        selected_count = sum(
                            1 for b in self.game.blocks if b.be_opted)
                        self._cmd_reply(
                            resp_q, True,
                            f"已选中滑块 {mi_key(block)}, 选中区域: {selected_count} 个")
                        continue
                    if tri:
                        # 三角形：select_block i j [up]（up 省略時優先 ▲）
                        if len(parts) < 3:
                            self._cmd_reply(resp_q, False,
                                            "用法: select_block i j [up]")
                            continue
                        try:
                            row = int(parts[1])
                            col = int(parts[2])
                            want_up = (int(parts[3]) != 0) if len(parts) >= 4 else True
                        except ValueError:
                            self._cmd_reply(resp_q, False, "i/j/up 必须是整数")
                            continue
                        block = None
                        fallback = None
                        for b in self.game.blocks:
                            if b.location[0] == row and b.location[1] == col:
                                if bool(b.location[2]) == want_up:
                                    block = b
                                    break
                                if fallback is None:
                                    fallback = b
                        if block is None:
                            block = fallback
                        if block is None:
                            self._cmd_reply(
                                resp_q, False, f"位置 ({row}, {col}) 没有滑块")
                            continue
                        if self.selected_gap is not None:
                            gap_type, line = self.selected_gap
                            self.game.opt(gap_type, line, block)
                        self.selected_block = block
                        selected_count = sum(
                            1 for b in self.game.blocks if b.be_opted)
                        self._cmd_reply(
                            resp_q, True,
                            f"已选中滑块 ({row},{col},{int(bool(block.location[2]))}), "
                            f"选中区域: {selected_count} 个")
                        continue
                    if len(parts) < 3:
                        self._cmd_reply(resp_q, False, "用法: select_block row col")
                        continue
                    try:
                        row = int(parts[1])
                        col = int(parts[2])
                    except ValueError:
                        self._cmd_reply(resp_q, False, "row/col 必须是整数")
                        continue
                    block = None
                    for b in self.game.blocks:
                        if b.location == [row, col]:
                            block = b
                            break
                    if block is None:
                        self._cmd_reply(resp_q, False, f"位置 ({row}, {col}) 没有滑块")
                        continue
                    if self.selected_gap is None:
                        self._cmd_reply(resp_q, False, "请先用 select_gap 选中缝隙")
                        continue
                    direction, line = self.selected_gap
                    self.game.opt(direction, line, block)
                    self.selected_block = block
                    selected_count = sum(1 for b in self.game.blocks if b.be_opted)
                    self._cmd_reply(resp_q, True, f"已选中滑块 ({row},{col}), 选中区域: {selected_count} 个")
                
                elif action == 'deselect':
                    self.selected_gap = None
                    self.selected_block = None
                    for b in self.game.blocks:
                        b.be_opted = False
                    self._cmd_reply(resp_q, True, "已取消选中")
                
                elif action == 'status':
                    status = self._get_game_status()
                    if resp_q:
                        resp_q.put(status)
                    else:
                        print(f"=== 状态 ===")
                        print(f"谜题: {status['puzzle']}")
                        print(f"步数: {status['step_count']}")
                        print(f"复原: {'是' if status['solved'] else '否'}")
                        print(f"矩阵:")
                        for row in status['matrix']:
                            print(' '.join(str(v) for v in row))
                        print(f"==========")
                
                elif action == 'undo':
                    self.undo()
                    self._cmd_reply(resp_q, True, "已撤销")

                elif action == 'redo':
                    self.redo()
                    self._cmd_reply(resp_q, True, "已重做")

                elif action == 'map':
                    map_str = self.game.export_map()
                    if resp_q:
                        resp_q.put({"ok": True, "map": map_str})
                    else:
                        print(map_str)

                elif action == 'quit':
                    self.running = False
                    self._cmd_reply(resp_q, True, "退出游戏")

                # ========== 自动求解命令 ==========
                elif action == 'solve':
                    # 用法: solve [algorithm]；运行中调用 = 取消
                    algorithm = parts[1] if len(parts) >= 2 else None
                    ok, msg = self._do_solve(algorithm)
                    self._cmd_reply(resp_q, ok, msg)

                elif action == 'solve_cancel':
                    ok, msg = self._do_cancel_solve()
                    self._cmd_reply(resp_q, ok, msg)

                elif action == 'solver_algorithms':
                    from solver import SOLVER_ALGORITHMS
                    algs = [{'key': k, 'name': v[0].strip()} for k, v in SOLVER_ALGORITHMS.items()]
                    data = {'current': self.solver_algorithm, 'algorithms': algs}
                    if resp_q:
                        resp_q.put({'ok': True, **data})
                    else:
                        print(f"当前算法: {self.solver_algorithm}")
                        for a in algs:
                            mark = '*' if a['key'] == self.solver_algorithm else ' '
                            print(f"  {mark} {a['key']:16s} {a['name']}")

                elif action == 'solver_status':
                    st = self._get_solver_state()
                    if resp_q:
                        resp_q.put({'ok': True, **st})
                    else:
                        print(f"求解状态: {st['state']}（算法 {st['algorithm']}）")
                        if st['result_steps'] is not None:
                            print(f"  解法步数: {st['result_steps']}")
                        if st['gradient']:
                            print(f"  梯度阶段: {st['gradient']['stage']}/{st['gradient']['total']}")

                elif action == 'solver_params':
                    if len(parts) < 2:
                        params = self._solver_params_get()
                        if resp_q:
                            resp_q.put({'ok': True, 'params': params})
                        else:
                            for k, info in params.items():
                                flag = '启用' if info['enabled'] else '不限'
                                print(f"  {k:20s} = {info['value']}  ({flag})")
                    else:
                        updates = {}
                        bad = False
                        for token in parts[1:]:
                            if '=' not in token:
                                self._cmd_reply(resp_q, False, f"参数格式错误: {token}（应为 key=value）")
                                bad = True
                                break
                            key, raw_val = token.split('=', 1)
                            key = key.strip()
                            raw_val = raw_val.strip()
                            if key.endswith('_enabled'):
                                if raw_val not in ('0', '1', 'true', 'false', 'True', 'False'):
                                    self._cmd_reply(resp_q, False, f"{key} 必须是 0/1/true/false")
                                    bad = True
                                    break
                                updates[key] = raw_val in ('1', 'true', 'True')
                            else:
                                try:
                                    updates[key] = float(raw_val) if '.' in raw_val else int(raw_val)
                                except ValueError:
                                    self._cmd_reply(resp_q, False, f"{key} 值必须是数值: {raw_val}")
                                    bad = True
                                    break
                        if not bad:
                            ok, msg = self._solver_params_apply(updates)
                            self._cmd_reply(resp_q, ok, msg)

                elif action == 'solve_status':
                    # 旧文本指令（保留兼容）
                    if self._auto_solve_running:
                        status = "running"
                    elif self._auto_solve_result is not None:
                        if self._auto_solve_result is False:
                            status = "failed (无解)"
                        else:
                            status = f"solved ({len(self._auto_solve_result)}步)"
                    else:
                        status = "idle"
                    self._cmd_reply(resp_q, True, status)

                # ========== 计时器命令 ==========
                elif action == 'timer_start':
                    if self.timer_state == 'ready':
                        self._timer_start()
                        self._cmd_reply(resp_q, True, "计时已开始")
                    elif self.timer_state == 'running':
                        self._cmd_reply(resp_q, False, "已在计时中")
                    else:
                        self._cmd_reply(resp_q, False, "当前无法开始计时（请先打乱）")

                elif action == 'timer_stop':
                    if self.timer_state == 'running':
                        self._timer_finish(dnf=True)
                        self._cmd_reply(resp_q, True, "已停止（DNF）")
                    else:
                        self._cmd_reply(resp_q, False, "当前未在计时")

                elif action == 'timer_status':
                    self._cmd_reply(resp_q, True, self.timer_state, {
                        'state': self.timer_state,
                        'elapsed_ms': int(self.timer_elapsed * 1000),
                    })

                elif action == 'records':
                    key = puzzle_key(self.current_step, self.current_m, self.current_n,
                                     kind='numbered' if getattr(self, 'numbered', False) else 'square')
                    st = self.records.stats(key)
                    self._cmd_reply(resp_q, True, f"共 {st['count']} 条", {
                        'puzzle': key,
                        'count': st['count'],
                        'best_ms': st['best'],
                        'worst_ms': st['worst'],
                        'dnf_count': st['dnf_count'],
                        'ao5_ms': st['ao5'],
                        'ao12_ms': st['ao12'],
                    })

                # ========== 宏命令 ==========
                elif action == 'macro_list':
                    names = self.macro_manager.list_names()
                    macros_info = []
                    for name in names:
                        m = self.macro_manager.get_macro(name)
                        if m:
                            macros_info.append({
                                'name': m.name,
                                'description': m.description,
                                'steps': m.step_count,
                                'recorded_step': m.recorded_step,
                                'base_point': m.base_point
                            })
                    if resp_q:
                        resp_q.put({"ok": True, "macros": macros_info})
                    else:
                        if macros_info:
                            for info in macros_info:
                                print(f"  {info['name']} ({info['steps']}步, step={info['recorded_step']})")
                        else:
                            print("  (无已保存的宏)")

                elif action == 'macro_record_start':
                    if self.macro_recording:
                        self._cmd_reply(resp_q, False, "已经在录制中")
                    elif self.macro_executing:
                        self._cmd_reply(resp_q, False, "正在执行宏，无法录制")
                    else:
                        self._start_macro_recording()
                        if self.macro_recording:
                            self._cmd_reply(
                                resp_q, True,
                                "已开始录制，请选择基准方块 (macro_set_base row col)")
                        else:
                            # 拦截路径（米字格等）只落 macro_notify，据实回失败，
                            # 否则调用方以为录上了，回放时对不上四族缝隙/八向
                            self._cmd_reply(
                                resp_q, False,
                                self.macro_notify_msg or "无法开始录制")

                elif action == 'macro_set_base':
                    if len(parts) < 3:
                        self._cmd_reply(resp_q, False, "用法: macro_set_base row col")
                        continue
                    try:
                        br = int(parts[1])
                        bc = int(parts[2])
                    except ValueError:
                        self._cmd_reply(resp_q, False, "row/col 必须是整数")
                        continue
                    if not getattr(self, 'macro_recording', False) and not getattr(self, 'macro_selecting_base', False):
                        self._cmd_reply(resp_q, False, "当前不在录制/执行基准选择模式")
                        continue
                    # 检查基准位置是否有方块
                    block = None
                    for b in self.game.blocks:
                        if b.location == [br, bc]:
                            block = b
                            break
                    if block is None:
                        self._cmd_reply(resp_q, False, f"位置 ({br}, {bc}) 没有滑块")
                        continue
                    if self.macro_selecting_base:
                        # 执行模式：确认基准
                        self._confirm_macro_execute(br, bc)
                    else:
                        # 录制模式：设置基准
                        self.macro_record_base_point = [br, bc]
                    self._cmd_reply(resp_q, True, f"基准坐标设为 ({br}, {bc})")

                elif action == 'macro_record_stop':
                    if not getattr(self, 'macro_recording', False):
                        self._cmd_reply(resp_q, False, "当前未在录制")
                    elif len(parts) < 2:
                        self._cmd_reply(resp_q, False, "用法: macro_record_stop <名称>")
                    else:
                        name = ' '.join(parts[1:])
                        if len(self.macro_recording_steps) == 0:
                            self.macro_recording = False
                            self.macro_recording_steps = []
                            self.macro_record_base_point = None
                            self._cmd_reply(resp_q, False, "录制了0步，已取消")
                        else:
                            self._save_macro_with_name(name)
                            self._cmd_reply(resp_q, True, f"宏 '{name}' 已保存 ({len(self.macro_recording_steps)} 步)")

                elif action == 'macro_execute':
                    # 用法: macro_execute <名称> <base_row> <base_col> [reverse]
                    if len(parts) < 4:
                        self._cmd_reply(resp_q, False, "用法: macro_execute <名称> <base_row> <base_col> [reverse]")
                        continue
                    reverse = (parts[-1].lower() == 'reverse')
                    coord_tokens = parts[-3:-1] if reverse else parts[-2:]
                    name_tokens = parts[1:-3] if reverse else parts[1:-2]
                    try:
                        base_row = int(coord_tokens[0])
                        base_col = int(coord_tokens[1])
                        name = ' '.join(name_tokens)
                    except (ValueError, IndexError):
                        self._cmd_reply(resp_q, False, "用法: macro_execute <名称> <base_row> <base_col> [reverse]")
                        continue
                    ok, msg = self._do_macro_execute(name, base_row, base_col, reverse)
                    self._cmd_reply(resp_q, ok, msg)

                elif action == 'macro_status':
                    data = {
                        'recording': bool(getattr(self, 'macro_recording', False)),
                        'executing': bool(getattr(self, 'macro_executing', False)),
                        'selecting_base': bool(getattr(self, 'macro_selecting_base', False)),
                        'reverse_mode': bool(getattr(self, 'macro_reverse_mode', False)),
                        'recording_steps': len(getattr(self, 'macro_recording_steps', []) or []),
                        'current_macro': getattr(self, 'macro_exec_name', '') or None
                        if getattr(self, 'macro_executing', False) else None,
                    }
                    if resp_q:
                        resp_q.put({'ok': True, **data})
                    else:
                        print(f"录制中: {'是' if data['recording'] else '否'}"
                              f"（已录 {data['recording_steps']} 步）")
                        print(f"执行中: {'是' if data['executing'] else '否'}"
                              f"（{data['current_macro'] or '-'}）")
                        print(f"逆序播放模式: {'开' if data['reverse_mode'] else '关'}")

                elif action == 'macro_delete':
                    if len(parts) < 2:
                        self._cmd_reply(resp_q, False, "用法: macro_delete <名称>")
                        continue
                    name = ' '.join(parts[1:])
                    if self.macro_manager.get_macro(name):
                        self.macro_manager.delete_macro(name)
                        self._cmd_reply(resp_q, True, f"宏 '{name}' 已删除")
                    else:
                        self._cmd_reply(resp_q, False, f"宏 '{name}' 不存在")

                elif action == 'macro_rename':
                    if len(parts) < 3:
                        self._cmd_reply(resp_q, False, "用法: macro_rename <旧名称> <新名称>")
                        continue
                    # 找到最后一个空格作为分隔（新名称可能包含空格）
                    cmd_body = ' '.join(parts[1:])
                    idx = cmd_body.rfind(' ')
                    if idx <= 0:
                        self._cmd_reply(resp_q, False, "用法: macro_rename <旧名称> <新名称>")
                        continue
                    old_name = cmd_body[:idx].strip()
                    new_name = cmd_body[idx+1:].strip()
                    if not old_name or not new_name:
                        self._cmd_reply(resp_q, False, "用法: macro_rename <旧名称> <新名称>")
                        continue
                    try:
                        self.macro_manager.rename_macro(old_name, new_name)
                        self._cmd_reply(resp_q, True, f"宏 '{old_name}' 已重命名为 '{new_name}'")
                    except FileNotFoundError:
                        self._cmd_reply(resp_q, False, f"宏 '{old_name}' 不存在")

                # ========== 局面分析指令 ==========
                elif action == 'window':
                    if self._form_blocked('局面分析'):
                        self._cmd_reply(resp_q, False, self.macro_notify_msg,
                                        {'reason': 'unsupported'})
                        continue
                    win = self._analysis_window()
                    if resp_q:
                        resp_q.put({'ok': True, 'window': win,
                                    'm': self.game.m, 'n': self.game.n,
                                    'step': self.current_step})
                    else:
                        if win:
                            print(f"目标窗口: 左上({win['r0']},{win['c0']}) "
                                  f"尺寸{win['rh']}×{win['cw']} 覆盖{win['overlap']}块")
                        else:
                            print("（无方块，无目标窗口）")

                elif action == 'holes':
                    if self._form_blocked('局面分析'):
                        self._cmd_reply(resp_q, False, self.macro_notify_msg,
                                        {'reason': 'unsupported'})
                        continue
                    win, holes, protrusions = self._analysis_holes()
                    if resp_q:
                        resp_q.put({'ok': True, 'window': win, 'holes': holes,
                                    'protrusions': protrusions})
                    else:
                        hn = sum(1 for h in holes if h['type'] == 'hole')
                        dn = sum(1 for h in holes if h['type'] == 'dent')
                        print(f"洞 {hn} 个 / 缺口 {dn} 个 / 凸起 {len(protrusions)} 个")
                        for h in holes:
                            kind = '孔洞' if h['type'] == 'hole' else '缺口'
                            print(f"  {kind}({h['size']}): {h['cells']}")

                elif action == 'actions':
                    if self._form_blocked('局面分析'):
                        self._cmd_reply(resp_q, False, self.macro_notify_msg,
                                        {'reason': 'unsupported'})
                        continue
                    acts = self._analysis_actions()
                    if resp_q:
                        resp_q.put({'ok': True, 'actions': acts})
                    else:
                        print(f"合法动作 {len(acts)} 个:")
                        for a in acts:
                            print(f"  缝{a['gap_type']}{a['gap_line']} {a['side']:6s} → {a['move_dir']}")

                # ========== 局面存取指令 ==========
                elif action == 'load_map':
                    # CLI: load_map <地图串>（行分隔可用 ; 代替换行）
                    map_str = ' '.join(parts[1:]).replace(';', '\n')
                    ok, msg = self._do_load_map(map_str)
                    self._cmd_reply(resp_q, ok, msg)

                elif action == 'save_file':
                    if len(parts) < 2:
                        self._cmd_reply(resp_q, False, "用法: save_file <路径>")
                        continue
                    path = ' '.join(parts[1:])
                    ok, msg = self._do_save_file(path)
                    self._cmd_reply(resp_q, ok, msg)

                elif action == 'load_file':
                    if len(parts) < 2:
                        self._cmd_reply(resp_q, False, "用法: load_file <路径>")
                        continue
                    path = ' '.join(parts[1:])
                    before = self.game.export_map()
                    self._do_load_from_path(path)
                    if os.path.abspath(getattr(self, 'current_file_path', '') or '') == os.path.abspath(path) \
                            or self.game.export_map() != before:
                        self._cmd_reply(resp_q, True, f"已从 {path} 加载")
                    else:
                        self._cmd_reply(resp_q, False, f"加载失败：{path}")

                # ========== 模式切换指令 ==========
                elif action == 'mode':
                    if len(parts) < 2:
                        if resp_q:
                            resp_q.put({'ok': True, 'mode': self.game_mode})
                        else:
                            print(f"当前模式: {self._mode_name()}")
                    else:
                        ok, msg = self._do_set_mode(parts[1].lower())
                        self._cmd_reply(resp_q, ok, msg)

                # ========== GUI 逻辑开关指令 ==========
                elif action == 'settings':
                    if len(parts) < 2:
                        data = self._settings_get()
                        if resp_q:
                            resp_q.put({'ok': True, 'settings': data})
                        else:
                            for k, v in data.items():
                                print(f"  {k:28s} = {v}")
                    elif len(parts) == 3:
                        key, raw_val = parts[1], parts[2].lower()
                        if raw_val in ('1', 'true', 'yes', 'on'):
                            val = True
                        elif raw_val in ('0', 'false', 'no', 'off'):
                            val = False
                        else:
                            try:
                                val = int(raw_val)
                            except ValueError:
                                self._cmd_reply(resp_q, False, f"值无法解析: {raw_val}")
                                continue
                        ok, msg = self._settings_apply({key: val})
                        self._cmd_reply(resp_q, ok, msg)
                    else:
                        self._cmd_reply(resp_q, False, "用法: settings [key value]")

                else:
                    self._cmd_reply(resp_q, False, f"未知指令: {action}")
                    if not resp_q:
                        print("可用指令: shuffle, reset, move, new, export, import, status, undo, redo, quit")
                        print("宏指令: macro_list, macro_record_start, macro_set_base, macro_record_stop, macro_execute, macro_delete, macro_rename, macro_status")
                        print("求解指令: solve [算法], solve_cancel, solver_algorithms, solver_status, solver_params [k=v ...]")
                        print("分析指令: window, holes, actions")
                        print("存取/模式/设置: load_map, save_file, load_file, mode [practice|timed], settings [key value]")
            
            except Exception as e:
                self._cmd_reply(resp_q, False, f"执行 '{cmd}' 时出错: {e}")
    
    def _update_slider_from_mouse(self, mouse_y):
        """根据鼠标Y坐标更新动画速度"""
        if not self.slider_rect:
            return
        track_top = self.slider_rect.top
        track_bottom = self.slider_rect.bottom
        track_height = track_bottom - track_top
        if track_height <= 0:
            return
        y = max(track_top, min(track_bottom, mouse_y))
        normalized = (y - track_top) / track_height
        new_duration = int(self.SPEED_MIN_MS + normalized * (self.SPEED_MAX_MS - self.SPEED_MIN_MS))
        if self.animating and self.animation_duration > 0:
            elapsed = pygame.time.get_ticks() - self.anim_start_time
            old_progress = elapsed / max(1, self.animation_duration)
            self.anim_start_time = pygame.time.get_ticks() - int(old_progress * new_duration)
        self.animation_duration = new_duration

    def _update_zoom_slider_from_mouse(self, mouse_y):
        """根据鼠标Y坐标更新缩放（以窗口中心为锚点）"""
        zr = getattr(self, 'zoom_slider_rect', None)
        if not zr or zr.height <= 0:
            return
        y = max(zr.top, min(zr.bottom, mouse_y))
        normalized = (y - zr.top) / zr.height
        # 倒置：越靠上(滑条顶部)=放大；越靠下=缩小
        new_zoom = self.min_zoom + (1.0 - normalized) * (self.max_zoom - self.min_zoom)
        cx = self.screen_width // 2
        cy = self.menu_bar_height + (self.screen_height - self.menu_bar_height - self.status_bar_height) // 2
        wx = (cx - self.camera_x) / self.zoom
        wy = (cy - self.camera_y) / self.zoom
        self.zoom = new_zoom
        self.camera_x = cx - wx * self.zoom
        self.camera_y = cy - wy * self.zoom

    def _update_settings_scrollbar(self, mx, my):
        """根据鼠标位置更新设置对话框滚动条"""
        sb = getattr(self, '_settings_scrollbar_rect', None)
        if not sb or sb.height <= 0:
            return
        max_scroll = getattr(self, '_settings_max_scroll', 0)
        if max_scroll <= 0:
            return
        ratio = (my - sb.y) / sb.height
        self._settings_scroll = max(0, min(max_scroll, int(ratio * max_scroll)))

    def _is_action_triggered(self, event, action_name):
        """
        检查事件是否匹配指定动作的快捷键配置。
        使用 event.mod 检测修饰键状态（事件生成时的状态，更可靠）。

        参数：
            event: pygame KEYDOWN 事件
            action_name: 快捷键动作名，如 'undo', 'save' 等
        返回：
            True 如果事件匹配该动作的快捷键
        """
        kb = self.keybindings.get(action_name)
        if not kb:
            return False

        target_key = kb.get('key', '')
        target_mods = kb.get('modifiers', [])

        # 将配置中的 key 名映射到 pygame 常量
        key_name_map = {
            'space': pygame.K_SPACE, 'up': pygame.K_UP, 'down': pygame.K_DOWN,
            'left': pygame.K_LEFT, 'right': pygame.K_RIGHT,
            'return': pygame.K_RETURN, 'escape': pygame.K_ESCAPE,
            'tab': pygame.K_TAB, 'backspace': pygame.K_BACKSPACE,
            'delete': pygame.K_DELETE, 'home': pygame.K_HOME, 'end': pygame.K_END,
            'pageup': pygame.K_PAGEUP, 'pagedown': pygame.K_PAGEDOWN,
            'insert': pygame.K_INSERT,
            'f1': pygame.K_F1, 'f2': pygame.K_F2, 'f3': pygame.K_F3, 'f4': pygame.K_F4,
            'f5': pygame.K_F5, 'f6': pygame.K_F6, 'f7': pygame.K_F7, 'f8': pygame.K_F8,
            'f9': pygame.K_F9, 'f10': pygame.K_F10, 'f11': pygame.K_F11, 'f12': pygame.K_F12,
        }
        if len(target_key) == 1:
            expected_key = getattr(pygame, f'K_{target_key}', None)
        else:
            expected_key = key_name_map.get(target_key)

        if expected_key is None or event.key != expected_key:
            return False

        # 检查修饰键：使用 event.mod（事件生成时的修饰键状态）
        has_ctrl = bool(event.mod & pygame.KMOD_CTRL)
        has_alt = bool(event.mod & pygame.KMOD_ALT)
        has_shift = bool(event.mod & pygame.KMOD_SHIFT)

        need_ctrl = 'ctrl' in target_mods
        need_alt = 'alt' in target_mods
        need_shift = 'shift' in target_mods

        return (has_ctrl == need_ctrl) and (has_alt == need_alt) and (has_shift == need_shift)

    def _handle_settings_dialog_event(self, event):
        """处理设置对话框中的事件"""
        # 聚拢参数值手动输入：只处理键盘输入（鼠标事件放行，由下方逻辑处理）
        if self.settings_active_tab == 'gather' and getattr(self, 'settings_editing_value', None):
            if event.type == pygame.KEYDOWN:
                key = self.settings_editing_value
                if event.key == pygame.K_RETURN:
                    self._commit_gather_value(key)
                elif event.key == pygame.K_ESCAPE:
                    self.settings_editing_value = None
                elif event.key == pygame.K_BACKSPACE:
                    self.settings_edit_buffer = self.settings_edit_buffer[:-1]
                elif event.key == pygame.K_PERIOD:
                    if '.' not in self.settings_edit_buffer and len(self.settings_edit_buffer) < 12:
                        self.settings_edit_buffer += '.'
                elif event.key == pygame.K_MINUS:
                    if '-' not in self.settings_edit_buffer and len(self.settings_edit_buffer) < 12:
                        self.settings_edit_buffer += '-'
                elif pygame.K_0 <= event.key <= pygame.K_9:
                    if len(self.settings_edit_buffer) < 12:
                        self.settings_edit_buffer += chr(event.key)
                return

        # ESC 关闭对话框（取消）
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.settings_editing_action:
                # 退出录制模式
                self.settings_editing_action = None
            else:
                # 关闭对话框，恢复备份
                self.keybindings = dict(self._settings_backup_keybindings)
                self.gather_params = dict(getattr(self, '_settings_backup_gather', self.gather_params))
                self.gather_enabled = dict(getattr(self, '_settings_backup_gather_enabled', self.gather_enabled))
                self.settings_editing_value = None
                self.show_settings_dialog = False
            return

        # 快捷键录制模式
        if self.settings_editing_action and event.type == pygame.KEYDOWN:
            # 忽略单独的修饰键按下
            if event.key in (pygame.K_LCTRL, pygame.K_RCTRL,
                             pygame.K_LALT, pygame.K_RALT,
                             pygame.K_LSHIFT, pygame.K_RSHIFT):
                return

            # 解析 event.mod 获取实际按下的修饰键
            modifiers = []
            if event.mod & pygame.KMOD_CTRL:
                modifiers.append('ctrl')
            if event.mod & pygame.KMOD_ALT:
                modifiers.append('alt')
            if event.mod & pygame.KMOD_SHIFT:
                modifiers.append('shift')

            # 将 pygame 按键映射回配置 key 名
            key_reverse_map = {
                pygame.K_SPACE: 'space', pygame.K_UP: 'up', pygame.K_DOWN: 'down',
                pygame.K_LEFT: 'left', pygame.K_RIGHT: 'right',
                pygame.K_RETURN: 'return', pygame.K_ESCAPE: 'escape',
                pygame.K_TAB: 'tab', pygame.K_BACKSPACE: 'backspace',
                pygame.K_DELETE: 'delete', pygame.K_HOME: 'home', pygame.K_END: 'end',
                pygame.K_PAGEUP: 'pageup', pygame.K_PAGEDOWN: 'pagedown',
                pygame.K_INSERT: 'insert',
                pygame.K_F1: 'f1', pygame.K_F2: 'f2', pygame.K_F3: 'f3', pygame.K_F4: 'f4',
                pygame.K_F5: 'f5', pygame.K_F6: 'f6', pygame.K_F7: 'f7', pygame.K_F8: 'f8',
                pygame.K_F9: 'f9', pygame.K_F10: 'f10', pygame.K_F11: 'f11', pygame.K_F12: 'f12',
            }
            if event.key in key_reverse_map:
                key_name = key_reverse_map[event.key]
            else:
                key_name = chr(event.key).lower() if 0 <= event.key < 128 else None

            if key_name:
                self.keybindings[self.settings_editing_action] = {
                    'key': key_name,
                    'modifiers': modifiers
                }
            self.settings_editing_action = None
            return

        # 鼠标事件
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # 聚拢参数编辑中：点击当前输入框之外 → 先提交（避免卡在编辑状态）
            if getattr(self, 'settings_editing_value', None):
                ekey = self.settings_editing_value
                erects = getattr(self, '_settings_gather_rects', {}).get(ekey)
                ebox = erects.get('box') if isinstance(erects, dict) else None
                if ebox is None or not ebox.collidepoint(mx, my):
                    self._commit_gather_value(ekey)

            # Tab 切换
            if hasattr(self, '_settings_tab_kb_rect') and self._settings_tab_kb_rect.collidepoint(mx, my):
                self.settings_active_tab = 'keybindings'
                self.settings_editing_action = None
                self.settings_editing_value = None
                self._settings_scroll = 0
                return
            if hasattr(self, '_settings_tab_anim_rect') and self._settings_tab_anim_rect.collidepoint(mx, my):
                self.settings_active_tab = 'animation'
                self.settings_editing_action = None
                self.settings_editing_value = None
                self._settings_scroll = 0
                return
            if hasattr(self, '_settings_tab_solver_rect') and self._settings_tab_solver_rect.collidepoint(mx, my):
                self.settings_active_tab = 'solver'
                self.settings_editing_action = None
                self.settings_editing_value = None
                self._settings_scroll = 0
                return
            if hasattr(self, '_settings_tab_gather_rect') and self._settings_tab_gather_rect.collidepoint(mx, my):
                self.settings_active_tab = 'gather'
                self.settings_editing_action = None
                self.settings_editing_value = None
                self._settings_scroll = 0
                return
            if hasattr(self, '_settings_tab_file_rect') and self._settings_tab_file_rect.collidepoint(mx, my):
                self.settings_active_tab = 'file'
                self.settings_editing_action = None
                self.settings_editing_value = None
                self._settings_scroll = 0
                return
            if hasattr(self, '_settings_tab_control_rect') and self._settings_tab_control_rect.collidepoint(mx, my):
                self.settings_active_tab = 'control'
                self.settings_editing_action = None
                self.settings_editing_value = None
                self._settings_scroll = 0
                return

            # 文件 Tab：存档只读开关
            if self.settings_active_tab == 'file' and hasattr(self, '_settings_readonly_toggle_rect'):
                if self._settings_readonly_toggle_rect.collidepoint(mx, my):
                    self.save_readonly_flag = not self.save_readonly_flag
                    status = '开' if self.save_readonly_flag else '关'
                    self.macro_notify_msg = f"存档只读：{status}"
                    self.macro_notify_timer = 90
                    return

            # 文件 Tab：防止覆盖开关
            if self.settings_active_tab == 'file' and hasattr(self, '_settings_prevent_overwrite_rect'):
                if self._settings_prevent_overwrite_rect.collidepoint(mx, my):
                    self.prevent_overwrite_flag = not self.prevent_overwrite_flag
                    status = '开' if self.prevent_overwrite_flag else '关'
                    self.macro_notify_msg = f"防止覆盖：{status}"
                    self.macro_notify_timer = 90
                    return

            # 快捷键 Tab：点击按键区域进入录制模式
            if self.settings_active_tab == 'keybindings' and hasattr(self, '_settings_key_rects'):
                for action, rect in self._settings_key_rects.items():
                    if rect.collidepoint(mx, my):
                        self.settings_editing_action = action
                        return
                # 点击了其他区域，退出录制模式
                self.settings_editing_action = None

            # 动画 Tab：开关按钮
            if self.settings_active_tab == 'animation' and hasattr(self, '_settings_anim_toggle_rect'):
                if self._settings_anim_toggle_rect.collidepoint(mx, my):
                    self.animation_enabled = not self.animation_enabled
                    if not self.animation_enabled and self.animating:
                        self.commit_animation()
                    status = '开' if self.animation_enabled else '关'
                    self.macro_notify_msg = f"滑动动画：{status}"
                    self.macro_notify_timer = 90
                    return

            # 动画 Tab：选中动画开关
            if self.settings_active_tab == 'animation' and hasattr(self, '_settings_sel_anim_toggle_rect'):
                if self._settings_sel_anim_toggle_rect.collidepoint(mx, my):
                    self.selection_animation_enabled = not self.selection_animation_enabled
                    if not self.selection_animation_enabled:
                        self._clear_sel_anim()
                    status = '开' if self.selection_animation_enabled else '关'
                    self.macro_notify_msg = f"选中动画：{status}"
                    self.macro_notify_timer = 90
                    return

            # 动画 Tab：分组着色器开关
            if self.settings_active_tab == 'animation' and hasattr(self, '_settings_coloring_toggle_rect'):
                if self._settings_coloring_toggle_rect.collidepoint(mx, my):
                    self.coloring_enabled = not self.coloring_enabled
                    status = '开' if self.coloring_enabled else '关'
                    self.macro_notify_msg = f"分组着色：{status}"
                    self.macro_notify_timer = 90
                    return

            # 动画 Tab：悬停连锁提示开关
            if self.settings_active_tab == 'animation' and hasattr(self, '_settings_chain_toggle_rect'):
                if self._settings_chain_toggle_rect.collidepoint(mx, my):
                    self.chain_hint_enabled = not self.chain_hint_enabled
                    status = '开' if self.chain_hint_enabled else '关'
                    self.macro_notify_msg = f"悬停连锁提示：{status}"
                    self.macro_notify_timer = 90
                    return

            # 控制 Tab：三种模式开关（独立布尔，可任意组合）
            if self.settings_active_tab == 'control':
                if hasattr(self, '_settings_ctrl_single_rect') and self._settings_ctrl_single_rect.collidepoint(mx, my):
                    if getattr(self, 'mi_mode', False) and not self.control_single_touch:
                        # 米字格按冻结决策只做两次触控 + 虚拟键盘：不许打开
                        self.macro_notify_msg = "米字格不使用单次触控（请用两次触控 + 虚拟键盘）"
                        self.macro_notify_timer = 120
                        return
                    self.control_single_touch = not self.control_single_touch
                    status = '开' if self.control_single_touch else '关'
                    self.macro_notify_msg = f"单次触控：{status}"
                    self.macro_notify_timer = 90
                    return
                if hasattr(self, '_settings_ctrl_two_rect') and self._settings_ctrl_two_rect.collidepoint(mx, my):
                    self.control_two_touch = not self.control_two_touch
                    status = '开' if self.control_two_touch else '关'
                    self.macro_notify_msg = f"两次触控：{status}"
                    self.macro_notify_timer = 90
                    return
                if hasattr(self, '_settings_ctrl_kb_rect') and self._settings_ctrl_kb_rect.collidepoint(mx, my):
                    self.control_mouse_kb = not self.control_mouse_kb
                    status = '开' if self.control_mouse_kb else '关'
                    self.macro_notify_msg = f"鼠标键盘：{status}"
                    self.macro_notify_timer = 90
                    return

            # 动画 Tab：滑动条
            if self.settings_active_tab == 'animation' and hasattr(self, '_settings_slider_knob_rect'):
                if self._settings_slider_knob_rect.collidepoint(mx, my) or \
                   (hasattr(self, '_settings_slider_track_rect') and self._settings_slider_track_rect.collidepoint(mx, my)):
                    self._settings_slider_dragging = True
                    self._update_settings_slider(mx)
                    return

            # 滚动条拖拽开始
            sb = getattr(self, '_settings_scrollbar_rect', None)
            kn = getattr(self, '_settings_scrollbar_knob', None)
            if sb and kn and kn.collidepoint(mx, my):
                self._settings_scrollbar_dragging = True
                self._settings_scrollbar_drag_start = (mx, my)
                self._settings_scrollbar_drag_orig = self._settings_scroll
                return
            if sb and sb.collidepoint(mx, my):
                # 点击滚动条轨道：跳到对应位置
                self._settings_scrollbar_dragging = True
                self._settings_scrollbar_drag_start = (mx, my)
                self._settings_scrollbar_drag_orig = self._settings_scroll
                # 立即更新
                track = sb
                if track.height > 0:
                    ratio = (my - track.y) / track.height
                    max_scroll = getattr(self, '_settings_max_scroll', 0)
                    self._settings_scroll = max(0, min(max_scroll, int(ratio * max_scroll)))
                return

            # 求解器 Tab：点击算法选择
            if self.settings_active_tab == 'solver' and hasattr(self, '_settings_solver_rects'):
                for algo_key, rect in self._settings_solver_rects.items():
                    if rect.collidepoint(mx, my):
                        self.solver_algorithm = algo_key
                        # 操作提示
                        from solver import SOLVER_ALGORITHMS
                        algo_name = SOLVER_ALGORITHMS.get(algo_key, ('求解器',))[0].strip()
                        self.macro_notify_msg = f"求解算法：{algo_name}"
                        self.macro_notify_timer = 120
                        return

            # 聚拢参数 Tab：开关 / 输入框 / -/+ 按钮
            if self.settings_active_tab == 'gather' and hasattr(self, '_settings_gather_rects'):
                for key, rects in self._settings_gather_rects.items():
                    if not isinstance(rects, dict):
                        continue  # 容错：跳过结构异常的旧 rect 数据
                    spec = None
                    for k, s in self._gather_param_specs:
                        if k == key:
                            spec = s
                            break
                    if not spec:
                        continue
                    _label, _vdef, vmin, vmax, vstep, _desc = spec
                    enabled = self.gather_enabled.get(key, True)
                    # 启用/禁用开关
                    tgl = rects.get('toggle')
                    if tgl is not None and tgl.collidepoint(mx, my):
                        new_state = not enabled
                        self.gather_enabled[key] = new_state
                        self.settings_editing_value = None
                        self.macro_notify_msg = f"{_label}：{'已启用' if new_state else '已禁用（不设限）'}"
                        self.macro_notify_timer = 90
                        return
                    # 输入框：进入手动编辑
                    box = rects.get('box')
                    if box is not None and box.collidepoint(mx, my):
                        val = self.gather_params.get(key, vmin)
                        if key in ('max_steps', 'patience'):
                            buf = str(int(val))
                        else:
                            buf = f"{val:g}"
                        self.settings_editing_value = key
                        self.settings_edit_buffer = buf
                        return
                    if not enabled:
                        continue  # 禁用时 −/+ 不可用
                    dec = rects.get('dec')
                    if dec is not None and dec.collidepoint(mx, my):
                        val = self.gather_params.get(key, vmin)
                        new_val = max(vmin, round(val - vstep, 6))
                        self.gather_params[key] = new_val
                        self.macro_notify_msg = f"参数已调整（未保存，点确定生效）"
                        self.macro_notify_timer = 90
                        return
                    inc = rects.get('inc')
                    if inc is not None and inc.collidepoint(mx, my):
                        val = self.gather_params.get(key, vmin)
                        new_val = min(vmax, round(val + vstep, 6))
                        self.gather_params[key] = new_val
                        self.macro_notify_msg = f"参数已调整（未保存，点确定生效）"
                        self.macro_notify_timer = 90
                        return

            # 确定按钮
            if hasattr(self, '_settings_ok_btn') and self._settings_ok_btn.collidepoint(mx, my):
                self._apply_settings()
                return

            # 取消按钮
            if hasattr(self, '_settings_cancel_btn') and self._settings_cancel_btn.collidepoint(mx, my):
                self.keybindings = dict(self._settings_backup_keybindings)
                self.gather_params = dict(getattr(self, '_settings_backup_gather', self.gather_params))
                self.gather_enabled = dict(getattr(self, '_settings_backup_gather_enabled', self.gather_enabled))
                self.settings_editing_value = None
                self.show_settings_dialog = False
                self.settings_editing_action = None
                return

            # 恢复默认按钮
            if hasattr(self, '_settings_reset_btn') and self._settings_reset_btn.collidepoint(mx, my):
                from gui.file_ops import DEFAULT_KEYBINDINGS
                self.keybindings = dict(DEFAULT_KEYBINDINGS)
                self.settings_editing_action = None
                self.settings_editing_value = None
                self._update_menu_shortcut_texts()
                # 恢复聚拢参数默认值
                if hasattr(self, '_gather_param_specs'):
                    for k, (_label, vdef, _vmin, _vmax, _vstep, _desc) in self._gather_param_specs:
                        self.gather_params[k] = vdef
                        self.gather_enabled[k] = True
                    self.macro_notify_msg = "已恢复默认参数"
                    self.macro_notify_timer = 90
                # 恢复控制模式默认值（三种模式全开；米字格仍禁单次触控）
                self.control_single_touch = not getattr(self, 'mi_mode', False)
                self.control_two_touch = True
                self.control_mouse_kb = True
                if getattr(self, 'mi_mode', False):
                    self.macro_notify_msg = "已恢复默认参数（米字格保持关闭单次触控）"
                    self.macro_notify_timer = 120
                return

        # 鼠标释放
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._settings_slider_dragging = False
            self._settings_scrollbar_dragging = False

        # 鼠标拖动滑动条 / 滚动条
        if event.type == pygame.MOUSEMOTION:
            if getattr(self, '_settings_slider_dragging', False):
                mx, my = event.pos
                self._update_settings_slider(mx)
            if getattr(self, '_settings_scrollbar_dragging', False):
                mx, my = event.pos
                self._update_settings_scrollbar(mx, my)

        # 鼠标滚轮（设置对话框中）
        if event.type == pygame.MOUSEWHEEL:
            if hasattr(self, '_settings_scrollbar_rect') and self._settings_scrollbar_rect:
                self._settings_scroll = max(0, min(
                    getattr(self, '_settings_max_scroll', 0),
                    self._settings_scroll - event.y * 28
                ))

    def _update_settings_slider(self, mx):
        """根据鼠标X坐标更新设置对话框中的动画速度滑动条"""
        if not hasattr(self, '_settings_slider_track_rect'):
            return
        track = self._settings_slider_track_rect
        normalized = (mx - track.x) / track.width
        normalized = max(0.0, min(1.0, normalized))
        new_duration = int(100 + normalized * 900)
        if self.animating and self.animation_duration > 0:
            elapsed = pygame.time.get_ticks() - self.anim_start_time
            old_progress = elapsed / max(1, self.animation_duration)
            self.anim_start_time = pygame.time.get_ticks() - int(old_progress * new_duration)
        self.animation_duration = new_duration

    def _apply_settings(self):
        """确定按钮：保存设置并关闭对话框"""
        self.save_keybindings()
        self._update_menu_shortcut_texts()
        self.show_settings_dialog = False
        self.settings_editing_action = None
        self.settings_editing_value = None

    def _commit_gather_value(self, key):
        """提交聚拢参数输入框的手动输入值（Enter）"""
        spec = None
        for k, s in self._gather_param_specs:
            if k == key:
                spec = s
                break
        if not spec:
            self.settings_editing_value = None
            return
        _label, _vdef, vmin, vmax, _vstep, _desc = spec
        try:
            val = float(self.settings_edit_buffer.strip())
        except ValueError:
            self.settings_editing_value = None
            self.macro_notify_msg = "输入无效，已保留原值"
            self.macro_notify_timer = 90
            return
        if key in ('max_steps', 'patience'):
            val = int(val)
            vmin, vmax = int(vmin), int(vmax)
        val = max(vmin, min(vmax, val))
        self.gather_params[key] = round(val, 6)
        self.settings_editing_value = None
        self.macro_notify_msg = "参数已调整（未保存，点确定生效）"
        self.macro_notify_timer = 90

    def _handle_right_panel_switch(self, key: str):
        """处理右侧面板快捷开关点击（滑动动画/选中动画/着色/连锁/模式/逆序）"""
        if key == 'animation_enabled':
            self.animation_enabled = not self.animation_enabled
            if not self.animation_enabled and self.animating:
                self.commit_animation()
            status = '开' if self.animation_enabled else '关'
            self.macro_notify_msg = f"滑动动画：{status}"
        elif key == 'selection_animation_enabled':
            self.selection_animation_enabled = not self.selection_animation_enabled
            if not self.selection_animation_enabled:
                self._clear_sel_anim()
            status = '开' if self.selection_animation_enabled else '关'
            self.macro_notify_msg = f"选中动画：{status}"
        elif key == 'coloring_enabled':
            self.coloring_enabled = not self.coloring_enabled
            status = '开' if self.coloring_enabled else '关'
            self.macro_notify_msg = f"分组着色：{status}"
        elif key == 'chain_hint_enabled':
            self.chain_hint_enabled = not self.chain_hint_enabled
            status = '开' if self.chain_hint_enabled else '关'
            self.macro_notify_msg = f"悬停连锁提示：{status}"
        elif key == 'game_mode':
            self.toggle_game_mode()
            return  # toggle_game_mode 已设置提示
        elif key == 'macro_reverse_mode':
            self.macro_reverse_mode = not self.macro_reverse_mode
            status = '开' if self.macro_reverse_mode else '关'
            self.macro_notify_msg = f"逆序播放宏指令：{status}"
        self.macro_notify_timer = 90

    # ==================== 宏功能 ====================

    def _handle_macro_menu_click(self, index: int):
        """
        处理宏定义菜单项点击
        
        菜单项结构（由 renderer 动态生成）：
          0: 管理宏...
          1: 录制宏 / 停止录制（根据状态切换）
          2: 逆序播放模式开关
          3: 分隔线
          4+: 已保存的宏名称
        """
        macro_names = self.macro_manager.list_names()
        
        if index == 0:
            # 管理宏 — 打开管理对话框
            self.show_macro_manager_dialog = True
        elif index == 1:
            # 录制 / 停止录制
            if self.macro_recording:
                self._stop_macro_recording()
            else:
                self._start_macro_recording()
        elif index == 2:
            # 切换逆序播放模式
            self.macro_reverse_mode = not self.macro_reverse_mode
            status = '开' if self.macro_reverse_mode else '关'
            self.macro_notify_msg = f"逆序播放：{status}"
            self.macro_notify_timer = 90
        elif index >= 4:
            # 点击了某个宏名称（按当前逆序模式播放）
            macro_idx = index - 4
            if 0 <= macro_idx < len(macro_names):
                macro_name = macro_names[macro_idx]
                self._start_macro_execute(macro_name, reverse=self.macro_reverse_mode)

    def _start_macro_recording(self):
        """开始录制宏 — 等待玩家选择基准方块"""
        if self.macro_recording or self.macro_executing:
            return
        if self._timer_blocked():
            self.macro_notify_msg = "计时中无法使用宏"
            self.macro_notify_timer = 90
            return
        # 米字格：录下的动作与四族缝隙/八向不对应，禁止录制
        if self._mi_blocked('宏录制'):
            return
        self.macro_recording = True
        self.macro_recording_steps = []
        self.macro_record_base_point = None
        self.macro_notify_msg = "选中一个方块作为基准坐标"
        self.macro_notify_timer = 180
        self.macro_notify_persistent = True

    def _stop_macro_recording(self):
        """停止录制宏 — 弹出命名对话框"""
        if not self.macro_recording:
            return
        self.macro_recording = False
        if not self.macro_recording_steps:
            self.macro_record_base_point = None
            return
        # 弹出宏命名对话框
        self.show_macro_name_dialog = True
        self.macro_name_text_input = TextInput(f'宏_{len(self.macro_manager.list_names()) + 1}')
        self.macro_name_active = True

    def _save_macro_with_name(self, name: str):
        """用指定名称保存当前录制的宏"""
        from macro.macro import Macro
        if not name or not self.macro_recording_steps:
            return
        macro = Macro(
            name=name,
            recorded_step=self.current_step,
            base_point=list(self.macro_record_base_point),
            steps=self.macro_recording_steps,
        )
        self.macro_manager.save_macro(macro)
        self.macro_recording_steps = []
        self.macro_record_base_point = None

    def _record_macro_step(self, gap_type: str, gap_line: int, side: str,
                           direction: str, rep_cell: list = None):
        """
        在录制模式下记录一个操作步骤
        
        参数:
            gap_type: 'h' 或 'v'
            gap_line: 缝隙绝对行/列号
            side: 选中缝隙哪一侧
            direction: 滑动方向
            rep_cell: 该步移动分量的代表格绝对坐标 [row, col]（可为 None）
        """
        from macro.macro import MacroStep
        base_r, base_c = self.macro_record_base_point
        if gap_type == 'h':
            rel = gap_line - base_r
        else:
            rel = gap_line - base_c
        rep_rel = None
        if rep_cell is not None:
            rep_rel = [rep_cell[0] - base_r, rep_cell[1] - base_c]
        step = MacroStep(
            gap_type=gap_type,
            gap_line_rel=rel,
            side=side,
            direction=direction,
            step=self.current_step,
            rep_cell_rel=rep_rel,
        )
        self.macro_recording_steps.append(step)

    def _get_selected_side(self) -> str:
        """
        获取当前选中方块组相对于缝隙的方位
        
        返回: 'above'/'below' (h型缝隙) 或 'left'/'right' (v型缝隙)
        """
        if not self.selected_gap or not self.selected_block:
            return ''
        gap_type, gap_line = self.selected_gap
        br, bc = self.selected_block.location
        if gap_type == 'h':
            return 'above' if br <= gap_line else 'below'
        else:
            return 'left' if bc <= gap_line else 'right'

    def _start_macro_execute(self, macro_name: str, reverse: bool = False):
        """开始执行宏 — 等待玩家选择基准方块"""
        if self.macro_recording or self.macro_executing:
            return
        # 只读存档：禁止宏执行（会改变滑块组状态）
        if getattr(self, '_readonly_blocked', lambda: False)():
            return
        if self._timer_blocked():
            self.macro_notify_msg = "计时中无法使用宏"
            self.macro_notify_timer = 90
            return
        macro = self.macro_manager.get_macro(macro_name)
        if macro is None:
            return
        # 检查步长兼容性
        compatible, factor, reason = macro.check_step_compatibility(self.current_step)
        if not compatible:
            self.macro_error_msg = reason
            self.macro_error_timer = 60 * 3
            return
        self.macro_executing = True
        self.macro_selecting_base = True
        self.macro_exec_factor = factor
        self.macro_exec_name = macro_name
        self.macro_exec_reverse = reverse
        self.macro_exec_ops = []
        self.macro_exec_index = 0
        label = '（逆序）' if reverse else ''
        self.macro_notify_msg = f"选中一个方块作为基准坐标{label}"
        self.macro_notify_timer = 180
        self.macro_notify_persistent = True

    def _confirm_macro_execute(self, base_row: int, base_col: int):
        """玩家选好基准后，开始逐步执行宏"""
        from macro.macro import MacroManager
        macro = self.macro_manager.get_macro(self.macro_exec_name)
        if macro is None:
            self.macro_executing = False
            self.macro_selecting_base = False
            self.macro_notify_persistent = False
            return
        # 将所有相对步骤转换为绝对操作队列
        # 逆序播放：顺序反转 + 每步方向取反（同切割位置 + 同侧，操作级逆）
        DIR_INVERSE = {'w': 's', 's': 'w', 'a': 'd', 'd': 'a'}
        ops = []
        steps = reversed(macro.steps) if self.macro_exec_reverse else macro.steps
        for step in steps:
            if self.macro_exec_reverse:
                from macro.macro import MacroStep
                step = MacroStep(
                    step.gap_type, step.gap_line_rel, step.side,
                    DIR_INVERSE[step.direction], step.step,
                    rep_cell_rel=step.rep_cell_rel,
                )
            ops.extend(MacroManager.convert_to_absolute(
                step, base_row, base_col, self.current_step, self.macro_exec_factor
            ))
        self.macro_exec_ops = ops
        self.macro_exec_index = 0
        self.macro_selecting_base = False
        self.macro_notify_persistent = False
        # 开始执行第一个操作
        self._execute_next_macro_step()

    def _execute_next_macro_step(self):
        """执行宏队列中的下一个操作（无动画时用循环迭代，避免长解法递归爆栈）"""
        while True:
            # 用户取消检测：宏执行中途可按 ESC 中断
            if not self.macro_executing:
                self.macro_exec_ops = []
                self.macro_exec_index = 0
                return

            # 聚拢播放：每步实时刷新当前聚拢度
            if getattr(self, '_gather_info', None) is not None:
                self._update_gather_notify()

            if self.macro_exec_index >= len(self.macro_exec_ops):
                if getattr(self, '_gather_info', None) is not None:
                    self._finish_gather()
                else:
                    # 所有步骤执行完毕 — 显示成功通知
                    total_ops = len(self.macro_exec_ops)
                    macro_name = self.macro_exec_name
                    label = '逆序' if self.macro_exec_reverse else ''
                    self.macro_notify_msg = f'[{macro_name}] {label}执行成功：{total_ops}步'
                    self.macro_notify_timer = 180  # 3秒 (60fps)
                # 所有步骤执行完毕
                # 梯度聚拢：后续阶段由后台流水线推送，无需在此启动
                self.macro_executing = False
                self.macro_exec_ops = []
                self.macro_exec_index = 0
                # 宏执行（尤其关闭动画时）可能把滑块带出视野：执行完居中一次
                self.center_map()
                return

            op = self.macro_exec_ops[self.macro_exec_index]
            gap_type = op['gap_type']
            gap_line = op['gap_line']
            side = op['side']
            direction = op['direction']
            step = op['step']

            # 检查缝隙有效性
            if gap_type == 'h' and not self.game.is_valid_h_line(gap_line):
                self.macro_error_msg = f'宏在第 {self.macro_exec_index + 1} 步失败: 横向缝隙 {gap_line} 无效'
                self.macro_error_timer = 60 * 3
                self._set_macro_interrupted_notify()
                self.macro_executing = False
                self.macro_exec_ops = []
                return
            if gap_type == 'v' and not self.game.is_valid_v_line(gap_line):
                self.macro_error_msg = f'宏在第 {self.macro_exec_index + 1} 步失败: 纵向缝隙 {gap_line} 无效'
                self.macro_error_timer = 60 * 3
                self._set_macro_interrupted_notify()
                self.macro_executing = False
                self.macro_exec_ops = []
                return

            # 选中缝隙
            self.selected_gap = (gap_type, gap_line)
            for b in self.game.blocks:
                b.be_opted = False
            self.selected_block = None

            # 找到缝隙对应侧的任意一个方块（若有 rep_cell 则精确指定）
            if 'rep_cell' in op:
                rr, cc = op['rep_cell']
                target_block = self._find_block_by_cell(rr, cc)
                if target_block is None:
                    target_block = self._find_block_on_side(gap_type, gap_line, side)
            else:
                target_block = self._find_block_on_side(gap_type, gap_line, side)
            if target_block is None:
                self.macro_error_msg = f'宏在第 {self.macro_exec_index + 1} 步失败: 缝隙 {gap_type}{gap_line} {side} 侧无方块'
                self.macro_error_timer = 60 * 3
                self._set_macro_interrupted_notify()
                self.macro_executing = False
                self.macro_exec_ops = []
                return

            # opt() 选中方块组
            self.game.opt(gap_type, gap_line, target_block)
            self.selected_block = target_block

            # 验证移动
            final_positions = self.game.try_move(direction, step)
            if not final_positions:
                self.macro_error_msg = f'宏在第 {self.macro_exec_index + 1} 步失败: 方向 {direction} 不可移动'
                self.macro_error_timer = 60 * 3
                self._set_macro_interrupted_notify()
                self.macro_executing = False
                self.macro_exec_ops = []
                return

            # 构建 move_info
            selected = [b for b in self.game.blocks if b.be_opted]
            move_info = {
                'gap_type': gap_type,
                'gap_line': gap_line,
                'direction': direction,
                'step': step,
                'moved_positions': [list(b.location) for b in selected],
            }
            self._pending_move_info = move_info

            # 播放动画或直接提交（无动画时循环执行后续步骤）
            if self.animation_enabled and self.animation_duration > 0:
                self.start_animation(selected, final_positions)
                return  # 动画结束由 commit_animation 中宏路径继续

            self.game.commit_move(final_positions)
            self.step_count += 1
            # 宏播放逐步留档（macro_executing=True → 不合并，保持每步可撤销）
            self.game_history.save_snapshot(self.game, move_info,
                                            self._move_merge_key())
            self._pending_move_info = None
            self.macro_exec_index += 1
            self._maybe_show_solved_popup()

    def _update_gather_notify(self):
        """聚拢播放中：实时刷新当前聚拢度到通知栏。"""
        from solver.ml.gather_solver import gather_metrics
        coords = frozenset((b.location[0], b.location[1]) for b in self.game.blocks)
        met = gather_metrics(coords, self.game.m, self.game.n)
        h, w = met['bbox']
        idx = self.macro_exec_index
        total = len(self.macro_exec_ops)
        self.macro_notify_msg = (
            f"聚拢 {idx}/{total} · 聚拢度 {met['score']*100:.1f}% · {h}×{w}"
        )
        self.macro_notify_timer = 180
        self.macro_notify_persistent = True

    def _finish_gather(self):
        """聚拢播放结束：显示起点→终点摘要与停机原因。"""
        info = self._gather_info
        s = info.get('start', {})
        e = info.get('end', {})
        total = len(self.macro_exec_ops)
        reason = info.get('reason', '')
        reason_text = {
            'solved': '已还原',
            'target': '达到目标聚拢度',
            'no_improve': '停滞无改进',
            'max_steps': '步数上限耗尽',
            'timeout': '达到时间上限',
            'cancelled': '已取消',
            'stuck': '无新状态可探索',
            'no_candidates': '无可移动动作',
            'invalid_action': '动作无效',
            'stages_exhausted': '阶段耗尽',
        }.get(reason, reason or '完成')
        sh, sw = s.get('bbox', (0, 0))
        eh, ew = e.get('bbox', (0, 0))
        gs = getattr(self, '_gradient_state', None)
        if gs is not None:
            # 梯度聚拢：逐阶段播报；后续阶段由后台流水线自动推送
            gstage = info.get('gradient_stage')
            gtotal = info.get('gradient_total') or gs.get('max_stages', 4)
            cur = gstage if gstage else (gs.get('stage_idx', 0) + 1)
            if info.get('solved'):
                self.macro_notify_msg = f"梯度聚拢：已复原！共{total}步"
                self._gradient_state = None
            elif gstage is not None and gstage >= gtotal:
                self.macro_notify_msg = (
                    f"梯度聚拢：{gtotal}阶段未复原 · "
                    f"聚拢度 {s.get('score', 0)*100:.1f}%→{e.get('score', 0)*100:.1f}%"
                )
                self._gradient_state = None
            else:
                self.macro_notify_msg = (
                    f"梯度聚拢 第{cur}/{gtotal}阶段完成（{reason_text}）· "
                    f"{total}步 · 聚拢度 {s.get('score', 0)*100:.1f}%→{e.get('score', 0)*100:.1f}%"
                )
        elif info.get('solved'):
            self.macro_notify_msg = f"聚拢完成：已复原（{total}步）"
        else:
            self.macro_notify_msg = (
                f"聚拢完成（{reason_text}）· {total}步 · "
                f"聚拢度 {s.get('score', 0)*100:.1f}%→{e.get('score', 0)*100:.1f}% "
                f"· 边界盒 {sh}×{sw}→{eh}×{ew}"
            )
        self.macro_notify_timer = 240
        self.macro_notify_persistent = False
        self._gather_info = None

    def _set_macro_interrupted_notify(self):
        """设置宏执行中断通知消息"""
        total_ops = len(self.macro_exec_ops)
        executed = self.macro_exec_index  # 已执行的步数（index 指向的是失败的那一步，之前的是已执行的）
        macro_name = self.macro_exec_name
        self.macro_notify_msg = f'[{macro_name}] 执行中断：{executed}/{total_ops}步'
        self.macro_notify_timer = 180  # 3秒 (60fps)
        self.macro_notify_persistent = False
        self._gather_info = None  # 中断时清空聚拢状态，避免污染后续宏
        self._gradient_state = None  # 中断时终止梯度聚拢后续阶段
        # 停掉后台梯度流水线，丢弃已排队阶段
        self._auto_solve_cancel = True
        self._gradient_gen += 1
        self._drain_gradient_queue()

    def _find_block_on_side(self, gap_type: str, gap_line: int, side: str):
        """
        在缝隙的指定侧找到一个方块
        
        参数:
            gap_type: 'h' 或 'v'
            gap_line: 缝隙行/列号
            side: 'above'/'below' (h) 或 'left'/'right' (v)
        返回:
            Block 对象或 None
        """
        for block in self.game.blocks:
            r, c = block.location
            if gap_type == 'h':
                if side == 'above' and r <= gap_line:
                    return block
                if side == 'below' and r > gap_line:
                    return block
            else:
                if side == 'left' and c <= gap_line:
                    return block
                if side == 'right' and c > gap_line:
                    return block
        return None

    def _find_block_by_cell(self, row: int, col: int):
        """根据精确坐标查找方块，供查表求解器指定代表方块。"""
        for block in self.game.blocks:
            if block.location[0] == row and block.location[1] == col:
                return block
        return None

    def handle_macro_base_selection_click(self, x: int, y: int) -> bool:
        """
        处理宏基准选择时的点击事件
        
        返回: True 如果事件被处理
        """
        if self.macro_selecting_base:
            cell = self.get_cell_at_pos(x, y)
            if cell:
                r, c = cell
                self._confirm_macro_execute(r, c)
            return True
        if self.macro_recording and self.macro_record_base_point is None:
            cell = self.get_cell_at_pos(x, y)
            if cell:
                r, c = cell
                self.macro_record_base_point = [r, c]
                # 清除基准选择提示
                self.macro_notify_msg = f"基准坐标 ({r}, {c}) 已选定，开始录制"
                self.macro_notify_timer = 120
                self.macro_notify_persistent = False
            return True
        return False

    def _handle_macro_manager_click(self, x: int, y: int) -> bool:
        """
        处理宏管理对话框内的点击事件
        
        返回: True 如果事件被处理
        """
        if not getattr(self, 'show_macro_manager_dialog', False):
            return False
        
        # 检查是否点击了对话框外 — 关闭
        dlg_rect = getattr(self, 'macro_manager_dialog_rect', None)
        if dlg_rect and not dlg_rect.collidepoint(x, y):
            self.show_macro_manager_dialog = False
            return True
        
        # 检查关闭按钮
        close_btn = getattr(self, '_macro_mgr_close_btn', None)
        if close_btn and close_btn.collidepoint(x, y):
            self.show_macro_manager_dialog = False
            return True
        
        # 检查宏列表项的删除/重命名按钮
        macro_names = self.macro_manager.list_names()
        
        # 检查滚动按钮
        if hasattr(self, '_macro_mgr_scroll_up_rect') and self._macro_mgr_scroll_up_rect and self._macro_mgr_scroll_up_rect.collidepoint(x, y):
            self._macro_mgr_scroll = max(0, getattr(self, '_macro_mgr_scroll', 0) - 1)
            return True
        if hasattr(self, '_macro_mgr_scroll_down_rect') and self._macro_mgr_scroll_down_rect and self._macro_mgr_scroll_down_rect.collidepoint(x, y):
            max_scroll = max(0, len(macro_names) - getattr(self, '_macro_mgr_visible_count', 5))
            self._macro_mgr_scroll = min(max_scroll, getattr(self, '_macro_mgr_scroll', 0) + 1)
            return True
        
        # 检查每项的操作按钮
        if hasattr(self, '_macro_mgr_item_rects'):
            for item_data in self._macro_mgr_item_rects:
                rect = item_data.get('row')
                if rect and rect.collidepoint(x, y):
                    idx = item_data.get('index', -1)
                    if 0 <= idx < len(macro_names):
                        # 检查是否点了重命名/删除/逆序按钮
                        rename_rect = item_data.get('rename')
                        delete_rect = item_data.get('delete')
                        inverse_rect = item_data.get('inverse')
                        if rename_rect and rename_rect.collidepoint(x, y):
                            self._start_macro_rename(idx)
                            return True
                        elif delete_rect and delete_rect.collidepoint(x, y):
                            self._delete_macro(idx)
                            return True
                        elif inverse_rect and inverse_rect.collidepoint(x, y):
                            self.show_macro_manager_dialog = False
                            self._start_macro_execute(macro_names[idx], reverse=True)
                            return True
                    break
        
        return True

    def _start_macro_rename(self, index: int):
        """开始重命名宏"""
        macro_names = self.macro_manager.list_names()
        if 0 <= index < len(macro_names):
            self.macro_renaming_index = macro_names[index]
            self.macro_name_text_input = TextInput(macro_names[index])
            self.show_macro_name_dialog = True
            self.macro_name_active = True

    def _delete_macro(self, index: int):
        """删除指定索引的宏"""
        macro_names = self.macro_manager.list_names()
        if 0 <= index < len(macro_names):
            self.macro_manager.delete_macro(macro_names[index])

    def handle_macro_name_dialog_events(self, event) -> bool:
        """
        处理宏命名对话框事件
        
        返回: True 如果事件被处理
        """
        if not getattr(self, 'show_macro_name_dialog', False):
            return False
        
        # macro_renaming_index: None 表示新建模式，字符串表示重命名旧名称
        rename_old_name = getattr(self, 'macro_renaming_index', None)
        is_renaming = isinstance(rename_old_name, str) and rename_old_name
        
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                # 确认命名
                name = self.macro_name_text_input.text.strip()
                if name:
                    if is_renaming:
                        # 重命名模式
                        self.macro_manager.rename_macro(rename_old_name, name)
                        self.macro_renaming_index = None
                    else:
                        # 新建模式
                        self._save_macro_with_name(name)
                self.show_macro_name_dialog = False
                return True
            elif event.key == pygame.K_ESCAPE:
                # 取消
                if not is_renaming:
                    self.macro_recording_steps = []
                    self.macro_record_base_point = None
                self.macro_renaming_index = None
                self.show_macro_name_dialog = False
                return True
            # 委托给 TextInput 处理其他按键（支持长按重复）
            if self.macro_name_text_input.handle_event(event):
                return True

        elif event.type == pygame.KEYUP:
            # 停止长按重复
            if self.macro_name_text_input.handle_event(event):
                return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # 让 TextInput 停止拖拽选中
            input_rect = getattr(self, '_macro_name_input_rect', None)
            font = getattr(self, 'input_font', None)
            if input_rect and font:
                self.macro_name_text_input.handle_event(event, font, input_rect)

        elif event.type == pygame.MOUSEMOTION:
            # 拖拽选中
            input_rect = getattr(self, '_macro_name_input_rect', None)
            font = getattr(self, 'input_font', None)
            if input_rect and font:
                if self.macro_name_text_input.handle_event(event, font, input_rect):
                    return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            # 检查确定按钮
            ok_btn = getattr(self, '_macro_name_ok_btn', None)
            if ok_btn and ok_btn.collidepoint(mx, my):
                name = self.macro_name_text_input.text.strip()
                if name:
                    if is_renaming:
                        self.macro_manager.rename_macro(rename_old_name, name)
                        self.macro_renaming_index = None
                    else:
                        self._save_macro_with_name(name)
                self.show_macro_name_dialog = False
                return True
            # 检查取消按钮
            cancel_btn = getattr(self, '_macro_name_cancel_btn', None)
            if cancel_btn and cancel_btn.collidepoint(mx, my):
                if not is_renaming:
                    self.macro_recording_steps = []
                    self.macro_record_base_point = None
                self.macro_renaming_index = None
                self.show_macro_name_dialog = False
                return True
            # 点击输入框区域则激活输入并定位光标（支持拖拽选中）
            input_rect = getattr(self, '_macro_name_input_rect', None)
            if input_rect and input_rect.collidepoint(mx, my):
                self.macro_name_active = True
                font = getattr(self, 'input_font', None)
                if font and hasattr(self, 'macro_name_text_input'):
                    self.macro_name_text_input.handle_event(event, font, input_rect)
                return True
            # 点击外部关闭对话框
            if not is_renaming:
                self.macro_recording_steps = []
                self.macro_record_base_point = None
            self.macro_renaming_index = None
            self.show_macro_name_dialog = False
            return True
        
        return False
