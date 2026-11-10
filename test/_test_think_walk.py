# -*- coding: utf-8 -*-
"""护栏：求解器「思考」演示的渲染层游走 / 连续撤回（待办 §三十四 第 4 条）。

只测纯逻辑状态机 ``gui.think_walk.ThinkWalk``，不需要 pygame / GUI 实例：
  A 组：等待门槛、游走节奏、偏移与 history 严格一致、max_offset 整步跳过。
  B 组：段到货后按逆序连续撤回、撤回完成严格归零、没游走过就直接放行。
  C 组：reset / 关开关 / find_move 返回 None 的边界。
  D 组：接线静态判据——pump 必须驱动状态机、renderer 必须叠加渲染偏移、
        停止/收尾必须清空（防「撤修复仍恒绿」的假护栏）。

执行：D:/python/python.exe -u test/_test_think_walk.py
"""
import inspect
import os
import queue
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gui.think_walk import (ThinkWalk, IDLE, WAITING,  # noqa: E402
                            WALKING, REWINDING)

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def make():
    return ThinkWalk(delay_frames=3, walk_frames=2, rewind_frames=2,
                     max_offset=2)


def one_step():
    """一步只推一个块 (bid=7) 向右一格。"""
    return [(7, 0, 1)]


def static_tests():
    w = make()
    check('T1 初始 IDLE / 无偏移', w.state == IDLE and not w.offsets
          and not w.steps)

    calls = []

    def fm():
        calls.append(1)
        return one_step()

    w.begin()
    check('T2 begin → WAITING', w.state == WAITING)
    w.tick(fm)
    w.tick(fm)
    check('T3 等待期内不游走、不调 find_move',
          w.state == WAITING and not w.offsets and not calls)
    w.tick(fm)
    check('T4 超过 delay → WALKING', w.state == WALKING)
    w.tick(fm)
    check('T5 walk_frames 内不取步', not calls and not w.steps)
    w.tick(fm)
    check('T6 到点取一步并累积偏移',
          len(calls) == 1 and w.walked == 1
          and w.offsets.get(7) == (0, 1) and len(w.steps) == 1)
    w.tick(fm)
    w.tick(fm)
    check('T7 两步后偏移累加', w.offsets.get(7) == (0, 2))

    w.tick(fm)
    w.tick(fm)
    check('T8 max_offset 整步跳过（偏移+history 都不变）',
          w.offsets.get(7) == (0, 2) and len(w.steps) == 2)

    # B 组：撤回
    pop_order = []
    w.start_rewind()
    check('T9 start_rewind → REWINDING', w.state == REWINDING)
    guard = 0
    while w.state == REWINDING and guard < 50:
        before = len(w.steps)
        got = w.tick(None)
        if len(w.steps) < before:
            pop_order.append((before, w.offsets.get(7)))
        guard += 1
        if got == 'rewound':
            break
    check('T10 撤回逆序（每步减一格、最后清空）',
          len(pop_order) == 2 and pop_order[0][1] == (0, 1)
          and pop_order[1][1] is None, str(pop_order))
    check('T11 撤回完成严格归零 + 回 IDLE',
          w.state == IDLE and not w.offsets and not w.steps)

    w2 = make()
    w2.begin()
    check('T12 没游走过就到货 → 立即放行',
          w2.start_rewind() == 'rewound' and w2.state == IDLE)

    # C 组
    w3 = make()
    w3.begin()
    for _ in range(8):
        w3.tick(one_step)
    check('T13 有游走后 reset 清空一切',
          w3.is_active, 'pre')
    w3.reset()
    check('T14 reset 后 IDLE / 无偏移 / 无 history',
          w3.state == IDLE and not w3.offsets and not w3.steps)

    w4 = make()
    w4.begin()
    for _ in range(12):
        w4.tick(lambda: None)
    check('T15 find_move 返回 None 不产生步',
          not w4.steps and not w4.offsets)

    w5 = make()
    check('T16 IDLE 态 tick 无副作用',
          w5.tick(one_step) is None and w5.state == IDLE
          and not w5.offsets)

    w6 = ThinkWalk(delay_frames=1, walk_frames=1, rewind_frames=1,
                   max_offset=99, max_steps=3)
    w6.begin()
    for _ in range(12):
        w6.tick(one_step)
    check('T17 游走步数受 max_steps 限制（撤回不会无限久）',
          w6.walked == 3 and len(w6.steps) == 3
          and w6.offsets.get(7) == (0, 3),
          'walked=%d offsets=%r' % (w6.walked, w6.offsets))


