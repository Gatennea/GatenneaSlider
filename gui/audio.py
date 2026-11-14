"""音效与背景音乐管理（AudioManager）。

照 docs/ui/前端動效優化計劃.md §S5 實作。素材由用戶提供，統一放在專案根目錄
`assets/audio/` 下，再分兩個子目錄：
- `assets/audio/sound/`  —— 一次性音效（slide / fail / solved / click / keyboard）
- `assets/audio/music/`  —— 背景音樂（bgm）

檔名規則（素材命名不必遷就槽位）：
- bgm  ：`music/` 下**所有**音訊檔進同一個播放池，**隨機輪播**（一首放完自動
  換下一首，且不會連兩首同一支）。目錄內容每次換曲都重掃，所以玩家隨時往
  `music/` 丟新曲子、刪掉舊的，下一首就會生效，不用重啟。單曲時就是它一直
  循環。舊行為（只認 `bgm.*`、否則取目錄第一個）已於 2026-11-14 改掉。
- slide：`sound/` 下所有 `slide*.*`，載入後輪換播放（S5-2 多樣本防識破，
  例如 slide1.wav … slide4.wav）；完全沒有才退回單一 `slide.*`。
- fail / solved：`sound/` 下 `fail.*`（**別名 `reject.*`**，2026-11-07 用戶給的
  `reject.mp3` 就是填這個槽位）/ `solved.*`；`solved` 也認別名 `cheer.*`。
  都沒有則靜默 no-op。
- click / keyboard：`sound/` 下 `click.*` / `keyboard.*`，是**獨立槽位**（鼠標點擊 /
  鍵盤事件），不是 fail 的別名。觸發點：`handle_events` 的全局左鍵、KEYDOWN。
副檔名任取 `.ogg` / `.wav` / `.mp3` 之一。

⚠️ **背景樂素材一律放壓縮格式**（2026-11-07 定，見 `docs/spec/打包与发版.md` §4）：
`music/` 只放 `.ogg` / `.mp3`，正式曲目叫 `bgm.ogg`。原始 `.wav` 是母帶，
留在本機、不進版本庫也不進安裝包——64.5MB 的 6 分鐘立體聲 PCM 用 zip
壓完還有 61.2MB，會把 31MB 的安裝包直接頂到 90MB 以上；轉 128k OGG 是
5.31MB，時長與立體聲都不變。新曲子照同一條命令轉好再放進來（命令在 §4）。
`Gatenneaslider.spec::_collect_assets()` 也會主動跳過 `music/*.wav`，
`build_release.py` 打包前會提醒。

一次交互只出一個聲音（2026-11-07 定）：
  · 鍵盤音是「這一按被系統收到」的**兜底反饋**，不是每按必響；
    **出聲時刻是 KEYUP（鬆開按鍵）**，與鍵盤事件的響應對齊，按下時只登記。
  · 一次推動若已有動作音（成功=滑動聲，被拒=拒絕聲），鍵盤音就不出，
    絕不兩個一起響；若這一按沒產生任何動作音（打字、快捷鍵、Esc、
    被狀態攔下又沒播拒絕聲），才補一聲鍵盤音。
  · 判定靠 `AudioManager.last_action_ms`：滑動聲 / 拒絕聲播出（或拒絕聲被
    節流攔下但素材在）時記時間戳；`handle_events` 在 KEYUP 時拿它和按下
    時間戳比對（跨幀也有效），見 `gui/events.py::_flush_keyboard_sound`。

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
                                  一次性音效（滑動被拒 / 復原 / 鼠標點擊 / 鍵盤按鍵）
                                  play_fail 走獨佔聲道 + 節流，長按被拒不疊音
- play_slide(distance=None, duration_ms=None)
                                  滑動聲：播**一次**原始 slide 樣本（單次魔方轉動聲），
                                  只按滑動速度調音量；不拉伸、不循環、不合成
- play_bgm() / update_bgm() / stop_bgm()
                                  背景音樂：music/ 下所有音訊檔隨機輪播（mixer.music
                                  串流，不把素材常駐記憶體）；update_bgm 每幀檢查
                                  「這一首放完了嗎」，放完就抽下一首（不連同日一首）

滑動聲的硬要求（使用者 2026-11-07 反覆糾正後定稿）：
1. **素材是「單次魔方轉動聲」**（70~165ms 的一次事件音），不是持續摩擦噪聲。
   工業做法（Unity `PlayOneShot` / `PlayOnceAudio`、Web Audio one-shot buffer）：
   事件音就是播**一次原始採樣**，只調音量；慢動作最多調音高／低通，
   **絕不把它拉成環境噪聲**。前九輪把「一下」撐滿整段動畫（整段循環、
   粒度拼接、無縫 loop、頻譜烙印成平穩白噪聲）全錯，最後一種聽成砂紙打磨聲。
2. **只要滑動動畫要播，就得有聲**——在 `start_animation()` 之後才發，跟畫面同步；
   動畫時長只用來換算速度，**不決定聲音長度**：真實魔方轉一下就是一聲，
   慢速動畫不必讓聲音鋪滿 1000ms。
3. **越慢越輕**——「就像魔方一樣，滑動越慢聲音越小」：音量按速度（格/秒）縮放。
4. **一次滑動只播一次**——不循環、不拼接、不重複觸發；獨佔聲道，新手頂掉舊手。
"""

