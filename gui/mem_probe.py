# -*- coding: utf-8 -*-
"""可选的内存观测通道（默认完全关闭，不影响平常路径）。

用途：用户报「偶发 700MB、无法复现」时，开环境变量重跑，拿一条
「哪一步把 RSS 顶上去」的时间线，而不是靠猜改缓存。

启用：

    set GATENNEA_MEM_PROBE=1              每 0.5 秒采一次
    set GATENNEA_MEM_PROBE=0.2            自定义间隔（秒）
    set GATENNEA_MEM_PROBE_OUT=D:\\mem.csv   自定义输出路径（可选）

输出：CSV 逐行追加写到系统临时目录（默认
``<temp>/gatennea_mem_<pid>_<时间戳>.csv``），进程一启动就建文件、
每行立即 flush，**强杀进程也不丢数据**。停用时不 import psutil、
不起线程、不建文件、不占内存。

每行记录：时间、RSS、当前阶段（求解 / 打乱 / 宏播放 / 动画 / 空闲）、
历史快照条数、查表缓存估算字节、开机帧张数、事件标签。单次涨幅
超过 SPIKE_MB 会自动记一条 ``SPIKE +xxxMB`` 事件，方便直接定位跳变点。

2026-11-12 实测背景见 docs/spec/内存开销排查_2026-11-12.md。
"""
import atexit
import ctypes
import os
import sys
import tempfile
import threading
import time
from ctypes import wintypes

ENV_FLAG = 'GATENNEA_MEM_PROBE'
ENV_OUT = 'GATENNEA_MEM_PROBE_OUT'
DEFAULT_INTERVAL = 0.5
SPIKE_MB = 32.0
MAX_SAMPLES = 20000          # 采样器自己也不能无上限增长

_CSV_HEADER = ('t_s,rss_mb,phase,history_len,table_cache_mb,'
               'boot_frames,solver_running,shuffle_active,event\n')
_ACTIVE = None


# ---------------------------------------------------------------------------
# RSS 读取：psutil 优先；打包环境没带 psutil 时退到系统 API
# ---------------------------------------------------------------------------
if sys.platform == 'win32':
    from ctypes import wintypes

    class _PMC(ctypes.Structure):
        _fields_ = [
            ('cb', wintypes.DWORD),
            ('PageFaultCount', wintypes.DWORD),
            ('PeakWorkingSetSize', ctypes.c_size_t),
            ('WorkingSetSize', ctypes.c_size_t),
            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPagedPoolUsage', ctypes.c_size_t),
            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
            ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
            ('PagefileUsage', ctypes.c_size_t),
            ('PeakPagefileUsage', ctypes.c_size_t),
        ]
else:
    _PMC = None


def rss_mb():
    """当前进程 RSS（MB）。取不到返回 0.0，绝不让观测拖垮游戏。"""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1048576.0
    except Exception:
        pass
    try:
        if _PMC is not None:
            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(pmc), pmc.cb)
            if ok:
                return pmc.WorkingSetSize / 1048576.0
        else:
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# 阶段 / 持有量观测（只读属性，跨线程读 Python 属性是安全的）
# ---------------------------------------------------------------------------
def observe(gui):
    """采样一帧的「当前在干什么 + 谁在持有内存」。"""
    try:
        solve_on = bool(getattr(gui, '_auto_solve_running', False)
                        or getattr(gui, '_gradient_busy', False))
        shuffle_on = bool(getattr(gui, '_infinite_shuffle_active', False))
        if solve_on:
            phase = 'solve'
        elif shuffle_on:
            phase = 'shuffle'
        elif getattr(gui, 'macro_executing', False):
            phase = 'macro'
        elif getattr(gui, 'animating', False):
            phase = 'anim'
        else:
            phase = 'idle'
        hist = len(getattr(getattr(gui, 'game_history', None), 'history', ()) or ())
        frames = getattr(gui, '_boot_frames', None)
        n_frames = len(frames) if frames else 0
        try:
            from solver.table_solver import table_cache_stats
            cache_mb = round(table_cache_stats()['bytes'] / 1048576.0, 1)
        except Exception:
            cache_mb = -1.0
        return {
            'phase': phase, 'history_len': hist,
            'table_cache_mb': cache_mb, 'boot_frames': n_frames,
            'solver_running': int(solve_on), 'shuffle_active': int(shuffle_on),
        }
    except Exception:
        return {
            'phase': '?', 'history_len': -1, 'table_cache_mb': -1.0,
            'boot_frames': -1, 'solver_running': 0, 'shuffle_active': 0,
        }


