# -*- coding: utf-8 -*-
r"""手动构造画布 headless 集成测试（dummy video，不开窗口）— 计划二 B。

覆盖（计划 §2 步骤 10）：
    1. 画布冒烟：三形态各 进构造 → 点选增/删 → 画布绘制 → 应用，不抛例外
       且 game.blocks 数与构造集一致；
    2. 非法路径：缺块 / 断开 / 类计数错的构造出现非法提示且不应用；
    3. 取消：构造到一半 _ann_build_cancel，局面、历史索引、编号、栈都回到进入前；
    4. 数字栈：进构造编号与进入前逐一相同 → 取一块栈==[该编号] → 放回编号相同
       → 取下 A 再取下 B，放回第一块拿到 B 的编号（后进先出）→ 栈空时再放被拒
       → 清空后按升序压栈、可放满 mn 块且编号集合 == {1..mn} → 应用后编号仍在；
    5. 随机生成：三角/米字下 _ann_btn_random_gen 只给提示、不开对话框、首页无按钮；
    6. 标注模式拒绝：三角/米字下应用（非创造）提示不支援、不进选目标。

运行：D:\python\python.exe test\_test_create_build_canvas.py
"""

import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

from gui.cell_class import cell_class  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def _new_gui():
    from GUI import SliderGUI
    gui = SliderGUI(m=5, n=5, step=2)
    gui.animation_enabled = False
    gui._readonly = False          # 屏蔽工作区 temp_history 残留的只读标记
    gui.save_readonly_flag = False
    # temp_history 可能是三角/米字存档：需要方形局面就先 new_puzzle
    if gui.triangle_mode or gui.mi_mode:
        gui.new_puzzle(5, 5, 2)
    return gui


def _enter_create(gui, shape, shuffle_steps=20):
    """切创造模式并进入手动构造（先建对应形态谜题，可选打乱）。"""
    gui.game_mode = 'create'
    if shape == 'triangle':
        assert gui.new_triangle_puzzle(6, 2)
    elif shape == 'mi':
        assert gui.new_mi_puzzle(6, 6, 2)
    else:
        assert gui.new_puzzle(6, 6, 2)
    if shuffle_steps:
        gui.game.shuffle(shuffle_steps, gui.current_step)
    gui._ann_btn_manual_build()
    assert gui._ann_view == 'build', f"view={gui._ann_view}"
    return gui


def _param(gui):
    return gui._ann_build_param()


def _same_class_spot(kind, step, pos, cells):
    """找 pos 的同类空位（沿 step 方向延伸，保证类计数不变）。"""
    for dy, dx in ((step, 0), (-step, 0), (0, step), (0, -step)):
        y = (pos[0] + dy, pos[1] + dx) + pos[2:]
        if y not in cells and cell_class(y, step, kind) == cell_class(pos, step, kind):
            return y
    return None


def _neighbor_spots(kind, x):
    """x 的相邻位置候选（方块 4 邻、三角/米字用各自 game 的 neighbors）。"""
    if kind == 'square':
        return [(x[0] + dr, x[1] + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))]
    if kind == 'triangle':
        from game_triangle import neighbors as tri_neighbors
        return tri_neighbors(x)
    from game_mi import neighbors as mi_neighbors
    return mi_neighbors(x)


def _kind_of(gui):
    if gui.triangle_mode:
        return 'triangle'
    if gui.mi_mode:
        return 'mi'
    return 'square'


def test_canvas_smoke():
    print("== 1. 画布冒烟：三形态 ==")
    for shape in ('triangle', 'mi', 'square'):
        gui = _enter_create(_new_gui(), shape)
        kind = _kind_of(gui)
        m, n, step = _param(gui)
        cells = set(gui._ann_build_coords)
        n0 = len(cells)
        pos = next(iter(sorted(cells)))
        # 增/删一个位置
        gui._ann_build_toggle(pos)
        check(f"{shape} 移除一块：集合少一", pos not in gui._ann_build_coords
              and len(gui._ann_build_coords) == n0 - 1)
        gui._ann_build_toggle(pos)
        check(f"{shape} 放回：集合复原", pos in gui._ann_build_coords
              and len(gui._ann_build_coords) == n0)
        # 画布绘制（空格轮廓 + 目标框）不抛例外
        gui._ann_draw_bar()
        gui._ann_draw_build_canvas()
        check(f"{shape} 画布绘制无异常", True)
        # 应用（打乱态合法）
        gui._ann_build_apply()
        check(f"{shape} 应用成功回到首页", gui._ann_view == 'home'
              and len(gui.game.blocks) == len(gui._ann_build_coords),
              f"view={gui._ann_view}")


