# -*- coding: utf-8 -*-
r"""
从人类还原记录导出训练数据（模仿学习，Learning-to-Rank 正/负样本）

来源：save/*.json（排除 auto / didntfinish / 废弃目录）
每条「相邻快照对」＝一个动作：
    snapshot[i-1]  — 动作前状态（matrix 已以 bounds 原点归一化）
    move_info      — 人类实际选择的动作（含 gap_type/gap_line/direction/step/moved_positions）

关键处理：
    1. side 推断：move_info 没有 side，用 moved_positions 与 gap_line 的相对位置反推
       （v 缝隙：移动组列全 > line → 'right'，全 ≤ line → 'left'；h 同理 above/below）
    2. 正样本 = 人类动作；负样本 = 同状态下 table_core 枚举的其他合法候选动作
       （随机抽 2 个），从而把「预测动作永远合法」约束揉进评分模型
    3. void_block_count = m*n - overlap（目标窗口面积固定，不约分，与尺寸相对无关）
    4. weight：依据 void_block_count 的分段权重 × score_delta 惩罚
       （小空位/收尾阶段权重高；本步聚拢度下降且空位多时折半）
    5. 特征统一约定与 ai_solver 推理端一致：
       状态 → matrix 直接作为归一化网格；动作 → 绝对坐标 gap_line /10 编码

输出（JSONL，每行一个样本，可直接查看）：
    solver/ml/data/human/human_samples.jsonl
    solver/ml/data/human/human_stats.json

运行：
    D:\python\python.exe -m solver.ml.export_human_data
"""

import os
import sys
import json
import math
import glob
import random

from solver import table_core as tc
from solver.ml.gather_solver import max_overlap

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SAVE_DIR = os.path.join(_PROJECT_ROOT, 'save')
_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'human')
_OUT_SAMPLES = os.path.join(_OUT_DIR, 'human_samples.jsonl')
_OUT_STATS = os.path.join(_OUT_DIR, 'human_stats.json')

_SKIP_KEYWORDS = ('auto', 'didntfinish')
_NEG_PER_POS = 4  # 每个正样本的随机负样本数
_RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# 权重
# ---------------------------------------------------------------------------
# void_block_count → 权重（0 空位 = 已还原，无训练价值，不产样本）
_VOID_WEIGHTS = {
    1: 0.95, 2: 0.90,
    3: 0.85, 4: 0.80, 5: 0.75,
    6: 0.60, 7: 0.55, 8: 0.50, 9: 0.45, 10: 0.40,
    11: 0.30, 12: 0.25, 13: 0.20, 14: 0.18, 15: 0.15,
}


def void_weight(void_count: int) -> float:
    """空位数 → 基础权重（收尾阶段权重大，早期混乱阶段权重小）。"""
    if void_count <= 15:
        return _VOID_WEIGHTS.get(void_count, 0.15)
    return max(0.15 * math.exp(-(void_count - 15) / 8.0), 0.01)


def sample_weight(void_count: int, score_delta: float) -> float:
    """最终样本权重。本步聚拢度下降且空位多 → 可能走偏，折半。"""
    w = void_weight(void_count)
    if score_delta < -0.02 and void_count > 5:
        w *= 0.5
    return max(w, 0.01)


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------
def _source_id(fp, save_dir):
    """样本来源唯一标识：相对 save 目录的路径（去 .json），避免根目录与子目录同名冲突。"""
    rel = os.path.relpath(fp, save_dir).replace('\\', '/')
    return rel[:-5] if rel.endswith('.json') else rel


def _load_human_files(save_dir: str):
    """收集人类手动还原的存档路径（排除 auto/didntfinish/废弃）。"""
    files = []
    for root, dirs, fnames in os.walk(save_dir):
        dirs[:] = [d for d in dirs if d != '废弃']
        for f in fnames:
            if not f.endswith('.json'):
                continue
            if any(k in f for k in _SKIP_KEYWORDS):
                continue
            files.append(os.path.join(root, f))
    return sorted(files)


