# -*- coding: utf-8 -*-
"""选块填空（pick_fill）混入：点「块+空位」再开算的那套交互。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第六步，
AutoSolve 整块再切一刀的第一刀）。pick_fill 是独立功能（Ctrl+A 触发，唯一有
前置交互的求解入口：先点块、再点空位才开算），与自动求解主管线
（gui/auto_solve.py 的 AutoSolveMixin）只是按钮并列关系，故独立成 mixin。
求解器调用均为函数内 late import，自包含。
"""
import threading
import time


class PickFillMixin:
    """选块填空（原 GUI.py 内联代码，整体搬迁）。"""

    def _pick_fill_form_blocked(self) -> bool:
        """选块填空的形态闸门：只有方形可用。

        点空位那条路（洞的命中判定）只覆盖方形；带序号 / 三角 / 米字进去了
        也只可能永远点不齐。所以**进选取态之前就明确拒绝**，别让玩家对着一个
        点不齐的选取态反复按 Ctrl+A。开算前再判一次是双保险（局面可能在
        选取途中被切换，届时建局收尾会清掉选取态，这里是兜底）。
        """
        if getattr(self, 'numbered', False):
            self.macro_notify_msg = "带序号模式暂不支援选块填空"
            self.macro_notify_timer = 90
            return True
        if getattr(self, 'triangle_mode', False):
            self.macro_notify_msg = "三角形密铺暂不支援选块填空"
            self.macro_notify_timer = 90
            return True
        if self._mi_blocked('选块填空', '求解器后续阶段开发中'):
            return True
        return False

    def _pick_fill_toggle(self):
        """选块填空按 Ctrl+A 的统一入口：进选取 / 齐了就开算 / 没齐就再按退出。

        按一次的语义取决于当前处在哪一步：
          · 没在选取 ── 进入选取态，提示要点的东西（右下角）；
          · 已在选取、但还缺点东西 ── 等同按了「停止求解」，退出；
          · 凸起与空位都点齐了 ── 开算。
        """
        if self._auto_solve_running:
            self._auto_solve_cancel = True
            return
        if self.macro_executing or self.animating:
            self.macro_notify_msg = "宏播放中，稍后再试"
            self.macro_notify_timer = 90
            return
        if self._pick_fill_form_blocked():
            return

        pf = self._pick_fill
        if pf is None:
            self._pick_fill = {'block': None, 'hole': None}
            self.macro_notify_msg = self._PICK_FILL_TIP
            self.macro_notify_timer = 200
            return
        if pf['block'] is None or pf['hole'] is None:
            # 没点齐就再按一次 Ctrl+A = 停止（与求解中按同一手感）
            self._pick_fill = None
            self.macro_notify_msg = "已退出选块填空"
            self.macro_notify_timer = 120
            return
        self._pick_fill_run(pf['block'], pf['hole'])

    def _pick_fill_missing_tip(self):
        """当前还缺哪一半——点错位置时照着这句话重提一次。"""
        pf = self._pick_fill
        if pf is None:
            return
        if pf['block'] is None and pf['hole'] is None:
            msg = self._PICK_FILL_TIP
        elif pf['block'] is None:
            msg = self._PICK_FILL_TIP + "（已选空位，还差点凸起方块）"
        else:
            msg = self._PICK_FILL_TIP + "（已选凸起，还差点一个空位）"
        self.macro_notify_msg = msg
        self.macro_notify_timer = 200

    def _pick_fill_click(self, x, y, block=None, gap=None):
        """选取态下的一次点击：只登记点选目标，绝不触发滑动 / 选缝 / 拖动。

        点方块 → 记下这一块；点空位 → 记下那个坑。点空白处**或点到缝隙**都
        算点错，重提一句还缺点什么，继续等 —— 缝隙说的是「从哪切开」，不是
        「填到哪去」，混进来会让这一步的意思含糊。
        """
        pf = self._pick_fill
        if pf is None:
            return
        if block is not None:
            loc = tuple(block.location)
            pf['block'] = loc
            # 坐标按玩家数数习惯：从 1 数第几行第几列
            self.macro_notify_msg = ("选块填空：已选方块（第%d行第%d列）"
                                     % (loc[0] + 1, loc[1] + 1))
            self.macro_notify_timer = 150
        elif gap is not None:
            self._pick_fill_missing_tip()
            return
        else:
            try:
                hole = self.get_hole_at_pos(x, y)
            except Exception:
                # 选空洞所用实现只覆盖方形；异常绝不许影响这次点击本身
                hole = None
            if hole:
                pf['hole'] = hole
                self.macro_notify_msg = (
                    "选块填空：已选空位（%s %d格）"
                    % (hole.get('type', ''), len(hole.get('cells', []))))
                self.macro_notify_timer = 150
            else:
                self._pick_fill_missing_tip()
                return
        if pf['block'] is not None and pf['hole'] is not None:
            self.macro_notify_msg = ("选块填空：已选好一对，按 Ctrl+A 开始"
                                     "（重按一次退出）")
            self.macro_notify_timer = 200

    def _pick_fill_run(self, p, hole):
        """开算一段：把玩家点选的凸起 p 送进点选的空位 hole。

        成功标准与其他算法不同 —— 只要求「这个空位被填上」，不要求整盘还原。
        推进权在玩家手里：反复「点一对 → Ctrl+A」才是它的正常节奏。
        """
        import threading
        import time
        from copy import deepcopy

        # 带序号 / 三角形 / 米字格沿用单段求解时期的封锁口径：这几类谜题
        # 要么没有「逐个凸起推进」的语义，要么对应通路还没接上。
        # （进选取态时已判过一次，这里是选取途中的兜底。）
        if self._pick_fill_form_blocked():
            self._pick_fill = None
            return

        # 局面可能已经变过（点选过程中玩家另行操作）：被指定为空位的那一簇
        # 若已不在当前空位列表里，就作废改由下层自动挑，别拿着过期坐标去算。
        vh = None
        if hole:
            from solver.ml.hole_detector import detect_holes
            _coords = frozenset((b.location[0], b.location[1])
                                for b in self.game.blocks)
            _region = getattr(self, '_target_region', None)
            if _region is None:
                _region = self._compute_target_region()
            try:
                _holes, _, _ = detect_holes(_coords, self.game.m, self.game.n,
                                            self.current_step, region=_region)
            except Exception:
                _holes = []
            _alive = next((q for q in _holes
                           if set(q.get('cells', []))
                           == set(hole.get('cells', []))), None)
            if _alive is None:
                self.macro_notify_msg = "刚才选的空位已不在局面里，改按最近自动配对"
                self.macro_notify_timer = 150
            else:
                _same = [c for c in _alive['cells']
                         if (c[0] - p[0]) % self.current_step == 0
                         and (c[1] - p[1]) % self.current_step == 0]
                vh = tuple(_same[0]) if _same else tuple(_alive['cells'][0])

        self._pick_fill = None
        self._auto_solve_result = None
        self._auto_solve_done = False
        self._auto_solve_running = True
        self._auto_solve_cancel = False
        self._auto_solve_start_time = time.time()
        self._auto_solve_progress = None
        self._api_solve_latch = None

        game_snapshot = deepcopy(self.game)
        step = self.current_step

        def cancel_check():
            return self._auto_solve_cancel

        def progress_callback(info):
            self._auto_solve_progress = info

        def solve_thread():
            try:
                from solver.ml.gap_solver import solve_single_segment
                solution = solve_single_segment(
                    game_snapshot, step=step, p=p, h=vh,
                    cancel_check=cancel_check,
                    progress_callback=progress_callback)
                self._auto_solve_result = solution
            except Exception as e:
                print(f"[选块填空] 出错: {e}")
                self._auto_solve_result = {
                    'type': 'fill_fail', 'reason': f'选块填空异常：{e}',
                    'solver_name': '选块填空'}
            finally:
                self._auto_solve_running = False
                self._auto_solve_done = True

        threading.Thread(target=solve_thread, daemon=True).start()

