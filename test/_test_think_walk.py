# -*- coding: utf-8 -*-
"""护栏：求解器「思考」演示 = 真实游走 + 真实撤销（待办 §三十四 第 4 条）。

⚠️ 2026-11-11 重写。旧实现让状态机维护一份**渲染层偏移**（offsets）并在
renderer 里叠进 pos_map，与真实盘面 / 历史脱钩：偏移一旦在「下一段动画已
开始、撤回还没清完」时叠到插值位置上，就把整片移动块推偏 = 棋盘撕裂、块
飞出网格（用户实测的渲染崩坏）。新模型：

  * 状态机只记 steps、tick() 返回动作（'walk' / 'rewind' / 'rewound'）；
  * 游走 / 撤回由 pump 走**真实接口**：commit_move 落盘 + 本地 GameHistory
    的 save_snapshot / undo（与玩家 Ctrl+Z 同一个 undo，同样出橙色高亮）；
  * 渲染层**不再叠加任何偏移**，只画 b.location。

测试分组：
  A 组 纯状态机（不需要 pygame）：节奏 / 步数上限 / 撤回顺序 / 归零。
  B 组 接线行为判据：渲染层无偏移（行为）、pump 走真实走/撤、commit_move
      真提交、undo 真被调用、取消时盘面被还原回基线。
  C 组 模块自律：think_walk 不得改 block.location。
"""
import inspect
import os
import queue
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gui.think_walk import (ThinkWalk, IDLE, WAITING,  # noqa: E402
                            WALKING, REWINDING)
from gui.auto_solve import AutoSolveMixin  # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def make():
    return ThinkWalk(delay_frames=3, walk_frames=2, rewind_frames=2,
                     max_steps=2)


def run_until(w, want, limit=200):
    """连续 tick 直到返回 want，返回 (动作序列, 是否命中)。"""
    acts = []
    for _ in range(limit):
        a = w.tick()
        acts.append(a)
        if a == want:
            return acts, True
    return acts, False


