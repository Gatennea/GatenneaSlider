# -*- coding: utf-8 -*-
"""自定义样式存取（自由捆绑/设计模式，docs/spec/bandaged_mode.md）。

样式 = 创造模式「设计」态造出的棋形：cells（归一坐标）+ groups（捆绑）
+ 尺寸。存为 config/design_styles/<name>.json，可作为谜题的还原形态
（is_solved 走 D4 八变换，旋转/翻面都算还原）。

对外契约：
- save_style(config_dir, name, data) -> path | None（重名覆盖）
- list_styles(config_dir) -> [name, ...]（按名排序）
- load_style(config_dir, name) -> dict | None
- delete_style(config_dir, name) -> bool
- sanitize_name(name) -> str（防路径穿越：只留安全字符）
"""
import json
import os
import re

STYLES_SUBDIR = 'design_styles'
_SAFE_NAME = re.compile(r'[^\w\u4e00-\u9fff.-]')


def styles_dir(config_dir: str) -> str:
    return os.path.join(config_dir, STYLES_SUBDIR)


def sanitize_name(name: str) -> str:
    """名称清洗：去路径分隔符与危险字符，限长 40；空名回退 '未命名'。"""
    name = _SAFE_NAME.sub('_', (name or '').strip())
    name = name.strip('._') or '未命名'
    return name[:40]


def save_style(config_dir: str, name: str, data: dict):
    """保存样式（重名覆盖）。返回文件路径；写盘失败返回 None。"""
    name = sanitize_name(name)
    d = styles_dir(config_dir)
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f'{name}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None


def list_styles(config_dir: str) -> list:
    """列出已存样式名（按名排序）。"""
    d = styles_dir(config_dir)
    try:
        return sorted(f[:-5] for f in os.listdir(d)
                      if f.endswith('.json') and not f.startswith('.'))
    except Exception:
        return []


def load_style(config_dir: str, name: str):
    """读取样式 dict（cells/groups/m/n/step）；不存在或损坏返回 None。"""
    path = os.path.join(styles_dir(config_dir), f'{sanitize_name(name)}.json')
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'cells' not in data:
            return None
        return data
    except Exception:
        return None


def delete_style(config_dir: str, name: str) -> bool:
    """删除样式；存在并删除成功返回 True。"""
    path = os.path.join(styles_dir(config_dir), f'{sanitize_name(name)}.json')
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except Exception:
        pass
    return False
