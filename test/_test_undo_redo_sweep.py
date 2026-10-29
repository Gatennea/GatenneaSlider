# -*- coding: utf-8 -*-
r"""跨档位「滑动 → 撤销到底 → 重做到底」全链路不变量巡检（2026-10-30 自由优化）。

背景：`_test_generic_undo` 只盯 **shield 一个模型板、一步移动**，而且只比
「块数 / 键数 / 连通分量」——**同数不同构抓不到**（块全换了但三个数不变，它照样
判过）。撤销/重做是**所有档位共用**的路径，本测试把同一套不变量铺开：

    square / numbered / triangle / mi / 全部已注册模型

每个档位：
  1. 从还原态走 K 步合法移动（走真实历史：`commit_move` + `game_history.save_snapshot`）；
  2. `gui.undo()` 一路撤到底 → 必须与**起点**逐项相同（块数 / 盘面身份 / 编号 /
     捆绑分组）；
  3. `gui.redo()` 一路重做到底 → 必须与**走完 K 步**时逐项相同；
  4. 撤到底应回到还原态（`is_solved()`）——这条最要紧：编号写了矩阵、模型板写了
     `engine_state`，任何一处还原不干净都会在这里现形。

⚠️ 写这个测试时踩到的坑（别退化）：
  - **内置档位没有 `game.board`**：引擎层只在模型板上挂，摸了就 AttributeError。
    盘面身份必须按形态分派（模型板比 `(point,orient)` 多重集，内置档位比整数矩阵）。
  - **模型板的缝族名不在「方向字母表」里**：`DIRS` 只有 square/triangle/mi 那几张
    方格表，模型板要用引擎自己的 `game._gap_directions(gt)`（`all_gaps()` 返回的
    族名是模型文件里派生的）。
  - **别假设「撤销 K 次 == 走 K 步」**：同一选中会话下的连续移动会被**并进同一张
    快照**（`_move_merge_key`）。所以这里撤到 `can_undo()` 为假为止，不数次数。

跑法：D:/python/python.exe test/_test_undo_redo_sweep.py
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame                                    # noqa: E402
from GUI import SliderGUI                        # noqa: E402
from engine import model_registry                # noqa: E402

FAILS = []
# 每个档位走几步（够暴露「撤到底对不上」，又不至于把测试拖慢）
K_MOVES = 6

# 内置档位的缝族 → 方向字母（模型板不用这张表，见下 _dirs_of）
_DIRS = {'square': {'h': ('a', 'd'), 'v': ('w', 's')},
         'numbered': {'h': ('a', 'd'), 'v': ('w', 's')},
         'triangle': {'h': ('a', 'd'), 'p': ('e', 'z'), 'n': ('w', 'x')},
         'mi': {'h': ('a', 'd'), 'v': ('w', 's'),
                'd1': ('q', 'z'), 'd2': ('e', 'x')}}
# 方形旧引擎没有 all_gaps，按边界盒合成候选缝
_SYNTH = {'square': ('h', 'v'), 'numbered': ('h', 'v')}


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('    FAIL:', msg)
    return bool(cond)


def _gui():
    g = SliderGUI(m=4, n=4, step=1)
    g.animation_enabled = False
    g.animation_duration = 0
    g._readonly = False
    g.save_readonly_flag = False
    g.tut_show_prompt = False
    g.tutorial_active = False
    pygame.display.set_mode((g.screen_width, g.screen_height))
    g.screen = pygame.display.get_surface()
    return g


def _engine(gui):
    """引擎层只在**模型板**上挂 `game.board` / `spec`，内置档位没有。"""
    return getattr(gui.game, 'board', None) is not None


def _state(gui):
    """盘面全态：块数 / 盘面身份 / 连通分量 / 编号 / 捆绑分组。"""
    if _engine(gui):
        ids = tuple(sorted(repr(k) for k in gui.game.board.keys))
        comp = len(gui.game.spec.components(frozenset(gui.game.board.keys)))
        nblk = len(gui.game.board.keys)
    else:
        ids = tuple(tuple(row) for row in gui.game.matrix)
        comp = None
        nblk = sum(1 for row in gui.game.matrix for v in row if v)
    try:
        nums = tuple(sorted(getattr(b, 'number', None) for b in gui.game.blocks
                            if getattr(b, 'number', None)))
    except Exception:
        nums = ()
    groups = getattr(gui.game, 'groups', None)
    return dict(nblk=nblk, ids=ids, comp=comp, nums=nums,
                groups=repr(sorted(groups.items())) if groups else None)


def _open(gui, tgt):
    kind = tgt[0]
    if kind in ('square', 'numbered'):
        _, m, n, step = tgt
        return bool(gui.new_puzzle(m, n, step, numbered=(kind == 'numbered')))
    if kind == 'triangle':
        _, k, step = tgt
        return bool(gui.new_triangle_puzzle(k, step))
    if kind == 'mi':
        _, m, n, step = tgt
        return bool(gui.new_mi_puzzle(m, n, step))
    if kind == 'model':
        _, name, step = tgt
        return bool(gui.new_model_puzzle(name, step))
    raise ValueError(kind)


def targets():
    ts = []
    for m, n, step in ((3, 3, 1), (4, 4, 1), (4, 4, 2), (5, 5, 1)):
        ts.append(('square', m, n, step))
    for m, n, step in ((4, 4, 1), (6, 6, 2)):
        ts.append(('numbered', m, n, step))
    for k, step in ((3, 1), (4, 1), (4, 2)):
        ts.append(('triangle', k, step))
    for m, n, step in ((3, 3, 1), (4, 4, 2)):
        ts.append(('mi', m, n, step))
    for name in sorted(model_registry.loaded() or {}):
        ts.append(('model', name, 1))
    return ts


def _gaps_of(game, kind):
    """当前全部候选缝（模型板 / 三角 / 米字有 all_gaps；方形按边界盒合成）。"""
    if hasattr(game, 'all_gaps'):
        return sorted(game.all_gaps(), key=lambda x: (str(x[0]), x[1]))
    b = game.get_boundaries()
    out = []
    for gt in _SYNTH[kind]:
        lo, hi = ((b['min_row'], b['max_row']) if gt == 'h'
                  else (b['min_col'], b['max_col']))
        out.extend((gt, ln) for ln in range(lo, hi))
    return sorted(out, key=lambda x: (str(x[0]), x[1]))


def _dirs_of(game, kind, gt):
    """缝族 → 方向字母。模型板用引擎自己的表（族名是模型文件派生的）。"""
    if hasattr(game, '_gap_directions'):
        return tuple(game._gap_directions(gt))
    return _DIRS.get(kind, {}).get(gt, ())


def _block_at(game, cell):
    if hasattr(game, 'block_at'):
        try:
            b = game.block_at(cell)
        except Exception:
            b = None
        if b is not None:
            return b
    return next((b for b in game.blocks if tuple(b.location) == cell), None)


def _one_move(gui, kind, rnd):
    """走一步合法移动（真实契约：opt → try_move_ex → commit_move）。

    返回 (gap_type, line, direction, 移动前选中块坐标列表) 或 None（走不动）。
    选块**按位置**取，不按 blocks 索引——块序在两套引擎下不同，按索引取会分叉。

    ⚠️ 坐标必须在 `commit_move` **之前**采集：`b.location` 是可变对象，
    commit 会原地改写它；而 move_info 的 moved_positions 语义就是「移动前」。
    传空列表会让 `expand_snapshot_moves` 直接走不展开的兜底 —— 合并路径就
    永远验不到了（2026-10-30 踩过）。
    """
    g = gui.game
    gaps = _gaps_of(g, kind)
    if not gaps:
        return None
    rnd.shuffle(gaps)
    cells = sorted(tuple(b.location) for b in g.blocks)
    if not cells:
        return None
    for gt, line in gaps[:40]:
        for d in _dirs_of(g, kind, gt):
            for cell in rnd.sample(cells, min(len(cells), 6)):
                blk = _block_at(g, cell)
                if blk is None:
                    continue
                g.opt(gt, line, blk)
                final, reason = g.try_move_ex(d, 1)
                if not final:
                    continue        # 含 'all_selected'（全员选中=纯平移，无意义）
                sel = [tuple(b.location) for b in g.blocks if b.be_opted]
                g.commit_move(final)
                return (gt, line, d, sel)
    return None


def _run_one(gui, tgt, merge):
    """跑一个档位。merge=True → 全部移动并入同一「选中会话」（模拟玩家
    选中一条缝连按方向键）。返回实际走的步数。"""
    kind = tgt[0]
    tag = '/'.join(str(x) for x in tgt) + ('[合并]' if merge else '[不合并]')
    if not check(_open(gui, tgt), f'{tag} 应能开局'):
        return 0
    s0 = _state(gui)
    rnd = random.Random(11)          # 固定种子：判据可复现，不 flaky
    moved = []
    for _ in range(K_MOVES):
        mv = _one_move(gui, kind, rnd)
        if mv is None:
            break
        gt, line, d, sel = mv
        moved.append(mv)
        # 与 GUI 真路径一致：move_info 带「移动前」坐标；session_key 恒定 →
        # 并入同一条快照（steps>1），撤销时要靠 _ensure_step_granularity 拆开。
        gui.game_history.save_snapshot(
            gui.game, {'gap_type': gt, 'gap_line': line, 'direction': d,
                       'step': 1,
                       'moved_positions': [list(x) for x in sel]},
            'SAME' if merge else None)
    if not check(len(moved) >= 2,
                 f'{tag} 还原态至少应能走 2 步（实测 {len(moved)} 步）'):
        return 0
    sk = _state(gui)
    # 非空判据：走完 K 步盘面必须真的变了。少了这条，「走出去又原样挪回来」
    # 或者 commit 出原地不动的伪步，会让上下游比较全部退化成自己比自己，
    # 巡检看起来全绿其实什么都没验。
    check(sk['ids'] != s0['ids'],
          f'{tag} 走完 {len(moved)} 步后盘面应真的变了（否则本条巡检是空的）')

    # 撤销到底
    n_undo = 0
    while gui.game_history.can_undo():
        before = gui.game_history.history_index
        try:
            gui.undo()
        except Exception as exc:                 # 撤销整条被异常弄死也算失败
            check(False, f'{tag} undo 抛异常：{exc!r}')
            break
        if gui.game_history.history_index == before:
            break            # 没推进：别死循环
        n_undo += 1
        if n_undo > 200:
            break
    check(n_undo >= 1, f'{tag} 应至少撤销 1 步（实测 {n_undo}）')
    back = _state(gui)
    check(back['nblk'] == s0['nblk'],
          f'{tag} 撤到底块数应回到起点（{back["nblk"]} vs {s0["nblk"]}）')
    check(back['ids'] == s0['ids'], f'{tag} 撤到底盘面身份应回到起点')
    if s0['comp'] is not None:
        check(back['comp'] == s0['comp'],
              f'{tag} 撤到底连通分量应回到起点'
              f'（{back["comp"]} vs {s0["comp"]}）')
    check(back['nums'] == s0['nums'], f'{tag} 撤到底编号集合应回到起点')
    check(back['groups'] == s0['groups'], f'{tag} 撤到底捆绑分组应回到起点')
    try:
        solved = gui.game.is_solved()
    except Exception:
        solved = None
    if solved is not None:
        check(solved, f'{tag} 撤到底应回到还原态（is_solved 实测 {solved}）')

    # 重做到底
    n_redo = 0
    while gui.game_history.can_redo():
        before = gui.game_history.history_index
        try:
            gui.redo()
        except Exception as exc:
            check(False, f'{tag} redo 抛异常：{exc!r}')
            break
        if gui.game_history.history_index == before:
            break
        n_redo += 1
        if n_redo > 200:
            break
    fwd = _state(gui)
    check(fwd['nblk'] == sk['nblk'],
          f'{tag} 重做到底块数应回到走完时（{fwd["nblk"]} vs {sk["nblk"]}）')
    check(fwd['ids'] == sk['ids'], f'{tag} 重做到底盘面身份应回到走完时')
    if sk['comp'] is not None:
        check(fwd['comp'] == sk['comp'],
              f'{tag} 重做到底连通分量应回到走完时'
              f'（{fwd["comp"]} vs {sk["comp"]}）')
    check(fwd['nums'] == sk['nums'], f'{tag} 重做到底编号集合应回到走完时')
    check(fwd['groups'] == sk['groups'], f'{tag} 重做到底捆绑分组应回到走完时')
    return len(moved)


def main():
    model_registry.install()
    gui = _gui()
    ts = targets()
    moved_total = 0
    # 两种模式都要跑：
    #   [不合并] 每步一条快照（跨会话移动 / 引擎板型的现状）
    #   [合并]   同一选中会话连走 → 一条 steps>1 的快照，撤销要靠
    #            _ensure_step_granularity 惰性拆开 —— 2026-10-30 抓到的
    #            「拆出的中间态丢 groups / 引擎板掉块」就在这条路上。
    # 注意：三角 / 米字 / 模型板在真 GUI 里本来就不合并（见 gui/drag.py 的
    # _move_merge_key），那几行是**健壮性**检查（旧档 / 导入数据可能带这种段）。
    for merge in (False, True):
        for tgt in ts:
            moved_total += _run_one(gui, tgt, merge)

    print()
    if FAILS:
        print(f'共 {len(FAILS)} 项失败：')
        for f in FAILS:
            print('  ·', f)
        sys.exit(1)
    print(f'跨档位撤销/重做巡检：{len(ts)} 个档位 × 合并/不合并、'
          f'共 {moved_total} 步，全部无损')


if __name__ == '__main__':
    main()
