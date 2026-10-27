# -*- coding: utf-8 -*-
"""把待办清单 §九 从「未定位」改写为「已定位」（一次性脚本，跑完可留档）。

用脚本而非编辑器改：本节含大量中文全角标点，Edit 工具匹配不可靠。
"""
import os

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PATH = os.path.join(_PROJ, 'docs', 'agent', '待办清单.md')
MARKER = '**2026-10-28 排查进展'

NEW = """**2026-10-28 定位结果：已复现，根因锁定（旧档缺 `engine_state`）**

- ✅ **两个症状都复现了**，且同源：`engine_state`（无损键表）是承重字段。模型板型
  同 2D 格可叠多块（不同朝向），矩阵编码把同格多块压成一格；`restore_snapshot`
  拿不到 `engine_state` 就回退 lossy 的 matrix 重建 → 盘面被压碎。
  实测（mi2 随机游走 10 步后存档，三个 seed 一致）：
  | | 块数 | 连通分量 | 按打乱 |
  |---|---|---|---|
  | 完整存档（带 es） | 48 | 1 | `已打乱：61步` |
  | 剥掉 es（= 旧档口径） | 29~31 | 13~14 | **`已打乱：0步`** |
  → 症状一「不单连通」= 分量 1 → 14；症状二「无法打乱」= 打乱一步都走不动
  （缝枚举在这种碎盘上仍有 6~10 条，**冻形预检拦不住**，门过了却没效果）。
- **触发条件随之明确**：只有载入**修复前写下的旧档**才会中（之后每次保存都带
  engine_state）。这正好解释用户「仅遇到一次、条件未知」——那份 temp_history 是
  `engine_state` 落盘修复（2026-10-27）之前写下的，之后再也碰不到。
- 复现脚本：`archive/scratch_2026-10-28/_dbg_mi2c.py`（往返对比）、
  `_dbg_mi2d.py`（打乱症状）。护栏：`test/_test_model_legacy_save.py`（2.5s，全绿）。
  ⚠️ 旧 `_dbg_mi2b.py` 之前「跑不出结果」是**路径 bug**（脚本在 archive 子目录、
  `_PROJ` 算成两层），不是 48 块太慢——已修同款路径。
- **排掉的错路（别再走）**：米字档位（§九 前半段已排除）、「模型板不写
  engine_state」（快照带该字段）、「启动恢复路径与 `_load_save_data` 不同」
  （`load_last_state` 就是调它，无中间态）。

### 修法待定（要定的是「旧档怎么办」，不是要不要修）

现状是**静默损坏**：旧档载入后块默默少掉一半、打乱失效，玩家只看到怪盘面，
没有任何提示。三条路，代价不同，等拍板：

1. **提示（推荐）**：`_load_save_data` 里，若形态为模型板型且任一快照缺
   `engine_state` → 弹一条「这是旧版本写下的存档，无法完整还原，块可能缺失」，
   盘面照旧载入（不阻断，玩家至少知道发生了什么）。
2. **拒绝载入**：直接报错、保持当前局。信息最安全，但用户想翻的旧局就打不开了。
3. **不动**：现状。理由只能是「旧档已经绝迹」，但用户手里那份就还在。

⚠️ 别去「修好旧档」——信息在写入时就丢了（matrix 里同格多块不可区分），
恢复不出来；能做的只有**说清楚**。
"""


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')
    idx = None
    for i, ln in enumerate(lines):
        if MARKER in ln:
            idx = i
            break
    if idx is None:
        print('未找到标记行，未修改')
        return
    out = lines[:idx] + NEW.rstrip('\n').split('\n') + ['']
    with open(PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    print('已改写 §九：保留前 %d 行，新写 %d 行' % (idx, len(out) - idx))


if __name__ == '__main__':
    main()
