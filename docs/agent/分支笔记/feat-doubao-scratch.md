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
  `_form_blocked()`——第 0 步时求解器也拒绝；P2 起 `gather` 已支持三维
  （其余算法仍明确拒绝，见本文件 2026-11-19 小节）。
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

## 2026-11-18 第 5 步：历史 / 撤销重做 / 存档扩到 (r,c,d)

- `engine/adapter.snapshot_state`／`restore_state`：无朝向板型（立方，`spec.orientations`
  为空元组）不再硬取 `orientations.index()`（那必抛 ValueError）。键表退化成
  `[r,c,d,gid]`，随点分量个数自动适配二维/三维；还原时朝向取 `''`。
- `history.GameHistory`：三维快照带 `cubic: True`，只存无损键表，`matrix` 写 `[]`、
  `bounds` 写零盒（二维矩阵没有深度，存了必丢）；`restore_snapshot` 见 `cubic`
  直接 `restore_state` 返回。`validate_snapshot(kind='cubic')` 只校验
  `engine_state.keys` 每条 `[r,c,d,gid]`。
- `gui/drag._move_merge_key`：三维返回 None（合并快照的逐步重播按方形 2-tuple 写死）。
- `gui/history`：三维撤销/重做开闸（`_cubic_undo_redo`，无动画）；到边界给
  「没有可撤销/可重做的步骤」；`jump_to_history_index` 在三维下跳过
  二维的 `ensure_blocks_visible`。
- `gui/move`：三维一律走「即时提交」，不套二维动画层（三维动画是第 6 步）。
- `gui/file_ops`：存档 `type: cubic` + `depth`，快照只写 `engine_state`；
  读回按 depth 重建三维局并补 `_cubic_load_defaults`（相机/缩放/拆分/平移/键盘）；
  `save_config` 不再跳过三维（退出即丢进度是旧口径）；`_cubic_save_blocked`
  只在逻辑对象缺 depth 时挡。旧的无 depth 三维档走 `StaleCubicSave` 安静回落。
- 测试：新增 `test/_test_cubic_history.py`（45 项：快照无损/撤销逐格回退/边界提示/
  跳步/存读回/坏档拒绝/二维不受影响）；`_test_cubic_play` 的「撤销被拒」改成
  「真的换局面」；`_test_cubic_save_guard` 的「三维不许存档」改成「能存能读」。

下一步：第 6 步动画（`gui/animation.py` 渲染层偏移）+ §2.4 渲染选项 GUI
（右侧栏拆分/透明度滑条、设置页「三维」专页）。

## 2026-11-18 第 6 步：推一步的滑动（动画）

- `engine/cubic_view`：`collect_faces` / `block_boxes` / `build_scene` 增加 `offsets`
  （{位置: 世界位移}）；只平移该块的面片，形状/遮挡/拾取口径不变。
- `gui/events`：`_cubic_start_anim(letter, 前位置)` 记下「这一推从哪到哪」，
  `_cubic_anim_offsets()` 按 `CUBIC_ANIM_MS=140` 的 ease-out 给逐渐归零的反向位移；
  `_cubic_push_letter` 推成功后起动画。逻辑位置仍在推的瞬间提交（可继续推/撤销）。
- `gui/renderer`：`build_scene(offsets=...)`；滑动期间**只隐藏切面红面**（面停在
  原处会被正在滑的块穿过，深度序必然错），箭头照画。
- `gui/history` 撤销/重做清掉 `cubic_anim`；`GUI.new_cubic_puzzle` / 读档补初始化。
- 测试：新增 `test/_test_cubic_animation.py`（16 项：逻辑先到位/位移收敛清空/只在
  动过那组/投影确实位移/关动画无尾巴/动画中仍可再推与撤销）。

至此方案六步（0 脚手架 → 1 画出来 → 2 六视角/旋转 → 3 选中 → 4 真的能玩 →
5 历史 → 6 动画）全部落地。剩余 §2.4「渲染选项 GUI」：右侧栏拆分/透明度滑条、
设置页「三维」专页、声明式配置表——尚未开工。

## 2026-11-18 §2.4（其一）：声明式选项表 + 右侧栏拆分/切面透明滑条

- 新 `gui/cubic_settings.py`：一张 `CUBIC_SETTINGS` 声明表（键 / 标签 / 属性 /
  类型 / 范围 / 默认 / 组 / help），提供 `defaults / clamp_value / serialize /
  apply / reset / items / by_key / by_attr`。**加选项只改这一处**：GUI 初始化、
  读档、`save_config` 的 `cubic_camera`、渲染与事件都从表里取。
- 四个已落地选项：拆分 `gap`(0~0.6, 0.12)、切面透明 `seam_alpha`(30~220, 110)、
  双击时间窗 `dblclick_ms`(120~600, 300)、旋转灵敏度 `rot_sensitivity`(0.2~2.0, 1.0)。
  读盘时越界夹紧、坏类型回默认（不静默写坏渲染参数）；gap 仍保留「0 不继承」守卫。
- 右侧栏（仅三维态）：底部开关从 7 个减到 5 个（连锁 / 复原标记这两个三维用不上
  的让位），上方补两条横向滑条「拆分」「切面透明」，拖了就立刻重画（边拖边看）。
  二维态原样 7 个开关、不画这两条滑条。
- 事件：`_update_cubic_opt_from_mouse` 按横坐标写值并夹紧；gap 一变立刻作废
  箭头可推性签名与贴纸轮廓缓存；只改显示参数不动 `_board_version`（标题栏不该
  平白多星号）。
- 顺手接上：双击时间窗、旋转灵敏度不再读类常量，改读表属性（`cubic_dblclick_ms`
  / `cubic_rot_sensitivity`）。
