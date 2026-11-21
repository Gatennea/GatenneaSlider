# -*- coding: utf-8 -*-
"""
虚拟键盘 Mixin

提供可拖动、独立浮动的虚拟键盘面板：
- 方向键：方形 上/下/左/右；三角形 六向（↖↗ / ←→ / ↙↘）；米字格 八向（3×3 方向盘）
- 编辑键：撤销 / 重做

面板通过标题栏拖动，点击右上角 × 关闭。
"""

import math

import pygame
import pygame.gfxdraw  # noqa: F401  （pygame-ce 里要显式 import 才有 .gfxdraw）


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
        self.cubic_pan = [0.0, 0.0]   # 三维平移盘面：屏幕像素偏移（不碰逻辑坐标）
        self.vk_rot_drag = None       # 三维弧轨拖动：{fam, center, theta, last_ang}
        self._vk_rot_t = {}           # 三维弧轨把手位置：fam -> [-1, 1]

    _VK_CUBIC_AREA = 232      # 三维「陀螺仪」区域边长：端点 + 弧轨 + 中心复位

    def _vk_dir_area_height(self) -> int:
        """方向区高度：三维用一块方形区域（坐标轴要朝四面八方伸），其余按行数算。"""
        if getattr(self, 'cubic_mode', False):
            return self._VK_CUBIC_AREA
        return (self._VK_BTN + self._VK_BTN_GAP) * self._vk_direction_rows()

    def _vk_panel_size(self):
        """计算面板宽高"""
        width = self._VK_PAD * 2 + self._VK_ACTION_BTN_W * 2 + self._VK_STICKY_W + self._VK_BTN_GAP * 2
        if getattr(self, 'cubic_mode', False):
            width = max(width, self._VK_CUBIC_AREA + self._VK_PAD * 2)
        height = (self._VK_TITLE_H + self._VK_PAD
                  + self._vk_dir_area_height()
                  + self._VK_ACTION_BTN_H + self._VK_BTN_GAP
                  + self._VK_JUMP_H + self._VK_PAD)
        return width, height

    def _vk_direction_rows(self) -> int:
        """方向键行数：方形 2 行（上 / 左下右）；三角/米字/cubic 3 行（六向 / 八向 / 三轴）"""
        if getattr(self, 'cubic_mode', False):
            return 3
        if getattr(self, 'mi_mode', False) or getattr(self, 'triangle_mode', False):
            return 3
        return 2

    def _vk_cubic_origin(self) -> tuple:
        """三维坐标轴的原点（屏幕坐标）。

        端点布局与绘制必须共用这一处：之前布局按 ``_VK_CUBIC_AREA``（200）
        算中心，绘制却按「三行按钮高度」算，白点就浮在轴交点上头约半格。
        """
        panel = self.vk_panel_rect
        top = panel.top + self._VK_TITLE_H + self._VK_PAD
        return (panel.centerx, top + self._vk_dir_area_height() // 2)

    def _vk_build_cubic_dirs(self) -> dict:
        """三维键盘 = 一根**坐标轴图**：中心一个原点，六条端点沿三轴伸出去。

        为什么改成坐标轴（用户 2026-11-18「虚拟键盘設計成坐標軸那樣，六個方向
        都可以點」）：三行「左负右正」的排法把三维压成了表格，看不出这是三根
        互相垂直的轴，也看不出相机转到哪个姿态。现在端点位置直接由**当前相机
        的投影**算：某个轴正对镜头它就缩到原点附近（屏幕上压成一个点），斜着看
        就自然张开——和棋盘上的方向箭头是同一套几何。

        端点仍然落在 44×44 的命中盒里（与二维键位同尺寸，好点），只是位置不再
        按行排。
        """
        # 拖动旋转时把整块坐标轴图冻住：相机每转一点，轴投影就会跟着转，
        # 若边拖边重算，弧轨和端点会在鼠标底下跑掉。拖动期间沿用按下瞬间
        # 的布局，松手后的下一次布局再按新视角重排。
        frozen = getattr(self, '_vk_frozen_cubic', None)
        if getattr(self, 'vk_rot_drag', None) and frozen:
            self._vk_cubic_rot_tracks = frozen['tracks']
            return {k: v.copy() for k, v in frozen['rects'].items()}

        btn = 40          # 三维端点键：比二维略小，六个都要挤进坐标轴区域
        area_h = self._VK_CUBIC_AREA
        cx, cy = self._vk_cubic_origin()
        axes = self._cubic_vk_axes() if hasattr(self, '_cubic_vk_axes') else {}
        rects = {}
        reach = area_h / 2.0 - btn / 2.0 - 6.0
        for letter, (dx, dy, plen) in axes.items():
            # 投影越短（越正对镜头）端点越靠近原点：最短 22px，最长 = 区域半径
            r = 22.0 + (reach - 22.0) * min(1.0, plen)
            if plen < 0.15:
                # 这条轴正对镜头：投影理论上是一个点。不硬造第三根线，两个端盘
                # 沿**斜对角**错开（不压在另外两根轴上），一个朝观察者、一个背向。
                off = 30
                px, py = (cx + off, cy + off) if letter.isupper() else (cx - off, cy - off)
            else:
                px, py = cx + dx * r, cy + dy * r
            panel = self.vk_panel_rect
            px = min(max(px, panel.left + btn / 2 + 4), panel.right - btn / 2 - 4)
            py = min(max(py, cy - area_h / 2 + btn / 2 + 2),
                     cy + area_h / 2 - btn / 2 - 2)
            rects['cubic_' + letter] = pygame.Rect(
                int(px - btn / 2), int(py - btn / 2), btn, btn)
        # 分离：某两条轴的端点在屏幕上挨得太近（甚至投影到同一处）时，两个键
        # 会互相吃点击。这里做几轮「沿连线互相推开」的松弛：位置只会从理想投影
        # 挪开一点点，但「点得中」比「摆得准」重要。绘制与命中用同一份 rect。
        keys = sorted(rects)
        lo_x = self.vk_panel_rect.left + btn / 2 + 4
        hi_x = self.vk_panel_rect.right - btn / 2 - 4
        lo_y = cy - area_h / 2 + btn / 2 + 2
        hi_y = cy + area_h / 2 - btn / 2 - 2
        pad = 5.0
        for _ in range(14):
            moved = False
            for i, a in enumerate(keys):
                for b in keys[i + 1:]:
                    ra, rb = rects[a], rects[b]
                    ca, cb = ra.center, rb.center
                    dxm = cb[0] - ca[0]
                    dym = cb[1] - ca[1]
                    dist = math.hypot(dxm, dym)
                    need = pad + btn
                    if dist >= need:
                        continue
                    if dist < 1e-6:
                        dxm, dym, dist = 0.0, -1.0, 1.0
                    push = (need - dist) / 2.0 + 0.5
                    ux, uy = dxm / dist * push, dym / dist * push
                    ra.move_ip(-int(round(ux)), -int(round(uy)))
                    rb.move_ip(int(round(ux)), int(round(uy)))
                    for rr in (ra, rb):
                        rr.center = (min(max(rr.centerx, int(lo_x)), int(hi_x)),
                                     min(max(rr.centery, int(lo_y)), int(hi_y)))
                    moved = True
            if not moved:
                break

        # 中心复位：只有视角已经离开默认斜视才出现；回正后自己消失。
        if not self._cubic_camera_is_default():
            rects['gyro_reset'] = pygame.Rect(cx - 8, cy - 8, 16, 16)

        # 内圈「旋转弧轨」：每条轴中段一段 36×36 的半圆弧轨，弧上有一个
        # 可拖把手；弧两端各有一个 15° 步进点。弧轨只占位，不当作普通按钮，
        # 拖动由 handle_virtual_keyboard_event 的 vk_rot_drag 分支处理。
        self._vk_cubic_rot_tracks = {}
        occupied = [rects['cubic_' + c] for c in 'cCdDrR' if 'cubic_' + c in rects]
        if 'gyro_reset' in rects:
            occupied.append(rects['gyro_reset'])
        for fam in ('r', 'c', 'd'):
            hi = rects.get('cubic_' + fam.upper())
            if hi is None:
                continue
            dx, dy = hi.centerx - cx, hi.centery - cy
            dist = math.hypot(dx, dy)
            box = None
            axis_theta = None
            if dist >= 68.0:
                ux, uy = dx / dist, dy / dist
                axis_theta = math.atan2(-uy, ux)
                for t in range(int(dist - 42.0), 25, -4):
                    cand = pygame.Rect(int(cx + ux * t - 18),
                                       int(cy + uy * t - 18), 36, 36)
                    if not self.vk_panel_rect.contains(cand):
                        continue
                    if any(cand.colliderect(r) for r in occupied):
                        continue
                    box = cand
                    break
            if box is None:
                # 轴几乎正对镜头：在原点周围找空位放一段同色弧轨。
                start = {'r': 90, 'c': 210, 'd': 330}.get(fam, 90)
                for radius in (28, 36, 44, 52, 60, 68, 76, 84, 92):
                    for k in range(12):
                        ang = math.radians(start + k * 30)
                        cand = pygame.Rect(
                            int(cx + math.cos(ang) * radius - 18),
                            int(cy - math.sin(ang) * radius - 18), 36, 36)
                        if not self.vk_panel_rect.contains(cand):
                            continue
                        if any(cand.colliderect(r) for r in occupied):
                            continue
                        box = cand
                        axis_theta = ang
                        break
                    if box is not None:
                        break
            if box is None:
                continue
            # 弧两端：各让出 60° 的短弧段，起点 = 左端 15° 步进，终点 = 右端。
            half_span = math.radians(60.0)
            start_pt = (box.centerx + math.cos(axis_theta + math.pi / 2.0
                                               - half_span) * 12.0,
                        box.centery - math.sin(axis_theta + math.pi / 2.0
                                               - half_span) * 12.0)
            end_pt = (box.centerx + math.cos(axis_theta + math.pi / 2.0
                                             + half_span) * 12.0,
                      box.centery - math.sin(axis_theta + math.pi / 2.0
                                             + half_span) * 12.0)
            rects['gyro_cw_' + fam] = pygame.Rect(
                int(start_pt[0] - 6), int(start_pt[1] - 6), 12, 12)
            rects['gyro_ccw_' + fam] = pygame.Rect(
                int(end_pt[0] - 6), int(end_pt[1] - 6), 12, 12)
            self._vk_cubic_rot_tracks[fam] = {
                'box': box,
                'theta': axis_theta,
                'span': half_span,
            }
            occupied.append(box)

        return rects


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
        if getattr(self, 'cubic_mode', False):
            rects.update(self._vk_build_cubic_dirs())
        elif getattr(self, 'mi_mode', False):
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
        action_row_y = top_row_y + self._vk_dir_area_height()
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
        # S0-2：绘制前先确保面板坐标在可视范围内
        self._vk_clamp_position()

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
        if getattr(self, 'cubic_mode', False):
            self._vk_draw_cubic_buttons(rects, mouse_pos)
        elif getattr(self, 'mi_mode', False):
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
        # 三维态已在上面按三轴六键单独画过（含粘滞/撤销/重做），这里跳过通用画法
        for action, rect in (() if getattr(self, 'cubic_mode', False) else rects.items()):
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

    def _vk_cubic_rot_track_hit(self, pos):
        """点在一条旋转弧轨的 36×36 占位框里？"""
        mx, my = pos
        for fam, data in getattr(self, '_vk_cubic_rot_tracks', {}).items():
            if data['box'].collidepoint(mx, my):
                return fam, data
        return None, None

    def _vk_cubic_rot_angle(self, data, pos):
        """鼠标相对弧轨圆心的数学角（屏幕 y 轴翻转）。"""
        cx, cy = data['box'].center
        return math.atan2(cy - pos[1], pos[0] - cx)

    def _vk_cubic_rot_begin(self, pos):
        fam, data = self._vk_cubic_rot_track_hit(pos)
        if fam is None:
            return False
        box = data['box']
        dist = math.hypot(pos[0] - box.centerx, pos[1] - box.centery)
        if not (5.0 <= dist <= 20.0):
            return False          # 点弧线附近才抓得住把手，点圆心不启动
        ang = self._vk_cubic_rot_angle(data, pos)
        mid = data['theta'] + math.pi / 2.0
        span = data.get('span', math.pi / 2.0)
        rel = (ang - mid + math.pi) % (2.0 * math.pi) - math.pi
        t = max(-1.0, min(1.0, rel / span))
        self._vk_rot_t[fam] = t
        self.vk_rot_drag = {'fam': fam, 'data': data, 'last_ang': ang}
        self._vk_frozen_cubic = {
            'rects': {k: v.copy() for k, v in self.vk_rects.items()
                      if k.startswith('cubic_') or k.startswith('gyro_')},
            'tracks': {f: {'box': d['box'].copy(), 'theta': d['theta'],
                           'span': d.get('span', math.pi / 2.0)}
                       for f, d in self._vk_cubic_rot_tracks.items()},
        }
        return True

    def _vk_cubic_rot_update(self, pos):
        drag = getattr(self, 'vk_rot_drag', None)
        if not drag:
            return False
        fam = drag['fam']
        data = drag['data']
        ang = self._vk_cubic_rot_angle(data, pos)
        delta = (math.degrees(ang - drag['last_ang']) + 180.0) % 360.0 - 180.0
        drag['last_ang'] = ang
        t_old = float(self._vk_rot_t.get(fam, 0.0))
        t_new = max(-1.0, min(1.0, t_old + delta / 90.0))
        applied = (t_new - t_old) * 90.0
        self._vk_rot_t[fam] = t_new
        if abs(applied) > 0.01:
            self._cubic_vk_spin(fam, applied)
        return True

    def _vk_cubic_rot_end(self):
        if getattr(self, 'vk_rot_drag', None):
            self.vk_rot_drag = None
            self._vk_frozen_cubic = None
            return True
        return False

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
                    self.vk_rot_drag = None
                    self._vk_frozen_cubic = None
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
                # 功能按钮（隐藏的条件键仍占位，但吃掉点击、不触发动作）
                for action, rect in self.vk_rects.items():
                    if rect.collidepoint(mx, my):
                        if not self._cubic_vk_action_visible(action):
                            return True
                        self._vk_trigger_action(action)
                        return True
                # 旋转弧轨：端点步进键已经在上面处理；其余落在弧轨框里的
                # 点击 = 抓住把手开始拖，不走普通按钮。
                if self._vk_cubic_rot_begin((mx, my)):
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
            if self._vk_cubic_rot_update(event.pos):
                return True
            if self.vk_dragging:
                self.vk_pos[0] = event.pos[0] - self.vk_drag_offset[0]
                self.vk_pos[1] = event.pos[1] - self.vk_drag_offset[1]
                self._vk_clamp_position()
                return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._vk_cubic_rot_end():
                return True
            if self.vk_dragging:
                self.vk_dragging = False
                return True

        return False

    def _vk_trigger_action(self, action):
        """触发虚拟键盘按钮对应的操作"""
        # 教程解法播放中：锁定棋盘操作（撤销/重做/移动/粘滞）
        if self._tut_board_locked():
            return
        # 三维三轴六键：有选中 = 推一步，没选中 = 平移盘面（方案 §1）
        if action.startswith('gyro_cw_') or action.startswith('gyro_ccw_'):
            self._cubic_vk_rotate(action)
            return
        if action == 'gyro_reset':
            self._cubic_view_oblique()
            return
        if action.startswith('cubic_'):
            self._cubic_vk_six(action.split('_', 1)[1])
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
            gen = self._generic_spec() is not None
            if mi or gen:
                # 米字格八向與碎三角通用通道共用這張表：↖ 是 q（不是三角
                # 版的 w）。碎三角 12 個字母裡活躍的 8 個（d/a/w/s/e/q/z/x）
                # 落屏方向與米字八向完全一致（S2c 實測），死族的 4 個字母
                # （r/t/f/g）沒有按鍵——按了也不會被 allowed 放行。
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
                msg = "请先选中缝隙和滑块" if not mi else "请先点选缝隙"
                if mi and self._mi_shifted() and direction in ('a', 'd', 'w', 's'):
                    # 错位态下这一族可能一条不剩，连「该点哪条」都得先交代
                    msg += "（错位态：%s）" % self._mi_hv_left(
                        'h' if direction in ('a', 'd') else 'v')
                self.macro_notify_msg = msg
                self.macro_notify_timer = 90
                return

            gap_type, _ = self.selected_gap
            # 方向必须与选中缝隙平行：方形 h→a/d、v→w/s；
            # 三角形 h→a/d、p→e/z、n→w/x；米字格 h→a/d、v→w/s、
            # d1→q/x、d2→e/z；通用通道（碎三角等）問板型數據反查的
            # 字母表（_gap_dir_letters，與渲染器/註解同一源）
            if mi:
                from game_mi import GAP_DIRECTIONS as MI_GAP_DIRECTIONS
                allowed = MI_GAP_DIRECTIONS.get(gap_type, ())
            elif gen:
                allowed = self._gap_dir_letters(gap_type)
            elif getattr(self, 'triangle_mode', False):
                from game_triangle import GAP_DIRECTIONS
                allowed = GAP_DIRECTIONS.get(gap_type, ())
            else:
                allowed = ('w', 's') if gap_type == 'v' else ('a', 'd')

            if direction in allowed:
                self.move_selected_blocks(direction)
            elif mi and self._mi_shifted() and direction in ('a', 'd', 'w', 's'):
                # 错位态：横竖縫大半切在块里，按这一族实际还剩几条说，
                # 别只说「不平行」（规划 §5 手动验收第 3 条）
                fam = 'h' if direction in ('a', 'd') else 'v'
                self.macro_notify_msg = ("移动方向与缝隙方向不匹配（错位态："
                                         + self._mi_hv_left(fam) + "）")
                self.macro_notify_timer = 120
            else:
                self.macro_notify_msg = "移动方向与缝隙方向不匹配"
                self.macro_notify_timer = 90

    @staticmethod
    def _vk_aa_circle(surface, color, center, radius, width=0):
        """gfxdraw 抗锯齿圆：填充/描边都比 draw.circle 干净。"""
        cx, cy, r = int(round(center[0])), int(round(center[1])), int(radius)
        if width <= 0:
            pygame.gfxdraw.filled_circle(surface, cx, cy, r, color)
            pygame.gfxdraw.aacircle(surface, cx, cy, r, color)
            return
        pygame.gfxdraw.aacircle(surface, cx, cy, r, color)
        if width >= 2:
            pygame.gfxdraw.aacircle(surface, cx, cy, r - 1, color)

    @staticmethod
    def _vk_aa_polygon(surface, color, points):
        """gfxdraw 抗锯齿多边形：轴端箭头、盘心箭头不再锯齿。"""
        pts = [(int(round(x)), int(round(y))) for x, y in points]
        pygame.gfxdraw.filled_polygon(surface, pts, color)
        pygame.gfxdraw.aapolygon(surface, pts, color)

    @staticmethod
    def _vk_aa_line(surface, color, a, b, width=2):
        """抗锯齿直线：用两条 1px aaline 并排模拟 2px，斜轴不会阶梯化。"""
        if width <= 1:
            pygame.draw.aaline(surface, color, a, b)
            return
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1.0
        px, py = -dy / ln * 0.6, dx / ln * 0.6
        for s in (-1.0, 1.0):
            pygame.draw.aaline(surface, color,
                               (a[0] + px * s, a[1] + py * s),
                               (b[0] + px * s, b[1] + py * s))

    def _vk_draw_cubic_buttons(self, rects, mouse_pos):
        """三维键盘：画成一根**投影坐标系**（三根带箭头的轴 + 六个可点端盘）。

        用户口径（2026-11-18）：「我要坐標軸投影，隨著滑塊視角一起轉」，
        不是六个散开的方键。所以：

          · 每族一条直轴，从负端穿过原点连到正端，颜色区分 r 红 / c 蓝 / d 绿；
          · 只在**正端**画箭头（r/R 的正方向），负端是轴的另一头；
          · 两端各一个圆形端盘（纯色，不写字母），整盘是命中盒——仍可六向点；
          · 端点位置由相机投影给出，旋转棋盘时这根三脚架跟着转；
          · 轴缩短到成一点（正对镜头）时，两端盘沿屏幕横轴拉开，仍各自可点。
        """
        axes = self._cubic_vk_axes() if hasattr(self, '_cubic_vk_axes') else {}
        axis_colors = {'r': (226, 120, 120), 'c': (98, 156, 232), 'd': (110, 200, 130)}
        panel = self.vk_panel_rect
        area_h = self._vk_dir_area_height()
        origin = self._vk_cubic_origin()

        pos = {action.split('_', 1)[1]: rect.center
               for action, rect in rects.items() if action.startswith('cubic_')}

        # ① 三根轴：负端 → 正端一条直线（穿过原点），只画一次
        for fam in ('r', 'c', 'd'):
            lo, hi = pos.get(fam), pos.get(fam.upper())
            if lo is None or hi is None:
                continue
            color = axis_colors[fam]
            self._vk_aa_line(self.screen, color, lo, hi, 2)
            # 正端箭头：朝轴外侧
            ux, uy = hi[0] - lo[0], hi[1] - lo[1]
            ln = math.hypot(ux, uy)
            plen = axes.get(fam, (0.0, 0.0, 0.0))[2]
            if plen < 0.15:
                # 正对镜头的轴：两个端盘是人为错开的，再连一条线会被读成「斜轴」，
                # 干脆不画线、不画箭头——只剩两个同色端盘点在原点旁边。
                continue
            if ln < 1e-6:
                continue
            ux, uy = ux / ln, uy / ln
            # 箭头要画在端盘**外面**（端盘半径约 19px，画在里面就被盘盖住了）
            r_hi = max(rects['cubic_' + fam.upper()].width,
                       rects['cubic_' + fam.upper()].height) // 2
            pxv, pyv = -uy, ux
            tip = (hi[0] + ux * (r_hi + 13.0), hi[1] + uy * (r_hi + 13.0))
            base = (hi[0] + ux * (r_hi + 3.0), hi[1] + uy * (r_hi + 3.0))
            self._vk_aa_polygon(self.screen, color, [
                (int(tip[0]), int(tip[1])),
                (int(base[0] + pxv * 6.0), int(base[1] + pyv * 6.0)),
                (int(base[0] - pxv * 6.0), int(base[1] - pyv * 6.0)),
            ])

        # ② 端点盘：纯色圆盘，hover 提亮；不再写字形/轴名
        #    （用户 2026-11-18：去掉虚拟键盘字母标记，避免相机旋转后
        #     字母与实际方向对不上，反而误导。）
        for action, rect in rects.items():
            if action.startswith('gyro_') or action == 'gyro_reset':
                continue                  # 陀螺环/复位在端点之后单独画
            if not action.startswith('cubic_'):
                # 粘滞 / 撤销 / 重做：与二维同一套画法
                hovered = rect.collidepoint(mouse_pos)
                color = (self.colors['button_hover']
                         if (action == 'sticky' and self.vk_sticky) or hovered
                         else self.colors['button_bg'])
                pygame.draw.rect(self.screen, color, rect, border_radius=4)
                if action == 'sticky' and self.vk_sticky:
                    pygame.draw.rect(self.screen, (255, 205, 60), rect, 2, border_radius=4)
                label = {'sticky': '粘滞' + ('开' if self.vk_sticky else '关'),
                         'undo': '撤销', 'redo': '重做'}.get(action, '')
                if label:
                    surf = self.dialog_font.render(label, True, (255, 255, 255))
                    self.screen.blit(surf, surf.get_rect(center=rect.center))
                continue

            letter = action.split('_', 1)[1]
            fam = letter.lower()
            hovered = rect.collidepoint(mouse_pos)
            center = rect.center
            state = self._cubic_vk_endpoint_state(letter)
            if state == 'off':
                # 条件不满足：不画按键、不吃点击；只留暗点保住轴端位置。
                self._vk_aa_circle(self.screen, (62, 64, 72), center, 3)
                continue
            if state == 'seam':
                # 法线轴：两个端点不做推块，改成「上/下一个切面」。
                # 方形键 + 双箭头，和圆形推块端盘明确区分。
                dx, dy = center[0] - origin[0], center[1] - origin[1]
                ln = math.hypot(dx, dy)
                if ln < 1e-6:
                    dx, dy = ((0.0, -1.0) if letter.isupper()
                              else (0.0, 1.0))
                else:
                    dx, dy = dx / ln, dy / ln
                btn = pygame.Rect(center[0] - 14, center[1] - 14, 28, 28)
                self._cubic_draw_seam_step_button(
                    self.screen, btn, (dx, dy), axis_colors[fam],
                    True, hovered)
                continue

            radius = min(rect.width, rect.height) // 2 - 1
            if state == 'push':
                fill = (axis_colors[fam] if hovered
                        else tuple(int(v * 0.42) for v in axis_colors[fam]))
            else:                          # pan：没选中，端点只做视角平移
                fill = (72, 76, 86) if hovered else (40, 42, 50)
            self._vk_aa_circle(self.screen, fill, center, radius)
            self._vk_aa_circle(self.screen, axis_colors[fam], center, radius,
                               2 if state == 'push' else 1)

            dx, dy = center[0] - origin[0], center[1] - origin[1]
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                continue
            ux, uy = dx / ln, dy / ln
            if state == 'push':
                # 可用方向预览：盘心一个朝轴外的白色小箭头，表示这一端能推。
                tip = (center[0] + ux * 10.0, center[1] + uy * 10.0)
                base = (center[0] + ux * 3.0, center[1] + uy * 3.0)
                pxv, pyv = -uy * 4.5, ux * 4.5
                self._vk_aa_polygon(self.screen, (245, 246, 250), [
                    (tip[0], tip[1]),
                    (base[0] + pxv, base[1] + pyv),
                    (base[0] - pxv, base[1] - pyv),
                ])
            else:
                # 平移提示：一小段垂直双向箭头，和“推”的单向箭头区分。
                ax, ay = center[0] - ux * 7.0, center[1] - uy * 7.0
                bx, by = center[0] + ux * 7.0, center[1] + uy * 7.0
                self._vk_aa_line(self.screen, (210, 214, 224),
                                 (ax, ay), (bx, by), 1)
                pxv, pyv = -uy * 2.5, ux * 2.5
                for ex, ey, s in ((ax, ay, 1.0), (bx, by, -1.0)):
                    self._vk_aa_polygon(self.screen, (210, 214, 224), [
                        (ex, ey),
                        (ex + ux * s * 4.0 + pxv, ey + uy * s * 4.0 + pyv),
                        (ex + ux * s * 4.0 - pxv, ey + uy * s * 4.0 - pyv),
                    ])

        # ③ 内圈旋转弧轨：半圆弧 + 可拖把手 + 两端 15° 步进箭头
        for fam, data in getattr(self, '_vk_cubic_rot_tracks', {}).items():
            hovered = data['box'].collidepoint(mouse_pos)
            self._cubic_draw_rot_track(
                self.screen, data, axis_colors[fam],
                float(self._vk_rot_t.get(fam, 0.0)), hovered)

        # ④ 原点：视角已离开默认斜视时，这里变成「复位」小键；否则只是白点
        if 'gyro_reset' in rects:
            hovered = rects['gyro_reset'].collidepoint(mouse_pos)
            self._cubic_draw_reset_button(self.screen, origin, hovered)
        else:
            self._vk_aa_circle(self.screen, (228, 228, 238), origin, 4)
            self._vk_aa_circle(self.screen, (120, 120, 136), origin, 6, 1)


    def _cubic_draw_arc_arrow(self, surface, center, radius, start_deg,
                              end_deg, color, width=2):
        """画一段圆弧并在末端加箭头；角度按数学正方向（屏幕 y 轴翻转）。"""
        steps = 18
        pts = []
        for i in range(steps + 1):
            a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            pts.append((center[0] + math.cos(a) * radius,
                        center[1] - math.sin(a) * radius))
        if len(pts) >= 2:
            pygame.draw.lines(surface, color, False,
                              [(int(x), int(y)) for x, y in pts], width)
        # 末端切线方向（沿参数前进方向）
        ax, ay = pts[-2]
        bx, by = pts[-1]
        tx, ty = bx - ax, by - ay
        ln = math.hypot(tx, ty) or 1.0
        tx, ty = tx / ln, ty / ln
        px, py = -ty * 4.0, tx * 4.0
        tip = (bx + tx * 4.0, by + ty * 4.0)
        pygame.draw.polygon(surface, color, [
            (int(tip[0]), int(tip[1])),
            (int(bx + px), int(by + py)),
            (int(bx - px), int(by - py)),
        ])

    def _cubic_draw_rot_track(self, surface, data, color, t, hovered=False):
        """旋转弧轨：120° 短弧 + 中点可拖把手；两端 −/+ 是 15° 步进点。

        这段线条很细、半径又小，直接在屏幕上 draw.lines/draw.circle 会出现
        明显锯齿（用户说的「毛毛糙糙」）。统一先在 4 倍画布上画，再
        smoothscale 回 36×36：弧线、十字、白芯把手都能拿到抗锯齿边缘。
        """
        ss = 4
        size = data['box'].width
        big = pygame.Surface((size * ss, size * ss), pygame.SRCALPHA)
        c = size * ss / 2.0
        radius = 12.0 * ss
        theta = math.degrees(data['theta'])
        span = math.degrees(data.get('span', math.pi / 2.0))
        ink = tuple(min(255, int(v * 1.2)) for v in color) if hovered else color
        dim = tuple(max(0, int(v * 0.55)) for v in color)
        width = (3 if hovered else 2) * ss
        # 整条弧轨是一条连续的槽线，不再拆成两枚箭头（避免又读成「环」）。
        pts = []
        for i in range(49):
            a = math.radians(theta + 90.0 - span
                             + 2.0 * span * i / 48.0)
            pts.append((int(c + math.cos(a) * radius),
                        int(c - math.sin(a) * radius)))
        pygame.draw.lines(big, ink, False, pts, width)
        # 三道刻度：中点 + 两边半个行程。
        for k in (-span / 2.0, 0.0, span / 2.0):
            a = math.radians(theta + 90.0 + k)
            pygame.draw.line(
                big, dim,
                (int(c + math.cos(a) * 9.0 * ss),
                 int(c - math.sin(a) * 9.0 * ss)),
                (int(c + math.cos(a) * 15.0 * ss),
                 int(c - math.sin(a) * 15.0 * ss)), ss)
        # 两端步进点：左 −15°，右 +15°，用短横/十字标出来。
        for sign in (-1.0, 1.0):
            a = math.radians(theta + 90.0 + sign * span)
            ex = int(c + math.cos(a) * radius)
            ey = int(c - math.sin(a) * radius)
            arm = 3 * ss
            pygame.draw.line(big, ink, (ex - arm, ey), (ex + arm, ey),
                             2 * ss)
            if sign > 0:
                pygame.draw.line(big, ink, (ex, ey - arm), (ex, ey + arm),
                                 2 * ss)
        # 把手：沿弧 t∈[-1,1]，0 在弧中点；白芯 + 轴色描边。
        a = math.radians(theta + 90.0 + t * span)
        hx = c + math.cos(a) * radius
        hy = c - math.sin(a) * radius
        pygame.draw.circle(big, (32, 34, 42),
                           (int(hx), int(hy)), 5 * ss)
        pygame.draw.circle(big, (245, 246, 250),
                           (int(hx), int(hy)), 4 * ss)
        pygame.draw.circle(big, ink, (int(hx), int(hy)), 4 * ss, ss)
        small = pygame.transform.smoothscale(big, (size, size))
        surface.blit(small, data['box'].topleft)

    def _cubic_draw_reset_button(self, surface, center, hovered=False):
        """中心复位键：一个小回环箭头；只有视角离开默认斜视时出现。"""
        color = (255, 214, 102) if hovered else (200, 204, 214)
        self._vk_aa_circle(surface, (40, 42, 50), center, 8)
        self._vk_aa_circle(surface, color, center, 8, 1)
        self._cubic_draw_arc_arrow(surface, center, 5.0, 300.0, 30.0,
                                   color, 1)

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
