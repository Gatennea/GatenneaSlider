# -*- coding: utf-8 -*-
"""取 git status / log（沙箱里 PowerShell 捕不到外部进程 stdout，绕一下）。"""
import os
import subprocess

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
GIT = 'F:/git/Git/cmd/git.exe'
out = []
for args in (['status', '--short'], ['log', '--oneline', '-8'],
             ['branch', '--show-current']):
    r = subprocess.run([GIT] + args, cwd=_PROJ, capture_output=True, text=True)
    out.append('$ git %s  (rc=%s)' % (' '.join(args), r.returncode))
    out.append(r.stdout.rstrip() or '(empty)')
    if r.stderr.strip():
        out.append('STDERR: ' + r.stderr.strip())
    out.append('')

with open(os.path.join(_PROJ, 'archive', '_git_probe.txt'), 'w',
          encoding='utf-8') as f:
    f.write('\n'.join(out))