def test_invalid_paths():
    print("== 2. 非法路径：缺块 / 断开 / 类计数错 ==")
    for shape in ('triangle', 'mi', 'square'):
        gui = _enter_create(_new_gui(), shape)
        kind = _kind_of(gui)
        m, n, step = _param(gui)
        cells = set(gui._ann_build_coords)
        n_expected = len(cells)
        # 缺块
        pos = next(iter(sorted(cells)))
        gui._ann_build_toggle(pos)
        text, ok = gui._ann_build_status(*_param(gui))
        check(f"{shape} 缺块：状态非法", not ok and '滑塊數' in text, f"text={text}")
        gui._ann_build_apply()
        check(f"{shape} 缺块：不应用", gui._ann_view == 'build'
              and bool(gui._ann_build_error))
        gui._ann_build_toggle(pos)   # 复原
        # 断开：还原态分两半、下半平移 (10,0)（块数与类计数都对的断开）
        half = sorted(cells)
        cut = n_expected // 2
        disc = set(half[:cut]) | {(p[0] + 10, p[1] + 10) + p[2:]
                                  for p in half[cut:]}
        gui._ann_build_coords = disc
        gui._ann_rebuild_game_from_coords()
        text, ok = gui._ann_build_status(*_param(gui))
        check(f"{shape} 两堆断开：状态非法", not ok and '連通' in text, f"text={text}")
        gui._ann_build_apply()
        check(f"{shape} 断开：不应用", gui._ann_view == 'build')
        # 类计数错：挖一块（保持连通）放到异类邻位（保持连通）
        from game import SliderMatrix
        from game_triangle import TriangleSliderMatrix
        from game_mi import MiSliderMatrix
        conn = (SliderMatrix.is_single_connected if kind == 'square'
                else TriangleSliderMatrix.is_single_connected
                if kind == 'triangle' else MiSliderMatrix.is_single_connected)
        bad = None
        for x in sorted(cells):
            rest = cells - {x}
            if not conn(rest):
                continue
            cx = cell_class(x, step, kind)
            for y in _neighbor_spots(kind, x):
                if y in cells:
                    continue
                if cell_class(y, step, kind) == cx:
                    continue
                new = rest | {y}
                if conn(new):
                    bad = new
                    break
            if bad is not None:
                break
        if bad is None:
            check(f"{shape} 找到类计数错的构造", False, '辅助枚举失败')
        else:
            gui._ann_build_coords = bad
            gui._ann_rebuild_game_from_coords()
            text, ok = gui._ann_build_status(*_param(gui))
            # 方形沿用旧判据消息（mod-step 同餘組計數…）；三角/米字为「類計數…」
            check(f"{shape} 类计数错：状态非法", not ok and '計數' in text,
                  f"text={text}")
            gui._ann_build_apply()
            check(f"{shape} 类计数错：不应用", gui._ann_view == 'build')


def test_cancel():
    print("== 3. 取消：局面 / 历史索引 / 编号 / 栈 回到进入前 ==")
    # 方形 numbered
    gui = _new_gui()
    gui.game_mode = 'create'
    gui.new_puzzle(6, 6, 2, numbered=True)
    gui.game.shuffle(20, 2)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)   # 让「进入前」成为快照（含编号）
    numbers_before = {tuple(b.location): b.number for b in gui.game.blocks}
    hi_before = gui.game_history.history_index
    gui._ann_btn_manual_build()
    check("方形编号 进构造后栈为空", gui._ann_build_num_stack == [])
    pos = next(iter(sorted(gui._ann_build_coords)))
    gui._ann_build_toggle(pos)                 # 取一块 → 栈非空
    gui._ann_build_cancel()
    check("方形编号 取消回首页", gui._ann_view == 'home')
    check("方形编号 栈清空", gui._ann_build_num_stack == [])
    now = {tuple(b.location): b.number for b in gui.game.blocks}
    check("方形编号 局面与编号逐一相同", now == numbers_before)
    check("方形编号 历史索引回到进入前",
          gui.game_history.history_index == hi_before)
    # 三角（无编号）
    gui = _new_gui()
    gui.game_mode = 'create'
    gui.new_triangle_puzzle(6, 2)
    gui.game.shuffle(20, 2)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    cells_before = set(gui.game.positions())
    hi_before = gui.game_history.history_index
    gui._ann_btn_manual_build()
    pos = next(iter(sorted(gui._ann_build_coords)))
    gui._ann_build_toggle(pos)
    gui._ann_build_cancel()
    check("三角 取消回首页与局面复原",
          gui._ann_view == 'home'
          and set(gui.game.positions()) == cells_before
          and gui.game_history.history_index == hi_before)


