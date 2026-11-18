"""三维竞速（2026-11-18）：模式放行 + 成绩无损初始局面 + 成绩面板识别/载入。

验收口径：
- 三维局 `set_game_mode('timed')` 放行；
- 竞速初始局面是 `cubic:` 前缀的无损键表（`engine_state.keys`），不是二维矩阵；
- 分組鍵带 `~cubic{m}*{n}*{d}`，不同层数不串榜；
- 成绩面板不把三维当模型板型/矩阵去渲染，详情能画、能载入练习并逐块还原。
"""
import json
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from records import Records  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f"  ok: {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL: {label}" + (f"  <- {extra}" if extra is not None else ''))


def positions(g):
    return sorted(tuple(int(v) for v in b.location) for b in g.game.blocks)


tmp = tempfile.mkdtemp(prefix='cubic_speedrun_')
gui = SliderGUI(m=4, n=4, step=1)
gui.config_dir = tmp
gui.config_path = os.path.join(tmp, 'config.json')
gui.temp_history_path = os.path.join(tmp, 'temp.json')
gui.tutorial_active = False
pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.screen = pygame.display.get_surface()
gui.records = Records(os.path.join(tmp, 'records.json'))

print('A. 模式放行与计时初始局面')
check(gui.new_cubic_puzzle(3, 3, 3, 1), '建立 3×3×3')
check(gui.mode_allowed('timed'), '三维可以进竞速')
check(gui.set_game_mode('timed'), 'set_game_mode(timed) 成功', gui.macro_notify_msg)
gui._timer_enter_ready()
check(gui.timer_state == 'ready', '打乱后进入就绪态', gui.timer_state)
check('~cubic3*3*3' in gui.timer_puzzle_key, '分組鍵带 cubic 尺寸与层数',
      gui.timer_puzzle_key)
raw = gui.timer_initial_matrix
check(raw.startswith('cubic:'), '初始局面是 cubic: 前缀', raw[:20])
try:
    state = json.loads(raw[len('cubic:'):])
    keys = state.get('keys') or []
    check(len(keys) == 27, '无损键表 27 块', len(keys))
    check(all(len(k) == 4 for k in keys), '键表每条 [r,c,d,gid]', keys[:2])
except Exception as exc:  # noqa: BLE001
    check(False, '三维初始局面可解析', exc)

print('B. 写一条三维成绩（临时库，不碰玩家记录）')
rec = gui.records.add_record(gui.timer_puzzle_key, 3, 3, 1, raw,
                             12345.0, 7, False)
check(bool(rec and rec.get('id')), '成绩已追加')
check(not gui._rp_is_shatter(rec), '三维成绩不被误判成模型板型')
check(gui._rp_is_cubic(rec), '成绩面板能识别三维')
_m, _n, _d = gui._rp_cubic_dims(rec)
check((_m, _n, _d) == (3, 3, 3), '从 key 取回 3×3×3', (_m, _n, _d))
check(gui._rp_save_as_puzzle(rec) == '', '三维成绩不产假的二维存档')

print('C. 详情渲染与载入练习')
gui.show_records_panel = True
gui.rp_detail_id = rec['id']
gui.draw_records_panel()
check(getattr(gui, 'rp_matrix_rect', None) is not None
      and gui.rp_matrix_rect.width > 0, '三维详情左栏仍可点击')
# 改一下局面再载入，确保真的还原
gui.game.restore_state({'keys': []})
gui.game.update_matrix()
check(len(gui.game.blocks) == 0, '先清空盘面')
gui._rp_load_into_practice(rec)
check(gui.cubic_mode and gui.current_depth == 3, '载入后仍是三维 3×3×3')
check(len(gui.game.blocks) == 27, '逐块还原 27 块', len(gui.game.blocks))
check(gui.step_count == 0 and gui.game_mode == 'practice', '载入后练习态、步数清零')
check(gui.selected_gap is None and gui.selected_block is None, '载入后清空选中')
_snap = gui.game.snapshot_state()
check(sorted(map(tuple, _snap.get('keys') or [])) == sorted(map(tuple, keys)),
      '还原局面与成绩初始局面一致')

print('D. 计时跑通：解开后真的写进成绩（同一临时库）')
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.set_game_mode('timed')
gui._timer_enter_ready()
gui._timer_start()
check(gui.timer_state == 'running', '空格开始后进入 running')
gui._timer_check_solved()
check(gui.timer_state in ('stopped', 'dnf'), '复原后停止计时', gui.timer_state)
_latest = gui.records.get_records(gui.timer_puzzle_key)
check(bool(_latest) and _latest[0]['initial_matrix'].startswith('cubic:'),
      '成绩落库且初始局面是三维键表')

print('E. 右侧栏：模式与成绩开关在三维真生效')
gui.new_cubic_puzzle(3, 3, 3, 1)
gui.set_game_mode('practice')
_r0 = gui.game_mode
gui._handle_right_panel_switch('game_mode')
check(gui.game_mode == 'timed', '三维点「模式」能进竞速',
      (_r0, gui.game_mode))
gui._handle_right_panel_switch('game_mode')
gui._handle_right_panel_switch('game_mode')
check(gui.game_mode == 'practice', '再点两次回到练习（练习→竞速→创造→练习）',
      gui.game_mode)
_rp0 = bool(gui.show_records_panel)
gui._handle_right_panel_switch('show_records_panel')
check(bool(gui.show_records_panel) != _rp0, '三维点「成绩」能开关面板')

print('=' * 60)
total = PASSED[0] + len(FAILED)
print(f'结果：{"全部通过" if not FAILED else "有失败"}（{PASSED[0]} 项通过，{len(FAILED)} 项失败）／共 {total} 项')
if FAILED:
    for f in FAILED:
        print('  -', f)
sys.exit(1 if FAILED else 0)
