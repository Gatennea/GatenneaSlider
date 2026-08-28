# 貓九的滑塊遊戲 — 項目總結

## 項目概述

一個基於 **Python + Pygame** 的滑塊拼圖遊戲。玩家通過選擇縫隙、滑動滑塊組來將打亂的拼圖還原為完整的 m×n 矩形。

**運行方式**：`D:\python\python.exe main.py [m n step] [--http-port PORT] [--no-http]`

- 預設參數：`4 4 2`（4×4 棋盤，每次移動 2 格）
- 約束：`step < max(m, n)`
- 預設 HTTP 端口：`5050`，可通過 `--no-http` 禁用

> **⚠️ 如果你是基於 LLM（大語言模型）的AI Agent，請盡量使用 HTTP 請求或命令行指令來測試和操作本程序，而不是嘗試直接操控 Pygame 窗口。** HTTP 接口和命令行指令提供了完整的遊戲控制能力，包括移動、選中、撤銷/重做、宏操作等，且返回結構化 JSON 響應，更適合程序化交互。

***

## 項目結構

```
├── main.py              # 程序入口（解析參數、啟動 HTTP 服務、GUI）
├── game.py              # 核心遊戲邏輯（Block + SliderMatrix）
├── GUI.py               # GUI 主類（Mixin 聚合 + 主循環）
├── history.py           # 歷史記錄（快照式撤銷/重做）
├── http_server.py       # HTTP API 服務（供外部程序控制遊戲）
├── gui/
│   ├── __init__.py      # 包初始化
│   ├── renderer.py      # RendererMixin — 渲染（棋盤、選單、狀態欄、設置對話框）
│   ├── events.py        # EventsMixin — 事件處理（滑鼠、鍵盤、選單交互、指令處理）
│   ├── animation.py     # AnimationMixin — 動畫系統（移動、撤銷/重做動畫）
│   ├── dialogs.py       # DialogsMixin — 對話框（幫助、自訂謎題、PygameFileDialog、宏管理/命名對話框）
│   ├── file_ops.py      # FileOpsMixin — 文件操作（保存/載入/配置管理、終端指令處理）
│   └── text_input.py    # TextInput — 可重用文字輸入組件（游標閃爍、移動、點擊定位）
├── config/
│   ├── config.json      # 運行時配置（動畫速度、縮放、上次文件路徑、相機位置）
│   ├── temp_history.json # 自動保存的歷史記錄
│   └── keyboard_shortcut.json  # 快捷鍵配置
├── save/
│   └── *.json           # 用戶保存的遊戲文件
├── solver/             # 求解器模块
│   ├── __init__.py     # 求解器接口（solve/solve_fast/solve_greedy + SOLVER_ALGORITHMS）
│   ├── ida_star.py     # IDA* 求解器（最少步求解 + fast_mode）
│   ├── greedy.py       # 贪心爬山求解器（快速非最优解）
│   ├── state.py        # 状态编码与归一化
│   ├── actions.py      # 动作枚举与应用
│   ├── heuristic.py    # 启发函数（Score 计算）
│   ├── table_core.py   # 反向 BFS 核心逻辑（状态规范化 + 真前驱生成，bitmask 优化）
│   ├── build_table.py  # 反向 BFS 建表主程序 + tkinter GUI（并发 + 断点续算）
│   ├── table_solver.py # 查表求解器（沿 dist-1 邻居重构最短 Action 序列）
│   ├── table_query.py  # 建表查询/验证 CLI（status/dist/solve/verify）
│   ├── repair_table.py # 修复不完整建表数据
│   ├── visualize_table.py # 建表数据 tkinter 可视化浏览器
│   └── data/{m}_{n}_{step}/ # 建表产物（table.pkl / checkpoint.pkl / meta.json）
├── macro/
│   ├── macro.py         # 宏系統核心（MacroManager、Macro、MacroStep）
│   └── *.json           # 已保存的宏定義文件
└── 測試/                # 無頭測試腳本（驗證渲染、事件、面板等）
```

***

## 核心架構

### 1. 遊戲邏輯層 (`game.py`)

**Block 類**：

