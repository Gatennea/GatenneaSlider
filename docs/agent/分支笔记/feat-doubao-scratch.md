# feat/doubao-scratch 分支笔记

> 受众：豆包（本分支归属 AI）+ 主目录巡检。只放「在办 + 未决发现」，完成随分支合并后清掉。
> 公共文件（待办清单 / agents.md / 实验索引）仍归主目录独占，本分支一律不改。

## 认领

- **§五十四 三维滑块扩展（正方体单元）**：2026-11-17 用户拍板交豆包，已认领、未排期。
  方案真源 `docs/spec/三维扩展方案_正方体单元_2026-11-17.md`（七节）；总账在 `docs/agent/待办清单.md` §五十四。
  本轮只接手、未动任何游戏代码。

## 动哪些文件（认领范围，防撞车）

按方案 §4 代码落点，六阶段涉及的文件列清；核心闭环第 1–4 步反复碰 `gui/renderer.py` 和
`gui/events.py`，**串行推到底，不按阶段分给多个 AI**：

- 第 0 步 建局/入口：`engine/adapter.py`（cubic 传 m/n/d）、`puzzle_types.py`（create_puzzle 加 depth、
  puzzle_key 加三维格式）、`GUI.py`（`_refresh_puzzle_presets` 加「三维 ▸」二级子菜单）、`gui/events.py`
  （子菜单分派核对 depth 传递）。
- 第 1 步 画出来：新增 `engine/cubic_view.py`（投影 + 深度排序）、`engine/cubic_camera.py`（四元数）；
  改 `gui/renderer.py` 的 `draw_board` 按 kind 分派。
- 第 2 步 六视角/旋转：`gui/events.py`（空白拖动→旋转、滚轮缩放、双击判定）、`gui/file_ops.py`
  （save/load_config 加一组三维相机字段）。
- 第 3 步 选中：新增 `gui/cubic_pick.py`（射线求交）；续改 `gui/events.py`。
- 第 4 步 真能玩：`gui/virtual_keyboard.py`（三轴六键）、renderer 加三维箭头、`engine/compat.py`
  注册 cubic 六向字母表。
- 第 5 步 历史：`history.py`（快照/动作扩到 (r,c,d)）、`gui/file_ops.py`（存档加深度 + type:cubic、
  按 type 读旧档），可能动 `gui/compressed_save.py`。
- 第 6 步 动画：`gui/animation.py`（渲染层偏移，不碰逻辑坐标）。
- 后期（求解器/创造/宏/防偏移）到那步再单独规划，不预判。
- **接口占位**：`gui/feature_index.py` 给功能加形态键、只登记已实现的；HTTP 的 `API_INDEX` 按实现进度
  逐条加、不铺空端点（`_test_external_control.py` 逐条断言）。

## 开工要点（主目录上一轮给的建议，落账备查）

1. **第一刀切第 0 步断点，它现在还在**：主目录 2026-11-17 实测 `create_adapter_puzzle('cubic',3,3,1)`
   仍抛 `TypeError: cubic_spec() missing 3 required positional arguments: 'm','n','d'`。
   先补 m/n/d 传参 + 菜单「三维 ▸ 1×1×1~3×3×3」入口；点进去报错也没关系，入口先于功能落地。
   保持显式报错，**禁止加「失败退化成二维」的兜底**。
2. **核心闭环不并行**：第 1–4 步几乎轮着改 `renderer.py`/`events.py`，文件高度交叠，按
   「同一件事只给一个 AI、尽量不并行」一个 AI 串行推到底。真正能并行的只有边界清楚的小块
   （如独立的 `cubic_camera.py`），且按文件交叠判、不按编号分。
3. **认领占位写清动哪些文件**（见上一节），不只是「认领 §54」——§43 两个 AI 各写一版白写回退的教训。
4. **验收先过第 1 步遮挡关**：几个立方体摆成小长方体，标准视角下前挡后、三面朝向、凹坑可见，
   肉眼验过再写拾取；这步不过后面全搭在空中。
5. **测试按 §9.2 分级，本机别跑全套**：全套 20–35 分钟且 CI 自动跑；本机只做 grep 旧 API 残留 +
   `pytest --collect-only` + compileall + 三项 lint + 受影响 `-k`。基线 4 红是既有的、别改门槛；
   三维新测试用 `_test_cubic_*.py`。
6. **API 安全点**：求解器接上前 `/solve` 和 `/solver/*` 对三维明确回「不支持」，不拿二维求解器硬算；
   新增端点同步 `API_INDEX`/`HELP_DETAILS`/分派三处。

## 未决 / 发现（开发中随手记）

- （暂无）
