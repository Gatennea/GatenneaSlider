# 貓九的滑塊遊戲（Gatennea Slider）

這是給 AI Agent 的readme。

---

基於 **Python + pygame-ce** 的滑塊拼圖遊戲。玩家（或 AI）透過「選擇縫隙 → 選擇滑塊組 → 滑動」把打亂的方塊還原成一個完整的 **m×n 或 n×m 實心矩形**（允許整體平移，不做模板比對）。

> ## ⚠️ 給 AI Agent 的速覽（先讀這節）
>
> 1. **不要嘗試操控 Pygame 窗口。** 本專案刻意提供兩條程序化控制通道：
>    - **HTTP REST**（推薦）：`http://127.0.0.1:5050`，結構化 JSON 請求/回應。
>    - **stdin 指令**：向主程序 stdin 寫一行指令（打包成 `--windowed` exe 時 `sys.stdin is None`，該通道自動停用）。
> 2. 一次完整移動 = 三個指令依序執行：`select_gap` → `select_block` → `move`，缺一不可。
> 3. 每次「動作型」指令後建議再 `GET /status` 確認結果；所有回應都有 `ok: true/false`。
> 4. `solved` 不代表「回到最初版面」，而是「方塊在任意位置構成實心矩形」。
> 5. 若要改求解器/調試面板：務必先讀 §2「核心不變量」與 §5「求解器子系統」，避免破壞平移不變量假設。
>
> **建議閱讀順序**（由底層到外層）：
> `game.py` → `solver/actions.py`、`solver/state.py` → `GUI.py` → `gui/events.py`（`process_commands`）→ `http_server.py` → `solver/__init__.py`、`solver/ml/gather_solver.py`。

---

## 1. 啟動與驗證

Python ≥ 3.10（需 pygame-ce、numpy、scikit-learn；打包後可直接跑 exe）。

```bash
# 預設 4×4、step=2，並開啟 HTTP(5050)；同時開 Pygame 窗口
python main.py

# 指定棋盤/等級；也可只給端口
python main.py 6 6 2          # 6×6、step=2
python main.py 4 4 2 8080     # 指定 HTTP 端口 8080
python main.py 4 4 2 --http-port 8080
python main.py --no-http      # 停用 HTTP，僅 stdin/GUI

# 無頭驗證（不開窗口）
python -m solver.ml.hole_detector
python test\_test_mod_constraint.py
```

- 參數規則：`m n step`（`step < max(m, n)`）；純數字單參數 = HTTP 端口。
- 啟動即連開：stdin 讀取執行緒、HTTP daemon 執行緒、`SliderGUI` 主迴圈（60 FPS）。
- 啟動/異常寫入 `error_log.txt`（與 exe 同目錄；無權限時退回系統 temp），全部異常（含子執行緒）都會記錄。

快速健康檢查：

```bash
curl http://127.0.0.1:5050/status
# => {"puzzle":"2~4*4","step_count":0,"solved":true,"matrix":[[...]],"selected_gap":null,...}
```

---

## 2. 詞彙與核心不變量

| 詞彙 | 定義 |
| --- | --- |
| 滑塊 Block | 正方形單元，`location=[r, c]`（0-based，row 向下為正） |
| 棋盤 SliderMatrix | `m×n` 起始版面；實際方塊可在任意位置活動 |
| 縫隙 gap | 兩區塊之間的**分割線**。`h`=橫向縫隙（row 之間），`v`=縱向縫隙（col 之間）；以 `line` 標號。`select_gap {type,line}` 選它 |
| 滑塊組 | `select_block {row,col}` 選中縫隙一側**連通**的整組方塊（DFS，`opt()`） |
| 移動 move | `w/s/a/d`（上/下/左/右）。**限制：`v` 縫隙只能 `w/s`；`h` 縫隙只能 `a/d`**（見 `gui/events.py` 移動分支） |
| step | 等級/基本步距；每次移動方塊組整體平移 step 的整數倍 |
| solved | 所有方塊構成**任意位置**的 `m×n` 或 `n×m` 實心矩形（含轉置，不含形狀模板） |
| puzzle 標籤 | 字串 `"{step}~{m}*{n}"`，例 `2~4*4`。成績/宏/建表皆以它分組 |
| map 文本 | `#`=方塊、`_`=空白 的棋盤框文本；`export_map()/import_map()` 序列化格式 |

