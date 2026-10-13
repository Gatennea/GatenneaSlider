# -*- coding: utf-8 -*-
"""功能检索索引（gui/feature_index.py）回归测试。

锁三件事：
  1. 清单数据完整（字段齐全、id 唯一、形态/模式键合法）—— 表与代码漂移时这里会红；
  2. 口语化查询能命中预期条目 —— 别名表是检索质量的关键，删别名会红；
  3. 每条的「一键到位」目标接得上（settings 打开对应页签 / toggle 真翻转 / 其余不抛）。

执行：``D:/python/python.exe -u test/_test_feature_index.py``
"""
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from gui import feature_index as fi  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


# ================================================================ 1 数据完整性
print("\n--- 1 数据完整性 ---")
ids = [f['id'] for f in fi.FEATURES]
check('条目 id 唯一', len(ids) == len(set(ids)), f'共 {len(ids)} 条')

_KINDS = {'action', 'setting', 'panel', 'puzzle', 'concept', 'link'}
_REQUIRED = ('id', 'name', 'aliases', 'kind', 'place', 'forms', 'modes',
             'howto', 'confusion')
bad = []
for f in fi.FEATURES:
    fid = f.get('id')
    for key in _REQUIRED:
        if key not in f:
            bad.append(f'{fid}:缺{key}')
    if f.get('kind') not in _KINDS:
        bad.append(f"{fid}:kind={f.get('kind')}")
    for fkey in f.get('forms', ()):
        if fkey not in fi.ALL_FORMS:
            bad.append(f'{fid}:形态键{fkey}')
    for mkey in f.get('modes', ()):
        if mkey not in fi.ALL_MODES:
            bad.append(f'{fid}:模式键{mkey}')
check('字段齐全且形态/模式键合法', not bad, '; '.join(bad))

# ================================================================ 2 检索命中
print("\n--- 2 检索命中（玩家口语） ---")
_CASES = (
    ('着色', 'coloring_enabled'),
    ('染色', 'coloring_enabled'),
    ('撤销', 'undo'),
    ('反悔', 'undo'),
    ('打乱', 'shuffle'),
    ('求解', 'auto_solve'),
    ('三角', 'preset_exotic'),
    ('米字', 'preset_exotic'),
    ('怎么用', 'help'),
    ('等级', 'concept_step'),
    ('虚拟键盘', 'virtual_keyboard'),
    ('成绩', 'records_panel'),
    ('宏', 'macro_record'),
    ('空位', 'concept_hole'),
)
for query, want in _CASES:
    hits = [e['id'] for _s, e, _a in fi.search(query)]
    check(f'「{query}」→ {want}', want in hits)

check('空查询返回空结果', fi.search('') == [])
check('无匹配返回空结果', fi.search('zzzz不存在的东西') == [])

# ================================================================ 3 上下文
print("\n--- 3 上下文（当前形态决定可用性） ---")
hits = fi.search('选块填空', form='triangle', mode='practice')
check('三角下「选块填空」标记为不可用',
      bool(hits) and hits[0][1]['id'] == 'pick_fill' and hits[0][2] is False)
hits = fi.search('选块填空', form='square', mode='practice')
check('矩形下「选块填空」标记为可用',
      bool(hits) and hits[0][1]['id'] == 'pick_fill' and hits[0][2] is True)
hits = fi.search('单次触控', form='mi', mode='practice')
check('米字下「单次触控」标记为不可用',
      bool(hits) and hits[0][1]['id'] == 'control_single_touch'
      and hits[0][2] is False)

# 形态键必须覆盖 4 种形态，否则检索结果会漏
_missing_forms = sorted({f for f in fi.ALL_FORMS} - {x for fe in fi.FEATURES for x in fe['forms']})
check('四种形态都至少被一条功能覆盖', not _missing_forms, f'未被覆盖: {_missing_forms}')

# ================================================================ 4 一键到位
print("\n--- 4 一键到位接线 ---")
gui = SliderGUI(m=6, n=6, step=2)
gui.animation_enabled = False
gui.save_readonly_flag = False

_opened_urls = []
_tutorial_starts = []
_orig_open = webbrowser.open
_orig_tut_start = gui._tut_start
webbrowser.open = lambda url, *a, **k: _opened_urls.append(url)
gui._tut_start = lambda *a, **k: _tutorial_starts.append(1)
try:
    for entry in fi.FEATURES:
        kind = entry['action']['type']
        if kind == 'settings':
            tab = entry['action']['tab']
            gui._activate_feature(entry)
            ok = (gui.show_settings_dialog is True
                  and gui.settings_active_tab == tab)
            check(f'{entry["id"]} → 设置·{tab} 页', ok)
            gui.show_settings_dialog = False
        elif kind == 'toggle':
            key = entry['action']['key']
            before = bool(getattr(gui, key, False))
            gui._activate_feature(entry)
            after = bool(getattr(gui, key, False))
            check(f'{entry["id"]} → 切换 {key} 生效', before != after)
            gui._handle_right_panel_switch(key)  # 还原
        else:
            gui._activate_feature(entry)
            check(f'{entry["id"]} → {kind} 不抛异常', True)
finally:
    webbrowser.open = _orig_open
    gui._tut_start = _orig_tut_start

check('官网条目真的调用了浏览器打开',
      bool(_opened_urls) and 'GatenneaSliderWeb' in _opened_urls[-1])
check('教程条目真的走了教程入口', bool(_tutorial_starts))

# ================================================================ 5 渲染不崩
print("\n--- 5 帮助对话框检索态渲染 ---")
import pygame  # noqa: E402

gui.show_help = True
gui.help_query = '着色'
gui.help_scroll_offset = 0
pygame.display.set_mode((1000, 700))
try:
    gui.screen.fill((0, 0, 0))
    gui.draw_help_dialog()
    pygame.display.flip()
    check('有检索词时对话框能画出来', True)
    check('检索结果登记了点击矩形',
          bool(getattr(gui, 'help_result_rects', None)))
except Exception as exc:
    check('有检索词时对话框能画出来', False, repr(exc))

gui.help_query = ''
try:
    gui.screen.fill((0, 0, 0))
    gui.draw_help_dialog()
    pygame.display.flip()
    check('无检索词时仍渲染操作说明全文', True)
except Exception as exc:
    check('无检索词时仍渲染操作说明全文', False, repr(exc))

print()
if _failures:
    print(f"FAILED: {len(_failures)} 项")
    for name in _failures:
        print("  -", name)
    sys.exit(1)
print("ALL PASS")
