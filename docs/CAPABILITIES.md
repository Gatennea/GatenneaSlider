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

> ⚠️ `solver/ml/` **分两块**：上表这些（含 `shape_gather` / `invariants` / `gather_solver` /
> `hole_detector` / `fill_macro` / `gap_solver` / `*_adapter` / `*_placement`）是**服役中的求解器核心**；
> 而 `train_*` / `features` / `export_*` / `annotate` / `ai_solver` / `human_solver` / `emd_solver` /
> `distance_solver` 属**已搁置的 ML 学习方向**（只剩参考价值，不再优化/重构/清理）。
> 划分与依据见 `solver/ml/__init__.py` docstring 与 `docs/agent/踩坑与搁置.md` §一。

## 纯逻辑游戏模块（零 pygame 依赖，可被直接 import）

| 模块 | 关键类 / 表 | 用途 |
|---|---|---|
| `game.py` | `SliderMatrix`、`is_solved`、`try_move_ex(direction, step) -> (positions, reason)` | 方形纯逻辑；`reason` 含 `no_selection/bad_direction/collision/disconnected` |
| `game_triangle.py` | `TriangleSliderMatrix`、`DIRECTIONS`/`GAP_DIRECTIONS`/`DIRECTION_SCREEN` | 三角密铺纯逻辑（3 族缝、6 向） |
| `game_mi.py` | `MiSliderMatrix`、`lattice_of(key)` | 米字格纯逻辑（4 族缝、8 向、两晶格 A/B） |
| `anchor_shuffle.py` | `AnchorPlanner`、`draw_candidates`、`reapply`、`select`、`rank`、`MAX_DRIFT` | 打乱序列规划：锚点=初始重心，偏移=Σ(块坐标−锚点) 的向量和（化简为坐标和之差），`MAX_DRIFT` 是**硬上限**（格，默认 1.0，过紧时至少留 1.25 个最小合法步；只有连续多次「候选全越界」才放一步打破僵局，放完立刻恢复），连续两步尽量不选平行缝，末尾几步把重心收回锚点。四套 `shuffle` 走 `select()`；**无限打乱**走 `rank()` 拿有序候选、按偏好逐个试提交，只借选步能力，不带有限次数/进度条/结束切屏，planner 跨帧存活、停止时清掉。`ENABLED=False` 退回旧随机路径。回归见 `test/_test_anchor_shuffle.py`、`test/_test_infinite_anchor.py` |

> ⚠️ `game*.py` **不得引入 pygame**；交互代码只 import 它们的方向表/函数。

## 前端（动效必须三形态同时生效，见 `agents.md` §3）

