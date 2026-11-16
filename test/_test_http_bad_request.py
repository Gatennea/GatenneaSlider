# -*- coding: utf-8 -*-
"""护栏：HTTP POST 请求体解析边界（2026-11-16）。

真 HTTP server + 裸 socket 驱动真实入口，不查源码。畸形 Content-Length
必须回 400 而不是连接重置 / 挂住线程；合法 JSON 但顶层非对象必须回 400
而不是 500，且与 /settings 口径一致；合法 dict 与空 body 的业务路径不变。

执行：D:/python/python.exe -u test/_test_http_bad_request.py
"""
import json
import os
import queue
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from http_server import start_http_server                 # noqa: E402

PORT = 5099
TOKEN = 'guard-token'
_failures = []


def check(name, cond, extra=''):
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        _failures.append(name)
    return bool(cond)


def request(path, length, body=b'', token=TOKEN, timeout=2.5):
    """裸 socket 发一条 POST；urllib 会自动补合法 Content-Length，测不了这些边界。"""
    req = (
        'POST %s HTTP/1.1\r\n'
        'Host: 127.0.0.1\r\n'
        'Authorization: Bearer %s\r\n'
        'Content-Type: application/json\r\n'
        'Content-Length: %s\r\n'
        'Connection: close\r\n\r\n'
        % (path, token, length)
    ).encode('ascii') + body
    s = socket.create_connection(('127.0.0.1', PORT), timeout=timeout)
    s.settimeout(timeout)
    try:
        s.sendall(req)
        chunks = []
        timed_out = False
        while True:
            try:
                b = s.recv(4096)
            except socket.timeout:
                timed_out = True
                break
            if not b:
                break
            chunks.append(b)
        raw = b''.join(chunks).decode('utf-8', 'replace')
    finally:
        s.close()
    if timed_out or not raw:
        return None, None, timed_out
    head, _, payload = raw.partition('\r\n\r\n')
    parts = head.split(' ')
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        data = None
    return status, data, False


def is_bad_length(status, data, timed_out):
    return (status == 400 and not timed_out and isinstance(data, dict)
            and data.get('ok') is False
            and 'Content-Length' in str(data.get('message')))


def is_bad_body(status, data, timed_out):
    return (status == 400 and not timed_out and isinstance(data, dict)
            and data.get('ok') is False
            and 'JSON 对象' in str(data.get('message')))


srv = start_http_server(queue.Queue(), port=PORT,
                        ext_state={'enabled': True, 'token': TOKEN})
try:
    # A 畸形 Content-Length：原先 _read_body 在 do_POST 的 try 之外，
    # int() 抛 ValueError 冒泡到 socketserver → 连接重置、无任何响应。
    for name, length in (('A1 非整数', 'abc'), ('A2 小数', '1.5')):
        st, data, to = request('/move', length)
        check('%s Content-Length 回明确 400' % name,
              is_bad_length(st, data, to), 'status=%s to=%s' % (st, to))

    # 负数曾被 int() 接受，rfile.read(-1) 读到 EOF 才返回，挂住请求线程。
    st, data, to = request('/move', '-1', b'[]')
    check('A3 负数 Content-Length 不挂线程且回 400',
          is_bad_length(st, data, to), 'status=%s to=%s' % (st, to))

    # B 合法 JSON 但顶层不是对象：原先多数端点 body.get 抛 AttributeError → 500，
    # 同一服务的 /settings 却回 400，错误口径自相矛盾。
    for name, body in (('B1 数组', b'[]'), ('B2 null', b'null'),
                       ('B3 字符串', b'"foo"'), ('B4 数字', b'123')):
        st, data, to = request('/move', str(len(body)), body)
        check('%s body 回 400 而非 500' % name,
              is_bad_body(st, data, to), 'status=%s' % st)

    st, data, to = request('/move', '2', b'\xff\xfe')
    check('B5 非法 UTF-8 回 400 且说明原因',
          st == 400 and not to and isinstance(data, dict)
          and '合法 JSON' in str(data.get('message')),
          'status=%s msg=%s' % (st, (data or {}).get('message')))

    st, data, to = request('/move', '4', b'{bad')
    check('B6 非法 JSON 回 400 且说明原因',
          st == 400 and not to and isinstance(data, dict)
          and '合法 JSON' in str(data.get('message')),
          'status=%s msg=%s' % (st, (data or {}).get('message')))

    # C 业务路径不变：空 body 仍按 {} 解析，合法 dict 仍走原校验。
    st, data, to = request('/move', '0')
    check('C1 空 body 仍按 {} 处理（不是畸形）',
          st == 400 and not to and isinstance(data, dict)
          and 'direction' in str(data.get('message')),
          'status=%s msg=%s' % (st, (data or {}).get('message')))
    st, data, to = request('/move', '2', b'{}')
    check('C2 合法 dict body 仍走原 direction 校验',
          st == 400 and not to and isinstance(data, dict)
          and 'direction' in str(data.get('message')),
          'status=%s msg=%s' % (st, (data or {}).get('message')))

    # D 鉴权先于解析：畸形 body 也不该绕过令牌闸门。
    st, data, to = request('/move', '2', b'[]', token='wrong-token')
    check('D1 畸形 body 无有效令牌仍回 401',
          st == 401 and not to, 'status=%s' % st)

    # E 跨端点一致：/settings 原本就回 400，/move 不得继续回 500。
    st1, d1, _ = request('/settings', '2', b'[]')
    st2, d2, _ = request('/move', '2', b'[]')
    check('E1 /settings 与 /move 对非 dict body 口径一致',
          st1 == st2 == 400, 'settings=%s move=%s' % (st1, st2))
finally:
    srv.shutdown()
    srv.server_close()

print('==== %s（%d 项失败）' % ('全部通过' if not _failures else '有失败',
                            len(_failures)))
sys.exit(1 if _failures else 0)
