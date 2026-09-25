# 貓九的滑塊遊戲（Gatennea Slider）

這是給 AI Agent 的readme。在讀該文檔前應當先著重理解“開發約定（尤其是通用開發約定）”。

---

基於 **Python + pygame-ce** 的滑塊拼圖遊戲。玩家（或 AI）透過「選擇縫隙 → 選擇滑塊組 → 滑動」把打亂的方塊還原成目標形狀：**方形/帶序號**是 `m×n` 或 `n×m` 實心矩形（允許整體平移，不做模板比對）；**三角形密鋪**是邊長 k 的實心大正三角形（k² 個單位三角，允許整體平移與 120°/240° 旋轉）；**米字格**是實心 m×n 米字矩陣（4mn 個直角三角滑塊，允許整體平移與換晶格）。四種形態共用同一套「縫隙 + 移動」互動模型，只有縫隙族數與方向字母不同。

> ## ⚠️ 給 AI Agent 的速覽（先讀這節）
>
> 1. **不要嘗試操控 Pygame 窗口。** 本專案刻意提供兩條程序化控制通道：
>    - **HTTP REST**（推薦）：`http://127.0.0.1:5050`，結構化 JSON 請求/回應。
>    - **stdin 指令**：向主程序 stdin 寫一行指令（打包成 `--windowed` exe 時 `sys.stdin is None`，該通道自動停用）。
> 2. 一次完整移動 = 三個指令依序執行：`select_gap` → `select_block` → `move`，缺一不可（**三角形密鋪例外**：`move` 可省略 `select_gap`，由遊戲按「縫隙線穿過滑塊」規則自動定縫）。
> 3. 每次「動作型」指令後建議再 `GET /status` 確認結果；所有回應都有 `ok: true/false`。
> 4. `solved` 不代表「回到最初版面」，而是「方塊在任意位置構成實心矩形／三角形／米字矩陣」。
> 5. 若要改求解器/調試面板：務必先讀 §2「核心不變量」與 §5「求解器子系統」，避免破壞平移不變量假設。
> 6. **四種形態**：方形 `{step}~{m}*{n}`、帶序號 `…#num`、三角形密鋪 `{step}~tri{k}`、米字格 `{step}~mi{m}*{n}`（見 §2 詞彙與 §12 限制；求解器/建表/ML 對後三者暫不支援）。
>
> **建議閱讀順序**（由底層到外層）：
> `game.py` → `game_mi.py`／`game_triangle.py` → `solver/actions.py`、`solver/state.py` → `GUI.py` → `gui/events.py`（`process_commands`）→ `http_server.py` → `solver/__init__.py`、`solver/ml/gather_solver.py`。

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
- 啟動/異常寫入 `config/error_log.jsonl`（一行一條 JSON；寫不進去時退回系統 temp），全部異常（含子執行緒）都會記錄。

快速健康檢查：

```bash
curl http://127.0.0.1:5050/status
# => {"puzzle":"2~4*4","step_count":0,"solved":true,"matrix":[[...]],"selected_gap":null,...}
```

---

## 2. 詞彙與核心不變量（四形態）

