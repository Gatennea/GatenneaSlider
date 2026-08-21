# -*- coding: utf-8 -*-
"""
贪心爬山求解器模块

提供：
    greedy_hill_climbing_solve(game, step, max_steps, cancel_check, progress_callback)
        - 随机局部搜索求解，不追求最小步数，只求快速找到解

算法特点：
    - 从当前状态出发，随机探索动作序列
    - 维护最佳 Score，跟踪到最佳状态的路径
    - 检测到原地踏步时随机扰动跳出
    - 超过步数限制则返回失败（不保证解存在）
    - 适合快速求解，不保证最优性
"""

import time
import random
from copy import deepcopy

from game import SliderMatrix
from solver.state import state_key, snapshot, restore
from solver.actions import enumerate_valid_actions, apply_action, is_inverse_action
from solver.heuristic import compute_score, is_solved_state

# 每步预览的动作数量
GREEDY_SAMPLE_SIZE = 10
# 局部最优检测阈值
NO_IMPROVE_LIMIT = 25
# 随机扰动步数
PERTURB_STEPS = 5
# 最大步数上限
DEFAULT_MAX_STEPS = 800
# 循环检测窗口
CYCLE_WINDOW = 8


def greedy_hill_climbing_solve(game: SliderMatrix, step: int,
                                max_steps: int = DEFAULT_MAX_STEPS,
                                cancel_check=None,
                                progress_callback=None) -> list | None:
    """
    随机局部搜索求解器

    每一步随机采样候选动作，选择 Score 最高的执行。
    当陷入局部最优时触发随机扰动。检测到循环时加大扰动幅度。

    参数：
        game: SliderMatrix 实例
        step: 移动步长
        max_steps: 最大步数限制
        cancel_check: callable() → bool，返回 True 取消搜索
        progress_callback: callable(info_dict)，进度回调

    返回：
        list[Action] | None
    """
    game_copy = deepcopy(game)

    if game_copy.is_solved():
        return []

    path = []
    visited = {}  # state_key -> last_step_idx
    no_improve_count = 0
    best_score = compute_score(game_copy)
    start_time = time.time()

    # 记录到最佳状态的路径
    best_path = []
    best_path_score = best_score

    for iteration in range(max_steps):
        # 取消检查
        if cancel_check and cancel_check():
            return None

        # 进度回调
        if progress_callback and iteration % 10 == 0:
            elapsed = time.time() - start_time
            progress_callback({
                'depth': len(path),
                'bound': 0,
                'nodes': iteration,
                'path_len': len(path),
                'path_preview': _format_path_preview(path),
                'elapsed': elapsed,
                'stage': 'GREEDY',
                'score': best_score,
            })

        if is_solved_state(game_copy):
            return path

        # 获取合法动作，排除逆向
        valid_actions = enumerate_valid_actions(game_copy, step)
        filtered = [a for a in valid_actions
                    if not path or not is_inverse_action(path[-1], a)]

        if not filtered:
            no_improve_count = NO_IMPROVE_LIMIT + 1

        # 循环检测
        key = state_key(game_copy)
        if key in visited:
            steps_ago = len(path) - visited[key]
            if steps_ago <= CYCLE_WINDOW:
                no_improve_count = max(no_improve_count, NO_IMPROVE_LIMIT // 2)
        visited[key] = len(path)

        # 触发随机扰动
        if no_improve_count >= NO_IMPROVE_LIMIT:
            perturb_count = min(PERTURB_STEPS, len(filtered) if filtered else 0)
            perturb_actions = []
            for _ in range(perturb_count):
                if not filtered:
                    break
                action = random.choice(filtered)
                if apply_action(game_copy, action, step):
                    path.append(action)
                    perturb_actions.append(action)
                    # 重新过滤
                    filtered = [a for a in filtered
                                if not is_inverse_action(action, a)]
            new_score = compute_score(game_copy)
            if new_score > best_score:
                best_score = new_score
            no_improve_count = 0
            continue

        # 随机采样候选动作并打分
        sample = filtered[:]
        if len(sample) > GREEDY_SAMPLE_SIZE:
            sample = random.sample(sample, GREEDY_SAMPLE_SIZE)

        scored_actions = []  # (score, action)
        for action in sample:
            saved = snapshot(game_copy)
            if not apply_action(game_copy, action, step):
                restore(game_copy, saved)
                continue
            s = compute_score(game_copy)
            restore(game_copy, saved)
            scored_actions.append((s, action))

        if not scored_actions:
            no_improve_count += 1
            continue

        # 排序：高分优先
        scored_actions.sort(key=lambda x: x[0], reverse=True)

        # 选择策略：以 70% 概率选最佳，30% 概率从 top-3 随机选
        top_n = min(3, len(scored_actions))
        if random.random() < 0.7 or top_n == 1:
            selected_score, selected_action = scored_actions[0]
        else:
            idx = random.randint(0, top_n - 1)
            selected_score, selected_action = scored_actions[idx]

        # 执行动作
        if not apply_action(game_copy, selected_action, step):
            no_improve_count += 1
            continue

        path.append(selected_action)

        # 更新分数
        if selected_score > best_score + 0.0001:
            best_score = selected_score
            no_improve_count = 0
            # 记录最佳路径
            if selected_score > best_path_score:
                best_path_score = selected_score
                best_path = path[:]
        else:
            no_improve_count += 1

    # 超过最大步数
    return None


def _format_path_preview(path: list) -> str:
    """将路径格式化为简短的可读字串"""
    if not path:
        return ''
    recent = path[-3:]
    parts = []
    for action in recent:
        gap_dir, gap_line, side, move_dir = action
        side_short = {'above': '上', 'below': '下', 'left': '左', 'right': '右'}.get(side, side)
        dir_short = {'w': '↑', 's': '↓', 'a': '←', 'd': '→'}.get(move_dir, move_dir)
        parts.append(f"{gap_dir}{gap_line}{side_short}{dir_short}")
    return ' '.join(parts)
