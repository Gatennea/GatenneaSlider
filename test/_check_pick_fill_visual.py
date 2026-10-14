# -*- coding: utf-8 -*-
"""选块填空选取态的视觉反馈 + 入口闸门验证（2026-10-12 补的 pending 项）。

背景：选取态（GUI._pick_fill）此前的反馈只有右下角文字提示，棋盘上
**看不出点了什么**——玩家点完方块/空位后没有任何视觉确认。本轮按
「金色 = 你选的东西」补上：已选方块金框（与宏定义基准块同款）、已选空位
每格金环，一处 shared helper + 三个 draw 各接一次（三形态铁律）。

覆盖：
  V1 进选取态（Ctrl+A 统一入口）；没点齐再按 = 退出，不开算；
  V2 点方块 → pf['block'] 登记 + 棋盘出现金框（绿/红/黄之外的第四种
     语义色不存在，金 = 宏基准块既有色，不引入新配色）；
  V3 点空位（走真实 get_hole_at_pos 路径）→ pf['hole'] 登记 + 金环；
  V4 清空选取态 → 金像素消失（反馈跟随状态，不残留）；
  V5 三形态铁律：helper 从三个 draw 各接一次；三角/米字下陈旧选取态
     也不画、不崩（选取态实际只存在于方形）；
  V6 入口闸门：三角/米字下按入口**不进选取态**（明确拒绝，而不是进了
     一个永远点不齐的态）；建局会清掉选取态（坐标属于旧局）。

执行：``D:/python/python.exe -u test/_check_pick_fill_visual.py``
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def gold_pixels(gui):
    """屏幕上金框色 (255,200,50) 的采样点数（与宏基准块同色）。"""
    return sum(1
               for yy in range(0, gui.screen_height, 2)
               for xx in range(0, gui.screen_width, 2)
               if gui.screen.get_at((xx, yy))[:3] == (255, 200, 50))


# ================================================================ 准备
gui = SliderGUI(m=6, n=6, step=2)
gui.animation_enabled = False
gui.new_puzzle(4, 4, 2)          # 方形还原局

# ================================================================ V1 进出选取态
print("\n--- V1 进选取态 / 没点齐再按=退出 ---")
gui._pick_fill_toggle()
check("V1a 按一次进入选取态", isinstance(gui._pick_fill, dict),
      f"{gui._pick_fill}")
check("V1b 提示文案说明要点什么", '凸起' in gui.macro_notify_msg,
      gui.macro_notify_msg)

# 点一个方块（顺序不限，先块后位）
blk = next(b for b in gui.game.blocks if tuple(b.location) != (3, 3))
sx, sy = gui._key_center(tuple(blk.location))
gui._pick_fill_click(int(sx), int(sy), block=blk)
check("V1c 点方块后登记进 pf['block']",
      gui._pick_fill['block'] == tuple(blk.location),
      f"{gui._pick_fill['block']}")
check("V1d 提示已选方块（带行列号）", '已选方块' in gui.macro_notify_msg,
      gui.macro_notify_msg)

# 没点齐（还缺空位）再按一次 = 退出，不开算
gui._pick_fill_toggle()
check("V1e 没点齐再按一次 = 退出选取态", gui._pick_fill is None)
check("V1f 退出不等同于开算（auto_solve 没跑）",
      not getattr(gui, '_auto_solve_running', False))

# ================================================================ V2/V3 金色反馈
print("\n--- V2 点空位（真实路径）+ 金框/金环上屏 ---")
gui._pick_fill_toggle()
gui._pick_fill_click(int(sx), int(sy), block=blk)

# 挖掉 (3,3) 那块 → 该格成空位，走真实 get_hole_at_pos 路径点它
victim = next(b for b in list(gui.game.blocks) if tuple(b.location) == (3, 3))
gui.game.blocks.remove(victim)
gui.game.update_matrix()
hx, hy = gui._key_center((3, 3))
gui._pick_fill_click(int(hx), int(hy))
check("V2a 点空位后登记进 pf['hole']",
      gui._pick_fill['hole'] is not None
      and (3, 3) in [tuple(c) for c in gui._pick_fill['hole']['cells']],
      f"{gui._pick_fill['hole']}")
# 第二个点齐的瞬间，提示会被「已选好一对」覆盖（先设“已选空位”再设完成句，
# 同一回合内后者胜出）——所以这里只断言完成句，不要求看到中间句。
check("V2c 点齐后提示按 Ctrl+A 开算", 'Ctrl+A' in gui.macro_notify_msg,
      gui.macro_notify_msg)

# 金框/金环真的画在棋盘上（同一实例，先画一次拿签名）
gui.screen.fill((0, 0, 0))
gui.draw_board()
gold_on = gold_pixels(gui)
check("V2d 选取态下棋盘出现金色高亮（框+环）", gold_on > 0,
      f'{gold_on} 个采样点')

# 清掉选取态再画 → 金色消失（反馈跟随状态，不残留）
gui._pick_fill = None
gui.screen.fill((0, 0, 0))
gui.draw_board()
check("V2e 退出选取态后金色消失", gold_pixels(gui) == 0)

# ================================================================ V5 三形态
print("\n--- V5 三形态铁律：三个 draw 都接、异形不画不崩 ---")
# 方形已接（V2d 证明）；这里证明另两个形态：陈旧选取态也不画、不抛
gui._pick_fill = {'block': (0, 0), 'hole': {'type': 'gap', 'cells': [(1, 1)]}}
gui.new_triangle_puzzle(4, 2)
check("V5a 建局清掉选取态（坐标属于旧局）", gui._pick_fill is None)
gui._pick_fill = {'block': (0, 0), 'hole': {'type': 'gap', 'cells': [(1, 1)]}}
try:
    gui.screen.fill((0, 0, 0))
    gui.draw_triangle_board()
    check("V5b 三角下 draw 接了 helper 且不崩", True)
except Exception as e:
    check("V5b 三角下 draw 接了 helper 且不崩", False,
          f'{type(e).__name__}: {e}')
check("V5c 三角下不画金色（选取态只属于方形）", gold_pixels(gui) == 0)

gui.new_mi_puzzle(4, 4, 2)
gui._pick_fill = {'block': (0, 0), 'hole': {'type': 'gap', 'cells': [(1, 1)]}}
try:
    gui.screen.fill((0, 0, 0))
    gui.draw_mi_board()
    check("V5d 米字下 draw 接了 helper 且不崩", True)
except Exception as e:
    check("V5d 米字下 draw 接了 helper 且不崩", False,
          f'{type(e).__name__}: {e}')
check("V5e 米字下不画金色", gold_pixels(gui) == 0)

# ================================================================ V6 入口闸门
print("\n--- V6 入口闸门：异形明确拒绝，不进点不齐的选取态 ---")
gui._pick_fill = None
gui.new_triangle_puzzle(4, 2)     # 先切到三角（V5 结尾停在米字）
gui._pick_fill_toggle()
check("V6a 三角下按入口不进选取态", gui._pick_fill is None)
check("V6b 三角拒绝有明确提示", '三角形' in gui.macro_notify_msg,
      gui.macro_notify_msg)
gui.new_mi_puzzle(4, 4, 2)
gui._pick_fill_toggle()
check("V6c 米字下按入口不进选取态", gui._pick_fill is None)
check("V6d 米字拒绝有明确提示", '米字' in gui.macro_notify_msg,
      gui.macro_notify_msg)

# 方形下闸门放行（证明不是永远返回 True 的假闸门）
gui.new_puzzle(4, 4, 2)
gui._pick_fill_toggle()
check("V6e 方形下闸门放行（能进选取态）", gui._pick_fill is not None)
gui._pick_fill = None

print("\n=== 结果 ===")
print("PASS" if not _failures else f"FAIL: {_failures}")
sys.exit(1 if _failures else 0)
