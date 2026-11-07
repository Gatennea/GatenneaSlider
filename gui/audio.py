"""音效与背景音乐管理（AudioManager）。

照 docs/ui/前端動效優化計劃.md §S5 實作。素材由用戶提供，統一放在專案根目錄
`assets/audio/` 下，再分兩個子目錄：
- `assets/audio/sound/`  —— 一次性音效（slide / fail / solved / click / keyboard）
- `assets/audio/music/`  —— 背景音樂（bgm）

檔名規則（素材命名不必遷就槽位）：
- bgm  ：`music/` 下 `bgm.*`；沒有就取該目錄第一個音訊檔。
- slide：`sound/` 下所有 `slide*.*`，載入後輪換播放（S5-2 多樣本防識破，
  例如 slide1.wav … slide4.wav）；完全沒有才退回單一 `slide.*`。
- fail / solved：`sound/` 下 `fail.*` / `solved.*`；`solved` 也認別名 `cheer.*`。
  都沒有則靜默 no-op。
- click / keyboard：`sound/` 下 `click.*` / `keyboard.*`，是**獨立槽位**（鼠標點擊 /
  鍵盤事件），不是 fail 的別名。觸發點：`handle_events` 的全局左鍵、KEYDOWN
  （移動鍵跳過，避免和摩擦聲疊）。
副檔名任取 `.ogg` / `.wav` / `.mp3` 之一。

設計約束（agents.md §4 打包鐵律）：
- 無素材時所有播放靜默 no-op，不報錯、不卡啟動。
- 無頭環境（無 pygame.mixer / 無聲卡 / SDL_AUDIODRIVER=dummy）整個模組 try 跳過，
  絕不拖垮啟動或渲染。
- 音量設定以 0..100 整數在 config / settings 之間傳遞，內部歸一成 0..1 給 mixer。
- 資源路徑解析與 GUI._gui_get_resource_path 同邏輯：開發模式走專案根，
  打包後走 sys._MEIPASS（--onefile / --onedir 都相容）。

api 概要：
- AudioManager(base_dir=None)
- load_all()                      掃 assets/audio/{sound,music} 載入已有素材
- sync_settings(..., slot_flags=None)  GUI 一次推送全部開關、音量與逐項槽位開關
- slot_status() / bgm_detail()    設置頁「音效一覽」用：逐項開關狀態與素材名
- preview(slot)                   試聽（无视开关与总静音）
- play_fail() / play_solved() / play_click() / play_keyboard()
                                  一次性音效（失敗 / 復原 / 鼠標點擊 / 鍵盤按鍵）
- play_slide(distance=None, duration_ms=None)
                                  滑動摩擦聲：以 slide 樣本的「頻譜形狀」為音色，
                                  用平穩帶限噪聲合成，長度貼合本次動畫；速度只調
                                  音量（慢=輕）與低通截止（慢=悶），絕不循環離散爆發
- play_bgm() / stop_bgm()        背景音樂迴圈（mixer.music 串流，不把素材常駐記憶體）

滑動聲的硬要求（使用者 2026-11-07）：
1. **只要滑動動畫要播，就得有聲**——音效在動畫啟動後才發，跟畫面同步；
2. **長度貼合動畫**——合成出的摩擦聲長度 = 本次動畫時長，過程連續不中斷；
3. **越慢越輕、越慢越悶**——「就像魔方一樣，滑動越慢聲音越小」（使用者二次
   糾正）：慢速動畫音量明顯變低、低通截止也調低（悶），快則亮而響；
4. **絕不循環離散爆發**——樣本本身是帶 attack 的短爆發（內部就有數十個峰），
   直接循環 = 一次滑動聽成「很多回快速音效」。本作法把樣本「頻譜形狀」烙印到
   一段平穩噪聲上（保留樣本音色、但幅度恆穩），再按速度做低通與音量，得到
   連續摩擦聲；慢速下的包絡峰數 ≈ 0（已用程序化指標驗證）。
"""

import os
import random
import sys

import pygame

try:                        # numpy 只用在「時長貼合」；沒裝就退回原樣本直放
    import numpy as _np
except Exception:           # pragma: no cover - 環境缺 numpy 時靜默降級
    _np = None

_EXTS = ('.ogg', '.wav', '.mp3')

# 外部資源根目錄：音效在 assets/audio/sound/，背景樂在 assets/audio/music/
_AUDIO_ROOT = 'assets/audio'

