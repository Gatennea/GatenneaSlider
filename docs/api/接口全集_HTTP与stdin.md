> **受眾**：AI / 開發者（外部控制接口的逐端點全集；實戰坑見同目錄 `AI使用API注意事项.md`）

# 接口全集：HTTP REST 與 stdin CLI

> 2026-11-06 從 `docs/agent/readme_to_agent.md` §6 / §7 **原樣搬來**（只補了這段說明，正文一字未改）。
> 兩條通道共用同一份動作清單：`http_server.py` 的 `API_INDEX` 與 `HELP_DETAILS` 是唯一真源，
> 本文是它的可讀鏡像——**兩者衝突時以代碼為準**，並順手修本文。
> 實際怎麼用不踩坑（令牌、請求寫法、多實例、截圖驗收、卡死處置）見 `docs/api/AI使用API注意事项.md`。

## 6. 控制介面一：HTTP REST（AI 主要通道）

伺服器綁定 `127.0.0.1:5050`；`GameHTTPHandler` 把每個請求轉成指令投到命令佇列，GUI 主執行緒於 `process_commands()` 執行後同步回 JSON。所有回應皆為信封 `{"ok":bool,"message":?...,"...":...}`；參數缺漏/型別/白名单/越界錯誤回 HTTP **400**（solver 參數數值越界為 `ok:false` 且不套用任何值，見 `/solver/params`），未知路徑回 **404**；`OPTIONS` 已開 CORS。

### 6.0 外部控制鑑權（2026-10-13 起，所有業務端點強制）

**威脅模型**：伺服器只綁 `127.0.0.1`，令牌防的是**本機上的其他程序與網頁**（CORS 全開，任意網頁都能探測這個端口）。stdin 管道通道**不設防**——能寫 stdin 的只有啟動遊戲的父進程，天然可信。

- **令牌**：進程級隨機（`secrets.token_urlsafe(24)`），只存內存、不落盤。取得方式：
  - **AI 啟動**：遊戲往 stdout 打印一行 `GATSLI_TOKEN=<令牌>`（subprocess 管道天然讀到）；
  - **人類啟動**：遊戲「設置-控制」頁「複製連接話術」按鈕（含令牌 + 端口 + 三步引導的一段話，直接發給外部程序即可——AI 助手是其中最常見的一種）。
- **傳遞**（二選一）：請求頭 `Authorization: Bearer <令牌>`（推薦）；或 URL 查詢參數 `?token=<令牌>`。
- **狀態碼**：開關關閉（遊戲「設置-控制」→「允許外部控制」）→ **403** 一切拒絕；令牌缺失 → **401**；令牌不匹配 → **401**。默認開啟。
- **生命週期**：遊戲重啟即換新令牌；關閉開關會立即作廢當前令牌，重開生成新令牌（關閉期間複製出去的話術隨之失效）。
- **`GET /help`**：API 索引（端點列表 + 第一條命令引導），永遠與代碼同步；索引與遊戲內「下載控制教程」按鈕導出的自包含 Markdown **同源生成**（教程文件不含令牌——它可能被分享/上傳官網）。**`GET /help/<端點>`**：單個端點的完整用法（說明 + body 字段表 + 返回字段 + curl 示例），如 `GET /help/move`；未知端點回 404 並指回 `/help`。

```bash
# 標準寫法（推薦 header）
curl -H "Authorization: Bearer <令牌>" http://127.0.0.1:5050/status
# 不方便加頭時用 query
curl "http://127.0.0.1:5050/status?token=<令牌>"
```

**端點一覽**（舊端點全部保留，舊腳本無需修改；**全部端點都需要令牌**，含 `/help`）：

