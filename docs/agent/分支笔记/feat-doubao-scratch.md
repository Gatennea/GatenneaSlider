# feat/doubao-scratch 分支笔记

> 受众：豆包（本分支归属 AI）+ 主目录巡检。只放「在办 + 未决发现」，完成随分支合并后清掉。
> 公共文件（待办清单 / agents.md / 实验索引）仍归主目录独占，本分支一律不改。

## 认领

- **§五十四 三维滑块扩展（正方体单元）**：2026-11-17 用户拍板交豆包，已认领、未排期。
  方案真源 `docs/spec/三维扩展方案_正方体单元_2026-11-17.md`（七节）；总账在 `docs/agent/待办清单.md` §五十四。
  本轮只接手、未动任何游戏代码。

## 动哪些文件（认领范围，防撞车）

按方案 §4 代码落点，六阶段涉及的文件列清；核心闭环第 1–4 步反复碰 `gui/renderer.py` 和
`gui/events.py`，**串行推到底，不按阶段分给多个 AI**：

- 第 0 步 建局/入口：`engine/adapter.py`（cubic 传 m/n/d）、`puzzle_types.py`（create_puzzle 加 depth、
  puzzle_key 加三维格式）、`GUI.py`（`_refresh_puzzle_presets` 加「三维 ▸」二级子菜单）、`gui/events.py`
  （子菜单分派核对 depth 传递）。
- 第 1 步 画出来：新增 `engine/cubic_view.py`（投影 + 深度排序）、`engine/cubic_camera.py`（四元数）；
  改 `gui/renderer.py` 的 `draw_board` 按 kind 分派。
- 第 2 步 六视角/旋转：`gui/events.py`（空白拖动→旋转、滚轮缩放、双击判定）、`gui/file_ops.py`
  （save/load_config 加一组三维相机字段）。
- 第 3 步 选中：新增 `gui/cubic_pick.py`（射线求交）；续改 `gui/events.py`。
- 第 4 步 真能玩：`gui/virtual_keyboard.py`（三轴六键）、renderer 加三维箭头、`engine/compat.py`
  注册 cubic 六向字母表。
- 第 5 步 历史：`history.py`（快照/动作扩到 (r,c,d)）、`gui/file_ops.py`（存档加深度 + type:cubic、
  按 type 读旧档），可能动 `gui/compressed_save.py`。
- 第 6 步 动画：`gui/animation.py`（渲染层偏移，不碰逻辑坐标）。
- 后期（求解器/创造/宏/防偏移）到那步再单独规划，不预判。
- **接口占位**：`gui/feature_index.py` 给功能加形态键、只登记已实现的；HTTP 的 `API_INDEX` 按实现进度
  逐条加、不铺空端点（`_test_external_control.py` 逐条断言）。

## 开工要点（主目录上一轮给的建议，落账备查）

1. **第一刀切第 0 步断点，它现在还在**：主目录 2026-11-17 实测 `create_adapter_puzzle('cubic',3,3,1)`
   仍抛 `TypeError: cubic_spec() missing 3 required positional arguments: 'm','n','d'`。
   先补 m/n/d 传参 + 菜单「三维 ▸ 1×1×1~3×3×3」入口；点进去报错也没关系，入口先于功能落地。
   保持显式报错，**禁止加「失败退化成二维」的兜底**。
2. **核心闭环不并行**：第 1–4 步几乎轮着改 `renderer.py`/`events.py`，文件高度交叠，按
   「同一件事只给一个 AI、尽量不并行」一个 AI 串行推到底。真正能并行的只有边界清楚的小块
   （如独立的 `cubic_camera.py`），且按文件交叠判、不按编号分。
3. **认领占位写清动哪些文件**（见上一节），不只是「认领 §54」——§43 两个 AI 各写一版白写回退的教训。
4. **验收先过第 1 步遮挡关**：几个立方体摆成小长方体，标准视角下前挡后、三面朝向、凹坑可见，
   肉眼验过再写拾取；这步不过后面全搭在空中。
5. **测试按 §9.2 分级，本机别跑全套**：全套 20–35 分钟且 CI 自动跑；本机只做 grep 旧 API 残留 +
   `pytest --collect-only` + compileall + 三项 lint + 受影响 `-k`。基线 4 红是既有的、别改门槛；
   三维新测试用 `_test_cubic_*.py`。
6. **API 安全点**：求解器接上前 `/solve` 和 `/solver/*` 对三维明确回「不支持」，不拿二维求解器硬算；
   新增端点同步 `API_INDEX`/`HELP_DETAILS`/分派三处。

## 未决 / 发现（开发中随手记）

### 2026-11-17 第 0 步（建局与入口）已落地

完成内容（分支内已提交，未推送）：

- `engine/adapter.py`：`create_adapter_puzzle(..., depth=None)` 新增 `depth`；
  `kind=='cubic'` 走 `cubic_board(m,n,d)`，**缺 depth 直接 `TypeError`**，
  不退化成二维/单层；`EngineGame` 记 `self.depth`（**不挂 `k`**，否则
  `history.restore_snapshot` 会把它误判成三角 2-bit 矩阵）；`goal_cells()`
  补 `(r,c,d)` 三元组分支。
- `puzzle_types.py`：`puzzle_key` / `create_puzzle` 加 `depth`（keyword-only），
  三维分榜键 `f'{step}~cubic{m}*{n}*{d}'`——缺 depth 的键显式报错，避免
  3×3×2 与 3×3×5 共榜/共存档识别。
- `GUI.py`：`new_cubic_puzzle(m,n,d,step)`（参数校验失败给 `macro_notify_msg`，
  不静默 False）；一级菜单「三维谜题 ▸」+ 子菜单
  `puzzle_sub_presets['cubic']`（条目比二维多一位 depth）；
  `cubic_mode` 旗标（二维三条建局路径都会清掉）；`_cubic_blocked()` 并接入
  `_form_blocked()`，求解器等入口对三维明确拒绝。
- `gui/events.py`：谜题菜单两处分派（一级 + 二级）加 `kind == 'cubic'` 分支。
- `gui/renderer.py`：`draw_board` 加三维分支 → `draw_cubic_board()` 只画
  「三维视图尚未接入」明示，**不顺二维分支画 m×n 扁平盘**。
