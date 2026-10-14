# -*- coding: utf-8 -*-
"""鼠标拖拽混入：拖拽跟随（三形态各自一套）、最大可移探测、提交、滑动动画。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第七步，
Move 整块再切第二刀；移动核心在 gui/move.py）。拖拽是「按住滑块跟着鼠标走、
松手落位」那一套：方形/三角/米字各有一个 _init_*_drag_follow（几何不同），
共用 _probe_max_cells/_commit_drag_move/_drag_slide。依赖 math、tri_key、
MI_DIRECTIONS、op_log，均为模块级 import。
"""
import math

from game_mi import DIRECTIONS as MI_DIRECTIONS
from game_triangle import tri_key

from gui import op_log


class DragMixin:
    """鼠标拖拽（原 GUI.py 内联代码，整体搬迁）。"""

    def clear_drag_follow(self):
        """清除拖拽跟随状态，恢复滑块原始位置与选中态。"""
        if not self.drag_following:
            return
        auto_deselect = self.drag_follow_auto_deselect
        self.drag_following = False
        self.drag_follow_block = None
        self.drag_follow_start_pos = None
        self.drag_follow_start_screen = None
        self.drag_follow_offset = (0.0, 0.0)
        self.drag_follow_max_cells = 0
        self.drag_follow_auto_deselect = False
        self.drag_follow_gap = None
        self.drag_follow_direction = None
        self.drag_follow_step = 0
        self.drag_follow_invalid = False
        # 单次触控发起的跟随：拖动结束后自动取消选中（与旧 _drag_slide 行为一致）
        # 两次触控（预选缝隙）发起时不取消，保留缝隙选中以便继续操作
        if auto_deselect and getattr(self, 'selected_gap', None):
            self.selected_gap = None
            self.selected_block = None
            for b in self.game.blocks:
                b.be_opted = False
            self._bump_move_session()

    def _init_drag_follow(self, block, dx, dy):
        """初始化拖拽跟随：确定缝隙、选中滑块组、记录初始位置。

        返回 True 如果成功进入跟随状态，False 否则。
        """
        # 已在跟随中则不重复初始化
        if self.drag_following:
            return False
        # 正在动画中不允许进入跟随
        if self.animating:
            if getattr(self, 'mi_mode', False):
                # 米字格提交移动只有拖拽和虚拟键盘两条路，两条都在动画期间
                # 被拒；静默返回在玩家看来就是「拖了没反应」，必须明说
                self.macro_notify_msg = "动画播放中，无法移动"
                self.macro_notify_timer = 90
            return False
        # 宏执行中不允许
        if getattr(self, 'macro_executing', False):
            return False
        # 米字格：位移向量投到已选缝隙的切向定方向（不猜 8 区扇区）
        if getattr(self, 'mi_mode', False):
            return self._init_mi_drag_follow(block, dx, dy)
        # 三角形密铺：手勢向量投影吸附到 6 個晶格方向（B2）
        if getattr(self, 'triangle_mode', False):
            return self._init_triangle_drag_follow(block, dx, dy)

        gap = self.selected_gap
        if gap is None:
            # 单次触控：8 区角度直接判定
            if not getattr(self, 'control_single_touch', True):
                return False
            import math
            angle = math.degrees(math.atan2(-dy, dx)) % 360
            sector = int(angle // 45) % 8
            GAP_SEQ = ['d', 'l', 'r', 'd', 'u', 'r', 'l', 'u']
            DIR_SEQ = ['r', 'u', 'u', 'l', 'l', 'd', 'd', 'r']
            gap_abbr = GAP_SEQ[sector]
            move_dir = DIR_SEQ[sector]
            r, c = block.location
            if gap_abbr == 'd':
                gap_type, line = 'h', r
            elif gap_abbr == 'u':
                gap_type, line = 'h', r - 1
            elif gap_abbr == 'l':
                gap_type, line = 'v', c - 1
            else:  # 'r'
                gap_type, line = 'v', c
            self.selected_gap = (gap_type, line)
        else:
            # 两次触控：沿已有缝隙的主方向轴
            if not getattr(self, 'control_two_touch', True):
                return False
            gap_type, line = gap
            if gap_type == 'h':
                move_dir = 'r' if dx > 0 else 'l'
            else:  # v
                move_dir = 'd' if dy > 0 else 'u'

        # 缝隙必须落在棋形内部
        gap_valid = (self.game.is_valid_h_line(line) if gap_type == 'h'
                     else self.game.is_valid_v_line(line))
        if not gap_valid:
            self.selected_gap = None
            self.selected_block = None
            for b in self.game.blocks:
                b.be_opted = False
            self.macro_notify_msg = "缝隙在棋形外沿：整体移动所有滑块没有意义"
            self.macro_notify_timer = 120
            self.clear_drag_follow()
            return False

        # 选中包含起点滑块的连通组
        self.game.opt(gap_type, line, block)
        self.selected_block = block
        dir_map = {'r': 'd', 'u': 'w', 'l': 'a', 'd': 's'}
        direction = dir_map[move_dir]

        # 记录初始位置，进入跟随状态
        self.drag_following = True
        self.drag_follow_block = block
        self.drag_follow_start_pos = list(block.location)
        self.drag_follow_start_screen = None  # 由 events.py 传入
        self.drag_follow_offset = (0.0, 0.0)
        self.drag_follow_gap = (gap_type, line)
        self.drag_follow_direction = direction
        self.drag_follow_step = 0
        self.drag_follow_invalid = False
        # 无预选缝隙（gap is None）= 单次触控发起 → 结束时需自动取消选中
        self.drag_follow_auto_deselect = (gap is None)
        # 探测本方向可达上限：跟随期间棋盘状态不变，只需探测一次
        self.drag_follow_max_cells = self._probe_max_cells(direction)
        return True

    def _init_mi_drag_follow(self, block, dx, dy):
        """米字格的拖拽跟随：把「按住并拖动」的位移向量投到已选缝隙的切向。

        两次触控的第一下已经选定了缝隙，所以这里既不必像方形那样猜 8 区
        扇区，也不必像三角版那样反推「缝隙线穿过手指」——只问一件事：位移
        向量投影到选中缝隙的切向后，符号落在正的一侧还是负的一侧（也就是
        位移落在法线的哪一侧）。正侧 → 该族正方向字母，负侧 → 负方向字母。

        纯法向拖动（切向投影落在瞄准容差里）→ 不进跟随，交回点击语义：那一
        手只是选中滑块组，方向留给虚拟键盘。这正是「不做单次触控」的代价：
        一次触控要在 8 个方向里猜一个，误触面大；两次触控只要区分法线两侧。

        dx/dy 是自按下点起算的屏幕像素。偏移按「一步的分量」记进
        drag_follow_offset（格坐标，可为小数），拖拽预览与松手提交共用同一
        份数据，不再另设锚点。
        """
        gap = getattr(self, 'selected_gap', None)
        if gap is None:
            # 米字格没有单次触控这条捷径：没有预选缝隙就无切向可投影
            return False
        gap_type, line = gap
        axes = self.MI_GAP_AXES.get(gap_type)
        if axes is None:
            return False
        tangent, _normal, pos_dir, neg_dir = axes
        t_len = math.hypot(*tangent)
        # 切向位移（屏幕像素）。容差与 gap_at 同源（1/12 格、最小 3px）：
        # 比这更小的切向分量与瞄准噪声同量级，作不得数
        tan_px = (dx * tangent[0] + dy * tangent[1]) / t_len
        tol = max(3.0, self._mi_view().cell_size * self.zoom / 12.0)
        if abs(tan_px) <= tol:
            op_log.log('mi_drag_reject', gap=[gap_type, line],
                       why='no_tangent', tan_px=round(tan_px, 2),
                       tol=round(tol, 2))
            return False
        direction = pos_dir if tan_px > 0 else neg_dir
        # 选中的缝可能在这一手之前就失效（错位态的半整数横竖缝会整条切进
        # 块里）。失效时清掉选中态，否则 opt 会静默不选组，玩家以为选上了
        if not self.game.is_valid_gap(gap_type, line):
            self.selected_gap = None
            self.selected_block = None
            for b in self.game.blocks:
                b.be_opted = False
            self.macro_notify_msg = (
                f"这条缝选不动（错位态切在块里）：{self._mi_hv_left(gap_type)}")
            self.macro_notify_timer = 120
            return False

        self.selected_gap = (gap_type, line)
        self.selected_block = block
        self.game.opt(gap_type, line, block)

        self.drag_following = True
        self.drag_follow_block = block
        self.drag_follow_start_pos = list(block.location)
        self.drag_follow_start_screen = None  # 由 events.py 传入
        self.drag_follow_offset = (0.0, 0.0)
        self.drag_follow_gap = (gap_type, line)
        self.drag_follow_direction = direction
        self.drag_follow_step = 0
        self.drag_follow_invalid = False
        # 米字格一定带着预选缝隙进来，不存在单次触控那种「结束自动取消选中」
        self.drag_follow_auto_deselect = False
        # 探测本方向可达上限：跟随期间棋盘状态不变，只需探测一次
        self.drag_follow_max_cells = self._probe_max_cells(direction)
        op_log.log('mi_drag_start', gap=[gap_type, line], dir=direction,
                   tan_px=round(tan_px, 1),
                   max_cells=self.drag_follow_max_cells)
        return True

    def _init_triangle_drag_follow(self, block, dx, dy):
        """三角形密鋪的拖拽跟隨：把手勢向量投影吸附到 6 個晶格方向之一。

        這裡刻意不枚舉「扇區」：只算手勢向量與每個晶格方向螢幕單位向量的
        點積，取最大者。因此日後形狀改成 12 向，只需擴充 game_triangle
        的 DIRECTIONS / DIRECTION_SCREEN 兩張表，互動代碼一行不改。

        方向鎖定後，縫隙線交給 game.resolve_drag（「縫隙線穿過手指」規則，
        無效時外推鄰近線），並把探到的最大格數記下來供夾緊用。
        """
        from game_triangle import DIRECTION_SCREEN, tri_key

        # 反向拖動（對六個方向的投影全為負）→ 不進入跟隨，交回點擊語義
        best_letter = None
        best_dot = 0.0
        for letter, (sx, sy) in DIRECTION_SCREEN.items():
            dot = dx * sx + dy * sy
            if dot > best_dot:
                best_dot = dot
                best_letter = letter
        if best_letter is None:
            return False

        gap = getattr(self, 'selected_gap', None)
        if gap is None:
            if not getattr(self, 'control_single_touch', True):
                return False
        else:
            if not getattr(self, 'control_two_touch', True):
                return False

        # 先用 1 格探路：確定方向可行、並拿到實際使用的縫隙線
        positions, gap_type, line, reason, _n = self.game.resolve_drag(
            tri_key(block), best_letter, 1)
        if not positions:
            self.macro_notify_msg = {
                'no_move': "这个方向滑不动（被其它滑块挡住或会断开）",
                'no_block': "滑动失败：找不到起始滑块",
            }.get(reason, "这个方向滑不动")
            self.macro_notify_timer = 90
            return False

        self.selected_gap = (gap_type, line)
        self.selected_block = block
        self.game.opt(gap_type, line, block)

        self.drag_following = True
        self.drag_follow_block = block
        self.drag_follow_start_pos = list(block.location)
        self.drag_follow_start_screen = None  # 由 events.py 传入
        # 三角跟隨偏移以斜座標 (di, dj) 記錄，與方形同一個槽位
        self.drag_follow_offset = (0.0, 0.0)
        self.drag_follow_gap = (gap_type, line)
        self.drag_follow_direction = best_letter
        self.drag_follow_step = 0
        self.drag_follow_invalid = False
        # 無預選縫隙 = 單次觸控發起 → 結束時自動取消選中
        self.drag_follow_auto_deselect = (gap is None)
        self.drag_follow_max_cells = self._probe_max_cells(best_letter)
        return True

    def _probe_max_cells(self, direction: str) -> int:
        """探测沿 direction 可连续推进的最大格数，向下取整到 current_step 的整数倍。

        跟随期间棋盘状态不变，故只需在进入跟随时探测一次。
        """
        limit = 64  # 安全上限，防止异常情况下死循环
        reach = 0
        while reach < limit:
            _, reason = self.game.try_move_ex(direction, reach + 1)
            if reason != '':
                break
            reach += 1
        step_size = max(1, self.current_step)
        return (reach // step_size) * step_size

    def _commit_drag_move(self):
        """提交拖拽跟随移动：根据夹紧后的偏移计算步数并执行移动。"""
        if not self.drag_following:
            return
        # 跟随期间若已经有一步在播（按住左键时另一只手按了方向键），提交
        # 会替换掉正在播的动画 → 只收尾，不移动
        if self.animating:
            self.clear_drag_follow()
            return
        direction = self.drag_follow_direction

        # 偏移已在跟随期间夹紧到 [0, drag_follow_max_cells]，此处直接取用（单一数据源）
        # max(0.0, ...) 为防御：负偏移（反向拖过起点）一律视为不移动，绝不产生反向位移
        dr, dc = self.drag_follow_offset
        # 取 max 而非 abs 之和：方形四向必然只有一個分量非零（兩者等價），
        # 而三角六向中有對角方向（如 w=(-1,+1)），沿該方向走 t 格時兩個分量
        # 都等於 t，只有 max 能正確還原步數
        cells = max(0.0, abs(dr), abs(dc))
        if getattr(self, 'mi_mode', False) and self.drag_follow_direction:
            # 米字格一「格」在 (行, 列) 上的分量：橫豎 = 1、斜向 = ½。偏移量
            # 按分量記，還原成格數要除掉它（不除的話斜向拖一格只能走半程）
            dr_u, dc_u = MI_DIRECTIONS[self.drag_follow_direction]
            cells /= max(abs(dr_u), abs(dc_u))
        # 取整用 int(x + 0.5)（等价 floor），规避 round() 的银行家舍入；再量化到 current_step 整数倍
        step_size = max(1, self.current_step)
        step = int(cells / step_size + 0.5) * step_size

        # 拖拽接续：动画起点接到松手那刻的跟随位置，不再从起点重播一遍
        # （否则松手瞬间整组会跳回原位再滑一次，见 animation._apply_drag_origin）
        self._drag_anim_origin = (dr, dc)

        # 循环递减：从最大合法步长开始，逐次减少 step_size，找到第一个可接受的值（兜底）
        moved = False
        while step > 0:
            moved = self.move_selected_blocks(direction, step)
            if moved:
                break
            step -= step_size

        # S1-3：越界松手 → 撞墙回弹（仅增强模式）。记录被选中切片，沿越界方向抖一下。
        # 注意：此刻 drag_follow_invalid 仍为 True（clear_drag_follow 会清掉），be_opted 切片仍在。
        if (not moved and self.drag_follow_invalid
                and getattr(self, 'ui_mode', 'enhanced') == 'enhanced'):
            chosen = [b for b in self.game.blocks if b.be_opted]
            if chosen:
                self._shake_blocks = set(id(b) for b in chosen)
                self._shake_dr = 1 if dr > 0 else (-1 if dr < 0 else 0)
                self._shake_dc = 1 if dc > 0 else (-1 if dc < 0 else 0)
                self._shake_t = 12  # 约 200ms（帧）

        # 清除跟随状态（含 single-touch auto-deselect）
        self.clear_drag_follow()
        # 未移动（或关了动画）时上面的 origin 没人消费，清掉避免污染下一次动画
        self._drag_anim_origin = None

    def _shake_offset(self):
        """S1-3：越界回弹的瞬时像素位移（屏幕坐标）。_shake_t 倒计时归零后返回 (0,0)。"""
        t = getattr(self, '_shake_t', 0)
        if t <= 0:
            return (0.0, 0.0)
        dr, dc = getattr(self, '_shake_dr', 0), getattr(self, '_shake_dc', 0)
        if dr == 0 and dc == 0:
            return (0.0, 0.0)
        # 衰减包络：先正向冲一下再弹回（|sin| × 线性衰减）
        phase = t / 12.0  # 1 → 0
        amp = 6.0 * self.zoom * phase * abs(math.sin(phase * 3.14159))
        return (dr * amp, dc * amp)

    def _move_merge_key(self):
        """当前移动所属「选中会话」标识；None = 不合并。

        宏/求解器播放、标注录制都不合并：前者需要逐步留档，后者要求
        history 与录制步一一对应（否则会把录制起点的快照就地改写）。
        三角形密铺同样不合并：合并快照的逐步重播（expand_snapshot_moves /
        cells_to_snapshot）按方形 2-tuple 格 + 0/1 矩陣寫死，三角的 2-bit
        菱形胞沒有對應實作；不合并則每步一條快照，撤回/重做按步進行。
        """
        if getattr(self, 'macro_executing', False):
            return None
        if getattr(self, '_ann_recording', False):
            return None
        if getattr(self, 'triangle_mode', False):
            return None
        if getattr(self, 'mi_mode', False):
            return None
        return getattr(self, '_move_session_id', 0)

    def _drag_slide(self, block, dx, dy):
        """拖拽滑动：根据拖拽位移，自动确定缝隙/方向并执行一次滑动。

        - 已有选中缝隙（two_touch 模式）：沿用缝隙，按主方向轴滑动；
        - 无选中缝隙（single_touch 模式）：按 8 区角度判定缝隙（对齐 web touch-gesture.md）。
        - 单次触控会在滑动后清空选中。
        返回是否真正移动。
        """
        # 米字格不走这条 8 区角度路径：滑块是按 (r, c, q) 三元素标识的，
        # 角度扇区只对方形两坐标成立。拖拽有专门入口（_init_mi_drag_follow，
        # 把位移向量投到已选缝隙的切向定方向），能走到这里说明跟随便没起来
        if getattr(self, 'mi_mode', False):
            self._mi_blocked('拖拽', '先点选缝隙，再按住滑块拖动')
            return False
        # 动画播放中：上一手的落点还没提交，此时再移一次会把正在播的动画
        # 整组替换掉（起点被改写、上一手被悄悄丢掉），画面表现为「滑块
        # 自己往回滑了一格」。虚拟键盘早有这道闸门（gui/virtual_keyboard.py
        # 的「动画播放中，无法移动」），鼠标这条漏了——松手时 st['moved']
        # 已置位（跟随便初始化失败），于是每一次落在动画窗口里的点击都会
        # 凭空多走一步。
        if self.animating:
            self.macro_notify_msg = "动画播放中，无法移动"
            self.macro_notify_timer = 90
            return False
        # 三角形密铺有自己的跟随入口（_init_triangle_drag_follow）：这条
        # 8 区角度 + is_valid_h_line/v_line 全是方形两坐标的解法，三角棋盘
        # 上这两个方法根本不存在。跟随没起来时（方向滑不动）回退到这里，
        # 只会崩或凭空移一步
        if getattr(self, 'triangle_mode', False):
            return False
        gap = self.selected_gap
        if gap is None:
            # 单次触控：8 区角度直接判定
            if not getattr(self, 'control_single_touch', True):
                return False
            import math
            angle = math.degrees(math.atan2(-dy, dx)) % 360
            sector = int(angle // 45) % 8
            # 与 web touch-gesture.md 一致
            GAP_SEQ = ['d', 'l', 'r', 'd', 'u', 'r', 'l', 'u']
            DIR_SEQ = ['r', 'u', 'u', 'l', 'l', 'd', 'd', 'r']
            gap_abbr = GAP_SEQ[sector]
            move_dir = DIR_SEQ[sector]
            r, c = block.location
            if gap_abbr == 'd':
                gap_type, line = 'h', r
            elif gap_abbr == 'u':
                gap_type, line = 'h', r - 1
            elif gap_abbr == 'l':
                gap_type, line = 'v', c - 1
            else:  # 'r'
                gap_type, line = 'v', c
            self.selected_gap = (gap_type, line)
        else:
            # 两次触控：沿已有缝隙的主方向轴
            if not getattr(self, 'control_two_touch', True):
                return False
            gap_type, line = gap
            if gap_type == 'h':
                move_dir = 'r' if dx > 0 else 'l'
            else:  # v
                move_dir = 'd' if dy > 0 else 'u'

        # 缝隙必须落在棋形内部（不在边界盒外沿）：外沿缝隙会让 opt() 把「同一侧」
        # 判成覆盖全部滑块，选中后整体平移（形状不变）没有意义 → 拒绝本次滑动
        gap_valid = (self.game.is_valid_h_line(line) if gap_type == 'h'
                     else self.game.is_valid_v_line(line))
        if not gap_valid:
            self.selected_gap = None
            self.selected_block = None
            for b in self.game.blocks:
                b.be_opted = False
            self.macro_notify_msg = "缝隙在棋形外沿：整体移动所有滑块没有意义"
            self.macro_notify_timer = 120
            return False

        # 选中包含起点滑块的连通组
        self.game.opt(gap_type, line, block)
        self.selected_block = block
        dir_map = {'r': 'd', 'u': 'w', 'l': 'a', 'd': 's'}
        direction = dir_map[move_dir]

        moved = self.move_selected_blocks(direction)
        # 单次触控：无论滑动成功还是失败，都清空临时选中（缝隙/滑块组高亮），
        # 成功时下一次拖拽是全新操作；失败时不留选中残影
        if gap is None and getattr(self, 'control_single_touch', True):
            self.selected_gap = None
            self.selected_block = None
            for b in self.game.blocks:
                b.be_opted = False
            # 选中已清空 → 结束本次选中会话（下一次拖拽另起快照）
            self._bump_move_session()
        return moved

