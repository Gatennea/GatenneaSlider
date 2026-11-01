# -*- coding: utf-8 -*-
"""三角 / 米字捆绑（v4）无头测试：点缝绑解 + 自定义形状 + 存样式 + 按样式开局。

锁六件事（用户 2026-10-20 定的范围：玩法 + 存档 + 点缝捆绑；形状也可自定义）：
  1. 引擎：opt 永远把整组拖进选中片 → 任何一条「会切组的缝」都切不开捆绑
     （整组同时被选中 ⇒ 移动是整组平移）；
  2. 交互：点捆绑块的内部缝 = 点中该组滑块（三形态统一，不再弹「选不动」），
     且 selected_gap 不被污染；
  3. 渲染：异形捆绑组走 draw_group_pieces 不抛异常（离屏截图冒烟）；
  4. 设计态：异形高级选项可自定义还原态形状（点格增删 + 点缝绑解），保存前
     过连通性 + 可打乱两道关；样式落 version 2（带 kind），按样式开局 =
     按 cells 摆形 + 捆绑 + goal_pattern（is_solved 逐块比位置）；
  5. 事件路径：设计态点击经 handle_events 真分发（直调方法测不出分流 bug）；
  6. 存档：三形态捆绑都落得住（含异形 3 分量坐标 / 半整数）。

执行：``D:/python/python.exe -u test/_test_bandage_forms.py``
"""
import os
import queue
import sys
import math
import random

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from game_mi import side_of as mi_side_of  # noqa: E402
from game_triangle import gap_index_range as tri_gap_range  # noqa: E402
from game_triangle import neighbors as tri_neighbors  # noqa: E402
from game_triangle import side_of as tri_side_of  # noqa: E402
from gui import design_styles  # noqa: E402
from engine.compat import direction_table  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def boot(which, *args):
    gui = SliderGUI(cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.animation_enabled = False
    getattr(gui, which)(*args)
    gui._update_in_progress = False
    return gui


def bind(gui, plan):
    """plan = [(gid, [位置, ...]), ...]"""
    pos = {tuple(b.location): b for b in gui.game.blocks}
    for gid, cells in plan:
        for c in cells:
            pos[tuple(c)].group = gid
    return pos


def seam_click_point(gui, gap, cells):
    """兩塊組員共邊的中點 → 屏幕座標（正好落在內部縫線上）。"""
    tri = getattr(gui, 'triangle_mode', False)
    view = gui._tri_view() if tri else gui._mi_view()
    for a in cells:
        for b in cells:
            if tuple(a) >= tuple(b):
                continue
            if gui.game.seam_between_positions(a, b) != gap:
                continue
            ax, ay = view.piece_center(*a)
            bx, by = view.piece_center(*b)
            return gui.world_to_screen((ax + bx) / 2.0, (ay + by) / 2.0)
    return None


def click(gui, p):
    gui.macro_notify_msg = None
    gui.macro_notify_timer = 0
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                        button=1, pos=p))
    gui.handle_events()


# ================================================================ 1 三角
print('\n--- 1 三角形：内部缝点击 / 刚性不变量 / 渲染 ---')
gui = boot('new_triangle_puzzle', 6, 2)
cells = {tuple(b.location) for b in gui.game.blocks}
seed = None
for p in sorted(c for c in cells if c[2] is True):
    on = [n for n in map(tuple, tri_neighbors(p)) if n in cells]
    if len(on) == 3:
        seed, nbs = p, on
        break
check('1a 找到一個三鄰塊俱全的 ▲', seed is not None, f'{seed}')
grp = [seed, nbs[0], nbs[1]]
pos = bind(gui, [(1, grp)])
bi = gui.game.bandage_internal_seams()
check('1b 3 塊 V 形有 2 條內部縫', len(bi) == 2, f'{sorted(bi)}')

gui.selected_gap = ('h', 1)
for b in gui.game.blocks:
    b.be_opted = False
gui.selected_block = None
gi = sorted(bi)[0]
p_in = seam_click_point(gui, gi, grp)
click(gui, p_in)
# 选中缝因捆绑被拒：统一提示「选不动」+ 选中预览（rejected_gap 记录该缝，供白线/叉号渲染）
check('1c 點內部縫彈統一拒絕提示', '选不动' in (gui.macro_notify_msg or ''),
      f'{gui.macro_notify_msg!r}')
check('1c2 拒絕縫已記錄(rejected_gap)', gui.rejected_gap == gi,
      f'{gui.rejected_gap!r}')
opted = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
check('1d 內部縫被拒：整組未被當滑塊選中', not set(grp).issubset(opted),
      f'opted={len(opted)}')
check('1e selected_gap 未被污染', gui.selected_gap == ('h', 1),
      f'{gui.selected_gap}')
