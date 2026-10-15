# -*- coding: utf-8 -*-
"""竞速模式混入：计时器 / 游戏模式 / 最好成绩(ao)系列。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第三步）。
计时用 time.perf_counter（单调钟，不受系统时间调整影响）；成绩走 self.records
（RecordsPanel 那套 storage）。模式与计时强耦合（进模式->就绪->空格开始->
解开完成），故放同一 mixin。
"""
import time


class SpeedrunMixin:
    """竞速计时与模式切换（原 GUI.py 内联代码，整体搬迁）。"""

    def _timer_enter_ready(self):
        """打乱完成后进入就绪态，捕获初始矩阵"""
        # 取消可能正在后台运行的求解器
        if self._auto_solve_running:
            self._auto_solve_cancel = True
        self.timer_state = 'ready'
        self.timer_elapsed = 0.0
        self.timer_m = self.current_m
        self.timer_n = self.current_n
        self.timer_step = self.current_step
        tri = getattr(self, 'triangle_mode', False)
        self.timer_puzzle_key = puzzle_key(
            self.current_step, self.current_m, self.current_n,
            kind=self._current_kind(),
            triangle_side=self.game.k if tri else None)
        self.timer_initial_matrix = self._timer_initial_map()

    def _timer_initial_map(self) -> str:
        """竞速初始局面的存档串。

        方形/序号转成 0/1（成绩面板按 █/· 渲染、可转回 #/_ 地图）；
        三角形保留 #^v_ 原生编码——菱形胞 2-bit 信息量比 0/1 大，
        且 import_map 能直接吃回，载入练习/另存为谜题都不用改编码。
        """
        if getattr(self, 'triangle_mode', False):
            return self.game.export_map()
        if getattr(self, 'mi_mode', False):
            # 米字格已随 M4 一起有 export_map（mi8 编码）；打乱被拦 →
            # 就绪态到不了这里
            return ''
        return self.game.export_map().replace('#', '1').replace('_', '0')

    def _timer_cancel(self):
        """取消当前计时会话（回到空闲态）"""
        self.timer_state = 'idle'
        self.timer_elapsed = 0.0

    def _mode_name(self) -> str:
        """当前模式的中文名（练习 / 竞速 / 创造）。"""
        return {'timed': '竞速', 'create': '创造'}.get(self.game_mode, '练习')

    def set_game_mode(self, mode: str) -> bool:
        """设置模式：'practice' 练习 / 'timed' 竞速 / 'create' 创造（幂等）。

        返回是否成功（计时进行中拒绝切换）。
        """
        if mode not in ('practice', 'timed', 'create'):
            return False
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换模式"
            self.macro_notify_timer = 90
            return False
        if mode == self.game_mode:
            return True
        # 离开创造模式：收掉创造界面
        if self.create_mode:
            self._ann_leave_to_home()
        if mode == 'create':
            # 创造模式与标注模式/计时互斥
            self.annotation_mode = False
            self._ann_leave_to_home()
        self._timer_cancel()
        self.game_mode = mode
        if mode == 'timed':
            self.macro_notify_msg = "竞速模式：打乱后需按空格开始计时"
        elif mode == 'create':
            if self.triangle_mode or self.mi_mode:
                self.macro_notify_msg = "创造模式：请用[手动构造]造题"
            else:
                self.macro_notify_msg = "创造模式：随机挖洞/缺口 或 手动构造，造好即成为当前谜题"
        else:
            self.macro_notify_msg = "练习模式：可自由滑动，不计时"
        self.macro_notify_timer = 120
        return True

    def toggle_game_mode(self):
        """循环切换 练习 → 竞速 → 创造 → 练习（「模式」开关 / 谜题菜单入口）"""
        order = ('practice', 'timed', 'create')
        try:
            idx = order.index(self.game_mode)
        except ValueError:
            idx = 0
        self.set_game_mode(order[(idx + 1) % len(order)])

    def _timer_start(self):
        """开始计时"""
        if self.timer_state != 'ready':
            return
        self.timer_state = 'running'
        self.timer_start = time.perf_counter()
        self.timer_elapsed = 0.0

    def _timer_on_space(self):
        """空格键：ready→开始，running→DNF（练习模式禁用计时）"""
        if self.game_mode != 'timed':
            return
        if self.timer_state == 'ready':
            self._timer_start()
        elif self.timer_state == 'running':
            self._timer_finish(dnf=True)

    def _timer_check_solved(self):
        """running 状态下检测是否复原，复原则停止计时"""
        if self.timer_state != 'running':
            return
        if self.animating:
            return
        if self.is_solved():
            self._timer_finish(dnf=False)

    def _timer_finish(self, dnf: bool):
        """结束计时并写成绩"""
        elapsed_ms = (time.perf_counter() - self.timer_start) * 1000.0
        self.timer_elapsed = elapsed_ms / 1000.0

        # 记录成绩前先取旧统计，用于“新最佳”判定
        key = self.timer_puzzle_key
        old = self.records.stats(key)
        old_series = self.records.series(key)
        old_ao5 = self._series_best_ao(old_series, 5)
        old_ao12 = self._series_best_ao(old_series, 12)

        self.records.add_record(
            self.timer_puzzle_key,
            self.timer_m, self.timer_n, self.timer_step,
            self.timer_initial_matrix,
            elapsed_ms,
            self.step_count,
            dnf,
            numbered=getattr(self, 'numbered', False),
        )
        self.timer_state = 'dnf' if dnf else 'stopped'

        # 计算本次成绩 / TPS / 最佳判定，供复原成功悬浮窗显示
        if dnf:
            self._last_timed_result = {
                'time_ms': int(round(elapsed_ms)), 'moves': self.step_count,
                'tps': 0.0, 'pb_single': False, 'pb_ao5': False, 'pb_ao12': False,
                'dnf': True,
            }
        else:
            tps = self.step_count / (elapsed_ms / 1000.0) if elapsed_ms > 0 else 0.0
            new_series = self.records.series(key)
            new_ao5 = self._series_best_ao(new_series, 5)
            new_ao12 = self._series_best_ao(new_series, 12)
            # 单次最佳：严格小于旧 best（旧记录中不存在该用时就算新最佳）
            is_pb_single = (old['best'] is None or elapsed_ms < old['best'])
            self._last_timed_result = {
                'time_ms': int(round(elapsed_ms)), 'moves': self.step_count,
                'tps': tps,
                'pb_single': is_pb_single,
                'pb_ao5': new_ao5 is not None and (old_ao5 is None or new_ao5 < old_ao5),
                'pb_ao12': new_ao12 is not None and (old_ao12 is None or new_ao12 < old_ao12),
                'dnf': False,
            }

        st = self.records.stats(self.timer_puzzle_key)

        def _fmt(v):
            if v is None:
                return '-'
            if v == 'DNF':
                return 'DNF'
            return format_time(v)

        cur2 = format_time(elapsed_ms)
        best = _fmt(st['best'])
        ao5 = _fmt(st['ao5'])
        if dnf:
            self.macro_notify_msg = f"DNF（{cur2}） | 最好 {best} | Ao5 {ao5}"
        else:
            self.macro_notify_msg = f"复原！{cur2}（{self.step_count}步） | 最好 {best} | Ao5 {ao5}"
        self.macro_notify_timer = 180

    @staticmethod
    def _series_best_ao(series, n):
        """取 series 中所有可计算 AoN 的最小值；不足 n 次或无有效值返回 None。"""
        best = None
        for _rec, ao, _a12 in series:
            if n == 12:
                ao = _a12
            if ao is not None and ao != 'DNF':
                if best is None or ao < best:
                    best = ao
        return best

    def _timer_blocked(self):
        """竞速模式下宏与求解器一律禁止（练习模式不禁）"""
        return self.game_mode == 'timed'

    def _timer_status_text(self):
        """返回状态栏要显示的计时器文本（练习/竞速/创造始终显示当前状态）"""
        if self.game_mode == 'practice':
            return "练习模式"
        if self.game_mode == 'create':
            return "创造模式"
        prefix = "竞速模式"
        if self.timer_state == 'idle':
            return f"{prefix}（待打乱）"
        if self.timer_state == 'ready':
            return f"{prefix}（就绪，空格开始）"
        if self.timer_state == 'running':
            return f"{prefix} {format_time(self.timer_elapsed * 1000)}"
        if self.timer_state == 'stopped':
            return f"{prefix} 成绩 {format_time(self.timer_elapsed * 1000)}"
        if self.timer_state == 'dnf':
            return f"{prefix} DNF"
        return ""

