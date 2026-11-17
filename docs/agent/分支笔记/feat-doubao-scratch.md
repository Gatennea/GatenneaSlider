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



