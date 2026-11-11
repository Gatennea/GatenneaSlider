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
import secrets
import tempfile

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


def _watcher_args(parent_pid, token):
    """看门进程的命令行：本程序以 --_restart_watch 模式启动，并带 --_restart_token；
    尾部 -- 之后是真正的 relaunch（新游戏命令）。token 用于新旧进程间的就绪哨兵。
    """
    relaunch = _relaunch_args()
    if _is_frozen():
        return [sys.executable, '--_restart_watch', str(parent_pid),
                '--_restart_token', token, '--'] + relaunch
    return [sys.executable, sys.argv[0], '--_restart_watch', str(parent_pid),
            '--_restart_token', token, '--'] + relaunch


def request_restart():
    """安排重启：spawn 看门进程（等自己退出后重启），调用方应随后退出游戏。

    看门进程（gui.restart_manager）会显示一段「重启中」动画窗口覆盖空窗期，
    旧进程退出后再重拉起游戏（带 --_restarted <token> 跳过冷启动开机封面），
    待游戏就绪后淡出。stdout/stderr 重定向到 DEVNULL——DETACHED 进程无控制台。
    """
    token = _gen_token()
    watcher = _watcher_args(os.getpid(), token)
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


# ---- 重启器可视动画的辅助（与 gui/restart_manager.py 共用） ----

# 就绪哨兵文件名前缀：新游戏首帧绘出后写此文件，看门进程据此淡出
READY_PREFIX = 'gatennea_restart_ready_'


def _gen_token():
    """生成一次性令牌，用于就绪哨兵文件命名，避免多次重启互相干扰。"""
    try:
        return secrets.token_hex(4)
    except Exception:
        return f"{os.getpid()}{int(time.time() * 1000)}"


def ready_path(token):
    """就绪哨兵文件路径。"""
    return os.path.join(tempfile.gettempdir(), READY_PREFIX + (token or ''))


def write_ready(token):
    """写就绪哨兵（幂等，重复调用无害）。"""
    if not token:
        return
    try:
        with open(ready_path(token), 'w', encoding='utf-8') as f:
            f.write('1')
    except Exception:
        pass


def clear_ready(token):
    """清理就绪哨兵。"""
    try:
        os.remove(ready_path(token))
    except Exception:
        pass


def pid_alive(pid):
    """非阻塞判断进程是否仍存活。Windows 用 ExitCode，其他平台轮询。"""
    if sys.platform == 'win32':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED = 0x1000
        h = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == 0x103  # STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