- 测试：新增 `test/_test_cubic_render_opts.py`（37 项：表语义 / 三维 5 开关 + 两条
  滑条不重叠 / 拖动夹紧与缓存作废 / config 落盘读回 / alpha 像素级浓淡 / 灵敏度
  真的改变转角）。既有两个「三维不许存档」断言按第 5 步口径改写后仍全绿。

⚠️ 踩坑记录：写测试时只改了 `config_dir` 没改 `config_path`，`save_config()` 把
测试值写进了仓库里用户真正在用的 `config/config.json`（last_file_path 也被指到
临时目录）。已把该文件恢复成 `config/temp_history.json` + 默认选项值，并在测试里
把 `config_path` 一起隔离。

剩下：设置页「三维」专页（8 个页签放不下，需把 tab_width 84→72；页内放「设一次
很少动」的项，二维局整页置灰 + 说明）。

## 2026-11-18 §2.4（其二）：设置页「三维」专页

- 页签 7 → 8：`tab_width` 84 收到 72（8*72+7*4=604 ≤ 612），新增「三维」页；
  其余页签内容与布局不动。
- `_draw_settings_cubic`：先一句「这里的项设一次很少动，拆分/切面透明在右侧栏
  边拖边看更直观」，再四行「双击时间窗 / 旋转灵敏度 / 拆分 / 切面透明」，
  每行 = 标签 + 当前值 + 「−」「+」步进（0.05 / 5 / 20ms / 0.1），说明另起一行
  按整行宽度换行（第一版把说明塞在右栏，被对话框右边缘切掉半句话）；
  行间细分隔线。
- 二维局：整页置灰 + 一句「当前是二维谜题，这一页的选项对二维没有作用」，
  不注册任何步进按钮（点不到），入口保持可发现（沿用求解器页先例）。
- `_calc_settings_content_height` 增加 'cubic' 分支（真实高度由绘制函数记录，
  首帧按 2 行提示 + 4×50 估算）。
- 事件：页签点击加 'cubic' 分支；页内点 −/+ 走 `_handle_settings_dialog_event`
  → 表夹紧 → 写属性 → 作废箭头/贴纸缓存 → 状态栏回显；「恢复默认」一并
  `cubic_settings.reset`。
- `_test_feature_index.py` 的 `_RECT_SKIPPED` 补 `tab_cubic`（该套件专门抓「新
  控件没登记」）。
- 测试：`_test_cubic_render_opts.py` 扩到 46 项（8 页签不重叠不出屏/宽 72、
  四行八枚按钮都在可见区、真实点一次 + 与 − 改值、二维局无按钮）；
  回归 `_test_audio_settings_scope` / `_test_command_palette` /
  `_test_external_control` / `_test_feature_index` / `_test_mi_gui` /
  `_test_click_feedback_buttons` 全绿。

§2.4 到此闭环：右侧栏「调节型」两条滑条 + 设置页「三维」专页 + 声明式表。
未做：feature_index 检索条目从表自动生成（目前只登记了页签，四个选项还没进
检索真源）；方案里写的「明暗 / 透视 / 分组着色」渲染支持本身尚未实现，故未放
进页面（不放假开关）。

## 2026-11-18 首页三条：切面矩形 / 配置持久化 / 平移视角

1. **切面恢复成一张矩形平面**。上一版为了遮挡把面按 1 格切成小四边形塞画家序，
   结果盘面一打散就缺格、格与格交界还会加深成网格线（用户：「形状也改了」）。
   现在 `engine.cubic_pick.seam_plane_rect(family, line, blocks, gap, dims)` 只给
   **整幅四角**（给了 dims=(m,n,d) 就按棋盘整幅取，不随块堆缩水）；遮挡改成
   按块相对平面的位置分两遍画：**背面块 → 整张半透明红面 → 相机侧块**。切面是
   平面、每块整块只在一侧，这个顺序就是真实前后关系，边界是块自己的像素轮廓。
2. **config.json 存三维局**。save_config 新增 `cubic_puzzle`（m/n/d/step）与
   `cubic_pan`（手工平移）。temp_history 读不回（旧档/被覆盖）时按 config 重建
   同一个三维局；读取时补 `current_depth`，修掉「状态栏取分榜键抛缺 depth、启动即崩」。
3. **视角可平移**。中键 / Shift+左键拖动 = 跟手平移（只改屏幕偏移，不动姿态）；
   Home = 居中归零；虚拟键盘六键那条平移路径保留。平移量进 config，重启还在原处。

测试：新增 `test/_test_cubic_config_state.py` 16 项（矩形几何、落盘、只有 config 时
重建三维局、拖动平移/夹紧/Home 居中）；`_test_cubic_seam_occlusion` 补 F 段 4 项
（一整张矩形、共面、打散不缩水）共 14 项；`_test_cubic_save_guard` 补测试隔离
（构造期已读真实 config，清掉 prefs）。全部 cubic 套件与 feature_index/statusbar/
generic_controls/rp_menu 回归通过。

## 2026-11-18 修正：视角平移改回方案口径

上一版我擅自加了「中键 / Shift+左键拖动平移 + Home 回正」，用户指出方案里不是这么写的。
重读 `docs/spec/三维扩展方案_正方体单元_2026-11-17.md` §2.2 / §1：

- 平移**只走虚拟键盘三轴六键**（没选中时点六键 = 平移盘面，**不占空白拖动**）；
- **居中 = 质心落在屏幕中心**；默认开「跟随质心」抵消整盘滑动带来的整体偏移
  （兼作三维防偏移口径）；**手动平移后暂停跟随，按「居中」回正并恢复**。

