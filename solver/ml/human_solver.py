# -*- coding: utf-8 -*-
r"""
人类模仿求解器 — 加载「人类还原记录」训练的评分模型逐步求解

推理方式（与 train_human_ranker 的数据约定严格一致）：
    1. 状态特征：把当前 game 坐标归一到原点 → 归一化网格 → build_state_features
    2. 候选动作：table_core.forward_neighbors_with_actions(绝对坐标) 枚举全部合法动作
    3. 逐候选：encode_action(绝对 gap_line) 拼接状态特征 → scaler → MLP 打分
    4. 按分数降序尝试 _apply_and_verify（游戏原生 API 逐步验证），
       第一个可执行且不回环的动作被真正提交 —— 输出永远合法可执行

接口签名与 SOLVER_ALGORITHMS 一致，可注册进 GUI「自動求解」。

headless 验证（真实存档开局 → 逐动作原生执行）：
    D:\python\python.exe -m solver.ml.human_solver
"""

import os
import sys
import json
import pickle
import numpy as np

from solver import table_core as tc
from solver.ml.features import build_human_state_features, encode_action
from solver.ml.ai_solver import _apply_and_verify

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH = os.path.join(_HERE, 'data', 'human', 'model_ranker.pkl')
_MAX_STEPS = 500
_MAX_VOID_INC = 2   # 主池允许的 void 增量上限；更大的拆解动作降级为后备（防拆开绕不回）
_PRUNE_TOP = 15     # 只对模型分最高的前 N 个候选做 void 护栏（低分候选轮不到执行）
_model_cache = {}


def load_human_model():
    """加载人类模仿评分模型（带缓存）。"""
    if 'human' in _model_cache:
        return _model_cache['human']
    if not os.path.exists(_MODEL_PATH):
        return None
    with open(_MODEL_PATH, 'rb') as f:
        data = pickle.load(f)
    _model_cache['human'] = data
    return data


def _game_feat(game, m, n, total):
    """当前 game 状态 → (state_feat, coords, min_row, min_col)。

    与训练端 build_human_state_features 严格一致：归一到原点 → 网格矩阵 →
    含聚拢度维度的状态特征；min_row/min_col 用于动作的相对缝隙编码。
    """
    coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
    rs = [r for r, _ in coords]
    cs = [c for _, c in coords]
    mr, mc = min(rs), min(cs)
    norm = frozenset((r - mr, c - mc) for r, c in coords)
    norm_rs = [r for r, _ in norm]
    norm_cs = [c for _, c in norm]
    grid_rows = max(norm_rs) + 1
    grid_cols = max(norm_cs) + 1
    matrix = [[1 if (r, c) in norm else 0 for c in range(grid_cols)]
              for r in range(grid_rows)]
    return build_human_state_features(matrix, m, n), coords, mr, mc


def _void_of_coords(coords, m, n, step):
    """目标窗内空位数 void = m·n − 重叠数（平移不变，用 find_best_window 保持一致语义）。"""
    from solver.ml.gather_solver import find_best_window
    region = find_best_window(coords, m, n, step)
    return m * n - (region[3] if region else 0)


def _decode_next_coords(nb_hash, total):
    """候选的 canonical hash → 归一化坐标集合（平移不变，可与绝对坐标算 void 比较）。"""
    return frozenset(tc.int_to_coords(nb_hash, total))