_BGM_BASE = 'bgm'                       # music/ 下的優先檔名（無則取第一個音訊檔）
_SLIDE_PREFIX = 'slide'                 # sound/ 下所有 slide*.* 做輪換
_ONE_SHOT_SLOTS = ('fail', 'solved', 'click', 'keyboard')    # sound/ 下精確檔名
# 槽位名之外的常用別名：素材常按「聲音內容」命名，按順序認。
# ⚠️ click / keyboard 是**獨立槽位**（鼠標點擊 / 鍵盤事件），不是 fail 的別名；
#    fail 素材用戶還在找，找到前 fail 保持靜音。
_ONE_SHOT_ALIASES = {
    'solved': ('solved', 'cheer'),
}

# ---- 槽位表：設定頁「音效一覽」直接讀這裡，新增一類音效只需改這一處 ----
# (鍵, 名稱, 說明)；順序就是設置頁列出的順序。
SLOT_SPECS = (
    ('slide',    '滑动摩擦', '拖动 / 键盘移动 / 打乱时的摩擦声（取样本音色合成，长度贴合动画，越慢越轻越闷）'),
    ('fail',     '滑动失败', '拖拽被拒（走不通 / 没缝隙）时的短提示音'),
    ('solved',   '复原',     '拼好复原时播放'),
    ('click',    '鼠标点击', '任意左键点击：棋盘、按钮、菜单、开关、对话框'),
    ('keyboard', '键盘按键', '按键事件；移动键只出滑动摩擦声，不叠按键声'),
)
SLOT_KEYS = tuple(k for k, _l, _d in SLOT_SPECS)
SLOT_LABELS = {k: l for k, l, _d in SLOT_SPECS}
SLOT_HINTS = {k: d for k, _l, d in SLOT_SPECS}
# 槽位 → GUI 上的布林屬性名（config / HTTP 白名單同名）
SLOT_SETTING_KEYS = {k: f'sfx_{k}_enabled' for k in SLOT_KEYS}

# 預設音量（0..1）；config / settings 以 0..100 整數傳入，預設調低（S5-1）
_DEFAULT_SFX_VOLUME = 0.7
_DEFAULT_MUSIC_VOLUME = 0.5

# 摩擦聲連播節流（毫秒）：只防「一次操作被重複觸發」抖出雙擊，正常連按不該被吞
_SLIDE_MIN_GAP_MS = 30
# 點擊 / 按鍵聲的節流：只防同一事件被派發兩次，正常連點連打不吞
_CLICK_MIN_GAP_MS = 25
_KEY_MIN_GAP_MS = 15

# 滑動聲：頻譜烙印（見檔頭說明與 _make_friction）
_SLIDE_DEFAULT_MS = 160     # 沒給時長（動畫關閉的瞬時提交）時的摩擦聲長度
_SLIDE_MIN_MS = 60          # 太短聽不出摩擦，直接夾到下限
_SLIDE_MAX_MS = 1200        # 上限＝動畫時長上限 1000ms 再留點餘量
_SLIDE_FADE_MS = 12         # 合成摩擦聲頭尾淡入淡出，避免硬切爆音
_SLIDE_VOL_JITTER = 0.08    # 音量隨機擾動 ±8%
_SLIDE_REF_CPS = 4.0        # 參考滑動速度（格/秒）：達到此速度音量才滿檔
_SLIDE_MIN_SPEED_VOL = 0.15 # 慢速時的音量下限（再慢也留一絲摩擦）
_SLIDE_LP_SLOW_HZ = 1100    # 慢速低通截止：把高頻悶掉 => 不刺耳、聽感更輕
_SLIDE_LP_FAST_HZ = 6500    # 快速低通截止：亮、帶勁
_SLIDE_LP_ORDER = 4         # 頻域低通滾降階數（Butterworth 幅頻響應）
_SLIDE_SPEC_SMOOTH = 8      # 樣本頻譜形狀的平滑窗長（bins）
_SLIDE_CACHE_MAX = 48       # (樣本, 時長桶, 速度桶, 變體) 快取上限
_SLIDE_VARIANTS = 3         # 每桶預備幾條不同噪聲，連按不至於完全一樣
_SLIDE_BUCKET_MS = 25       # 時長分桶粒度
_SLIDE_SPEED_BUCKETS = 8    # 速度分桶數（決定低通截止解析度）