| 现成符号 | 用途 |
|---|---|
| `gui/renderer.py` 的 `draw_board` / `draw_triangle_board` / `draw_mi_board` + `_game_dir_tables` | 三形态绘制与方向表取用（按形态从模块取，勿 getattr 实例） |
| `gui/model_preview.py` 的 `request()` / `thumbs()` / `pump()` / `system_idle_ratio()` | 菜单悬停预览（复原态＋打乱态两张缩图）。磁盘缓存签名含内容哈希＋算法版本＋尺寸＋配色，**跨启动复用**；空闲预热由主循环每帧调 `_preview_pump()` → `pump()`：启动 1 秒后起常驻后台线程，按「游戏忙不忙 ＋ 系统 CPU 空闲率」逐个补齐菜单里**所有预设**（内置／模型／自定义样式），运行中新增档位或换主题会自动补算；悬停 `request()` 优先读盘、零等待。⚠️ `_preview_pump` 的 try 段必须在方法体内（2026-11-01 反缩进事故：方法只剩 docstring，预热一次都没跑）；回归见 `test/_test_model_preview.py` M 组 |
| `gui/metrics_panel.py` 的剖面缺陷行 | 调试面板三形态统一行（调用 `profile_defect`） |
| `gui/audio.py` 的 `AudioManager` | 音效（§S5，已实装出声）：5 個音效槽位 `slide/fail/solved/click/keyboard` + `bgm`（`mixer.music` 串流）；`sync_settings` 一次性推送总开关、音量与逐项槽位开关并起停 bgm。**滑动声在 `start_animation()` 之后由 `_play_slide_sound()` 触发**（普通移动/瞬时提交/撤销/重做/宏播放/打乱演示/无限打乱全出声）。⚠️**slide 素材是「單次魔方轉動聲」（70~165ms 事件音），不是持續摩擦噪聲**：`play_slide(步数, duration_ms)` 走 `PlayOneShot` 作法，直接播**一次原始採樣**，不拉伸、不循環、不拼接、不合成；動畫時長只用來換算速度→音量（越慢越輕），不決定聲音長度。前九輪把這「一下」撐滿動畫（循環／粒度拼接／無縫 loop／頻譜烙印成白噪聲）全錯，最後一種聽成砂紙聲，已全數刪除。聲音獨佔聲道 0，新手頂掉舊手不疊音。`click` 挂在 `handle_events` 全局左键（与涟漪同源）、`keyboard` 在 KEYDOWN 只登记、**KEYUP（松开）才出声**（2026-11-07 定，与键盘事件响应对齐；**动作音优先**：这次按键期间已有滑动声/拒绝声就不补按键声，打字/快捷键等没有动作音时才响；靠 `last_action_ms` 跨帧比对，组合键最多一声）。`fail` 槽位认别名 `reject.*`（2026-11-07 用户新增的「滑动被拒」素材），`play_fail` 独占声道 2 + 节流，长按被拒不重开头、不叠音；**一次交互只出一个声音**。设置页有独立的**「音频」Tab**：音效/背景音乐总开关 + **音效一览**（五类各一行，逐项开关 + 试听 + 素材名，缺素材标红）+ 两条 0~100 音量滑条。无素材/无头环境静默 no-op。素材放 `assets/audio/{sound,music}/`，档名弹性发现（bgm 取 `music/` 下 `bgm.*` 或第一个音频档、slide 取所有 `slide*.*`、solved 取 `solved.*` 或别名 `cheer.*`）。护栏见 `test/_test_slide_audio.py`（A1 播出物件＝原始样本 / A3 对照组 22 回 vs 实际 1~2 回 / B1 静态禁止合成代码回流）。**背景乐正式素材是 `assets/audio/music/bgm.ogg`（5.31MB）**：64.5MB WAV 已转 128k Vorbis，原始 wav 留本机当母带、不进库也不进包（`docs/spec/打包与发版.md` §4） |
| `tools/gen_boot_assets.py` | 离屏生成开机动画 24 帧 `assets/picture/boot/frame_*.png` 与启动图 `assets/picture/splash.bmp`。2026-11-07 换代：标题改**硬边像素字**（小字号 `antialias=False` + 最近邻整数倍放大；字形来自**开发机 Windows 系统字体**的绝对路径，英文 `consola.ttf`、中文 `simhei.ttf`，不是手绘点阵字库、不从 assets 读、不联网；只在重生成时用，运行时与打包版只读 PNG；缺中文字体时整行降级英文、绝不画方框）。背景从 `assets/picture/cover.png` 全屏图标换成游戏调色板的棋盘、空位随帧补齐（打乱→还原）；但 Logo 本身保留——从同一张封面线稿抠出主体，用 `Image.LANCZOS` 平滑缩放成浅色细线稿，作为**标题上方的独立小图标**。⚠️ 封面**不故意做像素风**（2px 颗粒化 + NEAREST + 蓝色硬描边缩到 148px 会糊成一团，2026-11-07 已去掉），像素风只留给标题字和棋盘背景；护栏 `_test_boot_animation.py::test_boot_cover_logo_not_pixelated` 静态钉住颗粒化 API 不回流 + 灰阶像素数 + 2×2 块化反向验证。所有字色/棋盘色/HUD 色都取自 `GUI.py` 的 `self.colors`（白主标题 / 亮蓝副标题 / 灰加载提示 / 蓝硬阴影），脚本不另造色相，改主题色两边要同步。`GUI.py::_paint_boot` 配套改成最近邻放大，别改回 `smoothscale`。护栏 `_test_boot_animation.py` 会核 Logo 真的画进帧、颜色确实来自游戏调色板、字体注释没写错。重生成依赖 pygame + Pillow + numpy（仅开发机） |
| `GUI.py::get_gap_at_pos` + `gui/move.py::_sq_click_query` / `_mi_click_query` | 缝隙命中带**按交互阶段分两套**（2026-11-07 修）：第一击选缝用精准带 `GAP_TOL_FIRST`=10 世界单位，另有「点偏进相邻块」的 ±28 宽兜底（三角/米字对放大值仍是空操作）；**已选中缝后的第二下**四种形态一律收窄到 `GAP_TOL_SECOND`=2（`get_gap_at_pos(..., tight=True)`，米字格在 `_mi_click_query` 里给 `gap_at` 同一常量）。原因：事件层 `if gap is not None` 优先于「点块」分支，两下共用一条带会让贴缝的滑块被判成「重新选缝」甚至直接取消选中。收窄后只有真压在缝线上才换缝/取消。⚠️ **例外**：捆绑「内部缝」语义是「点整组滑块」而非可选缝，不参与收窄——`events.py` 在收窄后用 `_internal_seam_at()` 按默认带把它单独捞回，交给 `_bi` 分支转成整组选块，否则点在内部缝附近既不命中缝也不命中块。常量在 `gui/board_view.py`；护栏 `test/_test_gap_second_step.py` 覆盖四形态完整事件流并含「撤掉收窄必须转红」的反向验证，`test/_test_bandage_click.py` 守内部缝例外 |
| `selection_animation_enabled` + `gui/renderer.py::_selection_visuals_enabled()` + `gui/events.py::_clear_macro_selection_if_disabled()` | 「选中动画」总开关（2026-11-07 修「求解器播放时关不掉」）：撤销/重做、打乱演示、求解/宏播放三路共用。⚠️ 宏播放每步写的 `selected_gap` + `be_opted` 是 `game.opt` / `try_move` / `commit_move` 的**功能状态**，不能为了关高亮直接删；正解是每步**用完再清**（无动画路径必须排在 `commit_move` 之后，动画路径排在 `start_animation` 之后），八个退出分支全接上，播放结束不留残留。求解演示的白色光边 `_play_head_border()` 不读这两个状态，由 `_selection_visuals_enabled()` 这个共用判据直接关。关掉后手玩点选的缝/块、滑动动画都不受影响。护栏 `test/_test_macro_selection_visuals.py`（像素级开/关对比、四形态、撤掉修复必须转红的反向验证） |
| `engine/cell_class.py` | mod 着色类 `cell_class` / `class_index`（step>1 才开，1 级退化见 `readme_to_agent.md` §2.1）。2026-10-30 从 `gui/` 下沉到 `engine/`（纯数学、零依赖，solver 也要用）；**`gui/cell_class.py` 只剩一行转发壳**，新代码一律指 engine |
| `test/_check_gap_annot.py` | 三形态动效验收脚本 |

