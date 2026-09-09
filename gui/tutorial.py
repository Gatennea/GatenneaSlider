# -*- coding: utf-8 -*-
"""
新手教程 Mixin（闯关模式）

实现闯关模式与新手教程：
- 教程进度持久化（config.json 的 tutorial 键）
- 关卡数据驱动元数据（TUTORIAL_LEVELS，含子题 sublevels / 待补充 pending）
- 文案抽离：正文集中存于 gui/tutorial_texts.json（本模块加载，代码内不写正文）
- 关卡列表选择：进入教程先显示可玩/锁定的关卡列表
- 第 1 关：交互操作教学状态机（点缝隙→点滑块→移动→撤销→重做→复原演示→规则讲解+过关）
- 第 2/3/4 关：每关含多个子题（填洞/多洞分组/缺口），每子题「少量引导+还原过关」，
  按子题序号依次通过；第 5/6 关维持“待补充”锁定
- 解法查看：
  - 第 1 关 1.json 无 move_info → 回退既有自动求解器
  - 第 2/3/4 关存档含完整 move_info 链 → 直接回放（更稳定快速）
  - 查看解法时临时调慢动画速度，解法结束后（宏播放结束）自动还原
- 过关判定与解锁（复用 is_solved / _maybe_show_solved_popup 管道）
"""

import os
import json

import pygame

# 项目根目录（beginner_archive 所在处 = GUI.py 所在目录的上一级）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 查看解法时的动画速度（毫秒/步，越小越快；默认 300 → 临时调慢到此值）
SOLUTION_ANIM_MS = 600

# ---------------- 文案（从 JSON 加载，代码内不写正文） ----------------
_TEXT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tutorial_texts.json')
try:
    with open(_TEXT_FILE, 'r', encoding='utf-8') as _f:
        _TUT_TEXTS = json.load(_f)
except Exception as _e:  # 文案加载失败不致命，回退空字典
    print(f"[教程] 文案文件加载失败: {_e}")
    _TUT_TEXTS = {}


def _text_level(level_id):
    """取某关的文案节点（缺失时返回空 dict）"""
    return _TUT_TEXTS.get('levels', {}).get(str(level_id), {})


# ---------------- 关卡元数据（数据驱动层） ----------------
# 后续新增关卡只需在此追加条目（含子题与“困难任务”扩展位），无需改教程代码。
TUTORIAL_LEVELS = [
    {
        'id': 1,
        'title': '第 1 关·基本操作',
        'sublevels': ['1'],
        'pending': False,
    },
    {
        'id': 2, 'title': '第 2 关·填洞',
        'sublevels': ['2.1', '2.2', '2.3'],
        'pending': False,
    },
    {
        'id': 3, 'title': '第 3 关·多洞与分组',
        'sublevels': ['3.1', '3.2'],
        'pending': False,
    },
    {
        'id': 4, 'title': '第 4 关·缺口',
        'sublevels': ['4.1', '4.2', '4.3'],
        'pending': False,
    },
    # ---- 后续关卡扩展位（存稿/元数据未齐备，教程中显示“待补充”） ----
    {'id': 5, 'title': '第 5 关·刚体凸起', 'sublevels': [], 'pending': True},
    {'id': 6, 'title': '第 6 关·综合',     'sublevels': [], 'pending': True},
]
TUTORIAL_LEVELS_BY_ID = {lv['id']: lv for lv in TUTORIAL_LEVELS}

# 子题 id -> 存档路径
SUBLEVEL_ARCHIVE = {
    '1': 'beginner_archive/1.json',
    '2.1': 'beginner_archive/2.1.json',
    '2.2': 'beginner_archive/2.2.json',
    '2.3': 'beginner_archive/2.3.json',
    '3.1': 'beginner_archive/3.1.json',
    '3.2': 'beginner_archive/3.2.json',
    '4.1': 'beginner_archive/4.1.json',
    '4.2': 'beginner_archive/4.2.json',
    '4.3': 'beginner_archive/4.3.json',
}


def _sublevel_title(sublevel_id):
    """取子题显示标题（如 2.1 单洞填補）"""
    if sublevel_id == '1':
        return _text_level(1).get('title', '第 1 关')
    for lv in TUTORIAL_LEVELS:
        t = _text_level(lv['id']).get('sublevel_titles', {}).get(sublevel_id)
        if t:
            return t
    return sublevel_id


# 面板 UI 配色
_TUT_PANEL_BG = (28, 30, 40, 238)
_TUT_TITLE_CLR = (240, 195, 90)
_TUT_TEXT_CLR = (215, 218, 228)
_TUT_BTN_BG = (58, 62, 78)
_TUT_BTN_HOVER = (82, 88, 108)
_TUT_BTN_TXT = (235, 238, 245)
_TUT_BTN_MAIN_BG = (92, 76, 40)
_TUT_BTN_MAIN_HOVER = (120, 100, 52)
_TUT_LOCKED_BG = (48, 48, 55)
_TUT_LOCKED_TXT = (150, 150, 155)