# ---------------------------------------------------------------- A 组
def state_machine_tests():
    w = make()
    check('A1 初始 IDLE / 无步', w.state == IDLE and not w.steps)

    w.begin()
    check('A2 begin → WAITING', w.state == WAITING)

    outs = [w.tick() for _ in range(3)]
    check('A3 等待期内不游走（3 帧全是 None）',
          w.state == WALKING and outs[:2] == [None, None], repr(outs))

    # WALKING 且 walk_frames=2：第一帧等、第二帧给动作
    a1 = w.tick()
    a2 = w.tick()
    check('A4 walk_frames 门：先等一帧再给 walk',
          a1 is None and a2 == 'walk', 'a1=%r a2=%r' % (a1, a2))

    w.note_walk({'gap_type': 'h', 'gap_line': 0, 'direction': 'right',
                 'step': 2, 'moved_positions': [[0, 0]]})
    check('A5 note_walk 记为一步', len(w.steps) == 1 and w.walked == 1)

    w.tick()
    check('A6 第二步按节奏再来', w.tick() == 'walk')
    w.note_walk({'gap_type': 'v', 'gap_line': 1, 'direction': 'up',
                 'step': 2, 'moved_positions': [[1, 1]]})
    check('A7 两步在册', len(w.steps) == 2 and w.walked == 2)

    # max_steps=2 已满：不再往前走，转为**自查撤回**（不是旧版的静止干等）
    acts = [w.tick() for _ in range(10)]
    check('A8 max_steps 封顶后不再游走、转自查撤回',
          'walk' not in acts and w.state == REWINDING, repr(acts))

    # ---- 撤回
    w.start_rewind()
    check('A9 start_rewind → REWINDING', w.state == REWINDING)

    order = []
    for _ in range(2):
        acts, hit = run_until(w, 'rewind')
        if hit:
            order.append(w.steps[-1]['gap_type'])
            w.note_rewind()
    check('A10 逐步撤回且逆序（后走的先撤）',
          order == ['v', 'h'], repr(order))

    got = None
    for _ in range(10):
        got = w.tick()
        if got == 'rewound':
            break
    check('A11 撤完给 rewound + 回 IDLE + 无残留',
          got == 'rewound' and w.state == IDLE and not w.steps)

    w2 = make()
    w2.begin()
    check('A12 没游走过就到货 → 立即放行',
          w2.start_rewind() == 'rewound' and w2.state == IDLE)

    w3 = make()
    w3.note_rewind()          # 空栈弹栈不许炸
    check('A13 空栈 note_rewind 安全', not w3.steps)

    w4 = make()
    w4.begin()
    for _ in range(6):
        if w4.tick() == 'walk':
            w4.note_walk({'gap_type': 'h', 'gap_line': 0})
    w4.reset()
    check('A14 reset 清空步数与态',
          w4.state == IDLE and not w4.steps)

    w5 = make()
    check('A15 IDLE 态 tick 无动作', w5.tick() is None and w5.state == IDLE)

    # ---- 自查循环（用户 2026-11-13：多撤回多重做，别走满就停住干等）
    w6 = ThinkWalk(delay_frames=1, walk_frames=1, rewind_frames=1,
                   max_steps=3, self_loop=True)
    w6.begin()
    walks = rewinds = rewound_returns = 0
    for _ in range(120):
        a = w6.tick()
        if a == 'walk':
            walks += 1
            w6.note_walk({'gap_type': 'h', 'gap_line': 0})
        elif a == 'rewind':
            rewinds += 1
            w6.note_rewind()
        elif a == 'rewound':
            rewound_returns += 1
    check('A16 自查循环：走满额度自己撤回，撤完再开一轮（不停住/不交权）',
          walks > 3 and rewinds > 0 and rewound_returns == 0 and w6.is_active,
          'walks=%d rewinds=%d rewound=%d state=%s'
          % (walks, rewinds, rewound_returns, w6.state))

    # 段到货必须能打断自查循环：撤完返回 rewound 交还控制权
    w7 = ThinkWalk(delay_frames=1, walk_frames=1, rewind_frames=1,
                   max_steps=2, self_loop=True)
    w7.begin()
    for _ in range(40):
        a = w7.tick()
        if a == 'walk':
            w7.note_walk({'gap_type': 'h', 'gap_line': 0})
        elif a == 'rewind':
            w7.note_rewind()
    w7.start_rewind()
    got = None
    for _ in range(60):
        a = w7.tick()
        if a == 'rewind':
            w7.note_rewind()
        elif a == 'rewound':
            got = 'rewound'
            break
    check('A17 段到货打断自查循环：撤完给 rewound（不无限试推）',
          got == 'rewound' and w7.state == IDLE and not w7.steps,
          'got=%r state=%s steps=%d' % (got, w7.state, len(w7.steps)))

    # 默认节奏：要快（旧 45/14/7 每步半秒多）、一轮额度也不能只有两三步
    d = ThinkWalk()
    check('A18 默认节奏足够快（delay≤20、walk≤6、rewind≤4）',
          d.delay_frames <= 20 and d.walk_frames <= 6 and d.rewind_frames <= 4,
          'delay=%d walk=%d rewind=%d'
          % (d.delay_frames, d.walk_frames, d.rewind_frames))
    check('A19 默认一轮能试多步', d.max_steps >= 6, 'max=%d' % d.max_steps)


# ---------------------------------------------------------------- B 组
class _Blk:
    def __init__(self, r, c):
        self.location = [r, c]
        self.be_opted = False


class _FakeGame:
    """只实现思考演示用到的那几个真接口。"""

    def __init__(self):
        self.blocks = [_Blk(0, 0), _Blk(0, 1)]
        self.committed = []
        self.opted = 0

    def opt(self, gap_type, line, blk):
        self.opted += 1
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
        self.saved = []
        self.undo_calls = 0
        self.restored = []
        self.next_undo = (True, {'gap_type': 'h', 'gap_line': 0,
                                 'direction': 'right', 'step': 2,
                                 'moved_positions': [[0, 0]]})

    def save_snapshot(self, game, move_info=None, session_key=None):
        self.saved.append((move_info, session_key))
        self.history.append({'move_info': move_info})

    def undo(self, game):
        self.undo_calls += 1
        return self.next_undo

    def restore_snapshot(self, game, index):
        self.restored.append(index)


