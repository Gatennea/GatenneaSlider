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
import hashlib
import pygame
from puzzle_types import create_puzzle
from gui.compressed_save import (is_compressed, load_compressed_into_gui,
                                 compress_from_game, convert_save_file)
from history import (validate_snapshot, groups_to_json, groups_from_json)
from gui import cubic_settings


def _compute_checksum(data: dict) -> str:
    """对 puzzle+history 序列化文本算 SHA256（排除 checksum 自身），存档完整性校验。"""
    payload = {k: v for k, v in data.items() if k != 'checksum'}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _preview_kind() -> str:
    """搭积木编辑器预览局的哨兵形态名（单一真源在 gui/model_editor.py）。

    延迟导入：file_ops 是 Mixin，GUI 启动时先于编辑器模块被导入；这里
    只为了拿一个常量，不值得让两个模块在导入期互相牵扯。
    """
    from gui.model_editor import PREVIEW_KIND
    return PREVIEW_KIND


class StaleEditorSave(ValueError):
    """上次退出时停在搭积木编辑器里：存档里的形态是预览哨兵，不可载入。

    这类存档**不是损坏，也不该报「模型未安装」**——编辑器预览局从来没有
    对应的 models/*.json，载入端要把它当「无事发生」（安静回落到默认局）。

    继承 ValueError：`_do_load_from_path` 的「打开失败：…」分支只捕
    (JSONDecodeError, KeyError, ValueError)，用户真去文件对话框点开一份
    `__editor__` 存档时要落到那条提示里，而不是冒到事件循环变成
    「Event error (non-fatal)」。
    """


class StaleCubicSave(StaleEditorSave):
    """上次退出时停在**三维局**：`type: cubic` 的存档，现在读不回来。

    三维读回要扩到 (r,c,d) 与 `type: cubic`（方案第 5 步）。在那之前写进
    temp_history 的 cubic 局不该报「存档需要模型 'cubic'」——那是自造的坏档
    （2026-11-17 用户实测每次启动都弹）。按编辑器先例当「无事发生」：安静
    回落到默认二维局，并把这条坏档用新局覆盖掉（自愈）。
    """

# 已从注册表移除的**形态专用入口** → 现行统一入口。
# 2026-10-05 起三形态共用 `'gather'`，`tri_gather` / `mi_gather` 两个 key 已删除；
# 但老 config.json 里仍写着这些值（用户机器上实测就是 `'mi_gather'`）。
# 不迁移的话 solve_thread 会拿到一个**不存在的 key** —— 旧行为是静默兜底成
# IDA*，而 IDA* 是纯方形语义，落到异形 game 上直接抛异常（2026-10-06 用户
# 报的「list index out of range」就是这条链）。
_LEGACY_SOLVER_ALGORITHM = {
    'tri_gather': 'gather',
    'mi_gather': 'gather',
    # 填洞宏已并入补缺宏（菜单改叫「填洞补缺」）：老配置里选了它的迁移过去，
    # 否则界面会显示一个已经不存在的算法 key。
    'fill_macro': 'gap_macro',
    # 旧搜索三项已从 GUI 隐藏（低效、沉底备查；2026-11-13 用户拍板）：
    # 老 config 若选着它们，迁到默认的混合求解，免得界面显示一个不在
    # 列表里的 key（点开设置看不到任何选中项）。key 本身仍在注册表。
    'ida_star': 'hybrid',
    'fast': 'hybrid',
    'greedy': 'hybrid',
}


def _migrate_solver_algorithm(value):
    """把失效的旧算法 key 迁到现行 key；认不出的原样返回（由后续校验拦下）。"""
    return _LEGACY_SOLVER_ALGORITHM.get(value, value)


# Windows 文件名禁止字符（含这些字符写盘必抛 OSError，此前只 print 用户看不到）
ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'


def _find_illegal_filename_chars(name: str) -> list:
    """返回文件名中出现的 Windows 非法字符（去重保序），合法名返回空列表"""
    seen = []
    for ch in name:
        if ch in ILLEGAL_FILENAME_CHARS and ch not in seen:
            seen.append(ch)
    return seen


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
def _key_text(key):
    """配置里的键名 → 菜单上显示的写法。

    单字母大写（z → Z）；功能键也大写（f12 → F12，别在菜单里显示小写 f12）；
    其余多字母键名（pageup 等）原样给，交给调用方的映射表处理。
    """
    key = str(key or '')
    if len(key) == 1:
        return key.upper()
    if key.startswith('f') and key[1:].isdigit():
        return key.upper()
    return key


DEFAULT_KEYBINDINGS = {    'undo': {'key': 'z', 'modifiers': ['ctrl']},
    'redo': {'key': 'x', 'modifiers': ['ctrl']},
    'shuffle': {'key': 's', 'modifiers': ['alt']},
    'reset': {'key': 'r', 'modifiers': ['ctrl']},
    'save': {'key': 's', 'modifiers': ['ctrl']},
    'load': {'key': 'o', 'modifiers': ['ctrl']},
    # 截图：画面存成 PNG（F12 是窗口截图类工具的行规键位）
    'screenshot': {'key': 'f12', 'modifiers': []},
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
    # 命令面板：功能可发现性主入口（Ctrl+K 是命令面板的通用键位，别挪作他用）
    'command_palette': {'key': 'k', 'modifiers': ['ctrl']},
}