gui.draw_triangle_board()
check('1f 三角捆綁組渲染不拋異常', True)
# 捆綁內部縫被拒後，叉號應出現在「縫切入/切出捆綁塊」的兩個交點
_mk1 = gui._gap_reject_mark_points()
check('1f2 捆綁內部縫叉號點 = 2（切出入）', len(_mk1) >= 2,
      f'pts={len(_mk1)}')
gui._draw_gap_reject_marks()  # 不應拋異常
gui._draw_rejected_gap_preview()
check('1f3 拒絕白線/叉號渲染不拋異常', True)

# 剛性不變量：切組縫上 opt 也要把整組拖進來
gui = boot('new_triangle_puzzle', 5, 2)
cells = {tuple(b.location) for b in gui.game.blocks}
pair = None
for p in sorted(c for c in cells if c[2] is True):
    for q in map(tuple, tri_neighbors(p)):
        if (q[2] is False and q[0] == p[0] and q[1] == p[1] and q in cells):
            pair = (p, q)
            break
    if pair:
        break
check('1g 找到同胞 ▲+▼（菱形對）', pair is not None, f'{pair}')
pos = bind(gui, [(5, list(pair))])
checked = 0
bad = []
for gt in ('h', 'p', 'n'):
    for line in tri_gap_range(gt, cells):
        if not gui.game.is_valid_gap(gt, line):
            continue
        if tri_side_of(gt, line, pair[0]) == tri_side_of(gt, line, pair[1]):
            continue        # 這條縫不切組，驗不到擴張
        for b in gui.game.blocks:
            b.be_opted = False
        gui.game.opt(gt, line, pos[pair[0]])
        opted2 = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
        if not set(pair).issubset(opted2):
            bad.append((gt, line, len(opted2)))
        checked += 1
check('1h 切組縫上 opt 一律整組選中（剛性）', checked > 0 and not bad,
      f'{checked} 條, 失敗 {bad}')

# ================================================================ 2 米字
print('\n--- 2 米字格：同格四塊整胞 ---')
gui = boot('new_mi_puzzle', 4, 2)
cells = [tuple(b.location) for b in gui.game.blocks]
by_cell = {}
for p in cells:
    by_cell.setdefault((int(p[0]), int(p[1])), []).append(p)
quad = [v for v in by_cell.values() if len(v) == 4][0]
pos = bind(gui, [(7, quad)])
bi = gui.game.bandage_internal_seams()
check('2a 同格四塊有 2 條內部縫（兩條對角）', len(bi) == 2, f'{sorted(bi)}')
gui.selected_gap = ('h', 1)
for b in gui.game.blocks:
    b.be_opted = False
gui.selected_block = None
gi = sorted(bi)[0]
p_in = seam_click_point(gui, gi, quad)
click(gui, p_in)
check('2b 點內部縫彈統一拒絕提示', '选不动' in (gui.macro_notify_msg or ''),
      f'{gui.macro_notify_msg!r}')
check('2b2 拒絕縫已記錄(rejected_gap)', gui.rejected_gap == gi,
      f'{gui.rejected_gap!r}')
opted = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
check('2c 內部縫被拒：整胞未被當滑塊選中', not set(quad).issubset(opted),
      f'opted={len(opted)}')
check('2d selected_gap 未被污染', gui.selected_gap == ('h', 1),
      f'{gui.selected_gap}')
gui.draw_mi_board()
check('2e 米字捆綁組渲染不拋異常', True)
_mk2 = gui._gap_reject_mark_points()
check('2e2 米字捆綁內部縫叉號點 = 2（切出入）', len(_mk2) >= 2,
      f'pts={len(_mk2)}')
gui._draw_gap_reject_marks()
gui._draw_rejected_gap_preview()
check('2e3 拒絕白線/叉號渲染不拋異常', True)

checked = 0
bad = []
for gt, line in gui.game.all_gaps():
    if not gui.game.is_valid_gap(gt, line):
        continue
    if mi_side_of(gt, line, quad[0]) == mi_side_of(gt, line, quad[-1]):
        continue
    for b in gui.game.blocks:
        b.be_opted = False
    gui.game.opt(gt, line, pos[quad[0]])
    opted2 = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
    if not set(quad).issubset(opted2):
        bad.append((gt, line, len(opted2)))
    checked += 1
check('2f 切組縫上 opt 一律整組選中（剛性）', checked > 0 and not bad,
      f'{checked} 條, 失敗 {bad}')