改动：删掉中键/Shift 拖动平移与 Home 绑定；`engine.cubic_view.stable_frame/build_scene`
新增 `center`（origin 用给定参考点，scale 一律按包围盒半径，避免跟随质心时缩放跳动）；
`gui/renderer.draw_cubic_board` 在 `cubic_follow_centroid` 为真时传块质心；
`events._cubic_pan_by` 手动平移时置 `cubic_follow_centroid=False`；
`events._cubic_pan_center` 归零并恢复跟随，提示「视角已居中（恢复跟随质心）」；
`GUI.center_map` 加 cubic 分支（编辑菜单「居中」对三维直连 `_cubic_pan_center`）；
`new_cubic_puzzle` 初始化 `cubic_follow_centroid=True`；config 增存 `cubic_follow_centroid`
并读回 `_cubic_follow_prefs`（`_cubic_load_defaults` 套用）。
测试 `_test_cubic_config_state.py` 的拖动平移断言改写为「六键平移→暂停跟随 / 居中→
归零+恢复跟随 / 质心投影落在屏幕中心」共 19 项；补 config 存回断言后 21 项全绿。

## 2026-11-18 五条体验返工：打乱动画 / 切面铺满 / 跟随平滑 / 箭头随缝 / 双击选块

用户当场列了五条，逐条落点：

1. **打乱过程没有动画**。3D 打乱演示复用了 2D 的 `start_animation` 管线（逻辑位置按格
   推进），但三维渲染不认 2D 的格子坐标 → 每步只是瞬间换位置。修：`_cubic_anim_offsets`
   在 `cubic_mode` 且 `animating` 时，把 `anim_block → anim_end_pos` 的逻辑位移按
   `anim_progress` 换成世界位移（`(dc*dp, dd*dp, dr*dp)`）交给 `collect_faces/block_boxes`
   的 offsets。演示仍是「逻辑提交 + 渲染插值」，commit 后照旧推进下一条记录。
2. **切面要铺满包围盒横截面**。`seam_plane_rect` 不再向内缩半格 gap：两轴范围改成
   `[lo-gap/2, hi+gap/2]`，即块的可见外延。打散后也不跟着块堆缩水（dims 给整幅棋盘）。
3. **滑完强制居中导致画面抖动**。原先跟随即时换 origin，一步走完质心跳 1/9 盘 → 画面
   猛拽一下。改成平滑跟随：`_cubic_follow_center` 每帧朝质心 lerp 0.14（约 8 帧收敛），
   scale 仍按包围盒半径（不因跟随而变化）。手动平移仍立刻暂停跟随；「居中」重置平滑点。
4. **同向连推箭头不换位置**。`_cubic_push_letter` 成功后把 `selected_gap` 沿推行轴
   平移一格（`line ± 1`，方向由字母大小写定），箭头/可推性与缝口都重新挂到新位置；
   推不动就不动。
5. **双击仍可能选到别处缝隙**。双击分支不再退回 `seam_at_point`（「离点最近的一条缝」），
   改为只认**点中的那块自己挨着的**有效内部缝：优先「点中的那面外侧」，否则扫这块
   六个边界；一块都没有就把缝恢复成双击前那条并明说没缝。单击时记录 `_cubic_gap_before_click`
   供回滚。

测试：`_test_cubic_animation` F（演示中非零位移、未到落点、确实推进）/ G（跟随首帧
小于总位移 45%、逐帧不增）；`_test_cubic_vk` H（缝随推平移 + 新缝在推行轴挪整格）；
`_test_cubic_pick` H（两个朝向 × 全部可见面双击，缝必须属于点中的块，0 跑偏）；
`_test_cubic_seam_occlusion` F 改成 3.12 整幅、红像素边界按矩形、正视红占比阈值放宽到
4.5%（多出来的是铺满后露出的半格红边）；`_test_cubic_config_state` 跨度改 3.18。
全部 cubic 套件 + feature_index + statusbar 回绿（pick 297 / vk 49 / anim 24 / seam 14 / config 21）。

## 2026-11-18 切面范围再纠正：按**包围盒**，不按原始尺寸

上一版给 `seam_plane_rect` 传 `dims=(m,n,d)` 就按棋盘整幅取——用户指出这不对
（「我用的是包围盒范围不是原始尺寸」）。三维盘面推散后块本来就跑出原始格数，
几何必须跟着真实块堆走。改成：

- 有块时一律用 `min/max(world)` 的包围盒（逻辑 (r,c,d) → 世界 (c,d,r)），平面内
  两轴再各加半格 gap（块的可见外延）；`dims` 只在**一块都没有**时兜底；
- 箭头锚点也改用同一张 `seam_plane_rect` 的边（不再用 `seam_plane_cells` 那种
  按「缝口有没有相邻块」筛过的外框，盘面一散就缩水）。

测试同步：`_test_cubic_seam_occlusion` F / `_test_cubic_config_state` A 的「只剩
一块」断言改为**范围缩到 1 + gap**（不再要求保持整幅棋盘）。

## 2026-11-18 切面画家序再改：完整矩形 + 选中组永远在上层

用户复查：双击后「选中滑块和缝隙相交」、缝面「被切了一块不是完整矩形」。
如实核对过 `game.opt`：选中组**没有**跨缝两侧（脚本 3 个朝向 × 全部面双击，
`lo/hi` 混合 0 例）——看到的「相交」是绘制顺序造成的：切面半透明地压在选中块
上，块就被糊红了。

改画家序（不再按相机深度切前后，纯按选中态）：

  · 所有**未选中**块（按 depth）→ **完整矩形切面** → 所有**选中**块（按 depth）。

