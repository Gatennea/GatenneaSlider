# -*- coding: utf-8 -*-
"""无头验证：滑动摩擦声「跟着动画走」——每手都出声、长度贴合、慢速无爆发峰。

背景（使用者 2026-11-07 反复反馈，本文件守的就是这几条）
========================================================
  1. 声音跟动画脱节：素材只有 70~165ms，动画默认 300ms、最长 1000ms，
     一步还没滑完声音就没了；连按又叠成一团。
  2. 慢速「好像把一個音效快速播放了很多次」：素材本身是帶 attack 的短爆發
     （實測 10ms 窗 RMS 的局部峰 slide1 有 67 個、slide4 有 280 個），
     早期版本把這些爆發**循環／拼接**去撐長動畫，慢速自然聽成很多下。
  3. 慢速刺耳、而且「聲音根本不小」。
  4. 打亂演示 / 無限打亂也要出聲（使用者並沒要求靜音）。

修法（頻譜烙印，見 gui/audio.py::_make_friction）：只取 slide 樣本的**頻譜形狀**
給一段平穩白噪聲上色，全程不循環、不拼接任何時域爆發；頻域順手做低通
（慢＝悶、快＝亮），頭尾淡入淡出，長度精準等於動畫時長。播放點仍在
start_animation() 之後，滑動聲獨佔一條聲道，新手頂掉舊手。

護欄
====
  A1~A3 時長貼合：60/120/300/600/1000ms 請求 → 合成聲長度誤差 ≤ 12ms
  A4    慢速長聲沒有塌掉的靜音縫（逐 100ms 窗 RMS 都不塌）
  A5    不是整段樣本周期重複（相隔一個樣本長的兩段波形相似度低）
  A6    滑得越慢越輕（1000ms 音量明顯低於 160ms；峰值也隨時長壓低）
  A7 ★慢速沒有「很多峰值」：1000ms 合成聲 10ms 窗 RMS 的爆發數 ≤ 3；
       A7a 先以「把原始樣本整段循環拼 1000ms」做對照組，確認指標確實數得出
       十幾個爆發（證明不是恆真），A7b 再要求合成聲遠少於它——本輪核心驗收點
  A8    慢速比快速悶（>3kHz 高頻佔比明顯更低），治「刺耳」
  B1    時長不帶抖動、精準貼合動畫（同一入參恆等）
  B2    音量擾動存在且不越界
  B3    樣本隨機挑、不連兩手同一個
  C1    普通移动：动画启动后出声，时长＝animation_duration
  C2    动画关闭（瞬时提交）：一样出声，用短促默认长度
  C3    拖拽接续：时长跟着「缩短后的」动画走，不能还用原值
  C4/C5 撤销 / 重做：也是整组沿缝滑动 → 一样出声
  C6    宏播放路径静态引用 _play_slide_sound（防未来漏接）
  D1    打乱演示回放每一步都出声
  D2    无限打乱每一步都出声（无静音拦截）
  D2b   session._infinite_shuffle_step 静态接线检查（防漏接）
  E1    新手顶掉旧手：同一条声道，不排队叠音
  F1/F2 solved 认别名 cheer；click / keyboard 是独立槽位（不冒充 fail/solved）
  G1~G3 槽位表 / slot_status（五项、开关键、素材概况、缺素材标注）
  G4/G5 逐项开关真拦得住；试听无视逐项开关、总开关与静音
  G6~G8 click/keyboard 的挂接点存在；移动键不出按键声（只留摩擦声）

执行：D:/python/python.exe -u test/_test_slide_audio.py
"""
import inspect
import os
import queue
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402
import numpy as _np  # noqa: E402

import gui.audio as A  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


# ================================================================ A/B：AudioManager
mgr = A.AudioManager()
mgr.load_all()
check('0a 音效可用且载入到 slide 样本', mgr.available and len(mgr._slide_samples) >= 1,
      f"available={mgr.available} samples={len(mgr._slide_samples)}")

