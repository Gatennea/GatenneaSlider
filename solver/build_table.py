# -*- coding: utf-8 -*-
"""
反向 BFS 建表主程序 + tkinter 简易 GUI

功能：
    - 从目标状态出发，反向 BFS 遍历所有可解状态，生成"状态→求解距离"表
    - 支持暂停/恢复（断点续算）、定时自动保存（防崩溃丢数据）
    - 简易 tkinter GUI 实时查看进度与已有数据
    - 与游戏主程序完全隔离，不导入 pygame

运行：
    D:\\python\\python.exe -m solver.build_table [m n step] [--no-gui]
    默认 m=4 n=4 step=2
"""

import os
import sys
import time
import json
import pickle
import threading
import multiprocessing
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

try:
    from solver import table_core as tc
    #在根目录使用python -m solver.build_table时
except ImportError:
    import table_core as tc#在solver目录下python build_table.py时

# 提示音（可选依赖）
try:
    import numpy as np
    import sounddevice as sd
    _HAS_SOUND = True
except ImportError:
    _HAS_SOUND = False


def _beep(freq=800, duration=0.15, samplerate=44100):
    """播放一个短促的纯音提示。"""
    if not _HAS_SOUND:
        return
    t = np.linspace(0, duration, int(samplerate * duration), endpoint=False)
    envelope = np.exp(-t * 12)  # 快速衰减，不刺耳
    wave = (np.sin(2 * np.pi * freq * t) * envelope * 0.5).astype(np.float32)
    for i in range(5):
        sd.play(wave, samplerate)
        time.sleep(0.5)


def _layer_done_beep():
    """每层结束时播放短促提示音。"""
    try:
        _beep(660, 0.12)
    except Exception:
        pass


def _finished_pulse():
    """全部完成时播放间歇脉冲音（3 短 + 1 长）。"""
    if not _HAS_SOUND:
        return
    try:
        sr = 44100
        short = np.sin(2 * np.pi * 880 * np.linspace(0, 0.08, int(sr * 0.08), endpoint=False))
        short = (short * 0.5).astype(np.float32)
        silence = np.zeros(int(sr * 0.12), dtype=np.float32)
        long_wave = np.sin(2 * np.pi * 1100 * np.linspace(0, 0.3, int(sr * 0.3), endpoint=False))
        long_wave = (long_wave * 0.5).astype(np.float32)
        data = np.concatenate([short, silence, short, silence, short, silence, long_wave])
        sd.play(data, sr)
        sd.wait()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
AUTOSAVE_INTERVAL = 60.0       # 秒：定时保存间隔
AUTOSAVE_STATES = 50000        # 每处理多少新状态触发一次保存
GUI_REFRESH_MS = 500           # GUI 刷新间隔（毫秒）
PAUSE_CHECK_EVERY = 200        # 每处理多少个 frontier 状态检查一次暂停
PARALLEL_BATCH = 2000           # 并行处理时每批状态数（批间可暂停/停止）
PARALLEL_WORKERS = min(16, multiprocessing.cpu_count())  # 并行进程数
MAX_TASKS_PER_CHILD = 10000     # 子进程处理多少任务后重启（过高浪费内存，过低导致频繁重启）


def _worker_preds(args):
    """子进程工作函数：给定状态哈希，返回其所有前驱哈希。

    必须放在模块顶层以支持 pickle 序列化。
    """
    h, m, n, step, total = args
    from solver import table_core as _tc
    B = set(_tc.int_to_coords(h, total))
    preds = _tc.predecessors(B, m, n, step)
    return h, list(preds)


def get_data_dir(m, n, step):
    return os.path.join(DATA_DIR, f'{m}_{n}_{step}')


# ---------------------------------------------------------------------------
# 原子保存
# ---------------------------------------------------------------------------
def atomic_pickle_dump(obj, path):
    """原子写：先写 .tmp 再 rename，防写中途崩溃损坏文件。"""
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # 原子重命名（Windows 上 os.replace 跨进程安全）


