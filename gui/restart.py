# -*- coding: utf-8 -*-
"""间接自举重启（游戏自己不能重启自己）。

设计：游戏要「重启」时，先 spawn 一个**独立（DETACHED）的看门进程**——
其实就是本程序以隐藏参数 ``--_restart_watch <pid> -- <relaunch>`` 启动；
看门进程等当前游戏进程（pid）彻底退出后，用相同的命令行重新拉起游戏。
游戏 spawn 完看门进程就可以正常退出了。

看门模式在 ``main.py`` 的 ``__main__`` 入口拦截，因此：
- 源码运行：``python main.py`` 既是游戏也是看门进程；
- 冻结成 exe：``GatenneaSlider.exe`` 同理，无需额外文件。

这与 ``gui/updater.py`` 的「独立进程等游戏退出再跑 .cmd」是同一思路，已验证可行。
"""
import os
import subprocess
import sys
import time

# CREATE_DETACHED_PROCESS：看门进程脱离父进程的控制台/进程组独立存活，
# 父进程（游戏）退出不会把它一起带走。
DETACHED = 0x00000008
# CREATE_NEW_CONSOLE：看门进程重拉起的游戏拥有自己的控制台窗口（源码运行时有用；
# 冻结成 windowed exe 时无控制台，标志无效但无害）。
NEW_CONSOLE = 0x00000010


def _is_frozen():
    """是否处于 PyInstaller 冻结环境。抽成可打桩的函数便于测试。"""
    return getattr(sys, 'frozen', False)


def _relaunch_args():
    """重新拉起自己所需的完整命令行。"""
    if _is_frozen():
        return list(sys.argv)
    return [sys.executable] + sys.argv


def _watcher_args(parent_pid):
    """看门进程的命令行：本程序以 --_restart_watch 模式启动，尾部带真正的 relaunch。"""
    relaunch = _relaunch_args()
    if _is_frozen():
        return [sys.executable, '--_restart_watch', str(parent_pid), '--'] + relaunch
    return [sys.executable, sys.argv[0], '--_restart_watch', str(parent_pid), '--'] + relaunch


def request_restart():
    """安排重启：spawn 看门进程（等自己退出后重启），调用方应随后退出游戏。

    重定向看门进程的 stdout/stderr 到 DEVNULL——DETACHED 进程没有控制台，
    任何输出都会失败；看门进程本身不打日志，无妨。
    """
    watcher = _watcher_args(os.getpid())
    subprocess.Popen(watcher, creationflags=DETACHED, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env=dict(os.environ))
    return True


def _wait_for_pid_exit(pid):
    """阻塞直到 pid 对应进程退出。Windows 用内核句柄等待；其他平台轮询兜底。"""
    if sys.platform == 'win32':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        h = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if h:
            try:
                kernel32.WaitForSingleObject(h, 0xFFFFFFFF)  # INFINITE
            finally:
                kernel32.CloseHandle(h)
        # h 为 0（进程已退出）→ 直接返回，立即重拉起
        return
    # POSIX 兜底（本项目主目标 Windows）
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.2)
