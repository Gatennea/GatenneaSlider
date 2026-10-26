# -*- coding: utf-8 -*-
"""回归：谜题菜单重设计（用户 2026-10-26 晚）。

用户定的三条：
  1. 菜单条目行尾加「删除预设」——能删**模型谜题**（models/*.json，含随包的
     碎三角）与**自定义预设**（design_styles/*.json）；内置档位没有文件，
     所以不画删除键。直删 + 确认弹窗。
  2. 自定义对话框加「高级选项…」：按对话框参数开一局，然后进设计画布。
  3. 「捆绑谜题」不做成第四个平行子菜单，而是菜单里的**一段分组**：
     带粘连的样式归到「捆绑谜题」，其余留在「自定义还原态」。

本测试钉住：
  A. 可删判定：模型条目按「模型名」认（不是显示文本「碎三角（48 块）」）、
     样式条目按预设名认；内置档位 / 分组标题 / 分隔线 / 当前行一律 None。
  B. 当前局不许删（模型局的那道模型、样式局的那个样式）。
  C. 删除必须先过确认：点 ✕ 只弹框、不删；取消不删；确认才删，且菜单立刻少一行。
  D. 删模型是「删文件 → 摘板型 → 清缩图」三步，少一步就是死条目 / 孤儿图。
  E. 分组：带 groups 的样式在「捆绑谜题」下，不带的在「自定义还原态」下。
  F. 自定义对话框的「高级选项…」：按钮在、点了进设计视图、原「确定」不受影响。
  G. 带粘连的局不进竞速（竞速只记哪些格子有块，还原不出同一题）。

跑法：D:/python/python.exe test/_test_menu_redesign.py
"""
import json
import os
import shutil
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
from engine import model_registry  # noqa: E402
from gui import design_styles  # noqa: E402
from gui import menu_delete  # noqa: E402

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


def make_gui(config_dir):
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_puzzle(4, 4, 1)
    # 隔离配置目录：删除会真删文件，绝不能碰仓库里那份
    gui.config_dir = config_dir
    gui.temp_history_path = os.path.join(config_dir, 'temp_history.json')
    gui._refresh_puzzle_presets()
    return gui


def draw_menu(gui, sub=''):
    gui.show_puzzle_menu = True
    gui.puzzle_sub_open = sub
    gui.puzzle_sub_hovered = -1
    gui.puzzle_menu_hovered = -1
    gui.draw_menu_bar()
    gui.draw_puzzle_menu()


def draw_confirm(gui):
    gui.draw_confirm_dialog()


def click(gui, rect):
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)
    gui.handle_confirm_dialog_events(ev)


TMP = tempfile.mkdtemp(prefix='gs_menu_redesign_')
STYLES = os.path.join(TMP, design_styles.STYLES_SUBDIR)
os.makedirs(STYLES, exist_ok=True)


