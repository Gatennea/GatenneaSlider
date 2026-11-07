# -*- coding: utf-8 -*-
"""无头验证：滑动声是「单次魔方转动声」，一次滑动只播一次原始采样。

背景（使用者 2026-11-07 反覆糾正，本文件守的就是這幾條）
========================================================
  1. 素材是**單次魔方轉動聲**（70~165ms 的一次事件音），不是持續摩擦噪聲。
     前九輪把它們撐滿整段動畫：整段循環、粒度拼接、無縫 loop+低通、
     甚至頻譜烙印成平穩白噪聲 —— 最後一種聽成「砂紙打磨聲」，完全不像原採樣。
  2. 慢速「好像把一個音效快速播放了很多次」＝循環造成的，不是素材本身的問題。
  3. 「像魔方一樣，滑動越慢聲音越小」：只調音量。
  4. 打亂演示 / 無限打亂也要出聲（使用者並沒要求靜音）。

修法（工業做法，Unity `PlayOneShot` / `PlayOnceAudio`、Web Audio one-shot）：
`play_slide` 直接播**一次原始 slide 樣本**，不拉伸、不循環、不拼接、不合成；
動畫時長只用來換算速度 → 音量。真實魔方轉一下就是一聲，慢速不必鋪滿 1000ms。
播放點仍在 `start_animation()` 之後，獨佔聲道，新手頂掉舊手。

護欄
====
  A1    實際播出的 Sound 就是原始樣本物件之一（不合成、不改音色）
  A2    播放長度不隨動畫時長變化（1000ms 動畫仍是原來那一下，≤200ms）
  A3    ★「一次滑動不會有很多回」：A3a 對照組（把原始樣本整段循環拼 1000ms）
        確實數得出很多爆發，證明指標不是恆真；A3b 實際播出的聲音爆發數
        不隨動畫變長而增加、遠少於對照組
  A4    滑得越慢越輕（1000ms 音量明顯低於 160ms）
  B1    慢/快動畫播的都是原始樣本，長度一致（時長只進音量計算）
  B2    音量擾動存在且不越界
  B3    樣本隨機挑、不連兩手同一個
  C1    普通移动：动画启动后出声，时长＝animation_duration
  C2    动画关闭（瞬时提交）：一样出声，用短促默认长度
  C3    拖拽接续：时长跟着「缩短后的」动画走，不能还用原值
  C4/C5 撤销 / 重做：也是整组沿缝滑动 → 一样出声
  C6    宏播放路径静态引用 _play_slide_sound（防未来漏接）
  D1    打乱演示回放每一步都出声
  D2    无限打乱每一步都出声（无静音拦截）
  D1b/D2b 两条播放路径静态接线检查（防漏接）
  E1    新手顶掉旧手：同一条声道、无排队叠音，且播的是原始样本
  F1/F2 solved 认别名 cheer；click / keyboard 是独立槽位（不冒充 fail/solved）
  G1~G3 槽位表 / slot_status（五项、开关键、素材概况、缺素材标注）
  G4/G5 逐项开关真拦得住；试听无视逐项开关、总开关与静音
  G6~G8 click/keyboard 的挂接点存在；移动键不出按键声（只留滑动声）

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
    _raws = mgr._slide_samples

    def _snd_arr(snd):
        a = pygame.sndarray.array(snd).astype('float32')
        return a.mean(axis=1) if a.ndim == 2 else a

    def _bursts(a, thr=1.5):
        """10ms 窗 RMS 的明顯局部極大值＝可數的響度爆發（「一回」）。"""
        w = max(1, int(_rate0 * 0.010))
        n = (len(a) // w) * w
        env = _np.sqrt((a[:n].reshape(-1, w) ** 2).mean(1))
        med = float(_np.median(env)) + 1e-9
        return sum(1 for i in range(1, len(env) - 1)
                   if env[i] > env[i - 1] and env[i] > env[i + 1]
                   and env[i] > thr * med)

    def _is_raw(snd):
        return snd is not None and any(snd is r for r in _raws)

    def _played(dur):
        """真正播出去的 Sound（清节流，模擬不同動畫時長各滑一手）。"""
        mgr._last_slide_ms = -10 ** 9
        mgr.play_slide(1, duration_ms=dur)
        return mgr._slide_ch.get_sound() if mgr._slide_ch is not None else None

    # ---- A1：播的就是原始樣本，沒有任何合成 / 替換音色 ----
    picks = [mgr._pick_slide_sample() for _ in range(20)]
    check('A1 每次滑动播的就是原始采样之一（不合成、不改音色）',
          all(_is_raw(p) for p in picks), f'non_raw={sum(not _is_raw(p) for p in picks)}')

    # ---- A2：聲音長度與動畫時長無關（不再「撐滿動畫」）----
    played = {d: _played(d) for d in (160, 300, 600, 1000)}
    lens = {d: (s.get_length() * 1000.0 if s is not None else -1)
            for d, s in played.items()}
    check('A2 声音长度不随动画变长（1000ms 动画仍只播原来那一下，≤200ms）',
          all(_is_raw(s) and 0 < lens[d] <= 200 for d, s in played.items()),
          f'lengths={ {d: round(v) for d, v in lens.items()} }')

    # ---- A3：★一次滑動不會有「很多回」——帶對照組，證明指標不是恆真 ----
    _raw0 = _snd_arr(_raws[0])
    _n1000 = int(_rate0 * 1.0)
    _ctrl = _np.tile(_raw0, (_n1000 + len(_raw0) - 1) // len(_raw0))[:_n1000]
    _ctrl_b = _bursts(_ctrl)
    check('A3a 对照组（把原始样本循环拼到 1000ms）确实数得出很多回，指标不是恒真',
          _ctrl_b >= 10, f'control_bursts={_ctrl_b}')
    _played_b = {d: _bursts(_snd_arr(s)) for d, s in played.items() if s is not None}
    check('A3b 实际播出的仍是「一次」转动声（爆发数不随动画变长、远少于对照组）',
          bool(_played_b) and max(_played_b.values()) <= 6
          and max(_played_b.values()) < _ctrl_b * 0.5,
          f'played_bursts={_played_b} control_bursts={_ctrl_b}')

    # ---- A4：越慢越輕 ----
    _vs = sorted(mgr._slide_volume(1, 1000) for _ in range(41))[20]
    _vf = sorted(mgr._slide_volume(1, 160) for _ in range(41))[20]
    check('A4 滑得越慢越轻（1000ms 音量明显低于 160ms）',
          _vf > 0 and _vs < _vf * 0.6, f'slow={_vs:.3f} fast={_vf:.3f}')

    # ---- B：靜態防回流 / 音量擾動 / 樣本輪換 ----
    _audio_src = inspect.getsource(A)
    _forbidden = [w for w in ('sndarray.make_sound', '_make_friction',
                              '_texture_stretch', '_shape_to_length',
                              'loops=-1') if w in _audio_src]
    check('B1 音频模块里没有任何合成 / 循环 / 拉伸代码（防止再走回头路）',
          not _forbidden, f'forbidden={_forbidden}')

    vols = [mgr._slide_volume(1) for _ in range(40)]
    base = mgr.sfx_volume * 0.8
    spread = max(vols) - min(vols)
    check('B2 音量带随机扰动且不越界',
          spread > 0.005 and all(0.0 <= v <= min(1.0, base * 1.09) + 1e-9 for v in vols),
          f'spread={spread:.3f} min={min(vols):.3f} max={max(vols):.3f}')

    if len(_raws) > 1:
        seq = []
        for _ in range(24):
            seq.append(_raws.index(mgr._pick_slide_sample()))
        repeat = any(a == b for a, b in zip(seq, seq[1:]))
        check('B3 样本随机挑选且不连两手同一个', not repeat and len(set(seq)) > 1,
              f'distinct={sorted(set(seq))}')

    # ---- E. 声道不叠 ----
    if mgr._slide_ch is not None:
        mgr._last_slide_ms = -10 ** 9
        mgr.play_slide(1, duration_ms=300)
        pygame.time.wait(60)
        mgr._last_slide_ms = -10 ** 9
        mgr.play_slide(1, duration_ms=600)
        pygame.time.wait(30)
        q = mgr._slide_ch.get_queue()
        cur = mgr._slide_ch.get_sound()
        cur_ms = cur.get_length() * 1000.0 if cur is not None else -1
        check('E1 新手顶掉旧手（同一声道、无排队叠音，播的仍是原始样本）',
              not q and _is_raw(cur) and 0 < cur_ms <= 200,
              f'queue={q} current={round(cur_ms)}ms raw={_is_raw(cur)}')
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
