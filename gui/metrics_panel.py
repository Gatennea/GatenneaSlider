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

# 三角形调试记号半径 / cell_size。方形用 0.35；三角单元是等边三角形、
# 面积只有方形的 0.433 倍。用户在 2026-10-03 两次验收里都嫌大 —— 按面积
# 占比对齐（0.230）之后仍偏大，说明参照的是「屏幕上的视觉大小」而非面积
# 比例，再收一档到 0.16（约为方形 0.35 的 46%）。
_TRI_MARK_RADIUS_RATIO = 0.16

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

    def _mp_panel_size(self, n_rows=None):
        """计算面板宽高。

        `n_rows` 是指标行数；不给就按 6 行算（方形/三角的既有行数）。
        **mi 分支有 7 行**（多一行「mod 约束」，报 |S(step)| 而不是
        「有无约束」——倍数控法在 mi 上是错的，见 `experiments/_mi_mod_probe.py`），
        高度写死 6 行会把最后一行画到面板外面去（截图里表现为「mod 约束」
        那行被截断）。所以这里按调用方给的行数动态算，别再写死。
        """
        if n_rows is None:
            n_rows = 6
        height = (self._MP_TITLE_H + self._MP_PAD * 2 + self._MP_ROW_H * n_rows)
        return self._MP_WIDTH, height

    def _mp_build_layout(self, n_rows=None):
        """根据当前 mp_pos 计算面板矩形。"""
        x, y = self.mp_pos
        width, height = self._mp_panel_size(n_rows)
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
        w, h = self._mp_panel_size(self._mp_row_count())
        self.mp_pos[0] = max(0, min(self.mp_pos[0], self.screen_width - w))
        self.mp_pos[1] = max(self.menu_bar_height,
                             min(self.mp_pos[1], self.screen_height - self.status_bar_height - h))

    def _mp_current_metrics(self):
        """实时计算当前游戏状态的聚拢度指标。"""
        from solver.ml.gather_solver import gather_metrics
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return {'score': 0.0, 'overlap': 0, 'bbox': (0, 0), 'fill_rate': 0.0}
        if self._mp_kind() not in self._MP_SUPPORTED:
            # 未实装形态：返回 None 表示「算不出」，调用方据此走占位行。
            # **不要在这里退回方形公式** —— mi 的单元是 1/4 格直角三角形，
            # 用矩形的 m×n 窗口枚举会得到 0.0%/无意义数字，界面看起来
            # 「数据正常」实际全错，比明说「不支持」糟得多。
            return None
        if getattr(self, 'triangle_mode', False):
            # 三角走 tri_placement：目标形状是大三角、1 个朝向 × 全部平移，
            # 指标口径与方形对齐（score = 重叠 / 单元数）。
            from solver.ml.tri_placement import best_placement_of_game
            best = best_placement_of_game(
                game, k=getattr(game, 'k', None),
                step=getattr(self, 'current_step', 1))
            coords = best.coords
            rs = [c[0] for c in coords]
            cs = [c[1] for c in coords]
            return {'score': best.score,
                    'overlap': best.overlap,
                    'bbox': (max(rs) - min(rs) + 1 if rs else 0,
                             max(cs) - min(cs) + 1 if cs else 0),
                    'fill_rate': (best.overlap / (best.k * best.k)
                                  if best.k else 0.0)}
        if getattr(self, 'mi_mode', False):
            # 米字格走 mi_placement：目标是 m×n 棋盘轮廓、4mn 个四分之一格
            # 单元、两个形状枚举（m×n 与 n×m，計劃 §6 拍板），指标口径与前
            # 两形态对齐（score = 重叠 / 单元数 = best.score）。
            #
            # **必须调 best_placement_of_game 而不是自己套方形 find_best_window**：
            # mi 单元是 (r, c, q) 三元组且 r/c 可为半整数，方形公式拿不到 q
            # 维度、也不认半格偏移，算出来的是无意义数字。計劃 §4 铁律：面板
            # 与求解器共用同一份 best_placement。
            from solver.ml.mi_placement import best_placement_of_game
            best = best_placement_of_game(
                game, m=getattr(game, 'm', None), n=getattr(game, 'n', None),
                step=getattr(self, 'current_step', 1))
            rs = [c[0] for c in best.coords]
            cs = [c[1] for c in best.coords]
            return {'score': best.score,
                    'overlap': best.overlap,
                    # mi 的 bbox 用**几何格**跨度（r/c 可半整数 → 跨度 ×2 取整
                    # 会误报，这里只给整数格数，供面板显示用）
                    'bbox': (int(max(rs) - min(rs)) + 1 if rs else 0,
                             int(max(cs) - min(cs)) + 1 if cs else 0),
                    'fill_rate': (best.overlap / best.total) if best.total else 0.0}
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

        **三角形走另一條路**（2026-10-03）：返回 `TriPlacement` 本身。形狀
        不對稱（計劃 §5：大三角只有恆等與轉置兩個對稱、**沒有 120° 旋轉**），
        用 (r0, c0, (rh, cw)) 這種矩形三元組表達不了，所以直接攜帶形狀本身。
        **米字格同樣返回 `MiPlacement`**（2026-10-03，M3）：理由與三角不同 ——
        mi 的目標形狀**是** m×n 矩形輪廓（能表達成矩形），但它的單元是
        `(r, c, q)` 三元組且 r/c 可為半整數，矩形三元組裝不下（沒有 q 維度，
        整數行列也表達不了半格偏移）。所以三形态里只有方形走矩形三元组。
        方形分支不變。
        """
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return None
        step = getattr(self, 'current_step', 1)
        if getattr(self, 'triangle_mode', False):
            from solver.ml.tri_placement import best_placement_of_game
            best = best_placement_of_game(
                game, k=getattr(game, 'k', None), step=step)
            self._target_region = best
            return best
        if getattr(self, 'mi_mode', False):
            from solver.ml.mi_placement import best_placement_of_game
            best = best_placement_of_game(
                game, m=getattr(game, 'm', None), n=getattr(game, 'n', None),
                step=step)
            self._target_region = best
            return best
        from solver.ml.gather_solver import find_best_window, _game_coords
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
        if self._mp_kind() not in self._MP_SUPPORTED:
            return None
        if getattr(self, 'triangle_mode', False):
            return self._draw_tri_marks()
        if getattr(self, 'mi_mode', False):
            # 米字格不画洞/缺口/凸起标记（用户 2026-10-05 决定：标记太乱，
            # 只保留目标框）。检测逻辑仍供提示面板文字使用，这里只跳过绘制。
            return None
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

        scaled_cell, scaled_gap, cell_step = self._board_px()   # 与主棋盘同一套整数像素
        cam_x = int(round(self.camera_x))
        cam_y = int(round(self.camera_y))
        half = scaled_cell / 2
        radius = max(3, int(scaled_cell * 0.35))
        line_w = max(2, int(2 * self.zoom))

        def _cell_center(r, c):
            return (c * cell_step + cam_x + half,
                    r * cell_step + cam_y + half)

        # 目標窗口內的空位：孔洞→圓圈、缺口→三角形
        for h in holes:
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

        # 目標窗口外的方塊（凸起）→ 斜方形
        for r, c in protrusions:
            cx, cy = _cell_center(r, c)
            d = radius
            pts = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
            pygame.draw.polygon(self.screen, (255, 210, 60), pts, line_w)

    # 形态支持表：哪些形态有「目标框 + 洞/凸起记号」的实现。
    # 三个形态都已实装（方/角 M0，mi M3 2026-10-03）。留这张表的意义是
    # **将来加第四种形态时的显式挂载点** —— 未列进来的形态一律给「本形态
    # 尚未实装」文案，绝不落进方形分支用矩形公式在斜坐标上算出无意义的
    # 0.0%（面板看起来「开着但什么都不画」，静默无输出比明说不支持差得多）。
    _MP_SUPPORTED = ('square', 'triangle', 'mi')

    def _mp_kind(self):
        """当前棋形标识：'square' / 'triangle' / 'mi' / 其它。"""
        if getattr(self, 'triangle_mode', False):
            return 'triangle'
        if getattr(self, 'mi_mode', False):
            return 'mi'
        return 'square'

    def _mp_unsupported_rows(self):
        """未支持形态的占位行——说清「为什么没有」和「什么时候有」。"""
        k = self._mp_kind()
        if k == 'mi':
            # mi 已实装（M3 F2），走到这里说明 mi_mode 标志与实际棋盘不一致，
            # 说清是哪一层的判断，别让用户以为「面板没实装」。
            return [
                ("形态", "米字格（mi）"),
                ("调试面板", "已实装，但未识别到 mi 棋盘"),
            ]
        return [
            ("形态", k or "未知"),
            ("调试面板", "本形态尚未实装"),
        ]

    def _draw_target_window(self):
        """繪製目標窗口預告框（無填充、綠色邊框）。

        窗口位置由 _compute_target_region 計算（mod 約束 + 聚攏度最高），
        與 _draw_debug_holes 共用同一 region，保證標記系統與畫框一致。
        """
        if self._mp_kind() not in self._MP_SUPPORTED:
            return None
        if getattr(self, 'triangle_mode', False):
            return self._draw_tri_target_frame()
        if getattr(self, 'mi_mode', False):
            return self._draw_mi_target_frame()
        region = self._compute_target_region()
        if region is None:
            return None
        r0, c0, (rh, cw) = region

        board_x = getattr(self, '_board_x', 0)
        board_y = getattr(self, '_board_y', 0)
        scaled_cell, scaled_gap, cell_step = self._board_px()   # 与主棋盘同一套整数像素
        cam_x = int(round(self.camera_x))
        cam_y = int(round(self.camera_y))
        x = board_x + c0 * cell_step + cam_x
        y = board_y + r0 * cell_step + cam_y
        w = cw * cell_step - scaled_gap
        h = rh * cell_step - scaled_gap
        pygame.draw.rect(self.screen, (80, 220, 100),
                         (int(x), int(y), int(w), int(h)),
                         max(2, int(2 * self.zoom)))
        return region

    # ------------------------------------------------------------------
    # 三角形分支（M0 F2，计划 §4/§5）
    #
    # 与方形分支的**纪律完全一致**：目标框与洞/缺口/凸起标记都吃
    # `_compute_target_region()` 的同一个返回值（三角下是 `TriPlacement`），
    # 绝不各算一份。数据源 = solver/ml/tri_placement.py 与 tri_holes.py，
    # 与 M1 求解器将要用的完全是同一套。
    # ------------------------------------------------------------------
    def _draw_tri_target_frame(self):
        """三角：綠色框畫出最佳放置的大三角輪廓。

        不能畫矩形——大三角是**斜邊**形狀（計劃 §5：沒有 120° 旋轉對稱），
        這正是三角不能套方形那套 (r0,c0,rh,cw) 表達的根本原因。所以直接用
        視圖的 `boundary_edges()` 取目標形狀的外周單位邊，逐條畫。
        """
        best = self._compute_target_region()
        if best is None:
            return None
        view = self._tri_view()
        # 線寬與記號線寬同檔（記號縮小後仍用 2·zoom 會顯得過重）
        line_w = max(1, int(self.zoom * 0.6))   # 记号小了，线也要跟着收
        # world_to_screen 已经含 zoom 与相机平移（GUI.py:1154），**不要再乘
        # 一次 zoom**——我第一版多乘了导致框飞到屏幕外只剩两条边。
        # 三角块绘制走的是 view.piece_polygon + world_to_screen，同一条路。
        for p1w, p2w in view.boundary_edges(best.cells):
            pygame.draw.line(self.screen, (80, 220, 100),
                             self.world_to_screen(*p1w),
                             self.world_to_screen(*p2w), line_w)
        return best

    def _draw_tri_marks(self):
        """三角：洞（圓圈）/ 缺口（三角形）/ 凸起（菱形）標記。

        與方形 `_draw_debug_holes` 的記號語義一致（計劃 §4 說「異形版語義
        在實現時定」→ 定為沿用方形，便於對照驗收）。
        """
        from solver.ml.tri_holes import detect_tri_holes, hole_color
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return
        best = getattr(self, '_target_region', None)
        if best is None or not hasattr(best, 'cells'):
            best = self._compute_target_region()
        if best is None or not hasattr(best, 'cells'):
            return

        coords = frozenset(tuple(b.location) for b in game.blocks)
        step_len = getattr(self, 'current_step', 1)
        holes, protrusions = detect_tri_holes(coords, best.cells, step_len)

        view = self._tri_view()
        scaled_cell = self.cell_size * self.zoom
        # 標記尺寸與方形「視覺一致」（用戶 2026-10-03 驗收：標記太大）。
        # 方形單元外接盒 = cell_size 方形，半徑 0.35·cell → 面積佔格 38.5%。
        # 三角單元是等邊三角形，面積只有方形的 0.433 倍；按**面積佔比**與
        # 方形對齊（否則記號相對大 1.5 倍）→ r = 0.230·cell。線寬也同步
        # 收窄一檔，否則小記號配上粗線會糊成一團。
        radius = max(2, int(scaled_cell * _TRI_MARK_RADIUS_RATIO))
        line_w = max(1, int(self.zoom * 0.6))   # 记号小了，线也要跟着收

        def _center(i, j, up):
            """單元重心 → 屏幕坐標。与块的绘制同一条路（piece_center +
            world_to_screen），world_to_screen 已含 zoom 与相机。"""
            return self.world_to_screen(*view.piece_center(i, j, up))

        for h in holes:
            color = hole_color(h)
            for (i, j, up) in h['cells']:
                cx, cy = _center(i, j, up)
                if h['type'] == 'hole':
                    pygame.draw.circle(self.screen, color, (int(cx), int(cy)),
                                       radius, line_w)
                else:  # gap → 三角形
                    pygame.draw.polygon(
                        self.screen, color,
                        [(cx, cy - radius),
                         (cx - radius, cy + radius),
                         (cx + radius, cy + radius)], line_w)

        for (i, j, up) in protrusions:
            cx, cy = _center(i, j, up)
            d = radius
            pygame.draw.polygon(
                self.screen, (255, 210, 60),
                [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)],
                line_w)

    # ------------------------------------------------------------------
    # 米字格分支（M3 F2，計劃 §4/§6）
    #
    # 与前两个分支的**纪律完全一致**：目标框与洞/缺口/凸起标记都吃
    # `_compute_target_region()` 的同一个返回值（mi 下是 `MiPlacement`），
    # 绝不各算一份。数据源 = solver/ml/mi_placement.py 与 mi_holes.py，
    # 与 M1 求解器用的完全是同一套。
    # ------------------------------------------------------------------
    def _mi_goal_bbox(self, goal_cells):
        """目標單元集 → 世界座標外接框 (x, y, w, h)。

        **不從 offset/m/n 反算範圍**，而是直接取 `best.cells` 的 r/c 極值：
        mi 的偏移允許半整數（錯位態 `(r,c)` 是 .5 結尾），任何「整格口徑」
        的反算都會在錯位態下差半格 → 框畫歪。單元集是唯一真源。
        單元是 (r, c, q)，q 只決定三角形朝向、**不影響外接範圍**（四片
        覆蓋整格），所以只取 r/c。
        """
        rs = [c[0] for c in goal_cells]
        cs = [c[1] for c in goal_cells]
        if not rs:
            return None
        r0, r1 = min(rs), max(rs)
        c0, c1 = min(cs), max(cs)
        return r0, c0, (r1 - r0 + 1.0), (c1 - c0 + 1.0)

    def _draw_mi_target_frame(self):
        """米字格：綠色框畫出最佳放置的 m×n 目標輪廓外接矩形。

        mi 的目標形狀**是** m×n 的棋盤輪廓（矩形），所以這裡能畫矩形 ——
        與三角相反（三角是斜邊大三角，只能逐邊畫）。但**偏移可半整數**，
        所以範圍一律從 `best.cells` 取極值，不用 (r0+c0, m, n) 反算。
        """
        best = self._compute_target_region()
        if best is None:
            return None
        bb = self._mi_goal_bbox(best.cells)
        if bb is None:
            return None
        r0, c0, height, width = bb
        view = self._mi_view()
        # 格單位 → 世界像素（to_world）→ 屏幕（world_to_screen）。
        # **不要再乘一次 zoom**（三角那邊第一版就栽在這裡，框飛到屏外）。
        #
        # 兩層必須分開調：`to_world` 回傳 (x, y) 像素對，要用 `*` 拆開餵給
        # `world_to_screen(x, y)`；直接把整個元組塞進去當單一參數會報
        # `missing 1 required positional argument`（我第一版就這麼寫錯）。
        wx0, wy0 = view.to_world(c0, r0)
        wx1, wy1 = view.to_world(c0 + width, r0 + height)
        x0, y0 = self.world_to_screen(wx0, wy0)
        x1, y1 = self.world_to_screen(wx1, wy1)
        line_w = max(1, int(self.zoom * 0.6))
        pygame.draw.rect(self.screen, (80, 220, 100),
                         (int(min(x0, x1)), int(min(y0, y1)),
                          int(abs(x1 - x0)), int(abs(y1 - y0))),
                         line_w)
        return best

    def get_hole_at_pos(self, screen_x, screen_y):
        """返回屏幕坐标处的洞（若点击在洞格子上），否则 None。

        **纯几何查询，不承载任何「选中」状态** —— 选块填空（GUI._pick_fill）
        点选空位的那一步用它；调试面板自带的「点洞选中 + 记录样本」能力已于
        2026-10-12 按用户决定整体删除（由标注模式选空位取代），这里只保留
        几何判定本身，避免同一个命中逻辑出现第二套写法。

        与调试面板使用同一个目标窗口（`_target_region`），确保可点的洞 =
        画出的标记。**只覆盖方形**：唯一使用者选块填空按形态闸门就不支持
        三角/米字/带序号，其它形态直接返回 None，不静默套方形公式。
        """
        game = getattr(self, 'game', None)
        if game is None or not getattr(game, 'blocks', None):
            return None
        if self._mp_kind() != 'square':
            return None
        from solver.ml.hole_detector import detect_holes
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

    def draw_metrics_panel(self):
        """绘制聚拢度指标面板。"""
        if not getattr(self, 'show_metrics_panel', False):
            return
        # S0-2：绘制前先确保面板坐标在可视范围内
        # （修复：非全屏/缩放后记住的偏移坐标越界，面板「开了却看不见」）
        self._mp_clamp_position()

        x, y = self.mp_pos
        # **先算 rows 再定尺寸**：mi 有 7 行（多一行 mod 约束），高度写死
        # 6 行会把最后一行画到面板外面（截图里表现为那行被截断）。
        # 顺序反过来就修不了 —— 背景和 mp_panel_rect 都依赖 rows 的条数。
        rows, met = self._mp_rows()
        width, height = self._mp_panel_size(len(rows))
        self._mp_build_layout(n_rows=len(rows))
        mouse_pos = pygame.mouse.get_pos()

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

        row_y = y + self._MP_TITLE_H + self._MP_PAD
        for label, value in rows:
            label_surf = self.status_font.render(label, True, (170, 170, 180))
            value_surf = self.status_font.render(value, True, (240, 240, 240))
            self.screen.blit(label_surf, (x + self._MP_PAD, row_y))
            self.screen.blit(value_surf, (
                x + width - self._MP_PAD - value_surf.get_width(), row_y
            ))
            row_y += self._MP_ROW_H

    def _mp_reset_target_region(self):
        """清掉缓存的目标窗口（**切换形态/建局时必须调**）。

        `_target_region` 是「当前形态的目标窗口」缓存，但它的类型**随形态
        变**：方形是 `(r0, c0, (rh, cw))` 三元组，三角/mi 是 `TriPlacement` /
        `MiPlacement` 对象。不清就会跨形态串味 ——

        实测（2026-10-04）：mi 局切回方形后，方形分支直接
        `region[0]` 下标访问 → `TypeError: 'MiPlacement' object is not
        subscriptable`。这条在真实使用里必然触发（玩完 mi 换方形）。
        根因是三个建局函数都只调 `center_map()`，没有任何人清这个缓存。

        放在三个建局入口的公共收尾处（`game_history.reset()` 之后），
        一处改动覆盖方形/三角/mi 三条路径。
        """
        self._target_region = None

    def _mp_rows(self):
        """算出面板要显示的指标行 + 指标字典。

        抽成独立方法的理由：**行数会随形态变**（mi 7 行、方形/三角 6 行），
        而面板高度与命中矩形都得按行数算 —— 两者都必须在画之前拿到 rows。
        原来 rows 是在 `draw_metrics_panel` 里边算边画的，高度写死 6 行，
        mi 的第 7 行就画到面板外面去了。
        """
        met = self._mp_current_metrics()
        # 指标行：聚拢度/重叠/边界盒/填充率/剖面缺陷(Φ)/洞凸起/mod 约束等；
        # 不再显示「目标框」位置读数（对玩家无意义，棋盘绿框仍由 _draw_target_window 画）。
        game = self.game
        step = getattr(self, 'current_step', 1)
        kind = self._mp_kind()

        if kind not in self._MP_SUPPORTED:
            # 未实装形态：给占位行，**不跑任何形态专属公式**。
            # mi 若落进方形分支，会用矩形窗口枚举在斜坐标上算出 0.0% 的聚拢度
            # —— 数字看着「有效」其实完全无意义，比报错更糟。
            return self._mp_unsupported_rows(), met

        region = getattr(self, '_target_region', None)
        if region is None:
            region = self._compute_target_region()

        if kind == 'mi':
            # 米字格：目标形状 = m×n 棋盘轮廓、4mn 个单元、两个形状枚举
            # （m×n 与 n×m）。指标行与前两形态同构，差别只在「单元数」
            # 是 4mn 而不是 mn —— 面板显示的「重叠 x/4mn」与求解器
            # best_placement.overlap/total 同一口径。
            from solver.ml.mi_placement import best_placement_of_game
            from solver.ml.mi_holes import detect_mi_holes
            from solver.ml.mi_adapter import mi_coords
            best = (region if hasattr(region, 'cells')
                    else best_placement_of_game(
                        game, m=getattr(game, 'm', None),
                        n=getattr(game, 'n', None), step=step))
            coords = mi_coords(game)
            holes, protrusions = detect_mi_holes(coords, best.cells, step)
            n_gap = sum(1 for h in holes if h['type'] == 'gap')
            n_hole = sum(1 for h in holes if h['type'] == 'hole')
            m = getattr(game, 'm', 0) or 0
            n = getattr(game, 'n', 0) or 0
            from solver.ml.invariants import profile_defect
            # mi 单元带 q 分量（(r,c,q)），剖面缺陷只看 (r,c) 投影的基格平衡；
            # 已还原态基格恰成 m×n 矩形 → Φ=0。
            phi = profile_defect({(r, c) for r, c, _q in coords}, m, n)
            shape_txt = f"{m}×{n}" if m == n else f"{m}×{n}/{n}×{m}"
            rows = [
                ("聚拢度", f"{met['score'] * 100:.1f}%"),
                ("重叠", f"{met['overlap']}/{4 * m * n}"),
                ("边界盒", f"{met['bbox'][0]}×{met['bbox'][1]}"),
                ("填充率", f"{met['fill_rate'] * 100:.1f}%"),
                ("剖面缺陷", f"{phi}"),
                ("洞/凸起", f"洞{n_hole} 缺{n_gap} 凸{len(protrusions)}"),
            ]
            # mod 约束：mi 的合法偏移不是「step 倍数」而是「类自同构余数对
            # 集合 S(step)」（实测否证了倍数控法，见 experiments/_mi_mod_probe.py）。
            # 这里报 S 的大小而不是有无 —— 倍数口径在 mi 上是错的。
            from solver.ml.mi_placement import mod_auts
            rows.append(("mod 约束",
                         f"step={step} S={len(mod_auts(m, n, step))}"))
        elif kind == 'triangle':
            # 三角：目标形状是大三角、单元数 k²、放置 = 1 朝向 × 平移
            from solver.ml.tri_placement import (
                best_placement_of_game, tri_profile_defect)
            from solver.ml.tri_holes import detect_tri_holes
            k = getattr(game, 'k', 0) or 0
            best = (region if hasattr(region, 'cells')
                    else best_placement_of_game(game, k=k, step=step))
            coords = frozenset(tuple(b.location) for b in game.blocks)
            holes, protrusions = detect_tri_holes(coords, best.cells, step)
            n_gap = sum(1 for h in holes if h['type'] == 'gap')
            n_hole = sum(1 for h in holes if h['type'] == 'hole')
            # 剖面缺陷 Φ 走三角专属口径（参照大三角形的奇数阶梯剖面）——
            # 三角坐标是 (i,j,up) 三元组、理想形状不是矩形，方形那套
            # profile_defect 两者都不适用（曾直接 ValueError，2026-10-12 修）。
            # 与方形同构：Φ=0 ⟺ 已还原（平移无关）。
            phi = tri_profile_defect(coords, k)
            rows = [
                ("聚拢度", f"{met['score'] * 100:.1f}%"),
                ("重叠", f"{met['overlap']}/{k * k}"),
                ("边界盒", f"{met['bbox'][0]}×{met['bbox'][1]}"),
                ("填充率", f"{met['fill_rate'] * 100:.1f}%"),
                ("剖面缺陷", f"{phi}"),
                ("洞/凸起", f"洞{n_hole} 缺{n_gap} 凸{len(protrusions)}"),
            ]
        else:   # square
            from solver.ml.gather_solver import (
                detect_target_corner, _game_coords,
            )
            from solver.ml.invariants import profile_defect
            coords = frozenset(tuple(b.location) for b in game.blocks)
            tc = detect_target_corner(_game_coords(game), game.m, game.n, step)
            # 剖面缺陷 Φ：位置无关、已还原态=0（求解器「并列取 Φ 最小」判据同源）。
            phi = profile_defect(coords, game.m, game.n)
            rows = [
                ("聚拢度", f"{met['score'] * 100:.1f}%"),
                ("重叠", f"{met['overlap']}/{game.m * game.n}"),
                ("边界盒", f"{met['bbox'][0]}×{met['bbox'][1]}"),
                ("填充率", f"{met['fill_rate'] * 100:.1f}%"),
                ("剖面缺陷", f"{phi}"),
                ("mod 状态",
                 "有约束" if tc else ("无约束" if step > 1 else "step=1")),
            ]
        return rows, met

    def _mp_row_count(self):
        """当前形态的面板行数（不重算指标内容）。

        事件处理（拖动/点标题栏）只关心**面板矩形有多大**，不需要重跑一遍
        洞检测 —— 那玩意不便宜。所以这里用「形态 → 行数」的映射，
        跟 `_mp_rows` 的实际条数保持一致：mi 7 行（多一行 mod 约束），
        其余 6 行，未实装形态按占位行数。
        """
        if self._mp_kind() == 'mi' and self._mp_kind() in self._MP_SUPPORTED:
            return 7
        if self._mp_kind() not in self._MP_SUPPORTED:
            return len(self._mp_unsupported_rows())
        return 6

    def handle_metrics_panel_event(self, event):
        """处理指标面板事件（拖动 + 关闭），返回 True 表示事件已消费。"""
        if not getattr(self, 'show_metrics_panel', False):
            return False

        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self._mp_build_layout(self._mp_row_count())

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
