# -*- coding: utf-8 -*-
"""间接自举重启的单元自测（脚本型：python test/_test_restart.py）。

只验证 gui/restart.py 的「命令行拼装」与「等进程退出」兩块纯逻辑，
不拉起整个游戏。看门模式在 main.py __main__ 里接，逻辑同此模块。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gui import restart


def test_watcher_args_dev():
    saved = sys.argv[:]
    real = restart._is_frozen
    try:
        restart._is_frozen = lambda: False
        sys.argv = ['main.py', '6', '6', '2']
        rel = restart._relaunch_args()
        assert rel == [sys.executable, 'main.py', '6', '6', '2'], rel
        wat = restart._watcher_args(1234)
        assert wat[0] == sys.executable and wat[1] == 'main.py', wat
        assert wat[2:5] == ['--_restart_watch', '1234', '--'], wat
        assert wat[5:] == rel, wat
    finally:
        sys.argv = saved
        restart._is_frozen = real


def test_watcher_args_frozen():
    saved = sys.argv[:]
    real = restart._is_frozen
    try:
        restart._is_frozen = lambda: True
        sys.argv = ['GatenneaSlider.exe', '6', '6', '2']
        rel = restart._relaunch_args()
        assert rel == ['GatenneaSlider.exe', '6', '6', '2'], rel
        wat = restart._watcher_args(99)
        # 注意：测试在源码 python 下跑，sys.executable 仍是 python 而非 exe；
        # 冻结分支只决定「首段用 sys.executable 还是 sys.argv[0]」，这里验分支结构。
        assert wat == [sys.executable, '--_restart_watch', '99', '--',
                       'GatenneaSlider.exe', '6', '6', '2'], wat
    finally:
        sys.argv = saved
        restart._is_frozen = real


def test_wait_for_exit():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.4)'])
    t0 = time.time()
    restart._wait_for_pid_exit(child.pid)
    dt = time.time() - t0
    assert 0.3 < dt < 3.0, '等待耗时异常：%.2fs' % dt


def main():
    test_watcher_args_dev()
    test_watcher_args_frozen()
    test_wait_for_exit()
    print('ALL RESTART TESTS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
