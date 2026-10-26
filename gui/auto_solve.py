# -*- coding: utf-8 -*-
"""自动求解主管线混入：开算 / 梯度流水线 / 流式分段 / 阶段播放 / 结果落盘。

2026-10-14 从 GUI.py 拆出（纯搬方法，零逻辑改动；refactor-structure 第六步，
AutoSolve 整块再切第二刀；pick_fill 一家已先去 gui/pick_fill.py）。这是 UI 侧
最重的一块：_start_auto_solve 按空位数路由到各求解器（solver 调用均为函数内
late import），后台 worker 产结果，主线程泵（pump）逐段播放并实时刷新聚拢度。
模块级只补 queue/threading/time/traceback 四个标准库 import。
"""
import queue
import threading
import time
import traceback


class AutoSolveMixin:
    """自动求解主管线（原 GUI.py 内联代码，整体搬迁）。"""

    def _start_auto_solve(self):
        """启动/停止自动求解"""
        import threading
        import time
        from copy import deepcopy

        # 计时中禁止使用求解器
        if self._timer_blocked():
            self.macro_notify_msg = "计时中无法使用求解器"
            self.macro_notify_timer = 90
            return

        # 只读存档：禁止自动求解
        if self._readonly_blocked():
            return

        # 自造谜题（模型文件板型）：求解器只有方形 / 三角 / 米字三套语义，
        # 模型板型的缝族、朝向表、晶格都是 per-model 的，没有可用的求解器
        # ——明说「没有这个功能」，不要落到下面按算法名报一句含糊的拒绝。
        # 正在求解时放行（那条路径是「取消」，不能被拦）。
        if not getattr(self, '_auto_solve_running', False) and \
                self._model_blocked('求解器', '求解器只认方形/三角/米字'):
            return

        # 当前谜题形态不支持所选算法 → **明确告知并拒绝启动**。
        #
        # 旧行为是「静默自动切到 tri_gather / mi_gather」：用户看不到自己选的
        # 算法被换掉了，而且这等于给异形各留了一个专用入口。现在三形态共用
        # 'gather'（solver 内部按 game 类型分发），这里只负责把「该形态没有
        # 这个算法」讲清楚 —— 用户要的预期反馈就是这句
        # 「当前谜题没有 xxx 求解算法功能」。
        form = self._current_puzzle_form()
        from solver import solver_supports, unsupported_solver_msg
        if not solver_supports(self.solver_algorithm, form):
            self.macro_notify_msg = unsupported_solver_msg(
                self.solver_algorithm, form)
            self.macro_notify_timer = 150
            return

        # 标注录制中：自动回放不是人类示范，禁用
        if getattr(self, '_ann_recording', False):
            self.macro_notify_msg = "标注录制中无法使用自动求解"
            self.macro_notify_timer = 90
            return

        # 选块填空：列表里唯一要先收集玩家点选才能算的算法，因此在这里就转走
        # ——它有一段「等玩家点两下」的前置阶段，不该先把自己标记成「正在求解」。
        if self.solver_algorithm == 'pick_fill':
            self._pick_fill_toggle()
            return

        # 如果正在求解，則取消
        if self._auto_solve_running:
            self._auto_solve_cancel = True
            # API 状态锁存：记录取消时刻（/solver/status 判定 cancelled，elapsed 冻结）
            self._api_solve_latch = {
                'ok': False, 'steps': 0, 'reason': 'cancelled',
                'elapsed_ms': int((time.time() - self._auto_solve_start_time) * 1000)
                if getattr(self, '_auto_solve_start_time', 0) else None,
            }
            if getattr(self, '_gradient_state', None) is not None:
                # 梯度流水线：取消后台计算，丢弃已排队的结果
                self._gradient_state = None
                self._gradient_gen += 1
                self.macro_notify_msg = "梯度聚拢已停止"
                self.macro_notify_timer = 90
            elif getattr(self, '_auto_streamed', False):
                # 自动规划·流式：停后台段 + 恢复到历史最优态
                self._stop_auto_streamed(notify="自动规划已停止")
            return

        # 梯度播放中：再次点击 = 停止（终止后续阶段与后台计算）
        if self.macro_executing:
            if getattr(self, '_gradient_state', None) is not None:
                self._gradient_state = None
                self._auto_solve_cancel = True
                self._gradient_gen += 1
                self._api_solve_latch = {
                    'ok': False, 'steps': 0, 'reason': 'cancelled',
                    'elapsed_ms': int((time.time() - self._auto_solve_start_time) * 1000)
                    if getattr(self, '_auto_solve_start_time', 0) else None,
                }
                self.macro_notify_msg = "梯度聚拢已停止"
                self.macro_notify_timer = 90
            elif getattr(self, '_auto_streamed', False):
                # 自动规划·流式播放中：停后台段 + 恢复到历史最优态
                self._stop_auto_streamed(
                    notify="自动规划已停止（恢复到聚拢度最高态）")
            return

        self._auto_solve_result = None
        self._auto_solve_done = False
        self._auto_solve_running = True
        self._auto_solve_cancel = False
        self._auto_solve_start_time = time.time()
        self._auto_solve_progress = None
        # API 状态锁存：新一次求解开始时清空（供 HTTP /solver/status 结构化查询）
        self._api_solve_latch = None

        game_snapshot = deepcopy(self.game)
        algorithm = self.solver_algorithm

        # 梯度聚拢：启动后台流水线（各阶段连续计算，主线程并行播放动画）
        if algorithm == 'gather_gradient':
            from solver.ml.gather_solver import predict_params
            self._gradient_state = {'max_stages': 4}
            self._gradient_gen += 1
            gen = self._gradient_gen
            self._gradient_busy = True
            base_params = predict_params(game_snapshot, self.current_step)
            self._drain_gradient_queue()
            threading.Thread(target=self._gradient_worker,
                             args=(gen, game_snapshot, base_params, 4),
                             daemon=True).start()
            return

        # 自动规划（混合求解）：启动后台流式求解——各候选求解器算完一段即上报，
        # 主线程立即播放该段动画（同梯度流水线「边算边播」），并按历史最优
        # checkpoint 维护；取消时恢复到聚拢度最高态（多段播放设计哲学）。
        if algorithm == 'hybrid':
            import queue as _q
            from solver.state import snapshot
            from solver.ml.gather_solver import gather_metrics
            from solver.auto_solver import _phi_of
            coords0 = frozenset(tuple(b.location) for b in self.game.blocks)
            sc0 = gather_metrics(coords0, self.game.m, self.game.n)['score']
            phi0 = _phi_of(coords0, self.game.m, self.game.n)
            self._auto_stage_queue = _q.Queue()
            self._auto_stage_gen += 1
            gen = self._auto_stage_gen
            self._auto_stage_active = True
            self._auto_streamed = True
            self._auto_best = {'score': sc0, 'phi': phi0,
                               'snap': snapshot(self.game)}
            self._auto_solve_running = True
            self._auto_solve_cancel = False
            self._auto_solve_start_time = time.time()
            self._auto_solve_progress = None
            self._api_solve_latch = None
            threading.Thread(target=self._auto_stage_worker,
                             args=(gen, game_snapshot, self.current_step),
                             daemon=True).start()
            return

        def cancel_check():
            return self._auto_solve_cancel

        def progress_callback(info):
            self._auto_solve_progress = info

        def solve_thread():
            try:
                from solver import SOLVER_ALGORITHMS
                entry = SOLVER_ALGORITHMS.get(algorithm)
                if entry is None:
                    # ⚠️ 旧版这里写的是 `.get(algorithm, SOLVER_ALGORITHMS['ida_star'])`
                    # —— 未知/失效的 key 会**静默兜底成 IDA***：用户以为在跑自己
                    # 选的算法，实际跑的是 IDA*；而 IDA* 是纯方形语义（h/v 缝隙 +
                    # 整数坐标），落到异形 game 上直接抛异常。
                    # 2026-10-06 用户报的「list index out of range」正是这条链：
                    # config 里残留了已删除的旧 key 'mi_gather'。
                    # config 读取侧已有迁移（file_ops._migrate_solver_algorithm），
                    # 这里是兜底——宁可明确告知，也不要偷偷换个算法跑。
                    self._auto_solve_result = False
                    self.macro_notify_msg = (
                        f"求解算法「{algorithm}」不存在，请在设置里重新选择")
                    self.macro_notify_timer = 150
                    return
                alg_name, solver_func = entry
                kwargs = {}
                if algorithm == 'gather':
                    # 禁用的参数传 None（不设限）。三形态共用这一个入口，
                    # 参数一样要生效 —— 设置面板里的参数不该只对方形生效。
                    for k, v in self.gather_params.items():
                        kwargs[k] = v if self.gather_enabled.get(k, True) else None                # 填洞/补缺宏：流式播放——每解决一个 couple 即推送段
                if algorithm in ('fill_macro', 'gap_macro'):
                    import queue as _q
                    self._stream_queue = _q.Queue()
                    self._stream_active = True
                    self._stream_played = 0
                    # ⚠️ 必须置位：停止求解按钮按 `_auto_streamed` 分流，之前只有
                    # hybrid 置它，导致填洞/补缺宏流式播放中点「停止求解」毫无反应。
                    self._auto_streamed = True

                    def segment_cb(label, acts5):
                        seg_q = self._stream_queue
                        if seg_q is not None:
                            seg_q.put((label,
                                       [tuple(a) for a in acts5]))
                    kwargs['segment_cb'] = segment_cb
                solution = solver_func(
                    game_snapshot, step=self.current_step,
                    cancel_check=cancel_check,
                    progress_callback=progress_callback,
                    **kwargs,
                )
                if self._auto_solve_cancel:
                    self._auto_solve_result = False
                else:
                    self._auto_solve_result = solution
            except Exception as e:
                # ⚠️ 旧版只 `print(f"[自动求解] 出错: {e}")` —— 没有 traceback，
                # 用户只能看到一句「list index out of range」而完全无法定位
                # （2026-10-06 就是这样浪费了一轮排查）。异常类型 + 堆栈都要留。
                import traceback
                print(f"[自动求解] 出错: {type(e).__name__}: {e}")
                traceback.print_exc()
                self._auto_solve_result = False
            finally:
                if self._auto_solve_cancel:
                    # 取消/切盘：丢弃未播的残留段（旧盘面的段不能播到新盘面）
                    self._stream_queue = None
                self._stream_active = False   # 流式后台结束（pump 负责收尾）
                self._auto_solve_running = False
                self._auto_solve_done = True

        threading.Thread(target=solve_thread, daemon=True).start()

    def _drain_gradient_queue(self):
        """清空梯度流水线队列（丢弃过期结果）"""
        try:
            while True:
                self._gradient_queue.get_nowait()
        except Exception:
            pass

    def _gradient_worker(self, gen, snap, base_params, max_stages):
        """梯度流水线后台线程：阶段 k+1 的计算与阶段 k 的动画并行。

        sim 是求解私有的棋盘副本，从「上一阶段解完的构型」继续算下一阶段，
        不等待动画——动画只发生在主线程的真实棋盘上，二者互不冲突。
        """
        try:
            from solver.ml.gather_solver import gather_solve, stage_params

            def cancel_check():
                return self._auto_solve_cancel or gen != self._gradient_gen

            def progress_callback(info):
                self._auto_solve_progress = info

            for idx in range(max_stages):
                if cancel_check():
                    break
                p = stage_params(base_params, idx)
                r = gather_solve(snap, step=self.current_step,
                                 cancel_check=cancel_check,
                                 progress_callback=progress_callback, **p)
                if cancel_check():
                    break
                r = dict(r)
                r['gradient_stage'] = idx + 1
                r['gradient_total'] = max_stages
                self._gradient_queue.put((gen, r))
                # 该阶段无任何动作可播（且未复原）：与旧逻辑一致，整条流程到此为止
                if not r.get('actions') and not r.get('solved'):
                    break
                # 已复原或真正无法继续：不再安排后续阶段
                if r.get('solved') or r.get('reason') in (
                        'timeout', 'cancelled', 'no_candidates', 'invalid_action'):
                    break
        except Exception as e:
            print(f"[梯度流水线] 出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._gradient_queue.put((gen, None))  # 结束哨兵
            self._gradient_busy = False
            self._auto_solve_running = False

    def _pump_gradient_results(self):
        """把后台已算好的阶段结果，按序交给动画管道逐阶段播放。"""
        gen = self._gradient_gen
        while True:
            try:
                item_gen, item = self._gradient_queue.get_nowait()
            except Exception:
                return  # 队列暂时为空：后台仍在计算，继续等待
            if item_gen != gen:
                continue  # 过期项（取消/重开）：丢弃
            if item is None:
                # 后台全部算完且没有更多阶段：收尾
                self._gradient_state = None
                self.macro_notify_persistent = False
                return
            self._handle_gather_result(item)
            return

    def _stop_gradient_pipeline(self):
        """终止梯度流水线：手动改动棋盘会使已排队阶段失效，必须停止。"""
        if getattr(self, '_gradient_state', None) is None and not self._gradient_busy:
            return
        self._gradient_state = None
        self._auto_solve_cancel = True
        self._gradient_gen += 1
        self._drain_gradient_queue()

    # ---- 选块填空（原「单段求解」）：2026-10-12 从专用快捷键 Ctrl+G 收编进
    #      求解器列表，统一由 Ctrl+A 触发。它是列表里唯一需要先收集玩家点选
    #      的算法，所以开头多一段选取态。----
    _PICK_FILL_TIP = ("选块填空：请点选一个凸起方块和一个空位"
                      "（顺序不限；点空白处不算，会再提示一次）")

    def _pump_stream_segments(self):
        """流式求解（填洞/补缺宏）：把后台算好的段接进宏播放管道。

        后台线程在私有副本上继续算下一段，主线程把已就绪段追加到
        macro_exec_ops 播放——与梯度流水线同构（边算边播）。
        """
        seg_q = getattr(self, '_stream_queue', None)
        if seg_q is None:
            return
        active = getattr(self, '_stream_active', False)
        # 兜底：正常收尾靠线程 finally 把 _stream_active 置 False；只要这一步
        # 因异常/时序没生效，收尾就被永久跳过 → macro_executing 一直 True
        # （蓝色「执行宏」提示不消失，并锁住相机与停止按钮）。_auto_solve_done
        # 是线程结束的**独立证据**，与 active 取「或」，避免单点依赖。
        done = getattr(self, '_auto_solve_done', False)
        if (not active or done) and seg_q.empty():
            # 后台结束且无残留段：若处于流式等待态则收尾
            if self.macro_executing and not self.animating \
                    and self.macro_exec_index >= len(self.macro_exec_ops):
                total = self.macro_exec_index
                self.macro_executing = False
                self.macro_exec_ops = []
                self.macro_exec_index = 0
                # 与启动时置位配对：填洞/补缺宏也用了 _auto_streamed，收尾要清掉，
                # 否则残留会让「停止求解」分流到已结束的流式态。
                self._auto_streamed = False
                self.macro_notify_msg = ('[%s] 流水播放完成：%d 步'
                                         % (self.macro_exec_name, total))
                # 带序号模式：求解器只复原形状，数字乱序是预期行为，提醒玩家自行调整
                if getattr(self, 'numbered', False) and self.game.is_solved():
                    self.macro_notify_msg += '（形状已复原，数字排列未调整，请自行调整）'
                self.macro_notify_timer = 180
                self.center_map()
            return
        kicked = False
        while True:
            try:
                label, acts5 = seg_q.get_nowait()
            except Exception:
                break
            ops = []
            for a in acts5:
                op = {'gap_type': a[0], 'gap_line': a[1], 'side': a[2],
                      'direction': a[3], 'step': self.current_step}
                if len(a) > 4 and a[4]:
                    op['rep_cell'] = a[4]
                ops.append(op)
            if not ops:
                continue
            if self.macro_executing:
                self.macro_exec_ops.extend(ops)
                kicked = True
            else:
                self.macro_executing = True
                self.macro_exec_name = '填洞宏·流水'
                self.macro_exec_ops = ops
                self.macro_exec_index = 0
                self.macro_exec_factor = 1
                self._execute_next_macro_step()
            self._stream_played += len(ops)
            self.macro_notify_msg = '[流水] %s（+%d 步）' % (label, len(ops))
            self.macro_notify_timer = 120
        if kicked and self.macro_executing and not self.animating:
            self._execute_next_macro_step()

    # ---- 自动规划·流式（2026-10-10 多段播放改造）----
    def _auto_stage_worker(self, gen, snap, step):
        """后台线程：跑 auto_solve 并逐段上报；结束放哨兵 (gen, None)。"""
        try:
            from solver.auto_solver import auto_solve

            def cancel_check():
                return self._auto_solve_cancel or gen != self._auto_stage_gen

            def progress_callback(info):
                self._auto_solve_progress = info

            auto_solve(snap, step=step, cancel_check=cancel_check,
                       progress_callback=progress_callback,
                       stage_cb=lambda s: self._auto_stage_queue.put((gen, s)))
        except Exception as e:
            print(f"[自动规划·流式] 出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._auto_stage_queue.put((gen, None))  # 结束哨兵
            self._auto_stage_active = False
            self._auto_solve_running = False

    def _pump_auto_stages(self):
        """把后台算好的段接进宏播放管道（边算边播），并维护历史最优 checkpoint。"""
        q = getattr(self, '_auto_stage_queue', None)
        if q is None:
            return
        gen = self._auto_stage_gen
        # 仅在空闲（无动画、无宏播放）时推进 / 收尾，避免打断正在播的段
        if self.macro_executing or self.animating:
            return
        active = getattr(self, '_auto_stage_active', False)
        if not active and q.empty():
            self._finalize_auto_streamed()
            return
        try:
            item_gen, item = q.get_nowait()
        except Exception:
            if not active:
                self._finalize_auto_streamed()
            return
        if item_gen != gen:
            return  # 过期段（取消/重开）：丢弃
        if item is None:
            self._finalize_auto_streamed()
            return
        self._play_auto_stage(item)

    def _play_auto_stage(self, item):
        """播放一段动作并刷新历史最优 checkpoint（聚拢度最高、并列 Φ 最小）。"""
        label = item['label']
        actions = item['actions']
        reps = item.get('reps') or []
        end = item['end']
        score = item['score']
        phi = item.get('phi', 0.0)
        ops = []
        for i, a in enumerate(actions):
            op = {'gap_type': a[0], 'gap_line': a[1], 'side': a[2],
                  'direction': a[3], 'step': self.current_step}
            if i < len(reps) and reps[i]:
                op['rep_cell'] = reps[i]
            ops.append(op)
        # 无论是否有动作都刷新 checkpoint（空段仅记录终态）
        self._update_auto_best(end, score, phi)
        if not ops:
            return
        if self.macro_executing:
            self.macro_exec_ops.extend(ops)
        else:
            self.macro_executing = True
            self.macro_exec_name = '自动规划·' + label
            self.macro_exec_ops = ops
            self.macro_exec_index = 0
            self.macro_exec_factor = 1
            self._execute_next_macro_step()
        self.macro_notify_msg = ('[自动规划] %s（+%d 步，聚拢度 %.3f）'
                                 % (label, len(ops), score))
        self.macro_notify_timer = 120

    def _update_auto_best(self, end, score, phi):
        """刷新恢复点 checkpoint（播放恢复语义：播完/取消后回到哪）。

        择优规则 = solver.auto_solver.partial_better（单一真源，2026-10-15
        解耦修复）：修复前「并列取 Φ 最小」只在此处实现，与求解器
        keep_partial 的「只比聚拢度」不一致——headless 调用方拿到的
        fill_partial 并非同规则最优，且流式播放时求解器并列选中的段会被
        上报播放，GUI 只能在收到的段之间择优。现规则物理同源，此处只负责
        「恢复到哪」，不持裁判。函数内 import 零成本：调用发生在 auto_solve
        运行期，solver 包必已在 sys.modules。
        """
        from solver.auto_solver import partial_better
        best = self._auto_best
        if partial_better(score, phi,
                          best['score'] if best else None,
                          best['phi'] if best else None):
            self._auto_best = {
                'score': score, 'phi': phi,
                'snap': {'m': self.game.m, 'n': self.game.n,
                         'blocks': [tuple(c) for c in end]},
            }

    def _restore_auto_best(self):
        """把棋盘恢复到历史最优 checkpoint（设计哲学：打断停在聚拢度最高态）。"""
        if not self._auto_best or not self._auto_best.get('snap'):
            return
        from solver.state import restore
        restore(self.game, self._auto_best['snap'])

    def _stop_auto_streamed(self, notify=None):
        """停止流式求解：失效后台段、停动画（若在播）、恢复到最优态。

        hybrid 与填洞/补缺宏共用本函数，但两者用**不同的队列**，必须都清：
          · hybrid：_auto_stage_queue / _auto_stage_active
          · 填洞/补缺宏：_stream_queue / _stream_active
        旧版只清了 hybrid 那一套，填洞/补缺宏播放中点「停止求解」因此毫无
        反应（段照旧播、macro_executing 一直 True、相机也拖不动）。
        """
        self._auto_stage_gen += 1          # 使已在队列的段失效
        self._auto_stage_active = False
        self._auto_solve_cancel = True
        # 填洞/补缺宏：丢弃未播的残留段（设为 None 后 pump 直接 return）
        self._stream_queue = None
        self._stream_active = False
        if self.macro_executing or self.animating:
            self.macro_executing = False
            self.animating = False
            self.macro_exec_ops = []
            self.macro_exec_index = 0
            self.anim_blocks = []
        # ⚠️「历史最优 checkpoint」是 **hybrid 独有**的语义：只有 hybrid 会维护
        # _auto_best。填洞/补缺宏不维护它，若这里无条件恢复，就会把棋盘改写成
        # **上一次 hybrid 残留的旧 checkpoint**（_finalize_auto_streamed 并不清
        # 除它），表现为「点了停止，棋盘莫名其妙回到某个旧局面」。
        if getattr(self, 'solver_algorithm', None) == 'hybrid':
            self._restore_auto_best()
        self._auto_best = None
        self._auto_streamed = False
        self._auto_solve_running = False
        self._auto_stage_queue = None
        if notify:
            self.macro_notify_msg = notify
            self.macro_notify_timer = 180

    def _finalize_auto_streamed(self):
        """流式收尾：播放完成 / 求解结束，锁存结果并清空状态。"""
        total = self.macro_exec_index
        self.macro_executing = False
        self.macro_exec_ops = []
        self.macro_exec_index = 0
        self._auto_streamed = False
        self._auto_solve_running = False
        self._auto_stage_queue = None
        elapsed = (int((time.time() - self._auto_solve_start_time) * 1000)
                   if getattr(self, '_auto_solve_start_time', 0) else None)
        best = self._auto_best
        solved = bool(best and abs(best['score'] - 1.0) < 1e-6)
        self._api_solve_latch = {
            'ok': solved, 'steps': total,
            'reason': 'solved' if solved else 'partial_best',
            'elapsed_ms': elapsed,
        }
        if solved:
            self.macro_notify_msg = '[自动规划] 已复原：%d 步' % total
        else:
            self.macro_notify_msg = ('[自动规划] 完成 %d 步，停在聚拢度最高态 %.3f'
                                     % (total, best['score'] if best else 0))
        self.macro_notify_timer = 200
        # 清掉历史最优：不清的话它会残留到下一次求解，被停止逻辑误恢复
        self._auto_best = None
        self.center_map()

    def _check_auto_solve_result(self):
        """检查后台求解结果，如有结果则启动宏执行"""
        # 梯度流水线：后台连续计算，这里按序播放已就绪的阶段动画
        if (getattr(self, '_gradient_state', None) is not None
                and not self.macro_executing and not self.animating):
            self._pump_gradient_results()
            return
        if not self._auto_solve_done:
            return
        if self.macro_executing or self.animating:
            return

        # 计时中丢弃求解结果（禁止求解器帮助）
        if self._timer_blocked():
            self._auto_solve_done = False
            self._auto_solve_result = None
            return

        self._auto_solve_done = False
        result = self._auto_solve_result
        self._auto_solve_result = None

        # API 状态锁存：记录本次求解产物（供 HTTP /solver/status；梯度各阶段由
        # _handle_gather_result 覆盖更新，取消时无产物，状态判定由 cancel 标志负责）
        import time as _time
        _latch_elapsed = int((_time.time() - self._auto_solve_start_time) * 1000) \
            if getattr(self, '_auto_solve_start_time', 0) else None
        if isinstance(result, dict):
            self._api_solve_latch = {
                'ok': bool(result.get('solved', False)),
                'steps': len(result.get('actions', []) or []),
                'reason': result.get('reason', ''),
                'elapsed_ms': _latch_elapsed,
            }
        elif result is False:
            self._api_solve_latch = {'ok': False, 'steps': 0,
                                     'reason': 'no_solution', 'elapsed_ms': _latch_elapsed}
        elif result is None:
            self._api_solve_latch = {'ok': False, 'steps': 0,
                                     'reason': 'no_database', 'elapsed_ms': _latch_elapsed}
        else:
            acts = result[0] if isinstance(result, tuple) else result
            self._api_solve_latch = {
                'ok': True, 'steps': len(acts),
                'reason': 'already_solved' if len(acts) == 0 else 'solved',
                'elapsed_ms': _latch_elapsed,
            }

        if result is None:
            self._gradient_state = None
            self.macro_notify_msg = "自动求解：未找到数据库"
            self.macro_notify_timer = 180
            return

        if isinstance(result, dict) and result.get('type') in ('gather', 'gather_gradient'):
            self._handle_gather_result(result)
            return

        if isinstance(result, dict) and result.get('type') == 'fill_stream':
            # 流式求解收尾：贪心段已实时播过，这里只接「未播剩余」
            # （DFS 兜底 / 紧凑救援段）
            import time as _time
            _elapsed = int((_time.time() - self._auto_solve_start_time) * 1000) \
                if getattr(self, '_auto_solve_start_time', 0) else None
            streamed = int(result.get('streamed', 0))
            actions = result.get('actions', []) or []
            reps = result.get('rep_cells', []) or []
            solved = bool(result.get('solved'))
            self._api_solve_latch = {
                'ok': solved, 'steps': streamed + len(actions),
                'reason': 'solved' if solved
                else result.get('reason', 'streamed'),
                'elapsed_ms': _elapsed,
            }
            if actions:
                ops = []
                for i, action in enumerate(actions):
                    gap_dir, gap_line, side, move_dir = action
                    op = {'gap_type': gap_dir, 'gap_line': gap_line,
                          'side': side, 'direction': move_dir,
                          'step': self.current_step}
                    if i < len(reps) and reps[i]:
                        op['rep_cell'] = reps[i]
                    ops.append(op)
                if self.macro_executing:
                    self.macro_exec_ops.extend(ops)
                else:
                    self.macro_executing = True
                    self.macro_exec_name = '填洞宏·流水(续)'
                    self.macro_exec_ops = ops
                    self.macro_exec_index = 0
                    self.macro_exec_factor = 1
                    self._execute_next_macro_step()
            elif not solved and not self.macro_executing:
                reason = result.get('reason', '未全解')
                self.macro_notify_msg = ('流水播放 %d 步后停机：%s'
                                         % (streamed, reason))
                self.macro_notify_timer = 220
            return

        if isinstance(result, dict) and result.get('type') == 'fill_fail':
            self.macro_notify_msg = str(result.get('solver_name', '填洞宏')) \
                + '：' + str(result.get('reason', '失败'))
            self.macro_notify_timer = 220
            return

        if isinstance(result, dict) and result.get('type') == 'fill_partial':
            # 规则中断：播放已成功的部分动作，停在断点供用户观察
            reason = str(result.get('reason', '中断'))
            actions = result.get('actions', [])
            reps = result.get('rep_cells', [])
            ops = []
            for i, action in enumerate(actions):
                gap_dir, gap_line, side, move_dir = action
                op = {
                    'gap_type': gap_dir,
                    'gap_line': gap_line,
                    'side': side,
                    'direction': move_dir,
                    'step': self.current_step,
                }
                if i < len(reps) and reps[i]:
                    op['rep_cell'] = reps[i]
                ops.append(op)
            if not ops:
                self.macro_notify_msg = '填洞宏（断）：' + reason
                self.macro_notify_timer = 220
                return
            self.macro_executing = True
            self.macro_exec_name = '填洞宏（断：%s）' % reason
            self.macro_exec_ops = ops
            self.macro_exec_index = 0
            self.macro_exec_factor = 1
            self._execute_next_macro_step()
            return

        if result is False:
            self._gradient_state = None
            if self._auto_solve_cancel:
                played = getattr(self, '_stream_played', 0)
                self.macro_notify_msg = ('已停止（流水已播 %d 步）' % played) \
                    if played else '已停止'
            else:
                self.macro_notify_msg = "自动求解：未找到解法"
            self.macro_notify_timer = 180
            return

        if len(result) == 0:
            self.macro_notify_msg = "自动求解：已是复原状态"
            self.macro_notify_timer = 180
            return

        # 查表求解器返回 (actions, rep_cells) 元组，包含代表方块坐标
        rep_cells = None
        if isinstance(result, tuple):
            actions, rep_cells = result
        else:
            actions = result

        # 转换 solver Action → macro op
        ops = []
        for i, action in enumerate(actions):
            gap_dir, gap_line, side, move_dir = action
            op = {
                'gap_type': gap_dir,
                'gap_line': gap_line,
                'side': side,
                'direction': move_dir,
                'step': self.current_step,
            }
            if rep_cells:
                op['rep_cell'] = rep_cells[i]
            ops.append(op)

        # 通过宏执行管道播放解法（含动画）
        self.macro_executing = True
        self.macro_exec_name = "自动求解"
        self.macro_exec_ops = ops
        self.macro_exec_index = 0
        self.macro_exec_factor = 1
        self._execute_next_macro_step()

    def _handle_gather_result(self, result):
        """处理聚拢求解结果：播放动作，并实时显示聚拢度。"""
        actions = result.get('actions', [])
        rep_cells = result.get('rep_cells', [])
        solved = result.get('solved', False)
        reason = result.get('reason', '')
        # API 状态锁存（梯度逐阶段覆盖，终态以最后阶段为准）
        import time as _time
        _elapsed = int((_time.time() - self._auto_solve_start_time) * 1000) \
            if getattr(self, '_auto_solve_start_time', 0) else None
        self._api_solve_latch = {
            'ok': bool(solved), 'steps': len(actions), 'reason': reason or 'gather',
            'elapsed_ms': _elapsed,
        }
        # 记录梯度当前阶段（供 /solver/status 的 gradient.stage/total）
        gs = getattr(self, '_gradient_state', None)
        if isinstance(gs, dict):
            if result.get('gradient_stage') is not None:
                gs['stage'] = result['gradient_stage']
            if result.get('gradient_total'):
                gs['max_stages'] = result['gradient_total']

        # 停机原因播报
        reason_text = {
            'solved': '已还原',
            'target': '达到目标聚拢度',
            'no_improve': '停滞无改进',
            'max_steps': '步数上限耗尽',
            'timeout': '达到时间上限',
            'cancelled': '已取消',
            'stuck': '无新状态可探索',
            'no_candidates': '无可移动动作',
            'invalid_action': '动作无效',
            'stages_exhausted': '阶段耗尽',
        }.get(reason, reason or '完成')

        if not actions:
            # 无可播放动作 = 梯度流程到此为止（同时停掉后台流水线）
            if getattr(self, '_gradient_state', None) is not None:
                self._gradient_state = None
                self._auto_solve_cancel = True
                self._gradient_gen += 1
            if solved:
                self.macro_notify_msg = "聚拢：已是复原状态"
            else:
                self.macro_notify_msg = f"聚拢：无可移动动作（{reason_text}）"
            self.macro_notify_timer = 180
            return

        s, e = result.get('start', {}), result.get('end', {})
        sh, sw = s.get('bbox', (0, 0))
        eh, ew = e.get('bbox', (0, 0))
        gstage = result.get('gradient_stage')
        # 异形（tri）求解器返回的键名与方形不同：score 走 'score' /
        # 'best_score'，没有 start/end 两段指标。文案必须分形态写，
        # 否则会显示「聚拢度 0.0%→0.0%」这种假数字（同 11b 的教训：
        # 宁可少说，不要说错）。
        is_shape = 'start' not in result and 'score' in result
        if gstage:
            gtotal = result.get('gradient_total', 4)
            self.macro_notify_msg = (
                f"梯度聚拢 第{gstage}/{gtotal}阶段完成（{reason_text}）· {len(actions)}步 · "
                f"聚拢度 {s.get('score', 0)*100:.1f}%→{e.get('score', 0)*100:.1f}%"
            )
        elif is_shape:
            # 异形：只报能确定的量 —— 步数、终聚拢度、是否还原
            self.macro_notify_msg = (
                f"聚拢完成（{reason_text}）· 共{len(actions)}步 · "
                f"聚拢度 {result.get('score', 0)*100:.1f}%"
            )
        else:
            stages_info = ''
            if result.get('stages'):
                parts = []
                for st in result['stages']:
                    rname = {
                        'solved': '完成', 'no_improve': '停滞', 'stuck': '绕圈',
                        'max_steps': '步满', 'timeout': '超时',
                    }.get(st.get('reason', ''), st.get('reason', ''))
                    parts.append(f"{st.get('stage')}:{st.get('steps')}步({rname})")
                stages_info = ' · 阶段[' + '|'.join(parts) + ']'
            self.macro_notify_msg = (
                f"聚拢完成（{reason_text}）· 共{len(actions)}步 · "
                f"聚拢度 {s.get('score', 0)*100:.1f}%→{e.get('score', 0)*100:.1f}% "
                f"· 边界盒 {sh}×{sw}→{eh}×{ew}{stages_info}"
            )
        self.macro_notify_timer = 240

        ops = []
        for i, action in enumerate(actions):
            # 三角形是 5 元组（族, 线, 侧, 向, rep_key），方形是 4 元组。
            # rep 直接从动作里取，不再依赖 result['rep_cells'] 旁挂数组
            # （tri 求解器天然把 rep 固化进动作，計劃 §3 的要求）。
            if len(action) >= 5:
                gap_dir, gap_line, side, move_dir, rep = action[:5]
            else:
                gap_dir, gap_line, side, move_dir = action[:4]
                rep = None
            op = {
                'gap_type': gap_dir,
                'gap_line': gap_line,
                'side': side,
                'direction': move_dir,
                'step': self.current_step,
            }
            if rep is None and rep_cells and i < len(rep_cells):
                rep = rep_cells[i]
            if rep is not None:
                # rep 的第三分量是**米字格与三角形都必需的**：
                # mi 的位置是 (r, c, q)，同一个 (r, c) 上最多 8 块；三角的
                # 位置是 (i, j, up)，同一个 (i, j) 上正好 ▲▼ 各一块，而
                # **'n' 族缝恰好从这两块之间穿过**（gap_rank：▲=i+j、
                # ▼=i+j+1，线 L=i+j 时 ▲ 在 0 侧、▼ 在 1 侧）。只带前两
                # 分量的话 `_find_block_by_cell` 按「盘面里第一块」命中，
                # 可能从错朝向起 DFS → opt 选错侧 → 整步动作被静默改写
                # （回放表现为「解法播到一半走歪/某步不可移动」）。
                # ⚠️ 这不是理论风险：经典引擎块序把所有 ▲ 排在前面，恰好
                # 一直命中对的那块；几何引擎按键排序（down<up）后必挂
                # （2026-10-22 P3 观察期实测，G7b 复现）。方形的位置不含
                # 朝向分量，维持两分量。
                loc = list(rep)
                op['rep_cell'] = loc[:3] if (self.mi_mode
                                             or self.triangle_mode) else loc[:2]
            ops.append(op)

        self._gather_info = {
            'start': result.get('start', {}),
            'end': result.get('end', {}),
            'solved': solved,
            'reason': reason,
            'gradient_stage': gstage,
            'gradient_total': result.get('gradient_total'),
        }
        self.macro_executing = True
        self.macro_exec_name = "单次聚拢"  # 与设置-求解器页的算法名一致（2026-10-13 改名）
        self.macro_exec_ops = ops
        self.macro_exec_index = 0
        self.macro_exec_factor = 1
        self._execute_next_macro_step()

