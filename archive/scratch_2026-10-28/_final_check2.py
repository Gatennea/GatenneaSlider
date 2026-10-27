# -*- coding: utf-8 -*-
"""最终检查：跑三个关键子测试，各起独立进程，结果写文件。"""
import os
import subprocess
import sys

_PROJECT = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_PROJECT, 'archive', '_final_run_v2.txt')

NAMES = ['t_copy_paste_array', 't_right_click_delete', 't_bundle_toggle',
         't_open_shatter_route_a', 't_save_roundtrip_route_a']

CODE = """# -*- coding: utf-8 -*-
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, {proj!r})
sys.path.insert(0, {test!r})
import _test_model_editor as m
m.{name}()
print('FUNC_OK')
"""

lines = []
for name in NAMES:
    code = CODE.format(proj=_PROJECT, test=os.path.join(_PROJECT, 'test'), name=name)
    p = os.path.join(_PROJECT, '_fc_code.py')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(code)
    r = subprocess.run([sys.executable, p], capture_output=True, cwd=_PROJECT)
    out = (r.stdout + r.stderr).decode('utf-8', 'replace')
    tail = [ln for ln in out.splitlines() if ln.strip()][-6:]
    lines.append('=== %s === RC=%s' % (name, r.returncode))
    lines.extend('    ' + t for t in tail)
    lines.append('')

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
