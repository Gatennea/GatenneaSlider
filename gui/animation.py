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
- 打乱演示动画（_start_shuffle_demo 一族）：打乱后逐步重放打乱过程，
  步数过多只演前几步再淡入终态（2026-10-18 新增）
"""

import pygame
from contextlib import contextmanager


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
        # 拖拽提交：把起点接到松手那刻的跟随位置（见 _apply_drag_origin）
        self._apply_drag_origin()
        self.anim_progress = 0.0
        self.anim_start_time = pygame.time.get_ticks()
        self._anim_dr = self.anim_end_pos[0][0] - self.anim_start_pos[0][0]
        self._anim_dc = self.anim_end_pos[0][1] - self.anim_start_pos[0][1]
        self._undo_redo_type = None  # 普通移动动画，清除撤销/重做标记
        self.animating = True

    def _apply_drag_origin(self):
        """拖拽提交的动画：起点改用「松手那刻的跟随位置」。

        拖拽跟随是实时预览——松手时整组已经被画到近乎落点的位置。若动画
        仍从 b.location（起点）播起，松手瞬间整组会先跳回原位、再完整滑一
        遍，玩家看到的就是「拖完了又播一次滑动动画」。

        做法：按跟随位移在总位移上的占比 s∈[0,1] 把起点前移，动画只滑剩下
        的那一段；时长按剩余比例缩短，保证整段速度不变（不会变成最后一点
        点慢慢挪）。s 会被夹紧——跟随量超过落点时（如跟了 1.4 格却只走 1
        格）起点停在落点，动画退化为一帧落位，也不会往回滑。
        """
        origin = getattr(self, '_drag_anim_origin', None)
        self._drag_anim_origin = None
        self._anim_true_start = None
        if not origin or not self.anim_start_pos:
            return
        dr0, dc0 = origin
        if abs(dr0) < 1e-9 and abs(dc0) < 1e-9:
            return
        # 真實起點另存一份：取消動畫要把塊放回這裡（anim_start_pos 已被前移）
        self._anim_true_start = [list(p) for p in self.anim_start_pos]
        s0, e0 = self.anim_start_pos[0], self.anim_end_pos[0]
        tr, tc = e0[0] - s0[0], e0[1] - s0[1]
        den = tr * tr + tc * tc
        if den < 1e-12:
            return
        s = max(0.0, min(1.0, (dr0 * tr + dc0 * tc) / den))
        for p in self.anim_start_pos:
            p[0] += s * tr
            p[1] += s * tc
        base = getattr(self, '_anim_duration_base', None)
        if base is None:
            base = self.animation_duration
            self._anim_duration_base = base
        self.animation_duration = max(60, int(base * (1.0 - s)))

    def update_animation(self):
        """更新动画进度，完成时提交"""
        # 选中动画计时：撤销/重做高亮到期后清除
        if getattr(self, '_sel_anim_timer', 0) > 0:
            self._sel_anim_timer -= 1
            if self._sel_anim_timer == 0:
                self._clear_sel_anim()
        # S1-3：越界回弹抖动倒计时
        if getattr(self, '_shake_t', 0) > 0:
            self._shake_t -= 1
            if self._shake_t == 0:
                self._shake_blocks = set()
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

        # 打乱演示的提交：只是在「重播」打乱过程——不记历史、不计步、不弹
        # 复原窗（历史已在 shuffle_puzzle 里按打乱终态重置），落位后直接
        # 推进下一条记录
        if getattr(self, '_shuffle_demo_playing', False):
            self._reset_anim_state()
            self._play_next_shuffle_record()
            return

        undo_redo_type = self._undo_redo_type

        if undo_redo_type == 'undo':
            self.game_history.undo(self.game)
            # 合并快照可能覆盖多步：步数取目标快照的累计值
            self.step_count = self.game_history.current_step_total()
            self.ensure_blocks_visible()
            self._flash_move_selection(
                getattr(self, '_sel_anim_move_info', None), True, after_commit=True)
            self._maybe_show_solved_popup(suppress=True)
        elif undo_redo_type == 'redo':
            self.game_history.redo(self.game)
            self.step_count = self.game_history.current_step_total()
            self.ensure_blocks_visible()
            self._flash_move_selection(
                getattr(self, '_sel_anim_move_info', None), False, after_commit=True)
            self._maybe_show_solved_popup(via_redo=True)
        else:
            # 普通移动动画
            self.step_count += 1
            move_info = self._pending_move_info
            self.game_history.save_snapshot(self.game, move_info,
                                            self._move_merge_key())
            self._pending_move_info = None
            self.ensure_blocks_visible()
            self._maybe_show_solved_popup()

        self._mark_file_dirty()

        # 清除动画状态
        self._reset_anim_state()

        # 宏执行模式：动画结束后继续执行下一个宏步骤
        if getattr(self, 'macro_executing', False) and not getattr(self, 'macro_selecting_base', False):
            self.macro_exec_index = getattr(self, 'macro_exec_index', 0) + 1
            self._execute_next_macro_step()
            return

        # 处理队列中的下一个撤销/重做
        self._process_next_in_queue()

        # 连续撤销/重做：一步播完后自动推进下一轮（直到边界或被打断）
        self._advance_continuous_undo_redo()

    def _restore_anim_duration(self):
        """还原被拖拽接续缩短的动画时长（见 _apply_drag_origin）。"""
        base = getattr(self, '_anim_duration_base', None)
        if base:
            self.animation_duration = base
            self._anim_duration_base = None
        self._anim_true_start = None

    def _reset_anim_state(self):
        """清空滑块动画的运行态（位置已由调用方落位，这里只清状态）。"""
        self.animating = False
        self._undo_redo_type = None
        self.anim_blocks = []
        self.anim_start_pos = []
        self.anim_end_pos = []
        self.anim_progress = 0.0
        self._anim_dr = 0.0
        self._anim_dc = 0.0
        self._restore_anim_duration()

    def cancel_animation(self):
        """取消当前动画，恢复到动画前的位置，并清空队列"""
        # 打乱演示中断（撤销/删除成绩等路径会走到这里）：先把棋盘对齐到
        # 打乱终态再清动画态——否则取消后棋盘停在演示中途，与已按终态重置
        # 的历史（第一条快照=打乱终态）不符
        if getattr(self, '_shuffle_demo_active', False):
            self._abort_shuffle_demo()
        if not self.anim_blocks:
            return
        # 真實起點優先：拖拽接續把 anim_start_pos 前移過（見 _apply_drag_origin）
        back = getattr(self, '_anim_true_start', None) or self.anim_start_pos
        for i, block in enumerate(self.anim_blocks):
            block.location = list(back[i])
        self.animating = False
        self._undo_redo_type = None
        self.anim_blocks = []
        self.anim_start_pos = []
        self.anim_end_pos = []
        self.anim_progress = 0.0
        self._pending_move_info = None
        self._anim_dr = 0.0
        self._anim_dc = 0.0
        self._anim_true_start = None
        self._restore_anim_duration()
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

    def _move_delta(self, move_info):
        """动作位移（格）→ (dr, dc)。

        合并快照的合成动作直接给 'delta'（各步位移之和，方向可能不是单向）；
        单步动作按 direction × step 换算。三角形密铺走 game_triangle.DIRECTIONS
        （六向），米字格走 game_mi.DIRECTIONS（八向，斜族的整格在表里），
        方形走四向表；位移只作用在前兩個分量，第三分量（▲/▼、縫向）沿縫平行
        滑動時不變。
        """
        delta = move_info.get('delta')
        if delta is not None:
            return delta[0], delta[1]
        step = move_info.get('step', self.current_step)
        if getattr(self, 'triangle_mode', False):
            from game_triangle import DIRECTIONS
            d = DIRECTIONS.get(move_info.get('direction'), (0, 0))
            return d[0] * step, d[1] * step
        if getattr(self, 'mi_mode', False):
            from game_mi import DIRECTIONS
            d = DIRECTIONS.get(move_info.get('direction'), (0, 0))
            return d[0] * step, d[1] * step
        d = {'w': (-1, 0), 's': (1, 0),
             'a': (0, -1), 'd': (0, 1)}.get(move_info.get('direction'), (0, 0))
        return d[0] * step, d[1] * step

    @staticmethod
    def _shift_pos(pos, delta):
        """位置 + 位移：只平移前兩個分量，其餘分量（▲/▼ 朝向）原樣保留。"""
        return (pos[0] + delta[0], pos[1] + delta[1]) + tuple(pos[2:])

    def _flash_move_selection(self, move_info, is_undo, after_commit=False):
        """选中动画：撤销/重做每一步，短暂高亮该步选中的缝隙与滑块组。

        after_commit=True 表示移动已提交（滑塊已停在终点），反之表示动画播放前。
        高亮目标位置对照表：
            已提交(after_commit=True)：undo → moved；redo → moved+delta
            未提交(after_commit=False)：undo → moved+delta；redo → moved
        """
        if not getattr(self, 'selection_animation_enabled', False):
            return
        if not move_info:
            return
        self._clear_sel_anim()
        moved = move_info.get('moved_positions') or []
        gap_type = move_info.get('gap_type')
        gap_line = move_info.get('gap_line')
        delta = self._move_delta(move_info)
        if is_undo == after_commit:
            # 已提交的撤销 / 未提交的重做：滑块在「移动前」位置
            targets = [list(p) for p in moved]
        else:
            # 未提交的撤销 / 已提交的重做：滑块在「移动后」位置
            targets = [list(self._shift_pos(p, delta)) for p in moved]
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
            move_info: 移动元数据（合并快照的合成动作含 'delta'）
            is_undo: True=撤销(反向), False=重做(正向)
        """
        moved_positions = move_info['moved_positions']
        delta = self._move_delta(move_info)

        if is_undo:
            post_positions = [self._shift_pos(p, delta) for p in moved_positions]
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
            post_positions = [self._shift_pos(p, delta) for p in moved_positions]
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
                self.step_count = self.game_history.current_step_total()
                self.ensure_blocks_visible()
                self._flash_move_selection(move_info, True, after_commit=True)
                self._maybe_show_solved_popup(suppress=True)
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
                self.step_count = self.game_history.current_step_total()
                self.ensure_blocks_visible()
                self._flash_move_selection(move_info, False, after_commit=True)
                self._maybe_show_solved_popup(via_redo=True)
        
        # 如果直接执行了（无动画），继续处理队列
        if not self.animating and self._animation_queue:
            self._process_next_in_queue()
            return
        # 队列清空后：连续撤销/重做自动推进下一轮
        self._advance_continuous_undo_redo()

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

    # ------------------------------------------------------------------
    # 打乱演示动画（2026-10-18）
    #
    # 打乱本身是纯逻辑、瞬时完成的（game.shuffle 带 record 记录每步）。
    # 演示 = 把棋盘放回打乱前状态，按记录逐步重放：与玩家滑动共用
    # start_animation / commit_animation 管道（三形态渲染插值自动生效），
    # 步数过多只演前 SHUFFLE_DEMO_STEPS 步，然后淡出（全屏蒙层）、在
    # 全遮住的瞬间把棋盘切成打乱终态、再淡入——玩家看到的就是
    # 「演示几步 → 转场 → 打乱结果」。
    #
    # 历史语义不变：shuffle_puzzle 在演示开始前就已 step_count=0 +
    # reset + save_snapshot(终态)，演示的提交一律不碰历史。
    # ------------------------------------------------------------------

    # 最多演示几步（默认 300ms/步 ≈ 3.6s，正好是「几步」+「几秒」的量级）
    SHUFFLE_DEMO_STEPS = 12
    # 淡出 / 淡入各自的时长（毫秒）；两段合计 ~0.7s
    SHUFFLE_FADE_MS = 350

    def _start_shuffle_demo(self, records, pre_positions, final_positions, notify):
        """启动打乱演示。

        参数：
            records       : game.shuffle(record=...) 的记录列表（执行顺序）
            pre_positions : 打乱前各块位置（与 game.blocks 同序）——演示起点
            final_positions: 打乱终态各块位置（同序）——截断时淡入的目标
            notify        : 演示结束后补发的通知 (msg, timer)， None 则不补发
        """
        # 放回打乱前状态（records[0] 的 moved 正是从该状态出发的）
        for b, p in zip(self.game.blocks, pre_positions):
            b.location = list(p)
        self._clear_selection_all()
        self._shuffle_demo_game = self.game  # 身份锚：换盘（新局/载入/回放）
        #                                    → 演示视为失效，只清状态不写盘
        self._shuffle_demo_final = [list(p) for p in final_positions]
        self._shuffle_demo_notify = notify
        self._shuffle_demo_need_fade = len(records) > self.SHUFFLE_DEMO_STEPS
        self._shuffle_demo_queue = list(records[:self.SHUFFLE_DEMO_STEPS])
        self._shuffle_demo_active = True
        self._shuffle_demo_phase = 'play'
        self._shuffle_fade_alpha = 0.0
        # 视图按当前（打乱前）盘面适配；截断演示在切终态时会再适配一次
        self._fit_board_view()
        self._play_next_shuffle_record()

    def _shuffle_demo_stale(self) -> bool:
        """演示所绑定的棋盘是否已被整体替换（新局/载入/成绩回放）。

        所有换盘路径都是 `self.game = create_puzzle(...)`（换对象），
        因此对象身份一变，演示里记的位置/块就全部作废——必须只清状态，
        绝不能往新棋盘上写旧位置。
        """
        return getattr(self, '_shuffle_demo_game', None) is not self.game

    def _play_next_shuffle_record(self):
        """播放下一条打乱记录；队列空则进入淡出（截断时）或直接收尾。"""
        self._shuffle_demo_playing = False
        if self._shuffle_demo_stale():
            self._clear_demo_state()
            return
        while self._shuffle_demo_queue:
            rec = self._shuffle_demo_queue.pop(0)
            blocks = self._find_blocks_at_positions(rec['moved'])
            if len(blocks) != len(rec['moved']):
                continue  # 位置对不上（理论不发生）：跳过该步，演示继续
            self.start_animation(blocks, rec['final'])
            self._shuffle_demo_playing = True
            return
        # 全部演完：记录被截断 → 淡出切入终态；否则盘面已在终态、直接收尾
        if getattr(self, '_shuffle_demo_need_fade', False):
            self._shuffle_demo_phase = 'fade_out'
            self._shuffle_fade_alpha = 0.0
            self._shuffle_fade_last_ms = pygame.time.get_ticks()
            # 淡入淡出期间保持 animating：既有输入守卫（键盘/拖拽/求解）
            # 全部自动生效，转场中途不会被打断
            self.animating = True
        else:
            self._finish_shuffle_demo()

    def _update_shuffle_demo(self):
        """每帧推进打乱演示的淡出/淡入（记录播放由动画系统驱动）。"""
        if not getattr(self, '_shuffle_demo_active', False):
            return
        if self._shuffle_demo_stale():
            self._clear_demo_state()
            return
        phase = self._shuffle_demo_phase
        if phase == 'play':
            return
        now = pygame.time.get_ticks()
        dt = now - getattr(self, '_shuffle_fade_last_ms', now)
        self._shuffle_fade_last_ms = now
        step = 255.0 * dt / max(1, self.SHUFFLE_FADE_MS)
        if phase == 'fade_out':
            self._shuffle_fade_alpha = min(255.0, self._shuffle_fade_alpha + step)
            if self._shuffle_fade_alpha >= 255.0:
                # 全遮住：换盘到打乱终态（视图适配也在这刻做，藏在蒙层后面）
                for b, p in zip(self.game.blocks, getattr(self, '_shuffle_demo_final', [])):
                    b.location = list(p)
                self._fit_board_view()
                self._shuffle_demo_phase = 'fade_in'
        elif phase == 'fade_in':
            self._shuffle_fade_alpha = max(0.0, self._shuffle_fade_alpha - step)
            if self._shuffle_fade_alpha <= 0.0:
                self._finish_shuffle_demo()

    def _finish_shuffle_demo(self):
        """演示正常结束：清状态、对齐终态、补发通知。"""
        if self._shuffle_demo_stale():
            self._clear_demo_state()
            return
        for b, p in zip(self.game.blocks, getattr(self, '_shuffle_demo_final', [])):
            b.location = list(p)
        notify = self._shuffle_demo_notify
        self._clear_demo_state()
        if notify:
            self.macro_notify_msg, self.macro_notify_timer = notify
        self.ensure_blocks_visible()

    def _abort_shuffle_demo(self):
        """演示被外力打断（再次打乱/撤销/删成绩）：棋盘直接对齐终态。

        棋盘已被整体替换时（换锚失效）只清状态——此刻 self.game.blocks
        是新棋盘的块，写旧位置会把新局搞乱。
        """
        if not getattr(self, '_shuffle_demo_active', False):
            return
        if not self._shuffle_demo_stale():
            for b, p in zip(self.game.blocks, getattr(self, '_shuffle_demo_final', [])):
                b.location = list(p)
            # 连正在播的那条记录的动画态一起清掉（否则 cancel_animation 的
            # 常规路径会把块拖回动画起点，抵掉这次终态对齐）
            self._reset_anim_state()
        self._clear_demo_state()

    def _clear_demo_state(self):
        """清空打乱演示的全部状态（不动棋盘）。"""
        self._shuffle_demo_active = False
        self._shuffle_demo_playing = False
        self._shuffle_demo_queue = []
        self._shuffle_demo_need_fade = False
        self._shuffle_demo_phase = None
        self._shuffle_fade_alpha = 0.0
        self._shuffle_demo_notify = None
        self._shuffle_demo_game = None

    @contextmanager
    def _demo_logic_positions(self):
        """打乱演示播放期间：让「盘面查询」看到打乱终态而非视觉上的打乱前状态。

        演示把 game.blocks 临时放回打乱前状态逐步重放（_start_shuffle_demo），
        但逻辑语义——判胜 / HTTP /status 的 matrix 与 blocks / 求解器状态——
        必须回答终态，否则会出现「打乱后仍判胜」「status 还是旧盘面」。
        整盘被替换（reset / 新局 / 载入）后锚失效，不再修正（直接看新盘面）。

        嵌套安全：内层透传不重复交换；matrix 缓存进出还原，外部无感。
        """
        active = (getattr(self, '_shuffle_demo_active', False)
                  and getattr(self, '_shuffle_demo_game', None) is self.game
                  and getattr(self, '_shuffle_demo_depth', 0) == 0)
        if not active:
            yield
            return
        self._shuffle_demo_depth = 1
        blocks = self.game.blocks
        saved_pos = [list(b.location) for b in blocks]
        saved_matrix = self.game.matrix
        try:
            for b, p in zip(blocks, self._shuffle_demo_final):
                b.location = list(p)
            yield
        finally:
            for b, p in zip(blocks, saved_pos):
                b.location = list(p)
            self.game.matrix = saved_matrix
            self._shuffle_demo_depth = 0

    def _clear_selection_all(self):
        """清掉所有块的选中高亮与当前选中项（演示起止用）。"""
        for b in self.game.blocks:
            b.be_opted = False
        self.selected_gap = None
        self.selected_block = None
