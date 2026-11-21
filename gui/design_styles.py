# -*- coding: utf-8 -*-
"""自定义样式存取（自由捆绑/设计模式，docs/spec/bandaged_mode.md）。

样式 = 创造模式「设计」态造出的棋形：cells（归一坐标）+ groups（捆绑）
+ 尺寸。存为 config/design_styles/<name>.json，可作为谜题的还原形态
（is_solved 走 D4 八变换，旋转/翻面都算还原）。

对外契约：
- save_style(config_dir, name, data) -> path | None（重名覆盖）
- list_styles(config_dir) -> [name, ...]（按名排序）
- load_style(config_dir, name) -> dict | None（含旧名映射兜底，§64）
- delete_style(config_dir, name) -> bool
- rename_style(config_dir, old, new, overwrite=False) -> (ok, msg)（§64）
- sanitize_name(name) -> str（防路径穿越：只留安全字符）
"""
import json
import os
import re
import sys

STYLES_SUBDIR = 'design_styles'
# 入库示范样式（§68）：放 assets/ 下随包分发（spec 的 _collect_assets 整树收），
# 只读、不随玩家走；玩家自建仍在 config/design_styles（可写）。
_BUILTIN_REL = os.path.join('assets', 'presets', 'design_styles')
_SAFE_NAME = re.compile(r'[^\w\u4e00-\u9fff.-]')
# 改名映射（§64）：旧名 → 新名。点号前缀让 list_styles 自动跳过，不占菜单一项。
_RENAMES_FILE = '.renames.json'


def styles_dir(config_dir: str) -> str:
    return os.path.join(config_dir, STYLES_SUBDIR)


