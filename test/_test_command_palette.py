# -*- coding: utf-8 -*-
"""命令面板（Ctrl+K）无头测试。

命令面板是「功能可发现性」的主入口，这个测试锁的是几件容易悄悄坏掉的事：

  · 层级：面板开着时键鼠事件**必须被它吃掉**——它是最上层 UI，一旦穿透，
    玩家会「看着面板、操作却落到棋盘上」（本项目历史上出过同类图层错位）。
  · 键盘优先：↑↓ 选择 + 回车执行，且选择索引换词后要夹回合法范围。
  · 上下文：结果必须按当前形态/模式标注可用性（异形搜不支持的算法要标 ✕）。
  · 中文检索：走 TEXTINPUT（IME 组字），不能只支持英文。
  · 鼠标可达：按项目铁律「只用鼠标也能完成一切游戏内操作」，设置下拉菜单
    的「命令面板」项必须真的能点开面板。
"""
import os
import sys
import queue

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame
from GUI import SliderGUI

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def key_down(key, mod=0, unicode=''):
    pygame.event.post(pygame.event.Event(
        pygame.KEYDOWN, key=key, mod=mod, unicode=unicode, scancode=0))


def text_input(text):
    pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=text))


def click(pos, button=1):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=button, pos=pos))


# ---------------------------------------------------------------- 基础设施
gui = SliderGUI(m=3, n=3, step=1, cmd_queue=queue.Queue(),
                ext_state={'enabled': True, 'token': 'T', 'port': 5050})
gui.tut_show_prompt = False
gui.tutorial_active = False
# 会话恢复会读 config/temp_history.json：若上次关窗时停在**模型文件板型**，
# 这里拿到的就是模型局，而模型局按设计会拦下「着色/连锁/复原标记」等开关
# （b0c0d2a），P4b/P4d 会假红。本测试只验面板执行链路，强制回到方形局。
gui.new_puzzle(3, 3, 1)

CTRL = pygame.KMOD_CTRL

print("--- 命令面板：唤起与关闭 ---")
check('P0a 初始未打开', not gui.palette_active)
key_down(pygame.K_k, CTRL, 'k')
gui.handle_events()
check('P0b Ctrl+K 打开面板', gui.palette_active)
gui.draw_command_palette()   # 画一帧，结果矩形才存在

key_down(pygame.K_ESCAPE)
gui.handle_events()
check('P0c Esc 关闭面板', not gui.palette_active)
check('P0d 关闭后清空结果矩形（不留隐形命中区）',
      getattr(gui, 'palette_result_rects', None) == [])

print("\n--- 面板开着时事件不穿透（图层纪律） ---")
gui.open_command_palette()
gui.draw_command_palette()
_before = gui.game.get_blocks_snapshot() if hasattr(gui.game, 'get_blocks_snapshot') else None
# 点面板外的棋盘区域：面板应自己关闭，且这一下**不能**当成棋盘点击走下去
click((60, gui.menu_bar_height + 60))
gui.handle_events()
check('P1a 点击面板外 → 关闭面板', not gui.palette_active)

# 面板开着时按方向键 w（移动方块快捷键）：必须被面板吃掉，不能移动滑块
gui.open_command_palette()
gui.draw_command_palette()
try:
    _blocks_before = sorted(str(b) for b in gui.game.blocks) if hasattr(gui.game, 'blocks') else None
except Exception:
    _blocks_before = None
key_down(pygame.K_w)
gui.handle_events()
check('P1b 面板开着时按键被吃掉（面板仍开着）', gui.palette_active)
if _blocks_before is not None:
    try:
        _blocks_after = sorted(str(b) for b in gui.game.blocks)
    except Exception:
        _blocks_after = _blocks_before
    check('P1c 面板开着时按键未穿透到棋盘（滑块未动）',
          _blocks_before == _blocks_after)

print("\n--- 检索：关键词 → 结果 ---")
gui.open_command_palette()
for ch in '着色':
    text_input(ch)
    gui.handle_events()
gui.draw_command_palette()
check('P2a 中文 TEXTINPUT 能检索（IME 路径）',
      bool(gui.palette_results), f'results={len(gui.palette_results)}')
