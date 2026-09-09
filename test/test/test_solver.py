# -*- coding: utf-8 -*-
"""
求解器測試腳本

測試流程：
    1. 從復原狀態 shuffle → 求解 → 驗證復原
    2. 基準測試：記錄平均步數、搜索時間、成功率
"""

import sys
import os
import time

# 確保可以導入項目模塊
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game import SliderMatrix
from solver.state import state_key, snapshot, restore, encode_state
from solver.actions import enumerate_valid_actions, apply_action, is_inverse_action
from solver.heuristic import compute_score, heuristic, is_solved_state
from solver.ida_star import ida_star_solve


def test_basic_components():
    """測試基礎組件是否正常工作"""
    print("=" * 60)
    print("測試 1: 基礎組件")
    print("=" * 60)
    
    game = SliderMatrix(4, 4)
    
    # 測試 state_key
    key = state_key(game)
    print(f"  復原狀態的 state_key 大小: {len(key)}  (應為 16)")
    assert len(key) == 16, f"預期 16 個方塊，實際 {len(key)}"
    
    # 測試 encode_state
    vec = encode_state(game)
    print(f"  復原狀態的狀態向量: {[round(v, 3) for v in vec]}")
    
    # 測試 Score
    score = compute_score(game)
    print(f"  復原狀態 Score: {score:.4f}  (應為 1.0)")
    assert score == 1.0, f"預期 1.0，實際 {score}"
    
    # 測試 heuristic
    h = heuristic(game)
    print(f"  復原狀態 heuristic: {h:.4f}  (應為 0.0)")
    assert h == 0.0, f"預期 0.0，實際 {h}"
    
    # 測試 is_solved
    assert game.is_solved(), "復原狀態應該判定為已解"
    print(f"  is_solved: {game.is_solved()}  (應為 True)")
    
    # 測試快照保存/恢復
    game.shuffle(attempts=10, step=2)
    snap = snapshot(game)
    game2 = SliderMatrix(4, 4)
    restore(game2, snap)
    key1 = state_key(game)
    key2 = state_key(game2)
    print(f"  快照恢復後狀態一致: {key1 == key2}  (應為 True)")
    assert key1 == key2, "快照恢復失敗"
    
    # 測試動作枚舉
    actions = enumerate_valid_actions(game, step=2)
    print(f"  亂序狀態的合法動作數: {len(actions)}")
    assert len(actions) > 0, "應該有合法動作"
    
    # 測試 apply_action
    saved = snapshot(game)
    action = actions[0]
    ok = apply_action(game, action, step=2)
    print(f"  執行第一個動作: {action} -> {ok}")
    
    # 測試逆向檢測
    inv = list(actions)
    has_inv = any(is_inverse_action(action, a) for a in inv)
    print(f"  存在逆向動作: {has_inv}")
    
    restore(game, saved)  # 還原
    
    print("  基礎組件全部通過!\n")


def test_shuffle_solve_cycle(m=4, n=4, step=2, shuffle_attempts=20, max_depth=80):
    """
    測試完整流程：復原 → 打亂 → 求解 → 驗證
    
    參數：
        m, n: 棋盤尺寸
        step: 移動步長
        shuffle_attempts: 打亂次數
        max_depth: IDA* 最大搜索深度
    
    返回：
        (success, solution_length, elapsed_time)
    """
    game = SliderMatrix(m, n)
    
    # 打亂
    game.shuffle(attempts=shuffle_attempts, step=step)
    
    if game.is_solved():
        # 隨機打亂後仍然是復原狀態，跳過
        return True, [], 0.0
    
    # 求解
    start_time = time.time()
    solution = ida_star_solve(game, step=step, max_depth=max_depth)
    elapsed = time.time() - start_time
    
    if solution is None:
        return False, 0, elapsed
    
    # 驗證：在原始遊戲上執行解法
    for i, action in enumerate(solution):
        ok = apply_action(game, action, step=step)
        if not ok:
            print(f"    第 {i+1} 步失敗: {action}")
            return False, len(solution), elapsed
    
    return game.is_solved(), len(solution), elapsed


def main():
    """主測試函數"""
    print("\n" + "=" * 60)
    print("  貓九的滑塊遊戲 — 求解器測試")
    print("=" * 60 + "\n")
    
    # ---- 測試 1: 基礎組件 ----
    test_basic_components()
    
    # ---- 測試 2: 小尺寸求解 ----
    print("=" * 60)
    print("測試 2: 4×4 求解（打亂 20 次）")
    print("=" * 60)
    
    test_cases = [
        # (m, n, step, shuffle_attempts, max_depth, label)
        (2, 2, 1, 10, 30, "2×2 step=1"),
        (2, 3, 1, 10, 50, "2×3 step=1"),
        (3, 3, 1, 15, 60, "3×3 step=1"),
        (4, 4, 2, 20, 100, "4×4 step=2"),
        # (5, 5, 2, 30, 200, "5×5 step=2"),  # 可能較慢
    ]
    
    for m, n, step, shuff_attempts, max_d, label in test_cases:
        print(f"\n  [{label}] 運行中...")
        ok, sol_len, elapsed = test_shuffle_solve_cycle(
            m, n, step, shuff_attempts, max_d
        )
        if ok:
            status = f"成功 ({sol_len} 步)"
        else:
            status = "失敗"
        print(f"  [{label}] {status} | 耗時: {elapsed:.2f}s")
    
    # ---- 測試 3: 批量基準 ----
    print("\n" + "=" * 60)
    print("測試 3: 4×4 基準測試（10 局，打亂 20 次）")
    print("=" * 60)
    
    results = []
    for i in range(10):
        game = SliderMatrix(4, 4)
        game.shuffle(attempts=20, step=2)
        if game.is_solved():
            continue
        
        t0 = time.time()
        solution = ida_star_solve(game, step=2, max_depth=80)
        t1 = time.time()
        
        if solution:
            # 驗證
            for action in solution:
                apply_action(game, action, step=2)
            verified = game.is_solved()
            results.append({
                'steps': len(solution),
                'time': t1 - t0,
                'verified': verified
            })
            print(f"  局 {i+1}: {len(solution)} 步, {t1-t0:.3f}s, 驗證={verified}")
        else:
            print(f"  局 {i+1}: 未找到解 (耗時 {t1-t0:.3f}s)")
    
    if results:
        avg_steps = sum(r['steps'] for r in results) / len(results)
        avg_time = sum(r['time'] for r in results) / len(results)
        success_rate = len(results) / 10 * 100
        print(f"\n  平均值: {avg_steps:.1f} 步, {avg_time:.3f}s")
        print(f"  成功率: {success_rate:.0f}% ({len(results)}/10)")
    
    print("\n" + "=" * 60)
    print("  測試完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
