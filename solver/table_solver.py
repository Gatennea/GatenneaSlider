# -*- coding: utf-8 -*-
"""
基于预建 BFS 距离表的查表求解器

从 solver/data/{m}_{n}_{step}/table.pkl 加载距离表，通过沿 dist-1
邻居逐步走回目标状态，重构出最短 Action 序列。

作为 SOLVER_ALGORITHMS 中的第四种算法（'table'），可直接在 GUI 中选用。
"""

import os
import sys
import pickle
from solver import table_core as tc


# ---------------------------------------------------------------------------
# 表加载
#
# ⚠️ 内存预算（2026-11-12 实测，见 docs/spec/内存开销排查_2026-11-12.md）：
#   dict[int, int] 每条约 95 B。4_4_1 断点表 5,135,644 条 = +475 MB，
#   4_4_2 成品表 559,504 条 = +52.7 MB，5_5_2 断点表 612,563 条 = +67.5 MB。
#   旧实现把每张表**永久**存进模块级 _table_cache、无上限也不释放。而
#   solver/auto_solver.py 的第一步「①查表」无条件调 table_solve ⇒ 只要局面
#   恰好落在某个 checkpoint 档位，一次求解就从 138 MB 涨到 613 MB；再点两个
#   尺寸累积到 735 MB（用户偶发的 700MB），且是**常驻不回落**。
#   ⇒ 超过单表预算的大表不进长期缓存，只由本次调用的局部变量持有，
#     调用返回即释放；小表走有总预算的 LRU，避免多档累积。
# ---------------------------------------------------------------------------
_TABLE_ENTRY_BYTES = 100                       # 保守估算，实测约 95 B/条
TABLE_CACHE_MAX_SINGLE = 64 * 1024 * 1024     # 单表 > 64MB 不长期缓存
TABLE_CACHE_MAX_TOTAL = 128 * 1024 * 1024     # 缓存总预算 128MB

_table_cache = {}       # (m, n, step) → dict[int, int]
_table_cache_lru = []   # 档位键，最近使用在后


def _table_est_bytes(tbl):
    """按条目数估算常驻字节数（不遍历整张表，避免为估算付出 500 万次迭代）。"""
    try:
        return len(tbl) * _TABLE_ENTRY_BYTES
    except TypeError:
        return 0


def table_cache_stats():
    """内存观测用：当前缓存了哪些档位、估算字节数、预算上限。"""
    return {
        'entries': [(k, len(v)) for k, v in _table_cache.items()],
        'bytes': sum(_table_est_bytes(v) for v in _table_cache.values()),
        'max_single': TABLE_CACHE_MAX_SINGLE,
        'max_total': TABLE_CACHE_MAX_TOTAL,
    }


def release_table_cache(key=None):
    """释放表缓存。key=None 清全部；返回释放掉的档位数。

    供换局 / 切算法 / 求解收尾显式调用；大表本来就不进缓存，这里主要清小表。
    """
    global _table_cache_lru
    if key is None:
        n = len(_table_cache)
        _table_cache.clear()
        _table_cache_lru = []
        return n
    if key not in _table_cache:
        return 0
    del _table_cache[key]
    if key in _table_cache_lru:
        _table_cache_lru.remove(key)
    return 1