check('P2b 首条命中最相关（着色 → 分组着色）',
      gui.palette_results and '着色' in gui.palette_results[0][0]['name'],
      str([e['name'] for e, _ in gui.palette_results][:3]))
check('P2c 结果行有可点击矩形',
      len(gui.palette_result_rects) == len(gui.palette_results))

# 无结果（真零命中：search/suggest 全空）
# ⚠️ 必须先摘掉 AI 兜底：is_configured() 默认走作者中转返回 True（任何
# 机器都「已配置」），零命中查询会真的联网——测试不能依赖网络。摘掉后
# 才能确定性验证「结果为空 + 矩形清空」这条路径。
# （旧查询 'zzzz不存在的功能' 不成立：其中的「功能」二字本身就能命中
# 「命令面板（搜索功能）」，search=1，suggest 兜底根本没上场。）
import gui.palette as _pal_mod
from gui import feature_ai as _fai
_ai_orig = _fai.is_configured
_fai.is_configured = lambda: False
try:
    gui.open_command_palette()
    for ch in '鿅鿅':
        text_input(ch)
        gui.handle_events()
    gui.draw_command_palette()
    check('P2d 无匹配时结果为空且不崩', gui.palette_results == [])
    check('P2e 无匹配时清空点击矩形', gui.palette_result_rects == [])
finally:
    _fai.is_configured = _ai_orig

print("\n--- 键盘：↑↓ 选择 + 回车执行 ---")
gui.open_command_palette()
for ch in '求解':
    text_input(ch)
    gui.handle_events()
gui.draw_command_palette()
n = len(gui.palette_results)
check('P3a 有多条结果可供上下选择', n >= 2, f'n={n}')
check('P3b 初始选中第 0 条', gui.palette_sel == 0)
key_down(pygame.K_DOWN)
gui.handle_events()
check('P3c ↓ 移到第 1 条', gui.palette_sel == 1)
key_down(pygame.K_UP)
gui.handle_events()
check('P3d ↑ 回到第 0 条', gui.palette_sel == 0)
key_down(pygame.K_UP)
gui.handle_events()
check('P3e ↑ 在首条回绕到末条', gui.palette_sel == n - 1, f'sel={gui.palette_sel}')
key_down(pygame.K_DOWN)
gui.handle_events()
check('P3f ↓ 在末条回绕到首条', gui.palette_sel == 0)

# 换词后条数变少，索引必须夹回范围（不能指向已不存在的条目）
for _ in range(4):
    key_down(pygame.K_DOWN)
    gui.handle_events()
_sel_before = gui.palette_sel
gui.palette_input.insert_text('聚拢')
gui._pal_run_search()
check('P3g 换词后选择索引夹回合法范围',
      0 <= gui.palette_sel < max(1, len(gui.palette_results)),
      f'before={_sel_before} after={gui.palette_sel} n={len(gui.palette_results)}')

print("\n--- 执行：回车 / 点击 直接到位 ---")
# 用「着色」：动作类型是 toggle，执行后会切换开关，可观测
gui.open_command_palette()
for ch in '着色':
    text_input(ch)
    gui.handle_events()
gui.draw_command_palette()
_coloring_before = getattr(gui, 'coloring_enabled', None)
key_down(pygame.K_RETURN)
gui.handle_events()
check('P4a 回车执行选中项', not gui.palette_active)
check('P4b 执行后确实生效（着色开关被切换）',
      getattr(gui, 'coloring_enabled', None) != _coloring_before,
      f'{_coloring_before} -> {getattr(gui, "coloring_enabled", None)}')

# 点击结果行
gui.open_command_palette()
for ch in '着色':
    text_input(ch)
    gui.handle_events()
gui.draw_command_palette()
_c_before = getattr(gui, 'coloring_enabled', None)
click(gui.palette_result_rects[0][0].center)
gui.handle_events()
check('P4c 点击结果行执行选中项', not gui.palette_active)
check('P4d 点击执行同样生效',
      getattr(gui, 'coloring_enabled', None) != _c_before)

