# -*- coding: utf-8 -*-
r"""
新手教程（闯关模式）headless 冒烟测试（dummy video，不开窗口）

验证点：
    1. 首次启动弹窗：started/skipped 均未设置 → tut_show_prompt=True
    2. 教程入口：菜单栏“教程”→ 关卡选择列表（tut_selecting_levels、tut_level=0、
       标题“选择关卡”）；关卡/小关由 beginner_archive 自动识别（1-5，无存檔的 6 不出现），
       列表以每个小关为一行
    3. 关卡列表点第 1 关 → 载入完整 4×4 演示盘（底部标题 2~4*4）、tut_step=1
    4. 教学状态机：点缝隙(1→2) → 点滑块(2→3) → 真实移动(3→4) → 撤销(4→5) → 重做(5→6 合并挑战盘 1~3*3)
    5. 合并步骤（步骤6）：切回 3×3 挑战盘 1~3*3，面板按钮为 重置/查看解法/跳过
    6. 过关判定：is_solved → _tut_complete → tut_step=7、completed=[1]
    7. 进度持久化：save_config 写入 tutorial 键、load_last_state 还原；
       完成后首次启动不再弹窗
    8. 跳过教程：_tut_skip → tutorial_active=False、skipped=True
    9. 第 2/3/4 关：关卡列表进 2.1 打乱态、查看解法＝撤回初始＋存檔连续重做回放
       （动画临时调慢/结束还原）；回放中锁定棋盘操作，播完回到第 0 步并清空历史，
       强制玩家手动还原才算过关（小关推进靠玩家手动还原）
   10. 面板/弹窗按钮生成（draw_tutorial_panel / draw_tutorial_prompt / 关卡列表）

运行：
    D:\python\python.exe 測試\_test_tutorial.py
"""

import json
import os
import shutil
import sys
import tempfile
import time

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

import pygame

ok_all = True


def _check(name, cond, detail=''):
    global ok_all
    ok_all = ok_all and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")


def _find_valid_move(gui):
    """在教程第 3 步找一组可真实移动的选中配置：(gap_type, line, block, direction)"""
    gaps = []
    for line in range(-8, 9):
        if gui.game.is_valid_h_line(line):
            gaps.append(('h', line))
        if gui.game.is_valid_v_line(line):
            gaps.append(('v', line))
    for gt, line in gaps:
        for block in gui.game.blocks:
            gui.game.opt(gt, line, block)
            for d in ('w', 's', 'a', 'd'):
                if gui.game.try_move(d, gui.current_step):
                    return gt, line, block, d
    return None


def _manual_solve_current_sublevel(gui):
    """按存檔动作序列，用普通移动（非解法回放）手动还原当前小关。

    模拟玩家自己照解法动手：每步先选缝隙与目标块，再真实移动。
    还原成功时 _maybe_show_solved_popup → _tut_on_state_commit 会推进教学进度
    （换下一小关，或最后一小关时 tut_step=7）；推进即视为手动还原成功。

    存檔快照可能是「合并快照」（一次选中连移多步只存末态），故用
    expand_snapshot_moves 逐步展开，才能拿到每步动作前的块位置。
    """
    from history import expand_snapshot_moves
    import gui.tutorial as tut_mod
    start_sub = gui.tut_sublevel
    path = tut_mod._sublevel_archive_path(start_sub)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    snaps = data['history']['snapshots']
    for i in range(1, len(snaps)):
        for _pre, _post, mi in expand_snapshot_moves(snaps[i - 1], snaps[i]):
            if not mi:
                continue
            gt, line = mi['gap_type'], mi['gap_line']
            rr, cc = mi['moved_positions'][0]
            blk = gui._find_block_by_cell(rr, cc)
            if blk is None:
                return False
            gui.selected_gap = (gt, line)
            gui.game.opt(gt, line, blk)
            gui.selected_block = blk
            if not gui.move_selected_blocks(mi['direction']):
                return False
            if gui.tut_sublevel != start_sub or gui.tut_step == 7:
                return True   # 已还原并推进教学进度
    return False