def _get_data_dir():
    """获取 solver/data/ 目录路径，兼容 PyInstaller 打包环境"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        return os.path.join(base, 'solver', 'data')
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def _max_file_bytes():
    """可选硬上限：GATENNEA_TABLE_MAX_FILE_MB，0 / 未设 = 不限。

    默认不限（行为不变）。设置后，超过该大小的 table/checkpoint 直接跳过，
    table_solve 返回 None → 自动求解落到下一候选。玩家若在意内存可用它
    彻底避开「一次载入 164MB 断点表 = 瞬时 +475MB」这个固有峰值。
    """
    try:
        v = float(os.environ.get('GATENNEA_TABLE_MAX_FILE_MB', '0'))
    except (TypeError, ValueError):
        return 0
    return int(v * 1048576) if v > 0 else 0


def load_table(m, n, step):
    """加载距离表（带预算缓存）。优先 table.pkl，建表中回退 checkpoint.pkl。

    大表（估算 > TABLE_CACHE_MAX_SINGLE）**不进缓存**：返回的表只由调用方局部
    变量持有，本次求解结束即释放。小表走 LRU，总字节数超过
    TABLE_CACHE_MAX_TOTAL 时淘汰最久未用的档位。
    """
    key = (m, n, step)
    if key in _table_cache:
        if key in _table_cache_lru:
            _table_cache_lru.remove(key)
        _table_cache_lru.append(key)
        return _table_cache[key]
    data_dir = os.path.join(_get_data_dir(), f'{m}_{n}_{step}')
    cap = _max_file_bytes()
    # 优先成品表，其次断点表
    for fname in ('table.pkl', 'checkpoint.pkl'):
        path = os.path.join(data_dir, fname)
        if os.path.exists(path):
            fsize = os.path.getsize(path)
            if cap and fsize > cap:
                # PyInstaller --noconsole 下 sys.stdout 可能是 None，别让一句
                # 诊断输出把求解路径带崩。
                try:
                    print('[table_solver] 跳过 %s（%.0f MB 超过'
                          ' GATENNEA_TABLE_MAX_FILE_MB 上限 %.0f MB）'
                          % (path, fsize / 1048576.0, cap / 1048576.0),
                          flush=True)
                except Exception:
                    pass
                return None
            # 载入前粗判：文件比单表预算还大，内存里的表必然更大。
            # 先清掉小表缓存，别让「已缓存的 112MB」和「本次临时的 475MB」
            # 叠成 700MB 峰值（2026-11-12 离屏实测 727 → 615 MB）。
            if fsize > TABLE_CACHE_MAX_SINGLE:
                release_table_cache()
            with open(path, 'rb') as f:
                data = pickle.load(f)
            tbl = data if fname == 'table.pkl' else data['dist']
            # 断点表顶层还有 meta / frontier / stats；只留 dist，
            # 别让整包对象陪着表一起活到函数返回之后。
            data = None
            if _table_est_bytes(tbl) <= TABLE_CACHE_MAX_SINGLE:
                _table_cache[key] = tbl
                _table_cache_lru.append(key)
                while (sum(_table_est_bytes(_table_cache[k])
                           for k in _table_cache_lru if k in _table_cache)
                       > TABLE_CACHE_MAX_TOTAL
                       and len(_table_cache_lru) > 1):
                    oldest = _table_cache_lru.pop(0)
                    _table_cache.pop(oldest, None)
            return tbl
    return None


# ---------------------------------------------------------------------------
# 求解器主函数
# ---------------------------------------------------------------------------
def table_solve(game, step: int, cancel_check=None, progress_callback=None):
    """
    查表求解：从当前游戏状态出发，沿预建距离表的最短距离走回目标。

    参数：
        game   : SliderMatrix 实例
        step   : 移动步长
        cancel_check : callable → bool，返回 True 时取消求解
        progress_callback : callable(dict)，接收进度信息

    返回：
        list[Action] | None | False  — 成功返回 Action 列表；表文件不存在返回 None；
                                       状态不在表中/求解失败返回 False；
                                       已是目标返回空列表 []
    """
    # 1. 获取当前坐标
    if not game.blocks:
        return None
    coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
    m, n = game.m, game.n
    total = m * n

    # 2. 规范化并查表
    cur_h = tc.canonicalize(coords)
    table = load_table(m, n, step)
    if table is None:
        return None  # 表文件不存在 → 未找到数据库
    if cur_h not in table:
        return False  # 状态不在表中（死局或表未覆盖）
    distance = table[cur_h]
    if distance == 0:
        return []  # 已是目标状态

    # 3. 沿 dist-1 邻居逐步走回目标
    path = []
    rep_cells = []

    for i in range(distance):
        if cancel_check and cancel_check():
            return None

        if progress_callback:
            remaining = distance - i
            progress_callback({
                'step': i + 1, 'total': distance, 'distance_remaining': remaining,
            })

        cur_coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        found = False
        for nb_h, action in tc.forward_neighbors_with_actions(cur_coords, step, total):
            if nb_h in table and table[nb_h] == table[cur_h] - 1:
                ok, rep = _apply_action_to_target(game, action, step, nb_h, total)
                if not ok:
                    continue
                path.append(action)
                rep_cells.append(rep)
                cur_h = nb_h
                found = True
                break

        if not found:
            return False

    return path, rep_cells


def _apply_action_to_target(game, action, step, target_hash, total):
    """用游戏原生 opt()+try_move()+commit_move() 执行 Action，
    返回 (True, rep_cell) 成功时附带代表方块坐标，失败返回 (False, None)。"""
    from solver.table_core import _side_components, canonicalize, is_single_connected

    gap_type, gap_line, side, move_dir = action
    cur_coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)

    for comp in _side_components(cur_coords, gap_type, gap_line, side):
        for b in game.blocks:
            b.be_opted = False
        rep_cell = next(iter(comp))
        rep_block = None
        for b in game.blocks:
            if (b.location[0], b.location[1]) == rep_cell:
                rep_block = b
                break
        if rep_block is None:
            continue

        game.opt(gap_type, gap_line, rep_block)
        final_positions = game.try_move(move_dir, step)
        if not final_positions:
            continue

        selected = [b for b in game.blocks if b.be_opted]
        test_coords = []
        for b in game.blocks:
            if b.be_opted:
                idx = selected.index(b)
                test_coords.append(tuple(final_positions[idx]))
            else:
                test_coords.append(tuple(b.location))
        if len(test_coords) != total:
            continue
        if not is_single_connected(test_coords):
            continue
        if canonicalize(frozenset(test_coords)) != target_hash:
            continue

        game.commit_move(final_positions)
        for b in game.blocks: b.be_opted = False
        return True, rep_cell

    return False, None
