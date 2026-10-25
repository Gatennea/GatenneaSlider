# -*- coding: utf-8 -*-
r"""搭积木编辑器 GUI 集成测试（dummy video，不开窗口）。

覆盖（Mixin 的**逻辑路径 + 绘制路径**都在内）：
  1. 打开/退出：备份还原（game / 相机 / zoom / 三形态旗标）
  2. 预览局：EngineGame(kind='__editor__')、spec 名、朝向表恒定
  3. 通用渲染通道能吃下预览局：draw_board + _med_draw_overlay 不炸
  4. 放置/删除：贴边吸附 + 自由落点 + 点块删除 + 重叠拒放
  5. 整形：R 旋转 / F 镜像（索引查找，不是取模猜）
  6. 撤销/重做
  7. 缝族开关真的改变移动计数（2026-10-25 修的真 bug 的回归护栏）
  8. 保存门：空盘 / 不连通 / 冻形 / 合格 四种
  9. 保存 → 热注册 → 菜单刷新 → 可建局（写临时目录，不污染 models/）
 10. 事件钩子：棋盘点击被消费、顶栏菜单点击放行、ESC 退出
 11. 会话期被换局（菜单开了新谜题）→ 就地收摊，不还原错对象

跑法：D:/python/python.exe test/_test_model_editor.py
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

import pygame

from engine import editor_geom as eg
from engine.adapter import EngineGame
from engine.model_loader import load_shapes
from engine.model_registry import loaded
from engine.registry import board_types, make_board, unregister_board_type

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('    FAIL:', msg)
    return bool(cond)


# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------
def _make_gui():
    from GUI import SliderGUI
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    return gui


def _tri_indices(gui):
    """编辑器里 tri 形状的 ▲ / ▼ 下标。"""
    imgs = gui._med['images']['tri']
    up = eg.normalize(((0, 0), (1, 0), (0, 1)))
    dn = eg.normalize(((0, 0), (1, 0), (1, -1)))
    i_up = next(i for i, im in enumerate(imgs) if im == up)
    i_dn = next(i for i, im in enumerate(imgs) if im == dn)
    return i_up, i_dn


def _put_tri(gui, p, idx):
    gui._med['placed'][(p, 'tri', idx)] = gui._med['images']['tri'][idx]


def _big_triangle(gui, k=3):
    """摆一个边长 k 的实心正三角（引擎 tri preset 的还原态，保证可动）。"""
    i_up, i_dn = _tri_indices(gui)
    for i in range(k):
        for j in range(k - i):
            _put_tri(gui, (i, j), i_up)
    for i in range(k - 1):
        for j in range(k - 1 - i):
            _put_tri(gui, (i, j), i_dn)


def _med_free_r():
    """编辑器自由落点搜索半径（从源码读，免得测试里抄一份常量）。"""
    from gui import model_editor as me
    return me._FREE_R


def _center_screen(gui, key):
    """块重心 → 屏幕坐标（点击/拖动的落点都用它）。"""
    pts = eg.poly_of(key[0], gui._med['placed'][key])
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return gui._med_geom_to_screen(cx, cy)


def _gui_click(gui, sx, sy, button=1):
    """真实鼠标点击：down + up（放置与缝合都在 up 时结算）。"""
    for typ in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        gui._med_handle_event(pygame.event.Event(
            typ, {'button': button, 'pos': (float(sx), float(sy))}))


def _gui_drag(gui, x0, y0, x1, y1, button=1):
    """真实鼠标拖动：down → 三个 motion → up（超 4px 阈值才成拖）。"""
    gui._med_handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {'button': button,
                                 'pos': (float(x0), float(y0))}))
    for t in (0.3, 0.7, 1.0):
        gui._med_handle_event(pygame.event.Event(
            pygame.MOUSEMOTION,
            {'pos': (float(x0 + (x1 - x0) * t), float(y0 + (y1 - y0) * t)),
             'rel': (0, 0), 'buttons': (1, 0, 0)}))
    gui._med_handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {'button': button,
                               'pos': (float(x1), float(y1))}))


# ----------------------------------------------------------------------
# 1. 打开 / 退出
# ----------------------------------------------------------------------
def t_open_close():
    gui = _make_gui()
    orig_game = gui.game
    orig_cam = (gui.camera_x, gui.camera_y)
    orig_zoom = gui.zoom
    gui._med_open()
    check(gui.med_active, '打开后 med_active 应为真')
    med = gui._med
    check(med is not None, '会话 dict 应已建立')
    check(isinstance(gui.game, EngineGame), '预览局应为 EngineGame')
    check(gui.game.kind == '__editor__', f'预览 kind 错：{gui.game.kind}')
    check(gui.game.spec.name == '__editor_preview__',
          f'预览 spec 名错：{gui.game.spec.name}')
    shapes = load_shapes()
    check(len(med['images']) == len(shapes),
          f'形状库快照应等于 shapes.json（{len(med["images"])} vs {len(shapes)}）')
    check(len(med['placed']) == 1, '开局应自带一块')
    check(len(gui.game.spec.goal_blocks) == 1,
          '预览 spec 的还原态应只有一颗种子（原点锚）')
    gui._med_close()
    check(not gui.med_active, '退出后 med_active 应为假')
    check(gui.game is orig_game, '退出后 game 应还原')
    check((gui.camera_x, gui.camera_y) == orig_cam, '退出后相机应还原')
    check(gui.zoom == orig_zoom, '退出后 zoom 应还原')
    check(not gui.triangle_mode and not gui.mi_mode, '退出后旗标应还原')


def t_second_open_refused():
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_open()          # 重复进入只提示，不覆盖备份
        check(gui.med_active, '重复进入后应仍在会话中')
    finally:
        gui._med_close()
    check(not gui.med_active, '退出后应离开会话')


def t_spec_stable():
    """spec 对象在会话内必须是同一个（原点缓存才有效）。"""
    gui = _make_gui()
    gui._med_open()
    try:
        s1 = gui._med_spec()
        _put_tri(gui, (0, 0), _tri_indices(gui)[0])
        gui._med_rebuild()
        check(gui._med_spec() is s1, '编辑后 spec 对象应保持不变')
        check(gui.game.spec is s1, 'game.spec 应仍是同一对象')
    finally:
        gui._med_close()


# ----------------------------------------------------------------------
# 2. 渲染 / 命中
# ----------------------------------------------------------------------
def t_render():
    """预览局必须能被通用多边形通道画出来（含编辑器浮层）。"""
    gui = _make_gui()
    gui._med_open()
    try:
        _big_triangle(gui)
        gui._med_rebuild()
        gui.draw_board()                 # 走 _draw_polygon_board
        gui._med_draw_overlay()          # 调色盘 + 工具栏 + 幽灵
        gui.draw_status_bar()
        gui.draw_menu_bar()
        gui.draw_puzzle_sub_menu('models', 100)
        gui._med_mouse_motion(
            pygame.event.Event(pygame.MOUSEMOTION, {'pos': (400, 300)}))
        check(True, '')
    except Exception:
        traceback.print_exc()
        check(False, '渲染路径抛异常（见上）')
    finally:
        gui._med_close()


def t_ghost():
    gui = _make_gui()
    gui._med_open()
    try:
        _big_triangle(gui)
        gui._med_rebuild()
        gui._med_mouse_motion(
            pygame.event.Event(pygame.MOUSEMOTION, {'pos': (500, 320)}))
        check(gui._med['ghost'] is not None, '悬停应产出幽灵预览')
    finally:
        gui._med_close()


# ----------------------------------------------------------------------
# 3. 放置 / 删除 / 整形 / 撤销
# ----------------------------------------------------------------------
def t_place():
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        check(len(gui._med['placed']) == 0, '清空后应为 0 块')
        check(gui._med_place_at(0.4, 0.3), '空盘自由落点应放得上')
        check(len(gui._med['placed']) == 1, '落点后应 1 块')
        check(gui._med_place_at(1.0, 0.5), '共享边中点应吸附成菱形')
        check(len(gui._med['placed']) == 2, '吸附后应 2 块')
        #  invariants：无论怎么放，盘面永不允许两块正面积重叠
        from engine import geometry_ops as gops
        polys = [eg.poly_of(k[0], offs) for k, offs in gui._med['placed'].items()]
        bad = [(i, j) for i in range(len(polys)) for j in range(i + 1, len(polys))
               if gops.convex_overlap(polys[i], polys[j])]
        check(not bad, f'放置结果不应有重叠：{bad}')
        # 远处再自由落一块（第二朵云）
        check(gui._med_place_at(8.0, 8.0), '远处应能自由落点')
        check(len(gui._med['placed']) == 3, '远处落点后应 3 块')
        polys = [eg.poly_of(k[0], offs) for k, offs in gui._med['placed'].items()]
        bad = [(i, j) for i in range(len(polys)) for j in range(i + 1, len(polys))
               if gops.convex_overlap(polys[i], polys[j])]
        check(not bad, f'远处落点后仍不应有重叠：{bad}')
    finally:
        gui._med_close()


def t_click_inside_block_places():
    """左键单击（含点在块内部）= 接着这块放一块（2026-10-25 用户定案）。

    以前左键点块是删除，手一抖就把刚放好的块删了；现在删除只在右键，
    左键单击永远是「放」——点在块里就是「接着它搭」，贴边吸附选最近空位。
    """
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        gui._med_place_at(0.4, 0.3)
        check(len(gui._med['placed']) == 1, '应先有 1 块')
        # ⚠️ event.pos 必须给浮点：int() 取整后 screen_to_world 会
        # round-trip 回 (0,0)（锚点），落点全偏（2026-10-25 踩过）。
        key = next(iter(gui._med['placed']))
        gui.camera_x = 400.0
        gui.camera_y = 200.0
        gui.zoom = 1.0
        sx, sy = _center_screen(gui, key)
        check(32 < sy < gui.screen_height - 66, f'测试落点应落在棋盘区：{sx},{sy}')
        _gui_click(gui, sx, sy)
        check(len(gui._med['placed']) == 2,
              f'点块内部应接着放一块（实得 {len(gui._med["placed"])}）')
    finally:
        gui._med_close()


def t_right_click_delete():
    """右键删块（左键不再兼任删除）。"""
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        gui._med_place_at(0.4, 0.3)
        gui._med_place_at(3.4, 0.3)
        check(len(gui._med['placed']) == 2, '应先有 2 块')
        key = next(iter(gui._med['placed']))
        gui.camera_x, gui.camera_y, gui.zoom = 400.0, 200.0, 1.0
        sx, sy = _center_screen(gui, key)
        _gui_click(gui, sx, sy, button=3)
        check(len(gui._med['placed']) == 1,
              f'右键应删掉一块（实得 {len(gui._med["placed"])}）')
        check(key not in gui._med['placed'], '删的应是右键点中的那块')
    finally:
        gui._med_close()


def t_drag_move_block():
    """按住左键拖块 = 移动（整数格平移 ⇒ 天然贴合）。"""
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        gui._med_place_at(0.4, 0.3)
        key = next(iter(gui._med['placed']))
        n0 = len(gui._med['placed'])
        gui.camera_x, gui.camera_y, gui.zoom = 400.0, 250.0, 1.0
        sx, sy = _center_screen(gui, key)
        step = gui.cell_size * gui.zoom          # 拖整整 2 格
        _gui_drag(gui, sx, sy, sx, sy + 2 * step)
        keys = list(gui._med['placed'])
        check(len(keys) == n0, f'拖动不应增减块（{n0} -> {len(keys)}）')
        check(keys != [key], f'拖动后键应改变（仍 {keys}）')
        # 位移必须是**整数格**（同晶格才谈得上自动贴合）
        d = (keys[0][0][0] - key[0][0], keys[0][0][1] - key[0][0])
        check(all(isinstance(v, int) for v in d), f'锚点仍应是整数：{d}')
        check(d != (0, 0), f'锚点应真的挪了：{d}')
    finally:
        gui._med_close()


def t_drag_empty_pans():
    """空白处按住左键拖动 = 平移画布，不放置。"""
    gui = _make_gui()
    gui._med_open()
    try:
        n0 = len(gui._med['placed'])
        cam = (gui.camera_x, gui.camera_y)
        _gui_drag(gui, 860, 180, 930, 250)
        check(len(gui._med['placed']) == n0, '拖空白不应放置')
        check((gui.camera_x, gui.camera_y) != cam, '拖空白应平移画布')
    finally:
        gui._med_close()


def t_turn_block_hover():
    """悬停某块按 R = 只转那一块。"""
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        gui._med_place_at(0.4, 0.3)
        key = next(iter(gui._med['placed']))
        gui.camera_x, gui.camera_y, gui.zoom = 400.0, 200.0, 1.0
        sx, sy = _center_screen(gui, key)
        gui._med_handle_event(pygame.event.Event(
            pygame.MOUSEMOTION, {'pos': (float(sx), float(sy)),
                                 'rel': (0, 0), 'buttons': (0, 0, 0)}))
        check(gui._med['hover'] == key,
              f'悬停应命中这块（hover={gui._med["hover"]}）')
        gui._med_handle_event(pygame.event.Event(
            pygame.KEYDOWN, {'key': pygame.K_r, 'mod': 0, 'unicode': 'r'}))
        keys = list(gui._med['placed'])
        check(len(keys) == 1, f'转单块不应增减块（实得 {len(keys)}）')
        check(keys != [key], f'R 应转掉那一块（仍是 {key}）')
    finally:
        gui._med_close()


def t_delete():
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        gui._med_place_at(0.4, 0.3)
        bx, by = eg.to_plane((0, 0))
        check(gui._med_delete_at(bx + 0.3, by + 0.2), '点块内部应删除')
        check(len(gui._med['placed']) == 0, '删除后应 0 块')
        check(not gui._med_delete_at(bx + 5.0, by + 5.0), '空白处删不到东西')
    finally:
        gui._med_close()


def t_rotate_mirror():
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med['shape'] = 'half'          # 12 像，转/镜都换得动
        gui._med['cursor'] = 0
        n = len(gui._med['images']['half'])
        check(n == 12, f'half 应有 12 个像，实得 {n}')
        # R 只走旋转轨道：half 无旋转对称 → 6 步一周
        seen = {gui._med['cursor']}
        for _ in range(6):
            gui._med_rotate()
            seen.add(gui._med['cursor'])
        check(len(seen) == 6, f'R 转 6 步应回到旋转轨道（6 个），实得 {len(seen)}')
        check(gui._med['cursor'] == 0, 'R 转 6 步应回到起点')
        # F 跳到镜像侧，那里另有一个 6 步轨道；两边合起来才是全部 12 个
        gui._med_mirror()
        c1 = gui._med['cursor']
        check(c1 != 0, '镜像应跳到另一侧')
        seen2 = {c1}
        for _ in range(6):
            gui._med_rotate()
            seen2.add(gui._med['cursor'])
        check(len(seen2) == 6, f'镜像侧也应是 6 步轨道，实得 {len(seen2)}')
        check(len(seen | seen2) == 12,
              f'旋转轨道 + 镜像轨道应并成全部 12 个朝向，实得 {len(seen | seen2)}')
        gui._med_mirror()
        check(gui._med['cursor'] == 0, '镜像两次应回到原处')
    finally:
        gui._med_close()


def t_undo_redo():
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        for i in range(4):
            gui._med_place_at(0.4 + 0.1 * i, 0.3)
        n = len(gui._med['placed'])
        check(n == 4, f'连放 4 次应 4 块，实得 {n}')
        for _ in range(n):
            gui._med_undo()
        check(len(gui._med['placed']) == 0, '全撤销后应 0 块')
        for _ in range(n):
            gui._med_redo()
        check(len(gui._med['placed']) == n, '全重做后应复原')
    finally:
        gui._med_close()


# ----------------------------------------------------------------------
# 4. 缝族 / 保存门
# ----------------------------------------------------------------------
def t_family_toggle():
    """关掉一条缝族，合法移动数必须真的降（2026-10-25 真 bug 的回归护栏）。"""
    gui = _make_gui()
    gui._med_open()
    try:
        _big_triangle(gui)
        gui._med_rebuild()
        fams = gui._med_families()
        check(bool(fams), '边长 3 正三角应当推导出活缝')
        if not fams:
            return
        n_all = gui._med_move_info()[0]
        check(n_all > 0, f'合格盘应有合法移动，实得 {n_all}')
        off = fams[0][0]
        gui._med['fam_off'] = {off}
        gui._med['cnt_sig'] = None
        n_less = gui._med_move_info()[0]
        check(n_less < n_all,
              f'关掉 {off} 后移动数没降（{n_all} → {n_less}）：'
              f'计数用的还是含全部族的预览 spec')
        gui._med['fam_off'] = set()
        gui._med['cnt_sig'] = None
        check(gui._med_move_info()[0] == n_all, '开回应复原计数')
    finally:
        gui._med_close()


def t_gate():
    gui = _make_gui()
    gui._med_open()
    try:
        gui._med_clear()
        ok, why = gui._med_gate()
        check(not ok and '空盘' in why, f'空盘应被拒：{why}')
        gui._med_place_at(0.4, 0.3)
        gui._med_place_at(8.0, 8.0)
        ok, why = gui._med_gate()
        check(not ok and '连通' in why, f'不连通应被拒：{why}')
        gui._med_clear()
        gui._med_place_at(0.4, 0.3)
        ok, why = gui._med_gate()
        check(not ok, f'单块冻形应被拒：{why}')
        _big_triangle(gui)
        gui._med_rebuild()
        ok, why = gui._med_gate()
        check(ok, f'边长 3 正三角应过门：{why}')
    finally:
        gui._med_close()


# ----------------------------------------------------------------------
# 5. 保存 → 热注册 → 菜单
# ----------------------------------------------------------------------
def t_save_hot_reload():
    import engine.model_loader as ml
    gui = _make_gui()
    gui._med_open()
    tmp = tempfile.mkdtemp(prefix='med_test_')
    old = ml.DEFAULT_MODEL_DIR
    ml.DEFAULT_MODEL_DIR = tmp
    try:
        _big_triangle(gui)
        gui._med_rebuild()
        gui._med['name'] = 'built_by_test'
        gui._med_save()
        check(os.path.exists(os.path.join(tmp, 'built_by_test.json')),
              '保存应写出文件')
        check('built_by_test' in loaded(), '保存后应已安装')
        check('built_by_test' in board_types(), '保存后应已注册')
        b = make_board('built_by_test')
        check(b.block_count == 9, f'建局块数应 9，实得 {b.block_count}')
        check(b.has_legal_move(1), '建局应有合法移动')
        gui._refresh_puzzle_presets()
        items = gui.puzzle_sub_presets['models']
        check(not any(len(p) == 3 and p[1] == '__editor__' for p in items),
              '模型子菜单只列开局项，不再带编辑器新建入口（2026-10-25）')
        check(any(len(p) >= 5 and p[4] == 'built_by_test' for p in items),
              '菜单应出现刚保存的模型')
        gui._med_save()
        check(gui._med['confirm_overwrite'], '覆盖应要二次确认')
        gui._med_save()
        check(not gui._med['confirm_overwrite'], '二次确认后应放行')
    finally:
        if 'built_by_test' in board_types():
            unregister_board_type('built_by_test')
        ml.DEFAULT_MODEL_DIR = old
        gui._med_close()


def t_build_doc_loadable():
    """合成的文档必须过得了加载器 + A0–A2（reload 用的就是这套）。"""
    from engine.model_loader import load_model
    from engine.model_validate import validate
    gui = _make_gui()
    gui._med_open()
    try:
        _big_triangle(gui)
        gui._med_rebuild()
        doc = gui._med_build_doc('doc_probe')
        check(doc['solved'] == 'exact', '编辑器模型应逐块还原')
        check(all(s['rank'] == 'centroid' for s in doc['seams']),
              '编辑器产出的缝族应一律 centroid rank')
        m = load_model(doc)
        errs = [p for p in validate(m, deep=False) if p.level == 'error']
        check(not errs, f'文档应过 A0–A2：{[str(p) for p in errs]}')
    finally:
        gui._med_close()


# ----------------------------------------------------------------------
# 6. 事件钩子 / 换局收摊
# ----------------------------------------------------------------------
def t_event_routing():
    gui = _make_gui()
    gui._med_open()
    try:
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (420, 320)})
        check(gui._med_handle_event(ev) is True, '棋盘左键应被消费')
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (60, 10)})
        check(gui._med_handle_event(ev) is False, '顶栏菜单区应放行')
        ev = pygame.event.Event(pygame.KEYDOWN,
                                {'key': pygame.K_r, 'mod': 0, 'unicode': 'r'})
        check(gui._med_handle_event(ev) is True, '键盘应被消费')
        ev = pygame.event.Event(pygame.KEYDOWN,
                                {'key': pygame.K_ESCAPE, 'mod': 0, 'unicode': ''})
        check(gui._med_handle_event(ev) is True, 'ESC 应被消费')
        check(not gui.med_active, 'ESC 后应退出会话')
    finally:
        gui._med_close()


def t_abandon_on_swap():
    """会话期从菜单开了新谜题 → 收摊，且绝不把旧局还原到新局上。"""
    gui = _make_gui()
    gui._med_open()
    preview = gui.game
    try:
        gui.new_puzzle(6, 6, 1)          # 模拟「谜题菜单点了矩形 6×6」
        check(gui.game is not preview, '换局后 game 应已是新局')
        gui._med_draw_overlay()          # 绘制侧同一帧内发现并撤浮层
        check(not gui.med_active, '绘制侧应发现换局并收摊')
        # 事件侧同样发现
        gui._med_active = True
        gui._med = {'game': preview, 'backup': {'game': preview}}
        ev = pygame.event.Event(pygame.KEYDOWN,
                                {'key': pygame.K_r, 'mod': 0, 'unicode': 'r'})
        check(gui._med_handle_event(ev) is False, '事件侧应放行并收摊')
        check(not gui.med_active, '事件侧收摊后应离开会话')
        check(gui.game is not preview, '新局绝不能被旧局覆盖')
    finally:
        gui._med_close()


def t_menu_entry():
    """入口结构（2026-10-25 创造模式重组后）：

    玩家入口 = 右下角「模式」开关 → 创造 → ② 还原状态设计 → 搭积木。
    谜题菜单不再有新建入口（「高级选项...」「＋ 搭建新模型...」均废止），
    「模型谜题 ▸」只列已存模型的开局项。
    """
    gui = _make_gui()
    gui._refresh_puzzle_presets()
    names = [p[0] for p in gui.puzzle_presets]
    check('高级选项...' not in names, '谜题菜单不应再有「高级选项...」')
    items = gui.puzzle_sub_presets['models']
    check(not any(len(p) == 3 and p[1] == '__editor__' for p in items),
          '「模型谜题 ▸」不应再有编辑器新建入口（统一走模式开关）')
    check(items and items[0][0] == '__group__', '子菜单首项应是分组标题')
    # 渲染路径仍安全（无 3 元组编辑器条目了，但分组标题/占位文案要能画）
    gui.puzzle_sub_open = 'models'
    gui.puzzle_sub_rects = [pygame.Rect(0, 0, 10, 10)]
    gui.puzzle_sub_hovered = -1
    try:
        gui.draw_puzzle_sub_menu('models', 100)
        check(True, '')
    except Exception:
        traceback.print_exc()
        check(False, '画子菜单抛异常')
    # 真实入口：模式开关 → 创造 → 还原态设计 → 搭积木
    gui.set_game_mode('create')
    gui._ann_btn_home_restore()
    gui._ann_draw_bar()
    check('blocks' in gui._ann_btn_rects,
          '还原态二级应有「搭积木」按钮')
    gui._ann_btn_blocks()
    check(gui.med_active, '点「搭积木」应能开会话')
    gui._med_close()
    check(not gui.med_active, '退出后应离开会话')
    check(gui.create_mode, '退出编辑器不应掉出创造模式')
    check(gui._ann_home_sub == 'restore',
          '退出编辑器应回到「还原态设计」二级（从那儿进来的）')

    # 工具条与格子画布**同一套外观**（gui/editor_chrome）：右下悬浮条、
    # 贴状态栏上沿 8px、主操作从右往左「退出 / 试玩 / 保存」
    gui2 = _make_gui()
    gui2.set_game_mode('create')
    gui2._ann_btn_home_restore()
    gui2._ann_btn_blocks()
    bar = gui2._med_bar_rect()
    check(bar.bottom == gui2.screen_height - gui2.status_bar_height - 8,
          f'工具条应贴状态栏上沿 8px：bottom={bar.bottom}')
    check(bar.x >= gui2._med_panel_rect().right,
          f'工具条不应压到左面板：bar.x={bar.x} panel.right={gui2._med_panel_rect().right}')
    gui2._med_draw_bar()
    acts = {a for _r, a in gui2._med['bar_btns']}
    check(acts == {'exit', 'play', 'save', 'undo', 'clear'},
          f'按钮集合应完整：{sorted(acts)}')
    pos = {a: r for r, a in gui2._med['bar_btns']}
    check(pos['exit'].x > pos['play'].x > pos['save'].x,
          f'主操作应从右往左：退出 / 试玩 / 保存（{pos["exit"].x}, '
          f'{pos["play"].x}, {pos["save"].x}）')
    gui2._med_close()


def t_bundle_toggle():
    """点缝捆绑/解绑：同族整组滑动，剪开恢复独立。

    ⚠️ 菱形（2 块）全盘同组时**仍然 0 移**是正确的引擎语义：唯一的缝另
    一侧在整个盘面里是空的，整组滑出去没有对侧块可推。所以「捆成刚体后
    滑得动」的断言必须上大盘（下面用边长 3 正三角）。
    """
    gui = _make_gui()
    gui._med_open()
    try:
        i_up, i_dn = _tri_indices(gui)
        # 菱形：▲(0,0) + ▼(0,0)（共边相邻）
        _put_tri(gui, (0, 0), i_up)
        _put_tri(gui, (0, 0), i_dn)
        gui._med_rebuild()
        seams = eg.shared_edges(gui._med['placed'])
        check(len(seams) == 1, f'菱形应恰有 1 条共享边，实得 {len(seams)}')
        ka, kb, mid = seams[0]
        n0 = gui._med_move_info()[0]
        check(n0 == 0, f'菱形是冻形，应 0 移，实得 {n0}')
        # 捆绑：两块同组；全盘同组 ⇒ 缝的另一侧恒空 ⇒ 仍 0 移（引擎语义）
        gui._med_toggle_bundle(ka, kb)
        check(gui._med['groups'].get(ka) == gui._med['groups'].get(kb) != 0,
              '捆绑后两块应同组')
        check(gui._med_move_info()[0] == 0,
              '全盘同组时缝的另一侧恒空，仍应 0 移（引擎语义，非 bug）')
        # 保存文档里捆绑组写得出（单人组才归一，这两块同组要留下）
        doc = gui._med_build_doc('bundle_probe')
        gs = [t.get('g', 0) for t in doc['tiles']]
        check(len(gs) == 2 and gs[0] == gs[1] > 0,
              f'捆绑组应整族同一个正组号：{gs}')
        # 解绑：恢复冻形
        gui._med_toggle_bundle(ka, kb)
        check(gui._med['groups'].get(ka) != gui._med['groups'].get(kb),
              '解绑后两块应不同组')
        check(gui._med_move_info()[0] == 0, '解绑后应回到 0 移')
        # ---- 大盘：捆成刚体后移动统计必须变 ----
        gui._med_clear()
        _big_triangle(gui)
        gui._med_rebuild()
        seams = eg.shared_edges(gui._med['placed'])
        base = gui._med_move_info()
        check(base[0] > 0, f'大盘应有合法移动，实得 {base[0]}')
        # 逐缝试捆：至少一条缝捆上后 (移动数, 可动块数) 要变；同一条再点一
        # 次（剪开）必须把计数还原——开关的对称性
        changed = restored = 0
        for ka, kb, _mid in seams:
            gui._med_toggle_bundle(ka, kb)
            if gui._med_move_info() != base:
                changed += 1
                gui._med_toggle_bundle(ka, kb)
                if gui._med_move_info() == base:
                    restored += 1
            else:
                gui._med_toggle_bundle(ka, kb)
        check(changed > 0,
              f'大盘上至少一条缝捆绑后移动统计应变化（基准 {base}，'
              f'{changed}/{len(seams)} 条变了）')
        check(restored == changed,
              f'剪开必须把计数还原（{changed} 条变了，只有 {restored} 条还原）')
        check(gui._med_move_info() == base,
              f'逐缝捆/剪一轮后应全部恢复独立（{gui._med_move_info()} vs {base}）')
        # 全捆成一个大刚体 ⇒ 任何缝的另一侧都空 ⇒ 0 移
        # ⚠️ _med_toggle_bundle 是**开关**：已同组的缝再点一次就是剪开，
        # 所以这里要跳过已同组的边（否则循环把自己捆的又剪掉了）
        for ka, kb, _mid in seams:
            ga = gui._med['groups'].get(ka, 0)
            gb = gui._med['groups'].get(kb, 0)
            if ga and gb and ga == gb:
                continue
            gui._med_toggle_bundle(ka, kb)
        allg = {g for g in gui._med['groups'].values() if g}
        check(len(allg) == 1, f'全捆后应只剩一个大组，实得 {allg}')
        check(gui._med_move_info() == (0, 0),
              f'全盘一个刚体时应 0 移（对侧恒空），实得 {gui._med_move_info()}')
        doc = gui._med_build_doc('bundle_all')
        gs = [t.get('g', 0) for t in doc['tiles']]
        check(len(gs) == 9 and len(set(gs)) == 1 and gs[0] > 0,
              f'全捆后每块都应带同一个正组号：{gs}')
        # 逐缝剪开一轮：不再有「同组缝」，且盘面解冻。
        # ⚠️ 剪开只把 ka 侧摘出组、kb 侧保留旧组号：旧组若还有别的成员，
        # 会留下**无缝相连**的余组（与设计态点缝同口径，非 bug）——所以
        # 这里不断言计数复原，只断言「没有缝还捆着」+「不再全冻」。
        for ka, kb, _mid in seams:
            ga = gui._med['groups'].get(ka, 0)
            gb = gui._med['groups'].get(kb, 0)
            if ga and gb and ga == gb:
                gui._med_toggle_bundle(ka, kb)
        still = [(ka, kb) for ka, kb, _m in seams
                 if gui._med['groups'].get(ka, 0)
                 and gui._med['groups'].get(ka, 0) == gui._med['groups'].get(kb, 0)]
        check(not still, f'剪完不应再有同组缝：{still}')
        check(gui._med_move_info()[0] > 0,
              f'剪开后盘面应解冻，实得 {gui._med_move_info()}')
    finally:
        gui._med_close()


def t_bundle_seam_click_routes():
    """右键点缝 = 捆绑（右键点块才是删除）；左键只管放和拖。"""
    gui = _make_gui()
    gui._med_open()
    try:
        i_up, i_dn = _tri_indices(gui)
        _put_tri(gui, (0, 0), i_up)
        _put_tri(gui, (0, 0), i_dn)
        gui._med_rebuild()
        _ka, _kb, mid = eg.shared_edges(gui._med['placed'])[0]
        gui.camera_x, gui.camera_y, gui.zoom = 400.0, 200.0, 1.0
        sx, sy = gui._med_geom_to_screen(*mid)
        # ⚠️ pos 必须浮点：取整后 screen_to_world 会回到 (0,0)（两块锚
        # 点），于是缝没判中、反把块删了（2026-10-25 踩过）
        # 缝归右键管：左键点缝会被当成「在这里放一块」，所以缝合必须
        # 走右键（2026-10-25 实测：左键点缝导致「想放一块却变成了捆绑」）。
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 3, 'pos': (sx, sy)})
        check(gui._med_handle_event(ev) is True, '点缝应被编辑器消费')
        n_grp = len({g for g in gui._med['groups'].values() if g})
        check(n_grp == 1, f'点缝应捆出一组，实得 {n_grp}')
        check(len(gui._med['placed']) == 2, '点缝不应增删块')
    finally:
        gui._med_close()


def t_playtest():
    """[试玩]：过门 → 保存 → 直接开局（编辑器就地收摊）。"""
    import engine.model_loader as ml
    gui = _make_gui()
    gui._med_open()
    tmp = tempfile.mkdtemp(prefix='med_play_')
    old = ml.DEFAULT_MODEL_DIR
    ml.DEFAULT_MODEL_DIR = tmp
    # 形状库也读 DEFAULT_MODEL_DIR/shapes.json：临时目录里补一份，否则
    # 后半段第二次 _med_open 会撞「库里没有可用形状」被拒入
    shutil.copy(os.path.join(old, 'shapes.json'),
                os.path.join(tmp, 'shapes.json'))
    try:
        _big_triangle(gui)
        gui._med_rebuild()
        gui._med['name'] = 'play_probe'
        gui._med_playtest()
        check('play_probe' in board_types(), '试玩应先把模型存上并注册')
        check(not gui.med_active, '开局后编辑器应就地收摊')
        from engine.adapter import EngineGame
        check(isinstance(gui.game, EngineGame), '试玩后应已是模型局')
        check(gui.game.kind == 'play_probe', f'试玩后 kind 错：{gui.game.kind}')
        # 不过门时试玩只提示、不开局
        gui._med_open()
        gui._med_clear()
        gui._med['name'] = 'frozen_probe'
        gui._med_playtest()
        check(gui.med_active, '冻形不应开局（应仍在编辑器里）')
        check('frozen_probe' not in board_types(), '冻形不应被保存')
    finally:
        for nm in ('play_probe', 'frozen_probe'):
            if nm in board_types():
                unregister_board_type(nm)
        ml.DEFAULT_MODEL_DIR = old
        gui._med_close()


def t_unbundle_all():
    """「清空捆绑」：一键解掉所有组（块不动、U 可撤销）。"""
    gui = _make_gui()
    gui._med_open()
    try:
        # 无组时：只提示，不推进 undo 栈
        n_undo = len(gui._med['undo'])
        gui._med_unbundle_all()
        check(len(gui._med['undo']) == n_undo, '无组时清空不应进 undo 栈')
        # 菱形：捆上再一键清
        i_up, i_dn = _tri_indices(gui)
        _put_tri(gui, (0, 0), i_up)
        _put_tri(gui, (0, 0), i_dn)
        gui._med_rebuild()
        ka, kb, _mid = eg.shared_edges(gui._med['placed'])[0]
        gui._med_toggle_bundle(ka, kb)
        check(any(gui._med['groups'].values()), '应先有捆绑组')
        gui._med_unbundle_all()
        check(not any(gui._med['groups'].values()), '清空后不应有捆绑组')
        check(len(gui._med['placed']) == 2, '清空捆绑不动块')
        gui._med_undo()
        check(gui._med['groups'].get(ka) == gui._med['groups'].get(kb) != 0,
              'U 应撤销回捆绑态')
        # 大盘：全捆 0 移 → 一键清 → 计数复原
        gui._med_clear()
        _big_triangle(gui)
        gui._med_rebuild()
        base = gui._med_move_info()
        for ka, kb, _m in eg.shared_edges(gui._med['placed']):
            ga = gui._med['groups'].get(ka, 0)
            gb = gui._med['groups'].get(kb, 0)
            if ga and gb and ga == gb:
                continue          # 开关语义：已同组再点就是剪开
            gui._med_toggle_bundle(ka, kb)
        check(gui._med_move_info()[0] == 0, '全捆应 0 移')
        gui._med_unbundle_all()
        check(gui._med_move_info() == base,
              f'一键清捆绑后计数应复原：{base} vs {gui._med_move_info()}')
    finally:
        gui._med_close()


def t_open_model():
    """「打开模型…」：把已保存的模型读回编辑器续编（含捆绑组）。"""
    import engine.model_loader as ml
    from engine import model_registry
    from engine.model_loader import load_model
    gui = _make_gui()
    gui._med_open()
    tmp = tempfile.mkdtemp(prefix='med_open_')
    old = ml.DEFAULT_MODEL_DIR
    ml.DEFAULT_MODEL_DIR = tmp
    # 形状库也读 DEFAULT_MODEL_DIR/shapes.json，临时目录补一份
    shutil.copy(os.path.join(old, 'shapes.json'),
                os.path.join(tmp, 'shapes.json'))
    try:
        # ① 保存一个带捆绑组的模型（名字排在 'shatter' 前，列表第一项就是它）
        _big_triangle(gui)
        gui._med_rebuild()
        ka, kb, _mid = eg.shared_edges(gui._med['placed'])[0]
        gui._med_toggle_bundle(ka, kb)
        gui._med['name'] = 'reopen_probe'
        check(gui._med_save(), '先保存一个模型')
        n_before = len(gui._med['placed'])
        move_before = gui._med_move_info()
        gid_before = {g for g in gui._med['groups'].values() if g}
        check(len(gid_before) == 1, f'保存前应恰有 1 个捆绑组：{gid_before}')
        gui._med_clear()
        check(len(gui._med['placed']) == 0, '清空后 0 块')
        # ② 弹列表：已有注册模型都应列出来
        gui._med_open_model_list()
        check(gui._med['open_list'] is not None, '有模型时应弹出列表')
        gui._med_draw_open_list()                     # 生成点击热区
        rects = gui._med['open_list']['rects']
        names = [n for _r, n in rects]
        check('reopen_probe' in names, f'列表应含刚保存的模型：{names}')
        # 点棋盘空白处 = 取消，不载入（别点顶栏区：那里事件钩子直接放行，
        # 压根进不到编辑器，2026-10-25 踩过）
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (10, gui.screen_height - 10)})
        check(gui._med_handle_event(ev) is True, '列表点击应被编辑器消费')
        check(gui._med['open_list'] is None, '点外面应取消列表')
        check(len(gui._med['placed']) == 0, '取消不应载入任何块')
        # ESC 同样取消
        gui._med_open_model_list()
        ev = pygame.event.Event(pygame.KEYDOWN,
                                {'key': pygame.K_ESCAPE, 'mod': 0, 'unicode': ''})
        check(gui._med_handle_event(ev) is True, 'ESC 应被编辑器消费')
        check(gui._med['open_list'] is None, 'ESC 应取消列表')
        # ③ 点第一项载入（续编）：块数/移动统计/捆绑组都读得回
        gui._med_open_model_list()
        gui._med_draw_open_list()
        rect, name = next((r, n) for r, n in gui._med['open_list']['rects']
                          if n == 'reopen_probe')
        cx, cy = rect.center
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                {'button': 1, 'pos': (cx, cy)})
        check(gui._med_handle_event(ev) is True, '点模型项应被消费')
        check(gui._med['open_list'] is None, '载入后列表应关闭')
        check(len(gui._med['placed']) == n_before,
              f'读回应还原 {n_before} 块，实得 {len(gui._med["placed"])}')
        check(gui._med['name'] == 'reopen_probe', '名字应随模型名')
        check(gui._med_move_info() == move_before,
              f'读回后移动统计应与保存时一致：{move_before} vs '
              f'{gui._med_move_info()}')
        check({g for g in gui._med['groups'].values() if g} == gid_before,
              f'捆绑组应读得回：{gui._med["groups"]}')
        check(gui._med_gate()[0], '读回后的模型应过保存门')
        # ④ basis / pos_scale 与编辑器（三角晶格、scale 1）不同的模型拒载，
        #    且不动当前盘面——碎三角（basis (0.866,0)/(0,0.5)、scale 3）
        #    就是现成样本
        n_now = len(gui._med['placed'])
        if 'shatter' in model_registry.loaded():
            check(not gui._med_load_model('shatter'),
                  '碎三角 basis/scale 不同，应拒载')
            check(len(gui._med['placed']) == n_now, '拒载不应动盘面')
        # ⑤ 顶点对不上形状库的模型：载入失败（一块都放不下）
        doc = load_model(json.load(open(
            os.path.join(tmp, 'reopen_probe.json'), encoding='utf-8'))).doc
        doc = dict(doc)
        doc['name'] = 'alien_shape'
        doc['orientations'] = {'x:0': {'shape': 'x',
                                       'off': [[0, 0], [3, 0], [0, 3]]}}
        doc['tiles'] = [{'p': [0, 0], 'o': 'x:0'}]
        model_registry._LOADED['alien_shape'] = load_model(doc)
        try:
            check(not gui._med_load_model('alien_shape'),
                  '形状库里没有的顶点应载入失败')
            check(len(gui._med['placed']) == n_now, '失败不应动盘面')
        finally:
            model_registry._LOADED.pop('alien_shape', None)
        # ⑥ 不存在的名字：明确失败
        check(not gui._med_load_model('no_such_model'), '不存在的模型应拒载')
    finally:
        for nm in ('reopen_probe', 'alien_shape'):
            model_registry._LOADED.pop(nm, None)
            if nm in board_types():
                unregister_board_type(nm)
        ml.DEFAULT_MODEL_DIR = old
        gui._med_close()


def t_free_point_reach():
    """自由落点必须长在盘面旁（防几千格外锚点 → 巨大 matrix → MemoryError）。

    2026-10-25 用户实测：最小缩放下点屏幕边缘，旧逻辑以点击处为圆心搜
    索，锚点放到 (7398, -3107)，预览局据此建 7000×4000 matrix——先卡半分
    钟再 MemoryError。现在搜索圆心是盘面 bbox 中心，边缘点击也必须落在
    盘面 ±_FREE_R 格内。
    """
    gui = _make_gui()
    gui._med_open()
    try:
        img = gui._med['images'][gui._med['shape']][gui._med['cursor']]
        gui.zoom = gui.min_zoom          # 最缩：屏幕边缘的世界坐标数千格外
        # 落点 = 「按点击方向算的锚点」夹到「盘面 bbox 外扩 _FREE_R」内：
        # 既有界（不建巨大 matrix），又朝用户点的方向长。上界取 _FREE_R 的
        # 数倍——种子块自身的顶点跨度也占几格，不能拿单个 _FREE_R 卡死。
        for pos in [(gui.screen_width - 5, 40), (gui.screen_width - 5, 640),
                    (5, 640), (500, gui.screen_height - 5)]:
            gx, gy = gui._med_screen_to_geom(*pos)
            p = gui._med_free_point(img, (gx, gy), gui._med['placed'])
            check(p is not None, f'边缘点击也应给落点：{pos}')
            check(max(abs(p[0]), abs(p[1])) <= _med_free_r() * 4,
                  f'落点必须在盘面邻域：{p}')
        # 完整放置路径：连点边缘 6 次，块数照涨、锚点量级不爆。
        # ⚠️ 连续往同一侧点会**沿该方向一格格长**（每次顶到 bbox 外扩边界，
        # 落下后 bbox 又扩 _FREE_R）——这是有意的：像「往那边继续搭」。
        # 这里只锁「不爆量级」（几百 = 已能建巨大 matrix）。
        for pos in [(990, 40), (990, 640), (10, 640), (500, 650), (140, 660),
                    (870, 60)]:
            gx, gy = gui._med_screen_to_geom(*pos)
            gui._med_place_at(gx, gy)
        for k in gui._med['placed']:
            check(max(abs(k[0][0]), abs(k[0][1])) <= 120,
                  f'放置后锚点量级不应爆（实得 {k[0]}）')
        check(len(gui._med['placed']) >= 2, '边缘点击也应能放置')
    finally:
        gui._med_close()


def t_rebuild_guard():
    """sanity 护栏：离盘面 > _MED_MAX_REACH 的锚点拒绝刷新预览局。

    正常编辑到不了（自由落点被 _FREE_R 管着）；这是给「打开模型」读入
    手写文件兜底的——预览局 update_matrix 按坐标跨度建 matrix，坏锚点能
    让主循环卡死（用户实测 MemoryError）。宁可拒收也不卡死。
    """
    from gui import model_editor as me
    gui = _make_gui()
    gui._med_open()
    try:
        board_before = gui.game.board
        img = gui._med['images'][gui._med['shape']][gui._med['cursor']]
        # 手工塞一个几千格外的锚点（模拟坏文件读入）
        gui._med['placed'][((5000, 5000), gui._med['shape'],
                            gui._med['cursor'])] = img
        msgs = []
        gui._med_notify = lambda t: msgs.append(t)
        gui._med_rebuild()
        check(gui.game.board is board_before,
              '坏锚点应被护栏拒收（board 不重建）')
        check(any('太远' in m for m in msgs),
              f'护栏应通知原因：{msgs}')
        check(me._MED_MAX_REACH == 64, '护栏阈值应保持 64 格')
    finally:
        gui._med_close()


# ----------------------------------------------------------------------
def main():
    cases = [t_open_close, t_second_open_refused, t_spec_stable,
             t_render, t_ghost,
             t_place, t_click_inside_block_places, t_delete,
             t_right_click_delete, t_drag_move_block,
             t_drag_empty_pans, t_turn_block_hover,
             t_rotate_mirror, t_undo_redo,
             t_bundle_toggle, t_bundle_seam_click_routes,
             t_family_toggle, t_gate,
             t_save_hot_reload, t_build_doc_loadable, t_playtest,
             t_event_routing, t_abandon_on_swap, t_menu_entry,
             t_unbundle_all, t_open_model,
             t_free_point_reach, t_rebuild_guard]
    for fn in cases:
        print(f'--- {fn.__name__} ---')
        try:
            fn()
        except Exception:
            traceback.print_exc()
            FAILS.append(f'{fn.__name__} 抛异常')
    print()
    if FAILS:
        print(f'共 {len(FAILS)} 项失败：')
        for f in FAILS:
            print('  ·', f)
        sys.exit(1)
    print(f'搭积木编辑器 GUI 集成测试全部通过（{len(cases)} 组）')


if __name__ == '__main__':
    main()