于是：切面不再被前层块啃出缺口（整张矩形）；选中的绿色组永远不透明地压在
切面之上，不会再出现「块和缝相交」的观感。代价是未选中块在切面之前时会被
红面糊一层——这是用户要的「完整矩形」必然结果。

测试同步：`_test_cubic_seam_occlusion` 判据改为「红像素在矩形范围内 + 不落进
选中块盒子里」，D 段由「正视时红占比必须很小」改成「正视时必须仍是完整矩形」，
新增 G 段验证选中块没被红面糊住。

## 2026-11-18 虚拟键盘重画成真正的投影坐标系

用户：「虛擬鍵盤畫的是個啥玩意，我要坐標軸投影，隨著滑塊視角一起轉」。
旧版是六个 40×40 方键按投影方向散开、每键里塞一个小箭头——读起来是「散键」，
不是坐标系。改成：

- 每族一条**穿过原点的直轴**（负端→正端），r 红 / c 蓝 / d 绿；
- 只在**正端**画实心三角箭头（画在端盘外圈，不然被盘盖住）；
- 两端是圆形端盘，字母居中（r/R c/C d/D），hover 用轴色填充；
- 端盘位置仍由相机投影算（`_cubic_vk_axes`），旋转棋盘时三脚架跟着转；
- 轴正对镜头（`plen < 0.15`）时投影本来是一个点：两端盘沿斜对角错开，
  且**不画轴线和箭头**（否则一条斜线会被误读成一根斜轴），只剩两个同色端盘；
- 不再在轴上另写小写轴名（端盘字母 + 轴色已足够，写了压线）。

截图：`fix19/vk_axis_obl.png`（斜视 35/25）、`fix19/vk_axis_front.png`（正视 +Z，
r 轴正对镜头退化成两个端盘）。

## 2026-11-18 操作方式改版：左键选块 / 右键选缝 / 空白右键取消

用户确认：「允許外表面也選縫是有代價，那就改操作方式吧——以後右鍵選縫，
左鍵選滑塊，在空白處右鍵是取消選中」。

- `_cubic_click`（左键）：点中块 → 选这块所在的连通组，并**自动挂上这块旁边
  一条有效内部缝**（`_cubic_seam_for_block`），箭头立刻可用；不再有双击判定，
  `_cubic_last_click_t/p`、`_cubic_gap_before_click` 全部退场。旁边一条缝都没有
  （1×1×n 退化局）时只提示、不选组。
- 新增 `_cubic_seam_click`（右键）：点中块的任一表面 → 取这条面所属的内部缝
  （`seam_of_internal_face` 优先，外表面退回 `seam_of_face`），并把点中那块
  **同侧**的连通组选上（右键选完缝就能直接推）；点空白 → `_cubic_clear_selection`。
- 设置页删掉「双击时间窗」（已无双击），三维专页从 4 项变 3 项
  （拆分 / 切面透明 / 旋转灵敏度），CUBIC_STEP 与数值格式同步。
- 状态栏提示改成「左键选块组 · 右键选缝（空白=取消）」。

测试：pick 301 项（H 段由双击改单击、新增 I 段右键选缝/空白取消）、
render_opts 46、config 22、statusbar 及全部 cubic 套件全绿。

## 2026-11-18 操作顺序对齐原版：先右键选缝，左键才能选块

用户：「如果當前沒有選中縫隙，必須禁止選中滑塊」「右鍵滑塊預期是選中縫隙，
實際上還是取消選中」。两条都真：

1. **顺序**：`_cubic_click`（左键）先看 `selected_gap`；没有缝 → 只提示
   「先右键选一条缝，再左键选要滑的滑块」，不选任何块；有缝 → 才
   `game.opt(seam, 块)` 选同侧连通组，且**绝不改缝**。
2. **右键选不了缝**：右键在通用鼠标分支里落到了二维旧逻辑「右键取消选中」
   （`button == 3` 直接清 `selected_gap/be_opted`）。三维右键分支写在
   只给左键用的「游戏区点击」里面，根本到不了。改在 `handle_events`
   通用鼠标分支**之前**加三维右键入口（排除菜单栏 / 右侧栏 / 浮动面板 /
   下拉菜单），命中即 `_cubic_seam_click`。
3. `_cubic_seam_click` 只定切面，不再顺手选块（否则又变成「没点块却选上了」）。

测试同步：pick 303（新增「没缝时左键不选块」、右键只选缝、空白右键取消、
左键从不改缝）、play/vk/history/animation 的「选一组」全部改成「右键选缝 +
左键选块」；全套 cubic 套件绿。

## 2026-11-18 切面遮挡再修：未选中块按深度挡切面，选中组才压在切面之上

上一版为了「整张矩形不被啃缺口」把切面画在所有未选中块之后，等于让红面糊在
**所有**块上——用户：「現在切面遮擋怎麼又不对了，退回了好幾個版本之前」。
那是拿遮挡换矩形，不成立。

最终画家序：

  · 未选中块：**按相机深度**分成「切面之前 / 之后」两段，前段照旧画在切面之后
    （前层块正确挡住红面）；
  · 切面：夹在两段之间；
  · 选中组：**无条件**画在切面之上（绿色组不透明、不被红面糊住；代价是选中组
    若在切面远侧，遮挡略偏，但这是用户明确要的「不能相交」）。

不回避的取舍：切面是半透明面，**不可能既被前层块正确遮挡、又显示为完整矩形**。
按用户最新口径选遮挡优先，矩形只在没有被块挡住的地方连续可见。

测试：`_test_cubic_seam_occlusion` A 保留「红像素在矩形范围内」、B/G 保留
「红不落进选中块」、D 改回「正视前层挡死，红占比 < 5%」（实测 2.3%）；
全套 cubic 16 个套件绿。

