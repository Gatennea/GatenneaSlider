# -*- coding: utf-8 -*-
"""竞速模式混入：计时器 / 游戏模式 / 最好成绩(ao)系列。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第三步）。
计时用 time.perf_counter（单调钟，不受系统时间调整影响）；成绩走 self.records
（RecordsPanel 那套 storage）。模式与计时强耦合（进模式->就绪->空格开始->
解开完成），故放同一 mixin。
"""
import time

from puzzle_types import puzzle_key
from records import format_time


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

    def _mode_label(self, mode: str) -> str:
        """模式键的中文名（不读当前状态；_mode_name 是它的当前态特例）。"""
        return {'timed': '竞速', 'create': '创造'}.get(mode, '练习')

    def _mode_name(self) -> str:
        """当前模式的中文名（练习 / 竞速 / 创造）。"""
        return self._mode_label(getattr(self, 'game_mode', 'practice'))

    def mode_allowed(self, mode: str) -> bool:
        """该模式在当前盘面形态下能不能进（**只判形态，不看计时状态**）。

        模型文件板型（碎三角及以后任何 models/<name>.json）不进竞速：
        export_map 的方形分支会把 24 种朝向压成 '#'（质心晶格的「朝向下标+1」
        矩阵没有字符编码），初始局面存下来也还原不回同一题，成绩没有意义。
        判据用「形态名不在旧四种里」，与建局/存档同源（不硬编码 'shatter'）。
        ⚠️ 创造模式（2026-10-25 起）不再据此拒入：模式开关 → 创造 →
        ② 还原态设计 → 搭积木 不依赖当前盘面形态（编辑器自建预览局）；
        打乱态设计/格子画布两个子入口各自有 _is_model_kind 拒绝。

        带粘连（捆绑组）的局也拒竞速，理由见下面的 _board_has_bundles 分支。

        2026-10-26 从 set_game_mode 内联判据提出来，供循环开关跳档共用
        ——两处各写一份，就会出现「开关按了没反应」而 set 能进的不一致。
        """
        if mode not in ('practice', 'timed', 'create'):
            return False
        if mode == 'timed':
            if self._current_kind() not in ('square', 'numbered', 'triangle', 'mi'):
                return False
            # 带粘连（捆绑）的局同样不进竞速：竞速的初始局面只记「哪些格子
            # 有块」（export_map 是 0/1 或 #/_），不记谁和谁粘着 —— 成绩存
            # 下来还原出的是另一道题。这与模型板型被拒是同一类问题（那边丢
            # 的是朝向，这边丢的是捆绑组），所以同样明确拒绝、不静默存。
            return not self._board_has_bundles()
        return True

    def _board_has_bundles(self) -> bool:
        """当前盘面是否有粘连滑块（捆绑组）。

        判据直接看局面里的块，不看「这是不是样式局」：样式局也可能没粘连
        （用户可以只改形状不粘），官方档位打乱后也可能带粘连（编辑器里绑过）。
        """
        try:
            return any(int(getattr(b, 'group', 0) or 0)
                       for b in self.game.blocks)
        except Exception:      # noqa: BLE001 —— 拿不到就当没有，别把模式切换搞崩
            return False

    def set_game_mode(self, mode: str) -> bool:
        """设置模式：'practice' 练习 / 'timed' 竞速 / 'create' 创造（幂等）。

        返回是否成功（计时进行中拒绝切换；当前盘型不支持该模式也拒绝，
        理由写在 macro_notify_msg 里）。形态判据见 mode_allowed()。
        """
        if mode not in ('practice', 'timed', 'create'):
            return False
        if self.timer_state == 'running':
            self.macro_notify_msg = "计时中无法切换模式"
            self.macro_notify_timer = 90
            return False
        if not self.mode_allowed(mode):
            if mode == 'timed' and self._board_has_bundles():
                self.macro_notify_msg = (
                    "这道题有粘连滑块，暂不支持竞速"
                    "（竞速只记录哪些格子有块，还原不出同一题）")
            else:
                _kind = self._current_kind()
                _label = {'shatter': '碎三角'}.get(_kind, _kind)
                self.macro_notify_msg = f"{_label}暂不支持竞速模式（初始局面无字符编码）"
            self.macro_notify_timer = 120
            return False
        if mode == self.game_mode:
            return True
        # 高级选项设计画布：切模式 = 放弃未保存的编辑（先把盘面还原回进入前）
        if getattr(self, '_ann_design_session', False):
            self._ann_design_cancel()
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
            self.macro_notify_msg = ("创造模式：① 打乱状态设计 ② 还原状态设计"
                                     "（ESC 退出）")
        else:
            self.macro_notify_msg = "练习模式：可自由滑动，不计时"
        self.macro_notify_timer = 120
        return True

    def toggle_game_mode(self):
        """循环切换 练习 → 竞速 → 创造 → 练习（「模式」开关 / 谜题菜单入口）

        ⚠️ 跳过当前盘型进不去的档位（2026-10-26 用户报的真 bug）：模型文件
        板型不支持竞速，旧实现「练习 → 竞速」被拒后就原地不动，于是模式开关
        永远走不到创造——从玩家视角看就是「自造谜题进不了创造模式」，尽管
        set_game_mode('create') 本身是放行的。现在只把**允许的**下一档交出去，
        并在提示里点名跳过了谁，免得又是一次「按了没反应」。
        """
        order = ('practice', 'timed', 'create')
        try:
            idx = order.index(self.game_mode)
        except ValueError:
            idx = 0
        skipped = []
        for k in range(1, len(order) + 1):
            nxt = order[(idx + k) % len(order)]
            if not self.mode_allowed(nxt):
                skipped.append(self._mode_label(nxt))
                continue
            ok = self.set_game_mode(nxt)
            if ok and skipped:
                # set_game_mode 已写好「创造模式：…」这类正文，这里补一句
                # 跳档原因。失败时它自己已给理由（如计时中），别覆盖。
                self.macro_notify_msg += (
                    f"（本盘型不支持{'/'.join(skipped)}，已跳过）")
                self.macro_notify_timer = 150
            return ok
        # 三个模式全被拒：练习恒可用，走不到这里（留个兜底提示）
        self.macro_notify_msg = "当前盘型没有可切换的模式"
        self.macro_notify_timer = 120

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

