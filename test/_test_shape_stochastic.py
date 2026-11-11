# -*- coding: utf-8 -*-
r"""护栏：异形聚拢「随机重启」移植（待办 §三十四 第 6 条，2026-11-11）。

用户判据只有一条：**平均最终聚拢度提高**。对照实验
`archive/scratch_2026-11-11/bench_shape_stochastic.py` 实测：
  A 默认 / C 只踢 / D 完整 stochastic / E 加强随机重启
  → D 反而更差（band 内随机挑步破坏贪心骨架），C、E 提高。

移植时踩到两个坑，护栏专门盯住：
  ① 方形 `_do_kick`「失败即 break」，异形候选里大量动作当下不可执行，
     实测每脚只走 1 步 ⇒ 踢了白踢（A/B 里 C/E 与 A 逐位相同）。
     修法＝失败还原后重试，每脚真走满 k 步。
  ② 异形状态空间小，踢后立刻撞回 visited 被 stuck>5 掐断 ⇒ 需清
     visited + stuck 归零，才算一次真正的随机重启。

判据全部盯**行为**（spy 计数 / progress 帧 / 真盘重放），不靠源码子串：
撤掉任一修复，A2/A3/A7/B1 必转红。反向验证见
`archive/scratch_2026-11-11/reverse_shape_stochastic.py`。

执行：D:/python/python.exe -u test/_test_shape_stochastic.py
"""
import os
import random
import statistics
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game_mi import MiSliderMatrix                      # noqa: E402
from game_triangle import TriangleSliderMatrix          # noqa: E402
from solver import gather_solve_unified                 # noqa: E402
from solver.ml import mi_adapter as MA                  # noqa: E402
from solver.ml import tri_adapter as TA                 # noqa: E402
from solver.ml.shape_gather import ShapeGather          # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    print(('  PASS ' if cond else '  FAIL ') + name + '  ' + extra)
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------------------
# A 组：纯 Python 假盘（可控、确定性、快），盯「踢到底有没有真发生」
# ---------------------------------------------------------------------------
def _fake_sg(spy, fixed_hash=False, fail_actions=()):
    """分数恒 0.5（永不改进）⇒ patience 一到必然触发踢。

    `fail_actions` 指定哪些动作当下不可执行，复现异形「候选很多不可
    执行」的真实情况；用**动作本身**判定而不是调用序号，避免与主循环
    「选中后再应用」的调用次序耦合（那样会偶发 invalid_action）。
    """
    def coords_of(g):
        return frozenset((g['pos'],))

    def score(c, spec):
        return 0.5

    def enumerate_actions(g, step):
        spy['enum'] += 1
        return [('a', 0), ('b', 1), ('c', 2), ('d', 3)]

    def apply_action(g, a, step):
        spy['apply'] += 1
        if a[1] in fail_actions:
            return False
        g['pos'] += a[1] + 1
        spy['moves'].append(a[1])
        return True

    def snap(g):
        return {'pos': g['pos']}

    def restore(g, s):
        g['pos'] = s['pos']

    kw = {}
    if fixed_hash:
        kw['canonicalize'] = lambda c: 0      # 每轮都撞 visited，逼 stuck
    sg = ShapeGather(score, enumerate_actions, apply_action, snap, restore,
                     coords_of, is_solved=lambda g: False, **kw)
    return sg, {'pos': 0}, object()


def _spy():
    return {'enum': 0, 'apply': 0, 'moves': []}


def _run_fake(sg, game, spec, spy, kw):
    frames = []

    def cb(info):
        frames.append(info['n_actions'])

    res = sg.solve(game, spec, 1, max_steps=60, patience=3,
                   max_wait_time=0, target_score=1.0,
                   progress_callback=cb, **kw)
    return res, frames


