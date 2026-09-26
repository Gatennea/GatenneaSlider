# -*- coding: utf-8 -*-
"""
标注模式 Mixin — 人工录制「填洞 / 收敛空位」示范步骤数据集

独立于练习/竞速/创造的全新模式，隐藏入口：同时按住 B / Z / M / S 四个键。

学习起点来源：
    ① 存档中段（打开任意 save/*.json → 快照步进器选一个状态）
    ④ 当前棋盘状态

（原「② 随机生成 / ③ 手动构造」已独立为「创造模式」——模式开关第三态，
  见 create_mode：造好的棋形直接成为当前谜题，不再进标注流程。）

录制流程：
    1. 逐格标「目标空位」（点窗口内的空格，可多格，增删自由）→ 程序跟踪它
    2. 逐格标「要填入的凸起」（点滑块，标记须始终在滑块上）→ 程序跟踪它
    3. 按下「开始跟踪执行」→ 之后的每一步真实移动都被录制
       （阶段 A / B / A′ 随时可切，标志共轭 ABA′ 的当前阶段）
    4. 空位数相对起点净减 ≥ 1 后，按「结束并保存」写盘
    5. 撤销自动同步（撤掉废步即从录制中去掉）；跟踪点可用「重选」修正

跟踪（相对传播）：
    凸起标记看「所在滑块」有没有被移动带走；空位标记按幻影滑块传播
    —— 被移动组填上视为完成；否则若随滑动组让出的空格平移就跟过去；
    近似逻辑不完美处用「重选空位/凸起」人工修正。

输出（JSONL 每行一个 episode，可直接查看）：
    save/标注样本/annotations.jsonl
    save/标注样本/progress.json
"""

import os
import json
import math
import random
import time
import pygame

from game import Block
from game_mi import blocks_from_cells as mi_blocks_from_cells  # noqa: E402
from game_triangle import blocks_from_cells as tri_blocks_from_cells  # noqa: E402
from history import GameHistory, expand_snapshot_moves  # noqa: F401  （语义参照，不直接实例化）

# ---------------------------------------------------------------------------
# 纯函数工具（独立于 GUI，可 headless 测试）
# ---------------------------------------------------------------------------
_DIR_DELTA = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}

# 标注模式隐藏入口：同时按住 B / Z / M / S 四个字母键（「标注模式」拼音首字母）
_ANN_ENTRY_KEYS = frozenset({pygame.K_b, pygame.K_z, pygame.K_m, pygame.K_s})


def dir_delta(direction, step):
    dr, dc = _DIR_DELTA[direction]
    return dr * step, dc * step


def infer_side(gap_type, gap_line, moved_positions):
    """由移动组位置推断缝隙的哪一侧被选中（与 export_human_data 一致）。"""
    rows = [p[0] for p in moved_positions]
    cols = [p[1] for p in moved_positions]
    if gap_type == 'v':
        return 'right' if all(c > gap_line for c in cols) else 'left'
    return 'below' if all(r > gap_line for r in rows) else 'above'


def snapshot_abs_coords(matrix, bounds):
    """快照 matrix+bounds → 绝对坐标集合。"""
    min_row = bounds.get('min_row', 0)
    min_col = bounds.get('min_col', 0)
    coords = set()
    for r, row in enumerate(matrix):
        for c, v in enumerate(row):
            if v:
                coords.add((min_row + r, min_col + c))
    return coords


def window_void_metrics(coords, m, n, step):
    """当前状态的空位数指标（与求解器语义一致）。

    返回 dict：{overlap, void_block_count, score, bbox}。
    void_block_count = m*n - overlap（目标窗口内缺失格数）。
    """
    from solver.ml.gather_solver import find_best_window
    if not coords:
        return {'overlap': 0, 'void_block_count': m * n,
                'score': 0.0, 'bbox': (0, 0)}
    r0, c0, (rh, cw), overlap = find_best_window(coords, m, n, step)
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    return {
        'overlap': overlap,
        'void_block_count': m * n - overlap,
        'score': overlap / float(m * n),
        'bbox': (max(rs) - min(rs) + 1, max(cs) - min(cs) + 1),
    }


def _target_region_of(coords, m, n, step):
    """当前状态的 mod-aware 目标窗口 (r0, c0, (rh, cw))，None=失败。"""
    from solver.ml.gather_solver import find_best_window
    if not coords:
        return None
    try:
        r0, c0, (rh, cw), _ = find_best_window(coords, m, n, step)
        return r0, c0, (rh, cw)
    except Exception:
        return None


def _cut_separates(a, b, gap_type, gap_line):
    """与 game.SliderMatrix.opt 一致：跨缝隙的两格视为不连通。"""
    if gap_type == 'h':
        return (a[0] <= gap_line) != (b[0] <= gap_line)
    if gap_type == 'v':
        return (a[1] <= gap_line) != (b[1] <= gap_line)
    return False


def _component_over(occ, seed, extra, gap_type, gap_line):
    """DFS：在 occ|extra 上、不跨缝隙地从 seed 连通扩散。

    返回被访问到的坐标集合（与 game.opt 的选中组判定一致）。
    """
    occ_all = set(occ) | {tuple(e) for e in extra}
    seen = set()
    stack = [tuple(seed)]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        r, c = cur
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nxt = (r + dr, c + dc)
            if (nxt in occ_all and nxt not in seen
                    and not _cut_separates(cur, nxt, gap_type, gap_line)):
                stack.append(nxt)
    return seen


def move_group_geometry(moved_positions, direction, step):
    """一步移动的几何信息。

    history 快照记录的 moved_positions 是「移动前」的位置集合（GUI 在
    commit_move 之前读取 b.location），故：
        delta : (dr, dc) 整体平移量（本游戏一次只平移一组，方向一致）
        s_old : 移动组移动前占用的位置集合（= moved_positions 本身）
        new_m : 移动后的位置集合（= s_old + delta）
    """
    delta = dir_delta(direction, step)
    dr, dc = delta
    s_old = {tuple(p) for p in moved_positions}
    new_m = {(p[0] + dr, p[1] + dc) for p in s_old}
    return delta, s_old, new_m


def advance_anchor_cells(prev_cells, moved_positions, direction, step,
                         anchor_cells):
    """凸起标记：跟着所在滑块走，永远不需要人工重选。

    移动前锚点格若位于被移动的滑块上（∈ moved_positions），就整体平移
    delta（仍牢牢贴在同一滑块上）；所在滑块没动 → 原位不动。返回新坐标。
    """
    if not anchor_cells or not moved_positions:
        return sorted(anchor_cells) if anchor_cells else []
    delta, s_old, _ = move_group_geometry(moved_positions, direction, step)
    out = []
    for a in anchor_cells:
        a = tuple(a)
        if a in s_old:
            out.append((a[0] + delta[0], a[1] + delta[1]))
        else:
            out.append(a)
    return sorted(out)


def advance_void_cells(prev_cells, cur_cells, moved_positions, gap_type,
                       gap_line, direction, step, void_cells):
    """空位标记：幻影滑块模型（相对传播）。

    规则（近似，必要时由「重选空位」人工修正）：
        1. 该格被移动组填上（∈ new_m）→ 视为完成（从标记中移除）；
        2. 否则把空位当作一颗幻影滑块：若把它加入移动组前状态后，它仍
           属于「被选中滑动的那一组」（与移动组同侧且连通、且没有把别的
           组件桥接进来），并且它随整体平移的落点 v+delta 正好落在移动组
           让出的空格上，就把标记平移到该落点（空位相对滑块保持不动）；
        3. 其余情况保持原位。

    返回 (cells, filled_count, status)：
        cells : 剩余被跟踪的空位（保持原格且仍为空的空位，异常则置 lost）
        filled_count : 本步被填掉的格数
        status : 'ok' / 'filled'（全部填完）/ 'lost'（出现矛盾需人工修正）
    """
    void_cells = [tuple(v) for v in (void_cells or [])]
    if not void_cells or not moved_positions:
        return sorted(void_cells), 0, ('ok' if void_cells else 'filled')
    delta, s_old, new_m = move_group_geometry(moved_positions, direction, step)
    dr, dc = delta
    vacated = s_old - new_m           # 移动组真正让出的空格（落点候选）
    out = []
    filled = 0
    seed = next(iter(vacated)) if vacated else next(iter(s_old), None)
    for v in void_cells:
        if v in new_m:
            filled += 1               # 被填上 → 完成
            continue
        if seed is not None and (v[0] + dr, v[1] + dc) in vacated:
            # 幻影检测：v 若作为滑块加入，是否只属于本次移动的那一组
            comp = _component_over(prev_cells, seed, (), gap_type, gap_line)
            full = _component_over(prev_cells, seed, [v], gap_type, gap_line)
            if v in full and full - {v} == comp:
                out.append((v[0] + dr, v[1] + dc))
                continue
        out.append(v)
    if filled and not out:
        return [], filled, 'filled'
    bad = [c for c in out if c in set(cur_cells)]
    if bad:
        return out, filled, 'lost'   # 保持原格的标记竟然被占 → 需要人工修正
    return sorted(out), filled, 'ok'


def holes_and_protrusions(coords, m, n, step):
    """目标窗口内的洞 + 窗外凸起（region 由 find_best_window 现算）。"""
    from solver.ml.hole_detector import detect_holes
    region = _target_region_of(coords, m, n, step)
    if region is None:
        return [], [], None
    return detect_holes(coords, m, n, step, region=region)


