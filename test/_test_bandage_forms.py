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
check('1c 點內部縫不彈「選不動」', '选不动' not in (gui.macro_notify_msg or ''),
      f'{gui.macro_notify_msg!r}')
opted = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
check('1d 內部縫 → 整組當滑塊選中', set(grp).issubset(opted),
      f'opted={len(opted)}')
check('1e selected_gap 未被污染', gui.selected_gap == ('h', 1),
      f'{gui.selected_gap}')
gui.draw_triangle_board()
check('1f 三角捆綁組渲染不拋異常', True)

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
check('2b 點內部縫不彈「選不動」', '选不动' not in (gui.macro_notify_msg or ''),
      f'{gui.macro_notify_msg!r}')
opted = {tuple(b.location) for b in gui.game.blocks if b.be_opted}
check('2c 內部縫 → 整胞當滑塊選中', set(quad).issubset(opted),
      f'opted={len(opted)}')
check('2d selected_gap 未被污染', gui.selected_gap == ('h', 1),
      f'{gui.selected_gap}')
gui.draw_mi_board()
check('2e 米字捆綁組渲染不拋異常', True)

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
menu = [p for p in gui.puzzle_presets
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

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES',
      '===')
sys.exit(1 if _failures else 0)