### 2.1 Mod 著色不變量（求解器核心，勿違反）

對 `step > 1`，每次合法移動中，每個方塊的 `(r % step, c % step)` **永遠不變**（同側整組平移 step 的整數倍）。推論：

- 最終目標矩形左上角 `(r0, c0)` 只能落在特定 mod 網格上：
  - 若 `m % step != 0` → `r0 % step` 被唯一固定；
  - 若 `n % step != 0` → `c0 % step` 被唯一固定；
  - 兩者都被 step 整除的維度無約束。
- 相關函數（全部在 `solver/ml/gather_solver.py`）：
  - `detect_target_corner(coords, m, n, step)`：用 mod 類別計數預測 `(r0, c0)` 偏移（只對有約束的維度有效）。
  - `find_best_window(coords, m, n, step)`：**全鏈唯一窗口基準**。在邊界盒內枚舉所有 `m×n` 與 `n×m` 窗口，只保留符合 mod 約束的左上角，選重疊方塊數最高者。回傳 `(r0, c0, (rh, cw), overlap)`。
  - `is_mod_compliant(coords, step, r0, c0)`：校驗視窗是否與不變量相容。
- 調試面板「目標框/標記」與求解器必須共用同一 `find_best_window` 結果，否則洞/凸起語義會錯位（參 §5.2）。

### 2.2 移動流程（內部）

`try_move` 只做「純邏輯預測」不修改狀態 → GUI 決定播放動畫後 → `commit_move` → `save_snapshot`。`undo/redo` 走快照（`{matrix, bounds, move_info}`）。

- `game.try_move_ex(direction, step) -> (positions, reason)`：同 `try_move` 但附失敗原因 `''`/`'no_selection'`/`'collision'`（重疊）/`'disconnected'`（斷開，移動後失去單一連通）；`try_move` 為其薄包裝。
- GUI 層 `move_selected_blocks` 失敗時在右下角浮窗提示「滑動失敗：移動後滑塊會斷開/重疊」。

---

## 3. 目錄地圖（檔案 → 職責）

