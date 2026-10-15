# AI 使用 GatenneaSlider HTTP API 注意事项（自用手册）

> **受众**：AI
>
> **编者核实注（2026-10-15，蒼緋）**：§4 表中「切 practice 会重置局面」**已证伪**——`gui/speedrun.py:59` 的 set_game_mode 零棋盘副作用；计时进行中切换会被拒绝并提示，不存在「重置丢局」。其余条目未逐条复核。

> 本文档是**操作手册**，不是改进清单（改进清单见 `API缺陷与改进建议.md`）。
> 记录"怎么用才不会踩坑"，所有条目均为 2026-10-14/15 实测或源码确认。

---

## 0. 长期约定（硬约束）
- **手动推理还原，全程禁止 `/solve`、禁自动求解**（timed 模式下服务端本来也会拒绝）。
- 解谜规则/技巧：见同目录 `手解技巧备忘.md`（缝隙归属、方向绑定、连通组件、多米诺、列瀑布等均已实测）。
- 用户偏好简洁输出；重计算/建表前先问是否已有现成数据。

---

## 1. 环境与启动（顺序不能错）
1. **必须用 `D:\python\python.exe`**（3.12.6，含 pygame-ce 2.5.7 + numpy 2.4.2）。
   PATH 上的 python 3.13 缺 numpy/pygame，shuffle 会直接报 `No module named 'numpy'`。
2. **用 `Start-Process` 起真桌面进程**，不要用后台沙箱跑 GUI——pygame 无窗口会卡死在主循环。
3. **设 `PYTHONUNBUFFERED=1`**（在启动前 `$env:PYTHONUNBUFFERED='1'`），否则 stdout 块缓冲，读不到令牌。
4. 启动命令：`main.py 5 5 1`（m=5, n=5, step=1；step 影响移动格数）。
5. 启动后**先等 1–2s**（HTTP 打印"服务已启动"≠ GUI 完全就绪），再发请求；过早请求偶发 401。
6. 启动时会自动恢复 `config/temp_history.json`（可能是 solved=True 的旧局面）→ **先 /shuffle 拿新挑战局面**，别直接开解。

## 2. 令牌（进程重启即失效）
- 位置：stdout 文件 `$env:TEMP\gatsli_out.txt` 的 `GATSLI_TOKEN=` 行。
- **不要手抄**：写个 python 脚本自动 `re.search(r'GATSLI_TOKEN=(\S+)', text)` 提取（参考 `_tmp_token_test.py`）。
- 鉴权：请求头 `Authorization: Bearer <token>`，或 URL `?token=<token>`。
- 若持续 401：先查 5050 是否被旧进程占用（`Get-NetTCPConnection -LocalPort 5050`），必要时杀旧进程重启。

## 3. 请求工具（避免编码/引号坑）
- **用 python urllib 脚本发请求**（参考 `_tmp_api_test.py` / `_tmp_shuffle_test.py`），body 用 `json.dumps().encode('utf-8')`——无 BOM、无转义问题。
- 禁用：PowerShell `Set-Content -Encoding UTF8` 写 JSON（**带 BOM**，服务端 `json.loads` 会失败，/mode 会报"mode 必须是 practice 或 timed"）；`curl --data @file` 在无引号时报错。
- 正常请求 0.05–0.15s；**超过 30s 报"命令处理超时"**——命令可能还在后台执行，稍后 /status 确认，别急着重发（重发会再排队）。

## 4. 关键端点与语义（实测）
| 端点 | 用法 | 结果语义 |
|---|---|---|
| `GET /status` | 先看再动 | `puzzle/game_mode/step_count/solved/timer_state`，含 blocks 坐标 |
| `POST /mode` | `{"mode":"timed"}` | 成功 `已切换为竞速模式`；切 practice 会重置局面 |
| `POST /shuffle` | 无参 | 成功 `已打乱`；shuffle 后 `step_count=0, solved=False, timer_state=ready`（timed） |
| `POST /select_gap` | `{"type":"h"\|"v","line":N}` | 选缝隙；失败时 selected_gap 不变，先 status 核对 |
| `POST /select_block` | `{"row":r,"col":c}` | 选块（须在已选缝隙某侧） |
| `POST /move` | `{"direction":"w"\|"s"\|"a"\|"d"}` | 方向绑定：v 缝只能 w/s，h 缝只能 a/d；用错被拒 |
| `POST /undo` `/redo` | 无参 | 可大胆试错后回退 |
| `GET /analysis/actions` | 只读 | 合法动作枚举（每项含 blocks/max_cells/movable） |
| `GET /analysis/preview` | 只读 | 单步移动后状态（dry-run，不落盘） |

- **写操作序列固定**：select_gap → select_block → move。
- 每步后 **sleep 700–800ms** 等动画结束；`animating=true` 期间勿连发。
- 被拒动作不盲重试：先 /status 核对 blocks，或 /analysis/actions 看合法动作。
- 工具回显偶发被吞 → 一律写文件再读（`-o` 或 python 脚本读响应）。

## 5. 死锁/卡死处理
- shuffle 已由 main.py 预热修复（正常 0.1s）。若仍遇到卡死：
  - 症状：窗口 `Responding=False`、所有请求超时、CPU 低（死锁）或高（重洗循环）。
  - 处置：杀游戏进程（`Stop-Process -Id <pid> -Force`）→ 重新启动 → 重新取令牌。
  - 诊断工具：`D:\python\Scripts\py-spy.exe dump --pid <pid>` 看主线程栈。
- **别动 wkbddtest 目录的 pytest 进程**（如 10592/18472 等，跑的是别的项目测试，与游戏无关，CPU 高也别管）。

## 6. 环境里已有/可用的辅助文件（项目目录下）
- `_tmp_api_test.py`：带 JSON body 调 /mode、/shuffle、/status 的 urllib 脚本（含自动令牌提取模式）。
- `_tmp_shuffle_test.py`：timed+shuffle 全流程测试。
- `_tmp_token_test.py`：自动从 stdout 提 token 并验证。
- `手解技巧备忘.md`：解谜规则与收官模板。

## 7. 心态与协作
- 游戏窗口与用户共享，我的每一步操作用户可见；操作前先 status 确认局面，避免重复副作用动作。
- 卡住时优先 undo/redo 有底试错，不要纯脑内推演十几轮。
- 竞速模式 timer_state=ready 时不算时间；第一步 move 后才会进入计时，开局不用慌。