## 控制通道（程序化驱动游戏，别自己造）

- **HTTP REST** `http://127.0.0.1:5050`（推荐）：`/status` `/move` `/select_gap` `/select_block` `/solve` `/analysis/*` 等，详见 `docs/agent/readme_to_agent.md` §6。
- `GET /version` 回报当前进程的版本号、git 短提交、启动时刻、运行秒数与关键源码短哈希（`code_hashes`）；怀疑「界面跑的不是刚改的代码」时先查它，改完源码要重启才会变。
- 只读 GET 免令牌（白名单见 `GET /help` 的 `public_readonly`）；写操作与 `GET /screenshot` 仍需令牌；「允许外部控制」关闭时一律 403，带了令牌的请求仍会校验。
- **stdin CLI**：`status` `move` `select_gap` `solve` `solver_status` …（§7 全集），与 HTTP 1:1。
- 一次完整移动 = `select_gap` → `select_block` → `move`（三角可省略 `select_gap`）。

## 工具链（改完跑一遍，别自己重写）

| 现成工具 | 用途 | 用法 |
|---|---|---|
| `tools/static_lint/` | 静态审查：未用 import / 重复函数体 / 反向依赖 / mixin MRO 遮蔽死方法。`--baseline` 出 NEW / RESOLVED diff，`--strict` 给 CI 守门（非零退出 = 新引入问题）。基线锚定 61 条已知签名（2026-10-31 修正假阳性后从 81 降到 61），详 `tools/static_lint/README.md` | `python -m tools.static_lint.runner --baseline tools/static_lint/baseline.json` |
| `tools/doclink_check.py` | 文档引用校验：扫 `.md` 里的文件引用（存在性）与「§X」节号引用（目标有没有这一节）。产出 file_ref / sec_ref / ambiguous / artifact_ref / known_broken 五类；`--strict` 只让**新引入的**断链让 CI 变红。当前存量问题登记在 `docs/agent/待办清单.md` §十六 | `python tools/doclink_check.py --baseline tools/doclink_baseline.json` |
| `tools/gen_feature_overview.py` | 从真源 `gui/feature_index.py` 重新生成 `docs/player/功能总览.md`（48 项）。改了功能索引后跑它，别手改产物 | `python tools/gen_feature_overview.py` |
| `tools/experiments_index.py` | experiments/ 索引生成 + 命名守门：`--emit` 重生成 `experiments/INDEX.md`（三类分组 + 被谁引用）；`--check` 用 AST 重新判定真实类别与文件名前缀比对，不符就非零退出（CI 已接）。改名/新增脚本后跑它 | `python tools/experiments_index.py --emit --check` |

> 本环境 `& python x.py` 不执行，须 `Start-Process -Wait`（见该 README 的沙箱段）。

## 测量 / 测试纪律（易踩，先读）

- 微基准 ABAB 交替 + 逐轮配对（漂移 40% > 效应 14%）。
- 后台 hybrid/auto_solve stdout 黑洞 → 评测 `-u` + 落盘。
- 改求解器后至少重跑 `test/_test_mod_constraint.py` 与 `test/_test_gradient_pipeline.py`。
- CI 的 test job **排除了 `test/_test_tri_gather.py`**（C3c k=5 0/8 是已知红，用户拍板保持现状），
  真护栏是同文件的 C3e（k=4 ≥ 5/10）。见 `docs/agent/待办清单.md` §十五——别把它当回归，也别为了让
  它变绿去调门槛。
