# -*- coding: utf-8 -*-
"""逐个独立子进程跑 test/_test_model_editor.py 的 t_* 函数，结果落盘。

沙箱里「一个进程连跑多个 t_*」会因 pygame 状态累积偶发卡死，逐个起进程最稳。
"""
import os
import re
import subprocess
import sys

_PROJ = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_PROJ, 'archive', '_rbatch3.txt')
_SRC = os.path.join(_PROJ, 'test', '_test_model_editor.py')

NAMES = sys.argv[1:] or [
    't_open_model', 't_open_shatter_route_a', 't_save_roundtrip_route_a',
    't_gate', 't_lattice_switch', 't_save_hot_reload',
    't_square_lattice_save_open', 't_build_doc_loadable',
    't_copy_paste_array', 't_rotate_mirror', 't_orient_lock', 't_undo_redo',
    't_right_click_delete', 't_bundle_toggle', 't_place', 't_drag_move_block',
]

_code = """import os, sys
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, r'{test}')
sys.path.insert(0, r'{proj}')
os.chdir(r'{proj}')
import _test_model_editor as m
m.{name}()
print('FUNC_OK {name}')
""".format(test=os.path.join(_PROJ, 'test'), proj=_PROJ, name='{name}')

out = []
for name in NAMES:
    code = _code.format(name=name)
    tf = os.path.join(_PROJ, '_one_tmp.py')
    with open(tf, 'w', encoding='utf-8') as f:
        f.write(code)
    tmp = os.path.join(_PROJ, '_one_tmp_out.txt')
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            r = subprocess.run([sys.executable, tf], stdout=fh,
                               stderr=subprocess.STDOUT, timeout=120)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = 'TIMEOUT'
    try:
        body = open(tmp, encoding='utf-8', errors='replace').read()
    except OSError:
        body = ''
    tail = [l for l in body.splitlines()
            if ('FUNC_OK' in l or 'FAIL' in l or 'Error' in l
                or 'Traceback' in l or 'assert' in l)]
    out.append('=== %s === rc=%s' % (name, rc))
    out.append('\n'.join(tail[-12:]) if tail else body[-800:])
    out.append('')
    # 每个都 flush，便于中途查看
    with open(_OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out) + '\nALLDONE')
