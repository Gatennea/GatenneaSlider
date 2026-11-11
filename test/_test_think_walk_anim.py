# -*- coding: utf-8 -*-
"""护栏：「思考」演示的游走 / 撤回走**真实滑动动画**（2026-11-11 修复）。

用户实测三条：
  1. 假装尝试的步骤根本没动画（_think_do_walk 直接 commit_move，无 start_animation）；
  2. 撤回卡顿（每步 GameHistory.undo 瞬时跳回，无滑动）；
  3. 防偏移与打乱行为不一致 → 抖动。

修法：走步提交后补一个**纯视觉**滑动（moved→final）；撤回先滑回再在
`commit_animation` 的 think 分支补调真实 undo。两条路都不碰 step_count /
全局历史 / 文件脏标记。

判据（行为）：
  A 组 走步：_think_do_walk 后 anim_start_pos==moved、anim_end_pos==final、
        _think_walk_anim=='walk'、animating==True；commit_animation 后清标记、
        动画态归零、step_count 不变、全局历史未被 save_snapshot。
  B 组 撤回：_think_do_rewind 后 _think_walk_anim=='rewind' 且**还没**调
        undo；commit_animation 后才 undo + 橙色 + 弹栈。
  C 组 关闭动画时退回瞬时（原行为不变）：_think_do_walk 不建动画。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gui.think_walk import ThinkWalk          # noqa: E402
from gui.auto_solve import AutoSolveMixin     # noqa: E402
from gui.animation import AnimationMixin      # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    print(('  PASS ' if cond else '  FAIL ') + name + '  ' + extra)
    if not cond:
        FAILS.append(name)


class _Blk:
    def __init__(self, r, c):
        self.location = [r, c]
        self.be_opted = False


class _FakeGame:
    def __init__(self):
        self.blocks = [_Blk(0, 0), _Blk(0, 1)]
        self.committed = []

    def opt(self, gap_type, line, blk):
        for b in self.blocks:
            b.be_opted = False
        blk.be_opted = True

    def try_move(self, direction, step):
        sel = [b for b in self.blocks if b.be_opted]
        d = {'right': (0, step), 'left': (0, -step),
             'down': (step, 0), 'up': (-step, 0)}[direction]
        return [(b.location[0] + d[0], b.location[1] + d[1]) for b in sel]

    def commit_move(self, final_positions):
        sel = [b for b in self.blocks if b.be_opted]
        for b, p in zip(sel, final_positions):
            b.location = list(p)
        self.committed.append([list(p) for p in final_positions])


class _FakeHistory:
    def __init__(self):
        self.history = [{'baseline': True}]
        self.history_index = 0
        self.saved = []
        self.undo_calls = 0
        self.restored = []

    def save_snapshot(self, game, move_info=None, session_key=None):
        self.saved.append((move_info, session_key))
        self.history.append({'move_info': move_info})
        self.history_index = len(self.history) - 1

    def undo(self, game):
        self.undo_calls += 1
        mi = self.history[self.history_index].get('move_info')
        if self.history_index > 0:
            self.history_index -= 1
        return True, mi

    def restore_snapshot(self, game, index):
        self.restored.append(index)


class _AnimHost(AutoSolveMixin, AnimationMixin):
    def __init__(self, animation_enabled=True):
        self.game = _FakeGame()
        self.current_step = 2
        self._think_walk = ThinkWalk(delay_frames=1, walk_frames=1,
                                     rewind_frames=1, max_steps=9)
        self._think_history = _FakeHistory()
        self.animation_enabled = animation_enabled
        self.animation_duration = 200
        self.animating = False
        self.anim_blocks = []
        self.anim_start_pos = []
        self.anim_end_pos = []
        self.anim_progress = 0.0
        self._anim_dr = 0.0
        self._anim_dc = 0.0
        self._anim_duration_base = None
        self._anim_true_start = None
        self._undo_redo_type = None
        self._think_walk_anim = None
        self.step_count = 0
        self.flashes = []
        self.selected_block = None
        self.global_history_calls = 0
        self.dirty_marked = 0

    def _think_find_move(self):
        for b in self.game.blocks:
            b.be_opted = False
        self.game.blocks[1].be_opted = True
        # 方形方向字母用 'd'（_move_delta 走方形表；'right' 会映射成 0 位移）
        return ('h', 0, 'd', [(0, 3)])

    def _flash_move_selection(self, mi, is_undo, after_commit=False):
        self.flashes.append((is_undo, after_commit))

    def _reset_think_history(self):
        self._think_history = _FakeHistory()

    def _mark_file_dirty(self):
        self.dirty_marked += 1

    # 若 think 分支误走普通分支，会被这条抓住（不该被调用）
    class _GH:
        def save_snapshot(self, *a, **k):
            raise AssertionError('think 动画不应写全局历史')

    game_history = _GH()


def test_walk_animates():
    h = _AnimHost(animation_enabled=True)
    ok = h._think_do_walk()
    check('A1 _think_do_walk 成功', ok)
    check('A2 走步搭了视觉滑动：start=moved / end=final',
          h.anim_start_pos == [[0, 1]] and h.anim_end_pos == [[0, 3]],
          'start=%r end=%r' % (h.anim_start_pos, h.anim_end_pos))
    check('A3 标记为 walk 动画且在播',
          h._think_walk_anim == 'walk' and h.animating is True)
    # 提交：真实 AnimationMixin.commit_animation（think 分支应只清动画态）
    h.commit_animation()
    check('A4 commit 后清标记、动画态归零',
          h._think_walk_anim is None and h.animating is False
          and not h.anim_blocks)
    check('A5 不碰 step_count / 文件脏标记',
          h.step_count == 0 and h.dirty_marked == 0,
          'step=%d dirty=%d' % (h.step_count, h.dirty_marked))
    check('A6 块落到 final', h.game.blocks[1].location == [0, 3])


def test_rewind_animates_then_undo():
    h = _AnimHost(animation_enabled=True)
    h._think_do_walk()
    h.commit_animation()                 # 走步落定，块在 (0,3)
    check('B0 走步后块在移动后位置', h.game.blocks[1].location == [0, 3])

    h._think_do_rewind()
    check('B1 撤回先滑回、还没调 undo',
          h._think_walk_anim == 'rewind' and h._think_history.undo_calls == 0,
          'anim=%r undo=%d' % (h._think_walk_anim,
                               h._think_history.undo_calls))
    check('B2 撤回滑动方向正确：start=(0,3) → end=(0,1)',
          h.anim_start_pos == [[0, 3]] and h.anim_end_pos == [[0, 1]],
          'start=%r end=%r' % (h.anim_start_pos, h.anim_end_pos))
    # 提交：应补调真实 undo + 橙色 + 弹栈
    h.commit_animation()
    check('B3 commit 后才真 undo + 橙色 + 弹栈',
          h._think_history.undo_calls == 1
          and h.flashes == [(True, True)] and not h._think_walk.steps,
          'undo=%d flashes=%r' % (h._think_history.undo_calls, h.flashes))
    check('B4 撤回动画态清零', h._think_walk_anim is None and not h.anim_blocks)


def test_animation_off_is_instant():
    h = _AnimHost(animation_enabled=False)
    h._think_do_walk()
    check('C1 关动画时走步瞬时（不建动画）',
          h._think_walk_anim is None and h.animating is False
          and h.game.blocks[1].location == [0, 3])
    h._think_do_rewind()
    check('C2 关动画时撤回瞬时（立刻 undo）',
          h._think_history.undo_calls == 1 and h._think_walk_anim is None)


def main():
    test_walk_animates()
    test_rewind_animates_then_undo()
    test_animation_off_is_instant()
    print('\nFAILS=%d %r' % (len(FAILS), FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
