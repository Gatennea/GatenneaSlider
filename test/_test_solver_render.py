# -*- coding: utf-8 -*-
"""求解器渲染文案 / 边框配色的护栏（纯函数 + 渲染层判据）。

覆盖两件事：

1. 求解完成提示文案：算法**全称** + 总用时 + TPS；缺用时就不编数字。
   （用户要求「求解完成之后提示要添加总用时、tps」，且「全称都显示当前算法」。）
2. 思考游走「假装尝试」的边框：必须走白色（is_think），不是重做橙。
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.progress_text import (            # noqa: E402
    format_solve_done, solver_display_name)
from gui.renderer import RendererMixin     # noqa: E402


class ProgressTextTest(unittest.TestCase):

    def test_display_name_is_full_name(self):
        self.assertEqual(solver_display_name('hybrid'), '混合求解')
        self.assertEqual(solver_display_name('gather_gradient'), '梯度聚拢')
        self.assertEqual(solver_display_name('gap_macro'), '填洞补缺')
        self.assertEqual(solver_display_name('gather'), '单次聚拢')

    def test_done_includes_time_and_tps(self):
        s = format_solve_done('混合求解', 42, 1800, solved=True)
        self.assertIn('混合求解', s)
        self.assertIn('已复原', s)
        self.assertIn('42 步', s)
        self.assertIn('用时 1.8s', s)
        self.assertIn('TPS 23.3', s)   # 42 / 1.8 = 23.33

    def test_done_without_elapsed_omits_numbers(self):
        s = format_solve_done('单次聚拢', 7, None, solved=False)
        self.assertIn('单次聚拢', s)
        self.assertIn('完成', s)
        self.assertIn('7 步', s)
        self.assertNotIn('用时', s)
        self.assertNotIn('TPS', s)

    def test_done_extra_appended(self):
        s = format_solve_done('单次聚拢', 7, 500, solved=False,
                              extra='停在聚拢度最高态 0.970')
        self.assertIn('停在聚拢度最高态 0.970', s)


class _BorderHost(RendererMixin):
    """只喂 _sel_anim_border 需要的属性，直接调真实渲染层方法。"""

    def __init__(self, think, undo):
        self.selection_animation_enabled = True
        self.ui_mode = 'enhanced'
        self._sel_anim_timer = 100
        self._sel_anim_is_think = think
        self._sel_anim_is_undo = undo
        self.zoom = 1.0


class SelAnimBorderTest(unittest.TestCase):

    def test_think_is_white(self):
        h = _BorderHost(think=True, undo=False)
        color, _w = h._sel_anim_border()
        self.assertEqual(color, RendererMixin.PLAY_HEAD_BORDER)

    def test_think_beats_undo(self):
        """白边优先级最高（防御）：即便同时带 is_undo 也画白。

        生产里两者互斥——撤回不传 is_think（见 _test_think_walk_selection 的
        「撤回走撤销蓝」用例），这里只钉住渲染层的取值顺序。
        """
        h = _BorderHost(think=True, undo=True)
        color, _w = h._sel_anim_border()
        self.assertEqual(color, RendererMixin.PLAY_HEAD_BORDER)

    def test_redo_is_orange(self):
        h = _BorderHost(think=False, undo=False)
        color, _w = h._sel_anim_border()
        self.assertEqual(color, RendererMixin.SEL_ANIM_BORDER_REDO)

    def test_undo_is_blue(self):
        h = _BorderHost(think=False, undo=True)
        color, _w = h._sel_anim_border()
        self.assertEqual(color, RendererMixin.SEL_ANIM_BORDER_UNDO)

    def test_timer_zero_no_border(self):
        h = _BorderHost(think=True, undo=False)
        h._sel_anim_timer = 0
        self.assertIsNone(h._sel_anim_border())


class LegacyGuiTest(unittest.TestCase):
    """旧搜索三项从 GUI 隐藏，但 key 仍保留（HTTP/老配置可识别）。"""

    def test_hidden_set_keeps_keys(self):
        from solver import (SOLVER_ALGORITHMS,
                            GUI_HIDDEN_SOLVER_ALGORITHMS)
        for k in ('ida_star', 'fast', 'greedy'):
            self.assertIn(k, GUI_HIDDEN_SOLVER_ALGORITHMS)
            self.assertIn(k, SOLVER_ALGORITHMS)   # 注册表仍认得
        # 查表求解保留在 GUI（有数据库时亚秒级）
        self.assertNotIn('table', GUI_HIDDEN_SOLVER_ALGORITHMS)

    def test_migrate_legacy_to_hybrid(self):
        from gui.file_ops import _migrate_solver_algorithm as m
        for k in ('ida_star', 'fast', 'greedy'):
            self.assertEqual(m(k), 'hybrid')
        # 其它 key 原样保留
        self.assertEqual(m('table'), 'table')
        self.assertEqual(m('hybrid'), 'hybrid')
        self.assertEqual(m('gather'), 'gather')


if __name__ == '__main__':
    unittest.main()