| 詞彙 | 定義 |
| --- | --- |
| 滑塊 Block | 正方形單元，`location=[r, c]`（0-based，row 向下為正） |
| 棋盤 SliderMatrix | `m×n` 起始版面；實際方塊可在任意位置活動 |
| 縫隙 gap | 兩區塊之間的**分割線**。`h`=橫向縫隙（row 之間），`v`=縱向縫隙（col 之間）；以 `line` 標號。`select_gap {type,line}` 選它 |
| 滑塊組 | `select_block {row,col}` 選中縫隙一側**連通**的整組方塊（DFS，`opt()`） |
| 移動 move | `w/s/a/d`（上/下/左/右）。**限制：`v` 縫隙只能 `w/s`；`h` 縫隙只能 `a/d`**（見 `gui/events.py` 移動分支） |
| step | 等級/基本步距；每次移動方塊組整體平移 step 個「一格」。**米字格的「一格」按族定義**（橫豎 = 一條格邊、斜向 = √2/2），見下行；方形/三角形則恆為 step 個單位長 |
| solved | 所有方塊構成**任意位置**的 `m×n` 或 `n×m` 實心矩形（含轉置，不含形狀模板） |
| 帶序號 numbered | `Block.number`（`int|None`）可選欄位。**不改變移動/幾何語義**，只影響判勝與渲染。puzzle 標籤加 `#num` 後綴；存檔為 v2（`puzzle.type='numbered'` + `snapshots[].numbers`） |
| 帶序號 solved | 實心矩形 **且** 編號按行主序排佈，但允許整體旋轉/鏡像（矩形二面體群 D4 共 8 種：恆等/旋轉 90/180/270/上下左右鏡像/主副對角線翻轉）。非正方（如 4×3）轉置後朝向變 3×4 也算 |
| puzzle 標籤 | 字串 `"{step}~{m}*{n}"`，例 `2~4*4`。成績/宏/建表皆以它分組 |
| map 文本 | `#`=方塊、`_`=空白 的棋盤框文本；`export_map()/import_map()` 序列化格式。三角形另有 `^`=僅▲、`v`=僅▼（見下行） |
| 三角形密鋪 triangle | `game_triangle.py::TriangleSliderMatrix`。單位三角 `(i, j, up)` 斜座標（`up=True`▲尖朝上 / `False`▼尖朝下），一菱形胞 `R(i,j)` 含 ▲+▼ 兩片。`new m n step tri` 以 `m` 作大三角邊長 k（`n` 仍須給，通常同值），建局即邊長 k 實心大三角（還原態），`Alt+S` 另行打亂。puzzle 標籤 `{step}~tri{k}`；存檔為 v2（`puzzle.type='triangle'` + `triangle_side` + 菱形胞 2-bit 快照） |
| 三角形縫隙 | **3 族**（皆為穿過密鋪的直線，`line` 為該族線號）：`h`=水平線（`j=line`）、`p`=`i=line`（+60°）、`n`=`i+j=line`（−60°）。選組為縫隙一側 3-鄰接 DFS（▲↔▼ 交錯，每片恰 3 鄰） |
| 三角形移動 | **6 向**，字母 `w/e/a/d/z/x`（鍵盤正好六邊形：`W E` / `A D` / `Z X` = ↖↗ / ←→ / ↙↘）。移動**平行於縫隙線**：`h`→`a/d`、`p`→`e/z`、`n`→`w/x`；不平行回 `wrong_direction`。與方形「垂直於縫隙」相反，勿混淆 |
| 三角形 solved | 全部 k² 個單位三角拼成邊長 k 實心大正三角形；位置不限（可平移），朝向不限（120°/240° 旋轉等效），顛倒（鏡像）不可達。判定用頂點集凸包（三頂點、三邊長皆 k、殼內單元集合一致） |
| 三角形 mod 不變量 | `(i % step, j % step)` 永遠不變（三族移動向量都是 step 整數倍），連鎖提示（§2.1 類比）依 `cell_class(i,j)+up` 高亮（含朝向），且只亮整塊落在滑塊凸包內的位置 —— 斜座標方框右上側是大三角形狀外的空白，不畫 |
| 三角形 map 文本 | `#`=▲▼俱全、`^`=僅▲、`v`=僅▼、`_`=空白；匯出為菱形胞 2-bit 矩陣（0/1/2/3）。**方形 `#/_` 圖不可餵給三角形**（會整塊判定為非法） |
| 米字格 mi | `game_mi.py::MiSliderMatrix`。單位塊 `(r, c, q)`：方格沿兩對角線切成 4 個直角等腰三角，`q`∈`N/E/S/W` = 斜邊貼著哪條格邊，整盤 4mn 片。`new m n step mi`，標籤 `{step}~mi{m}*{n}`；建局即實心矩形（還原態），`Alt+S` 打亂。存檔為 v2（`puzzle.type='mi'` + 8-bit 快照） |
| 米字格縫隙 | **4 族**（皆為穿過棋盤的直線）：`h`=橫格邊、`v`=豎格邊、`d1`=`r-c` 主對角（`\`）、`d2`=`r+c` 副對角（`/`）。`select_gap {type,line}`；`line` 在錯位態可為半整數（如 `h 1.5`），終端/HTTP 座標解析走 `parse_mi_coord` |
| 米字格移動 | **8 向**，字母 `w/e/a/d/z/x/q/s`。移動**平行於縫隙線**：`h`→`a/d`、`v`→`w/s`、`d1`→`x/q`、`d2`→`e/z`；不平行回 `wrong_direction` |
| **米字格「一格」** | **一格 = 該方向能滑動的最小量，與幾何長度無關**（用戶口徑 2026-09-23）。橫豎一格 = 一條格邊（長 1）；斜向一格 = 半個格身的斜向距離 √2/2，座標上即平移 ±(½,½)。**不存在「半格滑動」這種說法**；舊版的整格斜距 ±(1,1) 是「斜向兩格」。step=2 的斜向 = 連走兩次 = 舊版等級 1 的斜距 |
| 錯位態 / 兩晶格 | 斜向一格後一半的塊落進半整數座標，從此有 **A**（整數，建局態）與 **B**（半整數）兩個晶格；`game_mi.lattice_of(key)` 給 0/1。不變量 `2r` 與 `2c` 同奇偶 → `r−c`、`r+c` 恆整，對角縫永不切進塊裡，只有橫豎縫會整條穿過塊內部而選不動。把任一半再沿斜向推一格即回單一晶格 |
| 米字格 solved | 全部 4mn 片拼成任意位置的實心 m×n 米字矩陣：**可平移、可換晶格（錯開半格也算對）**——一條斜縫兩半朝同向各滑一格就能換晶格，是普通玩法走得到的狀態。判據用 8-bit 矩陣形狀，不要求回到建局那張整數格圖 |
| 米字格地圖文本 | 每格 8 bit = 4 個 q × 2 個晶格（bit0~3 = A、bit4~7 = B）。匯出端沒有半整數塊時仍是舊的每格一字元（4-bit），有錯位塊時輸出帶 `mi8` 標記行的每格兩字元格式；匯入端兩種都吃 |
| 米字格 `/status` | `blocks[]` 每條帶 `q`（朝向）與 `lat`（`A`/`B`），**沒有 `mod`**：錯位態的 `r%step` 會在 0 與 0.5 之間翻，不再是那種不變式 |
| 米字格控制 | 兩次觸控：第一下點縫；第二下**按住滑塊拖動**才提交——方向取這一次拖動的位移向量在選中縫切向上的投影符號（正側/負側 → 該族兩個方向字母）。第二下只按不拖 = 選中滑塊組並等待，方向交給虛擬鍵盤，**不在按下瞬間猜方向**。**單次觸控按凍結決策禁用**（八向可選，手指一抖就滑錯，誤觸面太大）。求解器/建表/ML、`/analysis/*`、宏錄製執行、除錯面板暫不支援；分組著色與懸停連鎖可用（摘要見 §12） |

### 2.1 Mod 著色不變量（求解器核心，勿違反）

對 `step > 1`，每次合法移動中，每個方塊的 `(r % step, c % step)` **永遠不變**（同側整組平移 step 的整數倍）。

> **step=1 的退化（GUI 側，勿與求解器混淆）**：位置類退化成朝向分組——方形只剩一組（全盤同類，著色與連鎖都關），三角剩 `up` 兩組、米字剩 `q` 四族。後兩形態「原本就靠朝向分組」，1 級一步一格能去的恰是同朝向任意位置，故**連鎖在 1 級照常開啟**；著色刻意不含朝向，1 級會全盤單色，仍只在 `step > 1` 開。統一實現在 `gui/cell_class.py`，閘門見 `gui/renderer.py`。

推論：

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
game_triangle.py       # 三角形密鋪純邏輯：DIRECTIONS/GAP_DIRECTIONS 兩張方向表、TriangleSliderMatrix
game_mi.py             # 米字格純邏輯：DIRECTIONS/GAP_DIRECTIONS、兩晶格（lattice_of）、MiSliderMatrix、8-bit 快照/地圖
GUI.py                 # SliderGUI 主類（8 個 Mixin 聚合）+ 主迴圈/高層操作/資源路徑
history.py             # GameHistory 快照式撤銷/重做
records.py             # Records 成績管理器（pickle+XOR 混淆存 config/records.dat）
http_server.py         # GameHTTPHandler：HTTP REST → 指令佇列（見 §6）

gui/                   # 全是 Mixin，被 SliderGUI 繼承
  board_view.py        #   SquareBoardView      方形幾何（cell↔像素/命中/方向表/8 區表），事件與渲染委派
  triangle_view.py     #   TriangleBoardView    三角形幾何：(i,j,up)→像素、半平面命中、3 族縫命中、包圍盒
  mi_view.py           #   MiBoardView          米字格幾何：(r,c,q)→像素、內切圓縮放、4 族縫命中、半整數線號
  renderer.py          #   RendererMixin        繪製棋盤（方形/三角形/米字格三套）/選單/面板/求解器選單/目標框與標記
  events.py            #   EventsMixin          滑鼠/鍵盤/快捷鍵/長按/面板互動/指令佇列處理
  animation.py         #   AnimationMixin       移動與 undo/redo 動畫、緩動
  dialogs.py           #   DialogsMixin         幫助/自訂謎題/PygameFileDialog/宏管理與命名框
  file_ops.py          #   FileOpsMixin         存檔/載入/組態管理（JSON）
  virtual_keyboard.py  #   VirtualKeyboardMixin 虛擬鍵盤浮動面板（F1 開關；三角形為六向三行佈局）
  metrics_panel.py     #   MetricsPanelMixin    調試指標面板（F2）＋目標框/洞標記選取
  records_panel.py     #   RecordsPanelMixin    成績記錄浮動面板（F3）
  tutorial.py          #   TutorialMixin        新手教程引導（首次啟動彈窗/步驟提示）
  text_input.py        #   TextInput            自繪文字輸入框（游標/選取/剪貼簿）
  annotation.py        #   AnnotationMixin      標注模式（B/Z/M/S 隱藏入口）：標注取樣／手動構造畫布／跟蹤執行；創造模式手動構造（方形/三角/米字）
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
| 單次觸控 `control_single_touch` | 直接**按住滑塊拖拽**即滑動（方形 8 區角度判定縫隙與方向，對齊 `web/docs/touch-gesture.md`；**三角形改為 6 向投影吸附**：手勢向量與 `game_triangle.DIRECTION_SCREEN` 六個晶格方向取最大點積，不枚舉扇區）；滑動後（含失敗）清空臨時選中 | `GUI.py::_drag_slide` / `_init_triangle_drag_follow` + `gui/events.py` 拖拽狀態機（`_mouse_drag_state`） |
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
| `gather` | 普通聚攏 | `gather_solver.gather_solve` | 貪心聚攏 + patience 停機 |
| `ida_star` | 最少步 | `solver.solve` | 保證最優，較慢 |
| `fast` | 最快-1 | `solve_fast` | IDA* 放寬 |
| `greedy` | 最快-2 | `solve_greedy` | 貪心爬山 + 擾動 |
| `table` | 查表求解 | `table_solver.table_solve` | 需先 `solver.data` 建表 |
| `fill_macro` | 填洞宏 | `fill_macro.solve_fill_macro` | 單洞 A-B-A' 共軛子宏；多洞無缺口貪心逐 couple（§5.4） |

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

**B. 人類模仿管線（`human_ai` 已在代碼中註解掉，暫未接入求解菜單；管線本身仍在 `solver.ml.human_solver`）**
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

伺服器綁定 `127.0.0.1:5050`；`GameHTTPHandler` 把每個請求轉成指令投到命令佇列，GUI 主執行緒於 `process_commands()` 執行後同步回 JSON。所有回應皆為信封 `{"ok":bool,"message":?...,"...":...}`；參數缺漏/型別/白名单/越界錯誤回 HTTP **400**（solver 參數數值越界為 `ok:false` 且不套用任何值，見 `/solver/params`），未知路徑回 **404**；`OPTIONS` 已開 CORS。

**端點一覽**（舊端點全部保留，舊腳本無需修改）：

| Method | Path | Body / 說明 |
| --- | --- | --- |
| GET | `/status` | 完整狀態（§下方 schema，含求解器/宏/開關資訊） |
| GET | `/map` | `{"ok":true,"map":"##__\n##__..."}`（按方塊包圍盒裁剪空邊）。**三角形**回 `#^v_` 四字符（菱形胞 2-bit）；方形/序號仍為 `#_` |
| GET | `/analysis/window` | 目標聚攏視窗 `{ok,window:{r0,c0,rh,cw,overlap},m,n,step}`；**三角形形態不支援，回 HTTP 400** |
| GET | `/analysis/holes` | 洞/缺口/凸起 `{ok,window,holes:[{type:"hole"|"dent",size,cells}],protrusions:[[r,c],...]}`；**三角形回 400** |
| GET | `/analysis/actions` | 合法動作列舉 `{ok,actions:[{gap_type,gap_line,side,move_dir}]}`；**三角形回 400** |
| GET | `/solver/algorithms` | `{ok,current,algorithms:[{key,name}]}`（7 種算法） |
| GET | `/solver/status` | 結構化求解狀態 `{ok,state,algorithm,progress,gradient,result_steps,elapsed_ms}`；state=`idle/running/solved/failed/cancelled` |
| GET | `/solver/params` | gather 參數 `{ok,params:{<key>:{value,enabled}}}` |
| GET | `/macro/list` | `{"ok":true,"macros":[{name,description,steps,recorded_step,base_point}]}` |
| GET | `/macro/status` | `{ok,recording,executing,selecting_base,reverse_mode,recording_steps,current_macro}` |
| GET | `/mode` | `{ok,mode:"practice"|"timed"}` |
| GET | `/settings` | `{ok,settings:{<鍵>:<值>}}`（13 個 GUI 開關 + 動畫時長） |
| GET | `/records` | 目前謎題成績摘要 |
| GET | `/timer/status` | `{"ok":true,...}` + `state`/`elapsed_ms` |
| POST | `/command` | `{"cmd":"<任意 CLI 指令>"}`（§7 全集） |
| POST | `/move` | `{"direction":"w|s|a|d"}`（方形/序號）或 `{"direction":"w|e|a|d|z|x"}`（三角形，平行於縫隙）；失敗帶 `reason`（§下方列舉） |
| POST | `/undo` `/redo` `/shuffle` `/reset` `/deselect` `/quit` | — |
| POST | `/new` | `{"m","n","step","numbered"?:bool}`；`numbered=true` 建帶序號謎題（行主序賦 1..m·n）。`type` 可選 `square`（默認）/`numbered`/`triangle`；`triangle` 以 `m` 作大三角邊長 k（`n` 仍須給） |
| POST | `/select_gap` | `{"type":"h|v","line":N}`（方形/序號）；三角形為 `{"type":"h|p|n","line":N}`（3 族）；米字格為 `{"type":"h|v|d1|d2","line":N}`（4 族，錯位態的 line 可為半整數）。**三角形可省略**：`move` 會按「縫隙線穿過滑塊」自動定縫 |
| POST | `/select_block` | `{"row","col"}`；三角形填菱形胞 `(i, j)`（`up` 由 `GET /status` 的 `blocks[].up` 取得） |
| POST | `/solve`（= `/solver/solve`） | `{"algorithm?":"<key>"}`；省略用目前算法；**執行中呼叫 = 取消** |
| POST | `/solver/cancel` | 請求停止求解（執行中回「已請求停止求解」） |
| POST | `/solve/status` | 舊版純文字狀態（保留相容） |
| POST | `/solver/params` | 部分更新 gather 參數：`{"max_steps":123,"max_wait_time_enabled":false}`；數值越界/型別錯回 `ok:false` 且整批不套用 |
| POST | `/map/load` | `{"map":"#/_ 地圖串（\\n 分行）","step"?：N}`；直接導入局面（無對話框），成功後 step_count=0、歷史重置。**三角形**傳 `#^v_`；方形/序號傳 `#_`（兩者字符集不互通，混用回 `ok:false`） |
| POST | `/file/save` | `{"path":"<存檔路徑>"}` |
| POST | `/file/load` | `{"path":"<存檔路徑>"}`；檔案不存在/計時中回 `ok:false` |
| POST | `/mode` | `{"mode":"practice"|"timed"}`（計時 running 中切換被拒） |
| POST | `/settings` | 部分更新 GUI 開關，如 `{"coloring_enabled":true,"animation_duration_ms":120}`；未知鍵/型別錯/越界回 400 且整批不套用 |
| POST | `/timer/start` | 競速開始（需先打亂處於 ready）；`/timer/stop` = DNF |
| POST | `/macro/record/start` `/macro/record/set_base` `{row,col}` `/macro/record/stop` `{name}` | 錄製 |
| POST | `/macro/execute` | `{name,base_row,base_col,reverse?}`；`reverse:true` 逆序播放（與 GUI 勾選同路徑） |
| POST | `/macro/delete` `{name}` `/macro/rename` `{old_name,new_name}` | 管理 |

`POST /move` 失敗時的 `reason` 列舉（成功時無 reason）：

| reason | 時機 |
| --- | --- |
| `not_selected` | 尚未選好縫隙與滑塊組 |
| `wrong_direction` | 縫隙方向與移動方向不匹配（方形：v 縫僅能 w/s，h 縫僅能 a/d；三角形：h→a/d、p→e/z、n→w/x，且移動**平行**於縫隙線） |
| `disconnected` | 移動後選中組會斷開（`try_move_ex` 預演） |
| `collision` | 移動後滑塊會重疊 |
| `timer_blocked` | 競速就緒態/只讀存檔等禁止滑動的狀態 |

**標準操作序列**（AI 每步移動的固定寫法；可用 `/analysis/actions` 先取得合法動作）：

```bash
curl http://127.0.0.1:5050/status
curl -X POST http://127.0.0.1:5050/shuffle
curl http://127.0.0.1:5050/analysis/actions          # 查目前合法縫隙/側/方向
curl -X POST http://127.0.0.1:5050/select_gap -H "Content-Type: application/json" -d '{"type":"h","line":2}'
curl -X POST http://127.0.0.1:5050/select_block -H "Content-Type: application/json" -d '{"row":2,"col":0}'
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d '{"direction":"d"}'
curl http://127.0.0.1:5050/status
```

三角形密鋪的操作序列（6 向；可省略 `select_gap`）：

```bash
curl -X POST http://127.0.0.1:5050/new -H "Content-Type: application/json" -d '{"m":6,"n":6,"step":1,"type":"triangle"}'
curl -X POST http://127.0.0.1:5050/new -H "Content-Type: application/json" -d '{"m":4,"n":4,"step":1,"type":"mi"}'   # 米字格 4×4
curl http://127.0.0.1:5050/status          # blocks[].up 取 ▲/▼ 朝向
curl -X POST http://127.0.0.1:5050/select_block -H "Content-Type: application/json" -d '{"row":2,"col":1}'
curl -X POST http://127.0.0.1:5050/move -H "Content-Type: application/json" -d '{"direction":"e"}'   # 右上；與當前縫不平行會回 wrong_direction
```

`/status` schema（`gui/events.py::_get_game_status`；舊 7 欄位語義不變）：

```json
{
  "puzzle": "2~4*4",
  "step_count": 15,
  "solved": false,
  "matrix": [[1,1,0,0],[1,1,0,0],[0,0,1,1],[0,0,1,1]],
  "selected_gap": ["v", 1],
  "selected_block": [0, 0],
  "animating": false,
  "m": 4, "n": 4, "step": 2,
  "game_mode": "practice",
  "timer_state": "idle",
  "readonly": false,
  "blocks": [ {"row":0,"col":0,"mod":[0,0]}, {"row":0,"col":2,"mod":[0,0]} ],
           ↓ 米字格時每條改為 {"row":0,"col":0,"q":"N","lat":"A"}（q=斜邊朝向，lat=晶格 A/B；無 mod）
  "macro":  { "recording": false, "executing": false },
  "solver": { "state": "idle", "algorithm": "gather_gradient" }
}
```

`/settings` 鍵名（`*_enabled` 皆為布林；`animation_duration_ms` 為 50–1000 整數毫秒，對應 GUI 的 `animation_duration`）：
`coloring_enabled`、`chain_hint_enabled`、`show_metrics_panel`、`animation_enabled`、`selection_animation_enabled`、`animation_duration_ms`、`control_single_touch`、`control_two_touch`、`control_mouse_kb`、`macro_reverse_mode`、`save_readonly_flag`、`prevent_overwrite_flag`、`op_log_enabled`。

`/solver/params` 鍵名：`max_steps`、`patience`、`max_wait_time`、`target_gather_score`、`aggressiveness`，各自另有 `<key>_enabled` 布林（停用＝求解時不設限）；範圍與 GUI 設定對話框的 gather 參數規格同源。

---

## 7. 控制介面二：stdin CLI

GUI 每幀執行 `process_commands()`（`gui/events.py`），支援三種佇列項目：純字串（stdin）、`(cmd, resp_q)`（HTTP 傳統指令）、`(cmd, resp_q, payload)`（HTTP 富 JSON body：多行地圖/設置等，動作名與 CLI 同名）。指令以空白分隔，第一個 token 為動作。

**完整動作清單**（= `http_server.py` 對映來源，兩介面 1:1）：

| 動作 | 參數 | 說明 |
| --- | --- | --- |
| `status` | — | 狀態（含 matrix、blocks、solver、macro 等完整 schema） |
| `map` | — | `#`/`_` 文本地圖（三角形為 `#^v_`） |
| `move` | `w\|s\|a\|d`（方形）或 `w\|e\|a\|d\|z\|x`（三角形） | 移動（需先選縫隙+滑塊；方形 `v`→w/s、`h`→a/d；三角形 `h`→a/d、`p`→e/z、`n`→w/x，**可省略 select_gap**）；失敗附 reason：not_selected/wrong_direction/disconnected/collision/timer_blocked |
| `undo` / `redo` | — | 快照式撤銷/重做 |
| `shuffle` | — | 打亂 |
| `reset` | — | 回到打亂前 |
| `new` | `m n step [num\|tri]` | 換謎題；第四參數 `1/num/true` = 帶序號模式，`tri/triangle` = 三角形密鋪（`m` 作邊長 k，`n` 仍須給） |
| `select_gap` | `h\|v line`（方形）／`h\|p\|n line`（三角形） | 例 `select_gap v 1`；三角形 3 族，線號合法性由遊戲側判定 |
| `select_block` | `row col` | 例 `select_block 0 0` |
| `deselect` | — | 清選中 |
| `export` / `import` | （沿用舊終端介面） | 地圖字串進出 |
| `window` | — | 目標聚攏視窗（find_best_window，除錯面板綠框同源） |
| `holes` | — | 洞/缺口/凸起（detect_holes，region 取視窗） |
| `actions` | — | 合法動作列舉（enumerate_valid_actions） |
| `solve` | `[algorithm]` | 啟動自動求解；給算法名則先切換（非法名回錯誤）；**執行中再呼叫 = 取消** |
| `solve_cancel` | — | 顯式取消（未在求解回 ok:false） |
| `solver_algorithms` | — | 列出 7 種算法與目前算法 |
| `solver_status` | — | 結構化狀態：idle/running/solved/failed/cancelled（含 progress/gradient/result_steps/elapsed_ms） |
| `solve_status` | — | 舊版純文字 `idle/running/solved(N步)/failed`（保留相容） |
| `solver_params` | 無參 或 `key=value ...` | 查詢或部分設置 gather 參數；啟用標誌用 `key_enabled=0|1`；越界整批拒絕 |
| `timer_start` / `timer_stop` / `timer_status` | — | 競速計時 |
| `records` | — | 目前謎題成績摘要（count/best/worst/ao5/ao12/dnf） |
| `macro_list` | — | 列出宏 |
| `macro_status` | — | 錄製/執行/逆序模式等狀態 |
| `macro_record_start` | — | 開始錄製 |
| `macro_set_base` | `row col` | 設定錄製基準 |
| `macro_record_stop` | `name` | 停止並命名保存 |
| `macro_execute` | `name base_row base_col [reverse]` | 在新基準執行宏（會做 step 相容拆分）；尾參 `reverse` 逆序播放 |
| `macro_delete` | `name` | 刪除 |
| `macro_rename` | `old new` | 改名 |
| `load_map` | `<地圖串>` | 直接導入局面（行分隔用換行或 `;`），成功後 step_count=0、歷史重置 |
| `save_file` | `<路徑>` | 存檔到指定路徑（無對話框） |
| `load_file` | `<路徑>` | 從指定路徑讀檔（檔案不存在/計時中回 ok:false） |
| `mode` | 無參 或 `practice\|timed\|create` | 查詢或切換練習/競速/創造模式（計時 running 中拒絕） |
| `settings` | 無參 或 `key value` | 查詢或設置 GUI 開關（布林接受 1/0/true/false；animation_duration_ms 為 50–1000 整數） |
| `quit` | — | 結束遊戲（`running=False`） |

> 註：`load_map`/`save_file`/`load_file`/`mode`/`settings`/`solver_params`/`solve`/`macro_execute` 經 HTTP 呼叫時走 JSON body 通道（見 §6 對應端點），可傳多行地圖串與結構化參數；CLI 則用上述空白/`;` 語法。

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
| `config/error_log.jsonl` | 執行期錯誤（含子執行緒）+ 啟動痕跡，一行一條 JSON，traceback 按行拆成數組 | 常開，超 4MB 輪轉成 `.old`；寫不進去退回系統 temp |
| `config/op_log.jsonl` | 操作日誌（點擊坐標/命中/提示），調試用 | 默認關，設定→文件→操作日誌 打開 |

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
python test\_test_http_api.py           # HTTP REST 端到端（狀態/分析/求解/宏/存取/模式/開關，含真實求解與取消）
python test\_test_mod_constraint.py     # mod 約束/detect_target_corner
python test\_test_gradient_pipeline.py  # 智能聚攏並行管線收尾
python test\_test_full.py               # 綜合
python test\_test_rp_menu.py / _test_rp_colors.py   # 成績面板
python test\_test_block_load.py / _test_textinput.py
```

帶序號 / 三角形密鋪的無頭測試（每支涵蓋幾何/滑動/存讀/競速/HTTP 等子集）：

```bash
python test\_test_numbered.py / _test_numbered_p2.py / _test_numbered_save.py / _test_numbered_timer.py / _test_numbered_symmetry.py
python test\_test_triangle_geometry.py / _test_triangle_view.py / _test_triangle_core.py   # 幾何/視圖/純邏輯
python test\_test_triangle_history.py / _test_triangle_save.py / _test_triangle_timer.py   # 快照/存讀/競速
python test\_test_triangle_http.py / _test_triangle_play.py / _test_triangle_render.py / _test_triangle_p2.py  # HTTP/互動/渲染
```

米字格的無頭測試（幾何/引擎/視圖/提示/手動驗收/交互，每支直接執行、通過會印 `全部通過` 或 `anim-click 回归 PASS`）：

```bash
python test\_test_mi_geometry.py / _test_mi_h0_geometry.py / _test_mi_span.py   # 幾何與 side_of/span
python test\_test_mi_core.py                                                      # 引擎：opt/try_move/快照/地圖往返
python test\_test_mi_h2_view.py / _test_mi_h3_hint.py                             # 四族縫命中與被鎖縫提示
python test\_test_mi_gui.py / _test_mi_hittest.py / _test_mi_drag_direction.py    # 兩次觸控（第二下按住拖動）/命中/八向定向
python test\_test_mi_h4_acceptance.py / _test_mi_animation.py                     # 規劃 §5 手動驗收清單 / 八向動畫
python test\_test_anim_click.py                                                   # 動畫窗口裡的鼠標輸入（含米字格第二下）
```

三形態共用的純邏輯測試（移動不變量類／構造校驗，不開窗、不依賴 GUI）：

```bash
python test\_test_cell_class.py       # 移動不變量類：三形態類不變性／米字錯位態／class_index 與方形算式一致
python test\_test_shape_validate.py   # 構造校驗：塊數／單連通／類計數＋偏移掃描／空位；blocks_from_cells 重建
python test\_test_create_build_canvas.py  # 創造模式手動構造：三形態冒煙／非法路徑／取消／數字編號棧 LIFO／隨機生成攔截／標注取樣拒絕
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
- `game.py` 不得引入 pygame（保持純邏輯，可被求解器/solver.ml 直接 import）。**三角形密鋪同守此律**：`game_triangle.py` 亦為零 pygame 依賴的純邏輯模組（互動代碼只 import 它的 `DIRECTIONS` / `GAP_DIRECTIONS` / `DIRECTION_SCREEN` / `tri_key` 四張表或函式）。
- 修改求解器/調試面板不得破壞 §2.1 mod 不變量；目標框與洞/凸起標記必須共用 `find_best_window`。
- 三角形形態下 `/analysis/*` 一律回 400（降級），`solve`/建表/ML/宏等高級功能照 §12 禁用或暫不支援（創造模式手動構造已開放，隨機生成不支援）；新增進階功能前先確認形態分支。
- 不大改 `solver/data/` 產物與 `.gitignore` 列出的個人檔（`.clinerules/`、`.trae/`、`.vscode/`、`参考/` 不入庫）。
- 快取/執行期生成物（`__pycache__`、`config/records.dat`、`macro/*.json` 視情況）不要誤入 git。
- 除錯優先無頭測試；只有在需要視覺驗證（目標框/標記位置）時才跑 GUI。

## 12. 已知限制 / 長期目標

- 帶序號模式（`numbered`）：求解器/建表/ML 管線**暫不支援**（狀態需身份感知，動作語義也不同），入口直接拒絕並提示；其餘功能（撤銷重做/動畫/競速/存讀檔/地圖導入）全部可用。
- 三角形密鋪（`triangle`）：已實作核心五步 + P2 體驗（六向鍵盤/虛擬鍵盤/連鎖提示/分組著色/拖拽 6 向投影/競速成績/地圖導入）。**暫不支援**：求解器/建表/ML（需新動作語義與對稱群）、`/analysis/*`（回 400 降級）、宏、隨機生成（創造模式只能手動構造）、調試面板的三角版（P3，未做）；`solved` 只接受「尖朝上/120°/240°」三種朝向，鏡像（顛倒）不可達。
- 米字格（`mi`）：已實作斜向一格的引擎（`game_mi.py`，含錯位態兩晶格、8-bit 快照與 `mi8` 地圖）、兩次觸控（第二下按住滑塊拖動才定向提交，只按不拖則選組等虛擬鍵盤）+ 拖拽跟隨預覽 + 虛擬鍵盤 + 八向動畫 + 分組著色與懸停連鎖 + 競速/存讀檔/打亂/撤銷重做。**暫不支援**：求解器/建表/ML、`/analysis/*`（回 400）、宏錄製執行、隨機生成（創造模式只能手動構造）、調試面板、單次觸控（凍結決策：八向誤觸面太大）。已知注意點：等級語義漂移（等級 1 斜距 = √2/2，等級 2 = 舊版等級 1）；錯位態橫豎縫會整條穿過塊內部而選不動（提示按剩餘條數說，沿斜向再走一格即復活）；`/status` 的 `blocks[]` 沒有 `mod`，改帶 `q` 與 `lat`。 origin/main
- 存量缺陷（**方形同樣存在**，非新形態引入）：多步（批量）移動時 `step_count` 由 `move_selected_blocks` 累加 `move_step`，而 `history.save_snapshot` 每步只記 `steps = 1`，導致存檔重載（`_load_save_data` 以 `current_step_total()` 重算）與 undo/redo 後的步數比實際少。
- 求解長期目標：以「梯度聚攏粗調 + 填洞宏收尾」完成高階謎題。人類模仿（`human_ai`）管線仍在 `solver.ml.human_solver` 但未接入求解菜單（已註解）。填洞宏（`fill_macro`）已註冊為 `SOLVER_ALGORITHMS` 之一，實作單洞 A-B-A' 共軛子宏與多洞無缺口貪心逐 couple（§5.4 管線 B 相關）。
