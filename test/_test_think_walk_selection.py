# -*- coding: utf-8 -*-
"""求解器「思考」演示：选中动画走渲染途径 + 聚拢度稳定选步（待办 §三十四 第 4 条）。

两个独立行为的护栏，均不依赖真实显示：

1. 选中动画（Task #39）：游走步落下后通过真实渲染途径画高亮——选中缝隙红线
   （selected_gap）+ 滑块组提亮（be_opted），关掉选中动画时不留高亮。
   直接驱动真实 ``_think_do_walk``（走真实引擎接口 + 真实 ``_flash_move_selection``），
   校验 be_opted / selected_gap 落地，而非只看「有没有调用」。

2. 聚拢度稳定选步（Task #40）：仍是随机抽步，但优先选「做完之后聚拢度几乎不变」
   的步；并避开上一步正好反向。用受控假引擎 + 受控 gather_metrics 断言：最小
   Δ 档被选中、反向步被排除。反向验证：把「good 集合」改成让另一档也成最小 Δ，
   断言改用非反向那一步。
"""
import os
import sys
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import gui.auto_solve as auto_solve  # noqa: E402
import gui.animation as animation  # noqa: E402
from gui.think_walk import ThinkWalk  # noqa: E402


# 受控坐标集合：PRE 是初始盘面，A/C/B 是三步各自推完后的盘面条数分布
PRE_SET = frozenset({(0, 0), (1, 0), (2, 0), (3, 0)})
A_POST = frozenset({(0, 2), (1, 0), (2, 0), (3, 0)})   # 水平右移一格（行内）
C_POST = frozenset({(0, -2), (1, 0), (2, 0), (3, 0)})  # 水平左移一格（行内）
B_POST = frozenset({(2, 0), (1, 0), (3, 0)})           # 垂直下移，落到已占格（3 格）


class _Blk:
    def __init__(self, r, c):
        self.location = [r, c]
        self.be_opted = False


class _FakeHistory:
    def __init__(self):
        self.history = []
        self.history_index = -1
        # 非 None 时 undo 成功并回吐这条 move_info（供「撤回配色」用例驱动真路径）
        self.undo_move_info = None

    def save_snapshot(self, game, move_info=None, key=None):
        self.history.append({'move_info': move_info})
        self.history_index = len(self.history) - 1

    def undo(self, game):
        if self.undo_move_info is None:
            return (False, None)
        return (True, self.undo_move_info)

    def restore_snapshot(self, game, index):
        pass


class _FakeGame:
    def __init__(self):
        self.m = 4
        self.n = 4
        self.blocks = [_Blk(0, 0), _Blk(1, 0), _Blk(2, 0), _Blk(3, 0)]
        # 仅 blocks[0] 可动；终态与方向位移严格一致（'d'/'a' 行内、's' 列内）
        self._fin = {
            ('h', 0, 'd'): [(0, 2)],    # A
            ('h', 0, 'a'): [(0, -2)],   # C
            ('v', 0, 's'): [(2, 0)],    # B
        }

    def opt(self, gt, line, blk):
        self._cur_gap = gt
        self._cur_line = line
        for b in self.blocks:
            b.be_opted = False
        blk.be_opted = True

    def try_move(self, d, step):
        sel = [b for b in self.blocks if b.be_opted]
        if sel != [self.blocks[0]]:
            return []
        gt = getattr(self, '_cur_gap', None)
        ln = getattr(self, '_cur_line', None)
        fin = self._fin.get((gt, ln, d))
        if fin is None:
            return []
        return [list(p) for p in fin]

    def commit_move(self, final_positions):
        sel = [b for b in self.blocks if b.be_opted]
        for b, p in zip(sel, final_positions):
            b.location = list(p)

    def _ann_all_valid_gaps(self):
        return [('h', 0), ('v', 0)]

    def _ann_dirs_for_gap(self, gt):
        return ('a', 'd') if gt == 'h' else ('s', 'w')


class _WideGame(_FakeGame):
    """大盘面替身：40 块 × 20 条缝全可动，用来量「抽样是否真压住了枚举量」。

    全量枚举 = 20 缝 × 40 块 × 2 方向 = 800 次 opt；抽样应只有 3×6=18 次。
    """

    def __init__(self):
        super().__init__()
        self.opted = 0
        self.blocks = [_Blk(r, c) for r in range(8) for c in range(5)]
        self._gaps = ([('h', i) for i in range(10)]
                      + [('v', i) for i in range(10)])

    def opt(self, gt, line, blk):
        self.opted += 1
        super().opt(gt, line, blk)

    def _ann_all_valid_gaps(self):
        return list(self._gaps)

    def try_move(self, d, step):
        sel = [b for b in self.blocks if b.be_opted]
        return [(b.location[0], b.location[1] + 1) for b in sel]


class _Host(auto_solve.AutoSolveMixin, animation.AnimationMixin):
    def __init__(self, selection_enabled):
        self.game = _FakeGame()
        self.current_step = 2
        self.selection_animation_enabled = selection_enabled
        self.selected_gap = None
        self.animation_duration = 0
        self._think_walk = ThinkWalk(delay_frames=1, walk_frames=1,
                                     rewind_frames=1, max_steps=9)
        self._think_history = _FakeHistory()

    # 真实 GUI 上这些方法在注解 mixin 里、挂在 self 上；测试 host 委托给假引擎
    def _ann_all_valid_gaps(self):
        return self.game._ann_all_valid_gaps()

    def _ann_dirs_for_gap(self, gt):
        return self.game._ann_dirs_for_gap(gt)


