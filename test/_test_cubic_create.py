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

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

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
    check('manual_build' not in names and 'random_gen' not in names,
          '不出现二维手动构造/随机生成', names)
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
    g.set_game_mode('create')
    g._ann_home_sub = 'restore'
    g._ann_btn_cubic_goal_build()
    check(g._cubic_edit_purpose == 'goal', '会话目标是还原态')
    check(g._cubic_edit_commit(), '满实心还原目标能保存',
          g.macro_notify_msg)
    check(g.game.goal_pattern is not None, 'goal_pattern 已设')
    check(len(g.game.goal_pattern) == 27, '目标 27 块',
          len(g.game.goal_pattern or ()))


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


def main():
    print('=' * 62)
    print('三维创造模式：第 1–3 步回归')
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
    total = PASSED[0] + len(FAILED)
    print(f'结果：{"全部通过" if not FAILED else "有失败"}'
          f'（{PASSED[0]} 项通过，{len(FAILED)} 项失败）／共 {total} 项')
    if FAILED:
        for f in FAILED:
            print('  -', f)
    sys.exit(1 if FAILED else 0)


if __name__ == '__main__':
    main()
