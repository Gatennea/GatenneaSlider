# -*- coding: utf-8 -*-
"""
标注模式 Mixin — 人工录制「填洞 / 收敛空位」示范步骤数据集

独立于练习/竞速的全新模式，隐藏入口：同时按住 左Ctrl+右Ctrl+左Shift+右Shift。

学习起点四种来源：
    ① 存档中段（打开任意 save/*.json → 快照步进器选一个状态）
    ② 随机生成（generate_random_void：从还原态拔块，贴同余外圈凸起）
    ③ 手动构造（弹窗小画布逐格点选增删滑块，即时校验合法棋形）
    ④ 当前棋盘状态

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
import time
import random
import pygame

from game import Block
from history import GameHistory  # noqa: F401  （语义参照，不直接实例化）

# ---------------------------------------------------------------------------
# 纯函数工具（独立于 GUI，可 headless 测试）
# ---------------------------------------------------------------------------
_DIR_DELTA = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}


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

    def _ann_init_state(self):
        """初始化标注模式状态（GUI.__init__ 中调用）。"""
        self.annotation_mode = False        # 模式总开关
        self._ann_view = 'home'             # home/target/recording
        self._ann_msg = ''
        self._ann_msg_timer = 0
        # 子对话框
        self._ann_sub_dialog = None         # None / 'gen' / 'preview' / 'build'
        self._ann_gen_fields = {'m': '', 'n': '', 'step': '', 'void': '1'}
        self._ann_gen_active = 'm'
        self._ann_gen_error = ''
        # 手动构造对话框状态
        self._ann_build_fields = {'m': '', 'n': '', 'step': '', 'pad': ''}
        self._ann_build_active = 'm'
        self._ann_build_error = ''
        self._ann_build_coords = set()      # 画布上点出的滑块坐标（全局坐标）
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
    # 隐藏入口：同时按住 左/右 Ctrl + 左/右 Shift
    # ------------------------------------------------------------------
    def _ann_track_toggle_keys(self, event):
        if event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            both_ctrl = (mods & pygame.KMOD_LCTRL) and (mods & pygame.KMOD_RCTRL)
            both_shift = (mods & pygame.KMOD_LSHIFT) and (mods & pygame.KMOD_RSHIFT)
            if event.key in (pygame.K_LCTRL, pygame.K_RCTRL,
                             pygame.K_LSHIFT, pygame.K_RSHIFT) and both_ctrl and both_shift:
                self._ann_toggle_mode()
                return True
        return False

    def _ann_toggle_mode(self):
        """模式总开关（四键触发）。"""
        if self.timer_state == 'running':
            self._ann_notify('计时进行中无法进入标注模式')
            return
        if not self.annotation_mode:
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
        """标注模式事件处理（GUI.handle_events 最先询问），返回 True=已消费。

        关闭状态也需返回 False 并放行普通事件，只在检测到四键入口时消费。
        """
        if not getattr(self, 'annotation_mode', False):
            return self._ann_track_toggle_keys(event)

        # 模式开着：四键仍可再触发（关闭等）
        if self._ann_track_toggle_keys(event):
            return True

        # 其他模态对话框打开时：不抢事件（四键已在上方处理）
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
        keys = ['m', 'n', 'step', 'void', 'pad']
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
        """② 随机生成起点：打开参数对话框（输入框沿用上次内容）。"""
        saved = self._ann_saved('gen')
        fall = {'m': self.current_m, 'n': self.current_n,
                'step': self.current_step, 'void': 1}
        self._ann_gen_fields = {
            k: (saved.get(k) if k in saved else str(fall[k]))
            for k in fall
        }
        self._ann_gen_active = 'm'
        self._ann_gen_error = ''
        self._ann_sub_dialog = 'gen'

    def _ann_btn_manual_build(self):
        """③ 手动构造起点：直接在主棋盘上自由点选。

        进入构造视图后，主棋盘即变成可编辑画布：点空白格放置滑块、
        点已有滑块移除它；改 m/n/step/pad 后按 Enter 重排画布范围。
        底部工具条实时校验并给出「应用并开始 / 还原 m×n / 清空 / 取消」。
        """
        saved = self._ann_saved('build')
        m = int(saved['m']) if 'm' in saved else self.current_m
        n = int(saved['n']) if 'n' in saved else self.current_n
        step = int(saved['step']) if 'step' in saved else self.current_step
        pad = int(saved['pad']) if 'pad' in saved else max(1, step)
        # 备份当前局面：取消构造时可原样恢复（含历史栈）
        self._ann_build_backup = {
            'coords': [list(b.location) for b in self.game.blocks],
            'm': self.current_m, 'n': self.current_n,
            'step': self.current_step,
            'history': self.game_history,
        }
        self._ann_build_fields = {
            'm': str(m), 'n': str(n), 'step': str(step), 'pad': str(pad),
        }
        self._ann_build_active = 'm'
        self._ann_build_error = ''
        # 默认给还原态：可直接点空格挖洞、点窗外空格补凸起
        coords = set(self._ann_solved_coords(m, n))
        self._ann_build_coords = coords
        self.current_m, self.current_n, self.current_step = m, n, step
        self._ann_rebuild_game_from_coords()
        self._ann_sub_dialog = 'build'
        self._ann_view = 'build'
        self.center_map()
        self._ann_notify('构造模式：点格放/取滑块，改好参数后按[应用并开始]')

    def _ann_rebuild_game_from_coords(self):
        """把构造集实时落到主棋盘（不写历史，不打断旧历史）。"""
        self.game.blocks = [Block(list(c))
                            for c in sorted(self._ann_build_coords)]
        self.game.update_matrix()

    def _ann_build_toggle(self, r, c):
        """主棋盘点选：增/删一个滑块并即时刷新状态。"""
        try:
            m, n, step, _pad = self._ann_build_param()
        except ValueError as e:
            self._ann_build_error = str(e)
            return
        lo_r, hi_r, lo_c, hi_c = self._ann_build_grid(m, n, _pad)
        if not (lo_r <= r <= hi_r and lo_c <= c <= hi_c):
            self._ann_build_error = '点选超出可构造范围'
            return
        if (r, c) in self._ann_build_coords:
            self._ann_build_coords.discard((r, c))
        else:
            self._ann_build_coords.add((r, c))
        self._ann_build_error = ''
        self._ann_rebuild_game_from_coords()

    def _ann_build_cancel(self):
        """取消构造：恢复进入前的局面与历史。"""
        bk = getattr(self, '_ann_build_backup', None)
        if bk is not None:
            self.current_m = bk['m']
            self.current_n = bk['n']
            self.current_step = bk['step']
            self.game.blocks = [Block(list(c)) for c in bk['coords']]
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
        """根据 history[idx] 的 move_info 推进跟踪并记录一步。

        若此前在该索引之后曾有旧分支的步骤，先清掉（新移动会截断覆盖）。
        """
        for k in [k for k in self._ann_steps if k >= idx]:
            del self._ann_steps[k]
        snap = self.game_history.history[idx]
        move = snap.get('move_info')
        if not move:
            return
        prev = self.game_history.history[idx - 1]
        prev_cells = self._snapshot_coords(prev)
        cur_cells = self._snapshot_coords(snap)
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

        self._ann_steps[idx] = {
            'phase': self._ann_phase,
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
            keys = ['m', 'n', 'step', 'void']
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
            v = int(self._ann_gen_fields['void'])
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
        if v < 1 or v > (m * n) // 4:
            self._ann_gen_error = f'空位数需在 1 ~ {max(1, (m * n) // 4)}'
            return
        try:
            from solver.ml import ann_gen
            coords, _holes = ann_gen.generate_random_void(
                m, n, step, v, rng=random.Random())
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
        self.center_map()
        self._ann_start_target('gen', f'随机生成 {m}×{n} 空位{v}')
        self._ann_notify(f'已生成：{m}×{n} step{step} 空位 {v} 个，请选目标')

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
            snap = history[idx]
            move = snap.get('move_info')
            if rec is None or not move:
                continue
            pre = history[idx - 1]
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
                'track_void': rec.get('void'),
                'track_anchor': rec.get('anchor'),
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
        """标注模式渲染入口（run 循环里、浮动面板之后调用）。"""
        if not getattr(self, 'annotation_mode', False):
            return
        if self._ann_view == 'build':
            self._ann_draw_build_dialog()
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
        y, h = self.screen_height - self.status_bar_height - \
            self._ANN_BAR_H - 8, self._ANN_BAR_H
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
            add('exit_mode', '退出标注', (120, 90, 90))
            add('from_current', '④ 当前状态', (70, 120, 180))
            add('manual_build', '③ 手动构造起点', (70, 120, 180))
            add('random_gen', '② 随机生成起点', (70, 120, 180))
            add('from_save', '① 存档中段选起点', (70, 120, 180))
            title = self.status_font.render(
                '标注模式：录制「填洞/收敛空位」示范 · 隐藏入口=左右Ctrl+左右Shift',
                True, (200, 200, 210))
            self.screen.blit(title, (self._ann_bar_rect.x + 6,
                                     self._ann_bar_rect.y - 18))
        elif self._ann_view == 'build':
            # 参数输入（m / n / step / pad）
            self._ann_build_field_rects = {}
            fx = x + 10
            for key, lab in (('m', '行'), ('n', '列'),
                             ('step', '级'), ('pad', '外扩')):
                ls = self.status_font.render(lab, True, (210, 210, 225))
                self.screen.blit(ls, (fx, y + (h - ls.get_height()) // 2 + 3))
                frect = pygame.Rect(fx + ls.get_width() + 6, y + 13, 44, h - 26)
                self._ann_build_field_rects[key] = frect
                fbg = (self.colors['input_active']
                       if self._ann_build_active == key
                       else self.colors['input_bg'])
                pygame.draw.rect(self.screen, fbg, frect, border_radius=4)
                pygame.draw.rect(self.screen, (120, 120, 140), frect, 1,
                                 border_radius=4)
                txt = self.input_font.render(
                    self._ann_build_fields.get(key, ''),
                    True, self.colors['input_text'])
                self.screen.blit(txt, (frect.x + 5, frect.y + 2))
                if self._ann_build_active == key:
                    cx = frect.x + 5 + txt.get_width() + 2
                    pygame.draw.line(self.screen, self.colors['input_text'],
                                     (cx, frect.y + 2), (cx, frect.bottom - 2), 1)
                x = frect.right + 12
            add('build_ok', '应用并开始', (60, 150, 90))
            add('build_reset', '还原m×n')
            add('build_clear', '清空')
            add('build_cancel', '退出', (150, 90, 90))
            # 实时校验状态
            try:
                mm, nn, ss, pp = self._ann_build_param()
                msg, is_ok = self._ann_build_status(mm, nn, ss)
                oob = self._ann_build_oob(mm, nn, pp)
                if oob:
                    msg = f'{len(oob)} 格越出可构造范围，调大外扩或移除'
                    is_ok = False
            except ValueError as e:
                msg, is_ok = str(e), False
            if self._ann_build_error:
                msg, is_ok = self._ann_build_error, False
            color = (150, 230, 160) if is_ok else (255, 150, 140)
            title = self.status_font.render('手动构造  ' + msg,
                                            True, color)
            self.screen.blit(title, (self._ann_bar_rect.x + 6,
                                     self._ann_bar_rect.y - 18))
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
                n_steps = sum(1 for k in self._ann_steps
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

    # ---- 状态提示（工具条右下方小字） ----
    def _ann_draw_msg(self):
        if self._ann_msg_timer > 0:
            self._ann_msg_timer -= 1

    # ==================================================================
    # 手动构造对话框（自由点选画布）
    # ==================================================================
    def _ann_build_param(self):
        """解析构造参数 → (m,n,step,pad) 或抛 ValueError。"""
        m = int(self._ann_build_fields.get('m') or 0)
        n = int(self._ann_build_fields.get('n') or 0)
        step = int(self._ann_build_fields.get('step') or 0)
        pad = int(self._ann_build_fields.get('pad') or 0)
        if m < 2 or n < 2:
            raise ValueError('m、n 必须 >= 2')
        if step < 1:
            raise ValueError('等级必须 >= 1')
        if step >= max(m, n):
            raise ValueError(f'等级必须 < {max(m, n)}')
        if pad < 1 or pad > 8:
            raise ValueError('画布外扩 pad 需在 1 ~ 8')
        return m, n, step, pad

    def _ann_build_grid(self, m, n, pad):
        """画布网格边界（全局坐标）。"""
        return (-pad, m - 1 + pad, -pad, n - 1 + pad)

    def _ann_build_oob(self, m, n, pad):
        """画布外扩 pad 之外是否有滑块。返回越界坐标列表。"""
        lo_r, hi_r, lo_c, hi_c = self._ann_build_grid(m, n, pad)
        return [c for c in self._ann_build_coords
                if not (lo_r <= c[0] <= hi_r and lo_c <= c[1] <= hi_c)]

    def _ann_build_status(self, m, n, step):
        """即时校验状态：返回 (text, is_ok)。"""
        from solver.ml import ann_gen
        coords = frozenset(self._ann_build_coords)
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
        """构造视图：点底部工具条（输入框/按钮）或直接点棋盘增删滑块。"""
        if self._ann_bar_rect and self._ann_bar_rect.collidepoint(x, y):
            for key, rect in self._ann_build_field_rects.items():
                if rect.collidepoint(x, y):
                    self._ann_build_active = key
                    return True
            self._ann_click_button(x, y)
            return True
        cell = self.get_cell_at_pos(x, y)
        if cell is None:
            return True
        self._ann_build_toggle(*cell)
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
            keys = ['m', 'n', 'step', 'pad']
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
        """校验当前构造 → 写历史并进入选目标阶段。"""
        try:
            m, n, step, _pad = self._ann_build_param()
        except ValueError as e:
            self._ann_build_error = str(e)
            return
        from solver.ml import ann_gen
        coords = frozenset(self._ann_build_coords)
        ok, msg = ann_gen.validate_state(coords, m, n, step)
        if not ok:
            self._ann_build_error = f'非法棋形：{msg}'
            return
        if self._ann_build_oob(m, n, _pad):
            self._ann_build_error = '有滑块超出可构造范围，调大外扩或移除越界格'
            return
        vm = window_void_metrics(coords, m, n, step)
        if vm['void_block_count'] < 1:
            self._ann_build_error = '窗内没有空位，无法作为填洞示范起点'
            return
        self._ann_build_error = ''
        self._ann_store_inputs('build', self._ann_build_fields)
        self.current_m, self.current_n, self.current_step = m, n, step
        self._ann_rebuild_game_from_coords()
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self.center_map()
        self._ann_build_backup = None
        self._ann_start_target('build', f'手动构造 {m}×{n} step{step} '
                                        f'（{len(coords)} 颗）')
        self._ann_notify('已应用手动构造，请点目标空位与凸起')

    def _ann_build_reset(self):
        """还原为完整 m×n（无洞无凸起），从点空格挖洞开始。"""
        try:
            m, n, step, _pad = self._ann_build_param()
        except ValueError as e:
            self._ann_build_error = str(e)
            return
        self._ann_build_coords = set(self._ann_solved_coords(m, n))
        self._ann_build_error = ''
        self._ann_rebuild_game_from_coords()

    def _ann_build_clear(self):
        """清空全部滑块，从零开始铺。"""
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

    def _ann_draw_build_dialog(self):
        """主棋盘构造叠加层：可构造范围网格 + 目标窗口高亮。

        棋盘上的滑块由主渲染器绘制；这里补画空格轮廓与目标窗口框，
        让用户直接在主窗口点选增删滑块。
        """
        self._ann_build_field_rects = {}
        try:
            m, n, _step, pad = self._ann_build_param()
        except ValueError:
            return
        stepw = self.cell_size + self.gap_width
        cs = self.cell_size * self.zoom
        # 空格轮廓（有滑块处主渲染器已画）
        for r in range(-pad, m + pad):
            for c in range(-pad, n + pad):
                if (r, c) in self._ann_build_coords:
                    continue
                x, y = self.world_to_screen(c * stepw, r * stepw)
                pygame.draw.rect(self.screen, (70, 95, 120),
                                 pygame.Rect(int(x), int(y),
                                             max(1, int(cs)),
                                             max(1, int(cs))), 1)
        # 目标窗口（0..m-1 × 0..n-1）高亮框
        x0, y0 = self.world_to_screen(0, 0)
        x1, y1 = self.world_to_screen(n * stepw, m * stepw)
        pygame.draw.rect(self.screen, (120, 210, 255),
                         pygame.Rect(int(x0), int(y0),
                                     max(1, int(x1 - x0)),
                                     max(1, int(y1 - y0))), 2)

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
        w, h = 340, 320
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
        title = self.dialog_title_font.render("随机生成标注起点", True,
                                              self.colors['dialog_title'])
        self.screen.blit(title, (dx + 20, dy + 15))

        fields = [
            ('m', '行数:', self._ann_gen_fields['m']),
            ('n', '列数:', self._ann_gen_fields['n']),
            ('step', '等级:', self._ann_gen_fields['step']),
            ('void', '空位格数:', self._ann_gen_fields['void']),
        ]
        self._ann_gen_field_rects = {}
        y = dy + 55
        for key, label, value in fields:
            ls = self.input_font.render(label, True, self.colors['dialog_text'])
            self.screen.blit(ls, (dx + 25, y + 4))
            frect = pygame.Rect(dx + 175, y, 110, 30)
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
        hint = self.status_font.render('生成后从还原态挖空位并贴同余外圈凸起',
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
                move.get('direction', ''), move.get('direction', ''))
            desc = f'到达本步的动作：{gap_type}缝隙 L{move.get("gap_line")} {dname}移 {len(move.get("moved_positions", []))}块'
        else:
            desc = '（无动作信息）'

        line1 = self.input_font.render(
            f'第 {idx} / {len(snaps) - 1} 步快照', True, (230, 230, 230))
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