## 2026-11-18 回退三层画法；真正的 bug 是画布边界把切面四角裁了

用户澄清：他说的「完整」不是「不被块遮挡」，而是**四角不被相机 / 画布范围裁掉**
（截图里红面左上、右侧的角缺了，绿线画出应有的矩形范围）。前两轮我理解错了，
拿「遮挡 vs 矩形」当矛盾去调，白折腾。

已 `git revert b0b6042`（撤销三层弱覆盖 + 外框），回到「按深度遮挡 + 选中组在上」。

真因：`draw_cubic_board` 的超采样画布边界只按 `scene['faces']`（块的面）算，
而切面按包围盒取范围、拆分 gap 时比块堆宽出半格，投影四角落在块面顶点之外 →
被 `hi` 画布裁掉。切面越大/越斜越明显。

修法：把切面投影点 `seam_pts_screen` 也并入 `_all` 参与 min/max，四周留 4px；
并记 `self._cubic_hi_rect` 供测试核对。新增 H 段：gap 0.12/0.40 × 四个视角，
凡落在窗口内的切面角必须落在 `_cubic_hi_rect` 内（0 个被裁）。

全套 16 个 cubic 套件绿；证据帧 `fix19/dblclick_top.png`（gap 0.40 斜视，四角完整）。

## 2026-11-18 第 3 阶段开工：三维拒绝反馈（提示音 + 选中组红边闪 12 帧）

方案 §5「反馈与接入」第一项。二维 `_flash_reject` 是给块面换色，三维块是投影多边形，
换色会被画家序吃掉；改为在屏幕空间描被拒组的凸包轮廓（`screen_hull_of_box`），
颜色 `colors['line']`、线宽 2，亮 12 帧，状态复用二维的 `_shake_t/_shake_blocks`。

- `_cubic_push_letter` 推不动 → `_reject_move(None, 选中组)`：出声 + 闪；
- 没选块就按 → `_reject_move(None, visual=False)`：只出声 + 文字，不闪整盘
  （与二维同口径）；
- 闪烁期间 2D 的 `animation.py` 会自然递减 `_shake_t`，三维共用，无新增计时器。

测试：`_test_cubic_play` F 段（法向推必拒、`_shake_t=12`、闪烁集合=选中组、带红边帧不崩、
前提没满足不闪）；全套 16 个 cubic 套件绿。

## 2026-11-18 第 3 阶段收尾（音效/存档核对）

- 三维右键入口补 `_play_click_sound('right')`：右键选缝 / 空白取消与二维同一音槽
  （音量更低），之前走新入口 `continue` 掉了二维的右键音。
- 滑动音本来就走 `move.py` 公共路径（`_play_slide_sound`），三维推一步自动有声；
  左键点块走通用点击音，无需另接。
- 存档核对：`_test_cubic_history` 新增 E2 段——真走 `_save_to_path` → 磁盘文件 →
  `_do_load_from_path`，验证 `type:cubic` + `depth`、校验和、局面逐格、步数、
  提示语；连同原有 E 段（内存 `_build_save_data`/`_load_save_data`）、F 段坏档、
  重启恢复（`_test_cubic_config_state`）一起覆盖。结论：三维存/读正常，二维存档不受影响。
- 竞速：三维仍被 `mode_allowed` 明确拒绝（初始局面不是字符矩阵，成绩表存不了
  同一题）。要支持需扩 records schema（三维初始键表 + 回放缩略图），留到第 5 阶段。

## 2026-11-18 右侧面板三维适配（用户提醒的漏项）

之前只把「连锁 / 复原标记」换成两条滑条，剩下四个开关在三维里全是哑的：

- 选中动画、着色：按二维块面/分组语义手写，三维 `draw_cubic_board` 根本不读；
- 模式：三维只支持练习（竞速缺 records 初始局面），点了只会弹拒绝；
- 成绩：三维没有成绩记录。

改成三维态只留三个真生效的开关：**滑动动画 / 虚拟键盘 / 跟随质心**；二维仍是原 7 个。
`sw_count` 5→3，虚位让给两条横向滑条，避免大片空白里混着死按钮。

第二处哑控件：右侧竖向「速度」滑条以前只写 `animation_duration`，三维一步动画读的是
`CUBIC_ANIM_MS=140` 常量，所以三维里怎么拖都没反应。现在：

- 新增 `CUBIC_ANIM_MIN_MS=60` / `MAX=400` / `cubic_anim_ms=140`；
- 三维态滑条改 `cubic_anim_ms`，`_update_slider_from_mouse` 走三维分支，不碰二维；
- `_cubic_start_anim` 改读 `cubic_anim_ms`。

第三处：132px 放不下「切面透明 110」，面板改用短名 **拆分 / 切面**。

`_test_cubic_render_opts` 同步：三维 3 个开关、速度滑条写 `cubic_anim_ms` 且不改
`animation_duration`、跟随开关关闭后手动平移保留、重开回正。全套 16 个 cubic 套件绿；
面板截图 `fix19/panel_cubic.png`。

## 2026-11-18 功能检索三维登记 + 视觉页裁剪

- `gui/feature_index.py`：`FORM_NAMES` 增 `cubic: 三维`；新增 5 条三维条目
  （三维预设 / 拆分 / 切面透明度 / 三维视角 / 右键选缝左键选块）；
  `_CUBIC_IDS` 给 29 个已实现功能补 `cubic` 形态。明确不做的项（着色、连锁、
  复原标记、成绩、求解器、宏、创造等）保持不支持，命令面板显示 ✕ 与「仅支持…」。