- `gui/session.py` / `records_panel.py` / `speedrun.py`：`puzzle_key` 调用补
  `depth`；`_current_puzzle_label` 报「三维 m×n×d 等级 s」；Ctrl+R 重建加
  cubic 分支（漏了会变「模型不可用」）。
- `test/_test_cubic_entry.py`（新）：28 项，含「真点菜单 → 真建出 3×3×3」的
  端到端点击，以及缺 depth 报错、分榜键、占位渲染不崩、求解拦截。

验收通道：`D:\python\python.exe test\_test_cubic_entry.py`（28/28）。
回归：`_test_engine_adapter` / `_test_engine_gui` / `_test_menu_redesign` /
`_test_mi_gui` / `_test_model_registry` / `_test_shatter_gui` /
`_test_external_control` / `_test_feature_index` / `_test_command_palette` 全绿；
`tools.static_lint.runner` 无新增（产品代码未用 import 仍 0、`dup_body` 14 项）。

### 2026-11-17 第 1 步（投影渲染）已落地

- 新增 `engine/cubic_camera.py`：四元数姿态（`FACE_BASIS` 六正对视角 =
  三轴×两侧 + 规范 roll）；`from_yaw_pitch` 给默认斜视（yaw −32° / pitch 24°，
  三面可见）；`nearest_face_view()`（按相机 z 轴点积吸附）、`slerp`、
  `rotated(axis, deg)` 都先备好，第 2 步直接接线。
- 新增 `engine/cubic_view.py`：世界映射 `X=c / Y=d / Z=r`；背面剔除 +
  相邻块内部面剔除 + 画家排序（面心深度升序，远景先画）；`fit_view` 按相机空间
  包围盒装画面；`build_scene` 一步返回 `faces/scale/origin`。纯数学，不 import
  pygame。
- `gui/renderer.py::draw_cubic_board` 从佔位换成真渲染：面填「滑块基色 × 明暗」
  + 描边，选中块整片用 `block_selected`（状态仍靠颜色，不新增填充语义）；
  左上角一行「三维 m×n×d 等级 s　斜视预览」。行放顶部是因为底部整条被
  `draw_status_bar` 覆盖（放下面等于没画，首版截图已中招）。
- `GUI.new_cubic_puzzle` 建局时给 `self.cubic_camera = oblique_default()`、
  `self.cubic_zoom = 1.0`。
- 新增 `test/_test_cubic_view.py`（41 项）：六视角 z 轴、正对 9 面、斜视 27 面、
  顶视 +Y、内部面/背面剔除、前块深于后块且投影完全重叠、单块正投影是正方形。
- `test/_test_cubic_entry.py` 加 D2：3×3×3 整帧至少 3 级明暗、背景不糊、
  正对视角不崩（现 31 项）。
- 肉眼验（截图存 workspace `cubic_shots/`，不入库）：实心 3×3×3 三面正确；
  前排正中抠两格深坑 → 内部地板与侧壁可见；挖掉内核从外面看不到（正确）。

### 2026-11-17 拆分 = 渲染距离（第 1 步内补做）

**术语纠正**：用户口径「拆分 = 两个相邻滑块的**距离**」，即方案 §2.4「块按各自
质心往外散」的渲染参数；滑条本身排在「渲染选项 GUI」那一阶段。上一轮把它当成
棋局打乱去做（打乱 + 状态行），**跳步了**——那批代码按用户要求保留不回退，但
口径以下面这条为准。

- `engine/cubic_view.py` 加 `gap`：每块三轴各向内收 gap/2，于是相邻表面之间
  正好空出 gap；`gap=0` = 贴死（未拆分）。`DEFAULT_GAP = 0.12`（肉眼调的默认，
  滑条接入时再定档）。
- **`gap>0` 不再剔除「内部面」**：缝隙能看见邻块那一面，还按邻块存在就删会
  出现「该有的面缺失」的漏块感；只有 `gap=0` 才按邻块剔除。
- `fit_view` 按缩放基准含 gap，拉大拆分时画面不跳；`gap` 越界（<0 或 ≥1）显式
  `ValueError`，不静默裁剪。
- `gui/renderer.py`：三维分支传 `self.cubic_gap`（缺省取 `DEFAULT_GAP`），
  左上状态行改成「拆分 0.12（0 = 贴死）」，不再拿 `is_solved` 冒充拆分；
  `GUI.new_cubic_puzzle` 建局写入 `cubic_gap`，提示文案同步。
- 新增 `test/_test_cubic_gap.py`（18 项）：gap=0 → 27 外表面且内部面被剔除；
  gap>0 → 每块 1-gap 边长、相邻距离 = gap、面数 81、内部面保留、深度升序、
  正视 27 个正脸；gap 越界报错；GUI 默认非零拆分、整帧可画、拉到 0 也不崩。

**顺手修的自造坏档（第 0 步的副作用，已记录）**：三维局退出时会把
`type:cubic` 写进 `config/temp_history.json`，下次启动报「存档需要模型
'cubic'」。按编辑器同一条先例（`_med_active` 跳过写）在 `save_config` 里
`cubic_mode` 也不写 temp_history，等第 5 步存档扩到 (r,c,d) 再开。
副作用：**仓库里那份 temp_history 现已被写脏一次**（现有内容 = cubic 3×3
等级2），下次启动会有一句加载失败提示，正常退出即被合法局面覆盖（自愈）。
需要我代写一份干净默认局就说一声。三个 cubic 测试已加 `config_dir` 隔离，
不再碰仓库那份。


### 2026-11-17 第 2 步：六朝向 + 旋转 + 缩放（相机分组存 config）

**用户口径纠正**：我先前记的「正对视角天然扁平」被当场否掉——**六个朝向都不该
正对**。正对时实心 3×3×3 在屏幕上就是一张二维 3×3，深度全靠猜；所以六朝向
一律带固定倾斜，露邻面细边。

- `engine/cubic_camera.py`：`FACE_VIEW_LABELS` + `FACE_VIEW_ANGLES` 改
  `DEFAULT_VIEW_RESIDUE = (14°, 14°)`（绕原始 up 轴偏、再绕原始 right 轴抬，
  三根基矢量走同一个复合旋转 R=Rx·Ry，保证正交）。`face_view_rotation()`
  返回姿态；`CubicCamera.spin(axis, deg)` 直接转三根基矢量（不再用
  `dq·q`/`q·dq` 猜乘法顺序，符号不会翻）；保留 `decompose()` 备用。
