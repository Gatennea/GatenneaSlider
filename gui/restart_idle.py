# -*- coding: utf-8 -*-
"""重启动画空闲预生成调度器（运行在游戏主进程，非阻塞）。

设计：游戏主循环每帧调用 tick()，但本调度器只在「游戏真正空闲 + 系统负载低」
两层门禁下，才无头拉起 tools/gen_restart_anim.py（独立 DETACHED 子进程，不阻塞
游戏），按当前/上次盘面尺寸生成一个全新的预生成动画，并原子提交覆盖
assets/picture/restart/active —— 下次重启的看门进程就会播这个「不重样」的新动画。

- 第一层门禁（调用方控制）：仅在游戏不在求解 / 无限打乱时调用 tick()；
- 第二层门禁（本模块）：系统整体 CPU 占用低于阈值（gui/system_load）；
- 限流：每个 (尺寸) 只触发一次生成，子进程跑完前不重复 spawn，避免每帧拉起；
  每次游戏进程都是新进程（看门进程重拉起），故每会话至少趁闲生成一版，保证
  「每次重启动画都不重样」。

系统负载探测（system_cpu_busy）内部会 sleep 采样，故本模块把它放在守护线程里
做，主循环永不因采样而卡顿；tick() 只读缓存值（首次无采样则保守放行）。
"""
import os
import subprocess
import sys
import threading
import time

from gui.system_load import system_cpu_busy

# 生成器脚本路径（项目根/tools）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GEN = os.path.join(_ROOT, 'tools', 'gen_restart_anim.py')

# 系统 CPU 占用阈值：超过则不趁闲生成（避免与用户操作抢资源）
CPU_BUSY_THRESHOLD = 0.45
# 系统负载采样节流：至少间隔这么久才重新采样一次（采样在后台线程，主循环不阻塞）
CPU_SAMPLE_INTERVAL = 3.0


class RestartAnimScheduler:
    def __init__(self, cpu_threshold=CPU_BUSY_THRESHOLD):
        self.cpu_threshold = cpu_threshold
        self._triggered_key = None   # 本会话已为哪个尺寸触发过生成
        self._proc = None            # 正在跑的生成子进程（None = 空闲）
        self._cpu_busy = 0.0         # 缓存的系统占用（保守放行默认 0.0）
        self._cpu_ts = -1e9          # 上次采样时刻
        self._cpu_thread = None      # 后台采样线程

    def _sample_cpu(self):
        """后台线程：采样系统 CPU 占用，写入缓存。"""
        try:
            self._cpu_busy = system_cpu_busy(sample_ms=400)
        except Exception:
            self._cpu_busy = 0.0
        self._cpu_ts = time.time()

    def tick(self, m, n, step, kind, triangle_side):
        """每帧调用；条件满足时趁闲生成一版新动画（非阻塞）。

        m, n, step, kind, triangle_side：当前/上次盘面参数，决定生成何种动画。
        """
        key = (int(m), int(n), int(step), str(kind),
               None if triangle_side is None else int(triangle_side))
        # 已为同尺寸触发过且子进程已结束 → 不再触发（避免反复生成）
        if self._triggered_key == key and self._proc is None:
            return
        # 子进程回收：跑完了就清空，未跑完则不要重复 spawn
        if self._proc is not None:
            if self._proc.poll() is not None:
                self._proc = None
            else:
                return
        # 第二层门禁：系统负载（节流采样，后台线程做，主循环不阻塞）
        now = time.time()
        if now - self._cpu_ts > CPU_SAMPLE_INTERVAL:
            if self._cpu_thread is None or not self._cpu_thread.is_alive():
                self._cpu_thread = threading.Thread(
                    target=self._sample_cpu, daemon=True)
                self._cpu_thread.start()
        if self._cpu_busy > self.cpu_threshold:
            return
        # 触发生成（独立 DETACHED 子进程，SDL 走 dummy 驱动彻底无窗口）
        self._spawn(key, m, n, step, kind, triangle_side)

    def _spawn(self, key, m, n, step, kind, triangle_side):
        try:
            cmd = [sys.executable, _GEN,
                   '--m', str(int(m)), '--n', str(int(n)),
                   '--step', str(int(step)), '--kind', str(kind)]
            if triangle_side is not None:
                cmd += ['--triangle-side', str(int(triangle_side))]
            # DETACHED_PROCESS：脱离游戏进程独立存活，生成完自行退出；无控制台故
            # stdout/stderr 重定向到 DEVNULL。SDL_VIDEODRIVER=dummy 让生成器在
            # 纯离屏模式下渲染并写 PNG，不闪任何窗口。
            env = dict(os.environ)
            env['SDL_VIDEODRIVER'] = 'dummy'
            self._proc = subprocess.Popen(
                cmd, cwd=_ROOT, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x00000008, env=env)
            self._triggered_key = key
        except Exception:
            self._proc = None
