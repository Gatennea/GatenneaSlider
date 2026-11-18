# -*- coding: utf-8 -*-
"""三维创造模式：第 0 步（纯数据 / 判定层）。

本模块只做三件事，不 import pygame、不碰 `mode_allowed`、不碰 GUI：

1. 在 m×n×d 容积内增删单位立方体，维护一份草稿格集合；
2. 把草稿格集合无损地挂到 `EngineGame`（`apply_pattern`），供渲染 / 试玩；
3. 给出保存门与「能否还原」的**必要条件**检查。

为什么先做这一层：三维编辑器的点击翻译、幽灵预览、样式读写都依赖同一份
格集合与同一套判定。先把判定写成可 headless 测试的纯函数，后面 GUI 只负责
「点哪个面 → 调 add/remove」，不会把连通 / 冻形 / mod 配额散落在事件层。

口径（见 `docs/spec/三维创造模式方案_2026-11-18.md` §3）：

- 编辑中途允许空盘 / 不连通（不然没法挖成两半再合回去）；
- 保存 / 开玩才过门：非空 + 单一连通 + 有合法移动（至少一步）；
- 自订还原态再多一道必要条件：块数等于某个 m'×n'×d' 实心长方体，且各
  mod 类 `(r%step, c%step, d%step)` 的配额与那个长方体一致；
- 以上只叫「没被必要条件排除」，**不承诺充分可解**——三维求解器未接，
  存在满足必要条件的死局，UI 文案必须如实。

坐标：逻辑 `(r, c, d)`，与引擎 / 存档 / `cubic_pick` 一致；世界映射
`(X, Y, Z)=(c, d, r)` 是渲染层的事，本模块不换序。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import permutations

from .adapter import create_adapter_puzzle
from .board import Board
from .cubic_view import neighbor_location


#: 保存门 / 必要条件的原因码 → 给玩家看的一句话。
REASON_TEXT = {
    'empty': '至少要放一块',
    'disconnected': '所有滑块必须连成一体',
    'frozen': '没有任何合法移动（冻形）',
    'not_cuboid': '块数凑不出任何 m×n×d 实心长方体',
    'mod_mismatch': '各 mod 类配额与长方体不一致（step 分组被破坏）',
}


@dataclass(frozen=True)
class EditResult:
    """一次放块 / 挖块的结果。失败时 reason 是稳定代码，不靠中文匹配。"""

    ok: bool
    reason: str = ''


@dataclass(frozen=True)
class GateResult:
    """保存门 / 必要条件检查结果。

    reasons 保留全部原因码（不是只报第一条），方便 UI 一次说清；
    ok=True 也只表示「没被必要条件排除」，不表示保证可解。
    """

    ok: bool
    reasons: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        if not self.reasons:
            return ''
        return '；'.join(REASON_TEXT.get(r, r) for r in self.reasons)

    @property
    def uncertain(self) -> bool:
        """过了门但仍是「只做必要条件」的提示语，UI 可原样显示。"""
        return self.ok


def normalize_cells(cells, m: int, n: int, d: int) -> frozenset:
    """把任意可迭代位置规整成合法的 (r, c, d) 整数集合。

    越界 / 非整数 / 长度不足直接 ValueError——静默夹紧会让玩家造出一个
    自己看不见的块。空集合合法（编辑中途允许空盘）。
    """
    out = set()
    for p in cells or ():
        if not isinstance(p, (tuple, list)) or len(p) != 3:
            raise ValueError(f'三维位置必须是 (r, c, d)，收到 {p!r}')
        if any(isinstance(v, bool) or not isinstance(v, int) for v in p):
            raise ValueError(f'三维位置必须是整数，收到 {p!r}')
        vals = tuple(p)
        r, c, dep = vals
        if not (0 <= r < m and 0 <= c < n and 0 <= dep < d):
            raise ValueError(
                f'三维位置 {p!r} 越过容积 {m}×{n}×{d}')
        out.add(vals)
    return frozenset(out)


def full_cells(m: int, n: int, d: int) -> frozenset:
    """还原态：m×n×d 实心长方体。"""
    return frozenset((r, c, dep) for r in range(m)
                     for c in range(n) for dep in range(d))


def in_volume(loc, m: int, n: int, d: int) -> bool:
    """逻辑坐标是否在当前容积内。"""
    return (isinstance(loc, (tuple, list)) and len(loc) == 3
            and 0 <= int(loc[0]) < m and 0 <= int(loc[1]) < n
            and 0 <= int(loc[2]) < d)


class CubicDraft:
    """一份三维草稿局面：格集合 + 增删 + 保存门。

    典型用法（GUI 事件层）::

        draft = CubicDraft(m, n, d, step)
        draft.remove(face['loc'])          # 点块挖掉
        target = neighbor_location(face['loc'], face['axis'], face['sign'])
        draft.add(target)                  # 点面外放一块

    每次增删只改集合；`to_game()` 才重建 `EngineGame`，渲染 / 试玩共用。
    """

    def __init__(self, m: int, n: int, d: int, step: int = 1, cells=None,
                 *, solved_cells=None):
        if not all(isinstance(v, int) and v >= 1 for v in (m, n, d)):
            raise ValueError(f'三维容积须为正整数，收到 {(m, n, d)!r}')
        if not isinstance(step, int) or step < 1:
            raise ValueError(f'三维等级须为正整数，收到 {step!r}')
        self.m, self.n, self.d = m, n, d
        self.step = step
        if cells is None:
            self._cells = full_cells(m, n, d)
        else:
            self._cells = normalize_cells(cells, m, n, d)
        # 「还原态」不一定是编辑包围盒本身：滑过一步的局，块可能跑出原来的
        # m×n×d（例如 4×4×4 的 d 层推到 1..4），编辑器要拿当前包围盒当画布，
        # 但「还原态」仍应是原来那个 4×4×4。solved_cells 就是这个目标格集。
        self._solved_cells = normalize_cells(
            full_cells(m, n, d) if solved_cells is None else solved_cells,
            m, n, d)
        self._game = None

    # ---------------------------------------------------------------- 状态
    @property
    def cells(self) -> frozenset:
        return self._cells

    @property
    def solved_cells(self) -> frozenset:
        """「还原态」格集；默认是 m×n×d 实心，滑过一步时可另行指定。"""
        return self._solved_cells

    def __len__(self):
        return len(self._cells)

    def contains(self, loc) -> bool:
        return tuple(loc) in self._cells

    def set_cells(self, cells) -> None:
        self._cells = normalize_cells(cells, self.m, self.n, self.d)
        self._game = None

    def reset_solved(self) -> None:
        """回到还原态（草稿，不碰当前局的正式历史）。"""
        self._cells = self._solved_cells
        self._game = None

    def clear(self) -> None:
        """清空到空盘（编辑中途允许）。"""
        self._cells = frozenset()
        self._game = None

    # ---------------------------------------------------------------- 增删
    def add(self, loc) -> EditResult:
        """在空格放一块。

        2026-11-18 用户口径：创造模式的「容积」不该是放置墙——玩家从任意
        可见面向外搭块都应该成功。这里不再拒绝越界，而是把草稿的包围盒
        向目标格扩一格（整体平移回 0 起点），因此 ``m/n/d`` 只是当前草稿
        范围，不是限制。已有块仍然拒绝。
        """
        p = tuple(int(v) for v in loc)
        if p in self._cells:
            return EditResult(False, 'occupied')
        p = self._grow_to_include(p)
        self._cells = self._cells | {p}
        self._game = None
        return EditResult(True)

    def _grow_to_include(self, p) -> tuple:
        """把草稿范围扩到包含 p；必要时整体平移，保证坐标非负。

        返回**平移后的目标格**：调用方必须用返回值写回，不能拿原始 p
        去加（负坐标时 p 已不在新坐标系里）。``solved_cells`` 一起平移，
        否则「还原态」会和当前格错位；mod 配额检查本来按最小角归一
        （``_mod_quota_ok``），平移不改变判定。已有范围里的空白边不主动
        裁掉——只扩不缩，避免每次放块都改坐标。
        """
        if in_volume(p, self.m, self.n, self.d):
            return p
        lo = [min(0, int(p[i])) for i in range(3)]
        hi = [max(self.m - 1, int(p[i])) for i in range(3)]
        for q in self._cells | self._solved_cells:
            for i in range(3):
                lo[i] = min(lo[i], int(q[i]))
                hi[i] = max(hi[i], int(q[i]))
        shift = tuple(-v for v in lo)
        self._cells = frozenset((q[0] + shift[0], q[1] + shift[1],
                                 q[2] + shift[2]) for q in self._cells)
        self._solved_cells = frozenset(
            (q[0] + shift[0], q[1] + shift[1], q[2] + shift[2])
            for q in self._solved_cells)
        self.m, self.n, self.d = (hi[i] - lo[i] + 1 for i in range(3))
        return (p[0] + shift[0], p[1] + shift[1], p[2] + shift[2])

    def remove(self, loc) -> EditResult:
        """挖掉一块。空格 / 越界都拒绝。"""
        if not in_volume(loc, self.m, self.n, self.d):
            return EditResult(False, 'out_of_bounds')
        p = tuple(int(v) for v in loc)
        if p not in self._cells:
            return EditResult(False, 'empty')
        self._cells = self._cells - {p}
        self._game = None
        return EditResult(True)

    def toggle(self, loc) -> EditResult:
        """点同一格：有块就挖，没块就放（给「单键切换」工具用）。"""
        if self.contains(loc):
            return self.remove(loc)
        return self.add(loc)

    def neighbor(self, loc, axis: int, sign: int) -> tuple:
        """该面另一侧邻格（轴映射交给 `cubic_view.neighbor_location`）。"""
        return tuple(neighbor_location(loc, axis, sign))

    # ---------------------------------------------------------------- 重建
    def to_game(self):
        """按草稿格集合重建一个 `EngineGame`（不写当前局的正式历史）。"""
        game = create_adapter_puzzle('cubic', self.m, self.n, self.step,
                                     depth=self.d)
        if self._cells != full_cells(self.m, self.n, self.d):
            # apply_pattern 拒绝空列表；空盘时保留新建游戏的满盘再清空，
            # 但这里只用于判定，不交给渲染。渲染侧为「空盘」应直接不画块。
            if self._cells:
                game.apply_pattern(sorted(self._cells))
            else:
                # 没有公开的 clear 接口；空盘只用于判定，调用方应先用
                # check_save 看到 empty，不会把它当成可玩局面。
                pass
        return game

    def apply_to(self, game) -> None:
        """把草稿挂到已有 EngineGame（供编辑器预览 / 试玩共用）。

        空盘走 `game.board = Board(spec, ())`：`apply_pattern` 明确拒绝空
        列表，而编辑器中途允许空盘（详见模块头）。走 board setter 会同步
        spec 并重建块视图，等价于「空局面」而不是静默保留上一步的块。
        """
        if not self._cells:
            game.board = Board(game.spec, ())
            return
        game.apply_pattern(sorted(self._cells))

    # ---------------------------------------------------------------- 判定
    def _connected(self) -> bool:
        if not self._cells:
            return False
        return bool(self.to_game().is_single_connected(set(self._cells)))

    def _has_move(self) -> bool:
        if not self._cells:
            return False
        return bool(self.to_game().has_legal_move(self.step))

    def _mod_counter(self, cells, step: int) -> Counter:
        return Counter((r % step, c % step, dep % step)
                       for r, c, dep in cells)

    def _cuboid_candidates(self):
        """所有能塞进当前容积、块数相符的实心长方体尺寸（含朝向）。"""
        total = len(self._cells)
        seen = set()
        for a in range(1, self.m + 1):
            for b in range(1, self.n + 1):
                for c in range(1, self.d + 1):
                    if a * b * c != total:
                        continue
                    for dims in set(permutations((a, b, c))):
                        if dims not in seen:
                            seen.add(dims)
                            yield dims

    def _mod_quota_ok(self) -> bool:
        """块数 = 某长方体，且各 mod 类配额与它一致（必要条件）。"""
        if not self._cells:
            return False
        # 平移归一：局面整体挪过不影响「能不能还原」；归一后只枚举长方体
        # 的落点，避免把「还原态画在盒子另一角」误判成配额不对。
        mins = [min(p[i] for p in self._cells) for i in range(3)]
        norm = [(p[0] - mins[0], p[1] - mins[1], p[2] - mins[2])
                for p in self._cells]
        cur = self._mod_counter(norm, self.step)
        for a, b, c in self._cuboid_candidates():
            # 不做「当前局面最大坐标须装进候选长方体」的额外限制：草稿
            # 可以暂时散到目标盒外（编辑中途允许拆成两半），能不能还原
            # 只看块数与 mod 配额；候选只要求自身能塞进当前容积。
            for ox in range(0, self.m - a + 1):
                for oy in range(0, self.n - b + 1):
                    for oz in range(0, self.d - c + 1):
                        cube = [(ox + i, oy + j, oz + k)
                                for i in range(a) for j in range(b)
                                for k in range(c)]
                        if self._mod_counter(cube, self.step) == cur:
                            return True
        return False

    def check_save(self) -> GateResult:
        """保存 / 开玩门：非空 + 单一连通 + 至少一步合法移动。

        自订还原态还要 `check_restorable()` 的块数 / mod 配额；本方法只做
        「这份局面能不能当谜题」的玩法门，样式目标另走 restorable。
        """
        reasons = []
        if not self._cells:
            reasons.append('empty')
        else:
            if not self._connected():
                reasons.append('disconnected')
            if not self._has_move():
                reasons.append('frozen')
        return GateResult(not reasons, tuple(reasons))

    def check_restorable(self) -> GateResult:
        """自订还原态的必要条件：玩法门 + 块数/长方体 + mod 配额。

        注意：通过只代表「没被必要条件排除」，三维求解器未接前不能承诺
        一定有解；UI 必须把这句话带上。
        """
        gate = self.check_save()
        reasons = list(gate.reasons)
        if self._cells:
            if not any(self._cuboid_candidates()):
                reasons.append('not_cuboid')
            elif not self._mod_quota_ok():
                reasons.append('mod_mismatch')
        return GateResult(not reasons, tuple(dict.fromkeys(reasons)))