# ---------------------------------------------------------------------------
# 标注模式 Mixin
# ---------------------------------------------------------------------------
class AnnotationMixin:
    """标注模式（录制数据结构 + GUI 流程）"""

    # 布局
    _ANN_PAD = 10
    _ANN_BAR_H = 46

    @property
    def create_mode(self):
        """创造模式（「模式」开关第三态）：由 game_mode 派生，避免两处状态不一致。"""
        return getattr(self, 'game_mode', '') == 'create'

    def _ann_init_state(self):
        """初始化标注模式状态（GUI.__init__ 中调用）。"""
        self.annotation_mode = False        # 模式总开关
        self._ann_entry_keys = set()        # 已按下的隐藏入口键（B/Z/M/S 判定）
        self._ann_view = 'home'             # home/target/recording
        self._ann_msg = ''
        self._ann_msg_timer = 0
        # 子对话框
        self._ann_sub_dialog = None         # None / 'gen' / 'preview' / 'build'
        self._ann_gen_fields = {'m': '', 'n': '', 'step': '',
                                'hole': '1', 'dent': '0'}
        self._ann_gen_active = 'm'
        self._ann_gen_error = ''
        # 手动构造对话框状态
        self._ann_build_fields = {'m': '', 'n': '', 'step': ''}
        self._ann_build_active = 'm'
        self._ann_build_error = ''
        self._ann_build_coords = set()      # 画布上点出的滑块位置（全局坐标，各形态完整元组）
        self._ann_build_numbered = False    # 进入构造时是否为数字谜题（编号栈只对它生效）
        self._ann_build_numbers = {}        # 位置元组 -> number（仅 numbered，重建时写回 Block）
        self._ann_build_num_stack = []      # 取下一块把编号压栈；放一块弹栈顶（后进先出）
        self._ann_build_dialog_rect = None
        self._ann_build_field_rects = {}
        self._ann_build_cell_size = 0
        self._ann_build_ok_btn = None
        self._ann_build_reset_btn = None
        self._ann_build_clear_btn = None
        self._ann_build_cancel_btn = None
        # 输入框记忆（config/annotation_inputs.json，随机生成 + 手动构造共用）
        self._ann_saved_inputs = None
        self._ann_preview_data = None
        self._ann_preview_idx = 0
        self._ann_pending_open = False
        self._ann_preview_src = None
        self._ann_file_name = None
        self._ann_save_rel_name = None
        # 会话（target/recording 共享）
        self._ann_base_idx = None           # 录制起点 = history_index
        self._ann_void0 = None              # 会话选中的空位格集（重选会更新）
        self._ann_anchor0 = None            # 会话选中的凸起格（重选会更新）
        self._ann_start_void = None         # 录制起点时的空位快照（写盘用）
        self._ann_start_anchor = None       # 录制起点时的凸起快照（写盘用）
        self._ann_pick = None               # 'void' / 'anchor' / None
        self._ann_recording = False
        self._ann_phase = 'A'               # A / B / A'
        self._ann_phase_toggle = False
        self._ann_last_hi = None
        self._ann_steps = {}                # idx -> 该步的跟踪快照记录
        self._ann_track_void = None         # 当前跟踪的空位格集
        self._ann_track_anchor = None       # 当前跟踪的凸起格
        self._ann_track_status = 'none'     # none/ok/filled/lost
        self._ann_base_metrics = None
        self._ann_cur_metrics = None
        self._ann_source_type = 'current'
        self._ann_source_desc = ''
        # 按钮区域（每次 draw 重建，供事件命中）
        self._ann_btn_rects = {}
        # 布局记忆
        self._ann_bar_rect = None

    # ------------------------------------------------------------------
    # 隐藏入口：同时按住 B / Z / M / S
    # ------------------------------------------------------------------
    def _ann_track_toggle_keys(self, event):
        """隐藏入口：同时按住 B / Z / M / S 四个字母键。

        自行累计按下的键（不依赖修饰键状态，避免左右修饰位在某些平台/驱动上
        不可靠）；四键齐全时触发并消费该次按键，因此最后按下的键（可能是 s）
        不会漏到普通快捷键去（否则会误触发向下滑动）。
        """
        if event.type == pygame.KEYUP:
            self._ann_entry_keys.discard(event.key)
            return False
        if event.type != pygame.KEYDOWN or event.key not in _ANN_ENTRY_KEYS:
            return False
        self._ann_entry_keys.add(event.key)
        if _ANN_ENTRY_KEYS <= self._ann_entry_keys:
            self._ann_entry_keys.clear()
            self._ann_toggle_mode()
            return True
        return False

    def _ann_toggle_mode(self):
        """模式总开关（隐藏入口 B/Z/M/S 触发）。"""
        if self.timer_state == 'running':
            self._ann_notify('计时进行中无法进入标注模式')
            return
        if not self.annotation_mode:
            # 与创造模式互斥：进标注模式即退出创造
            if self.create_mode:
                self.game_mode = 'practice'
            self.annotation_mode = True
            self._ann_view = 'home'
            self._ann_pending_open = False
            self._ann_preview_data = None
            self._ann_notify('标注模式已开启')
        else:
            if self._ann_sub_dialog == 'build':
                self._ann_build_cancel()
                self.annotation_mode = False
                self._ann_notify('标注模式已关闭')
            elif self._ann_sub_dialog is not None:
                self._ann_close_sub_dialog()
                self.annotation_mode = False
                self._ann_notify('标注模式已关闭')
            elif self._ann_view in ('target', 'recording'):
                self._ann_notify('请先结束/放弃当前标注再退出标注模式')
            else:
                self.annotation_mode = False
                self._ann_notify('标注模式已关闭')

    def _ann_notify(self, text):
        self.macro_notify_msg = text
        self.macro_notify_timer = 150

    # ------------------------------------------------------------------
    # 输入法冲突 / 模态对话框守卫：这些状态交给原有对话框处理
    # ------------------------------------------------------------------
    def _ann_modal_conflict(self):
        return (self.file_dialog.active
                or getattr(self, 'show_custom_dialog', False)
                or getattr(self, 'show_help', False)
                or getattr(self, 'show_settings_dialog', False)
                or getattr(self, 'show_macro_manager_dialog', False)
                or getattr(self, 'show_macro_name_dialog', False)
                or getattr(self, 'macro_selecting_base', False))

    def handle_annotation_event(self, event):
        """标注/创造模式事件处理（GUI.handle_events 最先询问），返回 True=已消费。

        两种模式都关闭时只检测标注模式的隐藏入口（B/Z/M/S），其余事件放行。
        """
        active = getattr(self, 'annotation_mode', False) or self.create_mode
        if not active:
            return self._ann_track_toggle_keys(event)

        # 标注模式下：隐藏入口仍可再触发（开启/关闭）
        if getattr(self, 'annotation_mode', False) and self._ann_track_toggle_keys(event):
            return True

        # 其他模态对话框打开时：不抢事件（隐藏入口已在上方处理）
        if self._ann_modal_conflict():
            return False

        if event.type == pygame.KEYDOWN:
            if self._ann_sub_dialog == 'gen':
                return self._ann_gen_dialog_event(event)
            if self._ann_sub_dialog == 'build':
                return self._ann_build_dialog_event(event)
            if self._ann_sub_dialog == 'preview':
                return self._ann_preview_dialog_event(event)
            if event.key == pygame.K_ESCAPE:
                self._ann_escape()
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos
            # 顶栏菜单区（含已展开的下拉菜单）不属于棋盘拾取范围：
            # 这些点击应放行给常规菜单栏处理，而不是被当成「标空位/凸起」
            if y < self.menu_bar_height:
                return False
            if (getattr(self, 'show_file_menu', False) or
                    getattr(self, 'show_edit_menu', False) or
                    getattr(self, 'show_puzzle_menu', False) or
                    getattr(self, 'show_macro_menu', False) or
                    getattr(self, 'show_settings_menu', False)):
                # 有菜单展开时，点击交给常规下拉菜单处理，避免抢事件
                return False
            if self._ann_sub_dialog == 'gen':
                return self._ann_gen_dialog_click(x, y)
            if self._ann_sub_dialog == 'build':
                return self._ann_build_dialog_click(x, y)
            if self._ann_sub_dialog == 'preview':
                return self._ann_preview_dialog_click(x, y)
            # 面板按钮（仅当点在面板内）
            if self._ann_bar_rect and self._ann_bar_rect.collidepoint(x, y):
                return self._ann_click_button(x, y) or True
            # 取点模式下，棋盘点击用于选/改跟踪点
            if self._ann_pick and self._ann_view in ('target', 'recording'):
                return self._ann_try_pick_at(x, y)
            # 目标视图：空格=标空位 / 滑块=标凸起，逐格增删；
            # 已就绪时仍可微调，点好后按「开始跟踪执行」
            if self._ann_view == 'target' and not self._ann_recording:
                return self._ann_try_pick_at(x, y)
        return False

    def _ann_escape(self):
        """ESC：按当前所处场景逐级退出。"""
        if self._ann_sub_dialog is not None:
            self._ann_close_sub_dialog()
        elif self._ann_pick:
            self._ann_pick = None
            self._ann_notify('重选结束，可继续滑动')
        elif self._ann_view == 'recording':
            self._ann_abort('已放弃本次标注（ESC）')
        elif self._ann_view == 'target':
            self._ann_abort('已取消本次标注（ESC）')
        elif self.create_mode:
            self._ann_exit_create()
        else:
            self.annotation_mode = False
            self._ann_notify('标注模式已关闭')

    # ------------------------------------------------------------------
    # 面板按钮
    # ------------------------------------------------------------------
    def _ann_click_button(self, x, y):
        for name, rect in self._ann_btn_rects.items():
            if rect.collidepoint(x, y):
                handler = getattr(self, f'_ann_btn_{name}', None)
                if handler:
                    handler()
                return True
        return False

    def _ann_btn_exit_mode(self):
        self.annotation_mode = False
        self._ann_notify('标注模式已关闭')

    def _ann_exit_create(self):
        """退出创造模式（模式开关回到练习模式）；入口只有 ESC 与切模式。"""
        self._ann_leave_to_home()
        self.game_mode = 'practice'
        self._ann_notify('已退出创造模式（练习模式）')

    # ------------------------------------------------------------------
    # 输入框本地记忆（config/annotation_inputs.json）
    # ------------------------------------------------------------------
    def _ann_inputs_path(self):
        return os.path.join(self.config_dir, 'annotation_inputs.json')

    def _ann_load_inputs(self):
        """读取上次随机生成/手动构造输入框内容；读不到就返回 None。"""
        try:
            with open(self._ann_inputs_path(), 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    def _ann_saved(self, section):
        """section 的记忆 dict：{'m','n','step',...}（字符串，仅含有效整数）。"""
        if self._ann_saved_inputs is None:
            self._ann_saved_inputs = self._ann_load_inputs() or {}
        d = (self._ann_saved_inputs.get(section)
             if isinstance(self._ann_saved_inputs.get(section), dict) else {})
        keys = ['m', 'n', 'step', 'k', 'hole', 'dent']
        out = {}
        for k in keys:
            v = str(d.get(k, '')) if k in d else ''
            if v.lstrip('-').isdigit():
                out[k] = v
        return out

    def _ann_store_inputs(self, section, values):
        """把 section 的输入框内容写回 annotation_inputs.json（本次打开保持）。"""
        self._ann_saved_inputs = self._ann_load_inputs() or {}
        self._ann_saved_inputs[section] = dict(values)
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self._ann_inputs_path(), 'w', encoding='utf-8') as f:
                json.dump(self._ann_saved_inputs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _ann_solved_coords(self, m, n):
        return {(r, c) for r in range(m) for c in range(n)}

    def _ann_btn_from_save(self):
        """① 从存档中段选起点：打开文件对话框。"""
        self.file_dialog.show(mode='open', title='选择存档（中段作起点）',
                              initial_dir=self.save_dir, extensions=['json'])
        self._ann_pending_open = True

    def _ann_btn_random_gen(self):
        """随机生成：打开参数对话框（输入框沿用上次内容）。

        创造模式下生成完直接成为当前谜题；标注模式下则进入选目标。
        三角形/米字格没有随机生成：任何入口只给提示、不开参数对话框。
        """
        if self.triangle_mode or self.mi_mode:
            self._ann_notify('该谜题没有随机生成功能')
            return
        saved = self._ann_saved('gen')
        fall = {'m': self.current_m, 'n': self.current_n,
                'step': self.current_step, 'hole': 1, 'dent': 0}
        self._ann_gen_fields = {
            k: (saved.get(k) if k in saved else str(fall[k]))
            for k in fall
        }
        self._ann_gen_active = 'm'
        self._ann_gen_error = ''
        self._ann_sub_dialog = 'gen'

    def _ann_btn_manual_build(self):
        """手动构造：直接在主棋盘上自由点选。

        进入构造视图后，主棋盘即变成可编辑画布：点空白格放置滑块、
        点已有滑块移除它；改 m/n/step 后按 Enter 重排画布范围。
        底部工具条实时校验并给出「应用（并开始）/ 还原 m×n / 清空 / 退出」。
        创造模式下应用完直接成为当前谜题；标注模式下则进入选目标。
        """
        # 初始 m/n/step 一律取当前谜题，避免沿用上次构造的旧尺寸
        m = self.current_m
        n = self.current_n
        step = self.current_step
        # 备份当前局面：取消构造时可原样恢复（含历史栈、编号与编号栈）
        self._ann_build_backup = {
            'cells': frozenset({self._ann_normalize_build_pos(tuple(b.location))
                                for b in self.game.blocks}),
            'numbers': {self._ann_normalize_build_pos(tuple(b.location)): b.number
                        for b in self.game.blocks if b.number is not None},
            'stack': [],
            'numbered': bool(getattr(self, 'numbered', False)),
            'm': m, 'n': n, 'step': step,
            'history': self.game_history,
        }
        # 参数行按形态给：三角只填边长与等级
        if self.triangle_mode:
            self._ann_build_fields = {'k': str(m), 'step': str(step)}
        else:
            self._ann_build_fields = {
                'm': str(m), 'n': str(n), 'step': str(step),
            }
        self._ann_build_active = 'k' if self.triangle_mode else 'm'
        self._ann_build_error = ''
        # 数字谜题：编号全在盘上（画布初始 = 当前局面），编号栈为空
        self._ann_build_numbered = bool(getattr(self, 'numbered', False))
        self._ann_build_numbers = {
            self._ann_normalize_build_pos(tuple(b.location)): b.number
            for b in self.game.blocks if b.number is not None
        }
        self._ann_build_num_stack = []
        # 以「当前棋盘状态」为基础进入构造，而不是还原态：
        # 画布初始就是当前所有滑块，可直接点格增删、点窗外格补凸起
        coords = {self._ann_normalize_build_pos(tuple(b.location))
                  for b in self.game.blocks}
        self._ann_build_coords = coords
        self.current_m, self.current_n, self.current_step = m, n, step
        self._ann_rebuild_game_from_coords()
        self._ann_sub_dialog = 'build'
        self._ann_view = 'build'
        self.center_map()
        self._ann_notify('构造模式：初始为当前状态，点格放/取滑块，改好参数后按'
                         + ('[应用]' if self.create_mode else '[应用并开始]'))

    def _ann_rebuild_game_from_coords(self):
        """把构造集实时落到主棋盘（不写历史，不打断旧历史）。

        注意：构造过程允许改 m/n/step，而调试面板/求解器/is_solved 都读
        game.m/game.n 与 current_step，故这里必须同步——构造视图中以输入框
        最新有效值为准（点选增删前已校验过参数），否则尺寸修改后仍按旧值计算。
        """
        if getattr(self, '_ann_view', None) == 'build':
            try:
                m, n, step = self._ann_build_param()
                self.current_m, self.current_n, self.current_step = m, n, step
            except ValueError:
                pass  # 输入框暂不合法（如清空中）：沿用上一次有效尺寸
        # 防御：构造集统一规范化（GUI 命中可能带 .0 的 float；米字半整数保留）
        self._ann_build_coords = {
            self._ann_normalize_build_pos(c) for c in self._ann_build_coords}
        # 按形态重建：三角/米字走 blocks_from_cells（计划二 A 的产出），
        # 方形照旧捏 Block；三角还要同步 game.k（m/n 由 current_* 同步）
        if self.triangle_mode:
            k = self.current_m
            self.game.k = k
            self.game.m = k
            self.game.n = k
            blocks = tri_blocks_from_cells(self._ann_build_coords)
        elif self.mi_mode:
            self.game.m = self.current_m
            self.game.n = self.current_n
            blocks = mi_blocks_from_cells(self._ann_build_coords)
        else:
            self.game.m = self.current_m
            self.game.n = self.current_n
            blocks = [Block(list(c))
                      for c in sorted(self._ann_build_coords)]
        # 数字谜题：把「位置 → 编号」一起带上，不再造无编号的 Block
        if self._ann_build_numbered:
            for b in blocks:
                b.number = self._ann_build_numbers.get(tuple(b.location))
        else:
            for b in blocks:
                b.number = None
        self.game.blocks = blocks
        self.game.update_matrix()

    def _ann_normalize_build_pos(self, pos):
        """把构造坐标规范化为形态标准表示。

        方形/三角是整数格坐标；GUI 命中的 get_cell_at_pos / world_to_cell
        可能返回带 .0 的 float（如 (2.0, 2.0)），若原样存进构造集，重建的
        Block 位置变 float，draw_board/update_matrix 的 range() 与矩阵索引
        会直接崩。米字错位态的 B 晶格块坐标可以是半整数，必须保留——
        只有整数分量归一为 int，使集合/字典键与 blocks 位置一致。
        """
        r, c = pos[0], pos[1]
        if self.mi_mode:
            r = int(r) if float(r).is_integer() else r
            c = int(c) if float(c).is_integer() else c
        else:
            r, c = int(r), int(c)
        return (r, c) + tuple(pos[2:])

    def _ann_build_toggle(self, pos):
        """主棋盘点选：增/删一个滑块（吃各形态完整位置元组）并即时刷新状态。

        数字谜题走编号栈：取下一块（移除）把编号压栈，放一块（添加）弹栈顶
        编号写给它；栈空时不允许放。
        """
        pos = self._ann_normalize_build_pos(pos)
        try:
            m, n, step = self._ann_build_param()
        except ValueError as e:
            self._ann_build_error = str(e)
            return
        if self.triangle_mode:
            lo_i, hi_i, lo_j, hi_j, s_up, s_down = \
                self._ann_build_tri_range(m)
            s_bound = s_up if pos[2] else s_down
            if not (lo_i <= pos[0] <= hi_i and lo_j <= pos[1] <= hi_j
                    and pos[0] + pos[1] <= s_bound):
                self._ann_build_error = '点选超出可构造范围'
                return
        else:
            lo_r, hi_r, lo_c, hi_c = self._ann_build_grid(m, n)
            if not (lo_r <= pos[0] <= hi_r and lo_c <= pos[1] <= hi_c):
                self._ann_build_error = '点选超出可构造范围'
                return
        if pos in self._ann_build_coords:
            self._ann_build_coords.discard(pos)
            if self._ann_build_numbered:
                num = self._ann_build_numbers.pop(pos, None)
                if num is not None:
                    self._ann_build_num_stack.append(num)
        else:
            if self._ann_build_numbered:
                if not self._ann_build_num_stack:
                    self._ann_build_error = '没有可用的编号：先取下一个滑块'
                    return
                self._ann_build_numbers[pos] = self._ann_build_num_stack.pop()
            self._ann_build_coords.add(pos)
        self._ann_build_error = ''
        self._ann_rebuild_game_from_coords()

    def _ann_build_cancel(self):
        """取消构造：恢复进入前的局面与历史。"""
        bk = getattr(self, '_ann_build_backup', None)
        if bk is not None:
            self.current_m = bk['m']
            self.current_n = bk['n']
            self.current_step = bk['step']
            # 编号状态一併回复（栈进入前恒空，但按备份原样回）
            self._ann_build_numbered = bk.get('numbered', False)
            cells_n = {self._ann_normalize_build_pos(c) for c in bk['cells']}
            numbers_n = {self._ann_normalize_build_pos(k): v
                         for k, v in (bk.get('numbers') or {}).items()}
            self._ann_build_numbers = dict(numbers_n)
            self._ann_build_num_stack = list(bk.get('stack') or [])
            # 按形态重建（含编号），再让历史快照兜底覆盖
            if self.triangle_mode:
                self.game.k = bk['m']
                self.game.m = bk['m']
                self.game.n = bk['m']
                blocks = tri_blocks_from_cells(cells_n)
            elif self.mi_mode:
                self.game.m = bk['m']
                self.game.n = bk['n']
                blocks = mi_blocks_from_cells(cells_n)
            else:
                self.game.m = bk['m']
                self.game.n = bk['n']
                blocks = [Block(list(c)) for c in sorted(cells_n)]
            if self._ann_build_numbered:
                for b in blocks:
                    b.number = self._ann_build_numbers.get(tuple(b.location))
            else:
                for b in blocks:
                    b.number = None
            self.game.blocks = blocks
            self.game.update_matrix()
            self.game_history = bk['history']
            hi = min(self.game_history.history_index,
                     max(0, len(self.game_history.history) - 1))
            self.game_history.restore_snapshot(self.game, hi)
            self._ann_build_backup = None
        self._ann_sub_dialog = None
        self._ann_view = 'home'
        self._ann_build_error = ''
        self._ann_store_inputs('build', self._ann_build_fields)
        self.center_map()
        self._ann_notify('已取消手动构造')

    def _ann_btn_from_current(self):
        """④ 当前棋盘作为起点。"""
        if self.game.is_solved():
            self._ann_notify('当前已是还原态，请先打乱或准备一个状态')
            return
        self._ann_start_target('current', '当前棋盘状态')

    def _ann_start_target(self, source_type, desc):
        """进入选目标状态（学习起点 = 当前历史位置）。"""
        self._ann_view = 'target'
        self._ann_sub_dialog = None
        self._ann_source_type = source_type
        self._ann_source_desc = desc
        self._ann_base_idx = self.game_history.history_index
        self._ann_void0 = None
        self._ann_anchor0 = None
        self._ann_start_void = None       # 新会话：待开始执行时再快照
        self._ann_start_anchor = None
        self._ann_track_void = None
        self._ann_track_anchor = None
        self._ann_track_status = 'none'
        self._ann_recording = False
        self._ann_phase = 'A'
        self._ann_pick = None               # 目标阶段：点空格=标空位、点滑块=标凸起
        self._ann_last_hi = self.game_history.history_index
        self._ann_steps = {}
        self._ann_notify('点空格标目标空位、点滑块标凸起（逐格增删）')

    # ---- recording 控制 ----
    def _ann_btn_start_exec(self):
        if not self._ann_void0 or not self._ann_anchor0:
            self._ann_notify('请先选中目标空位与凸起')
            return
        self._ann_recording = True
        self._ann_view = 'recording'          # 切换工具栏到录制布局
        self._ann_base_idx = self.game_history.history_index
        self._ann_last_hi = self.game_history.history_index
        self._ann_steps = {}
        # 录制起点快照：此后「重选」只改会话级 _ann_void0/_ann_anchor0，
        # 写盘仍以此刻选中的目标空位/凸起为准
        self._ann_start_void = frozenset(self._ann_void0)
        self._ann_start_anchor = frozenset(self._ann_anchor0)
        self._ann_track_void = frozenset(self._ann_void0)
        self._ann_track_anchor = frozenset(self._ann_anchor0)
        self._ann_track_status = 'ok'
        coords = self._game_coords()
        self._ann_base_metrics = window_void_metrics(coords, self.current_m,
                                                     self.current_n,
                                                     self.current_step)
        self._ann_cur_metrics = dict(self._ann_base_metrics)
        self._ann_pick = None
        self._ann_notify(f'录制中：起点空位 {self._ann_base_metrics["void_block_count"]}'
                         f'（起点历史步 {self._ann_base_idx}）')

    def _ann_btn_repoint_void(self):
        # 二次点击同一按钮 = 退出重选模式，恢复普通棋盘操作
        self._ann_pick = None if self._ann_pick == 'void' else 'void'
        self._ann_notify('点击空格逐格改空位标记（再点此钮结束）'
                         if self._ann_pick == 'void' else '重选结束，可继续滑动')

    def _ann_btn_repoint_anchor(self):
        self._ann_pick = None if self._ann_pick == 'anchor' else 'anchor'
        self._ann_notify('点击滑块逐格改凸起标记（再点此钮结束）'
                         if self._ann_pick == 'anchor' else '重选结束，可继续滑动')

    def _ann_btn_phase_A(self):
        self._ann_phase = 'A'
        self._ann_phase_toggle = True
        self._ann_notify('阶段 A（推开隔离块）')

    def _ann_btn_phase_B(self):
        self._ann_phase = 'B'
        self._ann_phase_toggle = True
        self._ann_notify('阶段 B（推目标块进空位）')

    def _ann_btn_phase_AP(self):
        self._ann_phase = "A'"
        self._ann_phase_toggle = True
        self._ann_notify("阶段 A′（拉回隔离块）")

    def _ann_btn_finish(self):
        """结束并保存：空位净减 ≥ 1 才写盘。"""
        if not self._ann_recording:
            return
        self._ann_refresh_metrics()
        end_v = self._ann_cur_metrics['void_block_count']
        start_v = self._ann_base_metrics['void_block_count']
        if end_v >= start_v:
            self._ann_notify(f'空位数 {start_v} → {end_v}，未净减少，'
                             f'无法保存（继续或放弃）')
            return
        try:
            path = self._ann_write_episode()
        except Exception as e:
            self._ann_notify(f'保存失败: {e}')
            return
        n = len(self._ann_steps)
        self._ann_leave_to_home()
        self._ann_notify(f'已保存标注：{n}步，空位 {start_v}→{end_v}')

    def _ann_btn_abort(self):
        self._ann_abort('已放弃本次标注')

    def _ann_abort(self, msg):
        self._ann_leave_to_home()
        self._ann_notify(msg)

    def _ann_leave_to_home(self):
        self._ann_view = 'home'
        self._ann_sub_dialog = None
        self._ann_recording = False
        self._ann_pick = None
        self._ann_base_idx = None
        self._ann_steps = {}
        self._ann_track_void = None
        self._ann_track_anchor = None
        self._ann_track_status = 'none'

    # ------------------------------------------------------------------
    # 选中 / 修正跟踪点（逐格增删：一个标记=一颗滑块的格或一个空格）
    # ------------------------------------------------------------------
    def _ann_window_region(self):
        """当前棋盘 mod-aware 目标窗口 (r0,c0,rh,cw) 或 None。"""
        try:
            from solver.ml.gather_solver import find_best_window
            r0, c0, (rh, cw), _ = find_best_window(
                self._game_coords(), self.current_m, self.current_n,
                self.current_step)
            return r0, c0, rh, cw
        except Exception:
            return None

    def _ann_cell_inside_window(self, r, c):
        win = self._ann_window_region()
        if win is None:
            return True
        r0, c0, rh, cw = win
        return r0 <= r < r0 + rh and c0 <= c < c0 + cw

    def _ann_commit_sets(self, sync_track=True):
        """把会话级选择统一写回：None=空。"""
        self._ann_void0 = (frozenset(self._ann_void0)
                           if self._ann_void0 else None)
        self._ann_anchor0 = (frozenset(self._ann_anchor0)
                             if self._ann_anchor0 else None)
        if sync_track:
            self._ann_track_void = self._ann_void0
            self._ann_track_anchor = self._ann_anchor0
            if self._ann_track_void or self._ann_track_anchor:
                self._ann_track_status = 'ok'

    def _ann_toggle_void(self, r, c):
        """逐格增删「目标空位」标记：新增时空格才能标；取消时不限制。"""
        s = set(self._ann_void0 or ())
        removing = (r, c) in s
        if not removing and (r, c) in self._game_coords():
            self._ann_notify('该格有滑块，不能标为空位')
            return
        if not removing and self._ann_view == 'target' and not self._ann_cell_inside_window(r, c):
            self._ann_notify('目标空位需在目标窗口内（当前空格在窗外）')
            return
        if removing:
            s.discard((r, c))
            self._ann_void0 = frozenset(s)
            self._ann_notify(f'已取消空位标记 ({r},{c})，剩 {len(s)} 格'
                             if s else f'已取消空位标记 ({r},{c})')
        else:
            s.add((r, c))
            self._ann_void0 = frozenset(s)
            self._ann_notify(f'已标空位 ({r},{c})，共 {len(s)} 格'
                             f'（空格可能在后续被填上，届时视为完成）')
        self._ann_commit_sets(sync_track=(self._ann_recording
                                          or self._ann_view == 'target'))

    def _ann_toggle_anchor(self, r, c):
        """逐格增删「凸起」标记：新增时必须点在滑块上；取消时不限制。"""
        s = set(self._ann_anchor0 or ())
        removing = (r, c) in s
        if not removing and (r, c) not in self._game_coords():
            self._ann_notify('该格没有滑块，不能标为凸起')
            return
        if removing:
            s.discard((r, c))
            self._ann_notify(f'已取消凸起标记 ({r},{c})，剩 {len(s)} 格'
                             if s else f'已取消凸起标记 ({r},{c})')
        else:
            s.add((r, c))
            inside = self._ann_cell_inside_window(r, c)
            tag = '窗内块' if inside else '凸起块'
            self._ann_notify(f'已标凸起 {tag} ({r},{c})，共 {len(s)} 格')
        self._ann_anchor0 = frozenset(s)
        self._ann_commit_sets(sync_track=(self._ann_recording
                                          or self._ann_view == 'target'))

    def _ann_try_pick_at(self, x, y):
        """录制/选目标时，把棋盘点击转化为标/改空位与凸起。"""
        cell = self.get_cell_at_pos(x, y)
        if cell is None:
            return True  # 点在缝隙线上，吞掉
        r, c = cell
        # 重选按钮指定了本次只标哪一类
        if self._ann_pick == 'void':
            self._ann_toggle_void(r, c)
            return True
        if self._ann_pick == 'anchor':
            self._ann_toggle_anchor(r, c)
            return True
        # 初始选目标（view == 'target'）：空格=空位，滑块=凸起，逐格增删
        if (r, c) in self._game_coords():
            self._ann_toggle_anchor(r, c)
        else:
            self._ann_toggle_void(r, c)
        return True

    # ------------------------------------------------------------------
    # 逐帧轮询：捕捉提交动作 / 更新跟踪 / 处理打开存档结果
    # ------------------------------------------------------------------
    def _ann_poll(self):
        if not getattr(self, 'annotation_mode', False):
            return

        # 打开存档结果（文件对话框关闭后）
        if self._ann_pending_open and not self.file_dialog.active:
            self._ann_pending_open = False
            if self.file_dialog.result:
                self._ann_open_save_for_preview(self.file_dialog.result)
            return

        # 录制期间：检测历史增减，按需建步骤 / 刷新显示
        if not self._ann_recording:
            return
        hi = self.game_history.history_index
        if self._ann_last_hi is None:
            self._ann_last_hi = hi
            self._ann_refresh_metrics()
            return
        if hi != self._ann_last_hi:
            if hi > self._ann_last_hi:
                for idx in range(self._ann_last_hi + 1, hi + 1):
                    if idx > self._ann_base_idx and idx not in self._ann_steps:
                        self._ann_build_step(idx)
            self._ann_last_hi = hi
            self._ann_refresh_metrics()
            self._ann_sync_display_from_idx()

    def _ann_sync_display_from_idx(self):
        """把跟踪显示切到当前历史索引对应的录制状态（撤销/重做后一致）。"""
        hi = self.game_history.history_index
        if (self._ann_base_idx is not None and hi > self._ann_base_idx
                and hi in self._ann_steps):
            rec = self._ann_steps[hi]
            self._ann_track_void = (frozenset(rec['void'])
                                    if rec.get('void') else None)
            self._ann_track_anchor = (frozenset(rec['anchor'])
                                      if rec.get('anchor') else None)
            self._ann_track_status = rec.get('status', 'ok')
        else:
            self._ann_track_void = self._ann_void0
            self._ann_track_anchor = self._ann_anchor0
            self._ann_track_status = 'ok'

    def _game_coords(self):
        return frozenset((b.location[0], b.location[1])
                         for b in self.game.blocks)

    def _snapshot_coords(self, snap):
        return snapshot_abs_coords(snap['matrix'], snap['bounds'])

    def _ann_build_step(self, idx):
        """根据 history[idx] 推进跟踪并记录一步。

        合并快照（同一次选中连续移动）含多步：按 moves 日志逐步推进跟踪，
        末态记入 idx。若此前在该索引之后曾有旧分支的步骤，先清掉。
        """
        for k in [k for k in self._ann_steps if k >= idx]:
            del self._ann_steps[k]
        snap = self.game_history.history[idx]
        prev = self.game_history.history[idx - 1]
        n_moves = 0
        step_recs = []
        for pre_snap, post_snap, move in expand_snapshot_moves(prev, snap):
            if not move:
                continue
            step_recs.append(self._ann_advance_track(pre_snap, post_snap, move))
            n_moves += 1
        if not n_moves:
            return
        self._ann_steps[idx] = {
            'phase': self._ann_phase,
            'void': (sorted(self._ann_track_void)
                     if self._ann_track_void is not None else None),
            'anchor': (sorted(self._ann_track_anchor)
                       if self._ann_track_anchor is not None else None),
            'status': self._ann_track_status,
            'moves': n_moves,
            # 合并快照内的逐步跟踪（写盘时按步取用，长度与 moves 一致）
            'step_recs': step_recs,
        }

    def _ann_advance_track(self, pre_snap, post_snap, move):
        """按单步动作推进凸起/空位跟踪（合并快照逐步调用）→ 该步跟踪记录。"""
        prev_cells = self._snapshot_coords(pre_snap)
        cur_cells = self._snapshot_coords(post_snap)
        direction = move.get('direction', '')
        step = move.get('step', self.current_step)
        moved = move.get('moved_positions', [])
        gap_type = move.get('gap_type')
        gap_line = move.get('gap_line', 0)

        # 相对推进跟踪：凸起随滑块、空位按幻影滑块传播
        new_anchor = advance_anchor_cells(
            prev_cells, moved, direction, step,
            self._ann_track_anchor or ())
        new_void, _filled, status = advance_void_cells(
            prev_cells, cur_cells, moved, gap_type, gap_line,
            direction, step, self._ann_track_void or ())
        # 兜底保险：凸起标记必须始终落在滑块上（只应发生在极端异常时）；
        # 若几何推断脱靶就移除该标记并提示，绝不把菱形留在空格上
        curset = set(cur_cells)
        kept_anchor = [a for a in new_anchor if a in curset]
        if len(kept_anchor) != len(new_anchor):
            self._ann_notify('凸起跟踪脱靶已移除该点，可点[重选凸起]补上')
            if status == 'ok':
                status = 'lost'
        new_anchor = kept_anchor
        self._ann_track_void = (frozenset(new_void)
                                if new_void else None)
        self._ann_track_anchor = (frozenset(new_anchor)
                                  if new_anchor else None)
        self._ann_track_status = status
        if status == 'filled':
            self._ann_notify('跟踪空位已全部被填（空位数应已减少）')
        elif status == 'lost':
            self._ann_notify('跟踪出现矛盾，可用[重选空位]人工修正')
        return {
            'void': (sorted(self._ann_track_void)
                     if self._ann_track_void is not None else None),
            'anchor': (sorted(self._ann_track_anchor)
                       if self._ann_track_anchor is not None else None),
            'status': status,
        }

    def _ann_refresh_metrics(self):
        self._ann_cur_metrics = window_void_metrics(
            self._game_coords(), self.current_m, self.current_n,
            self.current_step)

    # ------------------------------------------------------------------
    # 存档中段选择（preview 子对话框）
    # ------------------------------------------------------------------
    def _ann_open_save_for_preview(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self._ann_notify(f'无法解析存档: {e}')
            return
        history = data.get('history', {})
        snapshots = history.get('snapshots', [])
        if not snapshots:
            self._ann_notify('该存档无历史快照')
            return
        self._ann_preview_data = data
        self._ann_preview_idx = history.get('history_index', 0)
        self._ann_preview_src = path
        self._ann_file_name = os.path.basename(path)
        try:
            rel = os.path.relpath(path, self.save_dir).replace('\\', '/')
        except Exception:
            rel = self._ann_file_name
        self._ann_save_rel_name = rel
        self._ann_sub_dialog = 'preview'
        self._ann_view = 'home'
        self._ann_notify(f'已打开 {os.path.basename(path)}：选择起点快照')

    def _ann_preview_apply(self):
        """把预览快照加载为当前棋盘并进入选目标状态。"""
        data = self._ann_preview_data
        idx = self._ann_preview_idx
        self._ann_cancel_session('载入存档起点')
        try:
            self._load_save_data(data)
        except Exception as e:
            self._ann_notify(f'载入失败: {e}')
            return
        if 0 <= idx < len(self.game_history.history):
            self.game_history.restore_snapshot(self.game, idx)
            self.game_history.history_index = idx
        self.center_map()
        self.selected_gap = None
        self.selected_block = None
        for b in self.game.blocks:
            b.be_opted = False
        rel = self._ann_save_rel_name
        src_desc = f'存档:{rel} 快照{idx}' if rel else f'存档快照{idx}'
        self._ann_start_target('save', src_desc)

    def _ann_preview_dialog_click(self, x, y):
        dlg = self._ann_preview_rect
        if dlg is None or not dlg.collidepoint(x, y):
            self._ann_close_sub_dialog()
            return True
        if self._ann_preview_prev_btn and self._ann_preview_prev_btn.collidepoint(x, y):
            self._ann_preview_idx = max(0, self._ann_preview_idx - 1)
            return True
        if self._ann_preview_next_btn and self._ann_preview_next_btn.collidepoint(x, y):
            n = len(self._ann_preview_data.get('history', {}).get('snapshots', []))
            self._ann_preview_idx = min(n - 1, self._ann_preview_idx + 1)
            return True
        if self._ann_preview_apply_btn and self._ann_preview_apply_btn.collidepoint(x, y):
            self._ann_preview_apply()
            return True
        if self._ann_preview_cancel_btn and self._ann_preview_cancel_btn.collidepoint(x, y):
            self._ann_close_sub_dialog()
            return True
        return True

    def _ann_preview_dialog_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._ann_close_sub_dialog()
            elif event.key == pygame.K_LEFT or event.key == pygame.K_UP:
                self._ann_preview_idx = max(0, self._ann_preview_idx - 1)
            elif event.key == pygame.K_RIGHT or event.key == pygame.K_DOWN:
                n = len(self._ann_preview_data.get('history', {}).get('snapshots', []))
                self._ann_preview_idx = min(n - 1, self._ann_preview_idx + 1)
            elif event.key == pygame.K_RETURN:
                self._ann_preview_apply()
            return True
        return False

    # ------------------------------------------------------------------
    # 随机生成参数子对话框
    # ------------------------------------------------------------------
    def _ann_gen_dialog_click(self, x, y):
        dlg = self._ann_gen_dialog_rect
        if dlg is None or not dlg.collidepoint(x, y):
            self._ann_close_sub_dialog()
            return True
        for key, rect in self._ann_gen_field_rects.items():
            if rect.collidepoint(x, y):
                self._ann_gen_active = key
                return True
        if self._ann_gen_ok_btn and self._ann_gen_ok_btn.collidepoint(x, y):
            self._ann_gen_confirm()
            return True
        if self._ann_gen_cancel_btn and self._ann_gen_cancel_btn.collidepoint(x, y):
            self._ann_close_sub_dialog()
            return True
        return True

    def _ann_gen_dialog_event(self, event):
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_ESCAPE:
            self._ann_close_sub_dialog()
            return True
        if event.key == pygame.K_RETURN:
            self._ann_gen_confirm()
            return True
        if event.key == pygame.K_TAB:
            keys = ['m', 'n', 'step', 'k', 'hole', 'dent']
            if self._ann_gen_active in keys:
                idx = keys.index(self._ann_gen_active)
                self._ann_gen_active = keys[(idx + 1) % len(keys)]
            else:
                self._ann_gen_active = 'm'
            return True
        if event.key == pygame.K_BACKSPACE:
            if self._ann_gen_active:
                cur = self._ann_gen_fields[self._ann_gen_active]
                self._ann_gen_fields[self._ann_gen_active] = cur[:-1]
            return True
        if event.unicode.isdigit():
            if self._ann_gen_active:
                cur = self._ann_gen_fields[self._ann_gen_active]
                if len(cur) < 3:
                    self._ann_gen_fields[self._ann_gen_active] = cur + event.unicode
            return True
        return True

    def _ann_gen_confirm(self):
        try:
            m = int(self._ann_gen_fields['m'])
            n = int(self._ann_gen_fields['n'])
            step = int(self._ann_gen_fields['step'])
            hole = int(self._ann_gen_fields.get('hole', '1'))
            dent = int(self._ann_gen_fields.get('dent', '0'))
        except ValueError:
            self._ann_gen_error = '请输入有效的整数'
            return
        if m < 2 or n < 2:
            self._ann_gen_error = 'm、n 必须 >= 2'
            return
        if step < 1:
            self._ann_gen_error = '等级必须 >= 1'
            return
        if step >= max(m, n):
            self._ann_gen_error = f'等级必须 < {max(m, n)}'
            return
        if hole < 0 or dent < 0:
            self._ann_gen_error = '孔洞/缺口数不能为负'
            return
        if hole + dent < 1:
            self._ann_gen_error = '孔洞与缺口至少有一个 ≥ 1'
            return
        if hole + dent > (m * n) // 4:
            self._ann_gen_error = f'空位总数需在 1 ~ {max(1, (m * n) // 4)}'
            return
        try:
            from solver.ml import ann_gen
            coords, _holes = ann_gen.generate_classified(
                m, n, step, hole, dent, rng=random.Random())
        except ValueError as e:
            self._ann_gen_error = str(e)
            return
        self._ann_gen_error = ''
        self._ann_sub_dialog = None
        self._ann_store_inputs('gen', self._ann_gen_fields)
        self.new_puzzle(m, n, step)
        self.game.blocks = [Block(list(c)) for c in sorted(coords)]
        self.game.update_matrix()
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        self.center_map()
        if self.create_mode:
            # 创造模式：造好即成为当前谜题，留在创造首页
            self._ann_leave_to_home()
            self._ann_notify(f'已生成谜题：{m}×{n} step{step} '
                             f'孔洞 {hole} 个 / 缺口 {dent} 个')
        else:
            self._ann_start_target(
                'gen', f'随机生成 {m}×{n} 孔洞{hole} 缺口{dent}')
            self._ann_notify(f'已生成：{m}×{n} step{step} '
                             f'孔洞 {hole} 个 / 缺口 {dent} 个，请选目标')

    def _ann_close_sub_dialog(self):
        # 关闭时把输入框内容留档，保证下次打开和上次一致
        if self._ann_sub_dialog == 'gen':
            self._ann_store_inputs('gen', self._ann_gen_fields)
        elif self._ann_sub_dialog == 'build':
            self._ann_store_inputs('build', self._ann_build_fields)
        self._ann_sub_dialog = None
        self._ann_preview_data = None
        self._ann_build_error = ''

    # ------------------------------------------------------------------
    # 打断保护：切换谜题/打乱/载入等会重置棋盘 → 结束当前标注会话
    # ------------------------------------------------------------------
    def _ann_cancel_session(self, reason):
        """在 new_puzzle/shuffle/_load_save_data 等入口调用，安全清场。"""
        was_active = self._ann_view in ('target', 'recording') or self._ann_recording
        self._ann_leave_to_home()
        if was_active and getattr(self, 'annotation_mode', False):
            self._ann_notify(f'{reason}：已结束当前标注')

    # 供外部接入：阻止录制中撤销到起点之前
    def _ann_undo_blocked(self):
        if not getattr(self, '_ann_recording', False):
            return False
        if self.game_history.history_index <= self._ann_base_idx:
            self._ann_notify('标注起点之前不可撤销')
            return True
        return False

    # ------------------------------------------------------------------
    # 写盘：save/标注样本/{annotations.jsonl, progress.json}
    # ------------------------------------------------------------------
    def _ann_out_dir(self):
        d = os.path.join(self.save_dir, '标注样本')
        os.makedirs(d, exist_ok=True)
        return d

    def _ann_progress_path(self):
        return os.path.join(self._ann_out_dir(), 'progress.json')

    def _ann_load_progress(self):
        try:
            with open(self._ann_progress_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _ann_write_episode(self):
        """把当前录制区间写为一行 episode（JSONL），并更新 progress.json。"""
        hi = self.game_history.history_index
        base = self._ann_base_idx
        if base is None or hi <= base:
            raise ValueError('没有任何已录制步骤')
        history = self.game_history.history
        base_snap = history[base]
        end_snap = history[hi]

        steps = []
        phase_cnt = {}
        for idx in range(base + 1, hi + 1):
            rec = self._ann_steps.get(idx)
            if rec is None:
                continue
            expanded = expand_snapshot_moves(history[idx - 1], history[idx])
            if not expanded:
                continue
            step_recs = rec.get('step_recs')
            if not step_recs or len(step_recs) != len(expanded):
                step_recs = [rec] * len(expanded)
            for (pre, _post, move), mrec in zip(expanded, step_recs):
                if not move:
                    continue
                pre_cells = self._snapshot_coords(pre)
                mets = window_void_metrics(pre_cells, self.current_m,
                                           self.current_n, self.current_step)
                moved = move.get('moved_positions', [])
                side = infer_side(move.get('gap_type', ''),
                                  move.get('gap_line', 0), moved) if moved else None
                ph = rec.get('phase', '')
                phase_cnt[ph] = phase_cnt.get(ph, 0) + 1
                steps.append({
                    'phase': ph,
                    'pre_matrix': pre['matrix'],
                    'pre_bounds': pre['bounds'],
                    'move_info': {
                        'gap_type': move.get('gap_type'),
                        'gap_line': move.get('gap_line'),
                        'side': side,
                        'direction': move.get('direction'),
                        'step': move.get('step', self.current_step),
                        'moved_positions': moved,
                    },
                    'void_block_count': mets['void_block_count'],
                    'gather_score': round(mets['score'], 6),
                    'track_void': mrec.get('void'),
                    'track_anchor': mrec.get('anchor'),
                })

        start_coords = self._snapshot_coords(base_snap)
        end_coords = self._snapshot_coords(end_snap)
        st_mets = window_void_metrics(start_coords, self.current_m,
                                      self.current_n, self.current_step)
        en_mets = window_void_metrics(end_coords, self.current_m,
                                      self.current_n, self.current_step)

        ts = time.strftime('%Y%m%d-%H%M%S')
        progress = self._ann_load_progress()
        counter = int(progress.get('episode_counter', 0)) + 1
        episode_id = f'ann-{ts}-{counter:04d}'
        region = self._current_region()

        ep = {
            'schema': 1,
            'episode_id': episode_id,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'puzzle': {'m': self.current_m, 'n': self.current_n,
                       'step': self.current_step},
            'source_type': self._ann_source_type,
            'source_desc': self._ann_source_desc,
            'start': {
                'matrix': base_snap['matrix'],
                'bounds': base_snap['bounds'],
                'region': list(region) if region else None,
                # 录制起点快照优先；无快照回退会话当前选择（兼容旧路径）
                'target_void': sorted([list(c) for c in
                                       (self._ann_start_void
                                        or self._ann_void0 or set())]),
                'target_anchor': sorted(
                    [list(c) for c in (self._ann_start_anchor
                                       or self._ann_anchor0 or set())])
                    if (self._ann_start_anchor or self._ann_anchor0) else None,
                'void_block_count': st_mets['void_block_count'],
                'gather_score': round(st_mets['score'], 6),
                'bbox': list(st_mets['bbox']),
            },
            'end': {
                'matrix': end_snap['matrix'],
                'bounds': end_snap['bounds'],
                'void_block_count': en_mets['void_block_count'],
                'gather_score': round(en_mets['score'], 6),
                'bbox': list(en_mets['bbox']),
            },
            'void_delta': en_mets['void_block_count'] - st_mets['void_block_count'],
            'phase_counts': phase_cnt,
            'steps': steps,
        }

        out_path = os.path.join(self._ann_out_dir(), 'annotations.jsonl')
        with open(out_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(ep, ensure_ascii=False) + '\n')

        progress['episode_counter'] = counter
        progress['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        progress.setdefault('source_counts', {})
        progress['source_counts'][self._ann_source_type] = \
            progress['source_counts'].get(self._ann_source_type, 0) + 1
        with open(self._ann_progress_path(), 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        return out_path

    def _current_region(self):
        from solver.ml.gather_solver import find_best_window
        try:
            r0, c0, (rh, cw), _ = find_best_window(self._game_coords(),
                                                   self.current_m,
                                                   self.current_n,
                                                   self.current_step)
            return [r0, c0, rh, cw]
        except Exception:
            return None

    # ==================================================================
    # 渲染
    # ==================================================================
    def draw_annotation_mode(self):
        """标注/创造模式渲染入口（run 循环里、浮动面板之后调用）。"""
        if not (getattr(self, 'annotation_mode', False) or self.create_mode):
            return
        if self._ann_view == 'build':
            self._ann_draw_build_canvas()
        elif self._ann_view in ('target', 'recording'):
            self._ann_draw_track_markers()
        self._ann_draw_bar()
        if self._ann_sub_dialog == 'gen':
            self._ann_draw_gen_dialog()
        elif self._ann_sub_dialog == 'preview':
            self._ann_draw_preview_dialog()
        self._ann_draw_msg()

    def _ann_screen_rect(self):
        return pygame.Rect(0, 0, self.screen_width,
                           self.screen_height - self.status_bar_height)

    def _ann_cell_center(self, r, c):
        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom
        step_px = scaled_cell + scaled_gap
        return (c * step_px + self.camera_x + scaled_cell / 2,
                r * step_px + self.camera_y + scaled_cell / 2)

    def _ann_draw_track_markers(self):
        """在棋盘上画跟踪标记：空位圈 + 凸起框。"""
        scaled_cell = self.cell_size * self.zoom
        radius = max(3, int(scaled_cell * 0.22))
        lw = max(2, int(3 * self.zoom))
        # 空位格
        cells = self._ann_track_void
        status = self._ann_track_status
        if cells:
            color = (255, 80, 80) if status == 'lost' else (255, 220, 60)
            for (r, c) in sorted(cells):
                cx, cy = self._ann_cell_center(r, c)
                pygame.draw.circle(self.screen, color, (int(cx), int(cy)),
                                   max(radius, int(scaled_cell * 0.35)), lw)
        # 凸起锚点格（可多格，逐格标在滑块上）
        if self._ann_track_anchor:
            for (r, c) in sorted(self._ann_track_anchor):
                cx, cy = self._ann_cell_center(r, c)
                d = scaled_cell / 2
                pts = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
                pygame.draw.polygon(self.screen, (80, 240, 160), pts, lw)

    def _ann_draw_bar(self):
        """底部标注工具栏（随视图变化）。"""
        w = min(820, self.screen_width - self.right_panel_width - 24)
        x = self.screen_width - self.right_panel_width - w - 10
        # 手动构造视图：工具条加高，内嵌 m/n/step 参数输入 + 操作按钮，
        # 这样主棋盘完全留给点格增删滑块（不再用居中弹窗遮挡棋盘）。
        bar_h = 82 if self._ann_view == 'build' else self._ANN_BAR_H
        y, h = self.screen_height - self.status_bar_height - \
            bar_h - 8, bar_h
        self._ann_bar_rect = pygame.Rect(x, y, w, h)
        self._ann_btn_rects = {}

        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        bg.fill((35, 35, 48, 235))
        self.screen.blit(bg, (x, y))
        pygame.draw.rect(self.screen, (110, 110, 130), self._ann_bar_rect, 1,
                         border_radius=8)

        btn_y = y + 8
        btn_h = h - 16

        def add(name, text, color=None):
            nonlocal x
            tw = self.menu_font.size(text)[0] + 22
            rect = pygame.Rect(x + 8, btn_y, tw, btn_h)
            x = rect.right
            col = color or self.colors['button_bg']
            hover = rect.collidepoint(pygame.mouse.get_pos())
            fill = (min(255, col[0] + 25), min(255, col[1] + 25),
                    min(255, col[2] + 25)) if hover else col
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            srf = self.menu_font.render(text, True, (255, 255, 255))
            self.screen.blit(srf, srf.get_rect(center=rect.center))
            self._ann_btn_rects[name] = rect

        if self._ann_view == 'home':
            if self.create_mode:
                add('manual_build', '手动构造', (70, 120, 180))
                # 随机生成只对方形开放（三角/米字没有随机生成）
                if not self.triangle_mode and not self.mi_mode:
                    add('random_gen', '随机生成', (70, 120, 180))
                if self.triangle_mode or self.mi_mode:
                    title_text = ('创造模式：请用[手动构造]造题 · '
                                  '造好即成为当前谜题 · ESC 退出')
                else:
                    title_text = ('创造模式：随机挖洞/缺口 或 手动构造 · '
                                  '造好即成为当前谜题 · ESC 退出')
            else:
                add('exit_mode', '退出标注', (120, 90, 90))
                add('from_current', '④ 当前状态', (70, 120, 180))
                add('from_save', '① 存档中段选起点', (70, 120, 180))
                title_text = ('标注模式：录制「填洞/收敛空位」示范 · '
                              '隐藏入口=同时按住 B Z M S')
            title = self.status_font.render(title_text, True, (200, 200, 210))
            self.screen.blit(title, (self._ann_bar_rect.x + 6,
                                     self._ann_bar_rect.y - 18))
        elif self._ann_view == 'build':
            # 参数输入直接内嵌在底部工具条，主棋盘用于点格增删滑块
            self._ann_draw_build_toolbar(x, y, w, h)
        elif self._ann_view in ('target', 'recording'):
            if self._ann_view == 'target':
                add('abort', '放弃', (150, 90, 90))
                if self._ann_void0 is not None and self._ann_anchor0 is not None:
                    add('start_exec', '▶ 开始跟踪执行', (60, 150, 90))
                info = ('点空格标空位 / 点滑块标凸起（逐格增删）'
                        if (self._ann_void0 is None or self._ann_anchor0 is None)
                        else '目标已选好，按下[开始跟踪执行]')
            else:
                # 顶部按钮（阶段）
                ph_col = {'A': (200, 150, 60), 'B': (90, 160, 200), "A'": (170, 120, 200)}
                add('phase_A', 'A', ph_col['A'] if self._ann_phase == 'A' else (90, 90, 100))
                add('phase_B', 'B', ph_col['B'] if self._ann_phase == 'B' else (90, 90, 100))
                add('phase_AP', "A′", ph_col["A'"] if self._ann_phase == "A'" else (90, 90, 100))
                add('repoint_void', '重选空位')
                add('repoint_anchor', '重选凸起')
                add('abort', '放弃', (150, 90, 90))
                add('finish', '结束并保存', (60, 150, 90))
                # 状态文本
                cur = self._ann_cur_metrics or self._ann_base_metrics or {}
                st = self._ann_base_metrics or {}
                # 合并快照一条覆盖多步：按 moves 计步（无该字段则记 1 步）
                n_steps = sum(rec.get('moves', 1)
                              for k, rec in self._ann_steps.items()
                              if k > (self._ann_base_idx or -1)
                              and k <= self.game_history.history_index)
                st_c = '●' if self._ann_track_void is not None else '○'
                an_c = '●' if self._ann_track_anchor is not None else '○'
                phase_show = {'A': 'A', 'B': 'B', "A'": "A′"}.get(self._ann_phase, self._ann_phase)
                info = (f'步骤 {n_steps} · 阶段 {phase_show} · '
                        f'空位 {st.get("void_block_count", "?")}→{cur.get("void_block_count", "?")} · '
                        f'空位跟踪{st_c} 凸起跟踪{an_c}')
            title = self.status_font.render('标注录制 ' + info, True,
                                            (200, 200, 210))
            self.screen.blit(title, (self._ann_bar_rect.x + 6,
                                     self._ann_bar_rect.y - 18))

    def _ann_draw_build_toolbar(self, x, y, w, h):
        """手动构造工具条：内嵌 m/n/step 参数输入 + 操作按钮 + 校验状态。

        主棋盘完全留给点格增删滑块，因此这里不用居中弹窗。
        点击/键盘事件由 _ann_build_dialog_click / _ann_build_dialog_event 处理，
        它们根据 _ann_build_field_rects 与各按钮矩形判定命中。
        """
        row1 = y + 10
        row2 = y + 46
        fh = 26
        self._ann_build_field_rects = {}
        bx = x + 10
        # 参数行按形态：三角只填边长 k／等级 step
        param_fields = (('k', '边长'), ('step', '等级')) \
            if self.triangle_mode else (('m', '行'), ('n', '列'), ('step', '等级'))
        for key, label in param_fields:
            ls = self.status_font.render(label, True, (200, 200, 210))
            self.screen.blit(ls, (bx, row1 + 5))
            lbl_w = ls.get_width() + 4
            frect = pygame.Rect(bx + lbl_w, row1, 52, fh)
            self._ann_build_field_rects[key] = frect
            fbg = self.colors['input_active'] if self._ann_build_active == key \
                else self.colors['input_bg']
            pygame.draw.rect(self.screen, fbg, frect, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['dialog_border'], frect, 1,
                             border_radius=4)
            vs = self.status_font.render(
                self._ann_build_fields.get(key, ''), True,
                self.colors['input_text'])
            self.screen.blit(vs, (frect.x + 5, frect.y + 4))
            if self._ann_build_active == key:
                cx = frect.x + 5 + vs.get_width() + 2
                pygame.draw.line(self.screen, self.colors['input_text'],
                                 (cx, frect.y + 4), (cx, frect.bottom - 4), 1)
            bx = frect.right + 16

        # 按钮行（右上对齐，状态文字留左侧空间）
        def toolbar_btn(rect, text, color=None):
            c = color or self.colors['button_bg']
            if rect.collidepoint(pygame.mouse.get_pos()):
                c = (min(255, c[0] + 25), min(255, c[1] + 25),
                     min(255, c[2] + 25))
            pygame.draw.rect(self.screen, c, rect, border_radius=6)
            s = self.status_font.render(text, True, (255, 255, 255))
            self.screen.blit(s, s.get_rect(center=rect.center))

        bx = x + w - 10
        bh = 26
        # 从右向左放置按钮：退出 / 清空 / 还原m×n / 应用并开始
        def place_right(text, color=None):
            nonlocal bx
            tw = self.status_font.size(text)[0] + 18
            rect = pygame.Rect(bx - tw, row2, tw, bh)
            toolbar_btn(rect, text, color)
            bx = rect.left - 8
            return rect

        self._ann_build_cancel_btn = place_right('退出', (120, 90, 90))
        self._ann_build_clear_btn = place_right('清空')
        self._ann_build_reset_btn = place_right('还原m×n')
        # 创造模式：应用后直接成为当前谜题；标注模式：应用后进入选目标
        self._ann_build_ok_btn = place_right(
            '应用' if self.create_mode else '应用并开始', (60, 150, 90))
        # 这个工具条就是本次构造的「对话框矩形」：命中其内输入/按钮即处理
        self._ann_build_dialog_rect = self._ann_bar_rect

        # 即时效验状态（按钮行左侧）
        try:
            mm, nn, ss = self._ann_build_param()
            msg, is_ok = self._ann_build_status(mm, nn, ss)
        except ValueError as e:
            msg, is_ok = str(e), False
        if self._ann_build_error:
            msg, is_ok = self._ann_build_error, False
        color = (150, 230, 160) if is_ok else (255, 150, 140)
        st = self.status_font.render('手动构造  ' + msg, True, color)
        self.screen.blit(st, (x + 10, row2 + 3))

    # ---- 状态提示（工具条右下方小字） ----
    def _ann_draw_msg(self):
        if self._ann_msg_timer > 0:
            self._ann_msg_timer -= 1

    # ==================================================================
    # 手动构造对话框（自由点选画布）
    # ==================================================================
    def _ann_build_param(self):
        """解析构造参数 → (m,n,step) 或抛 ValueError。

        三角只有边长 k／等级 step（m=n=k）；米字与方形填行/列/等级。
        上界沿用 new_triangle_puzzle / new_mi_puzzle / 原方形的守卫。
        """
        if self.triangle_mode:
            k = int(self._ann_build_fields.get('k') or 0)
            step = int(self._ann_build_fields.get('step') or 0)
            if k < 2:
                raise ValueError('边长必须 >= 2')
            if step < 1:
                raise ValueError('等级必须 >= 1')
            if step >= k:
                raise ValueError(f'等级必须 < {k}')
            return k, k, step
        m = int(self._ann_build_fields.get('m') or 0)
        n = int(self._ann_build_fields.get('n') or 0)
        step = int(self._ann_build_fields.get('step') or 0)
        if m < 2 or n < 2:
            raise ValueError('m、n 必须 >= 2')
        if step < 1:
            raise ValueError('等级必须 >= 1')
        if step >= max(m, n):
            raise ValueError(f'等级必须 < {max(m, n)}')
        return m, n, step

    def _ann_build_grid(self, m, n):
        """可构造范围（全局坐标）：当前棋形边界盒各扩一圈。

        只跟随棋形本身，不再并上 m×n 区域——两者取并集的包围盒会把范围
        撑成一大片无关矩形（棋形离原点远时尤其明显）。空画布无边界盒，
        回退到 m×n 各扩一圈，保证有地方落第一颗。

        注意：三角不用本方法——斜坐标矩形在屏幕上呈菱形，三角的可构造
        范围应是与地图形状一致的「三角环带」（见 _ann_build_tri_range）。
        """
        coords = getattr(self, '_ann_build_coords', None) or set()
        if not coords:
            return -1, m, -1, n
        # 各形态位置元组的前两个分量取边界盒（三角 (i,j,up)、米字 (r,c,q)）
        rs = [p[0] for p in coords]
        cs = [p[1] for p in coords]
        return min(rs) - 1, max(rs) + 1, min(cs) - 1, max(cs) + 1

    def _ann_build_tri_range(self, m):
        """三角可构造范围：当前棋形外扩一圈的三角环带，非斜坐标矩形。

        返回 (lo_i, hi_i, lo_j, hi_j, s_up, s_down)：i/j 下界各外扩 1；
        斜边按朝向分别外扩——▲ 片 i+j <= s_up、▼ 片 i+j <= s_down（完整
        大三角 ▲ 上界 i+j<=k-1、▼ 上界 i+j<=k-2，各自外扩一圈 +1）；hi
        不截断（对角约束兜底），斜边层的端点（如 (7,-1)、(-1,7)）补进
        范围。屏幕上仍是正三角形环带，与矩形/米字「外扩一圈」视觉一致。
        空画布回退标准三角外扩，保证有地方落第一颗。
        """
        coords = getattr(self, '_ann_build_coords', None) or set()
        if not coords:
            return -1, m, -1, m, m, m - 1
        lo_i = min(p[0] for p in coords) - 1
        lo_j = min(p[1] for p in coords) - 1
        s_all = max(p[0] + p[1] for p in coords)
        ups = [p[0] + p[1] for p in coords if p[2]]
        downs = [p[0] + p[1] for p in coords if not p[2]]
        # 单朝向兜底：缺 ▲ 或 ▼ 片时，该朝向外扩 = 棋形整体边界 + 1（覆盖邻位）
        s_up = (max(ups) if ups else s_all) + 1
        s_down = (max(downs) if downs else s_all) + 1
        # hi 不截断：斜边外扩层 i+j==s 的端点可达 i/j == s+1（如 (7,-1)、(-1,7)），
        # 对角约束 i+j<=s 已限定范围；hi 取 s_up+1 保证遍历覆盖端点。
        hi = s_up + 1
        return lo_i, hi, lo_j, hi, s_up, s_down

    def _ann_build_status(self, m, n, step):
        """即时校验状态：返回 (text, is_ok)。

        方形沿用既有判据（提示文字逐条保持，见计划验收 6）；三角/米字走
        shape_validate.validate_shape（计划二 A 产出，含偏移扫描 anchor）。
        """
        coords = frozenset(self._ann_build_coords)
        if self.triangle_mode or self.mi_mode:
            from gui.shape_validate import validate_shape
            kind = 'triangle' if self.triangle_mode else 'mi'
            params = (m,) if kind == 'triangle' else (m, n)
            try:
                ok, msg, _anchor = validate_shape(kind, coords, params, step)
            except Exception as e:
                return f'参数无效：{e}', False
            if not ok:
                return f'非法棋形：{msg}', False
            text = (f'合法 {m}×{n} step{step}：{len(coords)} 颗滑块'
                    f' · 单连通 · 同余一致')
            if self._ann_build_numbered:
                text += f' · 可用编号 {len(self._ann_build_num_stack)}'
            return text, True
        from solver.ml import ann_gen
        try:
            ok, msg = ann_gen.validate_state(coords, m, n, step)
        except Exception as e:
            return f'参数无效：{e}', False
        if not ok:
            return f'非法棋形：{msg}', False
        try:
            vm = window_void_metrics(coords, m, n, step)
            if vm['void_block_count'] < 1:
                return f'合法，但窗内无空位（{len(coords)} 颗）', False
        except Exception:
            pass
        return (f'合法 {m}×{n} step{step}：{len(coords)} 颗滑块 · 单连通 · 同余一致'
                f' · 窗内空位≥1，可应用', True)

    # ---- 主棋盘直接构造：点击 / 键盘 / 应用 ----
    def _ann_build_dialog_click(self, x, y):
        """构造弹窗：点输入框聚焦 / 点按钮操作 / 点窗外交互棋盘增删滑块。"""
        dlg = self._ann_build_dialog_rect
        if dlg is not None and dlg.collidepoint(x, y):
            for key, rect in self._ann_build_field_rects.items():
                if rect.collidepoint(x, y):
                    self._ann_build_active = key
                    return True
            for suffix, rect in (('ok', self._ann_build_ok_btn),
                                 ('reset', self._ann_build_reset_btn),
                                 ('clear', self._ann_build_clear_btn),
                                 ('cancel', self._ann_build_cancel_btn)):
                if rect and rect.collidepoint(x, y):
                    getattr(self, '_ann_btn_build_' + suffix)()
                    return True
            return True
        # 右侧面板（快捷开关 / 缩放、速度滑条）与状态栏不属于棋盘：
        # 放行给常规事件处理，否则这些正常操作会被吞掉，
        # 且因棋盘网格是无限的而被误判为「点选超出可构造范围」
        if x >= self.screen_width - self.right_panel_width:
            return False
        if y > self.screen_height - self.status_bar_height:
            return False
        # 弹窗外：直接在主棋盘点选增删滑块。
        # 三角/米字用各自 view 的 world_to_cell（不带 cells，空位也给身份）；
        # 方形照旧用 get_cell_at_pos。
        if self.triangle_mode:
            wx, wy = self.screen_to_world(x, y)
            cell = self._tri_view().world_to_cell(wx, wy)
        elif self.mi_mode:
            wx, wy = self.screen_to_world(x, y)
            cell = self._mi_view().world_to_cell(wx, wy)
        else:
            cell = self.get_cell_at_pos(x, y)
        if cell is None:
            return True
        self._ann_build_toggle(cell)
        return True

    def _ann_build_dialog_event(self, event):
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_ESCAPE:
            self._ann_build_cancel()
            return True
        if event.key == pygame.K_RETURN:
            self._ann_build_apply()
            return True
        if event.key == pygame.K_TAB:
            keys = ['k', 'step'] if self.triangle_mode else ['m', 'n', 'step']
            if self._ann_build_active in keys:
                idx = keys.index(self._ann_build_active)
                self._ann_build_active = keys[(idx + 1) % len(keys)]
            else:
                self._ann_build_active = 'm'
            return True
        if event.key == pygame.K_BACKSPACE:
            if self._ann_build_active:
                cur = self._ann_build_fields.get(self._ann_build_active, '')
                self._ann_build_fields[self._ann_build_active] = cur[:-1]
            return True
        if event.unicode and event.unicode.isdigit():
            if self._ann_build_active:
                cur = self._ann_build_fields.get(self._ann_build_active, '')
                if len(cur) < 3:
                    self._ann_build_fields[self._ann_build_active] = cur + event.unicode
            return True
        return True

    def _ann_build_apply(self):
        """校验当前构造 → 写历史并进入选目标阶段。

        方形沿用既有判据与提示文字；三角/米字走 validate_shape。
        标注模式（ML 取样流程）在三角/米字下不支援：只提示，不进选目标。
        """
        try:
            m, n, step = self._ann_build_param()
        except ValueError as e:
            self._ann_build_error = str(e)
            return
        coords = frozenset(self._ann_build_coords)
        if self.triangle_mode or self.mi_mode:
            from gui.shape_validate import validate_shape
            kind = 'triangle' if self.triangle_mode else 'mi'
            params = (m,) if kind == 'triangle' else (m, n)
            ok, msg, _anchor = validate_shape(kind, coords, params, step)
            if not ok:
                self._ann_build_error = f'非法棋形：{msg}'
                return
        else:
            from solver.ml import ann_gen
            ok, msg = ann_gen.validate_state(coords, m, n, step)
            if not ok:
                self._ann_build_error = f'非法棋形：{msg}'
                return
            vm = window_void_metrics(coords, m, n, step)
            if vm['void_block_count'] < 1:
                self._ann_build_error = '窗内没有空位（等于还原态），请挖出至少一个空位'
                return
        self._ann_build_error = ''
        self._ann_store_inputs('build', self._ann_build_fields)
        self.current_m, self.current_n, self.current_step = m, n, step
        self._ann_rebuild_game_from_coords()
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        self.center_map()
        self._ann_build_backup = None
        if self.create_mode:
            # 创造模式：造好即成为当前谜题，留在创造首页
            self._ann_leave_to_home()
            self._ann_notify(f'已应用构造：{m}×{n} step{step}（{len(coords)} 颗）')
        elif self.triangle_mode or self.mi_mode:
            self._ann_notify('该形态暂不支援标注取样，请在创造模式下使用手动构造')
        else:
            self._ann_start_target('build', f'手动构造 {m}×{n} step{step} '
                                            f'（{len(coords)} 颗）')
            self._ann_notify('已应用手动构造，请点目标空位与凸起')

    def _ann_build_reset(self):
        """还原为完整目标形态（无洞无凸起），从点空格挖洞开始。

        数字谜题按行主序重新编号 1..mn（与 new_puzzle(numbered=True)
        同一套约定），编号栈清空。
        """
        try:
            m, n, step = self._ann_build_param()
        except ValueError as e:
            self._ann_build_error = str(e)
            return
        if self.triangle_mode:
            from game_triangle import TriangleSliderMatrix
            self._ann_build_coords = TriangleSliderMatrix(m).positions()
        elif self.mi_mode:
            from game_mi import MiSliderMatrix
            self._ann_build_coords = MiSliderMatrix(m, n).positions()
        else:
            self._ann_build_coords = set(self._ann_solved_coords(m, n))
        if self._ann_build_numbered:
            ordered = sorted(self._ann_build_coords)
            self._ann_build_numbers = {
                pos: idx + 1 for idx, pos in enumerate(ordered)}
            self._ann_build_num_stack = []
        self._ann_build_error = ''
        self._ann_rebuild_game_from_coords()

    def _ann_build_clear(self):
        """清空全部滑块，从零开始铺。

        数字谜题：盘上所有编号按升序整批压栈（可预期、可复现），
        于是 mn 个都能重新放下。
        """
        if self._ann_build_numbered and self._ann_build_numbers:
            self._ann_build_num_stack.extend(
                sorted(self._ann_build_numbers.values()))
            self._ann_build_numbers = {}
        self._ann_build_coords = set()
        self._ann_build_error = ''
        self._ann_rebuild_game_from_coords()

    def _ann_btn_build_ok(self):
        self._ann_build_apply()

    def _ann_btn_build_reset(self):
        self._ann_build_reset()

    def _ann_btn_build_clear(self):
        self._ann_build_clear()

    def _ann_btn_build_cancel(self):
        self._ann_build_cancel()

    def _ann_draw_build_canvas(self):
        """主棋盘构造叠加层：可构造范围轮廓 + 目标区域高亮。

        棋盘上的滑块由主渲染器绘制；这里补画空格轮廓与目标框，
        让用户直接在主窗口点选增删滑块。空格轮廓按形态画单位片
        （三角画单位三角、米字画四分之一格），方形照旧画格。
        """
        try:
            m, n, step = self._ann_build_param()
        except ValueError:
            return
        stepw = self.cell_size + self.gap_width
        cs = self.cell_size * self.zoom
        lo_r, hi_r, lo_c, hi_c = self._ann_build_grid(m, n)
        # 米字错位态的 bbox 可能含半整数（B 晶格）：轮廓只枚举整数格范围，
        # 半整数空位不画轮廓（world_to_cell 命中后仍可点选增删）
        r_lo = int(math.floor(lo_r))
        r_hi = int(math.ceil(hi_r))
        c_lo = int(math.floor(lo_c))
        c_hi = int(math.ceil(hi_c))
        outline = (70, 95, 120)
        if self.triangle_mode:
            view = self._tri_view()
            tri_lo_i, tri_hi_i, tri_lo_j, tri_hi_j, s_up, s_down = \
                self._ann_build_tri_range(m)
            for i in range(tri_lo_i, tri_hi_i + 1):
                for j in range(tri_lo_j, tri_hi_j + 1):
                    for up in (True, False):
                        if i + j > (s_up if up else s_down):
                            continue
                        if (i, j, up) in self._ann_build_coords:
                            continue
                        pts = [self.world_to_screen(*p)
                               for p in view.piece_polygon(i, j, up)]
                        pygame.draw.polygon(self.screen, outline, pts, 1)
        elif self.mi_mode:
            view = self._mi_view()
            for r in range(r_lo, r_hi + 1):
                for c in range(c_lo, c_hi + 1):
                    for q in ('N', 'E', 'S', 'W'):
                        if (r, c, q) in self._ann_build_coords:
                            continue
                        pts = [self.world_to_screen(*p)
                               for p in view.piece_polygon(r, c, q)]
                        pygame.draw.polygon(self.screen, outline, pts, 1)
        else:
            # 空格轮廓（有滑块处主渲染器已画）
            for r in range(r_lo, r_hi + 1):
                for c in range(c_lo, c_hi + 1):
                    if (r, c) in self._ann_build_coords:
                        continue
                    x, y = self.world_to_screen(c * stepw, r * stepw)
                    pygame.draw.rect(self.screen, outline,
                                     pygame.Rect(int(x), int(y),
                                                 max(1, int(cs)),
                                                 max(1, int(cs))), 1)
        # 目标框：仅方形画——与求解器/调试面板同源（find_best_window，
        # mod-aware），是「该还原理的位置」；三角/米字没有求解器，
        # anchor 只是类匹配偏移、画出的还原态轮廓对用户无意义
        # （构造中位置漂移时框也不对），故不画。
        if not (self.triangle_mode or self.mi_mode):
            region = _target_region_of(self._ann_build_coords, m, n, step)
            if region is not None:
                r0, c0, (rh, cw) = region
                x0, y0 = self.world_to_screen(c0 * stepw, r0 * stepw)
                x1, y1 = self.world_to_screen((c0 + cw) * stepw, (r0 + rh) * stepw)
                pygame.draw.rect(self.screen, (120, 210, 255),
                                 pygame.Rect(int(x0), int(y0),
                                             max(1, int(x1 - x0)),
                                             max(1, int(y1 - y0))), 2)
        # 顶部操作提示（不遮棋盘中部）
        hint = self.status_font.render(
            '点棋盘格放/取滑块，点窗外格补凸起；改下方参数后 Enter 应用',
            True, (150, 220, 255))
        self.screen.blit(hint, (self.menu_bar_height + 8, self.menu_bar_height + 6))

    def _btn_row4(self, r1, t1, r2, t2, r3, t3, r4, t4):
        mouse = pygame.mouse.get_pos()
        for rect, text in ((r1, t1), (r2, t2), (r3, t3), (r4, t4)):
            c = self.colors['button_hover'] if rect.collidepoint(mouse) \
                else self.colors['button_bg']
            pygame.draw.rect(self.screen, c, rect, border_radius=4)
            s = self.input_font.render(text, True, (255, 255, 255))
            self.screen.blit(s, s.get_rect(center=rect.center))

    # ==================================================================
    # 随机生成参数对话框
    # ==================================================================
    def _ann_draw_gen_dialog(self):
        w, h = 360, 400
        dx = (self.screen_width - w) // 2
        dy = (self.screen_height - h) // 2
        overlay = pygame.Surface((self.screen_width, self.screen_height),
                                 pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        dlg = pygame.Rect(dx, dy, w, h)
        self._ann_gen_dialog_rect = dlg
        pygame.draw.rect(self.screen, self.colors['dialog_bg'], dlg,
                         border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], dlg, 2,
                         border_radius=8)
        title = self.dialog_title_font.render(
            "随机生成谜题" if self.create_mode else "随机生成标注起点",
            True, self.colors['dialog_title'])
        self.screen.blit(title, (dx + 20, dy + 15))

        fields = [
            ('m', '行数:', self._ann_gen_fields['m']),
            ('n', '列数:', self._ann_gen_fields['n']),
            ('step', '等级:', self._ann_gen_fields['step']),
            ('hole', '孔洞数:', self._ann_gen_fields['hole']),
            ('dent', '缺口数:', self._ann_gen_fields['dent']),
        ]
        self._ann_gen_field_rects = {}
        y = dy + 55
        for key, label, value in fields:
            ls = self.input_font.render(label, True, self.colors['dialog_text'])
            self.screen.blit(ls, (dx + 25, y + 4))
            frect = pygame.Rect(dx + 165, y, 120, 30)
            self._ann_gen_field_rects[key] = frect
            fbg = self.colors['input_active'] if self._ann_gen_active == key \
                else self.colors['input_bg']
            pygame.draw.rect(self.screen, fbg, frect, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['dialog_border'], frect, 1,
                             border_radius=4)
            vs = self.input_font.render(value, True, self.colors['input_text'])
            self.screen.blit(vs, (frect.x + 8, frect.y + 5))
            if self._ann_gen_active == key:
                cx = frect.x + 8 + vs.get_width() + 2
                pygame.draw.line(self.screen, self.colors['input_text'],
                                 (cx, frect.y + 5), (cx, frect.bottom - 5), 1)
            y += 42
        if self._ann_gen_error:
            es = self.status_font.render(self._ann_gen_error, True,
                                         (255, 120, 120))
            self.screen.blit(es, (dx + 25, y + 4))
            y += 24
        hint = self.status_font.render('孔洞=窗内被围空位；缺口=触窗缘空位（总空位=两者之和）',
                                       True, (150, 150, 160))
        self.screen.blit(hint, (dx + 25, y + 4))
        y += 28

        by = y + 14
        self._ann_gen_ok_btn = pygame.Rect(dx + w // 2 - 90, by, 80, 32)
        self._ann_gen_cancel_btn = pygame.Rect(dx + w // 2 + 10, by, 80, 32)
        self._btn_pair(self._ann_gen_ok_btn, '确定', self._ann_gen_cancel_btn, '取消')

    def _btn_pair(self, ok_rect, ok_text, cancel_rect, cancel_text):
        mouse = pygame.mouse.get_pos()
        c1 = self.colors['button_hover'] if ok_rect.collidepoint(mouse) \
            else self.colors['button_bg']
        pygame.draw.rect(self.screen, c1, ok_rect, border_radius=4)
        s = self.input_font.render(ok_text, True, (255, 255, 255))
        self.screen.blit(s, s.get_rect(center=ok_rect.center))
        c2 = self.colors['button_hover'] if cancel_rect.collidepoint(mouse) \
            else self.colors['button_bg']
        pygame.draw.rect(self.screen, c2, cancel_rect, border_radius=4)
        s = self.input_font.render(cancel_text, True, (255, 255, 255))
        self.screen.blit(s, s.get_rect(center=cancel_rect.center))

    # ==================================================================
    # 存档快照选择对话框
    # ==================================================================
    def _ann_draw_preview_dialog(self):
        data = self._ann_preview_data
        if not data:
            return
        snaps = data.get('history', {}).get('snapshots', [])
        w, h = 560, 240
        dx = (self.screen_width - w) // 2
        dy = (self.screen_height - h) // 2
        overlay = pygame.Surface((self.screen_width, self.screen_height),
                                 pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        dlg = pygame.Rect(dx, dy, w, h)
        self._ann_preview_rect = dlg
        pygame.draw.rect(self.screen, self.colors['dialog_bg'], dlg,
                         border_radius=8)
        pygame.draw.rect(self.screen, self.colors['dialog_border'], dlg, 2,
                         border_radius=8)

        src = os.path.basename(self._ann_preview_src or '')
        title = self.dialog_font.render(f'选择起点快照（{src}）', True,
                                        self.colors['dialog_title'])
        self.screen.blit(title, (dx + 20, dy + 14))

        idx = max(0, min(self._ann_preview_idx, len(snaps) - 1))
        self._ann_preview_idx = idx
        snap = snaps[idx]
        move = snap.get('move_info')
        if idx == 0:
            desc = '（起点：该存档的初始态）'
        elif move:
            gap_type = '横向' if move.get('gap_type') == 'h' else '纵向'
            dname = {'w': '上', 's': '下', 'a': '左', 'd': '右'}.get(
                move.get('direction', ''), move.get('direction') or '')
            n_mv = move.get('merged') or 1
            seg = f'（本段 {n_mv} 步）' if n_mv > 1 else ''
            desc = (f'到达本段{seg}的动作：{gap_type}缝隙 '
                    f'L{move.get("gap_line")} {dname}移 '
                    f'{len(move.get("moved_positions", []))}块')
        else:
            desc = '（无动作信息）'

        line1 = self.input_font.render(
            f'第 {idx} / {len(snaps) - 1} 段快照'
            f'（累计 {snap.get("step_total", idx)} 步）', True, (230, 230, 230))
        self.screen.blit(line1, (dx + 25, dy + 62))
        line2 = self.status_font.render(desc, True, (170, 210, 170))
        self.screen.blit(line2, (dx + 25, dy + 98))
        line3 = self.status_font.render(
            '← → 或点击下方按钮切换快照；回车/应用后以此状态开始标注',
            True, (150, 150, 160))
        self.screen.blit(line3, (dx + 25, dy + 126))

        self._ann_preview_prev_btn = pygame.Rect(dx + 25, dy + 160, 90, 30)
        self._ann_preview_next_btn = pygame.Rect(dx + 125, dy + 160, 90, 30)
        self._btn_pair(self._ann_preview_prev_btn, '上一段',
                       self._ann_preview_next_btn, '下一段')
        self._ann_preview_apply_btn = pygame.Rect(dx + w - 190, dy + 160, 82, 30)
        self._ann_preview_cancel_btn = pygame.Rect(dx + w - 100, dy + 160, 72, 30)
        self._btn_pair(self._ann_preview_apply_btn, '应用起点',
                       self._ann_preview_cancel_btn, '取消')