- 屬性：`location: list[int]`（座標 \[行, 列]）、`be_opted: bool`（是否選中）
- 支持 `==` 和 `hash`（基於位置）

**SliderMatrix 類**：

- `m, n`：初始棋盤尺寸
- `blocks: list[Block]`：滑塊對象列表
- `matrix / matrix_bounds`：0-1 矩陣 + 邊界（用於位置查詢）
- 核心方法：
  - `update_matrix()` — 從 blocks 同步更新 matrix
  - `opt(direction, line, block)` — DFS 選中連通的滑塊組（沿分割線分割）
  - `try_move(direction, step) -> list` — 純邏輯驗證移動（逐步預測-驗證，返回最終位置或空列表）
  - `commit_move(final_positions)` — 提交移動結果
  - `shuffle(attempts, step)` — 隨機打亂（模擬玩家操作）
  - `is_solved() -> bool` — 勝利判定（檢查滑塊是否形成 m×n 或 n×m 實心矩形）
  - `export_map() / import_map(map_str)` — 地圖序列化（`#` 表示滑塊，`_` 表示空白）

**關鍵設計**：

- `try_move` 不直接修改狀態，返回 `final_positions` 供 GUI 決定是否播放動畫後再 `commit_move`
- `check_move_valid` 靜態方法做碰撞檢測 + 連通性檢測（DFS）
- 勝利判定：不依賴模板比較，直接檢查當前 blocks 是否構成完整矩形

### 2. 歷史記錄層 (`history.py`)

**GameHistory 類**：

- 採用**狀態快照**方式：每條記錄保存 `{matrix, bounds, move_info}`
- `history_index` 指針支持線性撤銷/重做
- `save_snapshot(game, move_info)` — 保存快照，截斷後續分支
- `restore_snapshot(game, index)` — 從快照重建 blocks 列表
- `undo/redo` 返回 `(success, move_info)`，move\_info 包含動畫元數據

### 3. GUI 層 (`GUI.py` + `gui/`)

採用 **Mixin 架構**，`SliderGUI` 繼承 5 個 Mixin：

| Mixin          | 文件           | 職責                                                    |
| -------------- | ------------ | ----------------------------------------------------- |
| RendererMixin  | renderer.py  | 繪製棋盤、網格、選單、狀態欄、設置對話框、右側面板、宏通知                         |
| EventsMixin    | events.py    | 滑鼠/鍵盤事件處理、選單交互、長按撤銷/重做、指令處理                           |
| AnimationMixin | animation.py | 移動動畫、撤銷/重做動畫、緩動函數                                     |
| DialogsMixin   | dialogs.py   | 幫助對話框、自訂謎題對話框、PygameFileDialog（自繪文件選擇器）、宏管理對話框、宏命名對話框 |
| FileOpsMixin   | file\_ops.py | 保存/載入 JSON、配置管理、快捷鍵配置、終端指令處理                          |

**GUI 主類**（`GUI.py`）負責：

- 屬性初始化（顏色、字型、狀態變量、宏狀態等）
- `run()` 主循環（60 FPS），每幀處理：命令隊列、動畫更新、計時器、繪製、事件
- 高層操作：`move_selected_blocks`、`undo`、`redo`、`shuffle_puzzle`、`reset_puzzle`、`new_puzzle`
- 座標轉換：`world_to_screen` / `screen_to_world`
- 接受 `cmd_queue` 參數，支持來自終端和 HTTP 服務的外部指令

### 4. 宏系統 (`macro/macro.py`)

宏類似於魔方公式：一系列操作步驟，玩家在特定局面下執行以達到預期效果。

**MacroStep 類**（單個步驟）：

- `gap_type`：縫隙類型（`h` 橫向 / `v` 縱向）
- `gap_line_rel`：縫隙行/列相對於基準的偏移
- `side`：選中縫隙哪一側
- `direction`：滑動方向
- `step`：錄製時的步長

**Macro 類**（完整宏）：

- `name`、`description`、`recorded_step`、`base_point`、`steps`
- `check_step_compatibility(current_step)` — 檢查步長兼容性，返回拆分因子

**MacroManager 類**（管理器）：

- 載入/保存/刪除/重命名宏（JSON 文件存儲在 `macro/` 目錄）
- `convert_to_absolute()` — 將相對步驟轉換為絕對操作列表