# ---------------------------------------------------------------------------
# 采样器
# ---------------------------------------------------------------------------
class MemProbe:
    """后台按间隔采 RSS 与阶段，逐行 flush 到 CSV。"""

    def __init__(self, gui, interval=DEFAULT_INTERVAL, out_path=None):
        self.gui = gui
        self.interval = max(0.02, float(interval))
        self.t0 = time.monotonic()
        self.out_path = out_path or os.path.join(
            tempfile.gettempdir(),
            'gatennea_mem_%d_%s.csv' % (os.getpid(),
                                        time.strftime('%Y%m%d_%H%M%S')))
        self.samples = []
        self.events = []
        self.peak_mb = 0.0
        self.peak_phase = ''
        self._last_mb = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._fh = None
        self._closed = False
        self._lock = threading.Lock()

    def start(self):
        parent = os.path.dirname(self.out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._fh = open(self.out_path, 'w', encoding='utf-8', buffering=1)
        self._fh.write(_CSV_HEADER)
        self._sample('start', record=False)
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name='gatennea-mem-probe')
        self._thread.start()
        print('[mem_probe] 采样中：%s（间隔 %.2fs）'
              % (self.out_path, self.interval), flush=True)
        return self

    def _loop(self):
        while not self._stop.wait(self.interval):
            self._sample('', record=True)

    def _sample(self, tag, record=True):
        mb = rss_mb()
        obs = observe(self.gui)
        with self._lock:
            if mb > self.peak_mb:
                self.peak_mb = mb
                self.peak_phase = obs['phase']
            event = tag
            if record and self._last_mb and mb - self._last_mb >= SPIKE_MB:
                event = 'SPIKE +%.0fMB' % (mb - self._last_mb)
                self.events.append((round(time.monotonic() - self.t0, 2), event))
            self._last_mb = mb
            row = {
                't': round(time.monotonic() - self.t0, 2),
                'rss_mb': round(mb, 1), 'event': event,
            }
            row.update(obs)
            self.samples.append(row)
            if len(self.samples) > MAX_SAMPLES:
                del self.samples[:len(self.samples) - MAX_SAMPLES]
            line = ('%(t)s,%(rss_mb)s,%(phase)s,%(history_len)s,'
                    '%(table_cache_mb)s,%(boot_frames)s,'
                    '%(solver_running)s,%(shuffle_active)s,%(event)s\n') % row
            if self._fh is not None:
                try:
                    self._fh.write(line)
                except Exception:
                    pass

    def mark(self, tag):
        """外部关键节点打标签（求解开始 / 换局 / 载入存档…）。"""
        if not self._closed:
            self._sample(str(tag), record=False)

    def stop(self):
        """幂等；atexit 与正常退出都会调。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._stop.set()
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
            self._fh = None
        print('[mem_probe] 峰值 %.1f MB（阶段 %s），记录 %d 条 → %s'
              % (self.peak_mb, self.peak_phase, len(self.samples),
                 self.out_path), flush=True)

    def report(self):
        return {
            'out_path': self.out_path, 'peak_mb': round(self.peak_mb, 1),
            'peak_phase': self.peak_phase, 'samples': len(self.samples),
            'events': list(self.events), 'interval': self.interval,
        }


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def parse_flag(value=None):
    """返回间隔秒数；None / '0' / 空 = 不启用。"""
    raw = os.environ.get(ENV_FLAG, '') if value is None else value
    raw = (raw or '').strip()
    if not raw or raw in ('0', 'off', 'false', 'no'):
        return None
    try:
        return max(0.02, float(raw))
    except ValueError:
        return DEFAULT_INTERVAL


def is_enabled():
    return parse_flag() is not None


def maybe_start(gui):
    """GUI.run() 开头调一次；未启用时零开销返回 None。"""
    global _ACTIVE
    interval = parse_flag()
    if interval is None:
        return None
    try:
        probe = MemProbe(gui, interval=interval,
                         out_path=os.environ.get(ENV_OUT) or None).start()
        _ACTIVE = probe
        atexit.register(probe.stop)
        return probe
    except Exception as exc:
        print('[mem_probe] 启动失败，已跳过：%s' % exc, flush=True)
        return None


def mark(tag):
    """任何模块都能打标签；未启用时是空操作。"""
    if _ACTIVE is not None and not _ACTIVE._closed:
        _ACTIVE.mark(tag)
