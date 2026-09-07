# -*- coding: utf-8 -*-
"""
动画相关 Mixin

包含：
- ease_out: 缓出插值函数
- start_animation: 启动滑块移动动画
- update_animation: 更新动画进度
- commit_animation: 动画结束提交
- cancel_animation: 取消动画
- _start_undo_redo_animation: 撤销/重做动画
- _update_slider_from_mouse: 动画速度滑动条
"""

import pygame


class AnimationMixin:
    """动画相关方法 Mixin"""

    def ease_out(self, t: float) -> float:
        """缓出插值函数"""
        return 1.0 - (1.0 - t) ** 2

    def start_animation(self, selected, target_positions):
        """启动滑块移动动画"""
        self.anim_blocks = list(selected)
        self.anim_start_pos = [list(b.location) for b in selected]
        self.anim_end_pos = [list(p) for p in target_positions]
        self.anim_progress = 0.0
        self.anim_start_time = pygame.time.get_ticks()
        self._anim_dr = self.anim_end_pos[0][0] - self.anim_start_pos[0][0]
        self._anim_dc = self.anim_end_pos[0][1] - self.anim_start_pos[0][1]
        self._undo_redo_type = None  # 普通移动动画，清除撤销/重做标记
        self.animating = True

    def update_animation(self):
        """更新动画进度，完成时提交"""
        # 选中动画计时：撤销/重做高亮到期后清除
        if getattr(self, '_sel_anim_timer', 0) > 0:
            self._sel_anim_timer -= 1
            if self._sel_anim_timer == 0:
                self._clear_sel_anim()
        if not self.animating:
            return
        elapsed = pygame.time.get_ticks() - self.anim_start_time
        self.anim_progress = min(1.0, elapsed / max(1, self.animation_duration))
        if self.anim_progress >= 1.0:
            self.commit_animation()

    def commit_animation(self):
        """动画结束，提交最终位置（根据动画类型分别处理）"""
        if not self.anim_blocks:
            return

        # 设置所有Block到最终位置
        for i, block in enumerate(self.anim_blocks):
            block.location = list(self.anim_end_pos[i])

        undo_redo_type = self._undo_redo_type

        if undo_redo_type == 'undo':
            self.game_history.undo(self.game)
            self.step_count -= 1
            self.ensure_blocks_visible()
            self._flash_move_selection(
                getattr(self, '_sel_anim_move_info', None), True, after_commit=True)
            self._maybe_show_solved_popup()
        elif undo_redo_type == 'redo':
            self.game_history.redo(self.game)
            self.step_count += 1
            self.ensure_blocks_visible()
            self._flash_move_selection(
                getattr(self, '_sel_anim_move_info', None), False, after_commit=True)
            self._maybe_show_solved_popup(via_redo=True)
        else:
            # 普通移动动画
            self.step_count += 1
            move_info = self._pending_move_info
            self.game_history.save_snapshot(self.game, move_info)
            self._pending_move_info = None
            self.ensure_blocks_visible()
            self._maybe_show_solved_popup()

        self._mark_file_dirty()

        # 清除动画状态
        self.animating = False
        self._undo_redo_type = None
        self.anim_blocks = []
        self.anim_start_pos = []
        self.anim_end_pos = []
        self.anim_progress = 0.0
        self._anim_dr = 0.0
        self._anim_dc = 0.0

        # 宏执行模式：动画结束后继续执行下一个宏步骤
        if getattr(self, 'macro_executing', False) and not getattr(self, 'macro_selecting_base', False):
            self.macro_exec_index = getattr(self, 'macro_exec_index', 0) + 1
            self._execute_next_macro_step()
            return

        # 处理队列中的下一个撤销/重做
        self._process_next_in_queue()

    def cancel_animation(self):
        """取消当前动画，恢复到动画前的位置，并清空队列"""
        if not self.anim_blocks:
            return
        for i, block in enumerate(self.anim_blocks):
            block.location = list(self.anim_start_pos[i])
        self.animating = False
        self._undo_redo_type = None
        self.anim_blocks = []
        self.anim_start_pos = []
        self.anim_end_pos = []
        self.anim_progress = 0.0
        self._pending_move_info = None
        self._anim_dr = 0.0
        self._anim_dc = 0.0
        # 取消动画时清空队列
        self._animation_queue.clear()

    def _find_blocks_at_positions(self, positions):
        """根据位置列表找到对应的滑块对象，按 positions 顺序返回"""
        pos_to_block = {}
        for block in self.game.blocks:
            pos_to_block[tuple(block.location)] = block
        result = []
        for p in positions:
            block = pos_to_block.get(tuple(p))
            if block is not None:
                result.append(block)
        return result

    def _flash_move_selection(self, move_info, is_undo, after_commit=False):
        """选中动画：撤销/重做每一步，短暂高亮该步选中的缝隙与滑块组。

        after_commit=True 表示移动已提交（滑塊已停在终点），反之表示动画播放前。
        高亮目标位置对照表：
            已提交(after_commit=True)：undo → moved；redo → moved+delta*step
            未提交(after_commit=False)：undo → moved+delta*step；redo → moved
        """
        if not getattr(self, 'selection_animation_enabled', False):
            return
        if not move_info:
            return
        self._clear_sel_anim()
        direction = move_info.get('direction', '')
        moved = move_info.get('moved_positions') or []
        gap_type = move_info.get('gap_type')
        gap_line = move_info.get('gap_line')
        step = move_info.get('step', self.current_step)
        delta = {'w': (-1, 0), 's': (1, 0),
                 'a': (0, -1), 'd': (0, 1)}.get(direction, (0, 0))
        if is_undo == after_commit:
            # 已提交的撤销 / 未提交的重做：滑块在「移动前」位置
            targets = [list(p) for p in moved]
        else:
            # 未提交的撤销 / 已提交的重做：滑块在「移动后」位置
            targets = [(r + delta[0] * step, c + delta[1] * step)
                       for r, c in moved]
        blocks = self._find_blocks_at_positions(targets)
        for b in blocks:
            b.be_opted = True
        self._sel_anim_blocks = list(blocks)
        self._sel_anim_gap = (gap_type, gap_line) if gap_type is not None else None
        self.selected_gap = self._sel_anim_gap
        # 保存元数据，供动画提交（commit_animation）后刷新高亮位置
        self._sel_anim_move_info = move_info
        self._sel_anim_is_undo = is_undo
        # 至少 0.75s；若正在滑动则盖过滑动时长，让高亮贯穿该步全程
        dur = max(45, (self.animation_duration + 300) // 17)
        self._sel_anim_timer = dur

    def _clear_sel_anim(self):
        """清除选中动画高亮（只清除自己标记过的缝隙与滑块，不打扰用户选择）。"""
        if getattr(self, '_sel_anim_gap', None) is not None \
                and self.selected_gap == self._sel_anim_gap:
            self.selected_gap = None
        for b in getattr(self, '_sel_anim_blocks', []):
            b.be_opted = False
        self._sel_anim_blocks = []
        self._sel_anim_gap = None

    def _start_undo_redo_animation(self, move_info, is_undo):
        """
        启动撤销/重做动画

        参数：
            move_info: 移动元数据
            is_undo: True=撤销(反向), False=重做(正向)
        """
        direction = move_info['direction']
        moved_positions = move_info['moved_positions']
        step = move_info.get('step', self.current_step)
        delta = {'w': (-1, 0), 's': (1, 0), 'a': (0, -1), 'd': (0, 1)}[direction]

        if is_undo:
            post_positions = [(r + delta[0] * step, c + delta[1] * step)
                             for r, c in moved_positions]
            anim_blocks = self._find_blocks_at_positions(post_positions)
            if len(anim_blocks) != len(moved_positions):
                return False
            self.anim_blocks = list(anim_blocks)
            self.anim_start_pos = [list(b.location) for b in anim_blocks]
            self.anim_end_pos = [list(p) for p in moved_positions]
            self._undo_redo_type = 'undo'
        else:
            anim_blocks = self._find_blocks_at_positions(moved_positions)
            if len(anim_blocks) != len(moved_positions):
                return False
            post_positions = [(r + delta[0] * step, c + delta[1] * step)
                             for r, c in moved_positions]
            self.anim_blocks = list(anim_blocks)
            self.anim_start_pos = [list(b.location) for b in anim_blocks]
            self.anim_end_pos = [list(p) for p in post_positions]
            self._undo_redo_type = 'redo'

        self.anim_progress = 0.0
        self.anim_start_time = pygame.time.get_ticks()
        self._anim_dr = self.anim_end_pos[0][0] - self.anim_start_pos[0][0]
        self._anim_dc = self.anim_end_pos[0][1] - self.anim_start_pos[0][1]
        self.animating = True
        return True

    def _process_next_in_queue(self):
        """处理动画队列中的下一个撤销/重做操作"""
        if not self._animation_queue:
            return
        
        next_type = self._animation_queue.pop(0)
        
        if next_type == 'undo':
            move_info = None
            if self.game_history.can_undo():
                move_info = self.game_history.history[self.game_history.history_index].get('move_info')
            if self.animation_enabled and self.animation_duration > 0 and move_info:
                if self._start_undo_redo_animation(move_info, is_undo=True):
                    self._flash_move_selection(move_info, True)
                    return
            # 无动画或找不到滑块，直接执行
            success, _ = self.game_history.undo(self.game)
            if success:
                self.step_count -= 1
                self.ensure_blocks_visible()
                self._flash_move_selection(move_info, True, after_commit=True)
                self._maybe_show_solved_popup()
        elif next_type == 'redo':
            move_info = None
            if self.game_history.can_redo():
                target_idx = self.game_history.history_index + 1
                move_info = self.game_history.history[target_idx].get('move_info')
            if self.animation_enabled and self.animation_duration > 0 and move_info:
                if self._start_undo_redo_animation(move_info, is_undo=False):
                    self._flash_move_selection(move_info, False)
                    return
            # 无动画或找不到滑块，直接执行
            success, _ = self.game_history.redo(self.game)
            if success:
                self.step_count += 1
                self.ensure_blocks_visible()
                self._flash_move_selection(move_info, False, after_commit=True)
                self._maybe_show_solved_popup(via_redo=True)
        
        # 如果直接执行了（无动画），继续处理队列
        if not self.animating and self._animation_queue:
            self._process_next_in_queue()

    def _update_slider_from_mouse(self, mouse_y):
        """根据鼠标Y坐标更新动画速度"""
        if not self.slider_rect:
            return
        track_top = self.slider_rect.top
        track_bottom = self.slider_rect.bottom
        track_height = track_bottom - track_top
        if track_height <= 0:
            return
        y = max(track_top, min(track_bottom, mouse_y))
        normalized = (y - track_top) / track_height
        new_duration = int(self.SPEED_MIN_MS + normalized * (self.SPEED_MAX_MS - self.SPEED_MIN_MS))
        if self.animating and self.animation_duration > 0:
            elapsed = pygame.time.get_ticks() - self.anim_start_time
            old_progress = elapsed / max(1, self.animation_duration)
            self.anim_start_time = pygame.time.get_ticks() - int(old_progress * new_duration)
        self.animation_duration = new_duration
