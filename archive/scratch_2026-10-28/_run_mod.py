"""通用测试 runner：import test/<mod> 并调用指定函数（默认 main）。

沙箱吞子进程 stdout，所以结果一律由本进程 open().write() 落盘。
用法：python _run_mod.py <模块名> [函数名]
输出：<项目根>/archive/_mod_<模块名>.txt
"""
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))   # scratch/archive -> 项目根
_MOD = sys.argv[1] if len(sys.argv) > 1 else 'main'
_OUT = os.path.join(_ROOT, 'archive', '_mod_%s.txt' % _MOD)


def main():
    mod = sys.argv[1] if len(sys.argv) > 1 else '_test_model_modes'
    fn = sys.argv[2] if len(sys.argv) > 2 else 'main'
    out = []
    sys.path.insert(0, os.path.join(_ROOT, 'test'))
    sys.path.insert(0, _ROOT)
    try:
        m = __import__(mod)
        f = getattr(m, fn)
        f()
        out.append('FUNC_OK %s.%s' % (mod, fn))
    except SystemExit as e:
        code = e.code or 0
        out.append('SYSTEM_EXIT code=%s' % code)
        if code not in (0, None):
            out.append(traceback.format_exc())
    except Exception:
        out.append('FUNC_FAIL')
        out.append(traceback.format_exc())
    with open(_OUT, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out))


main()