def put_style(name, cells, groups):
    data = {'version': 1, 'name': name, 'm': 4, 'n': 4, 'step': 1,
            'cells': [list(c) for c in cells], 'groups': groups}
    with open(os.path.join(STYLES, f'{name}.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


CELLS4 = [[r, c] for r in range(4) for c in range(4)]
put_style('zz_bundled', CELLS4, {'0,0': 1, '0,1': 1})
put_style('zz_plain', CELLS4, {})

print('=' * 60)
print('A. 可删判定')
# ---------------------------------------------------------------- A
t_m = menu_delete.item_target(('碎三角（48 块）', 4, 4, 1, 'shatter'))
check(t_m is not None and t_m['kind'] == 'model' and t_m['key'] == 'shatter',
      'A1 模型条目 → kind=model，key 是模型名（不是带块数的显示文本）', f'{t_m}')

t_s = menu_delete.item_target(('zz_bundled', '__custom__', 'zz_bundled'))
check(t_s is not None and t_s['kind'] == 'style' and t_s['key'] == 'zz_bundled',
      'A2 自定义预设条目 → kind=style', f'{t_s}')

for item, label in (
        (('6×6 等级2', 6, 6, 2), '方形档位'),
        (('边长4 等级1', 4, 4, 1, 'triangle'), '三角档位'),
        (('4×4 等级2', 4, 4, 2, 'mi'), '米字档位'),
        (('8×8 等级2', 8, 8, 2, 'numbered'), '数字档位'),
        (('快速开始：矩形 6×6 等级2', 6, 6, 2), '快速开始'),
        (('__group__', '捆绑谜题'), '分组标题'),
        (('---',), '分隔线'),
        (('__current__',), '当前行'),
):
    check(menu_delete.item_target(item) is None, f'A3 {label}：无文件 → 不可删')

print('=' * 60)
print('B. 当前局不许删')
# ---------------------------------------------------------------- B
gui = make_gui(TMP)
models = sorted(model_registry.loaded())
if models:
    victim = models[0]
    gui.new_model_puzzle(victim, 1)
    item_cur = (f'{model_registry.loaded(victim).title}（1 块）', 4, 4, 1, victim)
    check(gui._menu_item_deletable(item_cur) is None,
          f'B1 正在玩的模型「{victim}」不显示删除键')
    others = [n for n in models if n != victim]
    if others:
        other = (f'{model_registry.loaded(others[0]).title}', 4, 4, 1, others[0])
        check(gui._menu_item_deletable(other) is not None,
              'B2 别的模型仍可删')
else:
    check(False, 'B 前置：注册表里没有任何模型（测试环境异常）')

gui.new_puzzle(4, 4, 1)
gui._ann_design_start_style('zz_bundled')
check(getattr(gui, '_ann_style_goal', None) == 'zz_bundled', 'B3 前置：样式局已开')
check(gui._menu_item_deletable(('zz_bundled', '__custom__', 'zz_bundled')) is None,
      'B4 正在玩的样式不许删')

print('=' * 60)
print('C. 删除必须过确认（样式，真实临时目录）')
# ---------------------------------------------------------------- C
gui.new_puzzle(4, 4, 1)
gui._refresh_puzzle_presets()
path_b = os.path.join(STYLES, 'zz_bundled.json')
check(os.path.exists(path_b), 'C1 前置：样式文件存在')

draw_menu(gui)
names = [p[0] for p in gui.puzzle_presets
         if len(p) == 3 and p[1] == '__custom__']
check('zz_bundled' in names and 'zz_plain' in names, 'C2 两个样式都进了菜单')

hits = gui.puzzle_menu_delete_hits
hit_names = [p[2] for _r, p in hits if len(p) == 3 and p[1] == '__custom__']
check('zz_bundled' in hit_names, 'C3 样式条目行尾有删除键（✕）', f'{hit_names}')
check(all(r.width <= 20 for r, _p in hits), 'C4 ✕ 的命中区是小方块，不是整行')

gui._request_delete_preset(('zz_bundled', '__custom__', 'zz_bundled'))
check(gui.show_confirm_dialog is True, 'C5 点 ✕ 只弹确认框')
check(os.path.exists(path_b), 'C6 还没删：文件仍在')

draw_confirm(gui)
click(gui, gui.confirm_cancel_btn)
check(gui.show_confirm_dialog is False, 'C7 取消 → 确认框关闭')
check(os.path.exists(path_b), 'C8 取消 → 文件没删')

gui._request_delete_preset(('zz_bundled', '__custom__', 'zz_bundled'))
draw_confirm(gui)
click(gui, gui.confirm_ok_btn)
check(not os.path.exists(path_b), 'C9 确认 → 文件真的删了')
check(gui.show_confirm_dialog is False, 'C10 确认后确认框关闭')
after = [p[0] for p in gui.puzzle_presets
         if len(p) == 3 and p[1] == '__custom__']
check('zz_bundled' not in after and 'zz_plain' in after,
      'C11 菜单立刻少一行（不用重开游戏）', f'{after}')
check('已删除' in (gui.macro_notify_msg or ''), 'C12 有给玩家看的删除说明',
      f'{gui.macro_notify_msg!r}')

print('=' * 60)
print('D. 删模型：删文件 → 摘板型 → 清缩图')
# ---------------------------------------------------------------- D
fake_file = os.path.join(TMP, 'zz_model.json')
with open(fake_file, 'w', encoding='utf-8') as f:
    f.write('{}')

_real_path = menu_delete.model_path
_real_unreg = model_registry.unregister
_calls = []


def _fake_unreg(name):
    _calls.append(name)


menu_delete.model_path = lambda key: fake_file
model_registry.unregister = _fake_unreg
try:
    ok, msg = menu_delete.remove(
        {'kind': 'model', 'key': 'zz_model', 'label': '测试模型'}, TMP)
finally:
    menu_delete.model_path = _real_path
    model_registry.unregister = _real_unreg

check(ok, 'D1 删除返回成功', f'{ok} {msg}')
check(not os.path.exists(fake_file), 'D2 模型文件被删掉')
check(_calls == ['zz_model'], 'D3 删完必须摘板型（否则菜单留死条目）', f'{_calls}')

model_registry._LOADED['zz_fake'] = object()
model_registry.unregister('zz_fake')
check('zz_fake' not in model_registry.loaded(),
      'D4 unregister 真能把板型从内存里摘掉')

print('=' * 60)
print('E. 捆绑谜题 = 菜单里的一段分组')
# ---------------------------------------------------------------- E
put_style('zz_bundled2', CELLS4, {'1,1': 1, '1,2': 1})
gui.new_puzzle(4, 4, 1)
gui._refresh_puzzle_presets()
seq = [(p[0], p[1] if len(p) == 2 and p[0] == '__group__' else None)
       for p in gui.puzzle_presets]
titles = [t for _n, t in seq if t]
check('捆绑谜题' in titles, 'E1 有「捆绑谜题」分组标题', f'{titles}')
check('自定义还原态' in titles, 'E2 有「自定义还原态」分组标题', f'{titles}')

idx_b = next(i for i, (n, t) in enumerate(seq) if t == '捆绑谜题')
idx_p = next(i for i, (n, t) in enumerate(seq) if t == '自定义还原态')
bundle_rows = [n for n, t in seq[idx_b + 1:idx_p] if n and t is None]
plain_rows = [n for n, t in seq[idx_p + 1:] if n and t is None]
check('zz_bundled2' in bundle_rows, 'E3 带粘连的样式在「捆绑谜题」下', f'{bundle_rows}')
check('zz_plain' in plain_rows and 'zz_bundled2' not in plain_rows,
      'E4 不带粘连的样式在「自定义还原态」下', f'{plain_rows}')

print('=' * 60)
print('F. 自定义对话框的「高级选项…」')
# ---------------------------------------------------------------- F
gui.new_puzzle(4, 4, 1)
gui.show_custom_dialog = True
gui.custom_kind = 'rect'
gui.custom_fields = {'m': '5', 'n': '5', 'step': '1'}
gui.custom_error = ''
pygame.display.get_surface()
gui.draw_custom_puzzle_dialog()
check(hasattr(gui, 'custom_adv_btn'), 'F1 对话框里有「高级选项…」按钮')
check(gui.custom_adv_btn.right < gui.custom_ok_btn.left,
      'F2 三个按钮不重叠（高级选项 / 确定 / 取消）')

ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                        pos=gui.custom_adv_btn.center)
gui.handle_custom_dialog_events(ev)
check(gui.show_custom_dialog is False, 'F3 点了会关掉对话框')
check(getattr(gui, '_ann_view', '') == 'design', 'F4 直接进设计画布',
      f'{getattr(gui, "_ann_view", None)!r}')
check((gui.current_m, gui.current_n, gui.current_step) == (5, 5, 1),
      'F5 按对话框里的尺寸/等级开的局',
      f'{(gui.current_m, gui.current_n, gui.current_step)}')
gui._ann_cancel_session('测试收摊')

# 原「确定」不受影响
gui.new_puzzle(4, 4, 1)
gui.show_custom_dialog = True
gui.custom_fields = {'m': '6', 'n': '6', 'step': '2'}
gui.custom_error = ''
gui.draw_custom_puzzle_dialog()
gui.handle_custom_dialog_events(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, button=1, pos=gui.custom_ok_btn.center))
check((gui.current_m, gui.current_n, gui.current_step) == (6, 6, 2),
      'F6 「确定」照旧只开一局、不进设计',
      f'{(gui.current_m, gui.current_n, gui.current_step)} ann={gui._ann_view}')

