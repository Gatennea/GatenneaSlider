# -*- coding: utf-8 -*-
"""历史操作混入：撤销 / 重做 / 跳步 / 连续播放。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第二步）。
连续播放两档推进：动画开=每步事件驱动弹栈；动画关=就地 while 推到底——
旧实现靠 undo() 与本函数互相递归，长局会撞 Python 递归上限（事故记录见
_advance_continuous_undo_redo 的 docstring）。相关状态旗标
（_continuous_undo/_redo、_advancing_continuous、_animation_queue、_undo_redo_type）
的初始化仍在原处（GUI/Animation 各管各的），本 mixin 只搬方法。
"""


class HistoryMixin:
    """撤销/重做/连续播放（原 GUI.py 内联代码，整体搬迁）。"""

    def undo(self):
        """撤销操作（Ctrl+Z）"""
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 手动撤销会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 撤销会改变选中 → 结束当前选中会话（后续移动另起快照）
        self._bump_move_session()
        # 标注录制中：不允许撤到起点之前（起点前的历史不属于本次示范）
        if self._ann_undo_blocked():
            return
        # 如果正在播放撤销/重做动画，入队等待
        if self.animating and self._undo_redo_type is not None:
            self._animation_queue.append('undo')
            return

        # 如果正在播放普通移动动画，取消后执行撤销
        if self.animating:
            self.cancel_animation()

        # 获取将被撤销那一步的移动元数据（合并段会先惰性展开成单步）
        move_info = self.game_history.peek_undo() if self.game_history.can_undo() else None

        if self.animation_enabled and self.animation_duration > 0 and move_info:
            # 有动画的撤销
            if self._start_undo_redo_animation(move_info, is_undo=True):
                self.selected_gap = None
                self.selected_block = None
                self._flash_move_selection(move_info, True)
                self.macro_notify_msg = "撤销"
                self.macro_notify_timer = 15
                return

        # 无动画的撤销（直接执行）
        if self._undo_step_now(move_info):
            # 连续撤销（无动画路径）：继续下一轮直到边界
            self._advance_continuous_undo_redo()

    def _undo_step_now(self, move_info):
        """无动画单步撤销（undo 的执行段 / 连续撤销的循环体）。返回是否成功。"""
        success, _ = self.game_history.undo(self.game)
        if success:
            self.selected_gap = None
            self.selected_block = None
            # 合并快照可能覆盖多步：步数直接取目标快照的累计值
            self.step_count = self.game_history.current_step_total()
            self.ensure_blocks_visible()
            self._flash_move_selection(move_info, True, after_commit=True)
            self.macro_notify_msg = "撤销"
            self.macro_notify_timer = 15
            self._maybe_show_solved_popup(suppress=True)
            self._mark_file_dirty()
        return success

    def redo(self):
        """重做操作（Ctrl+X）"""
        # 教程解法播放中：锁定棋盘操作（回放自身的连续重做除外）
        if self._tut_board_locked() and not self._continuous_redo:
            return
        # 手动重做会使已排队的梯度阶段失效 → 终止流水线
        self._stop_gradient_pipeline()
        # 重做会改变选中 → 结束当前选中会话（后续移动另起快照）
        self._bump_move_session()
        # 如果正在播放撤销/重做动画，入队等待
        if self.animating and self._undo_redo_type is not None:
            self._animation_queue.append('redo')
            return

        # 如果正在播放普通移动动画，取消后执行重做
        if self.animating:
            self.cancel_animation()

        # 获取将被重做那一步的移动元数据（目标段会先惰性展开成单步）
        move_info = self.game_history.peek_redo() if self.game_history.can_redo() else None

        if self.animation_enabled and self.animation_duration > 0 and move_info:
            # 有动画的重做
            if self._start_undo_redo_animation(move_info, is_undo=False):
                self.selected_gap = None
                self.selected_block = None
                self._flash_move_selection(move_info, False)
                self.macro_notify_msg = "重做"
                self.macro_notify_timer = 15
                return

        # 无动画的重做（直接执行）
        if self._redo_step_now(move_info):
            # 连续重做（无动画路径）：继续下一轮直到边界
            self._advance_continuous_undo_redo()

    def _redo_step_now(self, move_info):
        """无动画单步重做（redo 的执行段 / 连续重做的循环体）。返回是否成功。"""
        success, _ = self.game_history.redo(self.game)
        if success:
            self.selected_gap = None
            self.selected_block = None
            self.step_count = self.game_history.current_step_total()
            self.ensure_blocks_visible()
            self._flash_move_selection(move_info, False, after_commit=True)
            self.macro_notify_msg = "重做"
            self.macro_notify_timer = 15
            self._maybe_show_solved_popup(via_redo=True)
            self._mark_file_dirty()
        return success

    def jump_to_history_index(self, idx: int):
        """直接跳到历史记录第 idx 步的状态（虚拟键盘“跳到某步”）"""
        # 教程解法播放中：锁定棋盘操作
        if self._tut_board_locked():
            return
        # 手动跳步 = 打断连续撤销/重做
        self._stop_continuous_undo_redo()
        # 跳步会改变选中 → 结束当前选中会话（后续移动另起快照）
        self._bump_move_session()
        # 标注录制中跳转会破坏标注基准 → 阻止
        if getattr(self, '_ann_recording', False):
            self.macro_notify_msg = "标注录制中不可跳转步骤"
            self.macro_notify_timer = 90
            return
        n = len(self.game_history.history)
        if n == 0:
            return
        idx = max(0, min(idx, n - 1))
        # 终止进行中的动画
        if self.animating:
            self.cancel_animation()
        # 清空选择等临时状态
        self.selected_gap = None
        self.selected_block = None
        self.game_history.history_index = idx
        self.game_history.restore_snapshot(self.game, idx)
        # 合并快照可能覆盖多步：步数取该快照的累计值
        self.step_count = self.game_history.step_total_at(idx)
        self.ensure_blocks_visible()
        self._mark_file_dirty()

    # ==================== 连续撤销/重做（虚拟键盘一键连续播放） ====================

    def _toggle_continuous(self, mode: str):
        """点击虚拟键盘【撤销/重做】：进入或退出连续播放。

        mode='undo'/'redo'。再次点击同按钮 = 停止；点击另一按钮 = 切换方向。
        进入时立刻播放第一步；连续播放由每次动画提交后自动推进（见 _advance_continuous_undo_redo）。
        """
        if mode == 'undo':
            # 切换到撤销方向
            if self._continuous_redo:
                self._continuous_redo = False
            if self._continuous_undo:
                self._stop_continuous_undo_redo("已停止连续撤销")
                return
            self._continuous_undo = True
            self._finalize_continuous_enter('undo', "连续撤销（按空格停止）")
        else:  # redo
            if self._continuous_undo:
                self._continuous_undo = False
            if self._continuous_redo:
                self._stop_continuous_undo_redo("已停止连续重做")
                return
            self._continuous_redo = True
            self._finalize_continuous_enter('redo', "连续重做（按空格停止）")

    def _finalize_continuous_enter(self, mode, notify):
        """连续播放：清掉先前残留队列后开始第一步。"""
        # 清理可能残留的同向队列项（切换方向/重进时确保干净）
        self._animation_queue = [q for q in self._animation_queue
                                 if q != ('undo' if mode == 'undo' else 'redo')]
        self._macro_notify(notify)
        if mode == 'undo':
            self.undo()
        else:
            self.redo()

    def _advance_continuous_undo_redo(self):
        """连续播放推进：在每次撤销/重做提交后，若仍在连续模式且可继续，则播放下一步；
        到达边界（无路可退/进）则停止并提示。手动打断时由 _stop_continuous_undo_redo 处理。

        推进方式分两路：
        - 动画开启：每步由动画提交回调再次进入本函数 → self.undo()/redo() 播下一步
          （事件驱动，调用栈每步弹回，无深递归）。
        - 动画关闭（含重入兜底）：就地 while 循环推到底。旧实现靠
          undo() → 本函数 → undo() 互相递归逐步推进，长局会撞 Python
          递归上限（实测 2450 步的局约 495 步即崩）；异常被主循环事件
          大 try 吞掉后 restore_snapshot 半途而废 → 滑块残缺、步数卡半途。
        """
        animated = self.animation_enabled and self.animation_duration > 0
        if getattr(self, '_advancing_continuous', False):
            animated = False  # 重入（动画模式下遇到无动画步）：就地循环，不再叠栈
        if self._continuous_undo:
            if not self.game_history.can_undo():
                self._stop_continuous_undo_redo("已撤销到第一步")
            elif animated:
                self._advancing_continuous = True
                try:
                    self.undo()
                finally:
                    self._advancing_continuous = False
            else:
                while self.game_history.can_undo() and self._undo_step_now(
                        self.game_history.peek_undo()):
                    pass
                if not self.game_history.can_undo():
                    self._stop_continuous_undo_redo("已撤销到第一步")
        elif self._continuous_redo:
            if not self.game_history.can_redo():
                self._stop_continuous_undo_redo("已重做到最后一步")
            elif animated:
                self._advancing_continuous = True
                try:
                    self.redo()
                finally:
                    self._advancing_continuous = False
            else:
                while self.game_history.can_redo() and self._redo_step_now(
                        self.game_history.peek_redo()):
                    pass
                if not self.game_history.can_redo():
                    self._stop_continuous_undo_redo("已重做到最后一步")

    def _stop_continuous_undo_redo(self, notify=''):
        """停止连续撤销/重做；清除状态旗标与残留队列。notify 非空时右下角提示。"""
        was = self._continuous_undo or self._continuous_redo
        self._continuous_undo = False
        self._continuous_redo = False
        self._animation_queue.clear()
        if notify:
            self._macro_notify(notify)
        return was

