> **受眾**：AI

# 多 AI 協作與 worktree 工作流（2026-11-13 用戶拍板）

多個 AI 並行開發同一倉庫的分工模型：**主目錄獨佔 `main`，其他 AI 各開 worktree**。
比「每個 AI 各自 clone 一份」好在：對象庫只有一份（省磁盤）、fetch 一次所有目錄共享、分支天然隔離。

## 1. 分工模型

- **主目錄** `E:/program_project/other/wkbddtest/GatenneaSlider` 檢出 `main`，由管 main 的 AI 獨佔：
  負責合併、合併後測試、（經用戶決策）推送。**主目錄只做合併與同步，完全不改代碼**——
  管 main 的 AI 自己要改代碼時，同樣開 work 分支 + worktree，改完測完自己並回。
  例外：純文檔小改（紅線 / 索引 / 待辦登記）允許主目錄直接改並**立即提交**（停留分鐘級，
  `git add` 指定文件、不捲入他人半成品）。其他 AI **不得在自己目錄操作 main**
  （物理隔離：main 只在主目錄檢出，其他 AI 想誤提交都做不到）。
- **所有 AI（含管 main 的）改代碼一律走 worktree**：每個工作點一個目錄 `GatenneaSlider-<後綴>`，檢出自己的分支開發。
- 現有範例（2026-11-13）：`GatenneaSlider-geo` → `feat/geometry-engine`、
  `GatenneaSlider-math` → `feat/math-research`（數學長分支，不合完即刪）、
  `GatenneaSlider-reuse` → `topic/solver-reuse-refactor`。

## 2. worktree 基本操作

```bash
# 新建 worktree：新目錄 + 新分支，一條命令
git worktree add E:/.../GatenneaSlider-<後綴> -b feat/<主題>

# 列出所有 worktree
git worktree list

# 正確刪除（目錄裡有未提交改動會拒絕，防丟）
git worktree remove <目錄路徑>

# 目錄已被手動刪掉時，主倉庫跑這個清登記
git worktree prune
```

兩條硬規則：

1. **同一分支不能同時檢出到兩個目錄**（git 直接拒絕，這是保護不是障礙）。
2. **刪 worktree 必須走 `git worktree remove`**，別直接刪文件夾；已手動刪過的跑 `git worktree prune` 清登記。

## 3. 合併紀律（管 main 的 AI 執行）

0. **合併前置檢查：主目錄 tracked 工作區必須乾淨**（`git status --short --untracked-files=no` 為空）。
   主目錄可能被多個會話共用——別人的半成品（` M` 狀態）在場就**等它提交完再合併**，不搶窗口。
   理由：①merge 改動若與半成品文件相交，git 直接拒絕，白跑；②底座測試 import 的是帶半成品的工作區，
   好壞歸因會混（2026-11-13 靠「先採基線」倖免，這是臨時手段不是規則）；③最險的一種：merge 進行中
   對方 commit 推進了 HEAD，merge commit 的樹快照會**把對方已提交的內容回退掉**——不報錯、事後才炸。
1. **完成標準**：分支上功能完整 + 護欄測試通過，才通知合併——**不是每 commit 一次就並一次**
   （並得頻繁單次衝突小，但測試輪次暴增；按「完整功能」粒度並最省事）。
2. **合併串行**：一次只並一個分支；並完跑底座測試（`pytest test/ --collect-only -q` + compileall +
   三項 lint，見 `readme_to_agent.md` §9.2）確認沒炸，再並下一個。並行並兩個分支會讓衝突疊加。
3. **合完即刪**（沿用 `AGENTS.md` §7 既有約定）：合併後刪分支 + `git worktree remove`。
   `feat/math-research` 是長分支，例外不刪。
4. **衝突處理**：小衝突管 main 的 AI 直接解；大衝突（同文件兩邊大改）優先讓分支歸屬的 AI
   自己 rebase 到最新 main 後重新提出，不硬解。
5. **推送不變**：仍走「審後提交、不擅自推送」，push 由用戶 / 網關決策，合併進 main 不等於可推送。

## 4. 各 AI 需要知道的差異

- **config 運行態 / build / dist 各目錄獨立**：worktree 裡跑測試、清運行態**不會碰到主目錄用戶
  正在玩的實例**（隱藏好處）；但 build / dist 是空的，打包要各自重建。
- **分支快照滯後**：AGENTS.md / docs 在該 AI 開工那一刻定格，main 上新合入的約定**不會自動出現**
  在其目錄。重要約定更新後，各 AI 開工前先 `git merge main`（或由管 main 的 AI 在合併時提醒同步）。
- **untracked 大產物別堆 worktree**：experiments 產物 / 打包輸出用完即清，
  別積到只能 `git worktree remove --force` 的地步。