- `gui/events.py`：命令面板 `puzzle` 动作补 `cubic` 分派 → `new_cubic_puzzle`。
- `gui/renderer.py`：三维局「视觉」设置页只画真正生效的项——滑动动画、动画时长
  （写 `cubic_anim_ms` 60–400）、缩放、开机动画、防意外打乱；着色/连锁/缝隙闪烁/
  复原标记/调试面板/成绩/绘制网格/防偏移/思考演示一律不画，对应命中矩形清零。
- 测试：`_test_feature_index` 增第 7 段（形态 cubic、三维预设可建局、拆分可用、
  着色明确不支持且有理由）；`_test_cubic_render_opts` 增 G 段（视觉页裁剪、
  三维速度滑条不改二维值）。16 套 cubic + statusbar 全绿。

## 2026-11-18 三维竞速 + 三维成绩表

- `mode_allowed` 放行 `cubic`（仍有粘连的局照旧拒绝）；分組鍵
  `{step}~cubic{m}*{n}*{d}` 已由 `puzzle_key` 生成，层数不会串榜。
- 竞速初始局面不再用二维地图：`_timer_initial_map` 对三维写
  `cubic:` + `engine_state` 无损键表 JSON（`[r,c,d,gid]`）。
- 成绩面板识别 `cubic:` 前缀：详情显示尺寸与块数，不画二维矩阵；
  操作菜单只留「复制初始状态 / 载入练习模式」（不产假的二维存档）。
  载入练习按 key 取回 m/n/d，`new_cubic_puzzle` + `restore_state` 逐块还原。
- 右侧栏三维开关从 3 个恢复到 5 个：滑动动画 / 模式 / 成绩 / 虚拟键盘 /
  跟随质心（后两者现在都真生效）；着色/连锁/标记/选中动画仍不出现。
- `feature_index` 把 mode_practice / mode_timed / records_panel 登记为 cubic
  可用。
- 新增 `_test_cubic_speedrun.py`（26 项）：竞速放行、初始键表 27 块、
  成绩详情渲染、成绩载回练习逐块一致、计时开始→解开→写库、右侧栏开关。
  16 套 cubic + records/statusbar 全绿。

## 2026-11-18 第 5 阶段：三维自定义尺寸 + 预设扩充

- 谜题菜单「三维谜题 ▸」从 4 档扩到 9 档：2×2×2 L1、3×3×2 L1、3×3×3 L1/L2、
  4×3×2 L1、4×4×4 L1/L2/L3、5×5×5 L1。1×1×1 不再出现在菜单（代码路径仍明确
  拒绝「一步都动不了」），菜单高度 10 行 × 26 = 260px，618 高窗口内完整可点。
- `draw_custom_puzzle_dialog` 支持 `custom_kind='cubic'`：五个形态按钮一行（矩形/三角/
  米字/数字/三维），三维多「层数」一行；二维框 360×320，三维框 400×370；三维不画
  「高级选项…」（二维设计画布入口），确定/取消居中。
- `_custom_field_order`：三维 m→n→d→step；`_custom_apply_fields` 校验三维三项 ≥1、
  `max(m,n,d) >= 2`、`step < max`，失败原因回写 `custom_error`；成功走
  `new_cubic_puzzle(m,n,d,step)`。
- 「自定义...」与命令面板/帮助检索的 `custom_dialog` 动作都按当前形态预选页签，
  三维局直接落在「三维」并带回当前 d。`feature_index._CUBIC_IDS` 加 `custom_puzzle`。
- 预设菜单里 5×5×5 实测建局 3ms、首帧 13–18ms；4×4×4 L3 建局 1ms、首帧 14–16ms。
- 新增 `_test_cubic_custom.py`（33 项）：对话框渲染/五形态/四字段/按钮不越界、
  回车导航、真点「三维」+ 确定建局、非法值拒绝、预设档合法性、命令面板预选、自定义尺寸存档往返。
  `_test_cubic_entry.py` 的菜单查找补 `p[5]==3` 以区分 3×3×2 与 3×3×3。
  17 套 cubic 全绿（pick 303、view_nav 83、history 51 等），dialog/feature/rp 回归绿。

## 2026-11-18 三维撤销/重做动画 + 补回「选中动画」

用户口径：三维撤销/重做不能瞬间换盘，要像推一步那样滑过去；同时把此前从三维
入口撤掉的「选中动画」开关补回来——撤销蓝、重做橙地高亮这一步动过的滑块组与
切面。交互顺序不变（右键选缝 → 左键选块 → 空白右键取消）。

- `gui/animation.py`：新增 `_flash_cubic_move_selection`，三维只记
  `_sel_anim_locs` / `_sel_anim_gap` 供渲染叠色，**不改 `be_opted` 与
  `selected_gap`**——否则动画那 0.75s 内点六键会把高亮片当选中片推走。
  撤销目标 = `moved_positions`；重做目标 = moved + `CUBIC_DIRECTIONS` × step。
  三维是沿缝面内滑动，缝平面不挪，撤销/重做都用**原缝号**。
  新增 `_sel_anim_sets_gap`：二维改 `selected_gap` 才还原，三维不动玩家选择。
- `gui/history.py`：新增 `_cubic_start_undo_redo_anim`，逻辑换盘后只给渲染偏移；
  撤销给 `-world`、重做给 `+world`，ease-out 归零，时长读 `cubic_anim_ms`。
- `gui/renderer.py`：三维面片动画帧用选中色填充并按蓝/橙描边；切面轮廓叠同色
  2–3px 边；动画期间顶替显示动画缝（不写回 `selected_gap`）。右侧栏三维开关
  5→6（滑动动画、**选中动画**、模式、成绩、虚拟键盘、跟随质心）；视觉页补回
  选中动画开关，文案标明蓝=撤销、橙=重做。