def a_group():
    print('\n--- A 组：假盘 spy，盯随机踢真的启动且走满 k 步 ---')
    base = dict(kick_moves=5, max_kicks=5)
    # 默认：零随机、零踢
    spy = _spy()
    sg, g, spec = _fake_sg(spy)
    r0, f0 = _run_fake(sg, g, spec, spy, {})
    check('A1 默认零踢零随机源',
          r0['kicks'] == 0 and r0['seed'] is None
          and r0['stochastic'] is False,
          f"kicks={r0['kicks']} seed={r0['seed']} reason={r0['reason']}")
    n_enum_default = spy['enum']
    moves_default = list(spy['moves'])

    # A2：只开随机踢（关掉 band 内随机挑步）
    spy = _spy()
    sg, g, spec = _fake_sg(spy)
    rc, fc = _run_fake(sg, g, spec, spy,
                       dict(stochastic=True, seed=11, random_pick=False,
                            **base))
    check('A2 随机踢真的启动（spy 枚举次数 > 默认）',
          rc['kicks'] > 0 and spy['enum'] > n_enum_default + 5,
          f"kicks={rc['kicks']} enum={spy['enum']} vs {n_enum_default}")

    # A3：每脚走满 k 步 —— 抓「失败即 break」这个移植 bug。
    # 假盘里 2/4 动作不可执行；撤掉失败重试后每脚会被第一个失败动作掐断。
    spy = _spy()
    sg, g, spec = _fake_sg(spy, fail_actions={0, 2})
    rk, fk = _run_fake(sg, g, spec, spy,
                       dict(stochastic=True, seed=11, random_pick=False,
                            **base))
    jumps = [b - a for a, b in zip(fk, fk[1:]) if b - a > 1]
    check('A3 每脚真走满 kick_moves 步（失败重试有效）',
          sum(jumps) >= base['max_kicks'] * base['kick_moves'] - 2,
          f"踢造成的额外步数合计={sum(jumps)} 期望>="
          f"{base['max_kicks'] * base['kick_moves'] - 2}  跳变={jumps}")

    # A4：默认与「显式全关」逐位一致
    spy = _spy()
    sg, g, spec = _fake_sg(spy)
    r_off, f_off = _run_fake(
        sg, g, spec, spy,
        dict(stochastic=False, random_pick=False, kick=False,
             restart_on_kick=False, **base))
    check('A4 默认与显式全关逐位一致',
          (r_off['score'], r_off['steps'], r_off['reason'], f_off,
           list(spy['moves']))
          == (r0['score'], r0['steps'], r0['reason'], f0, moves_default))

    # A5：同 seed 可复现且不吃全局 random；换 seed 轨迹改变
    def trace_with(seed):
        sp = _spy()
        s, gg, ss = _fake_sg(sp)
        _, ff = _run_fake(s, gg, ss, sp,
                          dict(stochastic=True, seed=seed,
                               random_pick=False, **base))
        return ff, tuple(sp['moves'])
    t1 = trace_with(11)
    random.seed(999)                       # 扰动全局 random
    for _ in range(7):
        random.random()
    t1b = trace_with(11)
    t2 = trace_with(12)
    check('A5 同 seed 逐位可复现、不受全局 random 状态影响', t1 == t1b,
          f'frames {len(t1[0])}/{len(t1b[0])}')
    check('A5b 换 seed 随机轨迹确实改变', t1[1] != t2[1],
          f'moves {len(t1[1])}/{len(t2[1])}')

    # A6：② 与 ③ 确实可分离（用真实动作序列，不用帧数）
    spy = _spy()
    sg, g, spec = _fake_sg(spy)
    _run_fake(sg, g, spec, spy,
              dict(stochastic=True, seed=11, random_pick=False, kick=False,
                   **base))
    moves_none = list(spy['moves'])
    spy = _spy()
    sg, g, spec = _fake_sg(spy)
    _run_fake(sg, g, spec, spy,
              dict(stochastic=True, seed=11, kick=False, **base))
    moves_pick = list(spy['moves'])
    check('A6 只关踢＝默认动作序列；只开随机挑步会改变序列',
          moves_none == moves_default and moves_pick != moves_default,
          f'len {len(moves_none)}/{len(moves_pick)} vs {len(moves_default)}')

    # A7：restart_on_kick 真的重置 stuck（固定 hash 让每轮都撞 visited）
    def fixed_hash_frames(restart, seed=11):
        sp = _spy()
        s, gg, ss = _fake_sg(sp, fixed_hash=True)
        _, ff = _run_fake(s, gg, ss, sp,
                          dict(stochastic=True, seed=seed,
                               random_pick=False, restart_on_kick=restart,
                               **base))
        return ff
    f_no_restart = fixed_hash_frames(False)
    f_restart = fixed_hash_frames(True)
    check('A7 踢后重置 stuck/visited 让局部搜索能继续',
          len(f_restart) > len(f_no_restart) + 2,
          f'frames {len(f_no_restart)} → {len(f_restart)}')