```
main.py                # 入口：解析 CLI → 開 stdin 執行緒 + HTTP → SliderGUI().run()
game.py                # 純遊戲邏輯（無 pygame 依賴）：Block、SliderMatrix、is_solved
GUI.py                 # SliderGUI 主類（8 個 Mixin 聚合）+ 主迴圈/高層操作/資源路徑
history.py             # GameHistory 快照式撤銷/重做
records.py             # Records 成績管理器（pickle+XOR 混淆存 config/records.dat）
http_server.py         # GameHTTPHandler：HTTP REST → 指令佇列（見 §6）

gui/                   # 全是 Mixin，被 SliderGUI 繼承
  renderer.py          #   RendererMixin        繪製棋盤/選單/面板/求解器選單/目標框與標記
  events.py            #   EventsMixin          滑鼠/鍵盤/快捷鍵/長按/面板互動/指令佇列處理
  animation.py         #   AnimationMixin       移動與 undo/redo 動畫、緩動
  dialogs.py           #   DialogsMixin         幫助/自訂謎題/PygameFileDialog/宏管理與命名框
  file_ops.py          #   FileOpsMixin         存檔/載入/組態管理（JSON）
  virtual_keyboard.py  #   VirtualKeyboardMixin 虛擬鍵盤浮動面板（F1 開關）
  metrics_panel.py     #   MetricsPanelMixin    調試指標面板（F2）＋目標框/洞標記選取
  records_panel.py     #   RecordsPanelMixin    成績記錄浮動面板（F3）
  tutorial.py          #   TutorialMixin        新手教程引導（首次啟動彈窗/步驟提示）
  text_input.py        #   TextInput            自繪文字輸入框（游標/選取/剪貼簿）
  tutorial_texts.json  #   新手教程文案（可脫離代碼修改）

solver/                # 求解器（詳見 §5）
  __init__.py          #   SOLVER_ALGORITHMS 註冊表；solve/solve_fast/solve_greedy 入口
  actions.py           #   enumerate_valid_actions / apply_action（動作語義）
  state.py             #   snapshot/restore、狀態正規化
  greedy.py            #   貪心爬山（最快-2）
  ida_star.py          #   IDA*（最少步 / fast_mode）
  heuristic.py         #   啟發函數 Score
  table_core.py        #   反向 BFS 核心：canonicalize、_side_components、真前驅（bitmask）
  build_table.py       #   建表主程式（多進程 + 斷點續算，GUI/CLI）
  table_solver.py      #   查表求解：沿 dist-1 鄰居重構最短路徑
  table_query.py       #   建表查詢/驗證 CLI（status/dist/solve/verify）
  repair_table.py      #   修復不完整建表
  visualize_table.py   #   tkinter 瀏覽表內狀態
  ml/                  #   ML 子系統（訓練資料管線，見 §5.4）
  data/{m}_{n}_{step}/ #   建表產物 table.pkl/checkpoint.pkl/meta.json（不入庫，需自行建表）

macro/
  macro.py             #   宏系統：MacroManager / Macro / MacroStep（JSON 存 macro/*.json）
  test_macro_http.py   #   用 HTTP API 驅動宏錄製/執行的範例腳本

config/                # 執行期組態（§8）
save/                  # 使用者存檔 *.json
picture/               # cover.ico / cover.png（圖示）
test/                  # 無頭測試腳本（§9），命名 _test_*.py 或 test/
web/                   # Web 版（TypeScript/靜態頁），**獨立 git 倉庫**，不隨本庫提交
build_exe.bat / Gatenneaslider.spec / package_zip.bat   # 打包（§10）
```

---

## 4. 架構與資料流

```
 stdin 執行緒 ─┐                        ┌─→ print / 直接回應
 HTTP 執行緒 ──┴─→ cmd_queue ─→ SliderGUI.process_commands()（gui/events.py）
                 （元素：str 或 (cmd, resp_q) 元組）
```

- **單一指令佇列**：HTTP 每請求包成 `(cmd, resp_q)` 並阻塞等待（逾時 10s）；stdin 放入純字串；GUI 每幀取出執行。
- **SliderGUI** 繼承 10 個 Mixin（`RendererMixin, DialogsMixin, AnimationMixin, FileOpsMixin, EventsMixin, VirtualKeyboardMixin, MetricsPanelMixin, RecordsPanelMixin, AnnotationMixin, TutorialMixin`），Mixin 只提供方法，狀態集中在主類。
- 高層操作（`move_selected_blocks/undo/redo/shuffle_puzzle/reset_puzzle/new_puzzle/_start_auto_solve`）在 `GUI.py` 或 `gui/events.py` 定義。
- 三大可拖動浮動面板：虛擬鍵盤（F1）、調試面板（F2，預設關閉）、成績面板（F3）；位置/可見性寫入 `config/config.json` 的 `panels`。
- 調試面板（`metrics_panel`）額外支援：**框內空格 = 圓圈(孔洞)/三角(缺口)、框外滑塊 = 菱形(凸起)**，點擊可選中標記用於觀察；畫框與標記共用 `find_best_window` 產出的 `region`。

### 4.1 GUI 人工操作：三種控制模式（可任意組合）

設置對話框「控制」頁有三個獨立開關（`config.json` 對應 `control_single_touch` / `control_two_touch` / `control_mouse_kb`，預設全開）：