# 專用聲道：0 = 滑動摩擦聲，1 = 背景樂；餘下留給 fail / solved
_MIXER_CHANNELS = 8
_MIXER_RESERVED = 2


def _sample_spectrum(arr):
    """取 slide 樣本的**頻譜形狀**：幅值譜平滑後歸一成均值 1。

    只取「什麼頻率比較多」這種音色資訊，完全丟掉時域包絡（attack / 衰減 /
    離散爆發）。實測四個素材都是短爆發：10ms 窗 RMS 的局部極大值高達
    67~280 個、crest 2~3.8，直接拿去循環或拼接，慢速就會聽成「很多回快速
    音效」。取頻譜形狀才能只保留音色、不保留那一堆峰。
    """
    x = arr.astype(_np.float32)
    mono = x.mean(axis=1) if x.ndim == 2 else x
    shape = _np.abs(_np.fft.rfft(mono))
    shape = _np.convolve(shape,
                         _np.ones(_SLIDE_SPEC_SMOOTH) / _SLIDE_SPEC_SMOOTH,
                         mode='same')
    return (shape / (shape.mean() + 1e-9)).astype(_np.float32)


def _make_friction(spec, target_n, rate, cutoff_hz, channels=1, peak=26000.0):
    """**頻譜烙印**：把樣本音色印到一段平穩白噪聲上，合成任意長度的摩擦聲。

    做法是全程在頻域完成，沒有任何「把短樣本循環／拼接」的動作：
      1. 生成 target_n 點白噪聲（幅度天生平穩、沒有 attack）；
      2. rfft 後乘上插值到目標長度的樣本頻譜形狀 => 帶樣本音色的噪聲；
      3. 再乘 Butterworth 幅頻響應做低通 => 速度慢就悶（不刺耳）、快就亮；
      4. irfft 回時域、峰值歸一、頭尾淡入淡出。

    因為噪聲本身平穩、也沒有循環節，慢速 1000ms 下 10ms 窗 RMS 的局部峰
    實測 ≈ 0（見 `test/_test_slide_audio.py` 的 A7 護欄）。這正是使用者
    2026-11-07 要求的「慢速滑動時音頻不該有很多峰值」。

    返回 (target_n, channels) 的 int16 量級 float，交給呼叫方 clip 後 astype。
    """
    rng = _np.random.default_rng()
    noise = rng.standard_normal(target_n).astype(_np.float32)
    nf = _np.fft.rfft(noise)
    length = nf.shape[0]
    shape = _np.interp(_np.linspace(0.0, spec.shape[0] - 1.0, length),
                       _np.arange(spec.shape[0]), spec).astype(_np.float32)
    freqs = _np.fft.rfftfreq(target_n, 1.0 / rate)
    lp = 1.0 / _np.sqrt(1.0 + (freqs / max(1.0, cutoff_hz))
                        ** (2 * _SLIDE_LP_ORDER))
    out = _np.fft.irfft(nf * shape * lp, n=target_n).astype(_np.float32)
    cur = float(_np.max(_np.abs(out)))
    if cur > 1e-6:
        out *= (peak / cur)
    fade = max(1, min(target_n // 4, int(rate * _SLIDE_FADE_MS / 1000.0)))
    out[:fade] *= _np.linspace(0.0, 1.0, fade, dtype=_np.float32)
    out[-fade:] *= _np.linspace(1.0, 0.0, fade, dtype=_np.float32)
    out = out[:, None] if channels <= 1 else _np.repeat(out[:, None], channels, axis=1)
    return _np.ascontiguousarray(out)


def _audio_resource_path(relative):
    """解析資源路徑，相容開發模式與 PyInstaller 打包（--onefile / --onedir）。"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        # gui/audio.py 在 <root>/gui/，專案根目錄在其上層
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def _default_dirs():
    """回傳 {sfx, music} 兩個絕對目錄（開發模式 / 打包後都正確）。"""
    return {
        'sfx': _audio_resource_path(os.path.join(_AUDIO_ROOT, 'sound')),
        'music': _audio_resource_path(os.path.join(_AUDIO_ROOT, 'music')),
    }


def _is_audio_file(path):
    return (os.path.isfile(path)
            and os.path.splitext(path)[1].lower() in _EXTS)


def _find_in(d, base):
    """在 d 下找 base + 任一副檔名，回傳路徑或 None。"""
    for ext in _EXTS:
        p = os.path.join(d, base + ext)
        if os.path.exists(p):
            return p
    return None


def _list_audio(d):
    """列出 d 下所有音訊檔（依檔名排序，絕對路徑）。目錄不存在回空。"""
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, fn) for fn in os.listdir(d)
        if _is_audio_file(os.path.join(d, fn))
    )


def _list_prefixed(d, prefix):
    """列出 d 下檔名以 prefix 開頭的所有音訊檔。"""
    return [p for p in _list_audio(d)
            if os.path.basename(p).lower().startswith(prefix.lower())]


class AudioManager:
    def __init__(self, base_dir=None):
        self.available = False
        # base_dir 為「assets/audio」根；可由 GUI 覆寫（如打包後的絕對路徑）。
        # 預設：音效在 assets/audio/sound/，背景樂在 assets/audio/music/。
        if base_dir:
            self.sfx_dir = os.path.join(base_dir, 'sound')
            self.music_dir = os.path.join(base_dir, 'music')
        else:
            dirs = _default_dirs()
            self.sfx_dir = dirs['sfx']
            self.music_dir = dirs['music']
        self._sounds = {}            # slot -> pygame.mixer.Sound
        self._slide_samples = []     # slide 多樣本（S5-2），隨機挑選
        self._slide_files = []       # slide 素材路徑（設置頁顯示素材名用）
        self._slot_path = {}         # slot -> 實際載入的素材路徑
        self._slide_idx = -1         # 上一條用過的樣本（只用來避免連兩手同一個）
        self._slide_cache = {}       # (樣本序號, 時長桶, 速度桶) -> 合成摩擦聲
        self._slide_spectra = []     # 每個 slide 樣本的「頻譜形狀」（烙印音色用）
        self._slide_ch = None        # 專用聲道：新一手直接頂掉上一手，不疊音
        # bgm 只記路徑、不預載：播放走 mixer.music 串流（待办清单 §二十.2，
        # 67MB wav 若走 Sound 會整份解進常駐記憶體，實測 +67MB）
        self._bgm_path = None
        # 設定（由 GUI 推送；預設開，音量調低）
        self.sfx_enabled = True
        self.music_enabled = True
        self.muted = False
        self.sfx_volume = _DEFAULT_SFX_VOLUME
        self.music_volume = _DEFAULT_MUSIC_VOLUME
        # 每個槽位自己的開關（設置頁「音效一覽」逐項控制）
        self.slot_enabled = {k: True for k in SLOT_KEYS}
        self._last_click_ms = -10 ** 9
        self._last_key_ms = -10 ** 9
        try:
            pygame.mixer.init()
            self.available = True
            # 滑動聲獨佔聲道 0（新手頂掉舊手、不疊音）；bgm 走 mixer.music
            # 串流，用的是獨立的 music 聲道，不佔這裡的 Channel。
            # 預留 2 條避免一次性音效 snd.play() 隨機搶到聲道 0。
            pygame.mixer.set_num_channels(_MIXER_CHANNELS)
            pygame.mixer.set_reserved(_MIXER_RESERVED)
            self._slide_ch = pygame.mixer.Channel(0)
        except Exception as e:  # 無聲卡 / dummy 驅動 / 未安裝 => 靜默停用
            print(f'[audio] pygame.mixer 不可用，音效停用：{e}')

    # ---- 素材載入 ----
    def _make_sound(self, path):
        try:
            return pygame.mixer.Sound(path)
        except Exception as e:
            print(f'[audio] 載入 {path} 失敗：{e}')
            return None

    def _load_sound(self, slot, path):
        snd = self._make_sound(path)
        if snd is not None:
            self._sounds[slot] = snd

    def load_all(self):
        if not self.available:
            return
        # bgm：music/ 下 bgm.* 優先，否則該目錄第一個音訊檔。
        # 只記路徑不預載——啟動零成本，play_bgm 才開檔串流讀（§二十.2）
        bgm = _find_in(self.music_dir, _BGM_BASE)
        if bgm is None:
            music_files = _list_audio(self.music_dir)
            if music_files:
                bgm = music_files[0]
        self._bgm_path = bgm

        # slide：載入所有 slide*.* 做多樣本輪換；一個都沒有才退回單一 slide.*
        # 同時預算每個樣本的「頻譜形狀」給合成摩擦聲用（見 _sample_spectrum）。
        self._slide_spectra = []
        slide_paths = _list_prefixed(self.sfx_dir, _SLIDE_PREFIX)
        if slide_paths:
            self._slide_files = list(slide_paths)
            self._slide_samples = [
                s for s in (self._make_sound(p) for p in slide_paths)
                if s is not None
            ]
            if self._slide_samples:
                self._sounds['slide'] = self._slide_samples[0]
                self._slot_path['slide'] = slide_paths[0]
                if _np is not None:
                    for snd in self._slide_samples:
                        try:
                            self._slide_spectra.append(
                                _sample_spectrum(pygame.sndarray.array(snd)))
                        except Exception:
                            self._slide_spectra.append(None)
        else:
            one = _find_in(self.sfx_dir, _SLIDE_PREFIX)
            if one is not None:
                self._slide_files = [one]
                self._load_sound('slide', one)
                self._slot_path['slide'] = one
                snd = self._sounds.get('slide')
                if snd is not None and _np is not None:
                    try:
                        self._slide_spectra.append(
                            _sample_spectrum(pygame.sndarray.array(snd)))
                    except Exception:
                        self._slide_spectra.append(None)

        # fail / solved / click / keyboard：槽位名優先，其次常用別名（cheer→solved）
        for slot in _ONE_SHOT_SLOTS:
            for base in _ONE_SHOT_ALIASES.get(slot, (slot,)):
                one = _find_in(self.sfx_dir, base)
                if one is not None:
                    self._load_sound(slot, one)
                    self._slot_path[slot] = one
                    break

    # ---- 設定 ----
    def set_muted(self, b):
        self.muted = bool(b)
        self._apply_music_volume()

    def set_sfx_enabled(self, b):
        self.sfx_enabled = bool(b)

    def set_slot_enabled(self, slot, b):
        """单类音效开关（设置页「音效一览」逐项）。未知槽位忽略。"""
        if slot in self.slot_enabled:
            self.slot_enabled[slot] = bool(b)

    def set_slot_flags(self, flags):
        """一次推送全部槽位开关：{slot: bool}。缺项不改。"""
        if not isinstance(flags, dict):
            return
        for slot, flag in flags.items():
            self.set_slot_enabled(slot, flag)

    def slot_status(self):
        """给设置页「音效一览」用：逐项返回开关键、素材概况。

        返回 [{slot,label,hint,enabled,loaded,detail}]，顺序＝SLOT_SPECS。
        """
        out = []
        for key in SLOT_KEYS:
            files = self._slide_files if key == 'slide' else (
                [self._slot_path[key]] if key in self._slot_path else [])
            if files:
                detail = os.path.basename(files[0])
                if len(files) > 1:
                    detail += f' 等 {len(files)} 个'
            else:
                detail = '缺素材'
            out.append({
                'slot': key,
                'label': SLOT_LABELS[key],
                'hint': SLOT_HINTS[key],
                'enabled': bool(self.slot_enabled.get(key, True)),
                'loaded': bool(files),
                'detail': detail,
            })
        return out

    def bgm_detail(self):
        """背景乐素材名（设置页显示用；没载入返回「缺素材」）。"""
        p = self._bgm_path
        return os.path.basename(p) if p else '缺素材'

    def set_music_enabled(self, b):
        self.music_enabled = bool(b)
        if not self.music_enabled:
            self.stop_bgm()

    @staticmethod
    def _norm(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        if f > 1.0:          # 傳入 0..100 整數 => 歸一成 0..1
            f = f / 100.0
        return max(0.0, min(1.0, f))

    def set_sfx_volume(self, v):
        self.sfx_volume = self._norm(v)

    def set_music_volume(self, v):
        self.music_volume = self._norm(v)
        self._apply_music_volume()

    def sync_settings(self, sfx_enabled=True, music_enabled=True, muted=False,
                      sfx_volume=70, music_volume=50, slot_flags=None):
        """由 GUI 一次推送全部設定。"""
        self.set_sfx_enabled(sfx_enabled)
        self.set_music_enabled(music_enabled)
        self.set_muted(muted)
        self.set_sfx_volume(sfx_volume)
        self.set_music_volume(music_volume)
        if slot_flags is not None:
            self.set_slot_flags(slot_flags)

    def _apply_music_volume(self):
        if self.available and self._bgm_path is not None:
            vol = 0.0 if self.muted else self.music_volume
            try:
                pygame.mixer.music.set_volume(vol)
            except Exception:
                pass

    # ---- 播放 ----
    def _can_play_sfx(self):
        return (self.available and self.sfx_enabled and not self.muted
                and self._sounds)

    def play(self, slot):
        """播放一次性音效（slide / fail / solved / click / keyboard）。"""
        if not self._can_play_sfx():
            return
        if not self.slot_enabled.get(slot, True):
            return
        snd = self._sounds.get(slot)
        if snd is None:
            return
        try:
            snd.set_volume(self.sfx_volume)
            snd.play()
        except Exception as e:
            print(f'[audio] 播放 {slot} 失敗：{e}')

    def play_fail(self):
        self.play('fail')

    def play_solved(self):
        self.play('solved')

    def _play_throttled(self, slot, attr, gap_ms):
        now = pygame.time.get_ticks()
        if now - getattr(self, attr, -10 ** 9) < gap_ms:
            return
        setattr(self, attr, now)
        self.play(slot)

    def play_click(self):
        """鼠标点击声（棋盘 / 按钮 / 开关 / 对话框，全 GUI 一次性挂接）。"""
        self._play_throttled('click', '_last_click_ms', _CLICK_MIN_GAP_MS)

    def play_keyboard(self):
        """键盘按键声（移动键不调它，移动只出滑动摩擦声）。"""
        self._play_throttled('keyboard', '_last_key_ms', _KEY_MIN_GAP_MS)

    def preview(self, slot):
        """设置页「试听」：故意无视开关与总静音——就是要让你听完再决定开不开。

        返回是否真的播出了（缺素材 / 无音频设备时为 False，界面据此提示）。
        """
        if not self.available:
            return False
        if slot == 'slide':
            # 試聽也走合成摩擦聲（中速 400ms），聽感跟遊戲內一致，不是原始短爆發
            snd = self._slide_sound_for(1, 400)
        else:
            snd = self._sounds.get(slot)
        if snd is None:
            return False
        try:
            snd.set_volume(self.sfx_volume)
            snd.play()
            return True
        except Exception as e:
            print(f'[audio] 试听 {slot} 失敗：{e}')
            return False

    # ---- 滑動聲：頻譜烙印合成（見檔頭與 _make_friction）----
    def _slide_target_ms(self, duration_ms):
        """摩擦聲長度＝動畫時長（夾到上下限；不疊抖動，長度必須精準貼合）。"""
        try:
            target = float(duration_ms) if duration_ms else float(_SLIDE_DEFAULT_MS)
        except (TypeError, ValueError):
            target = float(_SLIDE_DEFAULT_MS)
        return int(max(_SLIDE_MIN_MS, min(_SLIDE_MAX_MS, target)))

    @staticmethod
    def _slide_speed_factor(distance, duration_ms):
        """速度係數 0..1：1 格 / 1 秒 ≈ 0.25，1 格 / 160ms ≈ 1.0。"""
        try:
            dist = max(1, int(distance or 1))
        except (TypeError, ValueError):
            dist = 1
        try:
            ms = max(1.0, float(duration_ms or _SLIDE_DEFAULT_MS))
        except (TypeError, ValueError):
            ms = float(_SLIDE_DEFAULT_MS)
        speed = dist / (ms / 1000.0)                     # 格/秒
        return max(0.0, min(1.0, speed / _SLIDE_REF_CPS))

    def _slide_sound_for(self, distance, duration_ms):
        """挑樣本頻譜 + 依速度/時長合成一條連續摩擦聲（帶快取）。"""
        specs = self._slide_spectra
        if not specs or _np is None:
            # 沒 numpy / 沒算到頻譜 => 退回原始樣本直放（至少仍有聲）
            return (random.choice(self._slide_samples) if self._slide_samples
                    else self._sounds.get('slide'))
        init = pygame.mixer.get_init()
        if not init:
            return self._sounds.get('slide')
        rate = init[0]
        channels = init[2] if len(init) > 2 else 1
        target_ms = self._slide_target_ms(duration_ms)
        speed_f = self._slide_speed_factor(distance, target_ms)
        cutoff = (_SLIDE_LP_SLOW_HZ
                  + (_SLIDE_LP_FAST_HZ - _SLIDE_LP_SLOW_HZ) * speed_f)
        # 快取分桶：時長 25ms 一桶、速度 8 檔、每桶數條不同噪聲變體
        ms_bucket = int(round(target_ms / float(_SLIDE_BUCKET_MS)))
        sp_bucket = int(round(speed_f * _SLIDE_SPEED_BUCKETS))
        idx = random.randrange(len(specs))
        if len(specs) > 1 and idx == self._slide_idx:
            idx = (idx + 1) % len(specs)
        self._slide_idx = idx
        key = (idx, ms_bucket, sp_bucket, random.randrange(_SLIDE_VARIANTS))
        hit = self._slide_cache.get(key)
        if hit is not None:
            return hit
        fallback = (self._slide_samples[idx] if idx < len(self._slide_samples)
                    else self._sounds.get('slide'))
        spec = specs[idx]
        if spec is None:
            return fallback
        target_n = max(1, int(rate * target_ms / 1000.0))
        try:
            # 慢速（長聲）再額外壓低峰值：長 + 悶 + 輕三管齊下
            peak = 26000.0 * max(0.6, min(1.0, 500.0 / target_ms))
            out = _make_friction(spec, target_n, rate, cutoff, channels, peak)
            snd = pygame.sndarray.make_sound(
                _np.clip(out, -32768.0, 32767.0).astype(_np.int16))
        except Exception as e:
            print(f'[audio] 合成摩擦聲失敗（退回原樣本）：{e}')
            return fallback
        if len(self._slide_cache) >= _SLIDE_CACHE_MAX:
            self._slide_cache.clear()
        self._slide_cache[key] = snd
        return snd

    def _slide_volume(self, distance, duration_ms=None):
        """音量 = 距離基準 × 速度係數 × 隨機擾動。

        速度係數就是「就像魔方一樣，滑動越慢聲音越小」：動畫被拉長（慢速檔）
        時摩擦聲同時變輕，而不是把同一個聲音硬撐滿整段動畫來冒充「一直在滑」。
        距離只決定 1 格 / 多格的基準差。
        """
        try:
            dist = max(1, int(distance or 1))
        except (TypeError, ValueError):
            dist = 1
        base = min(1.0, 0.8 + 0.1 * (dist - 1))
        ms = self._slide_target_ms(duration_ms)
        speed_f = max(_SLIDE_MIN_SPEED_VOL,
                      self._slide_speed_factor(dist, ms))
        vol = self.sfx_volume * base * speed_f
        vol *= random.uniform(1.0 - _SLIDE_VOL_JITTER, 1.0 + _SLIDE_VOL_JITTER)
        return max(0.0, min(1.0, vol))

    def play_slide(self, distance=None, duration_ms=None):
        """滑動摩擦聲：長度貼合本次動畫（見檔頭四條硬要求）。

        distance    本次滑動格數（與時長一起換算速度 → 音量 / 低通截止）。
        duration_ms 本次滑動動畫的實際時長；呼叫方應在動畫時長定稿後再傳
                    （拖拽接續會把時長按剩餘比例縮短）。省略則用預設短音。
        新一手直接頂掉上一手（專用聲道），所以連按不會疊成一團；同一手
        重複觸發只認第一次（_SLIDE_MIN_GAP_MS）。
        """
        if not self._can_play_sfx():
            return
        if not self.slot_enabled.get('slide', True):
            return
        now = pygame.time.get_ticks()
        if now - getattr(self, '_last_slide_ms', -10 ** 9) < _SLIDE_MIN_GAP_MS:
            return
        target_ms = self._slide_target_ms(duration_ms)
        snd = self._slide_sound_for(distance, target_ms)
        if snd is None:
            return
        self._last_slide_ms = now
        vol = self._slide_volume(distance, target_ms)
        try:
            ch = self._slide_ch
            if ch is not None:
                ch.set_volume(vol)
                ch.play(snd)
            else:
                snd.set_volume(vol)
                snd.play()
        except Exception as e:
            print(f'[audio] 播放 slide 失敗：{e}')

    def play_bgm(self, loop=True):
        if not (self.available and self.music_enabled and not self.muted):
            return
        if self._bgm_path is None:
            return
        try:
            # 已在播就別重開頭：設定每改一次都會 sync，重播會一直跳回開頭
            if pygame.mixer.music.get_busy():
                return
            # 串流播放：每次啟動都 load（開檔讀檔頭，不吃整份記憶體）；
            # 停播後重 load 也保證各 pygame 版本行為一致
            pygame.mixer.music.load(self._bgm_path)
            pygame.mixer.music.set_volume(self.music_volume)
            pygame.mixer.music.play(-1 if loop else 0)
        except Exception as e:
            print(f'[audio] 播放 bgm 失敗：{e}')

    def stop_bgm(self):
        if not self.available:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
