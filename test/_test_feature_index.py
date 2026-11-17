# -*- coding: utf-8 -*-
"""功能检索索引（gui/feature_index.py）回归测试。

锁四件事：
  1. 清单数据完整（字段齐全、id 唯一、形态/模式键合法）—— 表与代码漂移时这里会红；
  2. 口语化查询能命中预期条目 —— 别名表是检索质量的关键，删别名会红；
  3. 每条的「一键到位」目标接得上（settings 打开对应页签 / toggle 真翻转 / 其余不抛）。
  4. 防漏护栏（2026-11-17，待办 §五十二起因）：设置对话框的可点控件与真源条目
     双向锁——新增开关漏登记、或条目声明了设置页却没对应控件，这里会红。

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

# ================================================================ 2d 覆盖补齐（2026-11-14）
# 玩家反馈「有些已有功能搜不到」。体检发现两类：整条功能没登记（设置子页、
# 删除预设、搭积木编辑器…），以及排序规则把「名称/别名命中」压在「可用」
# 之后，导致带形态词的查询被不相干条目抢位。下面这组锁住补过的洞。
print("\n--- 2d 覆盖补齐：设置子页 / 玩法入口 / 别名 ---")
_CASES_2D = (
    ('聚拢参数', 'gather_params'),
    ('参数', 'gather_params'),
    ('压缩存档', 'save_compress'),
    ('存档压缩', 'save_compress'),
    ('只读', 'readonly_save'),
    ('防止覆盖', 'prevent_overwrite'),
    ('外部控制', 'external_control'),
    ('令牌', 'external_control'),
    ('http', 'external_control'),
    ('删除预设', 'delete_preset'),
    ('搭积木', 'model_editor'),
    ('模型', 'model_editor'),
    ('音量', 'sfx_slots'),
    ('漂移', 'anti_drift'),
    ('洞位', 'board_marks_enabled'),
    ('查表', 'algo_others'),
    ('混合', 'algo_others'),
    ('导入', 'load'),
    ('导出', 'save_as'),
    ('三角形', 'preset_exotic'),
    ('难度', 'concept_step'),
    ('截图', 'screenshot'),
    ('截屏', 'screenshot'),
)
for query, want in _CASES_2D:
    hits = [e['id'] for _s, e, _a in fi.search(query)]
    check(f'2D「{query}」→ {want}', want in hits)

# 带形态词的查询，指定形态的预设档要排第一（排序：强命中 > 可用）
for q in ('三角', '米字', '三角形'):
    hits = fi.search(q, form='square', mode='practice')
    check(f'2D「{q}」首位 = preset_exotic（矩形盘下也算）',
          bool(hits) and hits[0][1]['id'] == 'preset_exotic')

# ================================================================ 2e 漏登补齐
# 起因（待办 §五十二）：功能真实存在但真源漏登记，玩家 Ctrl+K 搜不到。
# 本轮补齐：谜题菜单悬停预览 + 设置页三个漏登开关 + 快捷键页 +
# 谜题菜单漏登的模型/样式子菜单 + 标注模式（仅文档登记，无显式入口）。
print("\n--- 2e 漏登补齐（2026-11-17） ---")
_CASES_2E = (
    ('预览', 'puzzle_hover_preview'),
    ('悬停预览', 'puzzle_hover_preview'),
    ('操作日志', 'op_log_enabled'),
    ('开机动画', 'boot_animation'),
    ('防意外打乱', 'confirm_before_shuffle'),
    ('改键', 'keybindings'),
    ('快捷键', 'keybindings'),
    ('模型谜题', 'preset_model'),
    ('捆绑', 'preset_styles'),
    ('自定义还原态', 'preset_styles'),
    ('标注', 'annotation_mode'),
)
for query, want in _CASES_2E:
    hits = [e['id'] for _s, e, _a in fi.search(query)]
    check(f'2E「{query}」→ {want}', want in hits)

# 标注模式只进文档、不给显式入口：一键到位必须是 none（不跳任何界面）
_ann = next((f for f in fi.FEATURES if f['id'] == 'annotation_mode'), None)
check('annotation_mode 登记为 none（无显式入口）',
      _ann is not None and _ann['action'].get('type') == 'none')

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
# 会话恢复若把「上次关窗时的模型文件板型」读回来，着色/连锁/复原标记三个
# 开关会按设计被拦（b0c0d2a），下面「切换生效」那几项就会假红。
# 本节验的是「一键到位接线」，与盘型无关 → 强制方形局。
gui.new_puzzle(6, 6, 2)

_opened_urls = []
_tutorial_starts = []
_shots = []
_orig_open = webbrowser.open
_orig_tut_start = gui._tut_start
_orig_shot = gui._do_screenshot
webbrowser.open = lambda url, *a, **k: _opened_urls.append(url)
gui._tut_start = lambda *a, **k: _tutorial_starts.append(1)
# 截图条目会真的写 PNG 到 screenshots/：本节只验接线，换成桩记录调用，
# 别让测试在仓库里撒垃圾文件。
gui._do_screenshot = lambda target='': (_shots.append(target),
                                       (True, '[测试桩] 已保存截图', {}))[1]
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
    gui._do_screenshot = _orig_shot
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
check('截图条目真的调用了截图实现', bool(_shots))

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

# ================================================================ 6 防漏护栏
# 起因（待办 §五十二）：谜题菜单悬停预览真实存在却没登记真源，玩家搜不到。
# 本节把「设置对话框可点控件」与真源条目双向锁住：
#   正向：events.py 里出现的每个 _settings_*_rect 控件必须登记在下表（或标明非功能项）；
#   反向：每条 place=('settings',…) 的真源条目必须能在下表里找到对应控件。
# 新增开关漏登记 / 删控件却留条目，本节都会红。
print("\n--- 6 防漏护栏：设置页控件 ↔ 真源条目 ---")
import re  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_ROOT, 'gui', 'events.py'), encoding='utf-8') as _fp:
    _events_src = _fp.read()
_rects_found = sorted(set(re.findall(r'self\._settings_(\w+)_rect', _events_src)))
# 控件名（events.py 里 _settings_<名>_rect 的 <名>）→ 真源 id；
# 值可为元组 = 该控件由多条真源条目共同覆盖。反向检查按值展开，
# 所以正则扫不到、以字符串构造的批量控件在这里手工登记。
_RECT_TO_ID = {
    # 文件页
    'readonly_toggle': 'readonly_save',
    'prevent_overwrite': 'prevent_overwrite',
    'oplog_toggle': 'op_log_enabled',
    'compressed_toggle': 'save_compress',
    # 视觉页
    'anim_toggle': 'animation_enabled',
    'sel_anim_toggle': 'selection_animation_enabled',
    'coloring_toggle': 'coloring_enabled',
    'chain_toggle': 'chain_hint_enabled',
    'gap_hover_toggle': 'gap_hover_flash_enabled',
    'marks_toggle': 'board_marks_enabled',
    'metrics_toggle': 'metrics_panel',
    'records_toggle': 'records_panel',
    'boot_toggle': 'boot_animation',
    'confirm_shuffle_toggle': 'confirm_before_shuffle',
    'grid_toggle': 'draw_grid',
    'anti_drift_toggle': 'anti_drift',
    'thinking_toggle': 'thinking',
    'zoom_knob': 'zoom',
    'zoom_track': 'zoom',
    'slider_knob': 'animation_duration',
    'slider_track': 'animation_duration',
    # 音频页
    'sfx_toggle': 'sfx_enabled',
    'music_toggle': 'music_enabled',
    'mute_toggle': 'sound_muted',
    '_settings_slot_toggle_rects': 'sfx_slots',    # 字典批量控件，手工登记
    '_settings_slot_preview_rects': 'sfx_slots',   # 试听按钮，同属音效一览
    # 求解器 / 聚拢参数页
    'solver': ('algo_gather', 'algo_others', 'pick_fill'),
    'solver_log_toggle': 'solver_log_enabled',
    'gather': 'gather_params',
    # 快捷键页
    'key': 'keybindings',
    # 控制页
    'ctrl_single': 'control_single_touch',
    'ctrl_two': 'control_two_touch',
    'ctrl_kb': 'control_mouse_kb',
    'ctrl_vk': 'virtual_keyboard',
    'ctrl_arrow': 'arrows_enabled',
    'ctrl_revmacro': 'macro_reverse',
    'infinite_shuffle_toggle': 'infinite_shuffle',
    'game_mode': 'mode_practice',
    'ext_toggle': 'external_control',
    'ext_copy': 'external_control',
    'ext_guide': 'external_control',
}
# 非功能控件（导航/框架件），值为登记理由
_RECT_SKIPPED = {
    'tab_kb': '页签导航（快捷键）',
    'tab_anim': '页签导航（视觉）',
    'tab_audio': '页签导航（音频）',
    'tab_solver': '页签导航（求解器）',
    'tab_gather': '页签导航（聚拢参数）',
    'tab_file': '页签导航（文件）',
    'tab_control': '页签导航（控制）',
    'tab_cubic': '页签导航（三维）',
}
_unreg = [r for r in _rects_found
          if r not in _RECT_TO_ID and r not in _RECT_SKIPPED]
check('设置页控件全部登记防漏映射', not _unreg,
      f'未登记控件: {_unreg}（先补真源条目，再登记进 _RECT_TO_ID / _RECT_SKIPPED）')

_ids = {f['id'] for f in fi.FEATURES}
_dangling = []
for _r, _v in _RECT_TO_ID.items():
    for _i in ((_v,) if isinstance(_v, str) else _v):
        if _i not in _ids:
            _dangling.append(f'{_r}→{_i}')
check('映射的功能 id 都在真源里', not _dangling, '; '.join(_dangling))

_mapped_ids = set()
for _v in _RECT_TO_ID.values():
    _mapped_ids.update((_v,) if isinstance(_v, str) else _v)
_settings_place = [f['id'] for f in fi.FEATURES
                   if isinstance(f.get('place'), tuple) and f['place']
                   and f['place'][0] == 'settings']
_orphan = [i for i in _settings_place if i not in _mapped_ids]
check('声明在设置页的条目都有对应控件', not _orphan, f'孤立条目: {_orphan}')

print()
if _failures:
    print(f"FAILED: {len(_failures)} 项")
    for name in _failures:
        print("  -", name)
    sys.exit(1)
print("ALL PASS")
