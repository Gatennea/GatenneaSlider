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
import os

import pygame

from game import DIRECTIONS as SQ_DIRECTIONS
from game_mi import mi_key, mi_vertices
from game_mi import neighbors as mi_neighbors
from game_mi import DIRECTIONS as MI_DIRECTIONS
from game_mi import GAP_DIRECTIONS as MI_GAP_DIRECTIONS
from game_triangle import tri_key
from game_triangle import neighbors as tri_neighbors
from game_triangle import DIRECTIONS as TRI_DIRECTIONS
from game_triangle import GAP_DIRECTIONS as TRI_GAP_DIRECTIONS
from gui.cell_class import cell_class, class_index
from gui.group_render import draw_group_chunks
from gui.mi_view import MiBoardView
from gui.triangle_view import TriangleBoardView
from records import format_time


class RendererMixin:
    """渲染相关方法 Mixin"""

    def _board_px(self):
        """方形棋盘的像素几何 → (格宽, 缝隙, 步进)，三个数全是整数像素。

        **为什么必须取整**：缝隙不是画出来的，而是「相邻两块之间的剩余空间」。
        若按 float 走（如 zoom=1.9 时格宽 114、缝 7.6、步进 121.6），
        `pygame.Rect` 对 float 坐标是截断，相邻两块的截断误差不相等，
        于是同一块棋盘上出现「这条缝 13px、那条 14px」——观感就是缝不齐。
        先把格宽/缝隙各自四舍五入成整数，步进 = 格宽 + 缝隙 也就恒为整数，
        任何两列（行）之间的缝都严格等于同一个 `缝隙` 值。

        与 SVG / canvas 版对齐的口径：那边坐标本身就是整数像素，故从来没这个毛病。
        """
        cell = max(1, int(round(self.cell_size * self.zoom)))
        gap = max(1, int(round(self.gap_width * self.zoom)))
        return cell, gap, cell + gap

    def _slider_corner_radius(self):
        """圓角半徑的**上限**（像素），方形直接用這個值。

        方形是 `pygame.draw.rect(border_radius=R)`，弧半徑就是 R，與塊的
        60px 邊長之比約 8.3%。多邊形（三角/米字/碎三角）不用這個固定值，
        而是走 `_corner_radius_for`：**按塊的最短邊給同一個比例**——它們的
        塊小得多（碎三角最短邊只有 30px），照抄固定像素會被削掉三分之一。

        歷史上這裡統一的是「削進深度」（R·(√2−1) ≈ 2px），同樣 2px 削進下
        90° 角弧半徑 4.8px、45° 只有 1.2px、30° 只有 0.7px——角越尖越尖，
        這正是「方形跟三角/碎三角像兩種畫風」的根。改為統一弧半徑（2026-10-24）。
        """
        return max(1, int(round(5 * self.zoom)))

    def _rounded_polygon_points(self, pts, radius):
        """把凸多邊形每個頂點削成**固定弧半徑 radius** 的圓角（像素）。

        口徑（2026-10-24 統一畫風時修正）：統一的是**弧半徑**，不是削進深度。
        舊實現按「削進深度」統一，同樣 2px 削進下，90° 角的弧半徑是 4.8px、
        60° 是 2px、45° 只有 1.2px、30° 只有 0.7px——角越尖看起來越尖，
        於是方形（pygame border_radius=5，弧半徑就是 5）跟三角/米字站成了
        兩種畫風。改成直接給弧半徑後，任意角度的圓角都與方形同尺寸。

        對頂角 θ：沿兩邊各回退 cut = radius·tan(θ/2) 得切點，再以「內角
        平分線方向、距頂點 radius/sin(θ/2)」定圓心，採短弧採樣。
        退化保護：邊太短使 cut 超過半邊長時自動縮小有效半徑；近乎平角 /
        退化頂點保留原樣；圓心若落在外側則翻轉（凸多邊形保險，正常不觸發）。
        """
        n = len(pts)
        if n < 3 or radius <= 0:
            return [tuple(p) for p in pts]
        out = []
        SEG = 5
        for k in range(n):
            prev = pts[(k - 1) % n]
            cur = pts[k]
            nxt = pts[(k + 1) % n]
            vin_x, vin_y = prev[0] - cur[0], prev[1] - cur[1]
            vout_x, vout_y = nxt[0] - cur[0], nxt[1] - cur[1]
            l1 = math.hypot(vin_x, vin_y)
            l2 = math.hypot(vout_x, vout_y)
            if l1 < 1e-6 or l2 < 1e-6:
                out.append(tuple(cur))
                continue
            uin_x, uin_y = vin_x / l1, vin_y / l1
            uout_x, uout_y = vout_x / l2, vout_y / l2
            dot = max(-1.0, min(1.0, uin_x * uout_x + uin_y * uout_y))
            ang = math.acos(dot)
            if ang < 1e-3 or ang > math.pi - 1e-3:
                out.append(tuple(cur))
                continue
            # 弧半徑直接取 radius（不再由削進深度反推——那正是「角越尖越尖」
            # 的來源）。邊太短時 cut 會被鉗到半邊長，r_eff 隨之縮小。
            r_eff = radius
            cut = r_eff * math.tan(ang / 2.0)
            cut = min(cut, l1 / 2.0, l2 / 2.0)
            if cut < 1e-6:
                out.append(tuple(cur))
                continue
            r_eff = cut / math.tan(ang / 2.0)
            p1 = (cur[0] + uin_x * cut, cur[1] + uin_y * cut)
            p2 = (cur[0] + uout_x * cut, cur[1] + uout_y * cut)
            # 內角平分線（從頂點出發的兩邊方向之和）指向多邊形內部
            bx, by = uin_x + uout_x, uin_y + uout_y
            bl = math.hypot(bx, by)
            if bl < 1e-9:  # 退化：二次貝塞爾兜底
                out.append(tuple(p1))
                for s in range(1, SEG):
                    t = s / float(SEG)
                    mt = 1 - t
                    out.append((mt * mt * p1[0] + 2 * mt * t * cur[0] + t * t * p2[0],
                                mt * mt * p1[1] + 2 * mt * t * cur[1] + t * t * p2[1]))
                out.append(tuple(p2))
                continue
            bnx, bny = bx / bl, by / bl
            dist = r_eff / math.sin(ang / 2.0)
            ox, oy = cur[0] + bnx * dist, cur[1] + bny * dist
            # 保險：圓心落在外側則翻轉（凸多邊形不應發生，但防萬一）
            if not self._point_in_convex((ox, oy), pts):
                ox, oy = cur[0] - bnx * dist, cur[1] - bny * dist
            a1 = math.atan2(p1[1] - oy, p1[0] - ox)
            a2 = math.atan2(p2[1] - oy, p2[0] - ox)
            da = a2 - a1
            while da > math.pi:
                da -= 2 * math.pi
            while da < -math.pi:
                da += 2 * math.pi
            out.append(tuple(p1))
            for s in range(1, SEG):
                a = a1 + da * (s / float(SEG))
                out.append((ox + r_eff * math.cos(a), oy + r_eff * math.sin(a)))
            out.append(tuple(p2))
        return out

    @staticmethod
    def _shortest_edge(pts):
        """凸多邊形的最短邊長（像素）。所有「按塊比例」的口徑共用它。"""
        n = len(pts)
        if n < 3:
            return 0.0
        return min(math.hypot(pts[(k + 1) % n][0] - pts[k][0],
                              pts[(k + 1) % n][1] - pts[k][1])
                   for k in range(n))

    @staticmethod
    def _border_width_for(pts, cap):
        """按滑塊**最小邊長**給普通塊的描邊寬度（像素），與方形同比例。

        方形 60px 塊配 2px 邊（3.3%），而碎三角的塊最短邊只有 30px，照抄
        2px 就等於 6.7%——放大看每條邊都比縫還搶眼，整盤發髒。按比例給寬
        之後四種形態的「線條重量」才一致。
        """
        n = len(pts)
        if n < 3:
            return 1
        shortest = min(math.hypot(pts[(k + 1) % n][0] - pts[k][0],
                                  pts[(k + 1) % n][1] - pts[k][1])
                       for k in range(n))
        return max(1, min(int(round(cap)), int(round(shortest * 0.033))))

    @staticmethod
    def _corner_radius_for(pts, cap):
        """按滑塊**最小邊長**給圓角半徑，比例與方形一致（5/60 ≈ 8.3%）。

        為什麼不能全盤用一個固定像素值：碎三角的塊邊長只有 30px、米字的
        三角形短邊 83px、三角 91px，同給 10px 圓角時碎三角等於被削掉三分
        之一，圓角弧上的描邊會在每個頂點伸出一圈「羽毛」（2026-10-24 放大
        實測）。按最小邊的比例給，四種形態的「圓鈍感」才真的一致——方形
        border_radius=5 對 60px 塊正好是 8.3%，本函數沿用同一個比例。
        """
        n = len(pts)
        if n < 3:
            return 0.0
        shortest = min(math.hypot(pts[(k + 1) % n][0] - pts[k][0],
                                  pts[(k + 1) % n][1] - pts[k][1])
                       for k in range(n))
        return max(1.5, min(float(cap), shortest * 0.083))

    @staticmethod
    def _offset_polygon_px(pts, d):
        """把凸多邊形的每條邊沿法線平移 d 像素（螢幕座標）。d>0 外擴、d<0 內縮。

        頂點沿內角平分線的反方向外移 d/sin(θ/2)，這樣平移後每條邊到原邊的
        距離都嚴格等於 |d|，與「向質心縮放」的近似不同（後者在不等邊三角形上
        各邊內移量不等，縫會一寬一窄）。

        用途：通用多邊形通道把塊**內縮半個縫寬**，讓縫帶露出來（方形/三角/
        米字都是這個畫法，通用通道原先塊貼邊，所以看起來是另一套畫風）。
        """
        if abs(d) < 1e-9 or len(pts) < 3:
            return [tuple(p) for p in pts]
        n = len(pts)
        out = []
        for k in range(n):
            prev = pts[(k - 1) % n]
            cur = pts[k]
            nxt = pts[(k + 1) % n]
            vin_x, vin_y = prev[0] - cur[0], prev[1] - cur[1]
            vout_x, vout_y = nxt[0] - cur[0], nxt[1] - cur[1]
            l1 = math.hypot(vin_x, vin_y)
            l2 = math.hypot(vout_x, vout_y)
            if l1 < 1e-9 or l2 < 1e-9:
                out.append(tuple(cur))
                continue
            ux, uy = vin_x / l1, vin_y / l1
            vx, vy = vout_x / l2, vout_y / l2
            dot = max(-1.0, min(1.0, ux * vx + uy * vy))
            ang = math.acos(dot)
            sin_h = math.sin(ang / 2.0)
            if sin_h < 1e-6:
                out.append(tuple(cur))
                continue
            # 內角平分線 = 兩條邊方向之和；外側取其反方向
            bx, by = -(ux + vx), -(uy + vy)
            bl = math.hypot(bx, by)
            if bl < 1e-9:
                out.append(tuple(cur))
                continue
            # 退化保護：近平角時 sin(θ/2)→1 不會爆炸，但極窄夾角（<1°）的
            # 頂點移動距離會很大，直接保留原頂點（這種形狀本身也不合法）。
            step = d / sin_h
            if abs(step) > 8.0 * abs(d):
                out.append(tuple(cur))
                continue
            out.append((cur[0] + bx / bl * step, cur[1] + by / bl * step))
        return out

    # 米字/三角滑块在缩得较小时，斜边切割像素出现明显阶梯锯齿（方形是
    # 轴对齐边，天然贴合像素网格，无此问题；本精简版 pygame 无 gfxdraw，
    # 用不了多边形抗锯齿）。办法是局部超采样抗锯齿（SSAA）：在 S 倍大的
    # 临时面上硬边绘制，再 smoothscale 回目标尺寸——边界像素与「透明」
    # 混合成半透明边，blit 时与棋盘底色自然融合，得到平滑边缘。只在 cell
    # 小于阈值时启用：大 cell 斜边锯齿本不可见，省掉每滑块一次 surface 分
    # 配 + smoothscale 的开销（256 滑块时差距明显）。
    _SLIDER_AA_MIN_CELL = 18   # cell(px) 低于此值才给三角/米字滑块开 AA
    _SLIDER_AA_SCALE = 3       # 超采样倍率

    def _slider_aa_on(self, cell_px):
        """三角/米字滑块是否启用抗锯齿（cell 小于阈值时）。"""
        return cell_px < self._SLIDER_AA_MIN_CELL

    def _draw_aa_polygon(self, poly, fill, border_color=None, border_w=0):
        """局部超采样抗锯齿画一个多边形（填充 + 可选描边）到 self.screen。

        poly 为屏幕坐标浮点列表。按外包框建一块 SRCALPHA 临时面，坐标平移
        到局部并放大 _SLIDER_AA_SCALE 倍，硬边填充 + 描边，再 smoothscale
        回 1×，blit 到外包框原点。边缘半透明与底色混合，斜边不再有阶梯；
        外形轮廓位置不变，不侵占块间缝隙（与 _board_px 的等宽缝隙兼容）。
        """
        S = self._SLIDER_AA_SCALE
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        pad = max(2, int(border_w) + 2)
        x0 = int(math.floor(min(xs))) - pad
        y0 = int(math.floor(min(ys))) - pad
        x1 = int(math.ceil(max(xs))) + pad
        y1 = int(math.ceil(max(ys))) + pad
        w = max(1, x1 - x0)
        h = max(1, y1 - y0)
        big = pygame.Surface((w * S, h * S), pygame.SRCALPHA)
        ipoly = [(int(round((p[0] - x0) * S)), int(round((p[1] - y0) * S)))
                 for p in poly]
        pygame.draw.polygon(big, fill, ipoly)
        if border_color is not None and border_w > 0:
            pygame.draw.polygon(big, border_color, ipoly, max(1, border_w * S))
        self.screen.blit(pygame.transform.smoothscale(big, (w, h)), (x0, y0))

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
        """繪製選中的縫隙線（三族之一）：貫穿整個視窗，與方形同口徑。

        舊版只畫到棋形凸包（理由是「畫到形狀外的線段只是雜訊」），但同一個
        交互在方形裡是「一刀切開整個地圖」，三角裡卻只剩一小段——用戶
        2026-10-24 指出這一點。現在統一：紅線沿縫方向延長到螢幕外，盤面
        外的部分是**背景**上的直線，恰好提示「這是整條縫，不是局部缺口」。
        裁剪與否只影響視覺，縫的號與可滑性完全不變。

        沒有這條線時，選中縫隙只有右下角文字提示，玩家看不到選了哪條。
        """
        gap = getattr(self, 'selected_gap', None)
        if not gap:
            return
        gap_type, line = gap
        if gap_type not in ('h', 'p', 'n'):
            return
        seg = view.gap_line_segment(gap_type, line, hull)
        self._draw_seam_through_screen(seg)

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

        # 縫帶底：用**未內縮**的精確形狀鋪 gap 色。
        # 三角是 60° 六塊交會，每塊各內縮半個縫寬後，頂點周圍必然留下一個
        # 小六邊形；`_draw_triangle_gaps` 沿各條縫畫的是矩形帶，蓋不到那個
        # 六邊形的楔形角，於是露出背景色——比縫色 (80) 暗得多的 (30)，放大
        # 看就是每個頂點的「梅花黑點」（用戶 2026-10-24 投訴畫風不統一，
        # 這是三角與方形的第二處差異；方形是 90° 四塊交會、恰好填滿一圈）。
        # 精確形狀的並集恰好等於「盤面 + 縫帶」，鋪一層就乾淨了。
        # 必須在 selected_gap 之前鋪，否則紅線被蓋掉。
        if getattr(self, 'gap_width', 0) > 0:
            _seal = self.colors['gap']
            for block in self.game.blocks:
                i, j, up = tri_key(block)
                pts = [self.world_to_screen(*p)
                       for p in view.piece_polygon(i, j, up, inset=False)]
                # 外擴 1px：斜邊的柵格化在相鄰塊之間會留 1px 亞像素縫，
                # 不補就會在縫裡數到背景色（像素測試抓到的就是這些）
                pygame.draw.polygon(
                    self.screen, _seal, self._offset_polygon_px(pts, 1.0))

        self._draw_triangle_selected_gap(view, hull)

        scaled_cell = self.cell_size * self.zoom
        radius = self._slider_corner_radius()  # 全形態統一圓角**半徑**
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


        # S1-2：撤销/重做的边框配色（三形态共用同一处定义），每帧只算一次
        _sel_anim = self._sel_anim_border()
        # S2-1：求解演示「当前步」光边（一次性，随动画进度收；键集合三形态通用）
        _play_head = self._play_head_border()
        _play_keys = self._play_head_keys() if _play_head is not None else ()

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
                elif _sel_anim is not None and is_selected:
                    # S1-2：撤销冷色/重做暖色——只换边框，填充不动（整片高亮是特色）
                    border_color, border_w = _sel_anim
                elif _play_head is not None and (i, j, up) in _play_keys:
                    # S2-1：同上（三角的键带朝向分量 up）
                    border_color, border_w = _play_head
                else:
                    # 分组着色：從外側向內一圈的縮環畫法（朝向不參與著色）。
                    # 描邊色不能直接換成組色：pygame 多邊形描邊以邊線為中心
                    # 向外也擴半個線寬，會漫進塊間縫隙蓋住縫線（含選中紅線），
                    # 縮環後著色帶整體落在滑塊內，與方形 rect 描邊同觀感
                    if getattr(self, 'coloring_enabled', False) and self.current_step > 1:
                        ring_color = self._group_color_for((i, j))
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(i, j, up)]
                rpoly = self._rounded_polygon_points(
                    poly, self._corner_radius_for(poly, radius))
                if self._slider_aa_on(scaled_cell):
                    self._draw_aa_polygon(rpoly, fill, border_color, border_w)
                else:
                    pygame.draw.polygon(self.screen, fill, rpoly)
                    pygame.draw.polygon(self.screen, border_color,
                                        rpoly, border_w)
                # 连锁提示：同類塊叠半透明白（hover 更亮）
                if hint_occ is not None and (i, j, up) in hint_occ:
                    self._draw_hint_overlay(rpoly, (i, j, up) == hint_hover)
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

        # 捆綁組：整組畫成一塊（組內無縫、只描組外邊）。必須在**塊循環之後**：
        # 放在循環前會被後畫的普通塊連同邊框一起蓋掉（實測只剩幾根細線）
        self._draw_bandaged_groups_poly(
            lambda b: (follow_map.get(id(b)) or anim_map.get(id(b))
                       or tri_key(b)),
            lambda key, inset: view.piece_polygon(*key, inset=inset),
            tri_neighbors)

        # 悬停连锁提示：同類空位叠半透明白（与方形空格同一套语言，
        # 不是描边轮廓——轮廓会让空位看着像有块）
        if hint_empty:
            for (i, j, up) in sorted(hint_empty):
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(i, j, up)]
                self._draw_hint_overlay(
                    self._rounded_polygon_points(
                        poly, self._corner_radius_for(poly, radius)),
                                       (i, j, up) == hint_hover)

        # 调试面板打开时：先画目标框（并把同一结果存到 self._target_region），
        # 再以该结果为基准画洞/缺口/凸起标记，两者严格一致。
        # **必须在这里调**——方形的同名调用在 draw_board 末尾，三角走的是
        # draw_triangle_board，不调就永远画不出来（2026-10-03 修：面板数字
        # 正常显示但棋盘上没有任何标记，就是漏了这一处）。
        # 记号与调试面板本体是两个独立开关：记号属于视觉强化，面板属于数据
        # 读数，可以只开记号不看面板，也可以只开面板不画记号。
        # 任一开着都要先算 region（两者共用同一基准），记号只在记号开关开时画。
        _panel_on = getattr(self, 'show_metrics_panel', False)
        _marks_on = getattr(self, 'board_marks_enabled', False)
        if _panel_on or _marks_on:
            self._compute_target_region()
            if _marks_on:
                self._draw_target_window()
                self._draw_debug_holes()

        # 选块填空选取态的金色高亮：跟随选取态本身，与面板/标记开关无关
        # （三形态铁律：共用 helper，三个 draw 各接一次）。
        self._draw_pick_fill_marks()

        # S1-4：方向标注画在滑块之后（最上层），且端点跟随选中切片而非整条缝
        self._draw_gap_direction_annotation()

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
        # 不變，插值只需動前兩個分量。插值位置**只用於畫塊本身**，背景網格
        # 與凸包另用 game.positions()（見下方：網格只在滑動結束後重畫）。
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
        # 背景網格只在「滑動結束後」重畫（與三角/方形同一套時序）：動畫
        # 播放期間 block.location 仍是起點（commit_animation 才寫入終點），
        # 所以直接拿 game.positions() 得到的就是滑動開始前的棋形。
        # 不能把 anim_map 裡插值中的浮點位置混進 cells——橫豎層級是由塊的
        # 邊導出的，2.4375 這種小數會每幀生成一批位置漂移的線（實測 36→44
        # 條、7 個非半整數層級），看起來就是「有些線亂跑」。
        hull = view.board_hull(cells)
        # 背景層級由塊的邊導出（錯位態的橫豎格邊落在半整數層級上），
        # 只傳凸包的話畫出來的仍是對齊態的整數格，與塊對不齊
        for p1, p2 in view.grid_segments(hull, cells):
            pygame.draw.line(self.screen, self.colors['gap'],
                             self.world_to_screen(*p1),
                             self.world_to_screen(*p2),
                             max(1, int(self.gap_width * self.zoom * 0.35)))

        # 縫帶底：與三角同一手法——用**未內縮**的精確形狀鋪 gap 色，讓塊
        # 內縮後露出的縫、以及頂點交會處的空隙，全部落在縫色上而不是背景色。
        # 米字每格 4 個三角形，一格的頂點是 4 塊＋相鄰格共 8 塊交會，圓角
        # 削角後露黑的範圍比三角更大（實測放大圖是羽毛狀黑角）。
        # 鋪在 selected_gap 之前，否則紅線被蓋掉。
        if getattr(self, 'gap_width', 0) > 0:
            _seal = self.colors['gap']
            for block in self.game.blocks:
                r, c, q = mi_key(block)
                pts = [self.world_to_screen(*p)
                       for p in view.piece_polygon(r, c, q, inset=False)]
                pygame.draw.polygon(
                    self.screen, _seal, self._offset_polygon_px(pts, 1.0))

        self._draw_mi_selected_gap(view, hull)

        scaled_cell = self.cell_size * self.zoom
        radius = self._slider_corner_radius()  # 全形態統一圓角**半徑**
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


        # S1-2：撤销/重做的边框配色（三形态共用同一处定义），每帧只算一次
        _sel_anim = self._sel_anim_border()
        # S2-1：求解演示「当前步」光边（一次性，随动画进度收；键集合三形态通用）
        _play_head = self._play_head_border()
        _play_keys = self._play_head_keys() if _play_head is not None else ()

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
                elif _sel_anim is not None and gi:
                    # S1-2：撤销冷色/重做暖色——只换边框，填充不动（整片高亮是特色）
                    border_color, border_w = _sel_anim
                elif _play_head is not None and (r, c, q) in _play_keys:
                    # S2-1：同上（米字的键带晶格档 q）
                    border_color, border_w = _play_head
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(r, c, q)]
                rpoly = self._rounded_polygon_points(
                    poly, self._corner_radius_for(poly, radius))
                if self._slider_aa_on(scaled_cell):
                    self._draw_aa_polygon(rpoly, fill, border_color, border_w)
                else:
                    pygame.draw.polygon(self.screen, fill, rpoly)
                    pygame.draw.polygon(self.screen, border_color,
                                        rpoly, border_w)
                # 连锁提示：同類塊叠半透明白（與方形/三角同一套語言）
                if hint_occ is not None and (r, c, q) in hint_occ:
                    self._draw_hint_overlay(rpoly, (r, c, q) == hint_hover)
                # 分组着色：縮環從外側向內一圈（位置類不含朝向 q，半整數
                # 座標在 cell_class 內部整數化），線寬沿用方形慣例。pygame
                # 多邊形描邊向外也擴半個線寬，直接描會漫進縫隙蓋住選中紅線
                if (not warn and not (_sel_anim is not None and gi)
                        and getattr(self, 'coloring_enabled', False)
                        and self.current_step > 1):
                    ring_w = max(2, int(4 * self.zoom))
                    pygame.draw.polygon(
                        self.screen, self._group_color_for((r, c)),
                        self._tri_ring(poly, ring_w / 2.0), ring_w)

        # 捆綁組：整組畫成一塊（組內無縫、只描組外邊）。必須在**塊循環之後**
        self._draw_bandaged_groups_poly(
            lambda b: (anim_map.get(id(b)) or follow_map.get(id(b))
                       or mi_key(b)),
            lambda key, inset: view.piece_polygon(*key, inset=inset),
            mi_neighbors)

        # 悬停连锁提示：同類空位叠半透明白（与方形空格同一套语言）
        if hint_empty:
            for (r, c, q) in sorted(hint_empty):
                poly = [self.world_to_screen(*p)
                        for p in view.piece_polygon(r, c, q)]
                self._draw_hint_overlay(
                    self._rounded_polygon_points(
                        poly, self._corner_radius_for(poly, radius)),
                                       (r, c, q) == hint_hover)

        # 调试面板打开时：先画目标框（同一结果存进 self._target_region），
        # 再以该结果为基准画洞/缺口/凸起标记，两者严格一致（同方形纪律）。
        #
        # **这一段原先是漏的**（2026-10-04 修）：`show_metrics_panel` 分支只加在
        # 了 `draw_board`（方形）与三角的绘制路径里，**没加在 `draw_mi_board`**。
        # 后果是 mi 下调试面板能显示数字（面板本体走 `draw_metrics_panel`），
        # 但棋盘上**永远不出现目标框与洞/凸起记号** —— 看起来「面板开着但
        # 什么都不画」。截图脚本 `test/_shot_mi_panel.py` 靠这一帧抓出来
        # （自动化测试抓不到：那一版直接调 `_draw_mi_target_frame()`，
        # 绕过了这条调用路径 → 像素有变化，但整段从没被执行）。
        # 记号与调试面板本体是两个独立开关：记号属于视觉强化，面板属于数据
        # 读数，可以只开记号不看面板，也可以只开面板不画记号。
        # 任一开着都要先算 region（两者共用同一基准），记号只在记号开关开时画。
        _panel_on = getattr(self, 'show_metrics_panel', False)
        _marks_on = getattr(self, 'board_marks_enabled', False)
        if _panel_on or _marks_on:
            self._compute_target_region()
            if _marks_on:
                self._draw_target_window()
                self._draw_debug_holes()

        # 选块填空选取态的金色高亮：跟随选取态本身，与面板/标记开关无关
        # （三形态铁律：共用 helper，三个 draw 各接一次）。
        self._draw_pick_fill_marks()

        # S1-4：方向标注画在滑块之后（最上层），且端点跟随选中切片而非整条缝
        self._draw_gap_direction_annotation()

    def _draw_mi_selected_gap(self, view: 'MiBoardView', hull):
        """繪製米字格選中的縫隙線（四族之一）：貫穿整個視窗，與方形同口徑。

        米字紋理本身就是「方格 + 每格兩條對角線」，選中哪條縫在背景裡
        看不出來，必須疊一條紅線（與方形/三角版同一套視覺語言）。舊版只
        畫到棋形凸包，用戶 2026-10-24 指出「縫隙沒有貫穿整個地圖」——
        改為沿縫方向延長到螢幕外（只動渲染，不動幾何）。
        """
        gap = getattr(self, 'selected_gap', None)
        if not gap:
            return
        gap_type, line = gap
        if gap_type not in ('h', 'v', 'd1', 'd2'):
            return
        seg = view.gap_segment(gap_type, line, hull)
        self._draw_seam_through_screen(seg)

    # ------------------------------------------------------------------
    # S1b 通用渲染通道
    # 几何引擎＝解释器：凡把形状写成数据（spec.cell_polygon）的板型，一律
    # 由同一份代码绘制，判据是「有没有形状数据」而不是「是哪个形态」。
    # ------------------------------------------------------------------
    def _generic_spec(self):
        """當前局面走通用渲染通道所需的 spec（與 _polygon_view 同門）。

        判據 = spec 帶 cell_polygon。來源有二：
          · 引擎遊戲（含碎三角）自帶 ``.spec`` → 直接用；
          · 舊引擎遊戲（game.py / game_triangle.py / game_mi.py，無
            ``.spec``）→ **選項 A 兜底**：按類型分派到註冊表 spec 構造器，
            讓通用通道也能畫它們；舊引擎遊戲本身一行不動（求解器 / 安全
            打亂 / 存檔照跑，幾何引擎只當渲染層，不接管原版其它功能）。

        效果：刪掉三個手畫渲染路徑後，默認配置（引擎開關關＝舊引擎遊戲）
        依然有 spec 可渲染——開關自此形同虛設（可保留控件或日後靜默退役）。
        """
        game = getattr(self, 'game', None)
        if game is None:
            return None
        # 通用通道強依賴 game.board（bounds_of / origin_of / 塊遍歷都以 board
        # 為入口）。舊引擎遊戲（game.py 等）**沒有 .board**——它們仍走既有手
        # 畫路徑渲染；兜底 _spec_for_old_game 只在「有 board 但無 spec」時接管。
        # 此閘門讓 _generic_spec() 與 _polygon_view() 保持一致：兩者同時為
        # None/非 None，共享的 _key_center 等才不會進通用分支卻拿到空 view。
        if getattr(game, 'board', None) is None:
            return None
        spec = getattr(game, 'spec', None)
        if spec is not None and callable(getattr(spec, 'cell_polygon', None)):
            return spec
        # 選項 A：有 board 但無 spec → 按類型兜底（舊引擎遊戲無 board，不會到這）。
        fb = self._spec_for_old_game(game)
        if fb is not None and callable(getattr(fb, 'cell_polygon', None)):
            return fb
        return None

    @staticmethod
    def _spec_for_old_game(game):
        """選項 A 兜底：舊三形態遊戲對象 → 註冊表 spec。

        按**類型**分派，不依賴 ``game.kind`` 字符串（SliderMatrix 根本
        不設 kind）。尺寸從遊戲對象自身取（m/n/k），與 EngineGame 走同一
        套註冊表 spec，故與舊引擎塊位置嚴格對齊（S0 引擎差分已證）。
        """
        from engine.registry import square_spec, tri_spec, mi_spec
        from game import SliderMatrix
        from game_triangle import TriangleSliderMatrix
        from game_mi import MiSliderMatrix
        if isinstance(game, TriangleSliderMatrix):
            return tri_spec(getattr(game, 'k', 4))
        if isinstance(game, MiSliderMatrix):
            return mi_spec(getattr(game, 'm', 4), getattr(game, 'n', 4))
        if isinstance(game, SliderMatrix):
            return square_spec(getattr(game, 'm', 4), getattr(game, 'n', 4))
        return None

    def _polygon_view(self):
        """当前局面能否通用渲染：有 cell_polygon 就能画，否则回既有手画路径。

        默认**只给旧路径不认识的板型**用：旧三形态（square/tri/mi）继续走
        各自的手画实现，一行不动 → 零回归风险；待 S1c 用 oracle 逐个对照
        验证通过后，再按用户指示删掉那些专属实现（终态是替换，不是并存）。

        环境变量 ``GATENNEA_POLY_RENDER=1`` 可强制旧形态也走通用路径，
        专供 oracle 对照（新通道 vs 旧手画路径的位置比对）使用。
        """
        spec = self._generic_spec()
        if spec is None:
            return None
        if not hasattr(self.game, 'board'):
            return None
        try:
            from gui.board_view import SpecPolygonView
        except Exception:
            return None
        # 世界座標 = 幾何單位 × **未縮放** cell_size；縮放在 world_to_screen
        # 裡統一發生。舊代碼取 _board_px()[0]（含 zoom）又疊 world+camera，
        # zoom≠1 時整條鏈路錯位——世界座標約定由此收口到一處。
        # gap_width 只影響捆綁組的 inset 形狀（見 world_polygon inset）。
        return SpecPolygonView(spec, cell_size=float(self.cell_size),
                               gap_width=float(getattr(self, 'gap_width', 0.0)))

    def _poly_view_origin(self, view):
        """通用視圖的佈局原點（世界座標）——**按板型固定，不隨局面變化**。

        舊實現把 origin 定義成「當前塊集合包圍盒的左上角」（`origin_of(board)`），
        於是每滑一步、塊集合一變、包圍盒一變、**原點就變**：移動的那一半
        因為原點補償原地不動，沒動的那一半整體平移一格——玩家眼裡就是
        「每走一步相機都在動」（2026-10-24 用戶實測投訴；實測一步 origin
        從 (0,0) 跳到 (-103.9,0)，而 camera_x/y 根本沒變）。

        現改為按**還原態**（``spec.goal_blocks``）定原點：世界座標系在一局
        之內恆定，滑動只移動塊，不再移動整盤。渲染 / 命中 / 箭頭錨點仍舊
        共用這一個 origin（三處各算一遍是「zoom≠1 全鏈路錯位」的舊病根）。
        """
        board = self.game.board
        spec = getattr(board, 'spec', None)
        cache = getattr(self, '_poly_origin_cache', None)
        if cache is not None and cache[0] is spec:
            return cache[1]
        ref = getattr(spec, 'goal_blocks', ()) or board.blocks
        minx, miny, _mx, _my = view.bounds_of(ref)
        s = view.cell_size
        origin = (-minx * s, -miny * s)   # 還原態左上角對齊世界 (0,0)
        self._poly_origin_cache = (spec, origin)
        return origin

    def _poly_key_parts(self, key):
        """扁平 location／視覺鍵 → (point, orient)（SpecPolygonView 的入參）。

        GUI 側的鍵一律是**扁平**的（方形 (r,c) / 碎三角 (P_x,P_y,角色)），
        而 SpecPolygonView 要的是嵌套的 (point, orient)——在這裡轉一次，
        三個消費端（繪製 / 質心 / 外接半徑）共用同一換算。
        """
        if len(key) > 2:
            return (key[0], key[1]), key[2]
        return (key[0], key[1]), ''

    def _poly_world_bbox(self):
        """通用通道**當前盤面**的世界包圍盒 (min_x, min_y, max_x, max_y)。

        非通用形態回 None。原點按板型固定（見 ``_poly_view_origin``），
        所以這裡必須回**真實角點**，不能再假設從 (0,0) 起——舊寫法
        「(0,0,W,H)」是建立在「origin 隨包圍盒歸零」之上的，那條假設
        正是「每步滑動整盤平移」的病根。
        """
        view = self._polygon_view()
        if view is None:
            return None
        minx, miny, maxx, maxy = view.bounds_of(self.game.board.blocks)
        s = view.cell_size
        ox, oy = self._poly_view_origin(view)
        return (minx * s + ox, miny * s + oy, maxx * s + ox, maxy * s + oy)

    def _draw_polygon_board(self, view):
        """通用多边形绘制：一份代码画所有形状，方法体内无任何形态分支。

        世界座標約定：``world = 幾何單位 × cell_size``（未縮放），
        ``screen = world_to_screen(world)``（×zoom + camera）——與米字/
        三角手畫路徑同一套，縮放與平移只發生一次。
        視覺位置走 ``_visual_key``（拖拽跟隨 / 移動動畫偏移，與舊三形態
        同源）；選中縫畫**一條直線**（足跡合併，見 `_merge_seam_line`）。

        **功能層對舊三形態對齊（Port 1，2026-10-24）**：本方法原先只畫
        「背景 + 縫 + 塊」，舊手畫路徑有的功能層在此補齊，刪舊路徑的前置
        條件（計劃 S6 對賬表）：
          - 塊循環：拖拽無效變暗+橙框 / 撞牆抖動 / 撤銷重做冷暖邊 /
            求解演示光邊 / 分組著色描邊 / 連鎖提示 / 編號字；
          - 塊循環後：捆綁組整組渲染（複用 _draw_bandaged_groups_poly，
            回調走通用視圖與引擎晶格鄰接）、連鎖提示空位、宏基準點金框；
          - epilogue：指標標記（目標框+洞/缺口/凸起）、選塊填空金標、
            方向箭頭按鍵——與三個 draw_*_board 末尾同一套鐵律。
        """
        self.screen.fill(self.colors['background'])
        board = self.game.board
        origin = self._poly_view_origin(view)

        # 選中縫足跡的繪製**移到塊循環之後**（見本方法末段）：碎三角多邊形
        # 邊貼邊、無縫隙（gap_width=0），若沿用方形「先畫縫再畫塊」的舊序，
        # 塊會把整條紅縫蓋掉——玩家點中縫卻看不到任何紅線（2026-10-24 用戶
        # 實測「沒有選中縫隙的效果」）。故通用通道改為壓在塊之上畫。
        gap = getattr(self, 'selected_gap', None)

        # 圓角半徑：與方形/三角/米字取同一個值（`_slider_corner_radius`）。
        #
        # 舊實現這裡是 depth=0（完全不削角），理由是「碎三角邊貼邊無縫隙，
        # 逐塊削角會在每個頂點咬出缺口（6 塊交會處就是小黑洞）」。那個理由
        # 成立的前提是「塊貼邊」，而方形/三角/米字**都有 gap_width 的縫**，
        # 圓角正好藏在縫裡——所以問題不是削角，是通用通道原先沒有縫。
        # 現在下面先把塊內縮半個縫寬、並鋪 gap 色底（見 _offset_polygon_px），
        # 削角的缺口落進縫帶裡，於是四種形態同一套畫風。
        radius = self._slider_corner_radius()
        # 縫寬的口徑：**按塊尺寸取比例**，不是固定像素。
        #
        # 方形棋盤的縫是格子之外的 4px（`_board_px`），塊 60px → 6.7%。通用
        # 通道的塊尺寸由板型決定：三角單元 ×cell_size 是 91px，碎三角的單元
        # 只有半個邊長、螢幕上 30px。若一律給 4px，碎三角的縫就佔到塊寬的
        # 13%——整盤每個頂點都糊成一團灰斑，遠看是「撒滿星星」（2026-10-24
        # 整盤截圖實測，4 倍放大看局部反而正常）。
        # 用「最短邊 × (gap_width / cell_size)」換算：塊 60px 得 4px（與方形
        # 一致）、91px 得 6px（與三角原有 gap*zoom 一致）、30px 得 2px。
        _gap = float(getattr(self, 'gap_width', 0.0) or 0.0)
        gap_ratio = (_gap / float(self.cell_size)) if (self.cell_size and _gap) else 0.0
        # 沒有縫就沒有地方藏圓角的缺口 → 退回尖角（否則頂點咬出黑洞）
        if gap_ratio <= 0:
            radius = 0
        # 邊框反餽三件套（每帧只算一次；helper 本身形態中立）
        _sel_anim = self._sel_anim_border()
        _play_head = self._play_head_border()
        _play_keys = self._play_head_keys() if _play_head is not None else ()
        # 拖拽無效（碰撞/斷開）變暗集合：與舊方形路徑同口徑——偏移非零的
        # 被選中塊（follow_map 的等價物；此處塊循環內無需逐塊建映射）
        follow_ids = set()
        if (getattr(self, 'drag_following', False)
                and getattr(self, 'drag_follow_invalid', False)):
            dr, dc = getattr(self, 'drag_follow_offset', (0.0, 0.0))
            if abs(dr) > 1e-9 or abs(dc) > 1e-9:
                follow_ids = {id(b) for b in self.game.blocks
                              if getattr(b, 'be_opted', False)}
        # 撞牆抖動（S1-3）：drag.py 對所有形態統一置位，舊路徑只有方形畫；
        # 通用通道一併畫上（反餽本身是形態中立的像素位移）
        _shaking = getattr(self, '_shake_t', 0) > 0
        _shake_ids = getattr(self, '_shake_blocks', set()) if _shaking else set()
        _sox = _soy = 0
        if _shaking:
            _sox, _soy = self._shake_offset()
        # 懸停連鎖提示（helper 三形態通用；碎三角下落方形分支、自然空轉）
        hint_occ, hint_empty, hint_hover = self._chain_hint_cells()
        # 分組著色開關（與舊路徑同條件：增強模式著色開 + 多級）
        _coloring = (getattr(self, 'coloring_enabled', False)
                     and self.current_step > 1)

        # 三趟繪製：縫帶底 → 全部填色 → 全部描邊。
        # 逐塊「填+描」時，後畫那塊的填色會蓋掉前畫那塊的半條描邊（相鄰兩塊
        # 共用同一條邊），結果每條邊的可見寬度都不一樣：有的只剩 1px、有的
        # 2px，接頭處還是圓角咬出的缺口——遠看就是一堆歪歪扭扭的線。
        # 分趟之後每條邊只被描一次、寬度均勻，接頭處嚴絲合縫。
        _paint = []  # (base_poly, rpoly, fill, border_color, border_w)

        # 先算一遍所有塊的螢幕多邊形。縫帶底直接用**精確形狀**（不內縮不
        # 外擴）鋪成 gap 色：若干塊的精確形狀並集 = 整個盤面（含縫帶區域），
        # 塊本身再內縮半個縫寬畫上去，露出來的那條就是縫。
        #
        # 曾試過「每塊外擴半個縫寬」當底，結果尖角處 miter 距離達 |d|/sin(θ/2)
        # （30° 角 3.86 倍），盤邊界的尖頂直接戳出星刺；內部又因各塊外擴在
        # 頂點互相咬合，留下梅花狀黑點。精確形狀沒有這兩個毛病。
        _geo = []
        for block in getattr(self.game, 'blocks', ()):
            key = self._visual_key(block)
            point, orient = self._poly_key_parts(key)
            poly = view.world_polygon(point, orient, origin)
            pts = [self.world_to_screen(x, y) for (x, y) in poly]
            if id(block) in _shake_ids and (_sox or _soy):
                pts = [(x + _sox, y + _soy) for (x, y) in pts]
            _geo.append((block, pts))

        for block, pts in _geo:
            # 縫寬按**這一塊的尺寸**取（見 gap_ratio 的說明）：同一盤裡的塊
            # 大小可以差一倍（碎三角的正三角與等腰三角），用統一像素會讓小
            # 塊的縫粗得離譜。
            shortest = self._shortest_edge(pts)
            seam_half = (max(1.0, shortest * gap_ratio / 2.0)
                         if gap_ratio > 0 else 0.0)
            # 縫帶底 = 精確形狀（外擴 1px 蓋斜邊柵格縫）；
            # 塊 = 精確形狀內縮半個縫寬後削圓角。
            base = (self._offset_polygon_px(pts, 1.0) if seam_half > 0 else pts)
            rpoly = self._rounded_polygon_points(
                self._offset_polygon_px(pts, -seam_half) if seam_half > 0 else pts,
                self._corner_radius_for(pts, radius) if seam_half > 0 else 0)
            fill = (self.colors['block_selected'] if getattr(
                block, 'be_opted', False) else self.colors['block'])
            loc = tuple(block.location)
            if id(block) in follow_ids or id(block) in _shake_ids:
                # 拖拽無效 / 撞牆：變暗 + 橙色邊框（同一套反餽）
                fill = tuple(int(ch * 0.45) for ch in fill[:3])
                border_color, border_w = (220, 80, 40), max(1, int(3 * self.zoom))
            elif _sel_anim is not None and block.be_opted:
                border_color, border_w = _sel_anim
            elif _play_head is not None and loc in _play_keys:
                border_color, border_w = _play_head
            elif _coloring:
                border_color = self._group_color_for(loc[:2])
                border_w = max(2, int(7 * self.zoom))  # 暫定7,不要改
            else:
                # 普通塊描邊走灰邊（colors['border']），與方形/三角/米字三條
                # 手畫路徑同一口徑；曾誤用 colors['line']（純紅）把所有塊描成
                # 紅邊，看起来像錯誤態（用戶投訴「詭異紅色描線」）。紅色只留給
                # 選中縫（selected_gap，三形態通用約定）。
                border_color = self.colors['border']
                border_w = self._border_width_for(pts, max(2, int(2 * self.zoom)))
            _paint.append((base, rpoly, fill, border_color, border_w))

            # 連鎖提示：同類已佔用格疊半透明白（與舊三形態同一套語言）
            if hint_occ is not None and loc in hint_occ:
                self._draw_hint_overlay(rpoly, loc == hint_hover)

            # 編號字（numbered）：畫在塊質心（與舊路徑同字體缓存/同色）
            if getattr(self, 'numbered', False) and getattr(block, 'number', None):
                font_size = max(12, int(self.cell_size * self.zoom * 0.45))
                if not hasattr(self, '_num_font_cache'):
                    self._num_font_cache = {}
                font = self._num_font_cache.get(font_size)
                if font is None:
                    # 延遲導入：GUI 模組在 import 期尚未定義 _gui_safe_font
                    from GUI import _gui_safe_font
                    font = _gui_safe_font('SimHei', font_size)
                    self._num_font_cache[font_size] = font
                text = font.render(str(block.number), True, (0, 0, 0))
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                self.screen.blit(text, text.get_rect(center=(int(cx), int(cy))))

        # 三趟落地：①縫帶底（gap 色）②塊填色 ③描邊。
        # 共用邊因此只被描一次、寬度均勻，頂點處也不會出現「後畫的填色啃掉
        # 前畫的邊」的缺口。
        #
        # 縫帶底放在最前：它是普通塊外擴半個縫寬的聯集，鋪成 colors['gap']，
        # 塊畫上去之後露出的那條邊就是縫——與方形棋盤格「先鋪縫帶再畫塊」
        # 同一套做法（方形那條路在 draw_board 開頭畫 band）。
        if gap_ratio > 0:
            for base, _r, _f, _bc, _bw in _paint:
                pygame.draw.polygon(self.screen, self.colors['gap'], base)
        #
        # 描邊後再疊一次 aalines：三角密鋪的邊幾乎全是 30°/60° 斜線，硬描邊
        # 在斜線上必然是像素階梯，遠看就是「每條線都歪歪扭扭」。線寬與顏色
        # 不變（仍走 colors['border'] 與原版 2px 口徑），只把斜邊柵格化平滑。
        for _base, rpoly, fill, _bc, _bw in _paint:
            pygame.draw.polygon(self.screen, fill, rpoly)
        for _base, rpoly, _fill, border_color, border_w in _paint:
            pygame.draw.polygon(self.screen, border_color, rpoly, border_w)
            pygame.draw.aalines(self.screen, border_color, True, rpoly)

        # 捆綁組：整組畫成一塊（組內無縫、只描組外邊）。必須在**塊循環之後**
        # ——放在循環前會被後畫的普通塊連同邊框一起蓋掉（三角實測過）。
        # 複用三角/米字那份多邊形實現，回調改走通用視圖 + 引擎晶格鄰接：
        # 形狀由 cell_polygon 回答，鄰接由 spec.lattice 回答，均形態中立。
        self._draw_bandaged_groups_poly(
            lambda b: self._visual_key(b),
            lambda key, inset: view.world_polygon(
                *self._poly_key_parts(tuple(key)), origin, inset=inset),
            self._poly_neighbors_of(view))

        # 選中縫（通用通道**壓在塊之上**）：碎三角多邊形邊貼邊、無縫隙，
        # 若沿用方形「先畫縫再畫塊」，塊會把整條紅縫蓋光——用戶實測「點了縫
        # 沒有任何效果」。方形的縫靠格間縫隙透出，碎三角沒有縫隙，故必須後畫。
        #
        # 樣式**照搬原版方形**：`colors['line']`、線寬 3px，不加粗、不加光暈、
        # 不改色，且**延長到螢幕外**（方形是貫穿整個視窗的直線，另外幾種
        # 形態此前只畫盤面內那一段，同一交互長得不一樣——用戶 2026-10-24
        # 指出）。足跡在幾何縫線板型下必然共線，合併成一段只是為了不留下
        # 1px 斷口；合併失敗時逐段畫，不做延長（那不是一條直線縫）。
        if gap:
            segs = self._poly_seam_segments(view, gap[0], gap[1], origin)
            merged = self._merge_seam_line(segs)
            if merged is not None:
                self._draw_seam_through_screen(merged, antialias=True)
            else:
                for (a, b) in segs:
                    pygame.draw.line(self.screen, self.colors['line'],
                                     self.world_to_screen(*a),
                                     self.world_to_screen(*b), 3)

        # 連鎖提示：同類空位疊半透明白（空位沒有塊，多邊形由格子身份直接算）
        if hint_empty:
            for pos in sorted(hint_empty):
                pp, oo = self._poly_key_parts(tuple(pos))
                poly = view.world_polygon(pp, oo, origin)
                pts = [self.world_to_screen(x, y) for (x, y) in poly]
                self._draw_hint_overlay(
                    self._rounded_polygon_points(
                        pts, self._corner_radius_for(pts, radius)),
                                        tuple(pos) == hint_hover)

        # 宏基準位置標記（固定座標，無論該格有無滑块；方形特性）
        base = getattr(self, 'macro_record_base_point', None)
        if base is not None:
            pp, oo = self._poly_key_parts(tuple(base))
            poly = view.world_polygon(pp, oo, origin)
            pts = [self.world_to_screen(x, y) for (x, y) in poly]
            hl = self._rounded_polygon_points(
                pts, self._corner_radius_for(pts, radius))
            pygame.draw.polygon(self.screen, (255, 200, 50), hl,
                                max(1, int(3 * self.zoom)))

        # 調試面板/標記開關：先算 region（面板與記號共用同一基準），
        # 記號只在記號開關開時畫。與三個 draw_*_board 末尾同一套鐵律；
        # 碎三角下 _mp_kind 不在受支持清單，兩個 draw 自行空轉。
        _panel_on = getattr(self, 'show_metrics_panel', False)
        _marks_on = getattr(self, 'board_marks_enabled', False)
        if _panel_on or _marks_on:
            self._compute_target_region()
            if _marks_on:
                self._draw_target_window()
                self._draw_debug_holes()

        # 選塊填空選取態的金色高亮：跟隨選取態本身，與面板/標記開關無關
        self._draw_pick_fill_marks()

        # S1-4：方向標注必須畫在**滑块之後**（最上層）
        self._draw_gap_direction_annotation()

    def _poly_neighbors_of(self, view):
        """通用通道的鄰接回調（餵給 _draw_bandaged_groups_poly）。

        GUI 扁平鍵 → 同輩扁平鄰鍵。兩件事在本回調裡一次做完：
          · **座標系**：米字 GUI (r,c) 是引擎點的 1/scale（B 晶格是半
            整數），引擎鄰接表的偏移是引擎單位——經 compat._norm_keys /
            _keys_to_positions 兩座橋換算，不自己乘除；
          · **朝向**：GUI 三角朝向是布爾（up=True/False）、引擎是
            'up'/'down' 字符串，orient_steps 表按後者索引——直接餵布爾
            會**靜默取空**（捆綁組的內部橋接全丟；2026-10-24 §6 oracle
            抓出來的第一個真 bug）。

        拖拽期間顯示鍵帶小數偏移：先吸附到 GUI 格點（步長 1/scale），
        鄰居算出後**把殘差原樣加回**——同組塊共享同一偏移，加回後鄰居鍵
        與其它成員的顯示鍵逐個對上（舊三角/米字純函數鄰接的等變性）。
        點級鄰接（顯式鄰接模式，碎三角）回落 '' 時，直接回那一格上**實際
        那塊的顯示鍵**——48 塊位置兩兩不同點，同點只會有一塊，顯示鍵才
        與 disp_key（3-tuple）對得上。
        """
        from engine.compat import _keys_to_positions, _norm_keys

        def _nbrs(key):
            key = tuple(key)
            dim = view.spec.lattice.dim
            scale = view.spec.lattice.scale
            # 吸附到格點（殘差隨後加回，故吸附誤差無害——只要落在格上）。
            # scale=1 時必須給 **int**：_real_to_point 對 scale=1 原樣透傳，
            # 而 lattice.valid 只要 int（0.0 會被判「不在板型格上」）。
            def _snap(v):
                n = int(round(v * scale))
                return n if scale == 1 else n / scale
            snapped = tuple(_snap(v) for v in key[:dim])
            resid = tuple(key[i] - snapped[i] for i in range(dim))
            try:
                _keys = _norm_keys([snapped + key[dim:]],
                                   view.spec, 'poly_neighbors')
                ekey = _keys[0]
            except Exception as _e:
                # 渲染路徑不拋：鍵不在格上（理論上不會，吸附已保證）→ 視作
                # 無鄰居，組退化成各塊分別畫，不崩。但把真實錯誤打到 stderr，
                # 避免像 2026-10-24 那樣靜默吞掉 bug（當時 _norm_keys 抛
                # 解包錯誤被 except 吃掉，捆綁組鄰接全空還查不出原因）。
                import sys, traceback as _tb
                print("[_poly_neighbors_of] 鄰接鍵轉換失敗：", repr(_e),
                      file=sys.stderr)
                _tb.print_exc()
                return []
            out = []
            for p, o in view.spec.lattice.neighbors_of(ekey[0], ekey[1]):
                if o:
                    pos, = _keys_to_positions([(p, o)], view.spec)
                    out.append(tuple(pos[i] + resid[i] for i in range(dim))
                               + (pos[dim],))
                    continue
                # 點級鄰接：回那一格上實際那塊的**顯示鍵**
                pos, = _keys_to_positions([(p, '')], view.spec)
                for b in self.game.blocks:
                    if tuple(b.location)[:dim] == tuple(pos):
                        out.append(tuple(self._visual_key(b)))
                        break
                else:
                    out.append(tuple(pos[i] + resid[i] for i in range(dim)))
            return out
        return _nbrs

    def _poly_seam_segments(self, view, gap_type, line, origin):
        """一條縫的接觸邊足跡（世界座標），按 (局面, 縫) 簽名緩存。

        每幀重算是 O(n²) 容差匹配（48 塊 ≈ 1128 對）；簽名 = 塊鍵集合 +
        縫——拖拽/動畫期間鍵不變，直接命中緩存。
        """
        board = self.game.board
        sig = (board.keys, gap_type, line)
        cache = getattr(self, '_poly_seam_cache', None)
        if cache is not None and cache[0] == sig:
            return cache[1]
        segs = view.seam_segments(board, gap_type, line, origin)
        self._poly_seam_cache = (sig, segs)
        return segs

    @staticmethod
    def _merge_seam_line(segs):
        """把一條縫的足跡合併成**一條**線段；不共線則回 None（退回逐段畫）。

        幾何縫線板型（碎三角）的縫是直線，足跡只是這條線被塊邊切成的若干
        段；逐段畫會在接頭留下 1px 斷口，看起來像虛線。合併成一條連續段
        才像「一刀切開」。判據是垂直偏移 < 1e-3 個世界單位（cell_size≈40
        時約 0.04px），共線才合併。
        """
        if not segs:
            return None
        pts = [p for seg in segs for p in seg]
        if len(pts) < 2:
            return None
        x0, y0 = pts[0]
        far = max(pts, key=lambda p: (p[0] - x0) ** 2 + (p[1] - y0) ** 2)
        dx, dy = far[0] - x0, far[1] - y0
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-9:
            return None
        ux, uy = dx / length, dy / length
        off = max(abs(-(p[0] - x0) * uy + (p[1] - y0) * ux) for p in pts)
        if off > 1e-3 * max(1.0, length):
            return None
        along = [(p[0] - x0) * ux + (p[1] - y0) * uy for p in pts]
        lo, hi = min(along), max(along)
        return ((x0 + ux * lo, y0 + uy * lo), (x0 + ux * hi, y0 + uy * hi))

    def _draw_seam_through_screen(self, seg, width=3, antialias=False):
        """把縫線沿自身方向延長到畫面外再畫（與方形同一套視覺語言）。

        方形原版把選中縫畫成**貫穿整個視窗**的直線（`(0,y)-(W,y)` /
        `(x,0)-(x,H)`）；三角、米字、通用多邊形通道都只畫棋形內部那一段，
        同一個交互在幾種形態下長得完全不一樣——用戶 2026-10-24 指出
        「縫隙沒有貫穿整個地圖」。

        這裡**只改渲染**：線的幾何定義、縫號、可滑性一律不動，只把已經
        算出來的線段兩端延長到螢幕外（超出部分 pygame 自己裁掉）。延長量
        取 2×(W+H)，任何角度都足以穿出視窗。

        `seg` 是**世界座標**兩端點（各 view 的 gap_line_segment /
        seam_segments 產物），None 直接跳過。
        """
        if seg is None:
            return
        x0, y0 = self.world_to_screen(*seg[0])
        x1, y1 = self.world_to_screen(*seg[1])
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            # 退化成一個點（這條縫在本局面只剩一個頂點那麼長）——沒有方向
            # 可延長，畫上去只是一個雜點，不如不畫
            return
        ux, uy = dx / length, dy / length
        span = 2.0 * (self.screen_width + self.screen_height)
        a = (x0 - ux * span, y0 - uy * span)
        b = (x1 + ux * span, y1 + uy * span)
        pygame.draw.line(self.screen, self.colors['line'], a, b, width)
        if antialias:
            pygame.draw.aaline(self.screen, self.colors['line'], a, b)

    def draw_board(self):
        """绘制游戏主界面"""
        _pv = self._polygon_view()
        if _pv is not None:
            self._draw_polygon_board(_pv)
            return
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

        scaled_cell, scaled_gap, step_px = self._board_px()
        # 相机偏移一次取整，随后的格坐标就都是整数 → 缝隙严格等宽
        cam_x = int(round(self.camera_x))
        cam_y = int(round(self.camera_y))

        bounds = self.game.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']

        # 缝隙绘制：连续整条线（与历史版本一致）。先画缝线、后画滑块，
        # 滑块覆盖缝线；捆绑组的大矩形最后绘制，会盖住组内那段缝线，
        # 因此「捆绑块内部不露缝」由覆盖自然达成，无需切断缝线段。
        # 缝的像素带 = [board + i*step - gap, board + i*step)：正好是第 i-1 行与
        # 第 i 行之间的空白，与滑块的位置共用同一组整数，缝宽恒等于 scaled_gap。
        gap_left = board_x + min_col * step_px + cam_x - 20
        gap_right = board_x + (max_col + 1) * step_px + cam_x + 20
        gap_top = board_y + min_row * step_px + cam_y - 20
        gap_bottom = board_y + (max_row + 1) * step_px + cam_y + 20

        # 绘制选中的横向分割线
        for i in range(min_row, max_row + 2):
            band_y = board_y + i * step_px - scaled_gap + cam_y

            if self.selected_gap == ('h', i - 1):
                line_y = band_y + scaled_gap // 2
                pygame.draw.line(self.screen, self.colors['line'],
                               (0, line_y), (self.screen_width, line_y), 3)

        # 绘制选中的纵向分割线
        for j in range(min_col, max_col + 2):
            band_x = board_x + j * step_px - scaled_gap + cam_x

            if self.selected_gap == ('v', j - 1):
                line_x = band_x + scaled_gap // 2
                pygame.draw.line(self.screen, self.colors['line'],
                               (line_x, 0), (line_x, self.screen_height), 3)

        # 绘制未选中的横向缝隙
        for i in range(min_row, max_row + 2):
            band_y = board_y + i * step_px - scaled_gap + cam_y

            if self.selected_gap != ('h', i - 1):
                pygame.draw.rect(self.screen, self.colors['gap'],
                                 pygame.Rect(gap_left, band_y,
                                             gap_right - gap_left, scaled_gap))

        # 绘制未选中的纵向缝隙
        for j in range(min_col, max_col + 2):
            band_x = board_x + j * step_px - scaled_gap + cam_x

            if self.selected_gap != ('v', j - 1):
                pygame.draw.rect(self.screen, self.colors['gap'],
                                 pygame.Rect(band_x, gap_top,
                                             scaled_gap, gap_bottom - gap_top))

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

        # S1-2：撤销/重做的边框配色，整个高亮窗口内共用一处结果（每帧只算一次）
        _sel_anim = self._sel_anim_border()
        # S2-1：求解演示「当前步」光边（一次性，随动画进度收；键集合三形态通用）
        _play_head = self._play_head_border()
        _play_keys = self._play_head_keys() if _play_head is not None else ()

        # 绘制所有滑块
        for block in self.game.blocks:
            if id(block) in follow_map:
                lr, lc = follow_map[id(block)]
            elif id(block) in anim_map:
                lr, lc = anim_map[id(block)]
            else:
                lr, lc = block.location[0], block.location[1]

            # 格坐标 → 整数像素：拖动/动画期间 lr/lc 为小数，round 后仍是逐像素平移
            screen_x = int(round(board_x + lc * step_px)) + cam_x
            screen_y = int(round(board_y + lr * step_px)) + cam_y

            if screen_x < -scaled_cell or screen_x > self.screen_width + scaled_cell:
                continue
            if screen_y < -scaled_cell or screen_y > self.screen_height + scaled_cell:
                continue

            # S1-3：越界回弹——本块属于被选中切片时整体抖动偏移（仅增强模式）
            if getattr(self, '_shake_t', 0) > 0 and id(block) in getattr(self, '_shake_blocks', set()):
                _sox, _soy = self._shake_offset()
                screen_x += _sox
                screen_y += _soy
                _is_shaking = True
            else:
                _is_shaking = False

            # 分组着色：只在滑块边界描边，中心保持原画风（淡蓝/选中淡绿）。
            # S1-2 的撤销/重做**不碰填充**——整片 be_opted 提亮是原始设计特色，
            # 冷/暖语义改由边框承担（见下方 _sel_anim 分支）。
            fill = self.colors['block_selected'] if block.be_opted else self.colors['block']
            # 拖拽跟随无效（碰撞/断开）时：变暗滑块 + 橙色边框提示不可移动
            if (self.drag_following and self.drag_follow_invalid
                    and id(block) in follow_map):
                fill = tuple(int(ch * 0.45) for ch in fill[:3])
                border_color = (220, 80, 40)
                border_w = max(1, int(3 * self.zoom))
            elif _is_shaking:
                # S1-3：越界回弹——抖动期间同样给「撞墙」橙色反馈（闪一次）
                fill = tuple(int(ch * 0.45) for ch in fill[:3])
                border_color = (220, 80, 40)
                border_w = max(1, int(3 * self.zoom))
            else:
                # S1-2：撤销冷色/重做暖色只换边框，优先级高于分组着色
                if _sel_anim is not None and block.be_opted:
                    border_color, border_w = _sel_anim
                elif _play_head is not None and tuple(block.location) in _play_keys:
                    # S2-1：求解演示正在动的那一组——光边只出现在动画播放期间
                    border_color, border_w = _play_head
                elif getattr(self, 'coloring_enabled', False) and self.current_step > 1:
                    border_color = self._group_color(block.location[0], block.location[1])
                    border_w = max(2, int(7 * self.zoom)) #暫定7,不要改
                else:
                    border_color = self.colors['border']
                    border_w = max(1, int(2 * self.zoom))
            rect = pygame.Rect(screen_x, screen_y, scaled_cell, scaled_cell)
            pygame.draw.rect(self.screen, fill, rect, border_radius=self._slider_corner_radius())
            pygame.draw.rect(self.screen, border_color, rect, border_w, border_radius=self._slider_corner_radius())

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

        # 捆绑组可视化（自由捆绑）：把同组滑块画成一整块实心矩形，
        # 让玩家在游玩中能一眼看出「这几块是胶粘的刚性整体」。
        # 三角形/米字形态当前没有 group 字段，直接跳过。
        self._draw_bandaged_groups_play(scaled_cell, scaled_gap)

        # 连锁提示：高亮的空格（无滑块）同样叠半透明白
        if hint_empty is not None:
            for (r, c) in sorted(hint_empty):
                bx = board_x + c * step_px + cam_x
                by = board_y + r * step_px + cam_y
                self._draw_hint_overlay(
                    [(bx, by), (bx + scaled_cell, by),
                     (bx + scaled_cell, by + scaled_cell), (bx, by + scaled_cell)],
                    (r, c) == hint_hover)

        # 宏基准位置标记（固定坐标，无论该格有无滑块）
        base = getattr(self, 'macro_record_base_point', None)
        if base is not None:
            br, bc = base
            bx = board_x + bc * step_px + cam_x
            by = board_y + br * step_px + cam_y
            hl_rect = pygame.Rect(bx - 3, by - 3, scaled_cell + 6, scaled_cell + 6)
            pygame.draw.rect(self.screen, (255, 200, 50), hl_rect, max(1, int(3 * self.zoom)), border_radius=self._slider_corner_radius())

        # 调试面板打开时：先画目标窗口框（并把同一 region 存到 self），
        # 再以该 region 为基准画洞/缺口/凸起标记，两者严格一致。
        # 记号与调试面板本体是两个独立开关：记号属于视觉强化，面板属于数据
        # 读数，可以只开记号不看面板，也可以只开面板不画记号。
        # 任一开着都要先算 region（两者共用同一基准），记号只在记号开关开时画。
        _panel_on = getattr(self, 'show_metrics_panel', False)
        _marks_on = getattr(self, 'board_marks_enabled', False)
        if _panel_on or _marks_on:
            self._compute_target_region()
            if _marks_on:
                self._draw_target_window()
                self._draw_debug_holes()

        # 选块填空选取态的金色高亮：跟随选取态本身，与面板/标记开关无关
        # （三形态铁律：共用 helper，三个 draw 各接一次）。
        self._draw_pick_fill_marks()

        # S1-4：方向标注必须画在**滑块之后**（最上层）。放在缝隙绘制阶段会被
        # 后画的滑块盖掉一半——圆的一半陷在块底下，看着像画崩了。
        self._draw_gap_direction_annotation()

    def _draw_bandaged_groups_poly(self, disp_key, poly_of, neighbors_of):
        """三角/米字：把捆绑组画成一整块（组内无缝、只描组外边界）。

        与方形 `_draw_bandaged_groups_play` 同观感。单位块是多边形，所以
        不能照搬「大矩形」那套，做法（gui/group_render.draw_group_pieces）：
          - 每块按普通块形状填色（组外留正常缝隙）；
          - 组内共用边铺一块同色四边形——端点取**两侧内缩边**，四边形天然
            落在组内，不会像粗线段那样在 60° 外角戳出组外（踩过）；
          - 只给非共用边重描边框，外轮廓与普通块边框同宽同色。

        disp_key(block)：显示用位置（拖拽跟随/动画插值），坐标可能带浮点
        噪声，故键统一 round 到 1e-3 再比对相邻关系。
        poly_of(key, inset)：该位置的世界坐标多边形（inset=True 为普通块形状）。
        neighbors_of(key)：该形态的相邻位置表（game_triangle/game_mi.neighbors）。
        """
        groups = {}
        for b in self.game.blocks:
            gid = getattr(b, 'group', 0)
            if not gid:
                continue
            groups.setdefault(gid, []).append((disp_key(b), b.be_opted))
        if not groups:
            return

        def _n(key):
            return tuple(round(v, 3)
                         if isinstance(v, (int, float)) and not isinstance(v, bool)
                         else v for v in key)

        from gui.group_render import (_round_pt, bridge_quad, draw_group_pieces,
                                      interior_angle, piece_edge_flags,
                                      shared_edge_index)
        for _gid, items in groups.items():
            fulls = {_n(key): poly_of(key, False) for key, _sel in items}
            insets = {_n(key): poly_of(key, True) for key, _sel in items}
            keys = set(fulls)
            pieces = []
            bridges = []
            # 组内 ≥3 块共用的顶点：各块内缩后会在该点周围漏出 ≈gap 的小洞
            # （米字同格四块的中心最典型）→ 记下顶点、各块在该点的内角之和
            # 与「到内缩顶点的最大距离」，交给 draw_group_pieces 补同色圆点。
            #
            # **内角之和 ≈ 2π 才是组内部点**：截图上那个小凸包就是没判这个——
            # 组外边界上恰好也有 3 块同组块交于一点（角各 60°，和为 π），
            # 那里根本没有洞，画圆就鼓到轮廓外面去了。
            vmap = {}
            for key, sel in items:
                nk = _n(key)
                full_poly, inset_poly = fulls[nk], insets[nk]
                for vi, v in enumerate(full_poly):
                    vk = _round_pt(v)
                    off = math.hypot(v[0] - inset_poly[vi][0],
                                     v[1] - inset_poly[vi][1])
                    ang = interior_angle(full_poly, vi)
                    rec = vmap.get(vk)
                    if rec is None:
                        vmap[vk] = [ang, off, sel]
                    else:
                        rec[0] += ang
                        rec[1] = max(rec[1], off)
            for key, sel in items:
                nk = _n(key)
                nbs = {_n(nb) for nb in neighbors_of(key)} & keys
                nbs.discard(nk)
                flags = piece_edge_flags(fulls[nk], [fulls[k] for k in nbs])
                pieces.append((insets[nk], flags, sel))
                for nk2 in sorted(nbs):
                    if nk > nk2:      # 每条内部缝只画一次
                        continue
                    i = shared_edge_index(fulls[nk], fulls[nk2])
                    j = shared_edge_index(fulls[nk2], fulls[nk])
                    if i is None or j is None:
                        continue
                    pa, pb = insets[nk], insets[nk2]
                    bridges.append((bridge_quad(
                        (pa[i], pa[(i + 1) % len(pa)]),
                        (pb[j], pb[(j + 1) % len(pb)])), sel))
            # 只在「被同组块围满一圈」的顶点补点（内角之和 ≈ 2π）；
            # 外边界上的顶点（和 < 2π）本来就没有洞，补了会鼓出轮廓。
            dots = [(v, off, sel) for v, (ang, off, sel) in vmap.items()
                    if ang >= 2 * math.pi - 0.2]
            draw_group_pieces(
                self.screen, pieces, bridges, self.world_to_screen,
                self.colors['block'], self.colors['block_selected'],
                self.colors['border'], max(1, int(2 * self.zoom)), dots)

    def _draw_bandaged_groups_play(self, scaled_cell, scaled_gap):
        """游玩主棋盘的捆绑组渲染：同组滑块 → 一整块「放大版普通滑塊」。

        目标画风（用户 2026-10-20 明确）：捆绑块就「像一个大一号的普通滑塊」——
        用普通块的填充色（block / block_selected）+ 普通块的灰色边框
        （colors['border']，宽度/圆角同普通块）；组内不画任何内部分隔线，
        读成一整块刚性体。矩形组（最常见，如 2*2、1*N）直接画一个「放大版
        普通块」圆角矩形；非矩形组（L 形/折线）退化为通用原语（实心填充 +
        仅外轮廓，无内部线）。三角/米字没有 group 字段，直接返回。
        """
        if getattr(self, 'triangle_mode', False) or getattr(self, 'mi_mode', False):
            return
        # 收集捆绑组（gid -> 块的屏幕有效位置），复用方块循环的偏移口径
        anim_map = {}
        if getattr(self, 'animating', False) and getattr(self, 'anim_blocks', None):
            t = self.ease_out(self.anim_progress)
            dr = self._anim_dr * t
            dc = self._anim_dc * t
            for i, block in enumerate(self.anim_blocks):
                sr, sc = self.anim_start_pos[i]
                anim_map[id(block)] = (sr + dr, sc + dc)
        follow_map = {}
        if getattr(self, 'drag_following', False):
            dr, dc = self.drag_follow_offset
            if abs(dr) > 1e-9 or abs(dc) > 1e-9:
                for block in self.game.blocks:
                    if block.be_opted:
                        follow_map[id(block)] = (block.location[0] + dr,
                                                 block.location[1] + dc)
        # (位置) -> 是否选中，给 draw_group_chunks 决定填充色
        sel_pos = set()
        groups = {}
        for block in self.game.blocks:
            g = getattr(block, 'group', 0)
            if not g:
                continue
            if id(block) in follow_map:
                lr, lc = follow_map[id(block)]
            elif id(block) in anim_map:
                lr, lc = anim_map[id(block)]
            else:
                lr, lc = block.location[0], block.location[1]
            if block.be_opted:
                sel_pos.add((lr, lc))
            groups.setdefault(g, []).append((lr, lc))
        if not groups:
            return
        step_px = scaled_cell + scaled_gap    # 两个参数已是整数像素（见 _board_px）
        cam_x = int(round(self.camera_x))
        cam_y = int(round(self.camera_y))

        def get_rect(r, c):
            # 与方块循环同口径：整数 step + round 到像素，缝宽才与普通块一致
            x = int(round(c * step_px)) + cam_x
            y = int(round(r * step_px)) + cam_y
            return (x, y, scaled_cell)

        from .group_render import draw_group_chunks
        # 与普通块完全一致的边框：颜色 / 宽度 / 圆角
        border_color = self.colors['border']
        border_w = max(1, int(2 * self.zoom))
        radius = self._slider_corner_radius()

        for gid, cells in groups.items():
            rs = [r for r, c in cells]
            cs = [c for r, c in cells]
            r0, r1 = min(rs), max(rs)
            c0, c1 = min(cs), max(cs)
            is_rect = len(cells) == (r1 - r0 + 1) * (c1 - c0 + 1)
            selected = any((r, c) in sel_pos for r, c in cells)
            if is_rect:
                # 像「一个大一号的普通滑塊」：单个圆角矩形，填充+边框同普通块。
                # 宽高用「整数步进 × 格数 − 缝隙」算，正好覆盖到相邻格的外沿，
                # 与逐块画出来的边界逐像素对齐。
                x = int(round(c0 * step_px)) + cam_x
                y = int(round(r0 * step_px)) + cam_y
                w = (c1 - c0 + 1) * step_px - scaled_gap
                h = (r1 - r0 + 1) * step_px - scaled_gap
                fill = self.colors['block_selected'] if selected else self.colors['block']
                rect = pygame.Rect(x, y, w, h)
                pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
                pygame.draw.rect(self.screen, border_color, rect, border_w,
                                 border_radius=radius)
            else:
                # 非矩形（L 形/折线）：通用原语——实心填充 + 仅外轮廓，无内部线
                draw_group_chunks(self.screen, {gid: cells}, get_rect, scaled_gap,
                                  self.colors['block'], self.colors['block_selected'],
                                  border_color, border_w,
                                  is_selected=lambda r, c: (r, c) in sel_pos)

    # ---------- S1-2 / S1-4：三形态共用的语义反馈原语 ----------
    #
    # **这一段是三形态唯一的样式来源**。任何只写进单一 draw_*_board 的效果
    # 都会在另外两种谜题里缺席（2026-10-05 用户指出：一处有效、另两种没有）。
    # 新增任何「发生了什么」的视觉反馈，一律在此处定义、三处各自调用。
    #
    # S1-4 曾犯的两个错，改前务必先读：
    #  (a) 图层：标注必须画在**滑块之后**。原先塞在缝隙绘制之前，滑块一盖只剩
    #      上半个圆看得见。
    #  (b) 锚点：必须按 **be_opted 选中切片的实际范围** 定位，不能按整条缝/棋盘
    #      边界算。缝是刀，同一条缝点不同的块带走的东西不同，端点跟着切片走才对。
    #
    # 几何一律由 `game.DIRECTIONS` 的格增量 + 形态自己的 view 反算屏幕位移，
    # 不维护「方向字母 → 屏幕向量」表：三角的 'w' 与米字的 'w' 屏幕朝向完全
    # 不同，任何硬编码必然错其一。

    # 撤销=冷色 / 重做=暖色。只换**边框**，不动填充——整片 be_opted 提亮是
    # 原始设计特色（用户 2026-10-05 明确要求保色）。
    SEL_ANIM_BORDER_UNDO = (70, 150, 255)
    SEL_ANIM_BORDER_REDO = (255, 150, 50)

    def _sel_anim_border(self):
        """S1-2：撤销/重做高亮窗口内的边框配色 → (色, 线宽)，其余时段回 None。

        三形态共用同一处定义。调用方按优先级套用：
        拖拽越界 / 撞墙抖动 > 本反馈 > 分组着色。
        """
        if getattr(self, 'ui_mode', 'enhanced') != 'enhanced':
            return None
        if getattr(self, '_sel_anim_timer', 0) <= 0:
            return None
        undo = getattr(self, '_sel_anim_is_undo', None)
        if undo is None:
            return None
        color = self.SEL_ANIM_BORDER_UNDO if undo else self.SEL_ANIM_BORDER_REDO
        return (color, max(2, int(4 * self.zoom)))

    # S2-1：求解演示「当前步」的光边色。**白**——be_opted 提亮填充是绿色，
    # 青绿描边跟它撞色（实测截图区分度不足）；白不与撤销蓝 / 重做橙 /
    # 越界橙红 / 选中红线任何语义色相撞，绿底与深底上都最醒目。
    PLAY_HEAD_BORDER = (252, 252, 248)

    def _play_head_border(self):
        """S2-1：求解演示中「正在動的那一組」的邊框高亮 → (色, 线宽) 或 None。

        一次性、非常駐——只存在于动画播放的那几十毫秒里，符合计划硬约束 1
        （棋盘上不加常驻动效）。求解连播 30+ 步时，玩家靠它知道眼睛看哪。

        只在**求解/宏播放**时生效（macro_executing，或梯度聚拢流水线在跑）；
        手玩时整片 be_opted 提亮已经把「动的是哪组」讲清楚了，再叠一层是噪音。

        亮度与线宽随进度收（起手最亮、落位回落），靠**纯 RGB 插值**而不是
        alpha —— pygame.draw 对不带 SRCALPHA 的目标面做 alpha 混合不可靠，
        插值出来的颜色无论底色深浅都稳定可读。
        """
        if getattr(self, 'ui_mode', 'enhanced') != 'enhanced':
            return None
        if not getattr(self, 'animating', False):
            return None
        playing = (getattr(self, 'macro_executing', False)
                   or getattr(self, '_gather_info', None) is not None)
        if not playing or not getattr(self, 'anim_blocks', None):
            return None
        p = max(0.0, min(1.0, getattr(self, 'anim_progress', 0.0)))
        k = 1.0 - 0.6 * p
        base = self.colors['border']
        glow = self.PLAY_HEAD_BORDER
        col = tuple(int(round(base[i] + (glow[i] - base[i]) * k)) for i in range(3))
        return (col, max(2, int(round((2 + 2 * k) * self.zoom))))

    def _play_head_keys(self):
        """正在动画的滑块**位置键**集合。

        三形态循环拿到的键不一样（方形是 block、三角是 (i,j,up)、米字是
        (r,c,q)），用位置键比对才能三形态通用；判 id 只有方形能接上。
        动画期间 block.location 仍是起点（终点在 commit 时才写回），所以
        这里取到的就是起点键，与绘制循环里的键同源。
        """
        return {tuple(b.location) for b in (getattr(self, 'anim_blocks', None) or [])}

    # 选块填空选取态的金色——与宏定义基准块的金框同一个色值，不引入新配色
    # （铁律：不给滑块加新填充色；这里是描边/环，本就走边框通道）。
    PICK_FILL_GOLD = (255, 200, 50)

    def _draw_pick_fill_marks(self):
        """选块填空选取态：把玩家已点选的「凸起方块」与「空位」高亮出来。

        选取态由 `GUI._pick_fill` 承载：{'block': (r, c) 或 None,
        'hole': 洞 dict 或 None}。金色 = 你选的东西——已选方块画金框
        （与宏定义基准块同款），已选空位把洞的每一格画上金环。

        按三形态铁律从三个 draw_*_board 各自调用；选取态实际只存在于
        方形（`_pick_fill_form_blocked` 入口闸门 + 建局清空），所以另两个
        形态走到这里直接返回——留着调用点是给「将来找块填空支援异形」
        预留的挂载位，也防止形态切换瞬间的陈旧状态画出错位几何。

        **通用通道分支（Port 1）**：金框貼那一個格子的**多邊形外接框**，
        與通用渲染同源；不借舊方格的 cell_step 整數像素——兩套世界座標
        在 zoom≠1 下會差半條縫。舊手畫路徑的整數像素數學原樣不動。
        """
        pf = getattr(self, '_pick_fill', None)
        if not pf:
            return
        if getattr(self, 'triangle_mode', False) or getattr(self, 'mi_mode', False):
            return
        gold = self.PICK_FILL_GOLD
        scaled_cell, scaled_gap, cell_step = self._board_px()   # 与主棋盘同一套整数像素

        spec = self._generic_spec()
        if spec is not None:
            view = self._polygon_view()
            if view is not None:
                origin = self._poly_view_origin(view)

                def _bbox_rect(pos):
                    pp, oo = self._poly_key_parts((pos[0], pos[1]))
                    pts = [self.world_to_screen(x, y) for (x, y) in
                           view.world_polygon(pp, oo, origin)]
                    xs = [q[0] for q in pts]
                    ys = [q[1] for q in pts]
                    return pygame.Rect(int(min(xs) - 3), int(min(ys) - 3),
                                       int(max(xs) - min(xs) + 6),
                                       int(max(ys) - min(ys) + 6))

                p = pf.get('block')
                if p is not None:
                    pygame.draw.rect(self.screen, gold, _bbox_rect(p),
                                     max(1, int(3 * self.zoom)),
                                     border_radius=self._slider_corner_radius())
                hole = pf.get('hole')
                if hole:
                    radius = max(3, int(scaled_cell * 0.35))
                    line_w = max(2, int(2 * self.zoom))
                    for r, c in hole.get('cells', []):
                        pp, oo = self._poly_key_parts((r, c))
                        pts = [self.world_to_screen(x, y) for (x, y) in
                               view.world_polygon(pp, oo, origin)]
                        cx = sum(q[0] for q in pts) / len(pts)
                        cy = sum(q[1] for q in pts) / len(pts)
                        pygame.draw.circle(self.screen, gold, (int(cx), int(cy)),
                                           radius, line_w)
                return

        board_x = getattr(self, '_board_x', 0)
        board_y = getattr(self, '_board_y', 0)
        cam_x = int(round(self.camera_x))
        cam_y = int(round(self.camera_y))
        p = pf.get('block')
        if p is not None:
            bx = board_x + p[1] * cell_step + cam_x
            by = board_y + p[0] * cell_step + cam_y
            hl_rect = pygame.Rect(bx - 3, by - 3, scaled_cell + 6, scaled_cell + 6)
            pygame.draw.rect(self.screen, gold, hl_rect,
                             max(1, int(3 * self.zoom)),
                             border_radius=self._slider_corner_radius())
        hole = pf.get('hole')
        if hole:
            radius = max(3, int(scaled_cell * 0.35))
            line_w = max(2, int(2 * self.zoom))
            half = scaled_cell / 2
            for r, c in hole.get('cells', []):
                cx = board_x + c * cell_step + cam_x + half
                cy = board_y + r * cell_step + cam_y + half
                pygame.draw.circle(self.screen, gold, (int(cx), int(cy)),
                                   radius, line_w)

    def _advance_key(self, key, delta):
        """形态中立的「key + 格增量」：朝向分量不参与平移。"""
        if len(key) == 2:
            return (key[0] + delta[0], key[1] + delta[1])
        return (key[0] + delta[0], key[1] + delta[1], key[2])

    def _key_center(self, key):
        """形态中立的 key → 屏幕中心。"""
        spec = self._generic_spec()
        if spec is not None:
            # 通用通道：多邊形質心（世界）→ 屏幕。origin 與渲染/命中
            # 同源（_poly_view_origin），箭頭錨點才不會漂。
            view = self._polygon_view()
            point, orient = self._poly_key_parts(key)
            poly = view.world_polygon(point, orient,
                                      self._poly_view_origin(view))
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            return self.world_to_screen(cx, cy)
        if getattr(self, 'triangle_mode', False):
            view = self._tri_view()
            return self.world_to_screen(
                *view.piece_center(key[0], key[1], bool(key[2])))
        if getattr(self, 'mi_mode', False):
            view = self._mi_view()
            return self.world_to_screen(
                *view.piece_center(key[0], key[1], key[2]))
        _, _, step_px = self._board_px()
        return (key[1] * step_px + step_px / 2.0 + int(round(self.camera_x)),
                key[0] * step_px + step_px / 2.0 + int(round(self.camera_y)))

    def _spec_gap_letters(self, spec):
        """板型 → {縫族名: (方向字母, 方向字母)}（引擎 parallel 反查字母表）。

        與 adapter._gap_directions 同源：``SeamFamily.parallel`` 存的是
        **方向向量**不是字母，必須經 compat.direction_table 反查（直接拿
        parallel 當字母餵給 try_move 會全判 bad_direction——方形打亂 0 步
        就是这么來的）。字母按字典序，兩端各一個。
        """
        from engine.compat import direction_table
        table = direction_table(spec)
        out = {}
        for fam in spec.seam_families:
            out[fam.name] = tuple(sorted(
                letter for letter, vec in table.items() if vec in fam.parallel))
        return out

    def _gap_dir_letters(self, gap_type):
        """選中縫族的兩個方向字母（通用通道；舊形態走 _game_dir_tables）。"""
        spec = self._generic_spec()
        if spec is None:
            return ()
        return self._spec_gap_letters(spec).get(gap_type, ())

    def _letter_screen_vec(self, letter, key):
        """從 key 出發走一步 letter 的**屏幕**位移向量（泛型算，不查字母表）。

        一步的屏幕向量 = 塊多邊形質心在 K+d 與 K 處的屏幕差——讓形態自己
        的幾何回答方向，與 _get_gap_direction_annotation 的位移軸同一手法
        （'w' 在三角是左上、在米字是正左，字母表回答不了；碎三角的恆等
        空間各向異性更要靠這個）。
        """
        spec = self._generic_spec()
        if spec is None:
            return None
        from engine.compat import direction_table
        d = direction_table(spec).get(letter)
        if d is None:
            return None
        c0 = self._key_center(key)
        c1 = self._key_center(self._advance_key(key, d))
        return (c1[0] - c0[0], c1[1] - c0[1])

    def _game_dir_tables(self):
        """该形态的 (DIRECTIONS, GAP_DIRECTIONS)。

        **两张表都是模块级常量，不是 game 实例的属性** —— 用
        `getattr(self.game, 'DIRECTIONS')` 取到的是空 dict，标注会静默
        退化成「什么都不画」（2026-10-05 踩：三形态全返回 None）。
        方形没有模块级 GAP_DIRECTIONS，缝族只有 h/v，这里内置兜底。
        """
        spec = self._generic_spec()
        if spec is not None:
            from engine.compat import direction_table
            return direction_table(spec), self._spec_gap_letters(spec)
        if getattr(self, 'triangle_mode', False):
            return TRI_DIRECTIONS, TRI_GAP_DIRECTIONS
        if getattr(self, 'mi_mode', False):
            return MI_DIRECTIONS, MI_GAP_DIRECTIONS
        return SQ_DIRECTIONS, {'h': ('a', 'd'), 'v': ('w', 's')}

    def _piece_screen_radius(self):
        """选中切片里代表性那块的**屏幕外接半径**（中心到最远顶点）。

        标记尺寸与让位距离都以此为准，不用「一格的屏幕长度」：三角/米字在
        斜方向上一格比块本身长得多（实测三角 k=3 未配好 zoom 时 ulen=235px
        而盘整个超出屏幕），按格长让位会把标记推到画面外。
        """
        for b in self.game.blocks:
            if not b.be_opted:
                continue
            key = tuple(b.location)
            cx, cy = self._key_center(key)
            spec = self._generic_spec()
            if spec is not None:
                view = self._polygon_view()
                point, orient = self._poly_key_parts(key)
                pts = [self.world_to_screen(*p) for p in
                       view.world_polygon(point, orient,
                                          self._poly_view_origin(view))]
            elif getattr(self, 'triangle_mode', False):
                view = self._tri_view()
                pts = [self.world_to_screen(*p)
                       for p in view.piece_polygon(
                           key[0], key[1], bool(key[2]))]
            elif getattr(self, 'mi_mode', False):
                view = self._mi_view()
                pts = [self.world_to_screen(*p)
                       for p in view.piece_polygon(key[0], key[1], key[2])]
            else:
                _, _, step_px = self._board_px()
                half = step_px / 2.0
                pts = [(cx - half, cy - half), (cx + half, cy - half),
                       (cx + half, cy + half), (cx - half, cy + half)]
            return max(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
        return 0.0

    # ---------------- S1-4 箭头按键（贴图版，三形态共用） ----------------
    _ARROW_STYLE = 'B'          # 素材样式（assets/ui/arrows/arrow_B.png）
    _ARROW_BASE_PX = 46         # zoom=1 时的按键边长；大小只跟全局缩放走
    _ARROW_CACHE_MAX = 96       # 旋转贴图缓存上限（size×角度）

    def _arrow_asset_path(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, 'assets', 'ui', 'arrows',
                            f'arrow_{self._ARROW_STYLE}.png')

    def _arrow_base(self):
        """基础贴图（朝右 0°）。方向一律靠 rotate 得到，不为每方向单独出图。"""
        if getattr(self, '_arrow_base_surf', None) is None:
            try:
                self._arrow_base_surf = pygame.image.load(
                    self._arrow_asset_path()).convert_alpha()
            except Exception:
                self._arrow_base_surf = False      # 记失败，避免每帧重试 IO
        return self._arrow_base_surf or None

    def _arrow_button_size(self):
        """按键边长：只取决于全局缩放值，与方向无关（用户定）。"""
        return max(18, int(round(self._ARROW_BASE_PX * getattr(self, 'zoom', 1.0))))

    def _arrow_sprite(self, angle_deg):
        """**先按 size 缩放、后旋转**；旋转结果绝不二次缩放。

        旋转后画布会变成更大的外接矩形，若再把它压回 size，斜方向的箭头
        就会比正交方向小 —— 那正是「缩放跟着方向走」的坑。
        """
        size = self._arrow_button_size()
        cache = getattr(self, '_arrow_sprite_cache', None)
        if cache is None:
            cache = self._arrow_sprite_cache = {}
        key = (size, int(round(angle_deg)) % 360)
        spr = cache.get(key)
        if spr is None:
            base = self._arrow_base()
            if base is None:
                return None
            if len(cache) > self._ARROW_CACHE_MAX:
                cache.clear()
            spr = pygame.transform.rotate(
                pygame.transform.smoothscale(base, (size, size)), key[1])
            cache[key] = spr
        return spr

    def _visual_offset(self):
        """当前视觉偏移（格）：拖拽跟随实时值 / 移动动画插值 / 无。

        拖拽期间 block.location 仍是起点，画面上却已经挪开了 —— 箭头锚点
        必须吃这个偏移，否则就出现「拖着走、箭头留在原地」（2026-10-05 用户报）。
        """
        if getattr(self, 'drag_following', False):
            return tuple(getattr(self, 'drag_follow_offset', (0.0, 0.0)))
        if getattr(self, 'animating', False):
            t = self.ease_out(getattr(self, 'anim_progress', 0.0))
            return (getattr(self, '_anim_dr', 0.0) * t,
                    getattr(self, '_anim_dc', 0.0) * t)
        return (0.0, 0.0)

    def _visual_key(self, block):
        """块的「视觉」key（含拖拽/动画偏移）。

        偏移**只作用在正在移动的那些块上**：拖拽 = 选中组（be_opted），
        动画 = ``anim_blocks``。旧实现无条件加到所有块上——于是碎三角一播
        重做动画，整盘跟着平移一格（用户 2026-10-24 报「重做动画完全错误」），
        拖拽时也会整盘跟着走。方形路径用 follow_map / anim_map 按 id 分发，
        本来就没有这个毛病；这里是通用通道漏掉的那道过滤。
        """
        key = tuple(block.location)
        dr, dc = self._visual_offset()
        if abs(dr) < 1e-9 and abs(dc) < 1e-9:
            return key
        if getattr(self, 'drag_following', False):
            if not getattr(block, 'be_opted', False):
                return key
        elif getattr(self, 'animating', False):
            if not any(b is block
                       for b in (getattr(self, 'anim_blocks', None) or ())):
                return key
        else:
            return key
        if len(key) == 2:
            return (key[0] + dr, key[1] + dc)
        return (key[0] + dr, key[1] + dc, key[2])

    def _get_gap_direction_annotation(self):
        """选中缝两端的「箭头按键」几何。**每帧重算**，不缓存几何。

        几何依赖 location + camera + zoom + 拖拽跟随偏移，缓存它就会得到
        「箭头不跟随」的 bug。只有 maxstep（try_move_ex 逐步试算，1..80）
        是贵的，单独按「缝 + 切片」签名缓存。

        返回 dict 或 None：
            buttons : [(方向字母, 中心(x,y), 旋转角度°, 可走 bool), ...] 两端
            size    : 按键边长
        副作用：把命中矩形写进 self._arrow_buttons，供点击检测复用同一套几何。
        """
        self._arrow_buttons = []
        if getattr(self, 'ui_mode', 'enhanced') != 'enhanced':
            return None
        # 箭头按键是宣传中的五种操作方式之一，有自己的开关（默认开）：
        # 不想看见箭头时不必为此把整个界面退回朴素模式。
        if not getattr(self, 'arrows_enabled', True):
            return None
        gap = getattr(self, 'selected_gap', None)
        # 移动动画播放中按键跟着插值移动会误导点击，直接不画
        if gap is None or getattr(self, 'animating', False):
            return None
        chosen = [b for b in self.game.blocks if b.be_opted]
        if not chosen:
            return None

        deltas, table = self._game_dir_tables()
        dirs = tuple(table.get(gap[0], ()))
        if len(dirs) != 2 or dirs[0] not in deltas or dirs[1] not in deltas:
            return None
        sample = self._visual_key(chosen[0])
        if len(sample) not in (2, 3):
            return None

        # 位移轴：dirs[0] 一格的屏幕位移。让形态自己的几何去回答方向，
        # 不查「字母 → 屏幕向量」表（'w' 在三角是左上、在米字是正左）。
        c0 = self._key_center(sample)
        c1 = self._key_center(self._advance_key(sample, deltas[dirs[0]]))
        ux, uy = c1[0] - c0[0], c1[1] - c0[1]
        ulen = math.hypot(ux, uy)
        if ulen < 1e-6:
            return None
        ux, uy = ux / ulen, uy / ulen

        size = self._arrow_button_size()

        # 锚点：**上一次选中滑块时的鼠标位置**（用户定）。存的是世界坐标，
        # 不是屏幕坐标 —— 同一位置换个记法而已，好处是平移/缩放后按键仍
        # 钉在玩家点过的那个棋盘位置上，不会重演「箭头留在原地」。
        # 没有任何记录时（例如由键盘/回放选中）回退到切片投影外沿中点。
        px, py = -uy, ux                       # 垂直于推行方向
        anchor_w = getattr(self, '_gap_anchor_world', None)
        if anchor_w is None:
            # 切片投影包围盒的「外沿中点」：只看选中切片，不看整条缝（bug-b）。
            # 用**视觉 key**，拖拽时按键才跟着切片走。
            ts, ss = [], []
            for b in chosen:
                cx, cy = self._key_center(self._visual_key(b))
                ts.append(cx * ux + cy * uy)
                ss.append(cx * px + cy * py)
            t_lo, t_hi = min(ts), max(ts)
            s_mid = (min(ss) + max(ss)) / 2.0
            hi_pt = (ux * t_hi + px * s_mid, uy * t_hi + py * s_mid)
            lo_pt = (ux * t_lo + px * s_mid, uy * t_lo + py * s_mid)
            use_pad = True
        else:
            # 鼠标点附近：两个按键沿推行轴分居两侧，间距够开避免互相吃点击
            base = self.world_to_screen(*anchor_w)
            off = size * 0.80
            hi_pt = (base[0] + ux * off, base[1] + uy * off)
            lo_pt = (base[0] - ux * off, base[1] - uy * off)
            use_pad = False

        # 「点下去会不会被拒绝」：干跑与点击**同一条判定路径**（见
        # _arrow_move_allowed）。别再自己逐格试算 try_move_ex —— 那与
        # move_selected_blocks 的步数档/形态专属判定是两套，会出现
        # 「能走却没箭头 / 有箭头点了却被拒」。
        # 成本只在签名变化的那一帧：缝 + 切片 + 步数档 + 参考块都算进去。
        sig = (gap, tuple(tuple(b.location) for b in chosen),
               getattr(self, 'current_step', 1),
               id(getattr(self, 'selected_block', None)))
        if getattr(self, '_gap_allowed_sig', None) != sig:
            self._gap_allowed = {d: self._arrow_move_allowed(d) for d in dirs}
            self._gap_allowed_sig = sig
        allowed = self._gap_allowed

        m = size / 2.0 + 6
        if use_pad:
            block_r = self._piece_screen_radius()
            # 让位 = 块半径（贴到切片外沿）+ 半个按键 + 一点呼吸空隙
            pad = block_r + size / 2.0 + max(4.0, block_r * 0.10)
            # 出屏收缩：斜方向一格很长，标准让位可能把按键推出画面（实测米字
            # 3×3 对角族右下端 y=880 而屏高 620）。逐步缩短让位，最低贴到
            # 「切片外沿 + 半个按键」，保证按键可见且仍指向正确的端。

            def _inside(x, y):
                return (m <= x <= self.screen_width - m
                        and m <= y <= self.screen_height - m)

            p = pad
            for _ in range(6):
                a_hi = (hi_pt[0] + ux * p, hi_pt[1] + uy * p)
                a_lo = (lo_pt[0] - ux * p, lo_pt[1] - uy * p)
                if _inside(*a_hi) and _inside(*a_lo):
                    break
                p *= 0.65
            pad = max(p, size / 2.0 + 4.0)
        else:
            pad = 0.0      # 鼠标锚点：按键就摆在点的地方，不再额外让位

        ends = [(dirs[0], (hi_pt[0] + ux * pad, hi_pt[1] + uy * pad), (ux, uy)),
                (dirs[1], (lo_pt[0] - ux * pad, lo_pt[1] - uy * pad), (-ux, -uy))]
        buttons = []
        for d, (ax, ay), (vx, vy) in ends:
            # 锚点跑出画面时夹回视区：「看得见」比「准而看不见」有用
            ax = min(max(ax, m), self.screen_width - m)
            ay = min(max(ay, m), self.screen_height - m)
            movable = bool(allowed.get(d, False))
            buttons.append((d, (ax, ay), math.degrees(math.atan2(-vy, vx)), movable))
            if not movable:
                continue        # 禁用态不画 → 也不该被点中（画与命中同一套几何）
            # 命中区取按键自身的正方形，不用旋转后的外接矩形 —— 后者更大，
            # 会让相邻方向的按键互相吃掉点击
            self._arrow_buttons.append(
                (d, pygame.Rect(int(ax - size / 2), int(ay - size / 2), size, size)))
        return {'buttons': buttons, 'size': size}

    def _draw_gap_direction_annotation(self):
        """S1-4：切片两端各画一个可点的箭头按键。**在滑块绘制之后**调用。

        禁用态（该方向走不动）按约定**直接不画**：不留灰叉、不留禁用贴图。
        """
        annot = self._get_gap_direction_annotation()
        if not annot:
            return
        for _d, (cx, cy), ang, movable in annot['buttons']:
            if not movable:
                continue
            spr = self._arrow_sprite(ang)
            if spr is None:
                continue
            self.screen.blit(spr, spr.get_rect(center=(int(cx), int(cy))))

    def _arrow_button_hit(self, x, y):
        """点在某端的箭头按键上？返回该端方向字母，否则 None。

        命中优先于选缝（events 里先问它），否则按键会被「点空白起拖」吃掉。
        矩形来自上一帧绘制，一帧延迟在 60fps 下不可感知。
        """
        for d, rect in getattr(self, '_arrow_buttons', ()):
            if rect.collidepoint(x, y):
                return d
        return None

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
                           (i == 3 and self.show_macro_menu)
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
        # 动态宽度：以最长文本为基准（左留白 12 + 右侧 ✓ 标记 16 + 右留白 12），
        # 避免「快速开始：矩形 6×6 等级2」这类长条目文字超出外框
        menu_width = 200
        for p in self.puzzle_presets:
            if len(p) == 1 and p[0] == '---':
                continue
            if len(p) == 1 and p[0] == '__current__':
                w = self.status_font.size('当前：' + self._current_puzzle_label())[0]
            else:
                w = self.menu_font.size(p[0])[0]
            menu_width = max(menu_width, w + 40)

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

            # 可展开的二级子菜单项：名字 + ▸ 箭头；悬停或展开时高亮，展开时绘制子菜单
            if len(preset) == 3 and preset[1] == '__sub__':
                sub_open = (self.puzzle_sub_open == preset[2])
                if i == self.puzzle_menu_hovered or sub_open:
                    pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

                text_surface = self.menu_font.render(preset[0], True, self.colors['menu_text'])
                text_rect = text_surface.get_rect()
                text_rect.x = menu_x + 12
                text_rect.centery = center_y
                self.screen.blit(text_surface, text_rect)

                arrow_surface = self.menu_font.render('▸', True, self.colors['menu_text'])
                arrow_rect = arrow_surface.get_rect()
                arrow_rect.right = menu_x + menu_width - 10
                arrow_rect.centery = center_y
                self.screen.blit(arrow_surface, arrow_rect)

                if sub_open:
                    self.draw_puzzle_sub_menu(preset[2], menu_x + menu_width + 2)
                continue

            if i == self.puzzle_menu_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            is_current = self._preset_is_current(preset, current_key)

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

    def draw_puzzle_sub_menu(self, subkey, sub_x):
        """绘制谜题二级子菜单（画在一级项右侧）。

        条目格式与一级 preset 相同（分组标题/分隔线/谜题档位），
        「当前✓」用同一套 _preset_puzzle_key 比对。
        """
        items = self.puzzle_sub_presets[subkey]
        item_height = 26
        # 动态宽度：组标题（如「米字格谜题（最难，奇偶等级难度有波动）」）较长，
        # 以最长文本为基准，避免文字超出外框
        menu_width = 230
        for p in items:
            if len(p) == 1 and p[0] == '---':
                continue
            name = p[1] if len(p) == 2 and p[0] == '__group__' else p[0]
            w = self.menu_font.size(name)[0]
            menu_width = max(menu_width, w + 40)
        menu_x = sub_x
        menu_y = self.menu_bar_height
        menu_height = item_height * len(items)

        dropdown_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['menu_bg'], dropdown_rect)
        pygame.draw.rect(self.screen, self.colors['border'], dropdown_rect, 1)

        self.puzzle_sub_rects = []
        current_key = self._current_puzzle_key()
        for i, preset in enumerate(items):
            y_pos = menu_y + i * item_height
            item_rect = pygame.Rect(menu_x, y_pos, menu_width, item_height)
            self.puzzle_sub_rects.append(item_rect)
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

            if i == self.puzzle_sub_hovered:
                pygame.draw.rect(self.screen, self.colors['menu_hover'], item_rect)

            is_current = self._preset_is_current(preset, current_key)

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

        # 左侧：当前逻辑引擎（几何引擎开关的状态指示，见 engine/config.py）
        # 常显而非只在几何态显示——玩家随时能确认自己跑的是哪一套。
        engine_text = f"引擎：{self.engine_label()}"
        engine_on = (self.engine_label() == '几何')
        engine_color = (120, 220, 200) if engine_on else self.colors['status_text']
        engine_surface = self.status_font.render(engine_text, True, engine_color)
        engine_x = timer_x + timer_surface.get_width() + 30
        self.screen.blit(engine_surface, (engine_x, text_y))

        # 计时区可点：竞速模式下「开始计时 / 放弃(DNF)」原本只有空格能按，
        # 这里补一个纯鼠标入口（画细框提示这里能点）。控制设计原则：只用
        # 鼠标也要能完成一切游戏内操作。
        self._timer_bar_rect = None
        if self.game_mode == 'timed' and self.timer_state in ('ready', 'running'):
            _pad = 6
            self._timer_bar_rect = pygame.Rect(timer_x - _pad, status_y + 3,
                                               timer_surface.get_width() + _pad * 2,
                                               self.status_bar_height - 6)
            pygame.draw.rect(self.screen, (110, 110, 110), self._timer_bar_rect,
                             1, border_radius=3)

        # 中间：当前谜题信息。样式局就用样式标题占这个位置——它不是一个
        # 官方档位，写「谜题：1~3*3」会让这局看起来是预设谜题；样式名本身
        # 已经是「在玩什么」最准确的答案，所以不再另起一截「目标：样式…」。
        style_goal = getattr(self, '_ann_style_goal', None)
        if style_goal:
            puzzle_text = f'样式：{style_goal}'
            puzzle_color = (255, 210, 120)
        else:
            # 带形态后缀：带序号 #num / 三角形 tri{k} / 米字格 mi{m}*{n}
            puzzle_text = f"谜题：{self._current_puzzle_key()}"
            puzzle_color = self.colors['status_text']
        puzzle_surface = self.status_font.render(puzzle_text, True, puzzle_color)
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

        # 视觉 Tab（新顺序第 3 位：动效 + 缩放 + 各类视觉提示）
        # 2026-10-13 由「动画速度」改名：本页早已不只是动画速度——缩放、
        # 着色、连锁提示、复原提示标记、调试面板都归它管。
        tab_anim_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 2, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'animation':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_anim_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_anim_rect, border_radius=4)
        tab_anim_text = self.status_font.render("视觉", True, self.colors['input_text'])
        tab_anim_text_rect = tab_anim_text.get_rect(center=tab_anim_rect.center)
        self.screen.blit(tab_anim_text, tab_anim_text_rect)

        # 求解器 Tab（新顺序第 3 位，与「聚拢参数」相邻）
        tab_solver_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 3, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'solver':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_solver_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_solver_rect, border_radius=4)
        tab_solver_text = self.status_font.render("求解器", True, self.colors['input_text'])
        tab_solver_text_rect = tab_solver_text.get_rect(center=tab_solver_rect.center)
        self.screen.blit(tab_solver_text, tab_solver_text_rect)

        # 聚拢参数 Tab（新顺序第 4 位，紧随「求解器」）
        tab_gather_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 4, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'gather':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_gather_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_gather_rect, border_radius=4)
        tab_gather_text = self.status_font.render("聚拢参数", True, self.colors['input_text'])
        tab_gather_text_rect = tab_gather_text.get_rect(center=tab_gather_rect.center)
        self.screen.blit(tab_gather_text, tab_gather_text_rect)

        # 文件/存档 Tab（新顺序第 5 位，置末）
        tab_file_rect = pygame.Rect(dialog_x + 15 + (tab_width + 5) * 5, tab_y, tab_width, tab_height)
        if self.settings_active_tab == 'file':
            pygame.draw.rect(self.screen, self.colors['button_bg'], tab_file_rect, border_radius=4)
        else:
            pygame.draw.rect(self.screen, self.colors['input_bg'], tab_file_rect, border_radius=4)
        tab_file_text = self.status_font.render("文件", True, self.colors['input_text'])
        tab_file_text_rect = tab_file_text.get_rect(center=tab_file_rect.center)
        self.screen.blit(tab_file_text, tab_file_text_rect)

        # 控制 Tab（新顺序第 1 位，紧随「快捷键」，同属操作类）
        tab_control_rect = pygame.Rect(dialog_x + 15 + tab_width + 5, tab_y, tab_width, tab_height)
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
        content_height = dialog_height - (content_y - dialog_y) - 64

        # 计算总内容高度以决定是否需要滚动条
        total_content_height = self._calc_settings_content_height(content_height)
        # 滚动条（与帮助框同源）：每帧依内容高度重算
        sb = self.settings_scrollbar
        sb.layout(dialog_x + dialog_width - 18, content_y, content_height,
                  total_content_height, content_height)
        # 控制页刚弹出内联反馈（复制结果等）→ 自动滚到底：反馈行是新长出来
        # 的内容，不pin底就会落在裁剪区外，玩家依旧「看不到反应」
        if getattr(self, '_settings_ext_pin_bottom', False):
            self._settings_ext_pin_bottom = False
            sb.set_scroll(10**9)  # set_scroll 内部夹紧到最大滚动量
        scroll = sb.scroll

        # 内容区域裁剪
        content_rect = pygame.Rect(dialog_x + 5, content_y, dialog_width - 20, content_height)
        self.screen.set_clip(content_rect)
        try:
            if self.settings_active_tab == 'keybindings':
                self._draw_settings_keybindings(dialog_x, content_y - scroll, dialog_width - 30, total_content_height if sb.need_scroll() else content_height)
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

        # 绘制滚动条（仅当内容超出可见区域）
        if sb.need_scroll():
            sb.draw(self.screen)

        # 底部按钮带分隔线（明确把内容与按钮区分开，避免视觉/命中重叠）
        divider_y = dialog_y + dialog_height - 48 - 14
        pygame.draw.line(self.screen, self.colors['dialog_border'],
                         (dialog_x + 15, divider_y),
                         (dialog_x + dialog_width - 15, divider_y))

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
        # 板型門（Port 1）：連鎖提示的「類」是對方/三角/米字三個形態分別
        # 寫的（鍵結構與朝向語義各不同），其它板型沒有對應定義。帶朝向的
        # 新板型（碎三角等）若落進下面的方形分支，hint_empty 會产出 2-tuple
        # 位置，通用通道拿它問 cell_polygon(point, '') 直接 KeyError
        # （_LOCAL_POLY['']）——明說不支援，不靜默算無意義高亮。
        # 判據與 _generic_spec 同源；spec 為 None（舊引擎遊戲）不觸發。
        _spec = self._generic_spec()
        if _spec is not None and getattr(_spec, 'name', '') not in (
                'square', 'tri', 'mi'):
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

    def _draw_switch_row(self, x, y, label, on, hint=None, btn_w=64, btn_h=28, on_text='ON', off_text='OFF'):
        """统一排版的开关行：左栏标签(x+15) + 右栏开关(x+220) + 可选说明。
        返回 (开关rect, 下一行y)。所有设置页开关共用，保证对齐。
        on_text/off_text 允许自定义开关文字（如界面模式的 增强/朴素）。"""
        label_s = self.dialog_font.render(label, True, self.colors['dialog_text'])
        self.screen.blit(label_s, (x + 15, y + 6))

        rect = pygame.Rect(x + 220, y + 2, btn_w, btn_h)
        if on:
            bg, txt, tc = self.colors['button_bg'], on_text, (255, 255, 255)
        else:
            bg, txt, tc = self.colors['input_bg'], off_text, (150, 150, 150)
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
        # 界面模式总开关（朴素 / 增强）—— S0-0 新增
        self._settings_ui_mode_rect, ny = self._draw_switch_row(
            x, y, "界面模式：", self.ui_mode == 'enhanced',
            "增强=新版动效与视觉优化；朴素=旧版界面（等同未启用本计划）",
            on_text='增强', off_text='朴素')

        # 滑动动画开关
        self._settings_anim_toggle_rect, ny = self._draw_switch_row(
            x, ny, "滑动动画：", self.animation_enabled,
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

        # 缩放滑动条（与右侧面板的垂直缩放滑条同源：两者读写同一个
        # self.zoom，改任意一个另一个下一帧就跟着动）。排版与上面的动画
        # 时长一致：左栏标签、右栏轨道，左端=最小缩放、右端=最大缩放。
        zoom_y = ny
        zoom_label = self.dialog_font.render("缩放：", True, self.colors['dialog_text'])
        self.screen.blit(zoom_label, (x + 15, zoom_y + 6))

        ztrack_x = x + 220
        ztrack_width = 190
        zoom_pct = f"{int(round(self.zoom * 100))}%"
        zvalue_surface = self.input_font.render(zoom_pct, True, self.colors['input_text'])
        self.screen.blit(zvalue_surface,
                         (ztrack_x + ztrack_width - zvalue_surface.get_width(), zoom_y + 6))

        # 滑动条轨道
        ztrack_y = zoom_y + 26
        self._settings_zoom_track_rect = pygame.Rect(ztrack_x, ztrack_y, ztrack_width, 4)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], self._settings_zoom_track_rect)

        # 滑动条位置（线性：min_zoom→0，max_zoom→1）
        znorm = (self.zoom - self.min_zoom) / max(1e-6, self.max_zoom - self.min_zoom)
        znorm = max(0.0, min(1.0, znorm))
        zknob_x = int(ztrack_x + znorm * ztrack_width)
        self._settings_zoom_knob_rect = pygame.Rect(zknob_x - 8, ztrack_y - 6, 16, 16)

        zknob_color = self.colors['button_hover'] if getattr(self, '_settings_zoom_dragging', False) else self.colors['button_bg']
        pygame.draw.rect(self.screen, zknob_color, self._settings_zoom_knob_rect, border_radius=8)

        # 刻度标签（两端对齐轨道）
        zmin_label = self.status_font.render(f"{int(round(self.min_zoom * 100))}%", True, (150, 150, 150))
        zmax_label = self.status_font.render(f"{int(round(self.max_zoom * 100))}%", True, (150, 150, 150))
        self.screen.blit(zmin_label, (ztrack_x, ztrack_y + 12))
        self.screen.blit(zmax_label, (ztrack_x + ztrack_width - zmax_label.get_width(), ztrack_y + 12))
        ny = zoom_y + 72

        # 分组着色器开关
        self._settings_coloring_toggle_rect, ny = self._draw_switch_row(
            x, ny, "分组着色：", getattr(self, 'coloring_enabled', False),
            "按移动不变量分组着色（同组颜色的滑块才可能互换位置）")

        # 悬停连锁提示开关（独立于着色器）
        self._settings_chain_toggle_rect, ny = self._draw_switch_row(
            x, ny, "悬停连锁提示：", getattr(self, 'chain_hint_enabled', False),
            "悬停滑块时，边界盒内同组位置（含空格）提亮提示，帮助找缺口")

        # 复原提示标记：调试面板画在棋盘上的那些记号（目标框 / 洞位等）。
        # 它们是视觉强化而非调试数据，故与面板本体拆成两个开关：可以只关
        # 画面上的记号、留着面板看数字，也可以整块面板一起关掉。
        # 2026-10-13 由「棋盘标记」改名「复原提示标记」——它提示的是
        # 「往哪走能复原」，不是泛泛的棋盘装饰。
        self._settings_marks_toggle_rect, ny = self._draw_switch_row(
            x, ny, "复原提示标记：", getattr(self, 'board_marks_enabled', False),
            "棋盘上提示复原方向的记号（目标框 / 洞位），可脱离调试面板单独开（F2 亦可开关）")

        # 调试面板本体：让 F2 的功能也有纯鼠标入口（面板自身的关闭按钮
        # 只能关、不能开）
        self._settings_metrics_toggle_rect, ny = self._draw_switch_row(
            x, ny, "调试面板：", getattr(self, 'show_metrics_panel', False),
            "右下角的数据面板（聚拢度 / 剖面缺陷等），F2 亦可开关")

        # 记录本页实际绘制高度：_calc_settings_content_height 曾把本页写死
        # 成 340，而真实内容有 660+ → 滚动最大只有 22px，「悬停连锁提示」
        # 的说明与下面的开关行整块落在裁剪区外，玩家根本看不到（2026-10-13
        # 用户实机反馈）。这里每帧记录真实高度，高度计算与绘制永不漂移。
        self._settings_anim_height = ny - y + 10

    def _ext_feedback_lines(self, width: int) -> int:
        """控制页内联反馈当前占几行（高度计算与绘制共用同一算法，避免漂移）。"""
        msg = getattr(self, '_settings_ext_msg', '')
        if not msg or getattr(self, '_settings_ext_msg_timer', 0) <= 0:
            return 0
        n = 0
        for seg in msg.split('\n'):
            n += len(self._wrap_text(seg, self.status_font, width - 30) or [''])
        return min(n, 4)

    def _draw_settings_control(self, x, y, width, height):
        """绘制控制模式设置内容（五种操作方式独立开关，可任意组合）"""
        hint = self.status_font.render(
            "五种操作方式可任意组合（甚至全关）；全关时只能平移/缩放", True, (200, 200, 120))
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
        # 虚拟键盘：F1 唤出的屏上键盘，这里给它一个纯鼠标的开关入口
        # （宣传里的五种操作方式，此前只有热键能开关它）
        self._settings_ctrl_vk_rect, ny = self._draw_switch_row(
            x, ny, "虚拟键盘：", getattr(self, 'show_virtual_keyboard', False),
            "屏幕上的方向键盘（F1 亦可开关）；米字格靠它定方向，默认开着")
        # 箭头按键：选中缝隙后两端的可点方向箭头，原先只跟界面模式走
        self._settings_ctrl_arrow_rect, ny = self._draw_switch_row(
            x, ny, "箭头按键：", getattr(self, 'arrows_enabled', True),
            "选中缝隙后在切片两端显示可点的方向箭头（需增强界面）")
        # 逆序播放宏：不常用，故从右下角常用区撤回设置（右下角留给常用开关）
        self._settings_ctrl_revmacro_rect, ny = self._draw_switch_row(
            x, ny, "逆序播放宏：", getattr(self, 'macro_reverse_mode', False),
            "宏指令倒着播一遍（本人用不上，故不放右下角常用区）")

        # —— 外部控制（本机 HTTP API）——
        # 与五种操作方式分区：那是「人怎么玩」，这是「外部程序怎么接」。
        ny += 8
        pygame.draw.line(self.screen, (90, 90, 95),
                         (x + 15, ny - 4), (x + width - 15, ny - 4))
        self._settings_ext_toggle_rect, ny = self._draw_switch_row(
            x, ny, "允许外部控制：", self.external_enabled(),
            "开启后本机 HTTP 接口可用；外部程序须带令牌请求（令牌只存内存）")
        note = self.status_font.render(
            "令牌进程级随机：游戏重启即失效；关闭立即作废，重开换新", True, (150, 150, 150))
        self.screen.blit(note, (x + 15, ny))
        ny += 22
        # 复制连接话术 / 下载控制教程（并排两按钮）
        # 悬停高亮与底部按钮同源（button_hover）：没有悬停反馈的按钮像死的
        btn_h = 32
        copy_r = pygame.Rect(x + 15, ny, 150, btn_h)
        guide_r = pygame.Rect(x + 175, ny, 170, btn_h)
        mouse_pos = pygame.mouse.get_pos()
        for r, label in ((copy_r, "复制连接话术"), (guide_r, "下载控制教程")):
            hover = r.collidepoint(mouse_pos)
            bg = self.colors['button_hover'] if hover else self.colors['button_bg']
            pygame.draw.rect(self.screen, bg, r, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['dialog_border'], r, 1, border_radius=4)
            ls = self.dialog_font.render(label, True, (255, 255, 255))
            self.screen.blit(ls, ls.get_rect(center=r.center))
        self._settings_ext_copy_rect = copy_r
        self._settings_ext_guide_rect = guide_r
        ny += btn_h + 6

        # —— 内联反馈（复制结果等）——
        # 为什么在对话框内自报：宏通知浮层画在模态之下，设置框开着时toast
        # 不可见——玩家点了没反应，按钮就像死的。反馈必须落在内容区里。
        msg = getattr(self, '_settings_ext_msg', '')
        n_lines = self._ext_feedback_lines(width)
        if msg and n_lines:
            color = (140, 230, 140) if getattr(self, '_settings_ext_msg_ok', True) \
                else (255, 150, 150)
            wrapped = []
            for seg in msg.split('\n'):
                wrapped.extend(self._wrap_text(seg, self.status_font, width - 30) or [''])
            for ln in wrapped[:n_lines]:
                self.screen.blit(self.status_font.render(ln, True, color), (x + 15, ny))
                ny += 18
        self._settings_ext_msg_lines = n_lines

    def _draw_settings_gather(self, x, y, width, height):
        """绘制聚拢参数设置内容（与谜题-自定义一致的输入框样式）"""
        # 顶部警告：不了解参数含义请勿调整
        warn = self.status_font.render("※ 参数含义若不理解请勿调整，以免求解效果变差", True, (220, 200, 80))
        self.screen.blit(warn, (x + 15, y + 8))
        # 适用范围（2026-10-13 用户要求标明）：这些参数是聚拢求解器的专用
        # 参数，只对设置-求解器页的「单次聚拢」生效；梯度聚拢自动预测参数，
        # 混合求解 / 填洞补缺 / 选块填空 / 查表等算法不读它们。
        scope = self.status_font.render(
            "这些参数只给「单次聚拢」用：梯度聚拢自动定参，其余算法不读它们", True, (150, 200, 150))
        self.screen.blit(scope, (x + 15, y + 26))
        row_y = y + 48
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
            # -/+ 按钮（禁用时灰化）。减号必须用 ASCII '-'：U+2212「−」
            # 在游戏字体里没有字形，上屏是方框（与旁边的 ASCII '+' 对称）。
            dec = pygame.Rect(x + 80, row_y, 28, 26)
            inc = pygame.Rect(x + 196, row_y, 28, 26)
            btn_color = self.colors['input_bg'] if enabled else (55, 55, 55)
            pygame.draw.rect(self.screen, btn_color, dec, border_radius=4)
            pygame.draw.rect(self.screen, btn_color, inc, border_radius=4)
            txt_color = (255, 255, 255) if enabled else (90, 90, 90)
            d = self.status_font.render("-", True, txt_color)
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

        from solver import solver_supports

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

            # 算法名：当前谜题形态不支持的**置灰**并标注。
            # 仍允许点选（用户可能先选好、之后切回方形），点击时会明确提示
            # 「当前谜题没有 xxx 求解算法功能」，不会静默换算法。
            supported = solver_supports(algo_key, self._current_puzzle_form())
            name_color = (self.colors['dialog_text'] if supported
                          else (110, 110, 115))
            name_surface = self.dialog_font.render(algo_name, True, name_color)
            self.screen.blit(name_surface, (option_x, row_y + row_height // 2 - name_surface.get_height() // 2))
            if not supported:
                tip = self.status_font.render("（当前谜题不支持）", True,
                                              (110, 110, 115))
                self.screen.blit(tip, (option_x + name_surface.get_width() + 8,
                                       row_y + row_height // 2 - tip.get_height() // 2))

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
            'ida_star': '使用 IDA* 迭代加深搜索，尽量找到最少步数解。速度非常慢。※ 旧搜索类算法，相对现有宏级流水线已低效，沉底仅备查。',
            'fast': 'IDA* 优化模式：加大搜索步进，放宽节点/时间限制，优先聚拢，速度中等。不能保证求解成功。※ 旧搜索类算法，沉底仅备查。',
            'greedy': '贪心爬山法：每步选当前最佳动作，速度中等但不保证最优。不能保证求解成功。※ 旧搜索类算法，沉底仅备查。',
            'table':'根据数据库的数据快速找到最优算法（一般1s内），只对已有数据库的谜题有效。',
            #'intelligence': 'AI求解：基于预训练评分模型，每步自动选最佳动作。需先用 solver.ml.train_ranker 训练模型。',
            #'emd': 'EMD求解：用 EMD 距离贪心搜索，速度快但不保证成功。',
            #'strategy': '策略求解：EMD 贪心 + 循环检测 + 随机扰动，成功率高于纯 EMD。',
            #'distance': '距离求解：用神经网络预测剩余步数做贪心搜索，需先用 solver.ml.train_distance 训练模型。',
            'gather': '单次聚拢（方形 / 三角形 / 米字格通用入口）：只跑一轮聚拢，提升聚拢度，不保证还原，实时显示进展。',
            'gather_gradient': '梯度聚拢：参数自动决定，分阶段放宽参数多轮聚拢，每阶段播放动画后再续。理论上比单次聚拢更高效。',
            # ➜ 填洞宏已并入本项（2026-10-12）：单独跑填洞遇到边缘缺口会全线
            #   失败，而它本来就是这一支遇到多空位时会转去跑的那条路。
            'gap_macro': '填洞补缺：多空位宏级机构（带移让位 + 粘上接走链）。单边缺口走「封壳 + 内部共轭 + 拆壳」；遇到多个空位或封闭孔洞则转去逐个 couple 填洞；最后一律带兜底救援。',
            # 选块填空要先收集玩家点选，所以它多一步交互 —— 说明写在这里，
            # 设置里就能看懂为什么它需要你先点两下。
            'pick_fill': '选块填空：你点一个方块和一个空位（顺序不限），它只把这一块送进那个坑。按一次进入选取态，点齐后按 Ctrl+A 开始，没点齐时再按一次退出。只保证这个空位被填上，不保证整盘还原。',
            'hybrid': '混合求解（自动规划）：有表先查表（最优且亚秒级）；无表按空位数路由——空位≤2 先混合流水线（聚拢+填洞+搜索），空位≥3 先补缺宏（couple→贴边setup→带移让位链）；一路落败另一路接力，补缺宏的部分成果可被混合续算；全败返回聚拢度提升最大的断点。',
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

        # 压缩存档开关（use_compressed_save：矩形谜题保存为 replay 压缩格式）
        cy = og_y + 70
        label4 = self.dialog_font.render("压缩存档：", True, self.colors['dialog_text'])
        self.screen.blit(label4, (x + 15, cy))
        self._settings_compressed_toggle_rect = pygame.Rect(toggle_x, cy, btn_w, btn_h)
        flag4 = getattr(self, 'use_compressed_save', False)
        btn_color = self.colors['button_bg'] if flag4 else self.colors['input_bg']
        btn_text = "ON" if flag4 else "OFF"
        text_color = (255, 255, 255) if flag4 else (150, 150, 150)
        pygame.draw.rect(self.screen, btn_color, self._settings_compressed_toggle_rect, border_radius=4)
        ts4 = self.status_font.render(btn_text, True, text_color)
        self.screen.blit(ts4, ts4.get_rect(center=self._settings_compressed_toggle_rect.center))
        hint = self.status_font.render(
            "打开后，矩形谜题存档改为“重放压缩格式”（初始+末态+步骤原语+哈希校验）", True, (150, 150, 150))
        self.screen.blit(hint, (x + 15, cy + 34))
        hint2 = self.status_font.render(
            "体积大幅缩小；异形谜题不受此开关影响，仍存普通格式", True, (150, 150, 150))
        self.screen.blit(hint2, (x + 15, cy + 54))

        # 当前存档路径
        path_y = cy + 80
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
            # 视觉页：真实绘制高度由 _draw_settings_animation 每帧记录
            # （self._settings_anim_height）——曾因写死 340 把底下好几行
            # 裁死在可见区外。首帧尚未绘制时用同一结构估算兜底：
            # 界面模式/滑动/选中 3 行开关(60) + 速度滑条(72) + 缩放滑条(72)
            # + 着色/连锁/标记/面板 4 行开关(60) + 余量。
            return getattr(self, '_settings_anim_height', 3 * 60 + 72 + 72 + 4 * 60 + 10)
        elif self.settings_active_tab == 'gather':
            # 警告行 + 适用范围行 + 每个参数一行(52) + 余量
            return 26 + 22 + len(self._gather_param_specs) * 52 + 10
        elif self.settings_active_tab == 'file':
            return 420  # 存档只读 + 防止覆盖 + 操作日志 + 压缩存档 + 当前存档路径说明
        elif self.settings_active_tab == 'control':
            # 提示 34 + 六行开关（每行 60）+ 外部控制区（分隔 8 + 开关 60
            # + 说明 22 + 按钮 32 + 内联反馈行（每行 18，无反馈为 0）+ 余量 10）
            # 反馈行数必须**当场按当前消息**算：等下一帧回填会把新行落在裁剪
            # 区外（内容长高但滚动量没跟上），玩家仍看不到反馈。
            # 宽度与 _draw_settings_control 收到的实参一致（对话框定宽 660-30）
            return 34 + 6 * 60 + 8 + 60 + 22 + 32 + 10 \
                + 18 * self._ext_feedback_lines(660 - 30)
        else:
            # solver tab：标题 + 选项 + 说明文字（动态计算，超出时出现滚动条）
            from solver import SOLVER_ALGORITHMS
            title_h = 20 + 36 + 10
            options_h = len(SOLVER_ALGORITHMS) * 36
            desc = self._solver_description(getattr(self, 'solver_algorithm', 'ida_star'))
            desc_w = 500 - 30 - 20  # 内容宽 470 再减边距
            desc_h = len(self._wrap_text(desc, self.status_font, desc_w)) * 18 + 12
            return title_h + options_h + desc_h

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

        # 弹入动画：前若干帧缩放回弹，随后轻微呼吸
        # S0-1：增强模式放大幅度（弹入更久更明显、呼吸更明显），朴素模式保持原设计口径
        _enh = getattr(self, 'ui_mode', 'enhanced') == 'enhanced'
        _in_frames = 18 if _enh else 12   # 增强≈300ms，朴素≈200ms
        _in_start = 0.85 if _enh else 0.70
        _breathe = 0.03 if _enh else 0.012
        p = min(1.0, t / _in_frames)
        ease = 1 - (1 - p) ** 3
        if p < 1:
            scale = _in_start + (1.0 - _in_start) * ease
        else:
            scale = 1.0 + _breathe * math.sin(t / 9.0)
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
        # 增强模式光晕更明显（朴素模式保持原 0.25±0.10）
        _glow_base = 0.45 if getattr(self, 'ui_mode', 'enhanced') == 'enhanced' else 0.25
        _glow_amp = 0.18 if getattr(self, 'ui_mode', 'enhanced') == 'enhanced' else 0.10
        glow_alpha = int(alpha * (_glow_base + _glow_amp * math.sin(t / 7.0)))
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

        # ---- 底部：7 个快捷开关（垂直排列）----
        sw_h = 24
        sw_gap = 4
        sw_count = 7
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

        # 摆放原则（用户定）：右下角只放**游玩中需要经常切换**的开关；
        # 不常改的一律收回设置对话框。逆序宏因此从这里撤回设置。
        _sw_btn('animation_enabled', '滑动动画', lambda: self.animation_enabled)
        _sw_btn('selection_animation_enabled', '选中动画', lambda: self.selection_animation_enabled)
        _sw_btn('coloring_enabled', '着色', lambda: self.coloring_enabled)
        _sw_btn('chain_hint_enabled', '连锁', lambda: self.chain_hint_enabled)
        # 复原提示标记：与连锁同属视觉强化，一局之内会来回切（前期晃眼
        # 不想看、后期要数格子又想看），故放常用区（设置页全名为
        # 「复原提示标记」，2026-10-13 由「棋盘标记」改名）
        _sw_btn('board_marks_enabled', '复原标记', lambda: self.board_marks_enabled)
        _sw_btn('game_mode', '模式', lambda: None)
        # 成绩面板：F3 的功能原先只有键盘能唤出，这里补一个纯鼠标入口，
        # 使三个悬浮面板（F1/F2/F3）都能只用鼠标开关
        _sw_btn('show_records_panel', '成绩', lambda: self.show_records_panel)

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

    def draw_shuffle_fade(self):
        """打乱演示的淡出/淡入全屏蒙层。

        演示只演前几步时，结尾用这块蒙层盖住「棋盘切到打乱终态」的瞬间：
        淡出到全遮 → 换盘（动画状态机在蒙层背后做）→ 淡入。整帧绘制
        最上层调用（与单击涟漪同层，谁后画谁在上，本方法在 flip 前最后
        调用）。蒙层是整屏的、与棋盘形态无关——三形态共用这一块。
        """
        if not getattr(self, '_shuffle_demo_active', False):
            return
        alpha = int(getattr(self, '_shuffle_fade_alpha', 0.0))
        if alpha <= 0:
            return
        veil = pygame.Surface((self.screen_width, self.screen_height),
                              pygame.SRCALPHA)
        veil.fill(self.colors['background'] + (alpha,))
        self.screen.blit(veil, (0, 0))

    def draw_shuffle_progress(self):
        """打乱演示的「打乱中 xx%」进度提示（画在淡出蒙层之上，最上层）。

        形态：屏幕底部居中的一条圆角进度条 + 条上方居中的文字。
        - 播放期：按已演步数/演示总步数推进
        - 淡出期：随蒙层不透明度补足，全遮（切屏）瞬间正好 100%
        - 淡入期：定格 100%，随蒙层一起淡出——切屏那一刻的 100% 有短暂定格
        填充色由主题蓝渐变到完成绿（>=90%），末端带发光头；100% 时文字
        也变绿，强调「满格切屏」。
        """
        if not getattr(self, '_shuffle_demo_active', False):
            return
        progress = min(1.0, max(0.0, getattr(self, '_shuffle_demo_progress', 0.0)))
        # 淡入收尾中（蒙层正在撤）：进度条随蒙层同步淡出，避免突然消失
        veil_alpha = int(getattr(self, '_shuffle_fade_alpha', 0.0))
        if getattr(self, '_shuffle_demo_phase', None) == 'fade_in':
            fade = 1.0 - veil_alpha / 255.0
        else:
            fade = 1.0
        if fade <= 0.01:
            return

        sw, sh = self.screen_width, self.screen_height
        bar_w = min(420, int(sw * 0.5))
        bar_h = 10
        bar_x = (sw - bar_w) // 2
        bar_y = sh - 78
        radius = bar_h // 2

        blue = self.colors['block']            # (60,150,200) 主题蓝
        green = self.colors['solved']          # (0,200,80) 完成绿
        # 90% 起蓝→绿渐变：给「即将完成」一个视觉暗示
        if progress < 0.9:
            fill_rgb = blue
        else:
            t = (progress - 0.9) / 0.1
            fill_rgb = tuple(int(blue[i] + (green[i] - blue[i]) * t) for i in range(3))

        alpha_btn = int(255 * fade)
        track = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        pygame.draw.rect(track, (255, 255, 255, int(38 * fade)), track.get_rect(),
                         border_radius=radius)
        self.screen.blit(track, (bar_x, bar_y))
        if progress > 0:
            fill_w = max(bar_h, int(bar_w * progress))  # 至少一个圆头，0% 也可见起点
            fill = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            pygame.draw.rect(fill, fill_rgb + (alpha_btn,), fill.get_rect(),
                             border_radius=radius)
            # 末端发光头：转场时有「能量充满」的感觉
            glow = pygame.Surface((bar_h + 8, bar_h + 8), pygame.SRCALPHA)
            pygame.draw.circle(glow, fill_rgb + (alpha_btn,),
                               ((bar_h + 8) // 2, (bar_h + 8) // 2), bar_h // 2 + 3)
            self.screen.blit(fill, (bar_x, bar_y))
            self.screen.blit(glow, (bar_x + fill_w - (bar_h + 8) // 2,
                                    bar_y - 4))

        # 文字：「打乱中 xx%」；:>3d 让位数变化时宽度稳定（不抖）；
        # 100% 时文字变绿，与填充末端同色，强调「满格切屏」
        pct = int(progress * 100)
        done = (progress >= 1.0)
        text_rgb = green if done else (235, 240, 245)
        label = self.status_font.render(f'打乱中 {pct:>3d}%', True, text_rgb)
        label.set_alpha(alpha_btn)
        lw, lh = label.get_size()
        self.screen.blit(label, ((sw - lw) // 2, bar_y - lh - 10))