def builtin_styles_dir() -> str:
    """入库示范样式目录：打包后 <_MEIPASS>/assets/presets/design_styles，
    开发时 <项目根>/assets/presets/design_styles（与 tutorial.py 同口径）。"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, _BUILTIN_REL)


def _renames_path(config_dir: str) -> str:
    return os.path.join(styles_dir(config_dir), _RENAMES_FILE)


def _read_renames(config_dir: str) -> dict:
    try:
        with open(_renames_path(config_dir), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_renames(config_dir: str, mapping: dict) -> bool:
    try:
        os.makedirs(styles_dir(config_dir), exist_ok=True)
        with open(_renames_path(config_dir), 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


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


def _names_in(d: str) -> set:
    try:
        return {f[:-5] for f in os.listdir(d)
                if f.endswith('.json') and not f.startswith('.')}
    except Exception:
        return set()


def list_styles(config_dir: str) -> list:
    """列出全部可用样式名（按名排序）：玩家自建 + 入库示范（§68）。

    同名时只出现一次（load_style 里 config 优先，玩家改过的盖住示范）。
    """
    return sorted(_names_in(styles_dir(config_dir)) | _names_in(builtin_styles_dir()))


def style_source(config_dir: str, name: str):
    """样式来源：'user'（config 玩家自建）/ 'builtin'（入库示范）/ None。

    config 优先——玩家另存的同名副本盖过示范，读写都按这个优先级。
    """
    safe = sanitize_name(name)
    if os.path.exists(os.path.join(styles_dir(config_dir), f'{safe}.json')):
        return 'user'
    if os.path.exists(os.path.join(builtin_styles_dir(), f'{safe}.json')):
        return 'builtin'
    return None


def copy_builtin_to_user(config_dir: str, name: str):
    """把入库示范另存为玩家自建（§68 写权隔离：只读示范→可写副本）。

    返回 (ok, result)：成功 (True, path)，非示范或失败 (False, reason)。
    同名已存在则不覆盖（玩家已有自己的版本时不能再压一份）。
    """
    safe = sanitize_name(name)
    src = os.path.join(builtin_styles_dir(), f'{safe}.json')
    dst = os.path.join(styles_dir(config_dir), f'{safe}.json')
    if not os.path.exists(src):
        return False, 'not_builtin'
    if os.path.exists(dst):
        return False, 'exists'
    try:
        with open(src, encoding='utf-8') as f:
            data = json.load(f)
        os.makedirs(styles_dir(config_dir), exist_ok=True)
        with open(dst, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True, dst
    except Exception:
        return False, 'io_error'


def resolve_name(config_dir: str, name: str) -> str:
    """沿改名映射链把旧名解析到当前名（A→B→C 一路追到底，带环保护）。

    这样旧存档的 ``preset`` 写的是旧名也能读到改名后的样式，不必批量改写
    玩家存档（§64 推荐的最小改动路线）。UI 侧也用它把 HUD 上的旧名换成新名。
    """
    mapping = _read_renames(config_dir)
    cur = name
    seen = set()
    while cur in mapping and cur not in seen:
        seen.add(cur)
        cur = mapping[cur]
    return cur


def _read_style_path(path: str):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and 'cells' in data:
            return data
    except Exception:
        pass
    return None


def load_style(config_dir: str, name: str):
    """读取样式 dict（cells/groups/m/n/step）；不存在或损坏返回 None。

    查找优先级（§64 旧名映射 + §68 入库示范）：
      1. config 玩家自建原名 → 2. 改名映射解析后的 config 名
      → 3. 入库示范同名。config 永远盖过示范。
    """
    safe = sanitize_name(name)
    data = _read_style_path(os.path.join(styles_dir(config_dir), f'{safe}.json'))
    if data is not None:
        return data
    resolved = resolve_name(config_dir, safe)
    if resolved != safe:
        data = _read_style_path(
            os.path.join(styles_dir(config_dir), f'{resolved}.json'))
        if data is not None:
            return data
    return _read_style_path(os.path.join(builtin_styles_dir(), f'{safe}.json'))


def groups_from_data(data: dict) -> dict:
    """样式里的捆绑组 → {完整位置元组: gid}（读侧统一入口）。

    两种落盘形式都要认：
      - version 1（方形/带序号）：{"r,c": gid}
      - version 2（三角/米字）：[[分量..., gid], ...]——位置可能是 3 分量
        （三角含 up、米字含 q），米字错位态还可能是半整数坐标
    坏项一律跳过（缺 gid / gid 非正 / 形状不合法），不让一份坏样式把
    开局流程打断。
    """
    raw = (data or {}).get('groups')
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                parts = str(k).split(',')
                pos = tuple(int(x) for x in parts)
                gid = int(v)
            except Exception:
                continue
            if gid > 0:
                out[pos] = gid
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            pos = tuple(item[:-1])
            try:
                gid = int(item[-1])
            except Exception:
                continue
            if gid > 0 and len(pos) >= 2:
                out[pos] = gid
    return out


def rename_style(config_dir: str, old: str, new: str,
                 overwrite: bool = False):
    """改名一个样式（§64）：文件名 + 文件内 name 字段一起改，并留旧名映射。

    四件事一次做完：
      1. ``os.replace`` 旧 .json → 新 .json（原子，避免中途断电留半截）；
      2. 新文件内 ``name`` 字段同步成新名（数据自述与文件名一致）；
      3. 旧名 → 新名写进 ``.renames.json``，让旧存档 ``preset`` 仍能读到；
      4. 返回值交给 UI 侧同步 ``_ann_style_goal``（HUD/提示）。

    返回 ``(ok, result)``：成功 ``(True, path)``；失败 ``(False, reason)``，
    reason ∈ empty / missing_old / same / exists / io_error。``exists`` 时
    UI 应先向玩家确认覆盖，再以 ``overwrite=True`` 重试。

    **只对 config 里的玩家样式有效**——入库示范样式不在 config 目录，
    传进来的 old 若在 config 找不到就返回 missing_old（§68 边界）。
    """
    old_raw = (old or '').strip()
    new_raw = (new or '').strip()
    if not new_raw:
        return False, 'empty'
    old_name = sanitize_name(old_raw)
    new_name = sanitize_name(new_raw)
    if not new_name or new_name == '未命名':
        return False, 'empty'
    d = styles_dir(config_dir)
    src = os.path.join(d, f'{old_name}.json')
    dst = os.path.join(d, f'{new_name}.json')
    if not os.path.exists(src):
        return False, 'missing_old'
    if old_name == new_name:
        return True, dst
    if os.path.exists(dst) and not overwrite:
        return False, 'exists'
    try:
        with open(src, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'cells' not in data:
            return False, 'io_error'
        data['name'] = new_name
        os.makedirs(d, exist_ok=True)
        tmp = dst + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, dst)   # 原子落新文件；中途失败则 tmp 留着，新旧都不丢
        os.remove(src)
        mapping = _read_renames(config_dir)
        # A→B→C：若旧名本身已是别人的映射目标，把指向旧的链一并接过来，
        # 否则旧存档写 A 时解析到已删除的 B 就断了。
        for k, v in list(mapping.items()):
            if v == old_name:
                mapping[k] = new_name
        mapping[old_name] = new_name
        _write_renames(config_dir, mapping)
        return True, dst
    except Exception:
        return False, 'io_error'


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
