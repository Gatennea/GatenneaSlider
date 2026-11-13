# -*- coding: utf-8 -*-
"""内存开销排查（待办 §三十六）— 行为护栏 + 真刀反向验证。

用户报「偶发 700MB、平常 <200MB、无法复现」。2026-11-12 离屏实测复现：

    真实 GUI 空闲                         138 MB
    load_table(4,4,1) 后                 613 MB   ← 5,135,644 条 dist = +475 MB
    + 4_4_2 / 5_5_2                     735 MB   ← 用户看到的 700MB
    release_table_cache() 后             141 MB

根因不是「背景没擦」「音频整份载入」，而是 solver/table_solver.py 的模块级
_table_cache **无上限、无释放**：solver/auto_solver.py 第一步「①查表」无条件
调 table_solve，只要局面落在某个 checkpoint 档位就把整张断点表永久留住。

判据不查源码字串，只盯真实行为：缓存里到底有没有这张表、调用返回后 RSS
回不回落、撤掉预算后 700MB 能不能被重新制造出来、开机帧播完还在不在。

用法：D:/python/python.exe test/_test_memory_budget.py
"""
import gc
import os
import sys
import time
import tempfile
from unittest import mock

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pygame  # noqa: E402
import GUI  # noqa: E402
from solver import table_solver as ts  # noqa: E402
from gui import mem_probe  # noqa: E402

_FAILS = []
_OK = [0]


def check(name, cond, detail=''):
    if cond:
        _OK[0] += 1
        print('  ok  : ' + name)
    else:
        _FAILS.append(name)
        print('  FAIL: ' + name + ('  ' + detail if detail else ''))
    return bool(cond)


class _FakeSurf:
    def __init__(self, w=854, h=480):
        self._w, self._h = w, h

    def get_size(self):
        return (self._w, self._h)

    def set_alpha(self, a):
        pass

    def get_rect(self, **kw):
        return pygame.Rect(0, 0, self._w, self._h)


class _FakeScreen:
    def __init__(self):
        self.blits = 0

    def get_size(self):
        return (960, 540)

    def fill(self, color):
        pass

    def blit(self, *a, **k):
        self.blits += 1


class _FakeClock:
    def tick(self, fps):
        return 16


def _fake_gui(**kw):
    g = type('G', (), {})()
    g.screen = _FakeScreen()
    g._boot_frames = [_FakeSurf()]
    g.show_boot_animation = True
    g.running = True
    g._boot_paint_time = 0
    for k, v in kw.items():
        setattr(g, k, v)
    return g


def _bind_boot(g):
    cls = GUI.SliderGUI
    for name in ('_make_boot_cover', '_paint_boot', '_paint_boot_cover',
                 '_load_boot_frames'):
        setattr(g, name, getattr(cls, name).__get__(g))
    return g


# ---------------------------------------------------------------------------
# P. 判据本身（不载入大表，快）
# ---------------------------------------------------------------------------
def predicate():
    check('P1 估算按条目数 × 100B',
          ts._table_est_bytes({i: i for i in range(1000)}) == 100000)
    check('P2 采样开关解析：0/空/关 都不启用',
          mem_probe.parse_flag('0') is None
          and mem_probe.parse_flag('') is None
          and mem_probe.parse_flag('off') is None)
    check('P2b 采样开关解析：1 / 0.2 给出间隔',
          mem_probe.parse_flag('1') == 1.0
          and mem_probe.parse_flag('0.2') == 0.2)
    check('P3 RSS 读取可用（psutil 或系统 API）', mem_probe.rss_mb() > 0)
    st = ts.table_cache_stats()
    check('P4 缓存观测结构完整',
          all(k in st for k in ('entries', 'bytes', 'max_single', 'max_total')))
    g = _fake_gui()
    check('P5 阶段观测：空闲 / 求解 / 打乱',
          mem_probe.observe(g)['phase'] == 'idle'
          and mem_probe.observe(_fake_gui(_auto_solve_running=True))['phase'] == 'solve'
          and mem_probe.observe(
              _fake_gui(_infinite_shuffle_active=True))['phase'] == 'shuffle')