| 模式 | 操作方式 | 實作位置 |
| --- | --- | --- |
| 單次觸控 `control_single_touch` | 直接**按住滑塊拖拽**即滑動（8 區角度判定縫隙與方向，對齊 `web/docs/touch-gesture.md`）；滑動後（含失敗）清空臨時選中 | `GUI.py::_drag_slide` + `gui/events.py` 拖拽狀態機（`_mouse_drag_state`） |
| 兩次觸控 `control_two_touch` | 原版三段式：點縫隙 → 點方塊 → 再拖拽/鍵盤；**關閉時入口門禁，點擊不寫入任何選中狀態** | `gui/events.py` MOUSEBUTTONDOWN |
| 鼠標鍵盤 `control_mouse_kb` | 方向鍵 / W/A/S/D 移動；關閉只屏蔽移動鍵，Ctrl+Z/Y 等快捷鍵不受影響 | `gui/events.py` KEYDOWN |

- 拖拽判定：按下累計位移超過 `drag_threshold`（預設 14px）才算拖拽，否則視為點擊。
- 桌面版一次拖拽滑動 = `step` 格（網頁版為 1 格）。
- 注意：三開關只影響**人工 GUI 操作**；HTTP/stdin 程式化通道（§6/§7）永遠可用。

---

## 5. 求解器子系統

### 5.1 演算法註冊表

`solver/__init__.py` 的 `SOLVER_ALGORITHMS: dict[key, (顯示名, callable)]` 是 GUI「自動求解」唯一來源：

| key | 顯示名 | 函數 | 特性 |
| --- | --- | --- | --- |
| `gather_gradient` | 智能聚攏 | `gather_solver.gradient_gather` | 參數預測 + 多階段 + 路徑優化 |
| `human_ai` | 人類模仿 | `human_solver.ai_human_solve` | 人類還原記錄訓練的評分模型（§5.4） |
| `gather` | 普通聚攏 | `gather_solver.gather_solve` | 貪心聚攏 + patience 停機 |
| `ida_star` | 最少步 | `solver.solve` | 保證最優，較慢 |
| `fast` | 最快-1 | `solve_fast` | IDA* 放寬 |
| `greedy` | 最快-2 | `solve_greedy` | 貪心爬山 + 擾動 |
| `table` | 查表求解 | `table_solver.table_solve` | 需先 `solver.data` 建表 |

通用函式庫契約：`f(game, step, max_steps, cancel_check=None, progress_callback=None) → list[action] | None`（`gather` 系回報 `progress_callback` 聚攏指標，即使未還原也回傳動作序列）。新增演算法 = 在 `solver/ml/` 新增模組 + 註冊進 `SOLVER_ALGORITHMS` + 加入設定介面的預設清單。

指令 `solve`（HTTP `POST /solve`）以目前 `config.json: solver_algorithm` 啟動非同步求解，用 `POST /solve/status` 輪詢（回 `running / solved(N步) / failed (无解) / idle`）。求解完成後 GUI 把解轉成宏執行。

### 5.2 聚攏族與「目標窗口」語義（改求解器前必讀）

- **聚攏度** `score = 最佳重疊塊數 / m*n`（`max_overlap`/`gather_score`），取 `m×n`、`n×m` 兩朝向的最大重疊，平移不變。
- **目標窗口**就是分數所對應的矩形，由 `find_best_window()`（mod-aware 枚舉）唯一決定；**洞/凸起的語義必須與它一致**：
  - `solver/ml/hole_detector.py::detect_holes(coords, m, n, step, region=None)` 接受外部傳入 `region=(r0,c0,(rh,cw))`；`region=None` 時退回無 mod 約束的 `find_target_region`（僅離線/測試用）。
  - 框內空格：被包圍→`hole`（圓圈）；連到框緣→`dent`/缺口（三角形）。框外方塊 = `protrusion`（菱形）。
