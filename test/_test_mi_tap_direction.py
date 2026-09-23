# -*- coding: utf-8 -*-
"""米字格第二下觸控定向：正對齊不再整手拒絕，只把滑塊組留給虛擬鍵盤。

用戶回報（2026-09-22）：「縫隙貫穿判定不完善，新建的 mi-1-2-2 存檔最後一個
狀態按理來說橫豎縫都能選中，實際被拒絕」。複查結論分兩半：

  1. 縫隙有效性（「線不嚴格切進任何一塊 + 兩側非空」）本身是精確的——用
     獨立的三角形內部貫穿判定對拍 2×2 全部 483 個、2×3 全部 2085 個可達
     狀態（h/v 各 21 個線位）零分歧；2×2 沿 d1 走過一格之後橫豎縫是**真的**
     全切在塊裡（E/W 塊整條跨過線），規劃 §1.3 記的退化情形，提示「這條縫
     選不動」是對的。
  2. 誤拒在定向：`_mi_tap_direction` 拿「第二下點 − 第一下點」的切向符號定
     方向，符號為 0 就整手拒絕；而「點縫 → 點它正下方那塊」這個最自然的手勢
     切向偏移恰好是 0（新建 2×2 上實測 700 次兩次觸控有 105 次栽在這）。
     法向校驗（「塊所在側與偏移指向要一致」）不會誤觸發：能走到「點塊」這個
     分支的點一定在所有單位邊一個瞄準容差之外（否則 gap_at 先把它判成點縫），
     而縫線正是塊的邊，所以法向符號必然與所點塊同側。

本文件守四件事：
  1. 兩下正對齊（切向偏移 0）與幾乎正對齊（< 瞄準容差）：不整手拒絕，
     滑塊組留在選中態、提示改用虛擬鍵盤給方向，且隨後按方向鍵確能移動；
  2. 方向只由切向符號決定：點在塊左邊那側縫 → 'd' 右移，右邊 → 'a' 左移，
     豎縫同理（縫在塊上方 → 's' 下移）；
  3. 靠近縫（離縫 15px，瞄準容差之外一點）的塊也照常移動；
  4. 對齊態提示逐字不變（選縫/選組/移動失敗那一套照舊）。

坐標說明：縫線與塊內點都按「格座標 → 世界像素」取，第二下統一落在塊內心
（離每條單位邊 = cell_size*0.207 ≈ 12px，遠超瞄準容差 cell_size/12 = 5px），
方向上用「第一下沿縫線錯開 15px」來給——這樣切向偏移遠遠大於容差，
而第二下仍是百分之百的「點塊」。位移按塊物件比對前後位置得出。

执行：python test/_test_mi_tap_direction.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def click_grid(gx, gy):
    """格座標 → 屏幕坐标點擊（與玩家看到的位置一致）。"""
    sx, sy = gui.world_to_screen(*view.to_world(gx, gy))
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {'button': 1, 'pos': (int(round(sx)), int(round(sy)))}))
    gui.handle_events()


def keys():
    """全部 (r, c, q) 的有序表：比對「盤面有沒有變」用。"""
    return sorted(tuple(mi_key(b)) for b in gui.game.blocks)


def snap_ids():
    """塊物件 → (r, c, q)。物件身份不會因移動而變，才能推出位移。"""
    return {id(b): tuple(mi_key(b)) for b in gui.game.blocks}


def mi_key(b):
    return (b.location[0], b.location[1], b.location[2])


def move_delta(before, after):
    """比對同一批塊物件的前後位置，推出這一次滑動的 (dr, dc)；
    沒動、或各塊位移不一致時回 None。"""
    moved = [k for k in before if k not in after or after[k] != before[k]]
    if not moved or any(k not in after for k in moved):
        return None
    deltas = {(round(after[k][0] - before[k][0], 3),
               round(after[k][1] - before[k][1], 3)) for k in moved}
    return deltas.pop() if len(deltas) == 1 else None


def fresh():
    """回到建局面，並清掉選中態。"""
    gui.new_mi_puzzle(6, 6, 1)
    gui.selected_gap = None
    gui.selected_block = None
    gui._mi_gap_point = None
    gui.macro_notify_msg = ''


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False        # 無頭只讀陷阱：載入後 new_puzzle 會靜默失敗
view = gui._mi_view()
fresh()
BASE = keys()

# 等腰直角塊的內心距斜邊 = (√½+√½−1)/2 = 0.2071 格（≈ cell_size 的 12%），
# 比 gap_at 的瞄準容差 cell_size/12 = 5px 大一倍多，所以「點內心」必被算成點塊。
INRADIUS = 2 ** 0.5 / 2 - 0.5
# 橫縫 h line=2 在幾何上是 y=3；縫下方 cell (3,2) 的 N 塊貼著縫
HSEAM = 3.0
CENTER = (2.5, HSEAM + INRADIUS)        # N 塊內心 = 可靠的「點塊」位置
NEAR = (2.5, HSEAM + 15.0 / view.cell_size)  # 同一塊裡離縫 15px 的點
LATERAL = 15.0 / view.cell_size         # 第一下沿縫線錯開 15px
# 豎縫 v line=2 在幾何上是 x=3；縫右側 cell (2,3) 的 W 塊
VSEAM = 3.0
V_CENTER = (VSEAM + INRADIUS, 2.5)      # W 塊內心

print("== 1. 兩下正對齊：不整手拒絕，留給虛擬鍵盤給方向 ==")
fresh()
click_grid(2.5, HSEAM)
check("第一下選中橫縫", gui.selected_gap == ('h', 2), str(gui.selected_gap))
click_grid(*CENTER)
check("第二下沒有移動任何一塊", keys() == BASE)
check("滑塊組留在選中態（be_opted 非空）",
      any(b.be_opted for b in gui.game.blocks))
check("提示指向虛擬鍵盤",
      '虚拟键盘' in gui.macro_notify_msg, repr(gui.macro_notify_msg))
ok = gui.move_selected_blocks('d', 1)
check("隨後按方向鍵確能移動", ok and keys() != BASE, str(gui.macro_notify_msg))

print("== 2. 兩下幾乎正對齊（偏移 < 瞄準容差）：同樣兜底 ==")
fresh()
click_grid(2.5, HSEAM)
click_grid(2.5 + 2.0 / view.cell_size, CENTER[1])
check("沒有移動", keys() == BASE)
check("同樣留選中態 + 鍵盤兜底",
      any(b.be_opted for b in gui.game.blocks)
      and '虚拟键盘' in gui.macro_notify_msg, repr(gui.macro_notify_msg))

print("== 3. 靠近縫的塊也照常移動（離縫 15px，容差之外） ==")
fresh()
click_grid(2.5 - LATERAL, HSEAM)
check("第一下選中橫縫", gui.selected_gap == ('h', 2), str(gui.selected_gap))
before = snap_ids()
click_grid(*NEAR)
after = snap_ids()
check("貼著縫點的塊照常移動",
      after != before, f"提示={gui.macro_notify_msg!r}")
check("位移是橫向一格（縫在塊左邊 → 右移 'd'）",
      move_delta(before, after) == (0, 1), str(move_delta(before, after)))

print("== 4. 方向只由切向符號決定 ==")
for shift, want, label in ((-LATERAL, (0, 1), "縫在塊左邊 → 右移"),
                           (LATERAL, (0, -1), "縫在塊右邊 → 左移")):
    fresh()
    click_grid(2.5 + shift, HSEAM)
    check("第一下選中橫縫", gui.selected_gap == ('h', 2), str(gui.selected_gap))
    before = snap_ids()
    click_grid(*CENTER)
    after = snap_ids()
    check(f"橫縫{label}", move_delta(before, after) == want,
          f"位移={move_delta(before, after)} 提示={gui.macro_notify_msg!r}")

print("== 5. 豎縫正對齊也走兜底，不拒絕 ==")
fresh()
click_grid(VSEAM, 2.5)
check("第一下選中豎縫", gui.selected_gap == ('v', 2), str(gui.selected_gap))
click_grid(*V_CENTER)
check("正對齊不整手拒絕",
      '虚拟键盘' in gui.macro_notify_msg, repr(gui.macro_notify_msg))
check("滑塊組留在選中態", any(b.be_opted for b in gui.game.blocks))
before = snap_ids()
ok = gui.move_selected_blocks('s', 1)
check("按方向鍵能移動", ok and move_delta(before, snap_ids()) == (1, 0),
      str(move_delta(before, snap_ids())))

print("== 6. 豎縫方向由切向符號決定（縫在塊上方 → 下移） ==")
fresh()
click_grid(VSEAM, 2.5 - LATERAL)
check("第一下選中豎縫", gui.selected_gap == ('v', 2), str(gui.selected_gap))
before = snap_ids()
click_grid(*V_CENTER)
after = snap_ids()
check("豎縫縫在塊上方 → 下移", move_delta(before, after) == (1, 0),
      f"位移={move_delta(before, after)} 提示={gui.macro_notify_msg!r}")

print()
if _failures:
    print(f"FAIL {len(_failures)} 项: " + "; ".join(_failures))
    sys.exit(1)
print("mi tap_direction PASS")
pygame.quit()