print('=' * 60)
print('G. 带粘连的局不进竞速')
# ---------------------------------------------------------------- G
gui.new_puzzle(4, 4, 1)
check(gui.mode_allowed('timed') is True, 'G1 前置：干净方形局可以竞速')
gui._ann_design_start_style('zz_bundled2')
check(getattr(gui, '_ann_style_goal', None) == 'zz_bundled2', 'G2 前置：粘连样式局已开')
check(gui.mode_allowed('timed') is False, 'G3 带粘连 → 竞速被拒')
ok = gui.set_game_mode('timed')
check(ok is False and '粘连' in (gui.macro_notify_msg or ''),
      'G4 拒绝了并说清原因（不是点了没反应）', f'{gui.macro_notify_msg!r}')
gui.set_game_mode('practice')
gui.new_puzzle(4, 4, 1)

print('=' * 60)
print('H. 真点一遍：✕ 优先于整行点击')
# ---------------------------------------------------------------- H
gui.new_puzzle(4, 4, 1)
put_style('zz_click', CELLS4, {'2,0': 1, '2,1': 1})
gui._refresh_puzzle_presets()
draw_menu(gui)

hit = next(((r, p) for r, p in gui.puzzle_menu_delete_hits
            if len(p) == 3 and p[2] == 'zz_click'), None)