- `_game_coords(game)`：把 `game.blocks` 轉成 `frozenset[(r,c)]`。

### 5.3 建表（`table` 算法前提）

距離表以「等級」為單位，一次建好後該等級任意狀態 < 1s 求最短解；表資料放 `solver/data/{m}_{n}_{step}/`，**不進 git**（`.gitignore`），拿到新環境需自己重建：

```bash
python -m solver.build_table 4 4 2            # GUI 建表
python -m solver.build_table 4 4 2 --no-gui   # 純 CLI
python -m solver.table_query status 4 4 2
python -m solver.table_query dist "##.|##.|.##" 4 4 2
python -m solver.table_query solve "##.|##.|.##" 4 4 2
python -m solver.repair_table 4 4 2
python -m solver.visualize_table 4 4 2
```

支援多程序（≤16）、checkpoint 斷點續算、定時自動存檔。

### 5.4 `solver/ml`（資料管線）

依賴 numpy + scikit-learn。目前有兩條獨立管線：

**A. 查表導出管線（離線，未接入求解菜單）**
`features`（特徵/動作編碼）→ `export_data`（從 BFS 表導出）→ `annotate` → `train_baseline` / `train_ranker` / `train_distance` → `ai_solver` / `distance_solver` 推理。

**B. 人類模仿管線（已註冊為 `human_ai`，見 §5.1）**
```bash
# 1. 從 save/*.json（人類還原記錄）導出正/負樣本，JSONL 可檢視
python -m solver.ml.export_human_data
# 2. 訓練評分模型：score(狀態, 動作)，輸出 data/human/model_ranker.pkl
python -m solver.ml.train_human_ranker
# 3. 無頭驗證（真實人類開局 → 原生 API 逐步執行）
python -m solver.ml.human_solver
```
`human_solver.ai_human_solve` 逐步對「當前狀態枚舉的全部合法動作」打分、取最高並用遊戲原生 API 執行——輸出永遠合法可執行。關鍵設計：
- 動作編碼含完整 `gap_type/gap_line/side/move_dir`（非單純方向），gap_line 相對狀態邊界（平移不變）
- 狀態特徵含聚攏度維度（`void_block_count` 的分段權重作為樣本權重）
- 最終目標：「梯度聚攏粗調 + AI 收尾」；當前模型僅作交互驗證用。

---

## 6. 控制介面一：HTTP REST（AI 主要通道）

伺服器綁定 `127.0.0.1:5050`；`GameHTTPHandler` 把每個請求轉成指令，同步等待 GUI 執行完後回 JSON。GET/POST 皆有 `/timer/status`、`/records`；`OPTIONS` 已開 CORS。

| Method | Path | Body / 說明 |
| --- | --- | --- |
| GET | `/status` | 完整狀態（§下方 schema） |
| GET | `/map` | `{"ok":true,"map":"##__\n##__..."}` |
| GET | `/macro/list` | `{"ok":true,"macros":[{name,description,steps,recorded_step,base_point}]}` |
| GET | `/records` | 目前謎題成績摘要（與 POST 同） |
| GET | `/timer/status` | `{"ok":true,...}` + `state`/`elapsed_ms` |
| POST | `/command` | `{"cmd":"<任意 CLI 指令>"}`（§7 全集） |
| POST | `/move` | `{"direction":"w|s|a|d"}`（需先選好 gap+block） |
| POST | `/undo` `/redo` `/shuffle` `/reset` `/deselect` `/quit` | — |
| POST | `/new` | `{"m","n","step"}` |
| POST | `/select_gap` | `{"type":"h|v","line":N}` |
| POST | `/select_block` | `{"row","col"}` |
| POST | `/solve` | 以目前算法開始非同步求解 |
| POST | `/solve/status` | 輪詢求解狀態（同 CLI `solve_status`） |
| POST | `/timer/start` | 競速開始（需先打亂處於 ready）；`/timer/stop` = DNF |
| POST | `/macro/record/start` `/macro/record/set_base` `{row,col}` `/macro/record/stop` `{name}` | 錄製 |
| POST | `/macro/execute` `{name,base_row,base_col}` `/macro/delete` `{name}` `/macro/rename` `{old_name,new_name}` | 管理 |

