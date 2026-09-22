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

    # settings 白名单（须与 gui/events.py EventsMixin._SETTINGS_* 保持一致）
    _SETTINGS_BOOL_KEYS = (
        'coloring_enabled', 'chain_hint_enabled', 'show_metrics_panel',
        'animation_enabled', 'selection_animation_enabled',
        'control_single_touch', 'control_two_touch', 'control_mouse_kb',
        'macro_reverse_mode', 'save_readonly_flag', 'prevent_overwrite_flag',
    )
    _SETTINGS_INT_RANGES = {'animation_duration_ms': (50, 1000)}
    # gather 参数白名单（须与 GUI.py gather_params 键一致）
    _SOLVER_PARAM_KEYS = (
        'max_steps', 'patience', 'max_wait_time',
        'target_gather_score', 'aggressiveness',
    )

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

    def _send_analysis(self, result):
        """局面分析响应：游戏侧对未实现形态回 reason=unsupported → 400。

        方形谜题保持 200；这样调用方无需解析 message 就能从状态码区分
        「该形态不支持」与「分析结果为空」。
        """
        status = 400 if (isinstance(result, dict)
                         and not result.get('ok', True)
                         and result.get('reason') == 'unsupported') else 200
        self._send_json(result, status)

    def _post_command(self, cmd_str, payload=None):
        """将命令放入队列并等待结果

        payload 为 None 时放二元组 (cmd, resp_q)；为 dict 时放三元组
        (cmd, resp_q, payload)，供富 JSON body（多行地图/设置等）通道使用。
        """
        resp_q = queue.Queue()
        if payload is None:
            self.cmd_queue.put((cmd_str, resp_q))
        else:
            self.cmd_queue.put((cmd_str, resp_q, payload))
        try:
            result = resp_q.get(timeout=30)
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
        # —— 局面分析 ——
        # 三角形密铺的洞/窗口/动作语义未实现：游戏侧回 reason=unsupported，
        # _send_analysis 映射为 400，让调用方能从状态码看出「该形态不支持」
        if path == '/analysis/window':
            self._send_analysis(self._post_command('window'))
        elif path == '/analysis/holes':
            self._send_analysis(self._post_command('holes'))
        elif path == '/analysis/actions':
            self._send_analysis(self._post_command('actions'))
        # —— 求解器 ——
        elif path == '/solver/algorithms':
            self._send_json(self._post_command('solver_algorithms'))
        elif path == '/solver/status':
            self._send_json(self._post_command('solver_status'))
        elif path == '/solver/params':
            self._send_json(self._post_command('solver_params'))
        # —— 宏 / 模式 / 设置 ——
        elif path == '/macro/status':
            self._send_json(self._post_command('macro_status'))
        elif path == '/mode':
            self._send_json(self._post_command('mode'))
        elif path == '/settings':
            self._send_json(self._post_command('settings'))
        # —— 既有端点（保留） ——
        elif path == '/status':
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
            # 方形 w/s/a/d；三角形密铺另加 e/z/x（wedxza 六向）；米字格八向
            # 再加 q（q/w/e/a/d/z/s/x）。合法性与「该方向是否平行于选中缝隙」
            # 由游戏侧判定，这里只挡明显非法的字母
            if direction not in ('w', 's', 'a', 'd', 'e', 'z', 'x', 'q'):
                self._send_json(
                    {"ok": False,
                     "message": "direction 必须是 w/s/a/d（三角形另加 e/z/x，米字格另加 q）"}, 400)
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
            # type 可选：square（默认）/ numbered / triangle / mi。
            # 三角形用 m 作大三角边长 k，n 仍须给出（ CLI 同款签名 new m n step tri ）；
            # 米字格 m 行 n 列，每格 4 个单元三角
            kind = body.get('type', 'square')
            if kind not in ('square', 'numbered', 'triangle', 'mi'):
                self._send_json(
                    {"ok": False, "message": "type 必须是 square/numbered/triangle/mi"}, 400)
                return
            suffix = {'numbered': 'num', 'triangle': 'tri',
                      'mi': 'mi'}.get(kind, '')
            cmd = f'new {m} {n} {step}' + (f' {suffix}' if suffix else '')
            result = self._post_command(cmd)
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
            # reverse 可选（默认 false）；经富 payload 通道传递
            result = self._post_command('macro_execute', body)
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
            # 方形 h/v；三角形密铺另加 p/n（3 族缝隙）；米字格是 d1/d2
            # （两条对角缝族）。线号合法性由游戏侧判定
            if gap_type not in ('h', 'v', 'p', 'n', 'd1', 'd2') or line is None:
                self._send_json(
                    {"ok": False,
                     "message": "需要 type (h/v，三角形另加 p/n，米字格另加 d1/d2) 和 line"}, 400)
                return
            result = self._post_command(f'select_gap {gap_type} {line}')
            self._send_json(result)

        elif path == '/select_block':
            row = body.get('row')
            col = body.get('col')
            if row is None or col is None:
                self._send_json({"ok": False, "message": "需要 row 和 col"}, 400)
                return
            cmd = f'select_block {row} {col}'
            # q 只对米字格有意义（N/E/S/W：斜边朝向哪条格边）；给了就转发，
            # 省略时游戏侧退回该格第一块
            q = body.get('q')
            if q:
                cmd += f' {q}'
            result = self._post_command(cmd)
            self._send_json(result)

        elif path == '/quit':
            result = self._post_command('quit')
            self._send_json(result)

        elif path == '/solve' or path == '/solver/solve':
            # 可选 {"algorithm": "<key>"}；运行中调用 = 取消
            algorithm = body.get('algorithm')
            if algorithm is not None:
                from solver import SOLVER_ALGORITHMS
                if algorithm not in SOLVER_ALGORITHMS:
                    self._send_json(
                        {"ok": False,
                         "message": f"未知算法: {algorithm}（可选: {', '.join(SOLVER_ALGORITHMS)}）"},
                        400)
                    return
            result = self._post_command('solve', body if isinstance(body, dict) else {})
            self._send_json(result)

        elif path == '/solver/cancel':
            result = self._post_command('solve_cancel')
            self._send_json(result)

        elif path == '/solve/status':
            result = self._post_command('solve_status')
            if result is None:
                result = {"ok": False, "message": "未响应"}
            self._send_json(result)

        elif path == '/solver/params':
            if not isinstance(body, dict) or not body:
                self._send_json({"ok": False, "message": "需要参数键值对"}, 400)
                return
            allowed = set(self._SOLVER_PARAM_KEYS) | {f'{k}_enabled' for k in self._SOLVER_PARAM_KEYS}
            bad = [k for k in body if k not in allowed]
            if bad:
                self._send_json({"ok": False, "message": f"未知参数: {', '.join(bad)}"}, 400)
                return
            result = self._post_command('solver_params', body)
            self._send_json(result)

        elif path == '/map/load':
            map_str = body.get('map')
            if not isinstance(map_str, str) or not map_str.strip():
                self._send_json({"ok": False, "message": "需要 map 字段（#/_ 地图字符串）"}, 400)
                return
            result = self._post_command('load_map', body)
            self._send_json(result)

        elif path == '/file/save':
            if not body.get('path'):
                self._send_json({"ok": False, "message": "需要 path 字段"}, 400)
                return
            result = self._post_command('save_file', body)
            self._send_json(result)

        elif path == '/file/load':
            if not body.get('path'):
                self._send_json({"ok": False, "message": "需要 path 字段"}, 400)
                return
            result = self._post_command('load_file', body)
            self._send_json(result)

        elif path == '/mode':
            mode = body.get('mode', '')
            if mode not in ('practice', 'timed'):
                self._send_json({"ok": False, "message": "mode 必须是 practice 或 timed"}, 400)
                return
            result = self._post_command('mode', body)
            self._send_json(result)

        elif path == '/settings':
            if not isinstance(body, dict) or not body:
                self._send_json({"ok": False, "message": "需要设置键值对"}, 400)
                return
            allowed = set(self._SETTINGS_BOOL_KEYS) | set(self._SETTINGS_INT_RANGES)
            bad = [k for k in body if k not in allowed]
            if bad:
                self._send_json({"ok": False, "message": f"未知设置键: {', '.join(bad)}"}, 400)
                return
            for k in self._SETTINGS_BOOL_KEYS:
                if k in body and not isinstance(body[k], bool):
                    self._send_json({"ok": False, "message": f"{k} 必须是 true/false"}, 400)
                    return
            for k, (lo, hi) in self._SETTINGS_INT_RANGES.items():
                if k in body:
                    v = body[k]
                    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
                        self._send_json({"ok": False, "message": f"{k} 必须是 {lo}–{hi} 的整数"}, 400)
                        return
            result = self._post_command('settings', body)
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