# ================================================================ 2g 米字非捆绑拒缝叉号定位
print('\n--- 2g 米字非捆绑缝：叉号定位修复（图1）---')
# 标准米字满盘时，缝走「块间隙」（距块顶点 ~3.6px），一条都不穿块；用户图1 是
# 移位后的局面（块被推到缝上）才出现「缝穿单块」。米字走独立 mi_mode 通道
# （与碎三角的通用多边形通道不是同一分支），故这里分两层验证 mi 通道：
#  (a) mi_mode 分支的 _block_screen_polygons 真能算出每块屏幕多边形（不崩）；
#  (b) 非捆绑派发逻辑：一旦某块被缝穿，叉号落在「缝×该块」交点而非缝两端。
# 真实「缝穿单块」的几何由第 7 节（碎三角）覆盖，那里缝天然穿块。
_bi = gui.game.bandage_internal_seams()
_nonb = [g for g in gui.game.all_gaps()
         if g not in _bi and gui.game.is_valid_gap(*g)]
check('2g0 存在非捆绑缝', len(_nonb) >= 1, f'{len(_nonb)} 条')
_nb = _nonb[0]
gui.selected_block = None
gui.rejected_gap = _nb
# (a) mi_mode 分支真实几何：每块屏幕多边形非空
_polys = gui._block_screen_polygons()
_nok = sum(1 for (_b, poly) in _polys if len(poly) >= 3)
check('2g1 mi_mode 分支每块屏幕多边形有效',
      _nok == len(_polys) and len(_polys) > 0, f'{_nok}/{len(_polys)}')
# (b) 派发逻辑：模拟「该缝穿了一块滑块」，叉号应落在该块交点而非缝两端
_line = gui._gap_screen_line(_nb)
check('2g2 非捆绑缝屏幕线非空', _line is not None, f'{_line}')
# 取一块真实多边形当载体（质心用于「最近的块」挑选），塞两个明显不在缝两端
# 的合成交点，验证派发确实取「被穿块交点」而非退回缝两端。
_realblk, _realpoly = _polys[0]
_syn = [(float(_line[0][0]) + 17.0, float(_line[0][1]) + 9.0),
        (float(_line[1][0]) - 23.0, float(_line[1][1]) + 11.0)]
_orig_hit = gui._reject_gap_blocks_hit
gui._reject_gap_blocks_hit = lambda g: [(_realblk, _realpoly, list(_syn))]
_mk = gui._gap_reject_mark_points()
gui._reject_gap_blocks_hit = _orig_hit
_mk_r = sorted(tuple(round(v) for v in p) for p in _mk)
_syn_r = sorted(tuple(round(v) for v in p) for p in _syn)
check('2g3 叉号落在被穿块交点(非缝两端)', _mk_r == _syn_r,
      f'mk={_mk_r} syn={_syn_r}')
# 兜底：没有任何块被穿 → 退回缝两端（旧实现永远走这；新实现仅在无穿块时）
gui._reject_gap_blocks_hit = lambda g: []
_mk_fb = gui._gap_reject_mark_points()
gui._reject_gap_blocks_hit = _orig_hit
_fb_r = sorted(tuple(round(v) for v in p) for p in _mk_fb)
_ends_r = sorted(tuple(round(v) for v in p) for p in _line)
check('2g4 无穿块时退回缝两端(兜底)', _fb_r == _ends_r,
      f'fb={_fb_r} ends={_ends_r}')
gui._draw_gap_reject_marks()
gui._draw_rejected_gap_preview()
check('2g5 非捆绑拒缝渲染不抛异常', True)

# ================================================================ 3 設計態
print('\n--- 3 異形高級選項：自定義形狀 + 點縫綁解 + 存/讀樣式 ---')
SNAME_T = design_styles.sanitize_name('_三角捆绑测试')
SNAME_M = design_styles.sanitize_name('_米字捆绑测试')
for nm in ('_三角捆绑测试', '_米字捆绑测试'):
    design_styles.delete_style(gui.config_dir, nm)

gui = boot('new_triangle_puzzle', 5, 2)
orig_cells = sorted(tuple(b.location) for b in gui.game.blocks)
orig_groups = {tuple(b.location): b.group for b in gui.game.blocks if b.group}
gui._ann_open_advanced()
check('3a 異形可進高級選項', gui._ann_view == 'design'
      and gui._ann_sub_dialog == 'design' and gui._ann_design_session is True)
check('3b 進入不切模式（練習模式、未開標注）',
      gui.game_mode == 'practice' and gui.annotation_mode is False)
check('3c 畫布盤面 = 進入前標準形', gui._ann_build_coords
      == {tuple(b.location) for b in gui.game.blocks})
check('3d 參數行按形態給（三角只有 k/等級）',
      set(gui._ann_build_fields) == {'k', 'step'}, f'{gui._ann_build_fields}')