- **姿态的唯一真源 = 四元数**（`self.cubic_camera`）。不另存 yaw/pitch：两处
  口径迟早打架，而且上一步实测过 Euler 在极点会退化。状态行只显示视角名。
- `gui/events.py` 新增 `_cubic_*` 一族：`_cubic_view(i)`（1–6 键）、
  `_cubic_view_oblique()`（0 键）、`_cubic_drag_begin/_cubic_drag_update`
  （横拖绕世界竖轴、竖拖绕相机右轴，**极点 1° 保护**）、`_cubic_zoom_by`
  （Ctrl+滚轮，夹在 0.5–3.0）。
- **旋转与选中互斥**：三维棋盘上左键只起「旋转」，点击分派在建局早期就
  `continue`，不会走二维的选缝/选块。第 3 步再在这里分派射线求交。
- `gui/file_ops.py`：`config.json` 加 `cubic_camera{quat, zoom, gap, view}`，
  二维 `camera_x/y`/`zoom` 原样保留（按形态分组，互不覆盖）；读档只记数值，
  建三维局时才套用（二维局不受影响）。
- `gui/renderer.py`：状态行两行——第一行「三维 m×n×d 等级 s / 视角 / 缩放 /
  拆分」，第二行操作提示（拖动旋转 · 1–6 · 0 · Ctrl+滚轮）。
- 新增 `test/_test_cubic_view_nav.py`（83 项）：六朝向都非正对、倾斜量一致、
  主面边沿≈屏幕横竖、每朝向 81 面且主面正确、六图互不相同；事件队列真拖
  100px → −45°、极点保护、拖完不选中不入历史；Ctrl+滚轮只动 `cubic_zoom`；
  1–6/0 键位；config 往返；六朝向整帧都能画。
- lint 一条要说明：`_cubic_view` 的提示文案引用 `DEFAULT_VIEW_RESIDUE`，它是
  元组了，格式化必须 unpack（写 `:.0f` 会 TypeError，事件循环会把它吞成
  「Event error (non-fatal)」——测试已覆盖该行）。

留给下一步的口径：

- **画面「规整」的极限**：两轴偏角是复合旋转，主面边沿会有约 1.5° 的轻微斜度
  （严格让两条边都贴屏幕横竖只能单轴旋转，那只剩两面可见）。1.5° 视觉上读作
  规整，等第 3 步用户实际拖动后再决定要不要改单轴大角度。
- 缩放目前只有 Ctrl+滚轮；右面板「缩放」滑条仍只改二维 `self.zoom`，
  三维面板接线在第 3 步（渲染选项那阶段加拆分/缩放滑条）。

### 2026-11-17 打乱路径（**跳步**，按用户要求保留不回退）

> 这批不属于第 1 步（打乱是第 4 步「真的能玩的起步」的事），2026-11-17 被
> 用户当场点出跳步。代码保留不删，口径一律以「拆分 = 渲染距离」那节为准；
> 这里只作为第 4 步的现成地基留着。

用户指出：**拆分 = 相邻块之间让出空位**；距离 0（还原态）时块贴死成一整块，
投影上只有一层外轮廓，前块挡后块根本看不出来——所以「能画出来」必须含
「拆分态画得对」。

- 结论：三维的拆分**不用新造机制**。引擎 `EngineGame.shuffle`（adapter.py）
  本来就走三维（`cubic_spec` 有 6 方向 / 3 縫族 r·c·d），`try_move` / `opt` /
  缝枚举全部维度无关；GUI 的 `shuffle_puzzle` 也没有形态闸门。
  实测 3×3×3 等级2：`shuffle_puzzle(confirm=False)` → 14~16 步、聚拢度 0.43、
  c/d 摆到 −2..4，块间让出空位。
- 三维**仍是「建局=还原态、Alt+S 打乱」**（与二维/三角同口径）——不擅自改成
  建局即打乱。
- 渲染层左上状态行当时按 `is_solved` 报「已拆分/未拆分」——**口径错了**（拆分
  是距离不是打乱），已在后一节改写成「拆分 0.12（0 = 贴死）」。
- 新增 `test/_test_cubic_split.py`（25 项）：未拆分恰好 27 个外表面且 `max(loc)==2`
  （内部块零露面）；打乱后不再还原、块数守恒、出现盒外坐标、聚拢度 < 1、记录非空；
  拆分态面数 > 27、深度升序仍成立、内部面仍剔除、三面明暗俱在、确有重叠面且
  远的先画；GUI 全路径（动画开着打乱 → 演示自行收尾 171 帧 → 拆分态整帧不崩）。
- 已肉眼验：拆分态实拍截图（`cubic_shots/gui_shuffled_cubic.png`）— 遮挡关系清楚。

留给下一步的口径：

- 三维**还没有拾取/六向操作/拖动旋转**，所以拆分态只能「看」，不能玩；
  第 2–4 步接上之后这盘才真正可交互。
- 右面板「缩放」滑条仍只改二维 `self.zoom`（三维用 `cubic_zoom`），面板接线在
  第 3 步；这一步别让它假装能拉。
- **正对视角天然扁平**：identity 下整块 3×3×3 与二维 3×3 长得一样；六视角必须
  定「正视仍看得出是三维」的补偿口径（轻斜视 residue 还是侧壁描边）。
- 「建局即打乱」是否要做成三维专属开关，等用户定；这轮按二维同口径保守处理。




## 第 3 步：能正确选中（单击切面 / 双击选中一侧）

- 新增 `engine/cubic_pick.py`（纯计算，不 import pygame）：`point_in_quad` /
  `hit_face` / `face_is_internal` / `seam_of_face` / `seam_plane_polygon` /
  `block_at_location`，外加两张映射表（`AXIS_TO_LOC_INDEX`、`AXIS_TO_FAMILY`）。
- **正中投影 → 不用解射线方程**：`cubic_view.project_point` 是正交投影，屏幕点与
  可见面是一一映射，所以「射线求交」退化成「对画家序倒着做点在凸四边形内测试」。
  好处是命中与画面**同源**：渲染层把这一帧的 scene 存进 `self._cubic_scene`，
  点击直接测那一份面，不存在「看得见点不中」的漂移。
