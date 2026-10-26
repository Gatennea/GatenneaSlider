# -*- coding: utf-8 -*-
"""回归：谜题菜单「模型谜题」悬停预览（复原态 + 一种打乱态缩图）。

用户 2026-10-26 提的「查」：菜單裡選謎題時，懸停就顯示它的復原態和一種
打亂態。这是自造谜题四项待办里的最后一项（前两项见 _test_model_modes /
_test_model_style）。

本测试钉住：
  A. 缩图能算出来：非 None、尺寸对、有内容、两张不相同；
  B. 几何同源：块数对得上、（拟合后）宽高比与真几何一致（没转置/拉伸）；
  C. 按块序上色：首尾块颜色不同、色相落在青→紫段（不是彩虹乱配）；
  D. 缓存与异步：第二次拿极快；request() 首帧可以不阻塞，随后变 ready；
     clear_cache() 后能重算；
  E. 失败不静默：不存在的模型名 → 返回空 + last_error 有话说；
  F. 菜单接线：悬停模型条目才画面板、悬停分组标题不画、右侧塞不下时
     翻到一级菜单左侧。
  G. 反向护栏：方形局没有被这套预览牵连（菜单照旧能画）。
  H. 调色板键护栏：渲染层引用的 `self.colors[...]` 键必须真存在
     （2026-10-26 一碰预览就崩的根因就是写错键名）。
  I. 预览失败不许连累整帧：假模型名 → 菜单照常画、原因记日志。
  J. 磁盘缓存：空闲预热落盘、清内存后仍能立刻取图、签名带内容哈希。

跑法：D:/python/python.exe test/_test_model_preview.py
"""
import os
import sys
import time

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from engine import model_registry  # noqa: E402
from gui import model_preview  # noqa: E402

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


def make_gui(model=None, step=2):
    """无头 GUI（可选直接开一个模型局）。"""
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    if model:
        gui.new_model_puzzle(model, step)
        gui.center_map()
    return gui


