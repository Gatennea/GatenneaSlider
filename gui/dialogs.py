# -*- coding: utf-8 -*-
"""
对话框相关 Mixin

包含：
- draw_help_dialog: 帮助对话框
- draw_custom_puzzle_dialog: 自定义谜题对话框
- handle_custom_dialog_events: 自定义对话框事件处理
- pygame 文件对话框（替代 tkinter）
"""

import pygame
import os
import sys
from gui.text_input import TextInput


class PygameFileDialog:
    """
    基于 Pygame 的文件选择对话框
    
    替代 tkinter.filedialog，提供打开/保存文件功能。
    支持目录导航、文件列表、输入文件名。
    """
    
    def __init__(self, screen, font, title_font, small_font, colors):
        """
        初始化文件对话框
        
        参数：
            screen: pygame 屏幕对象
            font: 普通字体
            title_font: 标题字体
            small_font: 小字体
            colors: 颜色配置字典
        """
        self.screen = screen
        self.font = font
        self.title_font = title_font
        self.small_font = small_font
        self.colors = colors
        
        # 对话框状态
        self.active = False
        self.mode = 'open'  # 'open' 或 'save'
        self.title = ''
        self.current_dir = ''
        self.file_list = []
        self.selected_index = -1
        self.scroll_offset = 0
        self.text_input = TextInput('')
        self.input_active = True
        self.result = None
        self.extensions = ['*']
        self.initial_file = ''
        
        # UI 布局
        self.dialog_rect = None
        self.file_list_rect = None
        self.input_rect = None
        self.ok_btn = None
        self.cancel_btn = None
        self.up_btn = None
        self.scrollbar_rect = None
        self.scrollbar_knob_rect = None
        self.item_height = 24
        self.visible_items = 12
        
        # 拖拽滚动条
        self.scrollbar_dragging = False
        self.scrollbar_drag_offset = 0
    
    def show(self, mode='open', title='打开', initial_dir=None, 
             extensions=None, initial_file=''):
        """
        显示文件对话框
        
        参数：
            mode: 'open' 或 'save'
            title: 对话框标题
            initial_dir: 初始目录
            extensions: 文件扩展名过滤列表，如 ['json']
            initial_file: 初始文件名（保存模式）
        
        返回：
            str 或 None: 选择的文件路径，取消返回 None
        """
        self.active = True
        self.mode = mode
        self.title = title
        self.current_dir = initial_dir or os.path.expanduser('~')
        self.extensions = extensions or ['json', '*']
        self.initial_file = initial_file
        self.text_input.set_text(initial_file if mode == 'save' else '')
        self.selected_index = -1
        self.scroll_offset = 0
        self.result = None
        self.input_active = True
        self.scrollbar_dragging = False
        
        self._refresh_file_list()
        self._calculate_layout()
        
        return None  # 实际结果通过 run() 获取
    
    def _calculate_layout(self):
        """计算对话框布局"""
        sw, sh = self.screen.get_size()
        dw = min(520, sw - 60)
        dh = min(440, sh - 60)
        dx = (sw - dw) // 2
        dy = (sh - dh) // 2
        self.dialog_rect = pygame.Rect(dx, dy, dw, dh)
        
        margin = 15
        # 文件列表区域
        list_top = dy + 55
        list_bottom = dy + dh - 95
        self.file_list_rect = pygame.Rect(dx + margin, list_top, dw - 2 * margin - 12, list_bottom - list_top)
        self.visible_items = max(1, self.file_list_rect.height // self.item_height)
        
        # 滚动条
        sb_x = self.file_list_rect.right + 2
        self.scrollbar_rect = pygame.Rect(sb_x, list_top, 10, list_bottom - list_top)
        
        # 文件名输入框
        input_top = dy + dh - 85
        self.input_rect = pygame.Rect(dx + margin, input_top, dw - 2 * margin, 28)
        
        # 按钮
        btn_y = dy + dh - 45
        btn_w = 70
        btn_h = 28
        self.ok_btn = pygame.Rect(dx + dw // 2 - btn_w - 10, btn_y, btn_w, btn_h)
        self.cancel_btn = pygame.Rect(dx + dw // 2 + 10, btn_y, btn_w, btn_h)
        
        # 上级目录按钮
        self.up_btn = pygame.Rect(dx + dw - margin - 60, dy + 25, 55, 22)
    
    @property
    def filename_input(self):
        """向后兼容：返回 text_input 的文本"""
        return self.text_input.text
    
    @filename_input.setter
    def filename_input(self, value):
        """向后兼容：设置 text_input 的文本"""
        self.text_input.text = value
        self.text_input.cursor_pos = len(value)

    def update(self, dt_ms: int):
        """更新文本输入闪烁（每帧调用）"""
        if self.active:
            self.text_input.update(dt_ms)

    def _refresh_file_list(self):
        """刷新文件列表"""
        self.file_list = []
        try:
            entries = sorted(os.listdir(self.current_dir), key=lambda x: (not os.path.isdir(os.path.join(self.current_dir, x)), x.lower()))
            for entry in entries:
                full_path = os.path.join(self.current_dir, entry)
                if os.path.isdir(full_path):
                    self.file_list.append((entry, True))  # (名称, 是否目录)
                else:
                    # 检查扩展名
                    if '*' in self.extensions:
                        self.file_list.append((entry, False))
                    else:
                        ext = os.path.splitext(entry)[1].lstrip('.')
                        if ext.lower() in [e.lower() for e in self.extensions]:
                            self.file_list.append((entry, False))
        except (PermissionError, OSError):
            pass
        self.scroll_offset = 0
        self.selected_index = -1
    
    def _update_scrollbar(self):
        """更新滚动条滑块位置"""
        if not self.scrollbar_rect:
            return
        total = len(self.file_list)
        if total <= self.visible_items:
            self.scrollbar_knob_rect = self.scrollbar_rect.copy()
            return
        knob_h = max(20, int(self.scrollbar_rect.height * self.visible_items / total))
        max_scroll = total - self.visible_items
        knob_y = self.scrollbar_rect.top + int((self.scrollbar_rect.height - knob_h) * self.scroll_offset / max_scroll)
        self.scrollbar_knob_rect = pygame.Rect(self.scrollbar_rect.x, knob_y, self.scrollbar_rect.width, knob_h)
    
    def handle_event(self, event):
        """
        处理事件
        
        返回：
            bool: 事件是否被处理
        """
        if not self.active:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            
            # 上级目录按钮
            if self.up_btn.collidepoint(mx, my):
                parent = os.path.dirname(self.current_dir)
                if parent and parent != self.current_dir:
                    self.current_dir = parent
                    self._refresh_file_list()
                return True
            
            # 文件列表点击
            if self.file_list_rect.collidepoint(mx, my):
                rel_y = my - self.file_list_rect.top
                idx = rel_y // self.item_height + self.scroll_offset
                if 0 <= idx < len(self.file_list):
                    self.selected_index = idx
                    name, is_dir = self.file_list[idx]
                    if is_dir:
                        # 双击进入目录（单击选中）
                        self.current_dir = os.path.join(self.current_dir, name)
                        self._refresh_file_list()
                    else:
                        self.text_input.set_text(name)
                return True
            
            # 滚动条点击
            if self.scrollbar_rect and self.scrollbar_rect.collidepoint(mx, my):
                if self.scrollbar_knob_rect and self.scrollbar_knob_rect.collidepoint(mx, my):
                    self.scrollbar_dragging = True
                    self.scrollbar_drag_offset = my - self.scrollbar_knob_rect.top
                else:
                    # 点击轨道跳转
                    total = len(self.file_list)
                    if total > self.visible_items:
                        ratio = (my - self.scrollbar_rect.top) / self.scrollbar_rect.height
                        self.scroll_offset = int(ratio * (total - self.visible_items))
                        self.scroll_offset = max(0, min(self.scroll_offset, total - self.visible_items))
                return True
            
            # 输入框点击 - 委托给 TextInput 处理（支持点击定位 + 拖拽选中）
            if self.input_rect.collidepoint(mx, my):
                self.input_active = True
                if self.text_input.handle_event(event, self.font, self.input_rect):
                    return True
            
            # 确定按钮
            if self.ok_btn.collidepoint(mx, my):
                self._confirm()
                return True
            
            # 取消按钮
            if self.cancel_btn.collidepoint(mx, my):
                self.result = None
                self.active = False
                return True
            
            # 点击对话框外部关闭
            if not self.dialog_rect.collidepoint(mx, my):
                self.result = None
                self.active = False
                return True
            
            return True
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.scrollbar_dragging = False
                # 同时让 TextInput 知道鼠标抬起
                if self.text_input.handle_event(event, self.font, self.input_rect):
                    pass

        elif event.type == pygame.MOUSEMOTION:
            if self.scrollbar_dragging:
                mx, my = event.pos
                total = len(self.file_list)
                if total > self.visible_items and self.scrollbar_rect:
                    rel_y = my - self.scrollbar_rect.top - self.scrollbar_drag_offset
                    ratio = max(0, min(1, rel_y / (self.scrollbar_rect.height - 20)))
                    self.scroll_offset = int(ratio * (total - self.visible_items))
                return True
            # 文本输入框的拖拽选中
            if self.text_input.handle_event(event, self.font, self.input_rect):
                return True
        
        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self.file_list_rect and self.file_list_rect.collidepoint(mx, my):
                total = len(self.file_list)
                self.scroll_offset -= event.y
                self.scroll_offset = max(0, min(self.scroll_offset, max(0, total - self.visible_items)))
                return True
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.result = None
                self.active = False
                return True
            elif event.key == pygame.K_RETURN:
                self._confirm()
                return True
            elif event.key == pygame.K_UP:
                if self.selected_index > 0:
                    self.selected_index -= 1
                    if self.selected_index < self.scroll_offset:
                        self.scroll_offset = self.selected_index
                return True
            elif event.key == pygame.K_DOWN:
                if self.selected_index < len(self.file_list) - 1:
                    self.selected_index += 1
                    if self.selected_index >= self.scroll_offset + self.visible_items:
                        self.scroll_offset = self.selected_index - self.visible_items + 1
                return True
            # 委托给 TextInput 处理其他按键（支持长按重复）
            if self.text_input.handle_event(event):
                return True

        elif event.type == pygame.KEYUP:
            # 停止长按重复
            if self.text_input.handle_event(event):
                return True

        return False
    
    def _confirm(self):
        """确认选择"""
        if self.mode == 'open':
            if self.selected_index >= 0 and self.selected_index < len(self.file_list):
                name, is_dir = self.file_list[self.selected_index]
                if is_dir:
                    self.current_dir = os.path.join(self.current_dir, name)
                    self._refresh_file_list()
                    return
                else:
                    self.result = os.path.join(self.current_dir, name)
            elif self.filename_input:
                path = os.path.join(self.current_dir, self.filename_input)
                if os.path.exists(path):
                    self.result = path
                else:
                    return
            else:
                return
        else:  # save
            def _ensure_json(name):
                if name and not name.lower().endswith('.json'):
                    return name + '.json'
                return name

            if self.filename_input:
                final_name = _ensure_json(self.filename_input)
                self.result = os.path.join(self.current_dir, final_name)
            elif self.selected_index >= 0 and self.selected_index < len(self.file_list):
                name, is_dir = self.file_list[self.selected_index]
                if is_dir:
                    self.current_dir = os.path.join(self.current_dir, name)
                    self._refresh_file_list()
                    return
                else:
                    final_name = _ensure_json(name)
                    self.filename_input = final_name
                    self.result = os.path.join(self.current_dir, final_name)
            else:
                return
        
        self.active = False
    
    def draw(self):
        """绘制文件对话框"""
        if not self.active:
            return
        
        # 半透明遮罩
        sw, sh = self.screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        
        dx, dy = self.dialog_rect.x, self.dialog_rect.y
        
        # 对话框背景
        pygame.draw.rect(self.screen, self.colors['dialog_bg'], self.dialog_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self.dialog_rect, 2, border_radius=8)
        
        # 标题
        title_surface = self.title_font.render(self.title, True, self.colors['dialog_title'])
        self.screen.blit(title_surface, (dx + 15, dy + 10))
        
        # 当前目录
        dir_text = self.small_font.render(self.current_dir, True, (150, 150, 150))
        # 截断过长路径
        max_dir_w = self.up_btn.left - dx - 20
        while dir_text.get_width() > max_dir_w and len(self.current_dir) > 10:
            self.current_dir = '...' + self.current_dir[4:]
            dir_text = self.small_font.render(self.current_dir, True, (150, 150, 150))
        self.screen.blit(dir_text, (dx + 15, dy + 32))
        
        # 上级目录按钮
        pygame.draw.rect(self.screen, self.colors['input_bg'], self.up_btn, border_radius=3)
        up_text = self.small_font.render("↑ 上级", True, self.colors['dialog_text'])
        up_rect = up_text.get_rect(center=self.up_btn.center)
        self.screen.blit(up_text, up_rect)
        
        # 文件列表背景
        pygame.draw.rect(self.screen, self.colors['input_bg'], self.file_list_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self.file_list_rect, 1, border_radius=4)
        
        # 文件列表项
        self._update_scrollbar()
        for i in range(self.visible_items):
            idx = i + self.scroll_offset
            if idx >= len(self.file_list):
                break
            name, is_dir = self.file_list[idx]
            y = self.file_list_rect.top + i * self.item_height
            item_rect = pygame.Rect(self.file_list_rect.left, y, self.file_list_rect.width, self.item_height)
            
            if idx == self.selected_index:
                pygame.draw.rect(self.screen, self.colors['menu_selected'], item_rect)
            
            # 目录用不同颜色
            if is_dir:
                prefix = "📁 "
                color = (100, 200, 255)
            else:
                prefix = "   "
                color = self.colors['dialog_text']
            
            text = self.small_font.render(prefix + name, True, color)
            text_rect = text.get_rect()
            text_rect.x = self.file_list_rect.left + 5
            text_rect.centery = y + self.item_height // 2
            
            # 裁剪到列表区域
            clip_rect = self.file_list_rect.clip(self.screen.get_rect())
            self.screen.set_clip(clip_rect)
            self.screen.blit(text, text_rect)
            self.screen.set_clip(None)
        
        # 滚动条
        if self.scrollbar_rect and len(self.file_list) > self.visible_items:
            pygame.draw.rect(self.screen, (60, 60, 60), self.scrollbar_rect, border_radius=3)
            if self.scrollbar_knob_rect:
                knob_color = self.colors['button_hover'] if self.scrollbar_dragging else self.colors['button_bg']
                pygame.draw.rect(self.screen, knob_color, self.scrollbar_knob_rect, border_radius=3)
        
        # 文件名输入框
        input_label = self.small_font.render("文件名:", True, self.colors['dialog_text'])
        self.screen.blit(input_label, (self.input_rect.left, self.input_rect.top - 16))
        
        bg_color = self.colors['input_active'] if self.input_active else self.colors['input_bg']
        pygame.draw.rect(self.screen, bg_color, self.input_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self.input_rect, 1, border_radius=4)
        
        # 使用 TextInput 获取显示文本和光标位置（支持长文本滚动）
        max_width = self.input_rect.width - 10
        display_text, cursor_visible = self.text_input.get_display_text(
            self.font, max_width, '', self.input_active)
        cursor_offset = self.text_input.get_cursor_offset(self.font)
        
        input_text_surface = self.font.render(display_text, True, self.colors['input_text'])
        clip = pygame.Rect(self.input_rect.left + 5, self.input_rect.top,
                           self.input_rect.width - 10, self.input_rect.height)
        self.screen.set_clip(clip)
        self.screen.blit(input_text_surface,
                         (self.input_rect.left + 5,
                          self.input_rect.centery - input_text_surface.get_height() // 2))

        # 选中高亮
        sel_offsets = self.text_input.get_selection_offsets(self.font)
        if sel_offsets is not None:
            s_off, e_off = sel_offsets
            sel_rect = pygame.Rect(self.input_rect.left + 5 + s_off, self.input_rect.top + 3,
                                   max(e_off - s_off, 2), self.input_rect.height - 6)
            pygame.draw.rect(self.screen, self.colors.get('selection_bg', (50, 80, 160)), sel_rect)
            # 重新绘制文本在高亮上层
            self.screen.blit(input_text_surface,
                             (self.input_rect.left + 5,
                              self.input_rect.centery - input_text_surface.get_height() // 2))

        self.screen.set_clip(None)

        # 闪烁光标
        if self.input_active and cursor_visible:
            cursor_x = self.input_rect.left + 5 + min(cursor_offset, clip.width - 5)
            pygame.draw.line(self.screen, self.colors['input_text'],
                           (cursor_x, self.input_rect.top + 4),
                           (cursor_x, self.input_rect.bottom - 4), 1)
        
        # 按钮
        mouse_pos = pygame.mouse.get_pos()
        
        ok_color = self.colors['button_hover'] if self.ok_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, ok_color, self.ok_btn, border_radius=4)
        ok_text = self.font.render("确定", True, (255, 255, 255))
        self.screen.blit(ok_text, ok_text.get_rect(center=self.ok_btn.center))
        
        cancel_color = self.colors['button_hover'] if self.cancel_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, cancel_color, self.cancel_btn, border_radius=4)
        cancel_text = self.font.render("取消", True, (255, 255, 255))
        self.screen.blit(cancel_text, cancel_text.get_rect(center=self.cancel_btn.center))


class DialogsMixin:
    """对话框相关方法 Mixin"""

    def _load_help_lines(self):
        """从 gui/操作说明.md 加载帮助文本，解析为 (文本, 是否高亮) 列表"""
        if getattr(sys, 'frozen', False):
            md_path = os.path.join(sys._MEIPASS, 'gui', '操作说明.md')
        else:
            md_path = os.path.join(os.path.dirname(__file__), "操作说明.md")
        lines = []
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n").rstrip("\r")
                    if not line:
                        lines.append(("", False))
                    elif line.startswith("## "):
                        lines.append((line[3:], True))
                    elif line.startswith("   - "):
                        lines.append(("     · " + line[5:], False))
                    elif line[0].isdigit() and ". " in line:
                        lines.append(("  " + line, False))
                    else:
                        lines.append(("  " + line, False))
        except FileNotFoundError:
            pass
        return lines

    def draw_help_dialog(self):
        """绘制帮助对话框（支持滚动）"""
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        dialog_width = min(560, self.screen_width - 80)
        dialog_height = min(580, self.screen_height - 60)
        dialog_x = (self.screen_width - dialog_width) // 2
        dialog_y = (self.screen_height - dialog_height) // 2

        # 存储对话框 rect 供事件处理使用
        self.help_dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_width, dialog_height)

        pygame.draw.rect(self.screen, self.colors['dialog_bg'], self.help_dialog_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self.help_dialog_rect, 2, border_radius=8)

        title_surface = self.dialog_title_font.render("帮助 - 操作说明", True, self.colors['dialog_title'])
        self.screen.blit(title_surface, (dialog_x + 20, dialog_y + 15))

        line_y = dialog_y + 50
        pygame.draw.line(self.screen, self.colors['dialog_border'],
                        (dialog_x + 15, line_y), (dialog_x + dialog_width - 15, line_y))

        help_lines = self._load_help_lines()

        # 计算内容总高度（考虑自动换行）
        text_max_width = dialog_width - 65
        total_content_height = 0
        for line, is_header in help_lines:
            if not line:
                total_content_height += 8
            else:
                wrapped = self._wrap_text(line, self.dialog_font, text_max_width)
                total_content_height += 26 * len(wrapped)

        # 内容绘制区域（标题下方到关闭提示上方）
        content_top = dialog_y + 58
        content_bottom = dialog_y + dialog_height - 40
        content_height = content_bottom - content_top

        # 存储高度信息供事件处理使用
        self._help_content_height = content_height
        self._help_total_height = total_content_height

        # 滚动偏移量
        scroll_offset = getattr(self, 'help_scroll_offset', 0)

        # 限制滚动范围
        max_scroll = max(0, total_content_height - content_height)
        scroll_offset = max(0, min(scroll_offset, max_scroll))
        self.help_scroll_offset = scroll_offset

        # 绘制内容（带裁剪）
        clip_rect = pygame.Rect(dialog_x + 10, content_top, dialog_width - 30, content_height)
        self.screen.set_clip(clip_rect)

        y_offset = content_top - scroll_offset
        for line, is_header in help_lines:
            if not line:
                y_offset += 8
                continue
            # 自动换行
            color = (100, 200, 255) if is_header else self.colors['dialog_text']
            wrapped_lines = self._wrap_text(line, self.dialog_font, text_max_width)
            for wline in wrapped_lines:
                # 只绘制可见区域的内容
                if y_offset + 26 > content_top - 10 and y_offset < content_bottom + 10:
                    text_surface = self.dialog_font.render(wline, True, color)
                    self.screen.blit(text_surface, (dialog_x + 25, y_offset))
                y_offset += 26

        self.screen.set_clip(None)

        # 绘制滚动条（如果内容超出可见区域）
        if max_scroll > 0:
            scrollbar_x = dialog_x + dialog_width - 20
            scrollbar_top = content_top
            scrollbar_height = content_height
            self.help_scrollbar_rect = pygame.Rect(scrollbar_x, scrollbar_top, 8, scrollbar_height)
            pygame.draw.rect(self.screen, (60, 60, 60), self.help_scrollbar_rect, border_radius=3)

            # 滚动条滑块
            knob_height = max(20, int(scrollbar_height * content_height / total_content_height))
            knob_y = scrollbar_top + int((scrollbar_height - knob_height) * scroll_offset / max_scroll)
            knob_color = self.colors['button_hover'] if getattr(self, 'help_scrollbar_dragging', False) else self.colors['button_bg']
            self.help_scrollbar_knob_rect = pygame.Rect(scrollbar_x, knob_y, 8, knob_height)
            pygame.draw.rect(self.screen, knob_color, self.help_scrollbar_knob_rect, border_radius=3)
        else:
            self.help_scrollbar_rect = None
            self.help_scrollbar_knob_rect = None

        # 底部提示
        close_text = self.status_font.render("点击外部区域关闭 | 滚轮翻页", True, (150, 150, 150))
        close_rect = close_text.get_rect(center=(self.screen_width // 2, dialog_y + dialog_height - 20))
        self.screen.blit(close_text, close_rect)

    def draw_custom_puzzle_dialog(self):
        """绘制自定义谜题对话框"""
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        dialog_width = 320
        dialog_height = 320
        dialog_x = (self.screen_width - dialog_width) // 2
        dialog_y = (self.screen_height - dialog_height) // 2

        dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_width, dialog_height)
        pygame.draw.rect(self.screen, self.colors['dialog_bg'], dialog_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], dialog_rect, 2, border_radius=8)

        title_surface = self.dialog_title_font.render("自定义谜题", True, self.colors['dialog_title'])
        self.screen.blit(title_surface, (dialog_x + 20, dialog_y + 15))

        line_y = dialog_y + 50
        pygame.draw.line(self.screen, self.colors['dialog_border'],
                        (dialog_x + 15, line_y), (dialog_x + dialog_width - 15, line_y))

        label_x = dialog_x + 25
        field_x = dialog_x + 170

        # 带序号勾选框：单独一行，位于分隔线与输入字段之间
        checkbox_label = '带序号'
        checkbox_state = 'x' if getattr(self, 'custom_numbered', False) else ''
        checkbox_text = f'[ {checkbox_state} ] {checkbox_label}'
        checkbox_surface = self.input_font.render(checkbox_text, True, self.colors['dialog_text'])
        checkbox_y = dialog_y + 65
        self.screen.blit(checkbox_surface, (label_x, checkbox_y + 5))
        self.custom_numbered_rect = checkbox_surface.get_rect(topleft=(label_x, checkbox_y + 5))

        fields = [
            ('m', '行数:', self.custom_fields['m']),
            ('n', '列数:', self.custom_fields['n']),
            ('step', '等级:', self.custom_fields['step']),
        ]

        field_width = 80
        field_height = 30

        self.custom_field_rects = {}
        y_offset = dialog_y + 65 + 35

        for key, label, value in fields:
            label_surface = self.input_font.render(label, True, self.colors['dialog_text'])
            self.screen.blit(label_surface, (label_x, y_offset + 5))

            field_rect = pygame.Rect(field_x, y_offset, field_width, field_height)
            self.custom_field_rects[key] = field_rect

            bg_color = self.colors['input_active'] if self.custom_active_field == key else self.colors['input_bg']
            pygame.draw.rect(self.screen, bg_color, field_rect, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['dialog_border'], field_rect, 1, border_radius=4)

            value_surface = self.input_font.render(value, True, self.colors['input_text'])
            value_rect = value_surface.get_rect()
            value_rect.x = field_x + 8
            value_rect.centery = y_offset + field_height // 2
            self.screen.blit(value_surface, value_rect)

            if self.custom_active_field == key:
                cursor_x = field_x + 8 + value_rect.width + 1
                pygame.draw.line(self.screen, self.colors['input_text'],
                               (cursor_x, y_offset + 5),
                               (cursor_x, y_offset + field_height - 5), 1)

            y_offset += 45

        if self.custom_error:
            error_surface = self.status_font.render(self.custom_error, True, (255, 100, 100))
            self.screen.blit(error_surface, (label_x, y_offset))
            y_offset += 25

        btn_width = 80
        btn_height = 32
        btn_x = dialog_x + dialog_width // 2 - btn_width - 10
        btn_y = y_offset + 15
        self.custom_ok_btn = pygame.Rect(btn_x, btn_y, btn_width, btn_height)

        mouse_pos = pygame.mouse.get_pos()
        btn_color = self.colors['button_hover'] if self.custom_ok_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, self.custom_ok_btn, border_radius=4)
        ok_text = self.input_font.render("确定", True, (255, 255, 255))
        ok_rect = ok_text.get_rect(center=self.custom_ok_btn.center)
        self.screen.blit(ok_text, ok_rect)

        cancel_x = dialog_x + dialog_width // 2 + 10
        self.custom_cancel_btn = pygame.Rect(cancel_x, btn_y, btn_width, btn_height)

        btn_color = self.colors['button_hover'] if self.custom_cancel_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, self.custom_cancel_btn, border_radius=4)
        cancel_text = self.input_font.render("取消", True, (255, 255, 255))
        cancel_rect = cancel_text.get_rect(center=self.custom_cancel_btn.center)
        self.screen.blit(cancel_text, cancel_rect)

        #hint_text = self.status_font.render("等级必须小于行列数的较大值，否则", True, (150, 150, 150))
        #hint_rect = hint_text.get_rect(center=(self.screen_width // 2, dialog_y + dialog_height - 15))
        #self.screen.blit(hint_text, hint_rect)

    def handle_custom_dialog_events(self, event) -> bool:
        """
        处理自定义谜题对话框事件

        返回：
            bool - 如果事件被处理返回 True
        """
        if not self.show_custom_dialog:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos

            if hasattr(self, 'custom_numbered_rect') and self.custom_numbered_rect.collidepoint(x, y):
                self.custom_numbered = not getattr(self, 'custom_numbered', False)
                return True

            for key, rect in self.custom_field_rects.items():
                if rect.collidepoint(x, y):
                    self.custom_active_field = key
                    return True

            if self.custom_ok_btn.collidepoint(x, y):
                try:
                    m = int(self.custom_fields['m'])
                    n = int(self.custom_fields['n'])
                    step = int(self.custom_fields['step'])

                    if m < 2 or n < 2:
                        self.custom_error = "行数和列数必须 >= 2"
                        return True
                    if step < 1:
                        self.custom_error = "等级必须 >= 1"
                        return True
                    if step >= max(m, n):
                        self.custom_error = f"等级必须 < {max(m, n)}"
                        return True

                    numbered = getattr(self, 'custom_numbered', False)
                    self.new_puzzle(m, n, step, numbered=numbered)
                    self.show_custom_dialog = False
                    self.custom_error = ''
                    return True
                except ValueError:
                    self.custom_error = "请输入有效的整数"
                    return True

            if self.custom_cancel_btn.collidepoint(x, y):
                self.show_custom_dialog = False
                self.custom_error = ''
                return True

            dialog_rect = pygame.Rect(
                (self.screen_width - 320) // 2,
                (self.screen_height - 280) // 2,
                320, 280
            )
            if not dialog_rect.collidepoint(x, y):
                self.show_custom_dialog = False
                self.custom_error = ''
                return True

            return True

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.show_custom_dialog = False
                self.custom_error = ''
                return True
            elif event.key == pygame.K_RETURN:
                fake_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                    button=1, pos=self.custom_ok_btn.center)
                return self.handle_custom_dialog_events(fake_event)
            elif event.key == pygame.K_TAB:
                fields = ['m', 'n', 'step']
                if self.custom_active_field in fields:
                    idx = fields.index(self.custom_active_field)
                    self.custom_active_field = fields[(idx + 1) % len(fields)]
                else:
                    self.custom_active_field = 'm'
                return True
            elif event.key == pygame.K_BACKSPACE:
                if self.custom_active_field:
                    current = self.custom_fields[self.custom_active_field]
                    self.custom_fields[self.custom_active_field] = current[:-1]
                return True
            elif event.unicode.isdigit():
                if self.custom_active_field:
                    current = self.custom_fields[self.custom_active_field]
                    if len(current) < 3:
                        self.custom_fields[self.custom_active_field] = current + event.unicode
                return True

            return True

        return False