- 面 → 缝的口径：面两侧是块 v 与 v+sign，缝线号取序号小的一侧（v / v−1），
  再用 `game.is_valid_gap(family, line)` 验；不成立就退回另一条相邻线，仍不成立
  返回 None（外沿面点上去就不硬选）。世界轴 → 逻辑坐标的映射沿用
  `cubic_view` 的 X=c / Y=d / Z=r：axis0→c(idx1)、axis1→d(idx2)、axis2→r(idx0)。
- `seam_plane_polygon` 固定坐标 = `line + 1`（与引擎 `_line_to_t` 同一口径），
  另外两轴取块的包围盒。pad 默认 **0**：一开始给 0.5，白线成了悬在棋盘外的一圈
  框（截图里明显「浮着」），改成 0 后白线正好压在棋盘轮廓上。
- 交互分派：**左键按下先当成可能的拖动，松手时看有没有真移动**（阈值 4px，
  `cubic_drag_moved`）。移动过 = 旋转收尾；没移动 = 一次点击。单击只设
  `selected_gap`（预览、不入历史、不产生步数）；双击（300ms + 8px 容差，pygame
  没有原生双击）才 `game.opt(family, line, block)`，选中该切面一侧的连通组。
  右键清空预览与选中。
- **正向化闸门**：`cubic_view_index is None`（斜视 / 自由旋转）时点击只提示
  「旋转态只看不选：按 1–6 回到一个朝向再选」，不选任何东西——方案 §2.2 的
  互斥口径。六朝向本身带 14° 偏角，闸门按「是不是某个朝向」判，不按「是否轴对齐」判。
- 渲染：`draw_cubic_board` 画完面之后存 scene，再画一层白线切面（`selected_gap`
  属于 r/c/d 才画）；状态行第二行补「单击选切面 · 双击选中一侧 · 右键取消」。
- `GUI.new_cubic_puzzle` 补 `cubic_drag_moved / cubic_drag_start / cubic_drag_from /
  _cubic_scene / _cubic_last_click_*` 初值，避免上一局的三维点击态漏到下一局。
- 新增 `test/_test_cubic_pick.py`（204 项）：四边形命中/边界/越界；3×3×3 拆分态
  81 片、面心命中最近那片；前后两块重叠区命中前块；每一片可见面都给出有效缝且
  落在六条有效线上；外表面退回相邻线、无有效线返回 None；预览平面固定坐标 =
  line+1 且是矩形；GUI 全路径——单击出预览（步数/历史不动）、双击选中的 9 块与
  引擎 `opt` 独立算出的组逐一同、拖动松手不选、旋转态点击不选、右键清空。
- 回归：`_test_cubic_pick` 204、`_test_cubic_view` 41、`_test_cubic_view_nav` 83、
  `_test_cubic_gap` 18、`_test_cubic_entry` 31、`_test_cubic_split` 25、
  `_test_menu_redesign` 56、`_test_external_control`、`_test_engine_gui` 全过；
  改动文件无新增 lint（pyflakes 报的都是既有历史项）。
- 肉眼验收截图（未入库）：`cubic_shots/pick_single_plane.png`（白线切面）、
  `cubic_shots/pick_double_selected.png`（一侧 9 块整片变绿）。

留给下一步的口径：

- 单击现在只出**一张**切面平面；「选中后能滑动、虚拟键盘六键、箭头重画、判胜」
  是第 4 步（真能玩的起步）。
- 双击时间窗与旋转灵敏度目前是类常量（`CUBIC_DOUBLE_CLICK_MS` 等），方案 §2.4
  要求它们将来进设置页「三维」专页的声明式配置表；这一步先不拆表。
- 尚未接：拆分滑条进右侧栏、透明度、明暗/透视（§2.4，属渲染选项阶段）。
- `_test_cubic_pick.py` 的 GUI 段依赖 `draw_cubic_board` 先跑一次（拾取用渲染
  存的 scene）；若将来渲染改为按需缓存，测试与事件都要跟着改成显式 build。

## 第 4 步（上半）：三轴六向能推 + 判胜 + 打乱

- `engine/compat.py`：注册 `CUBIC_DIRECTIONS = {r,R,c,C,d,D}`（大写沿轴增大）。
  不注册会派生 A~F，能滑但不直观。⚠️ 小写 r/c/d 与缝族同名——`_gap_family_of`
  先认族名，所以 cubic 上「往 opt 里传方向字母」不成立；GUI 的 opt 只传族名，
  字母只在 `_build_action` 查表用，这条写进注释免得以后误用。
- `gui/events.py`：新增 `_cubic_move_key`（r/R c/C d/D），接在 KEYDOWN 的
  `_cubic_view_key` 之后。三条闸门：带 Ctrl/Alt 不消费；旋转态不响应滑动只提示；
  没选中只提示「先双击选中」。移动直接走现成的 `move_selected_blocks`，所以步数、
  快照、动画开关、判胜判定全部复用，没有另起一套。
- `gui/move.py`：`_dir_name` 补 cubic 六字母 → `r+/r−/c+/c−/d+/d−`，提示不再出现
  「向c移动」这种半截话。
- **撤销/重做在三维下明确拒绝**（`gui/history.py`）：实跑发现 `undo()` 会把快照里
  的二元位置喂给 `_norm_keys` 直接抛 `ValueError: 含非法位置 (0, 0)`——历史扩到
  (r,c,d) 是第 5 步的事。按「接口占位不写空骨架」，这一步先给一句
  「三维撤销是第 5 步」的明示，不让它半崩。
- 新增 `test/_test_cubic_play.py`（32 项）：字母表与 spec 六向双射、单轴单位向量；
  双击选中 → 按 c 推一步（整组沿 c−1、块数守恒、步数 +1、提示带 c−、is_solved 转假）；
  大写 C 推回（重新还原）；旋转态按键不推、没选中按键不推且不涨步数；undo/redo 被拒
  且位置不变；打乱后 27 块、非还原、渲染仍有可见面、步数清零。
- 回归：`_test_cubic_play` 32、`_test_cubic_pick` 204、`_test_cubic_view_nav` 83、
  `_test_cubic_gap` 18、`_test_cubic_entry` 31、`_test_cubic_split` 25、
  `_test_geometry_engine`、`_test_menu_redesign` 56 全过。
- 截图：`cubic_shots/step4_shuffled.png`（3×3×3 打乱后的三维云团，深度可读）。

本步**还没做**（下一片接着做，别当成已完成）：

