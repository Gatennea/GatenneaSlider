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
from gui.file_ops import _find_illegal_filename_chars


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
        self.error_msg = ''  # 确定按钮校验失败的提示（如文件名含非法字符）
        
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
        self.error_msg = ''
        
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
                # Windows 非法字符校验：写盘必抛异常，这里提前拦下并留在对话框内提示
                illegal = _find_illegal_filename_chars(final_name)
                if illegal:
                    self.error_msg = f"文件名含非法字符 {' '.join(illegal)}，请修改"
                    return
                self.error_msg = ''
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
        
        # 当前目录（截断只作用于渲染副本——曾直接改 self.current_dir，
        # 导致长/含中文路径被啃坏，选文件后 join 出非法路径报「未找到文件」）
        dir_text_str = self.current_dir
        dir_text = self.small_font.render(dir_text_str, True, (150, 150, 150))
        # 截断过长路径
        max_dir_w = self.up_btn.left - dx - 20
        while dir_text.get_width() > max_dir_w and len(dir_text_str) > 10:
            dir_text_str = '...' + dir_text_str[4:]
            dir_text = self.small_font.render(dir_text_str, True, (150, 150, 150))
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

        # 校验错误提示（文件名含非法字符等）：显示在「文件名:」标签右侧
        if self.error_msg:
            err_surface = self.small_font.render(self.error_msg, True, (255, 100, 100))
            self.screen.blit(err_surface, (self.input_rect.left + 60, self.input_rect.top - 16))
        
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
        """从 docs/player/操作说明.md 加载帮助文本，解析为 (文本, 是否高亮) 列表"""
        if getattr(sys, 'frozen', False):
            md_path = os.path.join(sys._MEIPASS, 'docs', 'player', '操作说明.md')
        else:
            md_path = os.path.join(os.path.dirname(__file__), "..", "docs", "player", "操作说明.md")
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

        # 检索框（始终可见；打开帮助时焦点默认在它上面）。
        # 这是「功能可发现性」的主入口：玩家用口语（「着色」「怎么撤销」）就能
        # 定位功能，结果会说明当前形态/模式下能不能用，回车直接到位。
        search_h = 30
        search_rect = pygame.Rect(dialog_x + 20, dialog_y + 60,
                                  dialog_width - 40, search_h)
        self.help_search_rect = search_rect
        query = str(getattr(self, 'help_query', '') or '')
        active = bool(getattr(self, 'help_search_active', False))
        # 与事件层一致：以 help_query 为权威串，组件内容与之同步（光标置于末尾）；
        # 这样打开帮助若有残留查询，光标也会落在末尾而非错位。
        ti = getattr(self, 'help_input', None)
        if ti is not None and ti.text != query:
            ti.set_text(query)
        cursor_pos = ti.cursor_pos if ti is not None else len(query)
        pygame.draw.rect(self.screen,
                         self.colors['input_active' if active else 'input_bg'],
                         search_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.colors['dialog_border'],
                         search_rect, 1, border_radius=4)
        if query:
            text_surf = self.dialog_font.render(query, True, self.colors['input_text'])
        else:
            text_surf = self.dialog_font.render(
                '检索功能（试试「着色」「撤销」「三角」「怎么用」）', True, (140, 140, 140))
        self.screen.blit(text_surf, (search_rect.x + 8, search_rect.y + 4))
        if active and (pygame.time.get_ticks() // 500) % 2 == 0:
            if query:
                prefix = query[:cursor_pos]
                cx = search_rect.x + 8 + self.dialog_font.size(prefix)[0] + 1
            else:
                cx = search_rect.x + 8 + 1
            pygame.draw.line(self.screen, self.colors['input_text'],
                             (cx, search_rect.y + 6),
                             (cx, search_rect.y + search_h - 6), 1)

        help_lines = self._load_help_lines()

        # 内容绘制区域（检索框下方到关闭提示上方）
        content_top = dialog_y + 98
        content_bottom = dialog_y + dialog_height - 40
        content_height = content_bottom - content_top
        text_max_width = dialog_width - 65

        # 有检索词 → 渲染检索结果；无 → 渲染操作说明全文（与旧行为一致）。
        # 检索态滚动归零：结果条数与文档长度不同，沿用旧偏移会看到空白。
        query = str(getattr(self, 'help_query', '') or '').strip()
        if query:
            content_lines = self._help_search_result_lines(
                query, dialog_x, content_top, dialog_width, text_max_width)
        else:
            content_lines = help_lines

        # 计算内容总高度（考虑自动换行）
        total_content_height = 0
        for line, is_header in content_lines:
            if not line:
                total_content_height += 8
            else:
                wrapped = self._wrap_text(line, self.dialog_font, text_max_width)
                total_content_height += 26 * len(wrapped)

        # 滚动条（与设置框共用 Scrollbar）：每帧依内容高度重算，
        # 检索态/全文态切换时几何仍正确。
        sb = self.help_scrollbar
        sb.layout(dialog_x + dialog_width - 20, content_top, content_height,
                  total_content_height, content_height)
        scroll_offset = sb.scroll

        # 绘制内容（带裁剪）
        clip_rect = pygame.Rect(dialog_x + 10, content_top, dialog_width - 30, content_height)
        self.screen.set_clip(clip_rect)

        y_offset = content_top - scroll_offset
        for line, is_header in content_lines:
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

        # 绘制滚动条（仅当内容超出可见区域）
        if sb.need_scroll():
            sb.draw(self.screen)

        # 底部提示
        if query:
            close_text = self.status_font.render(
                "↑↓ 选择 · 回车 直接到位 · Esc 清空检索词", True, (150, 150, 150))
        else:
            close_text = self.status_font.render(
                "点击外部区域关闭 | 滚轮翻页", True, (150, 150, 150))
        close_rect = close_text.get_rect(center=(self.screen_width // 2, dialog_y + dialog_height - 20))
        self.screen.blit(close_text, close_rect)

    def _help_search_result_lines(self, query, dialog_x, content_top,
                                  dialog_width, text_max_width):
        """把检索结果渲染成 [(文本, 是否标题)]，并登记每项的点击矩形。

        命中范围：功能名 + 玩家别名 + 一句话用法 + 常见困惑 + 所在位置。
        每条结果依次显示「名称 —— 位置」「怎么用」「常见困惑」，中间空一行。
        """
        from gui import feature_index as _fi
        from gui import feature_ai as _ai

        form = self._feature_form()
        mode = getattr(self, 'game_mode', 'practice')
        results = _fi.search(query, form=form, mode=mode, limit=25)

        lines = []
        rects = []
        if not results:
            sugg = _fi.suggest(query, form=form, mode=mode, k=5)
            if sugg:
                lines.append((f'没有功能精确匹配「{query}」，你是不是想找：', True))
                for entry, available in sugg:
                    head = entry['name']
                    head = f'▶ {head}' if available else f'✕ {head}'
                    head += f'   ——   {_fi.place_text(entry["place"])}'
                    lines.append((head, False))
            elif _ai.is_configured():
                # suggest 仍空且 AI 兜底已配置 → 大模型最后兜底（离线未配置不进此分支）
                ai_res = _ai.resolve(query, form=form, mode=mode,
                                     features=_fi.FEATURES, k=5)
                if ai_res:
                    lines.append((f'AI 建议（仅供参考）：', True))
                    for entry, available in ai_res:
                        head = entry['name']
                        head = f'▶ {head}' if available else f'✕ {head}'
                        head += f'   ——   {_fi.place_text(entry["place"])}'
                        lines.append((head, False))
                else:
                    lines.append((f'没有功能匹配「{query}」。', True))
                    lines.append(('换个说法试试：着色 / 撤销 / 打乱 / 求解 / 三角 / 米字 / 等级 / 怎么用',
                                  False))
            else:
                lines.append((f'没有功能匹配「{query}」。', True))
                lines.append(('换个说法试试：着色 / 撤销 / 打乱 / 求解 / 三角 / 米字 / 等级 / 怎么用',
                              False))
            self.help_result_rects = rects
            self.help_sel = 0
            return lines

        lines.append((f'找到 {len(results)} 项（↑↓ 选择，回车 直接到位）：', True))
        lines.append(('', False))

        y = content_top
        for _line in lines:
            y += 8 if not _line[0] else 26

        for index, (_score, entry, available) in enumerate(results):
            top = y
            head = entry['name']
            if available:
                head = f'▶ {head}'
            else:
                head = f'✕ {head}（当前不可用：{_fi.unsupported_reason(entry, form, mode)}）'
            head += f'   ——   {_fi.place_text(entry["place"])}'
            for piece in (head, entry.get('howto', ''), entry.get('confusion', '')):
                if not piece:
                    continue
                for wline in self._wrap_text(piece, self.dialog_font, text_max_width):
                    lines.append((wline, index == getattr(self, 'help_sel', 0)))
                    y += 26
            lines.append(('', False))
            y += 8
            rects.append((pygame.Rect(dialog_x + 10, top, dialog_width - 30,
                          y - top), entry))

        self.help_result_rects = rects
        return lines

    def draw_custom_puzzle_dialog(self):
        """绘制自定义谜题对话框：先选形态，再填尺寸与等级"""
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

        # 形态三选一：矩形 / 三角 / 数字（分段按钮，选中项高亮）
        kind = getattr(self, 'custom_kind', 'rect')
        kind_label = self.input_font.render('形态:', True, self.colors['dialog_text'])
        kind_y = dialog_y + 62
        self.screen.blit(kind_label, (label_x, kind_y + 6))

        self.custom_kind_rects = {}
        # 形态四选一：矩形 / 三角 / 米字 / 数字（分段按钮，选中项高亮）
        # 加第四项后按钮收窄，四个并排仍在一行内
        btn_w, btn_h = 52, 26
        kind_x = dialog_x + 85
        for kid, kname in (('rect', '矩形'), ('triangle', '三角'),
                           ('mi', '米字'), ('numbered', '数字')):
            btn = pygame.Rect(kind_x, kind_y, btn_w, btn_h)
            self.custom_kind_rects[kid] = btn
            active = (kind == kid)
            pygame.draw.rect(self.screen,
                             self.colors['button_hover'] if active else self.colors['input_bg'],
                             btn, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['dialog_border'], btn, 1, border_radius=4)
            text = self.input_font.render(
                kname, True, (255, 255, 255) if active else self.colors['dialog_text'])
            self.screen.blit(text, text.get_rect(center=btn.center))
            kind_x += btn_w + 6

        # 输入字段随形态变化：三角只有边长和等级，矩形/数字是行数、列数、等级
        if kind == 'triangle':
            fields = [
                ('m', '边长:', self.custom_fields['m']),
                ('step', '等级:', self.custom_fields['step']),
            ]
        else:
            fields = [
                ('m', '行数:', self.custom_fields['m']),
                ('n', '列数:', self.custom_fields['n']),
                ('step', '等级:', self.custom_fields['step']),
            ]

        field_width = 80
        field_height = 30

        self.custom_field_rects = {}
        y_offset = dialog_y + 105

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

        # 三个按钮一行：[高级选项…] [确定] [取消]
        # 「高级选项…」= 按上面的形态/尺寸/等级开一局，然后直接进设计画布
        # （用户 2026-10-26 要的入口；实现只有 _ann_btn_design 这一个，
        # 这里只是转发，避免与创造模式的入口变成两套账）。
        btn_height = 32
        btn_y = dialog_y + 272
        adv_w, ok_w = 112, 80
        gap = 8
        row_w = adv_w + ok_w * 2 + gap * 2
        row_x = dialog_x + (dialog_width - row_w) // 2

        self.custom_adv_btn = pygame.Rect(row_x, btn_y, adv_w, btn_height)
        mouse_pos = pygame.mouse.get_pos()
        btn_color = (self.colors['button_hover']
                     if self.custom_adv_btn.collidepoint(mouse_pos)
                     else self.colors['button_bg'])
        pygame.draw.rect(self.screen, btn_color, self.custom_adv_btn, border_radius=4)
        adv_text = self.input_font.render("高级选项…", True, (255, 255, 255))
        self.screen.blit(adv_text, adv_text.get_rect(center=self.custom_adv_btn.center))

        btn_x = row_x + adv_w + gap
        # 按钮位置固定：字段数随形态变（三角少一个列数），按钮不跟着上下跳
        self.custom_ok_btn = pygame.Rect(btn_x, btn_y, ok_w, btn_height)

        btn_color = self.colors['button_hover'] if self.custom_ok_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, self.custom_ok_btn, border_radius=4)
        ok_text = self.input_font.render("确定", True, (255, 255, 255))
        ok_rect = ok_text.get_rect(center=self.custom_ok_btn.center)
        self.screen.blit(ok_text, ok_rect)

        cancel_x = btn_x + ok_w + gap
        self.custom_cancel_btn = pygame.Rect(cancel_x, btn_y, ok_w, btn_height)

        btn_color = self.colors['button_hover'] if self.custom_cancel_btn.collidepoint(mouse_pos) else self.colors['button_bg']
        pygame.draw.rect(self.screen, btn_color, self.custom_cancel_btn, border_radius=4)
        cancel_text = self.input_font.render("取消", True, (255, 255, 255))
        cancel_rect = cancel_text.get_rect(center=self.custom_cancel_btn.center)
        self.screen.blit(cancel_text, cancel_rect)

        #hint_text = self.status_font.render("等级必须小于行列数的较大值，否则", True, (150, 150, 150))
        #hint_rect = hint_text.get_rect(center=(self.screen_width // 2, dialog_y + dialog_height - 15))
        #self.screen.blit(hint_text, hint_rect)

    # ------------------------------------------------------------------
    # 通用确认弹窗（破坏性操作用；目前只有「删除预设」）
    # ------------------------------------------------------------------
    def draw_confirm_dialog(self):
        """画确认弹窗：标题 + 若干行人话 + [取消][确定]。

        为什么单独做一个通用弹窗而不是把确认塞进菜单条目里（点两次 ✕ 之类）：
        删除是**不可恢复**的（用户 2026-10-26 定：直删，不做回收站），必须让
        玩家在按下去之前看清「删的是哪一题、删完什么会没了」。做成一行的
        「再点一次确认」既看不清文字，也容易和「点开这一题」混起来。
        """
        lines = list(getattr(self, 'confirm_lines', ()) or ())
        title = getattr(self, 'confirm_title', '确认')
        ok_text = getattr(self, 'confirm_ok_text', '确定')

        pad = 22
        width = 440
        text_w = width - pad * 2
        wrapped = []
        for line in lines:
            wrapped.extend(self._wrap_text(line, self.dialog_font, text_w))
        height = pad + 34 + 10 + len(wrapped) * 24 + 16 + 36 + pad

        x = (self.screen_width - width) // 2
        y = (self.screen_height - height) // 2

        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, self.colors['dialog_bg'], rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], rect, 2, border_radius=8)

        # 标题：危险操作用缝的线色（palette 里唯一的红），不新造颜色
        title_color = (self.colors['line']
                       if getattr(self, 'confirm_danger', False)
                       else self.colors['dialog_title'])
        surf = self.dialog_title_font.render(title, True, title_color)
        self.screen.blit(surf, (x + pad, y + pad))

        ty = y + pad + 34 + 10
        for line in wrapped:
            s = self.dialog_font.render(line, True, self.colors['dialog_text'])
            self.screen.blit(s, (x + pad, ty))
            ty += 24

        btn_w, btn_h = 88, 34
        btn_y = y + height - pad - btn_h
        mouse_pos = pygame.mouse.get_pos()

        # 取消（左）/ 确定（右）：与其它对话框一致，确定在右
        self.confirm_cancel_btn = pygame.Rect(
            x + width - pad - btn_w * 2 - 10, btn_y, btn_w, btn_h)
        self.confirm_ok_btn = pygame.Rect(
            x + width - pad - btn_w, btn_y, btn_w, btn_h)

        c = (self.colors['button_hover']
             if self.confirm_cancel_btn.collidepoint(mouse_pos)
             else self.colors['button_bg'])
        pygame.draw.rect(self.screen, c, self.confirm_cancel_btn, border_radius=4)
        s = self.dialog_font.render('取消', True, (255, 255, 255))
        self.screen.blit(s, s.get_rect(center=self.confirm_cancel_btn.center))

        if getattr(self, 'confirm_danger', False):
            # 危险按钮：dialog_bg 与红线色混出暗红，悬停再亮一档
            r, g, b = self.colors['line']
            d = self.colors['dialog_bg']
            mix = (0.55 if self.confirm_ok_btn.collidepoint(mouse_pos) else 0.40)
            c = tuple(int(rr * mix + dd * (1 - mix)) for rr, dd in zip((r, g, b), d))
        else:
            c = (self.colors['button_hover']
                 if self.confirm_ok_btn.collidepoint(mouse_pos)
                 else self.colors['button_bg'])
        pygame.draw.rect(self.screen, c, self.confirm_ok_btn, border_radius=4)
        s = self.dialog_font.render(ok_text, True, (255, 255, 255))
        self.screen.blit(s, s.get_rect(center=self.confirm_ok_btn.center))

    def handle_confirm_dialog_events(self, event) -> bool:
        """确认弹窗事件（模态：吞掉一切，只有 [取消]/[确定]/ESC/回车有效）。

        §16 纪律：底部按钮**最先判定**，命中即返回；否则「点外面关掉」
        之类的外层判定会先吃掉落在按钮上的点击。
        """
        if not getattr(self, 'show_confirm_dialog', False):
            return False

        def _close():
            self.show_confirm_dialog = False
            self.confirm_action = None
            self.confirm_lines = []

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                _close()
            elif event.key == pygame.K_RETURN:
                act = getattr(self, 'confirm_action', None)
                _close()
                if callable(act):
                    act()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            ok_btn = getattr(self, 'confirm_ok_btn', None)
            cancel_btn = getattr(self, 'confirm_cancel_btn', None)
            if ok_btn is None:
                return True      # 还没画过一帧：没有可点区域，先吞掉
            if ok_btn.collidepoint(event.pos):
                act = getattr(self, 'confirm_action', None)
                _close()
                if callable(act):
                    act()
                return True
            if cancel_btn is not None and cancel_btn.collidepoint(event.pos):
                _close()
                return True
            # 点外部 = 取消（破坏性操作绝不在「点外面」时执行）
            _close()
            return True

        return True

    def _custom_apply_fields(self) -> bool:
        """按对话框里的形态 / 尺寸 / 等级建局。成功返回 True（并关掉对话框）。

        「确定」与「高级选项…」共用这一份：两条路必须过**同一套门槛**，
        各写一份必然分叉（同一个数字在一个按钮上过、另一个不过）。

        值域约束与各 new_*_puzzle 同源，不在这里另立一套：
        - 三角形存在任何合法移动 ⟺ k − step ≥ 2（贴合边长时一步都动不了，
          打乱会恒回还原态，故建局前就挡）；
        - 方形/米字要求 step < max(m, n)。
        """
        try:
            m = int(self.custom_fields['m'])
            step = int(self.custom_fields['step'])
        except (KeyError, ValueError):
            self.custom_error = "请输入有效的整数"
            return False

        if step < 1:
            self.custom_error = "等级必须 >= 1"
            return False

        if getattr(self, 'custom_kind', 'rect') == 'triangle':
            if m < 3:
                self.custom_error = "三角形边长必须 >= 3"
                return False
            if step > m - 2:
                self.custom_error = f"三角形等级必须 <= {m - 2}"
                return False
            self.new_triangle_puzzle(m, step)
            self.show_custom_dialog = False
            self.custom_error = ''
            return True

        try:
            n = int(self.custom_fields['n'])
        except (KeyError, ValueError):
            self.custom_error = "请输入有效的整数"
            return False
        if m < 2 or n < 2:
            self.custom_error = "行数和列数必须 >= 2"
            return False
        if step >= max(m, n):
            self.custom_error = f"等级必须 < {max(m, n)}"
            return False

        if getattr(self, 'custom_kind', 'rect') == 'mi':
            self.new_mi_puzzle(m, n, step)
            self.show_custom_dialog = False
            self.custom_error = ''
            return True

        numbered = getattr(self, 'custom_kind', 'rect') == 'numbered'
        self.new_puzzle(m, n, step, numbered=numbered)
        self.show_custom_dialog = False
        self.custom_error = ''
        return True

    def _custom_field_order(self) -> list:
        """自定义对话框当前可见的输入字段（三角形态没有列数）。"""
        if getattr(self, 'custom_kind', 'rect') == 'triangle':
            return ['m', 'step']
        return ['m', 'n', 'step']

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

            # 对话框还没画过一帧（双击的第二下、或刚被别的路径打开）时没有任何
            # 可点的矩形，直接吞掉这个点击，不要去摸不存在的 custom_field_rects
            if not hasattr(self, 'custom_ok_btn'):
                return True

            for kid, rect in getattr(self, 'custom_kind_rects', {}).items():
                if rect.collidepoint(x, y):
                    if self.custom_kind != kid:
                        self.custom_kind = kid
                        # 切到三角后列数用不上了，焦点落回第一个字段
                        self.custom_active_field = 'm'
                        self.custom_error = ''
                    return True

            for key, rect in self.custom_field_rects.items():
                if rect.collidepoint(x, y):
                    self.custom_active_field = key
                    return True

            if self.custom_ok_btn.collidepoint(x, y):
                self._custom_apply_fields()
                return True

            adv_btn = getattr(self, 'custom_adv_btn', None)
            if adv_btn is not None and adv_btn.collidepoint(x, y):
                # 先按对话框参数开一局（= 确定），成了再进设计画布。
                # 语义：设计的是**还原态**，所以从刚开出来的干净盘面进，
                # 而不是从玩家眼前可能已经打乱的盘面进。
                if self._custom_apply_fields():
                    self._ann_btn_design()
                return True

            if self.custom_cancel_btn.collidepoint(x, y):
                self.show_custom_dialog = False
                self.custom_error = ''
                return True

            dialog_rect = pygame.Rect(
                (self.screen_width - 320) // 2,
                (self.screen_height - 320) // 2,
                320, 320
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
                fields = self._custom_field_order()
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