# ---------------------------------------------------------------------------
# 建表工作线程
# ---------------------------------------------------------------------------
class BuildWorker(threading.Thread):
    """反向 BFS 工作线程。

    线程安全说明：
    - dist / frontier / current_dist 仅在本线程内修改（暂停时也只在本线程保存）
    - progress dict 供 GUI 轮询读取；简单类型赋值在 CPython 下原子，无需加锁
    - pause_event / stop_flag 用于线程间控制信号
    """

    def __init__(self, m, n, step):
        super().__init__(daemon=True)
        self.m = m
        self.n = n
        self.step = step
        self.total = m * n

        self.data_dir = get_data_dir(m, n, step)
        self.ckpt_path = os.path.join(self.data_dir, 'checkpoint.pkl')
        self.table_path = os.path.join(self.data_dir, 'table.pkl')
        self.meta_path = os.path.join(self.data_dir, 'meta.json')

        # BFS 状态
        self.dist = {}
        self.frontier = []
        self.current_dist = 0

        # 线程控制
        self.pause_event = threading.Event()
        self.stop_flag = False

        # 进度信息（供 GUI 轮询）
        self.progress = {
            'state': 'idle',            # idle/running/paused/finished/stopped
            'm': m, 'n': n, 'step': step,
            'total_states': 0,
            'frontier_size': 0,
            'current_dist': 0,
            'max_distance': 0,
            'dist_distribution': {},
            'layers_done': 0,
            'states_this_session': 0,
            'rate': 0.0,
            'elapsed': 0.0,
            'eta': None,
            'last_save_time': None,
            'started_at': None,
            'message': '',
        }

        # 定时保存簿记
        self._last_save_time = 0.0
        self._session_start = 0.0
        self._states_since_save = 0

    # ------------------------------------------------------------------
    # 断点加载 / 初始化
    # ------------------------------------------------------------------
    def load_checkpoint(self):
        """加载断点。返回 True 表示成功续算。"""
        if not os.path.exists(self.ckpt_path):
            return False
        try:
            with open(self.ckpt_path, 'rb') as f:
                data = pickle.load(f)
            meta = data.get('meta', {})
            if (meta.get('m') != self.m or meta.get('n') != self.n
                    or meta.get('step') != self.step):
                return False
            self.dist = data['dist']
            self.frontier = data['frontier']
            self.current_dist = data['current_dist']
            stats = data.get('stats', {})
            self.progress['total_states'] = stats.get('total_states', len(self.dist))
            self.progress['max_distance'] = stats.get('max_distance', self.current_dist)
            self.progress['dist_distribution'] = stats.get('distance_distribution', {})
            self.progress['layers_done'] = stats.get('layers_done', self.current_dist)
            self.progress['frontier_size'] = len(self.frontier)
            # 从 dist 重建完整分布（修复旧 checkpoint 因暂停/停止丢失的层数条目）
            rebuilt = {}
            for d in self.dist.values():
                rebuilt[d] = rebuilt.get(d, 0) + 1
            self.progress['dist_distribution'] = rebuilt
            self.progress['max_distance'] = max(rebuilt.keys()) if rebuilt else 0
            return True
        except Exception as e:
            print(f"[警告] 加载断点失败: {e}", flush=True)
            return False

    def init_fresh(self):
        """全新开始：从目标状态出发。"""
        goal = tc.goal_state(self.m, self.n)
        gH = tc.canonicalize(goal)
        self.dist = {gH: 0}
        self.frontier = [gH]
        self.current_dist = 0
        self.progress['dist_distribution'] = {0: 1}
        self.progress['total_states'] = 1
        self.progress['max_distance'] = 0
        self.progress['frontier_size'] = 1

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save_checkpoint(self, final=False):
        """保存断点到 checkpoint.pkl。final=True 时同时输出 table.pkl 和 meta.json。"""
        os.makedirs(self.data_dir, exist_ok=True)
        # 确保当前层的部分计数已记录（防止暂停/停止丢失分布条目）
        data = {
            'meta': {
                'm': self.m, 'n': self.n, 'step': self.step,
                'started_at': self.progress.get('started_at'),
                'last_saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'version': 1,
            },
            'dist': self.dist,
            'frontier': self.frontier,
            'current_dist': self.current_dist,
            'stats': {
                'total_states': len(self.dist),
                'max_distance': self.progress['max_distance'],
                'distance_distribution': self.progress['dist_distribution'],
                'layers_done': self.progress['layers_done'],
            },
        }
        atomic_pickle_dump(data, self.ckpt_path)
        self.progress['last_save_time'] = time.strftime('%H:%M:%S')

        if final:
            atomic_pickle_dump(self.dist, self.table_path)
            meta = {
                'm': self.m, 'n': self.n, 'step': self.step,
                'total_states': len(self.dist),
                'max_distance': self.progress['max_distance'],
                'distance_distribution': self.progress['dist_distribution'],
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            with open(self.meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

    def _maybe_save(self, force=False):
        """满足条件时自动保存。"""
        now = time.time()
        if (force
                or (now - self._last_save_time >= AUTOSAVE_INTERVAL)
                or (self._states_since_save >= AUTOSAVE_STATES)):
            self.save_checkpoint()
            self._last_save_time = now
            self._states_since_save = 0

    # ------------------------------------------------------------------
    # 暂停处理
    # ------------------------------------------------------------------
    def _check_pause(self):
        """检测暂停信号：保存后等待恢复。"""
        if not self.pause_event.is_set():
            return
        self.progress['state'] = 'paused'
        self.progress['message'] = '已暂停，正在保存...'
        self.save_checkpoint()
        self.progress['message'] = '已暂停（可安全关闭）'
        while self.pause_event.is_set() and not self.stop_flag:
            time.sleep(0.2)
        if self.stop_flag:
            return
        self.progress['state'] = 'running'
        self.progress['message'] = 'BFS 运行中'
        self._last_save_time = time.time()

    # ------------------------------------------------------------------
    # BFS 主循环
    # ------------------------------------------------------------------
    def run(self):
        self._session_start = time.time()
        self._last_save_time = time.time()
        if not self.dist:
            self.init_fresh()
        self.progress['started_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        self.progress['state'] = 'running'
        self.progress['message'] = 'BFS 运行中'

        total = self.total
        step = self.step
        m, n = self.m, self.n
        dist = self.dist

        # 并行进程池（全程复用，maxtasksperchild 定期回收子进程释放缓存）
        pool = multiprocessing.Pool(
            processes=PARALLEL_WORKERS,
            maxtasksperchild=MAX_TASKS_PER_CHILD,
        )
        try:
            while self.frontier and not self.stop_flag:
                self._check_pause()
                if self.stop_flag:
                    break

                self.current_dist += 1
                next_frontier = []
                new_count = 0
                cur_dist = self.current_dist
                dist_distrib = self.progress['dist_distribution']

                frontier = self.frontier
                batch_size = PARALLEL_BATCH
                for batch_start in range(0, len(frontier), batch_size):
                    # 批间可暂停/停止
                    self._check_pause()
                    if self.stop_flag:
                        # 批间 break 是安全的——imap_unordered 没在跑，不会丢数据
                        break

                    batch = frontier[batch_start:batch_start + batch_size]
                    tasks = [(h, m, n, step, total) for h in batch]

                    # 必须消耗完 imap_unordered 所有结果才能退出（否则子进程缓冲数据丢失）
                    for h_source, preds in pool.imap_unordered(
                            _worker_preds, tasks, chunksize=max(1, batch_size // PARALLEL_WORKERS)):
                        if not self.stop_flag:
                            for pH in preds:
                                if pH not in dist:
                                    dist[pH] = cur_dist
                                    next_frontier.append(pH)
                                    new_count += 1
                                    self.progress['states_this_session'] += 1
                                    self._states_since_save += 1
                        # stop_flag 时仍继续迭代以排出缓冲，但不写入新状态

                    # 批后进度更新 + 自动保存
                    self.progress['total_states'] = len(dist)
                    self.progress['frontier_size'] = (len(frontier) - batch_start
                                                      + len(next_frontier))
                    elapsed = time.time() - self._session_start
                    self.progress['elapsed'] = elapsed
                    session_states = self.progress['states_this_session']
                    self.progress['rate'] = session_states / elapsed if elapsed > 0 else 0
                    if self._states_since_save >= AUTOSAVE_STATES:
                        self._maybe_save()

                if self.stop_flag:
                    self.frontier = next_frontier
                    break

                self.frontier = next_frontier
                self.progress['layers_done'] = cur_dist
                self.progress['frontier_size'] = len(self.frontier)
                self.progress['total_states'] = len(dist)
                if new_count > 0:
                    dist_distrib[cur_dist] = new_count
                    self.progress['max_distance'] = cur_dist

                # 进度更新
                elapsed = time.time() - self._session_start
                self.progress['elapsed'] = elapsed
                self.progress['current_dist'] = cur_dist
                session_states = self.progress['states_this_session']
                if elapsed > 0:
                    self.progress['rate'] = session_states / elapsed
                rate = self.progress['rate']
                if rate > 0 and self.progress['frontier_size'] > 0:
                    self.progress['eta'] = self.progress['frontier_size'] / rate
                else:
                    self.progress['eta'] = None

                # 每层结束保存 + 提示音
                self._maybe_save(force=True)
                _layer_done_beep()

                if not self.frontier:
                    break
        finally:
            pool.close()
            pool.join()

        # 结束处理
        if self.stop_flag:
            self.progress['state'] = 'stopped'
            self.progress['message'] = '已停止并保存（可续算）'
            self.save_checkpoint()
        else:
            self.progress['state'] = 'finished'
            self.progress['message'] = f'建表完成！共 {len(dist)} 个状态'
            self.save_checkpoint(final=True)
            _finished_pulse()

    # ------------------------------------------------------------------
    # 控制接口
    # ------------------------------------------------------------------
    def pause(self):
        self.pause_event.set()

    def resume(self):
        self.pause_event.clear()

    def stop(self):
        self.stop_flag = True
        self.pause_event.clear()  # 解除暂停等待，让线程能退出


# ---------------------------------------------------------------------------
# tkinter GUI
# ---------------------------------------------------------------------------
class BuildGUI:
    """简易 tkinter GUI：状态显示 + 距离分布 + 按钮控制 + 数据浏览。"""

    def __init__(self, m, n, step):
        self.m, self.n, self.step = m, n, step
        self.worker = BuildWorker(m, n, step)

        self.root = tk.Tk()
        self.root.title(f'反向 BFS 建表 — {m}×{n} step={step}')
        self.root.geometry('720x640')
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

        self._build_ui()

        # 启动时检测断点
        if self.worker.load_checkpoint():
            self.log(f'检测到断点，已加载 {len(self.worker.dist)} 个状态，'
                     f'当前层 {self.worker.current_dist}，前沿 {len(self.worker.frontier)}')
        else:
            self.log('无断点，从头开始建表')

        self.worker.start()
        self.root.after(GUI_REFRESH_MS, self.refresh)

    def _build_ui(self):
        # ---- 顶部参数区 ----
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill='x')
        ttk.Label(top, text=f'尺寸: {self.m}×{self.n}  步长: {self.step}  '
                           f'总格子: {self.m * self.n}',
                  font=('', 11, 'bold')).pack(anchor='w')

        # ---- 状态信息区 ----
        info_frame = ttk.LabelFrame(self.root, text='运行状态', padding=8)
        info_frame.pack(fill='x', padx=8, pady=4)

        self.info_vars = {}
        labels = [
            ('state', '状态'), ('message', '消息'),
            ('current_dist', '当前层'), ('total_states', '已发现状态'),
            ('frontier_size', '前沿大小'), ('max_distance', '最大距离'),
            ('rate', '速率(状态/秒)'), ('elapsed', '已用时(秒)'),
            ('eta', 'ETA(秒)'), ('last_save_time', '上次保存'),
            ('layers_done', '已完成层'), ('states_this_session', '本轮新状态'),
        ]
        for i, (key, text) in enumerate(labels):
            row_idx, col_idx = divmod(i, 2)
            row = ttk.Frame(info_frame)
            row.grid(row=row_idx, column=col_idx, sticky='w', padx=4, pady=1)
            ttk.Label(row, text=f'{text}:', width=14).pack(side='left')
            v = tk.StringVar(value='-')
            ttk.Label(row, textvariable=v).pack(side='left')
            self.info_vars[key] = v
        info_frame.columnconfigure(0, weight=1)
        info_frame.columnconfigure(1, weight=1)

        # ---- 距离分布 ----
        dist_frame = ttk.LabelFrame(self.root, text='距离分布', padding=8)
        dist_frame.pack(fill='both', expand=True, padx=8, pady=4)
        self.dist_text = scrolledtext.ScrolledText(dist_frame, height=8,
                                                   font=('Consolas', 10))
        self.dist_text.pack(fill='both', expand=True)

        # ---- 按钮区 ----
        btn_frame = ttk.Frame(self.root, padding=8)
        btn_frame.pack(fill='x')
        self.btn_start = ttk.Button(btn_frame, text='运行中',
                                    command=self.start_or_resume, state='disabled')
        self.btn_start.pack(side='left', padx=4)
        self.btn_pause = ttk.Button(btn_frame, text='暂停',
                                    command=self.toggle_pause)
        self.btn_pause.pack(side='left', padx=4)
        ttk.Button(btn_frame, text='立即保存',
                   command=self.save_now).pack(side='left', padx=4)
        ttk.Button(btn_frame, text='查看数据',
                   command=self.show_data).pack(side='left', padx=4)
        ttk.Button(btn_frame, text='停止并保存',
                   command=self.stop_and_save).pack(side='right', padx=4)

        # ---- 日志区 ----
        log_frame = ttk.LabelFrame(self.root, text='日志', padding=8)
        log_frame.pack(fill='both', expand=True, padx=8, pady=4)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=5,
                                                  font=('Consolas', 9))
        self.log_text.pack(fill='both', expand=True)

    def log(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.log_text.insert('end', f'[{ts}] {msg}\n')
        self.log_text.see('end')

    def refresh(self):
        p = self.worker.progress
        for key in self.info_vars:
            val = p.get(key, '-')
            if isinstance(val, float):
                val = f'{val:.1f}'
            self.info_vars[key].set(str(val) if val is not None else '-')

        # 距离分布条形图（保留滚动位置，按比例缩放柱状图）
        distrib = p.get('dist_distribution', {})
        if distrib:
            # 保存滚动位置
            scroll_pos = self.dist_text.yview()
            self.dist_text.delete('1.0', 'end')
            max_count = max(distrib.values())
            max_count = max(max_count, 1)  # 防止除零
            for d in sorted(distrib.keys(), key=lambda x: int(x)):
                count = int(distrib[d])
                bar_len = count * 50 // max_count  # 按比例缩放
                bar = '█' * bar_len
                self.dist_text.insert('end', f'  d={int(d):3d}: {count:8d}  {bar}\n')
            # 恢复滚动位置
            self.dist_text.yview_moveto(scroll_pos[0] if scroll_pos[0] > 0 else 0)

        # 按钮状态
        state = p.get('state', 'idle')
        if state == 'finished':
            self.btn_pause.config(state='disabled', text='已完成')
            self.btn_start.config(state='disabled', text='已完成')
        elif state == 'stopped':
            self.btn_pause.config(state='disabled', text='已停止')
            self.btn_start.config(state='normal', text='开始/继续')
        elif state == 'paused':
            self.btn_pause.config(text='继续', state='normal')
            self.btn_start.config(state='disabled', text='运行中')
        else:
            self.btn_pause.config(text='暂停', state='normal')
            self.btn_start.config(state='disabled', text='运行中')

        self.root.after(GUI_REFRESH_MS, self.refresh)

    def toggle_pause(self):
        if self.worker.pause_event.is_set():
            self.worker.resume()
            self.btn_pause.config(text='暂停')
            self.log('继续运行')
        else:
            self.worker.pause()
            self.log('请求暂停...（将在当前批次完成后保存）')

    def save_now(self):
        threading.Thread(target=self.worker.save_checkpoint, daemon=True).start()
        self.log('手动保存中...')

    def show_data(self):
        """弹窗显示各距离层的样本状态可视化。"""
        win = tk.Toplevel(self.root)
        win.title('数据浏览 — 各距离层样本')
        win.geometry('520x600')
        text = scrolledtext.ScrolledText(win, font=('Consolas', 10))
        text.pack(fill='both', expand=True)

        dist = self.worker.dist
        if not dist:
            text.insert('end', '暂无数据')
            return

        # 每个距离层取第一个遇到的状态作为样本
        samples = {}
        for h, d in dist.items():
            if d not in samples:
                samples[d] = h
                if len(samples) >= 100:  # 防止太多
                    break

        total = self.m * self.n
        for d in sorted(samples.keys()):
            h = samples[d]
            coords = tc.int_to_coords(h, total)
            rs = [r for r, _ in coords]
            cs = [c for _, c in coords]
            mr, mc = min(rs), min(cs)
            grid = set((r - mr, c - mc) for r, c in coords)
            max_r = max(r for r, _ in grid)
            max_c = max(c for _, c in grid)
            text.insert('end', f'━━━ 距离 {d} ━━━\n')
            for r in range(max_r + 1):
                row_str = ''
                for c in range(max_c + 1):
                    row_str += '█' if (r, c) in grid else '·'
                text.insert('end', '  ' + row_str + '\n')
            text.insert('end', '\n')

    def stop_and_save(self):
        if not messagebox.askyesno('确认', '确定停止建表并保存当前进度？'):
            return
        self.worker.stop()
        self.log('请求停止并保存...')

    def start_or_resume(self):
        """停止后重新创建 worker 并从断点续算。"""
        self.worker = BuildWorker(self.m, self.n, self.step)
        if self.worker.load_checkpoint():
            self.log(f'从断点续算，已加载 {len(self.worker.dist)} 个状态，'
                     f'当前层 {self.worker.current_dist}，前沿 {len(self.worker.frontier)}')
        else:
            self.log('无断点，从头开始建表')
        self.worker.start()
        self.log('建表已启动')

    def on_close(self):
        if self.worker.is_alive():
            if messagebox.askyesno('确认', '建表仍在运行。\n停止并退出？（进度已自动保存）'):
                self.worker.stop()
                self.worker.join(timeout=15)
                self.root.destroy()
            else:
                return
        else:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# 无 GUI 模式（纯 CLI 日志）
# ---------------------------------------------------------------------------
def run_cli(m, n, step):
    """无 tkinter 环境下的纯 CLI 建表模式。"""
    worker = BuildWorker(m, n, step)
    if worker.load_checkpoint():
        print(f'[续算] 已加载 {len(worker.dist)} 个状态，'
              f'当前层 {worker.current_dist}，前沿 {len(worker.frontier)}', flush=True)
    else:
        print('[新建] 从目标状态开始建表', flush=True)

    worker.start()

    try:
        while worker.is_alive():
            time.sleep(5)
            p = worker.progress
            print(f'  [{p["state"]}] 层{p["current_dist"]} '
                  f'状态数={p["total_states"]} 前沿={p["frontier_size"]} '
                  f'速率={p["rate"]:.1f}/s 用时={p["elapsed"]:.0f}s '
                  f'保存={p["last_save_time"]}', flush=True)
    except KeyboardInterrupt:
        print('\n[中断] 正在停止并保存...', flush=True)
        worker.stop()
        worker.join(timeout=30)

    p = worker.progress
    print(f'\n最终: {p["message"]}', flush=True)
    print(f'  总状态数={p["total_states"]} 最大距离={p["max_distance"]}', flush=True)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    no_gui = '--no-gui' in args
    args = [a for a in args if a != '--no-gui']

    m = int(args[0]) if len(args) > 0 else 4
    n = int(args[1]) if len(args) > 1 else 4
    step = int(args[2]) if len(args) > 2 else 2

    if no_gui:
        run_cli(m, n, step)
    else:
        try:
            gui = BuildGUI(m, n, step)
            gui.run()
        except Exception as e:
            print(f'[GUI 启动失败: {e}] 回退到 CLI 模式', flush=True)
            run_cli(m, n, step)


if __name__ == '__main__':
    main()
