> **受眾**：AI（用戶不參與維護）

# 可复用能力索引（CAPABILITIES）

> **目的**：AI 接任务前先扫一遍这里，确认 `solver/ gui/ game*/` 里是否已有能直接用的函数，
> 避免「没查就重写一个已有的工具」。本文件是**第一版人工索引**，随开发持续补充。
> 行号/签名以代码为准；函数名都是检索锚点，可直接跳代码核实。
> 配套红线见根目录 `agents.md` §6。

## 求解器核心（最易被重写，先查这里）

| 现成符号 | 用途（一句话） | 位置 |
|---|---|---|
| `profile_defect(coords, m, n)` | 行列剖面 L1 偏差，平移无关，**Φ=0 ⟺ 已还原（含转置）**；只排序用 | `solver/ml/invariants.py` |
| `is_solved_by_profile(...)` | **位置无关**还原判定（任意 m×n 矩形/转置都算） | `solver/ml/`（判定模块） |
| `find_best_window(coords, m, n, step)` | 全链唯一目标窗口基准（mod-aware 枚举 m×n / n×m） | `solver/ml/gather_solver.py` |
| `detect_target_corner` / `is_mod_compliant` | mod 不变量：预测窗口左上角 / 校验窗口兼容性 | `solver/ml/gather_solver.py` |
| `detect_holes(coords, m, n, step, region)` | 洞(hole)/缺口(dent)/凸起(protrusion) 语义，必须与 `find_best_window` 同 region | `solver/ml/hole_detector.py` |
| `auto_solve(game, ..., stage_cb=None)` | **多段播放**自动规划入口：查表/补缺宏/混合续算各段经 `emit_stage` 上报 `{label,actions,reps,end,score,phi,solved}` | `solver/auto_solver.py` |
| `_end_state(coords0, acts, reps, ...)` | 整链重放求最终坐标（续算必须从原点整链重放，别后缀单独重放） | `solver/auto_solver.py` |
| `ShapeGather` | 方形/异形**共用贪心骨架**（patience/aggressiveness 等常数原样复用） | `solver/ml/shape_gather.py` |
| `tri_placement.py` / `mi_placement.py` | 异形放置偏移域（mod 约束：`mod_auts` / `placement_offset_ok`） | `solver/ml/` |
| `enumerate_valid_actions` / `apply_action` | 动作语义枚举与应用 | `solver/actions.py` |
| `snapshot` / `restore` | 状态正规化与回放 | `solver/state.py` |
| `table_solve` | 查表求解（需先 `solver.data` 建表；**会原地移动传入的 game**，调用方务必 deepcopy） | `solver/table_solver.py` |

## 纯逻辑游戏模块（零 pygame 依赖，可被直接 import）

| 模块 | 关键类 / 表 | 用途 |
|---|---|---|
| `game.py` | `SliderMatrix`、`is_solved`、`try_move_ex(direction, step) -> (positions, reason)` | 方形纯逻辑；`reason` 含 `no_selection/bad_direction/collision/disconnected` |
| `game_triangle.py` | `TriangleSliderMatrix`、`DIRECTIONS`/`GAP_DIRECTIONS`/`DIRECTION_SCREEN` | 三角密铺纯逻辑（3 族缝、6 向） |
| `game_mi.py` | `MiSliderMatrix`、`lattice_of(key)` | 米字格纯逻辑（4 族缝、8 向、两晶格 A/B） |

> ⚠️ `game*.py` **不得引入 pygame**；交互代码只 import 它们的方向表/函数。

## 前端（动效必须三形态同时生效，见 `agents.md` §3）

| 现成符号 | 用途 |
|---|---|
| `gui/renderer.py` 的 `draw_board` / `draw_triangle_board` / `draw_mi_board` + `_game_dir_tables` | 三形态绘制与方向表取用（按形态从模块取，勿 getattr 实例） |
| `gui/metrics_panel.py` 的剖面缺陷行 | 调试面板三形态统一行（调用 `profile_defect`） |
| `gui/cell_class.py` | mod 着色类（step>1 才开，1 级退化见 `readme_to_agent.md` §2.1） |
| `test/_check_gap_annot.py` | 三形态动效验收脚本 |

## 控制通道（程序化驱动游戏，别自己造）

- **HTTP REST** `http://127.0.0.1:5050`（推荐）：`/status` `/move` `/select_gap` `/select_block` `/solve` `/analysis/*` 等，详见 `docs/agent/readme_to_agent.md` §6。
- **stdin CLI**：`status` `move` `select_gap` `solve` `solver_status` …（§7 全集），与 HTTP 1:1。
- 一次完整移动 = `select_gap` → `select_block` → `move`（三角可省略 `select_gap`）。

## 测量 / 测试纪律（易踩，先读）

- 微基准 ABAB 交替 + 逐轮配对（漂移 40% > 效应 14%）。
- 后台 hybrid/auto_solve stdout 黑洞 → 评测 `-u` + 落盘。
- 改求解器后至少重跑 `test/_test_mod_constraint.py` 与 `test/_test_gradient_pipeline.py`。
