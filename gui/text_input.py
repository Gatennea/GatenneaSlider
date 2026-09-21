# -*- coding: utf-8 -*-
"""
文本输入组件

提供完整的文本输入功能，包括：
- 光标闪烁与移动
- 鼠标点击定位
- 长按键盘连续触发
- 文本选中（鼠标拖拽 / Shift+方向键）
- 选中后删除、替换
- 全选、复制、粘贴、剪切
- 双击选中
- 选中高亮显示
"""

import pygame


class TextInput:
    """文本输入组件

    属性：
        text: 当前输入文本
        cursor_pos: 光标位置（字符索引，0 ~ len(text)）
        active: 是否激活状态

    用法：
        input_box = TextInput('默认文本')
        ...
        # 在事件循环中
        input_box.handle_event(event, font, input_rect)
        # 在更新循环中
        input_box.update(dt_ms)
        # 在渲染循环中
        input_box.draw(screen, font, rect, colors)
        
        或使用细粒度 API：
            input_box.get_display_text(font, max_width, placeholder, active)
            input_box.get_cursor_offset(font)
            input_box.get_selection_offsets(font)  # 返回 (start_offset, end_offset)
            input_box.has_selection()
    """

    # 长按参数（毫秒）
    KEY_REPEAT_DELAY = 400      # 首次触发延迟
    KEY_REPEAT_INTERVAL = 30    # 重复间隔

    # 选中范围（如果 start == end 则表示无选中）
    _selection_start = 0
    _selection_end = 0

    # 长按状态
    _repeat_key = None
    _repeat_timer = 0
    _repeat_mods = 0

    # 鼠标拖拽状态
    _mouse_dragging = False

    def __init__(self, initial_text=''):
        self.text = initial_text
        self.cursor_pos = len(initial_text)
        self.active = True
        self._blink_timer = 0
        self._blink_visible = True
        self._blink_interval = 500
        self._selection_start = self.cursor_pos
        self._selection_end = self.cursor_pos
        self._display_start = 0

    # ------------------------------------------------------------------
    # 基本属性
    # ------------------------------------------------------------------

    @property
    def blink_visible(self):
        return self._blink_visible

    def has_selection(self):
        return self._selection_start != self._selection_end

    def get_selection_range(self):
        """返回 (start, end)，保证 start <= end"""
        if self._selection_start <= self._selection_end:
            return (self._selection_start, self._selection_end)
        return (self._selection_end, self._selection_start)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def handle_event(self, event, font=None, input_rect=None) -> bool:
        """
        处理输入事件

        参数:
            event: pygame 事件
            font: 字体（用于鼠标点击定位，可选）
            input_rect: 输入框矩形 pygame.Rect（用于鼠标点击定位，可选）

        返回: True 如果事件被消费
        """
        if not self.active:
            return False

        if event.type == pygame.KEYDOWN:
            # 清除任何之前的长按状态并启动新的长按
            self._start_repeat(event.key, event.mod)
            handled = self._process_key(event.key, event.mod, event.unicode)
            if handled:
                self._reset_blink()
                return True
            return False

        elif event.type == pygame.KEYUP:
            if event.key == self._repeat_key:
                self._stop_repeat()
            return False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if font is not None and input_rect is not None:
                if input_rect.collidepoint(event.pos):
                    # 点击输入框内 —— 定位光标
                    rel_x = event.pos[0] - input_rect.left
                    self.set_cursor_by_pixel(font, rel_x, input_rect.width)
                    self._mouse_dragging = True
                    # 点击时清除选中，新选择从点击位置开始
                    self._selection_start = self.cursor_pos
                    self._selection_end = self.cursor_pos
                    self._reset_blink()
                    return True
                else:
                    # 点击输入框外，停止拖拽但不处理事件
                    self._mouse_dragging = False

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse_dragging = False
            return False

        elif event.type == pygame.MOUSEMOTION and self._mouse_dragging:
            if font is not None and input_rect is not None:
                # 拖拽扩展选择
                rel_x = event.pos[0] - input_rect.left
                new_pos = self._pixel_to_index(font, rel_x)
                # selection_start 保持为拖拽起点，selection_end 随光标移动
                self._selection_end = new_pos
                self.cursor_pos = new_pos
                self._reset_blink()
                return True

        return False

    # ------------------------------------------------------------------
    # 按键处理
    # ------------------------------------------------------------------

    def _process_key(self, key, mods, unicode_char):
        """
        处理单个按键（被 KEYDOWN 和长按重复共用）

        返回: True 如果处理了按键
        """
        ctrl = bool(mods & pygame.KMOD_CTRL)
        shift = bool(mods & pygame.KMOD_SHIFT)

        # --- Ctrl 快捷键 ---
        if ctrl:
            if key == pygame.K_a:
                # 全选
                self._selection_start = 0
                self._selection_end = len(self.text)
                self.cursor_pos = len(self.text)
                return True
            elif key == pygame.K_c:
                # 复制
                if self.has_selection():
                    s, e = self.get_selection_range()
                    pygame.scrap.put(pygame.SCRAP_TEXT, self.text[s:e].encode('utf-8'))
                return True
            elif key == pygame.K_x:
                # 剪切
                if self.has_selection():
                    s, e = self.get_selection_range()
                    pygame.scrap.put(pygame.SCRAP_TEXT, self.text[s:e].encode('utf-8'))
                    self.text = self.text[:s] + self.text[e:]
                    self.cursor_pos = s
                    self._selection_start = s
                    self._selection_end = s
                return True
            elif key == pygame.K_v:
                # 粘贴
                try:
                    if pygame.scrap.has_text():
                        pasted = pygame.scrap.get(pygame.SCRAP_TEXT)
                        if pasted:
                            # 去掉末尾的 null 字节和处理编码
                            if isinstance(pasted, bytes):
                                pasted = pasted.rstrip(b'\x00').decode('utf-8', errors='ignore')
                            if self.has_selection():
                                s, e = self.get_selection_range()
                                self.text = self.text[:s] + pasted + self.text[e:]
                                self.cursor_pos = s + len(pasted)
                                self._selection_start = self.cursor_pos
                                self._selection_end = self.cursor_pos
                            else:
                                self.text = self.text[:self.cursor_pos] + pasted + self.text[self.cursor_pos:]
                                self.cursor_pos += len(pasted)
                except Exception:
                    pass
                return True

        # --- 方向键（支持 Shift 扩展选择）---
        if key == pygame.K_LEFT:
            if shift:
                # 扩展选择
                if self.cursor_pos > 0:
                    self.cursor_pos -= 1
                    self._selection_end = self.cursor_pos
                return True
            else:
                # 有选中则跳到选中起点，否则正常移动
                if self.has_selection():
                    s, e = self.get_selection_range()
                    self.cursor_pos = s
                    self._selection_start = s
                    self._selection_end = s
                elif self.cursor_pos > 0:
                    self.cursor_pos -= 1
                return True

        elif key == pygame.K_RIGHT:
            if shift:
                if self.cursor_pos < len(self.text):
                    self.cursor_pos += 1
                    self._selection_end = self.cursor_pos
                return True
            else:
                if self.has_selection():
                    s, e = self.get_selection_range()
                    self.cursor_pos = e
                    self._selection_start = e
                    self._selection_end = e
                elif self.cursor_pos < len(self.text):
                    self.cursor_pos += 1
                return True

        elif key == pygame.K_HOME:
            if shift:
                self.cursor_pos = 0
                self._selection_end = 0
            else:
                self.cursor_pos = 0
                self._selection_start = 0
                self._selection_end = 0
            return True

        elif key == pygame.K_END:
            if shift:
                self.cursor_pos = len(self.text)
                self._selection_end = len(self.text)
            else:
                self.cursor_pos = len(self.text)
                self._selection_start = len(self.text)
                self._selection_end = len(self.text)
            return True

        # --- 删除键 ---
        elif key == pygame.K_BACKSPACE:
            if self.has_selection():
                # 删除选中
                s, e = self.get_selection_range()
                self.text = self.text[:s] + self.text[e:]
                self.cursor_pos = s
                self._selection_start = s
                self._selection_end = s
            elif self.cursor_pos > 0:
                # 删除光标前的字符
                self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                self.cursor_pos -= 1
            return True

        elif key == pygame.K_DELETE:
            if self.has_selection():
                s, e = self.get_selection_range()
                self.text = self.text[:s] + self.text[e:]
                self.cursor_pos = s
                self._selection_start = s
                self._selection_end = s
            elif self.cursor_pos < len(self.text):
                # 删除光标后的字符
                self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
            return True

        # --- 可打印字符（插入或替换选中）---
        elif unicode_char and unicode_char.isprintable():
            if self.has_selection():
                # 替换选中内容
                s, e = self.get_selection_range()
                self.text = self.text[:s] + unicode_char + self.text[e:]
                self.cursor_pos = s + len(unicode_char)
                self._selection_start = self.cursor_pos
                self._selection_end = self.cursor_pos
            else:
                # 在光标位置插入
                self.text = self.text[:self.cursor_pos] + unicode_char + self.text[self.cursor_pos:]
                self.cursor_pos += len(unicode_char)
            return True

        return False

    # ------------------------------------------------------------------
    # 长按重复
    # ------------------------------------------------------------------

    def _start_repeat(self, key, mods):
        self._repeat_key = key
        self._repeat_mods = mods
        self._repeat_timer = 0

    def _stop_repeat(self):
        self._repeat_key = None
        self._repeat_timer = 0
        self._repeat_mods = 0

    # ------------------------------------------------------------------
    # 帧更新（闪烁 + 长按重复）
    # ------------------------------------------------------------------

    def update(self, dt_ms: int):
        """每帧调用，dt_ms 为本帧毫秒数"""
        # 光标闪烁
        if self.active:
            self._blink_timer += dt_ms
            if self._blink_timer >= self._blink_interval:
                self._blink_timer -= self._blink_interval
                self._blink_visible = not self._blink_visible

        # 长按重复
        if self._repeat_key is not None:
            self._repeat_timer += dt_ms

            # 首次延迟
            if self._repeat_timer < self.KEY_REPEAT_DELAY:
                return

            # 超过延迟后，按 interval 重复触发
            # 使用 while 处理一帧内可能触发多次的情况
            trigger_count = 0
            while self._repeat_timer >= self.KEY_REPEAT_DELAY + self.KEY_REPEAT_INTERVAL:
                self._repeat_timer -= self.KEY_REPEAT_INTERVAL
                trigger_count += 1

            # 限制一帧内最多重复次数，防止极端情况
            trigger_count = min(trigger_count, 20)

            for _ in range(trigger_count):
                # 只对方向键、删除键、可打印字符做重复
                key = self._repeat_key
                repeatable = (
                    key == pygame.K_LEFT or
                    key == pygame.K_RIGHT or
                    key == pygame.K_BACKSPACE or
                    key == pygame.K_DELETE or
                    key == pygame.K_HOME or
                    key == pygame.K_END or
                    (0x20 <= key <= 0x7E)  # 可打印 ASCII
                )
                if repeatable:
                    self._process_key(key, self._repeat_mods, '')
                    self._reset_blink()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _reset_blink(self):
        self._blink_timer = 0
        self._blink_visible = True

    def set_text(self, text: str):
        self.text = text
        self.cursor_pos = len(text)
        self._selection_start = self.cursor_pos
        self._selection_end = self.cursor_pos
        self._reset_blink()

    def clear(self):
        self.text = ''
        self.cursor_pos = 0
        self._selection_start = 0
        self._selection_end = 0
        self._reset_blink()

    def _pixel_to_index(self, font, pixel_x: int) -> int:
        """将像素位置转换为字符索引（考虑 _display_start）"""
        if not self.text:
            return 0

        display_start = getattr(self, '_display_start', 0)
        accumulated_width = 0

        for i in range(display_start, len(self.text)):
            char_width = font.size(self.text[i])[0]
            if pixel_x < accumulated_width + char_width // 2:
                return i
            accumulated_width += char_width
            if pixel_x < accumulated_width:
                return i + 1

        return len(self.text)

    def set_cursor_by_pixel(self, font, pixel_x: int, max_width: int) -> int:
        """根据像素位置设置光标，供外部调用"""
        if not self.text:
            self.cursor_pos = 0
            self._selection_start = 0
            self._selection_end = 0
            self._reset_blink()
            return 0

        new_pos = self._pixel_to_index(font, pixel_x)
        new_pos = max(0, min(new_pos, len(self.text)))
        self.cursor_pos = new_pos
        self._reset_blink()
        return new_pos

    # ------------------------------------------------------------------
    # 渲染相关
    # ------------------------------------------------------------------

    def get_display_text(self, font, max_width: int, placeholder: str, active: bool):
        """
        返回用于显示的文本，同时更新 _display_start

        返回: (display_text, cursor_visible)
        """
        if not self.text:
            self._display_start = 0
            if active:
                return '', self._blink_visible
            else:
                return placeholder, False
        else:
            # 计算光标前的文本宽度，用于确定是否需要滚动
            cursor_text_width = font.size(self.text[:self.cursor_pos])[0]

            if cursor_text_width < max_width:
                self._display_start = 0
                return self.text, self._blink_visible
            else:
                # 找到合适的起始位置，使光标可见
                start = 0
                for i in range(self.cursor_pos, 0, -1):
                    if font.size(self.text[i:self.cursor_pos])[0] > max_width:
                        start = i + 1
                        break
                self._display_start = start
                return self.text[start:], self._blink_visible

    def get_cursor_offset(self, font) -> int:
        """获取光标在显示文本中的像素偏移"""
        if not self.text:
            return 0
        display_start = getattr(self, '_display_start', 0)
        return font.size(self.text[display_start:self.cursor_pos])[0]

    def get_selection_offsets(self, font) -> tuple:
        """
        获取选中范围在显示文本中的像素偏移

        返回: (start_offset, end_offset) 或 None 如果无选中
        """
        if not self.has_selection():
            return None

        s, e = self.get_selection_range()
        display_start = getattr(self, '_display_start', 0)

        # 将选中范围限制在显示范围内
        vis_s = max(s, display_start)
        vis_e = min(e, len(self.text))

        if vis_s >= vis_e:
            return None

        start_offset = font.size(self.text[display_start:vis_s])[0]
        end_offset = font.size(self.text[display_start:vis_e])[0]
        return (start_offset, end_offset)

    def draw(self, screen, font, rect, colors):
        """
        便捷渲染方法：将输入内容绘制到 screen

        参数:
            screen: pygame surface
            font: 字体
            rect: pygame.Rect 输入框区域
            colors: dict with keys: 'input_bg', 'input_text', 'selection_bg',
                    'input_border', 'input_active'
        """
        # 背景
        bg_color = colors.get('input_active', colors.get('input_bg', (40, 40, 40))) if self.active else colors.get('input_bg', (40, 40, 40))
        pygame.draw.rect(screen, bg_color, rect, border_radius=4)

        # 边框
        border_color = colors.get('input_border', (100, 100, 100))
        pygame.draw.rect(screen, border_color, rect, 1, border_radius=4)

        # 文本
        max_width = rect.width - 10
        display_text, cursor_visible = self.get_display_text(font, max_width, '', self.active)
        text_color = colors.get('input_text', (220, 220, 220))

        text_surface = font.render(display_text, True, text_color)
        screen.blit(text_surface, (rect.left + 5, rect.centery - text_surface.get_height() // 2))

        # 选中高亮
        sel_offsets = self.get_selection_offsets(font)
        if sel_offsets is not None:
            s_off, e_off = sel_offsets
            sel_rect = pygame.Rect(rect.left + 5 + s_off, rect.top + 3,
                                   max(e_off - s_off, 2), rect.height - 6)
            sel_color = colors.get('selection_bg', (50, 80, 160))
            pygame.draw.rect(screen, sel_color, sel_rect)
            # 重新绘制文本在高亮上层
            screen.blit(text_surface, (rect.left + 5, rect.centery - text_surface.get_height() // 2))

        # 光标
        if self.active and cursor_visible:
            cursor_x = rect.left + 5 + self.get_cursor_offset(font)
            pygame.draw.line(screen, text_color,
                             (cursor_x, rect.top + 3),
                             (cursor_x, rect.bottom - 3), 1)
