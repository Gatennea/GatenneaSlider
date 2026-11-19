# -*- coding: utf-8 -*-
r"""三维创造模式：编辑会话 / 放挖 / 预览 / 保存门（2026-11-18，第 1–3 步）。

验收口径（对应 docs/spec/三维创造模式方案_2026-11-18.md）：
1. 三维 `mode_allowed('create')` 放行，`set_game_mode('create')` 能进；
2. 创造首页三维分支只给「打乱 / 还原」两条入口，不出现二维画布按钮；
3. 进入编辑器后草稿 = 当前局；点可见面挖块 / 放块都真正写回 game；
4. 取消恢复进入前的盘面；完成的保存门拦空盘/冻形，放行可玩局面；
5. 「还原目标」只过 restorable（允许满实心冻形），不套「必须有合法步」。

运行：D:\python\python.exe test\_test_cubic_create.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from engine import cubic_view  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f'  ok: {label}')
    else:
        FAILED.append(label)
        print(f'  FAIL: {label}' + (f'  <- {extra}' if extra is not None else ''))


def poly_center(pts):
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def new_gui():
    g = SliderGUI()
    assert g.new_cubic_puzzle(3, 3, 3, 1) is True
    g.set_game_mode('practice')
    return g


def t1_mode_entry():
    print('== 1. 三维创造档放行 ==')
    g = new_gui()
    check(g.mode_allowed('create'), 'mode_allowed(create) 为真')
    check(g.set_game_mode('create'), 'set_game_mode(create) 成功',
          g.macro_notify_msg)
    check(g.game_mode == 'create', '进入创造模式', g.game_mode)
    check(g.ann_canvas_active, '创造界面已激活')


def t2_home_buttons():
    print('== 2. 三维创造首页只给三维入口 ==')
    g = new_gui()
    g.set_game_mode('create')
    g._ann_home_sub = None
    g._ann_draw_bar()
    names = set(g._ann_btn_rects)
    check(names == {'home_shuffle', 'home_restore'}, '一级两钮', names)
    g._ann_btn_home_shuffle()
    g._ann_draw_bar()
    names = set(g._ann_btn_rects)
    check('cubic_manual_build' in names, '打乱二级有三维搭建', names)
    check('random_gen' in names, '打乱二级有三维随机生成', names)
    check('manual_build' not in names,
          '不出现二维手动构造（三维用 cubic_manual_build）', names)
    g._ann_btn_home_restore()
    g._ann_draw_bar()
    names = set(g._ann_btn_rects)
    check('cubic_goal_build' in names, '还原二级有三维搭建', names)
    check('design' not in names and 'blocks' not in names,
          '不出现二维格子画布/搭积木', names)


def t3_edit_and_click():
    print('== 3. 编辑会话：点面挖/放写回真盘 ==')
    g = new_gui()
    g.set_game_mode('create')
    g._ann_home_sub = 'shuffle'
    g._ann_btn_cubic_manual_build()
    check(g._cubic_edit_active, '进入会话')
    check(g._cubic_edit_length() == 27, '草稿 = 当前满盘',
          g._cubic_edit_length())
    g.draw_board()
    check(bool(g._cubic_scene and g._cubic_scene['faces']), '拿到可见面')
    face = g._cubic_scene['faces'][-1]
    pos = poly_center(face['pts'])
    before = len(g.game.blocks)
    g._cubic_edit_tool = 'remove'
    g._cubic_edit_click(pos)
    check(len(g.game.blocks) == before - 1,
          '挖一块写回 game', (before, len(g.game.blocks)))

    # 放回：挑一个朝外邻格还在容积内的可见面（边界面的邻格会越界）
    g.draw_board()
    g._cubic_edit_tool = 'add'
    add_pos = None
    for face in reversed(g._cubic_scene['faces']):
        cand = poly_center(face['pts'])
        g._cubic_edit_hover_update(cand)
        if g._cubic_edit_hover_valid:
            add_pos = cand
            break
    check(add_pos is not None, '找到可放的可见面邻格')
    if add_pos is not None:
        check(g._cubic_edit_hover_valid, '幽灵预览命中合法邻格',
              g._cubic_edit_hover)
        before = len(g.game.blocks)
        g._cubic_edit_click(add_pos)
        check(len(g.game.blocks) == before + 1,
              '放一块写回 game', (before, len(g.game.blocks)))
    g._cubic_edit_draw_overlay()
    g._ann_draw_bar()
    check('commit' in g._cubic_edit_btn_rects, '工具条按钮已建')


def t4_cancel_and_gate():
    print('== 4. 取消恢复 / 保存门 ==')
    g = new_gui()
    g.set_game_mode('create')
    g._ann_home_sub = 'shuffle'
    g._ann_btn_cubic_manual_build()
    g.draw_board()
    face = g._cubic_scene['faces'][-1]
    g._cubic_edit_tool = 'remove'
    g._cubic_edit_click(poly_center(face['pts']))
    check(len(g.game.blocks) == 26, '先挖一块')
    g._cubic_edit_cancel()
    g.draw_board()
    check(len(g.game.blocks) == 27, '取消后恢复 27 块',
          len(g.game.blocks))
    check(not g._cubic_edit_active, '会话已退出')

    # 空盘不能完成
    g._ann_btn_cubic_manual_build()
    g._cubic_edit_clear()
    check(not g._cubic_edit_commit(), '空盘被保存门拦下')
    check(g._cubic_edit_active, '被拦后仍留在编辑器')
    g._cubic_edit_cancel()

    # 抽掉中间整层：上下两层各自连通、整体不连通且冻住 → 保存门拦下
    g._ann_btn_cubic_manual_build()
    for c in range(3):
        for dep in range(3):
            g._cubic_draft.remove((1, c, dep))
    g._cubic_edit_apply()
    check(not g._cubic_edit_commit(), '不连通/冻形被保存门拦下')
    check('冻' in g.macro_notify_msg or '连通' in g.macro_notify_msg,
          '提示说明冻形/不连通', g.macro_notify_msg)
    g._cubic_edit_cancel()


def t5_goal_purpose():
    print('== 5. 还原目标：允许满实心冻形 ==')
    g = new_gui()
    g.config_dir = tempfile.mkdtemp(prefix='cubic_goal_')
    g.set_game_mode('create')
    g._ann_home_sub = 'restore'
    g._ann_btn_cubic_goal_build()
    check(g._cubic_edit_purpose == 'goal', '会话目标是还原态')
    check(not g._cubic_edit_commit(), '空样式名被保存门拦下')
    check(g._cubic_edit_active, '拦下后仍留在编辑器')
    # TEXTINPUT 走真实事件入口：输入法/字母都从这里进来
    ev = pygame.event.Event(pygame.TEXTINPUT, {'text': '满实心目标'})
    check(g.handle_annotation_event(ev), 'TEXTINPUT 被编辑会话消费')
    check(g._ann_design_style_name == '满实心目标', 'TEXTINPUT 写进名字框',
          g._ann_design_style_name)
    check(g._cubic_edit_commit(), '满实心还原目标能保存',
          g.macro_notify_msg)
    check(g.game.goal_pattern is not None, 'goal_pattern 已设')
    check(len(g.game.goal_pattern) == 27, '目标 27 块',
          len(g.game.goal_pattern or ()))
    check(g._ann_style_goal == '满实心目标', '样式名记到当前局',
          g._ann_style_goal)
    from gui import design_styles
    data = design_styles.load_style(g.config_dir, '满实心目标') or {}
    check(data.get('kind') == 'cubic', '样式落盘 kind=cubic', data.get('kind'))
    check(len(data.get('cells') or ()) == 27, '样式 cells 27 块',
          len(data.get('cells') or ()))


def t6_event_dispatch():
    print('== 6. 事件入口：按钮命中 / 工具条不穿透 ==')
    g = new_gui()
    g.set_game_mode('create')
    g._ann_home_sub = 'shuffle'
    g._ann_draw_bar()
    rect = g._ann_btn_rects['cubic_manual_build']
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                            {'pos': rect.center, 'button': 1})
    check(g.handle_annotation_event(ev), '首页按钮点击被创造模式消费')
    check(g._cubic_edit_active, '点击「三维搭建」进入会话')

    g.draw_board()
    g._ann_draw_bar()
    before = len(g.game.blocks)
    bar = g._ann_bar_rect
    # 条右侧空白（按钮都在左半），不应穿透到方块
    ev2 = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                             {'pos': (bar.right - 20, bar.y + 30),
                              'button': 1})
    check(g.handle_annotation_event(ev2), '工具条空白点击被消费')
    check(len(g.game.blocks) == before, '工具条空白不误挖/误放',
          (before, len(g.game.blocks)))

    # ESC 退出（事件入口）
    ev3 = pygame.event.Event(pygame.KEYDOWN, {'key': pygame.K_ESCAPE})
    check(g.handle_annotation_event(ev3), 'ESC 被编辑会话消费')
    check(not g._cubic_edit_active, 'ESC 退出编辑器')


def t7_step_carry():
    print('== 7. 等级步长随当前局带进草稿 ==')
    g = SliderGUI()
    check(g.new_cubic_puzzle(4, 4, 4, 2), '建立 4×4×4 等级2')
    g.set_game_mode('create')
    g._ann_btn_cubic_manual_build()
    check(g._cubic_edit_active, '进入会话')
    check(g._cubic_draft.step == 2, '草稿 step = current_step',
          (g._cubic_draft.step, g.current_step))


def t8_shifted_box():
    print('== 8. 滑出原盒后仍能进编辑器（不再报越过容积）==')
    g = SliderGUI()
    check(g.new_cubic_puzzle(4, 4, 4, 1), '建立 4×4×4')
    shifted = [(r, c, dep + 1) for r in range(4)
               for c in range(4) for dep in range(4)]
    g.game.apply_pattern(shifted)
    check(len(g.game.blocks) == 64, '整层推到 d=1..4')
    g.set_game_mode('create')
    g._ann_btn_cubic_manual_build()
    check(g._cubic_edit_active, '仍能进入三维搭建', g.macro_notify_msg)
    check((g._cubic_draft.m, g._cubic_draft.n, g._cubic_draft.d)
          == (4, 4, 5), '画布取 4×4×5 包围盒',
          (g._cubic_draft.m, g._cubic_draft.n, g._cubic_draft.d))
    check(g._cubic_draft.check_save().ok, '滑出原盒后连通性/可动性通过',
          g._cubic_draft.check_save().reasons)
    check(len(g.game.blocks) == 64, '盘面块数不变')
    g.draw_board()
    face = g._cubic_scene['faces'][-1]
    g._cubic_edit_tool = 'remove'
    before = len(g.game.blocks)
    g._cubic_edit_click(poly_center(face['pts']))
    check(len(g.game.blocks) == before - 1, '还能继续挖块',
          (before, len(g.game.blocks)))
    g._cubic_edit_cancel()
    check(not g._cubic_edit_active, '取消退出')
    check(len(g.game.blocks) == 64, '取消恢复 64 块', len(g.game.blocks))


def t9_negative_coords():
    print('== 9. 滑到负坐标：整体平移到 0 起点再编辑 ==')
    g = SliderGUI()
    check(g.new_cubic_puzzle(4, 4, 4, 1), '建立 4×4×4')
    shifted = [(r, c, dep - 1) for r in range(4)
               for c in range(4) for dep in range(4)]
    g.game.apply_pattern(shifted)
    check([min(b.location[i] for b in g.game.blocks) for i in range(3)]
          == [0, 0, -1], '整层推到 d=-1..2')
    g.set_game_mode('create')
    g._ann_btn_cubic_manual_build()
    check(g._cubic_edit_active, '负坐标也能进入搭建', g.macro_notify_msg)
    check((g._cubic_draft.m, g._cubic_draft.n, g._cubic_draft.d)
          == (4, 4, 5), '画布仍取 4×4×5')
    check([min(b.location[i] for b in g.game.blocks) for i in range(3)]
          == [0, 0, 0], '盘面已整体平移到 0 起点')
    check(g._cubic_draft.check_save().ok, '平移后连通/可动通过',
          g._cubic_draft.check_save().reasons)
    g._cubic_edit_cancel()
    check([min(b.location[i] for b in g.game.blocks) for i in range(3)]
          == [0, 0, -1], '取消恢复原负坐标')


def t10_auto_expand_volume():
    print('== 10. 放块自动扩范围（容積不再是放置墙）==')
    g = new_gui()
    g.set_game_mode('create')
    g._ann_btn_cubic_manual_build()
    g.draw_board()
    d = g._cubic_draft
    out_face = None
    for face in g._cubic_scene['faces']:
        t = d.neighbor(face['loc'], face['axis'], face['sign'])
        if not (0 <= t[0] < d.m and 0 <= t[1] < d.n and 0 <= t[2] < d.d):
            out_face = (face, tuple(t))
            break
    check(out_face is not None, '找到一个朝外、目标格在原容积外的可见面')
    if out_face is None:
        return
    face, target = out_face
    pos = poly_center(face['pts'])
    g._cubic_edit_tool = 'add'
    g._cubic_edit_hover_update(pos)
    check(g._cubic_edit_hover == target, '预览目标就是面外那一格', g._cubic_edit_hover)
    check(g._cubic_edit_hover_valid, '预览判为可放（不再按越界拦截）')
    before = len(g.game.blocks)
    g._cubic_edit_click(pos)
    check(len(g.game.blocks) == before + 1, '点击后真的放上了',
          (before, len(g.game.blocks)))
    check(g._cubic_draft.contains(target), '目标格进入草稿', target)
    check((g._cubic_draft.m, g._cubic_draft.n, g._cubic_draft.d) != (3, 3, 3),
          '草稿范围已自动扩展',
          (g._cubic_draft.m, g._cubic_draft.n, g._cubic_draft.d))
    new_dims = (g._cubic_draft.m, g._cubic_draft.n, g._cubic_draft.d)
    check('超出容积' not in getattr(g, 'macro_notify_msg', ''),
          '不再报「超出容积」', getattr(g, 'macro_notify_msg', ''))
    check(g._cubic_edit_commit(), '扩范围后仍能完成', g.macro_notify_msg)
    check((g.current_m, g.current_n, g.current_depth) == new_dims,
          '完成时 GUI 尺寸旗标跟着新范围走',
          (g.current_m, g.current_n, g.current_depth))
    check((g.game.m, g.game.n, g.game.depth) == new_dims,
          '正式局尺寸也跟着新范围',
          (g.game.m, g.game.n, g.game.depth))
    check(len(g.game.blocks) == 28, '块数 28（3×3×3 + 顶上 1）',
          len(g.game.blocks))


def t11_ghost_anchor():
    print('== 11. 幽灵预览与真盘共用拆分锚点 ==')
    g = new_gui()
    g.set_game_mode('create')
    g._ann_btn_cubic_manual_build()
    g.cubic_gap = 0.4
    g.draw_board()
    scene = g._cubic_scene
    check('anchor' in scene, '场景缓存带 anchor')
    check(scene['anchor'] == cubic_view.layout_anchor(g.game.blocks),
          'anchor 就是真盘包围盒中心', (scene.get('anchor'),
                                    cubic_view.layout_anchor(g.game.blocks)))
    face = scene['faces'][-1]
    ghost = cubic_view.collect_faces(
        [face['loc']], scene['camera'], scale=scene['scale'],
        origin=scene['origin'], gap=scene['gap'], anchor=scene['anchor'])
    same = [f for f in ghost if f['axis'] == face['axis']
            and f['sign'] == face['sign']]
    check(bool(same), '幽灵有同朝向的面')
    if not same:
        return
    real_c = poly_center(face['pts'])
    ghost_c = poly_center(same[0]['pts'])
    check(abs(real_c[0] - ghost_c[0]) < 1.0 and
          abs(real_c[1] - ghost_c[1]) < 1.0,
          '幽灵投影与真块完全重合', (real_c, ghost_c))
    no_anchor = cubic_view.collect_faces(
        [face['loc']], scene['camera'], scale=scene['scale'],
        origin=scene['origin'], gap=scene['gap'])
    same2 = [f for f in no_anchor if f['axis'] == face['axis']
             and f['sign'] == face['sign']]
    if same2:
        drift = (abs(poly_center(same2[0]['pts'])[0] - real_c[0])
                 + abs(poly_center(same2[0]['pts'])[1] - real_c[1]))
        check(drift > 2.0, '旧的无 anchor 路径确实会漂（回归证据）', drift)


def t12_cubic_style_roundtrip():
    print('== 12. 三维样式：命名存盘 / 样式库只列三维 / 再开局 ==')
    g = new_gui()
    g.config_dir = tempfile.mkdtemp(prefix='cubic_style_')
    g.set_game_mode('create')
    g._ann_home_sub = 'restore'
    g._ann_btn_cubic_goal_build()
    # 非满实心目标：抽掉 d=2 整层，剩 18 块 3×3×2（restorable 仍应通过）
    for r in range(3):
        for c in range(3):
            g._cubic_draft.remove((r, c, 2))
    g._cubic_edit_apply()
    check(g._cubic_draft.check_restorable().ok, '18 块非满目标过 restorable',
          g._cubic_draft.check_restorable().reasons)
    g._ann_design_style_name = '三维测试目标'
    check(g._cubic_edit_commit(), '命名后完成并存样式', g.macro_notify_msg)
    from gui import design_styles
    data = design_styles.load_style(g.config_dir, '三维测试目标') or {}
    check(data.get('kind') == 'cubic' and data.get('d') == 3,
          '样式带 kind=cubic 与 d=3', (data.get('kind'), data.get('d')))
    check(len(data.get('cells') or ()) == 18, '样式 18 块',
          len(data.get('cells') or ()))
    check(len(g.game.goal_pattern or ()) == 18, '当前局还原目标 18 块',
          len(g.game.goal_pattern or ()))

    # 同目录塞一个二维样式：三维样式库不应显示它
    design_styles.save_style(g.config_dir, '二维干扰', {
        'version': 2, 'name': '二维干扰', 'kind': 'square',
        'm': 3, 'n': 3, 'step': 1,
        'cells': [[0, 0], [0, 1]], 'groups': [],
    })
    g._ann_home_sub = 'restore'
    g._ann_btn_style_lib()
    g._ann_draw_bar()
    names = [nm for nm, _r in getattr(g, '_ann_design_menu_items', [])]
    check('三维测试目标' in names, '三维样式库列出三维样式', names)
    check('二维干扰' not in names, '三维样式库不列二维样式', names)

    # 从样式库重新开局：盘面 = 18 块样式形状，goal_pattern = 同一格集
    g._ann_design_start_style('三维测试目标')
    check(g.cubic_mode, '仍是三维局')
    check(len(g.game.blocks) == 18, '开局盘面 18 块', len(g.game.blocks))
    check(sorted(tuple(b.location) for b in g.game.blocks)
          == sorted(tuple(p) for p in data['cells']),
          '盘面与样式格集一致',
          (len(g.game.blocks), len(data['cells'])))
    check(len(g.game.goal_pattern or ()) == 18, '开局同时设还原目标',
          len(g.game.goal_pattern or ()))
    check(g._ann_style_goal == '三维测试目标', '当前局记样式名',
          g._ann_style_goal)


def t13_cubic_random_gen():
    print('== 13. 三维随机生成：安全打乱，终态非还原且必有解法 ==')
    g = new_gui()
    g.new_cubic_puzzle(3, 3, 3, 1)
    g.set_game_mode('create')
    g._ann_home_sub = 'shuffle'
    g._ann_draw_bar()
    check('random_gen' in g._ann_btn_rects, '三维打乱页有随机生成按钮',
          sorted(g._ann_btn_rects))
    # 走真实入口：打开 m/n/d/step 对话框 → 生成 4×4×4 等级2
    g._ann_btn_random_gen()
    check(g._ann_sub_dialog == 'gen' and g._ann_gen_cubic,
          '三维随机生成打开四格对话框',
          (g._ann_sub_dialog, g._ann_gen_cubic))
    # 体积护栏：7×7×7 超 216，停在对话框并给错误
    g._ann_gen_fields.update({'m': '7', 'n': '7', 'd': '7', 'step': '1'})
    g._ann_gen_confirm()
    check(g._ann_sub_dialog == 'gen' and '216' in g._ann_gen_error,
          '超体积被拦在对话框内', (g._ann_sub_dialog, g._ann_gen_error))
    g._ann_gen_fields.update({'m': '4', 'n': '4', 'd': '4', 'step': '2'})
    g._ann_gen_confirm()
    check((g.current_m, g.current_n, g.current_depth) == (4, 4, 4),
          '生成新尺寸 4×4×4',
          (g.current_m, g.current_n, g.current_depth))
    check(len(g.game.blocks) == 64, '生成后 64 块', len(g.game.blocks))
    check(not g.game.is_solved(), '生成后不是还原态')
    g.current_step = 2
    g.new_cubic_puzzle(3, 3, 3, 1)
    g._ann_home_sub = 'shuffle'
    steps = g._cubic_random_generate()
    check(steps > 0, '直接调用生成走出有效步', steps)
    check(not g.game.is_solved(), '直接生成后不是还原态')
    check(len(g.game.blocks) == 27, '直接生成后仍 27 块', len(g.game.blocks))

    check(g.game.goal_pattern is None, '默认局没有自定义还原目标',
          g.game.goal_pattern)
    check(len(g.game_history.history) == 1 and g.step_count == 0,
          '生成后历史重置为终态、步数归零',
          (len(g.game_history.history), g.step_count))
    check('随机生成' in getattr(g, 'macro_notify_msg', ''),
          '提示说明是随机生成', getattr(g, 'macro_notify_msg', ''))
    check((g.current_m, g.current_n, g.current_depth) == (3, 3, 3),
          '尺寸仍是 3×3×3',
          (g.current_m, g.current_n, g.current_depth))

    # 还原目标页不应出现随机生成（那是打乱局面的入口）
    g._cubic_edit_cancel()
    g._ann_home_sub = 'restore'
    g._ann_draw_bar()
    check('random_gen' not in g._ann_btn_rects,
          '三维还原页不显示随机生成', sorted(g._ann_btn_rects))


def t14_edit_start_rollback():
    print('== 14. 进编辑器时 set_goal_pattern 抛异常要回滚 ==')
    g = new_gui()
    # 自定义目标 + 偏移，保证 _cubic_edit_start 会真的调 set_goal_pattern
    g.game.apply_pattern([(1, 1, 1)])
    g.game.set_goal_pattern([(1, 1, 1)])
    before = sorted(tuple(int(v) for v in b.location[:3])
                    for b in g.game.blocks)

    def boom(_cells):
        raise RuntimeError('boom')

    orig = g.game.set_goal_pattern
    g.game.set_goal_pattern = boom
    try:
        ok = g._cubic_edit_start('goal')
    finally:
        g.game.set_goal_pattern = orig
    check(ok is False, '异常时 _cubic_edit_start 返回 False', ok)
    check(not getattr(g, '_cubic_edit_active', False),
          '不留在半截编辑态', getattr(g, '_cubic_edit_active', None))
    after = sorted(tuple(int(v) for v in b.location[:3])
                   for b in g.game.blocks)
    check(after == before, '盘面已回滚到进入前', (before, after))


def main():
    print('=' * 62)
    print('三维创造模式：第 1–5 步回归')
    print('=' * 62)
    t1_mode_entry()
    t2_home_buttons()
    t3_edit_and_click()
    t4_cancel_and_gate()
    t5_goal_purpose()
    t6_event_dispatch()
    t7_step_carry()
    t8_shifted_box()
    t9_negative_coords()
    t10_auto_expand_volume()
    t11_ghost_anchor()
    t12_cubic_style_roundtrip()
    t13_cubic_random_gen()
    t14_edit_start_rollback()
    total = PASSED[0] + len(FAILED)
    print(f'结果：{"全部通过" if not FAILED else "有失败"}'
          f'（{PASSED[0]} 项通过，{len(FAILED)} 项失败）／共 {total} 项')
    if FAILED:
        for f in FAILED:
            print('  -', f)
    sys.exit(1 if FAILED else 0)


if __name__ == '__main__':
    main()
