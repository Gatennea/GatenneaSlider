# -*- coding: utf-8 -*-
"""把 `models/` 下的模型文件注册成引擎板型。

设计要点
--------
1. **文件即板型**：启动扫描目录，每个 `<name>.json` 注册成同名板型；
   `make_board(name)` / `create_adapter_puzzle(name)` 直接可用，GUI 侧
   不需要为新形状加分支。
2. **不静默兜底**：某个模型加载或校验失败 → **不注册**该板型，同时把
   错误记进 `errors()`。之后玩家点它拿到的是「未注册的板型」KeyError，
   而不是一个悄悄换成方形的错盘（48 块变 16 块那条旧坑）。
3. **不覆盖已注册**：与内置板型重名默认跳过。`shatter` / `shatter_lattice`
   的内置注册已移除，改由文件提供——同一盘型只能有一个来源，否则
   `update_matrix` 的朝向编码会两套并存。

启动期只跑**结构校验 + A0/A1**（快）；A2/A3 由 CLI `validate_model.py`
负责（要对每条合法移动求新局面，不该压在启动路径上）。
"""
import os

_LOADED = {}      # {名字: LoadedModel}
_ERRORS = []      # [str] 加载/校验失败原因
_INSTALLED = False


def install(model_dir=None, *, override=False, validate_light=True):
    """扫描并注册模型。可重复调用（第二次为幂等：已装的跳过）。

    返回 {名字: LoadedModel}（本次新装的那批）。

    **逐个文件加载**，不让一个坏文件拖死整个启动：坏文件记进 errors()、
    不注册；好文件照装。这不是静默兜底——坏模型拿不到就用不了（KeyError），
    绝不会悄悄换成一个方形盘。
    """
    global _INSTALLED
    from .model_loader import DEFAULT_MODEL_DIR, ModelError, load_file
    from .model_validate import validate
    from .registry import board_types, register_board_type

    model_dir = model_dir or DEFAULT_MODEL_DIR
    if not os.path.isdir(model_dir):
        _ERRORS.append(f'模型目录不存在：{model_dir}')
        return {}

    loaded = {}
    for fname in sorted(os.listdir(model_dir)):
        if not fname.endswith('.json') or fname == 'shapes.json':
            continue
        path = os.path.join(model_dir, fname)
        try:
            model = load_file(path)
        except (ModelError, ValueError, TypeError, KeyError, OSError) as exc:
            _ERRORS.append(f'{fname} 加载失败：{exc}')
            continue
        if model.name in loaded:
            _ERRORS.append(
                f'模型名重复：{model.name!r}（{fname} 与前面某个文件同名），'
                f'该文件被跳过')
            continue
        loaded[model.name] = model

    fresh = {}
    for name, model in loaded.items():
        if name in _LOADED:
            continue
        if name in board_types() and not override:
            _ERRORS.append(
                f'模型 {name!r} 与已注册板型重名，跳过（未覆盖）。'
                f'若要让文件接管，先从注册表移除同名内置板型')
            continue
        if validate_light:
            problems = [p for p in validate(model, deep=False)
                        if p.level == 'error']
            if problems:
                _ERRORS.append(
                    f'模型 {name!r} 未通过物理公理，拒绝注册：'
                    + '；'.join(str(p) for p in problems[:3]))
                continue
        register_board_type(name, _spec_factory(model))
        _LOADED[name] = model
        fresh[name] = model

    _INSTALLED = True
    return fresh


def _spec_factory(model):
    """板型工厂：返回模型自带的 BoardSpec（不可变，可多局共用）。

    模型板型没有尺寸参数——尺寸已经写进 `tiles`。传参一律报错，不静默
    忽略（否则 `make_board('mymodel', m=4)` 会得到与参数无关的盘）。
    """
    def factory(**kw):
        if kw:
            raise TypeError(
                f'板型 {model.name!r} 由模型文件定义，不接受参数（收到 '
                f'{sorted(kw)}）——尺寸写在 tiles 里')
        return model.spec
    return factory


def loaded(name=None):
    """已装模型：给了名字返回该 LoadedModel（未装 → KeyError），
    否则返回 {名字: LoadedModel}。"""
    if name is None:
        return dict(_LOADED)
    if name not in _LOADED:
        raise KeyError(f'模型 {name!r} 未安装（已装: {sorted(_LOADED)}）')
    return _LOADED[name]


def errors():
    """加载/校验期的错误清单（GUI 可在启动时提示，也可以只记日志）。"""
    return tuple(_ERRORS)


def clear_errors():
    _ERRORS.clear()
