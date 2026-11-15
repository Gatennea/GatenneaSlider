# -*- coding: utf-8 -*-
"""特大尺寸（>10×10、step=2）自动求解期「短暂无响应」的测帧定位（待办 §四十三 第 1 步）。

只读探针：不改任何产品代码，只把真实主循环（``GUI.run``）套一个假时钟，
逐帧记录**帧间隔**，再把间隔按「思考演示 / 段播放 / 后台搜索等待 / 空闲」分段，
回答「停顿到底落在哪一段」。另单独给 ``_think_find_move``（含抽样全不合法时
退回全量枚举的最坏分支）计时，验证「段间等待最可疑」的推断。

跑法（必须用带 pygame 的解释器）：

    D:/python/python.exe -u experiments/script__probe_big_stall.py --m 12 --n 12 --step 2 --seconds 40
    ... --think 0            # 关掉思考演示做对照
    ... --frames-only 800    # 只跑帧数上限（默认同时受秒数限制）

输出：每类分段的最大帧间隔、>50/100/200ms 计数、最慢 12 帧明细（含帧号与阶段）。
"""

import argparse
import os
import random
import statistics
import sys
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import pygame  # noqa: E402


# --------------------------------------------------------------------------- #
# 运行态隔离：与 test/conftest.py 同款思路（原子挪走，不用 os.remove）
# --------------------------------------------------------------------------- #
def isolate_runtime():
    cfg = os.path.join(_ROOT, 'config')
    bak = os.path.join(cfg, '.probe_bak')
    os.makedirs(bak, exist_ok=True)
    for name in ('engine.json', 'temp_history.json'):
        src = os.path.join(cfg, name)
        if os.path.exists(src):
            os.replace(src, os.path.join(bak, name + '.bak'))


# --------------------------------------------------------------------------- #
# 打乱：用真实接口 opt + try_move + commit_move 随机走若干步（比 shuffle 便宜）
# --------------------------------------------------------------------------- #
def scramble(gui, moves):
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


# --------------------------------------------------------------------------- #
# 单测：思考演示选步（抽样 + 最坏「抽样全不合法 → 全量枚举」）
# --------------------------------------------------------------------------- #
def time_think_find_move(gui, rounds=5):
    out = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        spec = gui._think_find_move()
        dt = (time.perf_counter() - t0) * 1000.0
        out.append((dt, spec is not None))
        for b in gui.game.blocks:
            b.be_opted = False
    return out


def time_think_worst(gui, rounds=20):
    """连续选步：验证墙钟预算（旧「全量枚举兜底」分支应当已不存在）。"""
    out = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        spec = gui._think_find_move()
        dt = (time.perf_counter() - t0) * 1000.0
        out.append((dt, spec is not None))
        for b in gui.game.blocks:
            b.be_opted = False
    return out


# --------------------------------------------------------------------------- #
# 假时钟：套在真实主循环上，逐帧计时 + 到点启停求解
# --------------------------------------------------------------------------- #
def phase_label(gui):
    parts = []
    parts.append('solve' if getattr(gui, '_auto_solve_running', False)
                 else 'idle')
    if getattr(gui, 'macro_executing', False):
        parts.append('macro')
    if getattr(gui, 'animating', False):
        parts.append('anim')
    walk = getattr(gui, '_think_walk', None)
    if walk is not None and getattr(walk, 'is_active', False):
        parts.append('think')
    return '/'.join(parts)


def coarse(label):
    if 'think' in label:
        return 'thinking'
    if 'macro' in label or 'anim' in label:
        return 'playing'
    if label.startswith('solve'):
        return 'search-wait'
    return 'idle/finalize'