def rendered_positions(fake_self):
    """直接调真实渲染函数，看本帧渲染位置（行为判据，不查源码子串）。"""
    from gui import renderer as RD
    return RD.RendererMixin._frame_render_positions(fake_self)


class _FakeRender:
    animating = False
    drag_following = False

    def __init__(self):
        self.b = _Blk(2, 3)
        self.game = type('G', (), {'blocks': [self.b]})()
        # 旧实现遗留物：即使有人把 offsets 塞回来，渲染层也不许再叠
        self._think_walk = type('W', (), {'offsets': {id(self.b): (0, 1)}})()


class _PumpFake(AutoSolveMixin):
    """驱动真实 _pump_auto_stages 的替身（继承 mixin，收尾跑真实实现）。

    只把「走 / 撤 / 清历史 / 播段 / 收尾通知」换成旁路，其余（含
    ``_think_begin_wander``、``_think_abort_and_restore``）都跑真实代码。
    """

    def __init__(self):
        self._auto_stage_queue = queue.Queue()
        self._auto_stage_gen = 1
        self._auto_stage_active = True
        self.macro_executing = False
        self.animating = False
        self.thinking_enabled = True
        self.current_step = 2
        self._think_walk = ThinkWalk(delay_frames=2, walk_frames=1,
                                     rewind_frames=1, max_steps=50)
        self.game = _FakeGame()
        self._think_history = _FakeHistory()
        self.played = []
        self.finalized = 0
        self.walks = 0
        self.rewinds = 0
        self.resets = 0

    # —— 只覆盖「走 / 撤 / 清历史 / 播段」四个旁路，其余跑真实实现 ——
    def _think_do_walk(self):
        self.walks += 1
        self._think_walk.note_walk({'gap_type': 'h', 'gap_line': 0,
                                    'direction': 'right', 'step': 2,
                                    'moved_positions': [[0, 0]]})
        return True

    def _think_do_rewind(self):
        self.rewinds += 1
        self._think_walk.note_rewind()

    def _reset_think_history(self):
        self.resets += 1
        old = getattr(self, '_think_history', None)
        hist = _FakeHistory()
        if old is not None:
            # 保留还原痕迹，供「收尾真的把盘面还原了」这条断言用
            hist.restored = old.restored
            hist.undo_calls = old.undo_calls
        self._think_history = hist

    def _play_auto_stage(self, item):
        self.played.append(item)

    def _finalize_auto_streamed(self):
        self.finalized += 1


