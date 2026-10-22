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
  · **缝序号**：既有引擎的 gap_line 与引擎 t 的关系**随板型/缝族而定**
    ——统一公式 ``t = line_scale · L + 1``（line_scale 挂在 SeamFamily 上：
    方形/立方/米字 d1/d2 = 1，米字 h/v = 4——错位态会出现 ¼ 线，点部
    整数模型必须放大线分辨率）。米字 h/v 的 L 可以是 ¼ 整数，动作 dict
    的 gap_line 随之可能是 0.25 这类值（与 game_mi.gap_candidates 同形）；
  · **方向**：既有格式用字母（方形 a/d/w/s，米字 q/w/e/a/d/z/s/x），
    引擎用方向元组——词汇表按板型注册（square / mi 已注册）；
  · **坐标**：既有格式的位置是**真实坐标**（= 引擎点 / lattice.scale；
    米字 B 晶格是半整数），引擎用整数点——换算按 spec 的 scale 走；
  · **side**：既有格式不记侧（由 moved 相对缝的位置隐含），本层负责推导；
  · **位置形状**：无朝向板型的位置就是点 (r, c)；带朝向板型（米字）
    是 (r, c, q)——与 GUI move_info 的 moved_positions 逐项同形，
    块键 (point, orient) 与它的互换在本层完成（P2 硬骨 7）。

本模块是**迁移件**：既有格式随旧引擎退役时一并删除。引擎核心零依赖
本层，本层也**不 import 任何 game*.py**——迁移方向就是让上层只同
engine 对话，桥自己不能反向依赖旧引擎（方形字母表在此重新声明，
与 game.DIRECTIONS 的等价性由差分测试 K2 钉死）。

纪律（AGENTS.md §2）：不认识的板型/族名/字母、缺键、合并态动作、
跨侧选中片，全部显式抛错，绝不静默兜底。纯逻辑零 pygame。
"""

from .board import Board, Move, _add, _dot  # noqa: F401  （_add/_dot 供本模块复用）
from .mi_geometry import MI_DIRECTIONS  # noqa: E402  （米字字母表随 P2 板型落地）
from .tri_geometry import TRI_DIRECTIONS  # noqa: E402  （三角字母表随 P2 板型落地）


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


def _real_to_point(spec, coords, what):
    """既有格式的真实坐标（= 引擎点 / scale）→ 引擎整数点。

    方形/立方 scale=1：坐标即点，整数校验交给 lattice.valid；
    米字 scale=2：GUI 的 moved_positions 是实坐标 (r, c, q)——A 晶格
    整数、B 晶格半整数。乘 scale 转引擎点，**非 1/scale 倍数显式拒绝**
    （AGENTS.md §2：不静默取整——取整会把一个动作悄悄搬到别的缝上）。
    """
    scale = spec.lattice.scale
    if scale == 1:
        return tuple(coords)
    out = []
    for x in coords:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ValueError(f"{what} 含非数值坐标 {x!r}")
        v = x * scale
        if isinstance(v, float):
            if not v.is_integer():
                raise ValueError(
                    f"{what} 含坐标 {x!r}（不是 1/{scale} 的倍数，"
                    f"无法精确转到引擎整数点）")
            v = int(v)
        out.append(v)
    return tuple(out)


def _norm_keys(raw, spec, what):
    """位置列表 → 排序去重的块键 (point, orient) 元组。

    接受两种位置形状：长度 = dim 的点（orient 缺省 ''，方形/立方），
    或长度 = dim+1 的点 + 朝向（米字 (r, c, q)，与 GUI move_info 的
    moved_positions 逐项同形）。坐标按 lattice.scale 放大成引擎点，
    拒绝非整数倍 / 离格点 / 未知朝向 / 重复。
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(f"{what} 须为非空列表，收到 {raw!r}")
    dim = spec.lattice.dim
    # 三角的既有格式用布尔朝向（up=True/False），引擎用字符串 'up'/'down'——
    # 仅当板型声明这两个朝向时做 bool↔字符串映射，互不影响其他板型。
    tri_orient = (spec.orientations == ('up', 'down'))
    out = []
    for p in raw:
        if not isinstance(p, (list, tuple)):
            raise ValueError(f"{what} 含非法位置 {p!r}")
        if len(p) == dim:
            key = (_real_to_point(spec, p, what), '')
        elif len(p) == dim + 1:
            raw_orient = p[dim]
            if tri_orient and isinstance(raw_orient, bool):
                o = 'up' if raw_orient else 'down'
            elif isinstance(raw_orient, str):
                o = raw_orient
            else:
                raise ValueError(
                    f"{what} 含非法朝向 {raw_orient!r}（须为字符串或布尔）")
            key = (_real_to_point(spec, p[:dim], what), o)
        else:
            raise ValueError(
                f"{what} 含非法位置 {p!r}（长度须为 {dim} 或 {dim + 1}）")
        if not spec.lattice.valid(key[0]):
            raise ValueError(f"{what} 含非法坐标 {p!r}（不在板型格上）")
        if spec.orientations:
            if key[1] not in spec.orientations:
                raise ValueError(
                    f"{what} 含未知朝向 {key[1]!r}（合法: {spec.orientations}）")
        elif key[1] != '':
            raise ValueError(
                f"板型 {spec.name!r} 未声明朝向，位置却带朝向 {key[1]!r}")
        out.append(key)
    if len(set(out)) != len(out):
        raise ValueError(f"{what} 存在重复块键")
    return tuple(sorted(out))


