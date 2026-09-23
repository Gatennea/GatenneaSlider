# -*- coding: utf-8 -*-
"""
滑块游戏程序入口

用法：
    python main.py                  # 使用默认参数 2~4*4, HTTP 端口 5050
    python main.py m n step         # 指定参数，如 python main.py 6 6 2
    python main.py m n step port    # 指定 HTTP 端口，如 python main.py 4 4 2 8080
    python main.py m n step tri     # 正三角形密铺谜题（m 作大三角边长 k），如 python main.py 6 6 1 tri
    python main.py m n step num     # 带序号谜题
    python main.py --no-http        # 禁用 HTTP 服务（仅终端交互）
    python main.py --http-port PORT # 指定 HTTP 端口
"""

import sys


# ======== 日志系统（必须在任何可能失败的 import 之前安装）========

# 日志实现在 gui/log_writer.py（与 GUI 侧共用一份，不再各抄一份）。只依赖
# 标准库，import 它不会比 import 别的东西更容易失败；万一它自己坏了，退回
# stderr，excepthook 照样装得上——总比连异常都记不下来强。
try:
    from gui.log_writer import write as _write_log, exception as _write_exception
except Exception:      # pragma: no cover - 仅在打包损坏/源码缺失时发生
    def _write_log(msg, level='error', trace=None):
        try:
            print(f'[{level}] {msg}', file=sys.stderr)
        except Exception:
            pass

    def _write_exception(msg, exc_type, exc_value, exc_tb):
        try:
            print(f'[error] {msg}: {exc_value}', file=sys.stderr)
        except Exception:
            pass


def _log_error(msg: str, level: str = 'error'):
    """写一条运行日志（config/error_log.jsonl）"""
    _write_log(msg, level=level)


def _global_excepthook(exc_type, exc_value, exc_tb):
    """全局未捕获异常处理 —— 在 import 阶段就可用"""
    _write_exception('未捕获异常', exc_type, exc_value, exc_tb)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args):
    """子线程未捕获异常处理 —— 记录到错误日志（线程异常默认不触发 sys.excepthook）"""
    _write_exception(f'线程异常 [{args.thread.name}]',
                     args.exc_type, args.exc_value, args.exc_traceback)


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
        # PyInstaller --windowed 无控制台打包时 sys.stdin 为 None
        if sys.stdin is None:
            return
        for line in sys.stdin:
            line = line.strip()
            if line:
                cmd_queue.put(line)
    except (EOFError, OSError, TypeError):
        pass


def parse_args():
    """解析命令行参数，返回 (m, n, step, http_port, enable_http, kind)

    kind: 'square' | 'numbered' | 'triangle' | 'mi'（第 4 个参数为 tri/num/mi 时生效）
    """
    m, n, step = 4, 4, 2
    http_port = 5050
    enable_http = True
    kind = 'square'

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
            m, n, step = int(args[0]), int(args[1]), int(args[2])
        except ValueError:
            print("参数错误，用法: python main.py m n step [port|tri|num|mi]")
            sys.exit(1)
        forth = args[3].lower()
        if forth in ('tri', 'triangle'):
            kind = 'triangle'
        elif forth in ('mi', 'mizige'):
            kind = 'mi'
        elif forth in ('num', 'numbered'):
            kind = 'numbered'
        else:
            try:
                http_port = int(forth)
            except ValueError:
                print(f"参数错误: {args[3]}（第 4 个参数应为端口数字或 tri/num/mi）")
                sys.exit(1)
    elif len(args) > 0:
        print("用法: python main.py [m n step [port|tri|num|mi]] [--http-port PORT] [--no-http]")
        sys.exit(1)

    return m, n, step, http_port, enable_http, kind


if __name__ == '__main__':
    try:
        _log_error('===== 游戏启动 =====', level='info')
        m, n, step, http_port, enable_http, kind = parse_args()

        # 创建命令队列
        cmd_queue = queue.Queue()

        # 启动 stdin 读取线程
        threading.Thread(target=stdin_reader, args=(cmd_queue,), daemon=True).start()

        # 启动 HTTP 服务
        http_server = None
        if enable_http:
            http_server = start_http_server(cmd_queue, http_port)

        gui = SliderGUI(m=m, n=n, step=step, cmd_queue=cmd_queue, kind=kind)
        gui.run()
    except Exception:
        _write_exception('启动失败', *sys.exc_info())
        raise