check(hit is not None, 'H1 前置：找到 zz_click 的 ✕ 命中区')

row_rect = None
for i, p in enumerate(gui.puzzle_presets):
    if len(p) == 3 and p[2] == 'zz_click':
        row_rect = gui.puzzle_menu_rects[i]
check(row_rect is not None, 'H2 前置：找到该行矩形')
check(hit[0].width < row_rect.width / 4,
      'H3 ✕ 命中区远小于整行（不会把整行变成删除键）')

# 点 ✕：应当只弹确认，不开局
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                     pos=hit[0].center))
gui.handle_events()
check(gui.show_confirm_dialog is True, 'H4 点 ✕ → 弹确认框')
check(getattr(gui, '_ann_style_goal', None) != 'zz_click',
      'H5 点 ✕ 不会顺带把这一题开起来')
check(os.path.exists(os.path.join(STYLES, 'zz_click.json')),
      'H6 只弹框、还没删')

# 关掉确认框（取消）
draw_confirm(gui)
click(gui, gui.confirm_cancel_btn)

# 取消后菜单是关着的（弹确认前主动收了），重新展开再点整行
draw_menu(gui)
row_rect = None
for i, p in enumerate(gui.puzzle_presets):
    if len(p) == 3 and p[2] == 'zz_click':
        row_rect = gui.puzzle_menu_rects[i]
check(row_rect is not None, 'H7 取消后菜单能重新展开')

# 点整行左侧文字区：应当正常开局，不弹确认
pygame.event.post(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, button=1,
    pos=(row_rect.x + 20, row_rect.centery)))
gui.handle_events()
check(gui.show_confirm_dialog is False, 'H8 点整行文字 → 不弹确认框')
check(getattr(gui, '_ann_style_goal', None) == 'zz_click',
      'H9 点整行文字 → 正常开这一题',
      f'{getattr(gui, "_ann_style_goal", None)!r}')

print()
print('=' * 60)
if _fail:
    print(f'结果：{len(_fail)} 项失败 / 共 {_ok[0] + len(_fail)} 项')
    for m in _fail:
        print('  -', m)
else:
    print(f'结果：全部通过（{_ok[0]} 项）')

shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if _fail else 0)
