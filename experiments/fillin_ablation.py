# -*- coding: utf-8 -*-
r"""混合流水线填洞宏去留消融（fill-in-hybrid ablation，2026-10-16）。

设计文档：docs/solver/实验设计_混合流水线填洞去留.md

背景：用户主张删掉 hybrid_solve 内的填洞宏（fill_macro.solve_fill_macro）。
exp20(2026-09-30) 已在 hybrid 单层测过同配置消融（skip_fill：7.5s→12.7s，
慢 69%），但代码旧、语料窄、且只测了单层。本次补测三层：
    L1  hybrid_solve 直跑（单层刷新）
    L2a hybrid_solve_with_table（GUI「混合求解」入口，外面无独立补缺宏）
    L2b auto_solve（GUI「自动规划」入口，外面有独立补缺宏候选——决胜层）

口径（用户铁律：运算时间 > 解的长度）：
  - 端到端墙钟时间为主指标；逐局配对（同 seed 同局面 on/off）；
  - ABAB：第 i 对先 on 后 off（i 偶）/ 先 off 后 on（i 奇），抵消热态漂移；
  - 汇总报跨 rep 中位（fillin_report.py），不只均值（时间分布长尾）。

⚠️ 多轮 reps 是必需的（2026-10-16 实测发现）：L2b 路径上的补缺宏候选有
    30s 墙钟预算（gap_solver._GAP_GUI_TIME_BUDGET）+ 并行 couple 枚举，
    同盘面同代码可能 2.2s 解出、也可能 30s 到点掉混合续算——线程调度
    非确定性。单轮数据里这个运气会冒充填洞宏效应（实测同层同解长的一对
    耗时差 20 倍、且出现反向）。故每对跑 --reps N 轮（rep 间镜像 ABAB），
    跨 rep 取中位。L1 层无补缺宏参与，单轮即可信。

用法（可反复重启，断点续跑；每次调用在墙钟上限内干净退出）：
  D:\python\python.exe experiments/fillin_ablation.py \
      --level L1 --m 5 --n 5 --step 2 --games 4 [--wall-cap 540] \
      [--reps 3]

输出：experiments/results/fillin/<level>_<m>x<n>_s<step>.jsonl（逐局追加，
     已完成的 (level,size,seed,flag,rep) 自动跳过；旧数据无 rep 字段按
     rep=0 计；换 --games 12 即在同一 seed 序列上扩展为正式档，冒烟数据
     是正式档的子集，不浪费）。
"""
import argparse
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from experiments import harness as H  # noqa: E402

# 每局求解器预算（秒）：L1/L2a 单层 120s；L2b 两候选都可能跑，300s
_BUDGET = {'L1': 120.0, 'L2a': 120.0, 'L2b': 300.0}


def _run_one(level, snap, flag, budget):
    """跑一局，返回记录 dict。flag: 'on'（现状含填洞）/ 'off'（提案配置）。"""
    from solver.auto_solver import auto_solve
    from solver.hybrid_solver import hybrid_solve
    from solver import hybrid_solve_with_table
    from solver.ml.fill_macro import window_of

    m, n, step = snap['m'], snap['n'], snap['step']
    use_fill = (flag == 'on')
    g = H.load_game(snap)
    coords0 = frozenset((b.location[0], b.location[1]) for b in g.blocks)
    try:
        holes = len(window_of(coords0, m, n, step)[2])
    except Exception:
        holes = -1

    labels = []
    t0 = time.perf_counter()

    def cc():
        return time.perf_counter() - t0 >= budget

    err = None
    r = None
    try:
        if level == 'L1':
            r = hybrid_solve(g, step, use_fill=use_fill, cancel_check=cc)
        elif level == 'L2a':
            r = hybrid_solve_with_table(g, step, use_fill=use_fill,
                                        cancel_check=cc)
        else:  # L2b
            def cb(s):
                labels.append('%s%s' % (s['label'], '*' if s.get('solved') else ''))
            r = auto_solve(g, step, hybrid_use_fill=use_fill, stage_cb=cb,
                           time_budget=budget, cancel_check=cc)
    except Exception as e:
        err = '%s: %s' % (type(e).__name__, e)
    dt = time.perf_counter() - t0

    rec = {'dt': round(dt, 3), 'holes': holes, 'err': err,
           'outcome': None, 'n_actions': 0, 'score': None, 'phi': None,
           'labels': labels if level == 'L2b' else None}
    if err is None:
        if isinstance(r, tuple):
            rec['outcome'] = 'solved'
            rec['n_actions'] = len(r[0])
        elif isinstance(r, dict):
            rec['outcome'] = str(r.get('type', 'dict'))
            rec['n_actions'] = len(r.get('actions') or [])
            rec['score'] = r.get('score')
            rec['phi'] = r.get('phi')
        elif r is False:
            # 墙钟打满 = 超时；提前返回 False = 取消/守卫耗尽（本实验无外部取消）
            rec['outcome'] = 'timeout' if dt >= budget - 1.0 else 'fail'
        elif r is None:
            rec['outcome'] = 'none'
        else:
            rec['outcome'] = 'other:%s' % type(r).__name__
    return rec