- **虚拟键盘三轴六键**（`gui/virtual_keyboard.py`）：现在只能键盘推，鼠标玩家还没
  按钮可按；「没选中时点六键 = 平移盘面」也一并留到那片。
- **重画箭头**：三维的六向箭头还没画，二维箭头在 cubic 下不出。
- 撤销/重做要等第 5 步把快照扩到 (r,c,d)（`history.py` + `file_ops.py` + 压缩存档）。

## 修：旋转时「画面忽大忽小」+ 右侧缩放滑条接三维

用户 2026-11-17 实测指出（这是真机反馈，不是测试能发现的）：拖动旋转时整个立方
**大小在跳**。根因是我第 1 步用的 `fit_view` —— 它按**当前朝向的投影包围盒**拟合
画面，一旋转投影包围盒就变，scale 跟着变，看起来像镜头自己在推拉。

- `engine/cubic_view.py` 新增 `stable_frame`：比例只由几何本身的**包围球半径**定
  （任何朝向下都不变），中心固定为包围盒中心投影到屏幕中心。
  `build_scene` 改用 `stable_frame`；`fit_view` 保留（斜视默认构图/测试仍在用），
  但在 build_scene 里不再承担职责，函数头注释写清为什么换。
- 实测：0/20/40/60/80/100° 六张 scale **完全相同**（94.621），屏幕跨度仍随朝向变
  ——变的是投影范围，不是比例；缩放只由 zoom 决定（zoom 2 → scale ×2，zoom 3 → ×3）。
- 右侧「缩放」滑条接线：`_update_zoom_slider_from_mouse` 在 cubic 态改 `cubic_zoom`
  （映射到 `CUBIC_ZOOM_RANGE` 0.5–3.0），**不再**走 `_apply_zoom_centered`，
  二维 `self.zoom` 一根毫毛不动；`draw_right_panel` 的滑钮位置也改成读 `cubic_zoom`，
  否则滑条位置会和实际画面脱节。
- 新增 `test/_test_cubic_framing.py`（15 项）：六朝向 scale 恒等、跨度确实随朝向变、
  build_scene 与 stable_frame 同源、zoom 线性、滑条顶/底 = 3.0/0.5 且二维 zoom 不动、
  滑条从顶到底 scale 294.7 → 49.1。
- 回归：view 41 / view_nav 83 / pick 204 / play 32 / gap 18 / split 25 全过。
- 截图：`cubic_shots/zoom_top_view0.png`（缩放 300%）。⚠️ 3.0 倍会把棋盘推出屏幕、
  状态行被块压住；如果嫌太狠，把 `CUBIC_ZOOM_RANGE` 上限收到 2.0 即可（等用户定）。

**前端还推不动是事实**：虚拟键盘三轴六键与三维箭头还没做（第 4 步剩余两片），
现在只有键盘 r/R c/C d/D 能推。

## 修：拖动手感改 trackball（用户实测「有时旋转方向和鼠标反了」）

旧做法：横拖绕**世界**竖轴、竖拖绕**相机右轴**——两根轴在两个坐标系里，先转
哪根让结果依赖姿态；相机一抬头，世界竖轴在屏幕上就是斜的，横拖会看着像乱转
甚至反向（用户 2026-11-17 真机反馈）。

新做法（`_cubic_drag_update`）：拖动向量取在相机自己的 right/up 平面上，绕
`轴 = up·dx + right·dy` 一次转 `−k·|d|`，即 Shoemake 的 trackball / three.js
OrbitControls、pCubes 轨道相机同一套：轴永远垂直于屏幕、永远与拖动共面，任何
姿态手感一致，极点也不用特殊保护（去掉了那段 clamp）。

- 数值验收：7 个姿态（斜视/前+Z/右+X/上+Y/抬头60/低头60/斜向45）× 8 个拖动方向
  = 56 组，全部「抓住的点朝鼠标方向走」。
- `test/_test_cubic_view_nav.py` 第 165 行断言按新口径改（绕屏幕竖轴，不再绕世界
  竖轴）；83 项全绿。
- 截图 `cubic_shots/drag_right60.png`：斜视右拖 60px 后——转开约 27°，画面大小
  不变（stable_frame 已接管装画面）。

## 修：三维局存档口子（用户控制台报错）

现场是两条：
    旧模型存档缺 engine_state，已载入但块可能缺失
    加载上次状态失败: 存档需要模型 'cubic'，但它没有安装（…）请确认 models/cubic.json
两条其实同一条坏档：temp_history 里躺着一份 `type: cubic` 的自动存档，载入端
把它当「模型板型」，找不到 models/cubic.json 就抛错；而第 5 步之前它本来就读不
回来——这条档是我早期写脏的。

- `gui/file_ops.py` 新增 `StaleCubicSave`（继承 `StaleEditorSave`）：撞到 `type:
  cubic` 立刻安静回落，只打一行「忽略上次状态（上次退出时停在三维局…）」，
  **不再**冒充「模型未安装」。
- 自愈：回落时顺手用当前默认局把那条坏档覆盖掉，否则每次启动都要再撞一次。
- 存档入口拦住：`_save_to_path` / `save_as` 在 `cubic_mode` 下直接拒绝并提示
  「三维局暂时不能存档：存档格式在第 5 步才扩到 (r,c,d)」，不再造新的坏档
  （与撤销/重做在第 4 步明确拒绝同口径）。
- 新增 `test/_test_cubic_save_guard.py`（7 项）：坏档静默回落 + 被覆盖成当前局
  + 三维保存被拒且文件不落地 + 切回二维后不再拦。

## 改：拖动改成真 arcball（用户第二次说「还是奇怪」）

pCubes 是闭源 exe（E:\pC 只有 pCubes.exe + 数据），HyperSpeedcube 装的也是
二进制（D:\leuzhubi\hyperspeedcube_win64 只有 exe+yaml）；但魔方模拟器的拖动
惯例是公开的：**Shoemake 的 arcball**——把屏幕点投到虚拟球面，按下点、当前点
两个球面方向取夹角，绕 `cross(a,b)` 转。与「像素线性 × 固定轴」相比，它天然
「抓哪儿转哪儿」，球心和球缘的灵敏度也不同。

- `engine/cubic_camera.py` 新增 `arcball_sphere_point` / `arcball_axis_angle`
  （球半径 = 画面短边一半，球外压到球缘）。