# ---------------------------------------------------------------------------
# A. 正向：修复后的真实行为
# ---------------------------------------------------------------------------
def forward():
    ts.release_table_cache()

    t = ts.load_table(4, 4, 2)
    check('A1 小表 4_4_2 进缓存且条目数正确',
          bool(t) and len(t) == 559504
          and (4, 4, 2) in dict(ts.table_cache_stats()['entries']),
          'len=%s' % (len(t) if t else None))
    check('A2 重复载入命中缓存（同一对象，不是重读 18MB 文件）',
          ts.load_table(4, 4, 2) is t)

    # LRU 总预算：临时压到 100MB，让第二张表把第一张挤掉
    orig_total = ts.TABLE_CACHE_MAX_TOTAL
    ts.TABLE_CACHE_MAX_TOTAL = 100 * 1024 * 1024
    ts.load_table(5, 5, 2)
    keys = [k for k, _ in ts.table_cache_stats()['entries']]
    check('A3 超过总预算时淘汰最久未用的档位',
          (4, 4, 2) not in keys and (5, 5, 2) in keys,
          'keys=%s' % keys)
    ts.TABLE_CACHE_MAX_TOTAL = orig_total
    ts.release_table_cache()

    # 默认上限 = 单表预算：165MB 的 4_4_1 断点表直接跳过（2026-11-13 用户
    # 复报「求解期间卡顿 + 内存 500MB」，实测就是它：反序列化 8.9s、
    # 瞬时 RSS 513MB、主循环被切成 0.1~1s 的停顿）
    check('A0 单表文件上限默认 = 单表缓存预算（不是「不限」）',
          ts._max_file_bytes() == ts.TABLE_CACHE_MAX_SINGLE
          and ts.TABLE_CACHE_MAX_SINGLE == 64 * 1024 * 1024,
          'cap=%s max_single=%s' % (ts._max_file_bytes(),
                                    ts.TABLE_CACHE_MAX_SINGLE))

    gc.collect()
    base = mem_probe.rss_mb()
    skipped_big = ts.load_table(4, 4, 1)
    gc.collect()
    after_skip = mem_probe.rss_mb()
    check('A4 默认跳过 165MB 断点表（不载入就不该有 500MB 峰值）',
          skipped_big is None, repr(skipped_big))
    check('A4b 跳过时 RSS 基本不动', after_skip - base < 40,
          'delta=%.1f MB' % (after_skip - base))

    # 显式放开（=0）才真载入；载入完仍不许常驻
    os.environ['GATENNEA_TABLE_MAX_FILE_MB'] = '0'
    try:
        ln = len(ts.load_table(4, 4, 1) or {})
    finally:
        os.environ.pop('GATENNEA_TABLE_MAX_FILE_MB', None)
    gc.collect()
    after = mem_probe.rss_mb()
    keys = [k for k, _ in ts.table_cache_stats()['entries']]
    check('A4c 显式放开才载入 4_4_1，且不进长期缓存',
          ln == 5135644 and (4, 4, 1) not in keys,
          'len=%s keys=%s' % (ln, keys))
    check('A4d 载入返回后 RSS 回落（一次性峰值，不常驻）',
          after - base < 80, 'delta=%.1f MB' % (after - base))

    # 自定义上限：1MB 时连 18MB 的表也跳
    os.environ['GATENNEA_TABLE_MAX_FILE_MB'] = '1'
    ts.release_table_cache()
    skipped = ts.load_table(4, 4, 2)
    os.environ.pop('GATENNEA_TABLE_MAX_FILE_MB', None)
    check('A5 自定义上限（1MB）时超限表直接跳过', skipped is None, repr(skipped))
    check('A5b 上限恢复默认后，小表（18MB）照常载入',
          len(ts.load_table(4, 4, 2) or {}) == 559504)
    ts.release_table_cache()

    # 开机 24 帧：标题阶段一过就释放
    cls = GUI.SliderGUI
    g_off = _fake_gui(show_boot_animation=False)
    cls._run_boot_phase(g_off, _FakeClock())
    check('A6a 关闭开机动画的早退路径也释放帧',
          getattr(g_off, '_boot_frames', 'missing') is None)

    g_on = _bind_boot(_fake_gui())
    ticks = {'t': 0}

    def fake_ticks():
        ticks['t'] += 40
        return ticks['t']

    with mock.patch('pygame.time.get_ticks', side_effect=fake_ticks), \
            mock.patch('pygame.event.get', return_value=[]), \
            mock.patch('pygame.display.flip'), \
            mock.patch('pygame.draw.line', return_value=None), \
            mock.patch('pygame.transform.scale', return_value=_FakeSurf()):
        try:
            cls._run_boot_phase(g_on, _FakeClock())
        except Exception as exc:
            check('A6b 封面阶段不抛异常', False, repr(exc))
    check('A6b 封面阶段确有绘制且播完释放帧',
          g_on.screen.blits > 0
          and getattr(g_on, '_boot_frames', 'missing') is None,
          'blits=%s' % g_on.screen.blits)

    # 采样器：逐行落盘、峰值、标签、默认关闭
    out = os.path.join(tempfile.gettempdir(), '_gats_mem_probe_test.csv')
    if os.path.exists(out):
        os.remove(out)
    probe = mem_probe.MemProbe(_fake_gui(), interval=0.05, out_path=out)
    probe.start()
    time.sleep(0.18)
    probe.mark('unit_test')
    time.sleep(0.08)
    probe.stop()
    content = open(out, encoding='utf-8').read()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    check('A7a CSV 逐行落盘且有数据行与标签',
          len(lines) >= 3 and 'unit_test' in content
          and content.startswith('t_s,'), 'lines=%d' % len(lines))
    rep = probe.report()
    check('A7b 峰值 > 0 且报告含事件表',
          rep['peak_mb'] > 0 and rep['samples'] >= 3
          and isinstance(rep['events'], list))
    os.remove(out)
    os.environ.pop(mem_probe.ENV_FLAG, None)
    check('A7c 未启用时 maybe_start 零开销返回 None',
          mem_probe.maybe_start(_fake_gui()) is None)

    # 求解期缓存（2026-11-13 用户报「连续求解内存暴涨」的真凶）：
    # 规范态 / 连通性 lru_cache 只服务单次求解，收尾必须丢掉，只留玩家历史。
    import solver.table_core as TC
    check('A8a 求解期缓存上限已收紧（不再是 10 万条 ≈ 400MB）',
          TC._TC_CANON_CACHE_MAX <= 16384 and TC._TC_MASK_CACHE_MAX <= 16384,
          'canon=%s mask=%s' % (TC._TC_CANON_CACHE_MAX,
                                TC._TC_MASK_CACHE_MAX))
    TC.clear_caches()
    base_coords = frozenset({(0, 0), (0, 1), (1, 0)})
    for i in range(64):
        TC.canonicalize(frozenset({(0, i % 5), (1, i % 3)}) | base_coords)
    filled = TC.cache_stats()['canonicalize']
    TC.clear_caches()
    check('A8b clear_caches 能把求解期缓存清干净',
          filled > 0 and TC.cache_stats()['canonicalize'] == 0,
          'filled=%d after=%d' % (filled, TC.cache_stats()['canonicalize']))

    # 收尾接口本身：_release_solver_caches 得两张缓存 + 距离表缓存一起放
    cls2 = GUI.SliderGUI
    g_rel = _fake_gui()
    g_rel._release_solver_caches = cls2._release_solver_caches.__get__(g_rel)
    for i in range(64):
        TC.canonicalize(frozenset({(0, i % 5), (1, i % 3)}) | base_coords)
    ts.load_table(4, 4, 2)          # 塞一张小表进缓存
    g_rel._release_solver_caches()
    st = ts.table_cache_stats()
    check('A8c 求解收尾接口同时清缓存与距离表',
          TC.cache_stats()['canonicalize'] == 0 and st['entries'] == [],
          'tc=%s tbl=%s' % (TC.cache_stats(), st['entries']))
    ts.release_table_cache()        # 别把表留在缓存里污染后面的基线

    # 真求解一次：跑完（含取消路径）缓存必须归零，玩家历史保留
    g_live = GUI.SliderGUI(m=4, n=4, step=2)
    g_live.animation_enabled = False
    g_live.animation_duration = 0
    g_live.thinking_enabled = False
    g_live.solver_algorithm = 'hybrid'      # 流式收尾路径（快，几秒内跑完）
    g_live.game.shuffle(attempts=20, step=2)
    hist_before = len(getattr(g_live.game_history, 'history', []) or [])
    g_live._start_auto_solve()
    t_end = time.time() + 30
    while time.time() < t_end:
        g_live._pump_auto_stages()
        g_live.update_animation()
        q = getattr(g_live, '_auto_stage_queue', None)
        qempty = True
        if q is not None:
            try:
                qempty = q.empty()
            except Exception:
                pass
        if not getattr(g_live, '_auto_solve_running', False) and qempty:
            break
        time.sleep(0.002)
    check('A8d 真求解跑完后求解期缓存归零（计算过程用完即弃）',
          TC.cache_stats()['canonicalize'] == 0,
          'currsize=%d' % TC.cache_stats()['canonicalize'])
    check('A8e 玩家历史照旧保留（只丢计算过程，不丢记录）',
          len(getattr(g_live.game_history, 'history', []) or []) >= hist_before,
          'before=%d after=%d'
          % (hist_before,
             len(getattr(g_live.game_history, 'history', []) or [])))


