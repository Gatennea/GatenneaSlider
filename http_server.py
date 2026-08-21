# -*- coding: utf-8 -*-
"""
HTTP Server Mixin

提供本地 HTTP 接口，用于外部程序控制游戏。
通过命令队列与游戏主线程通信。
"""

import json
import queue
import threading
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler


class GameHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器，将请求转化为命令放入 cmd_queue"""

    # 由 start_http_server 设置
    cmd_queue = None

    def log_message(self, format, *args):
        """禁止 HTTP 日志刷屏"""
        pass

    def _send_json(self, data, status=200):
        """发送 JSON 响应"""
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _send_cors(self):
        """处理 CORS 预检"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _post_command(self, cmd_str):
        """将命令放入队列并等待结果"""
        resp_q = queue.Queue()
        self.cmd_queue.put((cmd_str, resp_q))
        try:
            result = resp_q.get(timeout=10)
            return result
        except queue.Empty:
            return {"ok": False, "message": "命令处理超时"}

    def _read_body(self):
        """读取请求 body 并解析为 JSON"""
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def do_OPTIONS(self):
        self._send_cors()

    def do_GET(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path.rstrip('/')
        try:
            self._dispatch_get(path)
        except Exception:
            # 非致命：控制台输出完整堆栈，HTTP 返回错误
            traceback.print_exc()
            try:
                self._send_json({"ok": False, "message": "服务器内部错误"}, 500)
            except Exception:
                pass

    def _dispatch_get(self, path):
        if path == '/status':
            result = self._post_command('status')
            self._send_json(result)
        elif path == '/map':
            result = self._post_command('map')
            if result is None:
                result = {"ok": False, "message": "未响应"}
            self._send_json(result)
        elif path == '/macro/list':
            result = self._post_command('macro_list')
            self._send_json(result if result else {"ok": False, "message": "未响应"})
        elif path == '/timer/status':
            result = self._post_command('timer_status')
            self._send_json(result if result else {"ok": False, "message": "未响应"})
        elif path == '/records':
            result = self._post_command('records')
            self._send_json(result if result else {"ok": False, "message": "未响应"})
        else:
            self._send_json({"ok": False, "message": f"未知 GET 路径: {path}"}, 404)

    def do_POST(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path.rstrip('/')
        body = self._read_body()
        try:
            self._dispatch_post(path, body)
        except Exception:
            # 非致命：控制台输出完整堆栈，HTTP 返回错误
            traceback.print_exc()
            try:
                self._send_json({"ok": False, "message": "服务器内部错误"}, 500)
            except Exception:
                pass

    def _dispatch_post(self, path, body):
        if path == '/command':
            cmd = body.get('cmd', '')
            if not cmd:
                self._send_json({"ok": False, "message": "缺少 cmd 字段"}, 400)
                return
            result = self._post_command(cmd)
            self._send_json(result)

        elif path == '/move':
            direction = body.get('direction', '')
            if direction not in ('w', 's', 'a', 'd'):
                self._send_json({"ok": False, "message": "direction 必须是 w/s/a/d"}, 400)
                return
            result = self._post_command(f'move {direction}')
            self._send_json(result)

        elif path == '/undo':
            result = self._post_command('undo')
            self._send_json(result if result else {"ok": False, "message": "未响应"})

        elif path == '/redo':
            result = self._post_command('redo')
            self._send_json(result if result else {"ok": False, "message": "未响应"})

        elif path == '/shuffle':
            result = self._post_command('shuffle')
            self._send_json(result)

        elif path == '/reset':
            result = self._post_command('reset')
            self._send_json(result)

        elif path == '/new':
            m = body.get('m')
            n = body.get('n')
            step = body.get('step')
            if m is None or n is None or step is None:
                self._send_json({"ok": False, "message": "需要 m, n, step 参数"}, 400)
                return
            result = self._post_command(f'new {m} {n} {step}')
            self._send_json(result)

        elif path == '/deselect':
            result = self._post_command('deselect')
            self._send_json(result)

        elif path == '/macro/list':
            result = self._post_command('macro_list')
            self._send_json(result if result else {"ok": False, "message": "未响应"})

        elif path == '/macro/record/start':
            result = self._post_command('macro_record_start')
            self._send_json(result)

        elif path == '/macro/record/set_base':
            row = body.get('row')
            col = body.get('col')
            if row is None or col is None:
                self._send_json({"ok": False, "message": "需要 row 和 col"}, 400)
                return
            result = self._post_command(f'macro_set_base {row} {col}')
            self._send_json(result)

        elif path == '/macro/record/stop':
            name = body.get('name', '')
            if not name:
                self._send_json({"ok": False, "message": "需要 name 字段"}, 400)
                return
            result = self._post_command(f'macro_record_stop {name}')
            self._send_json(result)

        elif path == '/macro/execute':
            name = body.get('name', '')
            base_row = body.get('base_row')
            base_col = body.get('base_col')
            if not name or base_row is None or base_col is None:
                self._send_json({"ok": False, "message": "需要 name, base_row, base_col"}, 400)
                return
            result = self._post_command(f'macro_execute {name} {base_row} {base_col}')
            self._send_json(result)

        elif path == '/macro/delete':
            name = body.get('name', '')
            if not name:
                self._send_json({"ok": False, "message": "需要 name 字段"}, 400)
                return
            result = self._post_command(f'macro_delete {name}')
            self._send_json(result)

        elif path == '/macro/rename':
            old_name = body.get('old_name', '')
            new_name = body.get('new_name', '')
            if not old_name or not new_name:
                self._send_json({"ok": False, "message": "需要 old_name 和 new_name"}, 400)
                return
            result = self._post_command(f'macro_rename {old_name} {new_name}')
            self._send_json(result)

        elif path == '/select_gap':
            gap_type = body.get('type', '')
            line = body.get('line')
            if gap_type not in ('h', 'v') or line is None:
                self._send_json({"ok": False, "message": "需要 type (h/v) 和 line"}, 400)
                return
            result = self._post_command(f'select_gap {gap_type} {line}')
            self._send_json(result)

        elif path == '/select_block':
            row = body.get('row')
            col = body.get('col')
            if row is None or col is None:
                self._send_json({"ok": False, "message": "需要 row 和 col"}, 400)
                return
            result = self._post_command(f'select_block {row} {col}')
            self._send_json(result)

        elif path == '/quit':
            result = self._post_command('quit')
            self._send_json(result)

        elif path == '/solve':
            result = self._post_command('solve')
            self._send_json(result)

        elif path == '/solve/status':
            result = self._post_command('solve_status')
            if result is None:
                result = {"ok": False, "message": "未响应"}
            self._send_json(result)

        elif path == '/timer/start':
            result = self._post_command('timer_start')
            self._send_json(result)

        elif path == '/timer/stop':
            result = self._post_command('timer_stop')
            self._send_json(result)

        elif path == '/timer/status':
            result = self._post_command('timer_status')
            self._send_json(result if result else {"ok": False, "message": "未响应"})

        elif path == '/records':
            result = self._post_command('records')
            self._send_json(result if result else {"ok": False, "message": "未响应"})

        else:
            self._send_json({"ok": False, "message": f"未知 POST 路径: {path}"}, 404)


def start_http_server(cmd_queue, port=5050):
    """
    启动 HTTP 服务器（daemon 线程）

    参数：
        cmd_queue: 命令队列，HTTP 请求会转化为 (cmd, resp_q) 元组放入
        port: 监听端口，默认 5050
    返回：
        HTTPServer 实例
    """
    GameHTTPHandler.cmd_queue = cmd_queue
    server = HTTPServer(('127.0.0.1', port), GameHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[HTTP] 服务已启动: http://127.0.0.1:{port}")
    print(f"[HTTP] 示例: curl http://127.0.0.1:{port}/status")
    return server