# -*- coding: utf-8 -*-
"""
宏定义功能模块

宏类似于魔方公式：一系列操作步骤，玩家在特定局面下执行以达到预期效果。
每个步骤记录相对于基准坐标的操作，执行时由玩家指定新基准坐标转换为绝对坐标。

坐标转换规则：
  录制时：gap_line_rel = gap_line_abs - base_row (h) 或 gap_line_abs - base_col (v)
  执行时：gap_line_abs = new_row + gap_line_rel (h) 或 new_col + gap_line_rel (v)
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MacroStep:
    """宏的单个步骤，记录相对于基准坐标的操作"""
    gap_type: str         # 缝隙类型: 'h' (横向) 或 'v' (纵向)
    gap_line_rel: int     # 缝隙行/列相对于基准的偏移
    side: str             # 选中缝隙哪一侧: 'above'/'below' (h) 或 'left'/'right' (v)
    direction: str        # 滑动方向: 'w'/'a'/'s'/'d'
    step: int             # 录制时的步长
    rep_cell_rel: Optional[list] = None  # 该步移动分量的代表格相对基准 [dr, dc]
                                         # （缝侧含多分量时用于精确定位；None=侧首块）

    def to_dict(self) -> dict:
        d = {
            'gap_type': self.gap_type,
            'gap_line_rel': self.gap_line_rel,
            'side': self.side,
            'direction': self.direction,
            'step': self.step,
        }
        if self.rep_cell_rel is not None:
            d['rep_cell_rel'] = self.rep_cell_rel
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'MacroStep':
        return cls(
            gap_type=d['gap_type'],
            gap_line_rel=d['gap_line_rel'],
            side=d['side'],
            direction=d['direction'],
            step=d['step'],
            rep_cell_rel=d.get('rep_cell_rel'),
        )


@dataclass
class Macro:
    """一个完整的宏，包含名称、描述和步骤列表"""
    name: str
    description: str = ''
    recorded_step: int = 2
    base_point: list = field(default_factory=lambda: [0, 0])  # [row, col]
    steps: list = field(default_factory=list)  # list[MacroStep]

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'description': self.description,
            'recorded_step': self.recorded_step,
            'base_point': self.base_point,
            'steps': [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Macro':
        return cls(
            name=d['name'],
            description=d.get('description', ''),
            recorded_step=d.get('recorded_step', 2),
            base_point=d.get('base_point', [0, 0]),
            steps=[MacroStep.from_dict(s) for s in d.get('steps', [])],
        )

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def check_step_compatibility(self, current_step: int) -> tuple:
        """
        检查宏的步长是否与当前谜题兼容
        
        返回: (compatible: bool, factor: int, reason: str)
            - compatible: 是否兼容
            - factor: 拆分因子（每步拆分为 factor 次小步），1 表示直接执行
            - reason: 不兼容时的原因说明
        """
        if self.recorded_step == current_step:
            return (True, 1, '')
        if current_step > 0 and self.recorded_step % current_step == 0:
            return (True, self.recorded_step // current_step, '')
        return (False, 0,
                f'宏的步长({self.recorded_step})与当前步长({current_step})不兼容')


class MacroManager:
    """
    宏管理器：负责加载、保存、列举、删除宏文件
    
    宏文件存储在 macro/ 目录下，每个宏一个 .json 文件。
    文件名格式: {sanitized_name}.json
    """

    def __init__(self, macro_dir: str):
        """
        参数:
            macro_dir: 宏文件存放目录路径
        """
        self.macro_dir = macro_dir
        os.makedirs(self.macro_dir, exist_ok=True)
        self._macros: dict[str, Macro] = {}  # name -> Macro
        self.load_all()

    def load_all(self):
        """从 macro_dir 加载所有 .json 宏文件"""
        self._macros.clear()
        if not os.path.isdir(self.macro_dir):
            return
        for fname in os.listdir(self.macro_dir):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(self.macro_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                macro = Macro.from_dict(data)
                self._macros[macro.name] = macro
            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f'[MacroManager] 加载宏文件失败: {fname} ({e})')

    def save_macro(self, macro: Macro):
        """
        保存一个宏到文件（会覆盖同名宏）
        
        参数:
            macro: 要保存的宏对象
        """
        self._macros[macro.name] = macro
        fname = self._sanitize_filename(macro.name) + '.json'
        fpath = os.path.join(self.macro_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(macro.to_dict(), f, ensure_ascii=False, indent=2)

    def delete_macro(self, name: str) -> bool:
        """
        删除指定名称的宏
        
        参数:
            name: 宏名称
        
        返回:
            是否删除成功
        """
        if name not in self._macros:
            return False
        del self._macros[name]
        fname = self._sanitize_filename(name) + '.json'
        fpath = os.path.join(self.macro_dir, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
        return True

    def rename_macro(self, old_name: str, new_name: str) -> bool:
        """
        重命名宏
        
        参数:
            old_name: 原名称
            new_name: 新名称
        
        返回:
            是否重命名成功
        """
        if old_name not in self._macros or new_name in self._macros:
            return False
        macro = self._macros.pop(old_name)
        # 删除旧文件
        old_fname = self._sanitize_filename(old_name) + '.json'
        old_fpath = os.path.join(self.macro_dir, old_fname)
        if os.path.exists(old_fpath):
            os.remove(old_fpath)
        # 更新名称并保存
        macro.name = new_name
        self.save_macro(macro)
        return True

    def get_macro(self, name: str) -> Optional[Macro]:
        """获取指定名称的宏"""
        return self._macros.get(name)

    def list_macros(self) -> list[Macro]:
        """返回所有已加载的宏列表"""
        return list(self._macros.values())

    def list_names(self) -> list[str]:
        """返回所有宏名称列表"""
        return list(self._macros.keys())

    def has_macro(self, name: str) -> bool:
        """检查是否存在指定名称的宏"""
        return name in self._macros

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        将宏名称转换为安全的文件名
        替换非法字符为下划线
        """
        illegal = '<>:"/\\|?*'
        result = name
        for ch in illegal:
            result = result.replace(ch, '_')
        return result.strip() or 'unnamed'

    @staticmethod
    def convert_to_absolute(step: MacroStep, base_row: int, base_col: int,
                            current_step: int, factor: int = 1) -> list[dict]:
        """
        将一个相对步骤转换为绝对操作列表
        
        参数:
            step: 宏步骤
            base_row: 新基准行
            base_col: 新基准列
            current_step: 当前谜题步长
            factor: 拆分因子（每步拆分为 factor 次小步）
        
        返回:
            操作列表 [{gap_type, gap_line, side, direction, step}, ...]
        """
        if step.gap_type == 'h':
            abs_gap_line = base_row + step.gap_line_rel
        else:
            abs_gap_line = base_col + step.gap_line_rel

        rep_cell = None
        if step.rep_cell_rel is not None:
            rep_cell = [base_row + step.rep_cell_rel[0],
                        base_col + step.rep_cell_rel[1]]

        ops = []
        for _ in range(factor):
            op = {
                'gap_type': step.gap_type,
                'gap_line': abs_gap_line,
                'side': step.side,
                'direction': step.direction,
                'step': current_step,
            }
            if rep_cell is not None:
                op['rep_cell'] = rep_cell
            ops.append(op)
        return ops