# ---------------------------------------------------------------------------
# B 组：真盘（三角 / 米字），盯「平均最终聚拢度提高」与解法合法性
# ---------------------------------------------------------------------------
def _real_setup(form, size, step, shuf, seed):
    random.seed(seed)
    if form == 'tri':
        g = TriangleSliderMatrix(size[0])
        A, coords, Spec = TA, TA.tri_coords, TA.TriSpec
        spec = Spec(k=size[0], step=step)
    else:
        g = MiSliderMatrix(size[0], size[1])
        A, coords, Spec = MA, MA.mi_coords, MA.MiSpec
        spec = Spec(m=size[0], n=size[1], step=step)
    g.shuffle(shuf, step)
    sg = ShapeGather(A.shape_score, A.enumerate_actions, A.apply_action,
                     A.snap, A.restore, coords)
    return g, sg, spec, A, coords


def _real_run(form, size, step, shuf, seed, arm):
    g, sg, spec, A, coords = _real_setup(form, size, step, shuf, seed)
    snap0 = A.snap(g)
    kw = dict(max_steps=80, patience=10, max_wait_time=2.0)
    if arm == 'E':
        kw.update(stochastic=True, seed=31000 + seed, random_pick=False,
                  kick_moves=8, max_kicks=5, restart_on_kick=True)
    res = sg.solve(g, spec, step, **kw)
    A.restore(g, snap0)
    ok = True
    for a in res['actions']:
        if not A.apply_action(g, a, step):
            ok = False
            break
    legal = ok and abs(A.shape_score(coords(g), spec) - res['score']) < 1e-9
    return res, legal


