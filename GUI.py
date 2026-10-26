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
import math
import secrets
import threading
from game import SliderMatrix, Block
from history import GameHistory
from records import Records, format_time
from puzzle_types import create_puzzle, puzzle_key
from game_triangle import tri_key
from game_mi import mi_key, DIRECTIONS as MI_DIRECTIONS
from gui.renderer import RendererMixin
from gui.dialogs import DialogsMixin
from gui.animation import AnimationMixin
from gui.file_ops import FileOpsMixin, DEFAULT_KEYBINDINGS
from gui.events import EventsMixin
from gui import op_log
from gui.virtual_keyboard import VirtualKeyboardMixin
from gui.metrics_panel import MetricsPanelMixin
from gui.records_panel import RecordsPanelMixin
from gui.annotation import AnnotationMixin
from gui.model_editor import ModelEditorMixin
from gui.tutorial import TutorialMixin
from gui.palette import PaletteMixin
from gui.board_view import SquareBoardView
from gui.text_input import TextInput
from gui.scrollbar import Scrollbar
from gui import log_writer
from gui.log_writer import _gui_log_error
from gui.update import UpdateMixin
from gui.history import HistoryMixin
from gui.speedrun import SpeedrunMixin
from gui.external import ExternalMixin
from gui.session import SessionMixin
from gui.pick_fill import PickFillMixin
from gui.auto_solve import AutoSolveMixin
from gui.move import MoveMixin
from gui.drag import DragMixin


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
            f = pygame.font.Font(filepath, size)
            if bold:
                try:
                    f.set_bold(True)
                except Exception:
                    pass
            return f
        except Exception:
            pass
    # 其次尝试 SysFont（可能触发 pygame 注册表扫描 bug）
    try:
        return pygame.font.SysFont(name, size, bold=bold)
    except Exception:
        _gui_log_error(f'字体加载失败: {name} {size}, 回退到默认字体', level='warn')
        return pygame.font.Font(None, size)