| Method | Path | Body / 說明 |
| --- | --- | --- |
| GET | `/help` | API 索引 `{ok,message,auth,first_step,detail,endpoints:[{path,method,summary}]}`；需要令牌（與全部端點一致） |
| GET | `/help/<端點>` | 單個端點詳情 `{ok,path,method,summary,description,params:[{name,type,required,desc}],returns,example}`；未知端點回 404。如 `/help/move` |
| GET | `/status` | 完整狀態（§下方 schema，含求解器/宏/開關資訊） |
| GET | `/map` | `{"ok":true,"map":"##__\n##__..."}`（按方塊包圍盒裁剪空邊）。**三角形**回 `#^v_` 四字符（菱形胞 2-bit）；方形/序號仍為 `#_` |
| GET | `/analysis/window` | 目標聚攏視窗 `{ok,window:{r0,c0,rh,cw,overlap},m,n,step}`；**三角形形態不支援，回 HTTP 400** |
| GET | `/analysis/holes` | 洞/缺口/凸起 `{ok,window,holes:[{type:"hole"|"dent",size,cells}],protrusions:[[r,c],...]}`；**三角形回 400** |
| GET | `/analysis/actions` | 合法動作列舉 `{ok,actions:[{gap_type,gap_line,side,move_dir}]}`；**三角形回 400** |
| GET | `/solver/algorithms` | `{ok,current,algorithms:[{key,name}]}`（9 種算法） |
| GET | `/solver/status` | 結構化求解狀態 `{ok,state,algorithm,progress,gradient,result_steps,elapsed_ms}`；state=`idle/running/solved/failed/cancelled` |
| GET | `/solver/params` | gather 參數 `{ok,params:{<key>:{value,enabled}}}` |
| GET | `/macro/list` | `{"ok":true,"macros":[{name,description,steps,recorded_step,base_point}]}` |
| GET | `/macro/status` | `{ok,recording,executing,selecting_base,reverse_mode,recording_steps,current_macro}` |
| GET | `/mode` | `{ok,mode:"practice"|"timed"}` |
| GET | `/settings` | `{ok,settings:{<鍵>:<值>}}`（13 個 GUI 開關 + 動畫時長） |
| GET | `/records` | 目前謎題成績摘要 |
| GET | `/timer/status` | `{"ok":true,...}` + `state`/`elapsed_ms` |
| GET | `/screenshot` | 保存當前畫面為 PNG：`?path=<目標>` 指定路徑（缺 .png 後綴自動補）；缺省存遊戲目錄 `screenshots/` 下按時間戳命名（同秒連拍自動加 `_1/_2` 不覆蓋）。回 `{ok,path,width,height}`；保存的是最近一次繪製完成的畫面 |
| POST | `/command` | `{"cmd":"<任意 CLI 指令>"}`（§7 全集） |
| POST | `/screenshot` | 同 `GET /screenshot`；body 可帶 `{"path":"<目標路徑>"}`，缺省自動命名 |
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

**stdin 通道不設防**（能寫 stdin 的只有啟動遊戲的父進程，天然可信）——與 HTTP 的令牌鑑權（§6.0）是兩套信任模型：HTTP 面向「本機任意程序/網頁」，stdin 面向「啟動方」。

**完整動作清單**（= `http_server.py` 對映來源，兩介面 1:1；`help` 可即時查這份清單 + HTTP API 索引）：

| 動作 | 參數 | 說明 |
| --- | --- | --- |
| `help` | — | 打印 CLI 命令索引 + HTTP API 索引（resp_q 通道回 JSON） |
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
| `screenshot` | `[路徑]` | 保存當前畫面為 PNG（缺省存 `screenshots/` 自動命名）；HTTP 同名端點 `GET/POST /screenshot` |
| `export` / `import` | （沿用舊終端介面） | 地圖字串進出 |
| `window` | — | 目標聚攏視窗（find_best_window，除錯面板綠框同源） |
| `holes` | — | 洞/缺口/凸起（detect_holes，region 取視窗） |
| `actions` | — | 合法動作列舉（enumerate_valid_actions） |
| `solve` | `[algorithm]` | 啟動自動求解；給算法名則先切換（非法名回錯誤）；**執行中再呼叫 = 取消** |
| `solve_cancel` | — | 顯式取消（未在求解回 ok:false） |
| `solver_algorithms` | — | 列出 9 種算法與目前算法 |
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

*維護記錄：2026-11-06 自 `docs/agent/readme_to_agent.md` §6/§7 拆出（內容未改），原處只留指針。*
