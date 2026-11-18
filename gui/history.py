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
        # 三維（§54 第 5 步）：快照走无损键表 [r,c,d,gid]，与二维矩阵无关，
        # 所以有自己的执行段（滑动由 cubic_anim 在渲染层补）。
        if getattr(self, 'cubic_mode', False):
            self._cubic_undo_redo(is_undo=True)
            return
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
        if getattr(self, 'cubic_mode', False):
            self._cubic_undo_redo(is_undo=False)
            return
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

    def _cubic_start_undo_redo_anim(self, move_info, is_undo: bool):
        """三维撤销/重做的滑动插值（只动渲染，逻辑已换好局面）。

        做法与推一步的 `_cubic_start_anim` 相同：给当前局面里的这组块一个
        反向位移，再按 cubic_anim_ms ease-out 归零。
          · 撤销：局面在移动前，旧位置 = moved + delta → 偏移取 −world
          · 重做：局面在移动后，旧位置 = moved     → 偏移取 +world
        """
        import pygame
        if not getattr(self, 'animation_enabled', True):
            return
        if not move_info or not move_info.get('moved_positions'):
            return
        from engine.compat import CUBIC_DIRECTIONS
        vec = CUBIC_DIRECTIONS.get(move_info.get('direction'))
        if vec is None:
            return
        step = int(move_info.get('step', 1) or 1)
        dr, dc, dd = (int(vec[0]) * step, int(vec[1]) * step,
                      int(vec[2]) * step)
        world = (float(dc), float(dd), float(dr))
        if is_undo:
            # 当前位置是 moved；旧位置还要再 +world
            group = {(int(p[0]), int(p[1]), int(p[2]))
                     for p in move_info['moved_positions']}
            anim_delta = tuple(-v for v in world)
        else:
            # 当前位置是 moved+world；旧位置是 moved
            group = {(int(p[0]) + dr, int(p[1]) + dc, int(p[2]) + dd)
                     for p in move_info['moved_positions']}
            anim_delta = world
        ms = int(getattr(self, 'cubic_anim_ms', self.CUBIC_ANIM_MS))
        if ms <= 0:
            return
        self.cubic_anim = {
            't0': pygame.time.get_ticks(),
            'ms': ms,
            'delta': anim_delta,
            'group': frozenset(group),
        }

    def _cubic_undo_redo(self, is_undo: bool):
        """三维撤销/重做：换局面即刻生效，渲染层补滑动位移。

        与二维无动画路径同口径：清选中、步数取历史累计值、标脏、可撤/重做
        到边界时给一句明确的提示（不是静默没反应）。
        """
        if self._tut_board_locked():
            return
        self._bump_move_session()
        if is_undo:
            available = self.game_history.can_undo()
        else:
            available = self.game_history.can_redo()
        if not available:
            self.macro_notify_msg = "没有可撤销的步骤" if is_undo else "没有可重做的步骤"
            self.macro_notify_timer = 90
            return
        if is_undo:
            success, _info = self.game_history.undo(self.game)
            label = "撤销"
        else:
            success, _info = self.game_history.redo(self.game)
            label = "重做"
        if not success:
            self.macro_notify_msg = "没有可撤销的步骤" if is_undo else "没有可重做的步骤"
            self.macro_notify_timer = 90
            return
        self.selected_gap = None
        self.selected_block = None
        # 撤销/重做换的是局面，别让上一推的收尾位移挂在新局面上
        self.cubic_anim = None
        clear = getattr(self, '_cubic_clear_selection', None)
        if callable(clear):
            clear()
        # 滑动动画（用户 2026-11-18：撤销重做也要有动画） + 选中高亮
        self._cubic_start_undo_redo_anim(_info, is_undo)
        self._flash_cubic_move_selection(_info, is_undo)
        self.step_count = self.game_history.current_step_total()
        self.macro_notify_msg = label
        self.macro_notify_timer = 15
        self._mark_file_dirty()

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
        if not getattr(self, 'cubic_mode', False):
            # 三维没有「相机跟随包围盒」这套二维口径（相机与缩放是独立的）
            self.ensure_blocks_visible()
        self._mark_file_dirty()

    # ==================== 连续撤销/重做（虚拟键盘一键连续播放） ====================

    def _toggle_continuous(self, mode: str):
        """点击虚拟键盘【撤销/重做】：进入或退出连续播放。

        mode='undo'/'redo'。再次点击同按钮 = 停止；点击另一按钮 = 切换方向。
        进入时立刻播放第一步；连续播放由每步动画结束后的推进接上
        （二维 `commit_animation()` 回调，三维 `_tick_cubic_continuous()` 每帧检查）。
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

    def _cubic_continuous_active(self) -> bool:
        """当前是否处于三维的连续撤销/重做。"""
        return bool(
            getattr(self, 'cubic_mode', False)
            and (getattr(self, '_continuous_undo', False)
                 or getattr(self, '_continuous_redo', False))
        )

    def _tick_cubic_continuous(self) -> bool:
        """三维粘滞连续撤销/重做：等 `cubic_anim` 播完再推下一步。

        原版二维靠 `commit_animation()` 末尾的 `_advance_continuous_undo_redo()`
        事件驱动推进；三维撤销/重做走的是独立 `cubic_anim`（逻辑已即时提交，
        仅渲染层补位移），从不进入 `animating`/动画队列，所以那条推进链在
        三维里永远等不到。这里按帧检查 `cubic_anim` 是否到期：
          · 未到期 → 继续等（画面还在滑）
          · 已到期 → 清掉并开始下一步
          · 无动画（用户关了动画）→ 与二维无动画路径同口径，就地推到边界
        返回 True 表示本次调用消费了连续状态，调用方无需再走二维逻辑。
        """
        if not self._cubic_continuous_active():
            return False
        # 二维动画（如三维打乱演示借用的 start_animation）还在跑时先让它收尾，
        # 避免两套动画同时改局面。
        if getattr(self, 'animating', False):
            return False

        import pygame
        anim = getattr(self, 'cubic_anim', None)
        if anim:
            elapsed = pygame.time.get_ticks() - int(anim.get('t0', 0))
            if elapsed < max(1, int(anim.get('ms', 0))):
                return True
            # 本步播完，释放渲染位移后推进下一步
            self.cubic_anim = None

        animated = (getattr(self, 'animation_enabled', True)
                    and int(getattr(self, 'cubic_anim_ms', 0) or 0) > 0)
        if not animated:
            # 与二维 no-anim 路径一致：一帧内推到底（不逐步堆调用栈）。
            if self._continuous_undo:
                while self.game_history.can_undo():
                    before = self.game_history.history_index
                    self._cubic_undo_redo(is_undo=True)
                    if self.game_history.history_index == before:
                        break       # 被教程锁定等挡住：退出，别空转
                if not self.game_history.can_undo():
                    self._stop_continuous_undo_redo("已撤销到第一步")
                else:
                    self._stop_continuous_undo_redo()
            else:
                while self.game_history.can_redo():
                    before = self.game_history.history_index
                    self._cubic_undo_redo(is_undo=False)
                    if self.game_history.history_index == before:
                        break
                if not self.game_history.can_redo():
                    self._stop_continuous_undo_redo("已重做到最后一步")
                else:
                    self._stop_continuous_undo_redo()
            return True

        # 动画开启：每次只推一步，下一步由下一次 tick 在本步播完后接上。
        if self._continuous_undo:
            if not self.game_history.can_undo():
                self._stop_continuous_undo_redo("已撤销到第一步")
                return True
            before = self.game_history.history_index
            self._cubic_undo_redo(is_undo=True)
        else:
            if not self.game_history.can_redo():
                self._stop_continuous_undo_redo("已重做到最后一步")
                return True
            before = self.game_history.history_index
            self._cubic_undo_redo(is_undo=False)
        # 这一步没推动（教程锁定 / 无步可走）→ 停止，避免每帧重试。
        if self.game_history.history_index == before:
            self._stop_continuous_undo_redo()
        return True

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

