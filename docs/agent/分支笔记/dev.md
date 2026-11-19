> **受眾**：AI（dev 分支私有筆記，隨分支生命週期走，不進 main）

# dev 分支笔记

## 认领

- **认领 §五十七（部分输入框按一下键输入两次）**，2026-11-19 用户拍板交 trae，本分支开工。
  范围按总账：`gui/events.py`（输入上下文注册表替换写死白名单）+
  `gui/cubic_create.py`（两处直调 `start_text_input` 改走统一入口）；
  不动 KEYDOWN 插入路径、`_text_input_mode` 仍留类级全局（§五十八 的事）。

## §五十七 完成记录（2026-11-19，本分支已 commit，待主目录核实核销）

- **根因复核实锤**（headless 复现脚本）：自定义框开着时 `_sync_ime_text_input`
  早退（`needed=False` 与 `_ime_text_input_on=False` 相等 → 连 stop 都不调），
  SDL 默认 text input **是开着的**（实测 `SDL_IsTextInputActive()==True`），
  于是 KEYDOWN.unicode + TEXTINPUT 双投 → 单次按键 `field='55'`。
- **改法**：
  1. `gui/events.py` 新增模块级注册表 `_IME_TEXT_INPUT_CONTEXTS`
     （每条 = 名字/打开判据/IME 锚点矩形），原白名单四项 + 漏掉的
     `show_custom_dialog`（'custom'）、`_ann_design_name_active`（'design_name'）
     共 6 条；`_sync_ime_text_input` 只读注册表，新增 `_ime_contexts_active()`
     供护栏断言。早退条件补 `_ime_text_input_on` 默认 None →
     **启动首帧无上下文也会 stop**（修掉 SDL 默认开着这一半根因）。
  2. `gui/cubic_create.py` 三处直调 `pygame.key.start/stop_text_input()`
     （进入编辑 / 退出编辑 / 点名字框）全部改 `self._sync_ime_text_input()`；
     全仓直调只剩 `events.py` 统一入口（grep 已核）。
- **护栏**：`test/_test_dialog_input.py` 扩 §C 节 12 断言——同一按键投
  KEYDOWN+TEXTINPUT 只进一次（ASCII + 全角各一）、注册表随对话框/命名框
  开关增减、原四项不回归。
- **实跑**：`_test_dialog_input` 23 项 / `_test_cubic_custom` 33 项 /
  `_test_cubic_create` 106 项 / `_test_textinput_full` 40 项 /
  `_test_command_palette` 全过 / `_test_menu_redesign` 56 项 /
  `_test_feature_index` ALL PASS；compileall 过、collect 233 条过。
  静态 lint / doclink 的 NEW 项均为本分支开工前已存在的脏文件
  （`experiments/_probe*` 未跟踪、`test/_tmp_save` 旧文件、`.trae/` 计划文档），
  与本节改动无关。
- **未做（按总账边界）**：KEYDOWN 插入路径未动、`_text_input_mode` 仍类级、
  6 处手写 KEYDOWN 框未接 TEXTINPUT——都是 §五十八 的范围，挂起待触发。
