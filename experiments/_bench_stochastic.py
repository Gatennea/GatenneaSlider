"""随机探索（② ε-greedy + ③ 随机踢）A/B 基准。

设计：
- 每个 (m,n,step) 配置用固定打乱种子生成「同一盘面」，两条臂都在该盘面上跑：
  * 确定性臂  stochastic=False（同盘同结果，便于回归）
  * 随机臂    stochastic=True，固定 STOCH_SEED（可复现）
- 唯一变量 = stochastic 开/关；optimize_path 两条臂都开（保持生产默认），避免混入其它效应。
- 捕获崩溃；max_wait_time 给每盘硬上限。

用法：
    python -u -X utf8 experiments/_bench_stochastic.py
"""
import sys, time, random
sys.path.insert(0, '.')
from game import SliderMatrix
from solver.state import snapshot, restore
from solver.ml.gather_solver import gather_solve

# (m, n, step, shuffle_attempts, max_wait_time)
CONFIGS = [
    (4, 4, 2, 80, 15),
    (4, 4, 3, 60, 15),
    (5, 5, 2, 150, 20),
    (6, 6, 2, 120, 25),
]
DISK_SEEDS = [1, 2, 3, 4, 5]      # 每个配置的 5 个固定盘面
STOCH_SEED = 12345                # 随机臂固定种子，保证可复现


def make_disk(m, n, step, attempts, dseed):
    random.seed(dseed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step)
    return snapshot(g)


def run(m, n, step, cap, stochastic, sseed, disk):
    g = SliderMatrix(m, n)
    restore(g, disk)
    t = time.time()
    try:
        r = gather_solve(g, step=step, max_steps=500, patience=150,
                        max_wait_time=cap, target_gather_score=1.0,
                        aggressiveness=0.2, optimize_path=True,
                        stochastic=stochastic, seed=sseed)
    except Exception as e:  # 崩溃捕获
        return {'crashed': True, 'err': repr(e)}, time.time() - t
    el = time.time() - t
    return r, el


def main():
    print(f"配置 {len(CONFIGS)} × 盘面 {len(DISK_SEEDS)} = {len(CONFIGS)*len(DISK_SEEDS)} 对 A/B\n")
    wins_det = wins_stoch = ties = crashes = 0
    step_diff_sum = 0.0
    score_diff_sum = 0.0
    n_solved_both = 0
    for (m, n, step, attempts, cap) in CONFIGS:
        print(f"=== {m}x{n} step{step} (shuffle={attempts}, cap={cap}s) ===")
        for dseed in DISK_SEEDS:
            disk = make_disk(m, n, step, attempts, dseed)
            rd, ed = run(m, n, step, cap, False, None, disk)
            rs, es = run(m, n, step, cap, True, STOCH_SEED, disk)
            if rd.get('crashed') or rs.get('crashed'):
                crashes += 1
                print(f"  disk{dseed}: CRASH det={rd.get('err')} stoch={rs.get('err')}")
                continue
            sd, ss = rd['solved'], rs['solved']
            nd, ns = len(rd['actions']), len(rs['actions'])
            scd, scs = rd['end']['score'], rs['end']['score']
            kd = rd['kicks']
            ks = rs['kicks']
            # 结果对比：以「是否还原」为首要，其次终聚拢度，再解法步数
            if ss and not sd:
                wins_stoch += 1
            elif sd and not ss:
                wins_det += 1
            else:
                ties += 1
            if sd and ss:
                n_solved_both += 1
                step_diff_sum += (ns - nd)
                score_diff_sum += (scs - scd)
            flag = 'STOCH+' if (ss and not sd) else ('DET+' if (sd and not ss) else '=')
            print(f"  disk{dseed}: det[solved={int(sd)} {nd}步 sc={scd:.3f} 踢{kd}] "
                  f"vs stoch[solved={int(ss)} {ns}步 sc={scs:.3f} 踢{ks} seed={rs['seed']}] "
                  f"-> {flag}  ({ed:.1f}s/{es:.1f}s)")
        print()
    print("=" * 60)
    print(f"确定性胜（随机臂没还原但确定性还原）: {wins_det}")
    print(f"随机臂胜（确定性没还原但随机还原）  : {wins_stoch}")
    print(f"平手（两臂同结果）                  : {ties}")
    print(f"崩溃                               : {crashes}")
    if n_solved_both:
        print(f"两臂都还原的 {n_solved_both} 盘：随机臂平均步数差 {step_diff_sum/n_solved_both:+.2f} "
              f"（正=随机更长），平均终聚拢度差 {score_diff_sum/n_solved_both:+.4f}")
    print("结论待子代理客观评估（见调用方说明）。")


if __name__ == '__main__':
    main()
