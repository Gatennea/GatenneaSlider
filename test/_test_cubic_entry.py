# -*- coding: utf-8 -*-
"""回归：§54 三维滑块「第 0 步」脚手架（建局 + 菜单入口）。

方案真源 `docs/spec/三维扩展方案_正方体单元_2026-11-17.md` §4 第 0 步：
  ① 补 cubic 的 m/n/d 传参（`create_adapter_puzzle('cubic',3,3,1)` 原抛
     TypeError），② 谜题菜单加「三维谜题 ▸ 1×1×1~3×3×3」入口。
本期**渲染 / 拾取 / 六向操作 / 求解器都还没接**，本测试钉住的是：

  A. 工厂：显式 depth 能建局、块位置是三元组；**缺 depth 抛 TypeError**
     （绝不退化成二维 / 单层）；三维不挂 `k`（防 history 误判成三角）。
  B. 分榜键：`1~cubic3*3*3`；不同层数不共键；缺 depth 的键显式报错。
  C. GUI：`new_cubic_puzzle` 能建局、旗标与 current_depth 就位；
     **真点一遍菜单**（事件队列 → handle_events）也能建出三维局，不是静默兜底。
  D. 1×1×1 这类「一步都动不了」的档位给明确说明，不静默失败。
  D2. 投影渲染接入后：画面真的出现多级明暗（三面可见），背景不糊。
  F. 切回二维清旗标、二维分榜键不受 depth 影响。
  G. 求解入口对三维明确拒绝（不拿二维求解器硬算）。

跑法：D:/python/python.exe test/_test_cubic_entry.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from puzzle_types import create_puzzle, puzzle_key  # noqa: E402
from engine.adapter import create_adapter_puzzle  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return bool(cond)


print('=' * 60)
print('A. 工厂：cubic 要 depth，缺了不许兜底')
g = create_adapter_puzzle('cubic', 3, 3, 1, depth=3)
check(type(g).__name__ == 'EngineGame' and g.kind == 'cubic',
      'cubic 建局走 EngineGame')
check(g.depth == 3, '维度 d 记在 game.depth 上', g.depth)
check(len(g.blocks) == 27, '3×3×3 共 27 块', len(g.blocks))
check(all(len(b.location) == 3 for b in g.blocks), '块位置是三元组 (r,c,d)')
check(not hasattr(g, 'k'), '三维不挂 k（防 history 误判成三角）')

try:
    create_adapter_puzzle('cubic', 3, 3, 1)
    check(False, '缺 depth 应抛 TypeError')
except TypeError as exc:
    check('depth' in str(exc), '缺 depth → TypeError 明示', str(exc))

print('=' * 60)
print('B. 分榜键：必须带层数')
check(puzzle_key(1, 3, 3, kind='cubic', depth=3) == '1~cubic3*3*3',
      '三维分榜键 = 1~cubic3*3*3',
      puzzle_key(1, 3, 3, kind='cubic', depth=3))
check(puzzle_key(1, 3, 3, kind='cubic', depth=2) !=
      puzzle_key(1, 3, 3, kind='cubic', depth=3), '不同层数键不同')
try:
    puzzle_key(1, 3, 3, kind='cubic')
    check(False, 'cubic 缺 depth 的 key 应报错')
except ValueError as exc:
    check('depth' in str(exc), 'cubic 缺 depth 的 key → ValueError', str(exc))
gp = create_puzzle(3, 3, 1, kind='cubic', depth=3)
check(gp.kind == 'cubic' and len(gp.blocks) == 27,
      'create_puzzle(cubic) 直通适配器')

print('=' * 60)
print('C. GUI：建局 + 菜单入口')
pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.animation_enabled = False
gui.tut_show_prompt = False
gui.tutorial_active = False
# 隔离配置目录：测试不许碰仓库里那份 config/temp_history.json（会污染开局形态）
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_entry_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui._readonly = False
gui.save_readonly_flag = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()

check(gui.new_cubic_puzzle(3, 3, 3, 1), 'new_cubic_puzzle(3,3,3,1) 成功')
check(gui.cubic_mode and gui.current_kind == 'cubic',
      'cubic_mode / current_kind 就位')
check(gui.current_depth == 3, 'current_depth = 3', gui.current_depth)
check(len(gui.game.blocks) == 27, 'GUI 局 27 块', len(gui.game.blocks))
check(gui._current_puzzle_key() == '1~cubic3*3*3',
      '当前键带层数', gui._current_puzzle_key())
check('三维' in gui._current_puzzle_label(), '状态行标签写三维',
      gui._current_puzzle_label())

sub = gui.puzzle_sub_presets['cubic']
check(any(len(p) == 6 and p[4] == 'cubic' for p in sub),
      '菜单有 6 元立方体条目', sub)
check(any(p == ('三维谜题 ▸', '__sub__', 'cubic') for p in gui.puzzle_presets),
      '一级菜单有「三维谜题 ▸」')
cur = gui._all_puzzle_items()
hit = next(p for p in cur if len(p) == 6 and p[1] == 3 and p[2] == 3
           and p[5] == 3 and p[3] == 1)
check(gui._preset_is_current(hit), '3×3×3 等级1 被标为当前档', hit)

gui.draw_board()
check(True, 'draw_board（三维占位）不抛异常')

# 真点一遍：打开子菜单 → 点「三维 3×3×3 等级1」→ 必须真建出三维局
gui.new_puzzle(4, 4, 1)
gui.show_puzzle_menu = True
gui.puzzle_sub_open = 'cubic'
gui.puzzle_sub_hovered = -1
gui.puzzle_menu_hovered = -1
gui.draw_menu_bar()
gui.draw_puzzle_menu()
idx = next(i for i, p in enumerate(sub)
           if len(p) == 6 and p[1] == 3 and p[2] == 3 and p[5] == 3
           and p[3] == 1)
rect = gui.puzzle_sub_rects[idx]
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                     pos=rect.center))
gui.handle_events()
check(gui.cubic_mode and gui.current_kind == 'cubic',
      '点菜单真的建出三维局（不是静默兜底）', gui.current_kind)
check(gui.current_depth == 3 and len(gui.game.blocks) == 27,
      '点出来的就是 3×3×3', (gui.current_depth, len(gui.game.blocks)))
check(not gui.show_puzzle_menu, '点完菜单收起')

print('=' * 60)
print('D. 一步都动不了的档位：明说，不静默')
gui.new_cubic_puzzle(1, 1, 1, 1)
check('动不了' in (gui.macro_notify_msg or ''),
      '1×1×1 给出「动不了」说明', gui.macro_notify_msg)

print('=' * 60)
print('D2. 投影渲染真的画出了东西（第 1 步接入后）')
gui._cubic_camera_prefs = {}      # 别继承存档里的姿态：六朝向各带 14° 倾斜才见三面
gui.new_cubic_puzzle(3, 3, 3, 1)
gui._cubic_view(0)
gui.draw_board()
_w, _h = gui.screen_width, gui.screen_height
_probe = {}
for _y in range(0, _h, 5):
    for _x in range(0, _w, 5):
        _c = gui.screen.get_at((_x, _y))[:3]
        _probe[_c] = _probe.get(_c, 0) + 1
_shades = [c for c, n in _probe.items() if n > 200]
check(len(_shades) >= 3, '画面上至少 3 级明暗（三面可见）', _shades)
check(any(c == gui.colors['background'] for c in _probe),
      '背景仍是主题底色（没整屏糊成一块）')
# 正对视角也要能画（不崩、不退回二维分支）
from engine.cubic_camera import CubicCamera  # noqa: E402
gui.cubic_camera = CubicCamera.identity()
gui.draw_board()
check(True, '正对视角 draw_board 不抛异常')

print('=' * 60)
print('E. 切回二维 / 求解拦截')
gui.new_puzzle(4, 4, 2)
check(not gui.cubic_mode, '切回方形清掉 cubic_mode')
check(gui._current_puzzle_key() == '2~4*4', '二维键不变',
      gui._current_puzzle_key())
gui.new_cubic_puzzle(3, 3, 3, 1)
check(gui._cubic_blocked('求解') is True, '三维求解入口被拦截')
check('尚未接入' in (gui.macro_notify_msg or ''), '拦截提示文案可读',
      gui.macro_notify_msg)

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}（{_ok[0]} 项通过，'
      f'{len(_fail)} 项失败）')
if _fail:
    for msg in _fail:
        print('  - ' + msg)
sys.exit(1 if _fail else 0)
