# -*- coding: utf-8 -*-
"""
滑块游戏图形界面主类

精简后保留核心属性初始化 + run() 主循环，
其余功能通过 Mixin 继承：
- RendererMixin: 渲染
- DialogMixin: 对话框
- AnimationMixin: 动画
- FileOpsMixin: 文件操作
- EventsMixin: 事件处理
"""

import pygame
import sys
import os
import json
import time
import traceback
import queue
from datetime import datetime
from game import SliderMatrix, Block
from history import GameHistory
from records import Records, format_time
from gui.renderer import RendererMixin
from gui.dialogs import DialogsMixin
from gui.animation import AnimationMixin
from gui.file_ops import FileOpsMixin
from gui.events import EventsMixin
from gui.virtual_keyboard import VirtualKeyboardMixin
from gui.metrics_panel import MetricsPanelMixin
from gui.records_panel import RecordsPanelMixin
from gui.annotation import AnnotationMixin


def _gui_log_error(msg: str):
    """写入错误日志"""
    try:
        base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base, 'error_log.txt')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f'[{timestamp}] {msg}\n')
    except Exception:
        import tempfile
        try:
            log_path = os.path.join(tempfile.gettempdir(), 'gatenneaslider_error_log.txt')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f'[{timestamp}] {msg}\n')
        except Exception:
            pass


def _gui_safe_font(name, size, bold=False):
    """安全加载字体：优先直接加载字体文件（绕过 pygame SysFont 注册表扫描的 bug）"""
    #20260727发现因字体加载失败导致程序崩溃的bug，现已修复
    # 已知的 Windows 中文字体文件路径映射
    _font_files = {
        'SimHei': 'C:/Windows/Fonts/simhei.ttf',
        'Microsoft YaHei': 'C:/Windows/Fonts/msyh.ttc',
        'SimSun': 'C:/Windows/Fonts/simsun.ttc',
    }
    # 优先尝试直接加载字体文件（不扫描注册表）
    filepath = _font_files.get(name)
    if filepath and os.path.exists(filepath):
        try:
            return pygame.font.Font(filepath, size)
        except Exception:
            pass
    # 其次尝试 SysFont（可能触发 pygame 注册表扫描 bug）
    try:
        return pygame.font.SysFont(name, size, bold=bold)
    except Exception:
        _gui_log_error(f'字体加载失败: {name} {size}, 回退到默认字体')
        return pygame.font.Font(None, size)


