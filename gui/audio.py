"""音效与背景音乐接口骨架。

照 docs/ui/前端動效優化計劃.md §S5 實作。素材由用戶提供，統一放在專案根目錄
`assets/audio/` 下，再分兩個子目錄：
- `assets/audio/sound/`  —— 一次性音效（slide / fail / solved）
- `assets/audio/music/`  —— 背景音樂（bgm）

檔名規則（素材命名不必遷就槽位）：
- bgm  ：`music/` 下 `bgm.*`；沒有就取該目錄第一個音訊檔。
- slide：`sound/` 下所有 `slide*.*`，載入後輪換播放（S5-2 多樣本防識破，
  例如 slide1.wav … slide4.wav）；完全沒有才退回單一 `slide.*`。
- fail / solved：`sound/` 下精確名 `fail.*` / `solved.*`；缺則靜默 no-op。
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
- sync_settings(...)              GUI 一次推送全部開關與音量
- play_fail() / play_solved()    一次性音效（失敗 / 復原）
- play_slide(distance=None)       滑動摩擦聲：多樣本輪換（素材備齊後可接 drag 長度）
- play_bgm() / stop_bgm()        背景音樂迴圈
"""

import os
import sys

import pygame

_EXTS = ('.ogg', '.wav', '.mp3')

# 外部資源根目錄：音效在 assets/audio/sound/，背景樂在 assets/audio/music/
_AUDIO_ROOT = 'assets/audio'

_BGM_BASE = 'bgm'                       # music/ 下的優先檔名（無則取第一個音訊檔）
_SLIDE_PREFIX = 'slide'                 # sound/ 下所有 slide*.* 做輪換
_ONE_SHOT_SLOTS = ('fail', 'solved')    # sound/ 下精確檔名

# 預設音量（0..1）；config / settings 以 0..100 整數傳入，預設調低（S5-1）
_DEFAULT_SFX_VOLUME = 0.7
_DEFAULT_MUSIC_VOLUME = 0.5

# 摩擦聲連播節流（毫秒）：連按方向鍵 / 求解演示連播時避免疊成一團（S5-3）
_SLIDE_MIN_GAP_MS = 55


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
        self._slide_samples = []     # slide 多樣本（S5-2），依序輪換
        self._slide_idx = 0
        self._bgm_channel = None
        self._bgm_sound = None
        # 設定（由 GUI 推送；預設開，音量調低）
        self.sfx_enabled = True
        self.music_enabled = True
        self.muted = False
        self.sfx_volume = _DEFAULT_SFX_VOLUME
        self.music_volume = _DEFAULT_MUSIC_VOLUME
        try:
            pygame.mixer.init()
            self.available = True
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

        # slide：載入所有 slide*.* 做多樣本輪換；一個都沒有才退回單一 slide.*
        slide_paths = _list_prefixed(self.sfx_dir, _SLIDE_PREFIX)
        if slide_paths:
            self._slide_samples = [
                s for s in (self._make_sound(p) for p in slide_paths)
                if s is not None
            ]
            if self._slide_samples:
                self._sounds['slide'] = self._slide_samples[0]
        else:
            one = _find_in(self.sfx_dir, _SLIDE_PREFIX)
            if one is not None:
                self._load_sound('slide', one)

        # fail / solved：精確名；缺則不載入，播放時靜默 no-op
        for slot in _ONE_SHOT_SLOTS:
            one = _find_in(self.sfx_dir, slot)
            if one is not None:
                self._load_sound(slot, one)

    # ---- 設定 ----
    def set_muted(self, b):
        self.muted = bool(b)
        self._apply_music_volume()

    def set_sfx_enabled(self, b):
        self.sfx_enabled = bool(b)

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
                      sfx_volume=70, music_volume=50):
        """由 GUI 一次推送全部設定。"""
        self.set_sfx_enabled(sfx_enabled)
        self.set_music_enabled(music_enabled)
        self.set_muted(muted)
        self.set_sfx_volume(sfx_volume)
        self.set_music_volume(music_volume)

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
        """播放一次性音效（slide / fail / solved）。"""
        if not self._can_play_sfx():
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

    def play_slide(self, distance=None):
        """滑動摩擦聲：多樣本依序輪換（S5-2 避免連播被識破）。

        distance 為本次滑動格數：走得遠稍響一點（S5-2「音量跟著滑動距離走」）。
        連按方向鍵 / 求解演示連播會密集觸發，這裡做 ~55ms 節流（S5-3），
        免得變成炒豆子。
        """
        if not self._can_play_sfx():
            return
        now = pygame.time.get_ticks()
        if now - getattr(self, '_last_slide_ms', -10 ** 9) < _SLIDE_MIN_GAP_MS:
            return
        self._last_slide_ms = now
        # 距離 → 音量：1 格 0.8x，3 格及以上 1.0x（不超過使用者音量）
        try:
            dist = max(1, int(distance or 1))
        except (TypeError, ValueError):
            dist = 1
        vol = self.sfx_volume * min(1.0, 0.8 + 0.1 * (dist - 1))
        samples = self._slide_samples
        if samples:
            snd = samples[self._slide_idx % len(samples)]
            self._slide_idx += 1
            try:
                snd.set_volume(vol)
                snd.play()
            except Exception as e:
                print(f'[audio] 播放 slide 失敗：{e}')
            return
        snd = self._sounds.get('slide')
        if snd is not None:
            try:
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
        # 已在播就別重開頭：設定每改一次都會 sync，重播會一直跳回開頭
        ch = self._bgm_channel
        if ch is not None and self._bgm_sound is snd:
            try:
                if ch.get_busy():
                    return
            except Exception:
                pass
        try:
            self._bgm_sound = snd
            self._bgm_channel = snd.play(-1 if loop else 0)
            self._apply_music_volume()
        except Exception as e:
            print(f'[audio] 播放 bgm 失敗：{e}')

    def stop_bgm(self):
        if self._bgm_channel is not None:
            try:
                self._bgm_channel.stop()
            except Exception:
                pass
        self._bgm_channel = None
        self._bgm_sound = None
