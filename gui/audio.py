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
                                  滑動摩擦聲：長度貼合本次動畫（不足則隨機粒度拼貼、
                                  過長則截斷收尾），音量隨滑動速度縮放，樣本 / 音高 /
                                  音量都帶隨機擾動
- play_bgm() / stop_bgm()        背景音樂迴圈

滑動聲的硬要求（使用者 2026-11-07）：
1. **只要滑動動畫要播，就得有聲**——音效在動畫啟動後才發，跟畫面同步；
2. **長度必須貼合動畫**——素材只有 70~165ms，而動畫可長達 1000ms，直接播會
   「一步沒滑完聲音就沒了」；連按又會「疊成一團」。這裡按目標時長現做變體：
   拉伸比 0.55~2.2 用重採樣（變速＝變音高，聽感自然）；超過 2.2 改用**隨機
   粒度拼接**（見 `_texture_stretch`）；低於 0.55 截斷並在尾部 15ms 淡出。
   變體按 (樣本, 20ms 桶) 快取，逐手現算不划算。
3. **越慢越輕**——「就像魔方一樣，滑動越慢聲音越小」（使用者 2026-11-07 二次
   糾正）。音量按滑動速度（格/秒）縮放，慢速動畫不但拉長、還要明顯變輕，
   不能靠把同一個聲音硬撐滿動畫時長來冒充。
4. **禁止整段循環拼接**——舊版把 70ms 樣本原樣首尾相接十幾遍撐到 1000ms，
   聽感是「同一個音效快速播了很多次」（使用者 2026-11-07 實機反饋）。慢速
   只能用打散重組的摩擦質感，不能出現可數的「一下、兩下、三下」。
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
    ('slide',    '滑动摩擦', '拖动 / 键盘移动滑块时的摩擦声（slide1~4 多样本轮换，时长贴合动画）'),
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

# 滑動聲時長貼合（見檔頭說明）
_SLIDE_DEFAULT_MS = 160     # 沒給時長（動畫關閉的瞬時提交）時的摩擦聲長度
_SLIDE_MIN_MS = 60          # 太短聽不出摩擦，直接夾到下限
_SLIDE_MAX_MS = 1200        # 上限＝動畫時長上限 1000ms 再留點餘量
_SLIDE_TILE_ABOVE = 2.2     # 拉伸比超過此值：改用隨機粒度拼接（保音高、不出現循環節）
_SLIDE_TRIM_BELOW = 0.55    # 壓縮比低於此值：改用截斷 + 尾部淡出
_SLIDE_FADE_MS = 15         # 截斷 / 拼接的淡出淡入長度
_SLIDE_FADE_IN_MS = 10      # 每手起播的淡入，避免硬切的爆音
_SLIDE_TAIL_MS = 25         # 变体尾部淡出：刚好在动画结束时收音，不能硬切
_SLIDE_GRAIN_MIN_MS = 45    # 粒度拼接的短粒下限（再短會出顆粒感／咔噠聲）
_SLIDE_GRAIN_MAX_MS = 85    # 短粒上限（再長就聽得出「同一段又來一遍」）
_SLIDE_JITTER = 0.06        # 時長（連帶音高）隨機擾動 ±6%
_SLIDE_VOL_JITTER = 0.08    # 音量隨機擾動 ±8%
_SLIDE_REF_CPS = 3.0        # 參考滑動速度（格/秒）：達到此速度音量才滿檔
_SLIDE_MIN_SPEED_VOL = 0.25  # 慢速時的音量下限（再慢也留一絲摩擦）
_SLIDE_CACHE_MAX = 64       # 变体缓存上限（20ms 一桶；300ms 档约 53KB/条）

# 專用聲道：0 = 滑動摩擦聲，1 = 背景樂；餘下留給 fail / solved
_MIXER_CHANNELS = 8
_MIXER_RESERVED = 2


