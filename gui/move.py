# -*- coding: utf-8 -*-
"""移动核心混入：方向键/键盘移动、三角与米字的 prepare、移动会话合拍。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第七步，
Move 整块再切第一刀；鼠标拖拽一家在 gui/drag.py）。这里管「怎么动」：
move_selected_blocks 是方形/通用的移动入口，三角/米字各有 prepare 管线；
_bump_move_session 管「同一选中会话的连续移动并入同一快照」（撤销/历史
也依赖它，故留名不变）。依赖 tri_key 与 op_log，均为模块级 import。
"""
from game_mi import mi_key
from game_triangle import tri_key

from gui import op_log


class MoveMixin:
    """移动核心（原 GUI.py 内联代码，整体搬迁）。"""

    def _arrow_move_allowed(self, direction: str, step: int = None) -> bool:
        """S1-4：干跑一次「点这个箭头」，看会不会被拒绝。

        为什么要干跑、而不是照旧拿 try_move_ex(d, 1) 去猜：点击按键走的
        move_selected_blocks 与箭头自己算的判定是两套东西 ——
          ① 步数档用的是 current_step（点一下走 current_step 格，不一定是 1）；
          ② 米字/三角走各自的 _mi_prepare_move / _triangle_prepare_move；
          ③ 还有一串前置拦截（只读存档、创造模式、计时模式就绪态、
             整体平移禁止…）。
        只算「能不能走一格」就会得到用户报的那个症状：明明能走却没箭头，
        或箭头点了被拒绝。这里逐条复用**同一条路径**，结论与点击一致。

        副作用：prepare 会重写 be_opted、会写提示浮窗；干跑一律原样还原。
        """
        move_step = step if step is not None else self.current_step
        # ---- move_selected_blocks 头部的前置拦截，逐条对齐
        if self._tut_board_locked():
            return False
        if self._readonly_blocked():
            return False
        if self.create_mode:
            return False
        if (getattr(self, '_ann_design_session', False)
                or (self.annotation_mode
                    and getattr(self, '_ann_view', None) == 'build')):
            return False
        if self.game_mode == 'timed' and self.timer_state == 'ready':
            return False

        snap_opt = [(b, b.be_opted) for b in self.game.blocks]
        snap_msg = self.macro_notify_msg
        snap_timer = self.macro_notify_timer
        try:
            if getattr(self, 'mi_mode', False):
                return self._mi_prepare_move(direction, move_step) is not None
            if getattr(self, 'triangle_mode', False):
                return self._triangle_prepare_move(direction, move_step) is not None
            selected = [b for b in self.game.blocks if b.be_opted]
            if not selected:
                return False
            if len(selected) == len(self.game.blocks):
                return False       # 整体平移：禁止（与真实路径同款拦截）
            return bool(self.game.try_move_ex(direction, move_step)[0])
        finally:
            for b, was in snap_opt:
                b.be_opted = was   # 还原选中态（prepare 会重 opt）
            self.macro_notify_msg = snap_msg
            self.macro_notify_timer = snap_timer

    def move_selected_blocks(self, direction: str, step: int = None):
        """
        移动所有选中的滑块，逐步验证（每次1格，共step次），
        所有步骤都通过后才提交。支持动画。

        参数：
            direction: 移动方向 'w'上 's'下 'a'左 'd'右
            step: 移动步数，默认为 self.current_step

        返回：
            bool - 是否真正执行了移动（被拦截/未选中/移动不合法均为 False）
        """
        move_step = step if step is not None else self.current_step
        # 教程解法播放中：锁定棋盘操作（不得打断回放）
        if self._tut_board_locked():
            return False
        # 手动移动会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 手动滑动 = 打断连续撤销/重做
        self._stop_continuous_undo_redo()
        # 只读存档：禁止滑动（撤销重做除外）
        if self._readonly_blocked():
            return False
        # 创造模式：只造题不玩游戏（与练习模式功能解耦）
        if self.create_mode:
            if self.triangle_mode or self.mi_mode:
                self.macro_notify_msg = "创造模式：请用[手动构造]造题"
            else:
                self.macro_notify_msg = "创造模式：请用[随机生成]或[手动构造]造题"
            self.macro_notify_timer = 90
            return False
        # 标注模式的手动构造视图 / 高级选项设计画布：主棋盘是编辑画布，禁止滑动
        if (getattr(self, '_ann_design_session', False)
                or (self.annotation_mode and self._ann_view == 'build')):
            if self._ann_view == 'build':
                _msg = "构造中：点格增删滑块，按[应用并开始]完成"
            elif getattr(self, 'triangle_mode', False) or getattr(self, 'mi_mode', False):
                # 异形的高级选项形状固定为标准形，只有点缝绑解
                _msg = "高级选项：形状固定，点缝捆绑/解绑，[存样式]后退出"
            else:
                _msg = "高级选项：点格增删/点缝捆绑，[存样式]后退出"
            self.macro_notify_msg = _msg
            self.macro_notify_timer = 90
            return False
        # 计时模式：就绪态（已打乱未开始）禁止滑动，保证公平
        if self.game_mode == 'timed' and self.timer_state == 'ready':
            self.macro_notify_msg = "计时模式：按空格开始计时后才能滑动"
            self.macro_notify_timer = 90
            return False

        # 计时模式：就绪态（已打乱未开始）禁止滑动，保证公平
        if self.game_mode == 'timed' and self.timer_state == 'ready':
            self.macro_notify_msg = "计时模式：按空格开始计时后才能滑动"
            self.macro_notify_timer = 90
            return False

        if getattr(self, 'mi_mode', False):
            prepared = self._mi_prepare_move(direction, move_step)
            if prepared is None:
                return False
            selected, final_positions, move_step = prepared
        elif getattr(self, 'triangle_mode', False):
            prepared = self._triangle_prepare_move(direction, move_step)
            if prepared is None:
                return False
            selected, final_positions, move_step = prepared
        else:
            selected = [b for b in self.game.blocks if b.be_opted]
            if not selected:
                return False
            # 选中了全部滑块 = 整体平移，形状不变，对还原毫无意义 → 禁止
            # （缝隙落在棋形外沿时会走到这里，见 _drag_slide 的前置拦截）
            if len(selected) == len(self.game.blocks):
                self.macro_notify_msg = "不能整体移动所有滑块（形状不变，没有意义）"
                self.macro_notify_timer = 120
                return False

            # 调用 game.py 的 try_move 进行纯逻辑验证（附带失败原因）
            final_positions, fail_reason = self.game.try_move_ex(direction, move_step)
            if not final_positions:
                # 失败提示（右下角浮窗）：断开 / 重叠；无选中时不提示
                if fail_reason == 'disconnected':
                    self.macro_notify_msg = "滑动失败：移动后滑块会断开"
                    self.macro_notify_timer = 90
                elif fail_reason == 'collision':
                    self.macro_notify_msg = "滑动失败：移动后滑块会重叠"
                    self.macro_notify_timer = 90
                return False

        # 构建移动元数据
        #
        # `delta` 是**实际位移向量**（按块坐标分量），不是字母换算出来的格数。
        # 动画层（animation._move_delta）优先吃它：引擎板型的块坐标是 P 空间
        # （碎三角一步是 (12,0) 这种量级），而字母方向表只有方形四向/三角
        # 六向/米字八向那几张**方格**表——拿方形的 'd'→(0,1) 去插值，撤销时
        # 按错位移找不到块（直接跳过动画），重做时朝错方向爬一格（动画错乱）。
        _delta = None
        if selected and final_positions and len(selected) == len(final_positions):
            d0 = (final_positions[0][0] - selected[0].location[0],
                  final_positions[0][1] - selected[0].location[1])
            # 只接受「整组同一位移」的动作（滑动必然如此）。顺序万一没对齐就能
            # 立刻发现，退回旧的按字母换算，不拿错误位移去插值。
            if all((fp[0] - sb.location[0], fp[1] - sb.location[1]) == d0
                   for sb, fp in zip(selected, final_positions)):
                _delta = d0
        move_info = {
            'gap_type': self.selected_gap[0] if self.selected_gap else None,
            'gap_line': self.selected_gap[1] if self.selected_gap else None,
            'direction': direction,
            'step': move_step,
            'moved_positions': [list(b.location) for b in selected],
        }
        if _delta is not None:
            move_info['delta'] = _delta
        self._pending_move_info = move_info

        # 录制模式：记录这一步到宏
        if self.macro_recording and self.macro_record_base_point is not None:
            side = self._get_selected_side()
            if self.selected_gap and side:
                rep_cell = list(selected[0].location) if selected else None
                self._record_macro_step(
                    self.selected_gap[0], self.selected_gap[1],
                    side, direction, rep_cell
                )

        # 所有步骤都合法
        if self.animation_enabled and self.animation_duration > 0:
            self.start_animation(selected, final_positions)
            self.macro_notify_msg = f"向{self._dir_name(direction)}移动 {move_step}步"
            self.macro_notify_timer = 120
        else:
            self.game.commit_move(final_positions)
            # 一次移动 = 一步：与动画路径（animation.py）、宏播放路径
            # （events.py）和历史快照的 steps 计数保持一致。按 move_step 累加
            # 会让读档/撤销后的步数（取历史累计）比实际少，计时成绩也对不上。
            self.step_count += 1
            self.game_history.save_snapshot(self.game, move_info,
                                            self._move_merge_key())
            self._pending_move_info = None
            # 走一步后**不主动拽相机**：只在整盘滑到完全看不见时兜底拉回。
            # 旧口径「有一块碰到边缘就平移」会让碎三角每步都动镜头。
            self.ensure_blocks_visible(only_if_invisible=True)
            # 操作提示先于过关判定：过关/教程播报优先级更高，不应被“向X移动”覆盖
            self.macro_notify_msg = f"向{self._dir_name(direction)}移动 {move_step}步"
            self.macro_notify_timer = 120
            self._maybe_show_solved_popup()
            self._mark_file_dirty()
        return True

    def _dir_name(self, direction: str) -> str:
        """方向字母 → 中文方向名（方形四向 + 三角六向；模型板型按几何算）。"""
        names = {
            'w': '上', 's': '下', 'a': '左', 'd': '右',
            'e': '右上', 'z': '左下', 'x': '右下',
        }
        if direction in names:
            return names[direction]
        # 模型文件板型（通用通道）：字母是**从几何派生的**（compat 的
        # A/B/C…），没有语义名。直接把 'A' 写进「向A移动」玩家看不懂，
        # 所以按这块盘自己的几何把方向折成屏幕八向名（用任一在盘块做参考
        # 点算一步的屏幕位移——方向与参考块无关，只取决于晶格与缩放）。
        spec = self._generic_spec() if hasattr(self, '_generic_spec') else None
        if spec is not None:
            from engine.compat import direction_table
            if direction_table(spec).get(direction) is not None:
                key = None
                for b in self.game.blocks:
                    key = tuple(b.location)
                    break
                if key is not None:
                    try:
                        vec = self._letter_screen_vec(direction, key)
                    except Exception:
                        vec = None
                    if vec:
                        vx, vy = vec
                        sx = '右' if vx > abs(vy) * 0.4 else (
                            '左' if vx < -abs(vy) * 0.4 else '')
                        sy = '下' if vy > abs(vx) * 0.4 else (
                            '上' if vy < -abs(vx) * 0.4 else '')
                        label = sy + sx
                        if label:
                            return label
                return f'缝向{direction}'
        return direction

    @staticmethod
    def _gap_type_name(gap_type: str) -> str:
        """缝隙族 → 中文名（方形 h/v，三角 h/p/n，米字 h/v/d1/d2）。"""
        names = {'h': '横向', 'v': '纵向', 'p': '斜向', 'n': '反向斜',
                 'd1': '主对角', 'd2': '副对角'}
        return names.get(gap_type, gap_type)

    def _gap_line_range(self, gap_type: str):
        """当前局面该缝族的候选 line 范围 (lo, hi)；取不到回 None。

        给 select_gap 的成功/失败消息带「有效范围」用（外部 AI 反馈：
        line 的有效范围不公开，全靠试错）。方形 = 边界盒内；三角用
        game_triangle.gap_index_range（保证两侧非空的候选域）；米字
        的半整数线号由 is_valid_gap 自判，不给范围提示；通用通道直接
        问 SpecPolygonView 的 distinct rank 边界（与点击选缝同源）。
        """
        if getattr(self, 'triangle_mode', False) is False and \
                getattr(self, 'mi_mode', False) is False and \
                self._generic_spec() is not None:
            try:
                spec = self._generic_spec()
                fam = next((f for f in spec.seam_families
                            if f.name == gap_type), None)
                if fam is None:
                    return None
                view = self._polygon_view()
                pts = view._family_candidates(self.game.board, fam)
                if not pts:
                    return None
                lines = [ln for _t, ln in pts]
                return (min(lines), max(lines))
            except Exception:
                return None
        if gap_type not in ('h', 'v'):
            return None
        try:
            if getattr(self, 'triangle_mode', False):
                from game_triangle import gap_index_range
                r = gap_index_range(gap_type, self.game.positions())
                return (r.start, r.stop - 1) if len(r) else None
            if getattr(self, 'mi_mode', False):
                return None
            b = self.game.get_boundaries()
            if gap_type == 'h':
                return (b['min_row'], b['max_row'] - 1)
            return (b['min_col'], b['max_col'] - 1)
        except Exception:
            return None

    # 三角六向键位 → 晶格方向字母（与 game_triangle.DIRECTIONS 一致；
    # 注意 's' 不是三角方向，故不映射 move_down）
    TRI_MOVE_KEYS = {
        'move_up': 'w', 'tri_up_right': 'e', 'move_left': 'a',
        'move_right': 'd', 'tri_down_left': 'z', 'tri_down_right': 'x',
    }

    # 米字格四族縫隙的切向／法向（格座標，y 軸向下）與兩個方向字母。
    # 切向平行於縫隙線，正方向對應第一個字母；法向指向 rank 增大的一側
    # （side_of 的 1 側），第二下觸控就靠這兩個分量定向：
    #   h（橫邊）   切向 (1, 0)    法向 (0, 1)      d=右 / a=左
    #   v（豎邊）   切向 (0, 1)    法向 (1, 0)      s=下 / w=上
    #   d1（"\"）   切向 (1, 1)/√2  法向 (-1, 1)/√2  x=↘ / q=↖
    #   d2（"/"）   切向 (1, -1)/√2 法向 (1, 1)/√2   e=↗ / z=↙
    MI_GAP_AXES = {
        'h': ((1.0, 0.0), (0.0, 1.0), 'd', 'a'),
        'v': ((0.0, 1.0), (1.0, 0.0), 's', 'w'),
        'd1': ((1.0, 1.0), (-1.0, 1.0), 'x', 'q'),
        'd2': ((1.0, -1.0), (1.0, 1.0), 'e', 'z'),
    }

    # 米字格「一格」按族定義（規劃表 22）：一格 = 該方向能滑動的最小量，
    # 與幾何長度是兩件事，所以同時把長度說清楚。橫豎一步是一條格邊長，
    # 斜向一步是半個格身的斜向距離（√2/2）；選中縫隙時把這句話一起顯示，
    # 玩家才好預期這一格到底滑多遠
    MI_STEP_NOTE = {
        'h': '横向一格 = 一条格边',
        'v': '纵向一格 = 一条格边',
        'd1': '斜向一格 = 半个格身的斜向距离',
        'd2': '斜向一格 = 半个格身的斜向距离',
    }

    def _triangle_keyboard_move(self, event) -> bool:
        """三角形密铺的 6 向键盘操作：W E / A D / Z X（围住 S 成六边形）。"""
        if not getattr(self, 'control_mouse_kb', True):
            return False
        for action_name, direction in self.TRI_MOVE_KEYS.items():
            if self._is_action_triggered(event, action_name):
                self.move_selected_blocks(direction)
                return True
        return False

    def _triangle_prepare_move(self, direction: str, step: int):
        """三角形密铺：為一次移動準備選中組與最終位置。

        需要 selected_block 作參考塊（沒有就提示先點選縫隙、或直接拖動滑塊），
        並沿用已選中的縫隙——縫隙要麼由「點縫→點塊」兩次觸控選定，要麼由拖拽
        發起時 resolve_drag 的「縫隙線穿過手指」規則定下，此處不再自行猜一條。

        回傳 (selected, final_positions, actual_step)；失敗回 None 並提示。
        """
        from game_triangle import DIRECTIONS, GAP_DIRECTIONS, tri_key
        if direction not in DIRECTIONS:
            self.macro_notify_msg = f"三角形密铺：未知方向 {direction}"
            self.macro_notify_timer = 90
            return None

        gap = getattr(self, 'selected_gap', None)
        if gap is not None:
            gap_type, line = gap
            if gap_type not in GAP_DIRECTIONS or direction not in GAP_DIRECTIONS[gap_type]:
                self.macro_notify_msg = "滑动失败：该方向与选中的缝隙不平行"
                self.macro_notify_timer = 90
                return None
            block = getattr(self, 'selected_block', None)
            if block is None:
                block = self.game.blocks[0] if self.game.blocks else None
            if block is None:
                return None
            self.game.opt(gap_type, line, block)
            selected = [b for b in self.game.blocks if b.be_opted]
            if not selected:
                return None
            final_positions, reason = self.game.try_move_ex(direction, step)
            if not final_positions:
                self.macro_notify_msg = {
                    'disconnected': "滑动失败：移动后滑块会断开",
                    'collision': "滑动失败：移动后滑块会重叠",
                    'all_selected': "滑动失败：不能移动全部滑块",
                }.get(reason, "滑动失败")
                self.macro_notify_timer = 90
                return None
            actual_step = step
        else:
            # 未預選縫隙：仍以 selected_block 為參考塊（由拖拽發起時置位）。
            # 沒有參考塊就明說，不偷偷拿 blocks[0] 頂替——那會讓「什麼都沒選」
            # 的按鍵憑空移走一組，與方形版「未選中縫隙和滑塊時方向鍵無反應」不一致
            block = getattr(self, 'selected_block', None)
            if block is None:
                self.macro_notify_msg = "三角形密铺：请先点选缝隙，或直接拖动滑块"
                self.macro_notify_timer = 90
                return None
            positions, gap_type, line, reason, actual_step = \
                self.game.resolve_drag(tri_key(block), direction, step)
            if not positions:
                self.macro_notify_msg = {
                    'no_move': "这个方向滑不动（被其它滑块挡住或会断开）",
                    'bad_direction': f"三角形密铺：未知方向 {direction}",
                    'no_block': "滑动失败：找不到起始滑块",
                }.get(reason, "滑动失败")
                self.macro_notify_timer = 90
                return None
            final_positions = positions
            self.selected_gap = (gap_type, line)

        selected = [b for b in self.game.blocks if b.be_opted]
        # 选中了全部滑块 = 整体平移，形状不变，对还原毫无意义 → 禁止
        if len(selected) == len(self.game.blocks):
            self.macro_notify_msg = "不能整体移动所有滑块（形状不变，没有意义）"
            self.macro_notify_timer = 120
            return None
        return selected, final_positions, actual_step

    # ---------- 米字格（M2）：选组 + 定向 ----------
    def _mi_shifted(self) -> bool:
        """米字格是否處於錯位態：任一塊落在半整數座標上。

        斜向一格是平移 ±(½,½)，走完之後一半的塊落進 B 晶格（半整數座標），
        此後橫豎縫大量失效——半整數層級的格邊整條穿過塊的內部，選不動也
        滑不動。規劃 H3 新增的幾處提示都只在這裡多說一句，對齊態的言行
        逐字不變，回歸面最小（對齊態的整數格邊本來就切不進任何塊）。
        """
        return any(r % 1 or c % 1 for (r, c, _q) in self.game.positions())

    def _mi_fam_counts(self) -> dict:
        """各族有效縫隙的條數（錯位態下橫豎族可能歸零，提示要按實數說）。"""
        counts = {'h': 0, 'v': 0, 'd1': 0, 'd2': 0}
        for fam, _line in self.game.all_gaps():
            if fam in counts:
                counts[fam] += 1
        return counts

    def _mi_hv_left(self, fam: str) -> str:
        """錯位態下橫豎一族還剩什麼、該怎麼辦（按實際剩餘條數說）。

        規劃 §1.3：不是所有橫豎縫都鎖——6×6 沿 d1 走一格後 h 還剩 3 條、
        v 還剩 2 條，所以先數一遍再說：還有剩就勸他點選其中的一條，一條
        不剩才勸他沿斜向滑（把任一半再推一格就回到單一晶格，橫豎縫全數
        復活，H4 的實測已核對過這個數）。一律「先沿斜向滑回去」會把
        「還有 3 條能用」說成「全鎖了」，反而誤導。
        """
        name = '横向' if fam == 'h' else '纵向'
        left = self._mi_fam_counts()[fam]
        if left:
            return f"{name}缝隙还剩 {left} 条，先点选其中一条"
        return f"错位了：{name}缝隙一条不剩，先沿斜向滑回去"

    def _mi_locked_seam(self, gap, cells) -> bool:
        """這條選不動的縫，是不是錯位態切在塊裡的那種（半整數橫豎縫）。

        判據用幾何原文：線嚴格落進某塊的跨度內部（與引擎 is_valid_gap
        同一套判據）。對角族永遠 False——兩個晶格的 y−x、x+y 都恆為整數，
        斜縫切不進塊；棋形外沿的縫也不算（一側沒有塊，整體平移沒有意義，
        與舊版一致地安靜捨棄）。
        """
        gap_type, line = gap
        if gap_type not in ('h', 'v') or not self._mi_shifted():
            return False
        from game_mi import span
        return any(lo < line < hi
                   for (lo, hi) in (span(gap_type, k) for k in cells))

    def _rejected_seam_at(self, screen_x: int, screen_y: int):
        """這次點擊附近有沒有一條「畫得出、點得到、選不動」的縫；有就回它。

        幾何與 get_gap_at_pos 同源（都走視圖的 candidate_gaps），差別只在
        這裡保留被引擎否決的候選：方形/三角否決的都是棋盤最外沿那條——
        一側沒有塊，整條線平移沒有意義，所以選不動。回 None 表示沒有。

        命中帶比選縫窄（方形 gap+3px、三角 6px；選縫用的是 gap+10 / 10）：
        提示要掛在「真的點在那條線上」才算說得對，否則在棋盤外沿的深色
        背景上起手拖地圖也會被念一句，反而吵。外沿線在塊外只露出幾個像素，
        這個帶寬正好蓋住它。
        """
        try:
            wx, wy = self.screen_to_world(screen_x, screen_y)
            if getattr(self, 'triangle_mode', False):
                for cand in self._tri_view().candidate_gaps(
                        wx, wy, self.game.positions(), tolerance=6.0):
                    if not self.game.is_valid_gap(*cand):
                        return cand
                return None
            if self._generic_spec() is not None:
                # 通用通道：候選縫按距離序，保留被引擎否決的第一條——要麼
                # 一側沒有塊（is_valid 否），要麼兩側都推不動（live 否）。
                # 碎三角實測 12 條接觸邊不被任何活縫覆蓋，點它們要給提示
                # 而不是一聲不吭。
                view = self._polygon_view()
                origin = self._poly_view_origin(view)
                for gap_type, line, _dist in view.gap_candidates(
                        wx, wy, self.game.board, origin, tolerance=6.0):
                    if not self.game.is_valid_gap(gap_type, line):
                        return (gap_type, line)
                    if not self._generic_gap_live((gap_type, line)):
                        return (gap_type, line)
                return None
            bounds = self.game.get_boundaries()
            for kind, idx in self.board_view.candidate_gaps(
                    wx, wy, bounds, tolerance=3.0):
                if kind == 'h' and not self.game.is_valid_h_line(idx):
                    return ('h', idx)
                if kind == 'v' and not self.game.is_valid_v_line(idx):
                    return ('v', idx)
        except Exception as e:
            print(f"_rejected_seam_at error: {e}")
        return None

    def _bandage_group_block_near(self, wx: float, wy: float):
        """世界座標附近最近的「已捆綁」滑塊；沒有捆綁塊回 None。

        用途：點中捆綁組的**內部縫**時，把它當成「點中該組的滑塊」（整組
        剛性體，點哪塊都通向同一整組），而不是彈「這條縫選不動」。

        三形態的位置語義不同（方形 (r,c)、三角 (i,j,up)、米字 (r,c,q)），
        所以「塊心」一律交給各自視圖算——方形用 block_rect，異形用
        piece_center（三角重心 / 米字內心）。都回世界座標，可直接和
        screen_to_world 的結果比距離。
        """
        tri_mode = getattr(self, 'triangle_mode', False)
        mi_mode = getattr(self, 'mi_mode', False)
        if tri_mode:
            view = self._tri_view()
        elif mi_mode:
            view = self._mi_view()
        else:
            view = None
        best = None
        best_d = None
        for b in self.game.blocks:
            if not getattr(b, 'group', 0):
                continue
            if tri_mode:
                cx, cy = view.piece_center(*tri_key(b))
            elif mi_mode:
                cx, cy = view.piece_center(*mi_key(b))
            else:
                bx, by, bw, bh = self.board_view.block_rect(*b.location)
                cx, cy = bx + bw / 2.0, by + bh / 2.0
            d = (cx - wx) ** 2 + (cy - wy) ** 2
            if best_d is None or d < best_d:
                best_d = d
                best = b
        return best

    def _sq_click_query(self, screen_x: int, screen_y: int) -> tuple:
        """方形/三角一次點擊的命中結果 (縫隙, 滑塊)，選不動的縫改走提示。

        棋盤最外沿那一圈縫是畫出來的（縫線比棋盤寬 20px，且整條沿外邊
        走），也點得到，但只有一側有塊——選不動。舊代碼對這種點擊一聲不
        響，玩家只覺得「點了沒反應」；米字格對錯位態鎖死的縫早就會說清楚
        （_mi_click_query），這裡對齊同一句話式：「這條縫選不動（為什麼）：
        該怎麼辦」。只在這一下既沒點中縫、也沒點中塊時才說，正常的選縫/
        選塊流程一字不變。
        """
        gap = self.get_gap_at_pos(screen_x, screen_y)
        block = self.get_block_at_pos(screen_x, screen_y)
        if (getattr(self, '_pick_fill', None) is None
                and self._generic_spec() is not None
                and gap is None and block is not None):
            # 通用通道多邊形密鋪無縫隙：共享邊的中點對兩相鄰塊都在
            # 「邊界內」（射線法對邊界點不設防），點縫時塊命中是假陽性。
            # 先問這附近有沒有被引擎否決的縫——有就當點縫處理（塊命中
            # 作廢），好讓下面的「選不動」提示有機會說句話。
            if self._rejected_seam_at(screen_x, screen_y) is not None:
                block = None
        # 选块填空的两下点击语义是「选哪块、填哪个坑」，不是滑动，
        # 此时别插嘴说缝选不动
        if (gap is None and block is None
                and getattr(self, '_pick_fill', None) is None):
            seam = self._rejected_seam_at(screen_x, screen_y)
            if seam is not None:
                # 排障日誌：與米字格的 mi_seam_reject 對位，事後能看出
                # 玩家說的「點了沒反應」到底落在哪條外沿縫上
                generic = self._generic_spec() is not None
                op_log.log('sq_seam_reject', gap=list(seam),
                           form='generic' if generic
                           else ('tri' if getattr(self, 'triangle_mode', False)
                                 else 'sq'))
                if generic:
                    # 通用通道的否決原因有兩種，分開說（外沿 vs 焊死）
                    self.macro_notify_msg = (
                        "这条缝选不动（两侧滑块都推不动）：请选旁边的缝"
                        if self.game.is_valid_gap(*seam)
                        else "这条缝选不动（一侧没有滑块）：请选里面的缝")
                else:
                    self.macro_notify_msg = ("这条缝选不动（棋盘外沿，外侧没有滑块）："
                                             "请选里面的缝")
                self.macro_notify_timer = 120
        return gap, block

    def _mi_click_query(self, screen_x: int, screen_y: int) -> tuple:
        """米字格一次點擊的命中結果 (縫隙, 滑塊)，選不動的縫改走提示。

        錯位態的半整數橫豎縫：畫面畫得出來、也點得到，就是選不動（線整條
        穿過塊的內部）。這種點擊只給提示並當作沒點中——照常放行的話它會
        落進兩次觸控的第二下分支，玩家點一條看得見卻選不動的縫就提交一次
        移動，方向還是由上一記落點瞎猜的（規劃 §5 手動驗收第 3 條：「而不是
        無反應」）。其餘情況與 get_gap_at_pos / get_block_at_pos 分別查詢
        等價（那兩個是純查詢，不發提示，供測試與其他地方複用）。
        """
        world_x, world_y = self.screen_to_world(screen_x, screen_y)
        cells = self.game.positions()
        gap = self._mi_view().gap_at(world_x, world_y, cells)
        if gap is not None and not self.game.is_valid_gap(*gap):
            if self._mi_locked_seam(gap, cells):
                from game_mi import span
                # 排障日志：这条缝「画得出、点得到、选不动」，是错位态横竖
                # 缝整条穿过块内部的那种。把切在哪些块里、各族还剩几条一起
                # 记下来——口头描述只能说到「点了没反应」这一层
                cut = []
                for k in cells:
                    lo, hi = span(gap[0], k)
                    if lo < gap[1] < hi:
                        cut.append(list(k))
                op_log.log('mi_seam_reject', gap=list(gap),
                           shifted=self._mi_shifted(), valid=False,
                           left=self._mi_fam_counts(), cut=cut)
                self.macro_notify_msg = (
                    f"这条缝选不动（错位态切在块里）：{self._mi_hv_left(gap[0])}")
                self.macro_notify_timer = 120
                return None, None
            gap = None
        return gap, self.get_block_at_pos(screen_x, screen_y)

    def _mi_prepare_move(self, direction: str, step: int):
        """米字格：為一次移動準備選中組與最終位置。

        與三角版的差別：不做單次觸控拖拽（resolve_drag 不存在），因此
        一定要有 selected_gap + selected_block——縫隙由第一下觸控選定，
        滑塊由第二下觸控選定（拖動則由那次拖動定向），虛擬鍵盤複用同一份選中態。
        方向必須平行於已選縫隙，否則提示並放棄。
        """
        from game_mi import DIRECTIONS, GAP_DIRECTIONS
        if direction not in DIRECTIONS:
            self.macro_notify_msg = f"米字格：未知方向 {direction}"
            self.macro_notify_timer = 90
            return None

        gap = getattr(self, 'selected_gap', None)
        if gap is not None:
            gap_type, line = gap
            if gap_type not in GAP_DIRECTIONS:
                return None
            if direction not in GAP_DIRECTIONS[gap_type]:
                self.macro_notify_msg = "滑动失败：该方向与选中的缝隙不平行"
                self.macro_notify_timer = 90
                return None
            block = getattr(self, 'selected_block', None)
            if block is None:
                # 沒有參考塊時退回第一塊：虛擬鍵盤路徑只要求先選縫隙，
                # 此時「移哪一側」由第一塊所在側決定（可預期：它就是
                # 建局時的第一塊，縫隙選定後側面也就固定了）
                block = self.game.blocks[0] if self.game.blocks else None
            if block is None:
                return None
            self.game.opt(gap_type, line, block)
            selected = [b for b in self.game.blocks if b.be_opted]
            if not selected:
                return None
            final_positions, reason = self.game.try_move_ex(direction, step)
            if not final_positions:
                msg = {
                    'disconnected': "滑动失败：移动后滑块会断开",
                    'collision': "滑动失败：移动后滑块会重叠",
                    'all_selected': "滑动失败：不能移动全部滑块",
                }.get(reason, "滑动失败")
                if gap_type in ('h', 'v') and self._mi_shifted():
                    # 錯位態的半整數橫豎縫容易被另一側卡住：沿斜向把任一半
                    # 再推一格就回到單一晶格，橫豎縫全數復活（H4 已實測核對）
                    msg += "（错位态可先沿斜向滑回去）"
                self.macro_notify_msg = msg
                self.macro_notify_timer = 90
                return None
            actual_step = step
        else:
            # 未選縫隙：米字格不猜縫（沒有拖拽那條捷徑），明說要兩次觸控
            self.macro_notify_msg = "米字格：请先点选缝隙，再点滑块移动"
            self.macro_notify_timer = 90
            return None

        selected = [b for b in self.game.blocks if b.be_opted]
        # 缝隙落在棋形外沿時會選中全部滑塊：整體平移形狀不變，禁止
        if len(selected) == len(self.game.blocks):
            self.macro_notify_msg = "不能整体移动所有滑块（形状不变，没有意义）"
            self.macro_notify_timer = 120
            return None
        return selected, final_positions, actual_step

    def _bump_move_session(self):
        """结束当前「选中会话」：之后的移动不再并入同一快照。

        在选中变化（点缝隙/点方块/右键取消）与撤销/重做/跳步时调用。
        """
        self._move_session_id = getattr(self, '_move_session_id', 0) + 1

