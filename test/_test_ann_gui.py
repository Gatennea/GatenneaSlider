# -*- coding: utf-8 -*-
r"""
标注模式 headless 集成测试（dummy video，不开窗口）

流程：
    1. 随机生成 5×5 step2、2 个空位的起点状态
    2. 进入标注模式 → 「当前状态开始」→ 选目标空位/凸起 → 开始跟踪执行
    3. 用 gather_solver 找出的（可重放）序列，在 GUI 上逐步真实执行
       （中途切换阶段 B，验证 phase 标签）
    4. 断言：步骤录制数量、跟踪推进无异常、空位净减、结束可保存 JSONL
    5. 输出写到临时目录，不污染 save/标注样本

运行：
    D:\python\python.exe 測試\_test_ann_gui.py
"""

import os
import sys
import json
import copy
import tempfile
import random
import shutil

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

from game import SliderMatrix, Block
from solver.ml import ann_gen
from solver.ml.gather_solver import gather_solve


def _set_board(gui, coords):
    """把 gui.game 替换为给定坐标集（保留 gui 尺寸/等级），并重置历史。"""
    gui.game.blocks = [Block(list(p)) for p in sorted(coords)]
    gui.game.update_matrix()
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.center_map()
    gui.selected_gap = None
    gui.selected_block = None


def _find_block(gui, rc):
    for b in gui.game.blocks:
        if b.location == list(rc):
            return b
    return None


def _apply_gui_action(gui, action, rep):
    """用 GUI 原生路径执行一步（opt 选中 + 方向移动，关动画即即时提交）。

    每次调用都模拟「重新点缝隙 + 点方块」的选中变化（结束上一个选中会话），
    与真实点击一致：否则同缝隙的连续移动会被合并成一个快照。
    """
    gap_type, line, _side, move_dir = action
    block = _find_block(gui, rep)
    if block is None:
        return False
    gui._bump_move_session()
    gui.selected_gap = (gap_type, line)
    gui.game.opt(gap_type, line, block)
    if not [b for b in gui.game.blocks if b.be_opted]:
        return False
    return bool(gui.move_selected_blocks(move_dir))