- `gui/events.py` 的 `_cubic_drag_update` 改走 arcball；`CUBIC_DRAG_DEG_PER_PX`
  （0.45°/px 线性）退役，换成 `CUBIC_DRAG_SENSITIVITY = 1.0`（倍率，将来进设置页）。
- 数值：同 100px，抓球心 19.5°、抓球缘 11.5°（arcball 该有的差异）；18 组姿态×
  方向全部朝拖动方向（cos=1.00）；半灵敏度精确转一半。
- `test/_test_cubic_view_nav.py` 的拖动断言改按 arcball 算；新增
  `test/_test_cubic_arcball.py`（5 项）。
- 回归：view 41 / nav 83 / pick 204 / play 32 / framing 15 / gap 18 / split 25 /
  save_guard 7 / entry 31 / arcball 5 全绿。

⚠️ 已知口径分歧：arcball 允许画面「滚转」，转到某些姿态后立方体的边不再贴
屏幕横竖。魔方软件里两种流派都有（自由球 / 固定水平）。如果用户嫌「歪」，下一步
加设置项：自由球 vs 保持水平（后者 = 绕世界竖轴 yaw + pitch 夹紧，无滚转）。

## 修：缝选中范围太大 → 只有点在缝线上才改切面

用户 2026-11-17 实测：双击选块时，第一下被当成「选缝」，缝当场跳走、第二下
就成了选到别的一侧。根因不是「缝的判定本身」，而是**当时点面内任何位置都算
选缝**（single click 命中面 → 无条件 `seam_of_face` → `selected_gap`）。

- `engine/cubic_pick.py` 新增 `_point_seg_distance`、`_point_quad_distance`、
  `seam_edge_distance(faces, hit_face, point, band=28)`：一条面边若「中点贴着
  另一块同轴同符号的面（距离 ≈ 缝宽像素）」，这条边就是缝线；返回点到它的
  像素距离。注意块之间有 gap，两块的面**并不共边**，所以不能按共享顶点认缝。
- `gui/events.py`：新增类常量 `CUBIC_SEAM_CLICK_PX = 6`；`_cubic_click` 重排
  成「先判双击 → 双击无条件选块；否则算点到缝线的距离，>6px 不动缝、只提示
  距离，≤6px 才改切面预览」。时间戳无论改不改缝都记，否则面内两连点拼不出双击。
- 实测：面心点击 selected_gap 保持 None（提示「距最近缝线 44px」）；点缝线
  上 → r·1；随后面心两连点 → 9 块整片变绿。截图 `seamfix_1/2/3_*.png`。
- 测试：`_test_cubic_pick.py` 新增「点面心不改缝」「点缝线上才出预览」两断言，
  缝线上取点改用新判定反查（共 206 项）；全回归 view 41 / nav 83 / pick 206 /
  play 32 / framing 15 / gap 18 / split 25 / save_guard 7 / entry 31 / arcball 5 全绿。

## 改：选缝判定改用「缝里的墙」（内部面）+ 切面预览填半透明面

用户 2026-11-17（截图指认）：点「贴着屏幕的那条缝」选出来的却是别的缝。
根因：旧 `seam_of_face` 按面的**法向**取缝族，点前面 = 选这块背后那张平行切面
（画面上根本看不见）。用户给的替代口径：拆分之后缝里的两面墙本来就画出来了
（gap>0 不剔除内部面），拿它们当判定基准；包围盒的平面不许选。

- `engine/cubic_pick.py` 新增 `seam_of_internal_face(face, is_valid_gap, locations)`：
  面在 v、法向 sign → sign>0 时缝线号 v，sign<0 时 v-1；传 locations 时先过
  `face_is_internal`，**外表面/包围盒面一律 None**（引擎其实允许「最外层整体
  滑出去」，那是包围盒平面，不该被点出来）。
- `gui/events.py::_cubic_click` 重写：命中内壁 → 直接选那条缝；命中外表面 →
  单击只提示不动缝；双击时内壁优先、外表面退化成 `seam_at_point` 最近缝。
- 渲染：切面预览从「白框」改成**半透明填充 + 描边**
  （`CUBIC_SEAM_FILL=(150,220,255,72)`、`CUBIC_SEAM_PAD=0`），单独 SRCALPHA 面
  blit，不破坏底色。
- 实测：点缝里的墙 (469,486) → 缝 c·0；双击同一处 → 选中 9 块；d·1 的切面
  在半透明渲染下是一张横贯整盘的玻璃面。图 `seamfill_1..4_*.png`。
- 测试：`_test_cubic_pick.py` 新增 B2 组 4 项（内壁 → 缝、两面墙同缝、包围盒
  面 None、外沿 line −1 None），并把「贴缝点」改成按内壁反查；共 211 项。
  全回归 view 41 / nav 83 / pick 211 / play 32 / framing 15 / gap 18 / split 25 /
  save_guard 7 / entry 31 / arcball 5 全绿。

⚠️ 已知：切面预览是「最后画的覆盖层」，不做逐块深度排序（半透明能看出后面
的块，但不会真的被前面的块挡住）。要更真实就按列切分加进画家序，属渲染细化。

## 改：可点范围扩到块的任意外表面（排除包围盒平面）+ 切面预览改红、进画家序

用户 2026-11-17 三条纠正：
1. 「外表面（只要不是包围盒的表面）也要可以选中，现在这样太小了」——上一版只
   认缝里的墙（细缝里的窄条），点不到大面上。
2. 「预览不是这个意思……应该改成红色」——二维的选中缝就是压在块上的**红线**
   （colors['line']），三维要同一套视觉语言。
3. 「切面看起来和滑块不在一个图层」——上一版切面是最后画的一层覆盖，永远压在
   块上面，没有遮挡关系。

- `engine/cubic_pick.py::seam_of_face(face, is_valid_gap, locations=None)` 重写：
  先试面外侧那条线（sign>0 → v，sign<0 → v-1），是**内部切面**就用；否则退回
  块的另一条边界。新增 `_is_internal_cut(family, line, locations)`：两侧都真有块
  才算（最外层=包围盒那层永远有一侧空 → 一律不选）。于是：
  最前块的前脸 → r·1（与屏幕平行的那层，正是用户先前指认想要的）；缝里的墙 →
  它所属的那条缝；点哪都能出切面，可点面积从「缝里的窄条」变成「整个面」。
