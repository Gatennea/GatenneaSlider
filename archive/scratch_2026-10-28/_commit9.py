# -*- coding: utf-8 -*-
"""提交本轮 §九 定位成果（本地 commit，不推送——按惯例等用户验收）。

只 add 本轮相关路径，不动工作区里前序 session 的其它改动。
"""
import os
import subprocess

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
GIT = 'F:/git/Git/cmd/git.exe'
out = []


def run(args):
    r = subprocess.run([GIT] + args, cwd=_PROJ, capture_output=True, text=True)
    out.append('$ git %s (rc=%s)' % (' '.join(args), r.returncode))
    out.append((r.stdout or '').strip() or '(empty)')
    if (r.stderr or '').strip():
        out.append('STDERR: ' + r.stderr.strip())
    out.append('')
    return r


run(['add', 'docs/agent/待办清单.md',
     'test/_test_model_legacy_save.py',
     'archive/scratch_2026-10-28/'])
run(['commit', '-m',
     'test+docs: §九（temp_history 导入 mi2 碎盘/无法打乱）定位为旧档缺 '
     'engine_state，加反向护栏'])
run(['log', '--oneline', '-3'])
run(['status', '--short'])

with open(os.path.join(_PROJ, 'archive', '_commit9.txt'), 'w',
          encoding='utf-8') as f:
    f.write('\n'.join(out))
