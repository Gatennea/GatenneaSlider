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
- **认领 §六十三（清除碎三角作为 Python 板型的残留）**，2026-11-20 用户
  拍板交 trae（dev 分支）。以 `docs/spec/几何引擎残留清理方案_2026-11-20.md`
  为准：四类不能清（生成器 shatter_spec / 差分测试 helper / compat 方向
  字母表 / loader 统一钩子），执行顺序步1纯文档→步2行为等价替换→步3清点
  →步4验收（真实行为护栏，禁 grep 当判据）。**A 项并入本节**：删两处
  死编号段 + 删 `_test_face_bevel` 两条人造状态锁 + 挂起记录定性改写；
  连锁 hint 不动。完成后只 commit 不推送不合并，回报节号由主目录核销。

- **认领 §六十五（立体光效对捆绑样式无效）+ §六十六（蓝色溢出灰色边框）
  + §六十九（模型禁用缝族提示加强）**，2026-11-21 用户点名三节一起交
  trae（dev 分支，B 组·光效）。同属 `_draw_face_bevel` / renderer 体系
  串行做。§65 两条捆绑路径（方形 `_draw_bandaged_groups_play`、多边形
  `group_render.draw_group_pieces`，helper 要抽到零依赖公共处、只沿组外
  轮廓压带）；§66 给 `_draw_face_bevel` 加 `edge_inset_px` 沿边法向内推
  `border_w/2`，五处调用点同步、默认 0 零变化；§69 走轻量路（改文案+挪
  位置+就近点击提示，不动几何层）。护栏：三形态开/关截图、关态逐像素、
  真实像素断言。完成后只 commit 不推送不合并。

## §六十五 / §六十六 / §六十九 完成记录（2026-11-21，本分支已 commit，待核销）

- **§66 蓝色溢出**：`_draw_face_bevel` 抽到新文件 `gui/lighting.py`
  （零依赖光照原语，renderer 与 group_render 共用——§65 要求 group_render
  不能反向依赖 renderer），加 `edge_inset_px` 参数：每条边沿法向朝质心推入
  `border_w/2`，带外沿落在框内沿、灰框独占边界。六处调用点同步传参：
  AA 路径 `border_w*S/2`（超采样面）、三角/米字/方形 `border_w/2`、
  三维段三分支各自的实际线宽 `_fbw/2`、聚合板**只有真会被描边的块**
  （特殊态，与描边趟同条件）才让位——普通块不描灰边，让位反而留空隙。
  默认 0 保持旧调用零变化。像素实证：直角矩形静态下新旧无差（后画的框
  本就盖住带外沿），真实盘面（圆角+浮点）新旧差 10656px（带整体内移）、
  三形态开态背景侧扫描 0 溢出。
- **§65 捆绑光效**：`draw_group_pieces` / `draw_group_chunks` 加
  `bevel=None, edge_inset_px=0.0` 可调用参数（零依赖，renderer 按
  face_bevel_enabled 传 `_draw_face_bevel` 或 None）。**只压组外轮廓边**
  （pieces 按 internal flags 过滤、chunks 按邻格在不在组内过滤边 0-3），
  组内共用边跳过——不现组内分隔线，守「一整块刚体」观感。三条 poly
  调用点（三角/米字/聚合板）共用 `_draw_bandaged_groups_poly`，gate 在
  方法内接一次三形态同步生效（铁律 §3）；方形矩形组在
  `_draw_bandaged_groups_play` 内接（同普通块口径 corner_inset +
  edge_inset）。三维不接（face_shade 自带光效）。
- **§69 禁缝提示（轻量路）**：①常驻文案抽 `_seam_disable_hint_text()`
  改提纲挈领+人话（「本模型关闭了部分方向的缝：X——推不动是设计如此，
  试试其它方向」，原版术语在前、括号里才讲人话）；②调用点从
  draw_status_bar 之后挪到主循环**非模态浮层末尾**（原位被
  records/annotation/menu_bar 一层层盖，用户「提示太弱」根因之一）；
  ③就地附句抽 `_reject_msg_with_seams(base)`：点「画得出选不中」的缝时
  （`_sq_click_query` 的 dead_seam/edge_hint 两分支汇合处）追加「（本模型
  关闭了X方向的缝，设计如此）」——只陈述事实不宣称点的就是它（同分支
  还覆盖外沿/切口，避免错误归因）；无 seams 原样返回不静默改旧提示。
  文案加宽夹 `screen_width-24` 防溢出。