**GUI 集成**：

- 選單欄「宏定義」選單：開始錄製、停止錄製、宏管理
- 宏錄製：設置基準座標 → 操作步驟自動記錄 → 命名保存
- 宏執行：指定宏名稱 + 新基準座標 → 自動執行（支持步長拆分）
- 宏管理對話框：列表、重命名、刪除、**滑鼠懸浮提示**（操作按鈕顯示功能說明）
- 右下角執行結果通知

### 5. HTTP 服務層 (`http_server.py`)

提供本地 HTTP REST API，用於外部程序（如求解器、自動化腳本）控制遊戲。

- 運行在 `127.0.0.1:5050`（預設），通過命令隊列與 GUI 主線程通信
- 支持 CORS，可從瀏覽器直接調用

**API 端點**：

| 方法   | 路徑                       | 功能                               |
| ---- | ------------------------ | -------------------------------- |
| GET  | `/status`                | 獲取遊戲狀態（步數、是否復原等）                 |
| GET  | `/map`                   | 獲取當前地圖                           |
| GET  | `/macro/list`            | 獲取所有宏列表                          |
| POST | `/command`               | 發送通用指令（`{cmd: "..."}`）           |
| POST | `/move`                  | 移動選中滑塊（`{direction: "w/s/a/d"}`） |
| POST | `/undo`                  | 撤銷                               |
| POST | `/redo`                  | 重做                               |
| POST | `/shuffle`               | 打亂                               |
| POST | `/reset`                 | 重置                               |
| POST | `/new`                   | 創建新謎題（`{m, n, step}`）            |
| POST | `/deselect`              | 取消選中                             |
| POST | `/select_gap`            | 選擇縫隙（`{type, line}`）             |
| POST | `/select_block`          | 選擇滑塊（`{row, col}`）               |
| POST | `/macro/record/start`    | 開始宏錄製                            |
| POST | `/macro/record/set_base` | 設置錄製基準座標                         |
| POST | `/macro/record/stop`     | 停止宏錄製並保存                         |
| POST | `/macro/execute`         | 執行宏                              |
| POST | `/macro/delete`          | 刪除宏                              |
| POST | `/macro/rename`          | 重命名宏                             |
| POST | `/quit`                  | 退出遊戲                             |

### 6. 文字輸入組件 (`gui/text_input.py`)

**TextInput 類**：

- 帶游標閃爍（500ms 週期）的文字輸入框
- 支持鍵盤輸入、Backspace、Delete、方向鍵、Home/End
- **長按重複**：（暫未實現）按住方向鍵/Backspace/Delete 自動重複（400ms 延遲 + 30ms 間隔）
- **滑鼠操作**：點擊定位游標、拖拽選中文本
- **選中功能**：Shift+方向鍵擴展選中、Ctrl+A 全選
- **剪貼板**：Ctrl+C 複製、Ctrl+X 剪切、Ctrl+V 粘貼
- `get_display_text()` — 帶滾動的文字顯示（超出寬度時自動捲動）
- `set_cursor_by_pixel()` — 滑鼠點擊定位游標
- `get_selection_offsets()` — 獲取選中區域像素偏移（用於高亮渲染）
- 用於文件對話框路徑輸入、宏命名對話框等場景

***

## 交互流程

### 移動操作

1. 點擊縫隙 → 選中分割線 (`selected_gap`)
2. 點擊滑塊 → 觸發 `opt()` 選中一側滑塊組 (`be_opted = True`)
3. 按 WASD → `move_selected_blocks()` → `game.try_move()` 驗證 → 動畫/直接提交 → `commit_move()` → 保存快照

### 撤銷/重做

1. 按 Ctrl+Z/X → 從快照獲取 `move_info`
2. 若有動畫：啟動動畫（從當前快照位置反向/正向移動到目標位置）
3. 動畫結束 → `restore_snapshot()` 恢復 blocks

### 文件操作

- 保存格式：JSON（包含 puzzle 參數、地圖字符串、步數、完整歷史）
- 文件對話框：純 Pygame 自繪（`PygameFileDialog`），不依賴 tkinter
- **自動補後綴**：保存時自動為文件名添加 `.json` 後綴（如輸入 `my_puzzle` 自動保存為 `my_puzzle.json`）
- 自動保存：退出時保存到 `config/temp_history.json` + `config/config.json`