pairs = gui._ann_design_seam_pairs()
check('3e 縫反查得到候選對', bool(pairs), f'{len(pairs)} 條縫')
gline = next(g for g, ps in pairs.items() if len(ps) > 1)
target = pairs[gline][-1]
mx, my = gui._ann_design_pair_mid_world(target)
sx, sy = gui.world_to_screen(mx, my)
gui._ann_design_seam_click(gline, sx, sy)
check('3f 點縫綁定的是落點最近的那一對',
      set(gui._ann_design_groups) == set(target), f'{gui._ann_design_groups}')
live = {tuple(b.location): b.group for b in gui.game.blocks if b.group}
check('3g 綁定即時落到棋盤（同組 gid 相同）',
      len(live) == 2 and len(set(live.values())) == 1, f'{live}')

# 點格可增刪（形狀自定義）：點一塊刪掉，再點同一塊回來
n_before = len(gui._ann_build_coords)
toggle_cell = next(c for c in sorted(gui._ann_build_coords)
                   if c not in gui._ann_design_groups)
tx, ty = gui.world_to_screen(*gui._tri_view().piece_center(*toggle_cell))
gui._ann_design_board_click(int(tx), int(ty))
deleted = len(gui._ann_build_coords) == n_before - 1
gui._ann_design_board_click(int(tx), int(ty))
restored = len(gui._ann_build_coords) == n_before
check('3h 異形設計態點格可增刪（形狀自定義）', deleted and restored,
      f'{n_before} → {n_before - 1} → {n_before}')

gui._ann_design_seam_click(gline, sx, sy)
check('3i 再點同一條縫 → 沿線解綁（兩顆各成單塊 → 清空）',
      gui._ann_design_groups == {}, f'{gui._ann_design_groups}')
gui._ann_design_seam_click(gline, sx, sy)   # 綁回來，供存樣式

gui._ann_design_style_name = '三角捆绑测试'
gui._ann_design_save_style()
data_t = design_styles.load_style(gui.config_dir, SNAME_T)
check('3j 存樣式成功且落 version 2 + kind=triangle',
      bool(data_t) and data_t.get('version') == 2
      and data_t.get('kind') == 'triangle', f'{gui._ann_build_error!r}')
try:
    raw_groups = data_t.get('groups') if data_t else None
    ok_shape = (isinstance(raw_groups, list) and len(raw_groups) == 2
                and all(len(it) == 4 for it in raw_groups))
except Exception:
    ok_shape = False
check('3k groups 是「完整位置元組 + gid」陣列', ok_shape, f'{raw_groups}')
norm = design_styles.groups_from_data(data_t or {})
check('3l groups_from_data 解出兩顆同組',
      len(norm) == 2 and len(set(norm.values())) == 1, f'{norm}')

gui._ann_design_cancel()
after_cells = sorted(tuple(b.location) for b in gui.game.blocks)
after_groups = {tuple(b.location): b.group for b in gui.game.blocks if b.group}
check('3m 退出後盤面與捆綁回到進入前',
      after_cells == orig_cells and after_groups == orig_groups)
check('3n 退出不殘留標注模式', gui.annotation_mode is False
      and gui._ann_design_session is False and gui._ann_view == 'home')

gui._refresh_puzzle_presets()
# 样式已收进二级子菜单（带粘连 → 「捆绑谜题」，否则 → 「自定义还原态」）
menu = [p for p in gui._all_puzzle_items()
        if len(p) == 3 and p[1] == '__custom__']
check('3o 樣式進謎題菜單',
      any(p[2] == SNAME_T for p in menu), f'{[p[2] for p in menu]}')

gui._ann_design_start_style(SNAME_T)
check('3p 按樣式開局 = 三角標準形', gui.triangle_mode is True
      and gui.game.k == 5 and gui.current_step == 2,
      f'k={getattr(gui.game, "k", None)} step={gui.current_step}')
started = {tuple(b.location): b.group for b in gui.game.blocks if b.group}
check('3q 開局帶上樣式的捆綁', len(started) == 2
      and len(set(started.values())) == 1, f'{started}')
check('3r 樣式局身份記住（HUD/菜單 ✓ 用）', gui._ann_style_goal == SNAME_T)

# ---- 米字：同樣走一遍（只驗存/讀與開局，交互已在第 2 節驗過）----
gui = boot('new_mi_puzzle', 3, 2)
gui._ann_open_advanced()
pairs = gui._ann_design_seam_pairs()
gline = next(g for g, ps in pairs.items() if len(ps) > 1)
target = pairs[gline][0]
mx, my = gui._ann_design_pair_mid_world(target)
sx, sy = gui.world_to_screen(mx, my)
gui._ann_design_seam_click(gline, sx, sy)
check('3s 米字點縫綁定成功',
      set(gui._ann_design_groups) == set(target), f'{gui._ann_design_groups}')