- `gui/renderer.py::draw_cubic_board`：切面按 3×3 切小四边形、各自带深度，
  **并进块面的画家序**一起画（半透明红填充 `colors['line']` + alpha 110），
  再单独把整张切面的轮廓压在上面（同二维「红线压在块上」口径，方案 §2.3 也写了
  要画整张切面的轮廓）。块的绘制逻辑与拾取不变。
- 实拍：正视点前脸 → r·1，红框正好框住前层；斜视 r·1 时面被前层挡住、只剩红色
  轮廓（切面在实心立方体内部本来就看不见，只有缝隙里能露出来）；d·1 时红线
  横贯盘面。图 `redseam_1..5_*.png`。
- 测试：`_test_cubic_pick.py` 改口径（任意外表面可点、`_is_internal_cut` 断言、
  包围盒面退回内部切面、最前块前脸 → r·1），293 项全绿；回归 view 41 / nav 83 /
  play 32 / framing 15 / gap 18 / split 25 / entry 31 全绿。

⚠️ 遗留口径：旋转态仍然「只看不选」（方案 §2.2 原文）。用户问「任意方向操作」——
拾取基于渲染面与画家序，任意姿态下本来就成立，放开只需删 `_cubic_click` 里那个
`cubic_view_index is None` 的闸；要不要改方案口径待用户定。

## 改：撤销「必须正向化」——任意姿态可选缝 / 选块 / 六键推（2026-11-18）

用户判定：「方案可以改，因为当初那是想的如果渲染很难做就退而求其次的方法」。
实测也证实拾取不依赖朝向：`hit_face` 走的是**本帧渲染出的面 + 画家序**，斜姿态
天然成立。于是把方案里那条保底口径整段作废，代码里的两道闸也拆掉。

- `docs/spec/三维扩展方案_正方体单元_2026-11-17.md`：§2.2「自由旋转：只看不操作 /
  必须正向化」改为**任意姿态可操作**（保留「旋转不与滑动动画同时发生」）；§2.3
  删掉「正向化限制让拾取规整可控」，补「预览切面 = 红色半透明 + 轮廓 + 与块有遮挡」；
  §5 第 2/3 步验收判据、§6 第 2 条、§7「平移需正向化」同步划线。
- `gui/events.py::_cubic_click`：删掉 `cubic_view_index is None` 那个「旋转态只看不选」
  的闸，任何姿态都能点选。
- `gui/events.py::_cubic_move_key`：同样删掉旋转态闸，任何姿态都能推（三轴是世界轴，
  与镜头朝向无关）。
- `gui/events.py::_cubic_drag_update`：不再「一开转就清选中」——转一下看看再推是正常
  操作，清掉反而打断；切面跟着盘转是对的（它切的就是那盘）。
- `gui/renderer.py` 状态行提示补「任意姿态均可单击选切面 / 双击选中 · r/R c/C d/D 推」。
- 测试：`_test_cubic_pick.py` E 段改成「斜视下照样选到正确内部切面 + 旋转不清选中」，
  296 项；`_test_cubic_play.py` C 段改成「斜姿态按键真的会去推（不再被拦）」+ 没选中
  仍拒绝，32 项；回归 view 41 / nav 83 / framing 15 / gap 18 / split 25 / save_guard 7 /
  entry 31 / arcball 5 全绿。
- 实拍 `anypose_1_single.png`（自由姿态单击出 r·1 红切面）、`anypose_2_double.png`
  （双击选中 9 块变绿 + 红框）、`anypose_3_push.png`（同姿态按 C 起推，动画进行中）。

## 改：切面预览的遮挡改成「射线可见性」，不再有被挡住还画出来的线（2026-11-18）

用户：「缝隙遮挡关系还不好，边界线被遮挡的时候还是画出来了」。逐条查下来是三个
不同的问题叠在一起：

1. **整张切面的轮廓是最后画的一层**（上一版为了「总看得见刀在哪」加的），正视图下
   切面明明埋在块里面，红框却完整画在块表面——这就是那条假的边线。已删。
2. **按 1/3 块宽粗切 + 按格心深度排序**：一格会同时压住「该被挡」和「该露」两块
   区域，只能按一个深度一刀切 → 红边爬过前面块。改成 `cubic_view.point_visible`：
   每个小格中心沿视线朝相机做射线求交（`_ray_hits_box`，逐块 AABB，先按投影剪掉
   在该点后面的块），撞到任何块就不画。格细分从 12×12 提到 24×24（每格 ≈1/8 块宽）。
3. **切面伸出盘子外轮廓**：`seam_plane_polygon` 原来用逻辑包围盒取边，没算拆分
   （块内收 gap/2），所以切面比块的**实际**外表面宽出去 gap/2，正好在斜视下露在
   盘子外面。改成按 gap 内收（新增参数 `gap=`，默认 0 兼容旧调用）。

顺带：
- 切面不再逐格描边（24×24 网格描边会织成红网、像线框不像面），整张先画进实色
  蒙版再按 alpha 贴一次，格与格的接缝不会叠出深色线。
- 缝两侧的**墙面**一起染红（真几何、在可见面表里、走正常画家序）：切面本身埋在
  实心块内部，正视下物理上就该看不见，只靠它读不出「刀在哪」；染红真实的缝壁
  既不造假图层，又能一眼看出切在哪一层（pCubes 一类魔方软件同一思路）。
- 24×24×27 次求交约 22ms/帧 → 加 `_cubic_seam_cache`（键 = 缝 + 相机矩阵 + 拆分 +
  块位 + 装画面），命中时降到 7.4ms/帧（无切面 5.5ms）。

实拍：`redseam_1_front.png`（正视 r·1：只剩缝口几像素，物理正确）、
`seamgap_2_rotated.png`（拆分 0.35 + 斜姿态，d·1 只在缝槽里露红）、
`seamgap_3_rotated_r.png`（同姿态 r·1，缝壁染红成一道红槽）。
测试：view 41 / nav 83 / pick 296 / play 32 / framing 15 / gap 18 / split 25 /
save_guard 7 / entry 31 / arcball 5 全绿。

## 2026-11-18 切面遮挡：解析影子 + 抗锯齿（4993e96）

用户：截图指出「遮擋畫的毛毛糙糙」，并批评「你驗證的不充分啊」。

