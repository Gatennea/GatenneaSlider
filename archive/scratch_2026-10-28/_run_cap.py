# -*- coding: utf-8 -*-
"""跑 test/<mod>.<func>，把 stdout 一并落盘（沙箱吞 stdout，只能走文件）。

用法：python _run_cap.py <模块名> <函数名>
输出：archive/_cap_out.txt —— 含 FAIL / ok / 异常摘要
"""
import os
import subprocess
import sys

_PROJ = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_PROJ, 'archive', '_cap_out.txt')


def main():
    mod = sys.argv[1] if len(sys.argv) > 1 else '_test_model_editor'
    fn = sys.argv[2] if len(sys.argv) > 2 else 'main'
    tf = os.path.join(_PROJ, '_cap_tmp.py')
    with open(tf, 'w', encoding='utf-8') as f:
        f.write(
            "import os, sys\n"
            "os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')\n"
            "os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')\n"
            "sys.path.insert(0, %r)\n"
            "sys.path.insert(0, %r)\n"
            "os.chdir(%r)\n"
            "import %s as m\n"
            "m.%s()\n"
            "_f = getattr(m, 'FAILS', [])\n"
            "print('FAILS=%%d' %% len(_f))\n"
            "for _x in _f:\n"
            "    print('  FAILLIST:', _x)\n"
            "print('FUNC_OK %s.%s')\n"
            % (os.path.join(_PROJ, 'test'), _PROJ, _PROJ, mod, fn, mod, fn))
    tmp = os.path.join(_PROJ, '_cap_tmp_out.txt')
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            r = subprocess.run([sys.executable, tf], stdout=fh,
                               stderr=subprocess.STDOUT, timeout=180)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = 'TIMEOUT'
    try:
        body = open(tmp, encoding='utf-8', errors='replace').read()
    except OSError:
        body = ''
    lines = body.splitlines()
    keep = [l for l in lines
            if ('FAIL' in l or 'FUNC_OK' in l or 'Traceback' in l
                or l.strip().startswith('File ') or 'Error' in l
                or '共 ' in l or '全部通过' in l or 'ok:' in l)]
    out = ['rc=%s' % rc, '--- 关键行 ---'] + keep[-60:]
    if not keep:
        out.append('(无关键行) 末尾输出：')
        out.extend(lines[-30:])
    with open(_OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))


main()