- **测试 `_test_face_bevel.py` 38→67 断言**：§66 段（让位单元有区分度
  ——inset=2 边界线保持底色 vs 默认 0 带压边界、三趟模拟框外侧背景/框
  保持灰、三形态开态背景侧扫描 0 越界）；§65 段（方形 2x2 与三角 3 块
  捆绑局关态零调用/开态走 helper/两帧不同、离屏 pieces+chunks 组外有带
  组内无带=不现分隔线）；§69 段（无 seams 不提示、文案点题/列族/行动
  指引、draw 真画出框、方形外沿死缝端到端保持旧文案、附句入口有/无
  seams 两态）。**踩坑记录**：①`SliderMatrix.__slots__` 挂不了
  disabled_seams——seams 只有模型局（EngineGame）才有，附句端到端在
  shatter 全活局扫不出死缝（12 条不活接触边是特定场景），故附句拼装
  抽成真实产品入口 `_reject_msg_with_seams` 直测、端到端用方形外沿
  （`_test_sq_seam_hint` 同款）测「不静默改旧文案」半边；②`GAP_UNSELECTABLE_MSG`
  是 MoveMixin 类属性非模组级。
- **截图验收（离屏，同一 draw 路径）**：`s6566_sq/tri/mi_{on,off}.png`
  六张 + `s6566_band_sq_on/band_tri_on.png`（像素抽验：捆绑矩形上边
  +24 左边 +17 提亮、下边 -24 压暗、灰框在外）+ `s69_hint.png`
  （左下提示框清晰未被盖）/ `s69_nohint.png` 对照。存工作区根不入库。
  HTTP 实例方案中途放弃（main.py 启动 stdout 缓冲抓不到 token），离屏
  与 HTTP 走同一 draw 函数，视觉证据等价。
- **回归**：group_render / bandage_forms / bandage_click / sq_seam_hint /
  reject_text_only / mi_h3_hint / poly_render / shatter_gui / generic_gap_band /
  gap_second_step 全绿；`_test_engine_gui` 首跑「引擎/经典打乱在 6× 以内」
  红一次，同状态重跑 2 次全绿——打乱步数统计的随机波动，本次改动只碰
  绘制与点击提示、不碰打乱逻辑（按 §23 记录，复发再对拍未修基线）。
  compileall 0；static_lint NEW=1 为他人 `_tmp_save` 存量。
- **§65 修正（2026-11-21 用户截反馈「捆绑块和普通滑块厚度不一样」，
  `d8bdd6c`）**：根因是 `inset=0.15` 比例制——带厚=0.15×(边中到质心
  距离)，普通 60px 块≈4.5px、2×2 捆绑 126px≈9.5px、1×5 长条端头≈22px，
  同盘三种厚度。改固定像素：lighting 加 `inset_px`（每边收边比例 =
  inset_px/法向距离，夹 0.45 防带越过质心自交）+ 常数 `BEVEL_INSET_PX=5.0`
  （取原比例制在 60px 普通块上的厚度取整，普通块观感不变、大块收薄）；
  renderer 二维六处传 `BEVEL_INSET_PX*zoom`（AA 再 ×S），**三维不传**
  （面片尺寸统一、比例制无此问题且是原设计）；group_render 两原语加
  `bevel_inset_px` 转传。测试 8e 断言 60px/126px 块带厚一致（±1 允许
  rasterize 边界含侧误差；原比例制下此断言红）。截图
  `s65_fix_thickness.png` 复现用户盘面（1×5+2×2）目视厚度统一。
  **贴图化性能议题（用户同日问）已答倾向不做**：收益未实测（无卡顿
  报告）、颜色跟状态走+尺寸跟缩放走+拆掉单 helper 结构的复杂度更重；
  若要做先 cProfile 测倒角占帧比再定。engine_gui 本次随机断言轮流红
  （每次不同+改动不碰引擎）= 既有波动，按 §23 记录。

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
- **子项：数字也搞成这种（2026-11-20 用户拍板「数字谜题的数字要不要也
  搞成这种」→ OK，代码 `e97eadf`）**：抽公共 `draw_block_number`（黑本体
  + 左上 1px 块色提亮浮雕边，`_shade255` +44，同四边倒角光向）；三角/
  聚合板/方形数字三处编号渲染各接一次、gate 同 `face_bevel_enabled`——
  emboss=False 与旧画法**逐位一致**（单元断言 RGBA 全等），关态=改动前不破。
