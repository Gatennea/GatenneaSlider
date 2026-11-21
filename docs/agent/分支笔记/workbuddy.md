> **受眾**：AI（workbuddy 分支私有筆記，隨分支生命週期走，不進 main）

# workbuddy 分支笔记

## 认领

- **认领 §五十八 / §六十四 / §六十八（A 组·样式体系）**，2026-11-21 主目录
  分发（`ac0872f 待办: 分发§58/64/68→workbuddy, §65/66/69→dev, §67→doubao`）。
  三节串行：§五十八 先把样式名 / 模型名两框接 TEXTINPUT（用户实测中文命名只能写英文），
  §六十四 改名复用该输入能力，§六十八 示范样式入库。
  按 AGENTS §22：只 commit 到 workbuddy 分支，不 push、不 merge；核销由主目录做。
- 認領本節前的工作區：`workbuddy` 與 `main` 同在 `4ae748e`、tracked 乾淨。

## 计划动的文件（开工前盘点，边做边修）

- §五十八：`gui/annotation.py`（设计样式名框 `_ann_build_dialog_event`）、
  `gui/model_editor.py`（模型名框 `_med_*` + 两道 alnum 过滤）、
  `gui/events.py`（IME 上下文注册表加 `design_name` / `model_name` 锚点、
  TEXTINPUT 转发）；`gui/text_input.py` 口径复用（TextInput.insert_text）。
- §六十四：`gui/design_styles.py`（`rename_style`）、`gui/annotation.py`（样式库菜单 +
  `_ann_style_goal` + 旧档 preset 映射兜底）、存档载入处
  （`gui/file_ops.py` / `gui/compressed_save.py`）、`gui/menu_delete.py`（入口并列）、
  `gui/feature_index.py` + 功能总览。
- §六十八：新建入库目录 + `Gatenneaslider.spec` datas、
  `gui/design_styles.py::list_styles` 合并列出、
  `GUI.py` / `gui/annotation.py` 菜单分流与角标、`gui/feature_index.py` + 功能总览。
- 护栏：真入口测试（中文输入 / 改名四件事 / 旧档载入 / 无 config 目录列出 + 只读），
  不用「源码里有没有某函数」当判据。

## 完成记录（2026-11-21，本分支已 commit，待主目录核销）

### §五十八 两框中文输入
- 二维样式名框 `annotation._ann_build_dialog_event` 加 TEXTINPUT 整串接收
  （handle_annotation_event 先分流），停掉 KEYDOWN.unicode 插字防双插；
  三维框 `cubic_create._cubic_edit_event` 本就接了，作范式未动。
- 模型名框 `model_editor` 新增 `_med_text_input` + IME 注册 `model_name`
  锚点 `med['name_rect']`；KEYDOWN 不再插字。
- **核实修正主目录初查**：`_med_save` 的 `isalnum()` 在 Python 3 本就含汉字
  （实测确认），不是「两道过滤都挡中文」；只改误导文案 + 注释，判断式未动。
- 护栏 `test/_test_style_name_input.py` 20/20；回归 cubic_create / ann_gui 绿。

### §六十四 游戏内样式改名
- `design_styles.rename_style`：os.replace 原子换名 + 档内 name 同步 +
  旧名映射 `.renames.json`（点号前缀不占菜单）；`resolve_name` chain 解析。
- `load_style` 先 config 原名 → 映射名 → builtin；旧存档 preset 写旧名仍读到。
- UI：样式库下拉每项行尾 ✎ 进改名态，复用 §58 名字框（不另造输入框），
  回车提交 / Esc 取消 / 重名二次确认；`_ann_style_goal` 与菜单同步。
- 映射兜底选「不改玩家存档内容」路线（待办二选一的推荐项）。
- 护栏 `test/_test_style_rename.py` 33/33（三类样式 + HUD + 旧档 + 护栏）。

### §六十八 入库示范样式
- 新目录 `assets/presets/design_styles/`（示范-双连带 = 带 groups；
  示范-缺角方 = 无 groups），走 `_collect_assets` 整树进包，spec 注释登记；
  `builtin_styles_dir()` 用 _MEIPASS 解析（tutorial.py 同口径）。
- `list_styles` 合并 builtin + config（同名去重、config 优先）；
  `style_source` / `copy_builtin_to_user` 支撑写权隔离。
- 菜单/下拉显示「·示范」角标；示范项禁删（`_menu_item_deletable`）、
  禁就地改名（行尾改「存」= 另存为自建），另存后可改名。
- ⚠️ 文件名不能用 `·`（中点）—— `sanitize_name` 只允许 `\w/汉字/./-`，
  中点会被替换导致查名失败；已改用 `-`。
- 护栏 `test/_test_builtin_styles.py` 20/20（干净环境列出开局 + 两类分流 +
  只读 + 同名共存）。

### 索引与回归
- `feature_index` 加 `style_rename` / `style_copy_builtin` 两条 action +
  `_ACTIONS` 注册；功能总览重生成 82→84，`docs/README.md` 计数同步。
- `test/_test_menu_redesign.py` E7 因示范恒占两个子菜单而失效 → 临时替换
  builtin 目录为空后再断言「空子菜单不出现」机制，测完还原（报告备查）。
- compileall 0；collect 245；static_lint NEW=0；experiments_index OK；
  doclink NEW=35 全是 worktree 缺 gitignored 目录的既有现象（记忆已载，
  主仓库 exit=0），无一涉及本节所改文档。
- 回归全绿：engine_gui / bandage_forms / menu_redesign / feature_index /
  ann_gui / cubic_create。