def wiring_tests():
    # W1 渲染层不再叠加任何游走偏移（行为判据）
    fake = _FakeRender()
    pos = rendered_positions(fake)
    check('W1 渲染层不叠游走偏移（offsets 在也不偏）',
          pos.get(id(fake.b)) in (None, (2, 3)), repr(pos))

    # W2 pump 走真实「走步 / 撤销」路线
    from gui.auto_solve import AutoSolveMixin
    pump = AutoSolveMixin._pump_auto_stages

    f = _PumpFake()
    pump(f)
    check('W2 等待门槛内不抢播', not f.played and f.walks == 0
          and f._think_walk.state == WAITING)

    for _ in range(8):
        pump(f)
    check('W3 等待期真的游走起来了（走真实 _think_do_walk）',
          f.walks >= 2 and len(f._think_walk.steps) == f.walks,
          'walks=%d steps=%d' % (f.walks, len(f._think_walk.steps)))

    item = {'label': 'next', 'actions': [], 'end': (), 'score': 1.0}
    f._auto_stage_queue.put((1, item))
    pump(f)
    check('W4 段到货当帧先撤、绝不抢播',
          not f.played and f._auto_stage_queue.qsize() == 1
          and f._think_walk.state == REWINDING)

    for _ in range(60):
        pump(f)
        if f.played:
            break
    check('W5 撤完（真实 _think_do_rewind）才播下一段',
          len(f.played) == 1 and f.rewinds == f.walks
          and not f._think_walk.steps,
          'played=%d rewinds=%d walks=%d' % (len(f.played), f.rewinds, f.walks))

    # W6 关开关：不清位移就走人 = bug，必须走还原收尾
    f2 = _PumpFake()
    f2.thinking_enabled = False
    f2._think_walk.begin()
    for _ in range(3):
        f2._think_walk.tick()
    f2._think_walk.note_walk({'gap_type': 'h', 'gap_line': 0})
    f2._think_history.saved.append(({'gap_type': 'h'}, None))
    pump(f2)
    check('W6 关开关时盘面被还原回基线（走 restore 收尾）',
          f2._think_history.restored == [0] and not f2._think_walk.is_active,
          'restored=%r active=%r' % (f2._think_history.restored,
                                     f2._think_walk.is_active))

    # W12 走满单轮额度：pump 必须把状态机给的 'rewind' 真正执行掉。
    #    旧 pump 的等待分支只认 'walk'，自查撤回会被无声丢弃 → 盘面停在
    #    推歪态干等下一段（用户看到的「试几步就不动了」）。
    f3 = _PumpFake()
    f3._think_walk = ThinkWalk(delay_frames=1, walk_frames=1,
                               rewind_frames=1, max_steps=3, self_loop=True)
    for _ in range(200):
        pump(f3)
    check('W12 走满额度后 pump 真的执行自查撤回（多撤回多重做接通）',
          f3.walks > 3 and f3.rewinds > 0,
          'walks=%d rewinds=%d state=%s'
          % (f3.walks, f3.rewinds, f3._think_walk.state))


def engine_route_tests():
    """真实 _think_do_walk / _think_do_rewind / _think_abort_and_restore。"""
    from gui.auto_solve import AutoSolveMixin

    class _Host(AutoSolveMixin):
        SLIDE_INSTANT_MS = 120   # 与 AnimationMixin 同值（本 Host 不混入它）

        def __init__(self):
            self.game = _FakeGame()
            self.current_step = 2
            self._think_walk = ThinkWalk(delay_frames=1, walk_frames=1,
                                         rewind_frames=1, max_steps=9)
            self._think_history = _FakeHistory()
            self.flashes = []
            self.slide_sounds = []
            self.selected_block = None

        def _play_slide_sound(self, steps=1, duration_ms=None):
            """记录滑动声调用（真实 AnimationMixin 会去 audio 播，本 Host 无音频）。"""
            self.slide_sounds.append((steps, duration_ms))

        def _reset_think_history(self):
            old = self._think_history
            hist = _FakeHistory()
            hist.restored = old.restored
            hist.undo_calls = old.undo_calls
            self._think_history = hist

        def _think_find_move(self):
            for b in self.game.blocks:
                b.be_opted = False
            self.game.blocks[1].be_opted = True
            return ('h', 0, 'right', [(0, 3)])

        def _flash_move_selection(self, mi, is_undo, after_commit=False,
                                  is_think=False):
            self.flashes.append((is_undo, after_commit, bool(is_think)))

    h = _Host()
    saved_before = len(h._think_history.saved)
    ok = h._think_do_walk()
    check('W7 游走走真引擎：commit_move 真提交 + 落本地历史',
          ok and h.game.committed and h.game.blocks[1].location == [0, 3]
          and len(h._think_history.saved) == saved_before + 1
          and len(h._think_walk.steps) == 1,
          'committed=%r saved=%d' % (h.game.committed,
                                     len(h._think_history.saved)))
    check('W7b 游走步有滑动声（修复「思考游走无声」）',
          len(h.slide_sounds) == 1 and h.slide_sounds[0][0] == 2,
          h.slide_sounds)
    check('W7c 游走步数进左下角显示计数（真实的 step_count 不动）',
          getattr(h, '_think_display_steps', None) == 1
          and getattr(h, 'step_count', 0) == 0,
          'display=%r step_count=%r' % (getattr(h, '_think_display_steps', None),
                                        getattr(h, 'step_count', 0)))

    mi = h._think_history.saved[-1][0]
    check('W8 落盘 move_info 是真的走法规约',
          mi.get('gap_type') == 'h' and mi.get('direction') == 'right'
          and mi.get('moved_positions') == [[0, 1]], repr(mi))

    h._think_do_rewind()
    check('W9 撤回走真 undo + 撤销蓝高亮 + 弹栈',
          h._think_history.undo_calls == 1
          and h.flashes == [(True, True, False)]  # (is_undo, after_commit, is_think)
          and not h._think_walk.steps,
          'undo=%d flashes=%r' % (h._think_history.undo_calls, h.flashes))
    check('W9b 撤回也补了一声瞬时滑动声',
          len(h.slide_sounds) >= 2, h.slide_sounds)
    check('W9c 撤回一步 → 显示步数同步减小回 0',
          getattr(h, '_think_display_steps', None) == 0,
          'display=%r' % (getattr(h, '_think_display_steps', None),))

    # 取消 / 收尾：游走留下的位移必须还原回基线
    h2 = _Host()
    h2._think_do_walk()
    h2._think_abort_and_restore()
    check('W10 收尾把盘面还原回基线（不信只 reset 状态机）',
          h2._think_history.restored == [0] and not h2._think_walk.is_active,
          'restored=%r' % (h2._think_history.restored,))

    # 收尾里 reset 与 restore 的先后：restore 必须在 reset 之前取到 steps
    src = inspect.getsource(AutoSolveMixin._think_abort_and_restore)
    check('W11 收尾先取 steps 再 reset（否则还原条件永远假）',
          src.index('walk.steps') < src.index('walk.reset()'), '')