def _gui_get_resource_path(relative_path):
    """获取资源文件路径（兼容 PyInstaller 打包和开发模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


class SliderGUI(RendererMixin, DialogsMixin, AnimationMixin, FileOpsMixin, EventsMixin, VirtualKeyboardMixin, MetricsPanelMixin, RecordsPanelMixin, AnnotationMixin, ModelEditorMixin, TutorialMixin, PaletteMixin, UpdateMixin, HistoryMixin, SpeedrunMixin, ExternalMixin, SessionMixin, PickFillMixin, AutoSolveMixin, MoveMixin, DragMixin):
    """
    滑块游戏图形界面类
    """

    def __init__(self, m: int = 6, n: int = 6, step: int = 1, cmd_queue: queue.Queue = None,
                 kind: str = 'square', ext_state: dict = None):
        """
        初始化游戏界面

        参数：
            m: 初始滑块行数，默认为6
            n: 初始滑块列数，默认为6
            step: 移动步数（等级），默认为1
            cmd_queue: 命令队列（用于接收终端指令），默认为None
            kind: 开局形态 'square' / 'numbered' / 'triangle' / 'mi'
                （三角形时 m 作边长 k；米字格 m/n 为行数/列数）
            ext_state: 外部控制共享状态 {'enabled': bool, 'token': str|None}
                （与 HTTP 服务器同一个 dict；None 时自建，默认开启+新令牌，
                 方便直接运行 GUI / 测试）
        """
        _gui_log_error(f'GUI初始化开始: m={m}, n={n}, step={step}', level='info')
        # 中文输入法（IME）：SDL/pygame 默认不显示输入法候选框界面，导致 Windows
        # 上中文输入法无法弹出候选框、无法键入汉字。必须显式开启，且须在
        # pygame.init()（视频子系统初始化）之前设置，否则无效。
        os.environ['SDL_IME_SHOW_UI'] = '1'

        # 外部控制共享状态（与 HTTP 服务器同一个 dict 对象）：
        #   {'enabled': bool, 'token': str|None, 'port': int}
        # 默认开启 + 进程级随机令牌；HTTP 请求必须带令牌。开关关闭时清空
        # 令牌（重开必换新，关闭期间复制出去的话术随之作废）。
        # main.py 会传入共享对象；直接运行 GUI / 测试时在此自建。
        self.ext_state = ext_state if ext_state is not None else {
            'enabled': True, 'token': secrets.token_urlsafe(24), 'port': 5050}

        try:
            pygame.init()
        except Exception:
            log_writer.exception('pygame.init() 失败', *sys.exc_info())
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

        # 游戏逻辑对象（带 kind；命令行走位若参数非法，会在下方显式报错而非静默方形）
        self.game = create_puzzle(m, n, step, kind=kind)

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
        # 「搜索」位于「设置」与「帮助」之间：功能可发现性的鼠标直达入口
        # （与「帮助」同属「找不到功能时先来这里」一族）。
        self.menu_items = ['文件', '编辑', '谜题', '宏定义', '设置', '搜索', '帮助', '教程', '官网']
        self.menu_hovered = -1
        self.menu_item_rects = []

        # 帮助对话框状态
        self.show_help = False
        # 帮助检索（功能可发现性的主入口）：打开帮助时焦点默认落在检索框，
        # 输入即过滤；回车 = 直接到位。数据来自 gui/feature_index.py。
        self.help_query = ''
        # 帮助检索框复用 gui.text_input.TextInput 组件（与宏命名框、文件对话框
        # 文件名框同源）：光标/删除/左右移动/鼠标定位/IME 一并支持。
        self.help_input = TextInput('')
        self.help_sel = 0
        self.help_search_active = False
        self.help_search_rect = None
        # 帮助对话框滚动条：与设置框共用 gui.scrollbar.Scrollbar（同一套交互）。
        self.help_scrollbar = Scrollbar()
        self.help_result_rects = []

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

        # 增量更新器状态（仅冻结/安装版生效；开发版全程不激活）
        # 属性定义随方法搬至 gui/update.py 的 UpdateMixin._init_update_state
        self._init_update_state()

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
        # 末项必须是自动求解：主循环按 edit_menu_items[-1] 改写为「停止求解」
        # 注：下面这一列改动时，记得同步 events.py 里按**序号**分派的那一处
        # （它是硬编码索引，加/删一项就会点错）
        self.edit_menu_items = ['撤销 Ctrl+Z', '重做 Ctrl+X', '打乱 Alt+S',
                                '重置 Ctrl+R', '---', '自动求解 Ctrl+Alt+S']
        self.edit_menu_rects = []
        self.edit_menu_hovered = -1

        # 谜题菜单状态
        self.show_puzzle_menu = False
        self.puzzle_menu_rects = []
        self.puzzle_menu_hovered = -1
        # 谜题菜单一级结构：矩形是默认/基础（正阶魔方地位），异形收进二级子菜单。
        # 条目格式：
        #   ('快速开始…', m, n, step[, kind])  置顶快捷项，直接生效（推荐档：矩形 6×6 等级2）
        #   ('名字 ▸', '__sub__', subkey)     可展开的二级子菜单项
        #   ('---',) / ('自定义...',) / ('__current__',)  同旧语义
        # 「当前是哪一档」由 _preset_puzzle_key() 和 _current_puzzle_key() 比对，
        # 以后再加形态也不用改渲染分支。模式切换已移到主窗口右下角，故不再放这里。
        #
        # ⚠️ 这里**不写字面量**：菜单内容由 _refresh_puzzle_presets() 生成（模型
        # 文件、自定义预设都是运行期扫描出来的）。以前两边各写一份，字面量那份
        # 长期留着已废止的「高级选项...」，而测试断言它不存在 —— 白读一份错清单。
        self.puzzle_presets = []

        # 二级子菜单：条目与旧 puzzle_presets 同格式（分组标题/分隔线/谜题档位），
        # 渲染与「当前✓」比对逻辑完全复用。
        # 难度定位：矩形等级1 最低（无教程也能过）、等级2 最经典（教程教学目标）、
        # 等级3+ 复杂；异形难度升序：三角形 < 米字格（米字格奇偶等级难度有波动）。
        # 碎三角是几何引擎解释器路线的首个新板型（实验性，暂无难度定位），
        # 列在异形子菜单末尾。
        self.puzzle_sub_presets = {
            'rect': [
                ('__group__', '等级1 · 入门'),
                ('4×4 等级1', 4, 4, 1),
                ('5×5 等级1', 5, 5, 1),
                ('6×6 等级1', 6, 6, 1),
                ('__group__', '等级2 · 经典 ★ 推荐'),
                ('4×4 等级2', 4, 4, 2),
                ('5×5 等级2', 5, 5, 2),
                ('6×6 等级2', 6, 6, 2),
                ('8×8 等级2', 8, 8, 2),
                ('10×10 等级2', 10, 10, 2),
                ('__group__', '等级3 · 复杂'),
                ('6×6 等级3', 6, 6, 3),
                ('8×8 等级3', 8, 8, 3),
                ('10×10 等级3', 10, 10, 3),
            ],
            'exotic': [
                ('__group__', '三角形谜题（比矩形难）'),
                ('边长4 等级1', 4, 4, 1, 'triangle'),
                ('边长6 等级2', 6, 6, 2, 'triangle'),
                ('边长8 等级2', 8, 8, 2, 'triangle'),
                ('__group__', '米字格谜题（最难，奇偶等级难度有波动）'),
                ('4×4 等级1', 4, 4, 1, 'mi'),
                ('4×4 等级2', 4, 4, 2, 'mi'),
                ('6×6 等级2', 6, 6, 2, 'mi'),
                ('8×8 等级2', 8, 8, 2, 'mi'),
                ('__group__', '数字谜题（矩形+编号）'),
                ('4×4 等级2', 4, 4, 2, 'numbered'),
                ('6×6 等级2', 6, 6, 2, 'numbered'),
                ('8×8 等级2', 8, 8, 2, 'numbered'),
            ],
            # 模型文件板型：条目由 models/*.json 决定（_refresh_puzzle_presets
            # 每次重建菜单时填充），这里给个空壳，免得菜单渲染先于刷新报 KeyError。
            'models': [],
            # 自定义预设（config/design_styles/*.json）按「有没有粘连」拆成两个
            # 二级子菜单（用户 2026-10-27 定：和矩形/异形/模型并列，放在
            # 「自定义...」上方）。同样只留空壳，条目在刷新时扫目录填。
            'bundled': [],
            'custom': [],
        }

        # 谜题菜单二级交互状态：当前展开的 subkey、条目矩形、悬停项
        self.puzzle_sub_open = ''
        self.puzzle_sub_rects = []
        self.puzzle_sub_hovered = -1
        # 静态预设 + 动态并入的自定义预设（高级选项保存的样式）
        self._refresh_puzzle_presets()

        # 自动求解状态
        self._auto_solve_result = None     # None=空闲, list=解法, False=无解
        self._auto_solve_done = False     # 求解线程是否已完成
        self._auto_solve_running = False   # 是否正在后台求解
        self._auto_solve_start_time = 0    # 求解开始时间戳
        self._auto_solve_cancel = False    # 是否请求取消
        self._auto_solve_progress = None   # 求解进度信息 dict
        self._stream_queue = None          # 流式求解段队列（fill/gap 宏边算边播）
        self._stream_active = False        # 流式后台是否仍在计算
        self._stream_played = 0            # 流式已实时播放的步数
        # 自动规划·流式（2026-10-10 多段播放改造）：参照梯度流水线，hybrid 边算边播
        self._auto_stage_queue = None      # hybrid 分段队列（gen, stage_dict）
        self._auto_stage_gen = 0           # 失效旧段用
        self._auto_stage_active = False    # 后台是否仍在计算
        self._auto_streamed = False        # 本次是否为 hybrid 流式求解
        self._auto_best = None             # 历史最优 checkpoint {'score','phi','snap'}
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
        # 选块填空（求解器列表里唯一要先点选才能算的算法）：
        # None = 没在选取；否则是 {'block': 坐标|None, 'hole': 洞|None}，
        # 两项都齐了才开算。**顺序不限**——先点凸起还是先点空位都行。
        # 单独设这个状态而不是借用 selected_block：后者是两次触控流程的
        # 中间态，滑块一动就被清空，留不住玩家点选的目标。
        self._pick_fill = None
        # 复原提示标记（设置页名，2026-10-13 由「棋盘标记」改名）：调试
        # 面板画在棋盘上的那些记号（目标框、洞位等）。它们是「视觉强化」
        # 而非调试数据，所以要能脱离调试面板本体单独关——只关记号、留着
        # 面板看数字，或反过来。两者是独立的两个开关。
        # 默认关闭：与解耦前「面板默认关 → 棋盘上没有记号」的观感保持一致，
        # 免得一进游戏就满屏记号。F2 会连带把它打开（见 events 的 F2 分支）。
        self.board_marks_enabled = False
        # 箭头按键：选中缝隙后在切片两端画出的可点方向箭头。
        # 原本只跟着界面模式（enhanced）走、没有自己的开关，这里解耦出来，
        # 作为宣传中的五种操作方式之一独立可控。
        self.arrows_enabled = True
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
        # 操作日志开关（gui/op_log.py）：默认关，打开后每次点击都写
        # config/op_log.jsonl，只用于排障「点了没反应/提示不对」
        self.op_log_enabled = False
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
        self.custom_kind = 'rect'       # 'rect' 矩形 / 'triangle' 三角 / 'mi' 米字 / 'numbered' 数字

        # 通用确认弹窗（破坏性操作；目前只有谜题菜单的「删除预设」）
        # 见 gui/dialogs.py draw_confirm_dialog / handle_confirm_dialog_events
        self.show_confirm_dialog = False
        self.confirm_title = ''
        self.confirm_lines = []
        self.confirm_ok_text = '确定'
        self.confirm_danger = False
        self.confirm_action = None      # 无参可调用对象；确认后执行

        # 三角形密铺模式（Stage B）：self.game 为 TriangleSliderMatrix 时为 True
        self.triangle_mode = False
        self.triangle_side = 6

        # 米字格模式（Stage M）：self.game 为 MiSliderMatrix 时为 True。
        # 交互走两次触控：第一下选缝隙，第二下点滑块提交；方向由两下的
        # 方向不再由「两下落点差」猜，而是由第二下按住拖动时的位移向量
        # 在选中缝隙切向上的投影给出，故无需记录第一下落点作锚点
        self.mi_mode = False

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
        # GUI 模式总开关：plain=旧版朴素界面（等同未启用本计划的动效优化）；
        # enhanced=新版动效与视觉优化。各增强效果在 S1–S7 中按此开关分流。
        # 默认 enhanced（若用户想默认朴素，改此处的 'enhanced' 即可）。
        self.ui_mode = 'enhanced'
        # 拖拽接续：本次动画的起点偏移（跟随位移，格）与被缩短前的时长基准
        self._drag_anim_origin = None
        self._anim_duration_base = None

        # 移动元数据（从 move_selected_blocks 传递到 commit_animation）
        self._pending_move_info = None
        # 选中会话标识：同一次选中下连续移动并入同一快照（见 history.save_snapshot）
        self._move_session_id = 0

        # 撤销/重做动画状态
        self._undo_redo_type = None  # 当前动画类型：'undo'/'redo'/None
        self._animation_queue = []   # 待执行的撤销/重做队列，存储 'undo'/'redo'

        # 打乱演示动画（2026-10-18）：打乱后从打乱前状态按记录逐步重放，
        # 步数过多只演前 SHUFFLE_DEMO_STEPS 步，再淡出切入打乱终态
        self._shuffle_demo_active = False   # 演示进行中（含淡入淡出）
        self._shuffle_demo_playing = False  # 正在播某一条记录（动画系统驱动）
        self._shuffle_demo_queue = []       # 待播记录（见 game.record_shuffle_move）
        self._shuffle_demo_final = []       # 打乱终态（与 game.blocks 同序）
        self._shuffle_demo_need_fade = False  # 记录被截断：结尾需淡入终态
        self._shuffle_demo_phase = None     # 'play' / 'fade_out' / 'fade_in'
        self._shuffle_fade_alpha = 0.0      # 蒙层不透明度 0~255
        self._shuffle_fade_last_ms = 0      # 上一帧时刻（淡入淡出按时间推进）
        self._shuffle_demo_notify = None    # 演示结束后补发的通知 (msg, timer)
        self._shuffle_demo_game = None      # 演示绑定的棋局对象（换盘即失效）
        self._shuffle_demo_prev_duration = None  # 演示前玩家滑动步长（收尾恢复）
        self._shuffle_demo_progress = 0.0   # 「打乱中 xx%」进度 0~1（切屏瞬间=1）
        self._shuffle_demo_done = 0         # 已演步数
        self._shuffle_demo_total = 0        # 演示总步数
        self._shuffle_demo_fade_base = 0.0  # 淡出补足进度的起点

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

        # S1-3：越界松手的撞墙回弹。_shake_blocks 记录被选中切片；_shake_dr/_shake_dc
        # 为抖动轴方向（取松手偏移符号）；_shake_t 为剩余帧数（>0 时渲染层抖动+橙边）
        self._shake_blocks = set()
        self._shake_dr = 0
        self._shake_dc = 0
        self._shake_t = 0

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

        # 顶栏「搜索」：命令面板的鼠标直达入口，点击直接打开（不依赖 Ctrl+K）。
        # 早期这里曾是一个只有一项「命令面板」的下拉，纯属多余——单选项不需要
        # 下拉，故改为点击即开面板。Ctrl+K 仍是键盘首选。

        # 设置对话框状态
        self.show_settings_dialog = False
        self.settings_active_tab = 'keybindings'  # 'keybindings' or 'animation'
        self.settings_editing_action = None  # 当前正在编辑快捷键的动作名
        self.settings_editing_key = None  # 临时存储正在录制的按键
        self._settings_slider_dragging = False
        self._settings_zoom_dragging = False   # 视觉页缩放滑条拖拽中
        self._settings_backup_keybindings = {}
        self._settings_ok_btn = None
        self._settings_cancel_btn = None
        self._settings_reset_btn = None
        # 设置对话框滚动条：与帮助框共用 gui.scrollbar.Scrollbar（同一套交互）。
        self.settings_scrollbar = Scrollbar()
        self._settings_key_rects = {}
        self._settings_tab_kb_rect = None
        self._settings_tab_anim_rect = None
        self._settings_anim_toggle_rect = None
        self._settings_slider_track_rect = None

        # 快捷键配置：直接取 file_ops 的默认表（加载失败或文件缺失时的兜底），
        # 不在这里另抄一份——两份表一旦漂移，新动作就会在加载时被静默丢掉
        self.keybindings = dict(DEFAULT_KEYBINDINGS)

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
        # 重新分组：原「游戏操作」10 项混了移动/三角移动/面板，拆成「移动方块」
        # 与「显示面板」；原两个单元素分组「求解器」「宏操作」合并为「求解与宏」。
        self.keybinding_groups = [
            ('文件', ['save', 'load']),
            ('编辑', ['undo', 'redo', 'shuffle', 'reset']),
            ('求解与宏', ['auto_solve', 'macro_record']),
            ('移动方块', ['move_up', 'move_down', 'move_left', 'move_right',
                          'tri_up_right', 'tri_down_left', 'tri_down_right']),
            ('显示面板', ['virtual_keyboard', 'metrics_panel', 'records_panel']),
            # 命令面板单独一组：它不属于任何一块，是「找功能」的入口
            ('搜索', ['command_palette']),
        ]

        # 虚拟键盘状态
        self._vk_init_state()

        # 聚拢度指标面板状态
        self._mp_init_state()

        # 成绩记录面板状态
        self._rp_init_state()

        # 标注模式状态
        self._ann_init_state()

        # 搭积木编辑器状态（gui/model_editor.py；会话期外全部为空）
        self._med_init_state()

        # 教程模式状态
        self._tut_init_state()

        # 命令面板状态（Ctrl+K，功能可发现性主入口，见 gui/palette.py）
        self._pal_init_state()

        # 加载上次状态
        self.load_last_state()

        # 操作日志开关：config.json 的恢复在 load_last_state 里，这里才生效
        op_log.set_enabled(getattr(self, 'op_log_enabled', False))

        # 命令行显式指定形态：以命令行为准，覆盖上面恢复的上次局面
        # （kind='square' 是默认值，不覆盖，保持「记住上次关闭时的样子」）
        if kind == 'triangle':
            if not self.new_triangle_puzzle(m, step):
                raise ValueError(f"无效的三角形参数：k={m}, step={step}"
                                 f"（需 k≥3 且 step≤k−2，否则一步都动不了）")
        elif kind == 'mi':
            if not self.new_mi_puzzle(m, n, step):
                raise ValueError(f"无效的米字格参数：m={m}, n={n}, step={step}（需 m,n≥2 且 step<max）")
        elif kind == 'numbered':
            if not self.new_puzzle(m, n, step, numbered=True):
                raise ValueError(f"无效的谜题参数：m={m}, n={n}, step={step}（需 step<max）")
        elif kind not in ('square', 'triangle', 'mi', 'numbered'):
            # 模型文件板型（任意 models/<name>.json）：m/n 被忽略，只认 step
            # （与菜单条目同口径）
            if not self.new_model_puzzle(kind, step):
                raise ValueError(f"无效的模型板型参数：kind={kind}, step={step}")

        # 一轮调试的起点标记（日志开着才有这一行，否则什么都不会写）
        op_log.log('session_start', form=type(self.game).__name__,
                   zoom=round(getattr(self, 'zoom', 1.0), 3))

        # 首次启动：弹出新手教程引导
        self._tut_check_first_launch()

    def _refresh_puzzle_presets(self, keep_sub: bool = False):
        """重建谜题菜单：静态开局项 + 自定义预设（还原态样式，见 design_styles）。

        2026-10-25 前还有「高级选项...」（新建还原态样式）与「＋ 搭建新
        模型...」（新建模型文件）两个新建入口，现统一为「模式开关 → 创造 →
        ② 还原状态设计」，本菜单只留**开局**入口。
        自定义预设条目格式 ('预设名', '__custom__', name)：len==3 且 preset[1]
        == '__custom__'，渲染为可点击项、点击走 _ann_design_start_style 开局。
        官方预设（矩形/三角/米字/数字）由 (m,n,step[,kind]) 元组标识，不带
        __custom__ 标记，载入存档时据此区分。

        一级菜单的长度是**恒定**的：快速开始 + 至多五个目录（矩形 / 异形 /
        模型 / 捆绑谜题 / 自定义还原态，后两个没内容就不出现）+ 分隔线 +
        自定义... + 当前行。条目再多也只长在子菜单里，不会把一级菜单撑出
        屏幕（这也是 2026-10-27 把样式从平铺改成子菜单的直接动机）。
        """
        from gui import design_styles
        # 重建前记下「当前展开的子菜单」，重建后原样恢复（只有它还有内容时）。
        # 用 keep_sub 区分两种调用：删条目要保留（连着删几个不必反复展开），
        # 开局 / 点菜单栏要收起（菜单每次打开都该是收拢状态）。
        _prev_sub = getattr(self, 'puzzle_sub_open', '') if keep_sub else ''
        base = [
            ('快速开始：矩形 6×6 等级2', 6, 6, 2),
            ('矩形谜题 ▸', '__sub__', 'rect'),
            ('异形谜题 ▸', '__sub__', 'exotic'),
            ('模型谜题 ▸', '__sub__', 'models'),
        ]
        # 模型文件板型：条目完全由注册表决定——丢一个 models/<name>.json
        # 进目录，菜单里就多一项，这里一行都不用改。
        # ⚠️ 2026-10-25：原「＋ 搭建新模型...」首项与「高级选项...」已废止——
        # 新建模型/样式统一走「模式开关 → 创造 → ② 还原状态设计」，本菜单
        # 只列已存板型的开局入口。
        from engine import model_registry
        models = model_registry.loaded()
        items = [('__group__', '模型文件（几何引擎，实验）')]
        for name in sorted(models):
            m = models[name]
            n_blocks = len(m.spec.goal_blocks)
            items.append((f'{m.title}（{n_blocks} 块）', 4, 4, 1, name))
            items.append((f'{m.title} 等级2', 4, 4, 2, name))
        if not models:
            # 没有任何可用模型文件：分组标题留着会显得像「有内容但列不出
            # 来」，换成一句人话（并指路新建入口）。
            items.append(('（models/ 下暂无可用模型：模式开关 → 创造 → '
                          '还原状态设计 → 搭积木）',))
        self.puzzle_sub_presets['models'] = items

        # 自定义预设：按「有没有粘连」拆成两个并列的二级子菜单。
        #
        # 用户 2026-10-27 定：这两个和矩形 / 异形 / 模型一样是**二级子菜单**，
        # 位置在「自定义...」上方。原先做的是把它们当分组标题塞进一级菜单
        # 底部（所有样式平铺），用户看过后否掉：「放这里不合适，至少应该是
        # 在『自定义』上方的二级菜单」。拉开成子菜单后，一级菜单恒定只有
        # 「5 个目录 + 分隔线 + 自定义... + 当前行」，样式再多也不撑长。
        #
        # 名称分工：捆绑谜题 = 带 groups 的样式（滑块粘成整体）；自定义还原态
        # = 不带 groups 的样式。两者都是「已存的还原态样式」，区别只在粘连，
        # 所以派生来源（内置四形态 / 模型谜题）不体现在这一层。
        #
        # 空的子菜单**不出现**（不画一个点进去空白的目录）：这与「本菜单只列
        # 已存的开局入口」一致，也避免放一句长提示把菜单撑宽。没有样式时的
        # 新建路径由紧邻的「自定义...」与创造模式承担。
        styles = design_styles.list_styles(self.config_dir)
        bundled, plain = [], []
        for name in styles:
            data = design_styles.load_style(self.config_dir, name)
            groups = design_styles.groups_from_data(data) if data else {}
            (bundled if groups else plain).append(name)
        self.puzzle_sub_presets['bundled'] = [
            (name, '__custom__', name) for name in bundled]
        self.puzzle_sub_presets['custom'] = [
            (name, '__custom__', name) for name in plain]
        if bundled:
            base.append(('捆绑谜题 ▸', '__sub__', 'bundled'))
        if plain:
            base.append(('自定义还原态 ▸', '__sub__', 'custom'))

        base.append(('---',))
        base.append(('自定义...',))
        base.append(('__current__',))   # 底部当前状态行
        self.puzzle_presets = base

        # 二级子菜单交互状态：当前展开的 subkey（''=无）、条目矩形、悬停项。
        # 恢复 _prev_sub 时要求「这个子菜单还在、且还有条目」——它刚刚被删空
        # 的话留着会画出一个没有内容的空框。
        subs = self.puzzle_sub_presets
        self.puzzle_sub_open = (
            _prev_sub if _prev_sub in subs and subs[_prev_sub] else '')
        self.puzzle_sub_rects = []
        self.puzzle_sub_hovered = -1

    def _all_puzzle_items(self):
        """菜单里**所有**条目（一级 + 每个子菜单），按显示顺序摊平。

        只给「问『某道题在不在菜单里』」用（自检、测试、命令面板）。判定
        「当前玩的是哪一档」不要走它——那条路是同层比对（`_preset_is_current`），
        摊平会把「同一档在两处出现」的旧问题带回来。
        """
        out = list(self.puzzle_presets)
        for subkey in ('rect', 'exotic', 'models', 'bundled', 'custom'):
            out.extend((getattr(self, 'puzzle_sub_presets', None) or {}).get(
                subkey) or [])
        return out


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
        self._gap_anchor_world = None   # 旧局的「选中滑块那一点」不再有效
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
        # 切回方形：清除三角形/米字格模式标记（存档/热键路径都走这里）
        self.triangle_mode = False
        self.mi_mode = False

        # 创建新的游戏对象
        kind = 'numbered' if numbered else 'square'
        self.game = create_puzzle(m, n, step, kind=kind)
        self.numbered = numbered
        # 形态标记同步到逻辑对象：编号谜题的整数矩阵靠 numbered 还原编号
        self.game.numbered = numbered
        # 新谜题 = 默认满矩形还原目标（样式局的 D4 判定只属于那一个局）
        self._ann_style_goal = None

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
        self._mp_reset_target_region()
        # 选块填空选取态跨建局必须作废（点选的方块/空位坐标属于旧局）
        self._pick_fill = None
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
            step: 移动步数（等级），须满足 k − step ≥ 2

        建局即为实心大三角形（還原態），Alt+S 另行打亂。
        求解器/著色等高級功能照計劃禁用。
        """
        if self._tut_board_locked():
            return False
        # 切换谜题会重置棋盘 → 终止梯度流水线 / 连续撤销重做
        self._stop_gradient_pipeline()
        self._gap_anchor_world = None
        self._stop_continuous_undo_redo()
        self._last_timed_result = None
        self._ann_cancel_session('切换谜题')

        # 可动性门槛（已验证性质，见 experiments/math_repro/tri_kstep_property.py）：
        # 三角形存在任何合法移动 ⟺ k − step ≥ 2。切片沿缝平行滑动，每推一格都
        # 要求「无碰撞 + 整体仍连通」，而边长 k 的实心三角形同族切口接触面
        # 最长只有 k−1，滑 step 格需要接触面 ≥ step+1，于是
        # k−1 ≥ step+1 ⟺ k−step ≥ 2。旧守卫只挡了 step ≥ k，放过了
        # step = k−1 这类一步都动不了、打乱恒回还原态的死配置。
        if k < 3 or step < 1 or step > k - 2:
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
        # 切回三角形也要清米字格旗标：两个形态的缝隙族/方向表不同，留着会让
        # 渲染、命中、HTTP 的状态字段继续走米字格分支（ symptom：/status 的
        # puzzle 仍是 n~mi*m 而三族缝隙只剩 'h' 选得中）
        self.mi_mode = False
        self.numbered = False
        # 换形态 = 换谜题：自定义样式目标（方形专属的 goal_pattern）必须作废，
        # 否则底部栏会继续显示「样式：X」、存档还会把方形样式名写进三角存档
        self._ann_style_goal = None

        # 切到三角形时把求解器落到「聚拢」：查表/补缺宏/DFS/IDA* 都是方形
        # 语义（动作 4 元组 + 矩形目标形状），在 tri 上会静默走错。
        # 注意是落到**统一的 'gather' 入口**，不是某个「三角专用入口」——
        # 三形态共用同一个菜单项，形态差异由 solver 内部按 game 类型分发
        # （2026-10-05 用户要求：不同谜题要用相同入口）。
        self.solver_algorithm = 'gather'

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
        self._mp_reset_target_region()
        # 选块填空选取态跨建局必须作废（点选的方块/空位坐标属于旧局）
        self._pick_fill = None
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

    def _form_blocked(self, action: str) -> bool:
        """新形态（三角形 / 米字格）尚未实现的操作：统一拦截并给一致提示。

        局面分析等建立在方形 h/v 缝隙的动作语义上，换形态后要么直接报错
        （MiSliderMatrix 没有 is_valid_h_line）要么给出无意义的窗口，因此在
        入口处一并挡下。两个单形态助手各自带自己的措辞。
        """
        if self._triangle_blocked(action):
            return True
        return self._mi_blocked(action, '后续阶段开发中')

    def new_mi_puzzle(self, m: int, n: int, step: int = 1) -> bool:
        """创建米字格谜题（可玩：两次触控选组 + 虚拟键盘）。

        参数：
            m: 行数
            n: 列数
            step: 移动步数（等级），须小于 max(m, n)

        建局即为实心 m×n 米字格（还原态）。交互走 M2 定案的两次触控：
        第一下点缝隙，第二下按住滑块拖动才定向提交（方向取位移在缝隙切向
        上的投影符号），只按不拖＝选中该组、方向交给虚拟键盘；单次触控
        永久关闭（八向靠一次触控猜方向误触面太大），物理键盘不绑。
        """
        if self._tut_board_locked():
            return False
        # 切换谜题会重置棋盘 → 终止梯度流水线 / 连续撤销重做
        self._stop_gradient_pipeline()
        self._gap_anchor_world = None
        self._stop_continuous_undo_redo()
        self._last_timed_result = None
        self._ann_cancel_session('切换谜题')

        if m < 2 or n < 2 or step >= max(m, n):
            return False
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换谜题"
            self.macro_notify_timer = 90
            return False
        self._timer_cancel()
        detached = self._detach_readonly_save()

        self.current_m = m
        self.current_n = n
        self.current_step = step
        self.mi_mode = True
        self.triangle_mode = False
        self.numbered = False
        # 换形态 = 换谜题：方形专属的自定义样式目标必须作废（同三角开局）
        self._ann_style_goal = None
        # 米字格按冻结决策禁用单次触控（只做两次触控 + 虚拟键盘）；
        # 摆在模式切换处而不是每次点击处检查，避免开着单次触控进米字格
        self.control_single_touch = False

        # 切到米字格时把求解器落到「聚拢」：查表/补缺宏/DFS/IDA* 都是方形语义
        # （4 元组动作 + 矩形目标形状 + 整数坐标），在 mi 上会静默走错 ——
        # mi 的 rep 是 (r,c,q) 且坐标可能是半整数。
        # 与三角一样走**统一的 'gather' 入口**，不给 mi 单开一个入口。
        self.solver_algorithm = 'gather'

        self.game = create_puzzle(m, n, step, kind='mi')

        # 重置状态
        self.zoom = self._fit_mi_zoom()
        self.selected_gap = None
        self.selected_block = None
        self.step_count = 0
        self.animating = False
        self.anim_blocks = []
        for block in self.game.blocks:
            block.number = None

        self.game_history.reset()
        self._mp_reset_target_region()
        # 选块填空选取态跨建局必须作废（点选的方块/空位坐标属于旧局）
        self._pick_fill = None
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()

        self.macro_notify_msg = (
            f"切换谜题：米字格 {m}×{n} 等级{step}"
            "（两次触控：先点缝隙，再点滑块）")
        self.macro_notify_timer = 150
        return True

    def new_shatter_puzzle(self, step: int = 1) -> bool:
        """创建碎三角谜题（保留旧调用点，等价于 new_model_puzzle('shatter')）。"""
        return self.new_model_puzzle('shatter', step)

    def new_model_puzzle(self, model_name: str, step: int = 1) -> bool:
        """按模型文件开局（几何引擎解释器路线的通用入口）。

        与 square / triangle / mi 三个手写入口不同：本方法**不写任何形状
        相关的分支**——盘面、形状、缝族全部来自 ``models/<name>.json``，
        绘制由通用渲染通道（``spec.cell_polygon``）完成。这里只做建局与
        状态重置。换一个 json 就多一个板型，本方法不用改。

        模型板型没有旧实现，只能走 EngineGame，故直接调
        ``create_adapter_puzzle``，**不依赖全局引擎开关**。
        """
        from engine import model_registry
        try:
            model = model_registry.loaded(model_name)
        except KeyError as exc:
            self.macro_notify_msg = f'模型不可用：{exc}'
            self.macro_notify_timer = 200
            return False
        if self._tut_board_locked():
            return False
        self._stop_gradient_pipeline()
        self._gap_anchor_world = None
        self._stop_continuous_undo_redo()
        self._last_timed_result = None
        self._ann_cancel_session('切换谜题')

        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换谜题"
            self.macro_notify_timer = 90
            return False
        self._timer_cancel()
        detached = self._detach_readonly_save()

        # 竞速对模型板型不可用（见 gui/speedrun.py set_game_mode 的拦截）：
        # 带着 timed 进模型局，打乱后会走到 _timer_enter_ready 的 lossy
        # export_map（24 种朝向压成 '#'），成绩是一份丢朝向的串。这里主动
        # 退回练习模式并说明，不把谜题换成一静默错的模式组合。
        #
        # 创造模式**不再退回**（2026-10-26 用户定）：创造首页的两个子入口都
        # 自建局面——「① 打乱状态设计 / 格子画布」各自有 _is_model_kind 拒绝，
        # 「② 还原态设计 → 搭积木」用编辑器自己的预览局——与当前盘面形态
        # 无关。此前连创造也一并退回练习，等于让自造谜题永远进不了创造
        # 模式（用户报「不能竞速是次要的，但影響是無法進入創造模式」）。
        mode_note = ''
        if self.game_mode == 'timed':
            self.set_game_mode('practice')
            mode_note = f"（{model.title}不支持竞速模式，已切回练习）"

        self.current_step = step
        # 模型板型是独立形态：既不是米字也不是三角（两者都有各自手画渲染，
        # 走了会画错）。形状交给通用通道，故两个旗标都关。
        self.mi_mode = False
        self.triangle_mode = False
        self.numbered = False
        self.current_m = 4
        self.current_n = 4
        self._ann_style_goal = None
        self.solver_algorithm = 'gather'   # 异形统一走聚拢入口（与 mi/tri 同）
        self._pick_fill = None

        # 幾何引擎板型只保留「箭頭 + 兩次觸控」兩種操作（用戶 2026-10-24 定）：
        # 鍵鼠方向鍵、單次觸控（拖拽角度猜縫）、虛擬鍵盤（鍵位按形狀排布）
        # 都與形狀強相關，新板型不做這層適配，直接關掉而不是留一個半壞的入口。
        self.control_two_touch = True
        self.control_single_touch = False
        self.control_mouse_kb = False
        self.show_virtual_keyboard = False

        from engine.adapter import create_adapter_puzzle
        self.game = create_adapter_puzzle(model_name, 4, 4, step)

        self.zoom = 1.0
        self.selected_gap = None
        self.selected_block = None
        self.step_count = 0
        self.animating = False
        self.anim_blocks = []
        for block in self.game.blocks:
            block.number = None

        self.game_history.reset()
        self._mp_reset_target_region()
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()

        self.macro_notify_msg = (
            f"切换谜题：{model.title} 等级{step}"
            f"（{len(model.spec.goal_blocks)} 块）{mode_note}")
        self.macro_notify_timer = 150
        return True

    def _generic_controls_locked(self) -> bool:
        """几何引擎板型：只允许「箭头 + 两次触控」这两种操作。

        键鼠方向键、单次触控（拖拽角度猜缝）、虚拟键盘（键位按形状排布）都与
        形状强相关——每个板型的缝族方向、屏幕落向、字母表都不同，新板型不做
        这层适配（用户 2026-10-24 定）。返回 True 时相关开关一律拒绝改动。
        """
        return self._generic_spec() is not None

    def _mi_blocked(self, action: str, hint: str = '') -> bool:
        """米字格模式下不可用的操作：给出一致提示并拦截。

        M2 起滑动/选组/虚拟键盘/拖拽已开放；这里只剩求解器等后续阶段功能。
        """
        if not getattr(self, 'mi_mode', False):
            return False
        msg = f"米字格：{action}不可用"
        if hint:
            msg += f"（{hint}）"
        self.macro_notify_msg = msg
        self.macro_notify_timer = 120
        return True

    def _model_blocked(self, action: str, hint: str = '') -> bool:
        """模型文件板型（自造谜题 / 碎三角等）暂不支持的入口：提示并拦截。

        分组着色、悬停连锁、复原提示标记、宏、求解器这五类是**按方形四邻 /
        三角三邻 / 米字八向手写语义**实现的：它们默认「相邻」有全局统一的
        定义、默认朝向集是全局那一套。模型板型的缝族、朝向表、晶格都是
        per-model 的（同一 2D 格还能叠不同朝向的块），套用会给出**错误**的
        着色/连锁/标记，而不是没有信息。用户 2026-10-26 定：宁可明说
        「自造谜题没这个功能」，也不留一个按得下去、反馈是错的入口。

        判据用 `_is_model_kind()`（形态键不在旧四形态里），与竞速/打乱/
        设计画布各处拦截同源，不硬编码 ``'shatter'``。
        """
        if not self._is_model_kind():
            return False
        msg = f"自造谜题：{action}暂不支持"
        if hint:
            msg += f"（{hint}）"
        self.macro_notify_msg = msg
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

    def _fit_mi_zoom(self, fill: float = 0.78) -> float:
        """米字格棋盘初始缩放：包围盒是矩形，走与三角形同一条算式。"""
        view = self._mi_view()
        min_x, min_y, max_x, max_y = view.bounding_box(self.game.positions())
        bw = max(1e-6, max_x - min_x)
        bh = max(1e-6, max_y - min_y)
        avail_w = (self.screen_width - self.right_panel_width) * fill
        avail_h = (self.screen_height - self.menu_bar_height - self.status_bar_height) * fill
        return max(self.min_zoom, min(self.max_zoom,
                                      min(avail_w / bw, avail_h / bh)))

    def _center_mi(self):
        """米字格棋盘居中：按矩形包围盒算相机偏移。"""
        view = self._mi_view()
        min_x, min_y, max_x, max_y = view.bounding_box(self.game.positions())
        board_cx = (min_x + max_x) / 2.0
        board_cy = (min_y + max_y) / 2.0
        game_center_x = (self.screen_width - self.right_panel_width) / 2
        game_center_y = (self.menu_bar_height +
                         (self.screen_height - self.menu_bar_height - self.status_bar_height) / 2)
        self.camera_x = game_center_x - board_cx * self.zoom
        self.camera_y = game_center_y - board_cy * self.zoom

    def _mi_hit_board(self, screen_x: int, screen_y: int) -> bool:
        """点击是否落在米字格棋盘包围盒内（落在空白处则不触发任何操作）。

        单位块与缝隙的命中由 mi_view 负责（world_to_cell / gap_at），这里
        只问「在不在棋盘范围里」，好让空白处的点击安静地走相机平移。
        """
        try:
            view = self._mi_view()
            min_x, min_y, max_x, max_y = view.bounding_box(self.game.positions())
            wx, wy = self.screen_to_world(screen_x, screen_y)
            return min_x <= wx <= max_x and min_y <= wy <= max_y
        except Exception:
            return False

    def is_solved(self) -> bool:
        """判断当前是否为复原状态（比较0-1矩阵形状；带序号时额外检查编号顺序）"""
        # 打乱演示播放中：视觉盘面是打乱前状态，逻辑上按打乱终态判胜
        # （演示只是重演过程，语义盘面早已是终态，见 _demo_logic_positions）
        with self._demo_logic_positions():
            return self._is_solved_positions()

    def _is_solved_positions(self) -> bool:
        """按当前 blocks 位置判胜（is_solved 的盘面判定核心）"""
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

    def ensure_blocks_visible(self, only_if_invisible: bool = False):
        """确保所有滑块都在可视区域内，超出时自动调整相机。

        ``only_if_invisible=True``：只在**整盘完全不在视口里**时才平移。
        走一步棋之后用这个口径——碎三角没有盘面边界，滑动会让拼盘逐格外扩，
        按「碰到边缘就拉回」的旧口径几乎每一步都会平移相机，玩家刚点过的
        位置立刻跑掉（2026-10-24 用户实测「每次滑動都調整相機，體驗非常差」）。
        兜底仍保留：真滑到整盘看不见了，至少还能拉回来。
        """
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
        elif getattr(self, 'mi_mode', False):
            # 米字格同理：一格 = 1 个世界单位（无 gap 间距），必须走 board_view，
            # 直接套方形那套 (cell+gap) 间距会把包围盒算大
            view = self._mi_view()
            min_x, min_y, max_x, max_y = view.bounding_box(self.game.positions())
            min_screen_x, min_screen_y = self.world_to_screen(min_x, min_y)
            max_screen_x, max_screen_y = self.world_to_screen(max_x, max_y)
        elif self._poly_world_bbox() is not None:
            # 通用通道：盤面世界包圍盒恆從零起點（origin 對齊左上角），
            # 直接過 world_to_screen——**不能**套方形那套
            # ``location[1]*(cell+gap)``：碎三角的 location 是 P 空間
            # （3× 質心，各向異性），乘出來的「屏幕座標」與真實幾何差著
            # √3/6 的比例，相機被推到宇宙外（實測 camera=(-1203,-1628)）
            _bx, _by, _mx, _my = self._poly_world_bbox()
            min_screen_x, min_screen_y = self.world_to_screen(_bx, _by)
            max_screen_x, max_screen_y = self.world_to_screen(_mx, _my)
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

        if need_adjust and only_if_invisible:
            # 只要还有一角和视口相交就不动相机：局部出界是正常游玩状态，
            # 玩家自己拖 / 按「居中」即可，不该被系统代劳。
            still_visible = (max_screen_x > view_left
                             and min_screen_x < view_right
                             and max_screen_y > view_top
                             and min_screen_y < view_bottom)
            if still_visible:
                return

        if need_adjust:
            self.camera_x += dx
            self.camera_y += dy

    def center_map(self):
        """将地图居中显示在游戏区域中"""
        if getattr(self, 'triangle_mode', False):
            self._center_triangle()
            return
        if getattr(self, 'mi_mode', False):
            self._center_mi()
            return
        bbox = self._poly_world_bbox()
        if bbox is not None:
            # 通用通道：原點按板型固定（不再隨局面歸零），包圍盒是**真實
            # 角點** (min_x, min_y, max_x, max_y)，居中取兩端中點。
            game_center_x = (self.screen_width - self.right_panel_width) / 2
            game_center_y = self.menu_bar_height + (
                self.screen_height - self.menu_bar_height - self.status_bar_height) / 2
            _cx = (bbox[0] + bbox[2]) / 2.0
            _cy = (bbox[1] + bbox[3]) / 2.0
            self.camera_x = game_center_x - _cx * self.zoom
            self.camera_y = game_center_y - _cy * self.zoom
            return
        bounds = self.game.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']

        scaled_cell, scaled_gap, step_px = self._board_px()   # 与绘制同一套整数像素

        map_width = (max_col - min_col + 1) * step_px - scaled_gap
        map_height = (max_row - min_row + 1) * step_px - scaled_gap

        map_center_x = min_col * step_px + map_width / 2
        map_center_y = min_row * step_px + map_height / 2

        game_center_y = self.menu_bar_height + (self.screen_height - self.menu_bar_height - self.status_bar_height) / 2

        self.camera_x = (self.screen_width - self.right_panel_width) / 2 - map_center_x
        self.camera_y = game_center_y - map_center_y

    # —— 外部控制（HTTP API 令牌 / 话术 / 教程）——
    # 威胁模型：HTTP 绑 127.0.0.1，令牌防的是本机上的其他进程与网页；
    # stdin 管道通道只有启动方父进程能写，天然可信，不设防。

    def _is_camera_valid(self) -> bool:
        """检查当前 camera 位置是否能让滑塊在视口内可见"""
        if not self.game.blocks:
            return True
        bbox = self._poly_world_bbox()
        if bbox is not None:
            # 通用通道：世界包圍盒過 world_to_screen（zoom+camera 只一次）
            left, top = self.world_to_screen(bbox[0], bbox[1])
            right, bottom = self.world_to_screen(bbox[2], bbox[3])
            view_left = 0
            view_right = self.screen_width - self.right_panel_width
            view_top = self.menu_bar_height
            view_bottom = self.screen_height - self.status_bar_height
            return not (right < view_left or left > view_right or
                        bottom < view_top or top > view_bottom)
        bounds = self.game.get_boundaries()
        min_row, max_row = bounds['min_row'], bounds['max_row']
        min_col, max_col = bounds['min_col'], bounds['max_col']
        scaled_cell, scaled_gap, step_px = self._board_px()   # 与绘制同一套整数像素

        # 滑塊区域在屏幕上的范围
        left   = min_col * step_px + self.camera_x
        right  = max_col * step_px + scaled_cell + self.camera_x
        top    = min_row * step_px + self.camera_y
        bottom = max_row * step_px + scaled_cell + self.camera_y

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

    def _generic_gap_live(self, gap) -> bool:
        """通用通道的縫活性：推不動就選不中（引擎適配器 is_live_gap）。

        與 is_valid_gap 的分工：後者只問「縫是否切出非空兩側」，前者追問
        「至少一側真能沿這條縫滑動」——碎三角有 12 條接觸邊不被任何活縫
        覆蓋（綠底三族恆死），只查 is_valid 會選中一條推不動的縫。
        舊形態無此方法，getattr 兜底回 True（舊路徑不經過本函式）。
        """
        fn = getattr(self.game, 'is_live_gap', None)
        if not callable(fn):
            return True
        return bool(fn(gap[0], gap[1]))

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

            if getattr(self, 'mi_mode', False):
                key = self._mi_view().world_to_cell(world_x, world_y,
                                                   self.game.positions())
                if key is None:
                    return None
                for block in self.game.blocks:
                    if mi_key(block) == key:
                        return block
                return None

            if self._generic_spec() is not None:
                # 通用通道：多邊形命中（origin 與渲染/箭頭同源），
                # 再按 (point, orient) 找回塊對象——鍵是扁平的。
                view = self._polygon_view()
                origin = self._poly_view_origin(view)
                key = view.hit(world_x, world_y, self.game.board, origin)
                if key is None:
                    return None
                point, orient = key
                point = tuple(point)
                for block in self.game.blocks:
                    loc = tuple(block.location)
                    if loc[:2] == point and (
                            len(loc) < 3 or loc[2] == orient):
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

    def get_gap_at_pos(self, screen_x: int, screen_y: int,
                       tolerance: float = None) -> tuple:
        """根据屏幕坐标获取缝隙位置

        tolerance 仅对通用通道（多边形密铺）生效：放大它即放大「点缝的
        可选命中带」。None 走默认 10 世界单位（≈12px@zoom1.21）——这是第一
        击选缝的精准带；放大值只用于「没选中缝时、点偏进相邻块」的兜底检索，
        绝不改变已选中缝后的第二步交互（见 _sq_click_query）。
        """
        try:
            world_x, world_y = self.screen_to_world(screen_x, screen_y)

            if getattr(self, 'triangle_mode', False):
                cells = self.game.positions()
                for gap_type, line in self._tri_view().candidate_gaps(
                        world_x, world_y, cells):
                    if self.game.is_valid_gap(gap_type, line):
                        return (gap_type, line)
                return None

            if getattr(self, 'mi_mode', False):
                # 米字格：最近單位邊裁定（等距取長邊）。命中的那條可能落在
                # 棋形外沿（兩側不全有塊），這種縫整體平移沒有意義，捨棄
                cells = self.game.positions()
                gap = self._mi_view().gap_at(world_x, world_y, cells)
                if gap is None:
                    return None
                if not self.game.is_valid_gap(*gap):
                    return None
                return gap

            if self._generic_spec() is not None:
                # 通用通道：候選縫按「到接觸邊足跡的距離」排序，逐條過
                # is_valid_gap + is_live_gap，第一條活縫即選中——一條邊可
                # 被多條候選縫共享（實測 1~4 條），歧義就按距離+族序決勝。
                view = self._polygon_view()
                origin = self._poly_view_origin(view)
                tol = 10.0 if tolerance is None else float(tolerance)
                for gap_type, line, _dist in view.gap_candidates(
                        world_x, world_y, self.game.board, origin,
                        tolerance=tol):
                    if self.game.is_valid_gap(gap_type, line) and \
                            self._generic_gap_live((gap_type, line)):
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

    def _macro_notify(self, msg):
        self.macro_notify_msg = msg
        self.macro_notify_timer = 90

    def close_all_menus(self):
        """关闭所有下拉菜单"""
        self.show_file_menu = False
        self.show_edit_menu = False
        self.show_puzzle_menu = False
        self.show_macro_menu = False
        # 谜题二级子菜单同步收起
        self.puzzle_sub_open = ''
        self.puzzle_sub_rects = []
        self.puzzle_sub_hovered = -1

    def is_blank_area(self, screen_x: int, screen_y: int) -> bool:
        """判断指定位置是否为空白区域"""
        return self.get_block_at_pos(screen_x, screen_y) is None and \
               self.get_gap_at_pos(screen_x, screen_y) is None

    def run(self):
        """游戏主循环"""
        clock = pygame.time.Clock()

        while self.running:
            try:
                # S1-1：输入优先——先处理事件、再更新状态与绘制，消除恒定 1 帧输入延迟
                self.handle_events()
                self._ann_poll()
                self._auto_update_poll()
                self._update_cursor()

                # 处理终端指令
                self.process_commands()

                # 更新动画
                self.update_animation()

                # 打乱演示：推进淡出/淡入（记录播放由上面的动画系统驱动）
                self._update_shuffle_demo()

                # S0-1：复原弹窗动画计时器——此前全项目从未递增，弹窗恒停第 0 帧
                # （缩放 0.7 / 透明 / 光晕 0 且 6 秒自动关闭永不触发）。每帧自增使其真正生效。
                if getattr(self, '_solved_popup_active', False):
                    self._solved_popup_t += 1

                # 检查自动求解结果
                self._check_auto_solve_result()

                # 流式求解：把后台算好的段接进宏播放管道（边算边播）
                self._pump_stream_segments()
                # 自动规划·流式：hybrid 边算边播 + 历史最优 checkpoint
                self._pump_auto_stages()

                # 计时器：刷新实时用时 + 检测复原
                if self.timer_state == 'running':
                    self.timer_elapsed = time.perf_counter() - self.timer_start
                self._timer_check_solved()

                # 求解中显示计时和进度（宏动画播放阶段保留逐步行进提示）
                # ⚠️ 旧条件带 `and not self.macro_executing`：流式（填洞/补缺宏）
                # 一开始播放首段就把 macro_executing 置 True，于是「后台还在算、
                # 新段还没到」这段窗口里计时/进度**不再被刷新**，通知 3 秒后淡出
                # ——表现为「右下角没了、以为卡死，其实在算」。后台没结束就该一直
                # 显示用时，故去掉该条件。
                if self._auto_solve_running:
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
                            # 「深度/节点」是 IDA*/BFS 一类搜索的标记：只有真在搜索
                            # （bound/nodes 非 0）才有意义。不加判断会把「深度0
                            # 节点0」这种空壳字样写进通知里。
                            if nodes or bound:
                                detail = f"深度{bound} 节点{nodes} {path_preview}"
                            else:
                                detail = path_preview
                            head = f"[{stage}] " if stage else ''
                            self.macro_notify_msg = (
                                f"{head}{detail} | {elapsed:.1f}s")
                    else:
                        self.macro_notify_msg = f"求解中... {elapsed:.1f}s"
                    self.macro_notify_timer = 180
                    self.macro_notify_persistent = True  # 持续显示不走淡出
                else:
                    self.macro_notify_persistent = False

                # 更新宏通知计时器（持玖模式不递减）
                if self.macro_notify_timer > 0 and not self.macro_notify_persistent:
                    self.macro_notify_timer -= 1

                # 设置-控制页内联反馈计时器（对话框内操作反馈，见 _set_ext_feedback）
                if getattr(self, '_settings_ext_msg_timer', 0) > 0:
                    self._settings_ext_msg_timer -= 1

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
                self.draw_status_bar()

                # 动态更新编辑菜单的求解按钮文字
                shortcut = self._format_menu_shortcut('auto_solve')
                if self._auto_solve_running:
                    self.edit_menu_items[-1] = f'停止求解 {shortcut}'
                else:
                    self.edit_menu_items[-1] = f'自动求解 {shortcut}'

                # 浮动面板（先画：位于菜单层和模态对话框之下）
                self.draw_virtual_keyboard()
                self.draw_metrics_panel()
                self.draw_records_panel()
                # 标注模式（工具栏 + 跟踪标记 + 子对话框）
                self.draw_annotation_mode()

                # 搭积木编辑器浮层（调色盘 + 工具栏 + 幽灵预览；
                # 块本体走上面的通用多边形通道，这里只画编辑器专属 UI）
                self._med_draw_overlay()

                # 模型悬停预览的空闲预热：每帧最多画+存一个模型（见 gui/model_preview）
                self._preview_pump()

                # 菜单栏 + 下拉菜单：非模态最上层（下拉菜单盖住浮动面板）
                self.draw_menu_bar()

                # 非模态浮层（通知 / 复原弹窗 / 教程引导）：盖在菜单与浮动面板之上，
                # 但必须落在模态对话框之下——模态是交互上的最高优先级层，事件分发里
                # 模态最先消费点击；若这里反过来画在模态之上，会出现「模态已吃掉点
                # 击、浮层却浮在模态表面」的视觉错位（求解进行中按设置键即触发）。
                self.draw_macro_notify()
                self.draw_solved_popup()
                self.draw_tutorial_prompt()
                self.draw_tutorial_panel()
                self.draw_update_banner()

                # 模态对话框（后画，真正最上层；盖住上述所有浮层）
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
                # 确认弹窗（删除预设）：盖在这些对话框之上——它是模态中的模态
                if getattr(self, 'show_confirm_dialog', False):
                    self.draw_confirm_dialog()
                # 命令面板：画在所有模态之上（事件分发里同样最先消费，两者必须一致）
                if getattr(self, 'palette_active', False):
                    self.draw_command_palette()
                self.draw_update_progress()

                '''# 虚拟键盘（浮动面板）
                self.draw_virtual_keyboard()

                # 聚拢度指标面板（浮动面板）
                self.draw_metrics_panel()

                # 成绩记录面板（浮动面板）
                self.draw_records_panel()'''

                # 左键单击反馈（盖在所有界面之上，含模态对话框）
                self.draw_click_feedback()

                # 打乱演示转场蒙层（淡出/淡入，盖住棋盘切换到打乱终态）
                self.draw_shuffle_fade()

                # 「打乱中 xx%」进度提示（画在蒙层之上：淡出到全遮时
                # 正好看到 100%，与切屏时刻严格对齐）
                self.draw_shuffle_progress()

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
                # 非致命：记进 config/error_log.jsonl 并继续运行，避免单帧小异常导致游戏闪退。
                # 节流：同一个异常（类型 + 消息）每会话只记一条。每帧都抛的话是
                # 60 条/秒，几秒就把日志写到 4MB 上限触发 rotate，把真正的第一条
                # （也是唯一有价值的那条）冲掉。控制台仍逐帧打印，方便当场看频率。
                _seen = getattr(self, '_loop_err_seen', None)
                if _seen is None:
                    _seen = self._loop_err_seen = set()
                _sig = (type(e).__name__, str(e))
                if _sig not in _seen:
                    _seen.add(_sig)
                    log_writer.exception('主循环异常', *sys.exc_info())
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