def _run(host, good_sets):
    """在受控 gather_metrics 下驱动一次真实 _think_find_move / _think_do_walk。"""

    def fake_gather(coords, m, n):
        return {'score': 1.0 if coords in good_sets else 0.5}

    with mock.patch('solver.ml.gather_solver.gather_metrics', side_effect=fake_gather):
        return host._think_find_move()


def _run_walk(host, good_sets):
    def fake_gather(coords, m, n):
        return {'score': 1.0 if coords in good_sets else 0.5}

    with mock.patch('solver.ml.gather_solver.gather_metrics', side_effect=fake_gather):
        return host._think_do_walk()


class ThinkWalkSelectionTest(unittest.TestCase):

    def test_gather_stable_picks_min_delta(self):
        """最小 |Δ聚拢度| 档被选中：A（Δ=0）优于 C/B（Δ=0.5）。"""
        host = _Host(selection_enabled=True)
        spec = _run(host, {PRE_SET, A_POST})
        self.assertEqual(spec[0], 'h')
        self.assertEqual(spec[1], 0)
        self.assertEqual(spec[2], 'd')
        self.assertEqual(spec[3], [[0, 2]])

    def test_reverse_avoidance_prefers_non_reverse(self):
        """A 与 C 同为最小 Δ，但 A 是上一步（h,0,'a'）的反向 → 改选 C。"""
        host = _Host(selection_enabled=True)
        host._think_last_move = ('h', 0, 'a')
        spec = _run(host, {PRE_SET, A_POST, C_POST})
        self.assertEqual((spec[0], spec[1], spec[2]), ('h', 0, 'a'))
        self.assertEqual(spec[3], [[0, -2]])

    def test_walk_flashes_selection_when_enabled(self):
        """选中动画走真实渲染途径：游走步落下后 be_opted + selected_gap 落地。"""
        host = _Host(selection_enabled=True)
        ok = _run_walk(host, {PRE_SET, A_POST})
        self.assertTrue(ok)
        # 选中组（blocks[0]）被提亮，缝隙红线指向本次走的缝
        self.assertTrue(host.game.blocks[0].be_opted)
        self.assertFalse(any(b.be_opted for b in host.game.blocks[1:]))
        self.assertEqual(host.selected_gap, ('h', 0))

    def test_walk_clears_selection_when_disabled(self):
        """关掉选中动画：不碰盘面状态，be_opted 清干净、selected_gap 不变脏。"""
        host = _Host(selection_enabled=False)
        ok = _run_walk(host, {PRE_SET, A_POST})
        self.assertTrue(ok)
        self.assertFalse(any(b.be_opted for b in host.game.blocks))
        self.assertIsNone(host.selected_gap)

    def test_walk_marks_think_for_white_border(self):
        """游走步必须打 is_think 标记——渲染层据此把边框画白，不是重做橙。"""
        host = _Host(selection_enabled=True)
        ok = _run_walk(host, {PRE_SET, A_POST})
        self.assertTrue(ok)
        self.assertTrue(getattr(host, '_sel_anim_is_think', False))
        self.assertGreater(getattr(host, '_sel_anim_timer', 0), 0)

    def test_clear_sel_anim_resets_think(self):
        """收掉高亮时必须复位 is_think，避免白色残留到下一轮真实撤销/重做。"""
        host = _Host(selection_enabled=True)
        _run_walk(host, {PRE_SET, A_POST})
        self.assertTrue(getattr(host, '_sel_anim_is_think', False))
        host._clear_sel_anim()
        self.assertFalse(getattr(host, '_sel_anim_is_think', False))

    def test_rewind_uses_undo_blue_not_white(self):
        """撤回不继承白边：渲染层应拿到 is_undo=True 且 is_think=False（撤销蓝）。

        白色只标「往前假装走」；往回退按普通撤销配色，玩家一眼能分方向。
        """
        host = _Host(selection_enabled=True)
        host._think_history.undo_move_info = {
            'gap_type': 'h', 'gap_line': 0, 'direction': 'd',
            'moved_positions': [[0, 2]],
        }
        host._think_undo_now(with_sound=False)
        self.assertTrue(getattr(host, '_sel_anim_is_undo', False))
        self.assertFalse(getattr(host, '_sel_anim_is_think', False))
        self.assertGreater(getattr(host, '_sel_anim_timer', 0), 0)

    def test_sampling_bounds_engine_calls(self):
        """选步必须抽样枚举，不能全量——全量在 6×6 上要 400ms/步，是「隔一下走一步」的真凶。

        40 块 × 20 缝的大盘替身，全量会是 800 次 opt；抽样后应只有 3×6=18 次。
        """
        host = _Host(selection_enabled=True)
        host.game = _WideGame()
        spec = _run(host, {PRE_SET, A_POST})
        self.assertIsNotNone(spec, '大盘面上也得找到一步')
        self.assertLessEqual(host.game.opted, 3 * 6,
                             '抽样没生效：opt 调了 %d 次' % host.game.opted)

    def test_sampling_fallback_never_starves(self):
        """抽样恰好全不合法时必须走**有界兜底**，不能「找不到步」卡死。

        _Host 的假盘只有 blocks[0] 能走；抽样 3 块有 1/4 概率漏掉它。
        2026-11-16（待办 §四十三）：兜底从「全量枚举」改成「小盘全扫 / 大盘
        再抽一批，且受同一墙钟预算约束」——12×12 上旧全量分支单次 13.7s，
        正是「特大尺寸求解无响应」的直接原因。本用例锁的是「小盘仍保证有步」，
        预算上限见 test/_test_think_select_budget.py。
        """
        host = _Host(selection_enabled=True)
        misses = [i for i in range(16) if _run(host, {PRE_SET, A_POST}) is None]
        self.assertEqual(misses, [], '有界兜底也没兜住，游走会卡死')


if __name__ == '__main__':
    unittest.main()
