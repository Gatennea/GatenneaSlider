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
from puzzle_types import create_puzzle, puzzle_key
from game_triangle import tri_key
from gui.renderer import RendererMixin
from gui.dialogs import DialogsMixin
from gui.animation import AnimationMixin
from gui.file_ops import FileOpsMixin
from gui.events import EventsMixin
from gui.virtual_keyboard import VirtualKeyboardMixin
from gui.metrics_panel import MetricsPanelMixin
from gui.records_panel import RecordsPanelMixin
from gui.annotation import AnnotationMixin
from gui.tutorial import TutorialMixin
from gui.board_view import SquareBoardView


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


class SliderGUI(RendererMixin, DialogsMixin, AnimationMixin, FileOpsMixin, EventsMixin, VirtualKeyboardMixin, MetricsPanelMixin, RecordsPanelMixin, AnnotationMixin, TutorialMixin):
    """
    滑块游戏图形界面类
    """

    def __init__(self, m: int = 6, n: int = 6, step: int = 1, cmd_queue: queue.Queue = None,
                 kind: str = 'square'):
        """
        初始化游戏界面

        参数：
            m: 初始滑块行数，默认为6
            n: 初始滑块列数，默认为6
            step: 移动步数（等级），默认为1
            cmd_queue: 命令队列（用于接收终端指令），默认为None
            kind: 开局形态 'square' / 'numbered' / 'triangle'（三角形时 m 作边长 k）
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
        self.game = create_puzzle(m, n, step)

        # 幾何抽象（預設正方形；三角形將於 Stage B 替換為 TriangleBoardView）
        self.board_view = SquareBoardView(self.cell_size, self.gap_width)

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
        # 注意：「教程」入口位于“帮助”右侧，点击开始/继续/回顾新手教程；
        # 最后一项「官网」点击用默认浏览器打开 Web 版主页。
        self.menu_items = ['文件', '编辑', '谜题', '宏定义', '设置', '帮助', '教程', '官网']
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
        # 预设选项（第一项是给玩家看的名字，不带内部键名）：
        #   ('__group__', 标题)   分组标题，不可点击
        #   ('---',)             分隔线
        #   ('自定义...',)        打开自定义对话框
        #   ('__current__',)     底部「当前谜题」状态行，不可点击
        #   (显示名, m, n, step[, kind])  kind 为 'triangle' / 'numbered'，缺省矩形
        # 「当前是哪一档」由 _preset_puzzle_key() 和 _current_puzzle_key() 比对，
        # 以后再加形态也不用改渲染分支。模式切换已移到主窗口右下角，故不再放这里
        self.puzzle_presets = [
            ('__group__', '矩形谜题'),
            ('4×4 等级2', 4, 4, 2),
            ('5×5 等级2', 5, 5, 2),
            ('6×6 等级2', 6, 6, 2),
            ('7×7 等级2', 7, 7, 2),
            ('8×8 等级2', 8, 8, 2),
            ('9×9 等级2', 9, 9, 2),
            ('10×10 等级2', 10, 10, 2),
            ('---',),
            ('6×6 等级3', 6, 6, 3),
            ('8×8 等级3', 8, 8, 3),
            ('10×10 等级3', 10, 10, 3),
            ('__group__', '三角形谜题'),
            ('边长4 等级1', 4, 4, 1, 'triangle'),
            ('边长6 等级2', 6, 6, 2, 'triangle'),
            ('边长8 等级2', 8, 8, 2, 'triangle'),
            ('__group__', '数字谜题'),
            ('4×4 等级2', 4, 4, 2, 'numbered'),
            ('6×6 等级2', 6, 6, 2, 'numbered'),
            ('8×8 等级2', 8, 8, 2, 'numbered'),
            ('---',),
            ('自定义...',),
            ('__current__',),   # 底部「当前：矩形 6×6 等级2」状态行
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
        # 打乱质量参数（控制 shuffle 的偏置强度和最低难度门槛）
        # bias：Metropolis 接受偏差，越大越偏向更散状态（0=纯随机）
        # min_score：打完后的聚拢度阈值，超过则重洗（None=不检查）
        self.shuffle_bias = 0.3
        self.shuffle_min_score = 0.75
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
        # 控制模式开关（独立布尔，非互斥；对应 web 版 touch-gesture.md 的三种模式）：
        #  single_touch：直接拖拽滑塊即滑動（移动后清空选中）
        #  two_touch   ：点缝隙→点滑块→再拖拽/键盘（原版两次触控习惯）
        #  mouse_kb    ：键盘/方向键移动（桌面键鼠）
        self.control_single_touch = True
        self.control_two_touch = True
        self.control_mouse_kb = True
        # 拖拽判定阈值（像素，可随 zoom 联动）
        self.drag_threshold = 14
        # 鼠标拖拽状态：None 或 dict(起始屏幕坐标, 起点滑块, 累计位移, 是否已判定为拖拽)
        self._mouse_drag_state = None
        # 存档只读：
        #  _readonly=True 时禁用改变滑块组状态的功能（滑动/求解/打乱/宏等），仅允许撤销重做
        # save_readonly_flag 是设置开关：打开后所有保存的存档都带 readonly 标记
        self._readonly = False
        self.save_readonly_flag = False
        # 防止覆盖开关：打开后按 Ctrl+S 一律进入另存为，避免误覆盖旧存档
        self.prevent_overwrite_flag = False
        # 复原成功悬浮窗：
        #  _solved_popup_active：当前是否显示；_solved_popup_t：弹入动画计时
        #  _prev_solved：上一次状态提交后的复原状况（用于判定“刚达成复原”，避免重复弹窗）
        self._solved_popup_active = False
        self._solved_popup_t = 0
        self._prev_solved = False
        # 左键单击反馈：活动涟漪列表，元素 {x, y, t0}（见 spawn/draw_click_feedback）
        self._click_feedback = []
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
        self.custom_kind = 'rect'       # 'rect' 矩形 / 'triangle' 三角 / 'numbered' 数字

        # 三角形密铺模式（Stage B）：self.game 为 TriangleSliderMatrix 时为 True
        self.triangle_mode = False
        self.triangle_side = 6

        # 历史记录
        self.game_history = GameHistory()

        # 计时器与成绩记录
        # 无头（headless）测试环境使用独立成绩文件，避免测试成绩污染真实 records.dat
        _is_headless = (os.environ.get('SDL_VIDEODRIVER') == 'dummy'
                        or os.environ.get('SDL_AUDIODRIVER') == 'dummy')
        _records_name = 'records_test.dat' if _is_headless else 'records.dat'
        _records_path = os.path.join(self.config_dir, _records_name)
        if _is_headless and os.path.exists(_records_path):
            try:
                os.remove(_records_path)  # 每次无头运行从空成绩开始，防累积
            except OSError:
                pass
        self.records = Records(_records_path)
        self.timer_state = 'idle'   # idle/ready/running/dnf/stopped
        self.timer_start = 0.0      # perf_counter 计时起点
        self.timer_elapsed = 0.0    # 已用秒数（浮点）
        self.timer_m = 0
        self.timer_n = 0
        self.timer_step = 0
        self.timer_initial_matrix = ''
        self.timer_puzzle_key = ''
        # 'practice' 练习 / 'timed' 竞速（计时）/ 'create' 创造（造题）
        self.game_mode = 'practice'
        # 最近一次计时完成结果（供复原成功悬浮窗显示成绩/TPS/最佳判定）
        self._last_timed_result = None

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
        # 选中会话标识：同一次选中下连续移动并入同一快照（见 history.save_snapshot）
        self._move_session_id = 0

        # 撤销/重做动画状态
        self._undo_redo_type = None  # 当前动画类型：'undo'/'redo'/None
        self._animation_queue = []   # 待执行的撤销/重做队列，存储 'undo'/'redo'

        # 连续撤销/重做（虚拟键盘一键连续播放）：True=连续模式进行中
        self._continuous_undo = False
        self._continuous_redo = False

        # 动画统一偏移量（方案四：所有Block使用同一偏移量）
        self._anim_dr = 0.0
        self._anim_dc = 0.0

        # 拖拽跟随状态（实时预览）
        self.drag_following = False
        self.drag_follow_block = None
        self.drag_follow_start_pos = None
        self.drag_follow_start_screen = None
        self.drag_follow_offset = (0.0, 0.0)
        self.drag_follow_max_cells = 0                    # 本方向可连续推进的最大格数（current_step 的整数倍）
        self.drag_follow_auto_deselect = False            # 本次跟随是否由单次触控发起（结束时需自动取消选中）
        self.drag_follow_gap = None
        self.drag_follow_direction = None
        self.drag_follow_step = 0
        self.drag_follow_invalid = False

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
            # 三角形密铺的另外两个对角方向（w/a/d/s 复用上面的四向键位）
            'tri_up_right': {'key': 'e', 'modifiers': []},
            'tri_down_left': {'key': 'z', 'modifiers': []},
            'tri_down_right': {'key': 'x', 'modifiers': []},
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
            'tri_up_right': '右上移',
            'tri_down_left': '左下移',
            'tri_down_right': '右下移',
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
            ('游戏操作', ['move_up', 'move_down', 'move_left', 'move_right',
                          'tri_up_right', 'tri_down_left', 'tri_down_right',
                          'virtual_keyboard', 'metrics_panel', 'records_panel']),
        ]

        # 虚拟键盘状态
        self._vk_init_state()

        # 聚拢度指标面板状态
        self._mp_init_state()

        # 成绩记录面板状态
        self._rp_init_state()

        # 标注模式状态
        self._ann_init_state()

        # 教程模式状态
        self._tut_init_state()

        # 加载上次状态
        self.load_last_state()

        # 命令行显式指定形态：以命令行为准，覆盖上面恢复的上次局面
        # （kind='square' 是默认值，不覆盖，保持「记住上次关闭时的样子」）
        if kind == 'triangle':
            self.new_triangle_puzzle(m, step)
        elif kind == 'numbered':
            self.new_puzzle(m, n, step, numbered=True)

        # 首次启动：弹出新手教程引导
        self._tut_check_first_launch()

    def new_puzzle(self, m: int, n: int, step: int = 1, numbered: bool = False):
        """
        创建新谜题

        参数：
            m: 行数
            n: 列数
            step: 移动步数（等级）
            numbered: 是否使用带序号滑块
        """
        # 切换谜题会重置棋盘 → 终止梯度流水线
        self._stop_gradient_pipeline()
        # 切换谜题会重置棋盘 → 打断连续撤销/重做
        self._stop_continuous_undo_redo()
        # 切换谜题 → 清掉上一次的计时成绩
        self._last_timed_result = None
        # 标注会话随棋盘重置而结束
        self._ann_cancel_session('切换谜题')
        # 验证等级约束：step < max(m, n)
        if step >= max(m, n):
            return False

        # 计时进行中禁止切换谜题
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换谜题"
            self.macro_notify_timer = 90
            return False
        self._timer_cancel()

        # 只读存档：允许切换谜题 —— 换的是另一张棋盘，不改动原存档的内容；
        # 但必须同时脱离只读存档（清只读标记 + 解除文件绑定），否则新谜题会继承
        # 只读而无法滑动，且 current_file_path 仍指向受保护档案，Ctrl+S 会覆写它
        detached = self._detach_readonly_save()

        self.current_m = m
        self.current_n = n
        self.current_step = step
        # 切回方形：清除三角形模式标记（存档/热键路径都走这里）
        self.triangle_mode = False

        # 创建新的游戏对象
        kind = 'numbered' if numbered else 'square'
        self.game = create_puzzle(m, n, step, kind=kind)
        self.numbered = numbered

        # 重置状态
        self.zoom = 1.0
        self.selected_gap = None
        self.selected_block = None
        self.step_count = 0

        # 取消动画
        self.animating = False
        self.anim_blocks = []

        # 带序号模式：按行主序赋予编号 1..m*n（必须在 save_snapshot 之前）
        if numbered:
            for idx, block in enumerate(self.game.blocks, start=1):
                block.number = idx
        else:
            for block in self.game.blocks:
                block.number = None

        # 重置历史记录
        self.game_history.reset()
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()

        if detached:
            self.macro_notify_msg = (f"切换谜题：{m}×{n} 等级{step}"
                                     "（只读存档已脱离，保存请另存为）")
            self.macro_notify_timer = 180
        else:
            self.macro_notify_msg = f"切换谜题：{m}×{n} 等级{step}"
            self.macro_notify_timer = 120
        return True

    def new_triangle_puzzle(self, k: int, step: int = 1) -> bool:
        """创建正三角形密铺谜题（B2：可滑动）。

        参数：
            k: 大三角形边长（单元三角个数，共 k² 个滑块）
            step: 移动步数（等级），须小于 k

        建局即为实心大三角形（還原態），Alt+S 另行打亂。
        求解器/著色等高級功能照計劃禁用。
        """
        if self._tut_board_locked():
            return False
        # 切换谜题会重置棋盘 → 终止梯度流水线 / 连续撤销重做
        self._stop_gradient_pipeline()
        self._stop_continuous_undo_redo()
        self._last_timed_result = None
        self._ann_cancel_session('切换谜题')

        if k < 2 or step >= k:
            return False
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换谜题"
            self.macro_notify_timer = 90
            return False
        self._timer_cancel()
        detached = self._detach_readonly_save()

        self.current_m = k
        self.current_n = k
        self.current_step = step
        self.triangle_side = k
        self.triangle_mode = True
        self.numbered = False

        self.game = create_puzzle(k, k, step, kind='triangle', triangle_side=k)

        # 重置状态
        self.zoom = self._fit_triangle_zoom()
        self.selected_gap = None
        self.selected_block = None
        self.step_count = 0
        self.animating = False
        self.anim_blocks = []
        for block in self.game.blocks:
            block.number = None

        self.game_history.reset()
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()

        self.macro_notify_msg = (
            f"切换谜题：三角形 边长{k} 等级{step}"
            f"（初始为实心大三角，Alt+S 打乱；W/E/A/D/Z/X 六向，或直接拖动滑块）")
        self.macro_notify_timer = 150
        return True

    def _triangle_blocked(self, action: str) -> bool:
        """三角形模式下尚未实现的操作：给出一致提示并拦截。

        B2 起滑动/打乱已开放；这里只剩求解器与竞速计时等后续阶段的功能。
        """
        if not getattr(self, 'triangle_mode', False):
            return False
        self.macro_notify_msg = f"三角形密铺：{action}尚未实现（后续阶段开发中）"
        self.macro_notify_timer = 120
        return True

    def _fit_triangle_zoom(self, fill: float = 0.78) -> float:
        """三角形棋盘初始缩放：让大三角形铺满可视区的主要部分。"""
        view = self._tri_view()
        min_x, min_y, max_x, max_y = view.bounding_box(self.game.positions())
        bw = max(1e-6, max_x - min_x)
        bh = max(1e-6, max_y - min_y)
        avail_w = (self.screen_width - self.right_panel_width) * fill
        avail_h = (self.screen_height - self.menu_bar_height - self.status_bar_height) * fill
        return max(self.min_zoom, min(self.max_zoom,
                                      min(avail_w / bw, avail_h / bh)))

    def _center_triangle(self):
        """三角形棋盘居中：按多边形包围盒算相机偏移。"""
        view = self._tri_view()
        min_x, min_y, max_x, max_y = view.bounding_box(self.game.positions())
        board_cx = (min_x + max_x) / 2.0
        board_cy = (min_y + max_y) / 2.0
        game_center_x = (self.screen_width - self.right_panel_width) / 2
        game_center_y = (self.menu_bar_height +
                         (self.screen_height - self.menu_bar_height - self.status_bar_height) / 2)
        self.camera_x = game_center_x - board_cx * self.zoom
        self.camera_y = game_center_y - board_cy * self.zoom

    def is_solved(self) -> bool:
        """判断当前是否为复原状态（比较0-1矩阵形状；带序号时额外检查编号顺序）"""
        if not getattr(self, 'numbered', False):
            return self.game.is_solved()
        if not self.game.is_solved():
            return False
        # 带序号：编号须按行主序排布，但允许整体旋转/镜像（矩形的二面体群 D4，共 8 种）。
        # 例如 4x3 的 1..12 旋转 90° 成 3x4 后仍递增，也算复原。
        # 边界直接由方块位置算出（与 game.is_solved() 同源，不依赖可能过期的 matrix_bounds）
        min_row = min(b.location[0] for b in self.game.blocks)
        min_col = min(b.location[1] for b in self.game.blocks)
        rows = max(b.location[0] for b in self.game.blocks) - min_row + 1
        cols = max(b.location[1] for b in self.game.blocks) - min_col + 1
        cells = {}
        for block in self.game.blocks:
            num = getattr(block, 'number', None)
            if num is None:
                # 编号缺失无法验证顺序 → 不判胜（避免误奖）
                return False
            r, c = block.location
            cells[(r - min_row, c - min_col)] = num
        if len(cells) != rows * cols:
            return False
        # 8 个对称变换：(i,j) -> (a,b)，目标网格尺寸 (rows2, cols2)
        transforms = (
            (lambda i, j: (i, j), rows, cols),                       # 恒等
            (lambda i, j: (rows - 1 - i, cols - 1 - j), rows, cols),  # 旋转 180°
            (lambda i, j: (rows - 1 - i, j), rows, cols),            # 上下镜像
            (lambda i, j: (i, cols - 1 - j), rows, cols),            # 左右镜像
            (lambda i, j: (j, i), cols, rows),                       # 主对角线翻转
            (lambda i, j: (cols - 1 - j, rows - 1 - i), cols, rows),  # 副对角线翻转
            (lambda i, j: (j, rows - 1 - i), cols, rows),            # 旋转 90°
            (lambda i, j: (cols - 1 - j, i), cols, rows),            # 旋转 270°
        )
        for fn, rows2, cols2 in transforms:
            for (i, j), num in cells.items():
                a, b = fn(i, j)
                if num != a * cols2 + b + 1:
                    break
            else:
                return True
        return False

    def ensure_blocks_visible(self):
        """确保所有滑块都在可视区域内，超出时自动调整相机"""
        if not self.game.blocks:
            return

        scaled_cell = self.cell_size * self.zoom

        # 可视区域（排除菜单栏、状态栏和右侧面板）
        view_left = 0
        view_right = self.screen_width - self.right_panel_width
        view_top = self.menu_bar_height
        view_bottom = self.screen_height - self.status_bar_height

        # 留一些边距
        margin = scaled_cell * 0.5

        if getattr(self, 'triangle_mode', False):
            # 三角形密铺：包围盒走 board_view（世界坐标 → 屏幕坐标）。
            # 打乱/移动后形状可能摊开超出视口，与方形同样拉回可见区。
            view = self._tri_view()
            min_x, min_y, max_x, max_y = view.bounding_box(self.game.positions())
            min_screen_x, min_screen_y = self.world_to_screen(min_x, min_y)
            max_screen_x, max_screen_y = self.world_to_screen(max_x, max_y)
        else:
            scaled_gap = self.gap_width * self.zoom

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
        if getattr(self, 'triangle_mode', False):
            self._center_triangle()
            return
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

            if getattr(self, 'triangle_mode', False):
                key = self._tri_view().world_to_cell(world_x, world_y)
                if key is None:
                    return None
                for block in self.game.blocks:
                    if tri_key(block) == key:
                        return block
                return None

            for block in self.game.blocks:
                x, y, w, h = self.board_view.block_rect(*block.location)
                rect = pygame.Rect(x, y, w, h)
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
            cell = self.board_view.world_to_cell(world_x, world_y)
            if cell is None:
                return None
            return cell
        except Exception as e:
            print(f"get_cell_at_pos error: {e}")
        return None

    def get_gap_at_pos(self, screen_x: int, screen_y: int) -> tuple:
        """根据屏幕坐标获取缝隙位置"""
        try:
            world_x, world_y = self.screen_to_world(screen_x, screen_y)

            if getattr(self, 'triangle_mode', False):
                cells = self.game.positions()
                for gap_type, line in self._tri_view().candidate_gaps(
                        world_x, world_y, cells):
                    if self.game.is_valid_gap(gap_type, line):
                        return (gap_type, line)
                return None

            bounds = self.game.get_boundaries()
            for kind, idx in self.board_view.candidate_gaps(world_x, world_y, bounds):
                if kind == 'h' and self.game.is_valid_h_line(idx):
                    return ('h', idx)
                if kind == 'v' and self.game.is_valid_v_line(idx):
                    return ('v', idx)
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

    def _detach_readonly_save(self) -> bool:
        """脱离只读存档：清只读标记 + 解除文件绑定。返回是否真的脱离了。

        只读保护的是「那份存档的棋盘内容」，而切换谜题换的是另一张棋盘；
        因此允许切换，但必须脱钩：新谜题不该继承只读（否则不能滑动），
        current_file_path 也不能继续指向受保护档案（否则 Ctrl+S 会覆写它）。
        脱离后标题回到「未存檔」，要保存请另存为。
        """
        if not getattr(self, '_readonly', False):
            return False
        self._readonly = False
        self.current_file_path = None
        return True

    def _update_window_title(self):
        """按存档路径/已修改/未存档 刷新窗口标题（只有标题变化时才调用 set_caption）"""
        if getattr(self, 'tutorial_active', False):
            if getattr(self, 'tut_selecting_levels', False) or self.tut_level == 0:
                new_title = '貓九的滑块游戏 — 教程·选择关卡'
            else:
                new_title = f'貓九的滑块游戏 — 教程·第 {self.tut_level} 关'
        elif self.current_file_path:
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

    def _maybe_show_solved_popup(self, via_redo: bool = False, suppress: bool = False):
        """状态提交后调用：刚达成复原（未复原→复原）且非重做触发时，弹出复原成功悬浮窗。

        via_redo=True  表示最后一步由重做实现（需求：此时不提示）。
        suppress=True  表示由撤销实现——撤销回到已达成过的复原状态，不再重复提示。
        每次调用都会同步 _prev_solved，保证「复原→离开→再复原」可再次弹出，且不会重复弹。
        """
        solved = self.is_solved()
        became_solved = solved and not getattr(self, '_prev_solved', False)
        self._prev_solved = solved
        # 教程解法播放中：不弹复原悬浮窗（播完会撤回初始态，强制玩家手动还原）
        if became_solved and not via_redo and not suppress and not self._tut_board_locked():
            self._solved_popup_active = True
            self._solved_popup_t = 0
        # 新手教程：状态提交后推进教学进度（移动/撤销/重做/过关）
        self._tut_on_state_commit(via_redo=via_redo, suppress=suppress)

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
            self.macro_notify_msg = "创造模式：请用[随机生成]或[手动构造]造题"
            self.macro_notify_timer = 90
            return False
        # 标注模式的手动构造视图：主棋盘是编辑画布，禁止滑动
        if self.annotation_mode and self._ann_view == 'build':
            self.macro_notify_msg = "构造中：点格增删滑块，按[应用并开始]完成"
            self.macro_notify_timer = 90
            return False
        # 计时模式：就绪态（已打乱未开始）禁止滑动，保证公平
        if self.game_mode == 'timed' and self.timer_state == 'ready':
            self.macro_notify_msg = "计时模式：按空格开始计时后才能滑动"
            self.macro_notify_timer = 90
            return False

        if getattr(self, 'triangle_mode', False):
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
        move_info = {
            'gap_type': self.selected_gap[0] if self.selected_gap else None,
            'gap_line': self.selected_gap[1] if self.selected_gap else None,
            'direction': direction,
            'step': move_step,
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
            self.ensure_blocks_visible()
            # 操作提示先于过关判定：过关/教程播报优先级更高，不应被“向X移动”覆盖
            self.macro_notify_msg = f"向{self._dir_name(direction)}移动 {move_step}步"
            self.macro_notify_timer = 120
            self._maybe_show_solved_popup()
            self._mark_file_dirty()
        return True

    @staticmethod
    def _dir_name(direction: str) -> str:
        """方向字母 → 中文方向名（方形四向 + 三角六向）。"""
        names = {
            'w': '上', 's': '下', 'a': '左', 'd': '右',
            'e': '右上', 'z': '左下', 'x': '右下',
        }
        return names.get(direction, direction)

    @staticmethod
    def _gap_type_name(gap_type: str) -> str:
        """缝隙族 → 中文名（方形 h/v，三角 h/p/n）。"""
        names = {'h': '横向', 'v': '纵向', 'p': '斜向', 'n': '反向斜'}
        return names.get(gap_type, gap_type)

    # 三角六向键位 → 晶格方向字母（与 game_triangle.DIRECTIONS 一致；
    # 注意 's' 不是三角方向，故不映射 move_down）
    TRI_MOVE_KEYS = {
        'move_up': 'w', 'tri_up_right': 'e', 'move_left': 'a',
        'move_right': 'd', 'tri_down_left': 'z', 'tri_down_right': 'x',
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

    def _bump_move_session(self):
        """结束当前「选中会话」：之后的移动不再并入同一快照。

        在选中变化（点缝隙/点方块/右键取消）与撤销/重做/跳步时调用。
        """
        self._move_session_id = getattr(self, '_move_session_id', 0) + 1

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
            return False
        # 宏执行中不允许
        if getattr(self, 'macro_executing', False):
            return False
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
        direction = self.drag_follow_direction

        # 偏移已在跟随期间夹紧到 [0, drag_follow_max_cells]，此处直接取用（单一数据源）
        # max(0.0, ...) 为防御：负偏移（反向拖过起点）一律视为不移动，绝不产生反向位移
        dr, dc = self.drag_follow_offset
        # 取 max 而非 abs 之和：方形四向必然只有一個分量非零（兩者等價），
        # 而三角六向中有對角方向（如 w=(-1,+1)），沿該方向走 t 格時兩個分量
        # 都等於 t，只有 max 能正確還原步數
        cells = max(0.0, abs(dr), abs(dc))
        # 取整用 int(x + 0.5)（等价 floor），规避 round() 的银行家舍入；再量化到 current_step 整数倍
        step_size = max(1, self.current_step)
        step = int(cells / step_size + 0.5) * step_size

        # 循环递减：从最大合法步长开始，逐次减少 step_size，找到第一个可接受的值（兜底）
        moved = False
        while step > 0:
            moved = self.move_selected_blocks(direction, step)
            if moved:
                break
            step -= step_size

        # 清除跟随状态（含 single-touch auto-deselect）
        self.clear_drag_follow()

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
        return getattr(self, '_move_session_id', 0)

    def _drag_slide(self, block, dx, dy):
        """拖拽滑动：根据拖拽位移，自动确定缝隙/方向并执行一次滑动。

        - 已有选中缝隙（two_touch 模式）：沿用缝隙，按主方向轴滑动；
        - 无选中缝隙（single_touch 模式）：按 8 区角度判定缝隙（对齐 web touch-gesture.md）。
        - 单次触控会在滑动后清空选中。
        返回是否真正移动。
        """
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

    def undo(self):
        """撤销操作（Ctrl+Z）"""
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 手动撤销会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 撤销会改变选中 → 结束当前选中会话（后续移动另起快照）
        self._bump_move_session()
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

        # 获取将被撤销那一步的移动元数据（合并段会先惰性展开成单步）
        move_info = self.game_history.peek_undo() if self.game_history.can_undo() else None

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
            # 合并快照可能覆盖多步：步数直接取目标快照的累计值
            self.step_count = self.game_history.current_step_total()
            self.ensure_blocks_visible()
            self._flash_move_selection(move_info, True, after_commit=True)
            self.macro_notify_msg = "撤销"
            self.macro_notify_timer = 15
            self._maybe_show_solved_popup(suppress=True)
            self._mark_file_dirty()
            # 连续撤销（无动画路径）：继续下一轮直到边界
            self._advance_continuous_undo_redo()

    def redo(self):
        """重做操作（Ctrl+X）"""
        # 教程解法播放中：锁定棋盘操作（回放自身的连续重做除外）
        if self._tut_board_locked() and not self._continuous_redo:
            return
        # 手动重做会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 重做会改变选中 → 结束当前选中会话（后续移动另起快照）
        self._bump_move_session()
        # 如果正在播放撤销/重做动画，入队等待
        if self.animating and self._undo_redo_type is not None:
            self._animation_queue.append('redo')
            return

        # 如果正在播放普通移动动画，取消后执行重做
        if self.animating:
            self.cancel_animation()

        # 获取将被重做那一步的移动元数据（目标段会先惰性展开成单步）
        move_info = self.game_history.peek_redo() if self.game_history.can_redo() else None

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
            self.step_count = self.game_history.current_step_total()
            self.ensure_blocks_visible()
            self._flash_move_selection(move_info, False, after_commit=True)
            self.macro_notify_msg = "重做"
            self.macro_notify_timer = 15
            self._maybe_show_solved_popup(via_redo=True)
            self._mark_file_dirty()
            # 连续重做（无动画路径）：继续下一轮直到边界
            self._advance_continuous_undo_redo()

    def jump_to_history_index(self, idx: int):
        """直接跳到历史记录第 idx 步的状态（虚拟键盘“跳到某步”）"""
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 手动跳步 = 打断连续撤销/重做
        self._stop_continuous_undo_redo()
        # 跳步会改变选中 → 结束当前选中会话（后续移动另起快照）
        self._bump_move_session()
        # 标注录制中跳转会破坏标注基准 → 阻止
        if getattr(self, '_ann_recording', False):
            self.macro_notify_msg = "标注录制中不可跳转步骤"
            self.macro_notify_timer = 90
            return
        n = len(self.game_history.history)
        if n == 0:
            return
        idx = max(0, min(idx, n - 1))
        # 终止进行中的动画
        if self.animating:
            self.cancel_animation()
        # 清空选择等临时状态
        self.selected_gap = None
        self.selected_block = None
        self.game_history.history_index = idx
        self.game_history.restore_snapshot(self.game, idx)
        # 合并快照可能覆盖多步：步数取该快照的累计值
        self.step_count = self.game_history.step_total_at(idx)
        self.ensure_blocks_visible()
        self._mark_file_dirty()

    # ==================== 连续撤销/重做（虚拟键盘一键连续播放） ====================

    def _toggle_continuous(self, mode: str):
        """点击虚拟键盘【撤销/重做】：进入或退出连续播放。

        mode='undo'/'redo'。再次点击同按钮 = 停止；点击另一按钮 = 切换方向。
        进入时立刻播放第一步；连续播放由每次动画提交后自动推进（见 _advance_continuous_undo_redo）。
        """
        if mode == 'undo':
            # 切换到撤销方向
            if self._continuous_redo:
                self._continuous_redo = False
            if self._continuous_undo:
                self._stop_continuous_undo_redo("已停止连续撤销")
                return
            self._continuous_undo = True
            self._finalize_continuous_enter('undo', "连续撤销（按空格停止）")
        else:  # redo
            if self._continuous_undo:
                self._continuous_undo = False
            if self._continuous_redo:
                self._stop_continuous_undo_redo("已停止连续重做")
                return
            self._continuous_redo = True
            self._finalize_continuous_enter('redo', "连续重做（按空格停止）")

    def _finalize_continuous_enter(self, mode, notify):
        """连续播放：清掉先前残留队列后开始第一步。"""
        # 清理可能残留的同向队列项（切换方向/重进时确保干净）
        self._animation_queue = [q for q in self._animation_queue
                                 if q != ('undo' if mode == 'undo' else 'redo')]
        self._macro_notify(notify)
        if mode == 'undo':
            self.undo()
        else:
            self.redo()

    def _advance_continuous_undo_redo(self):
        """连续播放推进：在每次撤销/重做提交后，若仍在连续模式且可继续，则播放下一步；
        到达边界（无路可退/进）则停止并提示。手动打断时由 _stop_continuous_undo_redo 处理。"""
        if self._continuous_undo:
            if self.game_history.can_undo():
                self.undo()
            else:
                self._stop_continuous_undo_redo("已撤销到第一步")
        elif self._continuous_redo:
            if self.game_history.can_redo():
                self.redo()
            else:
                self._stop_continuous_undo_redo("已重做到最后一步")

    def _stop_continuous_undo_redo(self, notify=''):
        """停止连续撤销/重做；清除状态旗标与残留队列。notify 非空时右下角提示。"""
        was = self._continuous_undo or self._continuous_redo
        self._continuous_undo = False
        self._continuous_redo = False
        self._animation_queue.clear()
        if notify:
            self._macro_notify(notify)
        return was

    def _macro_notify(self, msg):
        self.macro_notify_msg = msg
        self.macro_notify_timer = 90

    def _space_interrupts_continuous(self) -> bool:
        """空格打斷：仅在连续播放进行中拦截空格，返回 True 表示本次空格已被消费。"""
        if self._continuous_undo or self._continuous_redo:
            self._stop_continuous_undo_redo("已停止连续播放")
            return True
        return False

    def shuffle_puzzle(self):
        """打乱谜题 - 调用 game.py 的 shuffle 核心逻辑"""
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 打乱会改变棋盘 → 终止梯度流水线
        self._stop_gradient_pipeline()
        # 打乱会改变棋盘 → 打断连续撤销/重做
        self._stop_continuous_undo_redo()
        # 新谜题开始 → 清掉上一次的计时成绩（悬浮窗不再显示）
        self._last_timed_result = None
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

        # 调用 game.py 的 shuffle 方法，传入偏置强度和难度门槛
        self.game.shuffle(
            attempts, self.current_step,
            bias=self.shuffle_bias,
            min_score=self.shuffle_min_score
        )

        # 清除选中状态
        self.selected_gap = None
        self.selected_block = None

        # 步数归零，重置历史记录（以打乱态为第一条）
        self.step_count = 0
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        if getattr(self, 'triangle_mode', False):
            # 三角形的缩放本就是自动适配的（建局/载入都走 _fit_triangle_zoom），
            # 而打乱会把形状摊得比初始大三角更开，原 zoom 可能被 max_zoom 夹过、
            # 单靠平移拉不回视口 → 按打乱后的包围盒重新适配并居中
            self.zoom = self._fit_triangle_zoom()
            self.center_map()
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
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 只读存档：禁止重置 —— 重置是丢弃当前局面、重新生成同一题，
        # 属于改动这份存档的棋盘内容（与「切换谜题」换另一张棋盘不同）
        if self._readonly_blocked():
            return
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法重置"
            self.macro_notify_timer = 90
            return
        self._timer_cancel()
        if getattr(self, 'triangle_mode', False):
            self.new_triangle_puzzle(self.triangle_side, self.current_step)
        else:
            self.new_puzzle(self.current_m, self.current_n, self.current_step)

    # ==================== 计时器 ====================

    def _current_kind(self) -> str:
        """当前谜题形态键（puzzle_key / 成绩分榜共用）。"""
        if getattr(self, 'triangle_mode', False):
            return 'triangle'
        if getattr(self, 'numbered', False):
            return 'numbered'
        return 'square'

    def _current_puzzle_key(self) -> str:
        """当前谜题完整标识：方形 2~4*4 / 带序号 2~4*4#num / 三角 2~tri6。"""
        tri = getattr(self, 'triangle_mode', False)
        return puzzle_key(
            self.current_step, self.current_m, self.current_n,
            kind=self._current_kind(),
            triangle_side=self.game.k if tri else None)

    def _preset_puzzle_key(self, preset) -> str:
        """谜题菜单预设项对应的分榜键（与 _current_puzzle_key 同格式，用于比对当前项）。

        原先「当前是哪一档」是逐项比 m/n/step，三角形还漏比了边长；改成比键之后，
        同一预设不可能即命中方格又命中数字，新增形态也不必再写分支。
        """
        if len(preset) < 4:
            return ''
        _, pm, pn, ps = preset[:4]
        kind = preset[4] if len(preset) > 4 else 'square'
        return puzzle_key(ps, pm, pn, kind=kind,
                          triangle_side=pm if kind == 'triangle' else None)

    def _current_puzzle_label(self) -> str:
        """当前谜题的人话描述（谜题菜单底部状态行用）。"""
        if getattr(self, 'triangle_mode', False):
            k = getattr(self.game, 'k', self.current_m)
            return f'三角形 边长{k} 等级{self.current_step}'
        name = '数字' if getattr(self, 'numbered', False) else '矩形'
        return f'{name} {self.current_m}×{self.current_n} 等级{self.current_step}'

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
        tri = getattr(self, 'triangle_mode', False)
        self.timer_puzzle_key = puzzle_key(
            self.current_step, self.current_m, self.current_n,
            kind=self._current_kind(),
            triangle_side=self.game.k if tri else None)
        self.timer_initial_matrix = self._timer_initial_map()

    def _timer_initial_map(self) -> str:
        """竞速初始局面的存档串。

        方形/序号转成 0/1（成绩面板按 █/· 渲染、可转回 #/_ 地图）；
        三角形保留 #^v_ 原生编码——菱形胞 2-bit 信息量比 0/1 大，
        且 import_map 能直接吃回，载入练习/另存为谜题都不用改编码。
        """
        if getattr(self, 'triangle_mode', False):
            return self.game.export_map()
        return self.game.export_map().replace('#', '1').replace('_', '0')

    def _timer_cancel(self):
        """取消当前计时会话（回到空闲态）"""
        self.timer_state = 'idle'
        self.timer_elapsed = 0.0

    def _mode_name(self) -> str:
        """当前模式的中文名（练习 / 竞速 / 创造）。"""
        return {'timed': '竞速', 'create': '创造'}.get(self.game_mode, '练习')

    def set_game_mode(self, mode: str) -> bool:
        """设置模式：'practice' 练习 / 'timed' 竞速 / 'create' 创造（幂等）。

        返回是否成功（计时进行中拒绝切换）。
        """
        if mode not in ('practice', 'timed', 'create'):
            return False
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换模式"
            self.macro_notify_timer = 90
            return False
        if mode == self.game_mode:
            return True
        # 离开创造模式：收掉创造界面
        if self.create_mode:
            self._ann_leave_to_home()
        if mode == 'create':
            # 创造模式与标注模式/计时互斥
            self.annotation_mode = False
            self._ann_leave_to_home()
        self._timer_cancel()
        self.game_mode = mode
        if mode == 'timed':
            self.macro_notify_msg = "竞速模式：打乱后需按空格开始计时"
        elif mode == 'create':
            self.macro_notify_msg = "创造模式：随机挖洞/缺口 或 手动构造，造好即成为当前谜题"
        else:
            self.macro_notify_msg = "练习模式：可自由滑动，不计时"
        self.macro_notify_timer = 120
        return True

    def toggle_game_mode(self):
        """循环切换 练习 → 竞速 → 创造 → 练习（「模式」开关 / 谜题菜单入口）"""
        order = ('practice', 'timed', 'create')
        try:
            idx = order.index(self.game_mode)
        except ValueError:
            idx = 0
        self.set_game_mode(order[(idx + 1) % len(order)])

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

        # 记录成绩前先取旧统计，用于“新最佳”判定
        key = self.timer_puzzle_key
        old = self.records.stats(key)
        old_series = self.records.series(key)
        old_ao5 = self._series_best_ao(old_series, 5)
        old_ao12 = self._series_best_ao(old_series, 12)

        self.records.add_record(
            self.timer_puzzle_key,
            self.timer_m, self.timer_n, self.timer_step,
            self.timer_initial_matrix,
            elapsed_ms,
            self.step_count,
            dnf,
            numbered=getattr(self, 'numbered', False),
        )
        self.timer_state = 'dnf' if dnf else 'stopped'

        # 计算本次成绩 / TPS / 最佳判定，供复原成功悬浮窗显示
        if dnf:
            self._last_timed_result = {
                'time_ms': int(round(elapsed_ms)), 'moves': self.step_count,
                'tps': 0.0, 'pb_single': False, 'pb_ao5': False, 'pb_ao12': False,
                'dnf': True,
            }
        else:
            tps = self.step_count / (elapsed_ms / 1000.0) if elapsed_ms > 0 else 0.0
            new_series = self.records.series(key)
            new_ao5 = self._series_best_ao(new_series, 5)
            new_ao12 = self._series_best_ao(new_series, 12)
            # 单次最佳：严格小于旧 best（旧记录中不存在该用时就算新最佳）
            is_pb_single = (old['best'] is None or elapsed_ms < old['best'])
            self._last_timed_result = {
                'time_ms': int(round(elapsed_ms)), 'moves': self.step_count,
                'tps': tps,
                'pb_single': is_pb_single,
                'pb_ao5': new_ao5 is not None and (old_ao5 is None or new_ao5 < old_ao5),
                'pb_ao12': new_ao12 is not None and (old_ao12 is None or new_ao12 < old_ao12),
                'dnf': False,
            }

        st = self.records.stats(self.timer_puzzle_key)

        def _fmt(v):
            if v is None:
                return '-'
            if v == 'DNF':
                return 'DNF'
            return format_time(v)

        cur2 = format_time(elapsed_ms)
        best = _fmt(st['best'])
        ao5 = _fmt(st['ao5'])
        if dnf:
            self.macro_notify_msg = f"DNF（{cur2}） | 最好 {best} | Ao5 {ao5}"
        else:
            self.macro_notify_msg = f"复原！{cur2}（{self.step_count}步） | 最好 {best} | Ao5 {ao5}"
        self.macro_notify_timer = 180

    @staticmethod
    def _series_best_ao(series, n):
        """取 series 中所有可计算 AoN 的最小值；不足 n 次或无有效值返回 None。"""
        best = None
        for _rec, ao, _a12 in series:
            if n == 12:
                ao = _a12
            if ao is not None and ao != 'DNF':
                if best is None or ao < best:
                    best = ao
        return best

    def _timer_blocked(self):
        """竞速模式下宏与求解器一律禁止（练习模式不禁）"""
        return self.game_mode == 'timed'

    def _timer_status_text(self):
        """返回状态栏要显示的计时器文本（练习/竞速/创造始终显示当前状态）"""
        if self.game_mode == 'practice':
            return "练习模式"
        if self.game_mode == 'create':
            return "创造模式"
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

        # 三角形密铺：求解器需要新的动作语义（三族缝隙 + 六向），B2 不开放
        if self._triangle_blocked('自动求解'):
            return

        # 计时中禁止使用求解器
        if self._timer_blocked():
            self.macro_notify_msg = "计时中无法使用求解器"
            self.macro_notify_timer = 90
            return

        # 只读存档：禁止自动求解
        if self._readonly_blocked():
            return

        # 带序号模式：求解器暂不支援（需额外处理编号顺序）
        if getattr(self, 'numbered', False):
            self.macro_notify_msg = "带序号模式暂不支援自动求解"
            self.macro_notify_timer = 90
            return

        # 三角形密铺：动作语义不同（6 向/3 族缝隙），求解器在 D 阶段再评估
        if getattr(self, 'triangle_mode', False):
            self.macro_notify_msg = "三角形密铺暂不支援自动求解"
            self.macro_notify_timer = 90
            return

        # 标注录制中：自动回放不是人类示范，禁用
        if getattr(self, '_ann_recording', False):
            self.macro_notify_msg = "标注录制中无法使用自动求解"
            self.macro_notify_timer = 90
            return

        # 如果正在求解，則取消
        if self._auto_solve_running:
            self._auto_solve_cancel = True
            # API 状态锁存：记录取消时刻（/solver/status 判定 cancelled，elapsed 冻结）
            self._api_solve_latch = {
                'ok': False, 'steps': 0, 'reason': 'cancelled',
                'elapsed_ms': int((time.time() - self._auto_solve_start_time) * 1000)
                if getattr(self, '_auto_solve_start_time', 0) else None,
            }
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
                self._api_solve_latch = {
                    'ok': False, 'steps': 0, 'reason': 'cancelled',
                    'elapsed_ms': int((time.time() - self._auto_solve_start_time) * 1000)
                    if getattr(self, '_auto_solve_start_time', 0) else None,
                }
                self.macro_notify_msg = "梯度聚拢已停止"
                self.macro_notify_timer = 90
            return

        self._auto_solve_result = None
        self._auto_solve_done = False
        self._auto_solve_running = True
        self._auto_solve_cancel = False
        self._auto_solve_start_time = time.time()
        self._auto_solve_progress = None
        # API 状态锁存：新一次求解开始时清空（供 HTTP /solver/status 结构化查询）
        self._api_solve_latch = None

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

        # API 状态锁存：记录本次求解产物（供 HTTP /solver/status；梯度各阶段由
        # _handle_gather_result 覆盖更新，取消时无产物，状态判定由 cancel 标志负责）
        import time as _time
        _latch_elapsed = int((_time.time() - self._auto_solve_start_time) * 1000) \
            if getattr(self, '_auto_solve_start_time', 0) else None
        if isinstance(result, dict):
            self._api_solve_latch = {
                'ok': bool(result.get('solved', False)),
                'steps': len(result.get('actions', []) or []),
                'reason': result.get('reason', ''),
                'elapsed_ms': _latch_elapsed,
            }
        elif result is False:
            self._api_solve_latch = {'ok': False, 'steps': 0,
                                     'reason': 'no_solution', 'elapsed_ms': _latch_elapsed}
        elif result is None:
            self._api_solve_latch = {'ok': False, 'steps': 0,
                                     'reason': 'no_database', 'elapsed_ms': _latch_elapsed}
        else:
            acts = result[0] if isinstance(result, tuple) else result
            self._api_solve_latch = {
                'ok': True, 'steps': len(acts),
                'reason': 'already_solved' if len(acts) == 0 else 'solved',
                'elapsed_ms': _latch_elapsed,
            }

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
        # API 状态锁存（梯度逐阶段覆盖，终态以最后阶段为准）
        import time as _time
        _elapsed = int((_time.time() - self._auto_solve_start_time) * 1000) \
            if getattr(self, '_auto_solve_start_time', 0) else None
        self._api_solve_latch = {
            'ok': bool(solved), 'steps': len(actions), 'reason': reason or 'gather',
            'elapsed_ms': _elapsed,
        }
        # 记录梯度当前阶段（供 /solver/status 的 gradient.stage/total）
        gs = getattr(self, '_gradient_state', None)
        if isinstance(gs, dict):
            if result.get('gradient_stage') is not None:
                gs['stage'] = result['gradient_stage']
            if result.get('gradient_total'):
                gs['max_stages'] = result['gradient_total']

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
                # 新手教程：引导面板 / 首次启动弹窗（最顶层）
                self.draw_tutorial_prompt()
                self.draw_tutorial_panel()

                # 左键单击反馈（盖在所有界面之上，含模态对话框）
                self.draw_click_feedback()

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
                # 非致命：记录到 error_log.txt 并继续运行，避免单帧小异常导致游戏闪退
                _gui_log_error(f'主循环异常: {traceback.format_exc()}')
                print(f"Run error (non-fatal): {e}")
                self._frame_error_streak = getattr(self, '_frame_error_streak', 0) + 1
                # 连续异常约 2 秒（120 帧）仍无法恢复则终止，避免卡死刷屏
                if self._frame_error_streak >= 120:
                    self.running = False
            else:
                self._frame_error_streak = 0

        # 退出前保存配置与成绩（成绩内存中维护，此时统一落盘）
        self.records.save()
        self.save_config()
        pygame.quit()
        sys.exit()