# 设置类动作：跳到对应设置页（验证「先关面板再打开设置」的顺序不会把设置盖住）
# 检索词用清单里真实存在的别名（「聚拢参数」是设置页名，不是功能名，搜不到）
gui.open_command_palette()
for ch in '聚拢':
    text_input(ch)
    gui.handle_events()
gui.draw_command_palette()
_hits = [e for e, _a in gui.palette_results if e['id'] == 'algo_gather']
check('P4e 能搜到求解器类条目', bool(_hits))
if _hits:
    gui.palette_results = [(e, a) for (e, a) in gui.palette_results]
    gui._pal_activate(_hits[0])
    check('P4f 跳转设置页时面板已关（不会盖住设置框）',
          not gui.palette_active and gui.show_settings_dialog)
    check('P4g 落到求解器页', gui.settings_active_tab == 'solver',
          gui.settings_active_tab)
    gui.show_settings_dialog = False

print("\n--- 上下文：形态 / 模式可用性 ---")
gui.open_command_palette()
gui.palette_input.set_text('查表')
gui._pal_run_search()
gui.draw_command_palette()
_sq_hit = [a for e, a in gui.palette_results if e['id'] == 'algo_others']
check('P5a 方形下「查表」可用', bool(_sq_hit) and _sq_hit[0] is True,
      f'results={[(e["id"], a) for e, a in gui.palette_results][:3]}')

# 切到米字格：查表求解不支持异形 → 必须标为不可用，且给出可读原因
gui.close_command_palette()
gui.show_settings_dialog = False
gui.new_mi_puzzle(3, 3, 1)
gui.open_command_palette()
gui.palette_input.set_text('查表')
gui._pal_run_search()
gui.draw_command_palette()
_mi_hit = [a for e, a in gui.palette_results if e['id'] == 'algo_others']
check('P5b 米字格下「查表」标为不可用', bool(_mi_hit) and _mi_hit[0] is False,
      f'results={[(e["id"], a) for e, a in gui.palette_results][:3]}')
from gui import feature_index as _fi
_entry = [e for e, _a in gui.palette_results if e['id'] == 'algo_others']
_reason = _fi.unsupported_reason(_entry[0], gui._feature_form(),
                                 getattr(gui, 'game_mode', 'practice')) if _entry else ''
check('P5c 不可用项给出可读原因（含当前形态名）',
      bool(_reason) and '米字' in _reason, repr(_reason))

print("\n--- 鼠标入口：顶栏「搜索」直接打开命令面板 ---")
gui.close_command_palette()
gui.show_settings_dialog = False
gui.new_puzzle(3, 3, 1)
gui.close_all_menus()
# 顶栏矩形只在完整绘制帧里填充；无头测试须先画一次菜单栏，点击命中才有效。
gui.draw_menu_bar()
# 顶栏「搜索」现在点击即开命令面板（无下拉，单选项不需要下拉）
_search_idx = gui.menu_items.index('搜索')
click(gui.menu_item_rects[_search_idx].center)
gui.handle_events()
check('P6a 顶栏「搜索」点击直接打开命令面板（不依赖键盘）', gui.palette_active)
gui.close_command_palette()

# 菜单结构本身：顶栏有「搜索」、设置下拉已删（死机制），命令面板只在搜索菜单
check('P6b 顶栏含「搜索」菜单且位于「设置」与「帮助」之间',
      gui.menu_items[gui.menu_items.index('设置') + 1] == '搜索'
      and gui.menu_items[gui.menu_items.index('搜索') + 1] == '帮助',
      str(gui.menu_items))
check('P6c 命令面板不在任何「设置」下拉里（死机制已删）',
      not hasattr(gui, 'settings_menu_items'),
      'settings_menu_items 应已不存在')

print("\n--- 清场：不留残留状态 ---")
gui.close_command_palette()
check('P7a 关闭后结果为空', gui.palette_results == [] and gui.palette_result_rects == [])
check('P7b 关闭后输入框失活', gui.palette_input.active is False)
gui.draw_command_palette()   # 空面板也要能画（不崩）
check('P7c 空状态绘制不抛异常', True)

print()
if _failures:
    print(f"FAILED {len(_failures)}: {_failures}")
    sys.exit(1)
print("ALL PASSED")