def _gui_get_resource_path(relative_path):
    """获取资源文件路径（兼容 PyInstaller 打包和开发模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


class SliderGUI(RendererMixin, DialogsMixin, AnimationMixin, FileOpsMixin, EventsMixin, VirtualKeyboardMixin, MetricsPanelMixin, RecordsPanelMixin, AnnotationMixin):
    """
    滑块游戏图形界面类
    """

    def __init__(self, m: int = 6, n: int = 6, step: int = 1, cmd_queue: queue.Queue = None):
        """
        初始化游戏界面

        参数：
            m: 初始滑块行数，默认为6
            n: 初始滑块列数，默认为6
            step: 移动步数（等级），默认为1
            cmd_queue: 命令队列（用于接收终端指令），默认为None
        """
        _gui_log_error(f'GUI初始化开始: m={m}, n={n}, step={step}')
        try:
            pygame.init()
        except Exception:
            _gui_log_error(f'pygame.init() 失败: {traceback.format_exc()}')
            raise

        # 界面尺寸配置
        self.base_cell_size = 60
        self.cell_size = self.base_cell_size
        self.padding = 10
        self.gap_width = 4
        self.min_width = 1000
        self.min_height = 618

        # 菜单栏和状态栏高度
        self.menu_bar_height = 32
        self.status_bar_height = 28

        # 右侧面板宽度（速度滑条 + 5 个快捷开关）
        self.right_panel_width = 132

        # 窗口尺寸
        self.screen_width = self.min_width
        self.screen_height = self.min_height

        # 从 config.json 恢复上次窗口大小/位置（必须在 set_mode 之前生效）
        try:
            _cfg_base = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
                         else os.path.dirname(os.path.abspath(__file__)))
            _cfg_path = os.path.join(_cfg_base, 'config', 'config.json')
            if os.path.exists(_cfg_path):
                with open(_cfg_path, 'r', encoding='utf-8') as f:
                    _cfg = json.load(f)
                _ws = _cfg.get('window_size')
                if isinstance(_ws, list) and len(_ws) == 2:
                    self.screen_width = max(self.min_width, int(_ws[0]))
                    self.screen_height = max(self.min_height, int(_ws[1]))
                _wp = _cfg.get('window_pos')
                if isinstance(_wp, list) and len(_wp) == 2:
                    os.environ['SDL_VIDEO_WINDOW_POS'] = f'{int(_wp[0])},{int(_wp[1])}'
        except Exception:
            pass

        # 创建可调整大小的窗口
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height),
            pygame.RESIZABLE
        )
        pygame.display.set_caption("貓九的滑块游戏")

        # 设置窗口图标
        try:
            icon_path = _gui_get_resource_path('picture/cover.png')
            icon_surface = pygame.image.load(icon_path)
            pygame.display.set_icon(icon_surface)
        except Exception:
            pass  # 图标加载失败不影响运行

        # 颜色配置
        self.colors = {
            'background': (30, 30, 30),
            'block': (60, 150, 200),
            'block_selected': (0, 200, 100),
            'text': (255, 255, 255),
            'border': (100, 100, 100),
            'gap': (80, 80, 80),
            'line': (255, 0, 0),
            'grid': (40, 40, 40),
            'menu_bg': (50, 50, 50),
            'menu_hover': (70, 70, 70),
            'menu_text': (220, 220, 220),
            'menu_selected': (80, 130, 180),
            'status_bg': (40, 40, 40),
            'status_text': (200, 200, 200),
            'dialog_bg': (45, 45, 48),
            'dialog_border': (100, 100, 100),
            'dialog_text': (230, 230, 230),
            'dialog_title': (255, 255, 255),
            'solved': (0, 200, 80),
            'unsolved': (200, 160, 0),
            'input_bg': (60, 60, 65),
            'input_active': (80, 80, 120),
            'input_text': (255, 255, 255),
            'selection_bg': (50, 80, 160),
            'button_bg': (70, 130, 180),
            'button_hover': (90, 150, 200),
            'separator': (80, 80, 80),
        }

        # 当前谜题参数
        self.current_m = m
        self.current_n = n
        self.current_step = step

        # 游戏逻辑对象
        self.game = SliderMatrix(m, n)

        # 步数计数
        self.step_count = 0

        # 选中状态
        self.selected_gap = None
        self.selected_block = None

        # 字体设置
        self.font = _gui_safe_font('SimHei', 24)
        self.menu_font = _gui_safe_font('SimHei', 16)
        self.status_font = _gui_safe_font('SimHei', 14)
        self.dialog_font = _gui_safe_font('SimHei', 18)
        self.dialog_title_font = _gui_safe_font('SimHei', 22, bold=True)
        self.input_font = _gui_safe_font('SimHei', 20)

        # 相机位置
        self.camera_x = 0
        self.camera_y = 0

        # 拖拽状态
        self.is_dragging = False
        self.drag_start = (0, 0)
        self.drag_offset = (0, 0)

        # 缩放设置
        self.zoom = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 4.0

        # 命令队列
        self.cmd_queue = cmd_queue

        # 游戏运行状态
        self.running = True

        # 菜单栏配置
        self.menu_items = ['文件', '编辑', '谜题', '宏定义', '设置', '帮助']
        self.menu_hovered = -1
        self.menu_item_rects = []

        # 帮助对话框状态
        self.show_help = False
        self.help_scroll_offset = 0

        # 宏定义菜单状态
        self.show_macro_menu = False
        self.macro_menu_rects = []
        self.macro_menu_hovered = -1

        # 确定程序根目录（支持 PyInstaller onefile 模式）
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        # 宏管理器
        from macro.macro import MacroManager
        self.macro_manager = MacroManager(os.path.join(self.base_dir, 'macro'))

        # 宏录制状态
        self.macro_recording = False        # 是否正在录制宏
        self.macro_recording_steps = []     # 录制中的步骤列表
        self.macro_record_base_point = None # 录制时的基准坐标 [row, col]

        # 宏执行状态
        self.macro_executing = False        # 是否正在执行宏
        self.macro_selecting_base = False   # 是否正在选择执行基准
        self.macro_exec_ops = []            # 待执行的绝对操作队列
        self.macro_exec_index = 0           # 当前执行到第几个操作
        self.macro_exec_factor = 1          # 拆分因子
        self.macro_exec_name = ''           # 正在执行的宏名称
        self.macro_exec_reverse = False     # 是否逆序播放（方向取反 + 顺序逆序）
        self.macro_reverse_mode = False     # 逆序播放模式开关（宏菜单切换，点击宏名时生效）
        self.macro_error_msg = ''           # 宏错误提示信息
        self.macro_error_timer = 0          # 错误提示显示计时器

        # 宏执行结果通知（右下角提示）
        self.macro_notify_msg = ''          # 通知文本
        self.macro_notify_timer = 0         # 通知显示计时器（帧数，60fps）
        self.macro_notify_persistent = False  # 是否持久显示（不走淡出）
        self._gather_info = None            # 聚拢求解结果（用于播放时实时刷新）

        # 宏管理对话框状态
        self.show_macro_manager_dialog = False
        self._macro_mgr_scroll = 0
        self._macro_mgr_visible_count = 5
        self._macro_mgr_scroll_up_rect = None
        self._macro_mgr_scroll_down_rect = None
        self._macro_mgr_item_rects = []
        self.macro_manager_dialog_rect = None

        # 宏命名/重命名对话框
        self.show_macro_name_dialog = False
        self.macro_name_input = ''
        self.macro_name_active = False
        self.macro_renaming_index = -1

        # 配置文件路径（config 放在 exe 同目录，方便用户修改）
        self.config_dir = os.path.join(self.base_dir, 'config')
        self.config_path = os.path.join(self.config_dir, 'config.json')
        self.temp_history_path = os.path.join(self.config_dir, 'temp_history.json')

        # 保存目录（用于文件对话框初始目录）
        self.save_dir = os.path.join(self.base_dir, 'save')

        # 当前打开的文件路径（None 表示未保存过）
        self.current_file_path = None
        # 棋盘修改版号：任何改变滑块组状态的操作 +1；保存/载入时记录基准
        self._board_version = 0
        self._saved_board_version = 0
        self._window_title = ''

        # 文件菜单状态
        self.show_file_menu = False
        self.file_menu_items = ['打开 Ctrl+O', '保存 Ctrl+S', '另存为...']
        self.file_menu_rects = []
        self.file_menu_hovered = -1

        # 编辑菜单状态
        self.show_edit_menu = False
        self.edit_menu_items = ['撤销 Ctrl+Z', '重做 Ctrl+X', '打乱 Alt+S', '重置 Ctrl+R', '---', '自动求解 Ctrl+Alt+S']
        self.edit_menu_rects = []
        self.edit_menu_hovered = -1

        # 谜题菜单状态
        self.show_puzzle_menu = False
        self.puzzle_menu_rects = []
        self.puzzle_menu_hovered = -1
        # 预设选项: (显示名, m, n, step) 或 ('---',) 分隔线 或 ('自定义...',) 自定义
        self.puzzle_presets = [
            ('2~4*4', 4, 4, 2),
            ('2~5*5', 5, 5, 2),
            ('2~6*6', 6, 6, 2),
            ('2~7*7', 7, 7, 2),
            ('2~8*8', 8, 8, 2),
            ('2~9*9', 9, 9, 2),
            ('2~10*10', 10, 10, 2),
            ('---',),
            ('3~6*6', 6, 6, 3),
            ('3~7*7', 7, 7, 3),
            ('3~8*8', 8, 8, 3),
            ('3~9*9', 9, 9, 3),
            ('3~10*10', 10, 10, 3),
            ('---',),
            ('自定义...',),
            ('__mode__',),   # 计时/练习模式切换（特殊项，见 renderer/events 处理）
        ]

        # 自动求解状态
        self._auto_solve_result = None     # None=空闲, list=解法, False=无解
        self._auto_solve_done = False     # 求解线程是否已完成
        self._auto_solve_running = False   # 是否正在后台求解
        self._auto_solve_start_time = 0    # 求解开始时间戳
        self._auto_solve_cancel = False    # 是否请求取消
        self._auto_solve_progress = None   # 求解进度信息 dict
        self.solver_algorithm = 'ida_star' # 求解算法选择: 'ida_star', 'fast', 'greedy'

        # 聚拢求解器参数（GUI 设置对话框可调，保存到 config.json）
        self.gather_params = {
            'max_steps': 500,            # 最大步数上限
            'patience': 150,             # 连续无改进停机步数
            'max_wait_time': 20,         # 求解时间上限（秒），0=不限时
            'target_gather_score': 1.0,  # 目标聚拢度，达到即停（1.0=完全还原）
            'aggressiveness': 0.2,       # 激进程度：允许聚拢度临时下降的幅度
        }
        # 各参数启用标志：False = 该参数不设限（传 None 给求解器）
        self.gather_enabled = {k: True for k in self.gather_params}
        # 聚拢参数输入框手动编辑状态
        self.settings_editing_value = None   # 正在编辑的参数 key
        self.settings_edit_buffer = ''       # 输入缓冲区
        # 梯度聚拢（梯度）逐阶段状态：None = 非梯度模式
        self._gradient_state = None
        # 梯度流水线（阶段计算与动画并行）：
        self._gradient_queue = queue.Queue()  # (gen, result|None) 项；result=None=管线结束哨兵
        self._gradient_gen = 0                # 管线代数：取消/重开时自增，用于丢弃过期结果
        self._gradient_busy = False           # 后台流水线线程是否存活
        # 分组着色器：按 (位置 mod step) 给滑块分组涂色，帮助人工还原
        self.coloring_enabled = False
        # 悬停连锁提示：悬停某格时，边界盒内同组位置发光（独立开关）
        self.chain_hint_enabled = False
        self.hover_cell = None
        # 存档只读：
        #  _readonly=True 时禁用改变滑块组状态的功能（滑动/求解/打乱/宏等），仅允许撤销重做
        # save_readonly_flag 是设置开关：打开后所有保存的存档都带 readonly 标记
        self._readonly = False
        self.save_readonly_flag = False
        # 复原成功悬浮窗：
        #  _solved_popup_active：当前是否显示；_solved_popup_t：弹入动画计时
        #  _prev_solved：上一次状态提交后的复原状况（用于判定“刚达成复原”，避免重复弹窗）
        self._solved_popup_active = False
        self._solved_popup_t = 0
        self._prev_solved = False
        # 参数规格（GUI 步进器用）：key -> (显示名, 默认值, 最小值, 最大值, 步长, 说明)
        self._gather_param_specs = [
            ('max_steps',           ('最大步数',     500,  100,   5000, 100,  '聚拢求解的步数上限，越大越可能深入但越慢')),
            ('patience',            ('停滞容忍步数', 150,  10,    1000, 10,   '连续多少步聚拢度无改进就停止，越大越能跳出短暂卡顿')),
            ('max_wait_time',       ('最大等待秒数', 20,   0,     120,  5,    '求解时间上限（秒），0 表示不限时')),
            ('target_gather_score', ('目标聚拢度',   1.0,  0.5,   1.0,  0.05, '聚拢度达到该值即停止，1.0 表示完全还原')),
            ('aggressiveness',      ('激进程度',     0.2,  0.0,   0.5,  0.05, '允许选择比最佳候选低多少的聚拢度，越大越敢于探索、越可能偏离')),
        ]

        # 自定义谜题对话框状态
        self.show_custom_dialog = False
        self.custom_fields = {'m': '6', 'n': '6', 'step': '1'}
        self.custom_active_field = None  # 'm', 'n', 'step'
        self.custom_error = ''

        # 历史记录
        self.game_history = GameHistory()

        # 计时器与成绩记录
        self.records = Records(os.path.join(self.config_dir, 'records.dat'))
        self.timer_state = 'idle'   # idle/ready/running/dnf/stopped
        self.timer_start = 0.0      # perf_counter 计时起点
        self.timer_elapsed = 0.0    # 已用秒数（浮点）
        self.timer_m = 0
        self.timer_n = 0
        self.timer_step = 0
        self.timer_initial_matrix = ''
        self.timer_puzzle_key = ''
        self.game_mode = 'practice'  # 'timed' 计时模式 / 'practice' 练习模式（默认练习）

        # 动画状态
        self.animating = False
        self.anim_blocks = []
        self.anim_start_pos = []
        self.anim_end_pos = []
        self.anim_progress = 0.0
        self.anim_start_time = 0
        # 动画速度范围（毫秒/步）：越小越快
        self.SPEED_MIN_MS = 50
        self.SPEED_MAX_MS = 1000
        self.animation_duration = 300  # 毫秒
        self.animation_enabled = True          # 滑动动画（滑块移动/撤销重做滑动）
        self.selection_animation_enabled = True  # 选中动画（撤销/重做时高亮该步缝隙与滑块组）

        # 移动元数据（从 move_selected_blocks 传递到 commit_animation）
        self._pending_move_info = None

        # 撤销/重做动画状态
        self._undo_redo_type = None  # 当前动画类型：'undo'/'redo'/None
        self._animation_queue = []   # 待执行的撤销/重做队列，存储 'undo'/'redo'

        # 动画统一偏移量（方案四：所有Block使用同一偏移量）
        self._anim_dr = 0.0
        self._anim_dc = 0.0

        # 右侧面板控件
        self.slider_dragging = False
        self.slider_rect = None
        self.slider_knob_rect = None
        self.zoom_slider_dragging = False
        self.zoom_slider_rect = None
        self.zoom_knob_rect = None

        # 长按重复状态
        self.undo_held = False
        self.redo_held = False
        self.undo_first = False
        self.redo_first = False
        self.key_repeat_delay = 400   # 首次重复延迟(毫秒)
        self.key_repeat_interval = 80  # 后续重复间隔(毫秒)
        self.undo_timer = 0
        self.redo_timer = 0

        # 文件对话框（pygame 自绘）
        from gui.dialogs import PygameFileDialog
        self.file_dialog = PygameFileDialog(self.screen, self.dialog_font, self.dialog_title_font, self.status_font, self.colors)
        self._pending_save_as = False
        self._pending_load = False

        # 设置菜单状态
        self.show_settings_menu = False
        self.settings_menu_items = ['快捷键设置', '动画速度']
        self.settings_menu_rects = []
        self.settings_menu_hovered = -1

        # 设置对话框状态
        self.show_settings_dialog = False
        self.settings_active_tab = 'keybindings'  # 'keybindings' or 'animation'
        self.settings_editing_action = None  # 当前正在编辑快捷键的动作名
        self.settings_editing_key = None  # 临时存储正在录制的按键
        self._settings_slider_dragging = False
        self._settings_backup_keybindings = {}
        self._settings_ok_btn = None
        self._settings_cancel_btn = None
        self._settings_reset_btn = None
        self._settings_key_rects = {}
        self._settings_tab_kb_rect = None
        self._settings_tab_anim_rect = None
        self._settings_anim_toggle_rect = None
        self._settings_slider_track_rect = None

        # 快捷键配置（默认值）
        self.keybindings = {
            'undo': {'key': 'z', 'modifiers': ['ctrl']},
            'redo': {'key': 'x', 'modifiers': ['ctrl']},
            'shuffle': {'key': 's', 'modifiers': ['alt']},
            'reset': {'key': 'r', 'modifiers': ['ctrl']},
            'save': {'key': 's', 'modifiers': ['ctrl']},
            'load': {'key': 'o', 'modifiers': ['ctrl']},
            'move_up': {'key': 'w', 'modifiers': []},
            'move_down': {'key': 's', 'modifiers': []},
            'move_left': {'key': 'a', 'modifiers': []},
            'move_right': {'key': 'd', 'modifiers': []},
            'auto_solve': {'key': 's', 'modifiers': ['ctrl', 'alt']},
            'macro_record': {'key': 'm', 'modifiers': ['ctrl']},
            'virtual_keyboard': {'key': 'f1', 'modifiers': []},
            'metrics_panel': {'key': 'f2', 'modifiers': []},
            'records_panel': {'key': 'f3', 'modifiers': []},
        }

        # 快捷键动作显示名
        self.keybinding_labels = {
            'undo': '撤销',
            'redo': '重做',
            'shuffle': '打乱',
            'reset': '重置',
            'save': '保存',
            'load': '打开',
            'move_up': '上移',
            'move_down': '下移',
            'move_left': '左移',
            'move_right': '右移',
            'auto_solve': '自动求解',
            'macro_record': '录制宏',
            'virtual_keyboard': '虚拟键盘',
            'metrics_panel': '调试面板',
            'records_panel': '成绩面板',
        }

        # 快捷键动作分组（用于设置对话框显示）
        self.keybinding_groups = [
            ('文件操作', ['save', 'load']),
            ('编辑操作', ['undo', 'redo', 'shuffle', 'reset']),
            ('求解器', ['auto_solve']),
            ('宏操作', ['macro_record']),
            ('游戏操作', ['move_up', 'move_down', 'move_left', 'move_right', 'virtual_keyboard', 'metrics_panel', 'records_panel']),
        ]

        # 虚拟键盘状态
        self._vk_init_state()

        # 聚拢度指标面板状态
        self._mp_init_state()

        # 成绩记录面板状态
        self._rp_init_state()

        # 标注模式状态
        self._ann_init_state()

        # 加载上次状态
        self.load_last_state()

    def new_puzzle(self, m: int, n: int, step: int = 1):
        """
        创建新谜题

        参数：
            m: 行数
            n: 列数
            step: 移动步数（等级）
        """
        # 切换谜题会重置棋盘 → 终止梯度流水线
        self._stop_gradient_pipeline()
        # 标注会话随棋盘重置而结束
        self._ann_cancel_session('切换谜题')
        # 验证等级约束：step < max(m, n)
        if step >= max(m, n):
            return False

        # 只读存档：禁止新建谜题
        if self._readonly_blocked():
            return False

        # 计时进行中禁止切换谜题
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换谜题"
            self.macro_notify_timer = 90
            return False
        self._timer_cancel()

        self.current_m = m
        self.current_n = n
        self.current_step = step

        # 创建新的游戏对象
        self.game = SliderMatrix(m, n)

        # 重置状态
        self.zoom = 1.0
        self.selected_gap = None
        self.selected_block = None
        self.step_count = 0

        # 取消动画
        self.animating = False
        self.anim_blocks = []

        # 重置历史记录
        self.game_history.reset()
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()

        self.macro_notify_msg = f"切换谜题：{m}×{n} 等级{step}"
        self.macro_notify_timer = 120
        return True

    def is_solved(self) -> bool:
        """判断当前是否为复原状态（比较0-1矩阵形状）"""
        return self.game.is_solved()

    def ensure_blocks_visible(self):
        """确保所有滑块都在可视区域内，超出时自动调整相机"""
        if not self.game.blocks:
            return

        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom

        # 可视区域（排除菜单栏、状态栏和右侧面板）
        view_left = 0
        view_right = self.screen_width - self.right_panel_width
        view_top = self.menu_bar_height
        view_bottom = self.screen_height - self.status_bar_height

        # 留一些边距
        margin = scaled_cell * 0.5

        # 计算所有滑块的屏幕坐标范围
        min_screen_x = float('inf')
        max_screen_x = float('-inf')
        min_screen_y = float('inf')
        max_screen_y = float('-inf')

        for block in self.game.blocks:
            screen_x = block.location[1] * (scaled_cell + scaled_gap) + self.camera_x
            screen_y = block.location[0] * (scaled_cell + scaled_gap) + self.camera_y

            min_screen_x = min(min_screen_x, screen_x)
            max_screen_x = max(max_screen_x, screen_x + scaled_cell)
            min_screen_y = min(min_screen_y, screen_y)
            max_screen_y = max(max_screen_y, screen_y + scaled_cell)

        # 检查是否超出可视区域
        need_adjust = False
        dx, dy = 0, 0

        if min_screen_x < view_left + margin:
            dx = (view_left + margin) - min_screen_x
            need_adjust = True
        elif max_screen_x > view_right - margin:
            dx = (view_right - margin) - max_screen_x
            need_adjust = True

        if min_screen_y < view_top + margin:
            dy = (view_top + margin) - min_screen_y
            need_adjust = True
        elif max_screen_y > view_bottom - margin:
            dy = (view_bottom - margin) - max_screen_y
            need_adjust = True

        if need_adjust:
            self.camera_x += dx
            self.camera_y += dy

    def center_map(self):
        """将地图居中显示在游戏区域中"""
        bounds = self.game.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']

        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom

        map_width = (max_col - min_col + 1) * scaled_cell + (max_col - min_col) * scaled_gap
        map_height = (max_row - min_row + 1) * scaled_cell + (max_row - min_row) * scaled_gap

        map_center_x = min_col * (scaled_cell + scaled_gap) + map_width / 2
        map_center_y = min_row * (scaled_cell + scaled_gap) + map_height / 2

        game_center_y = self.menu_bar_height + (self.screen_height - self.menu_bar_height - self.status_bar_height) / 2

        self.camera_x = (self.screen_width - self.right_panel_width) / 2 - map_center_x
        self.camera_y = game_center_y - map_center_y

    def _is_camera_valid(self) -> bool:
        """检查当前 camera 位置是否能让滑塊在视口内可见"""
        if not self.game.blocks:
            return True
        bounds = self.game.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']
        scaled_cell = self.cell_size * self.zoom
        scaled_gap = self.gap_width * self.zoom

        # 滑塊区域在屏幕上的范围
        left   = min_col * (scaled_cell + scaled_gap) + self.camera_x
        right  = max_col * (scaled_cell + scaled_gap) + scaled_cell + self.camera_x
        top    = min_row * (scaled_cell + scaled_gap) + self.camera_y
        bottom = max_row * (scaled_cell + scaled_gap) + scaled_cell + self.camera_y

        # 视口范围
        view_left   = 0
        view_right  = self.screen_width - self.right_panel_width
        view_top    = self.menu_bar_height
        view_bottom = self.screen_height - self.status_bar_height

        # 滑塊区域是否与视口有交集
        return not (right < view_left or left > view_right or
                    bottom < view_top or top > view_bottom)

    def world_to_screen(self, world_x: float, world_y: float) -> tuple:
        """世界坐标转换为屏幕坐标"""
        return world_x * self.zoom + self.camera_x, world_y * self.zoom + self.camera_y

    def screen_to_world(self, screen_x: float, screen_y: float) -> tuple:
        """屏幕坐标转换为世界坐标"""
        return (screen_x - self.camera_x) / self.zoom, (screen_y - self.camera_y) / self.zoom

    def get_block_at_pos(self, screen_x: int, screen_y: int) -> Block:
        """根据屏幕坐标获取滑块对象"""
        try:
            world_x, world_y = self.screen_to_world(screen_x, screen_y)

            for block in self.game.blocks:
                bx = block.location[1] * (self.cell_size + self.gap_width)
                by = block.location[0] * (self.cell_size + self.gap_width)

                rect = pygame.Rect(bx, by, self.cell_size, self.cell_size)
                if rect.collidepoint(world_x, world_y):
                    return block
        except Exception as e:
            print(f"get_block_at_pos error: {e}")

        return None

    def get_cell_at_pos(self, screen_x: int, screen_y: int):
        """根据屏幕坐标获取对应的格子坐标 (row, col)，无论该格是否有滑块。

        用于宏基准选择等场景，允许把「空位」也作为基准坐标。
        点击落在格子之间的缝隙上时返回 None。
        """
        try:
            world_x, world_y = self.screen_to_world(screen_x, screen_y)
            cell = self.cell_size + self.gap_width
            c = int(world_x // cell)
            r = int(world_y // cell)
            # 检查是否落在格子的 cell 部分（而非 gap）
            if (world_x - c * cell) >= self.cell_size or (world_y - r * cell) >= self.cell_size:
                return None
            return r, c
        except Exception as e:
            print(f"get_cell_at_pos error: {e}")
        return None

    def get_gap_at_pos(self, screen_x: int, screen_y: int) -> tuple:
        """根据屏幕坐标获取缝隙位置"""
        try:
            world_x, world_y = self.screen_to_world(screen_x, screen_y)

            bounds = self.game.get_boundaries()
            min_row, max_row = bounds['min_row'], bounds['max_row']
            min_col, max_col = bounds['min_col'], bounds['max_col']

            cell = self.cell_size
            gap = self.gap_width

            for i in range(min_row, max_row + 2):
                gap_y = i * (cell + gap) - gap // 2
                if abs(world_y - gap_y) < gap + 10:
                    board_left = min_col * (cell + gap)
                    board_right = (max_col + 1) * (cell + gap)
                    if board_left - 50 < world_x < board_right + 50:
                        line_index = i - 1
                        if self.game.is_valid_h_line(line_index):
                            return ('h', line_index)

            for j in range(min_col, max_col + 2):
                gap_x = j * (cell + gap) - gap // 2
                if abs(world_x - gap_x) < gap + 10:
                    board_top = min_row * (cell + gap)
                    board_bottom = (max_row + 1) * (cell + gap)
                    if board_top - 50 < world_y < board_bottom + 50:
                        line_index = j - 1
                        if self.game.is_valid_v_line(line_index):
                            return ('v', line_index)
        except Exception as e:
            print(f"get_gap_at_pos error: {e}")

        return None

    def _readonly_blocked(self) -> bool:
        """只读存档检查：返回 True 表示当前存档只读，禁止改变滑块组状态。

        只读时仅允许撤销/重做（其入口不调用本检查）。被拦时右下角提示。
        """
        if not getattr(self, '_readonly', False):
            return False
        self.macro_notify_msg = "当前存档为只读"
        self.macro_notify_timer = 90
        return True

    def _update_window_title(self):
        """按存档路径/已修改/未存档 刷新窗口标题（只有标题变化时才调用 set_caption）"""
        if self.current_file_path:
            dirty = self._board_version != self._saved_board_version
            marker = ' *' if dirty else ''
            new_title = f'貓九的滑块游戏 — {self.current_file_path}{marker}'
        else:
            new_title = '貓九的滑块游戏 — 未存檔'
        if new_title != self._window_title:
            self._window_title = new_title
            pygame.display.set_caption(new_title)

    def _mark_file_dirty(self):
        """棋盘状态变更：提升修改版号并刷新窗口标题（星号）"""
        self._board_version += 1
        self._update_window_title()

    def _reset_file_dirty(self):
        """载入/新建基准：视为未修改，刷新窗口标题"""
        self._board_version = 0
        self._saved_board_version = 0
        self._update_window_title()

    def _maybe_show_solved_popup(self, via_redo: bool = False):
        """状态提交后调用：刚达成复原（未复原→复原）且非重做触发时，弹出复原成功悬浮窗。

        via_redo=True 表示最后一步由 Ctrl+X 重做实现（需求：此时不提示）。
        每次调用都会同步 _prev_solved，保证「复原→离开→再复原」可再次弹出，且不会重复弹。
        """
        solved = self.is_solved()
        became_solved = solved and not getattr(self, '_prev_solved', False)
        self._prev_solved = solved
        if became_solved and not via_redo:
            self._solved_popup_active = True
            self._solved_popup_t = 0

    def move_selected_blocks(self, direction: str):
        """
        移动所有选中的滑块，逐步验证（每次1格，共step次），
        所有步骤都通过后才提交。支持动画。

        参数：
            direction: 移动方向 'w'上 's'下 'a'左 'd'右

        返回：
            bool - 是否真正执行了移动（被拦截/未选中/移动不合法均为 False）
        """
        # 手动移动会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 只读存档：禁止滑动（撤销重做除外）
        if self._readonly_blocked():
            return False
        # 计时模式：就绪态（已打乱未开始）禁止滑动，保证公平
        if self.game_mode == 'timed' and self.timer_state == 'ready':
            self.macro_notify_msg = "计时模式：按空格开始计时后才能滑动"
            self.macro_notify_timer = 90
            return False

        selected = [b for b in self.game.blocks if b.be_opted]
        if not selected:
            return False

        # 调用 game.py 的 try_move 进行纯逻辑验证
        final_positions = self.game.try_move(direction, self.current_step)
        if not final_positions:
            return False

        # 构建移动元数据
        move_info = {
            'gap_type': self.selected_gap[0] if self.selected_gap else None,
            'gap_line': self.selected_gap[1] if self.selected_gap else None,
            'direction': direction,
            'step': self.current_step,
            'moved_positions': [list(b.location) for b in selected],
        }
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
            dir_names = {'w': '上', 's': '下', 'a': '左', 'd': '右'}
            dir_str = dir_names.get(direction, direction)
            self.macro_notify_msg = f"向{dir_str}移动 {self.current_step}步"
            self.macro_notify_timer = 120
        else:
            self.game.commit_move(final_positions)
            self.step_count += 1
            self.game_history.save_snapshot(self.game, move_info)
            self._pending_move_info = None
            self.ensure_blocks_visible()
            self._maybe_show_solved_popup()
            self._mark_file_dirty()
            # 操作提示，在撤销/重做时没有显示
            dir_names = {'w': '上', 's': '下', 'a': '左', 'd': '右'}
            dir_str = dir_names.get(direction, direction)
            self.macro_notify_msg = f"向{dir_str}移动 {self.current_step}步"
            self.macro_notify_timer = 120
        return True

    def undo(self):
        """撤销操作（Ctrl+Z）"""
        # 手动撤销会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 标注录制中：不允许撤到起点之前（起点前的历史不属于本次示范）
        if self._ann_undo_blocked():
            return
        # 如果正在播放撤销/重做动画，入队等待
        if self.animating and self._undo_redo_type is not None:
            self._animation_queue.append('undo')
            return

        # 如果正在播放普通移动动画，取消后执行撤销
        if self.animating:
            self.cancel_animation()

        # 获取当前快照的移动元数据
        move_info = None
        if self.game_history.can_undo():
            move_info = self.game_history.history[self.game_history.history_index].get('move_info')

        if self.animation_enabled and self.animation_duration > 0 and move_info:
            # 有动画的撤销
            if self._start_undo_redo_animation(move_info, is_undo=True):
                self.selected_gap = None
                self.selected_block = None
                self._flash_move_selection(move_info, True)
                self.macro_notify_msg = "撤销"
                self.macro_notify_timer = 15
                return

        # 无动画的撤销（直接执行）
        success, _ = self.game_history.undo(self.game)
        if success:
            self.selected_gap = None
            self.selected_block = None
            self.step_count -= 1
            self.ensure_blocks_visible()
            self._flash_move_selection(move_info, True, after_commit=True)
            self.macro_notify_msg = "撤销"
            self.macro_notify_timer = 15
            self._maybe_show_solved_popup()
            self._mark_file_dirty()

    def redo(self):
        """重做操作（Ctrl+X）"""
        # 手动重做会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 如果正在播放撤销/重做动画，入队等待
        if self.animating and self._undo_redo_type is not None:
            self._animation_queue.append('redo')
            return

        # 如果正在播放普通移动动画，取消后执行重做
        if self.animating:
            self.cancel_animation()

        # 获取目标快照的移动元数据
        move_info = None
        if self.game_history.can_redo():
            target_idx = self.game_history.history_index + 1
            move_info = self.game_history.history[target_idx].get('move_info')

        if self.animation_enabled and self.animation_duration > 0 and move_info:
            # 有动画的重做
            if self._start_undo_redo_animation(move_info, is_undo=False):
                self.selected_gap = None
                self.selected_block = None
                self._flash_move_selection(move_info, False)
                self.macro_notify_msg = "重做"
                self.macro_notify_timer = 15
                return

        # 无动画的重做（直接执行）
        success, _ = self.game_history.redo(self.game)
        if success:
            self.selected_gap = None
            self.selected_block = None
            self.step_count += 1
            self.ensure_blocks_visible()
            self._flash_move_selection(move_info, False, after_commit=True)
            self.macro_notify_msg = "重做"
            self.macro_notify_timer = 15
            self._maybe_show_solved_popup(via_redo=True)
            self._mark_file_dirty()

    def shuffle_puzzle(self):
        """打乱谜题 - 调用 game.py 的 shuffle 核心逻辑"""
        # 打乱会改变棋盘 → 终止梯度流水线
        self._stop_gradient_pipeline()
        # 只读存档：禁止打乱
        if self._readonly_blocked():
            return
        # 标注会话随棋盘重置而结束
        self._ann_cancel_session('打乱')
        # 计时进行中禁止打乱
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法打乱"
            self.macro_notify_timer = 90
            return

        # 取消当前动画
        if self.animating:
            self.cancel_animation()

        attempts = self.current_m * self.current_n * 10  # 打乱次数

        # 调用 game.py 的 shuffle 方法
        self.game.shuffle(attempts, self.current_step)

        # 清除选中状态
        self.selected_gap = None
        self.selected_block = None

        # 步数归零，重置历史记录（以打乱态为第一条）
        self.step_count = 0
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        self.ensure_blocks_visible()
        if self.game_mode == 'timed':
            self._timer_enter_ready()
            self.macro_notify_msg = f"已打乱：{attempts}步（空格开始计时）"
        else:
            self._timer_cancel()
            self.macro_notify_msg = f"已打乱：{attempts}步（练习模式）"
        self.macro_notify_timer = 120

    def reset_puzzle(self):
        """重置谜题到初始状态"""
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法重置"
            self.macro_notify_timer = 90
            return
        self._timer_cancel()
        self.new_puzzle(self.current_m, self.current_n, self.current_step)

    # ==================== 计时器 ====================

    def _timer_enter_ready(self):
        """打乱完成后进入就绪态，捕获初始矩阵"""
        # 取消可能正在后台运行的求解器
        if self._auto_solve_running:
            self._auto_solve_cancel = True
        self.timer_state = 'ready'
        self.timer_elapsed = 0.0
        self.timer_m = self.current_m
        self.timer_n = self.current_n
        self.timer_step = self.current_step
        self.timer_puzzle_key = f"{self.current_step}~{self.current_m}*{self.current_n}"
        self.timer_initial_matrix = self.game.export_map().replace('#', '1').replace('_', '0')

    def _timer_cancel(self):
        """取消当前计时会话（回到空闲态）"""
        self.timer_state = 'idle'
        self.timer_elapsed = 0.0

    def toggle_game_mode(self):
        """切换 计时模式 / 练习模式（谜题菜单入口）"""
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换模式"
            self.macro_notify_timer = 90
            return
        if self.game_mode == 'timed':
            self.game_mode = 'practice'
            self._timer_cancel()
            self.macro_notify_msg = "练习模式：可自由滑动，不计时"
        else:
            self.game_mode = 'timed'
            self.macro_notify_msg = "计时模式：打乱后需按空格开始计时"
        self.macro_notify_timer = 120

    def _timer_start(self):
        """开始计时"""
        if self.timer_state != 'ready':
            return
        self.timer_state = 'running'
        self.timer_start = time.perf_counter()
        self.timer_elapsed = 0.0

    def _timer_on_space(self):
        """空格键：ready→开始，running→DNF（练习模式禁用计时）"""
        if self.game_mode != 'timed':
            return
        if self.timer_state == 'ready':
            self._timer_start()
        elif self.timer_state == 'running':
            self._timer_finish(dnf=True)

    def _timer_check_solved(self):
        """running 状态下检测是否复原，复原则停止计时"""
        if self.timer_state != 'running':
            return
        if self.animating:
            return
        if self.is_solved():
            self._timer_finish(dnf=False)

    def _timer_finish(self, dnf: bool):
        """结束计时并写成绩"""
        elapsed_ms = (time.perf_counter() - self.timer_start) * 1000.0
        self.timer_elapsed = elapsed_ms / 1000.0
        self.records.add_record(
            self.timer_puzzle_key,
            self.timer_m, self.timer_n, self.timer_step,
            self.timer_initial_matrix,
            elapsed_ms,
            self.step_count,
            dnf,
        )
        self.timer_state = 'dnf' if dnf else 'stopped'

        st = self.records.stats(self.timer_puzzle_key)

        def _fmt(v):
            if v is None:
                return '-'
            if v == 'DNF':
                return 'DNF'
            return format_time(v)

        cur = format_time(elapsed_ms)
        best = _fmt(st['best'])
        ao5 = _fmt(st['ao5'])
        if dnf:
            self.macro_notify_msg = f"DNF（{cur}） | 最好 {best} | Ao5 {ao5}"
        else:
            self.macro_notify_msg = f"复原！{cur}（{self.step_count}步） | 最好 {best} | Ao5 {ao5}"
        self.macro_notify_timer = 180

    def _timer_blocked(self):
        """竞速模式下宏与求解器一律禁止（练习模式不禁）"""
        return self.game_mode == 'timed'

    def _timer_status_text(self):
        """返回状态栏要显示的计时器文本（练习模式/计时模式始终显示当前状态）"""
        if self.game_mode == 'practice':
            return "练习模式"
        prefix = "竞速模式"
        if self.timer_state == 'idle':
            return f"{prefix}（待打乱）"
        if self.timer_state == 'ready':
            return f"{prefix}（就绪，空格开始）"
        if self.timer_state == 'running':
            return f"{prefix} {format_time(self.timer_elapsed * 1000)}"
        if self.timer_state == 'stopped':
            return f"{prefix} 成绩 {format_time(self.timer_elapsed * 1000)}"
        if self.timer_state == 'dnf':
            return f"{prefix} DNF"
        return ""

    def _start_auto_solve(self):
        """启动/停止自动求解"""
        import threading
        import time
        from copy import deepcopy

        # 计时中禁止使用求解器
        if self._timer_blocked():
            self.macro_notify_msg = "计时中无法使用求解器"
            self.macro_notify_timer = 90
            return

        # 只读存档：禁止自动求解
        if self._readonly_blocked():
            return

        # 标注录制中：自动回放不是人类示范，禁用
        if getattr(self, '_ann_recording', False):
            self.macro_notify_msg = "标注录制中无法使用自动求解"
            self.macro_notify_timer = 90
            return

        # 如果正在求解，則取消
        if self._auto_solve_running:
            self._auto_solve_cancel = True
            if getattr(self, '_gradient_state', None) is not None:
                # 梯度流水线：取消后台计算，丢弃已排队的结果
                self._gradient_state = None
                self._gradient_gen += 1
                self.macro_notify_msg = "梯度聚拢已停止"
                self.macro_notify_timer = 90
            return

        # 梯度播放中：再次点击 = 停止（终止后续阶段与后台计算）
        if self.macro_executing:
            if getattr(self, '_gradient_state', None) is not None:
                self._gradient_state = None
                self._auto_solve_cancel = True
                self._gradient_gen += 1
                self.macro_notify_msg = "梯度聚拢已停止"
                self.macro_notify_timer = 90
            return

        self._auto_solve_result = None
        self._auto_solve_done = False
        self._auto_solve_running = True
        self._auto_solve_cancel = False
        self._auto_solve_start_time = time.time()
        self._auto_solve_progress = None

        game_snapshot = deepcopy(self.game)
        algorithm = self.solver_algorithm

        # 梯度聚拢：启动后台流水线（各阶段连续计算，主线程并行播放动画）
        if algorithm == 'gather_gradient':
            from solver.ml.gather_solver import predict_params
            self._gradient_state = {'max_stages': 4}
            self._gradient_gen += 1
            gen = self._gradient_gen
            self._gradient_busy = True
            base_params = predict_params(game_snapshot, self.current_step)
            self._drain_gradient_queue()
            threading.Thread(target=self._gradient_worker,
                             args=(gen, game_snapshot, base_params, 4),
                             daemon=True).start()
            return

        def cancel_check():
            return self._auto_solve_cancel

        def progress_callback(info):
            self._auto_solve_progress = info

        def solve_thread():
            try:
                from solver import SOLVER_ALGORITHMS
                alg_name, solver_func = SOLVER_ALGORITHMS.get(
                    algorithm, SOLVER_ALGORITHMS['ida_star']
                )
                kwargs = {}
                if algorithm == 'gather':
                    # 禁用的参数传 None（不设限）
                    for k, v in self.gather_params.items():
                        kwargs[k] = v if self.gather_enabled.get(k, True) else None
                solution = solver_func(
                    game_snapshot, step=self.current_step,
                    cancel_check=cancel_check,
                    progress_callback=progress_callback,
                    **kwargs,
                )
                if self._auto_solve_cancel:
                    self._auto_solve_result = False
                else:
                    self._auto_solve_result = solution
            except Exception as e:
                print(f"[自动求解] 出错: {e}")
                self._auto_solve_result = False
            finally:
                self._auto_solve_running = False
                self._auto_solve_done = True

        threading.Thread(target=solve_thread, daemon=True).start()

    def _drain_gradient_queue(self):
        """清空梯度流水线队列（丢弃过期结果）"""
        try:
            while True:
                self._gradient_queue.get_nowait()
        except Exception:
            pass

    def _gradient_worker(self, gen, snap, base_params, max_stages):
        """梯度流水线后台线程：阶段 k+1 的计算与阶段 k 的动画并行。

        sim 是求解私有的棋盘副本，从「上一阶段解完的构型」继续算下一阶段，
        不等待动画——动画只发生在主线程的真实棋盘上，二者互不冲突。
        """
        try:
            from solver.ml.gather_solver import gather_solve, stage_params

            def cancel_check():
                return self._auto_solve_cancel or gen != self._gradient_gen

            def progress_callback(info):
                self._auto_solve_progress = info

            for idx in range(max_stages):
                if cancel_check():
                    break
                p = stage_params(base_params, idx)
                r = gather_solve(snap, step=self.current_step,
                                 cancel_check=cancel_check,
                                 progress_callback=progress_callback, **p)
                if cancel_check():
                    break
                r = dict(r)
                r['gradient_stage'] = idx + 1
                r['gradient_total'] = max_stages
                self._gradient_queue.put((gen, r))
                # 该阶段无任何动作可播（且未复原）：与旧逻辑一致，整条流程到此为止
                if not r.get('actions') and not r.get('solved'):
                    break
                # 已复原或真正无法继续：不再安排后续阶段
                if r.get('solved') or r.get('reason') in (
                        'timeout', 'cancelled', 'no_candidates', 'invalid_action'):
                    break
        except Exception as e:
            print(f"[梯度流水线] 出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._gradient_queue.put((gen, None))  # 结束哨兵
            self._gradient_busy = False
            self._auto_solve_running = False

    def _pump_gradient_results(self):
        """把后台已算好的阶段结果，按序交给动画管道逐阶段播放。"""
        gen = self._gradient_gen
        while True:
            try:
                item_gen, item = self._gradient_queue.get_nowait()
            except Exception:
                return  # 队列暂时为空：后台仍在计算，继续等待
            if item_gen != gen:
                continue  # 过期项（取消/重开）：丢弃
            if item is None:
                # 后台全部算完且没有更多阶段：收尾
                self._gradient_state = None
                self.macro_notify_persistent = False
                return
            self._handle_gather_result(item)
            return

    def _stop_gradient_pipeline(self):
        """终止梯度流水线：手动改动棋盘会使已排队阶段失效，必须停止。"""
        if getattr(self, '_gradient_state', None) is None and not self._gradient_busy:
            return
        self._gradient_state = None
        self._auto_solve_cancel = True
        self._gradient_gen += 1
        self._drain_gradient_queue()

    def _check_auto_solve_result(self):
        """检查后台求解结果，如有结果则启动宏执行"""
        # 梯度流水线：后台连续计算，这里按序播放已就绪的阶段动画
        if (getattr(self, '_gradient_state', None) is not None
                and not self.macro_executing and not self.animating):
            self._pump_gradient_results()
            return
        if not self._auto_solve_done:
            return
        if self.macro_executing or self.animating:
            return

        # 计时中丢弃求解结果（禁止求解器帮助）
        if self._timer_blocked():
            self._auto_solve_done = False
            self._auto_solve_result = None
            return

        self._auto_solve_done = False
        result = self._auto_solve_result
        self._auto_solve_result = None

        if result is None:
            self._gradient_state = None
            self.macro_notify_msg = "自动求解：未找到数据库"
            self.macro_notify_timer = 180
            return

        if isinstance(result, dict) and result.get('type') in ('gather', 'gather_gradient'):
            self._handle_gather_result(result)
            return

        if isinstance(result, dict) and result.get('type') == 'fill_fail':
            self.macro_notify_msg = '填洞宏：' + str(result.get('reason', '失败'))
            self.macro_notify_timer = 220
            return

        if isinstance(result, dict) and result.get('type') == 'fill_partial':
            # 规则中断：播放已成功的部分动作，停在断点供用户观察
            reason = str(result.get('reason', '中断'))
            actions = result.get('actions', [])
            reps = result.get('rep_cells', [])
            ops = []
            for i, action in enumerate(actions):
                gap_dir, gap_line, side, move_dir = action
                op = {
                    'gap_type': gap_dir,
                    'gap_line': gap_line,
                    'side': side,
                    'direction': move_dir,
                    'step': self.current_step,
                }
                if i < len(reps) and reps[i]:
                    op['rep_cell'] = reps[i]
                ops.append(op)
            if not ops:
                self.macro_notify_msg = '填洞宏（断）：' + reason
                self.macro_notify_timer = 220
                return
            self.macro_executing = True
            self.macro_exec_name = '填洞宏（断：%s）' % reason
            self.macro_exec_ops = ops
            self.macro_exec_index = 0
            self.macro_exec_factor = 1
            self._execute_next_macro_step()
            return

        if result is False:
            self._gradient_state = None
            self.macro_notify_msg = "自动求解：未找到解法"
            self.macro_notify_timer = 180
            return

        if len(result) == 0:
            self.macro_notify_msg = "自动求解：已是复原状态"
            self.macro_notify_timer = 180
            return

        # 查表求解器返回 (actions, rep_cells) 元组，包含代表方块坐标
        rep_cells = None
        if isinstance(result, tuple):
            actions, rep_cells = result
        else:
            actions = result

        # 转换 solver Action → macro op
        ops = []
        for i, action in enumerate(actions):
            gap_dir, gap_line, side, move_dir = action
            op = {
                'gap_type': gap_dir,
                'gap_line': gap_line,
                'side': side,
                'direction': move_dir,
                'step': self.current_step,
            }
            if rep_cells:
                op['rep_cell'] = rep_cells[i]
            ops.append(op)

        # 通过宏执行管道播放解法（含动画）
        self.macro_executing = True
        self.macro_exec_name = "自动求解"
        self.macro_exec_ops = ops
        self.macro_exec_index = 0
        self.macro_exec_factor = 1
        self._execute_next_macro_step()

    def _handle_gather_result(self, result):
        """处理聚拢求解结果：播放动作，并实时显示聚拢度。"""
        actions = result.get('actions', [])
        rep_cells = result.get('rep_cells', [])
        solved = result.get('solved', False)
        reason = result.get('reason', '')

        # 停机原因播报
        reason_text = {
            'solved': '已还原',
            'target': '达到目标聚拢度',
            'no_improve': '停滞无改进',
            'max_steps': '步数上限耗尽',
            'timeout': '达到时间上限',
            'cancelled': '已取消',
            'stuck': '无新状态可探索',
            'no_candidates': '无可移动动作',
            'invalid_action': '动作无效',
            'stages_exhausted': '阶段耗尽',
        }.get(reason, reason or '完成')

        if not actions:
            # 无可播放动作 = 梯度流程到此为止（同时停掉后台流水线）
            if getattr(self, '_gradient_state', None) is not None:
                self._gradient_state = None
                self._auto_solve_cancel = True
                self._gradient_gen += 1
            if solved:
                self.macro_notify_msg = "聚拢：已是复原状态"
            else:
                self.macro_notify_msg = f"聚拢：无可移动动作（{reason_text}）"
            self.macro_notify_timer = 180
            return

        s, e = result.get('start', {}), result.get('end', {})
        sh, sw = s.get('bbox', (0, 0))
        eh, ew = e.get('bbox', (0, 0))
        gstage = result.get('gradient_stage')
        if gstage:
            gtotal = result.get('gradient_total', 4)
            self.macro_notify_msg = (
                f"梯度聚拢 第{gstage}/{gtotal}阶段完成（{reason_text}）· {len(actions)}步 · "
                f"聚拢度 {s.get('score', 0)*100:.1f}%→{e.get('score', 0)*100:.1f}%"
            )
        else:
            stages_info = ''
            if result.get('stages'):
                parts = []
                for st in result['stages']:
                    rname = {
                        'solved': '完成', 'no_improve': '停滞', 'stuck': '绕圈',
                        'max_steps': '步满', 'timeout': '超时',
                    }.get(st.get('reason', ''), st.get('reason', ''))
                    parts.append(f"{st.get('stage')}:{st.get('steps')}步({rname})")
                stages_info = ' · 阶段[' + '|'.join(parts) + ']'
            self.macro_notify_msg = (
                f"聚拢完成（{reason_text}）· 共{len(actions)}步 · "
                f"聚拢度 {s.get('score', 0)*100:.1f}%→{e.get('score', 0)*100:.1f}% "
                f"· 边界盒 {sh}×{sw}→{eh}×{ew}{stages_info}"
            )
        self.macro_notify_timer = 240

        ops = []
        for i, action in enumerate(actions):
            gap_dir, gap_line, side, move_dir = action
            op = {
                'gap_type': gap_dir,
                'gap_line': gap_line,
                'side': side,
                'direction': move_dir,
                'step': self.current_step,
            }
            if rep_cells and i < len(rep_cells):
                op['rep_cell'] = rep_cells[i]
            ops.append(op)

        self._gather_info = {
            'start': result.get('start', {}),
            'end': result.get('end', {}),
            'solved': solved,
            'reason': reason,
            'gradient_stage': gstage,
            'gradient_total': result.get('gradient_total'),
        }
        self.macro_executing = True
        self.macro_exec_name = "聚拢"
        self.macro_exec_ops = ops
        self.macro_exec_index = 0
        self.macro_exec_factor = 1
        self._execute_next_macro_step()

    def close_all_menus(self):
        """关闭所有下拉菜单"""
        self.show_file_menu = False
        self.show_edit_menu = False
        self.show_puzzle_menu = False
        self.show_settings_menu = False
        self.show_macro_menu = False

    def is_blank_area(self, screen_x: int, screen_y: int) -> bool:
        """判断指定位置是否为空白区域"""
        return self.get_block_at_pos(screen_x, screen_y) is None and \
               self.get_gap_at_pos(screen_x, screen_y) is None

    def run(self):
        """游戏主循环"""
        clock = pygame.time.Clock()

        while self.running:
            try:
                # 处理终端指令
                self.process_commands()

                # 更新动画
                self.update_animation()

                # 检查自动求解结果
                self._check_auto_solve_result()

                # 计时器：刷新实时用时 + 检测复原
                if self.timer_state == 'running':
                    self.timer_elapsed = time.perf_counter() - self.timer_start
                self._timer_check_solved()

                # 求解中显示计时和进度（宏动画播放阶段保留逐步行进提示）
                if self._auto_solve_running and not self.macro_executing:
                    elapsed = time.time() - self._auto_solve_start_time
                    progress = self._auto_solve_progress
                    if progress:
                        if progress.get('stage') == 'gradient_stage':
                            idx = progress.get('idx', 1)
                            total = progress.get('total', 4)
                            self.macro_notify_msg = f"梯度聚拢 第{idx}/{total}阶段（放宽参数再聚拢）..."
                        elif progress.get('stage') == 'gather':
                            score = progress.get('score', 0)
                            best = progress.get('best_score', 0)
                            bbox = progress.get('bbox', None)
                            fill = progress.get('fill_rate', 0)
                            if bbox:
                                bh, bw = bbox
                                self.macro_notify_msg = (
                                    f"聚拢中... 聚拢度 {score*100:.1f}%（最优 {best*100:.1f}%）"
                                    f"边界盒 {bh}×{bw} 填充 {fill*100:.0f}% | {elapsed:.1f}s"
                                )
                            else:
                                self.macro_notify_msg = f"聚拢中... 聚拢度 {score*100:.1f}%（最优 {best*100:.1f}%） | {elapsed:.1f}s"
                        else:
                            stage = progress.get('stage', '')
                            bound = progress.get('bound', 0)
                            nodes = progress.get('nodes', 0)
                            path_preview = progress.get('path_preview', '')
                            self.macro_notify_msg = f"[{stage}] 深度{bound} 节点{nodes} {path_preview} | {elapsed:.1f}s"
                    else:
                        self.macro_notify_msg = f"求解中... {elapsed:.1f}s"
                    self.macro_notify_timer = 180
                    self.macro_notify_persistent = True  # 持续显示不走淡出
                else:
                    self.macro_notify_persistent = False

                # 更新宏通知计时器（持玖模式不递减）
                if self.macro_notify_timer > 0 and not self.macro_notify_persistent:
                    self.macro_notify_timer -= 1

                # 处理文件对话框结果
                self.handle_file_dialog_result()

                # 处理长按撤销/重做
                now = pygame.time.get_ticks()
                if self.undo_held and not self.undo_first:
                    if now - self.undo_timer >= self.key_repeat_interval:
                        self.undo()
                        self.undo_timer = now
                if self.redo_held and not self.redo_first:
                    if now - self.redo_timer >= self.key_repeat_interval:
                        self.redo()
                        self.redo_timer = now
                # 首次延迟后切换到重复模式
                if self.undo_first and self.undo_held:
                    if now - self.undo_timer >= self.key_repeat_delay:
                        self.undo_first = False
                        self.undo_timer = now
                if self.redo_first and self.redo_held:
                    if now - self.redo_timer >= self.key_repeat_delay:
                        self.redo_first = False
                        self.redo_timer = now

                self.draw_board()
                self.draw_right_panel()

                # 动态更新编辑菜单的求解按钮文字
                shortcut = self._format_menu_shortcut('auto_solve')
                if self._auto_solve_running:
                    self.edit_menu_items[-1] = f'停止求解 {shortcut}'
                else:
                    self.edit_menu_items[-1] = f'自动求解 {shortcut}'

                self.draw_menu_bar()
                self.draw_status_bar()

                # 浮动面板（先画，被模态对话框遮住）
                self.draw_virtual_keyboard()
                self.draw_metrics_panel()
                self.draw_records_panel()
                # 标注模式（工具栏 + 跟踪标记 + 子对话框）
                self.draw_annotation_mode()

                # 模态对话框（后画，最上层）
                if self.show_help:
                    self.draw_help_dialog()
                if self.show_custom_dialog:
                    self.draw_custom_puzzle_dialog()
                if self.file_dialog.active:
                    self.file_dialog.draw()
                if self.show_settings_dialog:
                    self.draw_settings_dialog()
                if getattr(self, 'show_macro_manager_dialog', False):
                    self.draw_macro_manager_dialog()
                if getattr(self, 'show_macro_name_dialog', False):
                    self.draw_macro_name_dialog()

                '''# 虚拟键盘（浮动面板）
                self.draw_virtual_keyboard()

                # 聚拢度指标面板（浮动面板）
                self.draw_metrics_panel()

                # 成绩记录面板（浮动面板）
                self.draw_records_panel()'''

                # 宏执行结果通知（最顶层绘制）
                self.draw_macro_notify()
                # 复原成功悬浮窗（最顶层）
                self.draw_solved_popup()

                self.handle_events()
                # 标注模式：捕捉录制提交 / 处理存档打开结果
                self._ann_poll()
                pygame.display.flip()
                dt_ms = clock.tick(60)

                # 更新文本输入闪烁
                if self.file_dialog.active:
                    self.file_dialog.update(dt_ms)
                if getattr(self, 'show_macro_name_dialog', False):
                    macro_input = getattr(self, 'macro_name_text_input', None)
                    if macro_input:
                        macro_input.update(dt_ms)
            except Exception as e:
                _gui_log_error(f'主循环异常: {traceback.format_exc()}')
                print(f"Run error: {e}")
                self.running = False

        # 退出前保存配置与成绩（成绩内存中维护，此时统一落盘）
        self.records.save()
        self.save_config()
        pygame.quit()
        sys.exit()
