"""三维渲染/交互选项的**声明式表**（方案 §2.4「登记机制」）。

一张表说清楚每个三维选项的：键、标签、类型、范围、默认值、所属组、落在哪个
属性上。渲染、事件、读盘/落盘都从这里取，别再出现「加一个开关要改 8 处」。

用法：
    from gui.cubic_settings import CUBIC_SETTINGS, defaults, clamp_value, serialize, apply
    self.cubic_gap = defaults()['gap']
    serialize(self)        # → {'gap': 0.12, ...} 写进 config
    apply(self, cfg_dict)  # 读盘时套用（越界夹紧，缺项保默认）
"""
from engine.cubic_view import DEFAULT_GAP

#: 一条一个选项。attr 是 GUI 上的属性名（渲染/事件直接读它）。
CUBIC_SETTINGS = (
    {'key': 'gap', 'label': '拆分', 'attr': 'cubic_gap',
     'type': 'float', 'min': 0.0, 'max': 0.6, 'default': DEFAULT_GAP,
     'group': 'view',
     'help': '滑块大小不变，只拉开相邻滑块之间的间距（0 = 贴死成一整块，露不出内部）'},
    {'key': 'seam_alpha', 'label': '切面透明', 'attr': 'cubic_seam_alpha',
     'type': 'int', 'min': 30, 'max': 220, 'default': 110,
     'group': 'view',
     'help': '切面预览那张红面的不透明度（越小越透，越大越实）'},
    {'key': 'cubic_anim_ms', 'label': '动画时长', 'attr': 'cubic_anim_ms',
     'type': 'int', 'min': 60, 'max': 400, 'default': 140,
     'group': 'view',
     'help': '三维推一步 / 打乱演示 / 撤销重做的动画时长（毫秒）；右侧速度滑条同源'},
    {'key': 'rot_sensitivity', 'label': '旋转灵敏度', 'attr': 'cubic_rot_sensitivity',
     'type': 'float', 'min': 0.2, 'max': 2.0, 'default': 1.0,
     'group': 'control',
     'help': '拖动旋转时转角相对鼠标位移的倍率'},
)

_BY_KEY = {s['key']: s for s in CUBIC_SETTINGS}
_BY_ATTR = {s['attr']: s for s in CUBIC_SETTINGS}


def by_key(key: str) -> dict:
    return _BY_KEY[key]


def by_attr(attr: str) -> dict:
    return _BY_ATTR[attr]


def defaults() -> dict:
    return {s['key']: s['default'] for s in CUBIC_SETTINGS}


def clamp_value(key: str, value):
    """把外部（配置/滑条）传来的值夹到表里声明的类型与范围内。

    类型不对就退回默认值：宁可保持默认，也不让字符串/None 混进渲染。
    """
    spec = _BY_KEY.get(key)
    if spec is None:
        raise KeyError(f'未登记的三维选项：{key!r}')
    try:
        v = float(value)
    except (TypeError, ValueError):
        return spec['default']
    v = max(spec['min'], min(spec['max'], v))
    return int(round(v)) if spec['type'] == 'int' else v


def serialize(owner) -> dict:
    """按表把当前值导出成可落盘的 dict（只认表里有的键）。"""
    out = {}
    for s in CUBIC_SETTINGS:
        v = getattr(owner, s['attr'], s['default'])
        out[s['key']] = clamp_value(s['key'], v)
    return out


def apply(owner, values: dict) -> None:
    """读盘：把 dict 套到 owner 的属性上。缺项/坏值保默认（不静默写坏）。"""
    for s in CUBIC_SETTINGS:
        raw = (values or {}).get(s['key'], s['default'])
        setattr(owner, s['attr'], clamp_value(s['key'], raw))


def reset(owner) -> None:
    apply(owner, defaults())


def items(group: str = None) -> list:
    """按组取条目（设置页分块用）。"""
    if group is None:
        return list(CUBIC_SETTINGS)
    return [s for s in CUBIC_SETTINGS if s['group'] == group]