### 外部指令

- GUI 每幀從 `cmd_queue` 取出指令並執行
- 指令來源：終端 stdin（後台線程讀取）或 HTTP API（響應隊列同步等待結果）
- 支持的終端指令：`status`、`map`、`move w/s/a/d`、`undo`、`redo`、`shuffle`、`reset`、`new m n step`、`select_gap`、`select_block`、`macro_*`、`quit` 等

***

## 配置文件

### `config/config.json`

```json
{
  "animation_speed": 300,
  "zoom": 1.0,
  "last_file_path": "save/save.json",
  "camera_x": 0,
  "camera_y": 0,
  "solver_algorithm": "gather_gradient",
  "window_size": [1000, 600],
  "window_pos": [100, 80],
  "panels": {
    "records": { "visible": true, "pos": [660, 40] },
    "virtual_keyboard": { "visible": true, "pos": [20, 60] },
    "metrics": { "visible": false, "pos": [20, 400] }
  }
}
```

- `window_size` / `window_pos`：上次關閉時的窗口尺寸與屏幕位置，啟動時恢復
- `panels`：各浮動面板的可見性與位置，無 config 時默認開啟「成績記錄」「虛擬鍵盤」
- 保存自動命名格式：`step-m-n-YYYYMMDD-HHMMSS.json`（24 小時制）

### `config/keyboard_shortcut.json`

```json
{
  "undo": {"key": "z", "modifiers": ["ctrl"]},
  "redo": {"key": "x", "modifiers": ["ctrl"]},
  "shuffle": {"key": "s", "modifiers": ["alt"]},
  "reset": {"key": "r", "modifiers": ["ctrl"]},
  "save": {"key": "s", "modifiers": ["ctrl"]},
  "load": {"key": "o", "modifiers": ["ctrl"]},
  "deselect": {"key": "space", "modifiers": []},
  "move_up": {"key": "w", "modifiers": []},
  "move_down": {"key": "s", "modifiers": []},
  "move_left": {"key": "a", "modifiers": []},
  "move_right": {"key": "d", "modifiers": []},
  "auto_solve": {"key": "s", "modifiers": ["ctrl", "alt"]},
  "record_macro": {"key": "m", "modifiers": ["ctrl"]}
}
```

- 缺失文件時自動重新生成預設配置
- 快捷鍵設置界面支持按鍵錄製

***

## UI 特性

- **可調整大小窗口**（`pygame.RESIZABLE`），最小 1000×600
- **滑鼠拖拽平移**地圖 + **滾輪縮放**（0.3x \~ 3.0x）
- **選單欄**：文件、編輯、謎題、宏定義、設置、幫助
- **右側控制面板**：縮放滑動條 + 動畫速度滑動條（50~1000ms）+ 5 個開關（動畫/著色/連鎖/競速模式/宏逆序播放）
- **浮動面板**：虛擬鍵盤（F1）、調試指標（F2）、成績記錄（F3），可拖動、獨立開關，位置由 config 持久化
- **狀態欄**：復原狀態、步數、謎題信息、縮放比例
- **長按重複**：撤銷/重做支持長按（400ms 延遲後 80ms 間隔）
- **預設謎題**：步長 2（2\~4×4 到 2\~10×10）、步長 3（3\~6×6 到 3\~10×10），支持自訂
- **宏系統**：錄製/執行/管理宏定義，支持步長兼容性檢查與自動拆分，可逆序播放
- **競速模式**：打亂後空格開始計時，復原自動停止並計入成績；計時中再按空格記為 DNF；全程禁止求解器、宏與打開存檔
- **成績記錄**：按謎題分組保存，列表單次/Ao5/Ao12 最好標綠、最差標紅；詳情可複製初始狀態、另存為存檔或載入練習模式
- **求解器**：五種算法可選（智能聚攏/普通聚攏/最少步/最快-1/最快-2），實時進度顯示，中途可停止；其中「查表求解」需先用 `solver.build_table` 預建距離表
- **深色主題**配色

