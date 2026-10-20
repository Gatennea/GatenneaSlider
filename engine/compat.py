# -*- coding: utf-8 -*-
"""Move ↔ 既有动作格式映射层（P1 迁移件）。

P1 要把方形引擎切到引擎层（docs/spec/几何引擎.md §5），切之前必须先有
一条**无损的格式桥**：引擎的 Move 与现有两处动作表示互相转换——

  · history 动作 dict（gui/move.py 的 move_info / history.py 的 moves
    日志 / 存档）：``{'gap_type', 'gap_line', 'direction', 'step',
    'moved_positions'}``；
  · 打乱演示 record dict（game.record_shuffle_move 产出，GUI 演示
    动画重放消费）：``{'moved', 'final', 'gap', 'direction', 'step'}``；
  · 引擎 Move：``family / t / side / direction(元组) / step / moved``。

三处既有格式与引擎的差一在本层吸收，调用方不用记：
  · **缝序号**：既有引擎的 gap_line 是 0 基行/列号，引擎 ``t = gap_line + 1``
    （切分族双游：{p: f(p)=t} 的 f<t 侧 = above/left，f≥t 侧 = below/right）；
  · **方向**：既有格式用字母（方形 a/d/w/s），引擎用方向元组——词汇表
    按板型注册（square 已注册；三角/米字的字母表在 P2 随板型落地，
    两引擎的 DIRECTIONS 表现成即是）；
  · **side**：既有格式不记侧（由 moved 相对缝的位置隐含），本层负责推导。

本模块是**迁移件**：既有格式随旧引擎退役时一并删除。引擎核心零依赖
本层，本层也**不 import 任何 game*.py**——迁移方向就是让上层只同
engine 对话，桥自己不能反向依赖旧引擎（方形字母表在此重新声明，
与 game.DIRECTIONS 的等价性由差分测试 K2 钉死）。

纪律（AGENTS.md §2）：不认识的板型/族名/字母、缺键、合并态动作、
跨侧选中片，全部显式抛错，绝不静默兜底。纯逻辑零 pygame。
"""

from .board import Board, Move, _dot  # noqa: F401  （_dot 供本模块复用）


# ----------------------------------------------------------------------
# 方向字母词汇表（按板型注册）
# ----------------------------------------------------------------------
#: 方形密铺的方向字母表（与 game.DIRECTIONS 一致；等价性由测试 K2 钉死）。
#: 字母 → (d_row, d_col)，屏幕坐标 y 轴向下：w 上 / s 下 / a 左 / d 右。
SQUARE_DIRECTIONS = {
    'w': (-1, 0),
    's': (1, 0),
    'a': (0, -1),
    'd': (0, 1),
}

_VOCAB = {}


