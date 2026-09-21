# -*- coding: utf-8 -*-
"""B5：三角形密铺的竞速计时 / 成绩记录 / 面板取回。

执行：python test/_test_triangle_timer.py
覆盖：_timer_enter_ready 不再拦截三角（key = {step}~tri{k}）、
      initial_matrix 用 #^v_ 原生编码、records.add_record 落 key、
      _rp_record_map_str / _rp_matrix_display / _rp_save_as_puzzle /
      _rp_load_into_practice 的三角分派、_do_load_map 刷新目标轮廓、
      计时中判胜写成绩、方形与序号无回归。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI  # noqa: E402
from game_triangle import TriangleSliderMatrix  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False

# ================================================================ 就绪态
print("== _timer_enter_ready 三角分支 ==")
gui.new_triangle_puzzle(6, 2)
gui._timer_enter_ready()
check(f"不再被 B5 拦截，timer_state = {gui.timer_state}",
      gui.timer_state == 'ready')
check(f"timer key = {gui.timer_puzzle_key}", gui.timer_puzzle_key == '2~tri6')
check(f"timer m/n/step = {gui.timer_m}/{gui.timer_n}/{gui.timer_step}",
      (gui.timer_m, gui.timer_n, gui.timer_step) == (6, 6, 2))
init_map = gui.timer_initial_matrix
check(f"initial_matrix 字元集 = {sorted(set(init_map))}",
      set(init_map) <= set('#^v_\n'))
check("initial_matrix 无残留 0/1 替换痕迹", '1' not in init_map and '0' not in init_map)

# ================================================================ 写成绩
print("== 计时→判胜→写成绩 ==")
gui.new_triangle_puzzle(6, 2)
solid_map = gui.game.export_map()      # 边長 6 實心大三角的地圖串（稍後擺回去判勝）
check(f"實心大三角地圖行數 = {len(solid_map.splitlines())}",
      len(solid_map.splitlines()) == 6)
gui.set_game_mode('timed')
gui.shuffle_puzzle()
check(f"打乱后进入就绪态（{gui.timer_state}）", gui.timer_state == 'ready')
check(f"打乱后 initial_matrix 仍是 #^v_（字元集 {sorted(set(gui.timer_initial_matrix))}）",
      set(gui.timer_initial_matrix) <= set('#^v_\n'))
check("打乱后未判胜", gui.is_solved() is False)

gui._timer_start()
check(f"计时运行中（{gui.timer_state}）", gui.timer_state == 'running')
# 手动摆回实心大三角 → 应判胜；计时由主循环调的 _timer_check_solved 收尾
# （直接改 game，不走 _do_load_map 以免重置计时态）
gui.game.import_map(solid_map)
check("实心大三角判胜", gui.is_solved() is True)
gui._timer_check_solved()
check(f"判胜后计时自动停止（{gui.timer_state}）", gui.timer_state == 'stopped')
recs = gui.records.get_records('2~tri6')
check(f"成绩写入 key 2~tri6（{len(recs)} 条）", len(recs) == 1)
rec = recs[0]
check(f"成绩 m/n/step = {rec['m']}/{rec['n']}/{rec['step']}",
      (rec['m'], rec['n'], rec['step']) == (6, 6, 2))
check(f"成绩 initial_matrix 字元集 = {sorted(set(rec['initial_matrix']))}",
      set(rec['initial_matrix']) <= set('#^v_\n'))
check("非 DNF 成绩 dnf 为假", rec['dnf'] is False)

# DNF：重开一局，走空格键的 _timer_finish(dnf=True)
gui.shuffle_puzzle()
gui._timer_start()
gui._timer_finish(dnf=True)
check(f"DNF 也写入（共 {len(gui.records.get_records('2~tri6'))} 条）",
      len(gui.records.get_records('2~tri6')) == 2)
check("DNF 记录标记 dnf",
      gui.records.get_records('2~tri6')[1]['dnf'] is True)

# ================================================================ 面板取回
print("== 成绩面板三角分派 ==")
check(f"_rp_current_key = {gui._rp_current_key()}", gui._rp_current_key() == '2~tri6')
check("_rp_is_triangle 认出三角记录", gui._rp_is_triangle(rec) is True)
check("_rp_is_triangle 不误判方形记录",
      gui._rp_is_triangle({'puzzle_key': '2~6*6'}) is False)
check("_rp_is_triangle 不误判序号记录",
      gui._rp_is_triangle({'puzzle_key': '2~6*6#num'}) is False)
check("_rp_record_map_str 原样返回 #^v_", gui._rp_record_map_str(rec) == rec['initial_matrix'])
disp = gui._rp_matrix_display(rec['initial_matrix'], True)
check(f"面板渲染字元集 = {sorted(set(disp))}", set(disp) <= set('█▲▼·\n'))
check("方形 0/1 仍渲染成 █/·",
      gui._rp_matrix_display('10\n01', False) == '█·\n·█')

# 面板详情真画一遍：▲/▼ 字形与裁剪路径都要走得通
gui.show_records_panel = True
gui.rp_detail_id = rec['id']
gui._rp_draw_detail(0, 0, 420, 320, rec)
check("面板详情渲染三角 initial_matrix 正常", True)

# 另存为谜题：产出 v2 三角存档
path = gui._rp_save_as_puzzle(rec)
check(f"另存为谜题成功：{os.path.basename(path) if path else '(失败)'}", bool(path))
if path:
    import json
    with open(path, 'r', encoding='utf-8') as f:
        saved = json.load(f)
    check("另存存档 version=2 / type=triangle / triangle_side=6",
          saved['version'] == 2 and saved['puzzle']['type'] == 'triangle'
          and saved['puzzle']['triangle_side'] == 6)
    check("另存存档快照是 2-bit 菱形网格",
          all(v in (0, 1, 2, 3)
              for row in saved['history']['snapshots'][0]['matrix'] for v in row))
    # 该存档能直接载入，且仍是三角形
    gui.new_puzzle(5, 5, 2)
    gui._load_save_data(saved)
    check("另存存档可载入且形态为三角",
          gui.triangle_mode is True and isinstance(gui.game, TriangleSliderMatrix)
          and gui.game.k == 6)
    os.remove(path)

# 载入练习：复现该打乱，形态/轮廓/缩放都对
gui.new_puzzle(4, 4, 2)
gui._rp_load_into_practice(rec)
check("载入练习后 triangle_mode 复原", gui.triangle_mode is True)
check("载入练习后 game 为三角形且边长 6",
      isinstance(gui.game, TriangleSliderMatrix) and gui.game.k == 6)
check(f"载入练习后块数 = {len(gui.game.blocks)}", len(gui.game.blocks) == 36)
# 位置应与 initial_matrix 一致：拿一份新三角局导入同一串来比对
probe = TriangleSliderMatrix(rec['m'])
check("initial_matrix 可被三角局解析", probe.import_map(rec['initial_matrix']))
check("载入练习后位置与 initial_matrix 一致",
      set(gui.game.positions()) == set(probe.positions()))
check(f"目标轮廓仍是边长 6 实心大三角（{len(gui._tri_goal_cells)} 格）",
      gui._tri_goal_cells == gui.game.goal_cells())
check(f"载入练习后 game_mode = {gui.game_mode}", gui.game_mode == 'practice')
check("载入练习后步数归零", gui.step_count == 0)
check("载入练习后历史只有导入态一条", len(gui.game_history.history) == 1)

# ================================================================ 地图导入刷新轮廓
print("== _do_load_map 刷新目标轮廓 ==")
gui.new_triangle_puzzle(6, 1)
before = set(gui._tri_goal_cells)
gui._do_load_map('\n'.join('^' * 6 for _ in range(6)))     # 纯 ▲ 菱形片，形状完全不同
check(f"导入后目标轮廓未随局部形状改变（{len(gui._tri_goal_cells)} 格）",
      gui._tri_goal_cells == before)
check("导入后轮廓 = 边长 6 实心大三角", gui._tri_goal_cells == gui.game.goal_cells())
check(f"导入后块数 = {len(gui.game.blocks)}", len(gui.game.blocks) == 36)

# ================================================================ 回归
print("== 方形 / 序号无回归 ==")
gui.new_puzzle(6, 6, 2)
gui._timer_enter_ready()
check(f"方形 timer key = {gui.timer_puzzle_key}", gui.timer_puzzle_key == '2~6*6')
check("方形 initial_matrix 仍为 0/1",
      set(gui.timer_initial_matrix) <= set('01\n'))
check(f"方形 _rp_current_key = {gui._rp_current_key()}",
      gui._rp_current_key() == '2~6*6')
gui.new_puzzle(6, 6, 2, numbered=True)
gui._timer_enter_ready()
check(f"序号 timer key = {gui.timer_puzzle_key}",
      gui.timer_puzzle_key == '2~6*6#num')
check("序号 initial_matrix 仍为 0/1", set(gui.timer_initial_matrix) <= set('01\n'))
check(f"序号 _rp_current_key = {gui._rp_current_key()}",
      gui._rp_current_key() == '2~6*6#num')

# 序号记录不能被误判成三角（否则 save_as / load_into_practice 会走错分支）
sq_rec = {'puzzle_key': '2~6*6#num', 'm': 6, 'n': 6, 'step': 2,
          'initial_matrix': '1' * 6 + '\n' + '0' * 6}
check("序号记录 _rp_is_triangle 为假", gui._rp_is_triangle(sq_rec) is False)
check("序号记录 _rp_record_map_str 仍换回 #/_",
      gui._rp_record_map_str(sq_rec) == '#' * 6 + '\n' + '_' * 6)

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