***

## HTTP API 詳細用法

> **致 LLM/AI Agent：這是你測試和操控遊戲的主要方式。** 請使用 `curl` 或任何 HTTP 客戶端向 `http://127.0.0.1:5050` 發送請求。所有響應均為 JSON 格式，包含 `ok` 字段表示操作是否成功。

### 基礎用法

```bash
# 獲取遊戲狀態（返回步數、是否復原、矩陣、選中狀態等）
curl http://127.0.0.1:5050/status

# 獲取當前地圖（返回 # 和 _ 組成的文本地圖）
curl http://127.0.0.1:5050/map

# 獲取所有已保存的宏列表
curl http://127.0.0.1:5050/macro/list
```

### 通用指令接口

通過 `/command` 可以發送任意終端指令（見下方命令行指令章節）：

```bash
# 發送通用指令
curl -X POST http://127.0.0.1:5050/command -H "Content-Type: application/json" -d "{\"cmd\": \"status\"}"
curl -X POST http://127.0.0.1:5050/command -H "Content-Type: application/json" -d "{\"cmd\": \"shuffle\"}"
curl -X POST http://127.0.0.1:5050/command -H "Content-Type: application/json" -d "{\"cmd\": \"move w\"}"
```

### 操作流程（重要！）

遊戲的操作順序是：**選縫隙 → 選滑塊 → 移動**。以下是一個完整的操作範例：

```bash
# 步驟 1: 查看當前狀態，了解棋盤布局
curl http://127.0.0.1:5050/status

# 步驟 2: 選擇縫隙（type: h=橫向縫隙, v=縱向縫隙; line: 縫隙所在的行列號）
# 例如選擇縱向縫隙（垂直分割線），位於第 1 列右側
curl -X POST http://127.0.0.1:5050/select_gap -H "Content-Type: application/json" -d "{\"type\": \"v\", \"line\": 1}"

# 步驟 3: 選擇滑塊（點擊縫隙某一側的一個滑塊，DFS 會自動選中該側所有連通的滑塊）
curl -X POST http://127.0.0.1:5050/select_block -H "Content-Type: application/json" -d "{\"row\": 0, \"col\": 0}"

# 步驟 4: 移動選中的滑塊（direction: w=上, s=下, a=左, d=右）
# 注意：縱向縫隙只能上下移動（w/s），橫向縫隙只能左右移動（a/d）
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d "{\"direction\": \"s\"}"

# 步驟 5: 確認移動結果
curl http://127.0.0.1:5050/status
```

### 移動操作

```bash
# 移動已選中的滑塊（必須先 select_gap + select_block）
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d "{\"direction\": \"w\"}"   # 上移
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d "{\"direction\": \"s\"}"   # 下移
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d "{\"direction\": \"a\"}"   # 左移
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d "{\"direction\": \"d\"}"   # 右移
```

### 撤銷/重做

```bash
curl -X POST http://127.0.0.1:5050/undo
curl -X POST http://127.0.0.1:5050/redo
```

### 謎題管理

```bash
# 打亂當前謎題
curl -X POST http://127.0.0.1:5050/shuffle

# 重置謎題（回到打亂前的狀態）
curl -X POST http://127.0.0.1:5050/reset

# 創建新謎題（m×n 棋盤，步長為 step）
curl -X POST http://127.0.0.1:5050/new -H "Content-Type: application/json" -d "{\"m\": 4, \"n\": 4, \"step\": 2}"
curl -X POST http://127.0.0.1:5050/new -H "Content-Type: application/json" -d "{\"m\": 5, \"n\": 6, \"step\": 3}"
```

### 選中操作

```bash
# 選擇縫隙（h=橫向, v=縱向; line=行/列號）
curl -X POST http://127.0.0.1:5050/select_gap -H "Content-Type: application/json" -d "{\"type\": \"h\", \"line\": 2}"

# 選擇滑塊（需要先選縫隙，會自動 DFS 選中同側連通滑塊）
curl -X POST http://127.0.0.1:5050/select_block -H "Content-Type: application/json" -d "{\"row\": 1, \"col\": 2}"

# 取消所有選中
curl -X POST http://127.0.0.1:5050/deselect
```