- `gui/feature_index.py`：`_CUBIC_IDS` 加 `selection_animation_enabled`。
- 修一个自己引入的渲染 bug：描边线宽变量曾写作 `_bw`，把超采样层
  `smoothscale` 的目标宽度覆盖成 6px，整盘被压成一条细线；改用 `_lw`，并在
  `_test_cubic_selection_anim` 增加「动画帧仍是完整盘面」的像素跨度断言。
- 测试：新增 `_test_cubic_selection_anim.py`（28 项：撤销/重做目标、只画不改、
  两个开关独立、右侧栏/视觉页/功能检索入口、到期清理）；`_test_cubic_play.py`
  D 段补真实推块后的滑动/高亮断言；`_test_cubic_render_opts` 期望改 6 开关 +
  视觉页选中动画；`_test_cubic_split` 固定相机/拆分，避免仓库 config 残留的
  正对视角让「≥3 级明暗」假失败。19 套 cubic 全绿。
- 证据帧：`fix20/sel_anim_undo.png`（蓝）、`fix20/sel_anim_redo.png`（橙）、
  `fix20/panel_cubic6.png`（6 开关右栏）、`fix20/settings_visual_cubic.png`。

## 2026-11-18 撤销/重做选中动画：切面遮挡与红线（用户报）

- 切面轮廓原来在**所有块画完之后**用屏幕坐标补一圈，颜色还借用撤销蓝/重做橙；
  它永远浮在最上层，前面的块挡不住，视觉上像高亮边框没被切面影响。
- `gui/renderer.py`：切面轮廓改成和切面同一深度、画进 2× 画师序，颜色恒为
  `colors['line']` 红；前块后画自然盖住，背块先画被红面盖住。冷暖色只留滑块组。
- 撤销/重做走 `cubic_anim` 偏移，原分侧按**逻辑终点**算；块在动画中穿过切面时，
  整段边框都被分到错的一侧。现在 `scene['offsets']` 有偏移就按**当前渲染位置**
  分侧，跨面瞬间切换；2D 动画管線仍保留原「起终点都算近侧」兜底。
- 测试：`_test_cubic_selection_anim` 补 G 段（起点近侧/终点远侧 + 切面轮廓红色
  像素计数），32 项全绿；全量 `_test_cubic*` 全绿。

## 2026-11-19 三维创造第 4 步：样式命名 / 存盘 / 样式库

- `gui/cubic_create.py`：还原目标（purpose='goal'）进入即打开样式名输入框，
  `TEXTINPUT` 走 SDL 输入法（中文可入）；空名字点「完成」停在编辑器，不落盘。
  保存门（`check_restorable`）通过后**先落样式再改当前局**，写盘失败不提交，
  避免「样式库没有、局面已换」的半截状态。样式 JSON：`kind='cubic'`、
  `m/n/d/step`、`cells`、`groups=[]`（捆绑留到阶段 5）。
- `gui/annotation.py`：三维还原二级菜单加「三维样式库」；样式菜单按
  `kind='cubic'` 过滤，二维库不再显示三维样式，反之亦然；`_ann_design_start_style`
  新增 cubic 分支：建 `m×n×d` 局 → `apply_pattern(cells)` → `set_goal_pattern(cells)`，
  旋转/翻面仍走 48 对称还原判定。
- 测试：`_test_cubic_create.py` 增至 13 段 / 103 项全绿；新增命名框空名拦截、
  `TEXTINPUT` 入名、样式落盘、样式库过滤、按样式再开局。
- **步 5 随机生成（同日）**：三维打乱页加「随机生成」；复用 `game.shuffle`
  的安全打乱（每步先提交再验同缝反向可精确推回，反转即解法），`bias=0`
  （三维 `_scatter_of` 仍走二维评分，非零偏置会按 2-tuple 解包三坐标）。
  入口是 `m/n/d/等级` 四格对话框，体积上限 216；生成后清 goal、重置历史。
  测试 t13 覆盖按钮、对话框、4×4×4 生成、3×3×3 直调生成、非还原/块数/历史。
- 六套 cubic 回归（entry 31 / split 25 / animation 31 / infinite 30 /
  render_opts 72 / lighting 27）全绿；二维样式库隔离、打乱与随机生成用
  独立探针验证通过。
- 注意：仓库 `config/config.json` 当前 `infinite_shuffle=true`；二维设计测试
  若直接跑会把首次「打乱」解释成「停止无限打乱」而误报 D6b，需在测试进程里
  先关该开关（本次未改用户配置）。

## 2026-11-19 三維收尾口徑（調試面板 / 宏 / 聚攏）

本節是與用戶逐條對齊後的當前真源，避免把「玩家宏 UI」與「求解器用的宏執行器」
混成一件事。

### 架構鏈路

`求解器產生 actions / rep_cells → gui/auto_solve.py 轉成 macro_exec_ops
（世界絕對座標）→ _execute_next_macro_step() → 三維 _execute_cubic_macro_op()
→ opt() → move_selected_blocks()`。

- 求解器不直接改盤面；它只產生動作序列。
- 三維 op 契約：`kind='cubic'`、`gap_type=r/c/d`、`rep_cell=[r,c,d]`、
  `side=above/below`、`direction=六向`、`step=當前步長`。
- 求解器播放用絕對 op；`MacroStep` 只用於玩家錄製／存檔的相對宏。不要把
  求解器動作先相對化再回放。

### 已定案

1. **自訂還原態降為低優先**：現有代碼保留，不擴充。
2. **三維 GUI 宏入口暫時不接**：點入口提示「三維暫未開放宏功能」；
   `feature_index` 維持三維不可用，文案寫「暫未開放」，不是 bug 式「不支援」。
   二維宏照舊。
