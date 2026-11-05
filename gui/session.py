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

    def shuffle_puzzle(self, confirm=True):
        """打乱谜题 - 调用 game.py 的 shuffle 核心逻辑

        confirm=True（交互入口默认）：若「防意外打乱」开关开着且当前历史非空，
        先弹确认框（确定打乱 / 存档 / 取消），避免误触把可撤销的历史冲掉。
        确认后与外部控制（API / stdin）都会以 confirm=False 再调一次直接执行。
        """
        # 无限打乱进行中：本次调用即为「停止」（优先于一切 guard）
        if getattr(self, '_infinite_shuffle_active', False):
            self._stop_infinite_shuffle()
            return
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
        # 构造/设计画布中：主棋盘就是编辑画布，打乱会把未保存的编辑冲掉
        if getattr(self, '_ann_sub_dialog', None) in ('build', 'design'):
            self.macro_notify_msg = "构造/设计中：先退出画布再打乱"
            self.macro_notify_timer = 90
            return
        # 标注会话随棋盘重置而结束
        self._ann_cancel_session('打乱')
        # 计时进行中禁止打乱
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法打乱"
            self.macro_notify_timer = 90
            return

        # 冻形预检（P2 产品化预检，2026-10-24）：一条能选中的缝都没有
        # （每条缝线都切进滑块内部、或只剩一侧有滑块）时 game.shuffle
        # 一步也走不了——与其让玩家按了打乱却毫无变化，不如说清楚。
        # 可达性：正常对局每步可逆 ⇒ 恒有合法移动，官方预设更不在话下；
        # 这条拦的是手工改坏的存档/老样式之类的非常规盘面。枚举自身
        # 抛异常时不拦（fail-open），别让预检把正常打乱挡掉。
        try:
            gaps = self._ann_all_valid_gaps()
        except Exception:
            gaps = None
        if gaps is not None and not gaps:
            self.macro_notify_msg = "无法打乱：这个盘面没有能选中的缝，滑块滑不动"
            self.macro_notify_timer = 90
            return

        # 防意外打乱：历史非空时先确认（打乱会清空历史、之后无法撤回）
        if (confirm
                and getattr(self, 'confirm_before_shuffle', True)
                and self._shuffle_has_history()):
            self._request_shuffle_confirm()
            return

        # 无限打乱模式：开启后首次调用打乱 -> 启动连续随机游走（再次调用停止）
        if getattr(self, 'infinite_shuffle', False):
            self._start_infinite_shuffle()
            return

        # 取消当前动画 / 打乱演示
        self._abort_shuffle_demo()
        if self.animating:
            self.cancel_animation()

        attempts = self.current_m * self.current_n * 10  # 打乱尝试次数

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
        # 提示里的步数用**实际走成**的步数，不是 attempts（attempts 是尝试
        # 次数：不可逆走法被跳过，两者能差到 5 倍，玩家看到的步数与盘面
        # 打乱程度对不上）。records 是唯一的成功流水，两种引擎都往里写。
        real_steps = len(records)
        if self.game_mode == 'timed':
            self._timer_enter_ready()
            notify_msg = f"已打乱：{real_steps}步（空格开始计时）"
        else:
            self._timer_cancel()
            notify_msg = f"已打乱：{real_steps}步（练习模式）"
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

    # ------------------------------------------------------------------
    # 无限打乱：开启后调用打乱即进入连续「单步随机游走」，再次调用打乱即停止。
    #
    # 实现是真正的逐格游走——完全绕开「打乱演示」管線：
    #   · 每步调用 game.shuffle(1, …, bias=0) 只走成一步（不放 min_score，
    #     避免触发其「重洗重试」循环产生成千上万步、进而又走回普通打乱的
    #     淡出切屏 + 进度条）；个别形态偶发该步不可逆被回滚，则补到 1 步。
    #   · 把棋盘回退到这一步起点、用 start_animation 滑一格、落位后立刻
    #     在 commit_animation 里续下一格——视觉就是无缝连续随机游走。
    #   · 不设 _shuffle_demo_active -> 渲染层不会画进度条、不会走淡出切屏。
    #   · 每步都从当前盘面的合法缝取走法 -> 所有形态（方/三角/米字/自定義
    #     模型局）通用；每步经 commit_shuffle_step 可逆校验 -> 终态恒有解。
    # ------------------------------------------------------------------
    def _start_infinite_shuffle(self):
        """进入无限打乱：从当前态开始连续随机游走。"""
        self._abort_shuffle_demo()
        if self.animating:
            self.cancel_animation()
        self._infinite_shuffle_active = True
        self._infinite_shuffle_game = self.game  # 换盘（新局/载入）即失效停止
        self._infinite_prev_duration = self.animation_duration  # 停止时还原步长
        self.selected_gap = None
        self.selected_block = None
        # 以当前态为根：清历史、步数归零（连续游走的历史无意义）
        self.step_count = 0
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        self._last_timed_result = None
        self.macro_notify_msg = "无限打乱中：再次打乱停止"
        self.macro_notify_timer = 120
        self._infinite_shuffle_step()

    def _infinite_shuffle_step(self):
        """无限打乱的下一格：从当前态取一步随机可逆走法并滑出。"""
        if not getattr(self, '_infinite_shuffle_active', False):
            return
        # 运行中若被取消开关，立即收尾（否则开关关了还在走会让人困惑）
        if not getattr(self, 'infinite_shuffle', False):
            self._infinite_shuffle_active = False
            self._restore_infinite_duration()
            self._finalize_infinite_state()
            self.macro_notify_msg = "已停止无限打乱（开关已关）"
            self.macro_notify_timer = 90
            return
        # 游走会摊开盘面，仅在块滑出视口时才平移镜头跟随（不动整体缩放）
        self.ensure_blocks_visible(only_if_invisible=True)
        # 换盘（新局/载入/成绩回放）-> 无限模式立即结束，不碰新棋盘
        if getattr(self, '_infinite_shuffle_game', None) is not self.game:
            self._infinite_shuffle_active = False
            self._restore_infinite_duration()
            return
        recs = []
        # 一次只走成一步：attempts=1 且不放 min_score（避免 game.shuffle 的
        # 重洗重试循环，否则会产生成千上万步、甚至触发普通打乱的淡出切屏）。
        # 个别形态偶发 0 步（该次随机走法不可逆被回滚），循环补到 1 步为止。
        tries = 0
        while len(recs) < 1 and tries < 40:
            recs = []
            # min_score=None：各形态均跳过「难度重洗」循环，只走恰好 attempts=1
            # 步；bias=0 纯随机。这样每轮只产出 0~1 步，绝不触发成千上万步。
            self.game.shuffle(1, self.current_step, bias=0.0,
                              min_score=None, record=recs)
            tries += 1
        if len(recs) < 1:
            # 没有可用缝（极罕见）：安全退出，不空转
            self._infinite_shuffle_active = False
            self._restore_infinite_duration()
            self._finalize_infinite_state()
            self.macro_notify_msg = "无限打乱：当前盘面无可移动缝，已自动停止"
            self.macro_notify_timer = 120
            return
        rec = recs[0]
        # game.shuffle 已把棋盘推到该步终点；先找到「终点位置」上的块（即
        # 这一步实际移动的块），再回退到移动前位置，最后滑回终点重放这一格。
        blocks = self._find_blocks_at_positions(rec['final'])
        if len(blocks) != len(rec['final']):
            # 位置对不上（理论不发生）：跳过这步、直接续下一格
            self._infinite_shuffle_step()
            return
        for b, p in zip(blocks, rec['moved']):
            b.location = list(p)  # 回退到移动前
        # 步长跟随玩家速度但夹在 200ms 以内，保证游走连贯可看；动画关闭时
        # 退化为 60ms 一格（无限打乱本质是视觉特效，仍让它可见地游走）
        if getattr(self, 'animation_enabled', True) and self.animation_duration > 0:
            dur = min(self.animation_duration, 200)
        else:
            dur = 60
        self.animation_duration = dur
        # 无限打乱只计步、不记历史：左下角步数持续增长，纯粹是游走进度
        self.step_count += 1
        self._infinite_shuffle_step_playing = True
        self.start_animation(blocks, rec['final'])

    def _restore_infinite_duration(self):
        """停止无限打乱时还原玩家原来的动画步长。"""
        prev = getattr(self, '_infinite_prev_duration', None)
        if prev is not None:
            self.animation_duration = prev
        self._infinite_prev_duration = None
        self._infinite_shuffle_step_playing = False

    def _stop_infinite_shuffle(self):
        """停止无限打乱：对齐到当前态、还原步长、清状态。"""
        self._infinite_shuffle_active = False
        # 若正有一格在滑：把它落到**终点**再快照。此时 game 内部矩阵早已推进
        # 到终点，若走 cancel_animation（放回起点）会让 blocks 与矩阵不一致，
        # 快照出来的历史根就是错位盘面。
        if getattr(self, '_infinite_shuffle_step_playing', False) and self.anim_blocks:
            for i, b in enumerate(self.anim_blocks):
                b.location = list(self.anim_end_pos[i])
            self._reset_anim_state()
        elif self.animating:
            self.cancel_animation()
        self._restore_infinite_duration()
        self._abort_shuffle_demo()
        self._finalize_infinite_state()
        self.macro_notify_msg = "已停止无限打乱"
        self.macro_notify_timer = 90
        self.ensure_blocks_visible()

    def _finalize_infinite_state(self):
        """无限打乱结束的统一收尾：步数清零、历史以当前态为根（绝不可撤回）。

        游走期间只计步、不写历史——历史里仍是最初为根的那一条快照。若不在
        这时重置，撤销会把棋盘拉回游走起点。所以结束时把**当前态**存成唯一
        快照（history_index=0，can_undo=False），与普通打乱后的语义一致。
        """
        self.step_count = 0
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()

    # ------------------------------------------------------------------
    # 防意外打乱：历史非空时先确认（确定打乱 / 存档 / 取消）
    # ------------------------------------------------------------------
    def _shuffle_has_history(self) -> bool:
        """当前是否存在会被打乱清掉的历史（可撤销或可重做）。"""
        h = getattr(self, 'game_history', None)
        if h is None:
            return False
        try:
            return bool(h.can_undo() or h.can_redo())
        except Exception:
            # 历史接口异常时保守放行（不因预检把正常打乱挡掉）
            return False

    def _request_shuffle_confirm(self):
        """弹出「打乱前确认」：明确会清空历史，提供 确定打乱 / 存档 / 取消。"""
        self.show_confirm_dialog = True
        self.confirm_title = '打乱前确认'
        self.confirm_lines = [
            '打乱会清空当前的历史记录，之后将无法撤销回打乱前的局面。',
            '建议先存档再打乱。',
        ]
        self.confirm_ok_text = '确定打乱'
        self.confirm_danger = True
        self.confirm_extra_text = '存档'
        self.confirm_action = (lambda: self.shuffle_puzzle(confirm=False))
        self.confirm_extra_action = self._save_then_shuffle

    def _save_then_shuffle(self):
        """确认框的「存档」：先存档，成功后再打乱（用户本意仍是打乱）。

        无当前文件路径时走另存为对话框（异步）——先挂 `_pending_shuffle_after_save`
        标记，等 handle_file_dialog_result 保存成功后再打乱；取消另存为则放弃打乱。
        """
        # 编辑器画布不能存成谜题存档（save_to_file 会拦截并提示）
        if self._med_save_blocked():
            return
        if getattr(self, 'prevent_overwrite_flag', False) and self.current_file_path:
            self._pending_shuffle_after_save = True
            self.save_as()
        elif self.current_file_path:
            if self._save_to_path(self.current_file_path):
                self.shuffle_puzzle(confirm=False)
        else:
            self._pending_shuffle_after_save = True
            self.save_as()

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
        # 高级选项样式局：复原 = 回到样式还原态，不是默认满矩形。
        # new_puzzle 会清 goal_pattern/_ann_style_goal，直接重建等于一转就把
        # 自定义还原目标丢了（样式局开局本就是还原态，玩家按 Ctrl+R 的期望
        # 显然是回到那个形状）。样式文件被删/改名时退回普通重建。
        preset = getattr(self, '_ann_style_goal', None)
        if preset:
            from gui import design_styles
            if design_styles.load_style(self.config_dir, preset):
                self._ann_design_start_style(preset)
                return
        # 按当前形态重建：只分「三角 / 其它」会让米字格被当成矩形重建
        # （Ctrl+R 之后米字格变矩形，尺寸等级还正好是初始预设），
        # 带序号重建后编号也一起丢掉——两者都是这里漏了分支。
        # 碎三角同理：没有旗标，按 game.kind 判（与 _current_kind 同源），
        # 漏了它 Ctrl+R 会把 48 块碎三角静默换成 4×4 矩形。
        kind = self._current_kind()
        if getattr(self, 'triangle_mode', False):
            self.new_triangle_puzzle(self.triangle_side, self.current_step)
        elif getattr(self, 'mi_mode', False):
            self.new_mi_puzzle(self.current_m, self.current_n, self.current_step)
        elif kind not in ('square', 'triangle', 'mi', 'numbered'):
            # 模型文件板型（碎三角及任何 models/<name>.json）：固定块数，
            # 只有等级可重建。漏了这条 Ctrl+R 会把 48 块碎三角静默换成
            # 4×4 矩形——那正是本项目明令禁止的静默兜底。
            self.new_model_puzzle(kind, self.current_step)
        elif getattr(self, 'numbered', False):
            self.new_puzzle(self.current_m, self.current_n, self.current_step,
                            numbered=True)
        else:
            self.new_puzzle(self.current_m, self.current_n, self.current_step)

    # ==================== 几何引擎开关（实验） ====================

    def engine_label(self) -> str:
        """当前逻辑引擎的人话标签（状态栏常显，一眼看出在跑哪套）。"""
        try:
            from engine import config as _ecfg
            return '几何' if _ecfg.is_enabled() else '经典'
        except ImportError:
            return '经典'

    # ==================== 计时器 ====================

    def _current_kind(self) -> str:
        """当前谜题形态键（puzzle_key / 成绩分榜共用）。

        旧四形态走旗标（triangle_mode/mi_mode/numbered）；几何引擎的新板型
        （碎三角等）没有旗标——形态挂在逻辑对象自带的 ``game.kind`` 上
        （EngineGame 建局即带），与 solver.game_form 同源。新板型登记进
        engine.registry 即自动在此可见，不必再改这里。
        """
        if getattr(self, 'triangle_mode', False):
            return 'triangle'
        if getattr(self, 'mi_mode', False):
            return 'mi'
        if getattr(self, 'numbered', False):
            return 'numbered'
        kind = getattr(self.game, 'kind', '')
        if kind and kind not in ('square', 'numbered', 'triangle', 'mi'):
            return kind
        return 'square'

    def _is_model_kind(self) -> bool:
        """当前是否为模型文件板型（碎三角及任何 models/<name>.json）。

        各处拦截（竞速/创造/设计画布/随机生成/手动构造）都该用这个判据，
        而不是 `== 'shatter'`——否则丢一个新模型进目录，那些入口会静默
        把模型局换来换去。
        """
        return self._current_kind() not in ('square', 'numbered', 'triangle', 'mi')

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

    def _preset_is_current(self, preset, current_key=None) -> bool:
        """菜单项是否标记为「当前所在」（✓ 与高亮共用）。

        高级选项样式局的 m/n/step 往往正好等于某个官方档位（例如 3×3 等级1，
        因为样式的边界盒就是那次设计画布的尺寸），只比分榜键会把那一档标成
        「当前✓」——看起来像这局变成了预设谜题。所以样式局只认自己那条
        自定义预设 `('名','__custom__','名')`，官方档位一律不标。
        """
        style = getattr(self, '_ann_style_goal', None)
        if len(preset) == 3 and preset[1] == '__custom__':
            return style is not None and preset[2] == style
        if style:
            return False
        if current_key is None:
            current_key = self._current_puzzle_key()
        return len(preset) >= 4 and self._preset_puzzle_key(preset) == current_key

    def _current_puzzle_label(self) -> str:
        """当前谜题的人话描述（谜题菜单底部状态行用）。"""
        if getattr(self, '_med_active', False):
            # 搭积木编辑器会话：self.game 是预览局（kind='__editor__'），
            # 落到下面的模型分支会显示成一个不存在的板型名
            return '搭积木编辑器（未保存）'
        style = getattr(self, '_ann_style_goal', None)
        if style:
            # 高级选项样式局不是任何一个官方档位：尺寸/等级可能刚好撞上
            # 预设（3×3 等级1 之类），但说「当前：矩形 3×3 等级1」是错的
            return f'样式「{style}」'
        if getattr(self, 'triangle_mode', False):
            k = getattr(self.game, 'k', self.current_m)
            return f'三角形 边长{k} 等级{self.current_step}'
        if getattr(self, 'mi_mode', False):
            return f'米字格 {self.current_m}×{self.current_n} 等级{self.current_step}'
        _kind = self._current_kind()
        if _kind not in ('square', 'numbered', 'triangle', 'mi'):
            # 模型文件板型：固定块数、无尺寸维度，标签只报等级（名字取文件里的 title）
            try:
                from engine import model_registry
                _title = model_registry.loaded(_kind).title
            except (KeyError, ImportError):
                _title = _kind
            return f'{_title} 等级{self.current_step}'
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

