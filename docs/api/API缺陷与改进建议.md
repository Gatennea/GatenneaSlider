# GatenneaSlider HTTP API 缺陷与改进建议

> **受众**：AI / 開發者
>
> **编者核实注（2026-10-15，蒼緋）**：第 1/2 条关键事实已对源码核实属实（`resp_q.get(timeout=30)` 见 http_server.py:589；懒加载链 game.py:519 → solver/\_\_init\_\_ → solver/ml/ai_solver.py:19 `import numpy` 属实）。第 9 条「切 practice 会重置局面」**已证伪**：`gui/speedrun.py:59` 的 set_game_mode 只切模式 + 停表归零，零棋盘副作用（2026-10-14、10-15 两度代码实证）。其余条目未逐条复核。

> 来源：2026-10-15 实测（feat/api-info-layer 分支，含 9edbec8/a3f9b21/b2db589 三提交）+ 源码走读。
> 分级：🔴 严重（会卡死/误导）｜🟡 中（体验/效率）｜🟢 轻（锦上添花）

---

## 🔴 1. 命令处理是同步串行 + 30 秒硬超时（最大痛点）

**现象**
- `POST /shuffle` 首次调用超时，返回 `{"ok":false,"message":"命令处理超时"}`，但命令**仍在后台执行**；
- 超时后 GUI 主线程若仍忙，**所有后续请求（含 GET /status）继续排队阻塞**，表现为"服务假死"；
- 没有任何"命令执行中/忙"的状态暴露给调用方，无法区分"慢"和"死"。

**根因**
- GUI 主线程串行消费 `cmd_queue`；HTTP 层 `_post_command` 用 `resp_q.get(timeout=30)` 等结果，超时即报错但命令不取消。

**建议**
1. 长命令（shuffle/求解/大棋盘动作）改为**子线程或子进程执行**，GUI 主线程永不阻塞；
2. 命令执行中返回 `202 + task_id`，提供 `/tasks/<id>` 轮询进度/结果；
3. 至少在 `/status` 增加 `busy: bool` + `current_command` 字段，让调用方一眼看到"服务在忙什么"；
4. 超时报错文案明确"命令可能仍在执行，请稍后轮询 /status"。

---

## 🔴 2. 重型依赖懒加载 → 首次调用在 GUI 主循环里死锁

**现象**
- `game.shuffle()` 首次触发 `from solver.deadend_guard import ...` → 整包 `solver/__init__.py` → `solver.ml.ai_solver` → `import numpy`；
- numpy 扩展模块（`numpy._core.multiarray` 的 .pyd）**在 SDL 线程活跃的 GUI 主循环里首次加载 → DLL 加载死锁**（py-spy 实测：主线程 8 分钟纹丝不动卡在 importlib；独立进程 `import numpy` 只要 0.7s）；
- 后果：窗口 `Responding=False`，一切 HTTP 请求超时，只能杀进程。

**已做的临时修复**
- `main.py` 顶部加预热 `from solver.deadend_guard import has_deadend_guard, is_deadend`（干净环境 2s 加载完）→ shuffle 实测 0.09s。
- ⚠️ 这只是把"首次 import"挪到安全时机，**其它未预热的懒加载路径（求解器、其他 solver.ml 模块）仍可能踩同一坑**。

**建议（根治）**
1. 启动时统一前置 import 全部重型模块（求解器全家桶、numpy），并把它们从"shuffle/求解"路径解耦；
2. 或把求解/打乱放到**独立进程**（多进程隔离，GUI 永不因算法/加载卡死）——这也顺带解决第 1 条；
3. 至少：给 http_server 包一层"看门狗"，检测主线程长时间无响应时自动 dump 栈/重启服务。

---

## 🟡 3. JSON body 不兼容 UTF-8 BOM

**现象**
- 用 PowerShell `Set-Content -Encoding UTF8` 写 body 文件（带 BOM）→ 服务端 `json.loads` 报错，例如 `/mode` 返回"mode 必须是 practice 或 timed"；
- 排查半天，最后只能用 python urllib 绕开。

**建议**
- 服务端读取 body 用 `encoding='utf-8-sig'`（或 `body.lstrip('\ufeff')`）容错，一行修复。

---

## 🟡 4. 鉴权令牌的获取与启动竞态

