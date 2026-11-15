# -*- coding: utf-8 -*-
"""护栏：「思考」演示选步在大尺寸盘面上必须有墙钟预算（待办 §四十三）。

背景（2026-11-16 无头实测，`experiments/script__probe_big_stall.py`）：
  · 旧实现抽样「3 块 × 6 缝」全不合法时**退回全量枚举**；12×12 step=2 上
    单次实测 13.7s —— 整个窗口无响应，就是用户报的「特大尺寸求解时短暂
    无响应」的直接原因；
  · 抽样路径本身在大尺寸上也要 38~70ms/步（每步掉帧）。

修复后判据（本测试锁死的契约）：
  1. 任何一次选步的墙钟耗时有上限（远小于一帧能容忍的卡顿）；
  2. 引擎调用（try_move）次数有上限——不允许出现「块×缝×方向」全量枚举；
  3. 预算不是靠「永远找不到步」实现：大尺寸上多数轮次仍要拿到走法。

跑法：`python test\\_test_think_select_budget.py`（脚本型测试，需 __main__ 守卫）。
"""
import os
import random
import sys
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def scramble(gui, moves):
    """用真实接口随机走若干步（便宜、且终态一定可逆可解）。"""
    game = gui.game
    done = 0
    for _ in range(moves * 3):
        if done >= moves:
            break
        gaps = list(gui._ann_all_valid_gaps())
        if not gaps:
            break
        gt, line = random.choice(gaps)
        blk = random.choice(game.blocks)
        dirs = list(gui._ann_dirs_for_gap(gt))
        random.shuffle(dirs)
        fin = None
        for d in dirs:
            for b in game.blocks:
                b.be_opted = False
            try:
                game.opt(gt, line, blk)
                fin = game.try_move(d, gui.current_step)
            except Exception:
                fin = None
            if fin:
                break
        if fin:
            game.commit_move(fin)
            done += 1
        for b in game.blocks:
            b.be_opted = False
    return done


def set_limit(d):
    """修复后允许的最慢单次选步（毫秒）。旧实现全量兜底在 12×12 上 13700ms。"""
    return 300.0 if d <= 12 else 500.0


def main():
    from GUI import SliderGUI

    m = n = 12
    step = 2
    gui = SliderGUI(m=m, n=n, step=step)
    gui._update_cursor = lambda: None
    print('棋盘 %dx%d step=%d 块数=%d' % (m, n, step, len(gui.game.blocks)))

    done = scramble(gui, 40)
    print('打乱走法 %d 步，is_solved=%s' % (done, gui.game.is_solved()))
    check('P0 打乱成功（非复原态）', done > 0 and not gui.game.is_solved())

    # 计引擎调用次数：这是「有没有偷偷全量枚举」的硬判据。
    # SliderMatrix 有 __slots__，实例上不能挂包装 → 包类方法（本进程内即还原）。
    import game as game_mod
    cls = game_mod.SliderMatrix
    calls = [0]
    orig_move = cls.try_move

    def counting_move(self, *a, **k):
        calls[0] += 1
        return orig_move(self, *a, **k)

    cls.try_move = counting_move

    rounds = 10
    # 预热：首次调用含「聚拢度打分」模块的懒加载（真实游戏里早已加载过），
    # 计时从稳态开始；否则第一名会被 import 成本顶到几百毫秒。
    gui._think_find_move()
    for b in gui.game.blocks:
        b.be_opted = False
    gui._think_last_move = None
    times, found, call_counts = [], 0, []
    for _ in range(rounds):
        calls[0] = 0
        t0 = time.perf_counter()
        spec = gui._think_find_move()
        times.append((time.perf_counter() - t0) * 1000.0)
        call_counts.append(calls[0])
        if spec is not None:
            found += 1
        for b in gui.game.blocks:
            b.be_opted = False
        gui._think_last_move = None

    cls.try_move = orig_move

    limit = set_limit(max(m, n))
    print('选步 %d 轮：均 %.1fms 最大 %.1fms；try_move 最多 %d 次；找到走法 %d/%d'
          % (rounds, sum(times) / rounds, max(times), max(call_counts),
             found, rounds))

    check('P1 单次选步不超墙钟上限', max(times) <= limit,
          '最大 %.1fms > %.0fms' % (max(times), limit))
    check('P2 引擎调用有上限（未全量枚举）', max(call_counts) <= 80,
          '最多 %d 次' % max(call_counts))
    check('P3 预算不是靠「永远找不到步」', found >= rounds - 2,
          '%d/%d' % (found, rounds))

    if FAILS:
        print('\n[FAILED] ' + '; '.join(FAILS))
        return 1
    print('\n[OK] 全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
