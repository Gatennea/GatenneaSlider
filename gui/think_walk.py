# -*- coding: utf-8 -*-
"""求解器「思考」演示的状态机（纯逻辑，无 pygame / GUI 依赖）。

用户待办 §三十四 第 4 条：流式求解播完一段、下一段还没算出来的等待期，
让滑块在**渲染层**随机游走，看起来像人在试着推；下一段到货的瞬间按游走
步逆序「连续撤回」到段末状态，撤回完毕才允许播下一段动画。

⚠️ 为什么不走真实移动：
  * ``commit_animation`` 的普通移动分支会 ``step_count += 1`` +
    ``save_snapshot`` + ``_mark_file_dirty()``，游走会污染玩家历史；
  * 求解器后台算好的下一段以**段末真实盘面**为起点，游走真改盘面会让
    坐标对不上（除非撤回分毫不差）；
  * 聚拢度按 ``game.blocks`` 算，渲染层偏移让它**恒定不变**——正是用户
    要求的「盡量保證聚攏度沒有很大變化」。

故本模块只维护 ``{id(block): (dr, dc)}`` 的渲染偏移，绝不改
``b.location``。偏移由 GUI 用真实合法走法（``game.opt`` + ``try_move``
只读试算）生成，所以看起来确实在试着推块，而不是凭空抖动。

撤回 = 按 history 逆序把每步偏移逐格减掉（连续、可见），最后强制清零
兜底，保证无论中途被打断多少次，盘面显示都严格回到段末状态。
"""
import random

IDLE = 'idle'
WAITING = 'waiting'
WALKING = 'walking'
REWINDING = 'rewinding'


class ThinkWalk:
    """段间等待的渲染层游走 / 撤回状态机。

    delay_frames：播完一段后先空等多少帧再开始游走（避免段间快速衔接时
    闪一下）。walk_frames / rewind_frames：每几帧走一步 / 撤一步。
    max_offset：单块累积渲染偏移的绝对值上限（格），防止越走越散。

    所有时间量都用「帧」而非秒：调用方每帧 tick 一次，不依赖 clock，
    便于护栏确定性推进（项目里 audio / 动画护栏同样口径）。
    """

    def __init__(self, delay_frames=45, walk_frames=14, rewind_frames=7,
                 max_offset=2, max_steps=12, rng=None):
        self.delay_frames = int(delay_frames)
        self.walk_frames = max(1, int(walk_frames))
        self.rewind_frames = max(1, int(rewind_frames))
        self.max_offset = float(max_offset)
        # 长等待时不许无限游走：撤回是「连续」的，步数越多撤回越久。
        # 上限 12 步 × rewind_frames 帧 ≈ 1.4s，观感够用且不拖慢求解。
        self.max_steps = int(max_steps)
        self.rng = rng or random.Random()
        self.state = IDLE
        self.offsets = {}       # id(block) -> (dr, dc) 累积渲染偏移
        self.steps = []         # 每步 [(bid, dr, dc), ...]，撤回按逆序弹
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
        self.offsets.clear()
        self.steps.clear()
        self._wait = 0
        self._frame = 0

    def begin(self):
        """一段播完、下一段还没来：开始等待计时。重复调用不重置计时。"""
        if self.state == IDLE:
            self.state = WAITING
            self._wait = 0
            self._frame = 0

    def tick(self, find_move=None):
        """推进一帧。

        find_move(): 返回 ``[(bid, dr, dc), ...]`` 或 None（GUI 用只读合法
        步生成器提供；撤回态不会调用它）。

        返回 ``'rewound'`` 表示撤回完成、调用方可以播下一段；否则 None。
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
            if find_move is None:
                return None
            rec = find_move()
            if not rec:
                return None
            # 先整体试算：任一块会越过 max_offset 就**整步跳过**，
            # 保证 history 与 offsets 严格一一对应（撤回不会多减/少减）。
            cand = {}
            for bid, dr, dc in rec:
                r, c = self.offsets.get(bid, (0.0, 0.0))
                nr, nc = r + dr, c + dc
                if abs(nr) > self.max_offset or abs(nc) > self.max_offset:
                    return None
                cand[bid] = (nr, nc)
            self.offsets.update(cand)
            self.steps.append(list(rec))
            self.walked += 1
            return None

        if self.state == REWINDING:
            self._frame += 1
            if self._frame < self.rewind_frames:
                return None
            self._frame = 0
            if self.steps:
                for bid, dr, dc in self.steps.pop():
                    r, c = self.offsets.get(bid, (0.0, 0.0))
                    nr, nc = r - dr, c - dc
                    if abs(nr) < 1e-9 and abs(nc) < 1e-9:
                        self.offsets.pop(bid, None)
                    else:
                        self.offsets[bid] = (nr, nc)
                self.rewound += 1
                return None
            # 兜底：严格归零，不允许残留浮点尾巴
            self.offsets.clear()
            self.state = IDLE
            self._wait = 0
            return 'rewound'

        return None

    def start_rewind(self):
        """下一段到货 / 求解结束：开始连续撤回。

        返回 ``'rewound'`` 表示根本没游走过（或已在撤回尾声），调用方可
        立即继续；否则 None，之后每帧 tick 直到返回 'rewound'。
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