if mgr.available and mgr._slide_samples:
    _rate0 = (pygame.mixer.get_init() or (44100,))[0]

    def _snd_arr(snd):
        a = pygame.sndarray.array(snd).astype('float32')
        return a.mean(axis=1) if a.ndim == 2 else a

    def _env(a, ms=10):
        w = max(1, int(_rate0 * ms / 1000.0))
        n = (len(a) // w) * w
        return _np.sqrt((a[:n].reshape(-1, w) ** 2).mean(1))

    def _local_peaks(env, thr=1.3):
        med = float(_np.median(env)) + 1e-9
        return sum(1 for i in range(1, len(env) - 1)
                   if env[i] > env[i - 1] and env[i] > env[i + 1]
                   and env[i] > thr * med)

    def _hf_frac(a):
        spec = _np.abs(_np.fft.rfft(a))
        fr = _np.fft.rfftfreq(len(a), 1.0 / _rate0)
        hi = spec[fr > 3000].sum()
        lo = spec[fr <= 3000].sum()
        return float(hi / (hi + lo + 1e-9))

    # ---- A1~A3 时长贴合 ----
    bad = []
    for target in (60, 120, 300, 600, 1000):
        snd = mgr._slide_sound_for(1, mgr._slide_target_ms(target))
        got = snd.get_length() * 1000.0
        if abs(got - target) > 12:
            bad.append((target, round(got)))
    check('A1/A2/A3 请求 60/120/300/600/1000ms 都合成出长度相符的摩擦声',
          not bad, str(bad))

    slow = _snd_arr(mgr._slide_sound_for(1, 1000))
    fast = _snd_arr(mgr._slide_sound_for(1, 160))

    # A4：慢速长声没有中途静音缝
    win = max(1, int(_rate0 * 0.1))
    rms = [float((slow[i:i + win] ** 2).mean() ** 0.5)
           for i in range(0, slow.shape[0] - win, win)]
    rms = [r for r in rms if r == r]
    med = sorted(rms)[len(rms) // 2] if rms else 0.0
    check('A4 慢速长声 1s 内没有塌掉的静音缝',
          bool(rms) and med > 0 and min(rms) > 0.08 * med,
          f'windows={len(rms)} min/med={min(rms) / med:.3f}' if med else 'no rms')

    # A5：不是整段样本周期重复
    _n0 = int(round(mgr._slide_samples[0].get_length() * _rate0))
    _a5, _b5 = slow[:max(1, _n0)], slow[_n0:_n0 + max(1, _n0)]
    if _a5.shape[0] > 8 and _b5.shape[0] == _a5.shape[0]:
        _dot = float((_a5 * _b5).sum())
        _den = float((_a5 ** 2).sum() ** 0.5 * (_b5 ** 2).sum() ** 0.5) or 1.0
        _corr = abs(_dot) / _den
        check('A5 慢速声不是整段样本循环（隔一个样本长的两段不相像）',
              _corr < 0.5, f'corr={_corr:.3f}')
    else:
        print('   [skip] 样本太短，A5 跳过')

    # A6：越慢越轻
    _vs = sorted(mgr._slide_volume(1, 1000) for _ in range(41))[20]
    _vf = sorted(mgr._slide_volume(1, 160) for _ in range(41))[20]
    check('A6 滑得越慢越轻（1000ms 音量明显低于 160ms）',
          _vf > 0 and _vs < _vf * 0.6, f'slow={_vs:.3f} fast={_vf:.3f}')

    # ★ A7：慢速「不会有很多峰值」——本轮用户点名要验证的硬指标。
    #   用 10ms 窗 RMS 数「明顯高於中位數的局部極大值」＝可數的響度爆發。
    #   對照組故意把原始短爆發樣本整段循環拼到 1000ms（正是舊版「一次滑動
    #   播放了很多回快速音效」的成因）：指標必須先抓到它，才證明不是恆真斷言。
    def _bursts(a, thr=1.5):
        return _local_peaks(_env(a), thr)

    _raw0 = _snd_arr(mgr._slide_samples[0])
    _n1000 = int(_rate0 * 1.0)
    _ctrl = _np.tile(_raw0, (_n1000 + len(_raw0) - 1) // len(_raw0))[:_n1000]
    _ctrl_b, _slow_b = _bursts(_ctrl), _bursts(slow)
    check('A7a 对照组（整段循环拼 1000ms）确实数得出很多爆发，指标不是恒真',
          _ctrl_b >= 10, f'control_bursts={_ctrl_b}')
    check('A7b 慢速 1000ms 合成摩擦声没有「很多回快速音效」（爆发数 ≤3 且远少于对照组）',
          _slow_b <= 3 and _slow_b < _ctrl_b * 0.25,
          f'slow_bursts={_slow_b} control_bursts={_ctrl_b}')

    # A8：慢速比快速闷（高频占比显著更低），治「刺耳」
    _hf_slow, _hf_fast = _hf_frac(slow), _hf_frac(fast)
    check('A8 慢速比快速闷（>3kHz 高频占比显著更低）',
          _hf_slow < _hf_fast * 0.6,
          f'slow_hf={_hf_slow:.3f} fast_hf={_hf_fast:.3f}')

    # ---- B. 时长不抖动 / 音量扰动 / 样本轮换 ----
    targets = {mgr._slide_target_ms(300) for _ in range(20)}
    check('B1 摩擦声长度精准贴合动画（同一入参恒等、不带抖动）',
          targets == {300}, f'{sorted(targets)}')

    vols = [mgr._slide_volume(1) for _ in range(40)]
    base = mgr.sfx_volume * 0.8
    spread = max(vols) - min(vols)
    check('B2 音量带随机扰动且不越界',
          spread > 0.005 and all(0.0 <= v <= min(1.0, base * 1.09) + 1e-9 for v in vols),
          f'spread={spread:.3f} min={min(vols):.3f} max={max(vols):.3f}')

    if len(mgr._slide_samples) > 1:
        seq = []
        for _ in range(24):
            mgr._slide_sound_for(1, 300)
            seq.append(mgr._slide_idx)
        repeat = any(a == b for a, b in zip(seq, seq[1:]))
        check('B3 样本随机挑选且不连两手同一个', not repeat and len(set(seq)) > 1,
              f'distinct={sorted(set(seq))}')

    # ---- E. 声道不叠 ----
    if mgr._slide_ch is not None:
        mgr.play_slide(1, duration_ms=300)
        pygame.time.wait(60)
        mgr.play_slide(1, duration_ms=600)
        pygame.time.wait(30)
        q = mgr._slide_ch.get_queue()
        cur = mgr._slide_ch.get_sound()
        cur_ms = cur.get_length() * 1000.0 if cur is not None else -1
        check('E1 新手顶掉旧手（同一声道、无排队叠音）',
              not q and 590 <= cur_ms <= 610,
              f'queue={q} current={round(cur_ms)}ms')
elif not mgr.available:
    print('   [skip] 无声卡/无 mixer：A/B/E 跳过')

# ---- F. 槽位别名：solved 也認 cheer.*（click / keyboard 是输入事件音，不挂槽位）----
import shutil  # noqa: E402
import tempfile  # noqa: E402

_src_sound = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'assets', 'audio', 'sound')
if mgr.available:
    _alias_pairs = (('cheer', 'solved'),)
    _found = [(n, s) for n, s in _alias_pairs
              if os.path.exists(os.path.join(_src_sound, n + '.ogg'))
              or os.path.exists(os.path.join(_src_sound, n + '.mp3'))]
    if _found:
        _tmp = tempfile.mkdtemp(prefix='gs_audio_alias_')
        try:
            _sd = os.path.join(_tmp, 'sound')
            os.makedirs(_sd, exist_ok=True)
            for _name, _slot in _found:
                for _ext in ('.ogg', '.mp3', '.wav'):
                    _p = os.path.join(_src_sound, _name + _ext)
                    if os.path.exists(_p):
                        shutil.copy2(_p, os.path.join(_sd, _name + _ext))
                        break
            _m2 = A.AudioManager(_tmp)
            _m2.load_all()
            _miss = [s for _n, s in _found if s not in _m2._sounds]
            check('F1 别名素材能认到槽位（cheer→solved）',
                  not _miss, f'missing={_miss} loaded={sorted(_m2._sounds)}')
            _m2.stop_bgm()
        finally:
            shutil.rmtree(_tmp, ignore_errors=True)
    else:
        print('   [skip] 素材里没有 cheer，F1 跳过')

# F2：click / keyboard 是**独立槽位**（鼠标点击 / 键盘事件），不冒充 fail / solved
if mgr.available and os.path.isdir(_src_sound):
    _tmp2 = tempfile.mkdtemp(prefix='gs_audio_noslot_')
    try:
        _sd2 = os.path.join(_tmp2, 'sound')
        os.makedirs(_sd2, exist_ok=True)
        _copied = []
        for _n in ('click', 'keyboard'):
            for _ext in ('.ogg', '.mp3', '.wav'):
                _p = os.path.join(_src_sound, _n + _ext)
                if os.path.exists(_p):
                    shutil.copy2(_p, os.path.join(_sd2, _n + _ext))
                    _copied.append(_n)
                    break
        if _copied:
            _m3 = A.AudioManager(_tmp2)
            _m3.load_all()
            check('F2 click / keyboard 各自成独立槽位（不冒充 fail / solved）',
                  set(_m3._sounds) == set(_copied)
                  and 'fail' not in _m3._sounds and 'solved' not in _m3._sounds,
                  f'loaded={sorted(_m3._sounds)} copied={_copied}')
            _m3.stop_bgm()
        else:
            print('   [skip] 素材里没有 click/keyboard，F2 跳过')
    finally:
        shutil.rmtree(_tmp2, ignore_errors=True)


# ================================================================ G：音效一览的逐项开关
class _FakeSnd:
    def __init__(self):
        self.plays = 0
        self.vol = None

    def set_volume(self, v):
        self.vol = v

    def play(self, *a, **k):
        self.plays += 1


print("\n--- G. 音效一览（逐项开关 / 试听）---")
check('G1 槽位表就是设置页要列的五项',
      list(A.SLOT_KEYS) == ['slide', 'fail', 'solved', 'click', 'keyboard'],
      str(list(A.SLOT_KEYS)))
_status = mgr.slot_status()
check('G2 slot_status 五项齐全、带开关键与素材概况',
      [r['slot'] for r in _status] == list(A.SLOT_KEYS)
      and all('enabled' in r and 'detail' in r for r in _status),
      str([(r['slot'], r['detail']) for r in _status]))
check('G3 有素材的项标 loaded、没素材的标「缺素材」',
      all((r['loaded'] and r['detail'] != '缺素材') or
          ((not r['loaded']) and r['detail'] == '缺素材') for r in _status),
      str([(r['slot'], r['loaded']) for r in _status]))

_fake = _FakeSnd()
_old_click_snd = mgr._sounds.get('click')
if mgr.available:
    mgr._sounds['click'] = _fake
    try:
        mgr.set_slot_enabled('click', False)
        mgr.play_click()
        _off = _fake.plays
        mgr.set_slot_enabled('click', True)
        mgr._last_click_ms = -10 ** 9          # 清节流
        mgr.play_click()
        _on = _fake.plays
        check('G4 逐项开关真的拦得住（关→不出声，开→出声）',
              _off == 0 and _on == 1, f'off={_off} on={_on}')

        # 试听无视开关与总静音（就是要让你听完再决定开不开）
        mgr.set_slot_enabled('click', False)
        mgr.set_sfx_enabled(False)
        mgr.set_muted(True)
        _before = _fake.plays
        _ok = mgr.preview('click')
        check('G5 试听无视逐项开关 / 总静音 / 静音闸门',
              bool(_ok) and _fake.plays == _before + 1,
              f'ok={_ok} plays={_fake.plays}')
        mgr.set_sfx_enabled(True)
        mgr.set_muted(False)
        mgr.set_slot_enabled('click', True)
    finally:
        if _old_click_snd is None:
            mgr._sounds.pop('click', None)
        else:
            mgr._sounds['click'] = _old_click_snd
else:
    print('   [skip] 无声卡/无 mixer：G4/G5 跳过')

# 事件层：全局点击 / 按键挂接点（防「开关做了但没人触发」）
_ev_src = inspect.getsource(SliderGUI.handle_events)
check('G6 左键点击挂到了全局点击声',
      '_play_click_sound()' in _ev_src and 'spawn_click_feedback' in _ev_src, '')
check('G7 KEYDOWN 挂到了键盘按键声',
      '_play_keyboard_sound(' in _ev_src, '')
_g = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue())
_g.tutorial_active = False
_g.tut_show_prompt = False
if getattr(_g, 'audio', None) is not None:
    _calls_kb = []
    _orig_kb = _g.audio.play_keyboard
    _g.audio.play_keyboard = lambda: _calls_kb.append(1)
    try:
        _g._play_keyboard_sound(pygame.K_LEFT)       # 移动键：交给滑动摩擦声
        _move_only = len(_calls_kb)
        _g._play_keyboard_sound(pygame.K_SPACE)      # 非移动键：出按键声
        _typed = len(_calls_kb)
    finally:
        _g.audio.play_keyboard = _orig_kb
    check('G8 移动键不出按键声（只留滑动摩擦声），其它键出',
          _move_only == 0 and _typed == 1, f'move={_move_only} other={_typed}')
else:
    print('   [skip] 音频模块不可用：G8 跳过')


# ================================================================ C/D：触发点
SIGN = {'w': -1, 'a': -1, 's': 1, 'd': 1}


def boot(anim=True, dur=300):
    g = SliderGUI(m=4, n=4, step=2, cmd_queue=queue.Queue())
    g.tutorial_active = False
    g.tut_show_prompt = False
    g.shuffle_puzzle(confirm=False)
    g._shuffle_demo_playing = False
    g._restore_anim_duration()
    g.animation_duration = dur
    g.animation_enabled = anim
    return g


def spy(g):
    calls = []
    g.audio.play_slide = lambda distance=None, duration_ms=None: calls.append(
        (distance, duration_ms))
    return calls


def legal_move(g, drag_frac=None):
    """走一手合法滑动（方向由缝隙朝向决定）；drag_frac 模拟拖拽已跟随的格数。"""
    gt = g.selected_gap[0] if g.selected_gap else None
    if gt is None:
        return None
    for d in (('w', 's') if gt == 'v' else ('a', 'd')):
        if drag_frac:
            s = SIGN[d] * drag_frac
            g._drag_anim_origin = ((s, 0) if gt == 'v' else (0, s))
        if g.move_selected_blocks(d):
            return d
        if drag_frac:
            g._drag_anim_origin = None
    return None


def boot_with_move(anim=True, dur=300, drag_frac=None, tries=15):
    """建局并走成一手，返回 (gui, 本次 play_slide 记录, move_info)。"""
    for _ in range(tries):
        g = boot(anim=anim, dur=dur)
        calls = spy(g)
        d = legal_move(g, drag_frac=drag_frac)
        if d:
            mi = dict(g._pending_move_info or {})
            return g, calls, mi
    return None, [], {}


# ---- C1 普通移动 ----
g, calls, _mi = boot_with_move()
check('C1 普通移动：动画启动后出声，时长＝animation_duration',
      bool(calls) and g.animating and abs(calls[-1][1] - g.animation_duration) <= 1,
      f'calls={calls} duration={g.animation_duration}')

# ---- C2 动画关闭 ----
g2, calls2, _ = boot_with_move(anim=False)
check('C2 动画关闭时一样出声（短促默认长度）',
      bool(calls2) and calls2[-1][1] == SliderGUI.SLIDE_INSTANT_MS,
      f'calls={calls2} expect={SliderGUI.SLIDE_INSTANT_MS}')

# ---- C3 拖拽接续：时长取缩短后的值 ----
g3, calls3, _ = boot_with_move(drag_frac=0.6)
check('C3 拖拽接续：时长跟着缩短后的动画走（< 原值）',
      bool(calls3) and calls3[-1][1] < 300 and calls3[-1][1] == g3.animation_duration,
      f'calls={calls3} anim={g3.animation_duration}')

# ---- C4/C5 撤销 / 重做 ----
if _mi:
    g.commit_animation()          # 落位，块停在终态（B）
    undo_calls = spy(g)
    ok_undo = g._start_undo_redo_animation(dict(_mi), is_undo=True)
    check('C4 撤销动画也出声', ok_undo and bool(undo_calls), f'calls={undo_calls}')
    # 重做要求盘面已在动作前的状态（A）：撤销动画只动画不落位，这里手动摆回
    # A 再测（等价于真实流程里 undo 提交之后的局面）。
    g._reset_anim_state()
    _delta = g._move_delta(dict(_mi))
    _post = [(p[0] + _delta[0], p[1] + _delta[1]) for p in _mi['moved_positions']]
    _blks = g._find_blocks_at_positions(_post)
    if len(_blks) == len(_mi['moved_positions']):
        for _b, _p in zip(_blks, _mi['moved_positions']):
            _b.location = list(_p)
        redo_calls = spy(g)
        ok_redo = g._start_undo_redo_animation(dict(_mi), is_undo=False)
        check('C5 重做动画也出声', ok_redo and bool(redo_calls),
              f'calls={redo_calls} ok={ok_redo}')
    else:
        check('C5 重做动画也出声', False,
              f'摆不回动作前状态：{len(_blks)}/{len(_mi["moved_positions"])}')
else:
    check('C4 撤销动画也出声', False, '建局失败，无法验证')
    check('C5 重做动画也出声', False, '建局失败，无法验证')

# ---- C6 宏播放路径静态接线 ----
try:
    macro_src = inspect.getsource(SliderGUI._execute_next_macro_step)
except (TypeError, OSError):
    macro_src = ''
check('C6 宏播放路径引用了 _play_slide_sound（防漏接）',
      '_play_slide_sound' in macro_src, '')

# ---- D1 打乱演示每一步都出声 ----
g4 = boot()
g4._shuffle_demo_playing = True
calls4 = spy(g4)
g4._play_slide_sound(1, duration_ms=200)
check('D1 打乱演示不再静音（每步出声）', bool(calls4), f'calls={calls4}')

# ---- D2 无限打乱每一步都出声 ----
g5 = boot()
g5._infinite_shuffle_step_playing = True
calls5 = spy(g5)
g5._play_slide_sound(1, duration_ms=200)
check('D2 无限打乱不再静音（每步出声）', bool(calls5), f'calls={calls5}')

# ---- D1b/D2b 静态接线：两条播放路径真的调了 _play_slide_sound ----
try:
    _demo_src = inspect.getsource(SliderGUI._play_next_shuffle_record)
    _inf_src = inspect.getsource(SliderGUI._infinite_shuffle_step)
except (TypeError, OSError):
    _demo_src, _inf_src = '', ''
check('D1b 打乱演示路径接上 _play_slide_sound（防漏接）',
      '_play_slide_sound(' in _demo_src, '')
check('D2b 无限打乱路径接上 _play_slide_sound（防漏接）',
      '_play_slide_sound(' in _inf_src, '')

print()
if _failures:
    print(f'FAILED {len(_failures)}:')
    for n in _failures:
        print(f'  · {n}')
    sys.exit(1)
print('ALL PASS')