import os
import random
import sys

import pygame

_EXTS = ('.ogg', '.wav', '.mp3')

# 外部資源根目錄：音效在 assets/audio/sound/，背景樂在 assets/audio/music/
_AUDIO_ROOT = 'assets/audio'

_BGM_BASE = 'bgm'                       # 舊的優先檔名；現在只當推薦命名用，不再有特權
_SLIDE_PREFIX = 'slide'                 # sound/ 下所有 slide*.* 做輪換
_ONE_SHOT_SLOTS = ('fail', 'solved', 'click', 'keyboard')    # sound/ 下精確檔名
# 槽位名之外的常用別名：素材常按「聲音內容」命名，按順序認。
# ⚠️ click / keyboard 是**獨立槽位**（鼠標點擊 / 鍵盤事件），不是 fail 的別名。
#    fail 槽位認 `reject.*`：2026-11-07 用戶新增的「滑動被拒」素材。
_ONE_SHOT_ALIASES = {
    'fail': ('fail', 'reject'),
    'solved': ('solved', 'cheer'),
}

# ---- 槽位表：設定頁「音效一覽」直接讀這裡，新增一類音效只需改這一處 ----
# (鍵, 名稱, 說明)；順序就是設置頁列出的順序。
SLOT_SPECS = (
    ('slide',    '滑动声', '拖动 / 键盘移动 / 打乱时的单次转动声（原始样本播一次，越慢越轻）'),
    ('fail',     '滑动被拒', '尝试推动但走不通时播放（没选缝 / 方向不对 / 会断开或重叠）'),
    ('solved',   '复原',     '拼好复原时播放'),
    ('click',    '鼠标点击', '任意左键点击：棋盘、按钮、菜单、开关、对话框'),
    ('keyboard', '键盘按键', '松开按键时响；这一按若已有滑动声或拒绝声，就不叠按键声'),
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
# 右鍵點擊聲：與左鍵共用 click 槽（不新增開關），靠更低的音量做區分；
# 左右各用獨立節流時間戳，連點時不會互相吞
_CLICK_RIGHT_VOLUME = 0.65
# 拒絕音素材約 1.2s：節流只防「同一次按鍵被多條路徑重複觸發」，
# 長按連發靠專用聲道的 get_busy() 擋，聲音沒播完不重開頭。
_FAIL_MIN_GAP_MS = 120

# 滑動聲：單次事件音，只按速度調音量（見檔頭）
_SLIDE_DEFAULT_MS = 160     # 沒給動畫時長時，用於速度→音量換算的基準值
_SLIDE_VOL_JITTER = 0.08    # 音量隨機擾動 ±8%
_SLIDE_REF_CPS = 4.0        # 參考滑動速度（格/秒）：達到此速度音量才滿檔
_SLIDE_MIN_SPEED_VOL = 0.15 # 慢速時的音量下限（再慢也留一絲轉動聲）

# 專用聲道：0 = 滑動聲，1 = 保留（bgm 走 mixer.music 不佔 Channel），
# 2 = 拒絕音；餘下留給 solved / click / keyboard 等一次性音效。
_MIXER_CHANNELS = 8
_MIXER_RESERVED = 3


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
        self._slide_ch = None        # 專用聲道：新一手直接頂掉上一手，不疊音
        self._fail_ch = None         # 拒絕音專用聲道：沒播完不重開，長按不疊音
        # 「本次交互已經有動作音」的時間戳：事件層據此決定要不要補鍵盤音。
        # 只有滑動聲 / 拒絕聲真的接管了這次反饋才更新（缺素材或關掉不更新）。
        self.last_action_ms = -10 ** 9
        self._last_fail_ms = -10 ** 9
        # bgm 只記路徑、不預載：播放走 mixer.music 串流（待办清单 §二十.2，
        # 67MB wav 若走 Sound 會整份解進常駐記憶體，實測 +67MB）
        # 2026-11-14：單曲 → 隨機輪播池（music/ 下全部音訊檔）
        self._bgm_paths = []         # 播放池（按檔名排序，重掃時整體替換）
        self._bgm_current = None     # 正在播的那一首（避免連兩首同一支）
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
            self._fail_ch = pygame.mixer.Channel(2)
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
        # bgm：music/ 下所有音訊檔進同一個播放池，隨機輪播。
        # 只記路徑不預載——啟動零成本，play_bgm 才開檔串流讀（§二十.2）
        self.rescan_music()

        # slide：載入所有 slide*.* 做多樣本輪換；一個都沒有才退回單一 slide.*
        # 這些是「單次轉動聲」事件音，原樣播放，不做任何加工或預算。
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
        was_muted = self.muted
        self.muted = bool(b)
        self._apply_music_volume()
        # 一键静音要「立刻」安静：_can_play_sfx 只挡住新播放，已经在响的那一声
        # （reject / keyboard 约 1.2s）会一路拖到播完。停掉所有一次性音效声道；
        # bgm 走 mixer.music 独立流，由 GUI._sync_audio_settings 起停，不在这里动。
        if self.muted and not was_muted and self.available:
            try:
                pygame.mixer.stop()
            except Exception:
                pass

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
        """背景乐状态（设置页显示用）：当前曲名 + 池子大小。"""
        if not self._bgm_paths:
            return '缺素材'
        cur = os.path.basename(self._bgm_current or self._bgm_paths[0])
        if len(self._bgm_paths) > 1:
            return f'{cur}（music/ 共 {len(self._bgm_paths)} 首，随机轮播）'
        return cur

    def rescan_music(self):
        """重扫 music/ 目录，返回当前的播放池。

        每次换曲都会调用：玩家往目录里丢新曲子（或删掉旧的）后，下一首就按
        新目录抽，不需要重启游戏。目录不存在时返回空池，不报错。
        """
        self._bgm_paths = _list_audio(self.music_dir)
        if self._bgm_current not in self._bgm_paths:
            self._bgm_current = None
        return list(self._bgm_paths)

    def _pick_bgm_path(self):
        """从池里随机抽一首，且不抽正在播的这一首（单曲时只能抽它）。"""
        paths = self._bgm_paths
        if not paths:
            return None
        if len(paths) == 1:
            return paths[0]
        pool = [p for p in paths if p != self._bgm_current] or list(paths)
        return random.choice(pool)

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
        if self.available and (self._bgm_paths or self._bgm_current):
            vol = 0.0 if self.muted else self.music_volume
            try:
                pygame.mixer.music.set_volume(vol)
            except Exception:
                pass

    # ---- 播放 ----
    def _can_play_sfx(self):
        return (self.available and self.sfx_enabled and not self.muted
                and self._sounds)

    def play(self, slot, volume_scale=1.0):
        """播放一次性音效（slide / fail / solved / click / keyboard）。

        volume_scale 只按比例压低这一次的音量（右鍵點擊用，見 play_click）；
        不改全域 sfx_volume，也不影響下一次播放。
        """
        if not self._can_play_sfx():
            return
        if not self.slot_enabled.get(slot, True):
            return
        snd = self._sounds.get(slot)
        if snd is None:
            return
        try:
            snd.set_volume(self.sfx_volume * max(0.0, min(1.0, volume_scale)))
            snd.play()
        except Exception as e:
            print(f'[audio] 播放 {slot} 失敗：{e}')

    def play_fail(self):
        """滑動被拒：`reject.*` / `fail.*` 短提示音。

        兩件事一起做：
        1. 登記 `last_action_ms` —— 只要在放（含被節流/忙碌攔下），這次按鍵
           就由動作音說話，事件層不再補鍵盤音，杜絕兩個音同時響。
        2. 獨佔聲道 + 節流 —— 素材約 1.2s，長按被拒時不重開頭、不疊成一片。
        缺素材或該槽位關掉時**不登記**，鍵盤音照常補上，不會全靜音。
        回傳 bool：本次是否**真的發聲**（False＝被 120ms 節流／聲道忙攔下）。
        2026-11-13 起視覺**不再**復用此判定——聲音可節流，變色不許有冷卻；
        回傳值只留給需要知道「這下有沒有響」的呼叫方。
        """
        if not self._can_play_sfx():
            return True
        if not self.slot_enabled.get('fail', True):
            return True
        snd = self._sounds.get('fail')
        if snd is None:
            return True
        now = pygame.time.get_ticks()
        self.last_action_ms = now
        if now - self._last_fail_ms < _FAIL_MIN_GAP_MS:
            return False
        ch = self._fail_ch
        try:
            if ch is not None and ch.get_busy():
                return False
        except Exception:
            pass
        self._last_fail_ms = now
        try:
            snd.set_volume(self.sfx_volume)
            if ch is not None:
                ch.play(snd)
            else:
                snd.play()
        except Exception as e:
            print(f'[audio] 播放 fail 失敗：{e}')
        return True

    def play_solved(self):
        self.play('solved')

    def _play_throttled(self, slot, attr, gap_ms):
        now = pygame.time.get_ticks()
        if now - getattr(self, attr, -10 ** 9) < gap_ms:
            return
        setattr(self, attr, now)
        self.play(slot)

    def play_click(self, kind='left'):
        """鼠标点击声（棋盘 / 按钮 / 开关 / 对话框，全 GUI 一次性挂接）。

        kind='right' 走同一个 click 槽，但音量压到 _CLICK_RIGHT_VOLUME 并用
        `_last_click_right_ms` 独立节流：左右各连点互不吞，设置页也只需要
        一个「鼠标点击」开关。
        """
        if kind == 'right':
            now = pygame.time.get_ticks()
            if now - getattr(self, '_last_click_right_ms', -10 ** 9) < _CLICK_MIN_GAP_MS:
                return
            self._last_click_right_ms = now
            self.play('click', volume_scale=_CLICK_RIGHT_VOLUME)
            return
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
            # 試聽就是播一次原始轉動聲，跟遊戲內完全一致
            snd = self._pick_slide_sample()
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

    # ---- 滑動聲：單次事件音，播一次原始樣本（見檔頭）----
    def _slide_speed_ms(self, duration_ms):
        """動畫時長：**只用來換算速度 → 音量，不決定播放長度**。"""
        try:
            ms = float(duration_ms) if duration_ms else float(_SLIDE_DEFAULT_MS)
        except (TypeError, ValueError):
            ms = float(_SLIDE_DEFAULT_MS)
        return max(1.0, ms)

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

    def _pick_slide_sample(self):
        """隨機挑一條**原始**樣本（避免連兩手同一個），不做任何加工。"""
        samples = self._slide_samples
        if not samples:
            return self._sounds.get('slide')
        idx = random.randrange(len(samples))
        if len(samples) > 1 and idx == self._slide_idx:
            idx = (idx + 1) % len(samples)
        self._slide_idx = idx
        return samples[idx]

    def _slide_volume(self, distance, duration_ms=None):
        """音量 = 距離基準 × 速度係數 × 隨機擾動（「越慢越小聲」）。

        慢速動畫只讓這一聲變輕，不把它拉長、不循環、不合成噪聲——
        真實魔方轉一下就是一聲，差別只在力道。
        """
        try:
            dist = max(1, int(distance or 1))
        except (TypeError, ValueError):
            dist = 1
        base = min(1.0, 0.8 + 0.1 * (dist - 1))
        speed_f = max(_SLIDE_MIN_SPEED_VOL,
                      self._slide_speed_factor(dist,
                                               self._slide_speed_ms(duration_ms)))
        vol = self.sfx_volume * base * speed_f
        vol *= random.uniform(1.0 - _SLIDE_VOL_JITTER, 1.0 + _SLIDE_VOL_JITTER)
        return max(0.0, min(1.0, vol))

    def play_slide(self, distance=None, duration_ms=None):
        """一次滑動 = 播**一次**原始單次轉動聲；只按速度調音量。

        duration_ms 是動畫時長定稿值（拖拽接續會縮短），**只用來算速度**，
        不會把聲音拉長、循環或合成。慢速動畫聽到的仍是原本那一聲，只是更輕。
        新一手直接頂掉上一手（獨佔聲道），連按不疊音；30ms 節流只防重複觸發。
        """
        if not self._can_play_sfx():
            return
        if not self.slot_enabled.get('slide', True):
            return
        now = pygame.time.get_ticks()
        if now - getattr(self, '_last_slide_ms', -10 ** 9) < _SLIDE_MIN_GAP_MS:
            return
        snd = self._pick_slide_sample()
        if snd is None:
            return
        self._last_slide_ms = now
        self.last_action_ms = now       # 這次按鍵已有滑動聲 → 壓掉鍵盤音
        vol = self._slide_volume(distance, duration_ms)
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

    def play_bgm(self, loop=False):
        """播放池里随机抽一首（默认放一遍就结束，由 update_bgm 接下一首）。

        loop=True 保留旧语义（把当前这首无限循环），给需要「一首到底」的场合用。
        返回是否真的开播（池子空 / 被静音 / 已在播 → False）。
        """
        if not (self.available and self.music_enabled and not self.muted):
            return False
        # 已在播就別重開頭：設定每改一次都會 sync，重播會一直跳回開頭
        if pygame.mixer.music.get_busy():
            return False
        # 先放掉上一首的文件句柄：Windows 上 mixer 不鬆手，玩家就刪不掉正在
        # 播過的那首（而且我們要在下一行重掃目錄）
        self._release_bgm_file()
        # 换曲顺手重扫目录：玩家丢进来的新曲子 / 删掉的旧曲子下一次换曲即生效
        self.rescan_music()
        tried = 0
        total = max(1, len(self._bgm_paths))
        while tried < total:
            if loop and self._bgm_current:
                path = self._bgm_current
            else:
                path = self._pick_bgm_path()
            if path is None:
                return False
            try:
                # 串流播放：每次启动都 load（開檔讀檔頭，不吃整份記憶體）；
                # 停播後重 load 也保證各 pygame 版本行為一致
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self.music_volume)
                pygame.mixer.music.play(-1 if loop else 0)
                self._bgm_current = path
                return True
            except Exception as e:
                # 坏档（损坏 / 编码不支持）：从本轮池里剔除，换下一首再试
                print(f'[audio] 播放 bgm 失敗（{os.path.basename(path)}）：{e}')
                try:
                    self._bgm_paths.remove(path)
                except ValueError:
                    pass
                if self._bgm_current == path:
                    self._bgm_current = None
                tried += 1
        return False

    def _release_bgm_file(self):
        """放掉 mixer.music 当前占用的文件。

        Windows 上只要还占着句柄，玩家在资源管理器里就删不掉这首曲子；
        换曲/停播时主动 unload（pygame 2.0+），老接口没有就降级只 stop。
        """
        if not self.available:
            return
        try:
            pygame.mixer.music.unload()
        except Exception:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    def update_bgm(self):
        """每帧调用：这一首放完了就自动随机换下一首（连续轮播）。

        只在「音乐开着 且 没静音」时接手；被关掉或静音期间绝不偷偷重启。
        没有 pygame.mixer / 播放池为空时静默 no-op。
        """
        if not (self.available and self.music_enabled and not self.muted):
            return
        if not self._bgm_paths:
            return
        try:
            if pygame.mixer.music.get_busy():
                return
        except Exception:
            return
        self.play_bgm()

    def stop_bgm(self):
        if not self.available:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        # 停播后立即放掉句柄，别占着文件（见 _release_bgm_file）
        self._release_bgm_file()