### 宏操作

```bash
# 查看所有宏
curl -X POST http://127.0.0.1:5050/macro/list

# 開始錄製宏
curl -X POST http://127.0.0.1:5050/macro/record/start

# 設置錄製基準座標（在錄製開始後，進行實際操作前設置）
curl -X POST http://127.0.0.1:5050/macro/record/set_base -H "Content-Type: application/json" -d "{\"row\": 0, \"col\": 0}"

# （在此期間進行 select_gap → select_move → move 等操作，步驟會自動記錄）

# 停止錄製並保存（需指定宏名稱）
curl -X POST http://127.0.0.1:5050/macro/record/stop -H "Content-Type: application/json" -d "{\"name\": \"my_macro\"}"

# 執行宏（指定名稱和新的基準座標）
curl -X POST http://127.0.0.1:5050/macro/execute -H "Content-Type: application/json" -d "{\"name\": \"my_macro\", \"base_row\": 2, \"base_col\": 3}"

# 重命名宏
curl -X POST http://127.0.0.1:5050/macro/rename -H "Content-Type: application/json" -d "{\"old_name\": \"my_macro\", \"new_name\": \"better_name\"}"

# 刪除宏
curl -X POST http://127.0.0.1:5050/macro/delete -H "Content-Type: application/json" -d "{\"name\": \"better_name\"}"
```

### 其他

```bash
# 退出遊戲
curl -X POST http://127.0.0.1:5050/quit
```

### 響應格式

所有接口返回 JSON，基本格式：

```json
{"ok": true, "message": "操作描述"}
```

`/status` 返回的完整數據：

```json
{
  "puzzle": "2~4*4",
  "step_count": 15,
  "solved": false,
  "matrix": [[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 1], [0, 0, 1, 1]],
  "selected_gap": ["v", 1],
  "selected_block": [0, 0],
  "animating": false
}
```

`/map` 返回：

```json
{"ok": true, "map": "##__\n##__\n__##\n__##"}
```

***

## 命令行指令詳細用法

> **致 LLM：你也可以通過 stdin 向遊戲進程發送指令。** 遊戲運行時會在後台線程監聽 stdin 輸入。指令格式與 HTTP `/command` 接口一致。

### 基本指令

| 指令         | 說明            | 範例         |
| ---------- | ------------- | ---------- |
| `status`   | 獲取遊戲狀態（打印到終端） | `status`   |
| `map`      | 獲取當前地圖文本      | `map`      |
| `shuffle`  | 隨機打亂謎題        | `shuffle`  |
| `reset`    | 重置謎題          | `reset`    |
| `undo`     | 撤銷上一步操作       | `undo`     |
| `redo`     | 重做已撤銷的操作      | `redo`     |
| `deselect` | 取消所有選中        | `deselect` |
| `quit`     | 退出遊戲          | `quit`     |

### 移動指令

```bash
# 創建新謎題：new m n step
new 4 4 2        # 4×4 棋盤，步長 2
new 5 6 3        # 5×6 棋盤，步長 3

# 選擇縫隙：select_gap <h|v> <line>
select_gap v 1   # 選擇縱向縫隙，第 1 列
select_gap h 2   # 選擇橫向縫隙，第 2 行

# 選擇滑塊：select_block <row> <col>
select_block 0 0 # 選擇座標 (0,0) 的滑塊（DFS 自動選中連通組）

# 移動：move <w|s|a|d>
move s            # 向下移動
move d            # 向右移動
```

### 宏指令

```bash
macro_list                          # 列出所有宏
macro_record_start                  # 開始錄製
macro_set_base 0 0                  # 設置錄製基準座標
# ... 執行操作（select_gap, select_block, move）...
macro_record_stop my_macro          # 停止錄製並命名
macro_execute my_macro 2 3          # 在 (2,3) 為基準執行宏
macro_delete my_macro               # 刪除宏
macro_rename old_name new_name      # 重命名宏
```

### 操作範例（命令行）