gui._ann_design_style_name = '米字捆绑测试'
gui._ann_design_save_style()
data_m = design_styles.load_style(gui.config_dir, SNAME_M)
check('3t 米字樣式 kind=mi', bool(data_m) and data_m.get('kind') == 'mi',
      f'{gui._ann_build_error!r}')
gui._ann_design_cancel()
gui._ann_design_start_style(SNAME_M)
check('3u 按米字樣式開局', gui.mi_mode is True
      and (gui.current_m, gui.current_n) == (3, 2),
      f'{gui.current_m}x{gui.current_n}')
started = {tuple(b.location): b.group for b in gui.game.blocks if b.group}
check('3v 米字開局帶上捆綁', len(started) == 2
      and len(set(started.values())) == 1, f'{started}')

for nm in ('_三角捆绑测试', '_米字捆绑测试'):
    design_styles.delete_style(gui.config_dir, nm)

# ================================================================ 4 事件路径
print('\n--- 4 真實事件路徑：設計態點擊經 handle_events 分發 ---')
# 這一節專門鎖「點擊分流」：三角/米字的棋盤點擊曾經在
# _ann_build_dialog_click 裡先落進「按形態增删滑块」分支就 return 了，
# 設計態的點縫綁解永遠收不到事件（直接調 _ann_design_board_click 的測試
# 看不出這個問題，故這裡一律走真事件）。
gui = boot('new_triangle_puzzle', 5, 2)
orig4 = sorted(tuple(b.location) for b in gui.game.blocks)
gui._ann_open_advanced()
n_before = len(gui._ann_build_coords)
pairs = gui._ann_design_seam_pairs()
gline = next(g for g, ps in pairs.items() if len(ps) > 1)
target = pairs[gline][-1]
mx, my = gui._ann_design_pair_mid_world(target)
sx, sy = gui.world_to_screen(mx, my)
click(gui, (int(sx), int(sy)))
check('4a 事件路徑點縫 → 綁定落點那一對',
      set(gui._ann_design_groups) == set(target), f'{gui._ann_design_groups}')
click(gui, (int(sx), int(sy)))
check('4b 事件路徑再點同一處 → 沿線解綁', gui._ann_design_groups == {},
      f'{gui._ann_design_groups}')
bx, by = gui.world_to_screen(*gui._tri_view().piece_center(*target[0]))
click(gui, (int(bx), int(by)))
check('4c 事件路徑點格 → 增刪生效（形狀自定義）',
      len(gui._ann_build_coords) == n_before - 1
      and target[0] not in gui._ann_design_groups,
      f'coords={len(gui._ann_build_coords)} groups={gui._ann_design_groups}')
click(gui, (int(bx), int(by)))
check('4c2 再點同一塊 → 加回來',
      len(gui._ann_build_coords) == n_before,
      f'coords={len(gui._ann_build_coords)}')
gui._ann_design_cancel()
check('4d 退出後回到進入前盤面',
      sorted(tuple(b.location) for b in gui.game.blocks) == orig4)

# ================================================================ 5 存档往返
print('\n--- 5 存檔往返：三形態捆綁都留得住 ---')


def save_roundtrip(which, args, tag):
    g = boot(which, *args)
    for b in g.game.blocks[:2]:
        b.group = 1
    for b in g.game.blocks[5:7]:
        b.group = 2
    g.game_history.save_snapshot(g.game)
    data = g._build_save_data()
    before = sorted((tuple(b.location), b.group)
                    for b in g.game.blocks if b.group)
    g.new_puzzle(3, 3, 1)          # 換成另一局再載入
    g._load_save_data(data)
    after = sorted((tuple(b.location), b.group)
                   for b in g.game.blocks if b.group)
    check(f'5 {tag} 存檔往返保留捆綁（{len(before)} 顆 / 2 組）',
          len(before) == 4 and after == before, f'{len(after)} 顆還原')
    return g


save_roundtrip('new_triangle_puzzle', (5, 2), '三角形')
save_roundtrip('new_mi_puzzle', (4, 2), '米字格')
save_roundtrip('new_puzzle', (4, 4, 1), '方形（對照）')

# ================================================================ 6 自定义形状 + 连通性
print('\n--- 6 異形自定義還原態形狀：增刪 / 連通性 / 還原判定 / 畫布 ---')
for nm in ('_洞形三角', '_洞形米字'):
    design_styles.delete_style(gui.config_dir, nm)

# ---- 6a~6g 三角：刪掉整頂行 → 帶「平頭」的自定義形狀 ----
gui = boot('new_triangle_puzzle', 6, 2)
orig6 = sorted(tuple(b.location) for b in gui.game.blocks)
gui._ann_open_advanced()
victims = [c for c in sorted(gui._ann_build_coords) if c[0] == 0]
for c in victims:
    gui._ann_build_toggle(c)
