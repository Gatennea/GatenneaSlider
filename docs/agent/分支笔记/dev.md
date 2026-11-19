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
  与 §五十六/§五十八 不交叠。完成后只 commit 到 dev。

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
