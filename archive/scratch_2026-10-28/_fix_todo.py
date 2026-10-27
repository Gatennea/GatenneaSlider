# -*- coding: utf-8 -*-
"""修清单两处遗留：§七 里对已删 §六 的引用编号 + §八 被拼坏的一行。"""
import io
import os
import re

_PROJ = os.path.dirname(os.path.abspath(__file__))
_P = os.path.join(_PROJ, 'docs', 'agent', '待办清单.md')

with io.open(_P, encoding='utf-8') as f:
    txt = f.read()

# 1) 「§一～§六」→「§一～§五」（§六 已完工删除，编号不再指代待办节）
txt2, n = re.subn(r'§一[～~]§六', '§一～§五', txt)

# 2) §八：上一轮替换把下一条 '- ' 拼到了同一行，拆回来
bad = '一起推。- 工作区已改完'
if bad in txt2:
    txt2 = txt2.replace(bad, '一起推。\n- 工作区已改完')

with io.open(_P, 'w', encoding='utf-8', newline='') as f:
    f.write(txt2)

with io.open(os.path.join(_PROJ, 'archive', '_fix_todo.txt'), 'w',
             encoding='utf-8') as f:
    f.write('renumber=%d  split_line=%s\n' % (n, bad in txt))