class ProbeClock:
    def __init__(self, gui, seconds, max_frames, start_after, think_on):
        self.gui = gui
        self.seconds = seconds
        self.max_frames = max_frames
        self.start_after = start_after
        self.t0 = time.perf_counter()
        self.last = self.t0
        self.frames = 0
        self.samples = []            # (frame, t_s, gap_ms, label)
        self.start_frame = None
        self.cancel_frame = None
        self.stop_frame = None
        self._think_on = think_on

    def tick(self, fps=0):
        now = time.perf_counter()
        gap = now - self.last
        self.last = now
        if fps:
            target = 1.0 / fps
            if gap < target:
                time.sleep(target - gap)
                gap = target
        self.frames += 1
        t = now - self.t0

        if self.start_frame is None and self.frames >= self.start_after:
            self.start_frame = self.frames
            try:
                self.gui.thinking_enabled = self._think_on
                self.gui.solver_algorithm = 'hybrid'
                self.gui._start_auto_solve()
            except Exception:
                import traceback
                traceback.print_exc()

        if self.cancel_frame is None and t >= self.seconds:
            self.cancel_frame = self.frames
            try:
                if getattr(self.gui, '_auto_solve_running', False):
                    self.gui._auto_solve_cancel = True
            except Exception:
                pass
        if self.cancel_frame is not None and self.stop_frame is None \
                and self.frames - self.cancel_frame >= 180:
            self.stop_frame = self.frames
            self.gui.running = False

        self.samples.append((self.frames, t, gap * 1000.0, phase_label(self.gui)))
        return gap * 1000.0


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def summarize(clock, tail=12):
    rows = [r for r in clock.samples if r[0] >= clock.start_frame] \
        if clock.start_frame else list(clock.samples)
    if not rows:
        print('[probe] 无采样')
        return {}
    gaps_all = [r[2] for r in rows]
    print('\n=== 帧间隔汇总（求解启动后，共 %d 帧，墙钟 %.1fs）==='
          % (len(rows), rows[-1][1] - rows[0][1]))
    print('  平均 %.2fms  中位 %.2fms  最大 %.1fms'
          % (statistics.mean(gaps_all), statistics.median(gaps_all),
             max(gaps_all)))
    for th in (50, 100, 200, 500):
        n = sum(1 for g in gaps_all if g >= th)
        print('  >=%3dms: %d 帧' % (th, n))

    by = {}
    for r in rows:
        k = coarse(r[3])
        by.setdefault(k, []).append(r[2])
    print('\n=== 分段（按粗分类）===')
    for k, vals in sorted(by.items(), key=lambda kv: -max(kv[1])):
        print('  %-14s 帧 %5d  最大 %8.1fms  均值 %6.2fms'
              % (k, len(vals), max(vals), statistics.mean(vals)))

    print('\n=== 最慢 %d 帧 ===' % tail)
    for r in sorted(rows, key=lambda x: -x[2])[:tail]:
        print('  帧%5d  t=%6.2fs  %8.1fms  %s' % r)
    return {'max_ms': max(gaps_all), 'frames': len(rows), 'by': by}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--m', type=int, default=12)
    ap.add_argument('--n', type=int, default=12)
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--moves', type=int, default=60, help='打乱走法数')
    ap.add_argument('--seconds', type=float, default=40.0)
    ap.add_argument('--max-frames', type=int, default=4000)
    ap.add_argument('--start-after', type=int, default=20)
    ap.add_argument('--think', type=int, default=1, help='1=开思考演示，0=关')
    ap.add_argument('--breakdown', type=int, default=0,
                    help='1=加帧内分段计时（会略增开销，只看占比）')
    args = ap.parse_args()

    isolate_runtime()
    from GUI import SliderGUI

    gui = SliderGUI(m=args.m, n=args.n, step=args.step)
    # 跳过开机标题阶段，让主循环从头就是「已就绪」
    gui._restart_token = 'probe'
    # dummy 视频驱动建不了系统光标：真实主循环会每帧抛
    # 「Error while creating system cursor」，120 帧后自我终止。测帧与光标无关，置空。
    gui._update_cursor = lambda: None
    print('棋盘 %dx%d step=%d，初态 is_solved=%s，块数 %d'
          % (args.m, args.n, args.step, gui.game.is_solved(),
             len(gui.game.blocks)))

    n_done = scramble(gui, args.moves)
    print('打乱走法 %d 步（请求 %d），is_solved=%s'
          % (n_done, args.moves, gui.game.is_solved()))

    think = time_think_find_move(gui, rounds=5)
    print('\n=== 思考选步（抽样路径）===')
    for i, (ms, ok) in enumerate(think):
        print('  #%d %7.1fms  spec=%s' % (i + 1, ms, ok))
    if think:
        print('  均值 %.1fms  最大 %.1fms'
              % (statistics.mean([t[0] for t in think]),
                 max(t[0] for t in think)))

    print('\n=== 思考选步（连续 20 次，验证预算上限）===')
    worst = time_think_worst(gui, rounds=20)
    print('  均值 %.1fms  最大 %.1fms  空手 %d/%d'
          % (statistics.mean([t[0] for t in worst]),
             max(t[0] for t in worst),
             sum(1 for _, ok in worst if not ok), len(worst)))

    # 分项计时：游走/撤回/滑动各占多少（嵌套调用会重复计入，看总量分配即可）
    stats = {}

    def wrap(name, fn):
        def inner(*a, **k):
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                d = (time.perf_counter() - t0) * 1000.0
                s = stats.setdefault(name, [0, 0.0, 0.0])
                s[0] += 1
                s[1] += d
                s[2] = max(s[2], d)
        return inner

    gui._think_find_move = wrap('find_move', gui._think_find_move)
    gui._think_do_walk = wrap('do_walk', gui._think_do_walk)
    gui._think_do_rewind = wrap('do_rewind', gui._think_do_rewind)
    if hasattr(gui, '_think_start_slide'):
        gui._think_start_slide = wrap('start_slide', gui._think_start_slide)

    clock = ProbeClock(gui, args.seconds, args.max_frames,
                       args.start_after, bool(args.think))
    if args.breakdown:
        for name in ('handle_events', '_ann_poll', '_auto_update_poll',
                     'process_commands', 'update_animation',
                     '_update_shuffle_demo', '_check_auto_solve_result',
                     '_pump_stream_segments', '_pump_auto_stages',
                     'draw_board', 'draw_right_panel', 'draw_status_bar',
                     'draw_annotation_mode', '_med_draw_overlay',
                     'is_solved', '_status_step_text', '_timer_status_text',
                     'engine_label', '_current_puzzle_key'):
            fn = getattr(gui, name, None)
            if fn is not None:
                setattr(gui, name, wrap(name, fn))
        pygame.display.flip = wrap('flip', pygame.display.flip)
    orig_clock = pygame.time.Clock
    pygame.time.Clock = lambda: clock
    try:
        gui.run()
    except SystemExit:
        pass
    finally:
        pygame.time.Clock = orig_clock
    try:
        gui.game_history = None
        pygame.quit()
    except Exception:
        pass

    print('\n求解启动于第 %s 帧，取消于第 %s 帧，收尾退出于第 %s 帧'
          % (clock.start_frame, clock.cancel_frame, clock.stop_frame))
    summarize(clock)
    print('\n=== 分项耗时（演示期间的调用总量）===')
    for name, (n, total, worst) in sorted(stats.items(),
                                         key=lambda kv: -kv[1][1]):
        print('  %-11s 调用 %5d 总 %8.1fms 均 %6.1fms 最大 %6.1fms'
              % (name, n, total, total / n, worst))
    return 0


if __name__ == '__main__':
    sys.exit(main())