def _load_done(path):
    """断点续跑：已写入 jsonl 的 (level,size,seed,flag,rep) 不重跑。

    旧数据无 rep 字段，按 rep=0 计（天然兼容）。
    """
    done = set()
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                done.add((d['level'], d['m'], d['n'], d['step'],
                          d['seed'], d['flag'], d.get('rep', 0)))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--level', required=True, choices=['L1', 'L2a', 'L2b'])
    ap.add_argument('--m', type=int, required=True)
    ap.add_argument('--n', type=int, required=True)
    ap.add_argument('--step', type=int, required=True)
    ap.add_argument('--games', type=int, default=4)
    ap.add_argument('--reps', type=int, default=1,
                    help='每对重复轮数（补缺宏墙钟预算有非确定性，多轮取中位分离变量）')
    ap.add_argument('--seed0', type=int, default=2000)
    ap.add_argument('--wall-cap', type=float, default=540.0,
                    help='单次调用墙钟上限（秒），到点干净退出可续跑')
    ap.add_argument('--budget', type=float, default=None,
                    help='覆盖单局求解器预算（秒）')
    args = ap.parse_args()

    budget = args.budget or _BUDGET[args.level]
    out_dir = os.path.join(_ROOT, 'experiments', 'results', 'fillin')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, '%s_%dx%d_s%d.jsonl'
                        % (args.level, args.m, args.n, args.step))
    done = _load_done(path)

    # ABAB 配对计划：rep 内第 i 对 i 偶 → (on, off)、i 奇 → (off, on)；
    # rep 间镜像（奇数 rep 反转每对起手），进一步抵消顺序效应。
    plan = []
    for rep in range(args.reps):
        for i in range(args.games):
            seed = args.seed0 + i
            order = ('on', 'off') if i % 2 == 0 else ('off', 'on')
            if rep % 2 == 1:
                order = order[::-1]
            for pos, flag in enumerate(order):
                plan.append((seed, flag, pos, rep))

    t_start = time.perf_counter()
    ran = skipped = 0
    total = len(plan)
    with open(path, 'a', encoding='utf-8') as out:
        for seed, flag, pos, rep in plan:
            key = (args.level, args.m, args.n, args.step, seed, flag, rep)
            if key in done:
                skipped += 1
                continue
            if ran > 0 and time.perf_counter() - t_start >= args.wall_cap:
                print('[cap] 墙钟上限 %.0fs 到，剩 %d 项下次续跑'
                      % (args.wall_cap, total - ran - skipped), flush=True)
                break
            snap = H.gen_state(args.m, args.n, args.step, seed)
            rec = _run_one(args.level, snap, flag, budget)
            rec.update({'level': args.level, 'm': args.m, 'n': args.n,
                        'step': args.step, 'seed': seed, 'flag': flag,
                        'pos': pos, 'rep': rep, 'budget': budget,
                        'ts': time.strftime('%Y-%m-%d %H:%M:%S')})
            out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            out.flush()
            ran += 1
            extra = (' ' + ' '.join(rec['labels'])) if rec.get('labels') else ''
            print('[%s %dx%d s%d] seed=%d %-3s r%d %-8s %7.1fs act=%-3d h=%d%s'
                  % (args.level, args.m, args.n, args.step, seed, flag, rep,
                     rec['outcome'], rec['dt'], rec['n_actions'],
                     rec['holes'], extra), flush=True)
    print('[done] 本次 %d 项 / 共 %d 项（跳过已完成 %d）→ %s'
          % (ran, total, skipped, path), flush=True)


if __name__ == '__main__':
    main()