def _keys_to_positions(keys, spec):
    """块键 → 既有格式的位置（真实坐标 = 引擎点 / scale，orient 为 '' 时剥掉）。

    整数结果归一为 int（与 GUI location / gap_candidates 的整数归一同形：
    A 晶格块写 [0, 1, 'N'] 而不是 [0.0, 1.0, 'N']）。
    """
    scale = spec.lattice.scale
    out = []
    for p, o in keys:
        if scale == 1:
            q = p
        else:
            q = tuple(int(x / scale) if x % scale == 0 else x / scale
                      for x in p)
        if o == '':
            out.append(q)
        elif o == 'up':
            out.append(q + (True,))      # 三角既有格式用布尔朝向
        elif o == 'down':
            out.append(q + (False,))
        else:
            out.append(q + (o,))
    return out


# ----------------------------------------------------------------------
# 引擎 Move → 既有格式
# ----------------------------------------------------------------------
def move_to_action(spec, move) -> dict:
    """引擎 Move → history 动作 dict（存档 / moves 日志 / move_info 同格式）。

    差一在本层吸收：``gap_line = (t - 1) / line_scale``（方形/立方/米字
    d1/d2 为 int；米字 h/v 可能是 0.25 这类 ¼ 线，整数时归一成 int，与
    game_mi.gap_candidates 的归一同形）；方向元组 → 字母；坐标转真实
    值。产出可 JSON 序列化（与 GUI 写的 move_info 逐键同形）。
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
    if fam.line_scale == 1:
        line = move.t - 1
    else:
        raw = (move.t - 1) / fam.line_scale
        line = int(raw) if raw.is_integer() else raw
    return {
        'gap_type': move.family,
        'gap_line': line,
        'direction': letters[0],
        'step': move.step,
        'moved_positions': _keys_to_positions(move.moved, spec),
    }


def move_to_record(spec, move) -> dict:
    """引擎 Move → 打乱演示 record dict（与 game.record_shuffle_move 同格式）。

    ``'final'`` 由 moved + step·direction 现算（record 格式本就冗余，
    GUI 重放只消费 moved/final/gap/direction/step）。位置形状与
    move_to_action 一致（无朝向板型剥 orient）。
    """
    action = move_to_action(spec, move)
    delta = tuple(move.step * x for x in move.direction)
    final = []
    for p, o in move.moved:
        q = _add(p, delta)
        final.append(q if o == '' else q + (o,))
    return {
        'moved': action['moved_positions'],
        'final': final,
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
    if isinstance(line, bool) or not isinstance(line, (int, float)):
        raise ValueError(f"gap_line 须为数值，收到 {line!r}")
    scaled = fam.line_scale * line
    if isinstance(scaled, float):
        if not scaled.is_integer():
            raise ValueError(
                f"gap_line {line!r} 不是 1/{fam.line_scale} 的倍数"
                f"（缝族 {fam.name!r} 的线分辨率是 {fam.line_scale}×）")
        scaled = int(scaled)
    step = action['step']
    if type(step) is not int or step < 1:
        raise ValueError(f"step 须为 ≥ 1 的整数，收到 {step!r}")
    moved = _norm_keys(action['moved_positions'], spec, 'moved_positions')
    t = scaled + 1
    vals = {fam.rank_of(p, o) for p, o in moved}
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
    ``board.move_ok``（完整 legal_moves 语义，但不枚举整棵移动树）+
    apply。不合法显式抛错——回放层最怕静默容忍一个错动作、然后整条
    路径跑偏。
    """
    move = action_to_move(board.spec, action)
    if not board.move_ok(move):
        raise ValueError(
            f"动作在当前局面不合法: {move.family} t={move.t} "
            f"side={move.side} dir={move.direction} step={move.step} "
            f"moved={move.moved}（不在 legal_moves({move.step}) 内——"
            f"回放基准局面或动作本身有误）")
    return board.apply(move)


register_direction_vocab('square', SQUARE_DIRECTIONS)
# 米字字母表（引擎坐标 = game_mi.DIRECTIONS × 2，等价性由 L 节差分钉死）
register_direction_vocab('mi', MI_DIRECTIONS)
# 三角字母表（斜坐标单位位移，与 game_triangle.DIRECTIONS 逐项一致，
# 等价性由 M 节差分钉死）
register_direction_vocab('tri', TRI_DIRECTIONS)
