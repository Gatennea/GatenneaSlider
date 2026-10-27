# -*- coding: utf-8 -*-
"""待办清单维护：删掉已完成的 §六（搭积木复制粘贴）+ 刷新 §八 发布状态。

清单规矩：做完即整节删，完成记录只在 git log 与日记。§六 的实现落在
46e8786，有依据了才删。按行号/特征定位（中文全角会让 Edit 匹配失败）。
"""
import io
import os

_PROJ = os.path.dirname(os.path.abspath(__file__))
_P = os.path.join(_PROJ, 'docs', 'agent', '待办清单.md')

with io.open(_P, encoding='utf-8') as f:
    lines = f.readlines()

# ---- 1) 删 §六（从 '## 六、' 到下一个 '## ' 之前）----
s6 = next(i for i, l in enumerate(lines) if l.startswith('## 六、'))
e6 = next(i for i, l in enumerate(lines) if i > s6 and l.startswith('## '))
del lines[s6:e6]

# ---- 2) §八 发布状态：领先数 4 → 5，补本次提交 ----
NEW8 = [
    '- 活跃分支 `main`；`ls-remote` 核过 `origin/main` == `8c9def6`，本地**领先 5 个\n'
    '  提交**：`c333b07`（菜单重设计）/ `7ed0ce6`（清单整理）/ `a9133f7`（样式\n'
    '  子菜单化）/ `3a8a983`（踩坑拆分）/ `46e8786`（搭积木 route A 续编 + 复制\n'
    '  粘贴阵列 + 「改当前盘面」同口径）—— **均未推送**，按惯例等用户验收后一起推。',
]
s8 = next(i for i, l in enumerate(lines) if l.startswith('## 八、'))
# 定位该节里的「领先」那几行（到下一个 '-' 条目或下一个 '## ' 为止）
j = s8
while j < len(lines) and '领先' not in lines[j]:
    j += 1
k = j
while k < len(lines) and not lines[k].startswith('## ') \
        and not (lines[k].startswith('- ') and k > j):
    k += 1
lines[j:k] = NEW8

with io.open(_P, 'w', encoding='utf-8', newline='') as f:
    f.writelines(lines)

with io.open(os.path.join(_PROJ, 'archive', '_splice_todo.txt'), 'w',
             encoding='utf-8') as f:
    f.write('deleted §6 lines %d..%d\nrewrote §8 lines %d..%d\n'
            % (s6 + 1, e6, j + 1, k))
