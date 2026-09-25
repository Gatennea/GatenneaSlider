# -*- coding: utf-8 -*-
"""
渲染相关 Mixin

包含：
- draw_board: 绘制游戏主界面（网格、缝隙、滑块）
- draw_menu_bar: 绘制顶部菜单栏
- draw_status_bar: 绘制底部状态栏
- draw_right_panel: 绘制右侧动画控制面板
- 各下拉菜单绘制方法
"""

import math

import pygame

from game_mi import mi_key, mi_vertices
from game_triangle import tri_key
from gui.cell_class import cell_class, class_index
from gui.mi_view import MiBoardView
from gui.triangle_view import TriangleBoardView
from records import format_time


class RendererMixin:
    """渲染相关方法 Mixin"""

    def _tri_view(self) -> TriangleBoardView:
        """三角形棋盤視圖（隨 cell_size/gap_width 緩存重建）。"""
        view = getattr(self, '_triangle_view', None)
        if (view is None or view.cell_size != self.cell_size
                or view.gap_width != self.gap_width):
            view = TriangleBoardView(self.cell_size, self.gap_width)
            self._triangle_view = view
        return view

    def _mi_view(self) -> MiBoardView:
        """米字格棋盤視圖（隨 cell_size/gap_width 緩存重建）。"""
        view = getattr(self, '_mi_board_view', None)
        if (view is None or view.cell_size != self.cell_size
                or view.gap_width != self.gap_width):
            view = MiBoardView(self.cell_size, self.gap_width)
            self._mi_board_view = view
        return view

    def _draw_triangle_grid(self, view: TriangleBoardView):
        """繪製三角網格背景（三族平行線，間距 = 三角高）。

        直接由世界座標除以間距求起止索引，不像方形版那樣逐格矩形，
        因此不存在 double-zoom 類的累計誤差。
        """
        world_left, world_top = self.screen_to_world(0, 0)
        world_right, world_bottom = self.screen_to_world(
            self.screen_width, self.screen_height)
        corners = ((world_left, world_top), (world_right, world_top),
                   (world_left, world_bottom), (world_right, world_bottom))
        color = self.colors['grid']

        # 水平族
        for level in view.grid_h_levels(world_top, world_bottom):
            y = view.grid_h_y(level)
            p1 = self.world_to_screen(world_left, y)
            p2 = self.world_to_screen(world_right, y)
            pygame.draw.line(self.screen, color, p1, p2, 1)

        # 兩組斜族
        for gap_type in ('p', 'n'):
            for level in view.grid_oblique_levels(gap_type, corners):
                x_top = view.grid_oblique_x(gap_type, level, world_top)
                x_bottom = view.grid_oblique_x(gap_type, level, world_bottom)
                p1 = self.world_to_screen(x_top, world_top)
                p2 = self.world_to_screen(x_bottom, world_bottom)
                pygame.draw.line(self.screen, color, p1, p2, 1)

    def _draw_triangle_selected_gap(self, view: TriangleBoardView, hull):
        """繪製選中的縫隙線（三族之一），只畫在棋形範圍內。

        方形版的紅線貫穿整個視窗、由滑塊蓋住；三角版的棋形是三角形，
        畫到形狀外的線段只是雜訊，故裁剪到棋形凸包。裁剪只看凸包、不看
        「縫隙兩側是否都有相鄰塊」，所以洞裡紅線仍然連續，與原版一致。
        沒有這條線時，選中縫隙只有右下角文字提示，玩家看不到選了哪條。
        """
        gap = getattr(self, 'selected_gap', None)
        if not gap:
            return
        gap_type, line = gap
        if gap_type not in ('h', 'p', 'n'):
            return
        seg = view.gap_line_segment(gap_type, line, hull)
        if seg is None:
            return
        pygame.draw.line(self.screen, self.colors['line'],
                         self.world_to_screen(*seg[0]),
                         self.world_to_screen(*seg[1]), 3)

    def _draw_triangle_gaps(self, view: TriangleBoardView, cells, hull):
        """繪製未選中的縫隙（灰色），與方形版一致：選中那條改畫紅線。

        方形版把棋盤矩形範圍內每條 h/v 分割線畫成 colors['gap']；三角版的
        棋形不是矩形，改為裁剪到棋形凸包，線就不會伸到三角形外面的空白處。
        原版先畫線、後畫滑塊蓋住，洞裡也留直線，故這裡不按相鄰塊截斷。
        矩形四邊在原版裡也畫灰線，故這裡補上外輪廓，棋盤才有完整邊界。
        """
        width = max(1, int(self.gap_width * self.zoom))
        for gap_type, line in self.game.all_gaps():
            if self.selected_gap == (gap_type, line):
                continue
            seg = view.gap_line_segment(gap_type, line, hull)
            if seg is None:
                continue
            pygame.draw.line(self.screen, self.colors['gap'],
                             self.world_to_screen(*seg[0]),
                             self.world_to_screen(*seg[1]), width)
        for p1, p2 in view.boundary_edges(cells):
            pygame.draw.line(self.screen, self.colors['gap'],
                             self.world_to_screen(*p1),
                             self.world_to_screen(*p2), width)

    def draw_triangle_board(self):
        """繪製三角形密鋪棋盤（含 B2 的拖拽實時預覽）。"""
        self.screen.fill(self.colors['background'])

        view = self._tri_view()
        self._draw_triangle_grid(view)
        cells = self.game.positions()
        hull = view.board_hull(cells)
        self._draw_triangle_gaps(view, cells, hull)
        self._draw_triangle_selected_gap(view, hull)

        scaled_cell = self.cell_size * self.zoom
        # 拖拽跟隨：選中組沿鎖定方向平移 di/dj 格（斜座標，可為小數）
        follow_map = {}
        if self.drag_following:
            di, dj = self.drag_follow_offset
            if abs(di) > 1e-9 or abs(dj) > 1e-9:
                for block in self.game.blocks:
                    if block.be_opted:
                        i, j, up = tri_key(block)
                        follow_map[id(block)] = (i + di, j + dj, up)

        # 移動動畫 / 撤銷重做動畫：整組沿同一斜座標位移插值（up 朝向不變）
        anim_map = {}
        if self.animating and self.anim_blocks:
            t = self.ease_out(self.anim_progress)
            di = self._anim_dr * t
            dj = self._anim_dc * t
            for idx, block in enumerate(self.anim_blocks):
                si, sj, sup = self.anim_start_pos[idx]
                anim_map[id(block)] = (si + di, sj + dj, sup)

        selected = []
        normal = []
        for block in self.game.blocks:
            if id(block) in follow_map:
                i, j, up = follow_map[id(block)]
                is_follow = True
            elif id(block) in anim_map:
                i, j, up = anim_map[id(block)]
                is_follow = False
            else:
                i, j, up = tri_key(block)
                is_follow = False
            cx, cy = view.piece_center(i, j, up)
            sx, sy = self.world_to_screen(cx, cy)
            if (sx < -scaled_cell or sx > self.screen_width + scaled_cell
                    or sy < -scaled_cell or sy > self.screen_height + scaled_cell):
                continue
            # 高亮只认 be_opted：未選縫隙時點滑塊不會有任何反應（與方形一致），
            # 單獨的 selected_block 不是一種可視狀態
            hi = block.be_opted
            (selected if hi else normal).append(
                (block, i, j, up, is_follow))

        # 悬停连锁提示：同類（含朝向）的塊提亮、空位實心提亮（悬停键更亮）
        hint_occ, hint_empty, hint_hover = self._chain_hint_cells()

        for group, is_selected in ((normal, False), (selected, True)):
            for block, i, j, up, is_follow in group:
                fill = self.colors['block_selected'] if is_selected else self.colors['block']
                border_color = self.colors['border']
                border_w = max(1, int(2 * self.zoom))
                ring_color = None
                # 拖拽越界（碰撞/斷開/超過可達上限）：變暗 + 橙色邊框提示不可移動
                if is_follow and self.drag_follow_invalid:
                    fill = tuple(int(ch * 0.45) for ch in fill[:3])
                    border_color = (220, 80, 40)
                    border_w = max(1, int(3 * self.zoom))
                else:
                    # 分组着色：從外側向內一圈的縮環畫法（朝向不參與著色）。
                    # 描邊色不能直接換成組色：pygame 多邊形描邊以邊線為中心
                    # 向外也擴半個線寬，會漫進塊間縫隙蓋住縫線（含選中紅線），
                    # 縮環後著色帶整體落在滑塊內，與方形 rect 描邊同觀感
                    if getattr(self, 'coloring_enabled', False) and self.current_step > 1:
                        ring_color = self._group_color_for((i, j))
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(i, j, up)]
                pygame.draw.polygon(self.screen, fill, poly)
                pygame.draw.polygon(self.screen, border_color, poly, border_w)
                # 连锁提示：同類塊叠半透明白（hover 更亮）
                if hint_occ is not None and (i, j, up) in hint_occ:
                    self._draw_hint_overlay(poly, (i, j, up) == hint_hover)
                if ring_color is not None:
                    ring_w = max(2, int(4 * self.zoom))
                    pygame.draw.polygon(self.screen, ring_color,
                                        self._tri_ring(poly, ring_w / 2.0),
                                        ring_w)

                if getattr(self, 'numbered', False) and getattr(block, 'number', None):
                    font_size = max(12, int(scaled_cell * 0.45))
                    if not hasattr(self, '_num_font_cache'):
                        self._num_font_cache = {}
                    font = self._num_font_cache.get(font_size)
                    if font is None:
                        from GUI import _gui_safe_font
                        font = _gui_safe_font('SimHei', font_size)
                        self._num_font_cache[font_size] = font
                    cx, cy = view.piece_center(i, j, up)
                    text = font.render(str(block.number), True, (0, 0, 0))
                    text_rect = text.get_rect(
                        center=self.world_to_screen(cx, cy))
                    self.screen.blit(text, text_rect)

        # 悬停连锁提示：同類空位叠半透明白（与方形空格同一套语言，
        # 不是描边轮廓——轮廓会让空位看着像有块）
        if hint_empty:
            for (i, j, up) in sorted(hint_empty):
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(i, j, up)]
                self._draw_hint_overlay(poly, (i, j, up) == hint_hover)

    def draw_mi_board(self):
        """繪製米字格棋盤（两次触控 + 虚拟键盘，方向由第二下的拖动给出）。

        背景是「方格 + 每格兩條對角線」的米字紋理，按棋形凸包裁剪
        （與三角版同理：線不伸到棋形外的空白處，洞裡也不畫）。
        單位塊以內心為中心內縮 gap_width/2，相鄰塊之間剛好留出
        視覺間隙；be_opted 的塊用選中色，選中的縫疊一條紅線。
        拖拽跟隨時選中組沿鎖定方向平移 dr/dc 個小數格實時預覽（q 朝向
        在平移下不變），越過可達上限則整組變暗 + 橙色邊框；移動動畫
        整組沿同一格座標位移插值。
        """
        self.screen.fill(self.colors['background'])

        view = self._mi_view()
        # 移動動畫 / 撤銷重做動畫：整組平移 dr/dc 格（位移表見
        # gui/animation._move_delta，撤銷時是反向），單位塊的朝向 q 在平移下
        # 不變，插值只需動前兩個分量。動畫中的當前位置要畫進凸包，否則背景
        # 網格和紅縫會提前跳到終點。
        anim_map = {}
        if self.animating and self.anim_blocks:
            t = self.ease_out(self.anim_progress)
            dr = self._anim_dr * t
            dc = self._anim_dc * t
            for idx, block in enumerate(self.anim_blocks):
                sr, sc, sq = self.anim_start_pos[idx]
                anim_map[id(block)] = (sr + dr, sc + dc, sq)

        # 拖拽跟隨：選中組沿鎖定方向平移 dr/dc 個小數格（格座標）
        follow_map = {}
        if self.drag_following:
            dr, dc = self.drag_follow_offset
            if abs(dr) > 1e-9 or abs(dc) > 1e-9:
                for block in self.game.blocks:
                    if block.be_opted:
                        r, c, q = mi_key(block)
                        follow_map[id(block)] = (r + dr, c + dc, q)

        cells = self.game.positions()
        if anim_map:
            moving = {mi_key(b) for b in self.anim_blocks}
            cells = ((cells - moving)
                     | {(r, c, q) for (r, c, q) in anim_map.values()})
        hull = view.board_hull(cells)
        # 背景層級由塊的邊導出（錯位態的橫豎格邊落在半整數層級上），
        # 只傳凸包的話畫出來的仍是對齊態的整數格，與塊對不齊
        for p1, p2 in view.grid_segments(hull, cells):
            pygame.draw.line(self.screen, self.colors['gap'],
                             self.world_to_screen(*p1),
                             self.world_to_screen(*p2),
                             max(1, int(self.gap_width * self.zoom * 0.35)))
        self._draw_mi_selected_gap(view, hull)

        scaled_cell = self.cell_size * self.zoom
        selected = []
        normal = []
        for block in self.game.blocks:
            r, c, q = (anim_map.get(id(block)) or follow_map.get(id(block))
                       or mi_key(block))
            cx, cy = view.piece_center(r, c, q)
            sx, sy = self.world_to_screen(cx, cy)
            if (sx < -scaled_cell or sx > self.screen_width + scaled_cell
                    or sy < -scaled_cell or sy > self.screen_height + scaled_cell):
                continue
            # 拖過可達上限：這一塊要變暗 + 橙框，連同組別一起畫
            warn = (self.drag_following and self.drag_follow_invalid
                    and id(block) in follow_map)
            (selected if block.be_opted else normal).append(((r, c, q), warn))

        # 悬停连锁提示：同類（含朝向 q）的塊提亮、空位實心提亮
        hint_occ, hint_empty, hint_hover = self._chain_hint_cells()

        for gi, group in enumerate((normal, selected)):
            base = (self.colors['block_selected'] if gi
                    else self.colors['block'])
            for (r, c, q), warn in group:
                fill = base
                border_color = self.colors['border']
                border_w = max(1, int(2 * self.zoom))
                if warn:
                    fill = tuple(int(ch * 0.45) for ch in base[:3])
                    border_color = (220, 80, 40)
                    border_w = max(1, int(3 * self.zoom))
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(r, c, q)]
                pygame.draw.polygon(self.screen, fill, poly)
                pygame.draw.polygon(self.screen, border_color,
                                    poly, border_w)
                # 连锁提示：同類塊叠半透明白（與方形/三角同一套語言）
                if hint_occ is not None and (r, c, q) in hint_occ:
                    self._draw_hint_overlay(poly, (r, c, q) == hint_hover)
                # 分组着色：縮環從外側向內一圈（位置類不含朝向 q，半整數
                # 座標在 cell_class 內部整數化），線寬沿用方形慣例。pygame
                # 多邊形描邊向外也擴半個線寬，直接描會漫進縫隙蓋住選中紅線
                if (not warn
                        and getattr(self, 'coloring_enabled', False)
                        and self.current_step > 1):
                    ring_w = max(2, int(4 * self.zoom))
                    pygame.draw.polygon(
                        self.screen, self._group_color_for((r, c)),
                        self._tri_ring(poly, ring_w / 2.0), ring_w)

        # 悬停连锁提示：同類空位叠半透明白（与方形空格同一套语言）
        if hint_empty:
            for (r, c, q) in sorted(hint_empty):
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(r, c, q)]
                self._draw_hint_overlay(poly, (r, c, q) == hint_hover)

    def _draw_mi_selected_gap(self, view: 'MiBoardView', hull):
        """繪製米字格選中的縫隙線（四族之一），只畫在棋形範圍內。

        米字紋理本身就是「方格 + 每格兩條對角線」，選中哪條縫在背景裡
        看不出來，必須疊一條紅線（與方形/三角版同一套視覺語言）。對角族
        的縫是整條對角線鏈（同一條 r−c 或 r+c 上的全部格子），所以線會
        貫穿整塊棋盤，這正是「一條鏈一條縫」的機制所要求的。
        """
        gap = getattr(self, 'selected_gap', None)
        if not gap:
            return
        gap_type, line = gap
        if gap_type not in ('h', 'v', 'd1', 'd2'):
            return
        seg = view.gap_segment(gap_type, line, hull)
        if seg is None:
            return
        pygame.draw.line(self.screen, self.colors['line'],
                         self.world_to_screen(*seg[0]),
                         self.world_to_screen(*seg[1]), 3)

    def draw_board(self):
        """绘制游戏主界面"""
        if getattr(self, 'triangle_mode', False):
            self.draw_triangle_board()
            return
        if getattr(self, 'mi_mode', False):
            self.draw_mi_board()
            return

        self.screen.fill(self.colors['background'])

        board_x = 0
        board_y = 0
        self._board_x = board_x
        self._board_y = board_y

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

        # 构建拖拽跟随渲染位置映射（非整数格坐标，实时预览）
        # 偏移已在 events.py 夹紧到 [0, max_cells]，此处直接使用（单一数据源）
        follow_map = {}
        if self.drag_following:
            dr, dc = self.drag_follow_offset
            if abs(dr) > 1e-9 or abs(dc) > 1e-9:
                for block in self.game.blocks:
                    if block.be_opted:
                        follow_map[id(block)] = (block.location[0] + dr, block.location[1] + dc)

        # 悬停连锁提示：预计算高亮格集合（含空格），块循环中叠半透明白
        hint_occ, hint_empty, hint_hover = self._chain_hint_cells()

        # 绘制所有滑块
        for block in self.game.blocks:
            if id(block) in follow_map:
                lr, lc = follow_map[id(block)]
                x = board_x + lc * (scaled_cell + scaled_gap)
                y = board_y + lr * (scaled_cell + scaled_gap)
            elif id(block) in anim_map:
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

            # 分组着色：只在滑块边界描边，中心保持原画风（淡蓝/选中淡绿）
            if block.be_opted:
                fill = self.colors['block_selected']
            else:
                fill = self.colors['block']
            # 拖拽跟随无效（碰撞/断开）时：变暗滑块 + 橙色边框提示不可移动
            if (self.drag_following and self.drag_follow_invalid
                    and id(block) in follow_map):
                fill = tuple(int(ch * 0.45) for ch in fill[:3])
                border_color = (220, 80, 40)
                border_w = max(1, int(3 * self.zoom))
            else:
                if getattr(self, 'coloring_enabled', False) and self.current_step > 1:
                    border_color = self._group_color(block.location[0], block.location[1])
                    border_w = max(2, int(7 * self.zoom)) #暫定7,不要改
                else:
                    border_color = self.colors['border']
                    border_w = max(1, int(2 * self.zoom))
            rect = pygame.Rect(screen_x, screen_y, scaled_cell, scaled_cell)
            pygame.draw.rect(self.screen, fill, rect, border_radius=int(5 * self.zoom))
            pygame.draw.rect(self.screen, border_color, rect, border_w, border_radius=int(5 * self.zoom))

            # 连锁提示：同组格叠一层半透明白（hover 更亮），着色描边仍在最上层
            if hint_occ is not None and tuple(block.location) in hint_occ:
                bl = tuple(block.location)
                self._draw_hint_overlay(
                    [(screen_x, screen_y),
                     (screen_x + scaled_cell, screen_y),
                     (screen_x + scaled_cell, screen_y + scaled_cell),
                     (screen_x, screen_y + scaled_cell)],
                    bl == hint_hover)

            if getattr(self, 'numbered', False) and getattr(block, 'number', None):
                font_size = max(12, int(scaled_cell * 0.45))
                if not hasattr(self, '_num_font_cache'):
                    self._num_font_cache = {}
                font = self._num_font_cache.get(font_size)
                if font is None:
                    # 延遲導入：GUI 模組在 import 期尚未定義 _gui_safe_font
                    from GUI import _gui_safe_font
                    font = _gui_safe_font('SimHei', font_size)
                    self._num_font_cache[font_size] = font
                text = font.render(str(block.number), True, (0, 0, 0))
                text_rect = text.get_rect(center=(screen_x + scaled_cell / 2, screen_y + scaled_cell / 2))
                self.screen.blit(text, text_rect)

        # 连锁提示：高亮的空格（无滑块）同样叠半透明白
        if hint_empty is not None:
            step_px = scaled_cell + scaled_gap
            for (r, c) in sorted(hint_empty):
                bx = board_x + c * step_px + self.camera_x
                by = board_y + r * step_px + self.camera_y
                self._draw_hint_overlay(
                    [(bx, by), (bx + scaled_cell, by),
                     (bx + scaled_cell, by + scaled_cell), (bx, by + scaled_cell)],
                    (r, c) == hint_hover)

        # 宏基准位置标记（固定坐标，无论该格有无滑块）
        base = getattr(self, 'macro_record_base_point', None)
        if base is not None:
            br, bc = base
            bx = board_x + bc * (scaled_cell + scaled_gap) + self.camera_x
            by = board_y + br * (scaled_cell + scaled_gap) + self.camera_y
            hl_rect = pygame.Rect(bx - 3, by - 3, scaled_cell + 6, scaled_cell + 6)
            pygame.draw.rect(self.screen, (255, 200, 50), hl_rect, max(1, int(3 * self.zoom)), border_radius=int(5 * self.zoom))

        # 调试面板打开时：先画目标窗口框（并把同一 region 存到 self），
        # 再以该 region 为基准画洞/缺口/凸起标记，两者严格一致。
        if getattr(self, 'show_metrics_panel', False):
            self._draw_target_window()
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
        """绘制谜题下拉菜单：按形态分组，底部一行显示当前谜题"""
        puzzle_rect = self.menu_item_rects[2]
        menu_x = puzzle_rect.x
        menu_y = self.menu_bar_height

        item_height = 26
        menu_width = 200

        total_items = len(self.puzzle_presets)
        menu_height = item_height * total_items

        dropdown_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], dropdown_rect)
        pygame.draw.rect(self.screen, self.colors['border'], dropdown_rect, 1)

        self.puzzle_menu_rects = []
        current_key = self._current_puzzle_key()
        for i, preset in enumerate(self.puzzle_presets):
            y_pos = menu_y + i * item_height
            item_rect = pygame.Rect(menu_x, y_pos, menu_width, item_height)
            self.puzzle_menu_rects.append(item_rect)
            center_y = y_pos + item_height // 2

            if len(preset) == 1 and preset[0] == '---':
                pygame.draw.line(self.screen, self.colors['separator'],
                               (menu_x + 8, center_y),
                               (menu_x + menu_width - 8, center_y))
                continue

            # 分组标题：不可点击，也不随悬停高亮
            if len(preset) == 2 and preset[0] == '__group__':
                title_surface = self.menu_font.render(
                    preset[1], True, self.colors['menu_selected'])
                title_rect = title_surface.get_rect()
                title_rect.x = menu_x + 12
                title_rect.centery = center_y
                self.screen.blit(title_surface, title_rect)
                continue

            # 底部状态行：模式切换挪走后，这里是唯一提示「当前玩的哪一档」的地方
            if len(preset) == 1 and preset[0] == '__current__':
                label = '当前：' + self._current_puzzle_label()
                label_surface = self.status_font.render(label, True, self.colors['menu_text'])
                label_rect = label_surface.get_rect(
                    center=(menu_x + menu_width // 2, center_y))
                self.screen.blit(label_surface, label_rect)
                continue

            if i == self.puzzle_menu_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            is_current = (len(preset) >= 4
                          and self._preset_puzzle_key(preset) == current_key)

            name = preset[0]
            color = self.colors['menu_selected'] if is_current else self.colors['menu_text']
            text_surface = self.menu_font.render(name, True, color)
            text_rect = text_surface.get_rect()
            text_rect.x = menu_x + 12
            text_rect.centery = center_y
            self.screen.blit(text_surface, text_rect)

            if is_current:
                check_surface = self.menu_font.render('✓', True, self.colors['menu_selected'])
                check_rect = check_surface.get_rect()
                check_rect.right = menu_x + menu_width - 10
                check_rect.centery = center_y
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
        items.append(f'逆序播放：{"开" if self.macro_reverse_mode else "关"}')
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

        # 左侧：复原状态（走 GUI 层判定：带序号模式会额外检查编号顺序）
        solved = self.is_solved()
        status_text = "状态：复原" if solved else "状态：未复原"
        status_color = self.colors['solved'] if solved else self.colors['unsolved']
        status_surface = self.status_font.render(status_text, True, status_color)
        self.screen.blit(status_surface, (10, text_y))

        # 左侧：步数
        step_text = f"步数：{self.step_count}"
        step_surface = self.status_font.render(step_text, True, self.colors['status_text'])
        step_x = 10 + status_surface.get_width() + 30
        self.screen.blit(step_surface, (step_x, text_y))

        # 左侧：模式 / 计时状态（步数右边）
        timer_text = self._timer_status_text()
        if self.game_mode == 'timed' and self.timer_state == 'running':
            timer_color = (255, 200, 80)  # 竞速计时中：醒目黄色
        else:
            timer_color = self.colors['status_text']
        timer_surface = self.status_font.render(timer_text, True, timer_color)
        timer_x = step_x + step_surface.get_width() + 30
        self.screen.blit(timer_surface, (timer_x, text_y))

        # 中间：当前谜题信息（带形态后缀：带序号 #num / 三角形 tri{k} / 米字格 mi{m}*{n}）
        puzzle_text = f"谜题：{self._current_puzzle_key()}"
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
        dialog_width = 660
        dialog_height = 480
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

        # 聚拢参数 Tab
        tab_gather_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 3, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'gather':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_gather_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_gather_rect, border_radius=4)
        tab_gather_text = self.status_font.render("聚拢参数", True, self.colors['input_text'])
        tab_gather_text_rect = tab_gather_text.get_rect(center=tab_gather_rect.center)
        self.screen.blit(tab_gather_text, tab_gather_text_rect)

        # 文件/存档 Tab
        tab_file_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 4, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'file':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_file_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_file_rect, border_radius=4)
        tab_file_text = self.status_font.render("文件", True, self.colors['input_text'])
        tab_file_text_rect = tab_file_text.get_rect(center=tab_file_rect.center)
        self.screen.blit(tab_file_text, tab_file_text_rect)

        # 控制 Tab
        tab_control_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 5, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'control':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_control_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_control_rect, border_radius=4)
        tab_control_text = self.status_font.render("控制", True, self.colors['input_text'])
        tab_control_text_rect = tab_control_text.get_rect(center=tab_control_rect.center)
        self.screen.blit(tab_control_text, tab_control_text_rect)

        # 存储 tab rect 用于点击检测
        self._settings_tab_kb_rect = tab_kb_rect
        self._settings_tab_anim_rect = tab_anim_rect
        self._settings_tab_solver_rect = tab_solver_rect
        self._settings_tab_gather_rect = tab_gather_rect
        self._settings_tab_file_rect = tab_file_rect
        self._settings_tab_control_rect = tab_control_rect

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
                self._draw_settings_animation(dialog_x, content_y - scroll, dialog_width - 30, content_height)
            elif self.settings_active_tab == 'gather':
                self._draw_settings_gather(dialog_x, content_y - scroll, dialog_width - 30, content_height)
            elif self.settings_active_tab == 'file':
                self._draw_settings_file(dialog_x, content_y - scroll, dialog_width - 30, content_height)
            elif self.settings_active_tab == 'control':
                self._draw_settings_control(dialog_x, content_y - scroll, dialog_width - 30, content_height)
            else:
                self._draw_settings_solver(dialog_x, content_y - scroll, dialog_width - 30, content_height)
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

    def _group_color(self, r: int, c: int):
        """分组着色（描边色）：颜色由 (r mod step, c mod step) 唯一决定。

        移动 step 格时该二元组不变（模 step 不变量），所以同一滑块的颜色
        恒为初始颜色——不需要记录任何轨迹。

        配色：
        - 组数 ≤ 16：色相均匀分色（k×360/N），相邻组最小色差 = 360/N；
        - 组数 > 16：黄金比例色相法（hue = frac(k×0.61803)），大量颜色时分布更均匀。
        S/V 取马卡龙色系（柔和鲜亮），适合描边小面积着色（区分度优先）。
        """
        step = self.current_step
        k = (r % step) * step + (c % step)
        n = step * step
        if n <= 16:
            hue = k * 360.0 / n
        else:
            hue = (k * 0.618033988749895 % 1.0) * 360.0
        col = pygame.Color(0, 0, 0)
        col.hsva = (hue, 75, 92, 100)
        return col

    def _group_color_for(self, pos):
        """三形態通用描邊色：位置 → 移動不變量類（不含朝向）→ 色相。

        方形與 _group_color 同源（class_index 對方形給出同一個
        (r%step)*step+(c%step)），三角用 (i%step, j%step)、米字用
        ((r+c)%step, (r−c)%step)；朝向（up/q）不參與著色。呼叫端按
        當前形態傳位置前兩個分量即可，形態分派在 cell_class 內部。
        """
        if getattr(self, 'triangle_mode', False):
            kind = 'triangle'
        elif getattr(self, 'mi_mode', False):
            kind = 'mi'
        else:
            kind = 'square'
        step = self.current_step
        k = class_index(cell_class(pos, step, kind), step)
        n = step * step
        if n <= 16:
            hue = k * 360.0 / n
        else:
            hue = (k * 0.618033988749895 % 1.0) * 360.0
        col = pygame.Color(0, 0, 0)
        col.hsva = (hue, 75, 92, 100)
        return col

    # 连锁提示：半透明白色叠加层的透明度（hover 更亮）
    HINT_ALPHA_HOVER = 110
    HINT_ALPHA_OTHER = 60

    def _draw_hint_overlay(self, poly, is_hover):
        """在滑块/空位多边形上叠一层半透明白色（连锁提示的本体观感）。

        原版连锁高亮是半透明白色，不是把块的原色提亮：提亮会把选中绿、
        空位、着色描边各自拉成不同色阶，玩家看到的是「变色」而非「罩了
        一层白光」。半透明白叠加对任何底色都给出同样的高光，且着色描边
        与选中状态仍然透得出来。
        """
        if not poly:
            return
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
        w = int(max(xs)) - x0 + 2
        h = int(max(ys)) - y0 + 2
        if w <= 0 or h <= 0:
            return
        alpha = (self.HINT_ALPHA_HOVER if is_hover
                 else self.HINT_ALPHA_OTHER)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        local = [(p[0] - x0, p[1] - y0) for p in poly]
        pygame.draw.polygon(surf, (255, 255, 255, alpha), local)
        self.screen.blit(surf, (x0, y0))

    def _point_in_convex(self, pt, poly, eps=1e-9):
        """点是否在凸多边形内（含边）。顶点次序任意（凸包保证凸）。

        凸多边形的每条边把平面切成两半，点在内 iff 对所有边都在同一侧
        （叉积同号）；落在边上（叉积 0）算在內——邊界塊的內心貼著凸包
        邊時不能因為浮點誤差被判出去。
        """
        n = len(poly)
        if n < 3:
            return False
        sign = 0
        for k in range(n):
            ox, oy = poly[k]
            ax, ay = poly[(k + 1) % n]
            cr = (ax - ox) * (pt[1] - oy) - (ay - oy) * (pt[0] - ox)
            if abs(cr) <= eps:
                continue
            s = 1 if cr > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                return False
        return True

    def _tri_ring(self, pts, w):
        """三角形顶点的「外置内环」顶点（屏幕座标）。

        着色要求是「在原有图形基础上，从外侧向内画一圈颜色」，且描边
        不带圆角/斜接伸出、顶角不留缝、厚度恒定。pygame 的多边形描边
        以边线为中心向两侧各扩半个线宽，width 一大就 (a) 向外漫进块间
        缝隙盖住缝线，(b) 尖角按斜接向外伸出。所以先算**多边形各边
        向内偏移 w** 所得的三条直线的交点（内切的平行边三角形），
        再以 2w 描边——环带整体落在 [0, 2w] 的内缩区，恰好「从外缘向
        内一圈」；用直线交点而非顶点缩放，顶角处环带连续无缺口。
        """
        if w <= 0 or len(pts) < 3:
            return pts
        inward = []
        for k in range(3):
            (px, py), (qx, qy) = pts[k], pts[(k + 1) % 3]
            ex, ey = qx - px, qy - py
            ln = math.hypot(ex, ey)
            if ln < 1e-9:
                return pts
            cx = sum(p[0] for p in pts) / 3.0
            cy = sum(p[1] for p in pts) / 3.0
            # 指向重心的法线就是内向，无需依赖顶点绕向
            nx, ny = -ey / ln, ex / ln
            if nx * (cx - px) + ny * (cy - py) < 0:
                nx, ny = -nx, -ny
            inward.append(((px + nx * w, py + ny * w),
                           (qx + nx * w, qy + ny * w)))
        out = []
        for k in range(3):
            (x1, y1), (x2, y2) = inward[k]
            (x3, y3), (x4, y4) = inward[(k + 1) % 3]
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-9:            # 平行（退化三角形）：退回该边中点
                out.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
                continue
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
        return out

    def _chain_hint_cells(self):
        """悬停连锁提示的高亮集合（三形態通用）。

        返回 (occupied_keys, empty_positions, hover_cell)；
        未开启/无悬停/无效时返回 (None, None, None)。
        注意：shuffle 后棋盘坐标可为负，用棋盘实际边界判定。

        連鎖用類含朝向（「這塊能去哪」不含朝向會把 ▲ 指到 ▼ 該去的
        位置，是假提示）：
        - 方形 (r,c)：類 = (r%step, c%step)，鍵與位置都是二元組；
        - 三角 (i,j,up)：類 = (i%step, j%step, up)；
        - 米字 (r,c,q)：類 = ((r+c)%step, (r−c)%step, q)。

        **只高亮當前棋形內的位置**：棋形外的空位（三角棋形外的斜座標）
        畫出來玩家無從到達，只是徒增困惑；棋形＝滑塊併集的凸包（也是背景
        網格的裁剪範圍）。米字不另按晶格過濾——奇數 step 斜向一步就換晶格，
        另一晶格是同一條軌道的另一半（見該分支的推導）。

        occupied_keys 是同類且當前被佔用的位置鍵（塊循環裡提亮），
        empty_positions 是同類的空位（渲染端以實心提亮畫出，與方形空格
        同一套語言）。方形兩集合的併集與舊版單集合語義一致。
        """
        if not getattr(self, 'chain_hint_enabled', False):
            return None, None, None
        cell = getattr(self, 'hover_cell', None)
        if not cell:
            return None, None, None
        step = self.current_step
        if step < 1:
            return None, None, None
        if step == 1 and not (getattr(self, 'triangle_mode', False)
                              or getattr(self, 'mi_mode', False)):
            # 1 級（step=1）位置類退化：方形只剩一組——全盤同類，畫了等於
            # 沒畫，關掉。三角/米字退化成朝向分組（▲/▼ 兩組、N/E/S/W 四
            # 族），而這兩形態「原本就靠朝向分組」，1 級一步一格時一塊能去
            # 的恰是同朝向的任意位置（米字還能斜向一格換晶格），連鎖照常
            # 有用。著色不含朝向（位置類單色、無資訊），仍只在 >1 級開。
            return None, None, None
        bounds = self.game.get_boundaries()
        if not (
            bounds['min_row'] - 1 <= cell[0] <= bounds['max_row'] + 1 and
            bounds['min_col'] - 1 <= cell[1] <= bounds['max_col'] + 1
        ):
            return None, None, None
        blocks = self.game.blocks
        if not blocks:
            return None, None, None

        if getattr(self, 'triangle_mode', False):
            # 懸停與鍵都是 (i, j, up) 三元組，類含朝向
            if len(cell) < 3:
                return None, None, None
            hkey = (cell[0], cell[1], bool(cell[2]))
            hcls = cell_class(hkey, step, 'triangle') + (hkey[2],)
            occ, empty = set(), set()
            keys = {tri_key(b) for b in blocks}
            iis = [k[0] for k in keys]
            jjs = [k[1] for k in keys]
            # 棋形內＝落在滑塊併集的凸包裡（與米字同一套判據）：三角棋盤
            # 不是矩形，斜座標方框的右上側那一大片是形狀外的空白，原版靠
            # 「菱形格是否與棋形有公共角」擋不住（邊角上的空菱形照樣貼著
            # 棋形），復原態就會在滑塊組右上側亮出一整片假空位。凸包同時
            # 也是背景網格的裁剪範圍，所以「有畫網格的地方」＝凸包內。
            view = self._tri_view()
            hull = view.board_hull(keys) if keys else []
            for i in range(min(iis), max(iis) + 1):
                for j in range(min(jjs), max(jjs) + 1):
                    for up in (True, False):
                        if cell_class((i, j), step, 'triangle') + (up,) != hcls:
                            continue
                        # 凸包裁剪：**整塊都要在包內**。只查內心的話，
                        # 內心恰好貼在包邊上的空位（本體探出包外，如三角
                        # 斜邊外側貼著的空菱形）會被放進來，畫出越界高亮。
                        # 頂點全在包內才亮，與背景網格的裁剪範圍一致；
                        # 佔用格的頂點本來就是凸包的候選點，必在包內。
                        if len(hull) >= 3 and not all(
                                self._point_in_convex(p, hull)
                                for p in view.piece_polygon(i, j, up,
                                                            inset=False)):
                            continue
                        (occ if (i, j, up) in keys else empty).add((i, j, up))
            return occ, empty, hkey

        if getattr(self, 'mi_mode', False):
            # 懸停與鍵都是 (r, c, q)。位置枚舉＝「凸包內 + 同類（含朝向）」，
            # **不按晶格過濾**——見下面的推導，過濾在奇數 step 下是錯的。
            #
            # 位移生成元：一步走 step 格，橫豎是 (step,0)/(0,step)，斜向是
            # (±step/2, ±step/2)；橫豎兩個恰是斜向兩個的和，所以真實軌道是
            #     {(step/2·p, step/2·q) : p ≡ q (mod 2)}
            # 又「同類」的條件是 (r'+c')−(r+c) 與 (r'−c')−(r−c) 都是 step 的
            # 倍數，解出 r'−r = step(u+v)/2、c'−c = step(u−v)/2，其中
            # p = u+v、q = u−v 必同奇偶 —— 兩式完全等價，也就是說
            # **「同類」就等於「真的到得了」**，晶格不是額外的約束。
            #   step 偶數：step/2 是整數，位移全整數，晶格確實是不變量；而
            #     A 晶格有 (r+c)≡(r−c)、B 晶格有 (r+c)≢(r−c) (mod 2)，類匹配
            #     本來就排除另一晶格，加不加過濾結果一樣。
            #   step 奇數：斜向走 step（奇數）格的位移 ±(step/2, step/2) 是
            #     半整數，一步就把整盤換到另一晶格（實測 step=3：(0,0,'N')
            #     斜走 3 格 ⇒ (−1.5,−1.5,'N')，類不變）。這時另一晶格是同一
            #     條軌道的另一半，按晶格過濾會把高亮數砍掉一半。
            # 棋形內用「滑塊併集的凸包」裁定（見下面的 hull），不再看該
            # 1×1 格有沒有塊——洞也要亮。
            if len(cell) < 3:
                return None, None, None
            hkey = (cell[0], cell[1], cell[2])
            hcls = cell_class(hkey, step, 'mi') + (hkey[2],)
            occupied = {mi_key(b) for b in blocks}
            occ, empty = set(), set()
            rs2 = [int(round(2 * b.location[0])) for b in blocks]
            cs2 = [int(round(2 * b.location[1])) for b in blocks]
            # 棋形内：取滑塊併集的凸包，只有落在凸包裡的位置才算數。
            # 凸包正是背景網格的裁剪範圍（grid_segments 按凸包 chord），
            # 所以「地圖上有畫網格的地方」＝凸包內＝這裡的判據；洞在凸包
            # 內照樣要亮——洞才是連鎖提示最該指的地方（哪塊能補進來）。
            # 不能用「該 1×1 格有沒有塊」當判據：那會把洞一起排除，表現
            # 就是懸停洞時別處都亮、洞自己不亮。
            view = self._mi_view()
            hull = view.board_hull(occupied) if occupied else []
            # 上界多掃一格（r2 的 +2 = 半格）：另一晶格的位置可能落在滑塊
            # 座標邊界外半格處（如 6×6 盤的 r=5.5），凸包邊界仍可能收它。
            for r2 in range(min(rs2), max(rs2) + 3):
                for c2 in range(min(cs2), max(cs2) + 3):
                    # 合法的米字位置：r、c 同奇偶（A 晶格全整 / B 晶格全半整），
                    # 一整一半的座標不是任何塊能待的地方。
                    if r2 % 2 != c2 % 2:
                        continue
                    r, c = r2 / 2.0, c2 / 2.0
                    pos_cls = cell_class((r, c), step, 'mi')
                    for q in ('N', 'E', 'S', 'W'):
                        if pos_cls + (q,) != hcls:
                            continue
                        # 凸包裁剪：**整塊都要在包內**。只查內心的話，內心
                        # 恰好貼在包邊上的空位（本體探出包外半格——1 級米字
                        # 右/下邊的 B 晶格楔形就是這麼漏出去的）會被放進來，
                        # 畫出越界的高亮。三頂點全在包內才亮，與背景網格的
                        # 裁剪範圍（grid_segments 按凸包 chord）一致；佔用格
                        # 的頂點本來就是凸包的候選點，必在包內。
                        if len(hull) >= 3 and not all(
                                self._point_in_convex(view.to_world(x, y), hull)
                                for (x, y) in mi_vertices(r, c, q)):
                            continue
                        key = (r, c, q)
                        if key in occupied:
                            occ.add(key)
                        else:
                            empty.add(key)
            return occ, empty, hkey

        # 方形：鍵與位置都是 (r, c) 二元組，類不含朝向
        hr, hc = cell[0], cell[1]
        hcls = cell_class((hr, hc), step, 'square')
        occ, empty = set(), set()
        rs = [b.location[0] for b in blocks]
        cs = [b.location[1] for b in blocks]
        occupied = {(b.location[0], b.location[1]) for b in blocks}
        for r in range(min(rs), max(rs) + 1):
            for c in range(min(cs), max(cs) + 1):
                if cell_class((r, c), step, 'square') == hcls:
                    (occ if (r, c) in occupied else empty).add((r, c))
        return occ, empty, (hr, hc)

    def _draw_switch_row(self, x, y, label, on, hint=None, btn_w=64, btn_h=28):
        """统一排版的开关行：左栏标签(x+15) + 右栏开关(x+220) + 可选说明。
        返回 (开关rect, 下一行y)。所有设置页开关共用，保证对齐。"""
        label_s = self.dialog_font.render(label, True, self.colors['dialog_text'])
        self.screen.blit(label_s, (x + 15, y + 6))

        rect = pygame.Rect(x + 220, y + 2, btn_w, btn_h)
        if on:
            bg, txt, tc = self.colors['button_bg'], "ON", (255, 255, 255)
        else:
            bg, txt, tc = self.colors['input_bg'], "OFF", (150, 150, 150)
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        ts = self.status_font.render(txt, True, tc)
        self.screen.blit(ts, ts.get_rect(center=rect.center))

        row_h = 60
        if hint:
            hs = self.status_font.render(hint, True, (150, 150, 150))
            self.screen.blit(hs, (x + 15, y + 38))
            row_h = 60
        return rect, y + row_h

    def _draw_settings_animation(self, x, y, width, height):
        """绘制动画速度设置内容（统一排版：标签左栏 x+15、控件右栏 x+220）"""
        # 滑动动画开关
        self._settings_anim_toggle_rect, ny = self._draw_switch_row(
            x, y, "滑动动画：", self.animation_enabled,
            "滑块移动时的补间动画过渡")

        # 选中动画开关（撤销/重做时高亮该步缝隙与滑块组）
        self._settings_sel_anim_toggle_rect, ny = self._draw_switch_row(
            x, ny, "选中动画：", getattr(self, 'selection_animation_enabled', True),
            "撤销/重做时短暂高亮该步选中的缝隙与滑块组")

        # 动画时长滑动条（轨道与开关同一右栏对齐）
        speed_y = ny
        speed_label = self.dialog_font.render("动画时长：", True, self.colors['dialog_text'])
        self.screen.blit(speed_label, (x + 15, speed_y + 6))

        track_x = x + 220
        track_width = 190
        value_text = f"{self.animation_duration} ms"
        value_surface = self.input_font.render(value_text, True, self.colors['input_text'])
        self.screen.blit(value_surface,
                         (track_x + track_width - value_surface.get_width(), speed_y + 6))

        # 滑动条轨道
        track_y = speed_y + 26
        self._settings_slider_track_rect = pygame.Rect(track_x, track_y, track_width, 4)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self._settings_slider_track_rect)

        # 滑动条位置
        normalized = (self.animation_duration - 100) / 900.0
        normalized = max(0.0, min(1.0, normalized))
        knob_x = int(track_x + normalized * track_width)
        self._settings_slider_knob_rect = pygame.Rect(knob_x - 8, track_y - 6, 16, 16)

        knob_color = self.colors['button_hover'] if self._settings_slider_dragging else self.colors['button_bg']
        pygame.draw.rect(self.screen, knob_color, self._settings_slider_knob_rect, border_radius=8)

        # 刻度标签（两端对齐轨道）
        min_label = self.status_font.render("100ms", True, (150, 150, 150))
        max_label = self.status_font.render("1000ms", True, (150, 150, 150))
        self.screen.blit(min_label, (track_x, track_y + 12))
        self.screen.blit(max_label, (track_x + track_width - max_label.get_width(), track_y + 12))
        ny = speed_y + 72

        # 分组着色器开关
        self._settings_coloring_toggle_rect, ny = self._draw_switch_row(
            x, ny, "分组着色：", getattr(self, 'coloring_enabled', False),
            "按移动不变量分组着色（同组颜色的滑块才可能互换位置）")

        # 悬停连锁提示开关（独立于着色器）
        self._settings_chain_toggle_rect, ny = self._draw_switch_row(
            x, ny, "悬停连锁提示：", getattr(self, 'chain_hint_enabled', False),
            "悬停滑块时，边界盒内同组位置（含空格）提亮提示，帮助找缺口")

    def _draw_settings_control(self, x, y, width, height):
        """绘制控制模式设置内容（三种模式独立开关，可任意组合）"""
        hint = self.status_font.render(
            "三种模式可任意组合（甚至全关）；全关时只能平移/缩放", True, (200, 200, 120))
        self.screen.blit(hint, (x + 15, y + 6))

        ny = y + 34
        self._settings_ctrl_single_rect, ny = self._draw_switch_row(
            x, ny, "单次触控：", getattr(self, 'control_single_touch', True),
            "直接拖拽滑块即滑动；完成后清空选中，下次拖拽是全新操作")
        self._settings_ctrl_two_rect, ny = self._draw_switch_row(
            x, ny, "两次触控：", getattr(self, 'control_two_touch', True),
            "点缝隙 → 点方块 → 再拖拽 / 键盘（原版操作习惯）")
        self._settings_ctrl_kb_rect, ny = self._draw_switch_row(
            x, ny, "鼠标键盘：", getattr(self, 'control_mouse_kb', True),
            "方向键 / W/A/S/D 移动滑块（撤销/重做等快捷键不受影响）")

    def _draw_settings_gather(self, x, y, width, height):
        """绘制聚拢参数设置内容（与谜题-自定义一致的输入框样式）"""
        # 顶部警告：不了解参数含义请勿调整
        warn = self.status_font.render("※ 参数含义若不理解请勿调整，以免求解效果变差", True, (220, 200, 80))
        self.screen.blit(warn, (x + 15, y + 8))
        row_y = y + 32
        self._settings_gather_rects = {}
        editing = getattr(self, 'settings_editing_value', None)
        specs = getattr(self, '_gather_param_specs', [])
        for key, (_label, vdef, vmin, vmax, vstep, desc) in specs:
            enabled = getattr(self, 'gather_enabled', {}).get(key, True)
            # 启用/禁用开关
            toggle = pygame.Rect(x + 15, row_y, 58, 26)
            if enabled:
                cbg, ctxt, ctext_color = self.colors['button_bg'], "启用", (255, 255, 255)
            else:
                cbg, ctxt, ctext_color = self.colors['input_bg'], "禁用", (150, 150, 150)
            pygame.draw.rect(self.screen, cbg, toggle, border_radius=4)
            t = self.status_font.render(ctxt, True, ctext_color)
            self.screen.blit(t, t.get_rect(center=toggle.center))
            # −/+ 按钮（禁用时灰化）
            dec = pygame.Rect(x + 80, row_y, 28, 26)
            inc = pygame.Rect(x + 196, row_y, 28, 26)
            btn_color = self.colors['input_bg'] if enabled else (55, 55, 55)
            pygame.draw.rect(self.screen, btn_color, dec, border_radius=4)
            pygame.draw.rect(self.screen, btn_color, inc, border_radius=4)
            txt_color = (255, 255, 255) if enabled else (90, 90, 90)
            d = self.status_font.render("−", True, txt_color)
            p = self.status_font.render("+", True, txt_color)
            self.screen.blit(d, d.get_rect(center=dec.center))
            self.screen.blit(p, p.get_rect(center=inc.center))
            # 值输入框（谜题-自定义样式）：可点击进入键盘编辑
            box = pygame.Rect(x + 112, row_y, 80, 26)
            is_editing = editing == key
            bg_color = self.colors.get('input_active', (70, 110, 160)) if is_editing else self.colors['input_bg']
            pygame.draw.rect(self.screen, bg_color, box, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['dialog_border'], box, 1, border_radius=4)
            if is_editing:
                text = getattr(self, 'settings_edit_buffer', '')
            else:
                val = self.gather_params.get(key, vdef)
                text = self._fmt_gather_value(key, val)
            vcol = (255, 255, 255) if enabled else (120, 120, 120)
            vs = self.input_font.render(text, True, vcol)
            self.screen.blit(vs, (box.x + 6, box.centery - vs.get_height() // 2))
            if is_editing:
                # 光标
                cw = vs.get_width()
                pygame.draw.line(self.screen, (255, 255, 255),
                                 (box.x + 6 + cw + 2, box.y + 4),
                                 (box.x + 6 + cw + 2, box.bottom - 4), 1)
            # 名称 + 说明（说明截断防重叠）
            name = self.dialog_font.render(_label, True, self.colors['dialog_text'])
            self.screen.blit(name, (x + 234, row_y))
            desc_surf = self.status_font.render(desc, True, (150, 150, 150))
            max_w = width - 234
            if desc_surf.get_width() > max_w:
                clip_r = pygame.Rect(x + 234, row_y + 18, max_w, 16)
                self.screen.set_clip(clip_r)
                self.screen.blit(desc_surf, (x + 234, row_y + 18))
                self.screen.set_clip(None)
            else:
                self.screen.blit(desc_surf, (x + 234, row_y + 18))
            self._settings_gather_rects[key] = {'toggle': toggle, 'box': box, 'dec': dec, 'inc': inc,
                                                'enabled': enabled, 'vmin': vmin, 'vmax': vmax,
                                                'vstep': vstep, 'vdef': vdef}
            row_y += 52

    def _fmt_gather_value(self, key: str, val) -> str:
        """聚拢参数值显示：整数原样、时长加 's'、浮点保留两位"""
        if val is None:
            return '不限'
        if key == 'max_wait_time':
            return f"{val:.0f}s"
        if isinstance(val, float):
            return f"{val:.2f}"
        return str(int(val))

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

        # 说明文字（紧跟选项之下，自动换行，不遮挡选项）
        desc = self._solver_description(self.solver_algorithm)
        desc_y = row_y + 12
        max_w = width - 20
        wrapped = self._wrap_text(desc, self.status_font, max_w)
        for i, line in enumerate(wrapped):
            line_surf = self.status_font.render(line, True, (160, 160, 160))
            self.screen.blit(line_surf, (x + 15, desc_y + i * 18))

    def _solver_description(self, algo_key: str) -> str:
        """当前求解算法的说明文字"""
        descriptions = {
            'ida_star': '使用 IDA* 迭代加深搜索，尽量找到最少步数解。速度非常慢。',
            'fast': 'IDA* 优化模式：加大搜索步进，放宽节点/时间限制，优先聚拢，速度中等。不能保证求解成功。',
            'greedy': '贪心爬山法：每步选当前最佳动作，速度中等但不保证最优。不能保证求解成功。',
            'table':'根据数据库的数据快速找到最优算法（一般1s内），只对已有数据库的谜题有效。',
            #'intelligence': 'AI求解：基于预训练评分模型，每步自动选最佳动作。需先用 solver.ml.train_ranker 训练模型。',
            #'emd': 'EMD求解：用 EMD 距离贪心搜索，速度快但不保证成功。',
            #'strategy': '策略求解：EMD 贪心 + 循环检测 + 随机扰动，成功率高于纯 EMD。',
            #'distance': '距离求解：用神经网络预测剩余步数做贪心搜索，需先用 solver.ml.train_distance 训练模型。',
            'gather': '聚拢：提升聚拢度，不保证还原，实时显示进展。',
            'gather_gradient': '梯度聚拢：参数自动决定，分阶段放宽参数多轮聚拢，每阶段播放动画后再续。理论上比上一个更高效。',
            'fill_macro': '填洞宏：死代码规则（无搜索）。单洞单凸整盘还原；多洞无缺口时逐 couple 填洞（成功一次重扫，全败停机）。',
        }
        return descriptions.get(algo_key, '')

    def _draw_settings_file(self, x, y, width, height):
        """绘制“文件/存档”设置内容"""
        btn_w = 60
        btn_h = 28
        toggle_x = x + 180

        # 存档只读开关（save_readonly_flag：保存时给存档打只读标记）
        toggle_y = y + 20
        label = self.dialog_font.render("存档只读：", True, self.colors['dialog_text'])
        self.screen.blit(label, (x + 15, toggle_y))
        self._settings_readonly_toggle_rect = pygame.Rect(toggle_x, toggle_y, btn_w, btn_h)
        flag = getattr(self, 'save_readonly_flag', False)
        btn_color = self.colors['button_bg'] if flag else self.colors['input_bg']
        btn_text = "ON" if flag else "OFF"
        text_color = (255, 255, 255) if flag else (150, 150, 150)
        pygame.draw.rect(self.screen, btn_color, self._settings_readonly_toggle_rect, border_radius=4)
        ts = self.status_font.render(btn_text, True, text_color)
        self.screen.blit(ts, ts.get_rect(center=self._settings_readonly_toggle_rect.center))
        hint = self.status_font.render(
            "打开后，保存的存档都会带只读标记", True, (150, 150, 150))
        self.screen.blit(hint, (x + 15, toggle_y + 34))
        hint2 = self.status_font.render(
            "只读存档仅能撤销/重做，禁止滑动、求解等改变滑块状态的操作",
            True, (150, 150, 150))
        self.screen.blit(hint2, (x + 15, toggle_y + 54))

        # 防止覆盖开关（prevent_overwrite_flag：Ctrl+S 一律进入另存为）
        po_y = toggle_y + 90
        label2 = self.dialog_font.render("防止覆盖：", True, self.colors['dialog_text'])
        self.screen.blit(label2, (x + 15, po_y))
        self._settings_prevent_overwrite_rect = pygame.Rect(toggle_x, po_y, btn_w, btn_h)
        flag2 = getattr(self, 'prevent_overwrite_flag', False)
        btn_color = self.colors['button_bg'] if flag2 else self.colors['input_bg']
        btn_text = "ON" if flag2 else "OFF"
        text_color = (255, 255, 255) if flag2 else (150, 150, 150)
        pygame.draw.rect(self.screen, btn_color, self._settings_prevent_overwrite_rect, border_radius=4)
        ts = self.status_font.render(btn_text, True, text_color)
        self.screen.blit(ts, ts.get_rect(center=self._settings_prevent_overwrite_rect.center))
        hint = self.status_font.render(
            "打开后，Ctrl+S 一律进入“另存为”，避免误覆盖旧存档", True, (150, 150, 150))
        self.screen.blit(hint, (x + 15, po_y + 34))

        # 操作日志开关（op_log_enabled：把每次点击写进 config/op_log.jsonl）
        og_y = po_y + 60
        label3 = self.dialog_font.render("操作日志：", True, self.colors['dialog_text'])
        self.screen.blit(label3, (x + 15, og_y))
        self._settings_oplog_toggle_rect = pygame.Rect(toggle_x, og_y, btn_w, btn_h)
        flag3 = getattr(self, 'op_log_enabled', False)
        btn_color = self.colors['button_bg'] if flag3 else self.colors['input_bg']
        btn_text = "ON" if flag3 else "OFF"
        text_color = (255, 255, 255) if flag3 else (150, 150, 150)
        pygame.draw.rect(self.screen, btn_color, self._settings_oplog_toggle_rect, border_radius=4)
        ts3 = self.status_font.render(btn_text, True, text_color)
        self.screen.blit(ts3, ts3.get_rect(center=self._settings_oplog_toggle_rect.center))
        hint = self.status_font.render(
            "打开后，每次点击都记一行：坐标、命中结果、右下角提示", True, (150, 150, 150))
        self.screen.blit(hint, (x + 15, og_y + 34))
        hint2 = self.status_font.render(
            "写在 config/op_log.jsonl，只用于调试，日常请关闭", True, (150, 150, 150))
        self.screen.blit(hint2, (x + 15, og_y + 54))

        # 当前存档路径
        path_y = og_y + 80
        plabel = self.dialog_font.render("当前存档：", True, self.colors['dialog_text'])
        self.screen.blit(plabel, (x + 15, path_y))
        path = getattr(self, 'current_file_path', None) or '(未保存/自动暂存)'
        ptext = self.input_font.render(path, True, self.colors['input_text'])
        self.screen.blit(ptext, (x + 130, path_y + 4))

        # 当前只读状态
        ro_y = path_y + 40
        ro = getattr(self, '_readonly', False)
        ro_text = "当前存档：只读（仅可撤销/重做）" if ro else "当前存档：可编辑"
        ro_color = (255, 160, 140) if ro else (150, 230, 160)
        rts = self.status_font.render(ro_text, True, ro_color)
        self.screen.blit(rts, (x + 15, ro_y))

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
            return 340  # 滑动动画 + 选中动画 + 时长滑动条 + 着色器 + 连锁提示
        elif self.settings_active_tab == 'gather':
            return 12 + 26 + len(self._gather_param_specs) * 52 + 10
        elif self.settings_active_tab == 'file':
            return 320  # 存档只读 + 防止覆盖 + 操作日志 + 当前存档路径说明
        else:
            # solver tab：标题 + 选项 + 说明文字（动态计算，超出时出现滚动条）
            from solver import SOLVER_ALGORITHMS
            title_h = 20 + 36 + 10
            options_h = len(SOLVER_ALGORITHMS) * 36
            desc = self._solver_description(getattr(self, 'solver_algorithm', 'ida_star'))
            desc_w = 500 - 30 - 20  # 内容宽 470 再减边距
            desc_h = len(self._wrap_text(desc, self.status_font, desc_w)) * 18 + 12
            return title_h + options_h + desc_h

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
        self._macro_notify_rect = pygame.Rect(0, 0, box_w, box_h)   # 位置确定后回填

        # 位于状态栏上方、右侧面板左侧的右下角
        box_x = self.screen_width - self.right_panel_width - box_w - 12
        box_y = self.screen_height - self.status_bar_height - box_h - 8
        # 新手教程：教程面板占据右下角会遮住提示 → 提示栏改挂到面板正上方
        # （面板矩形由上一帧 draw_tutorial_panel 记录；位置稳定，仅首帧略滞后）
        tut_rect = getattr(self, 'tut_panel_rect', None)
        if getattr(self, 'tutorial_active', False) and tut_rect is not None:
            box_x = tut_rect.right - box_w
            box_y = tut_rect.top - box_h - 8
            if box_y < 8:                 # 面板贴近顶部时改为挂在面板下方
                box_y = tut_rect.bottom + 8
        self._macro_notify_rect.topleft = (box_x, box_y)

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

    def draw_solved_popup(self):
        """绘制复原成功悬浮窗（居中 + 弹入动画 + 呼吸光晕 + 自动消失）"""
        if not getattr(self, '_solved_popup_active', False):
            return
        t = getattr(self, '_solved_popup_t', 0)
        popup_w, popup_h = 460, 200
        result = getattr(self, '_last_timed_result', None)
        show_result = (getattr(self, 'game_mode', 'practice') == 'timed'
                       and result and not result.get('dnf', False))
        if show_result:
            popup_h = 300
        cx = (self.screen_width - self.right_panel_width) // 2
        cy = self.screen_height // 2

        # 弹入动画：前 12 帧缩放回弹，随后轻微呼吸
        p = min(1.0, t / 12.0)
        ease = 1 - (1 - p) ** 3
        if p < 1:
            scale = 0.7 + 0.3 * ease
        else:
            scale = 1.0 + 0.012 * math.sin(t / 9.0)
        alpha = int(240 * min(1.0, t / 6.0))

        # 超过 360 帧（约 6 秒）自动淡出关闭
        fade = 1.0
        if t > 360:
            fade = max(0.0, (15 - (t - 360)) / 15.0)
            if fade <= 0:
                self._solved_popup_active = False
                return
            alpha = int(alpha * fade)

        w = int(popup_w * scale)
        h = int(popup_h * scale)
        x = cx - w // 2
        y = cy - h // 2

        # 背景面板（与「帮助/设置」对话框同款皮肤：dialog_bg 底 + dialog_border 圆角描边）
        bg_surf = pygame.Surface((w, h))
        bg_surf.fill(self.colors['dialog_bg'])
        bg_rect = bg_surf.get_rect()
        pygame.draw.rect(bg_surf, self.colors['dialog_border'], bg_rect, 3, border_radius=10)
        self.screen.blit(bg_surf, (x, y))

        # 标题（对话框标题样式 + 下方分隔线）
        title_text = '复原成功！'
        title_surf = self.dialog_title_font.render(title_text, True, self.colors['dialog_title'])
        title_rect = title_surf.get_rect(center=(cx, y + int(h * (0.22 if show_result else 0.28))))
        self.screen.blit(title_surf, title_rect)
        line_y = y + int(h * (0.30 if show_result else 0.40))
        pygame.draw.line(self.screen, self.colors['dialog_border'],
                        (x + 20, line_y), (x + w - 20, line_y))

        # 外圈呼吸光晕（对话框边框同色，微弱）
        ring = pygame.Surface((w + 14, h + 14), pygame.SRCALPHA)
        glow_alpha = int(alpha * (0.25 + 0.10 * math.sin(t / 7.0)))
        pygame.draw.rect(ring, (130, 130, 140, max(0, glow_alpha)), ring.get_rect(), 2, border_radius=15)
        self.screen.blit(ring, (x - 7, y - 7))

        # 正文
        body_surf = self.dialog_font.render('所有滑块已归位', True, (215, 215, 220))
        body_rect = body_surf.get_rect(center=(cx, y + int(h * (0.48 if show_result else 0.62))))
        self.screen.blit(body_surf, body_rect)

        # 竞速模式：成绩 + TPS + 最佳恭喜
        if show_result:
            time_str = format_time(result['time_ms'])
            m = result['moves']
            tps_str = f"{result['tps']:.2f}"
            score_surf = self.dialog_font.render(
                f"用时 {time_str}　|　{m} 步　|　TPS {tps_str}", True, (240, 225, 150))
            score_rect = score_surf.get_rect(center=(cx, y + int(h * 0.62)))
            self.screen.blit(score_surf, score_rect)

            pb_parts = []
            if result.get('pb_single'):
                pb_parts.append('单次')
            if result.get('pb_ao5'):
                pb_parts.append('Ao5')
            if result.get('pb_ao12'):
                pb_parts.append('Ao12')
            if pb_parts:
                pb_text = '恭喜最佳 ' + '/'.join(pb_parts) + '！'
                pb_surf = self.dialog_font.render(pb_text, True, (255, 190, 90))
                pb_rect = pb_surf.get_rect(center=(cx, y + int(h * 0.75)))
                self.screen.blit(pb_surf, pb_rect)

        # 操作提示
        hint_surf = self.status_font.render('按 Enter 保存 ｜ 按 Esc 关闭', True, self.colors['dialog_border'])
        hint_rect = hint_surf.get_rect(center=(cx, y + int(h * 0.92)))
        self.screen.blit(hint_surf, hint_rect)

        # 供事件层判定点击区域
        self._solved_popup_rect = pygame.Rect(x, y, w, h)

    def draw_right_panel(self):
        """绘制右侧面板：垂直速度滑条 + 6 个快捷开关（滑动动画/选中动画/着色/连锁/模式/逆序）"""
        panel_x = self.screen_width - self.right_panel_width
        panel_rect = pygame.Rect(panel_x, 0, self.right_panel_width, self.screen_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], panel_rect)
        pygame.draw.line(self.screen, self.colors['border'],
                        (panel_x, 0), (panel_x, self.screen_height))

        # ---- 底部：6 个快捷开关（垂直排列）----
        sw_h = 24
        sw_gap = 4
        sw_count = 6
        switch_area_h = sw_count * sw_h + (sw_count - 1) * sw_gap + 10
        switch_area_top = self.screen_height - self.status_bar_height - switch_area_h + 4
        sw_x = panel_x + 6
        sw_w = self.right_panel_width - 12
        sw_top = switch_area_top

        self.right_panel_switch_rects = {}

        def _sw_btn(key, label, getter):
            nonlocal sw_top
            rect = pygame.Rect(sw_x, sw_top, sw_w, sw_h)
            bg, color = self.colors['input_bg'], (150, 150, 150)
            if key == 'game_mode':
                mode = getattr(self, 'game_mode', 'practice')
                if mode == 'create':
                    # 创造模式用「选中滑块」的绿色
                    bg, color = self.colors['block_selected'], (255, 255, 255)
                    text = '模式:创造'
                elif mode == 'timed':
                    bg, color = self.colors['button_bg'], (255, 255, 255)
                    text = '模式:竞速'
                else:
                    text = '模式:练习'
            else:
                on = bool(getter())
                text = f'{label}:{"开" if on else "关"}'
                if on:
                    bg, color = self.colors['button_bg'], (255, 255, 255)
            pygame.draw.rect(self.screen, bg, rect, border_radius=4)
            ts = self.status_font.render(text, True, color)
            self.screen.blit(ts, ts.get_rect(center=rect.center))
            self.right_panel_switch_rects[key] = rect
            sw_top += sw_h + sw_gap

        _sw_btn('animation_enabled', '滑动动画', lambda: self.animation_enabled)
        _sw_btn('selection_animation_enabled', '选中动画', lambda: self.selection_animation_enabled)
        _sw_btn('coloring_enabled', '着色', lambda: self.coloring_enabled)
        _sw_btn('chain_hint_enabled', '连锁', lambda: self.chain_hint_enabled)
        _sw_btn('game_mode', '模式', lambda: None)
        _sw_btn('macro_reverse_mode', '逆序宏', lambda: self.macro_reverse_mode)

        # ---- 上方：垂直滑条（左=缩放，右=速度）----
        track_top = self.menu_bar_height + 35
        track_bottom = switch_area_top - 10
        track_height = track_bottom - track_top

        speed_x = panel_x + self.right_panel_width - 18   # 右列轨道
        zoom_x = panel_x + 18                            # 左列轨道

        speed_label = self.status_font.render("速度", True, self.colors['status_text'])
        zoom_label = self.status_font.render("缩放", True, self.colors['status_text'])
        self.screen.blit(speed_label, speed_label.get_rect(center=(speed_x, self.menu_bar_height + 15)))
        self.screen.blit(zoom_label, zoom_label.get_rect(center=(zoom_x, self.menu_bar_height + 15)))

        if track_height > 0:
            half = self.right_panel_width // 2
            # 左半：缩放滑条
            pygame.draw.line(self.screen, self.colors['border'],
                            (zoom_x, track_top), (zoom_x, track_bottom), 2)
            norm_z = (self.zoom - self.min_zoom) / max(1e-6, self.max_zoom - self.min_zoom)
            norm_z = max(0.0, min(1.0, norm_z))
            # 倒置：滑条顶部=放大(max_zoom)，底部=缩小(min_zoom)
            knob_y = int(track_top + (1.0 - norm_z) * track_height)
            self.zoom_slider_rect = pygame.Rect(panel_x + 4, track_top, half - 8, track_height)
            knob_color = self.colors['button_hover'] if getattr(self, 'zoom_slider_dragging', False) else self.colors['button_bg']
            self.zoom_knob_rect = pygame.Rect(zoom_x - 10, knob_y - 6, 20, 12)
            pygame.draw.rect(self.screen, knob_color, self.zoom_knob_rect, border_radius=4)

            # 右半：速度滑条
            pygame.draw.line(self.screen, self.colors['border'],
                            (speed_x, track_top), (speed_x, track_bottom), 2)
            norm_v = (self.animation_duration - self.SPEED_MIN_MS) / max(1e-6, self.SPEED_MAX_MS - self.SPEED_MIN_MS)
            norm_v = max(0.0, min(1.0, norm_v))
            knob_y = int(track_top + norm_v * track_height)
            self.slider_rect = pygame.Rect(panel_x + half, track_top, half - 4, track_height)
            knob_color = self.colors['button_hover'] if self.slider_dragging else self.colors['button_bg']
            self.slider_knob_rect = pygame.Rect(speed_x - 10, knob_y - 6, 20, 12)
            pygame.draw.rect(self.screen, knob_color, self.slider_knob_rect, border_radius=4)

    # ==================================================================
    # 左键单击反馈（全 GUI 生效的涟漪动效）
    # ==================================================================
    CLICK_FEEDBACK_MS = 380          # 单次涟漪时长（毫秒）
    CLICK_FEEDBACK_RADIUS = 34       # 涟漪最大半径（像素）
    CLICK_FEEDBACK_MAX = 12          # 同时存在的涟漪上限（防连点堆积）

    def spawn_click_feedback(self, pos):
        """记录一次左键单击的涟漪。

        在事件分发最前面调用，故与命中的控件无关：棋盘、菜单、面板、
        对话框、教程面板等任意位置的左键单击都会有反馈。
        """
        if not pos:
            return
        fx = getattr(self, '_click_feedback', None)
        if fx is None:
            fx = self._click_feedback = []
        fx.append({'x': int(pos[0]), 'y': int(pos[1]),
                   't0': pygame.time.get_ticks()})
        if len(fx) > self.CLICK_FEEDBACK_MAX:
            del fx[:-self.CLICK_FEEDBACK_MAX]

    def draw_click_feedback(self):
        """绘制左键单击涟漪：外扩圆环 + 中心亮点，随时间淡出。

        在整帧绘制的最上层调用（模态对话框之上），保证任何界面都能看到。
        """
        fx = getattr(self, '_click_feedback', None)
        if not fx:
            return
        now = pygame.time.get_ticks()
        r_max = self.CLICK_FEEDBACK_RADIUS
        alive = []
        for item in fx:
            p = (now - item['t0']) / float(self.CLICK_FEEDBACK_MS)
            if p >= 1.0:
                continue
            alive.append(item)
            alpha = int(170 * (1.0 - p))
            if alpha <= 0:
                continue
            # 缓出：半径先快后慢地扩张
            radius = 6 + (r_max - 6) * (1.0 - (1.0 - p) ** 2)
            size = int(radius) * 2 + 4
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            center = (size // 2, size // 2)
            pygame.draw.circle(surf, (150, 220, 255, alpha), center, int(radius), 2)
            # 中心亮点：快速收缩，让「点到了」更明确
            dot_r = max(1, int(4 * (1.0 - p)))
            pygame.draw.circle(surf, (225, 245, 255, min(255, alpha + 60)),
                               center, dot_r)
            self.screen.blit(surf, (item['x'] - center[0], item['y'] - center[1]))
        self._click_feedback = alive