def test_number_stack():
    print("== 4. 数字谜题编号栈（方形 6×6 step2 numbered）==")
    gui = _new_gui()
    gui.game_mode = 'create'
    # 用还原态进构造（bbox 0..5、内部点丰富；编号 1..36 行主序）
    gui.new_puzzle(6, 6, 2, numbered=True)
    numbers_before = {tuple(b.location): b.number for b in gui.game.blocks}
    assert sorted(numbers_before.values()) == list(range(1, 37))
    gui._ann_btn_manual_build()
    check("进构造：编号与进入前逐一相同",
          gui._ann_build_numbers == numbers_before)
    check("进构造：栈为空", gui._ann_build_num_stack == [])
    # 取一块 → 栈 == [该编号]；放回来编号相同
    pos_a = (1, 1)
    num_a = gui._ann_build_numbers[pos_a]
    gui._ann_build_toggle(pos_a)
    check("取一块：栈 == [该编号]", gui._ann_build_num_stack == [num_a])
    gui._ann_build_toggle(pos_a)
    check("放回来：编号相同且栈空",
          gui._ann_build_numbers[pos_a] == num_a
          and gui._ann_build_num_stack == [])
    # 取下 A 再取下 B，放回第一块拿到 B 的编号（后进先出）
    pos_a, pos_b = (1, 1), (1, 2)
    num_a = gui._ann_build_numbers[pos_a]
    num_b = gui._ann_build_numbers[pos_b]
    gui._ann_build_toggle(pos_a)              # 移除 A → 栈 [num_a]
    gui._ann_build_toggle(pos_b)              # 移除 B → 栈 [num_a, num_b]
    gui._ann_build_toggle(pos_a)              # 放回 A → 弹 num_b
    check("后进先出：放回 A 拿到 B 的编号",
          gui._ann_build_numbers[pos_a] == num_b
          and gui._ann_build_num_stack == [num_a],
          f"stack={gui._ann_build_num_stack}")
    gui._ann_build_toggle(pos_b)              # 放回 B（弹 num_a）→ 栈空
    check("放回 B：栈空", gui._ann_build_num_stack == [])
    # 栈空时再放被拒且有提示（盘满，找盘外位置）
    pos_out = (6, 0)
    gui._ann_build_toggle(pos_out)
    check("栈空再放：被拒且有提示",
          pos_out not in gui._ann_build_coords
          and gui._ann_build_error == '没有可用的编号：先取下一个滑块',
          f"err={gui._ann_build_error}")
    # 清空：编号按升序整批压栈；可放满 mn 块且编号集合 == {1..mn}
    gui._ann_build_clear()
    check("清空：编号按升序压栈（36 个）",
          sorted(gui._ann_build_num_stack) == list(range(1, 37))
          and len(gui._ann_build_num_stack) == 36)
    for r in range(6):
        for c in range(6):
            gui._ann_build_toggle((r, c))
    check("清空后放满 mn 块", len(gui._ann_build_coords) == 36
          and sorted(gui._ann_build_numbers.values()) == list(range(1, 37))
          and gui._ann_build_num_stack == [])
    # 应用后编号仍在（造一个合法形状：还原态挖 (0,0) 放同类 (6,0)）
    gui._ann_build_toggle((0, 0))
    gui._ann_build_toggle((6, 0))
    check("应用前：形状合法（有洞有凸起）",
          gui._ann_build_status(*_param(gui))[1])
    gui._ann_build_apply()
    check("应用成功回首页", gui._ann_view == 'home')
    nums = sorted(b.number for b in gui.game.blocks if b.number is not None)
    check("应用后编号集合 == {1..36}", nums == list(range(1, 37)),
          f"n={len(nums)}")


def test_random_gen_gate():
    print("== 5. 随机生成：三角/米字只提示、不开关、首页无按钮 ==")
    for shape in ('triangle', 'mi'):
        gui = _new_gui()
        gui.game_mode = 'create'
        if shape == 'triangle':
            gui.new_triangle_puzzle(6, 2)
        else:
            gui.new_mi_puzzle(6, 6, 2)
        gui._ann_leave_to_home()
        gui._ann_btn_random_gen()
        check(f"{shape} random_gen 不开对话框",
              gui._ann_sub_dialog is None)
        check(f"{shape} random_gen 只给提示",
              '没有随机生成' in gui.macro_notify_msg,
              f"msg={gui.macro_notify_msg}")
        gui._ann_draw_bar()
        check(f"{shape} 创造模式首页无 random_gen 按钮",
              'random_gen' not in gui._ann_btn_rects
              and 'manual_build' in gui._ann_btn_rects)


def test_annotation_reject():
    print("== 6. 标注模式（非创造）下三角/米字应用被拒 ==")
    for shape in ('triangle', 'mi'):
        gui = _new_gui()                      # 默认 practice 模式
        if shape == 'triangle':
            gui.new_triangle_puzzle(6, 2)
        else:
            gui.new_mi_puzzle(6, 6, 2)
        gui.game.shuffle(20, 2)
        gui._ann_btn_manual_build()
        assert gui._ann_view == 'build'
        gui._ann_build_apply()
        check(f"{shape} 应用被拒：提示不支援标注取样",
              gui._ann_view == 'build'
              and '暂不支援标注取样' in gui.macro_notify_msg,
              f"msg={gui.macro_notify_msg}")


def main():
    test_canvas_smoke()
    test_invalid_paths()
    test_cancel()
    test_number_stack()
    test_random_gen_gate()
    test_annotation_reject()
    if _failures:
        print(f'\nFAILURES: {_failures}')
        sys.exit(1)
    print('\nALL PASS')


if __name__ == '__main__':
    main()