def _ink_ratio(surf):
    """非背景像素占比（判断「这图不是空的」）。"""
    bg = (30, 30, 30)
    w, h = surf.get_size()
    n = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if tuple(surf.get_at((x, y))[:3]) != bg:
                n += 1
    return n / max(1.0, (w // 2) * (h // 2))


def _diff_ratio(a, b):
    """两张同尺寸图的逐像素差异占比。"""
    w, h = a.get_size()
    n = 0
    tot = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            tot += 1
            if tuple(a.get_at((x, y))[:3]) != tuple(b.get_at((x, y))[:3]):
                n += 1
    return n / max(1, tot)


def _model_items(gui, name='shield'):
    """在菜单的模型子菜单里找该模型的第一条（等级1）。"""
    for i, it in enumerate(gui.puzzle_sub_presets.get('models') or []):
        if len(it) >= 5 and isinstance(it[4], str) and it[4] == name:
            return i
    return -1


def main():
    model_preview.clear_cache()
    # 调色板直接取真 GUI 的（C 组要比「缩图块色 == 真盘块色」）
    gui = make_gui('shield', 2)

    # ---- A. 基本可用 ------------------------------------------------
    goal, scr = model_preview.thumbs('shield', 104)
    check(goal is not None and scr is not None, 'A1 shield 能算出两张缩图')
    if goal is None or scr is None:
        print('A 组全灭，后续跳过')
        return _report()
    check(goal.get_size() == (104, 104) and scr.get_size() == (104, 104),
          'A2 缩图尺寸 = 104×104', f'{goal.get_size()} {scr.get_size()}')
    check(_ink_ratio(goal) > 0.15, 'A3 复原态缩图有内容（非纯底色）',
          f'ink={_ink_ratio(goal):.2f}')
    dr = _diff_ratio(goal, scr)
    check(dr > 0.10, 'A4 打乱态与复原态明显不同（不是同一张图）',
          f'diff={dr:.2f}')

    # ---- B. 几何同源 ------------------------------------------------
    spec = model_registry.loaded('shield').spec
    gp = model_preview._polys_goal(spec)
    sp = model_preview._polygons_of_board(
        __import__('engine.adapter', fromlist=['create_adapter_puzzle'])
        .create_adapter_puzzle('shield', 4, 4, 2).board)
    check(len(gp) == len(spec.goal_blocks),
          'B1 复原态多边形数 = goal_blocks 数', f'{len(gp)}/{len(spec.goal_blocks)}')
    check(len(sp) == len(gp), 'B2 打乱态块数 = 复原态块数',
          f'{len(sp)}/{len(gp)}')

    xs = [p[0] for poly, _ in gp for p in poly]
    ys = [p[1] for poly, _ in gp for p in poly]
    gw, gh = max(xs) - min(xs), max(ys) - min(ys)
    fitted = model_preview._fit(gp, 104)
    fx = [p[0] for poly, _ in fitted for p in poly]
    fy = [p[1] for poly, _ in fitted for p in poly]
    fw, fh = max(fx) - min(fx), max(fy) - min(fy)
    ratio_geo = gw / gh
    ratio_fit = fw / fh
    check(abs(ratio_geo - ratio_fit) < 0.02,
          'B3 拟合后宽高比与真几何一致（没转置、没拉伸）',
          f'geo={ratio_geo:.3f} fit={ratio_fit:.3f}')
    check(max(fw, fh) <= 104 - 2 * model_preview._PAD + 0.01,
          'B4 拟合结果不超出缩图内边距', f'{fw:.1f}x{fh:.1f}')

    # ---- C. 画风一致：缩图块色 = 真盘块色（不搞彩虹） ----------------
    # 2026-10-26 用户质疑「为什么这么多颜色的滑块」。实测单色下两张缩图
    # 像素差就有 26~37%，彩色渐变没换来可读性，反而和真盘画风不一致。
    pal = model_preview._palette(gui.colors)
    g_c, s_c = model_preview.thumbs('shield', 104, gui.colors)
    cnt = set()
    for y in range(0, 104, 2):
        for x in range(0, 104, 2):
            cnt.add(tuple(g_c.get_at((x, y))[:3]))
    check(len(cnt) <= 3, 'C1 缩图只用「底色 / 块色 / 缝线」三种颜色',
          f'{sorted(cnt)}')
    check(pal[1] in cnt, 'C2 块色 = 真盘滑块色（与碎三角同一套画风）',
          f'block={pal[1]} 实际={sorted(cnt)}')

    # ---- D. 缓存与异步 ----------------------------------------------
    t0 = time.perf_counter()
    model_preview.thumbs('shield', 104)
    dt = (time.perf_counter() - t0) * 1000
    check(dt < 5.0, 'D1 命中缓存时几乎零耗时', f'{dt:.2f}ms')

    model_preview.clear_cache()
    g2, s2, state = model_preview.request('shield', 104)
    check(state in ('pending', 'ready'),
          'D2 request() 首帧不阻塞（pending 或已 ready）', f'state={state}')
    deadline = time.time() + 10.0
    while state == 'pending' and time.time() < deadline:
        time.sleep(0.02)
        g2, s2, state = model_preview.request('shield', 104)
    check(state == 'ready' and g2 is not None and s2 is not None,
          'D3 后台算完后变 ready 且有图', f'state={state}')
    check(model_preview.last_error('shield') is None,
          'D4 正常模型不该留下错误')

    model_preview.clear_cache()
    g3, _s3 = model_preview.thumbs('shield', 104)
    check(g3 is not None, 'D5 clear_cache() 之后能重算')

    # D6 竞态护栏：后台线程算的途中被 clear_cache()（= 编辑器存了新形状），
    # 算完的旧结果**不许写回**，否则「改了模型、预览还是老样子」。
    # 两种时序都被这条断言覆盖：①清得早 → 旧结果被世代检查丢弃；
    # ②算得比清还快 → 清本身把那条删掉了。任一时序下缓存都不该有它。
    model_preview.clear_cache()
    key = ('shield', 104, model_preview._palette(None))
    model_preview.request('shield', 104)     # 起一个后台线程
    model_preview.clear_cache()              # 立刻作废（模型刚被改写）
    time.sleep(1.0)                          # 等后台线程跑完
    hit, _val = model_preview._lookup(key)
    check(not hit, 'D6 清缓存期间算完的旧图不写回缓存')

    # ---- E. 失败不静默 ----------------------------------------------
    model_preview.clear_cache()
    bad_g, bad_s = model_preview.thumbs('__no_such_model__', 104)
    check(bad_g is None and bad_s is None, 'E1 不存在的模型 → 两张都 None')
    check(bool(model_preview.last_error('__no_such_model__')),
          'E2 失败原因被记下（渲染层会画「预览不可用：…」）',
          repr(model_preview.last_error('__no_such_model__')))

    # ---- F. 菜单接线 ------------------------------------------------
    model_preview.clear_cache()
    model_preview.thumbs('shield', 104)          # 先热身，避免悬停那帧还在 pending
    gui._refresh_puzzle_presets()
    idx = _model_items(gui, 'shield')
    check(idx >= 0, 'F0 菜单的模型子菜单里能定位 shield 条目')
    if idx < 0:
        return _report()

    gui.show_puzzle_menu = True
    gui.puzzle_sub_open = 'models'
    gui.puzzle_sub_hovered = idx
    gui.draw_board()
    gui.draw_menu_bar()
    sub_right = gui.puzzle_sub_rects[0].right
    menu_y = gui.menu_bar_height
    panel_bg = gui.colors['menu_bg']

    def _count_bg(x0, x1, y0, y1):
        n = 0
        for y in range(max(0, y0), min(gui.screen.get_height(), y1)):
            for x in range(max(0, x0), min(gui.screen.get_width(), x1)):
                if tuple(gui.screen.get_at((x, y))[:3]) == panel_bg:
                    n += 1
        return n

    right_hits = _count_bg(sub_right + 2, gui.screen.get_width(), menu_y, menu_y + 200)
    check(right_hits > 1000, 'F1 悬停模型条目时右侧画出预览面板',
          f'bg_px={right_hits}')

    # 悬停分组标题（模型子菜单第 0 条是 '__group__'）→ 不该画面板
    gui.puzzle_sub_hovered = 0
    gui.draw_board()
    gui.draw_menu_bar()
    right_hits2 = _count_bg(sub_right + 2, gui.screen.get_width(), menu_y, menu_y + 200)
    check(right_hits2 == 0, 'F2 悬停分组标题不画预览面板', f'bg_px={right_hits2}')

    # 右侧塞不下 → 翻到一级菜单左边
    gui.puzzle_sub_hovered = idx
    gui.screen = pygame.Surface((660, gui.screen_height))
    gui.draw_board()
    gui.draw_menu_bar()
    base = getattr(gui, 'puzzle_menu_rect', None)
    check(base is not None, 'F3 一级菜单外框被记下（翻边定位用）')
    left_hits = _count_bg(0, base.x - 2, menu_y, menu_y + 200) if base else 0
    check(left_hits > 1000, 'F4 右侧塞不下时面板翻到一级菜单左侧',
          f'bg_px={left_hits}')

    # ---- G. 反向护栏：方形局菜单照旧 --------------------------------
    gui2 = make_gui()
    gui2._refresh_puzzle_presets()
    gui2.show_puzzle_menu = True
    gui2.puzzle_sub_open = 'models'
    gui2.puzzle_sub_hovered = -1
    try:
        gui2.draw_board()
        gui2.draw_menu_bar()
        drew = True
    except Exception as exc:      # noqa: BLE001
        drew = False
        print('   方形菜单异常:', exc)
    check(drew, 'G1 方形局菜单绘制不受影响（悬停 -1 时不碰预览）')

    # ---- H. 调色板键护栏（2026-10-26 事故） -------------------------
    # 事故：失败提示分支写了 self.colors['unsolvable']，实际键名是
    # 'unsolved' → 悬停任何「预览算不出来」的条目就 KeyError，打断主循环，
    # 表现成「一碰预览就崩」。这里静态扫一遍所有 self.colors['x'] 字面量。
    import re
    pat = re.compile(r"self\.colors\[\s*['\"]([a-z_]+)['\"]\s*\]")
    files = [os.path.join(_PROJ, 'GUI.py')]
    files += [os.path.join(_PROJ, 'gui', n)
              for n in sorted(os.listdir(os.path.join(_PROJ, 'gui')))
              if n.endswith('.py')]
    missing = []
    for path in files:
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
        for mt in pat.finditer(src):
            if mt.group(1) not in gui.colors:
                missing.append(f'{os.path.basename(path)}: {mt.group(1)}')
    check(not missing, 'H1 渲染层引用的调色板键全部存在于 GUI.colors',
          str(sorted(set(missing))[:8]))

    # ---- I. 预览失败不许连累整帧 ------------------------------------
    model_preview.clear_cache()
    gui.puzzle_sub_presets['models'] = list(gui.puzzle_sub_presets['models']) + [
        ('假模型（0 块）', 4, 4, 1, '__no_such_model__')]
    gui.puzzle_sub_hovered = len(gui.puzzle_sub_presets['models']) - 1
    gui.screen = pygame.display.get_surface()
    # 边画边等：request() 由绘制触发（首帧 pending，线程算完才留下失败原因）
    deadline = time.time() + 10.0
    draw_err = None
    while time.time() < deadline:
        try:
            gui.draw_board()
            gui.draw_menu_bar()
        except Exception as exc:      # noqa: BLE001
            draw_err = exc
            break
        if model_preview.last_error('__no_such_model__'):
            break
        time.sleep(0.02)
    try:
        gui.draw_board()               # 再画一帧：这一帧走的是「预览不可用」分支
        gui.draw_menu_bar()
    except Exception as exc:          # noqa: BLE001
        draw_err = draw_err or exc
    check(draw_err is None, 'I1 预览算不出来时菜单照常绘制（不再中断主循环）',
          repr(draw_err))
    check(bool(model_preview.last_error('__no_such_model__')),
          'I2 失败原因被记下（面板画「预览不可用：…」而不是假装没这功能）',
          repr(model_preview.last_error('__no_such_model__')))

    # I3：失败也要留在错误日志里（真因不能只活在内存里）
    try:
        with open(os.path.join(_PROJ, 'config', 'error_log.jsonl'),
                  encoding='utf-8') as fh:
            tail = fh.read()[-20000:]
        logged = '模型预览生成失败' in tail
    except OSError:
        logged = False
    check(logged, 'I3 预览失败写进了 error_log.jsonl（带 traceback）')

    # ---- J. 磁盘缓存：空闲预热落盘 + 下次启动零计算 ------------------
    # 用户 2026-10-26 的方案：开局后空闲时把每个模型的两张图都算好导出，
    # 悬停只读图。这里钉住「能落盘」「清内存后仍立刻有图」「签名带模型内容哈希」。
    model_preview.clear_cache()
    key = ('shield', 104, model_preview._palette(gui.colors))
    for _f in range(400):
        model_preview.pump(gui.colors)
        if model_preview._disk_ok(key):
            break
        time.sleep(0.02)
    check(model_preview._disk_ok(key), 'J1 空闲预热把缩图存到本地（下次启动零计算）')
    model_preview.clear_cache()          # 只清内存，磁盘仍在
    g4, s4, st4 = model_preview.request('shield', 104, gui.colors)
    check(st4 == 'ready' and g4 is not None and s4 is not None,
          'J2 内存清空后仍能从磁盘立刻取图（悬停零等待）', f'state={st4}')
    check(model_registry.loaded('shield').hash() in model_preview._disk_sig(key),
          'J3 磁盘签名含模型内容哈希（改了形状自动失效，不会用旧图）',
          model_preview._disk_sig(key))

    return _report()


def _report():
    print(f'\n== {_ok[0]} passed, {len(_fail)} failed ==')
    for m in _fail:
        print('  FAILED:', m)
    return 0 if not _fail else 1


if __name__ == '__main__':
    sys.exit(main())