# ---------------------------------------------------------------------------
# B. 真刀反向验证：把修复在当前进程里中和掉，要求 700MB 真能被再制造出来
# ---------------------------------------------------------------------------
def reverse():
    s1 = ts.TABLE_CACHE_MAX_SINGLE
    s2 = ts.TABLE_CACHE_MAX_TOTAL
    ts.TABLE_CACHE_MAX_SINGLE = 10 ** 12   # 所有表都进缓存 = 旧实现
    ts.TABLE_CACHE_MAX_TOTAL = 10 ** 13
    ts.release_table_cache()
    gc.collect()
    base = mem_probe.rss_mb()
    held = []
    try:
        for case in ((4, 4, 1), (4, 4, 2), (5, 5, 2)):
            held.append(ts.load_table(*case))
        keys = [k for k, _ in ts.table_cache_stats()['entries']]
        delta = mem_probe.rss_mb() - base
        check('B1 撤掉预算后，大表真的被永久缓存（A4 不是恒绿）',
              (4, 4, 1) in keys and len(keys) == 3, 'keys=%s' % keys)
        check('B2 撤掉预算后，多档累积真的把 RSS 顶上去（A4b 不是恒绿）',
              delta > 450, 'delta=%.1f MB' % delta)

        # 撤掉开机帧释放：换成「什么都不做」的旧阶段实现
        def old_phase(self, clock):
            pass

        g = _fake_gui()
        with mock.patch.object(GUI.SliderGUI, '_run_boot_phase', old_phase):
            GUI.SliderGUI._run_boot_phase(g, _FakeClock())
        check('B3 撤掉释放后开机帧仍在（A6 不是恒绿）',
              isinstance(getattr(g, '_boot_frames', None), list))
    finally:
        held.clear()
        ts.TABLE_CACHE_MAX_SINGLE = s1
        ts.TABLE_CACHE_MAX_TOTAL = s2
        ts.release_table_cache()
        gc.collect()


def main():
    print('P. 判据本身')
    predicate()
    print('A. 正向：修复后的真实行为')
    forward()
    print('B. 反向验证：中和修复')
    reverse()
    print('\n结果：%s（%d 项通过）' % (
        '全部通过' if not _FAILS else '%d 项失败' % len(_FAILS), _OK[0]))
    if _FAILS:
        for m in _FAILS:
            print('  · 失败：', m)
        sys.exit(1)


if __name__ == '__main__':
    main()