**標準操作序列**（AI 每步移動的固定寫法）：

```bash
curl http://127.0.0.1:5050/status
curl -X POST http://127.0.0.1:5050/shuffle
curl -X POST http://127.0.0.1:5050/select_gap -H "Content-Type: application/json" -d '{"type":"h","line":2}'
curl -X POST http://127.0.0.1:5050/select_block -H "Content-Type: application/json" -d '{"row":2,"col":0}'
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d '{"direction":"d"}'
curl http://127.0.0.1:5050/status
```

`/status` schema（`gui/events.py::_get_game_status`）：

```json
{
  "puzzle": "2~4*4",
  "step_count": 15,
  "solved": false,
  "matrix": [[1,1,0,0],[1,1,0,0],[0,0,1,1],[0,0,1,1]],
  "selected_gap": ["v", 1],
  "selected_block": [0, 0],
  "animating": false
}
```

---

## 7. 控制介面二：stdin CLI

GUI 每幀執行 `process_commands()`（`gui/events.py`），支援純字串（stdin）或 `(cmd, resp_q)`（HTTP）。指令以空白分隔，第一個 token 為動作。

**完整動作清單**（= `http_server.py` 對映來源，兩介面 1:1）：

| 動作 | 參數 | 說明 |
| --- | --- | --- |
| `status` | — | 狀態（含 matrix） |
| `map` | — | `#`/`_` 文本地圖 |
| `move` | `w|s|a|d` | 移動（需先選縫隙+滑塊；`v`→w/s，`h`→a/d） |
| `undo` / `redo` | — | 快照式撤銷/重做 |
| `shuffle` | — | 打亂 |
| `reset` | — | 回到打亂前 |
| `new` | `m n step` | 換謎題 |
| `select_gap` | `h\|v line` | 例 `select_gap v 1` |
| `select_block` | `row col` | 例 `select_block 0 0` |
| `deselect` | — | 清選中 |
| `export` / `import` | （沿用舊終端介面） | 地圖字串進出 |
| `solve` | — | 以目前算法自動求解 |
| `solve_status` | — | `idle/running/solved(N步)/failed (无解)` |
| `timer_start` / `timer_stop` / `timer_status` | — | 競速計時 |
| `records` | — | 目前謎題成績摘要（count/best/worst/ao5/ao12/dnf） |
| `macro_list` | — | 列出宏 |
| `macro_record_start` | — | 開始錄製 |
| `macro_set_base` | `row col` | 設定錄製基準 |
| `macro_record_stop` | `name` | 停止並命名保存 |
| `macro_execute` | `name base_row base_col` | 在新基準執行宏（會做 step 相容拆分） |
| `macro_delete` | `name` | 刪除 |
| `macro_rename` | `old new` | 改名 |
| `quit` | — | 結束遊戲（`running=False`） |

**操作示範**：

```
> status          # 查看狀態（stdin 無 resp_q，故直接 print 人類版）
> shuffle
> select_gap v 1
> select_block 0 0
> move s
> status
```

宏錄製期間，`select_gap→select_block→move` 的操作會被自動記錄成相對步驟。

---

## 8. 組態與資料檔案