**现象**
- 令牌只通过 stdout 打印一行 + 游戏设置页复制；**进程重启即失效**，外部程序每次重启游戏都得重新抓；
- 启动早期偶发 401（HTTP 已打印"服务已启动"，但 GUI 尚未完全就绪的窗口期请求被拒）；
- 401 只回"令牌无效"，不区分"令牌错误"与"服务未就绪"。

**建议**
1. 服务未就绪时返回 `503 Service Unavailable`（而不是 401 令牌无效）；
2. 令牌支持固定/持久化选项（或提供 `--auth-off` 本机调试开关）；
3. 错误信息区分 `token_missing` / `token_invalid` / `service_busy`。

---

## 🟡 5. shuffle 参数写死、外部不可控

**现象**
- `bias=0.3`、`min_score=0.75`、`attempts=m*n*10` 全部硬编码在 GUI.py，HTTP 无参数通道；
- 外部无法控制打乱难度/重洗阈值，行为不可预期。

**建议**
- `/shuffle` 支持 body：`{bias, min_score, attempts}`（带默认值），并在响应里回显实际使用的参数。

---

## 🟡 6. 动作分析：preview 只画单步、actions 枚举 O(N²)

**现象**（feat/api-info-layer 已加的改进，仍有残留）
- `/analysis/preview` 只返回**单步长**移动后的状态，无法预览"整条路径/多步"结果；
- `/analysis/actions` 是 O(N²) 全枚举，大棋盘（10×10+）会明显变慢。

**建议**
- preview 支持 `steps: int`（多步）或直接预览整条动作序列的终态；
- actions 支持按缝隙/方向过滤或增量枚举，避免每次全量 O(N²)。

---

## 🟡 7. 错误信息不友好、无错误码分层

**现象**
- "命令处理超时" / "未响应" / "令牌无效" 等文案过简；
- 调用方无法程序化区分：参数错 / 权限错 / 服务忙 / 命令执行中。

**建议**
- 统一响应体：`{ok, error_code, message}`，`error_code` 用稳定枚举（`invalid_param` / `unauthorized` / `busy` / `timeout` / `command_running`...）。

---

## 🟡 8. 无取消/恢复通道

**现象**
- 一旦命令卡死（死锁/超长求解），没有取消手段；`/quit` 也被同一主线程阻塞，只能杀进程。

**建议**
- 命令带 `cancel_token`，HTTP 提供 `/commands/<id>/cancel`；
- HTTP 服务与 GUI 主线程解耦（独立线程池），保证"控制面"永远可响应。

---

## 🟢 9. API 文档与状态机说明不全

**现象**
- `/help` 索引齐全，但以下语义靠猜/读源码：
  - `/timer/*` 各端点参数与返回值；
  - timed 模式 `timer_state` 转换（idle→ready→running→finished）；
  - `/mode` 切换的副作用（切 practice 会重置局面、计时器状态变化）；
  - undo/redo 栈的边界（空栈行为、与 shuffle 的关系）。

**建议**
- 补：端点参数表（/help/<端点> 已起步）+ 模式/计时状态机图 + 典型调用序列示例。

---

## 🟢 10. 进程生命周期脆弱，状态恢复语义不透明

**现象**
- 游戏退出即令牌/HTTP 会话全失；未保存进度靠 `config/temp_history.json` 自动恢复；
- 恢复的可能是 `solved=True` 的"完成态"存档——外部程序拿到后若直接开始"还原"会以为已解完，实际必须先 shuffle 才有挑战局面。

**建议**
- `/status` 增加 `restored: bool`（是否恢复自临时存档）+ `restore_note`；
- 提供显式 `/new_puzzle` 端点（不依赖 GUI 菜单），让外部能干净开局。

---

## 附：值得保留的好设计（避免改坏）
- **stdin 命令通道不设防、HTTP 必须鉴权**——威胁模型清晰，很好；
- **Bearer 头 + URL 参数双通道**传令牌，兼容性好；
- **写操作统一走 select_gap → select_block → move 三步序列**，状态可回查，试错友好；
- **undo/redo 无参数**，配合 /analysis/actions 可做"有底试错"，体验优秀；
- 每步 700–800ms 动画延迟是 UI 层体验，API 层若能提供 `animation: false` 加速模式会更适合程序控制。
