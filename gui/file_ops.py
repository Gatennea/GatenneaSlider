# -*- coding: utf-8 -*-
"""
文件操作 Mixin

包含：
- save_config / load_last_state: 配置管理
- _build_save_data / _load_save_data: 序列化/反序列化
- save_to_file / save_as / _save_to_path: 保存
- load_from_file: 加载（使用 pygame 文件对话框）
- export_map / import_map: 兼容旧终端接口
"""

import json
import os
import pygame
from puzzle_types import create_puzzle


def _compact_json_dumps(data, indent=2, max_line_width=200):
    """紧凑 JSON 序列化：纯数字/布尔数组输出为单行，短对象也尽量单行"""

    def _format(obj, depth, sparse=False):
        # sparse=True 时，数组元素之间用空行分隔（适用于 matrix 等需要人类阅读的二维数组）
        current_pad = ' ' * (depth * indent)
        next_pad = ' ' * ((depth + 1) * indent)

        if isinstance(obj, dict):
            if not obj:
                return '{}'
            pairs = []
            for k, v in obj.items():
                k_str = json.dumps(k, ensure_ascii=False)
                # matrix 字段的二维数组启用稀疏模式，行间加空行方便阅读
                v_str = _format(v, depth + 1, sparse=(k == 'matrix' and isinstance(v, list) and v and isinstance(v[0], list)))
                pairs.append((k_str, v_str))

            # 尝试内联：所有 value 都是单行且总长度不超限
            all_single = all('\n' not in v for _, v in pairs)
            if all_single:
                inline_parts = [f'{k}: {v}' for k, v in pairs]
                inline = '{' + ', '.join(inline_parts) + '}'
                if len(inline) <= max_line_width:
                    return inline

            lines = [f'{next_pad}{k}: {v}' for k, v in pairs]
            return '{\n' + ',\n'.join(lines) + '\n' + current_pad + '}'

        elif isinstance(obj, list):
            if not obj:
                return '[]'

            # 纯原子类型数组（数字、布尔、None）→ 尝试单行
            all_atomic = all(isinstance(x, (int, float, bool, type(None))) for x in obj)
            if all_atomic:
                inline = '[' + ', '.join(json.dumps(x) for x in obj) + ']'
                if len(inline) <= max_line_width:
                    return inline
                # 原子数组超长时仍逐个放在一行（如超长矩阵行），不做拆分
                return inline

            # 递归格式化每个元素
            items = [_format(x, depth + 1) for x in obj]

            # 稀疏模式（matrix 等二维数组）：强制每个元素一行，元素间空行分隔
            if sparse:
                sep = ',\n'
                return '[\n' + sep.join(f'{next_pad}{item}' for item in items) + '\n' + current_pad + ']'

            all_single = all('\n' not in item for item in items)

            if all_single:
                inline = '[' + ', '.join(items) + ']'
                if len(inline) <= max_line_width:
                    return inline

            return '[\n' + ',\n'.join(f'{next_pad}{item}' for item in items) + '\n' + current_pad + ']'

        else:
            return json.dumps(obj, ensure_ascii=False)

    return _format(data, 0)

# 快捷键默认表，也是唯一底表：加载时按它补全缺失动作、文件损坏时按它回退，
# GUI 启动时的初值同样用它（GUI.py 不再另抄一份）。加新动作必须同时改这里，
# 否则已有配置文件的用户在加载时会被静默丢掉新键位（三角形 E/Z/X 就这么丢过）。
DEFAULT_KEYBINDINGS = {
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
    # 三角形密铺的另外三个方向（w/a/d/s 复用上面的四向键位，六键围成六边形）
    'tri_up_right': {'key': 'e', 'modifiers': []},
    'tri_down_left': {'key': 'z', 'modifiers': []},
    'tri_down_right': {'key': 'x', 'modifiers': []},
    'auto_solve': {'key': 'a', 'modifiers': ['ctrl']},
    'macro_record': {'key': 'm', 'modifiers': ['ctrl']},
    'virtual_keyboard': {'key': 'f1', 'modifiers': []},
    'metrics_panel': {'key': 'f2', 'modifiers': []},
    'records_panel': {'key': 'f3', 'modifiers': []},
}