class TutorialMixin:
    """新手教程相关方法 Mixin"""

    # ---------------- 初始化与进度管理 ----------------

    def _tut_init_state(self):
        """初始化教程状态（在 __init__ 尾部、load_last_state() 之前调用）"""
        self.tutorial_active = False      # 是否处于教程模式
        self.tut_level = 1                # 当前教程关卡 id
        self.tut_sublevel = None          # 当前子题 id（如 '2.1'；关卡1为 None）
        self.tut_step = 0                 # 步骤：关卡1=状态机(1-7)；2/3/4 关 1=子题还原 7=已过关
        self.tut_selecting_levels = False # 是否显示关卡选择列表
        self.tut_solution_ops = []        # 当前子题的解法回放 ops（关卡1为 [] 走自动求解器）
        self.tut_anim_slowed = False      # 查看解法是否已临时调慢动画
        self.tut_solution_playing = False # 解法是否正在播放（用于结束时还原动画速度）
        self._tut_saved_anim_duration = 300
        self.tut_progress = {
            'started': False,             # 是否开始过教程（开始/跳过后为 True，用于首次启动弹窗判定）
            'skipped': False,             # 是否跳过了教程
            'completed': [],              # 已完成关卡 id 列表
            'subcompleted': {},           # {关卡id: [已完成子题id]} 用于 2/3/4 关的子题顺序进度
            'current': None,              # 最近进入的关卡 id
        }
        self.tut_show_prompt = False      # 首次启动引导弹窗
        self.tut_btn_rects = []           # 教学面板按钮矩形（每帧绘制时重建）
        self.tut_level_btn_rects = []     # 关卡选择列表按钮矩形
        self.tut_prompt_btn_rects = []    # 首次启动弹窗按钮矩形
        # 教学面板正文滚动状态（自动换行 + 滚动条，复用 help 对话框模式）
        self.tut_panel_scroll = 0
        self.tut_panel_scrollbar_dragging = False
        self.tut_panel_drag_start_y = 0
        self.tut_panel_rect = None        # 面板整体矩形（事件/滚轮判定用，每帧重建）
        self.tut_panel_content_h = 0      # 正文可视区高度（绘制时更新）
        self.tut_panel_total_h = 0        # 正文换行后总高度（绘制时更新）
        self.tut_panel_scrollbar_rect = None
        self.tut_panel_scrollbar_knob_rect = None

    def _tut_menu_name(self):
        """菜单栏「教程」入口的显示名（随进度变化）：可随时回顾/重玩"""
        cleared = [int(x) for x in self.tut_progress.get('completed', [])]
        if self.tutorial_active or self.tut_progress.get('started'):
            return '回顾教程' if cleared else '继续教程'
        return '新手教程'

    def _tut_check_first_launch(self):
        """首次启动自动弹出引导（load_last_state() 之后调用）"""
        if (not self.tut_progress.get('started')
                and not self.tut_progress.get('skipped')):
            self.tut_show_prompt = True

    def _tut_is_started(self) -> bool:
        return bool(self.tut_progress.get('started'))

    def _tut_is_skipped(self) -> bool:
        return bool(self.tut_progress.get('skipped'))

    def _tut_completed_levels(self) -> list:
        return list(self.tut_progress.get('completed', []))

    def _tut_is_completed(self, level_id: int) -> bool:
        return level_id in self.tut_progress.get('completed', [])

    def _tut_completed_sublevels(self, level_id: int) -> list:
        return list(self.tut_progress.get('subcompleted', {}).get(level_id, []))

    def _tut_save_progress(self):
        """将进度写入 config.json（幂等，失败不阻塞）"""
        try:
            self.save_config()
        except Exception as e:
            print(f"[教程] 保存进度失败: {e}")

    # ---------------- 关卡选择列表 ----------------

    def _tut_show_level_select(self):
        """显示关卡选择列表（教学面板切换为关卡列表视图）"""
        self._tut_restore_anim_speed()
        self.tutorial_active = True
        self.tut_selecting_levels = True
        self.tut_level = 0          # 关卡列表视图用『0』表示（标题显示“选择关卡”）
        self.tut_step = 0
        self.tut_panel_scroll = 0
        self._update_window_title()

    def _tut_start(self):
        """教程入口：显示关卡选择列表（不直接载入某一关）"""
        if self.tut_show_prompt:
            self.tut_show_prompt = False
        self.tut_progress['started'] = True
        self._tut_save_progress()
        self._tut_show_level_select()

    def _tut_skip(self):
        """跳过教程：回到普通练习模式，已完成进度保留"""
        self.tutorial_active = False
        self.tut_selecting_levels = False
        self.tut_show_prompt = False
        self.tut_progress['started'] = True
        self.tut_progress['skipped'] = True
        self._tut_save_progress()
        self.macro_notify_msg = "已跳过教程，回到练习模式"
        self.macro_notify_timer = 180

    def _tut_exit(self):
        """主动退出教程：回到普通练习模式"""
        self.tutorial_active = False
        self.tut_selecting_levels = False
        self._tut_restore_anim_speed()
        if not self.tut_progress.get('started'):
            self.tut_progress['started'] = True
        self._tut_save_progress()
        self._update_window_title()
        self.macro_notify_msg = "已回到练习模式"
        self.macro_notify_timer = 120

    # ---------------- 关卡 / 子题载入 ----------------

    def _tut_load_level(self, level_id: int) -> bool:
        """载入指定关卡：
        - 第 1 关：进入操作教学（完整 4×4 演示盘，步骤 1）
        - 第 2/3/4 关：进入该关第一个未完成的子题（均已完成则从第一个重玩）
        - 待补充关返回 False
        """
        level = TUTORIAL_LEVELS_BY_ID.get(level_id)
        if level is None or level.get('pending'):
            self.macro_notify_msg = "此关卡待补充"
            self.macro_notify_timer = 180
            return False

        self._stop_continuous_undo_redo()
        self.game_mode = 'practice'
        if getattr(self, 'macro_executing', False):
            self.macro_executing = False
        if getattr(self, '_auto_solve_running', False):
            self._auto_solve_cancel = True
        self._tut_restore_anim_speed()
        self.tut_selecting_levels = False
        self.tutorial_active = True
        self.tut_level = level_id
        self.tut_progress['started'] = True
        self.tut_progress['current'] = level_id

        if level_id == 1:
            # 关卡1：完整 4×4 演示盘（底部标题 2~4*4）教操作与断开规则
            self.new_puzzle(4, 4, 2)
            self.current_file_path = None
            self._reset_file_dirty()
            self.center_map()
            self.tut_sublevel = None
            self.tut_step = 1
            self.tut_solution_ops = []
            self._tut_save_progress()
            self.macro_notify_msg = level['title']
            self.macro_notify_timer = 180
            return True

        # 第 2/3/4 关：选第一个未完成子题
        subs = level['sublevels']
        done = self.tut_progress.setdefault('subcompleted', {}).setdefault(level_id, [])
        start = next((s for s in subs if s not in done), subs[0])
        self._tut_save_progress()
        return self._tut_load_sublevel(start)

    def _tut_load_sublevel(self, sublevel_id: str) -> bool:
        """载入某子题的打乱题并进入“还原过关”步骤（tut_step=1）。

        从存档 rebuild history 后跳回 index 0（打乱态）供玩家还原，
        并预计算该子题的解法回放 ops（存档含完整 move_info 链）。
        """
        archive = SUBLEVEL_ARCHIVE.get(sublevel_id)
        level_id = self._tut_level_of_sublevel(sublevel_id)
        if not archive:
            self.macro_notify_msg = "此关卡待补充"
            self.macro_notify_timer = 180
            return False
        path = os.path.join(_PROJECT_ROOT, archive)
        if not os.path.exists(path):
            self.macro_notify_msg = f"关卡存档缺失：{archive}"
            self.macro_notify_timer = 240
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
        except Exception as e:
            self.macro_notify_msg = "关卡存档读取失败"
            self.macro_notify_timer = 240
            print(f"[教程] 读取存档失败: {e}")
            return False

        # 停掉可能正在进行的计时/求解/动画
        self.game_mode = 'practice'
        if getattr(self, 'macro_executing', False):
            self.macro_executing = False
        if getattr(self, '_auto_solve_running', False):
            self._auto_solve_cancel = True
        self._tut_restore_anim_speed()
        self.tut_selecting_levels = False
        self.tutorial_active = True
        self.tut_level = level_id
        self.tut_sublevel = sublevel_id
        self.tut_step = 1
        self.tut_panel_scroll = 0

        self._stop_continuous_undo_redo()
        self._load_save_data(save_data)
        self.current_file_path = None
        self._reset_file_dirty()
        # 跳到打乱态（index 0）：history_index 可能停在还原态，必须回到起点供玩家还原
        if len(self.game_history.history) > 0:
            self.jump_to_history_index(0)
        self.center_map()

        # 预计算解法回放 ops（存档含完整 move_info 链）
        self.tut_solution_ops = self._tut_compute_solution_ops(save_data)

        self.macro_notify_msg = f"第 {level_id} 关 · {_sublevel_title(sublevel_id)}"
        self.macro_notify_timer = 180
        return True

    def _tut_level_of_sublevel(self, sublevel_id: str) -> int:
        for lv in TUTORIAL_LEVELS:
            if sublevel_id in lv['sublevels']:
                return lv['id']
        return 0

    @staticmethod
    def _tut_compute_solution_ops(save_data) -> list:
        """把存档的 move_info 链转为宏执行 op 列表。

        存档 snapshots[i].move_info 描述从状态 i-1 到 i 的移动，
        moved_positions 是「移动前」的位置集合（事件写入时在 commit_move 之前
        取 b.location；annotation.move_group_geometry 亦按此约定）。
        因此 rep_cell 直接用 moved_positions[0]（移动前坐标，宏执行时该格必存在），
        side 依该格相对缝隙线的位置推断（同 infer_side 约定）。
        """
        ops = []
        snapshots = save_data.get('history', {}).get('snapshots', [])
        for snap in snapshots:
            mi = snap.get('move_info')
            if not mi:
                continue
            gap_type = mi.get('gap_type')
            gap_line = mi.get('gap_line')
            direction = mi.get('direction')
            step = mi.get('step', 1)
            moved = mi.get('moved_positions') or []
            if not moved or not gap_type or not direction:
                continue
            rr, cc = moved[0]
            # side（缝隙哪一侧，宏执行 rep_cell 未命中时的 fallback）：
            # h 缝隙：above=r<=gap_line / below=r>gap_line；v 缝隙：left=c<=gap_line / right=c>gap_line
            if gap_type == 'h':
                side = 'below' if rr > gap_line else 'above'
            else:
                side = 'right' if cc > gap_line else 'left'
            ops.append({
                'gap_type': gap_type,
                'gap_line': gap_line,
                'side': side,
                'direction': direction,
                'step': step,
                'rep_cell': [rr, cc],
            })
        return ops

    # ---------------- 教学状态机 ----------------

    def _tut_reload_challenge(self):
        """（第 1 关）切回 3×3 打乱挑战盘（讲解步长/尺寸时底部标题显示 1~3*3）。"""
        path = os.path.join(_PROJECT_ROOT, 'beginner_archive/1.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
        except Exception as e:
            self.macro_notify_msg = "关卡存档读取失败"
            self.macro_notify_timer = 240
            print(f"[教程] 读取关卡存档失败: {e}")
            return
        self._stop_continuous_undo_redo()
        self._load_save_data(save_data)
        self.current_file_path = None
        self._reset_file_dirty()
        self.center_map()

    def _tut_set_step(self, n: int):
        """推进教学步骤（第 1 关）：
        1-5 在完整 4×4 演示盘（底部标题 2~4*4）教操作与断开规则；
        6 = 合并步骤：切回 3×3 挑战盘（底部标题 1~3*3），讲步长/尺寸并还原过关；
        7 = 已过关。
        """
        self.tut_step = n
        self.tut_panel_scroll = 0
        if n == 6:
            self._tut_reload_challenge()
            self.macro_notify_msg = "请把 3×3 打乱题还原成完整矩形（底部标题 1~3*3）"
            self.macro_notify_timer = 220
        elif n == 7:
            self._tut_restore_anim_speed()

    def _tut_on_gap_clicked(self):
        """玩家点击了一条缝隙（events.py 缝隙选中处挂接）"""
        if not self.tutorial_active or getattr(self, 'macro_executing', False):
            return
        if self.tut_selecting_levels:
            return
        if self.tut_level == 1 and self.tut_step == 1:
            self._tut_set_step(2)

    def _tut_on_block_clicked(self):
        """玩家点击了滑块（events.py 滑块选中处挂接）"""
        if not self.tutorial_active or getattr(self, 'macro_executing', False):
            return
        if self.tut_selecting_levels:
            return
        if self.tut_level == 1 and self.tut_step == 2:
            self._tut_set_step(3)

    def _tut_on_state_commit(self, via_redo: bool = False, suppress: bool = False):
        """状态提交后检测教学进度（挂在 _maybe_show_solved_popup 末尾）。

        提交来源：
        - 移动：via_redo=False, suppress=False
        - 撤销：suppress=True
        - 重做：via_redo=True
        - 解法播放/宏执行：步骤 3/4/5 一律忽略（不推进教程、不误过关）；
          步骤 6（关卡1）或子题还原（2/3/4 关）允许（查看解法自动还原后应算过关）
        """
        if not self.tutorial_active:
            return
        if self.tut_selecting_levels:
            return
        mac = getattr(self, 'macro_executing', False)

        # 第 2/3/4 关：子题还原过关
        if self.tut_level in (2, 3, 4):
            if self.tut_step == 1 and not via_redo and not suppress and self.is_solved():
                self._tut_advance_sublevel()
            return

        # 第 1 关原有状态机
        if self.tut_step == 3 and not mac and not via_redo and not suppress:
            self._tut_set_step(4)
        elif self.tut_step == 4 and not mac and suppress:
            self._tut_set_step(5)
        elif self.tut_step == 5 and not mac and via_redo:
            self._tut_set_step(6)
        elif self.tut_step == 6 and not via_redo and not suppress and self.is_solved():
            self._tut_complete()

    def _tut_advance_sublevel(self):
        """（第 2/3/4 关）子题解决：记录已完成并推进到下一子题；最后一个子题则过关"""
        level_id = self.tut_level
        level = TUTORIAL_LEVELS_BY_ID.get(level_id, {})
        subs = level.get('sublevels', [])
        cur = self.tut_sublevel
        sc = self.tut_progress.setdefault('subcompleted', {}).setdefault(level_id, [])
        if cur and cur not in sc:
            sc.append(cur)
        self._tut_save_progress()

        idx = subs.index(cur) if cur in subs else len(subs) - 1
        self._tut_restore_anim_speed()

        if idx + 1 < len(subs):
            nxt = subs[idx + 1]
            self._tut_load_sublevel(nxt)
            self.macro_notify_msg = f"{_sublevel_title(cur)} 还原成功，进入下一小題"
            self.macro_notify_timer = 200
        else:
            self._tut_complete()

    def _tut_complete(self):
        """过关：记录完成、解锁下一关（第 5/6 关本期显示“待补充”锁定）"""
        self.tut_step = 7
        self._tut_restore_anim_speed()
        completed = self.tut_progress.setdefault('completed', [])
        if self.tut_level not in completed:
            completed.append(self.tut_level)
        self.tut_progress['current'] = self.tut_level
        self._tut_save_progress()
        notify = _text_level(self.tut_level).get('complete_notify') or f"过关！第 {self.tut_level} 关完成"
        self.macro_notify_msg = notify
        self.macro_notify_timer = 240

    # ---------------- 解法查看 / 动画速度 ----------------

    def _tut_show_solution(self):
        """查看解法：
        - 第 1 关：回退自动求解器
        - 第 2/3/4 关：回放存档 move_info 链
        同时临时调慢动画速度，解法结束后由 draw_tutorial_panel 还原。
        """
        if not self.tutorial_active or self.tut_selecting_levels:
            return
        if getattr(self, '_readonly_blocked', lambda: False)():
            return
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法查看解法"
            self.macro_notify_timer = 90
            return

        # 临时调慢动画速度
        if not self.tut_anim_slowed:
            self.tut_anim_slowed = True
            self._tut_saved_anim_duration = self.animation_duration
            self.animation_duration = max(self.animation_duration, SOLUTION_ANIM_MS)

        if self.tut_level == 1:
            self._start_auto_solve()  # 求解/回放/中途打断均由既有管道处理
            return

        # 2/3/4 关：直接回放存档解法 ops
        if not self.tut_solution_ops:
            self.macro_notify_msg = "此关暂无可回放的解法"
            self.macro_notify_timer = 180
            return
        if getattr(self, 'macro_executing', False) or getattr(self, 'animating', False):
            return
        self.macro_executing = True
        self.macro_exec_name = "查看解法"
        self.macro_exec_ops = list(self.tut_solution_ops)
        self.macro_exec_index = 0
        self.macro_exec_factor = 1
        self._execute_next_macro_step()

    def _tut_restore_anim_speed(self):
        """还原被“查看解法”临时调慢的动画速度（幂等）"""
        if self.tut_anim_slowed:
            self.animation_duration = self._tut_saved_anim_duration
        self.tut_anim_slowed = False
        self.tut_solution_playing = False

    def _tut_tick_restore_anim_speed(self):
        """绘制/主循环钩子：解法播放结束后自动还原动画速度。

        开始时（macro/_auto_solve 在跑）标记 playing；结束后（都不在跑）还原。
        _start_auto_solve 同步置 _auto_solve_running=True，故无需处理“请求后首帧”竞态。
        """
        if not self.tut_anim_slowed:
            return
        playing = (getattr(self, 'macro_executing', False)
                   or getattr(self, '_auto_solve_running', False))
        if playing:
            self.tut_solution_playing = True
        else:
            self._tut_restore_anim_speed()

    def _tut_reset_level(self):
        """重置本关/本子题：跳回打乱态"""
        if not self.tutorial_active or self.tut_selecting_levels:
            return
        if len(self.game_history.history) > 0:
            self.jump_to_history_index(0)
            self.selected_gap = None
            self.selected_block = None
        self.macro_notify_msg = "已重置本关打乱态"
        self.macro_notify_timer = 120

    # ---------------- 事件挂接 ----------------

    def _tut_handle_panel_click(self, x: int, y: int) -> bool:
        """教学面板按钮点击；命中返回 True（事件被消费）"""
        if getattr(self, 'tut_selecting_levels', False):
            for btn in self.tut_level_btn_rects:
                if btn['rect'].collidepoint(x, y):
                    if btn['action'] == 'load':
                        self._tut_load_level(btn['level'])
                    elif btn['action'] == 'exit':
                        self._tut_exit()
                    return True
            return False

        for btn in self.tut_btn_rects:
            if btn['rect'].collidepoint(x, y):
                action = btn['action']
                if action == 'solution':
                    self._tut_show_solution()
                elif action == 'skip':
                    self._tut_skip()
                elif action == 'help':
                    self.show_help = True
                    self.help_scroll_offset = 0
                elif action == 'reset':
                    self._tut_reset_level()
                elif action == 'level_select':
                    self._tut_show_level_select()
                elif action == 'exit':
                    self._tut_exit()
                return True
        return False

    def _tut_handle_prompt_click(self, x: int, y: int) -> bool:
        """首次启动弹窗按钮点击；命中返回 True"""
        for btn in self.tut_prompt_btn_rects:
            if btn['rect'].collidepoint(x, y):
                if btn['action'] == 'start':
                    self._tut_start()
                else:
                    self._tut_skip()
                return True
        return False

    def _tut_handle_panel_scroll(self, event) -> bool:
        """教学面板滚动事件（滚轮 / 滚动条拖拽 / 点击空白跳转）。

        复用 help 对话框滚动模式（events.py 中 help 分支的等价实现）。
        命中返回 True（事件被消费；按钮点击在 events.py 中优先于本方法处理）。
        """
        rect = getattr(self, 'tut_panel_rect', None)
        if rect is None:
            return False
        max_scroll = max(0, getattr(self, 'tut_panel_total_h', 0)
                         - getattr(self, 'tut_panel_content_h', 0))

        if event.type == pygame.MOUSEWHEEL:
            pos = getattr(event, 'pos', None) or pygame.mouse.get_pos()
            if not rect.collidepoint(pos):
                return False
            self.tut_panel_scroll = max(0, min(
                self.tut_panel_scroll - event.y * 30, max_scroll))
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not rect.collidepoint(event.pos):
                return False
            sb = getattr(self, 'tut_panel_scrollbar_rect', None)
            knob = getattr(self, 'tut_panel_scrollbar_knob_rect', None)
            if sb and knob and knob.collidepoint(event.pos):
                self.tut_panel_scrollbar_dragging = True
                self.tut_panel_drag_start_y = event.pos[1] - knob.top
                return True
            if sb and sb.collidepoint(event.pos):
                ratio = (event.pos[1] - sb.top) / sb.height
                self.tut_panel_scroll = int(ratio * max_scroll)
                return True
            return False

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.tut_panel_scrollbar_dragging:
                self.tut_panel_scrollbar_dragging = False
                return True
            return False

        if event.type == pygame.MOUSEMOTION:
            if getattr(self, 'tut_panel_scrollbar_dragging', False):
                sb = getattr(self, 'tut_panel_scrollbar_rect', None)
                if sb:
                    rel_y = event.pos[1] - sb.top - self.tut_panel_drag_start_y
                    ratio = max(0.0, min(1.0, rel_y / (sb.height - 20)))
                    self.tut_panel_scroll = int(ratio * max_scroll)
                    return True
            return False

        return False

    # ---------------- 渲染 ----------------

    def _tut_wrap_step_text(self, text: str, font, max_width: int) -> list:
        """把步骤正文（含 \n 段落与空行）转为换行后的行列表。

        复用 renderer._wrap_text；空段落保留为 ''（对应一行空行），
        使换行后行数可直接换算总高度（行高 * 行数）。
        """
        out = []
        for paragraph in (text or '').split('\n'):
            if not paragraph:
                out.append('')
            else:
                out.extend(self._wrap_text(paragraph, font, max_width))
        return out

    def _tut_current_step_text(self) -> str:
        """当前应显示的正文（按 关卡/步骤/子题 选择）"""
        if self.tut_level == 1:
            return _text_level(1).get('steps', {}).get(str(self.tut_step), '')
        if self.tut_step == 7:
            return _text_level(self.tut_level).get(
                'complete_notify', f"✓ 过关！第 {self.tut_level} 关完成")
        # 2/3/4 关：子题引导 + 还原目标
        return (_text_level(self.tut_level).get('sublevels', {}).get(self.tut_sublevel, '')
                or '请把这块拼图还原成完整矩形，即可过关！')

    def draw_tutorial_prompt(self):
        """首次启动引导弹窗（居中模态）"""
        if not getattr(self, 'tut_show_prompt', False):
            return
        w, h = 430, 200
        cx = (self.screen_width - self.right_panel_width) // 2
        cy = self.screen_height // 2
        x, y = cx - w // 2, cy - h // 2

        bg = pygame.Surface((w, h))
        bg.fill(self.colors['dialog_bg'])
        pygame.draw.rect(bg, self.colors['dialog_border'], bg.get_rect(), 3, border_radius=10)
        self.screen.blit(bg, (x, y))

        prompt = _TUT_TEXTS.get('prompt', {})
        title = self.dialog_title_font.render(
            prompt.get('title', '新手教程'), True, _TUT_TITLE_CLR)
        self.screen.blit(title, title.get_rect(center=(cx, y + 30)))
        pygame.draw.line(self.screen, self.colors['dialog_border'],
                         (x + 20, y + 52), (x + w - 20, y + 52))

        body = prompt.get('body', '')
        lines = body.split('\n')
        ty = y + 78
        for ln in lines:
            surf = self.dialog_font.render(ln, True, _TUT_TEXT_CLR)
            self.screen.blit(surf, surf.get_rect(center=(cx, ty)))
            ty += 24

        # 按钮：开始教程（主色）/ 跳过
        bw, bh = 130, 34
        bx1 = cx - bw - 12
        bx2 = cx + 12
        by = y + h - 52
        rects = []
        for label, action, br, bx in (
                (prompt.get('start_btn', '开始教程'), 'start', _TUT_BTN_MAIN_BG, bx1),
                (prompt.get('skip_btn', '跳过'), 'skip', _TUT_BTN_BG, bx2)):
            r = pygame.Rect(bx, by, bw, bh)
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(self.screen, _TUT_BTN_MAIN_HOVER if hover else br, r, border_radius=6)
            st = self.dialog_font.render(label, True, _TUT_BTN_TXT)
            self.screen.blit(st, st.get_rect(center=r.center))
            rects.append({'rect': r, 'action': action})
        self.tut_prompt_btn_rects = rects

    def _draw_level_select_panel(self):
        """绘制关卡选择列表面板（tut_selecting_levels=True 时）"""
        ls = _TUT_TEXTS.get('level_select', {})
        title_txt = ls.get('title', '选择关卡')
        exit_label = ls.get('exit_btn', '回到练习模式')
        locked_label = ls.get('locked', '待补充')
        mark = ls.get('completed_mark', '✓')

        # 面板布局
        line_h = 22
        pad = 12
        title_h = 28
        gap = 8
        w = 310
        row_h = 34
        n_levels = len(TUTORIAL_LEVELS)
        list_h = n_levels * row_h + (n_levels - 1) * 6
        btn_row_h = 34
        h = title_h + pad + list_h + gap + btn_row_h + pad

        x = self.screen_width - self.right_panel_width - w - 10
        y = self.screen_height - self.status_bar_height - h - 10
        if x < 10:
            x = 10
        if y < 10:
            y = 10

        # 可滚动视区（关卡多时超出封顶高度）
        max_h = 320
        content_top = y + title_h + pad
        orig_list_h = list_h
        list_h = min(list_h, max_h - title_h - pad - gap - btn_row_h - pad)
        h = title_h + pad + list_h + gap + btn_row_h + pad
        content_h = list_h
        max_scroll = max(0, orig_list_h - content_h)
        self.tut_panel_scroll = max(0, min(self.tut_panel_scroll, max_scroll))
        self.tut_panel_rect = pygame.Rect(x, y, w, h)
        self.tut_panel_content_h = content_h
        self.tut_panel_total_h = orig_list_h

        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill(_TUT_PANEL_BG)
        pygame.draw.rect(panel, (120, 122, 140, 255), panel.get_rect(), 2, border_radius=10)
        self.screen.blit(panel, (x, y))

        ts = self.dialog_title_font.render(title_txt, True, _TUT_TITLE_CLR)
        self.screen.blit(ts, ts.get_rect(topleft=(x + pad + 4, y + 6)))

        # 关卡行（裁剪 + 滚动）
        clip_rect = pygame.Rect(x + 4, content_top, w - 14, content_h)
        self.screen.set_clip(clip_rect)
        row_rects = []
        mouse_pos = pygame.mouse.get_pos()
        rowh_used = row_h + 6
        ry = content_top - self.tut_panel_scroll
        for lv in TUTORIAL_LEVELS:
            if ry > content_top + content_h + 10 or ry + row_h < content_top - 10:
                ry += rowh_used
                continue
            pending = lv.get('pending')
            completed = self._tut_is_completed(lv['id'])
            r = pygame.Rect(x + pad, ry, w - pad * 2, row_h)
            if not pending:
                hover = r.collidepoint(mouse_pos)
                bg = _TUT_BTN_MAIN_BG if hover else _TUT_BTN_BG
                pygame.draw.rect(self.screen, bg, r, border_radius=6)
                row_rects.append({'rect': r, 'action': 'load', 'level': lv['id']})
                label = f"{mark} " + lv['title'] if completed else lv['title']
                txt_clr = _TUT_BTN_TXT
            else:
                bg = _TUT_LOCKED_BG
                pygame.draw.rect(self.screen, bg, r, border_radius=6)
                label = lv['title'] + f"（{locked_label}）"
                txt_clr = _TUT_LOCKED_TXT
            st = self.dialog_font.render(label, True, txt_clr)
            self.screen.blit(st, st.get_rect(midleft=(r.left + 10, r.centery)))
            ry += rowh_used
        self.screen.set_clip(None)
        self.tut_level_btn_rects = row_rects

        # 滚动条
        sb_w = 8
        if max_scroll > 0:
            sb_x = x + w - pad - 8
            sb_rect = pygame.Rect(sb_x, content_top, sb_w, content_h)
            pygame.draw.rect(self.screen, (60, 60, 60), sb_rect, border_radius=3)
            knob_h = max(20, int(content_h * content_h / max(1, orig_list_h)))
            knob_y = content_top + int((content_h - knob_h) * self.tut_panel_scroll / max_scroll)
            knob_rect = pygame.Rect(sb_x, knob_y, sb_w, knob_h)
            pygame.draw.rect(self.screen, _TUT_BTN_BG, knob_rect, border_radius=3)
            self.tut_panel_scrollbar_rect = sb_rect
            self.tut_panel_scrollbar_knob_rect = knob_rect
        else:
            self.tut_panel_scrollbar_rect = None
            self.tut_panel_scrollbar_knob_rect = None

        # 底部：回到练习模式
        by = y + h - btn_row_h - pad + 2
        total_w = w - pad * 2
        bw = total_w
        r = pygame.Rect(x + pad, by, bw, btn_row_h - 4)
        hover = r.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, _TUT_BTN_MAIN_HOVER if hover else _TUT_BTN_BG, r, border_radius=6)
        st = self.dialog_font.render(exit_label, True, _TUT_BTN_TXT)
        self.screen.blit(st, st.get_rect(center=r.center))
        row_rects.append({'rect': r, 'action': 'exit'})
        self.tut_level_btn_rects = row_rects

    def draw_tutorial_panel(self):
        """教学引导面板（右下角浮动，最顶层绘制）"""
        # 解法播放结束后自动还原动画速度
        self._tut_tick_restore_anim_speed()

        if not getattr(self, 'tutorial_active', False):
            return

        # 关卡选择列表模式
        if getattr(self, 'tut_selecting_levels', False):
            self._draw_level_select_panel()
            return

        level = TUTORIAL_LEVELS_BY_ID.get(self.tut_level, {})
        step_text = self._tut_current_step_text()

        # 按钮集合（随步骤变化）
        if self.tut_step == 7:
            buttons = [('选择关卡', 'level_select', _TUT_BTN_BG),
                       ('回到练习模式', 'exit', _TUT_BTN_MAIN_BG)]
        elif self.tut_level == 1 and self.tut_step == 6:
            buttons = [('重置本关', 'reset', _TUT_BTN_BG),
                       ('查看解法', 'solution', _TUT_BTN_BG),
                       ('跳过教程', 'skip', _TUT_BTN_BG)]
        elif self.tut_level in (2, 3, 4):
            buttons = [('查看解法', 'solution', _TUT_BTN_BG),
                       ('重置本关', 'reset', _TUT_BTN_BG),
                       ('选择关卡', 'level_select', _TUT_BTN_BG),
                       ('跳过教程', 'skip', _TUT_BTN_BG)]
        else:
            buttons = [('查看解法', 'solution', _TUT_BTN_BG),
                       ('跳过教程', 'skip', _TUT_BTN_BG)]

        # ---- 布局：正文自动换行（复用 _wrap_text）→ 总高度 → 面板高度（封顶）----
        line_h = 22
        btn_row_h = 34
        pad = 12
        title_h = 28
        gap = 10
        w = 310
        max_h = 300
        sb_w = 8                                     # 滚动条宽度
        text_left = pad + 4
        text_max_width = w - pad - 4 - (sb_w + 6)   # 右侧预留滚动条

        wrapped = self._tut_wrap_step_text(step_text, self.dialog_font, text_max_width)
        total_h = len(wrapped) * line_h
        wanted_h = title_h + pad + total_h + gap + btn_row_h + pad
        h = min(wanted_h, max_h)

        x = self.screen_width - self.right_panel_width - w - 10
        y = self.screen_height - self.status_bar_height - h - 10
        if x < 10:
            x = 10
        if y < 10:
            y = 10

        # 正文可视区（标题与按钮行之间）：记录供事件/滚轮/滚动条使用
        content_top = y + title_h + pad
        content_h = h - title_h - pad - gap - btn_row_h - pad
        max_scroll = max(0, total_h - content_h)
        self.tut_panel_scroll = max(0, min(self.tut_panel_scroll, max_scroll))
        self.tut_panel_rect = pygame.Rect(x, y, w, h)
        self.tut_panel_content_h = content_h
        self.tut_panel_total_h = total_h

        # 半透明面板
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill(_TUT_PANEL_BG)
        pygame.draw.rect(panel, (120, 122, 140, 255), panel.get_rect(), 2, border_radius=10)
        self.screen.blit(panel, (x, y))

        # 标题
        title_txt = f"教程·{level.get('title', '')}"
        ts = self.dialog_title_font.render(title_txt, True, _TUT_TITLE_CLR)
        self.screen.blit(ts, ts.get_rect(topleft=(x + pad + 4, y + 6)))

        # 步骤正文（set_clip 裁剪 + 滚动偏移绘制，模式同 draw_help_dialog）
        clip_rect = pygame.Rect(x + 4, content_top, w - 14, content_h)
        self.screen.set_clip(clip_rect)
        ty = content_top - self.tut_panel_scroll
        for ln in wrapped:
            if ln:
                if ty + line_h > content_top - 10 and ty < content_top + content_h + 10:
                    surf = self.dialog_font.render(ln, True, _TUT_TEXT_CLR)
                    self.screen.blit(surf, (x + text_left, ty))
            ty += line_h
        self.screen.set_clip(None)

        # 滚动条（内容超出可视区时显示；模式同 draw_help_dialog）
        if max_scroll > 0:
            sb_x = x + w - pad - 8
            sb_rect = pygame.Rect(sb_x, content_top, sb_w, content_h)
            pygame.draw.rect(self.screen, (60, 60, 60), sb_rect, border_radius=3)
            knob_h = max(20, int(content_h * content_h / max(1, total_h)))
            knob_y = content_top + int((content_h - knob_h) * self.tut_panel_scroll / max_scroll)
            knob_clr = _TUT_BTN_HOVER if self.tut_panel_scrollbar_dragging else _TUT_BTN_BG
            knob_rect = pygame.Rect(sb_x, knob_y, sb_w, knob_h)
            pygame.draw.rect(self.screen, knob_clr, knob_rect, border_radius=3)
            self.tut_panel_scrollbar_rect = sb_rect
            self.tut_panel_scrollbar_knob_rect = knob_rect
        else:
            self.tut_panel_scrollbar_rect = None
            self.tut_panel_scrollbar_knob_rect = None

        # 按钮行
        by = y + h - btn_row_h - pad + 2
        total_w = w - pad * 2
        bgaps = 8
        n = len(buttons)
        bw = (total_w - bgaps * (n - 1)) // n
        rects = []
        bx = x + pad
        mouse_pos = pygame.mouse.get_pos()
        for label, action, base_clr in buttons:
            r = pygame.Rect(bx, by, bw, btn_row_h - 4)
            hover = r.collidepoint(mouse_pos)
            clr = _TUT_BTN_MAIN_HOVER if action == 'to_solve' and hover else (
                _TUT_BTN_HOVER if hover else base_clr)
            pygame.draw.rect(self.screen, clr, r, border_radius=6)
            st = self.dialog_font.render(label, True, _TUT_BTN_TXT)
            self.screen.blit(st, st.get_rect(center=r.center))
            rects.append({'rect': r, 'action': action})
            bx += bw + bgaps
        self.tut_btn_rects = rects