def real_engine_tests():
    """真引擎往返：真 SliderMatrix + 真 GameHistory，游走后必须逐格回到基线。

    ⚠️ 这条是整件事的核心判据：游走是**真实移动**，所以唯一能证明「不会把
    盘面留在推歪状态」的方式，就是拿真盘面走几刀、再撤回来、逐格比对。
    """
    from game import SliderMatrix
    from history import GameHistory

    class _RealHost(AutoSolveMixin):
        SLIDE_INSTANT_MS = 120   # 与 AnimationMixin 同值（本 Host 不混入它）

        def __init__(self, game):
            self.game = game
            self.current_step = 2
            self._think_walk = ThinkWalk(delay_frames=1, walk_frames=1,
                                         rewind_frames=1, max_steps=5)
            self._think_history = GameHistory()
            self.flashes = []
            self.slide_sounds = []
            self.selected_block = None

        def _play_slide_sound(self, steps=1, duration_ms=None):
            """记录滑动声调用（真实 AnimationMixin 会去 audio 播）。"""
            self.slide_sounds.append((steps, duration_ms))

        def _think_find_move(self):
            """方形盘的最小真实找步（不自带 GUI 依赖，只用引擎接口）。"""
            g = self.game
            b0 = g.get_boundaries()
            cands = ([('h', i) for i in range(b0['min_row'], b0['max_row'])]
                     + [('v', j) for j in range(b0['min_col'], b0['max_col'])])
            for gt, ln in cands:
                for blk in list(g.blocks):
                    for b in g.blocks:
                        b.be_opted = False
                    g.opt(gt, ln, blk)
                    sel = [b for b in g.blocks if b.be_opted]
                    if not sel or len(sel) == len(g.blocks):
                        continue
                    for d in ({'h': ('a', 'd'), 'v': ('w', 's')}[gt]):
                        fin = g.try_move(d, self.current_step)
                        if fin:
                            return (gt, ln, d, fin)
            for b in g.blocks:
                b.be_opted = False
            return None

        def _flash_move_selection(self, mi, is_undo, after_commit=False,
                                  is_think=False):
            self.flashes.append((is_undo, after_commit, bool(is_think)))

    def snappos(game):
        return sorted(tuple(b.location) for b in game.blocks)

    g = SliderMatrix(5, 5)
    g.shuffle(attempts=25, step=2)
    base = snappos(g)
    h = _RealHost(g)
    h._think_begin_wander()

    walked = 0
    for _ in range(80):
        if h._think_walk.tick() == 'walk' and h._think_do_walk():
            walked += 1
    moved = snappos(g)
    check('E1 真引擎：游走真的推了块（盘面已变）',
          walked >= 1 and moved != base, 'walked=%d changed=%s'
          % (walked, moved != base))
    check('E1b 真引擎：显示用游走步数与真实走步数一致',
          getattr(h, '_think_display_steps', None) == walked,
          'display=%r walked=%d' % (getattr(h, '_think_display_steps', None),
                                    walked))

    # 逆向撤回到基线
    h._think_walk.start_rewind()
    guard = 0
    while guard < 400:
        guard += 1
        act = h._think_walk.tick()
        if act == 'rewind':
            h._think_do_rewind()
        elif act == 'rewound':
            break
    check('E2 真引擎：撤完逐格回到基线（盘面没被推歪）',
          snappos(g) == base and not h._think_walk.steps,
          'same=%s rewinds_flash=%d' % (snappos(g) == base, len(h.flashes)))
    check('E3 真引擎：每次撤回都出撤销蓝高亮（不走白边）',
          all(f == (True, True, False) for f in h.flashes) and h.flashes,
          repr(h.flashes[:3]))
    check('E3b 真引擎：全部撤完，显示用游走步数归零',
          getattr(h, '_think_display_steps', None) == 0,
          'display=%r' % (getattr(h, '_think_display_steps', None),))

    # 取消路径：游走中直接收尾，盘面也必须回基线
    g2 = SliderMatrix(5, 5)
    g2.shuffle(attempts=25, step=2)
    base2 = snappos(g2)
    h2 = _RealHost(g2)
    h2._think_begin_wander()
    for _ in range(80):
        if h2._think_walk.tick() == 'walk':
            h2._think_do_walk()
    changed2 = snappos(g2) != base2
    h2._think_abort_and_restore()
    check('E4 真引擎：游走中取消/收尾，盘面回基线',
          changed2 and snappos(g2) == base2 and not h2._think_walk.is_active,
          'changed=%s restored=%s' % (changed2, snappos(g2) == base2))
    check('E4b 收尾时显示用游走步数一起归零（不留幽灵步数）',
          getattr(h2, '_think_display_steps', None) == 0,
          'display=%r' % (getattr(h2, '_think_display_steps', None),))

    # 游走绝不进玩家全局历史：本地历史独立，玩家历史里没有这些步
    check('E5 游走只落本地历史（不写玩家全局历史）',
          len(h2._think_history.history) == 0,
          'local_hist=%d' % len(h2._think_history.history))


def module_tests():
    """用 AST 看真实代码节点。

    ⚠️ 别用 ``'.location' not in src``：模块 docstring 里就有这几个字，
    注释写了也算命中 —— 那是「查源码有没有某个词」的假判据（项目踩过）。
    """
    import ast
    from gui import think_walk
    src = inspect.getsource(think_walk)
    tree = ast.parse(src)

    loc_stores, off_attrs = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr == 'offsets':
                off_attrs.append(node.lineno)
            if node.attr == 'location' and isinstance(node.ctx, ast.Store):
                loc_stores.append(node.lineno)

    check('C1 状态机不写 block.location（移动只由调用方借引擎做）',
          not loc_stores, 'stores=%r' % (loc_stores,))
    check('C2 状态机不再维护渲染偏移（offsets 已废）',
          not off_attrs, 'attrs=%r' % (off_attrs,))


def main():
    state_machine_tests()
    wiring_tests()
    engine_route_tests()
    real_engine_tests()
    module_tests()
    print('==== %s（%d 项失败）====' %
          ('全部通过' if not FAILS else '有失败', len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
