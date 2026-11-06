"""音效与背景音乐接口骨架。

照 docs/ui/前端動效優化計劃.md §S5 實作。素材由用戶提供，放在專案根目錄
`sound/` 下，檔名對應槽位：bgm / slide / fail / solved，副檔名任取
`.ogg` / `.wav` / `.mp3` 之一。

設計約束（agents.md §4 打包鐵律）：
- 無素材時所有播放靜默 no-op，不報錯、不卡啟動。
- 無頭環境（無 pygame.mixer / 無聲卡 / SDL_AUDIODRIVER=dummy）整個模組 try 跳過，
  絕不拖垮啟動或渲染。
- 音量設定以 0..100 整數在 config / settings 之間傳遞，內部歸一成 0..1 給 mixer。

api 概要：
- AudioManager(sound_dir=None)
- load_all()                      掃 sound/ 載入已有素材
- sync_settings(...)              GUI 一次推送全部開關與音量
- play_fail() / play_solved()    一次性音效（失敗 / 復原）
- play_slide(distance=None)       滑動摩擦聲（素材備齊後接 drag 長度）
- play_bgm() / stop_bgm()        背景音樂迴圈
"""

import os

import pygame

# 槽位 -> 檔名（不含副檔名）；副檔名按下方清單依序嘗試
_SLOT_FILES = {
    'bgm': 'bgm',
    'slide': 'slide',
    'fail': 'fail',
    'solved': 'solved',
}
_EXTS = ('.ogg', '.wav', '.mp3')

# 預設音量（0..1）；config / settings 以 0..100 整數傳入，預設調低（S5-1）
_DEFAULT_SFX_VOLUME = 0.7
_DEFAULT_MUSIC_VOLUME = 0.5


def _project_sound_dir():
    # gui/audio.py 在 <root>/gui/，根目錄在其上層
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, 'sound')


class AudioManager:
    def __init__(self, sound_dir=None):
        self.available = False
        self.sound_dir = sound_dir or _project_sound_dir()
        self._sounds = {}            # slot -> pygame.mixer.Sound
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
    def load_all(self):
        if not self.available:
            return
        for slot, base in _SLOT_FILES.items():
            if slot in self._sounds:
                continue
            for ext in _EXTS:
                path = os.path.join(self.sound_dir, base + ext)
                if os.path.exists(path):
                    try:
                        self._sounds[slot] = pygame.mixer.Sound(path)
                    except Exception as e:
                        print(f'[audio] 載入 {path} 失敗：{e}')
                    break

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
        """滑動摩擦聲（持續音，素材備齊後接 drag 長度）。骨架階段為一次性觸發。"""
        self.play('slide')

    def play_bgm(self, loop=True):
        if not (self.available and self.music_enabled and not self.muted):
            return
        snd = self._sounds.get('bgm')
        if snd is None:
            return
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