class FileOpsMixin:
    """文件操作相关方法 Mixin"""

    def save_config(self):
        """保存配置到 config/config.json，历史记录到 config/temp_history.json，快捷键到 keyboard_shortcut.json"""
        os.makedirs(self.config_dir, exist_ok=True)

        # 保存历史记录到 temp_history.json
        save_data = self._build_save_data()
        try:
            with open(self.temp_history_path, 'w', encoding='utf-8') as f:
                f.write(_compact_json_dumps(save_data))
        except Exception as e:
            print(f"保存临时历史记录失败: {e}")

        # 始终以 temp_history_path 作为 last_file_path
        # 这样重启时必定加载退出瞬间的最新状态
        config = {
            'animation_speed': self.animation_duration,
            'zoom': self.zoom,
            'last_file_path': self.temp_history_path,
            'camera_x': self.camera_x,
            'camera_y': self.camera_y,
            'solver_algorithm': getattr(self, 'solver_algorithm', 'ida_star'),
            'coloring_enabled': getattr(self, 'coloring_enabled', False),
            'chain_hint_enabled': getattr(self, 'chain_hint_enabled', False),
            'save_readonly_flag': getattr(self, 'save_readonly_flag', False),
            'prevent_overwrite_flag': getattr(self, 'prevent_overwrite_flag', False),
            'gather_params': getattr(self, 'gather_params', {}),
            'gather_enabled': getattr(self, 'gather_enabled', {}),
            # 教程进度（闯关模式）
            'tutorial': getattr(self, 'tut_progress', {}),
        }

        # 窗口大小 / 屏幕位置 / 面板状态（下次启动恢复）
        config['window_size'] = [self.screen_width, self.screen_height]
        try:
            config['window_pos'] = list(pygame.display.get_window_position())
        except Exception:
            config['window_pos'] = None
        config['panels'] = {
            'records': {
                'visible': getattr(self, 'show_records_panel', False),
                'pos': list(getattr(self, 'rp_pos', [10, self.menu_bar_height + 10])),
            },
            'virtual_keyboard': {
                'visible': getattr(self, 'show_virtual_keyboard', False),
                'pos': list(getattr(self, 'vk_pos', [0, 0])),
            },
            'metrics': {
                'visible': getattr(self, 'show_metrics_panel', False),
                'pos': list(getattr(self, 'mp_pos', [10, self.menu_bar_height + 10])),
            },
        }
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

        # 保存快捷键配置
        self.save_keybindings()

    def save_keybindings(self):
        """将当前快捷键配置保存到 keyboard_shortcut.json"""
        kb_path = os.path.join(self.config_dir, 'keyboard_shortcut.json')
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(kb_path, 'w', encoding='utf-8') as f:
                json.dump(self.keybindings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存快捷键配置失败: {e}")

    def load_keybindings(self):
        """从 keyboard_shortcut.json 加载快捷键配置，若文件不存在或格式错误则使用默认值"""
        kb_path = os.path.join(self.config_dir, 'keyboard_shortcut.json')

        # 默认配置
        default = DEFAULT_KEYBINDINGS.copy()

        if not os.path.exists(kb_path):
            # 文件不存在，自动重新生成默认配置
            self.keybindings = default
            try:
                os.makedirs(self.config_dir, exist_ok=True)
                with open(kb_path, 'w', encoding='utf-8') as f:
                    json.dump(default, f, ensure_ascii=False, indent=2)
                print(f"快捷键配置文件不存在，已重新生成默认配置: {kb_path}")
            except Exception as e:
                print(f"重新生成默认快捷键配置失败: {e}")
            return

        try:
            with open(kb_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 验证格式：必须是 dict，且每个 value 必须有 'key' 和 'modifiers'
            if not isinstance(data, dict):
                raise ValueError("配置格式错误")
            for action_name in default:
                if action_name in data:
                    entry = data[action_name]
                    if not isinstance(entry, dict) or 'key' not in entry or 'modifiers' not in entry:
                        raise ValueError(f"动作 '{action_name}' 格式错误")
                else:
                    # 缺失的动作用默认值补全
                    data[action_name] = default[action_name]
            self.keybindings = data
        except Exception as e:
            print(f"加载快捷键配置失败: {e}，使用默认配置")
            self.keybindings = default
            # 尝试重新生成默认配置文件
            try:
                with open(kb_path, 'w', encoding='utf-8') as f:
                    json.dump(default, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _update_menu_shortcut_texts(self):
        """根据当前 keybindings 更新菜单栏快捷键提示文字"""
        self.file_menu_items = [
            f"打开 {self._format_menu_shortcut('load')}",
            f"保存 {self._format_menu_shortcut('save')}",
            '另存为...'
        ]
        self.edit_menu_items = [
            f"撤销 {self._format_menu_shortcut('undo')}",
            f"重做 {self._format_menu_shortcut('redo')}",
            f"打乱 {self._format_menu_shortcut('shuffle')}",
            f"重置 {self._format_menu_shortcut('reset')}",
            '---',
            f"自动求解 {self._format_menu_shortcut('auto_solve')}",
        ]

    def _format_menu_shortcut(self, action_name):
        """格式化单个快捷键为菜单显示文本，如 'Ctrl+Z'"""
        kb = self.keybindings.get(action_name)
        if not kb:
            return ''
        parts = []
        for mod in kb.get('modifiers', []):
            if mod == 'ctrl':
                parts.append('Ctrl')
            elif mod == 'alt':
                parts.append('Alt')
            elif mod == 'shift':
                parts.append('Shift')
        key = kb.get('key', '')
        key_display = {
            'space': 'Space', 'up': '↑', 'down': '↓', 'left': '←', 'right': '→',
            'return': 'Enter', 'escape': 'Esc', 'tab': 'Tab', 'backspace': 'Bksp',
        }
        parts.append(key_display.get(key, key.upper() if len(key) == 1 else key))
        return '+'.join(parts)

    def load_last_state(self):
        """加载上次状态：从 config.json 读取配置，从对应文件恢复游戏状态"""
        # 先加载快捷键配置
        self.load_keybindings()
        self._update_menu_shortcut_texts()

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                if 'animation_speed' in config:
                    self.animation_duration = config['animation_speed']
                if 'zoom' in config:
                    self.zoom = config['zoom']

                # 恢复浮动面板状态（位置 / 开关）
                panels = config.get('panels', {})
                if isinstance(panels, dict):
                    _rp = panels.get('records', {})
                    if isinstance(_rp, dict):
                        if 'visible' in _rp:
                            self.show_records_panel = bool(_rp['visible'])
                        if isinstance(_rp.get('pos'), list) and len(_rp['pos']) == 2:
                            self.rp_pos = [int(_rp['pos'][0]), int(_rp['pos'][1])]
                    _vk = panels.get('virtual_keyboard', {})
                    if isinstance(_vk, dict):
                        if 'visible' in _vk:
                            self.show_virtual_keyboard = bool(_vk['visible'])
                        if isinstance(_vk.get('pos'), list) and len(_vk['pos']) == 2:
                            self.vk_pos = [int(_vk['pos'][0]), int(_vk['pos'][1])]
                    _mp = panels.get('metrics', {})
                    if isinstance(_mp, dict):
                        if 'visible' in _mp:
                            self.show_metrics_panel = bool(_mp['visible'])
                        if isinstance(_mp.get('pos'), list) and len(_mp['pos']) == 2:
                            self.mp_pos = [int(_mp['pos'][0]), int(_mp['pos'][1])]

                last_path = config.get('last_file_path')

                # 恢复教程进度（闯关模式）——无论棋盘状态如何都需还原
                tut = config.get('tutorial')
                if isinstance(tut, dict) and hasattr(self, 'tut_progress'):
                    # subcompleted：各关已完成的小关列表（闯关解锁依据）。
                    # 必须一并还原，否则每次重启关卡内进度归零、小关重新锁上。
                    sub = tut.get('subcompleted')
                    subcompleted = {}
                    if isinstance(sub, dict):
                        for k, v in sub.items():
                            if isinstance(v, list) and str(k).lstrip('-').isdigit():
                                subcompleted[int(k)] = [str(s) for s in v]
                    # best_scores：各小关最高分（键为子题 id，如 '2.1'）
                    bs = tut.get('best_scores')
                    best_scores = {}
                    if isinstance(bs, dict):
                        for k, v in bs.items():
                            if isinstance(v, (int, float)):
                                best_scores[str(k)] = int(v)
                    self.tut_progress = {
                        'started': bool(tut.get('started', False)),
                        'skipped': bool(tut.get('skipped', False)),
                        'completed': [int(x) for x in tut.get('completed', []) if isinstance(x, (int, float))],
                        'current': tut.get('current'),
                        'subcompleted': subcompleted,
                        'best_scores': best_scores,
                    }

                if last_path and os.path.exists(last_path):
                    with open(last_path, 'r', encoding='utf-8') as f:
                        save_data = json.load(f)
                    self._load_save_data(save_data)
                    # 恢复 zoom
                    if 'zoom' in config:
                        self.zoom = config['zoom']
                    # 恢复相机位置：如果有保存的 camera_x/y 则直接恢复，否则用 center_map
                    if 'camera_x' in config and 'camera_y' in config:
                        self.camera_x = config['camera_x']
                        self.camera_y = config['camera_y']
                        # 检查是否超出当前窗口范围（窗口大小可能已改变）
                        if not self._is_camera_valid():
                            self.center_map()
                    else:
                        self.center_map()
                    # 恢复求解算法选择
                    if 'solver_algorithm' in config:
                        self.solver_algorithm = config['solver_algorithm']
                    # 着色器开关
                    if 'coloring_enabled' in config:
                        self.coloring_enabled = bool(config['coloring_enabled'])
                    # 悬停连锁提示开关
                    if 'chain_hint_enabled' in config:
                        self.chain_hint_enabled = bool(config['chain_hint_enabled'])
                    # 存档只读开关（保存时给存档打只读标记）
                    if 'save_readonly_flag' in config:
                        self.save_readonly_flag = bool(config['save_readonly_flag'])
                    # 防止覆盖开关（Ctrl+S 一律进入另存为）
                    if 'prevent_overwrite_flag' in config:
                        self.prevent_overwrite_flag = bool(config['prevent_overwrite_flag'])
                    # 恢复聚拢参数（缺失的键用默认值）
                    if 'gather_params' in config and isinstance(config['gather_params'], dict):
                        defaults = getattr(self, 'gather_params', {})
                        defaults.update({k: v for k, v in config['gather_params'].items()
                                         if k in defaults})
                        self.gather_params = defaults
                    # 恢复聚拢参数启用标志
                    if 'gather_enabled' in config and isinstance(config['gather_enabled'], dict):
                        de = getattr(self, 'gather_enabled', {})
                        de.update({k: bool(v) for k, v in config['gather_enabled'].items()
                                   if k in de})
                        self.gather_enabled = de
                    # temp_history_path 是自动保存，不算用户手动打开的文件
                    self.current_file_path = None
                    # 未存檔的自动恢复默认可写（不受 save_readonly_flag 限制）
                    self._readonly = False
                    print(f"已从文件恢复: {last_path}")
                    self._reset_file_dirty()
                    return
            except Exception as e:
                print(f"加载上次状态失败: {e}")

        # 都没有，使用默认初始化
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._reset_file_dirty()

    def _build_save_data(self) -> dict:
        """构建当前游戏状态的保存数据"""
        self.game.update_matrix()
        history_data = {
            'history_index': self.game_history.history_index,
            'snapshots': []
        }
        for snap in self.game_history.history:
            snap_data = {
                'matrix': snap['matrix'],
                'bounds': snap['bounds']
            }
            if snap.get('move_info'):
                snap_data['move_info'] = snap['move_info']
            # 合并快照：逐步动作日志与步数（会话标识不入盘，载入后不承接旧会话）
            if snap.get('moves'):
                snap_data['moves'] = snap['moves']
            if snap.get('steps'):
                snap_data['steps'] = snap['steps']
            if snap.get('step_total'):
                snap_data['step_total'] = snap['step_total']
            if snap.get('numbers'):
                snap_data['numbers'] = snap['numbers']
            history_data['snapshots'].append(snap_data)
        numbered = bool(getattr(self, 'numbered', False))
        triangle = bool(getattr(self, 'triangle_mode', False))
        mi = bool(getattr(self, 'mi_mode', False))
        data = {
            # 带序号/三角形/米字格谜题写 v2（puzzle.type 标明形态）；普通方形保持 v1 不变
            'version': 2 if (numbered or triangle or mi) else 1,
            'puzzle': {
                'm': self.current_m,
                'n': self.current_n,
                'step': self.current_step
            },
            'step_count': self.step_count,
            'history': history_data
        }
        if numbered:
            data['puzzle']['type'] = 'numbered'
        if triangle:
            data['puzzle']['type'] = 'triangle'
            data['puzzle']['triangle_side'] = self.game.k
        if mi:
            data['puzzle']['type'] = 'mi'
        if getattr(self, 'save_readonly_flag', False):
            data['readonly'] = True
        return data

    def _load_save_data(self, save_data: dict):
        """从保存数据恢复游戏状态"""
        # 载入会整体替换棋盘 → 结束进行中的标注会话
        self._ann_cancel_session('载入存档')
        # 载入只读标志：带 readonly:true 的存档载入后为只读
        self._readonly = bool(save_data.get('readonly', False))
        version = int(save_data.get('version', 1))
        puzzle = save_data.get('puzzle', {})
        m = puzzle.get('m', 4)
        n = puzzle.get('n', 4)
        step = puzzle.get('step', 2)
        kind = 'square'
        if version >= 2:
            kind = puzzle.get('type', 'square')
        # v1 存档的 snapshots 若带 numbers（搭便车存档），也按带序号还原
        self.numbered = kind == 'numbered' or any(
            snap.get('numbers') for snap in save_data.get('history', {}).get('snapshots', []))
        # 三角形密铺：mode 标记 + 大三角形边长（k 缺省时退回 m）
        self.triangle_mode = kind == 'triangle'
        # 米字格：mode 标记；切回别的形态时必须一起清掉，否则旧旗标会让
        # 渲染/命中继续走米字格分支
        self.mi_mode = kind == 'mi'
        triangle_side = puzzle.get('triangle_side', m)

        self.current_m = m
        self.current_n = n
        self.current_step = step

        self.game_history.reset()
        history_data = save_data.get('history', {})
        snapshots = history_data.get('snapshots', [])
        for i, snap in enumerate(snapshots):
            move_info = snap.get('move_info')
            moves = snap.get('moves')
            if moves is None:
                # 旧存档：每快照一步
                moves = [move_info] if move_info else []
            entry = {
                'matrix': snap['matrix'],
                'bounds': snap['bounds'],
                'move_info': move_info,
                'moves': moves,
                'steps': snap.get('steps', 1 if move_info else 0),
                # 旧存档无该字段：参考态在第 0 条，第 i 条即 i 步
                'step_total': snap.get('step_total', i),
                # 载入后不承接旧选中会话，避免与后续移动误合并
                'session_key': None,
            }
            if snap.get('numbers'):
                entry['numbers'] = snap['numbers']
            self.game_history.history.append(entry)
        self.game_history.history_index = history_data.get('history_index', 0)
        # 步数以历史累计值为准（合并快照一条覆盖多步，不能再按索引算）
        self.step_count = self.game_history.current_step_total()

        # 从快照重建游戏状态（依版本/形態分派）
        self.game = create_puzzle(m, n, step, kind=kind, triangle_side=triangle_side)
        if kind == 'triangle':
            self.current_m = self.current_n = self.game.k
            # 载入后按当前棋盘大小重新适配缩放并居中（存档不保存 zoom）
            self.zoom = self._fit_triangle_zoom()
            self.center_map()
        elif kind == 'mi':
            # 米字格同理：包围盒走 mi_view（世界坐标无 gap 间距）
            self.zoom = self._fit_mi_zoom()
            self.center_map()
        self.game_history.restore_snapshot(self.game, self.game_history.history_index)

        self.selected_gap = None
        self.selected_block = None
        self._mi_gap_point = None
        self.animating = False
        self.anim_blocks = []

    def save_to_file(self):
        """保存到当前文件（Ctrl+S）"""
        # 防止覆盖开关：打开后即使已有存档路径，Ctrl+S 也一律进入另存为
        if getattr(self, 'prevent_overwrite_flag', False) and self.current_file_path:
            self.save_as()
        elif self.current_file_path:
            self._save_to_path(self.current_file_path)
        else:
            self.save_as()

    def _default_save_name(self) -> str:
        """自动命名：形态标记-step-m-n-日期时间.json（24小时制），
        如 mi-1-2-2-20260922-112821.json；矩形不加标记（保持旧名 2-6-6-…），
        米字格 mi、三角形 tri、带序号 num 按序追加（可叠加，如 tri-num-…）。

        标记放最前面：四种形态的 step-m-n 完全同形（都是 1-6-6 这种），
        放在中段会被尺寸数字淹没，扫一眼分不出是哪一局。
        """
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        marks = []
        if getattr(self, 'mi_mode', False):
            marks.append('mi')
        if getattr(self, 'triangle_mode', False):
            marks.append('tri')
        if getattr(self, 'numbered', False):
            marks.append('num')
        tag = ('-'.join(marks) + '-') if marks else ''
        return f"{tag}{self.current_step}-{self.current_m}-{self.current_n}-{ts}.json"

    def save_as(self):
        """另存为：弹出 pygame 文件对话框（默认名自动生成）"""
        self.file_dialog.show(
            mode='save',
            title='另存为',
            initial_dir=self.save_dir,
            extensions=['json'],
            initial_file=self._default_save_name()
        )
        self._pending_save_as = True

    def _save_to_path(self, path: str):
        """将当前状态保存到指定路径"""
        save_data = self._build_save_data()
        try:
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(_compact_json_dumps(save_data))
            self.current_file_path = path
            self._saved_board_version = self._board_version
            self._update_window_title()
            self.macro_notify_msg = f"已保存：{os.path.basename(path)}"
            self.macro_notify_timer = 120
            print(f"游戏已保存到 {path}")
        except Exception as e:
            print(f"保存失败: {e}")

    def load_from_file(self):
        """从文件打开：弹出 pygame 文件对话框"""
        # 竞速模式全程禁止打开存档（否则可加载已复原存档直接判胜）
        if self._timer_blocked():
            self.macro_notify_msg = "竞速模式中无法打开存档"
            self.macro_notify_timer = 90
            return
        self.file_dialog.show(
            mode='open',
            title='打开',
            initial_dir=self.save_dir,
            extensions=['json']
        )
        self._pending_load = True

    def handle_file_dialog_result(self):
        """处理文件对话框结果"""
        if not self.file_dialog.active:
            if getattr(self, '_pending_save_as', False):
                self._pending_save_as = False
                if self.file_dialog.result:
                    self._save_to_path(self.file_dialog.result)
                    self.save_dir = os.path.dirname(self.file_dialog.result)
            if getattr(self, '_pending_load', False):
                self._pending_load = False
                if self.file_dialog.result:
                    self._do_load_from_path(self.file_dialog.result)

    def _do_load_from_path(self, path: str):
        """从指定路径加载游戏（竞速模式下拒绝，防加载已复原存档判胜）"""
        # 载入会替换棋盘 → 打断连续撤销/重做
        self._stop_continuous_undo_redo()
        # 载入新棋盘 → 清掉上一次的计时成绩
        self._last_timed_result = None
        if self._timer_blocked():
            self.macro_notify_msg = "竞速模式中无法打开存档"
            self.macro_notify_timer = 90
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            self._load_save_data(save_data)
            # 打开的是另一张图，当前 camera 可能是针对上一张图的 →
            # 若滑块组已不在视口内则重新居中，避免打开后看不见滑块组
            if not self._is_camera_valid():
                self.center_map()
            self.current_file_path = path
            self.save_dir = os.path.dirname(path)
            self.macro_notify_msg = f"已打开：{os.path.basename(path)}"
            self.macro_notify_timer = 120
            print(f"游戏已从 {path} 加载")
            self._reset_file_dirty()
        except FileNotFoundError:
            print("未找到文件")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"文件格式错误: {e}")

    def export_map(self):
        """兼容旧终端指令：保存到当前文件或另存为"""
        self.save_to_file()

    def import_map(self):
        """兼容旧终端指令：从文件打开"""
        self.load_from_file()
