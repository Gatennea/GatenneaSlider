# -*- coding: utf-8 -*-
"""对局会话混入：打乱 / 重置 / 当前局信息（种类、key、标签、形态）。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第五步）。
「当前局信息」一族（_current_kind/_current_puzzle_key/_preset_puzzle_key/
_current_puzzle_label/_current_puzzle_form）被计时/记录/求解多处共用，
与打乱/重置同属对局级操作，放同一 mixin。块内只用到 puzzle_key
（from puzzle_types），其余均为 self.*。
"""
from puzzle_types import puzzle_key


class SessionMixin:
    """对局会话操作与当前局信息（原 GUI.py 内联代码，整体搬迁）。"""

    def _space_interrupts_continuous(self) -> bool:
        """空格打斷：仅在连续播放进行中拦截空格，返回 True 表示本次空格已被消费。"""
        if self._continuous_undo or self._continuous_redo:
            self._stop_continuous_undo_redo("已停止连续播放")
            return True
        return False

    def shuffle_puzzle(self):
        """打乱谜题 - 调用 game.py 的 shuffle 核心逻辑"""
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 米字格打乱已随 game_mi.shuffle 落地（M2），无需拦截
        # 打乱会改变棋盘 → 终止梯度流水线
        self._stop_gradient_pipeline()
        # 打乱会改变棋盘 → 打断连续撤销/重做
        self._stop_continuous_undo_redo()
        # 新谜题开始 → 清掉上一次的计时成绩（悬浮窗不再显示）
        self._last_timed_result = None
        # 只读存档：禁止打乱
        if self._readonly_blocked():
            return
        # 标注会话随棋盘重置而结束
        self._ann_cancel_session('打乱')
        # 计时进行中禁止打乱
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法打乱"
            self.macro_notify_timer = 90
            return

        # 取消当前动画 / 打乱演示
        self._abort_shuffle_demo()
        if self.animating:
            self.cancel_animation()

        attempts = self.current_m * self.current_n * 10  # 打乱次数

        # 演示动画起点：打乱前各块位置。打乱本身是纯逻辑、瞬时完成的；
        # 「打乱过程动画」靠 game.shuffle 带 record 记录每步，从该状态重放
        # （格式与语义见 game.record_shuffle_move / gui/animation.py 演示段）
        pre_positions = [list(b.location) for b in self.game.blocks]
        records = []

        # 调用 game.py 的 shuffle 方法，传入偏置强度和难度门槛
        self.game.shuffle(
            attempts, self.current_step,
            bias=self.shuffle_bias,
            min_score=self.shuffle_min_score,
            record=records
        )

        # 清除选中状态
        self.selected_gap = None
        self.selected_block = None

        # 步数归零，重置历史记录（以打乱态为第一条）。演示动画一律不碰
        # 历史——这条语义保持不变：打乱结束（含演示）后历史里只有终态
        self.step_count = 0
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        final_positions = [list(b.location) for b in self.game.blocks]

        # 打乱难度门槛：随机重洗到上限后仍可能未达标，如实提示（不静默）
        unmet = (self.shuffle_min_score is not None
                 and self.game.compute_score() > self.shuffle_min_score)
        if self.game_mode == 'timed':
            self._timer_enter_ready()
            notify_msg = f"已打乱：{attempts}步（空格开始计时）"
        else:
            self._timer_cancel()
            notify_msg = f"已打乱：{attempts}步（练习模式）"
        if unmet:
            notify_msg += "；本次随机打乱未达难度门槛，可再打乱一次"
        notify = (notify_msg, 120)

        # 打乱过程演示：enhanced 模式 + 滑动动画开着 + 确实有可演的步骤。
        # 演示从打乱前状态逐步重放，步数过多只演前几步，再淡出切入终态；
        # 期间棋盘输入被 animating 守卫挡着，结束/中断都会对齐到终态
        demo = (records and self.animation_enabled
                and self.animation_duration > 0
                and getattr(self, 'ui_mode', 'enhanced') == 'enhanced')
        if demo:
            # 通知延后到演示结束再补发：那会儿玩家才能真正操作
            self._start_shuffle_demo(records, pre_positions,
                                     final_positions, notify)
        else:
            self._fit_board_view()
            self.macro_notify_msg, self.macro_notify_timer = notify

    def _fit_board_view(self):
        """按当前盘面适配视图（打乱后 / 演示切终态时用）。"""
        if getattr(self, 'triangle_mode', False):
            # 三角形的缩放本就是自动适配的（建局/载入都走 _fit_triangle_zoom），
            # 而打乱会把形状摊得比初始大三角更开，原 zoom 可能被 max_zoom 夹过、
            # 单靠平移拉不回视口 → 按打乱后的包围盒重新适配并居中
            self.zoom = self._fit_triangle_zoom()
            self.center_map()
        self.ensure_blocks_visible()

    def reset_puzzle(self):
        """重置谜题到初始状态"""
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 只读存档：禁止重置 —— 重置是丢弃当前局面、重新生成同一题，
        # 属于改动这份存档的棋盘内容（与「切换谜题」换另一张棋盘不同）
        if self._readonly_blocked():
            return
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法重置"
            self.macro_notify_timer = 90
            return
        self._timer_cancel()
        # 按当前形态重建：只分「三角 / 其它」会让米字格被当成矩形重建
        # （Ctrl+R 之后米字格变矩形，尺寸等级还正好是初始预设），
        # 带序号重建后编号也一起丢掉——两者都是这里漏了分支。
        if getattr(self, 'triangle_mode', False):
            self.new_triangle_puzzle(self.triangle_side, self.current_step)
        elif getattr(self, 'mi_mode', False):
            self.new_mi_puzzle(self.current_m, self.current_n, self.current_step)
        elif getattr(self, 'numbered', False):
            self.new_puzzle(self.current_m, self.current_n, self.current_step,
                            numbered=True)
        else:
            self.new_puzzle(self.current_m, self.current_n, self.current_step)

    # ==================== 计时器 ====================

    def _current_kind(self) -> str:
        """当前谜题形态键（puzzle_key / 成绩分榜共用）。"""
        if getattr(self, 'triangle_mode', False):
            return 'triangle'
        if getattr(self, 'mi_mode', False):
            return 'mi'
        if getattr(self, 'numbered', False):
            return 'numbered'
        return 'square'

    def _current_puzzle_key(self) -> str:
        """当前谜题完整标识：方形 2~4*4 / 带序号 2~4*4#num / 三角 2~tri6。"""
        tri = getattr(self, 'triangle_mode', False)
        return puzzle_key(
            self.current_step, self.current_m, self.current_n,
            kind=self._current_kind(),
            triangle_side=self.game.k if tri else None)

    def _preset_puzzle_key(self, preset) -> str:
        """谜题菜单预设项对应的分榜键（与 _current_puzzle_key 同格式，用于比对当前项）。

        原先「当前是哪一档」是逐项比 m/n/step，三角形还漏比了边长；改成比键之后，
        同一预设不可能即命中方格又命中数字，新增形态也不必再写分支。
        """
        if len(preset) < 4:
            return ''
        _, pm, pn, ps = preset[:4]
        kind = preset[4] if len(preset) > 4 else 'square'
        return puzzle_key(ps, pm, pn, kind=kind,
                          triangle_side=pm if kind == 'triangle' else None)

    def _current_puzzle_label(self) -> str:
        """当前谜题的人话描述（谜题菜单底部状态行用）。"""
        if getattr(self, 'triangle_mode', False):
            k = getattr(self.game, 'k', self.current_m)
            return f'三角形 边长{k} 等级{self.current_step}'
        if getattr(self, 'mi_mode', False):
            return f'米字格 {self.current_m}×{self.current_n} 等级{self.current_step}'
        name = '数字' if getattr(self, 'numbered', False) else '矩形'
        return f'{name} {self.current_m}×{self.current_n} 等级{self.current_step}'

    def _current_puzzle_form(self) -> str:
        """当前谜题形态：'square' | 'triangle' | 'mi'。

        优先用 solver 的 `game_form`（按 game 类名判），GUI 旗标只作兜底 ——
        两者历史上各错过一次（旗标忘了清 / game 还没换），互为备份更稳。
        """
        try:
            from solver import game_form
            return game_form(self.game)
        except Exception:
            pass
        if getattr(self, 'mi_mode', False):
            return 'mi'
        if getattr(self, 'triangle_mode', False):
            return 'triangle'
        return 'square'