```
> status
=== 狀態 ===
謎題: 2~4*4
步數: 0
復原: 是
矩陣:
1 1 0 0
1 1 0 0
0 0 1 1
0 0 1 1

> shuffle
[OK] 已打乱

> select_gap v 1
[OK] 已選中縫隙: v 1

> select_block 0 0
[OK] 已選中滑塊 (0,0), 選中區域: 2 個

> move s
[OK] 已移動 s

> status
=== 狀態 ===
謎題: 2~4*4
步數: 1
復原: 否
矩陣:
0 0 0 0
1 1 0 0
1 1 1 1
0 0 1 1
```

***

## 已知限制 / 待完成功能

- 未來可能加入除了正方形以外的其他形狀滑塊（如三角形）、三維滑塊、獨立編號滑塊
- 求解器長期目標：用神經網絡/強化學習訓練專用 AI，或找到人類可理解的通用解法

***

## 求解器

遊戲內置五種求解算法，可通過「編輯 → 自動求解」或快捷鍵 `Ctrl+Alt+S` 啟動：

| 算法               | 說明                                  | 特點            |
| ---------------- | ----------------------------------- | ------------- |
| 智能聚攏（gradient）  | 先驗參數預測 + 多階段放寬參數 + 路徑優化（去環 + 徘徊壓縮）  | 聚攏系增強版，適配性強   |
| 普通聚攏（gather）    | 貪心聚攏 + 連續無改進停機                      | 快速，不保證復原      |
| 最少步求解 (IDA\*)    | IDA\* + 轉置表 + 動作排序 + 分階段搜索          | 保證最優解，但速度較慢   |
| 最快求解-1 (IDA\*快速) | 調整 bound 增量、節點限制、動作排序採樣             | 犧牲最優性換取速度     |
| 最快求解-2 (貪心爬山)    | 貪心爬山 + 隨機擾動 + 轉置表                   | 速度最快，不保證最優解   |

五種算法均通過 `solver.SOLVER_ALGORITHMS` 對照表註冊，可在「設置」對話框中選擇默認算法（保存到 `config/config.json` 的 `solver_algorithm` 字段，當前默認值為 `gather_gradient`）。

求解過程中：

- 實時顯示階段、深度、節點數、耗時
- 支持中途停止（點擊「停止求解」或再次按 `Ctrl+Alt+S`）
- 求解成功後自動生成宏指令並執行

### 反向 BFS 建表

「查表求解」依賴預建的距離表，需為每個等級（`m n step`）單獨建表一次。建表完成後，該等級的任意打亂狀態可在 < 1 秒內求出最短解。已建表等級存放在 `solver/data/{m}_{n}_{step}/`，目前完成的有 `1~2*3`、`1~3*3`、`2~4*4`（559,504 個狀態、最大距離 17、表文件 18.7MB）。

```bash
# 建表（帶 tkinter GUI，實時進度 + 距離分布 + 暫停/續算）
D:\python\python.exe -m solver.build_table 4 4 2

# 無 GUI 純 CLI 模式
D:\python\python.exe -m solver.build_table 4 4 2 --no-gui

# 查詢表統計 / 給定地圖的求解距離 / 最短解法 / 距離一致性驗證
D:\python\python.exe -m solver.table_query status 4 4 2
D:\python\python.exe -m solver.table_query dist "##.|##.|.##" 4 4 2
D:\python\python.exe -m solver.table_query solve "##.|##.|.##" 4 4 2
D:\python\python.exe -m solver.table_query verify 50 4 4 2

# 修復不完整表 / 可視化瀏覽表中狀態
D:\python\python.exe -m solver.repair_table 4 4 2
D:\python\python.exe -m solver.visualize_table 4 4 2
```

建表支持**斷點續算**（崩潰/暫停後可從 `checkpoint.pkl` 繼續）、**定時自動保存**（每 60 秒或每 5 萬新狀態）、**多進程並發**（最多 16 進程）。

***

## 開發約定

- Python 路徑：`D:\python\python.exe`
- 修改應盡量只改少量代碼，避免影響已有功能
- 不改動數據集 `solver/data` 內容
- 模塊邊界清晰：game.py 純邏輯無 pygame 依賴，GUI 層通過 Mixin 拆分職責
- 個人參考文檔與 IDE 配置（`.clinerules/`、`.trae/`、`.vscode/`、`参考/`）不入庫，見 `.gitignore`