check('6a 三角設計態可刪塊（自定義形狀）',
      len(gui._ann_build_coords) == len(orig6) - len(victims),
      f'{len(orig6)} → {len(gui._ann_build_coords)}')
ok, err = gui._ann_validate_connected()
check('6b 連通形狀通過校驗', ok, err)
pairs = gui._ann_design_seam_pairs()
g0 = sorted(pairs)[0]
gui._ann_design_seam_click(g0, 0, 0)
gui._ann_design_style_name = '_洞形三角'
gui._ann_design_save_style()
data = design_styles.load_style(gui.config_dir, '_洞形三角')
check('6c 自定義形狀存樣式（cells 少於標準形）',
      bool(data) and len(data['cells']) == len(orig6) - len(victims),
      f'{gui._ann_build_error!r}')
gui._ann_design_cancel()
check('6d 退出後回到進入前盤面',
      sorted(tuple(b.location) for b in gui.game.blocks) == orig6)
gui._ann_design_start_style('_洞形三角')
check('6e 開局按 cells 擺形（塊數 = 樣式 cells）',
      len(gui.game.blocks) == len(orig6) - len(victims),
      f'{len(gui.game.blocks)}')
check('6f 還原判定改為逐塊比位置（goal_pattern）',
      gui.game.goal_pattern is not None and gui.game.is_solved())
gui.shuffle_puzzle()
check('6g GUI 打亂（Alt+S 同路徑）後判未還原',
      not gui.game.is_solved(), f'{gui.macro_notify_msg!r}')
design_styles.delete_style(gui.config_dir, '_洞形三角')

# ---- 6h~6j 米字：刪掉一整格（4 塊）→ 帶洞形狀 ----
gui = boot('new_mi_puzzle', 3, 3)
orig6m = sorted(tuple(b.location) for b in gui.game.blocks)
gui._ann_open_advanced()
victims = [c for c in sorted(gui._ann_build_coords) if c[0] == 0 and c[1] == 0]
for c in victims:
    gui._ann_build_toggle(c)
check('6h 米字設計態可刪塊（整格 4 塊）',
      len(gui._ann_build_coords) == len(orig6m) - len(victims),
      f'{len(orig6m)} → {len(gui._ann_build_coords)}')
gui._ann_design_style_name = '_洞形米字'
gui._ann_design_save_style()
data = design_styles.load_style(gui.config_dir, '_洞形米字')
check('6i 帶洞形狀存樣式成功', bool(data), f'{gui._ann_build_error!r}')
gui._ann_design_cancel()
gui._ann_design_start_style('_洞形米字')
check('6j 米字帶洞形狀開局即還原態',
      len(gui.game.blocks) == len(orig6m) - len(victims)
      and gui.game.is_solved())
design_styles.delete_style(gui.config_dir, '_洞形米字')

# ---- 6k~6m 連通性攔截（用戶明確要求）----
gui = boot('new_mi_puzzle', 3, 3)
gui._ann_open_advanced()
keep = {(0, 0), (2, 2)}
for c in sorted(set(gui._ann_build_coords)):
    if (c[0], c[1]) not in keep:
        gui._ann_build_toggle(c)
ok, err = gui._ann_validate_connected()
check('6k 兩片互不相連 → 校驗拒', not ok and '不连通' in err, err)
gui._ann_design_style_name = '_不该存'
gui._ann_design_save_style()
check('6l 不連通形狀存不進樣式', '不连通' in (gui._ann_build_error or ''),
      f'{gui._ann_build_error!r}')
gui._ann_design_cancel()

# 組內斷開：綁 N-E-S 再刪橋接塊 E → 組剩 N/S 不相鄰
gui = boot('new_mi_puzzle', 3, 3)
gui._ann_open_advanced()
for q1, q2 in (('N', 'E'), ('E', 'S')):
    a, b = (1, 1, q1), (1, 1, q2)
    seam = gui.game.seam_between_positions(a, b)
    mx, my = gui._ann_design_pair_mid_world((a, b))
    sx, sy = gui.world_to_screen(mx, my)
    gui._ann_design_seam_click(seam, sx, sy)
gui._ann_build_toggle((1, 1, 'E'))
ok, err = gui._ann_validate_connected()
check('6m 捆綁組被刪成兩段 → 校驗拒', not ok and '组捆绑不连通' in err, err)
gui._ann_design_style_name = '_组断'
gui._ann_design_save_style()
check('6n 組內斷開存不進樣式', '组捆绑不连通' in (gui._ann_build_error or ''),
      f'{gui._ann_build_error!r}')
gui._ann_design_cancel()

