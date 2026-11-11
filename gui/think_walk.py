# -*- coding: utf-8 -*-
"""求解器「思考」演示的状态机（纯逻辑，无 pygame / GUI / 游戏引擎依赖）。

用户待办 §三十四 第 4 条：流式求解播完一段、下一段还没算出来的等待期，
让滑块在**真实盘面**上随机试着推几步（纯视觉，看起来像人在想），下一段到货
的瞬间按游走步**逆序连续撤回**到段末状态，撤回完毕才允许播下一段动画。

⚠️ 关键修正（2026-11-11）：游走 / 撤回**走真实的撤销接口**，不再维护一份
并行的「渲染层偏移」。旧实现（维护 offsets + 自减撤回）与真实盘面 / 历史
永远存在脱钩风险——偏移一旦在「下一段动画已开始、撤回还没清完」时叠到插值
位置上，就把整片移动块推偏，表现为棋盘撕裂、块飞出网格；又因为它从不在真实
历史上留痕，回放时反而显得多出了求解过程没有的步骤（假象）。

新模型：
  * 本模块只做**纯状态机**：记 `steps`（按游走顺序的 move_info 列表），`tick()`
    返回调用方该执行的动作（'walk' / 'rewind' / 'rewound' / None）。
  * 真实走步与真实撤销由调用方（`gui/auto_solve.py` 的 pump）用
    ``GameHistory`` 完成——游走一步 = ``opt``+``try_move``+``commit_move`` 后
    ``save_snapshot`` 进**本地** ``GameHistory``；撤回一步 = 调该本地历史的
    ``undo(game)``（与橙色撤销**同一个** ``GameHistory.undo`` 接口），并触发
    橙色高亮。用本地历史而非玩家全局历史，避免回放 / 撤销链里混进游走步骤。
  * 渲染器不再叠加偏移：游走已是真实移动，直接画 ``b.location`` 即可，天然与
    相机 / 防偏移同源，不会脱钩。

绝不动 ``block.location`` 本模块内部——移动由调用方借引擎完成，状态机只管
「何时走、何时撤、撤几步」。
"""
import random

IDLE = 'idle'
WAITING = 'waiting'
WALKING = 'walking'
REWINDING = 'rewinding'


class ThinkWalk:
    """段间等待的游走 / 撤回状态机。

    delay_frames：播完一段后先空等多少帧再开始游走（避免段间快速衔接时
    闪一下）。walk_frames / rewind_frames：每几帧走一步 / 撤一步。
    max_steps：长等待时不许无限游走（撤回是连续的，步数越多撤回越久）。

    所有时间量都用「帧」而非秒：调用方每帧 tick 一次，不依赖 clock，
    便于护栏确定性推进（项目里 audio / 动画护栏同样口径）。
    """

    def __init__(self, delay_frames=45, walk_frames=14, rewind_frames=7,
                 max_steps=12, rng=None):
        self.delay_frames = int(delay_frames)
        self.walk_frames = max(1, int(walk_frames))
        self.rewind_frames = max(1, int(rewind_frames))
        self.max_steps = int(max_steps)
        self.rng = rng or random.Random()
        self.state = IDLE
        # 按游走顺序记录的 move_info 列表；撤回时由调用方用真实撤销接口
        # 逐一回退，回退一步就 pop 一个——与本列表严格一一对应。
        self.steps = []
        self._wait = 0
        self._frame = 0
        # 观测用（护栏可断言「段到货前不许播段」）
        self.walked = 0
        self.rewound = 0

    @property
    def is_active(self):
        return self.state != IDLE

    def reset(self):
        """彻底清空（取消求解 / 换盘 / 关开关 / 撤回完成）。"""
        self.state = IDLE
        self.steps = []
        self._wait = 0
        self._frame = 0

    def begin(self):
        """一段播完、下一段还没来：开始等待计时。重复调用不重置计时。"""
        if self.state == IDLE:
            self.state = WAITING
            self._wait = 0
            self._frame = 0

    def tick(self):
        """推进一帧，返回本帧该执行的动作：

        ``'walk'``    该走一步（调用方做真实走步 + note_walk）
        ``'rewind'``  该撤一步（调用方做真实撤销 + note_rewind）
        ``'rewound'`` 已撤完（调用方清本地历史并继续播段 / 收尾）
        ``None``      无动作（仍在等待 / 游走节奏 / 撤回节奏中）
        """
        if self.state == WAITING:
            self._wait += 1
            if self._wait >= self.delay_frames:
                self.state = WALKING
                self._frame = 0
            return None

        if self.state == WALKING:
            if len(self.steps) >= self.max_steps:
                return None
            self._frame += 1
            if self._frame < self.walk_frames:
                return None
            self._frame = 0
            return 'walk'

        if self.state == REWINDING:
            self._frame += 1
            if self._frame < self.rewind_frames:
                return None
            self._frame = 0
            if self.steps:
                return 'rewind'
            # 兜底：严格归零，不允许残留
            self.state = IDLE
            self._wait = 0
            self.rewound += 1
            return 'rewound'

        return None

    def start_rewind(self):
        """下一段到货 / 求解结束：开始连续撤回。

        返回 ``'rewound'`` 表示根本没游走过（或已在撤回尾声），调用方可立即
        继续；否则 None，之后每帧 tick 直到返回 'rewound'。
        """
        if self.state == IDLE:
            return 'rewound'
        if self.state in (WAITING, WALKING):
            if not self.steps:
                self.reset()
                return 'rewound'
            self.state = REWINDING
            self._frame = 0
        return None

    def note_walk(self, move_info):
        """调用方真实走完一步后登记（move_info 入 steps）。"""
        self.steps.append(move_info)
        self.walked += 1

    def note_rewind(self):
        """调用方真实撤完一步后登记（steps 弹栈，与 undo 严格对应）。"""
        if self.steps:
            self.steps.pop()