def wiring_tests():
    """接线判据：撤掉任一接线都会转红（配合反向验证）。"""
    from gui import auto_solve as AS
    from gui import renderer as RD
    pump = inspect.getsource(AS.AutoSolveMixin._pump_auto_stages)
    check('D1 pump 驱动思考状态机',
          '_think_walk' in pump and 'start_rewind' in pump
          and '_think_find_move' in pump)
    # ⚠️ 行为判据，不用静态子串：第一版查「源码里有没有 _think_walk /
    # offsets」，反向验证把条件改成 `False and ...` 后字符串还在、判据恒绿，
    # 是假护栏。现在直接调渲染函数，看偏移有没有真的叠进 pos_map。
    class _B:
        def __init__(self, r, c):
            self.location = [r, c]

    class _G:
        def __init__(self, blocks):
            self.blocks = blocks

    class _W:
        def __init__(self, offsets):
            self.offsets = offsets

    class _FakeRender:
        animating = False
        drag_following = False

        def __init__(self):
            self.b = _B(2, 3)
            self.game = _G([self.b])
            self._think_walk = _W({id(self.b): (0, 1)})

    fake = _FakeRender()
    pos = RD.RendererMixin._frame_render_positions(fake)
    check('D2 renderer 把思考偏移叠进本帧渲染位置（行为）',
          pos.get(id(fake.b)) == (2, 4), repr(pos))
    fake._think_walk.offsets.clear()
    check('D2b 偏移清空后渲染位置回到真实坐标',
          not RD.RendererMixin._frame_render_positions(fake),
          repr(RD.RendererMixin._frame_render_positions(fake)))
    stop = inspect.getsource(AS.AutoSolveMixin._stop_auto_streamed)
    fin = inspect.getsource(AS.AutoSolveMixin._finalize_auto_streamed)
    check('D3 停止/收尾清空思考状态',
          '_think_walk.reset()' in stop and '_think_walk.reset()' in fin)
    # 真实盘面绝不许被改：状态机模块不得出现 location 赋值
    from gui import think_walk
    src = inspect.getsource(think_walk)
    check('D4 思考模块不改 block.location',
          '.location =' not in src and 'location[' not in src)


class _FakePump:
    """驱动真实 _pump_auto_stages 的最小替身（只记录播放 / 收尾）。"""

    def __init__(self):
        from gui.think_walk import ThinkWalk
        self._auto_stage_queue = queue.Queue()
        self._auto_stage_gen = 1
        self._auto_stage_active = True
        self.macro_executing = False
        self.animating = False
        self.thinking_enabled = True
        self._think_walk = ThinkWalk(delay_frames=2, walk_frames=1,
                                     rewind_frames=1, max_offset=9,
                                     max_steps=50)
        self.played = []
        self.finalized = 0

    def _think_find_move(self):
        return [(7, 0, 1)]

    def _play_auto_stage(self, item):
        self.played.append(item)

    def _finalize_auto_streamed(self):
        self.finalized += 1


def pump_behavior_tests():
    """行为判据：撤掉泵里的撤回逻辑必转红（静态判据抓不到这种绕开）。"""
    from gui.auto_solve import AutoSolveMixin
    f = _FakePump()
    pump = AutoSolveMixin._pump_auto_stages
    # 等待门槛内：不游走、不播段
    pump(f)
    check('P1 空闲等待期不抢播、不收尾',
          not f.played and f.finalized == 0
          and f._think_walk.state == WAITING)
    # 推进到产生几步游走
    for _ in range(6):
        pump(f)
    check('P2 等待期真的游走起来了',
          f._think_walk.walked >= 2 and f._think_walk.offsets,
          'walked=%d offsets=%r' % (f._think_walk.walked,
                                    f._think_walk.offsets))
    # 下一段到货
    item = {'label': 'next', 'actions': [], 'end': (), 'score': 1.0}
    f._auto_stage_queue.put((1, item))
    pump(f)
    check('P3 段到货当帧先撤回、绝不抢播',
          not f.played and f._auto_stage_queue.qsize() == 1
          and f._think_walk.state == REWINDING)
    # 继续推进直到撤回完成
    for _ in range(40):
        pump(f)
        if f.played:
            break
    check('P4 撤回完成后才播下一段',
          len(f.played) == 1 and f._auto_stage_queue.empty()
          and not f._think_walk.offsets
          and f._think_walk.state == IDLE,
          'played=%d q=%d offsets=%r'
          % (len(f.played), f._auto_stage_queue.qsize(),
             f._think_walk.offsets))

    # 关开关：不产生任何偏移
    f2 = _FakePump()
    f2.thinking_enabled = False
    for _ in range(6):
        pump(f2)
    check('P5 开关关闭时不游走、不残留偏移',
          not f2._think_walk.is_active and not f2._think_walk.offsets)


def main():
    static_tests()
    wiring_tests()
    pump_behavior_tests()
    print('==== %s（%d 项失败）' %
          ('全部通过' if not FAILS else '有失败', len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