def main():
    from GUI import SliderGUI
    gui = SliderGUI(m=5, n=5, step=2)
    gui.animation_enabled = False
    gui._readonly = False          # 屏蔽 temp_history 可能残留的只读标记
    gui.save_readonly_flag = False

    # 重定向配置（不污染工作区真实 config）
    tmpdir = tempfile.mkdtemp(prefix='slider_tutorial_')
    gui.config_dir = os.path.join(tmpdir, 'config')
    gui.config_path = os.path.join(gui.config_dir, 'config.json')
    gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')

    # ---- 1. 首次启动弹窗 ----
    _check('谜题菜单不再含教程入口', ('__tutorial__',) not in gui.puzzle_presets,
           str(gui.puzzle_presets[:2]))
    _check('教程入口位于帮助右侧、官网为最右项',
           gui.menu_items[-1] == '官网'
           and gui.menu_items[-2] == '教程'
           and gui.menu_items[-3] == '帮助', str(gui.menu_items))
    gui.tut_progress = {'started': False, 'skipped': False, 'completed': [], 'current': None}
    gui.tut_show_prompt = False
    gui._tut_check_first_launch()
    _check('首次启动弹窗出现', gui.tut_show_prompt is True, f'prompt={gui.tut_show_prompt}')

    # ---- 2. 教程入口：点击菜单栏“教程”（帮助右侧）→ 关卡选择列表 ----
    gui.draw_menu_bar()
    tut_idx = gui.menu_items.index('教程')
    _check('教程菜单位于帮助右侧', len(gui.menu_item_rects) == len(gui.menu_items)
           and gui.menu_item_rects[tut_idx].x > gui.menu_item_rects[tut_idx - 1].x, '')
    gui.tut_show_prompt = False   # 关闭首次弹窗，模拟玩家手动进入
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                         {'button': 1, 'pos': gui.menu_item_rects[tut_idx].center}))
    gui.handle_events()
    _check('菜单栏点击进入教程', gui.tutorial_active is True, '')
    _check('进入关卡选择列表', gui.tut_selecting_levels is True,
           f'selecting={gui.tut_selecting_levels}')
    _check('列表视图 tut_level=0', gui.tut_level == 0, f'level={gui.tut_level}')
    _check('进度 started=True', gui.tut_progress.get('started') is True, '')
    _check('未载入任何关卡', gui.current_file_path is None, str(gui.current_file_path))
    _check('标题为教程·选择关卡', '选择关卡' in gui._window_title, gui._window_title)

    # 关卡选择列表：以「每个小关」为一行 + 回到练习模式
    gui.draw_tutorial_panel()
    import gui.tutorial as tut_mod
    lv_ids = [lv['id'] for lv in tut_mod.TUTORIAL_LEVELS]
    subs_of = {lv['id']: lv['sublevels'] for lv in tut_mod.TUTORIAL_LEVELS}
    _check('自动识别关卡 1-5（无存檔的 6 不出现）', lv_ids == [1, 2, 3, 4, 5], str(lv_ids))
    _check('第3关自动识别 3.1-3.4（3.5 无存檔被排除）',
           subs_of[3] == ['3.1', '3.2', '3.3', '3.4'], str(subs_of[3]))
    visible_subs = [b.get('sublevel') for b in gui.tut_level_btn_rects
                    if b.get('action') == 'load']
    _check('列表按小关分行', bool(visible_subs) and all(visible_subs), str(visible_subs))
    _check('列表含回到练习模式', any(b.get('action') == 'exit' for b in gui.tut_level_btn_rects), '')

    # 点第 1 关 → 载入完整 4×4 演示盘
    btn1 = next(b for b in gui.tut_level_btn_rects if b.get('level') == 1)
    _check('点第1关被消费', gui._tut_handle_panel_click(*btn1['rect'].center) is True, '')
    _check('载入完整 4×4 演示盘(2~4*4)', (gui.current_m, gui.current_n, gui.current_step) == (4, 4, 2),
           f'({gui.current_m},{gui.current_n},{gui.current_step})')
    _check('退出关卡选择列表', gui.tut_selecting_levels is False, '')
    _check('步骤=1(选中缝隙)', gui.tut_step == 1, f'step={gui.tut_step}')
    _check('当前关卡=1', gui.tut_progress.get('current') == 1, '')
    _check('未绑定存档路径', gui.current_file_path is None, str(gui.current_file_path))
    _check('标题为教程·第 1 关', '第 1 关' in gui._window_title, gui._window_title)

    # 面板按钮：步骤1应含“查看解法/跳过教程”
    gui.draw_tutorial_panel()
    actions = [b['action'] for b in gui.tut_btn_rects]
    _check('步骤1面板按钮', 'solution' in actions and 'skip' in actions, str(actions))

    # ---- 3. 教学状态机 ----
    gui._tut_on_gap_clicked()
    _check('点缝隙 1→2', gui.tut_step == 2, f'step={gui.tut_step}')

    gui._tut_on_block_clicked()
    _check('点滑块 2→3', gui.tut_step == 3, f'step={gui.tut_step}')

    # 宏执行（解法播放）期间：操作教学不得被推进
    gui.macro_executing = True
    gui._tut_on_state_commit()
    _check('宏执行不推进步骤3', gui.tut_step == 3, f'step={gui.tut_step}')
    gui.macro_executing = False

    # 真实移动一次（走 move_selected_blocks → _maybe_show_solved_popup → 状态机推进）
    mv = _find_valid_move(gui)
    _check('找到可移动配置', mv is not None, '')
    if mv:
        gt, line, block, d = mv
        gui.selected_gap = (gt, line)
        gui.game.opt(gt, line, block)
        ok = gui.move_selected_blocks(d)
        _check('移动真正执行', ok is True, '')
    _check('移动一次 3→4', gui.tut_step == 4, f'step={gui.tut_step}')

    gui.undo()
    _check('撤销一次 4→5', gui.tut_step == 5, f'step={gui.tut_step}')

    gui.redo()
    _check('重做一次 5→6(合并挑战)', gui.tut_step == 6, f'step={gui.tut_step}')
    _check('合并挑战盘切回 3×3(1~3*3)', (gui.current_m, gui.current_n, gui.current_step) == (3, 3, 1),
           f'({gui.current_m},{gui.current_n},{gui.current_step})')
    _check('合并挑战题回到初始打乱态', gui.step_count == 0, f'step_count={gui.step_count}')

    # ---- 3.5 自动换行 + 滚动条（步骤6合并挑战长文案） ----
    gui.tut_panel_scroll = 10 ** 9           # 预设超大滚动值，验证绘制时 clamp
    gui.draw_tutorial_panel()
    _check('步骤6正文自动换行后超出一屏', gui.tut_panel_total_h > gui.tut_panel_content_h,
           f'total={gui.tut_panel_total_h} content={gui.tut_panel_content_h}')
    _check('内容超出时出现滚动条', gui.tut_panel_scrollbar_rect is not None
           and gui.tut_panel_scrollbar_knob_rect is not None, '')
    scr_max = max(0, gui.tut_panel_total_h - gui.tut_panel_content_h)
    _check('滚动 clamp 到上界', gui.tut_panel_scroll == scr_max, f'scroll={gui.tut_panel_scroll}')

    # 滚轮：光标在面板内上滚减 scroll / 在面板外不消费
    gui.tut_panel_scroll = scr_max
    ev_in = pygame.event.Event(pygame.MOUSEWHEEL, {'y': 3, 'x': 0, 'pos': gui.tut_panel_rect.center})
    _check('光标在面板内滚轮被消费', gui._tut_handle_panel_scroll(ev_in) is True, '')
    _check('滚轮上滚减小 scroll', gui.tut_panel_scroll == max(0, scr_max - 90),
           f'scroll={gui.tut_panel_scroll}')
    ev_out = pygame.event.Event(pygame.MOUSEWHEEL, {'y': 3, 'x': 0, 'pos': (5, 5)})
    _check('画面板外滚轮不消费', gui._tut_handle_panel_scroll(ev_out) is False, '')

    # 滚动条：拖拽滑块 / 点空白跳转
    gui._tut_handle_panel_scroll(pygame.event.Event(pygame.MOUSEBUTTONUP, {'button': 1, 'pos': (0, 0)}))
    knob = gui.tut_panel_scrollbar_knob_rect
    ev_down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button': 1, 'pos': knob.center})
    _check('点中滑块开始拖拽', gui._tut_handle_panel_scroll(ev_down) is True
           and gui.tut_panel_scrollbar_dragging is True, '')
    gui._tut_handle_panel_scroll(pygame.event.Event(pygame.MOUSEMOTION,
                                                    {'pos': (0, 0), 'rel': (0, 0), 'buttons': (1, 0, 0)}))
    _check('拖拽到顶部 scroll=0', gui.tut_panel_scroll == 0, f'scroll={gui.tut_panel_scroll}')
    gui._tut_handle_panel_scroll(pygame.event.Event(pygame.MOUSEBUTTONUP, {'button': 1, 'pos': (0, 0)}))
    _check('松开停止拖拽', gui.tut_panel_scrollbar_dragging is False, '')

    # 回归：非滚动条拖拽的 MOUSEBUTTONUP 不得被吞（否则 is_dragging 卡死 → 地图跟随鼠标）
    up_free = pygame.event.Event(pygame.MOUSEBUTTONUP, {'button': 1, 'pos': (0, 0)})
    _check('非拖拽时松开不消费', gui._tut_handle_panel_scroll(up_free) is False, '')
    gui.tut_panel_scrollbar_dragging = True
    _check('拖拽中松开被消费', gui._tut_handle_panel_scroll(up_free) is True
           and gui.tut_panel_scrollbar_dragging is False, '')

    gui.draw_tutorial_panel()          # 按 scroll=0 重绘，刷新滑块矩形
    sb = gui.tut_panel_scrollbar_rect
    ev_jump = pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                 {'button': 1, 'pos': (sb.centerx, sb.bottom - 5)})
    eaten_j = gui._tut_handle_panel_scroll(ev_jump)
    _check('点滚动条空白跳转到底部', eaten_j is True and gui.tut_panel_scroll >= scr_max - 10,
           f'scroll={gui.tut_panel_scroll}')

    # 短步骤（步骤4）无需滚动条；换步骤滚动归零
    gui.tut_panel_scroll = scr_max
    gui._tut_set_step(4)
    gui.draw_tutorial_panel()
    _check('短步骤无滚动条', gui.tut_panel_scrollbar_rect is None, '')
    _check('换步骤滚动归零', gui.tut_panel_scroll == 0, f'scroll={gui.tut_panel_scroll}')
    gui._tut_set_step(6)

    # ---- 4. 合并步骤（步骤6=规则讲解+过关挑战）盘面与按钮 ----
    _check('合并步骤6 为 3×3 挑战盘(1~3*3)',
           (gui.current_m, gui.current_n, gui.current_step) == (3, 3, 1),
           f'({gui.current_m},{gui.current_n},{gui.current_step})')
    _check('合并步骤6 回到初始打乱态', gui.step_count == 0, f'step_count={gui.step_count}')
    gui.draw_tutorial_panel()
    acts6 = [b['action'] for b in gui.tut_btn_rects]
    _check('合并步骤6 面板按钮重置/解法/跳过',
           'reset' in acts6 and 'solution' in acts6 and 'skip' in acts6, str(acts6))

    # ---- 5. 过关判定 ----
    gui.is_solved = lambda: True
    gui._maybe_show_solved_popup()
    _check('过关 → 完成 7', gui.tut_step == 7, f'step={gui.tut_step}')
    _check('关卡1记入完成', 1 in gui._tut_completed_levels(), str(gui._tut_completed_levels()))
    gui.is_solved = SliderGUI.is_solved  # 还原

    # 查看解法播放中：即便已还原也不判定过关、不弹复原窗
    # （播完会撤回初始态，强制玩家手动还原才算过关）
    gui.tut_step = 6
    gui.tut_solution_replaying = True
    gui.macro_executing = True
    gui._solved_popup_active = False
    gui.is_solved = lambda: True
    gui._maybe_show_solved_popup()
    _check('解法播放中不判过关', gui.tut_step == 6, f'step={gui.tut_step}')
    _check('解法播放中不弹复原窗', gui._solved_popup_active is False, '')
    gui.macro_executing = False
    gui.tut_solution_replaying = False
    del gui.is_solved  # 还原（删除实例遮蔽，回到类方法）

    # ---- 6. 进度持久化 ----
    gui._tut_save_progress()
    with open(gui.config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    _check('save_config 写入 tutorial', cfg.get('tutorial', {}).get('completed') == [1],
           str(cfg.get('tutorial')))
    gui.tut_progress = {'started': False, 'skipped': False, 'completed': [], 'current': None}
    gui.load_last_state()
    _check('load_last_state 还原进度', gui.tut_progress.get('completed') == [1],
           str(gui.tut_progress))
    gui.tut_show_prompt = False
    gui._tut_check_first_launch()
    _check('已开始后不再弹窗', gui.tut_show_prompt is False,
           f'prompt={gui.tut_show_prompt}')

    # ---- 7. 跳过教程 ----
    gui._tut_skip()
    _check('跳过教程', gui.tutorial_active is False and gui.tut_progress.get('skipped') is True, '')

    # 菜单入口名称三态（随时间：新手教程 → 继续教程 → 回顾教程）
    gui.tutorial_active = False
    gui.tut_progress = {'started': False, 'skipped': False, 'completed': [], 'current': None}
    _check('菜单名=新手教程', gui._tut_menu_name() == '新手教程', gui._tut_menu_name())
    gui.tut_progress['started'] = True
    _check('菜单名=继续教程', gui._tut_menu_name() == '继续教程', gui._tut_menu_name())
    gui.tut_progress['completed'] = [1]
    _check('菜单名=回顾教程', gui._tut_menu_name() == '回顾教程', gui._tut_menu_name())

    # ---- 8. 第 2/3/4 关：关卡列表选择 + 小关顺序 + 存檔重做回放 + 动画调慢 ----
    def _click_level(level_id):
        """从关卡列表点击指定关卡（列表可滚动，必要时下滚查找）"""
        gui._tut_show_level_select()
        for _ in range(40):
            gui.draw_tutorial_panel()
            btn = next((b for b in gui.tut_level_btn_rects
                        if b.get('level') == level_id), None)
            if btn:
                return gui._tut_handle_panel_click(*btn['rect'].center)
            gui.tut_panel_scroll += 40
        return False

    # 8.1 载入第 2 关：自动选第一个未完成小关 2.1
    gui.tut_progress['subcompleted'] = {}
    _check('点第2关被消费', _click_level(2) is True, '')
    _check('第2关可玩', gui.tutorial_active is True and gui.tut_level == 2,
           f'level={gui.tut_level}')
    _check('载入 2.1 小关', gui.tut_sublevel == '2.1', str(gui.tut_sublevel))
    _check('小关步骤=1(还原)', gui.tut_step == 1, f'step={gui.tut_step}')
    _check('小关回到打乱态', gui.step_count == 0, f'step_count={gui.step_count}')
    _check('2.1 存檔含完整重做链', len(gui.game_history.history) == 4,
           f'snapshots={len(gui.game_history.history)}')
    _check('标题为教程·第 2 关', '第 2 关' in gui._window_title, gui._window_title)

    # 8.2 查看解法：临时调慢动画 + 撤回初始 + 连续重做回放
    #     播完 = 回到第 0 步 + 清掉解法历史 + 解锁，强制玩家手动还原（不推进小关）
    gui.animation_duration = 300
    gui.tut_anim_slowed = False
    saved_dur = gui.animation_duration
    gui._tut_show_solution()
    _check('解法播完不推进小关', gui.tut_sublevel == '2.1', str(gui.tut_sublevel))
    _check('解法播完回到第 0 步', gui.step_count == 0, f'step_count={gui.step_count}')
    _check('解法历史被清空（只剩初始快照）', len(gui.game_history.history) == 1,
           f'snapshots={len(gui.game_history.history)}')
    _check('撤销/重做失效', gui.game_history.can_undo() is False
           and gui.game_history.can_redo() is False, '')
    _check('解法播完解锁棋盘', gui._tut_board_locked() is False, '')
    _check('解法结束动画速度还原', gui.tut_anim_slowed is False
           and gui.animation_duration == saved_dur, f'dur={gui.animation_duration}')
    _check('连续重做已结束', getattr(gui, '_continuous_redo', False) is False, '')
    _check('提示玩家自行还原', '自行还原' in gui.macro_notify_msg, gui.macro_notify_msg)

    # 8.3 播放中保持调慢 / 结束后由 tick 钩子还原
    gui.tut_anim_slowed = True
    gui.animation_duration = 600
    gui._tut_saved_anim_duration = 300
    gui._continuous_redo = True
    gui._tut_tick_restore_anim_speed()
    _check('播放中保持调慢', gui.tut_anim_slowed is True
           and gui.animation_duration == 600 and gui.tut_solution_playing is True,
           f'dur={gui.animation_duration}')
    gui._continuous_redo = False
    gui._tut_tick_restore_anim_speed()
    _check('结束后还原速度', gui.tut_anim_slowed is False
           and gui.animation_duration == 300, f'dur={gui.animation_duration}')

    # 8.4 小关顺序推进（须玩家手动还原）：2.1 → 2.2 → 2.3 → 第 2 关完成
    _check('当前小关=2.1（解法未推进）', gui.tut_sublevel == '2.1', str(gui.tut_sublevel))
    _check('手动还原 2.1', _manual_solve_current_sublevel(gui) is True, '')
    _check('2.1 还原推进到 2.2', gui.tut_sublevel == '2.2', str(gui.tut_sublevel))
    _check('手动还原 2.2', _manual_solve_current_sublevel(gui) is True, '')
    _check('2.2 还原推进到 2.3', gui.tut_sublevel == '2.3', str(gui.tut_sublevel))
    _check('手动还原 2.3', _manual_solve_current_sublevel(gui) is True, '')
    _check('2.3 还原 → 第2关完成', gui.tut_step == 7, f'step={gui.tut_step}')
    _check('第2关记入完成', 2 in gui._tut_completed_levels(),
           str(gui._tut_completed_levels()))
    _check('2.1-2.3 小关全部记录', gui._tut_completed_sublevels(2) == ['2.1', '2.2', '2.3'],
           str(gui._tut_completed_sublevels(2)))
    compl_note = tut_mod._text_level(2).get('complete_notify', '')
    _check('文案含过关通知', compl_note.startswith('过关！第 2 关（填洞）'), compl_note)

    # 8.5 关卡列表标记已完成；App 状态切换回列表面板正常
    gui._tut_show_level_select()
    gui.draw_tutorial_panel()
    _check('过关后可重进第 2 关', any(b.get('action') == 'load' and b.get('level') == 2
           for b in gui.tut_level_btn_rects), '')

    # 8.6 无存檔的关卡不可载入（自动识别后不出现）
    ok6 = gui._tut_load_level(6)
    _check('无存檔关卡不可玩', ok6 is False, f'ok={ok6}')
    _check('提示待补充', '待补充' in gui.macro_notify_msg, gui.macro_notify_msg)

    # 8.7 第 3/4 关：长 move_info 链的解法回放须能完整播完并回到第 0 步；
    #     但小关推进只能靠玩家手动还原
    def _replay_then_manual_solve():
        """先播一次解法（验证长链回放 + 播完回第 0 步 + 解锁），再手动还原推进。

        返回 (回放是否正常收尾, 手动还原是否成功)。
        """
        before = gui.tut_sublevel
        gui._tut_show_solution()
        replay_ok = (gui.tut_sublevel == before and gui.step_count == 0
                     and len(gui.game_history.history) == 1
                     and gui._tut_board_locked() is False)
        return replay_ok, _manual_solve_current_sublevel(gui)

    _check('点第3关被消费', _click_level(3) is True, '')
    _check('第3关载入 3.1', gui.tut_sublevel == '3.1', str(gui.tut_sublevel))
    _check('第3关打乱态', gui.step_count == 0, f'step_count={gui.step_count}')
    n3 = 0
    while gui.tut_step != 7:
        rep_ok, man_ok = _replay_then_manual_solve()
        _check(f'第3关第{n3 + 1}个小关解法回放正常收尾', rep_ok, '')
        _check(f'第3关第{n3 + 1}个小关手动还原成功', man_ok, '')
        n3 += 1
    _check('第3关 4 个小关全部走完至过关',
           n3 == 4 and gui.tut_step == 7 and gui.tut_progress['completed'] == [1, 2, 3],
           f'n={n3} step={gui.tut_step} completed={gui.tut_progress["completed"]}')
    _check('第3关小关全部记录', gui._tut_completed_sublevels(3) == ['3.1', '3.2', '3.3', '3.4'],
           str(gui._tut_completed_sublevels(3)))

    _check('点第4关被消费', _click_level(4) is True, '')
    _check('第4关载入 4.1', gui.tut_sublevel == '4.1', str(gui.tut_sublevel))
    n4 = 0
    while gui.tut_step != 7 and n4 < 10:   # 上限仅防死循环刷屏，正常 5 个小关
        rep_ok, man_ok = _replay_then_manual_solve()
        _check(f'第4关第{n4 + 1}个小关解法回放正常收尾', rep_ok, '')
        _check(f'第4关第{n4 + 1}个小关手动还原成功', man_ok, '')
        n4 += 1
    _check('第4关 5 个小关全部走完至过关',
           n4 == 5 and gui.tut_step == 7 and gui.tut_progress['completed'] == [1, 2, 3, 4],
           f'n={n4} step={gui.tut_step} completed={gui.tut_progress["completed"]}')
    _check('第4关小关全部记录',
           gui._tut_completed_sublevels(4) == ['4.1', '4.2', '4.3', '4.4', '4.5'],
           str(gui._tut_completed_sublevels(4)))

    # 8.8 有动画时的真实回放路径：连续重做由动画提交逐帧推进；
    #     播放中锁定棋盘操作，播完回第 0 步、清历史且不推进小关
    gui.animation_enabled = True
    gui._tut_load_sublevel('2.1')
    _check('载入 2.1 时未锁定', gui._tut_board_locked() is False, '')
    gui._tut_show_solution()
    _check('动画回放已启动', gui.animating is True and gui._continuous_redo is True,
           f'animating={gui.animating} redo={gui._continuous_redo}')
    _check('回放中锁定棋盘', gui._tut_board_locked() is True, '')

    def _board_sig():
        return (gui.step_count, gui.current_m, gui.current_n,
                [tuple(b.location) for b in gui.game.blocks])

    sig0 = _board_sig()
    _check('回放中移动被拦截', gui.move_selected_blocks('a') is False, '')
    gui.undo()
    gui.shuffle_puzzle()
    gui.reset_puzzle()
    _check('回放中撤销/打乱/重置被拦截', _board_sig() == sig0, '')
    _check('回放中仍保持连续重做', gui._continuous_redo is True, '')

    frames = 0
    while gui.tut_solution_replaying and frames < 2000:
        if gui.animating:   # 强制当前动画到点提交，驱动连续重做推进
            gui.anim_start_time = pygame.time.get_ticks() - gui.animation_duration - 1
        gui.update_animation()
        gui.draw_tutorial_panel()   # 触发 _tut_maybe_finish_replay 收尾
        frames += 1
    _check('动画回放播完解锁', gui._tut_board_locked() is False, f'frames={frames}')
    _check('动画回放播完回到第 0 步', gui.step_count == 0, f'step_count={gui.step_count}')
    _check('动画回放播完历史只剩初始快照', len(gui.game_history.history) == 1,
           f'snapshots={len(gui.game_history.history)}')
    _check('动画回放播完不推进小关', gui.tut_sublevel == '2.1', str(gui.tut_sublevel))
    _check('动画回放结束后已停连续重做', gui._continuous_redo is False, '')
    gui.animation_enabled = False

    # 8.9 第 1 关查看解法：走 IDA* 求解器（1~3*3 状态少），播完同样回第 0 步
    gui._tut_load_level(1)
    gui._tut_set_step(6)
    _check('第1关挑战盘为 1~3*3',
           (gui.current_m, gui.current_n, gui.current_step) == (3, 3, 1),
           f'({gui.current_m},{gui.current_n},{gui.current_step})')
    gui._tut_show_solution()
    _check('第1关解法走 IDA* 并锁定棋盘',
           gui.tut_solution_replaying is True and gui._auto_solve_running is True
           and gui._tut_board_locked() is True, f'run={gui._auto_solve_running}')
    frames = 0
    while gui.tut_solution_replaying and frames < 6000:
        gui._check_auto_solve_result()
        if gui.animating:
            gui.anim_start_time = pygame.time.get_ticks() - gui.animation_duration - 1
        gui.update_animation()
        gui.draw_tutorial_panel()
        frames += 1
        time.sleep(0.001)
    _check('第1关解法播完解锁', gui._tut_board_locked() is False, f'frames={frames}')
    _check('第1关解法播完回第 0 步', gui.step_count == 0, f'step_count={gui.step_count}')
    _check('第1关解法播完历史只剩初始快照', len(gui.game_history.history) == 1,
           f'snapshots={len(gui.game_history.history)}')
    _check('第1关解法播完仍未过关（须手动还原）', gui.tut_step == 6,
           f'step={gui.tut_step}')

    # ---- 9. 弹窗按钮生成（首次启动弹窗） ----
    gui.tut_show_prompt = True
    gui.draw_tutorial_prompt()
    acts = [b['action'] for b in gui.tut_prompt_btn_rects]
    _check('弹窗含 开始/跳过', 'start' in acts and 'skip' in acts, str(acts))

    shutil.rmtree(tmpdir, ignore_errors=True)

    print('\n' + ('ALL PASS' if ok_all else 'SOME FAILED'))
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()