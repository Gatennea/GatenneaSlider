# -*- coding: utf-8 -*-
"""
滑块游戏程序入口

用法：
    python main.py                  # 使用默认参数 2~4*4, HTTP 端口 5050
    python main.py m n step         # 指定参数，如 python main.py 6 6 2
    python main.py m n step port    # 指定 HTTP 端口，如 python main.py 4 4 2 8080
    python main.py --no-http        # 禁用 HTTP 服务（仅终端交互）
    python main.py --http-port PORT # 指定 HTTP 端口
"""

import sys
import os
import traceback
from datetime import datetime


# ======== 日志系统（必须在任何可能失败的 import 之前安装）========

def _get_log_path():
    """获取日志文件路径，确保打包后也可写入"""
    try:
        base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, 'error_log.txt')
        with open(path, 'a', encoding='utf-8') as f:
            f.write('')
        return path
    except (OSError, PermissionError):
        import tempfile
        return os.path.join(tempfile.gettempdir(), 'gatenneaslider_error_log.txt')


def _log_error(msg: str):
    """写入错误日志"""
    try:
        log_path = _get_log_path()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f'[{timestamp}] {msg}\n')
    except Exception:
        pass


def _global_excepthook(exc_type, exc_value, exc_tb):
    """全局未捕获异常处理 —— 在 import 阶段就可用"""
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _log_error(f'未捕获异常:\n{tb_str}')
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args):
    """子线程未捕获异常处理 —— 记录到错误日志（线程异常默认不触发 sys.excepthook）"""
    tb_str = ''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    _log_error(f'线程异常 [{args.thread.name}]:\n{tb_str}')


# 必须在 import 之前安装，确保 import 阶段的异常也能记录
import threading
sys.excepthook = _global_excepthook
# 子线程（stdin/HTTP/求解器）异常也写入日志，避免静默失效
threading.excepthook = _thread_excepthook

# ======== 以下正常 import ========

import queue
from GUI import SliderGUI
from http_server import start_http_server


def stdin_reader(cmd_queue: queue.Queue):
    """后台线程：从 stdin 读取指令并放入队列"""
    try:
        for line in sys.stdin:
            line = line.strip()
            if line:
                cmd_queue.put(line)
    except (EOFError, OSError):
        pass


def parse_args():
    """解析命令行参数，返回 (m, n, step, http_port, enable_http)"""
    m, n, step = 4, 4, 2
    http_port = 5050
    enable_http = True

    args = sys.argv[1:]
    if '--no-http' in args:
        enable_http = False
        args.remove('--no-http')
    if '--http-port' in args:
        idx = args.index('--http-port')
        if idx + 1 < len(args):
            http_port = int(args[idx + 1])
            args.pop(idx)
            args.pop(idx)

    if len(args) == 1:
        try:
            http_port = int(args[0])
        except ValueError:
            print(f"参数错误: {args[0]}")
            sys.exit(1)
    elif len(args) == 3:
        try:
            m, n, step = int(args[0]), int(args[1]), int(args[2])
        except ValueError:
            print("参数错误，用法: python main.py m n step")
            sys.exit(1)
    elif len(args) == 4:
        try:
            m, n, step, http_port = int(args[0]), int(args[1]), int(args[2]), int(args[3])
        except ValueError:
            print("参数错误，用法: python main.py m n step port")
            sys.exit(1)
    elif len(args) > 0:
        print("用法: python main.py [m n step] [--http-port PORT] [--no-http]")
        sys.exit(1)

    return m, n, step, http_port, enable_http


if __name__ == "__main__":
    try:
        _log_error('===== 游戏启动 =====')
        m, n, step, http_port, enable_http = parse_args()

        # 创建命令队列
        cmd_queue = queue.Queue()

        # 启动 stdin 读取线程
        threading.Thread(target=stdin_reader, args=(cmd_queue,), daemon=True).start()

        # 启动 HTTP 服务
        http_server = None
        if enable_http:
            http_server = start_http_server(cmd_queue, http_port)

        gui = SliderGUI(m=m, n=n, step=step, cmd_queue=cmd_queue)
        gui.run()
    except Exception:
        _log_error(f'启动失败:\n{traceback.format_exc()}')
        raise
