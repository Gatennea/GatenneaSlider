> **受眾**：AI（dev 分支私有筆記，隨分支生命週期走，不進 main）

# dev 分支笔记

## 认领

- **认领 §五十七（输入框双插）**，2026-11-19 用户拍板交 trae。
  完成 → `eda1f60`，主目录已核销（`5216e0d`）。
  （注：本文件早期版本在分支同步中丢失，此处重建。）
- **认领 §五十九（三维与二维的说明体系 A–E）**，2026-11-19 用户拍板交 trae，
  承接 §五十七 后连续做。完成后只 commit 到 dev、不推送不合并，回报节号
  由主目录核实核销。→ 已交付 `51a1ff7`，主目录已核销（`130c977`）。
- **认领 §六十一（§五十九 新增入口未登记功能索引）**，2026-11-19 用户
  指示开工。范围按总账：`gui/feature_index.py` 补条目 + 同步 support 表 +
  重成功能总览 + 测试（`_test_feature_index` / `_test_help_cubic59`），
  与 §五十六/§五十八 不交叠。完成后只 commit 到 dev。→ 已交付 `abb137d`。
- **认领 §六十二（三维打光实体感移植到二维）**，2026-11-19 用户点名交
  trae（dev 分支）。范围：`gui/renderer.py` + 设置页开关（三处同步）+
  测试；与 §五十六/§五十八 文件交叠小。先做第 2 层（四边微倒角抽公共
  helper 接三形态），第 1 层降级不硬套相机基，第 3 层（留缝）不动。
  默认开/关按观感定，验收 `GET /screenshot` 开关对比 + 关态渲染与改动前
  一致的断言。完成后只 commit 不推送不合并。

## §六十二 完成记录（2026-11-20，本分支已 commit，待核销）

- **第 2 层（核心）**：三维面片倒角画法抽成模块级公共函数
  `gui/renderer.py::_draw_face_bevel`（n 边泛化——三角/米字块面不是四边形；
  `corner_inset` 参数供矩形圆角收端，带不碰角部）。**三维段改为调用它
  （同参 strength=30/inset=0.15，行为逐位一致）**；二维三形态各接一次：
  方形（draw_board fill 与 border 之间）、三角/米字（AA 与非 AA 双路径——
  AA 版给 `_draw_aa_polygon` 加 `bevel=False` 默认参数，在超采样面的
  fill 与 border 之间压带，默认零变化）。
- **第 1 层降级**：不硬套 `face_shade` 相机基——二维用窄带本身携带
  「上/左提亮、下/右压暗」的面内明暗（方向与三维同一 helper 数学），
  面心保持原色，未引入逐行渐变（性能无风险）。
- **第 3 层（留缝）**：按总账未动。
- **开关 `face_bevel_enabled`（默认开——用户点名要这效果）**：
  只管二维三形态；**三维恒走原倒角不受开关影响**（关态=改动前，三维
  行为零变化）。设置页「视觉页·分组着色下一行」+ `_handle_right_panel_switch`
  同支（Ctrl+K 一键切换）+ `_SETTINGS_BOOL_KEYS`×2 + config 存取——
  三处同步（AGENTS §16）。三维局设置页不显示（入清零列表防旧帧残留）。
- **feature_index 登记（§3 新红线）**：`face_bevel_enabled` setting 条
  （forms=方/数/三角/米字，三维标不适用）+ `_ACTIONS` toggle +
  测试 `_RECT_TO_ID` 登记；总览重生成 82 项，README 计数 81→82。
- **护栏**：新 `test/_test_face_bevel.py` 29 断言全过——关态三形态
  **零次**调用倒角（运行时计数，非源码判据=「关态渲染与改动前一致」）、
  开/关两帧像素不同、关态两帧一致、方向数学（上亮下暗面心原色）、
  AA 双路径同源、设置页点击/一键切换/config roundtrip。回归全绿：
  `_test_engine_gui` / `_test_bandage_forms` / `_test_feature_index`；
  compileall 0。
- **截图验收（AGENTS §20 `GET /screenshot` 通道）**：新实例 5053
  （`--http-port` 换端口不碰用户实例，验完强杀防写 temp_history）。
  首拍踩坑：实例恢复用户三维局盖掉启动参数 → 对比图无效（三维不吃开关）；
  改 `POST /new` 切回 6×6 方形后重拍成功：`s62_off.png`（纯平）vs
  `s62_on.png`（四边明暗带、圆角完好），两图存工作区根（未跟踪、不入库）。
- lint NEW=1（存量 `_tmp_save`）、doclink NEW 中涉本节的均为既有文档
  引用 `renderer.py` 因目标修改重新入列（renderer.py 真实存在，非断链）。
- **补接（2026-11-20 用户问「其他二维谜题改了没」后排查）**：`draw_board`
  三分流——方/数字走手画循环（**数字已随方形覆盖**）、`_polygon_view`
  非空走 `_draw_polygon_board` 聚合填色趟（**碎三角/模型板，首交付漏了
  这条，已补同款 gate**）、triangle_mode 走三角。捆绑组**刻意全不接**：
  它是逐块填色+桥接拼合（`_draw_bandaged_groups_poly`/`draw_group_chunks`），
  逐格压带会画出组内不存在的假内棱，外轮廓级倒角需几何重构、超 §六十二
  范围——全不接反而让所有捆绑态统一平坦（部分接=矩形鼓异形平，更不一致）；
  预览缩图非游玩盘面不接。护栏补「碎三角(聚合板)」4 断言（33/33），回归
  engine_gui / bandage_forms / gap_second_step 全绿。

## §六十一 完成记录（2026-11-19，本分支已 commit，待核销）