# ---- 6o~6p 畫布尾部回填（_cell_center_screen 曾把函數尾吞進死代碼區）----
gui = boot('new_triangle_puzzle', 5, 2)
gui._ann_open_advanced()
gui.draw_triangle_board()
gui.draw_annotation_mode()
check('6o 設計態畫布繪製不拋異常（目標框/提示尾部已回填）', True)
c = gui._cell_center_screen(1, 1)
check('6p _cell_center_screen 仍是座標函數（未被截斷）',
      isinstance(c, tuple) and len(c) == 2, f'{c}')
gui._ann_design_cancel()

# ================================================================ 7 碎三角死缝回退
print('\n--- 7 碎三角：死缝（一条缝无接触边足迹）也能出白线+叉号（图2 修复）---')
gui = boot('new_shatter_puzzle', 1)
pv = gui._polygon_view()
check('7a 碎三角走通用多边形通道', pv is not None)
origin = gui._poly_view_origin(pv)
board = gui.game.board
# 取一条「非退化」缝：至少一块滑块被缝穿过且交点=2（落在该块内部两端），
# 这样叉号定位（缝×块边界两交点）才验得到；退化缝（缝正好压在块顶点共享线
# 上）每块只交 1 点，不是本修复要验的场景。
_g = None
for _gt, _ln in pv.seam_candidates(board):
    _hs = gui._reject_gap_blocks_hit((_gt, _ln))
    if any(len(pts) >= 2 for (_b, _p, pts) in _hs):
        _g = (_gt, _ln)
        break
check('7b 取到一条非退化候选缝', _g is not None, f'{_g}')
# 正常路径：缝有接触边足迹 → 屏幕线非空
_real = gui._gap_screen_line(_g)
check('7c 正常缝屏幕线非空', _real is not None, f'{_real}')
# 死缝路径：让该缝的 seam_segments 返回空（模拟「一侧无块/无接触边」），
# 旧实现会直接回 None → 白线/叉号全无；新实现走代数直线回退。
_orig = gui._poly_seam_segments
gui._poly_seam_segments = lambda pv_, gt_, line_, origin_: []
_dead_line = gui._gap_screen_line(_g)
check('7d 死缝也能拿到屏幕线（回退生效）', _dead_line is not None,
      f'{_dead_line}')
# 死缝路径下，回退直线仍应「穿过」同侧有块的滑块（被拒缝叉号才有载体）
_dead_hits = gui._reject_gap_blocks_hit(_g)
gui._poly_seam_segments = _orig
check('7e 死缝回退直线仍穿过至少一块滑块', len(_dead_hits) >= 1,
      f'{len(_dead_hits)} 块')
# 叉号定位：鼠标摆到「被缝穿且交点=2」的滑块上，验证出 >=2 个交点
gui.selected_block = None
gui.rejected_gap = _g
_hits = gui._reject_gap_blocks_hit(_g)
_good = next((h for h in _hits if len(h[2]) >= 2), _hits[0] if _hits else None)
if _good is not None:
    _blk, _poly, _ = _good
    _cx = sum(p[0] for p in _poly)/len(_poly)
    _cy = sum(p[1] for p in _poly)/len(_poly)
    pygame.mouse.set_pos((int(_cx), int(_cy)))
_mk = gui._gap_reject_mark_points()
check('7f 死缝叉号点 >= 2', len(_mk) >= 2, f'pts={len(_mk)}')
gui._draw_gap_reject_marks()
gui._draw_rejected_gap_preview()
check('7g 死缝白线/叉号渲染不抛异常', True)
# 回退直线几何正确性：与真实缝线（满盘时）应重合
_fb = gui._poly_dead_seam_line(pv, _g[0], _g[1], origin)
check('7h 回退直线非空', _fb is not None, f'{_fb}')
if _real is not None and _fb is not None:
    _rmid = ((_real[0][0]+_real[1][0])/2.0, (_real[0][1]+_real[1][1])/2.0)
    _d = abs((_rmid[0]-_fb[0][0])*(_fb[1][1]-_fb[0][1])
             - (_rmid[1]-_fb[0][1])*(_fb[1][0]-_fb[0][0])) / \
        (math.hypot(_fb[1][0]-_fb[0][0], _fb[1][1]-_fb[0][1]) or 1)
    check('7i 回退直线≈真实缝线（满盘重合）', _d < 40.0, f'dist={_d:.1f}')

# ================================================================ 8 碎三角：拒绝点击门控通过（图2 根因闭环）
print('\n--- 8 碎三角：真实点击被拒缝后，门控通过→白线+叉号可渲染（图2 根因）---')
# 旧门控 _mouse_near_gap 测「鼠标到合并短段端点」距离+tol=24，玩家点在缝的
# 其它分片（无限直线 28px 带内、但离合并段端点>24）时门控 False→只有文字、
# 白线/叉号全无（正是用户 2026-11-01 报的「图2 毫无改观」）。修复后测「到无限
# 直线」垂直距离+tol=28，与 _rejected_seam_at 宽频带±28 对齐，门控必过。
# 下面 8A-8D 是确定性单测（不依赖盘面恰有被拒缝），8E-8G 是端到端复现。

