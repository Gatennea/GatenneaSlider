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

# ⚠️ 本档会遍历 FEATURES 把**每一条都真的激活一遍**。其中「几何引擎」条目
# 会把开关写进 `config/engine.json`（产品行为：拨过一次就记住），而那份文件
# 是**全局开关**——写成 true 会让同批接着跑的其它测试全部拿到 EngineGame，
# 一齐爆出假失败（实测全套从 7 失败顶到 15~17 失败，且症状全是三角/米字
# GUI 测试崩，看着像引擎有 bug，其实是污染）。故这里把持久化重定向到临时
# 文件，跑完删掉，与 `_test_engine_gui.py` H 节同一招。
import tempfile  # noqa: E402

from engine import config as _ecfg  # noqa: E402

_REAL_CFG_PATH = _ecfg.config_path()
_TMP_CFG = os.path.join(tempfile.gettempdir(),
                        '_gatennea_engine_cfg_featidx.json')
_ecfg.config_path = lambda: _TMP_CFG
_CFG_BACKUP = None
if os.path.isfile(_REAL_CFG_PATH):
    with open(_REAL_CFG_PATH, 'r', encoding='utf-8') as _fp:
        _CFG_BACKUP = _fp.read()

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

# ================================================================ 2b 改进检索（S1/S2/S3）
print("\n--- 2b 改进检索：疑问前缀 / 无空格组合 / 同分精排 ---")
# S2 疑问前缀剥离：『怎么撤销』应剥离成『撤销』命中 undo
hits = [e['id'] for _s, e, _a in fi.search('怎么撤销')]
check('S2「怎么撤销」→ undo（前缀剥离）', 'undo' in hits)
# S2 句尾语气词 + 前缀：『能不能着色吗』→『着色』
hits = [e['id'] for _s, e, _a in fi.search('能不能着色吗')]
check('S2「能不能着色吗」→ coloring_enabled（前缀+语气词）', 'coloring_enabled' in hits)
# S1 无空格组合词：『三角求解』主路失配，模糊兜底应同时命中异形预设与求解相关
hits = [e['id'] for _s, e, _a in fi.search('三角求解')]
check('S1「三角求解」→ preset_exotic（模糊兜底）', 'preset_exotic' in hits)
check('S1「三角求解」→ auto_solve（模糊兜底）', 'auto_solve' in hits)
# S1 无空格组合词：『撤销步』应模糊命中 undo
hits = [e['id'] for _s, e, _a in fi.search('撤销步')]
check('S1「撤销步」→ undo（模糊兜底）', 'undo' in hits)
# S3 同分精排：『求解』精确别名(90)的 auto_solve 应排在前，include(60) 的 algo_others 在后
hits = fi.search('求解')
check('S3「求解」首位 = auto_solve（精确别名优先）',
      bool(hits) and hits[0][1]['id'] == 'auto_solve')
# S3 同分精排：『着色』精确别名(90)的 coloring_enabled 应排首位
hits = fi.search('着色')
check('S3「着色」首位 = coloring_enabled', bool(hits) and hits[0][1]['id'] == 'coloring_enabled')

check('空查询返回空结果', fi.search('') == [])
check('无匹配返回空结果', fi.search('zzzz不存在的东西') == [])

# ================================================================ 2c Phase2：list_all / suggest
print("\n--- 2c Phase2：空查询功能地图 / 零命中相近推荐 ---")
allrows = fi.list_all()
check('list_all 列出全部功能（数量=条目数）',
      len(allrows) == len(fi.FEATURES) and all(isinstance(r, tuple) and len(r) == 2 for r in allrows))
check('list_all 可用项排在不可用之前',
      all(allrows[i][1] >= allrows[i + 1][1] for i in range(len(allrows) - 1)))
# suggest：零命中时给相近推荐（『三角求解』应推荐到异形预设 / 自动求解）
sugg = fi.suggest('三角求解')
sugg_ids = [e['id'] for e, _a in sugg]
check('suggest「三角求解」非空且含 preset_exotic', bool(sugg) and 'preset_exotic' in sugg_ids)
check('suggest「三角求解」含 auto_solve', 'auto_solve' in sugg_ids)
# suggest：垃圾串（无任何模糊重叠）返回空
check('suggest 垃圾串返回空', fi.suggest('zzzz不存在的东西') == [])

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
    # 还原开关文件（见文件头的重定向说明），并清掉临时文件
    _ecfg.clear_override()
    try:
        if _CFG_BACKUP is None:
            if os.path.isfile(_REAL_CFG_PATH):
                os.remove(_REAL_CFG_PATH)
        else:
            with open(_REAL_CFG_PATH, 'w', encoding='utf-8') as _fp:
                _fp.write(_CFG_BACKUP)
        if os.path.isfile(_TMP_CFG):
            os.remove(_TMP_CFG)
    except OSError as _e:
        print(f"[WARN] 还原开关文件失败: {_e}")

check('官网条目真的调用了浏览器打开',
      bool(_opened_urls) and 'GatenneaSliderWeb' in _opened_urls[-1])
check('教程条目真的走了教程入口', bool(_tutorial_starts))

# ================================================================ 5 渲染不崩
print("\n--- 5 帮助对话框检索态渲染 ---")
import pygame  # noqa: E402

gui.show_help = True
gui.help_query = '着色'
gui.help_scrollbar.set_scroll(0)
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