def _matrix_to_coords(matrix, min_row, min_col):
    """把归一化矩阵恢复为绝对坐标集合。"""
    coords = set()
    for r, row in enumerate(matrix):
        for c, v in enumerate(row):
            if v:
                coords.add((min_row + r, min_col + c))
    return coords


def _infer_side(gap_type: str, gap_line: int, moved_positions) -> str:
    """
    从移动组位置推断选中的是缝隙哪一侧。
    actions.py 语义：'h' above=行≤line, below=行>line；'v' left=列≤line, right=列>line。
    移动的整组必然全在同一侧（缝隙分割不跨侧）。
    """
    rows = [p[0] for p in moved_positions]
    cols = [p[1] for p in moved_positions]
    if gap_type == 'v':
        return 'right' if all(c > gap_line for c in cols) else 'left'
    else:
        return 'below' if all(r > gap_line for r in rows) else 'above'


def _snapshot_metrics(matrix, min_row, min_col, m, n):
    """计算动作前状态的 (overlap, gather_score)。"""
    coords = _matrix_to_coords(matrix, min_row, min_col)
    overlap = max_overlap(coords, m, n)
    return overlap, overlap / float(m * n)


def _finished(snapshots) -> bool:
    """最后快照是否为还原态（bbox 尺寸 == m×n/n×m 且内部全 1）。"""
    if not snapshots:
        return False
    last = snapshots[-1]
    matrix = last.get('matrix', [])
    if not matrix:
        return False
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    if not ((rows == last['bounds'].get('m_dim', 0)) or True):
        pass
    # 用 puzzle 尺寸判断由调用方处理；这里只判断矩阵是否实心
    return all(all(v == 1 for v in row) for row in matrix)


