# -*- coding: utf-8 -*-
"""HTTP 截图 API 无头端到端测试。

覆盖：
  AC-1  GET  /screenshot            自动命名存到 <base_dir>/screenshots/，回 ok/path/width/height
  AC-2  GET  /screenshot?path=...   指定目标路径
  AC-3  POST /screenshot {"path":..} 指定目标路径
  AC-4  POST /screenshot {}         空 body 走自动命名
  AC-5  落盘文件是合法 PNG（魔数 + 非空）
  AC-6  CLI 通道 screenshot <路径>  与 HTTP 同源

机制同 _test_http_api.py：HTTP 在后台线程收请求并阻塞等待 resp_q；
主线程（本测试）循环调用 gui.process_commands() 排空队列。
"""
import os, sys, time, json, queue, threading, struct, tempfile, shutil
import urllib.request, urllib.error

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from GUI import SliderGUI
from http_server import start_http_server

PORT = 5098
_failures = []
_created = []          # 测试中创建的截图文件，结束前清理


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


def _is_png(path):
    """合法 PNG：8 字节魔数 + IHDR 宽高与声称值一致 + 文件非空。"""
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return False, 0, 0
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return False, 0, 0
    w, h = struct.unpack('>II', data[16:24])
    return True, w, h


# ---------------------------------------------------------------- 基础设施
# 外部控制鉴权（2026-10-13 起）：测试与游戏共享同一 ext_state，请求带令牌。
ext_state = {'enabled': True, 'token': 'SHOTTOKEN123456', 'port': PORT}
cmd_queue = queue.Queue()
server = start_http_server(cmd_queue, PORT, ext_state)
gui = SliderGUI(m=4, n=4, step=2, cmd_queue=cmd_queue, ext_state=ext_state)
gui.game_mode = 'practice'


def _raw_request(method, path, body=None):
    url = f'http://127.0.0.1:{PORT}{path}'
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', 'Bearer SHOTTOKEN123456')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def api(method, path, body=None, timeout=15):
    """发 HTTP 请求，同时主线程排空命令队列（否则请求线程会永远阻塞）。"""
    box = {}

    def worker():
        try:
            box['result'] = _raw_request(method, path, body)
        except Exception as e:
            box['error'] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t0 = time.time()
    while t.is_alive() and time.time() - t0 < timeout:
        gui.process_commands()
        t.join(0.02)
    if t.is_alive():
        raise RuntimeError(f"请求超时: {method} {path}")
    if 'error' in box:
        raise box['error']
    return box['result']


def cleanup():
    for p in _created:
        try:
            os.remove(p)
        except OSError:
            pass
    # 自动命名目录只删测试产生的文件（目录本身保留无妨，删掉更干净）
    shot_dir = os.path.join(gui.base_dir, 'screenshots')
    if os.path.isdir(shot_dir):
        try:
            shutil.rmtree(shot_dir)
        except OSError:
            pass


# ---------------------------------------------------------------- 测试
screen_w, screen_h = gui.screen.get_width(), gui.screen.get_height()

# AC-1：GET 自动命名
status, r = api('GET', '/screenshot')
check('AC-1 GET /screenshot ok', status == 200 and r.get('ok') is True, r)
auto_path = r.get('path', '')
_created.append(auto_path)
check('AC-1 路径在 screenshots/ 下',
      auto_path.startswith(os.path.join(gui.base_dir, 'screenshots')), auto_path)
ok_png, w, h = _is_png(auto_path)
check('AC-1 落盘为合法 PNG', ok_png, auto_path)
check('AC-1 宽高与屏幕一致', (w, h) == (screen_w, screen_h), f'{(w, h)} vs {(screen_w, screen_h)}')
check('AC-1 响应宽高一致', (r.get('width'), r.get('height')) == (screen_w, screen_h))

# AC-2：GET 指定路径
tmpdir = tempfile.mkdtemp(prefix='gatsli_shot_')
target2 = os.path.join(tmpdir, 'get_named.png')
status, r = api('GET', f'/screenshot?path={urllib.request.quote(target2)}')
check('AC-2 GET ?path= ok', status == 200 and r.get('ok') is True, r)
_created.append(target2)
check('AC-2 文件存在于指定路径', os.path.isfile(target2), target2)
ok_png, w, h = _is_png(target2)
check('AC-2 为合法 PNG', ok_png and (w, h) == (screen_w, screen_h))

# AC-3：POST 指定路径
target3 = os.path.join(tmpdir, 'post_named.png')
status, r = api('POST', '/screenshot', {'path': target3})
check('AC-3 POST {path} ok', status == 200 and r.get('ok') is True, r)
_created.append(target3)
check('AC-3 文件存在于指定路径', os.path.isfile(target3), target3)

# AC-4：POST 空 body 自动命名
status, r = api('POST', '/screenshot', {})
check('AC-4 POST {} ok', status == 200 and r.get('ok') is True, r)
if r.get('ok'):
    _created.append(r.get('path', ''))
    check('AC-4 自动命名落盘', os.path.isfile(r.get('path', '')), r.get('path'))

# AC-5：连续两张内容不同（第二张在第一张之后生成，时间戳命名不覆盖）
status, r2 = api('GET', '/screenshot')
if r2.get('ok'):
    _created.append(r2.get('path', ''))
    check('AC-5 连续截图不互相覆盖', r2.get('path') != auto_path,
          f'{r2.get("path")} vs {auto_path}')

# AC-6：CLI 通道（字符串命令，无 resp_q 时打印到终端）
target6 = os.path.join(tmpdir, 'cli_named.png')
resp_q6 = queue.Queue()
cmd_queue.put((f'screenshot {target6}', resp_q6))
t0 = time.time()
while resp_q6.empty() and time.time() - t0 < 5:
    gui.process_commands()
    time.sleep(0.01)
r6 = resp_q6.get() if not resp_q6.empty() else {}
_created.append(target6)
check('AC-6 CLI screenshot 落盘', os.path.isfile(target6), r6)
check('AC-6 CLI 回 ok', r6.get('ok') is True, r6)

# AC-7：坏路径（目标父路径是文件）→ ok:false 且不崩
bad_target = os.path.join(tmpdir, 'get_named.png', 'sub.png')   # 父级是文件
status, r = api('GET', f'/screenshot?path={urllib.request.quote(bad_target)}')
check('AC-7 坏路径回 ok:false', status == 200 and r.get('ok') is False, r)

cleanup()
shutil.rmtree(tmpdir, ignore_errors=True)

print()
if _failures:
    print(f"共 {len(_failures)} 项失败: {_failures}")
    sys.exit(1)
print("全部通过")
