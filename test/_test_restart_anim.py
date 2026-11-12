# -*- coding: utf-8 -*-
"""重启动画管线护栏（脚本型回归测试，见 test/conftest.py）。

覆盖三件事：
1) 生成器确定性：同一 --seed 两次生成，逐帧字节一致 + meta 一致。动画「不重样」
   靠随机 seed，但同一 seed 必须可复现，否则回归/调试无从下手；且帧数 == meta
   声明的 frame_count（播放器按文件名全量加载，二者必须一致）。
2) 播放器加载：gui.restart_manager._load_anim 能读回帧、帧数/ fps 与 meta 吻合；
   目录缺失时回退返回 None（看门进程据此回退旧版 spinner）。
3) 空闲调度门禁：RestartAnimScheduler 按 (尺寸) 每会话只触发一次生成、子进程
   存活/已触发同尺寸不重复 spawn、系统负载超阈值不触发、换尺寸重新触发。
   _spawn 用桩替换（不真起子进程、不碰 active 目录）。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, 'tools', 'gen_restart_anim.py')
PY = sys.executable

FAILS = []


def _hash_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _run_gen(out_dir, seed):
    env = dict(os.environ)
    env.setdefault('SDL_VIDEODRIVER', 'dummy')
    subprocess.run([PY, GEN, '--m', '6', '--n', '6', '--step', '2',
                    '--kind', 'square', '--seed', str(seed), '--out', out_dir],
                   cwd=ROOT, env=env, check=True,
                   capture_output=True, text=True)


def check():
    # ---- 1) 生成器确定性 ----
    seed = 12345
    d1 = tempfile.mkdtemp(prefix='restart_gen1_')
    d2 = tempfile.mkdtemp(prefix='restart_gen2_')
    try:
        _run_gen(d1, seed)
        _run_gen(d2, seed)
        f1 = sorted(os.path.join(d1, f) for f in os.listdir(d1)
                    if f.endswith('.png'))
        f2 = sorted(os.path.join(d2, f) for f in os.listdir(d2)
                    if f.endswith('.png'))
        if len(f1) != len(f2):
            FAILS.append('determinism: frame counts differ %d vs %d'
                         % (len(f1), len(f2)))
        else:
            for a, b in zip(f1, f2):
                if _hash_file(a) != _hash_file(b):
                    FAILS.append('determinism: frame bytes differ %s'
                                 % os.path.basename(a))
                    break
        m1 = json.load(open(os.path.join(d1, 'meta.json')))
        m2 = json.load(open(os.path.join(d2, 'meta.json')))
        if m1.get('seed') != m2.get('seed'):
            FAILS.append('determinism: meta seed differs')
        if m1.get('frame_count') != len(f1):
            FAILS.append('frame_count mismatch: meta %s vs files %d'
                         % (m1.get('frame_count'), len(f1)))

        # ---- 2) 播放器加载（复用 d1，避免多跑一次生成） ----
        sys.path.insert(0, ROOT)
        from gui.restart_manager import _load_anim
        frames, fps, ox, oy = _load_anim(d1, 960, 540)
        if frames is None:
            FAILS.append('load: returned None for valid dir')
        else:
            if len(frames) != m1['frame_count']:
                FAILS.append('load: frame count %d != meta %d'
                             % (len(frames), m1['frame_count']))
            if fps != m1['fps']:
                FAILS.append('load: fps %s != meta %s' % (fps, m1['fps']))
        nf, nfps, nox, noy = _load_anim(os.path.join(d1, 'missing'), 960, 540)
        if nf is not None:
            FAILS.append('load: should return None for missing dir')
    finally:
        for d in (d1, d2):
            shutil.rmtree(d, ignore_errors=True)

    # ---- 3) 空闲调度门禁 ----
    sys.path.insert(0, ROOT)
    from gui import restart_idle

    class _FakeProc:
        def poll(self):
            return None  # 永生（模拟子进程在跑）

    sched = restart_idle.RestartAnimScheduler(cpu_threshold=0.45)
    spawned = []

    def fake_spawn(key, m, n, step, kind, ts):
        spawned.append((m, n, step, kind, ts))
        sched._proc = _FakeProc()   # 模拟子进程已拉起
        sched._triggered_key = key  # 真 _spawn 会记下已触发尺寸
    sched._spawn = fake_spawn

    # 第一层触发：CPU 初值 0.0（< 阈值）→ 放行；同尺寸子进程存活 → 不重复
    sched.tick(6, 6, 2, 'square', None)
    sched.tick(6, 6, 2, 'square', None)
    # 模拟子进程结束后再 tick 同尺寸 → 已触发过，不重复
    sched._proc = None
    sched._cpu_busy = 0.0
    sched._cpu_ts = time.time()    # 跳过采样线程，直接用设定值
    sched.tick(6, 6, 2, 'square', None)
    if len(spawned) != 1:
        FAILS.append('scheduler: expected 1 spawn for same size, got %d'
                     % len(spawned))

    # 换尺寸 → 重新触发
    sched.tick(4, 4, 2, 'square', None)
    if len(spawned) != 2:
        FAILS.append('scheduler: expected 2 spawns after size change, got %d'
                     % len(spawned))

    # CPU 超阈值 → 不触发（直接设定 _cpu_busy，并阻止采样线程覆盖）
    sched._proc = None
    sched._cpu_busy = 0.99
    sched._cpu_ts = time.time()
    before = len(spawned)
    sched.tick(5, 5, 2, 'square', None)
    if len(spawned) != before:
        FAILS.append('scheduler: should not spawn when CPU busy')

    # 阈值恢复 + 换尺寸 → 触发
    sched._cpu_busy = 0.0
    sched._cpu_ts = time.time()
    sched.tick(5, 5, 2, 'square', None)
    if len(spawned) != before + 1:
        FAILS.append('scheduler: expected spawn after CPU idle + size change')


if __name__ == '__main__':
    try:
        check()
    except Exception as e:
        print('EXC', repr(e))
        sys.exit(1)
    if FAILS:
        for f in FAILS:
            print('FAIL', f)
        sys.exit(1)
    print('ALL_OK restart_anim guardrails')
