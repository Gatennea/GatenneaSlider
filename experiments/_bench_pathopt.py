"""路径优化 A/B 真基准（阶段3后续）。

正确设计（此前版本有 bug，已修）：
- 每个 (m,n,step,trials) 配置用固定打乱种子生成「同一盘面」，两条臂都在该盘面上跑：
  * off 臂  optimize_path=False（原始路径长）
  * on  臂  optimize_path=True（优化后路径长）
- 唯一变量 = optimize_path 开/关；两条臂用同一 run 种子对齐全局 random 状态，
  保证搜索轨迹完全一致（贪心主循环本就确定性），对比出的步数差纯粹是路径优化贡献。

此前 bug：run_once 每次 `SliderMatrix(...); g.shuffle(...)` 重新生成盘面，
off/on 拿到两个不同谜题，导致「搜索不一致」虚高、步数对比无意义。

用法：
    python -u -X utf8 experiments/_bench_pathopt.py
"""
import sys, random, time
sys.path.insert(0, '.')

from game import SliderMatrix
from solver.state import snapshot, restore
from solver.ml.gather_solver import gather_solve

# (m, n, step, trials)
CONFIGS = [
    (4, 4, 2, 80),
    (4, 4, 3, 60),
    (5, 5, 2, 50),
    (6, 6, 2, 20),
]
SHUFFLE_ATTEMPTS = 40
RUN_SEED = 777          # 两条臂共用，对齐全局 random 状态 => 搜索一致


def make_disk(m, n, step, dseed):
    """生成一份固定盘面快照（deterministic by dseed）。"""
    random.seed(dseed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=SHUFFLE_ATTEMPTS, step=step)
    return snapshot(g)


def run_once(m, n, step, optimize, disk, run_seed):
    """在同一盘面上跑一次 gather_solve。run_seed 对齐全局 random 状态。"""
    g = SliderMatrix(m, n)
    restore(g, disk)
    random.seed(run_seed)
    r = gather_solve(g, step=step, max_steps=500, patience=300,
                     max_wait_time=12.0, target_gather_score=1.0,
                     aggressiveness=0.2, optimize_path=optimize)
    return r


def determinism_check(m, n, step):
    """核心确定性自检：同盘同 run 种子，off 臂两次跑应得完全相同动作序列。"""
    disk = make_disk(m, n, step, 1)
    r1 = run_once(m, n, step, False, disk, RUN_SEED)
    r2 = run_once(m, n, step, False, disk, RUN_SEED)
    same = (r1['actions'] == r2['actions'])
    print(f"  [确定性自检 {m}x{n} step{step}] off 两跑动作序列一致: {same}"
          f"（步数 {len(r1['actions'])} vs {len(r2['actions'])}）")


def main():
    print("路径优化 A/B 基准（同盘同种子，只差 optimize_path 开/关）\n")
    determinism_check(4, 4, 2)
    determinism_check(5, 5, 2)
    print()
    for (m, n, step, trials) in CONFIGS:
        solvedA = solvedB = 0
        lenA_solved = []   # optimize off（原始路径长）
        lenB_solved = []   # optimize on（优化后路径长）
        removed_list = []  # lenA - lenB（仅 solved）
        mismatch = 0       # 同盘两臂还原判定不一致（应恒为0，验证确定性）
        t0 = time.time()
        for s in range(trials):
            disk = make_disk(m, n, step, s)
            rA = run_once(m, n, step, False, disk, RUN_SEED)
            rB = run_once(m, n, step, True, disk, RUN_SEED)
            if rA['solved']:
                solvedA += 1
                lenA_solved.append(len(rA['actions']))
            if rB['solved']:
                solvedB += 1
                lenB_solved.append(len(rB['actions']))
            if rA['solved'] and rB['solved']:
                removed_list.append(len(rA['actions']) - len(rB['actions']))
            if rA['solved'] != rB['solved']:
                mismatch += 1
        el = time.time() - t0

        rateA = solvedA / trials * 100
        rateB = solvedB / trials * 100
        avgA = sum(lenA_solved) / len(lenA_solved) if lenA_solved else 0
        avgB = sum(lenB_solved) / len(lenB_solved) if lenB_solved else 0
        avg_rem = sum(removed_list) / len(removed_list) if removed_list else 0
        max_rem = max(removed_list) if removed_list else 0
        rem_ratio = (sum(removed_list) / sum(lenA_solved) * 100) if lenA_solved else 0

        print(f"{m}x{n} step{step}  trials={trials}  ({el:.1f}s)")
        print(f"  还原率  off={rateA:.0f}%  on={rateB:.0f}%  "
              f"搜索不一致={mismatch}（应=0）")
        print(f"  解法均长(已还原)  off={avgA:.2f}步  on={avgB:.2f}步")
        print(f"  废步删除  均={avg_rem:.2f}步  最多={max_rem}步  "
              f"占原始长度={rem_ratio:.1f}%")
        print()


if __name__ == '__main__':
    main()