def register_direction_vocab(name: str, table: dict):
    """注册某板型的方向字母表 {字母: 方向元组}。

    同名重复注册**显式拒绝**（不静默覆盖——换了个字母表这种事必须
    听得见响，AGENTS.md §2）。
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"板型名须为非空字符串，收到 {name!r}")
    if not isinstance(table, dict) or not table:
        raise ValueError(
            f"板型 {name!r} 的方向词汇表须为非空 dict，收到 {table!r}")
    for letter, d in table.items():
        if not isinstance(letter, str) or len(letter) != 1:
            raise ValueError(
                f"板型 {name!r} 的方向字母须为单字符，收到 {letter!r}")
        if (not isinstance(d, tuple) or not d
                or not all(isinstance(x, int) for x in d)):
            raise ValueError(
                f"板型 {name!r} 的字母 {letter!r} 方向须为非空整数元组，"
                f"收到 {d!r}")
    if name in _VOCAB:
        raise ValueError(
            f"板型 {name!r} 的方向词汇表已注册，拒绝静默覆盖"
            f"（如需替换请先移除旧注册）")
    _VOCAB[name] = dict(table)


def direction_table(spec):
    """取板型的方向字母表 {字母: 方向元组}；未注册 → KeyError 带清单。"""
    try:
        return _VOCAB[spec.name]
    except KeyError:
        raise KeyError(
            f"板型 {spec.name!r} 未注册方向词汇表（已注册: {sorted(_VOCAB)}）"
            f"——映射层只支持显式注册过字母表的板型，不静默猜") from None


# ----------------------------------------------------------------------
# 内部小工具
# ----------------------------------------------------------------------
def _require_keys(obj, keys, what):
    if not isinstance(obj, dict):
        raise TypeError(f"{what} 须为 dict，收到 {type(obj).__name__}")
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(f"{what} 缺少键: {missing}")


def _family_of(spec, name):
    for fam in spec.seam_families:
        if fam.name == name:
            return fam
    raise ValueError(
        f"板型 {spec.name!r} 没有缝族 {name!r}"
        f"（已有: {[f.name for f in spec.seam_families]}）")


def _letter_to_dir(spec, letter):
    table = direction_table(spec)
    if letter not in table:
        raise ValueError(
            f"板型 {spec.name!r} 的方向字母表没有 {letter!r}"
            f"（已有: {sorted(table)}）")
    return table[letter]


def _norm_points(raw, spec, what):
    """位置列表 → 排序去重元组（接受 list/tuple，拒绝非整数/离格点）。"""
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(f"{what} 须为非空列表，收到 {raw!r}")
    out = []
    for p in raw:
        q = tuple(p) if isinstance(p, (list, tuple)) else None
        if q is None or not spec.lattice.valid(q):
            raise ValueError(f"{what} 含非法坐标 {p!r}（不在板型格上）")
        out.append(q)
    if len(set(out)) != len(out):
        raise ValueError(f"{what} 存在重复坐标")
    return tuple(sorted(out))


# ----------------------------------------------------------------------
# 引擎 Move → 既有格式
# ----------------------------------------------------------------------
def move_to_action(spec, move) -> dict:
    """引擎 Move → history 动作 dict（存档 / moves 日志 / move_info 同格式）。

    差一在本层吸收：``gap_line = t - 1``；方向元组 → 字母；moved 排序。
    产出可 JSON 序列化（元组在 json.dump 下自动变 list，与 GUI 写的
    move_info 逐键同形）。
    """
    fam = _family_of(spec, move.family)
    if _dot(fam.coeffs, move.direction) != 0:
        raise ValueError(
            f"移动方向 {move.direction} 不平行于缝族 {fam.name!r}"
            f"（f(d)={_dot(fam.coeffs, move.direction)}）——非法 Move")
    table = direction_table(spec)
    letters = [k for k, v in table.items() if v == move.direction]
    if len(letters) != 1:
        raise ValueError(
            f"方向 {move.direction} 在板型 {spec.name!r} 的字母表里对应 "
            f"{len(letters)} 个字母（{letters}）——词汇表须与方向一一对应")
    if not move.moved:
        raise ValueError("空选中片的移动不能转动作（合法移动必有非空 moved）")
    return {
        'gap_type': move.family,
        'gap_line': move.t - 1,
        'direction': letters[0],
        'step': move.step,
        'moved_positions': [tuple(p) for p in move.moved],
    }


def move_to_record(spec, move) -> dict:
    """引擎 Move → 打乱演示 record dict（与 game.record_shuffle_move 同格式）。

    ``'final'`` 由 moved + step·direction 现算（record 格式本就冗余，
    GUI 重放只消费 moved/final/gap/direction/step）。
    """
    action = move_to_action(spec, move)
    delta = tuple(move.step * x for x in move.direction)
    return {
        'moved': action['moved_positions'],
        'final': [tuple(p[i] + delta[i] for i in range(len(p)))
                  for p in action['moved_positions']],
        'gap': (action['gap_type'], action['gap_line']),
        'direction': action['direction'],
        'step': move.step,
    }


# ----------------------------------------------------------------------
# 既有格式 → 引擎 Move
# ----------------------------------------------------------------------
def action_to_move(spec, action) -> Move:
    """history 动作 dict → 引擎 Move（纯结构转换，不查局面合法性）。

    side 不在既有格式里，由 moved 相对缝的位置推导——合法移动的选中片
    必整片落在缝的一侧（横跨两侧 = 动作本身坏了，显式拒绝）。

    合并态动作（history.compose_move_info 的 'merged' 产物，方向可能
    为 None）**不是**单一移动，显式拒绝：回放/存档请先用逐步动作
    （expand_snapshot_moves 已负责把合并快照拆成逐步）。
    """
    _require_keys(action, ('gap_type', 'gap_line', 'direction', 'step',
                           'moved_positions'), '动作 dict')
    if 'merged' in action:
        raise ValueError(
            f"合并态动作（merged={action['merged']!r}）不是单一移动，"
            f"请先拆步再转换（compose_move_info 的产物供撤销动画整段播放，"
            f"回放/存档消费的是 expand_snapshot_moves 拆出的逐步动作）")
    fam = _family_of(spec, action['gap_type'])
    d = _letter_to_dir(spec, action['direction'])
    if _dot(fam.coeffs, d) != 0:
        raise ValueError(
            f"动作方向 {action['direction']!r}={d} 不平行于缝族 "
            f"{fam.name!r}（f(d)={_dot(fam.coeffs, d)}）")
    line = action['gap_line']
    if type(line) is not int:
        raise ValueError(f"gap_line 须为整数，收到 {line!r}")
    step = action['step']
    if type(step) is not int or step < 1:
        raise ValueError(f"step 须为 ≥ 1 的整数，收到 {step!r}")
    moved = _norm_points(action['moved_positions'], spec, 'moved_positions')
    t = line + 1
    vals = {_dot(fam.coeffs, p) for p in moved}
    if all(v < t for v in vals):
        side = -1
    elif all(v >= t for v in vals):
        side = 1
    else:
        raise ValueError(
            f"选中片横跨缝 {fam.name!r} t={t} 两侧（泛函值 {sorted(vals)}）——"
            f"合法移动的选中片必整片在缝的一侧")
    return Move(fam.name, t, side, d, step, moved)


def record_to_action(record) -> dict:
    """打乱演示 record dict → history 动作 dict（只取结构字段，final 冗余丢弃）。"""
    _require_keys(record, ('moved', 'final', 'gap', 'direction', 'step'),
                  'record dict')
    gap = record['gap']
    if not isinstance(gap, (list, tuple)) or len(gap) != 2:
        raise ValueError(
            f"record 的 gap 须为 (gap_type, line) 二元组，收到 {gap!r}")
    return {
        'gap_type': gap[0],
        'gap_line': gap[1],
        'direction': record['direction'],
        'step': record['step'],
        'moved_positions': [tuple(p) for p in record['moved']],
    }


def record_to_move(spec, record) -> Move:
    """record dict → 引擎 Move（record_to_action + action_to_move）。"""
    return action_to_move(spec, record_to_action(record))


# ----------------------------------------------------------------------
# 回放原语（存档 / 宏）
# ----------------------------------------------------------------------
def apply_action(board, action) -> Board:
    """动作 dict 在 board 上重放（存档 / 宏回放原语）。

    转换 + 校验「该动作确实是本局面的合法移动」（出现在
    ``legal_moves(step)`` 且 moved 一致）+ apply。不合法显式抛错——
    回放层最怕静默容忍一个错动作、然后整条路径跑偏。
    """
    move = action_to_move(board.spec, action)
    if move not in board.legal_moves(move.step):
        raise ValueError(
            f"动作在当前局面不合法: {move.family} t={move.t} "
            f"side={move.side} dir={move.direction} step={move.step} "
            f"moved={move.moved}（不在 legal_moves({move.step}) 内——"
            f"回放基准局面或动作本身有误）")
    return board.apply(move)


register_direction_vocab('square', SQUARE_DIRECTIONS)