def main():
    gui = None
    from GUI import SliderGUI
    gui = SliderGUI(m=5, n=5, step=2)
    gui.animation_enabled = False
    gui._readonly = False          # 屏蔽工作区 temp_history 残留的只读标记
    gui.save_readonly_flag = False
    ok_all = True

    # ---- 0. 隐藏入口四键判定（同时按住 B / Z / M / S）----
    import pygame

    def _kd(k):
        return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0)

    for k in (pygame.K_b, pygame.K_z, pygame.K_m):
        assert not gui.handle_annotation_event(_kd(k))
    assert not gui.annotation_mode, '只按三个键不应开启标注模式'
    assert gui.handle_annotation_event(_kd(pygame.K_s))
    assert gui.annotation_mode, 'B/Z/M/S 隐藏入口未开启标注模式'
    gui._ann_toggle_mode()          # 关掉，后续走正常流程
    assert not gui.annotation_mode
    print('隐藏入口 B/Z/M/S: OK')

    # ---- 1. 生成起点状态（5×5 step2, 2 空位, 固定种子）----
    seed = 3
    coords, holes = ann_gen.generate_random_void(5, 5, 2, 2,
                                                 rng=random.Random(seed))
    assert gui.new_puzzle(5, 5, 2)
    _set_board(gui, coords)
    gui.ensure_blocks_visible()

    # ---- 2. 进入标注模式 & 当前状态开始 ----
    gui._ann_toggle_mode()
    assert gui.annotation_mode, '标注模式未开启'
    gui._ann_btn_from_current()
    assert gui._ann_view == 'target', f'view={gui._ann_view}'

    # 程序化选中目标（等价于逐格点选）：取第一个洞（单格即可）+ 第一个凸起
    from gui.annotation import holes_and_protrusions
    holes_l, protrusions, _region = holes_and_protrusions(
        gui._game_coords(), 5, 5, 2)
    assert holes_l, '起点没有窗内空位（洞）'
    assert protrusions, '起点没有窗外凸起'
    gui._ann_void0 = frozenset(holes_l[0]['cells'])
    gui._ann_track_void = gui._ann_void0
    gui._ann_anchor0 = frozenset({tuple(protrusions[0])})
    gui._ann_track_anchor = gui._ann_anchor0
    gui._ann_pick = None
    gui._ann_btn_start_exec()
    assert gui._ann_recording, '未进入录制'
    base_void = gui._ann_base_metrics['void_block_count']
    print(f'起点空位: {base_void}  洞格: {len(holes_l[0]["cells"])}')

    # ---- 3. 用 gather 求解可重放动作序列 ----
    g0 = copy.deepcopy(gui.game)
    r = gather_solve(g0, step=2, max_steps=800, patience=200,
                     max_wait_time=60, target_gather_score=1.0,
                     aggressiveness=0.0)
    acts, reps = r['actions'], r['rep_cells']
    assert acts, f'求解空：{r["reason"]}'
    print(f'gather: {len(acts)}步 reason={r["reason"]} '
          f'end_overlap={r["end"]["overlap"]}')

    executed = 0
    for i, (act, rep) in enumerate(zip(acts, reps)):
        if i == 3:
            gui._ann_btn_phase_B()          # 中途切到 B 阶段
        if i == 6:
            gui._ann_btn_phase_AP()         # 再切 A′
        if not _apply_gui_action(gui, act, rep):
            print(f'第{i}步执行失败: {act} rep={rep}')
            ok_all = False
            break
        executed += 1
        gui._ann_poll()                     # 每次提交后推进录制
    print(f'真实执行: {executed}步  history_index={gui.game_history.history_index}')

    # 断言录制条数 = 已执行步数
    n_rec = sum(1 for k in gui._ann_steps
                if k > gui._ann_base_idx and k <= gui.game_history.history_index)
    print(f'录制条数: {n_rec}  阶段分布: '
          f'{ {v["phase"] for v in gui._ann_steps.values()} }')
    assert n_rec == executed, f'录制条数 {n_rec} != 执行 {executed}'
    assert {v['phase'] for v in gui._ann_steps.values()} <= {'A', 'B', "A'"}

    # 空位净减断言
    gui._ann_refresh_metrics()
    end_void = gui._ann_cur_metrics['void_block_count']
    print(f'空位: {base_void} → {end_void}')
    assert end_void < base_void, f'空位未减少: {base_void}→{end_void}'

    # 录制中途「重选」后，写盘仍须用录制起点快照而非会话级选择
    expect_start_void = gui._ann_start_void
    expect_start_anchor = gui._ann_start_anchor
    gui._ann_void0 = frozenset({(-1, -1)})   # 模拟重选（只改会话级）
    gui._ann_anchor0 = frozenset({(-2, -2)})

    # ---- 4. 结束并保存到临时目录 ----
    tmp = tempfile.mkdtemp(prefix='ann_test_')
    try:
        gui.save_dir = tmp
        gui._ann_btn_finish()
        out = os.path.join(tmp, '标注样本', 'annotations.jsonl')
        assert os.path.exists(out), 'annotations.jsonl 未生成'
        with open(out, 'r', encoding='utf-8') as f:
            lines = [l for l in f if l.strip()]
        ep = json.loads(lines[0])
        assert ep['void_delta'] < 0, 'void_delta 应为负'
        assert len(ep['steps']) == executed
        st0 = ep['steps'][0]
        assert st0['move_info']['side'] in ('above', 'below', 'left', 'right')
        assert 'matrix' in ep['start'] and 'target_void' in ep['start']
        assert ep['start']['target_void'] == sorted(
            [list(c) for c in expect_start_void])
        assert ep['start']['target_anchor'] == sorted(
            [list(c) for c in expect_start_anchor])
        print(f'已保存 episode: id={ep["episode_id"]} '
              f'steps={len(ep["steps"])} delta={ep["void_delta"]}')
        assert ep['source_type'] == 'current'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 5. 撤销同步冒烟：录制中撤销一步，条数减少 ----
    # （回到上面保存后的状态：再做一次简单录制）
    print('撤销同步冒烟：')
    coords2, _h2 = ann_gen.generate_random_void(5, 5, 2, 2,
                                                rng=random.Random(3))
    _set_board(gui, coords2)
    gui._ann_start_target('current', '撤销测试')
    holes_l2, protrusions2, _ = holes_and_protrusions(gui._game_coords(), 5, 5, 2)
    gui._ann_void0 = frozenset(holes_l2[0]['cells'])
    gui._ann_anchor0 = frozenset({tuple(protrusions2[0])})
    gui._ann_track_void = gui._ann_void0
    gui._ann_track_anchor = gui._ann_anchor0
    gui._ann_pick = None
    gui._ann_btn_start_exec()
    g0 = copy.deepcopy(gui.game)
    r2 = gather_solve(g0, step=2, max_steps=300, patience=100,
                      max_wait_time=30, target_gather_score=1.0,
                      aggressiveness=0.0)
    assert r2['actions'], f'求解空2：{r2["reason"]}'
    # 执行前 5 步
    for act, rep in zip(r2['actions'][:5], r2['rep_cells'][:5]):
        assert _apply_gui_action(gui, act, rep)
        gui._ann_poll()
    hi_before = gui.game_history.history_index
    assert hi_before - gui._ann_base_idx == 5
    # 撤销 2 步（录制起点之内允许）
    gui.undo(); gui._ann_poll()
    gui.undo(); gui._ann_poll()
    n_after_undo = sum(1 for k in gui._ann_steps
                       if gui._ann_base_idx < k <= gui.game_history.history_index)
    print(f'  撤销后历史步 {gui.game_history.history_index - gui._ann_base_idx}'
          f'  录制条数 {n_after_undo}')
    assert n_after_undo == 3, f'撤销未同步录制：{n_after_undo} != 3'
    # 尝试撤到起点以下 → 应被阻止
    gui.undo(); gui.undo(); gui.undo(); gui._ann_poll()
    assert gui.game_history.history_index >= gui._ann_base_idx, '撤销越过录制起点！'
    print('  撤销未越过录制起点: OK')

    # ---- 6. 手动构造 + 输入框持久化 ----
    print('手动构造 / 输入框持久化：')
    tmpc = tempfile.mkdtemp(prefix='ann_cfg_')
    old_cfg = gui.config_dir
    try:
        gui.config_dir = tmpc
        gui._ann_saved_inputs = None          # 强制按新目录重读
        # 打开手动构造（默认参数=当前 5×5 step2，pad=2，
        # 画布初始=当前棋盘状态而非还原态）
        gui._ann_btn_manual_build()
        assert gui._ann_sub_dialog == 'build'
        assert gui._ann_build_fields['m'] == '5'
        cur = {tuple(b.location) for b in gui.game.blocks}
        assert gui._ann_build_coords == cur, \
            '进入构造应以当前棋盘状态为基础'
        gui._ann_draw_bar()                  # 渲染冒烟（工具条内嵌参数输入，不抛异常即可）

        # 非法棋形（颗数不符）→ 拒绝应用
        gui._ann_build_coords = set(gui._ann_solved_coords(4, 4))
        gui._ann_build_apply()
        assert gui._ann_sub_dialog == 'build', '非法棋形不应被应用'
        assert gui._ann_build_error, '应提示非法棋形原因'

        # 合法：5×5 step2，挖 (1,1)、贴同余凸起 (-1,1)
        coords = set(gui._ann_solved_coords(5, 5))
        coords.discard((1, 1))
        coords.add((-1, 1))
        gui._ann_build_coords = coords
        gui._ann_build_apply()
        assert gui._ann_sub_dialog is None
        assert gui._ann_view == 'target'
        assert gui._ann_source_type == 'build'
        bs = gui._game_coords()
        assert (1, 1) not in bs and (-1, 1) in bs, '手动构造未落到棋盘'
        # 默认可立即开始（进入 target，可直接标注）
        gui._ann_abort('done')

        # gen 输入框持久化：hole 改成 3 → 关闭 → 重开仍为 3
        gui._ann_btn_random_gen()
        gui._ann_gen_fields['hole'] = '3'
        gui._ann_close_sub_dialog()
        gui._ann_saved_inputs = None
        gui._ann_btn_random_gen()
        assert gui._ann_gen_fields['hole'] == '3', 'gen hole 未持久化'
        gui._ann_close_sub_dialog()
        print('  手动构造应用 + 输入框持久化: OK')
    finally:
        gui.config_dir = old_cfg
        shutil.rmtree(tmpc, ignore_errors=True)

    # ---- 7. 创造模式：模式开关三态 + 造题即当前谜题 ----
    print('创造模式：')
    gui._ann_abort('清理')
    gui.annotation_mode = False
    gui.set_game_mode('practice')
    seq = []
    for _ in range(3):
        gui.toggle_game_mode()
        seq.append(gui.game_mode)
    assert seq == ['timed', 'create', 'practice'], f'模式循环异常：{seq}'
    gui.set_game_mode('create')
    assert gui.create_mode and gui._ann_view == 'home', '进入创造模式应停在创造首页'
    # 创造模式全程禁止滑动（与练习模式功能解耦）
    gui.move_selected_blocks('a')
    assert '创造模式' in gui.macro_notify_msg, '创造模式应禁止滑动并给出提示'

    # 随机生成 → 直接成为当前谜题（留在创造首页）
    gui._ann_btn_random_gen()
    assert gui._ann_sub_dialog == 'gen'
    gui._ann_gen_fields = {'m': '4', 'n': '4', 'step': '2',
                           'hole': '1', 'dent': '1'}
    gui._ann_gen_confirm()
    assert gui._ann_view == 'home', '创造模式生成后应留在创造首页'
    assert gui.create_mode and (gui.current_m, gui.current_n) == (4, 4)
    assert len(gui.game_history.history) == 1, '新谜题历史应为 1 条'
    assert not gui.game.is_solved(), '生成的谜题不应是还原态'

    # 手动构造 → 初始参数跟随当前谜题（刚生成的 4×4 step2）
    gui._ann_btn_manual_build()
    assert gui._ann_view == 'build'
    assert (gui._ann_build_fields['m'], gui._ann_build_fields['n'],
            gui._ann_build_fields['step']) == ('4', '4', '2'), \
        '构造初始参数应跟随当前谜题'
    coords = set(gui._ann_solved_coords(5, 5))
    coords.discard((1, 1))
    coords.add((-1, 1))
    gui._ann_build_fields.update({'m': '5', 'n': '5', 'step': '2'})
    gui._ann_build_coords = coords
    gui._ann_build_apply()
    assert gui._ann_view == 'home', '创造模式构造后应留在创造首页'
    bs = gui._game_coords()
    assert (1, 1) not in bs and (-1, 1) in bs, '构造结果未落到棋盘'

    # 可构造范围 = 棋形边界盒各扩一圈（不再并上 m×n 区域，避免撑成大片无关矩形）
    gui._ann_build_coords = {(0, 0)}
    assert gui._ann_build_grid(5, 5) == (-1, 1, -1, 1), \
        f'边界盒外扩异常：{gui._ann_build_grid(5, 5)}'
    gui._ann_build_coords = {(0, 0), (7, 8)}
    assert gui._ann_build_grid(5, 5) == (-1, 8, -1, 9), \
        f'边界盒外扩异常：{gui._ann_build_grid(5, 5)}'
    # 离原点较远时不应被 m×n 区域撑大
    gui._ann_build_coords = {(6, 6), (7, 7)}
    assert gui._ann_build_grid(5, 5) == (5, 8, 5, 8), \
        f'远离原点时外扩异常：{gui._ann_build_grid(5, 5)}'
    # 空画布回退到 m×n 各扩一圈
    gui._ann_build_coords = set()
    assert gui._ann_build_grid(5, 5) == (-1, 5, -1, 5), \
        f'空画布外扩异常：{gui._ann_build_grid(5, 5)}'

    # 构造视图禁止滑动
    gui._ann_btn_manual_build()
    assert gui.move_selected_blocks('a') is False, '构造视图不应允许滑动'
    gui._ann_build_cancel()

    # 退出创造 → 练习模式
    gui._ann_exit_create()
    assert gui.game_mode == 'practice' and not gui.create_mode
    print('  三态循环 / 生成 / 构造 / 退出: OK')

    print('\n全部通过' if ok_all else '\n存在失败')
    return 0 if ok_all else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
