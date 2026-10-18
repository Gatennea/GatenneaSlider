# -*- coding: utf-8 -*-
"""
打亂演示動畫測試（2026-10-18 新功能）

覆蓋：
    T1 記錄不變量（純邏輯，三形態）：從打亂前快照按記錄逐步重放，
       必須精確復現打亂終態（逐塊比對）——GUI 演示正確性的地基
    T2 演示啓動：history 照舊清空（step_count=0 / 一條快照），
       棋盤放回打亂前狀態，第一條記錄開始播放
    T3 完整播放：截斷演示播完前幾步 → 淡出 → 切終態 → 淡入；
       結束後棋盤=打亂終態、快照內容=終態、全程不碰歷史
    T4 短記錄不求淡出：只餵前 3 條真實記錄，演完即終態、無淡出階段
    T5 中斷對齊：演示中途 _abort → 棋盤直接对齐終態、狀態全清
    T6 換盤失效：演示中換 self.game → 演示只清狀態、不碰新棋盤
    T7 門控：plain 模式 / 動畫關閉 → 不演示，打亂後立即是終態
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI                  # noqa: E402
from game import SliderMatrix              # noqa: E402
from game_mi import MiSliderMatrix         # noqa: E402
from game_triangle import TriangleSliderMatrix  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def positions(game):
    return [tuple(b.location) for b in game.blocks]


def board_matrix(game):
    game.update_matrix()
    return [row[:] for row in game.matrix]


def replay(game, records):
    """按記錄逐步重放（與 GUI 演示同一套查找/落位邏輯）。"""
    for rec in records:
        pos_to_block = {tuple(b.location): b for b in game.blocks}
        blocks = [pos_to_block[tuple(p)] for p in rec['moved']]
        assert len(blocks) == len(rec['moved']), '記錄位置找不到塊'
        for b, p in zip(blocks, rec['final']):
            b.location = list(p)


# ================================================================ T1 記錄不變量
print("=" * 60)
print("T1 記錄重放不變量（三形態，純邏輯）")
print("=" * 60)

for tag, game, attempts, step, kw in [
        ('方形 4x4', SliderMatrix(4, 4), 60, 2, {}),
        ('方形 5x5', SliderMatrix(5, 5), 50, 2, {}),
        ('方形 4x4 bias', SliderMatrix(4, 4), 60, 2, {'bias': 2.0}),
        ('米字 4x4', MiSliderMatrix(4, 4), 60, 2, {}),
        ('三角 k=4', TriangleSliderMatrix(4), 60, 2, {})]:
    pre = positions(game)
    recs = []
    game.shuffle(attempts, step, min_score=0.6, record=recs, **kw)
    final = positions(game)
    for b, p in zip(game.blocks, pre):
        b.location = list(p)
    replay(game, recs)
    check(f'T1 {tag}：{len(recs)} 條記錄重放復現終態',
          positions(game) == final)

# 無 record 調用不受影響（向後兼容）
g = SliderMatrix(4, 4)
r = g.shuffle(40, 2)
check('T1 無 record 調用返回 None（向後兼容）', r is None)


# ================================================================ GUI 演示
# 注意：GUI 構造時會從 config/temp_history.json 恢復上次對局（尺寸/形態
# 隨殘留狀態而變），因此以下斷言全部動態取樣（pre/final 都從實例捕獲），
# 不假設棋盤尺寸；淡出場景用「臨時包裝 shuffle 截斷記錄」確定化造出來。

def make_gui(m=4, n=4, step=2):
    gui = SliderGUI(m=m, n=n, step=step)
    gui.save_readonly_flag = False
    return gui


def with_truncated_records(gui, keep, fn):
    """在 fn() 期間把 gui.game 所屬類的 shuffle 包裝成「記錄截斷」版。

    截斷只影響「演示演幾步」，不影響棋盤終態（終態由完整打亂決定）——
    從而確定性地造出「記錄被截斷 → 需要淡出」的場景。
    SliderMatrix 有 __slots__，實例掛不了屬性，只能臨時包裝類方法
    （finally 保證恢復）。
    """
    cls = type(gui.game)
    orig = cls.shuffle

    def wrapped(self, attempts, step, bias=0.0, min_score=0.75, record=None):
        orig(self, attempts, step, bias=bias, min_score=min_score, record=record)
        if record is not None and len(record) > keep:
            del record[keep:]

    cls.shuffle = wrapped
    try:
        fn()
    finally:
        cls.shuffle = orig


def ff_anim(gui):
    """把當前滑動動畫快進到結尾（下一幀 update_animation 即提交）。"""
    gui.anim_start_time = pygame.time.get_ticks() - gui.animation_duration - 5


def run_demo_until_done(gui, max_frames=3000):
    """驅動主循環同款的兩步更新，直到演示結束；返回耗幀數。"""
    frames = 0
    while getattr(gui, '_shuffle_demo_active', False) and frames < max_frames:
        if gui.animating:
            ff_anim(gui)
        if getattr(gui, '_shuffle_demo_phase', None) in ('fade_out', 'fade_in'):
            gui._shuffle_fade_last_ms -= 20   # 測試裡人為推進淡入淡出時鐘
        gui.update_animation()
        gui._update_shuffle_demo()
        frames += 1
    return frames


print()
print("=" * 60)
print("T2/T3 GUI 演示播放（截斷 + 淡出）")
print("=" * 60)

random.seed(20261018)
gui = make_gui()
gui.animation_duration = 20          # 測試裡加快單步動畫
gui.SHUFFLE_FADE_MS = 2              # 淡入淡出也加速（實例遮罩類屬性）
gui.SHUFFLE_DEMO_STEPS = 2           # 截斷閘值調小，方便觸發淡出路徑
pre = positions(gui.game)
with_truncated_records(gui, 3, gui.shuffle_puzzle)   # 3 > 2 → 必然截斷 + 淡出
expected_final = [list(p) for p in gui._shuffle_demo_final]

check('T2 演示已啓動', gui._shuffle_demo_active)
check('T2 第一條記錄開始播放', gui.animating and gui.anim_blocks)
check('T2 棋盤放回打亂前狀態', positions(gui.game) == pre)
check('T2 歷史照舊清空：step_count=0', gui.step_count == 0)
check('T2 歷史照舊清空：僅一條快照',
      len(gui.game_history.history) == 1
      and gui.game_history.history_index == 0)
check('T2 需要淡出（記錄被截斷）', gui._shuffle_demo_need_fade)
check('T2 通知延後到演示結束', gui.macro_notify_timer <= 0)

frames = run_demo_until_done(gui)
check('T3 演示能自行收尾（不卡死）', not gui._shuffle_demo_active,
      f'{frames} 幀')
check('T3 結束後棋盤=打亂終態',
      positions(gui.game) == [tuple(p) for p in expected_final])
check('T3 快照內容=打亂終態',
      gui.game_history.history[0]['matrix'] == board_matrix(gui.game))
check('T3 全程不碰歷史', len(gui.game_history.history) == 1
      and gui.step_count == 0)
check('T3 通知已補發', gui.macro_notify_timer > 0
      and '已打乱' in gui.macro_notify_msg,
      gui.macro_notify_msg)
check('T3 結束後 animating 復位（轉場守衛解除）',
      not gui.animating and not gui.anim_blocks)

# 端到端穿透驗證：F2（指標面板）不在動畫守衛豁免清單（undo/redo/auto_solve/
# 空格）裡。animating 卡死時 KEYDOWN 會被 events.py 的動畫守衛吞掉、面板
# 不翻轉——正是「打亂後快捷鍵全失效」的用戶體感；修復後應正常 toggle。
_before = getattr(gui, 'show_metrics_panel', False)
pygame.event.post(pygame.event.Event(pygame.KEYDOWN,
                                     key=pygame.K_F2, mod=0, unicode=''))
gui.handle_events()
check('T3 結束後鍵盤輸入恢復（F2 穿透動畫守衛）',
      getattr(gui, 'show_metrics_panel', False) != _before)

# ================================================================ T4 短記錄不求淡出
print()
print("=" * 60)
print("T4 短記錄（只餵前 3 條真實記錄，不求淡出）")
print("=" * 60)

gui2 = make_gui()
gui2.animation_duration = 20
gui2.SHUFFLE_DEMO_STEPS = 5
random.seed(7)
pre2 = positions(gui2.game)
recs_all = []
gui2.game.shuffle(80, 2, min_score=0.6, record=recs_all)
take = recs_all[:3]
# 在 gui2.game 自身上算「演完 3 步的狀態」：先放回 pre2 再重放
# （不新建模擬局——GUI 構造時會從 temp_history 恢復舊局，尺寸/形態
#   都不一定是 4×4 復原態，新建假設會錯）
for b, p in zip(gui2.game.blocks, pre2):
    b.location = list(p)
replay(gui2.game, take)
final2 = positions(gui2.game)
gui2._start_shuffle_demo(take, pre2, final2, ('演示完成', 60))
check('T4 短記錄啓動且不求淡出',
      gui2._shuffle_demo_active and not gui2._shuffle_demo_need_fade)
frames = run_demo_until_done(gui2)
check('T4 演完即終態、無淡出',
      not gui2._shuffle_demo_active and positions(gui2.game) == final2,
      f'{frames} 幀')
check('T4 結束後 animating 復位',
      not gui2.animating and not gui2.anim_blocks)

# ================================================================ T5 中斷對齊
print()
print("=" * 60)
print("T5 演示中斷對齊終態")
print("=" * 60)

gui3 = make_gui()
gui3.animation_duration = 20
gui3.SHUFFLE_DEMO_STEPS = 2
random.seed(11)
with_truncated_records(gui3, 3, gui3.shuffle_puzzle)
final3 = [list(p) for p in gui3._shuffle_demo_final]
check('T5 演示進行中', gui3._shuffle_demo_active)
gui3._abort_shuffle_demo()
check('T5 中斷後棋盤=終態',
      positions(gui3.game) == [tuple(p) for p in final3])
check('T5 中斷後狀態全清', not gui3._shuffle_demo_active
      and not gui3.animating and gui3._shuffle_demo_queue == [])

# ================================================================ T6 換盤失效
print()
print("=" * 60)
print("T6 演示中換盤（身份錨失效）")
print("=" * 60)

gui4 = make_gui()
gui4.animation_duration = 20
gui4.SHUFFLE_DEMO_STEPS = 2
random.seed(13)
with_truncated_records(gui4, 3, gui4.shuffle_puzzle)
check('T6 演示進行中', gui4._shuffle_demo_active)
new_game = SliderMatrix(4, 4)
new_game.shuffle(30, 2)
new_positions = positions(new_game)
gui4.game = new_game                      # 模擬切換謎題/載入
gui4._update_shuffle_demo()
check('T6 換盤後演示只清狀態', not gui4._shuffle_demo_active)
check('T6 換盤後不碰新棋盤', positions(gui4.game) == new_positions)

# ================================================================ T7 門控
print()
print("=" * 60)
print("T7 門控：plain 模式 / 動畫關閉")
print("=" * 60)

gui5 = make_gui()
gui5.ui_mode = 'plain'
random.seed(3)
gui5.shuffle_puzzle()
check('T7 plain 模式不演示', not gui5._shuffle_demo_active)
check('T7 plain 模式棋盤即終態（=快照）',
      gui5.game_history.history[0]['matrix'] == board_matrix(gui5.game))
check('T7 plain 模式通知立即發', gui5.macro_notify_timer > 0)

gui6 = make_gui()
gui6.animation_enabled = False
random.seed(5)
gui6.shuffle_puzzle()
check('T7 動畫關閉不演示', not gui6._shuffle_demo_active)
check('T7 動畫關閉通知立即發', gui6.macro_notify_timer > 0)

# ================================================================ T8 打亂中 xx% 進度
print()
print("=" * 60)
print("T8 「打亂中 xx%」進度（切屏瞬間正好 100%）")
print("=" * 60)

gui7 = make_gui()
gui7.animation_duration = 20
gui7.SHUFFLE_FADE_MS = 2
gui7.SHUFFLE_DEMO_STEPS = 2           # 3 條記錄 > 2 → 截斷 + 淡出
random.seed(17)
with_truncated_records(gui7, 3, gui7.shuffle_puzzle)
check('T8 演示已啓動', gui7._shuffle_demo_active)
# 啓動即播第一步（_start_shuffle_demo 尾部直接開播），故初始進度=1/total
check('T8 啓動後第一步已計入進度',
      0.0 < gui7._shuffle_demo_progress <= 1.0,
      f'progress={gui7._shuffle_demo_progress}')

# 逐幀驅動，捕捉「fade_out → fade_in」切換的那一幀（=切屏瞬間）
prog_at_switch = None
switch_ok = False
frames = 0
prev_phase = gui7._shuffle_demo_phase
monotonic = True
last_p = -1.0
while getattr(gui7, '_shuffle_demo_active', False) and frames < 3000:
    if gui7.animating:
        gui7.anim_start_time = pygame.time.get_ticks() - gui7.animation_duration - 5
    if gui7._shuffle_demo_phase in ('fade_out', 'fade_in'):
        gui7._shuffle_fade_last_ms -= 20
    gui7.update_animation()
    gui7._update_shuffle_demo()
    p = gui7._shuffle_demo_progress
    # 收尾復位（_clear_demo_state 歸 0）不算「遞減」：演示已結束
    if p < last_p - 1e-9 and gui7._shuffle_demo_active:
        monotonic = False
    last_p = p
    if gui7._shuffle_demo_phase != prev_phase:
        if prev_phase == 'fade_out' and gui7._shuffle_demo_phase == 'fade_in':
            prog_at_switch = gui7._shuffle_demo_progress
            switch_ok = True
        prev_phase = gui7._shuffle_demo_phase
    frames += 1

check('T8 捕獲到切屏幀（fade_out→fade_in）', switch_ok, f'{frames} 幀')
check('T8 切屏瞬間進度正好 100%',
      switch_ok and prog_at_switch is not None and prog_at_switch == 1.0
      and int(prog_at_switch * 100) == 100,
      f'progress={prog_at_switch}')
check('T8 播放期進度單調不減', monotonic)
check('T8 結束後進度復位', gui7._shuffle_demo_progress == 0.0)

# 未截斷（短記錄）：演完即 100%（_play_next_shuffle_record 的 else 分支
# 先置 1.0 再收尾復位）——語義由截斷路徑的切屏斷言覆蓋，此處驗渲染在各
# 進度值下不炸（dummy surface 真實走一遍繪製）
gui8 = make_gui()
gui8.animation_duration = 20
gui8.SHUFFLE_DEMO_STEPS = 50
random.seed(23)
pre8 = positions(gui8.game)          # 先取打亂前位置（順序別抄錯）
recs_all = []
gui8.game.shuffle(80, 2, min_score=0.6, record=recs_all)
take = recs_all[:3]
for b, p in zip(gui8.game.blocks, pre8):
    b.location = list(p)
replay(gui8.game, take)
final8 = positions(gui8.game)
gui8._start_shuffle_demo(take, pre8, final8, ('演示完成', 60))
run_demo_until_done(gui8)
for p in (0.0, 0.37, 0.9, 0.99, 1.0):
    gui8._shuffle_demo_active = True
    gui8._shuffle_demo_progress = p
    gui8._shuffle_demo_phase = 'play'
    try:
        gui8.draw_shuffle_progress()
        ok = True
    except Exception as e:
        ok = False
        print('   渲染異常:', e)
    check(f'T8 渲染冒煙 progress={p:.2f}', ok)
gui8._clear_demo_state()

# ================================================================ 匯總
print("\n" + "=" * 60)
if _failures:
    print(f"[FAIL] {len(_failures)} 項未通過：")
    for name in _failures:
        print(f"   - {name}")
    sys.exit(1)
print("[OK] 打亂演示動畫全部通過")