def b_group():
    print('\n--- B 组：真盘平均最终聚拢度（用户唯一胜利判据）---')
    cases = [
        ('tri_k5', 'tri', (5,), 2, 200),
        ('mi_3x3', 'mi', (3, 3), 1, 60),
        ('mi_4x4', 'mi', (4, 4), 2, 80),
    ]
    sa, se, bad = [], [], []
    for name, form, size, step, shuf in cases:
        for seed in (7000, 7001):
            ra, la = _real_run(form, size, step, shuf, seed, 'A')
            re_, le = _real_run(form, size, step, shuf, seed, 'E')
            sa.append(ra['score'])
            se.append(re_['score'])
            if not (la and le):
                bad.append((name, seed, la, le))
            print(f'     {name:8s} seed={seed}  A {ra["score"]:.4f} '
                  f'E {re_["score"]:.4f}  踢{re_["kicks"]}')
    ma, me = statistics.mean(sa), statistics.mean(se)
    check('B1 平均最终聚拢度提高（E > A）', me > ma + 1e-9,
          f'A {ma:.4f} → E {me:.4f}  差 {me - ma:+.4f}')
    check('B2 两臂解法都能从起点重放到返回末态', not bad,
          f'非法 {len(bad)} 例 {bad[:3]}')

    # B3：三个入口都要真的把随机参数透传到 ShapeGather.solve
    seen = []
    fake_res = dict(type='gather', actions=[], solved=False, reason='x',
                    score=0.5, best_score=0.5, best_step=0, steps=0,
                    trace=[], elapsed=0.0, stochastic=True, seed=7, kicks=0)

    def spy_solve(self, game, spec, step, **kw):
        seen.append(kw)
        return dict(fake_res)

    with mock.patch.object(ShapeGather, 'solve', spy_solve):
        random.seed(5)
        gt = TriangleSliderMatrix(4)
        gt.shuffle(10, 2)
        TA.tri_gather_solve(gt, step=2, stochastic=True, seed=7)
        random.seed(5)
        gm = MiSliderMatrix(3, 3)
        gm.shuffle(10, 1)
        MA.mi_gather_solve(gm, step=1, stochastic=True, seed=7)
        gather_solve_unified(gm, step=1, stochastic=True, seed=7)
    got = [kw.get('stochastic') is True and kw.get('seed') == 7
           for kw in seen]
    check('B3 三角 / 米字 / 统一入口都透传 stochastic+seed',
          len(seen) == 3 and all(got),
          f'收到 {len(seen)} 次  {[ (k.get("stochastic"), k.get("seed")) for k in seen ]}')

    # B4：异形统一入口缺省＝只开随机踢，且 seed 稳定、可显式关掉
    seen.clear()
    with mock.patch.object(ShapeGather, 'solve', spy_solve):
        random.seed(5)
        gt = TriangleSliderMatrix(4)
        gt.shuffle(10, 2)
        TA.tri_gather_solve(gt, step=2)                 # 默认
        TA.tri_gather_solve(gt, step=2)                 # 同盘再来一次
        TA.tri_gather_solve(gt, step=2, stochastic=False)   # 显式关
        random.seed(5)
        gm = MiSliderMatrix(3, 3)
        gm.shuffle(10, 1)
        MA.mi_gather_solve(gm, step=1)                  # 米字默认
    d1, d2, off, dm = seen
    check('B4 缺省只开踢且关掉随机挑步（三角 + 米字）',
          all(k.get('kick') is True and k.get('random_pick') is False
              and k.get('stochastic') is False
              for k in (d1, d2, dm)),
          f'{[ (k.get("kick"), k.get("random_pick")) for k in (d1, d2, dm) ]}')
    check('B4b 同盘 seed 稳定（跨两次调用一致）',
          d1.get('seed') == d2.get('seed') and isinstance(d1.get('seed'), int),
          f"{d1.get('seed')} / {d2.get('seed')}")
    check('B4c 显式 stochastic=False 完全关掉（移植前逐位一致）',
          off.get('kick') is False and off.get('random_pick') is False
          and off.get('seed') is None,
          f"{[ (k, off.get(k)) for k in ('kick', 'random_pick', 'seed') ]}")

    # B5：走**统一入口**时缺省臂的平均最终聚拢度确实高于显式关闭臂
    cases = [
        ('tri_k5', 'tri', (5,), 2, 200),
        ('mi_3x3', 'mi', (3, 3), 1, 60),
        ('mi_4x4', 'mi', (4, 4), 2, 80),
    ]
    s_on, s_off, bad2 = [], [], []
    for name, form, size, step, shuf in cases:
        for seed in (7000, 7001):
            vo, lo = _unified_run(form, size, step, shuf, seed, False)
            vn, ln = _unified_run(form, size, step, shuf, seed, None)
            s_off.append(vo)
            s_on.append(vn)
            if not (lo and ln):
                bad2.append((name, seed, lo, ln))
    mo, mn = statistics.mean(s_off), statistics.mean(s_on)
    check('B5 统一入口缺省即受益（平均聚拢度 > 显式关闭）', mn > mo + 1e-9,
          f'关 {mo:.4f} → 缺省 {mn:.4f}  差 {mn - mo:+.4f}')
    check('B5b 统一入口两臂解法都合法', not bad2,
          f'非法 {len(bad2)} 例 {bad2[:3]}')


def _unified_run(form, size, step, shuf, seed, stochastic):
    random.seed(seed)
    if form == 'tri':
        g = TriangleSliderMatrix(size[0])
        A, coords = TA, TA.tri_coords
    else:
        g = MiSliderMatrix(size[0], size[1])
        A, coords = MA, MA.mi_coords
    g.shuffle(shuf, step)
    snap0 = A.snap(g)
    res = gather_solve_unified(g, step=step, max_steps=80, patience=10,
                               max_wait_time=2.0, stochastic=stochastic)
    A.restore(g, snap0)
    ok = True
    for a in res['actions']:
        if not A.apply_action(g, a, step):
            ok = False
            break
    legal = ok and abs(A.shape_score(coords(g), _spec_of(form, size, step, A))
                       - res['score']) < 1e-9
    return res['score'], legal


def _spec_of(form, size, step, A):
    if form == 'tri':
        return A.TriSpec(k=size[0], step=step)
    return A.MiSpec(m=size[0], n=size[1], step=step)


def main():
    a_group()
    b_group()
    print('\nFAILS=%d %r' % (len(FAILS), FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