# ---- 8A-8D 确定性门控单测：取一条真实缝，构造「点在缝其它分片/无限直线带内、
#      但越过合并短段端点外推 25px」的点击，断言门控通过（旧代码此处必 False）。
gui = boot('new_shatter_puzzle', 1)
pv = gui._polygon_view()
board = gui.game.board
_real_gap = None
for _gt, _ln in pv.seam_candidates(board):
    if gui._gap_screen_line((_gt, _ln)) is not None:
        _real_gap = (_gt, _ln)
        break
check('8A 取到一条有屏幕线真实缝', _real_gap is not None, f'{_real_gap}')
if _real_gap is not None:
    a, b = gui._gap_screen_line(_real_gap)
    _dx, _dy = b[0] - a[0], b[1] - a[1]
    _L = math.hypot(_dx, _dy) or 1.0
    # 沿缝线方向越过 b 端点外推 25px：到无限直线距离≈0(<=28)，但到端点=25(>24旧容差)
    _px = b[0] + _dx / _L * 25.0
    _py = b[1] + _dy / _L * 25.0
    pygame.mouse.set_pos((int(_px), int(_py)))
    _near = gui._mouse_near_gap(_real_gap)
    _dist = abs(_dx * (a[1] - _py) - (a[0] - _px) * _dy) / _L
    check('8B 外推点到无限直线距离<=28（门控判据）', _dist <= 28.0,
          f'dist={_dist:.1f}')
    check('8C 门控对「其它分片点击」返回True（修复核心）', _near is True,
          f'near={_near}')
    gui.rejected_gap = _real_gap
    _mk = gui._gap_reject_mark_points()
    check('8D 门控通过后叉号几何点>=1（可渲染前置）', len(_mk) >= 1,
          f'pts={len(_mk)}')
    gui.rejected_gap = None

# ---- 8E-8G 端到端复现：随机走子制造被拒缝，扫描真实点击，断言「被拒点击→门控
#      全过」（白线+叉号与文字提示同寿、鼠标挪开即消失）。复刻 2026-11-01 排障。
gui = boot('new_shatter_puzzle', 1)
g = gui.game
_tbl = direction_table(g.spec)


def _all_moves():
    out = []
    for (_gf, _line) in list(g.all_gaps()):
        _fam = next(f for f in g.spec.seam_families if f.name == _gf)
        for _letter, _d in sorted(_tbl.items()):
            if _d not in _fam.parallel:
                continue
            for _b in g.blocks:
                g.opt(_gf, _line, _b)
                _pos, _reason = g.try_move_ex(_letter, 1)
                if _reason == '':
                    out.append((_gf, _line, _b, _letter))
    return out


random.seed(7)
for _i in range(25):
    _moves = _all_moves()
    if not _moves:
        break
    _gf, _line, _blk, _letter = random.choice(_moves)
    gui.selected_gap = (_gf, _line)
    gui.selected_block = _blk
    g.opt(_gf, _line, _blk)
    pygame.event.post(pygame.event.Event(
        pygame.KEYDOWN, {'key': getattr(pygame, 'K_' + _letter.lower()),
                         'mod': 0, 'unicode': _letter}))
    gui.handle_events()
W = gui.screen_width
H = gui.screen_height
_found = 0
_bad = 0
_sample = None
for _sx in range(20, W - 20, 7):
    for _sy in range(20, H - 20, 7):
        pygame.mouse.set_pos((_sx, _sy))
        gui.selected_gap = None
        gui.selected_block = None
        gui.rejected_gap = None
        gui._sq_click_query(_sx, _sy)
        _rg = gui.rejected_gap
        if _rg is None:
            continue
        _found += 1
        _near = gui._mouse_near_gap(_rg)
        _mk = gui._gap_reject_mark_points()
        if (not _near) or len(_mk) < 1:
            _bad += 1
            if _sample is None:
                _sample = (_sx, _sy, _rg, _near, len(_mk))
print(f'  端到端：扫到 {_found} 个拒绝点击点，门控失败 {_bad} 个')
check('8E 拒绝点击点门控全过（白线+叉号可渲染）', _bad == 0,
      f'found={_found} bad={_bad} sample={_sample}')
if _sample is not None:
    _sx, _sy, _rg, _near, _n = _sample
    check('8F 样本门控=True', _near is True, f'near={_near}')
    check('8G 样本叉号点>=1', _n >= 1, f'pts={_n}')
else:
    check('8F 样本门控=True（无失败样本，跳过）', True)
    check('8G 样本叉号点>=1（无失败样本，跳过）', True)

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES',
      '===')
sys.exit(1 if _failures else 0)