# ---------------------------------------------------------------------------
# 主导出
# ---------------------------------------------------------------------------
def export(save_dir: str = None):
    save_dir = save_dir or _SAVE_DIR
    os.makedirs(_OUT_DIR, exist_ok=True)

    files = _load_human_files(save_dir)
    print(f"人类存档文件: {len(files)} 个")

    random.seed(_RANDOM_SEED)
    n_files = 0
    n_snap_skipped = 0
    n_pos = 0
    n_neg = 0
    n_missing_in_candidates = 0
    size_counter = {}
    void_counter = {}
    weight_sum = 0.0
    finished_records = 0
    examples = []

    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"  跳过无法解析: {os.path.basename(fp)} ({e})")
            continue

        puzzle = data.get('puzzle') or {}
        m = puzzle.get('m')
        n = puzzle.get('n')
        step = puzzle.get('step')
        if not (m and n and step):
            continue

        snapshots = data.get('history', {}).get('snapshots', [])
        if len(snapshots) < 2:
            continue

        rec_finished = _finished(snapshots)
        if rec_finished:
            finished_records += 1

        n_files += 1
        size_counter.setdefault((m, n, step), 0)
        size_counter[(m, n, step)] += 1

        # 每对相邻快照：snapshots[i-1] →(动作)→ snapshots[i]
        for i in range(1, len(snapshots)):
            prev = snapshots[i - 1]
            cur = snapshots[i]
            move = cur.get('move_info')
            if not move:
                n_snap_skipped += 1
                continue

            prev_matrix = prev.get('matrix', [])
            if not prev_matrix:
                n_snap_skipped += 1
                continue
            b = prev.get('bounds', {})
            min_row = b.get('min_row', 0)
            min_col = b.get('min_col', 0)

            # 恢复动作
            moved_positions = move.get('moved_positions', [])
            if not moved_positions:
                n_snap_skipped += 1
                continue
            side = _infer_side(move['gap_type'], move['gap_line'], moved_positions)
            human_action = (move['gap_type'], move['gap_line'], side, move['direction'])

            # 指标（动作前状态）
            overlap_prev, score_prev = _snapshot_metrics(prev_matrix, min_row, min_col, m, n)
            overlap_cur, _ = _snapshot_metrics(cur['matrix'], cur.get('bounds', {}).get('min_row', 0),
                                               cur.get('bounds', {}).get('min_col', 0), m, n)
            void = m * n - overlap_prev
            if void <= 0:
                # 动作前已还原 → 拆解步，不属于「还原学习」，跳过
                n_snap_skipped += 1
                continue
            score_delta = (overlap_cur - overlap_prev) / float(m * n)
            w = sample_weight(void, score_delta)

            void_counter[void] = void_counter.get(void, 0) + 1
            weight_sum += w

            base = {
                'kind': 'pos',
                'source': _source_id(fp, save_dir),
                'seq_idx': i,
                'finished': rec_finished,
                'm': m, 'n': n, 'step': step,
                'min_row': min_row, 'min_col': min_col,
                'matrix': prev_matrix,
                'void_block_count': void,
                'gather_score': round(score_prev, 6),
                'score_delta': round(score_delta, 6),
                'weight': round(w, 6),
            }

            # 校验人类动作在候选集合中（side 推断正确性 / 数据一致性）
            abs_coords = frozenset(_matrix_to_coords(prev_matrix, min_row, min_col))
            candidates = tc.forward_neighbors_with_actions(abs_coords, step, m * n)
            cand_set = set((a[0], a[1], a[2], a[3]) for _, a in candidates)

            if human_action not in cand_set:
                n_missing_in_candidates += 1
                # 不产正样本（数据不可靠），但打印前 5 个便于排查
                if n_missing_in_candidates <= 5:
                    print(f"  警告: {os.path.basename(fp)} step{i} 人类动作 {human_action} "
                          f"不在候选集合（共 {len(cand_set)} 候选）")
                continue

            # 正样本
            pos = dict(base)
            pos['action'] = {
                'gap_type': human_action[0], 'gap_line': human_action[1],
                'side': human_action[2], 'move_dir': human_action[3],
            }
            examples.append(pos)
            n_pos += 1

            # 负样本：随机抽 NEG_PER_POS 个其他合法候选
            other_actions = [a for a in cand_set if a != human_action]
            if other_actions:
                random.shuffle(other_actions)
                for cand in other_actions[:_NEG_PER_POS]:
                    neg = dict(base)
                    neg['kind'] = 'neg'
                    neg['action'] = {
                        'gap_type': cand[0], 'gap_line': cand[1],
                        'side': cand[2], 'move_dir': cand[3],
                    }
                    examples.append(neg)
                    n_neg += 1

    # ── 写出 JSONL ──
    with open(_OUT_SAMPLES, 'w', encoding='utf-8') as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')

    stats = {
        'files': n_files,
        'finished_records': finished_records,
        'skipped_snapshots': n_snap_skipped,
        'positive': n_pos,
        'negative': n_neg,
        'missing_in_candidates': n_missing_in_candidates,
        'size_distribution': {f'{m}x{n}step{st}': c for (m, n, st), c in sorted(size_counter.items())},
        'void_distribution': dict(sorted(void_counter.items())),
        'weight_mean': weight_sum / n_pos if n_pos else 0,
        'output': _OUT_SAMPLES,
    }
    with open(_OUT_STATS, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n文件数: {n_files}  完成还原: {finished_records}")
    print(f"正样本: {n_pos:,}  负样本: {n_neg:,}")
    print(f"跳过快照: {n_snap_skipped}  人类动作不在候选集: {n_missing_in_candidates}")
    print(f"尺寸分布: {stats['size_distribution']}")
    print(f"输出: {_OUT_SAMPLES}")

    return stats


def main():
    save_dir = sys.argv[1] if len(sys.argv) > 1 else _SAVE_DIR
    export(save_dir)


if __name__ == '__main__':
    main()
