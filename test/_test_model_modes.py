# -*- coding: utf-8 -*-
"""回归：自造谜题（模型文件板型）的模式入口与「该关的接口」。

用户 2026-10-26 报：
  · 自造谜题不能竞速（次要），但**影響是無法進入創造模式**；
  · 著色 / 連鎖 / 宏定義 / 求解器 / 標記这些接口难以在模型板型上统一实现，
    希望「点这些按键时就提示因为是自定义就没这个功能」。

本测试钉住：
  A. 模型局**可以**进创造模式（旧实现把 create 和 timed 一起退回练习）；
  B. 创造模式下换另一个模型谜题，模式仍是创造（不被换局踢回练习）；
  C. 竞速仍被拒：set_game_mode('timed') 拒绝；带着 timed 载模型局自动退回
     练习并说明（旧行为保留，因为 export_map 会丢朝向）；
  D. 创造模式 → 还原态设计 → 搭积木 在模型局能打开（创造模式真的可用）；
  E. 右侧面板「着色 / 连锁 / 复原标记」在模型局**不改变值**且给出提示；
  F. 宏录制 / 宏执行被拦并提示；
  G. 求解器被拦并提示（ok=False）；
  H. 反向护栏：方形局这些开关照旧可用（不要误伤旧四形态）。
  J. 「模式」开关**循环**：模型局按一次直接到创造，跳档要点名说明；
     计时中不许越过闸门；方形局循环顺序不变。

跑法：D:/python/python.exe test/_test_model_modes.py
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402

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


def make(model='shield', step=1):
    """无头 GUI + 一个模型谜题局。"""
    gui = SliderGUI(m=4, n=4, step=step)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    gui.new_model_puzzle(model, step)
    gui.center_map()
    return gui


def _set_msg(gui):
    """清掉通知，便于判断这一下到底说了什么。"""
    gui.macro_notify_msg = ''
    gui.macro_notify_timer = 0


def main():
    gui = make()

    # ---- A. 模型局可进创造模式 -------------------------------------
    check(gui._is_model_kind(), 'A0 shield 被判为模型板型（_is_model_kind）')
    _set_msg(gui)
    ok = gui.set_game_mode('create')
    check(ok and gui.game_mode == 'create' and gui.create_mode,
          'A1 模型局可以进入创造模式（旧实现会被退回练习）',
          f'ok={ok} mode={gui.game_mode}')

    # ---- B. 创造模式下换模型谜题，模式保持 -------------------------
    _set_msg(gui)
    gui.new_model_puzzle('shield', 2)
    check(gui.game_mode == 'create',
          'B1 创造模式下换模型谜题，仍留在创造模式',
          f'mode={gui.game_mode} note={gui.macro_notify_msg!r}')

    # ---- D. 创造模式 → 搭积木 能打开 ------------------------------
    gui._ann_home_sub = 'restore'
    gui._ann_btn_blocks()
    check(gui._med_active, 'D1 模型局创造模式下「搭积木」能打开编辑器',
          f'msg={gui.macro_notify_msg!r}')
    if gui._med_active:
        gui._med_close()
    check(not gui._med_active, 'D2 退出编辑器后会话收摊')

    # ---- C. 竞速仍被拒 -------------------------------------------
    _set_msg(gui)
    gui.set_game_mode('practice')
    check(gui.game_mode == 'practice', 'C0 先退回练习（前置条件）',
          f'mode={gui.game_mode}')
    _set_msg(gui)
    ok = gui.set_game_mode('timed')
    check(not ok and gui.game_mode == 'practice',
          'C1 模型局 set_game_mode("timed") 被拒且留在练习',
          f'ok={ok} mode={gui.game_mode} msg={gui.macro_notify_msg!r}')
    check('竞速' in gui.macro_notify_msg, 'C2 拒绝时说明了原因（竞速）',
          f'msg={gui.macro_notify_msg!r}')

    # 方形局 → 竞速 → 载入模型局：自动退回练习
    gui.new_puzzle(4, 4, 1)
    gui.set_game_mode('timed')
    check(gui.game_mode == 'timed', 'C3 方形局可进竞速（前置条件）')
    gui.new_model_puzzle('shield', 1)
    check(gui.game_mode == 'practice' and '竞速' in gui.macro_notify_msg,
          'C4 带着竞速载模型局 → 退回练习并说明',
          f'mode={gui.game_mode} msg={gui.macro_notify_msg!r}')

    # ---- E. 着色 / 连锁 / 复原标记：不改变值 + 提示 ----------------
    gui.new_model_puzzle('shield', 1)
    for key, label in (('coloring_enabled', '分组着色'),
                       ('chain_hint_enabled', '悬停连锁提示'),
                       ('board_marks_enabled', '复原提示标记')):
        before = getattr(gui, key)
        _set_msg(gui)
        gui._handle_right_panel_switch(key)
        after = getattr(gui, key)
        check(after == before,
              f'E 模型局「{label}」开关不被改动（{before}→{after}）')
        check('暂不支持' in gui.macro_notify_msg
              and label in gui.macro_notify_msg,
              f'E 模型局「{label}」给出「暂不支持」提示',
              f'msg={gui.macro_notify_msg!r}')

    # ---- F. 宏录制 / 宏执行 --------------------------------------
    _set_msg(gui)
    gui._start_macro_recording()
    check(not gui.macro_recording and '暂不支持' in gui.macro_notify_msg,
          'F1 模型局宏录制被拦并提示', f'msg={gui.macro_notify_msg!r}')
    _set_msg(gui)
    ok, msg = gui._do_macro_execute('任意宏', 0, 0)
    check(not ok and '暂不支持' in msg,
          'F2 模型局宏执行被拦并提示', f'ok={ok} msg={msg!r}')

    # ---- G. 求解器 -----------------------------------------------
    _set_msg(gui)
    ok, msg = gui._do_solve()
    check(not ok and '暂不支持' in msg,
          'G1 模型局求解器被拦并提示', f'ok={ok} msg={msg!r}')
    check(not gui.macro_notify_msg == '',
          'G2 求解器被拦时也有可见通知（不是只回一个字符串）',
          f'msg={gui.macro_notify_msg!r}')

    # ---- I. 改当前盘面：把在玩的模型局导入编辑器 ------------------
    gui.new_model_puzzle('shield', 1)
    gui.set_game_mode('create')
    gui._ann_home_sub = 'restore'
    n_before = len(gui.game.blocks)
    keys_before = set(gui.game.board.keys)
    _set_msg(gui)
    gui._ann_btn_blocks_current()
    check(gui._med_active, 'I1 「改当前盘面」打开搭积木编辑器',
          f'msg={gui.macro_notify_msg!r} {gui._ann_msg!r}')
    if gui._med_active:
        placed = gui._med['placed']
        check(len(placed) == n_before,
              f'I2 导入块数与当前局面一致（{n_before}→{len(placed)}）')
        check(bool(gui._med['images']) and 'tri' in gui._med['images'],
              'I3 形状库按模型朝向表重建（含 tri）',
              f'shapes={sorted(gui._med["images"])}')
        try:
            spec = gui.game.spec
            comps = spec.components(frozenset(gui.game.board.keys))
            n_comp = len(comps)
        except Exception as exc:            # noqa: BLE001
            n_comp = -1
            print('  （连通分量计算失败：', exc, '）')
        check(n_comp == 1, f'I4 预览局仍是单一连通分量（{n_comp}）')
        gate_ok, why = gui._med_gate()
        check(gate_ok, 'I5 导入的盘面通过保存门（连通 + ≥2 可动）',
              f'why={why!r}')
        gui._med_close()
        check(not gui._med_active, 'I6 退出编辑器后会话收摊')
        check(len(gui.game.blocks) == n_before
              and set(gui.game.board.keys) == keys_before,
              'I7 退出后原局逐块复原（键集一致）')
    else:
        check(False, 'I2-I7 跳过（编辑器没打开）')

    # ---- I-2. 碎三角（同为模型板型，但晶格与编辑器不相容）---------
    # shatter 的 basis 是旋转 30° 的三角格（顶点格），与搭积木的 tri 基
    # 不是同一套整数格——导不进编辑器是**预期**的。要求只有一条：不能
    # 静默给一个残缺盘，必须说明并退回空盘。
    if gui.new_model_puzzle('shatter', 1):
        gui.set_game_mode('create')
        gui._ann_home_sub = 'restore'
        n_sh = len(gui.game.blocks)
        gui._ann_btn_blocks_current()
        if gui._med_active:
            n_imp = len(gui._med['placed'])
            if n_imp == n_sh:
                gate_ok, why = gui._med_gate()
                check(gate_ok, 'I8 碎三角导入盘面通过保存门', f'why={why!r}')
            else:
                check(n_imp == 1 and '无法导入' in gui.macro_notify_msg,
                      'I8 碎三角晶格不相容：明确提示并退回空盘（不静默残缺）',
                      f'placed={n_imp} msg={gui.macro_notify_msg!r}')
            gui._med_close()
        else:
            check(False, 'I8 跳过（碎三角编辑器没打开）')

    # ---- H. 反向护栏：方形局照旧 --------------------------------
    gui.new_puzzle(4, 4, 1)
    check(not gui._is_model_kind(), 'H0 方形局不是模型板型')
    before = gui.coloring_enabled
    _set_msg(gui)
    gui._handle_right_panel_switch('coloring_enabled')
    check(gui.coloring_enabled != before,
          'H1 方形局「分组着色」仍可切换（别误伤旧四形态）',
          f'msg={gui.macro_notify_msg!r}')
    before = gui.chain_hint_enabled
    gui._handle_right_panel_switch('chain_hint_enabled')
    check(gui.chain_hint_enabled != before,
          'H2 方形局「悬停连锁提示」仍可切换')
    ok, msg = gui._do_solve('gather')
    check(ok, 'H3 方形局求解器照常启动（不被模型闸门误拦）', f'msg={msg!r}')
    if ok:
        gui._do_cancel_solve()

    # ---- J. 「模式」开关循环：模型局必须真的走得到创造 ------------
    # 用户 2026-10-26 二次报的 bug：set_game_mode('create') 本身放行（A1 绿），
    # 但右侧那枚开关是**循环**的（练习→竞速→创造），模型局卡在竞速被拒那一步
    # 原地不动，于是点多少下都进不了创造——A 组测的是 API，没测到开关。
    gui.new_model_puzzle('shield', 1)
    gui.set_game_mode('practice')
    _set_msg(gui)
    check(gui.game_mode == 'practice' and gui._is_model_kind(),
          'J0 前置：模型局在练习模式', f'mode={gui.game_mode}')
    check(not gui.mode_allowed('timed') and gui.mode_allowed('create')
          and gui.mode_allowed('practice'),
          'J1 mode_allowed：模型局只有竞速被拒')
    gui.toggle_game_mode()
    check(gui.game_mode == 'create' and gui.create_mode,
          'J2 模型局按一次「模式」开关直达创造（跳过不支持的竞速）',
          f'mode={gui.game_mode} msg={gui.macro_notify_msg!r}')
    check('跳过' in gui.macro_notify_msg and '竞速' in gui.macro_notify_msg,
          'J3 跳档时点名「竞速已跳过」，不是静默跳',
          f'msg={gui.macro_notify_msg!r}')
    _set_msg(gui)
    gui.toggle_game_mode()
    check(gui.game_mode == 'practice',
          'J4 创造再按一次回到练习（也不落进竞速）',
          f'mode={gui.game_mode} msg={gui.macro_notify_msg!r}')
    seen = []
    for _ in range(4):
        gui.toggle_game_mode()
        seen.append(gui.game_mode)
    check('timed' not in seen, f'J5 模型局连按 4 次从不落进竞速（{seen}）',
          f'seen={seen}')

    # 计时中仍应拒绝（跳档逻辑不许越过计时闸门）
    gui.new_puzzle(4, 4, 1)
    gui.set_game_mode('timed')
    gui.timer_state = 'running'
    _set_msg(gui)
    gui.toggle_game_mode()
    check(gui.game_mode == 'timed' and '计时' in gui.macro_notify_msg,
          'J6 计时中按「模式」开关被拒并说明（跳档不越过计时闸门）',
          f'mode={gui.game_mode} msg={gui.macro_notify_msg!r}')
    gui.timer_state = 'idle'

    # 反向护栏：方形局循环顺序不变
    gui.set_game_mode('practice')
    check(gui.mode_allowed('timed'),
          'J7a 方形局 mode_allowed("timed") 仍为真（别误伤旧四形态）')
    seq = []
    for _ in range(3):
        gui.toggle_game_mode()
        seq.append(gui.game_mode)
    check(seq == ['timed', 'create', 'practice'],
          f'J7 方形局循环仍是 练习→竞速→创造→练习（{seq}）', f'seq={seq}')

    print(f"\n结果：{'全部通过' if not _fail else str(len(_fail)) + ' 项失败'} "
          f"（{_ok[0]} 项通过）")
    if _fail:
        for m in _fail:
            print('  · 失败：', m)
        sys.exit(1)


if __name__ == '__main__':
    main()