3. **內部宏 op 執行器保留並必須做穩**：求解器依賴它；不做玩家錄製／命名／
   宏管理 UI。不要因為 GUI 不接就把 `macro/` 或 `_execute_cubic_macro_op` 刪掉。
4. **求解器只先接「聚攏」**：不搬查表／PDB／IDA*／混合；新增三維 adapter，
   不直接把 `gather_solve` 丟給 `EngineGame`。
5. **文檔／測試收尾不是求解器前置門檻**：先做功能，文檔口徑與既有紅燈可並行收。

### 當前剩餘與順序

- **P0 三維調試面板（2026-11-19 已完成）**：`gui/metrics_panel.py` 已加
  `_MP_WIDTH_CUBIC=260`、`_mp_cubic_rows()`、cubic 分支與動態行數；面板現在
  先報聚攏數據：聚攏度、重疊、目標盒、邊界盒、填充率、mod 約束，再報
  視角/縮放/拆分/切面/選中組/操作隊/錯誤，共 16 行。`_mp_current_metrics()`
  對 cubic 走 `_cubic_metrics_now()`，不落二維 `gather_metrics`；空盤也回
  三維字典。`gui/renderer.py::draw_cubic_board()` 在調試面板或棋盤記號打開時
  畫綠色目標盒（與面板共用同一份 `cubic_metrics().window`）。
  `gui/renderer.py::_draw_settings_cubic` 末尾有「調試面板」開關，`gui/events.py`
  `settings_active_tab == 'cubic'` 已接點擊。`_MP_SUPPORTED` 仍不含 cubic，
  所以二維洞記號/目標框邏輯不會誤入三維。護欄：
  `test/_test_cubic_metrics_panel.py` 25/25；`_test_cubic_render_opts.py`
  72/72、`_test_cubic_entry.py` 33/33、`_test_tri_metrics_panel.py` ALL PASS。

- **P1 三維宏 op 執行器（2026-11-19 已完成）**：`_execute_cubic_macro_op`
  已鎖 40 連 op（動畫開／關）、`side=None` 由 `rep_cell` 反推側別、
  `rep_cell` 失效退回同側找塊、壞 gap 明確失敗並清隊列；三維 GUI 錄製／執行
  入口已 gate，提示「三维暂未开放宏功能」。護欄
  `test/_test_cubic_macro_exec.py` 15/15。求解器路徑仍直接使用
  `macro_exec_ops` + `_execute_cubic_macro_op`，不經過 GUI gate。
- **P2 三維聚攏求解器（2026-11-19 已完成）**：新增 `solver/ml/cubic_gather.py`；
  三維 action adapter（`r/c/d` 三縫族、兩側、兩方向）；三維前綴和枚舉 6 種軸排列
  窗口；`gather_solve_unified` 分派 cubic；`SOLVER_FORM_SUPPORT['gather']` 加 cubic；
  其他算法仍明確拒絕三維。只做重疊率貪心，不承諾還原；返回 `form='cubic'`，
  GUI `_handle_gather_result` 已按三元 bbox 寫文案，且三維 `rep_cell` 保留三分量
  （不再被二維分支截成 `[r,c]`）。
  目標盒約束改用 **mod 不變量**（不是棋盤邊界）：`cubic_mod_constraints()`
  按每軸 mod 分佈鎖定非整除軸的窗口起點餘數，`cubic_metrics()` 接受
  `step` / `mod_constraints`，求解器一輪只算一次；等級 1 或三軸都整除時
  無約束。護欄 `test/_test_cubic_gather.py` 665/665：3D 前綴和 vs 暴力、
  平移/軸置換仍 score=1、mod 約束（3×3×3/step2 鎖 (0,0,0) 與強制餘數過濾）、
  4×4×4 短聚攏可逐步重放、終態與返回 end 一致、GUI 轉換保留三元 rep、
  播放/收尾文案三元 bbox。三維目標盒已在棋盤上投影成綠色線框，測試由
  `_test_cubic_metrics_panel.py` 覆蓋「畫框用同一份 window」。
- **P3 自訂還原態**：低優先，暫不動。
- **P4 文檔同步**：§54 已補 P2；後續箭頭/相機凍結/縮放/引擎標籤補記。

### 已知狀態

- HEAD 為本次三維收尾提交（調試面板聚攏數據/目標盒 + mod 約束 + 文檔），
  工作樹在提交前含這批改動。
- 三維 28 套測試：27 套全綠；`_test_cubic_vk.py` 50/51，唯一紅是既有的
  「箭頭外接矩形角部重疊」斷言，不是箭頭多邊形本體重疊。
- 三維 GUI 宏已 gate（15/15）；求解器內部 op 執行器已鎖 40 連 op；
  P2 聚攏 665/665（含 mod 約束），4×4×4 打亂短聚攏 0.344→0.516 共 18 步可重放；
  實機自動求解入口跑通（20 步、34.4%→53.1%、停機原因「達到時間上限」）。
  三維調試面板 25/25，目標盒綠色線框已在棋盤上可見。
- 修正一個會擋住 P2 的既有 bug：`_current_kind()` 原先把 `cubic` 落到
  `game.kind` 的「非四形態」分支，`_is_model_kind()` 因此把三維局當自造
  謎題，`_model_blocked` 讓自動求解入口提示「求解器暫不支持」。現在
  `cubic_mode` 顯式回 `'cubic'`，`_is_model_kind` 允許 `'cubic'`。
- 下一步：核對三維自動求解入口與 `gather_params` 參數映射（GUI 目前可能把
  二維參數原樣傳入，cubic 會記進 `ignored_kwargs`）；P3 自訂還原態仍低優先。