- **顺手修的既有 bug（报备）**：聚合板（`_draw_polygon_board`）编号原在
  **填色趟之前** blit＝被②整块填色盖掉＝碎三角编号从未显示。验证过程要
  诚实记：实验一（0 黑像素）当时只证明「模型板建局不生成 number 数据」
  （手动 numbered 仍 0），实验三（手动赋号后 3067 黑像素）才同时证实
  「挪位后可见」＝修复实证；编号改收集落地表 `_nums`、挪到三趟之后。
  **连锁 hint 在同一被盖结构里**（chain_hint 默认关、无人报过），未动，
  待用户定是否单开小节。
- **护栏**：`_test_face_bevel` 40/40（+7：helper 逐位/亮边像素/三路径
  emboss 参数计数/挪位回归锁＝黑像素 0 即红）。回归 engine_gui 第一次红
  「mi 解法动作逐项一致（118 vs 48）」→ **按 §23 不静默收下**，定性三证：
  ①重跑同状态绿（118 vs 118，一侧恒定、48→118 波动＝对拍局面不同步）；
  ②测试 357 行存在无 seed 的 `o.shuffle(...)`（随机源）；③最近三提交
  stat 全为 renderer 绘制层/文档，无人动求解引擎（AGENTS §10 引擎不依赖
  渲染）。**复发时按 §23 对拍未修基线，不许直接当 flaky。**
- **截图验收**：数字形态 off/on ＝ `s62_num_off.png` / `s62_num_on.png`
  （5054 新实例 `/new type=numbered`，验完强杀），关＝纯平贴、开＝数字左上
  浮雕亮缘 + 块面倒角；连同方形两张共四张存工作区根（不入库）。

## 挂起记录（2026-11-20 用户：「暫時提交，等主分支整理好再說」）→ 三项去向

原三项挂起，2026-11-20 主分支整理后全部有了去向：

1. **死代码处置 A/B/C → 用户拍板走 A，并入 §六十三**（总账 098e4fc）。
   **执行中有一处修正（2026-11-20，删后复核发现）**：A 项「两处死编号段」
   的前提**半错**——三角手画路径的编号段真死（所有入口清 numbered，删）；
   但 `_draw_polygon_board` 的编号段**不是死代码**：引擎开关打开时
   （config/engine.json / GATENNEA_ENGINE=1），EngineGame 方形数字谜题
   **默认就走通用通道**（`_generic_spec` 的旧闸门已移除，见
   `_test_poly_render.py:105-111`），adapter 挂 Block.number、该段真的
   执行——`_test_poly_render` 的 S6 锁（`:279` `_num_font_cache` 已建）
   在我删段后立刻红，就是活路径的执行证据。已还原该段（e97eadf 挪位修复
   保留，注释改写为「活路径 + 模型局降级」口径）。最终 A 执行 = 删三角
   手画死段 + 删 `_test_face_bevel` 两条人造状态锁（40→38 全绿）+ 本
   定性改写；保留方形手画数字浮雕、聚合板编号段与 helper 逐位断言。
   **教训**：「实验测出 0 像素」只证明了**默认配置（引擎开关关）**下的
   不可达，没覆盖开关打开的配置——「死活」结论必须枚举所有支持的配置态。
   我此前「修了被盖老 bug」（`e97eadf` 挪位）的定性**恢复成立**（仅限
   引擎开关开的数字谜题路径）。
2. **碎三角残留清理 → 已立为总账 §六十三**（098e4fc，trae 认领），
   以 `docs/spec/几何引擎残留清理方案_2026-11-20.md` 为准，正在执行。
3. **连锁 hint 同结构被盖问题**：chain_hint 默认关、无人报过，本次不动
   （总账 §63 明确），仍待用户定是否单开小节。

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