class FileOpsMixin:
    """文件操作相关方法 Mixin"""

    def save_config(self):
        """保存配置到 config/config.json，历史记录到 config/temp_history.json，快捷键到 keyboard_shortcut.json

        ⚠️ **搭积木编辑器会话中不写历史**（2026-10-25 用户实测）：那时候
        ``self.game`` 是预览局（``kind = PREVIEW_KIND``），写下去就是一条
        ``type: '__editor__'`` 的存档——它没有模型文件，下次启动必然
        「存档需要模型 '__editor__'，但它没有安装」。temp_history 保留进入
        编辑器之前的那个真实局面（退出/崩溃都不丢东西），配置照写。

        ⚠️ **三维局（cubic_mode）现在可以正常存**（2026-11-18，§54 第 5 步）：存档
        带 ``type: cubic`` + ``depth``，快照走无损键表 ``engine_state``
        （``[r,c,d,gid]``），读回重建三维局。这条规则之前是「跳过不写」，现在
        撤掉了——再跳过就等于退出即丢三维进度。
        """
        os.makedirs(self.config_dir, exist_ok=True)

        # 保存历史记录到 temp_history.json（编辑器预览局跳过，见 docstring）
        skip_temp = getattr(self, '_med_active', False)
        if not skip_temp:
            save_data = self._build_save_data()
            try:
                with open(self.temp_history_path, 'w', encoding='utf-8') as f:
                    f.write(_compact_json_dumps(save_data))
            except Exception as e:
                print(f"保存临时历史记录失败: {e}")

        # 始终以 temp_history_path 作为 last_file_path
        # 这样重启时必定加载退出瞬间的最新状态
        # 三维相机姿态：四元数就是姿态本身（不另存 yaw/pitch，免得两处口径打架）
        _cam = getattr(self, 'cubic_camera', None)
        _quat = tuple(getattr(_cam, 'q', (1.0, 0.0, 0.0, 0.0)))

        config = {
            'animation_speed': self.animation_duration,
            'zoom': self.zoom,
            'last_file_path': self.temp_history_path,
            'camera_x': self.camera_x,
            'camera_y': self.camera_y,
            # 三维相机组（§54 第 2 步）：姿态 + 缩放 + 拆分单独一组，
            # 与二维 camera_x/y、zoom 互不覆盖（按形态分组，方案 §2.2 口径）
            'cubic_camera': dict(
                {
                    'quat': [round(float(v), 6) for v in _quat],
                    'zoom': round(float(getattr(self, 'cubic_zoom', 1.0)), 3),
                    'view': getattr(self, 'cubic_view_index', None),
                },
                # 拆分 / 切面透明度 / 双击时间窗 / 旋转灵敏度：全部由声明式表导出，
                # 加选项不用再回来改这里（方案 §2.4「登记机制」）。
                **cubic_settings.serialize(self),
            ),
            # 三维**局本身**也要进配置（2026-11-18 用户报「config.json 没存
            # 三维滑块的信息」）：只存相机/选项时，配置里没有任何 m×n×d 与
            # 等级，退出后连「上次在玩哪个三维局」都不知道，只能靠 temp_history
            # 的存档兜；而那个存档一旦失效（旧档/被覆盖），就会退回方形局。
            # 这里存的是「上次三维局的尺寸与等级」，启动时按存档优先、配置兜底。
            'cubic_puzzle': (
                {
                    'm': int(getattr(self, 'current_m', 0)),
                    'n': int(getattr(self, 'current_n', 0)),
                    'd': int(getattr(self, 'current_depth', 0)),
                    'step': int(getattr(self, 'current_step', 1)),
                }
                if getattr(self, 'cubic_mode', False) else None
            ),
            # 三维视图平移（屏幕像素偏移）：用户手拖过就记下来，重启还在原处。
            # 与相机姿态分开存——姿态是「看的方向」，平移是「盘在屏幕上的位置」。
            'cubic_pan': [round(float(v), 1)
                          for v in (getattr(self, 'cubic_pan', None) or (0.0, 0.0))],
            # 跟随质心：手动平移会暂停它，重启要还原「暂停/开启」这一状态，
            # 否则玩家挪好的位置一启动又被拉回中心。
            'cubic_follow_centroid': bool(
                getattr(self, 'cubic_follow_centroid', True)),
            'solver_algorithm': getattr(self, 'solver_algorithm', 'ida_star'),
            'coloring_enabled': getattr(self, 'coloring_enabled', False),
            'chain_hint_enabled': getattr(self, 'chain_hint_enabled', False),
            'gap_hover_flash_enabled': getattr(self, 'gap_hover_flash_enabled', True),
            'solver_log_enabled': getattr(self, 'solver_log_enabled', False),
            'board_marks_enabled': getattr(self, 'board_marks_enabled', True),
            'arrows_enabled': getattr(self, 'arrows_enabled', True),
            'save_readonly_flag': getattr(self, 'save_readonly_flag', False),
            'prevent_overwrite_flag': getattr(self, 'prevent_overwrite_flag', False),
            'op_log_enabled': getattr(self, 'op_log_enabled', False),
            'boot_animation': getattr(self, 'show_boot_animation', True),
            'infinite_shuffle': getattr(self, 'infinite_shuffle', False),
            'confirm_before_shuffle': getattr(self, 'confirm_before_shuffle', True),
            'draw_grid': getattr(self, 'draw_grid', True),
            'anti_drift_enabled': getattr(self, 'anti_drift_enabled', True),
            'thinking_enabled': getattr(self, 'thinking_enabled', True),
            'use_compressed_save': getattr(self, 'use_compressed_save', False),
            # 音效（见 gui/audio.py / docs S5）
            'sfx_enabled': getattr(self, 'sfx_enabled', True),
            'music_enabled': getattr(self, 'music_enabled', True),
            'sound_muted': getattr(self, 'sound_muted', False),
            'sfx_volume': int(getattr(self, 'sfx_volume', 70)),
            'music_volume': int(getattr(self, 'music_volume', 50)),
            # 逐项音效开关（设置页「音效一览」）
            'sfx_slide_enabled': getattr(self, 'sfx_slide_enabled', True),
            'sfx_fail_enabled': getattr(self, 'sfx_fail_enabled', True),
            'sfx_solved_enabled': getattr(self, 'sfx_solved_enabled', True),
            'sfx_click_enabled': getattr(self, 'sfx_click_enabled', True),
            'sfx_keyboard_enabled': getattr(self, 'sfx_keyboard_enabled', True),
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
            '另存为...',
            '存档转换...',
            # 间接自举重启：点下去会 spawn 看门进程等本进程退出后自动重拉起，
            # 见 gui/restart.py。游戏自己不能重启自己，故走独立进程。
            '重启（自动重开）',
            # 截图：把当前画面存成 PNG（screenshots/ 下自动命名）。此前只有
            # 外部控制（HTTP/stdin）能截，玩家在游戏里没法触发。
            f"截图 {self._format_menu_shortcut('screenshot')}",
        ]
        self.edit_menu_items = [
            f"撤销 {self._format_menu_shortcut('undo')}",
            f"重做 {self._format_menu_shortcut('redo')}",
            f"打乱 {self._format_menu_shortcut('shuffle')}",
            f"重置 {self._format_menu_shortcut('reset')}",
            '---',
            # 视图操作：把滑块组拉回屏幕中央（撤销/重做等坐标漂移跑出视口时手动救回）
            '居中',
            # 自动求解必须留在最后一项：主循环按 edit_menu_items[-1]
            # 把它改成「停止求解」
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
        parts.append(key_display.get(key, _key_text(key)))
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
                # 旧档里的 'ui_mode' 键直接忽略（2026-11-17 界面模式已删）
                if 'zoom' in config:
                    self.zoom = config['zoom']

                # 三維相机组（§54 第 2 步）：只记下数值，建三维局时才套用
                # （二维局不该被三维姿态影响；这里不新建三维对象）
                cc = config.get('cubic_camera')
                if isinstance(cc, dict):
                    prefs = {}
                    quat = cc.get('quat')
                    if (isinstance(quat, (list, tuple)) and len(quat) == 4
                            and all(isinstance(v, (int, float))
                                    and not isinstance(v, bool) for v in quat)):
                        prefs['quat'] = [float(v) for v in quat]
                    # 三维选项：按声明式表保留全部数值键（以前只手抄 zoom/gap，
                    # 结果 seam_alpha / rot_sensitivity / cubic_anim_ms 读盘即丢）。
                    for _meta in cubic_settings.CUBIC_SETTINGS:
                        _key = _meta['key']
                        val = cc.get(_key)
                        if isinstance(val, (int, float)) and not isinstance(val, bool):
                            prefs[_key] = float(val)
                    view = cc.get('view')
                    if isinstance(view, int) and 0 <= view < 6:
                        prefs['view'] = view
                    self._cubic_camera_prefs = prefs

                # 上次在玩的三维局本身（尺寸 m×n×d 与等级）：temp_history 读不回来
                # 时靠它兜底重建，否则一重启就退回方形局（用户 2026-11-18 报）。
                cpz = config.get('cubic_puzzle')
                if isinstance(cpz, dict):
                    try:
                        vals = [int(cpz.get(k)) for k in ('m', 'n', 'd', 'step')]
                    except (TypeError, ValueError):
                        vals = None
                    if vals and all(v >= 1 for v in vals[:3]) \
                            and 1 <= vals[3] < max(vals[:3]):
                        self._cubic_puzzle_prefs = {
                            'm': vals[0], 'n': vals[1],
                            'd': vals[2], 'step': vals[3]}

                pan = config.get('cubic_pan')
                if isinstance(pan, (list, tuple)) and len(pan) == 2 \
                        and all(isinstance(v, (int, float))
                                and not isinstance(v, bool) for v in pan):
                    self._cubic_pan_prefs = [float(pan[0]), float(pan[1])]
                if 'cubic_follow_centroid' in config:
                    self._cubic_follow_prefs = bool(config['cubic_follow_centroid'])

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

                # S0-2：从存档恢复面板坐标后，立即拉回可视范围
                # （非全屏/缩放后不再越界；依赖 screen/menu/status 高度已初始化）
                if all(hasattr(self, a) for a in ('screen_width', 'menu_bar_height', 'status_bar_height')):
                    if hasattr(self, '_vk_clamp_position'): self._vk_clamp_position()
                    if hasattr(self, '_mp_clamp_position'): self._mp_clamp_position()
                    if hasattr(self, '_rp_clamp_position'): self._rp_clamp_position()

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
                        # 迁移失效的旧形态专用 key（'tri_gather'/'mi_gather'
                        # → 'gather'）；不迁移会让求解拿到不存在的算法 key。
                        self.solver_algorithm = _migrate_solver_algorithm(
                            config['solver_algorithm'])
                    # 着色器开关
                    if 'coloring_enabled' in config:
                        self.coloring_enabled = bool(config['coloring_enabled'])
                    # 悬停连锁提示开关
                    if 'chain_hint_enabled' in config:
                        self.chain_hint_enabled = bool(config['chain_hint_enabled'])
                    # 悬停缝隙闪烁开关（缺省开；旧档没有该键就保持默认）
                    if 'gap_hover_flash_enabled' in config:
                        self.gap_hover_flash_enabled = bool(
                            config['gap_hover_flash_enabled'])
                    # 求解器日志开关（2026-11-14 新增；旧档没有该键保持默认关）
                    if 'solver_log_enabled' in config:
                        self.solver_log_enabled = bool(
                            config['solver_log_enabled'])
                    # 棋盘标记开关（视觉强化，独立于调试面板本体；缺省开）
                    if 'board_marks_enabled' in config:
                        self.board_marks_enabled = bool(config['board_marks_enabled'])
                    # 箭头按键开关（缺省开）
                    if 'arrows_enabled' in config:
                        self.arrows_enabled = bool(config['arrows_enabled'])
                    # 开机动画开关（缺省开）
                    if 'boot_animation' in config:
                        self.show_boot_animation = bool(config['boot_animation'])
                    # 无限打乱开关（缺省关）
                    if 'infinite_shuffle' in config:
                        self.infinite_shuffle = bool(config['infinite_shuffle'])
                    # 防意外打乱开关（缺省开）
                    if 'confirm_before_shuffle' in config:
                        self.confirm_before_shuffle = bool(config['confirm_before_shuffle'])
                    if 'draw_grid' in config:
                        self.draw_grid = bool(config['draw_grid'])
                    if 'anti_drift_enabled' in config:
                        self.anti_drift_enabled = bool(config['anti_drift_enabled'])
                    if 'thinking_enabled' in config:
                        self.thinking_enabled = bool(config['thinking_enabled'])
                    # 音效开关（见 gui/audio.py / docs S5）
                    if 'sfx_enabled' in config:
                        self.sfx_enabled = bool(config['sfx_enabled'])
                    if 'music_enabled' in config:
                        self.music_enabled = bool(config['music_enabled'])
                    if 'sound_muted' in config:
                        self.sound_muted = bool(config['sound_muted'])
                    if 'sfx_volume' in config:
                        self.sfx_volume = int(config['sfx_volume'])
                    if 'music_volume' in config:
                        self.music_volume = int(config['music_volume'])
                    # 逐项音效开关（旧档没有这些键就保持默认开）
                    for _slot_key in ('slide', 'fail', 'solved', 'click', 'keyboard'):
                        _cfg_key = f'sfx_{_slot_key}_enabled'
                        if _cfg_key in config:
                            setattr(self, _cfg_key, bool(config[_cfg_key]))
                    # 把读到的音效设置推送给音频管理器
                    sync = getattr(self, '_sync_audio_settings', None)
                    if callable(sync):
                        sync()
                    # 存档只读开关（保存时给存档打只读标记）
                    if 'save_readonly_flag' in config:
                        self.save_readonly_flag = bool(config['save_readonly_flag'])
                    # 防止覆盖开关（Ctrl+S 一律进入另存为）
                    if 'prevent_overwrite_flag' in config:
                        self.prevent_overwrite_flag = bool(config['prevent_overwrite_flag'])
                    # 操作日志开关（默认关；由 GUI.__init__ 末尾调 set_enabled 生效）
                    if 'op_log_enabled' in config:
                        self.op_log_enabled = bool(config['op_log_enabled'])
                    # 压缩存档开关（矩形谜题保存为 replay 压缩格式）
                    if 'use_compressed_save' in config:
                        self.use_compressed_save = bool(config['use_compressed_save'])
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
            except StaleEditorSave as e:
                # 编辑器预览局 / 三维局不是「坏存档」：安静退回默认局，不吓人
                print(f"忽略上次状态（{e}）")
                self._stale_autosave = True
            except Exception as e:
                print(f"加载上次状态失败: {e}")

        # 都没有，使用默认初始化
        # 先**真的**回到启动参数那套局：构造期可能已经从上一份配置恢复成三维，
        # 那条读不回来的旧档若直接「保留现状」，就等于把坏档当成了默认局。
        _boot = getattr(self, '_boot_puzzle_args', None)
        if _boot and len(_boot) == 4:
            _m0, _n0, _s0, _k0 = _boot
            if _k0 in ('square', 'numbered') and (
                    self._current_kind() not in ('square', 'numbered')
                    or (self.current_m, self.current_n, self.current_step)
                    != (_m0, _n0, _s0)):
                self.new_puzzle(_m0, _n0, _s0, numbered=(_k0 == 'numbered'))
        cpz = getattr(self, '_cubic_puzzle_prefs', None)
        if cpz and not getattr(self, 'cubic_mode', False):
            # 上次是三维局、但那条自动存档读不回来（旧档/损坏/被覆盖）：
            # 按 config 里记下的尺寸重建同一个三维局，别让玩家一启动就发现
            # 「我的三维盘不见了」。重建后 history 从还原态起一条，不会串档。
            try:
                if self.new_cubic_puzzle(cpz['m'], cpz['n'], cpz['d'], cpz['step']):
                    self._reset_file_dirty()
                    print(f"三维局按配置重建：{cpz['m']}×{cpz['n']}×{cpz['d']} "
                          f"等级{cpz['step']}")
                    return
            except Exception as e:      # noqa: BLE001
                print(f'按配置重建三维局失败，回落默认局: {e}')
        self.center_map()
        self.game_history.save_snapshot(self.game)
        self._reset_file_dirty()
        if getattr(self, '_stale_autosave', False):
            # 自愈：把那条读不回来的 temp_history 用当前默认局覆盖掉，
            # 否则每次启动都要再撞一次（编辑器先例同口径）。
            self._stale_autosave = False
            try:
                save_data = self._build_save_data()
                with open(self.temp_history_path, 'w', encoding='utf-8') as f:
                    f.write(_compact_json_dumps(save_data))
                print('已用当前局面覆盖上次那条读不回的自动存档')
            except Exception as e:
                print(f'覆盖自动存档失败: {e}')

    def _check_saved_model_identity(self, kind, info):
        """模型局存档：认出「模型缺失」与「模型已变更」。

        缺失 → **明确抛错**（绝不回退成方形：48 块变 16 块那条旧坑）。
        变更 → 提示后继续（旧档仍尽量读出来，但快照 matrix 的朝向编码是
        按 `orientations` 顺序写的，顺序一变块的角色就会错位）。
        """
        from engine import model_registry
        try:
            m = model_registry.loaded(kind)
        except KeyError:
            errs = model_registry.errors()
            raise ValueError(
                f'存档需要模型 {kind!r}，但它没有安装（或被物理公理校验拒绝）。'
                f'请确认 models/{kind}.json 存在。'
                f'（加载期记录：{"；".join(errs) if errs else "无"}）') from None
        want = info.get('hash')
        if want and want != m.hash():
            self.macro_notify_msg = (
                f'模型 {kind} 与存档时不一致（内容已改动），旧档的朝向可能有偏移')
            self.macro_notify_timer = 240

    def _cubic_camera_pref(self, prefs=None):
        """按存档选默认相机：只认明确选过的 1–6 朝向，自由旋转不恢复。

        2026-11-18 用户报「默认载入还是个斜放的」：旧逻辑会把 config 里
        退出时的任意四元数当默认，拖到滚转 80° 的姿态也会被下次开局继承。
        新建/载入三维局一律回到参考图校准过的斜视；只有玩家按过 1–6 选了
        某个朝向，才把那个朝向（含统一 14° 倾斜）带回来。
        """
        from engine.cubic_camera import CubicCamera, FACE_VIEW_LABELS
        prefs = (prefs if prefs is not None
                 else getattr(self, '_cubic_camera_prefs', None) or {})
        view = prefs.get('view')
        if (isinstance(view, int) and not isinstance(view, bool)
                and 0 <= view < len(FACE_VIEW_LABELS)):
            return (CubicCamera.from_view_angles(view),
                    FACE_VIEW_LABELS[view], view)
        return CubicCamera.oblique_default(), '斜视', None

    def _cubic_load_defaults(self, load: bool = False):
        """载入三维存档后把三维专属的 GUI 状态补齐（相机/缩放/拆分/平移/键盘）。"""
        from engine.cubic_view import DEFAULT_GAP
        prefs = getattr(self, '_cubic_camera_prefs', None) or {}
        cam, label, view_idx = self._cubic_camera_pref(prefs)
        self.cubic_camera = cam
        self.cubic_view_label = label
        self.cubic_view_index = view_idx
        self.cubic_zoom = 1.0
        zoom = prefs.get('zoom')
        if zoom is not None:
            lo, hi = self.CUBIC_ZOOM_RANGE
            self.cubic_zoom = max(lo, min(hi, zoom))
        gap = prefs.get('gap')
        self.cubic_gap = gap if (gap is not None and 1e-6 < gap < 1.0) else DEFAULT_GAP
        # 其余三维选项走声明式表（越界夹紧、缺项保默认）
        from gui import cubic_settings
        for _meta in cubic_settings.CUBIC_SETTINGS:
            if _meta['key'] == 'gap':
                continue
            if _meta['key'] in prefs:
                setattr(self, _meta['attr'],
                        cubic_settings.clamp_value(_meta['key'],
                                                   prefs[_meta['key']]))
        self.cubic_pan = [0.0, 0.0]
        _pan0 = getattr(self, '_cubic_pan_prefs', None)
        if isinstance(_pan0, (list, tuple)) and len(_pan0) == 2:
            _lim = 0.55 * max(self.screen_width, self.screen_height)
            self.cubic_pan = [max(-_lim, min(_lim, float(_pan0[0]))),
                              max(-_lim, min(_lim, float(_pan0[1])))]
        _fol = getattr(self, '_cubic_follow_prefs', None)
        self.cubic_follow_centroid = True if _fol is None else bool(_fol)
        # 关闭跟随后冻结的取景：块移动不再改 origin/scale，箭头不会自己跑。
        self._cubic_static_center = None
        self._cubic_static_scale = None
        self.cubic_dragging = False
        self.cubic_drag_moved = False
        self.cubic_drag_start = None
        self.cubic_drag_from = None
        self._cubic_scene = None
        self._cubic_last_click_t = None
        self._cubic_last_click_p = None
        self._cubic_last_click_surface = None
        self.cubic_anim = None
        self.show_virtual_keyboard = True
        self.zoom = 1.0

    def _build_save_data(self) -> dict:
        """构建当前游戏状态的保存数据"""
        self.game.update_matrix()
        # 模型文件板型（碎三角等）：matrix 是「朝向下标+1」编码（质心晶格），
        # 压缩存档的方形公式（0/1 + (r,c) 二元组 canonicalize）一概不适用。
        # 判据是「形态名不在旧四种里」，不是硬编码 'shatter'——否则换一个
        # models/<name>.json 就会被静默当成方形存下去。
        kind_now = self._current_kind()
        is_cubic = kind_now == 'cubic'
        is_model = (kind_now not in ('square', 'numbered', 'triangle', 'mi')
                    and not is_cubic)
        shatter = is_model
        # 矩形谜题 + 开启压缩：直接生成 replay 压缩格式
        # （初始+末态+步骤原语+哈希校验点），异形不受此开关影响
        if getattr(self, 'use_compressed_save', False) and not (
                getattr(self, 'triangle_mode', False) or getattr(self, 'mi_mode', False)
                or shatter or is_cubic):
            try:
                return compress_from_game(self)
            except Exception as e:
                # 压缩失败（理论仅当历史不一致）回退普通格式，保证存档不丢
                print(f"压缩存档生成失败，回退普通格式：{e}")
        history_data = {
            'history_index': self.game_history.history_index,
            'snapshots': []
        }
        for snap in self.game_history.history:
            if snap.get('cubic'):
                # 三维：矩阵是二维口径（没有深度），局面只存无损键表
                snap_data = {'engine_state': snap.get('engine_state'),
                             'cubic': True}
            else:
                snap_data = {
                    'matrix': snap['matrix'],
                    'bounds': snap['bounds']
                }
            # 无损键表（引擎板型专属）：模型板（shield 等）同 2D 格可叠多块
            # （不同朝向），矩阵编码会把同格多块压成一格、还原时永久丢块 →
            # 还原态永不等于目标、判定「未复原」（2026-10-26 用户实测报的 bug）。
            # 内存态 restore_snapshot 本就优先用它，但落盘若不写它，载入只能
            # 回退到 lossy 的 matrix 重建。故模型板每个快照都必须带上。
            es = snap.get('engine_state')
            if es is not None:
                snap_data['engine_state'] = es
            # 捆绑组（自由捆绑 / 高级选项）：{位置:gid} → [[r,c,gid],...]。
            # 不写的话载入后恢复端拿到 None，会把整盘静默拆成散块。
            _groups = groups_to_json(snap.get('groups'))
            if _groups:
                snap_data['groups'] = _groups
            if snap.get('move_info'):
                snap_data['move_info'] = snap['move_info']
            # 合并快照：逐步动作日志与步数（会话标识不入盘，载入后不承接旧会话）
            if snap.get('moves'):
                snap_data['moves'] = snap['moves']
            if snap.get('steps'):
                snap_data['steps'] = snap['steps']
            if snap.get('step_total'):
                snap_data['step_total'] = snap['step_total']
            history_data['snapshots'].append(snap_data)
        numbered = bool(getattr(self, 'numbered', False))
        triangle = bool(getattr(self, 'triangle_mode', False))
        mi = bool(getattr(self, 'mi_mode', False))
        data = {
            # 带序号/三角形/米字格/碎三角谜题写 v2（puzzle.type 标明形态）；
            # 普通方形保持 v1 不变
            'version': 2 if (numbered or triangle or mi or shatter or is_cubic) else 1,
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
        if is_cubic:
            # 三维（§54 第 5 步）：type + 层数。读回时靠这两个字段重新建局，
            # 局面从每条快照的 engine_state 无损还原（[r,c,d,gid] 列表）。
            data['puzzle']['type'] = 'cubic'
            data['puzzle']['depth'] = int(getattr(self.game, 'depth', 0))
        if shatter:
            # 不写 type 的模型局存档会被 v1 口径读成「方形 4×4」——载入即
            # 静默换形态（48 块变 16 块）。type = 模型名，载入时据此
            # 重新注册表取板型。matrix 的值域校验走 validate_snapshot 的
            # else 分支（非负整数），0..24 合法。
            data['puzzle']['type'] = kind_now
            # 模型身份：改名/改几何后旧档还能认出「是哪个盘、什么时候的版本」。
            # hash 不一致不拒绝打开（只提示），模型缺失才拒绝——见 _load_save_data。
            try:
                from engine import model_registry
                m = model_registry.loaded(kind_now)
                data['puzzle']['model'] = {'name': m.name,
                                           'hash': m.hash()}
            except (KeyError, ImportError):
                pass
        # 高级选项自定义样式局：只记预设名（不内嵌样式），导入时按名查
        # config/design_styles/<名>.json 恢复还原目标（D4）。官方预设为 None。
        _preset = getattr(self, '_ann_style_goal', None)
        if _preset:
            data['puzzle']['preset'] = _preset
        if getattr(self, 'save_readonly_flag', False):
            data['readonly'] = True
        data['checksum'] = _compute_checksum(data)
        return data

    def _load_save_data(self, save_data: dict):
        """从保存数据恢复游戏状态"""
        # 压缩存档（replay 格式）：用重放重建历史 + 哈希校验，失败回退末态
        if is_compressed(save_data):
            # 载入会整体替换棋盘 → 结束进行中的标注会话（与普通分支一致）
            self._ann_cancel_session('载入存档')
            if not save_data.get('checksum') or _compute_checksum(save_data) != save_data.get('checksum'):
                raise ValueError('存档校验失败：文件可能已损坏或被修改')
            ok, warn = load_compressed_into_gui(self, save_data)
            if not ok:
                # 公式校验未过 → 已按末态加载（棋盘正确），提示用户
                self.macro_notify_msg = warn
                self.macro_notify_timer = 180
                print(f"压缩存档载入：{warn}")
            # 压缩存档的只读标记同样要应用（与普通分支一致）
            self._readonly = bool(save_data.get('readonly', False))
            self._reset_file_dirty()
            return
        # 载入会整体替换棋盘 → 结束进行中的标注会话
        self._ann_cancel_session('载入存档')
        version = int(save_data.get('version', 1))
        # 完整性校验：带 checksum 的存档必须通过；旧存档无该字段则跳过
        ck = save_data.get('checksum')
        if ck and _compute_checksum(save_data) != ck:
            raise ValueError('存档校验失败：文件可能已损坏或被修改')
        puzzle = save_data.get('puzzle', {})
        m = puzzle.get('m', 4)
        n = puzzle.get('n', 4)
        step = puzzle.get('step', 2)
        # 结构/范围校验：防损坏或篡改的存档产生异常局面（卡死/无法滑动）
        if not isinstance(m, int) or not isinstance(n, int) or not isinstance(step, int):
            raise ValueError('存档参数类型错误')
        if m < 1 or n < 1 or step < 1 or step >= max(m, n):
            raise ValueError('存档参数超出合法范围')
        if m * n > 250000:
            raise ValueError('存档尺寸过大')
        kind = 'square'
        if version >= 2:
            kind = puzzle.get('type', 'square')
        cubic_depth = puzzle.get('depth')
        if kind == 'cubic':
            # 三维存档（§54 第 5 步）：m×n×depth，step 必须小于最大维度
            if not isinstance(cubic_depth, int) or isinstance(cubic_depth, bool) \
                    or cubic_depth < 1:
                # 旧版本可能写下的无 depth 三维档（第 5 步之前根本读不回来）：
                # 按「上次停在三维局」安静回落，别冒充「模型缺失」或数据损坏。
                raise StaleCubicSave('三维存档缺少 depth（旧档，无法还原）')
            if cubic_depth > 32 or m * n * cubic_depth > 250000:
                raise ValueError('三维存档尺寸过大')
            if step >= max(m, n, cubic_depth):
                raise ValueError('三维存档参数超出合法范围')
        if kind == _preview_kind():
            # 编辑器预览局（旧版本退出时被自动存档写下的）。没有 models/
            # 文件，也不该有——按「上次退出停在编辑器里」安静略过，
            # 不冒充「模型缺失」报错（2026-10-25 用户实测每次启动都弹）。
            raise StaleEditorSave(
                f'上次退出时停在搭积木编辑器里（预览局面不存档）')

        history_data = save_data.get('history', {})
        snapshots = history_data.get('snapshots', [])
        # ③ 载入前先校验每条快照的 matrix/bounds：坏数据（形如字符串/形状错乱/
        # 包围盒不符/单元非整数）直接判失败，绝不静默当成功载入
        # （否则会生成死局并把垃圾原样写回磁盘）。校验在改状态之前，
        # 失败时当前局面保持原样。
        for snap in snapshots:
            validate_snapshot(snap, kind)

        # §九：模型板型旧档（engine_state 落盘修复 2026-10-27 之前写下）静默损坏提示
        # 缺 engine_state 时 restore_snapshot 回退 lossy 的 matrix 重建 → 盘面被压碎
        # （块少一半、不单连通、打乱失效）。现在的存档每个快照都带，只有旧档会缺。
        # 不阻断载入：盘面照旧载入，只让玩家知道发生了什么。
        if kind not in ('square', 'numbered', 'triangle', 'mi'):
            if any(snap.get('engine_state') is None for snap in snapshots):
                self.macro_notify_msg = (
                    '这是旧版本写下的模型存档，缺少无损键表，无法完整还原，块可能缺失')
                self.macro_notify_timer = 300
                print('旧模型存档缺 engine_state，已载入但块可能缺失')

        # 载入只读标志：带 readonly:true 的存档载入后为只读（校验通过后才设，
        # 避免载入失败却把当前局的只读标记改掉）
        self._readonly = bool(save_data.get('readonly', False))

        # v1 存档的 snapshots 若带 numbers（搭便车存档），也按带序号还原
        self.numbered = kind == 'numbered' or any(
            snap.get('numbers') for snap in snapshots)
        # 三角形密铺：mode 标记 + 大三角形边长（k 缺省时退回 m）
        self.triangle_mode = kind == 'triangle'
        # 米字格：mode 标记；切回别的形态时必须一起清掉，否则旧旗标会让
        # 渲染/命中继续走米字格分支
        self.mi_mode = kind == 'mi'
        # 三维（§54 第 5 步）：形态旗标同理，切回二维必须清掉
        self.cubic_mode = kind == 'cubic'
        triangle_side = puzzle.get('triangle_side', m)

        self.current_m = m
        self.current_n = n
        self.current_step = step
        # 三维：层数也要跟着回到旗标上。只设 cubic_mode 不设 current_depth 时，
        # 状态栏/成绩/存档取分榜键会直接抛「缺 depth」（2026-11-18 启动即崩）。
        self.current_depth = int(cubic_depth) if kind == 'cubic' else 0

        self.game_history.reset()
        for i, snap in enumerate(snapshots):
            move_info = snap.get('move_info')
            moves = snap.get('moves')
            if moves is None:
                # 旧存档：每快照一步
                moves = [move_info] if move_info else []
            if snap.get('cubic'):
                # 三维：没有 matrix/bounds（矩阵是二维口径），局面在 engine_state
                entry = {
                    'matrix': [],
                    'bounds': {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0},
                    'move_info': move_info,
                    'moves': moves,
                    'steps': snap.get('steps', 1 if move_info else 0),
                    'step_total': snap.get('step_total', i),
                    'session_key': None,
                    'groups': groups_from_json(snap.get('groups')),
                    'engine_state': snap.get('engine_state'),
                    'cubic': True,
                }
                self.game_history.history.append(entry)
                continue
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
                # 捆绑关系随快照还原；旧存档无该字段 = 全散块（行为与修复前一致）
                'groups': groups_from_json(snap.get('groups')),
                # 无损键表（引擎板型）：落盘带来了就原样带回内存，restore_snapshot
                # 据它无损还原（见 _build_save_data 的写入说明）。旧方形/三角/米字
                # 存档无该字段 → None，restore 走各自的专属分支，行为不变。
                'engine_state': snap.get('engine_state'),
            }
            # 旧格式兼容：01 矩阵 + 平行 numbers 表 → 折叠进整数矩阵（值即编号），
            # 不再携带 numbers 字段（编号谜题的整数矩阵本身即承载编号）
            if snap.get('numbers'):
                nums = snap['numbers']
                mat = [row[:] for row in snap['matrix']]
                for i, row in enumerate(nums):
                    for j, v in enumerate(row):
                        if v:
                            mat[i][j] = v
                entry['matrix'] = mat
            self.game_history.history.append(entry)
        self.game_history.history_index = history_data.get('history_index', 0)
        # 步数以历史累计值为准（合并快照一条覆盖多步，不能再按索引算）
        self.step_count = self.game_history.current_step_total()

        # 从快照重建游戏状态（依版本/形態分派）。
        # create_puzzle 对模型板型直接走 EngineGame 适配器（puzzle_types 的
        # 模型分支，不依赖全局引擎开关）——没有「落回方形」的回退。
        if kind not in ('square', 'numbered', 'triangle', 'mi', 'cubic'):
            self._check_saved_model_identity(kind, puzzle.get('model') or {})
        if kind == 'cubic':
            self.game = create_puzzle(m, n, step, kind='cubic',
                                      depth=cubic_depth)
        else:
            self.game = create_puzzle(m, n, step, kind=kind,
                                      triangle_side=triangle_side)
        # 形态标记同步到逻辑对象：编号谜题的整数矩阵靠 numbered 还原编号；
        # 三角/米字为独立矩阵编码，其逻辑类 __slots__ 不含 numbered，跳过
        if kind in ('square', 'numbered'):
            self.game.numbered = self.numbered
        if kind not in ('square', 'numbered', 'triangle', 'mi'):
            # 模型文件板型：相机按通用通道包围盒居中（与建局同式；
            # 存档不保存 zoom）
            self.zoom = 1.0
            self.center_map()
        if kind == 'triangle':
            self.current_m = self.current_n = self.game.k
            # 载入后按当前棋盘大小重新适配缩放并居中（存档不保存 zoom）
            self.zoom = self._fit_triangle_zoom()
            self.center_map()
        elif kind == 'mi':
            # 米字格同理：包围盒走 mi_view（世界坐标无 gap 间距）
            self.zoom = self._fit_mi_zoom()
            self.center_map()
        elif kind == 'cubic':
            self._cubic_load_defaults(load=True)
            self.current_m, self.current_n = m, n
        self.game_history.restore_snapshot(self.game, self.game_history.history_index)

        # 自定义预设局：按存档记录的预设名恢复还原目标（D4）；无预设名则清空，
        # 避免上一局的样式判定残留到本局（官方预设/普通方形走默认满矩形判定）。
        self._ann_apply_saved_style_goal(puzzle.get('preset'))

        self.selected_gap = None
        self.selected_block = None
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
        米字格 mi、三角形 tri、带序号 num、碎三角 shat 按序追加（可叠加，
        如 tri-num-…）。

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
        if self._current_kind() not in ('square', 'numbered', 'triangle', 'mi'):
            # 模型局：文件名带模型名（截 8 字符，免得碎三角之外的长名撑爆）
            marks.append(self._current_kind()[:8])
        tag = ('-'.join(marks) + '-') if marks else ''
        return f"{tag}{self.current_step}-{self.current_m}-{self.current_n}-{ts}.json"

    def _med_save_blocked(self) -> bool:
        """搭积木编辑器会话中禁止「存档」类操作（Ctrl+S / 另存为）。

        理由同 `StaleEditorSave`：那时候 `self.game` 是预览局，存成 json
        的话 `puzzle.type` 会写成 `__editor__`，那份文件永远载不回来。编辑器
        自己的落盘口是左侧 [存样式]（写 `models/<名>.json`）。

        放在 FileOpsMixin 而不是 model_editor：`save_to_file` / `_save_to_path`
        的调用方不一定带 ModelEditorMixin（测试里有只继承 FileOps 的桩 GUI）。
        """
        if not getattr(self, '_med_active', False):
            return False
        self.macro_notify_msg = ('搭积木编辑器里的摆放不能存成谜题存档：'
                                 '请用左侧 [存样式] 存成模型，或先退出编辑器')
        self.macro_notify_timer = 200
        return True

    def _cubic_save_blocked(self) -> bool:
        """三维局现在允许存档（§54 第 5 步：format 已扩到 (r,c,d) + type: cubic）。

        这里保留这个门（调用点还是 ``_med_save_blocked() or _cubic_save_blocked()``），
        但只在「三维局连层数都不认识」这种自造坏局时才挡——正常三维局一律放行，
        否则退出即丢进度。
        """
        if not getattr(self, 'cubic_mode', False):
            return False
        depth = getattr(getattr(self, 'game', None), 'depth', None)
        if isinstance(depth, int) and depth >= 1:
            return False
        self.macro_notify_msg = '三维局缺层数（depth），存档会读不回来，先重建局面'
        self.macro_notify_timer = 240
        print('三维局存档被拒：逻辑对象缺 depth')
        return True

    def save_as(self):
        """另存为：弹出 pygame 文件对话框（默认名自动生成）"""
        if self._med_save_blocked() or self._cubic_save_blocked():
            return
        self.file_dialog.show(
            mode='save',
            title='另存为',
            initial_dir=self.save_dir,
            extensions=['json'],
            initial_file=self._default_save_name()
        )
        self._pending_save_as = True

    def _save_to_path(self, path: str) -> bool:
        """将当前状态保存到指定路径。返回是否成功（供「存档后打乱」续接判断）。"""
        if self._med_save_blocked() or self._cubic_save_blocked():
            return False
        # 文件名校验：Windows 非法字符（如 * ? : 等）写盘必抛异常，先拦截并明确提示
        illegal = _find_illegal_filename_chars(os.path.basename(path))
        if illegal:
            self.macro_notify_msg = f"文件名含非法字符 {' '.join(illegal)}，保存取消"
            self.macro_notify_timer = 240
            print(f"保存失败: 文件名含非法字符 {' '.join(illegal)}: {path}")
            return False
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
            return True
        except Exception as e:
            # 兜底：权限/磁盘/路径等任何异常都要转成用户可见提示，绝不静默
            self.macro_notify_msg = f"保存失败：{e}"
            self.macro_notify_timer = 240
            print(f"保存失败: {e}")
            return False

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
                    ok = self._save_to_path(self.file_dialog.result)
                    self.save_dir = os.path.dirname(self.file_dialog.result)
                    # 「存档后打乱/重置」：另存为保存成功才续；失败不续
                    if getattr(self, '_pending_shuffle_after_save', False):
                        self._pending_shuffle_after_save = False
                        if ok:
                            self.shuffle_puzzle(confirm=False)
                    if getattr(self, '_pending_reset_after_save', False):
                        self._pending_reset_after_save = False
                        if ok:
                            self.reset_puzzle(confirm=False)
                else:
                    # 取消另存为：放弃「存档后打乱/重置」
                    self._pending_shuffle_after_save = False
                    self._pending_reset_after_save = False
            if getattr(self, '_pending_load', False):
                self._pending_load = False
                if self.file_dialog.result:
                    self._do_load_from_path(self.file_dialog.result)
            if getattr(self, '_pending_convert', False):
                self._pending_convert = False
                if self.file_dialog.result:
                    self._do_convert_from_path(self.file_dialog.result)
            if getattr(self, '_pending_guide_save', False):
                self._pending_guide_save = False
                if self.file_dialog.result:
                    ok, msg = self.write_external_control_guide(self.file_dialog.result)
                    self.macro_notify_msg = msg
                    self.macro_notify_timer = 150

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
            # ① 载入失败也要给用户可见提示（与保存路径一致，绝不静默）
            self.macro_notify_msg = "打开失败：未找到文件"
            self.macro_notify_timer = 180
            print("未找到文件")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # ① 同上：格式错误/校验失败/矩阵非法等一律弹状态栏提示
            self.macro_notify_msg = f"打开失败：{e}"
            self.macro_notify_timer = 180
            print(f"文件格式错误: {e}")

    def export_map(self):
        """兼容旧终端指令：保存到当前文件或另存为"""
        self.save_to_file()

    def import_map(self):
        """兼容旧终端指令：从文件打开"""
        self.load_from_file()

    def convert_save(self):
        """存档转换：弹文件对话框选一个存档 → 一键转成另一种格式并导出文件。

        用法：选中一个存档，点确定，自动在其同目录生成转换后的文件
        （普通→压缩：<名>.compressed.json；压缩→普通：<名>.normal.json）。
        """
        self.file_dialog.show(
            mode='open',
            title='选择要转换的存档',
            initial_dir=self.save_dir,
            extensions=['json']
        )
        self._pending_convert = True

    def _do_convert_from_path(self, src_path: str):
        """把 src_path 转成另一种格式写到同目录的派生文件名。"""
        try:
            with open(src_path, 'r', encoding='utf-8') as f:
                src = json.load(f)
            src_compressed = is_compressed(src)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.macro_notify_msg = f"读取失败（文件可能损坏）：{e}"
            self.macro_notify_timer = 180
            print(f"存档转换读取失败: {e}")
            return
        except Exception as e:
            self.macro_notify_msg = f"读取失败：{e}"
            self.macro_notify_timer = 180
            return
        base, _ = os.path.splitext(src_path)
        dst = (base + '.normal.json') if src_compressed else (base + '.compressed.json')
        try:
            kind, msg = convert_save_file(src_path, dst)
            self.macro_notify_msg = f"已转换（{kind}）：{os.path.basename(dst)}"
            self.macro_notify_timer = 200
            print(msg)
        except Exception as e:
            self.macro_notify_msg = f"转换失败：{e}"
            self.macro_notify_timer = 240
            print(f"存档转换失败: {e}")