| 路徑 | 用途 | 備註 |
| --- | --- | --- |
| `config/config.json` | 視窗/動畫/縮放/相機/上次檔案/`solver_algorithm`/`panels` 位置 | 缺檔自動重生 |
| `config/keyboard_shortcut.json` | 快捷鍵（動作→key+modifiers），如 undo=`ctrl+z`、panels=`f1/f2/f3` | 設定介面可錄製 |
| `config/records.dat` | 成績記錄（pickle 以固定 XOR `0x5A` 混淆檔頭，非加密） | 關閉遊戲時統一寫入 |
| `config/temp_history.json` | 退出時自動快照，下次啟動還原進度 | |
| `save/*.json` | 使用者存檔（含 puzzle 參數、map、步數、歷史） | 自動補 `.json` 後綴 |
| `macro/*.json` | 宏定義 | |
| `error_log.txt` | 執行期錯誤（含子執行緒） | 位置＝exe/腳本目錄 |

`config.json` 關鍵範例（`solver_algorithm` 決定 `POST /solve` 用哪個算法）：

```json
{
  "animation_speed": 300,
  "zoom": 1.0,
  "solver_algorithm": "gather_gradient",
  "window_size": [1000, 600],
  "panels": {
    "records":      { "visible": true,  "pos": [660, 40] },
    "virtual_keyboard": { "visible": true, "pos": [20, 60] },
    "metrics":      { "visible": false, "pos": [20, 400] }
  }
}
```

---

## 9. 測試與驗證

`test/` 內全部是無頭腳本（不開窗口，需 pygame 可於背景模式建立 surface），直接執行，通過會印 `ALL PASS`：

```bash
python test\_test_mod_constraint.py     # mod 約束/detect_target_corner
python test\_test_gradient_pipeline.py  # 智能聚攏並行管線收尾
python test\_test_full.py               # 綜合
python test\_test_rp_menu.py / _test_rp_colors.py   # 成績面板
python test\_test_block_load.py / _test_textinput.py
```

另有 `test/test/`（pytest 風格：`test_solver/test_table_core/test_bfs_explore/test_profile`）與開發用探針 `_debug_cursor.py`、`_test_mouse_cursor.py` 等。改動求解器核心後，至少重跑 `_test_mod_constraint` 與 `_test_gradient_pipeline`。

若環境有 pyflakes，可用它抓未使用 import/變數（注意殘留的「f-string 無佔位符」與 `emd_solver.py` 的 `candidates` 前向引用屬已知保留項，非錯誤）：

```bash
python -m pyflakes game.py GUI.py gui\*.py solver\*.py solver\ml\*.py
```

---

## 10. 打包

- `Gatenneaslider.spec`：PyInstaller 規格；`build_exe.bat` 一鍵打包（`--windowed`）。
- **`--windowed` 無控制台時 `sys.stdin is None`**，`main.py::stdin_reader` 會檢查並跳過 stdin 監聽；HTTP 通道不受影響。
- `package_zip.bat` / `package_zip.ps1`：把 exe + 必要資源壓成發布 zip。
- 圖示：`picture/cover.ico`；運行期資源路徑統一走 `GUI.py::_gui_get_resource_path`（相容 frozen）。

---

## 11. 開發約定與注意事項

- Python 一律用 `python`（本機路徑見 `本機環境.md`）。
- `game.py` 不得引入 pygame（保持純邏輯，可被求解器/solver.ml 直接 import）。
- 修改求解器/調試面板不得破壞 §2.1 mod 不變量；目標框與洞/凸起標記必須共用 `find_best_window`。
- 不大改 `solver/data/` 產物與 `.gitignore` 列出的個人檔（`.clinerules/`、`.trae/`、`.vscode/`、`参考/` 不入庫）。
- 快取/執行期生成物（`__pycache__`、`config/records.dat`、`macro/*.json` 視情況）不要誤入 git。
- 除錯優先無頭測試；只有在需要視覺驗證（目標框/標記位置）時才跑 GUI。

## 12. 已知限制 / 長期目標

- 目前滑塊皆為同尺寸正方形；暫不支援三角形/編號方塊等變體。
- 求解長期目標：以「梯度聚攏粗調 + AI 收尾」完成高階謎題。人類模仿（`human_ai`）已接入 `SOLVER_ALGORITHMS`（§5.4 管線 B）；AI 收尾模型仍在提升中。