def _resample(arr, target_n):
    """線性插值重採樣：等同變速播放，音高隨之升降（0.55~2.2 倍內聽感自然）。"""
    src_n = arr.shape[0]
    pos = _np.linspace(0.0, src_n - 1.0, target_n, dtype=_np.float32)
    i0 = _np.floor(pos).astype(_np.int32)
    i1 = _np.minimum(i0 + 1, src_n - 1)
    frac = (pos - i0)[:, None]
    a = arr.astype(_np.float32)
    return a[i0] * (1.0 - frac) + a[i1] * frac


def _texture_stretch(arr, target_n, rate):
    """把短樣本拉成任意長度：**隨機粒度拼接**，不是整段循環。

    舊做法是把整條樣本原樣首尾相接 N 遍。70ms 的樣本撐 1000ms 動畫＝同一個
    音效連響十四下，聽感非常怪（使用者 2026-11-07 實機反饋「好像把一個音效
    快速播放了很多次」）。這裡改成：每段從樣本裡**隨機位置**切 45~85ms 的
    短粒、隨機決定是否倒放，再用等長交叉淡化接上。相鄰兩粒的位置／方向都
    不同，聽感是連續摩擦而不是可數的「一下、兩下、三下」。
    首段仍保留樣本開頭，起手的 attack 不丟，才像「滑了一下」而不是一段噪音。
    """
    x = arr.astype(_np.float32)
    n = x.shape[0]
    if n < 4:
        return x
    fade = max(1, min(n // 4, int(rate * _SLIDE_FADE_MS / 1000.0)))
    g_lo = max(int(rate * _SLIDE_GRAIN_MIN_MS / 1000.0), 2 * fade, 2)
    g_hi = max(int(rate * _SLIDE_GRAIN_MAX_MS / 1000.0), g_lo + 1)
    g_lo = min(g_lo, n)
    g_hi = min(max(g_hi, g_lo), n)
    out = x[:min(n, target_n)].copy()
    last_off = -1
    guard = 0
    while out.shape[0] < target_n and guard < 256:
        guard += 1
        g = random.randint(g_lo, g_hi)
        off = random.randint(0, max(0, n - g))
        if off == last_off and n > g:      # 同一位置連切兩粒＝又能聽出重複
            off = (off + g) % max(1, n - g)
        last_off = off
        piece = x[off:off + g]
        if random.random() < 0.5:
            piece = piece[::-1]
        f = min(fade, out.shape[0], piece.shape[0])
        if f <= 0:
            out = _np.concatenate([out, piece], axis=0)
            continue
        ramp = _np.linspace(0.0, 1.0, f, dtype=_np.float32)[:, None]
        seam = out[-f:] * (1.0 - ramp) + piece[:f] * ramp
        out = _np.concatenate([out[:-f], seam, piece[f:]], axis=0)
    return out[:target_n]


def _trim_faded(arr, target_n, rate):
    """截斷到目標長度，並在尾部做淡出，避免硬切爆音。"""
    out = arr[:target_n].astype(_np.float32).copy()
    k = min(out.shape[0], max(1, int(rate * _SLIDE_FADE_MS / 1000.0)))
    out[-k:] *= _np.linspace(1.0, 0.0, k, dtype=_np.float32)[:, None]
    return out


def _shape_to_length(arr, target_n, rate):
    """把樣本整形到恰好 target_n 個採樣點（三段策略，見檔頭）。"""
    src_n = arr.shape[0]
    ratio = target_n / float(src_n)
    if ratio >= _SLIDE_TILE_ABOVE:
        return _texture_stretch(arr, target_n, rate)
    if ratio <= _SLIDE_TRIM_BELOW:
        return _trim_faded(arr, target_n, rate)
    return _resample(arr, target_n)


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
        self._slide_cache = {}       # (樣本序號, 10ms 桶) -> 時長整形後的 Sound
        self._slide_ch = None        # 專用聲道：新一手直接頂掉上一手，不疊音
        self._bgm_ch = None
        self._bgm_channel = None
        self._bgm_sound = None
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
            # 滑動聲與 bgm 各佔一條專用聲道：既能「新手頂掉舊手」不疊音，
            # 也避免 snd.play() 隨機搶聲道時把背景樂踢掉。
            pygame.mixer.set_num_channels(_MIXER_CHANNELS)
            pygame.mixer.set_reserved(_MIXER_RESERVED)
            self._slide_ch = pygame.mixer.Channel(0)
            self._bgm_ch = pygame.mixer.Channel(1)
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
        # bgm：music/ 下 bgm.* 優先，否則該目錄第一個音訊檔
        bgm = _find_in(self.music_dir, _BGM_BASE)
        if bgm is None:
            music_files = _list_audio(self.music_dir)
            if music_files:
                bgm = music_files[0]
        if bgm is not None:
            self._load_sound('bgm', bgm)
            self._slot_path['bgm'] = bgm

        # slide：載入所有 slide*.* 做多樣本輪換；一個都沒有才退回單一 slide.*
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
        else:
            one = _find_in(self.sfx_dir, _SLIDE_PREFIX)
            if one is not None:
                self._slide_files = [one]
                self._load_sound('slide', one)
                self._slot_path['slide'] = one

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
        p = self._slot_path.get('bgm')
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
        if self.available and self._bgm_channel is not None:
            vol = 0.0 if self.muted else self.music_volume
            try:
                self._bgm_channel.set_volume(vol)
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
            snd = (random.choice(self._slide_samples) if self._slide_samples
                   else self._sounds.get('slide'))
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

    # ---- 滑動聲：時長貼合 + 隨機擾動 ----
    def _slide_target_ms(self, duration_ms):
        """本次摩擦聲的目標長度：貼合動畫時長，再疊 ±6% 擾動當作音高微變。"""
        try:
            target = float(duration_ms) if duration_ms else float(_SLIDE_DEFAULT_MS)
        except (TypeError, ValueError):
            target = float(_SLIDE_DEFAULT_MS)
        target *= random.uniform(1.0 - _SLIDE_JITTER, 1.0 + _SLIDE_JITTER)
        return int(max(_SLIDE_MIN_MS, min(_SLIDE_MAX_MS, target)))

    def _make_variant(self, sample, target_ms):
        """按目標時長現做一條該長度的 Sound（失敗就退回原樣本）。"""
        if _np is None or sample is None:
            return sample
        init = pygame.mixer.get_init()
        if not init:
            return sample
        try:
            arr = pygame.sndarray.array(sample)
        except Exception:
            return sample
        if arr.ndim != 2 or arr.shape[0] < 2:
            return sample
        rate = init[0]
        target_n = max(1, int(rate * target_ms / 1000.0))
        try:
            out = _shape_to_length(arr, target_n, rate)
            # 尾部淡出：变体长度＝动画时长，硬切会「咔」一下；动画收尾时声音同步收掉
            k = min(out.shape[0], max(1, int(rate * _SLIDE_TAIL_MS / 1000.0)))
            if k > 1:
                out = out.astype(_np.float32, copy=True)
                out[-k:] *= _np.linspace(1.0, 0.0, k, dtype=_np.float32)[:, None]
            out = _np.clip(out, -32768.0, 32767.0).astype(_np.int16)
            return pygame.sndarray.make_sound(_np.ascontiguousarray(out))
        except Exception as e:
            print(f'[audio] 生成 slide 變體失敗（退回原樣本）：{e}')
            return sample

    def _slide_variant(self, duration_ms):
        """挑樣本 + 取（或現做）對應長度的變體。"""
        samples = self._slide_samples
        if not samples:
            return self._sounds.get('slide')
        # 樣本隨機挑（S5-2 防識破），但避免連兩手同一個
        idx = random.randrange(len(samples))
        if len(samples) > 1 and idx == self._slide_idx:
            idx = (idx + 1) % len(samples)
        self._slide_idx = idx
        target_ms = self._slide_target_ms(duration_ms)
        # 20ms 一桶：±6% 扰动落在同一桶的相邻值直接复用，避免逐手现做
        key = (idx, int(round(target_ms / 20.0)))
        hit = self._slide_cache.get(key)
        if hit is not None:
            return hit
        snd = self._make_variant(samples[idx], target_ms)
        if len(self._slide_cache) >= _SLIDE_CACHE_MAX:
            self._slide_cache.clear()
        self._slide_cache[key] = snd
        return snd

    def _slide_volume(self, distance, duration_ms=None):
        """音量 = 距离基准 × 速度系数 × 随机扰动。

        速度系数就是用家说的「就像魔方一样，滑动越慢声音越小」：动画被拉长
        （慢速档）时摩擦声同时变轻，而不是把同一个声音硬撑满整段动画来冒充
        「一直在滑」。距离只决定 1 格 / 多格的基准差。
        """
        try:
            dist = max(1, int(distance or 1))
        except (TypeError, ValueError):
            dist = 1
        base = min(1.0, 0.8 + 0.1 * (dist - 1))
        try:
            ms = float(duration_ms) if duration_ms else float(_SLIDE_DEFAULT_MS)
        except (TypeError, ValueError):
            ms = float(_SLIDE_DEFAULT_MS)
        speed = dist / (max(1.0, ms) / 1000.0)          # 格/秒
        speed_f = max(_SLIDE_MIN_SPEED_VOL, min(1.0, speed / _SLIDE_REF_CPS))
        vol = self.sfx_volume * base * speed_f
        vol *= random.uniform(1.0 - _SLIDE_VOL_JITTER, 1.0 + _SLIDE_VOL_JITTER)
        return max(0.0, min(1.0, vol))

    def play_slide(self, distance=None, duration_ms=None):
        """滑動摩擦聲：長度貼合本次動畫（見檔頭兩條硬要求）。

        distance   本次滑動格數（與時長一起換算速度 → 音量）。
        duration_ms 本次滑動動畫的實際時長；呼叫方應在動畫時長定稿後再傳
                    （拖拽接續會把時長按剩餘比例縮短）。省略則用預設短音。
        新一手直接頂掉上一手（專用聲道），所以連按不會疊成一團；同一手
        重複觸發只認第一次（_SLIDE_MIN_GAP_MS）。
        """
        if not self._can_play_sfx():
            return
        now = pygame.time.get_ticks()
        if now - getattr(self, '_last_slide_ms', -10 ** 9) < _SLIDE_MIN_GAP_MS:
            return
        snd = self._slide_variant(duration_ms)
        if snd is None:
            return
        self._last_slide_ms = now
        vol = self._slide_volume(distance, duration_ms)
        try:
            ch = self._slide_ch
            if ch is not None:
                ch.set_volume(vol)
                ch.play(snd, fade_ms=_SLIDE_FADE_IN_MS)
            else:
                snd.set_volume(vol)
                snd.play()
        except Exception as e:
            print(f'[audio] 播放 slide 失敗：{e}')

    def play_bgm(self, loop=True):
        if not (self.available and self.music_enabled and not self.muted):
            return
        snd = self._sounds.get('bgm')
        if snd is None:
            return
        ch = self._bgm_ch
        # 已在播就別重開頭：設定每改一次都會 sync，重播會一直跳回開頭
        if ch is not None and self._bgm_sound is snd:
            try:
                if ch.get_busy():
                    return
            except Exception:
                pass
        try:
            self._bgm_sound = snd
            if ch is not None:
                ch.play(snd, loops=-1 if loop else 0)
                self._bgm_channel = ch
            else:
                self._bgm_channel = snd.play(-1 if loop else 0)
            self._apply_music_volume()
        except Exception as e:
            print(f'[audio] 播放 bgm 失敗：{e}')

    def stop_bgm(self):
        ch = self._bgm_ch if self._bgm_ch is not None else self._bgm_channel
        if ch is not None:
            try:
                ch.stop()
            except Exception:
                pass
        self._bgm_channel = None
        self._bgm_sound = None