def ai_human_solve(game, step: int, cancel_check=None, progress_callback=None):
    """
    人类模仿求解主入口。

    参数：与 ai_solver.ai_solve 一致。
    返回：
        (actions, rep_cells) — 完成（还原或达到最大步）
        []                    — 已是还原状态
        None                  — 无模型 / 无候选可执行 / 取消
    """
    if not game.blocks:
        return None

    m, n = game.m, game.n
    total = m * n
    model_data = load_human_model()
    if model_data is None:
        return None
    mlp = model_data['mlp']
    scaler = model_data['scaler']

    actions = []
    rep_cells = []
    visited = set()       # canonical hash（候选去重依据，与 ai_solver 一致）
    visited_raw = set()   # 原始排序坐标（真重复检测）

    for i in range(_MAX_STEPS):
        if cancel_check and cancel_check():
            return None
        if game.is_solved():
            break
        if progress_callback:
            progress_callback({'step': i + 1, 'total': _MAX_STEPS})

        coords = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        coords_sorted = tuple(sorted(coords))
        if coords_sorted in visited_raw:
            break
        visited_raw.add(coords_sorted)
        cur_hash = tc.canonicalize(coords)
        visited.add(cur_hash)

        state_feat, coords, mr, mc = _game_feat(game, m, n, total)

        # 枚举全部合法候选动作（绝对坐标）
        candidates = tc.forward_neighbors_with_actions(coords, step, total)
        if not candidates:
            break

        # 批量打分（候选多 → 一次 predict）
        feats = []
        for _, action in candidates:
            af = encode_action({
                'gap_type': action[0], 'gap_line': action[1],
                'side': action[2], 'move_dir': action[3],
            }, origin=(mr, mc))
            feats.append(np.concatenate([state_feat, af]))
        X = scaler.transform(np.array(feats, dtype=np.float32))
        scores = mlp.predict(X)
        scored = [(float(s), candidates[j][0], candidates[j][1])
                  for j, s in enumerate(scores)]

        # 按分数降序尝试执行（跳过会回到历史状态者）
        # 稳定性护栏：先把「void 大增（拆解失控）」的动作降级到后备池，
        # 只有主池全不可行时才允许拆解——避免重蹈「拆开绕不回来」的下滑。
        scored.sort(key=lambda x: -x[0])
        considered = scored[:_PRUNE_TOP]   # 只护栏高分候选，控制 find_best_window 成本
        rest = scored[_PRUNE_TOP:]
        void_cur = _void_of_coords(coords, m, n, step)
        primary, fallback = [], []
        for best_score, nb_hash, action in considered:
            if nb_hash in visited:
                continue
            nxt = _decode_next_coords(nb_hash, total)
            void_inc = _void_of_coords(nxt, m, n, step) - void_cur
            if void_inc >= _MAX_VOID_INC:
                fallback.append((best_score, nb_hash, action))
            else:
                primary.append((best_score, nb_hash, action))

        ok = False
        for best_score, nb_hash, action in primary:
            ok, rep = _apply_and_verify(game, action, step, nb_hash, total)
            if ok:
                actions.append(action)
                rep_cells.append(rep)
                if progress_callback:
                    progress_callback({'step': i + 1, 'total': _MAX_STEPS,
                                       'candidates': len(scored), 'score': best_score})
                break
        if not ok:
            for best_score, nb_hash, action in fallback:
                ok, rep = _apply_and_verify(game, action, step, nb_hash, total)
                if ok:
                    actions.append(action)
                    rep_cells.append(rep)
                    if progress_callback:
                        progress_callback({'step': i + 1, 'total': _MAX_STEPS,
                                           'candidates': len(scored), 'score': best_score})
                    break
        if not ok:
            # 前 N 名全部执行失败才轮到低分候选（原样尝试，不再护栏）
            for best_score, nb_hash, action in rest:
                if nb_hash in visited:
                    continue
                ok, rep = _apply_and_verify(game, action, step, nb_hash, total)
                if ok:
                    actions.append(action)
                    rep_cells.append(rep)
                    if progress_callback:
                        progress_callback({'step': i + 1, 'total': _MAX_STEPS,
                                           'candidates': len(scored), 'score': best_score})
                    break

        if not ok:
            break

    if game.is_solved():
        return actions, rep_cells
    return actions, rep_cells if actions else None


# ---------------------------------------------------------------------------
# headless 验证：真实人类存档开局 → 逐动作原生执行
# ---------------------------------------------------------------------------
def _load_puzzle_start(m, n, step, save_path):
    """从存档读人类开局状态（snapshot[0]），重建 SliderMatrix。"""
    from game import SliderMatrix
    with open(save_path, encoding='utf-8') as f:
        data = json.load(f)
    p = data['puzzle']
    if not (p['m'] == m and p['n'] == n and p['step'] == step):
        return None
    snap0 = data['history']['snapshots'][0]
    matrix = snap0['matrix']
    b = snap0['bounds']
    coords = [(b['min_row'] + r, b['min_col'] + c)
              for r, row in enumerate(matrix) for c, v in enumerate(row) if v]
    game = SliderMatrix(m, n)
    assert len(coords) == m * n, f"块数不符 {len(coords)} != {m*n}"
    for blk, pos in zip(game.blocks, coords):
        blk.location = list(pos)
    return game


def _demo():
    from solver.ml.gather_solver import gather_metrics
    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'save')
    # 演示用档（存在即用，否则随机）
    demos = [
        ('2-5-5.json', 5, 5, 2),
        ('2-6-6.json', 6, 6, 2),
        ('2-7-7.json', 7, 7, 2),
    ]
    for fname, m, n, step in demos:
        path = os.path.join(save_dir, fname)
        if not os.path.exists(path):
            continue
        game = _load_puzzle_start(m, n, step, path)
        if game is None:
            print(f"跳过 {fname}: 尺寸不符")
            continue

        from solver.state import snapshot
        coords0 = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        met0 = gather_metrics(coords0, m, n)
        print(f"\n{'='*66}\n{fname} ({m}x{n} step={step})  起始聚攏度={met0['score']:.3f} "
              f"void={m*n - met0['overlap']}")

        res = ai_human_solve(game, step)
        if res is None:
            print("  求解失败（无候选/未执行任何动作）")
            continue
        actions, rep_cells = res
        coords1 = frozenset((b.location[0], b.location[1]) for b in game.blocks)
        met1 = gather_metrics(coords1, m, n)
        print(f"  执行 {len(actions)} 步 → 聚攏度 {met0['score']:.3f} → {met1['score']:.3f} "
              f"(void {m*n-met0['overlap']} → {m*n-met1['overlap']})"
              + ("  ✓ 还原！" if game.is_solved() else ""))
        if actions:
            print(f"  前 5 个动作: {[f'{a[0]}{a[1]}/{a[2]}/{a[3]}' for a in actions[:5]]}")
        # 严格校验：动作全程由 _apply_and_verify 在原生 game 上执行成功，
        # 每个提交过的动作都验证过最终坐标哈希匹配，故此处无需再校验。


if __name__ == '__main__':
    _demo()