- **help 条扩 aliases**（总账二选一：不另立 help_tabs 条，避免同一入口
  重复登记）：+三维操作/三维说明/通用说明/帮助页签；howto 改写为三页签
  切换说明；confusion 点破与「设置 → 三维」的混淆。
- **新增 `cubic_intro_replay`（action）**：place 用 `menu_sub`
  （谜题→三维谜题→重看新手引导，place_text 原生支持四元形状），
  进 `_CUBIC_IDS`（任何局的谜题菜单都能点到），
  `_ACTIONS` 注册 `{'type':'menu','name':'谜题'}`——**不加 events 分支**
  （总账限定只碰 feature_index/生成物/测试）。
- **新增 `cubic_ops_card`（concept）**：`forms=('cubic',)` →
  二维局 `available=False`（排序显示 ✕，不隐藏）；`place=('right_panel',)`
  → 「主窗口右下角快捷区」；`_ACTIONS` 注册 `{'type':'none'}`。
- **生成物**：`tools/gen_feature_overview.py` 重生成（81 项，78→81 是
  本节 +3；**README 的「75 项」是旧账过期数字**，顺手改为 81——
  超出总账字面范围但属生成物计数标注，回报中已说明）。
- **测试**：`_test_feature_index` 新增 2-c1 段 7 断言（引导/三维操作/
  常驻/操作卡 首位与可用性 + _ACTIONS/_CUBIC_IDS 防漏）；
  实测 S1/S2/S3 不回归（怎么撤销→undo 100、三角求解→auto_solve+
  preset_exotic、存档在三维→save）。`_test_feature_index` ALL PASS、
  `_test_help_cubic59` 62/62、compileall 0。
- **规定缺口已核**：AGENTS.md / readme_to_agent 中**无**「新入口必须登记
  feature_index」条款（只有 gen 工具说明）→ §六十一 属规定缺失，
  非执行漏项；改进提议（补红线条款 + 合并检查项）已口头报给用户。

## §五十九 完成记录（2026-11-19，本分支已 commit，待核销）

改动按验收五块（A–E）：

- **A 帮助三页**：`gui/dialogs.py` `_load_help_lines(tab)` 按 tab 读三份
  文件并缓存（`_HELP_TAB_FILES` / `_help_lines_cache`）；标题
  `_help_title()` 跟页走；`draw_help_dialog` 标题行右侧加三页签
  （`help_tab_rects`）。`gui/events.py` 页签点击分支（滚动位经
  `help_scroll_pos` 换入换出，每页独立）；新开关 `_open_help(tab=None)`
  默认页按局形态（三维局→三维页），菜单「帮助」与教程入口改走它。
  检索本就走 feature_index（全局），切页结果不丢，缓存键含 tab。
- **文档拆分**：`操作说明.md` 瘦身为二维页（修 1 处跨页引用）；
  新建 `通用说明.md`（快捷键/宏/求解/自定义/关于）；新建
  `三维操作说明.md`（B）。三份全部进 `Gatenneaslider.spec` datas 与
  `docs/README.md` 索引；`玩家指南.md` 补三维节并指到三维文档。
- **E 入口告知**：谜题菜单三维子菜单加 `('… · 查看操作', '__opshelp__')`
  行 → `_open_help('3d')`；自定义框三维态标题行右侧画「查看操作」
  （`custom_opshelp_rect`，点击先关本框再开帮助——绘制/分发顺序上
  custom 压在 help 之上，两框同开点不到）。
- **C 首次引导**：`CUBIC_INTRO_STEPS` 4 步 + 状态机
  （`_cubic_intro_start/close/advance`）；`new_cubic_puzzle` 成功后
  未看过即弹；跳过/走完 → `cubic_intro_seen=True` + `save_config()`；
  重看入口 = 三维子菜单 `('__intro_replay__')` 行；
  `cubic_intro_seen` 按 AGENTS §16 三处同步（config.json 存取、
  events `_SETTINGS_BOOL_KEYS`、http_server 同名白名单）。
- **D 常驻操作卡**：`renderer.draw_cubic_ops_card`（右下角折叠小钮
  → 展开要点卡：回到中央/重看引导/完整说明三按钮），仅三维局画；
  点击分发 `events._cubic_hud_click`（引导卡 + 操作卡统一，
  只吞卡内命中、卡外放行给棋盘，插在浮动面板之后、游戏分支之前）。
  两卡绘制接进 GUI 主循环「非模态浮层」层（模态之下）。
- **护栏**：新 `test/_test_help_cubic59.py` 62 断言全过（A/B/C/D/E 各验收
  项 + 真实事件路径的页签/菜单/入口点击）。回归 7 件全绿
  （feature_index/dialog_input/menu_redesign/cubic_custom/cubic_create/
  cubic_entry/scroll_perf_bench）；compileall、collect 237 过。
  静态 lint NEW=1、doclink NEW=90、experiments 前缀报错——逐一核过均为
  本分支开工前已存在的存量（`test/_tmp_save`、`.trae/` 计划、
  `experiments/_probe*` 未跟踪文件），无一涉及本节文件。

### 本节踩坑备忘
- SliderGUI 上**没有** `small_font`（那是 PygameFileDialog 的构造参数）；
  浮层绘制用 `status_font`（14px）或 `input_font`。
- 新增会话状态必须在 `GUI.__init__` 显式赋初值：`getattr` 兜底只对
  「读」有效，测试/外部直接「读」未初始化属性照样 AttributeError。
- 帮助 `_open_help` 里切页必须同时换出/换入滚动位，否则三页共用一根
  scrollbar 的 scroll 值（验收「各自滚动」直接红）。