真因两条：
1. 切面近乎侧对时（旧阈值 |d_axis|<5e-2）渲染端退回 24×24 逐格采样，一格 10px 级
   —— 用户截图里那种梳齿状边界就是格子边。已整段删除，`seam_shadow_polygons` 阈值
   收到 1e-3，只有与切面真正平行（投影成一条线、没有面积）才返回空。
2. 就算全是多边形，pygame.draw 也不做抗锯齿，斜边是 1px 台阶。切面合成改成
   「局部 3× SRCALPHA 超采样 → smoothscale 回原尺寸 → 一次半透明 blit」；块面同样
   在棋盘包围盒内开 2× 超采样（那些碎三角有一半是块面自己的边）。

验收（不只截图）：
- `test/_test_cubic_seam_occlusion.py`（259 项全绿）：
  A 解析影子 vs 逐点射线，6 姿态 × 3 族 × 2 缝 × 2 拆分，16 万采样点 0 不一致；
  B 正视 r·1 的可见点必须都落在缝里；C 斜视 + 拆分 0.35 必须真露出来；
  D 影子多边形凸、顶点 3..8；E 像素级互证——每像素中心反投影回切面做精确射线，
  与渲染出来的 alpha 逐像素比，21 万内部像素 0 不一致。
- 帧成本：9.4ms（无切面）/ 9.9ms（每帧重建），原 5.5→7.4ms。
- 探针坑：`tmp_shadow_check*.py` 里把三维顶点当二维用（`a[0]` 恒等于切面坐标）会让
  凸包退化成一条线、报 4 万处假不一致；必须先按 axis 取另外两维。

遗留：切面靠近视线的极端姿态（|d_axis|→0）直接不画；是否给个 1px 提示线未定。

## 2026-11-18 第 4 步下半：三轴六键 + 重画箭头（0fdaa66）

第 4 步收口。前端从「只能看」变成「能推」。

- 虚拟键盘 cubic 态方向区改三行：c / d / r 各一对正负键，中间写轴名
  （c 轴 / d 轴 / r 轴）。字母小写=负方向、大写=正方向，与 `CUBIC_DIRECTIONS` 同源。
- 箭头不是静态图标：每次绘制按当前相机现算（世界轴 → 相机坐标 → 屏幕单位向量），
  所以拖转画面时六个箭头一起转。轴快正对镜头时投影长度趋零，改画空心圈
  （按了也没方向感，但至少不骗人）。
- 「没选中任何东西时点六键 = 平移盘面」按方案 §1 落地：屏幕像素偏移 `cubic_pan`，
  渲染时走 `build_scene(origin_offset=...)`，不碰逻辑坐标、不参与缩放/装画面；
  偏移夹在 0.55×屏幕长边内，推不丢。
- 有选中时六键 = 推一步，和 r/R c/C d/D 共用 `_cubic_push_letter`（同一个
  `move_selected_blocks` 口径），提示文案分开（「六键」/「r/R c/C d/D」）。
- 新增 `test/_test_cubic_vk.py`（32 项全绿）。其余 11 个 cubic 测试与
  切面遮挡的 259 项一起全绿。

下一步：第 5 步历史（快照/动作扩到 (r,c,d)、存档 type:cubic、撤销重做在三维下开闸）。

## 2026-11-18 第 4 步收尾整改（用户睡前四条 + 两项质量改进）

四条：切面遮挡结构 / 拆分回退 / 三维箭头 / 坐标轴键盘。

- **切面遮挡**：放弃「整张切面 + 解析影子」。一张面上只有一个「面心深度」，
  斜视时同一张面既该被挡又该露出来，一个深度值做不到 —— 这就是用户说
  「像切在另一层」的根因。改成 `cubic_pick.seam_plane_cells()` 把切面按 1 格
  切成四边形（只留「缝口有块」的格），按格中心相机深度插进同一个画家序
  `items=(faces + seam_items)`，同张 2× 超采样画布上依次画（半透明格先在小
  SRCALPHA 面上画再 blit，因为 `pygame.draw` 忽略 alpha）。另加「屏幕面积
  < 1.5px² 不画」：近侧对视线时一格退化成 1px 红线且深度最前压块，正是
  「边界线被遮住还画出来」的来源。
- **拆分回退**：`GUI.new_cubic_puzzle` 从 `_cubic_camera_prefs` 恢复 gap 时接受
  0.0，而 0 一旦写进 config 就永久贴死。改成 `1e-6 < gap < 1.0` 才采纳，
  0 一律回落 `DEFAULT_GAP=0.12`。
- **箭头**：锚点从「切面投影中心 + 屏幕外沿」改成真三维点（切面外沿再探 0.85 格），
  可推性走与真正点下去同一条路径（`try_move_ex` 干跑）并缓存，推不动一枚不画；
  遮挡双判：`point_visible`（沿视线被挡）+ 屏幕轮廓（`screen_hull_of_box` /
  `point_in_hull`：锚点落在更近块的投影轮廓内 = 贴纸，不画）。样式复用二维的
  `_arrow_sprite()` 同一张素材。
- **键盘**：方向区改坐标轴布局 —— 三色轴线（r 红 / c 蓝 / d 绿）+ 六端点白箭头
  + 原点；端点半径随该轴屏幕投影长度伸缩（26→88），投影≈0 的两端沿屏幕横轴
  ±26 拆开（否则正负两键完全重叠、只能点到一个）。14 轮「沿两心连线互相推开
  + 夹回方向区」松弛，65 姿态（13 偏航 × 5 俯仰）扫描 0 冲突 0 出界。
  方向区高度固定 200（`_VK_CUBIC_AREA`），面板随之加宽加高，行动作/步数/跳出
  行跟着下移（`_vk_dir_area_height()` 统一口径，避免面板高度和内容打架）。
- 帧成本：选中态 `draw_cubic_board()` 15.9ms（轮廓缓存前 18.2）、无选中 11.1ms。

测试：`_test_cubic_seam_occlusion.py` 整篇重写为**像素级回投**验证（屏幕偏红像素
正交反解回切面世界点，再用 `point_visible` 判「它理当被挡吗」），10 项；`_test_cubic_vk.py`
A 段换成坐标轴断言 + A2 段 65 姿态扫描，F 段换成新箭头断言（只画合法轴 / 每枚都干跑
可推 / 推得动一个不少 / 命中盒 = `_ARROW_BASE_PX*zoom - 6` / 互不重叠），44 项。

下一步仍然是第 5 步历史，然后第 6 步动画 + §2.4 渲染选项 GUI。
