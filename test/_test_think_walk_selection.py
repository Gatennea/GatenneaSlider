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

    def save_snapshot(self, game, move_info=None, key=None):
        self.history.append({'move_info': move_info})
        self.history_index = len(self.history) - 1

    def undo(self, game):
        return (False, None)

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


if __name__ == '__main__':
    unittest.main()
