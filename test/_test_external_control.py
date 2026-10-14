# -*- coding: utf-8 -*-
"""外部控制（HTTP 令牌鉴权 + help 索引 + 话术/教程）无头测试。

对应设计决策（2026-10-13 用户拍板）：
  一律 token（AI 经 stdout 自动交付，人类经设置页复制按钮）；
  默认开：无 token 拒绝；关闭=403、错 token=401；
  /help 索引与游戏内下载教程同源；教程文件不含 token；
  stdin 通道不设防（父进程可信）。
"""
import os, sys, time, json, queue, threading, tempfile, urllib.request, urllib.error

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from GUI import SliderGUI
from http_server import (start_http_server, API_INDEX, HELP_DETAILS,
                         TOKEN_MESSAGE_TEMPLATE)
from gui.events import CLI_COMMANDS

PORT = 5098
_failures = []

def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)

# ---------------------------------------------------------------- 基础设施
ext_state = {'enabled': True, 'token': 'TESTTOKEN123456', 'port': PORT}
cmd_queue = queue.Queue()
server = start_http_server(cmd_queue, PORT, ext_state)
gui = SliderGUI(m=3, n=3, step=1, cmd_queue=cmd_queue, ext_state=ext_state)
gui.tut_show_prompt = False
gui.tutorial_active = False

def _raw_request(method, path, body=None, headers=None):
    url = f'http://127.0.0.1:{PORT}{path}'
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}

def api(method, path, body=None, headers=None, timeout=15):
    """发 HTTP 请求，同时主线程排空命令队列（否则进队列的请求会永远阻塞）。"""
    box = {}
    def worker():
        try:
            box['result'] = _raw_request(method, path, body, headers)
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

AUTH = {'Authorization': 'Bearer TESTTOKEN123456'}

# ---------------------------------------------------------------- AC-1~5 鉴权
s, r = api('GET', '/status')
check('AC-1 无令牌 → 401', s == 401, f'(got {s})')
check('AC-1b 无令牌提示含获取途径', '设置-控制' in r.get('message', ''))

s, r = api('GET', '/status', headers={'Authorization': 'Bearer WRONG'})
check('AC-2 错令牌 → 401', s == 401 and '无效' in r.get('message', ''))

s, r = api('GET', '/status', headers=AUTH)
check('AC-3 正确令牌（header）→ 200', s == 200 and 'step_count' in r, f'(got {s})')

s, r = api('GET', '/status?token=TESTTOKEN123456')
check('AC-4 正确令牌（query）→ 200', s == 200 and 'step_count' in r, f'(got {s})')

# AC-5 开关关闭 → 一切拒绝（403），带不错令牌都一样
ext_state['enabled'] = False
s1, r1 = api('GET', '/status', headers=AUTH)
s2, r2 = api('POST', '/undo', body={}, headers=AUTH)
check('AC-5 开关关闭 → 403（GET+POST 全拒）',
      s1 == 403 and s2 == 403 and '外部控制未开启' in r1.get('message', ''))
ext_state['enabled'] = True

# AC-6 关→开换新令牌：旧话术作废
old = ext_state['token']
gui.set_external_control(False)
check('AC-6a 关闭清空令牌', ext_state['token'] is None and not gui.external_enabled())
gui.set_external_control(True)
new = ext_state['token']
check('AC-6b 重开生成新令牌', bool(new) and new != old)
s, _ = api('GET', '/status', headers={'Authorization': f'Bearer {old}'})
check('AC-6c 旧令牌 → 401', s == 401)
s, r = api('GET', '/status', headers={'Authorization': f'Bearer {new}'})
check('AC-6d 新令牌 → 200', s == 200 and 'step_count' in r)
ext_state['token'] = 'TESTTOKEN123456'  # 还原，后续用例用
AUTH = {'Authorization': 'Bearer TESTTOKEN123456'}

# AC-7 /help 索引
s, r = api('GET', '/help')
check('AC-7a /help 无令牌 → 401', s == 401)
s, r = api('GET', '/help', headers=AUTH)
ok = (s == 200 and r.get('ok') and isinstance(r.get('endpoints'), list)
      and len(r['endpoints']) > 20 and 'first_step' in r and 'auth' in r)
check('AC-7b /help 索引完整（端点>20 + first_step + auth）', ok)
s, _ = api('GET', '/help?token=TESTTOKEN123456')
check('AC-7c /help query 传令牌 → 200', s == 200)

# AC-8 API_INDEX 防腐烂：每个 (path, method) 都能在对应分派函数里找到
src = open('http_server.py', encoding='utf-8').read()
def _func_src(src, name):
    i = src.index(f'def {name}(')
    j = src.find('\n    def ', i + 10)
    return src[i:j if j > 0 else len(src)]
get_src, post_src = _func_src(src, '_dispatch_get'), _func_src(src, '_dispatch_post')
bad = []
for p, m, _s in API_INDEX:
    if m in ('GET', 'BOTH') and f"'{p}'" not in get_src:
        bad.append(f'GET {p}')
    if m in ('POST', 'BOTH') and f"'{p}'" not in post_src:
        bad.append(f'POST {p}')
check('AC-8 API_INDEX 与分派代码一致（无腐烂）', not bad, str(bad))

# AC-9 CLI_COMMANDS 防腐烂：每个命令名（第三列显式列出）都有分派分支
ev_src = open(os.path.join('gui', 'events.py'), encoding='utf-8').read()
i = ev_src.index('def process_commands')
j = ev_src.find('\n    def ', i + 10)
proc = ev_src[i:j if j > 0 else len(ev_src)]
names = [n for _c, _s, ns in CLI_COMMANDS for n in ns]
bad = [n for n in names if f"action == '{n}'" not in proc]
check('AC-9 CLI_COMMANDS 与分派代码一致（无腐烂）', not bad, str(bad))

# AC-10 CLI help 命令（stdin 通道）
rq = queue.Queue()
cmd_queue.put(('help', rq))
gui.process_commands()
res = rq.get_nowait() if not rq.empty() else {}
check('AC-10 CLI help 返回 commands + http_api',
      res.get('ok') and len(res.get('commands', [])) > 10
      and len(res.get('http_api', [])) > 20)

# AC-11 复制话术内容
msg = gui.external_control_message()
ok = ('TESTTOKEN123456' in msg and f'127.0.0.1:{PORT}' in msg
      and 'Authorization: Bearer' in msg and 'GET /help' in msg
      and 'GET /status' in msg and '重启后令牌失效' in msg)
check('AC-11 连接话术含令牌/端口/三步引导', ok)
check('AC-11b 话术模板含署名规范文案', '貓九的滑塊遊戲' in msg)

# AC-12 关闭时复制被拒（反馈走设置页内联消息，不用模态下的隐形 toast）
gui.set_external_control(False)
gui._copy_external_message()
check('AC-12 关闭时复制被拒并提示',
      '关闭' in (getattr(gui, '_settings_ext_msg', '') or ''))
gui.set_external_control(True)
ext_state['token'] = 'TESTTOKEN123456'

# AC-13 教程文件：内容同源、不含令牌
with tempfile.TemporaryDirectory() as td:
    gp = os.path.join(td, 'guide.md')
    okw, msg = gui.write_external_control_guide(gp)
    content = open(gp, encoding='utf-8').read()
    check('AC-13a 教程生成成功', okw and os.path.isfile(gp))
    check('AC-13b 教程含 API 索引与请求示例',
          '## 3. API 索引' in content and '| GET | `/status` |' in content
          and 'Authorization: Bearer' in content)
    check('AC-13c 教程不含令牌（职责分离）',
          'TESTTOKEN123456' not in content and ext_state['token'] not in content)

# AC-14 控制页三控件 + 开关点击（滚到底：与玩家实际看到的按钮位置一致）
gui.show_settings_dialog = True
gui.settings_active_tab = 'control'
gui._settings_backup_keybindings = dict(gui.keybindings)
gui.draw_settings_dialog()
has3 = all(getattr(gui, a, None) for a in (
    '_settings_ext_toggle_rect', '_settings_ext_copy_rect', '_settings_ext_guide_rect'))
check('AC-14a 控制页绘制三个外部控制控件', has3)
import pygame
gui.external_enabled() and gui.set_external_control(True)
gui.settings_scrollbar.set_scroll(10**6)  # 滚到底——按钮在内容区可见位置
gui.draw_settings_dialog()
# AC-14a2 按钮必须落在内容裁剪区内（曾因不滚动就画在对话框外而「看不见」）
_sw, _sh = gui.screen.get_size()
_dlg_y = (_sh - 480) // 2
_content_top = _dlg_y + 58 + 30 + 10
_content_bottom = _dlg_y + 480 - 64
for _name in ('_settings_ext_toggle_rect', '_settings_ext_copy_rect', '_settings_ext_guide_rect'):
    _r = getattr(gui, _name)
    check(f'AC-14a2 {_name} 在内容可见区内',
          _r.top >= _content_top and _r.bottom <= _content_bottom,
          f'({_r}, 区域 {_content_top}..{_content_bottom})')
pygame.event.post(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, button=1, pos=gui._settings_ext_toggle_rect.center))
gui.handle_events()
check('AC-14b 点开关 → 关闭', not gui.external_enabled())
pygame.event.post(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, button=1, pos=gui._settings_ext_toggle_rect.center))
gui.handle_events()
check('AC-14c 再点开关 → 开启', gui.external_enabled())
ext_state['token'] = 'TESTTOKEN123456'
AUTH = {'Authorization': 'Bearer TESTTOKEN123456'}

# AC-16 点「复制连接话术」→ 对话框内联反馈（无头环境也能看出按钮没死）
gui._settings_ext_msg = ''
gui._settings_ext_msg_timer = 0
pygame.event.post(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, button=1, pos=gui._settings_ext_copy_rect.center))
gui.handle_events()
_msg = getattr(gui, '_settings_ext_msg', '')
check('AC-16a 复制点击有内联反馈', bool(_msg), repr(_msg))
check('AC-16b 反馈措辞面向外部程序', '外部程序' in _msg, repr(_msg))
# AC-16c 失败兜底：剪贴板整体不可用时，令牌/端口直接显示可人工抄送
_orig = (pygame.scrap.put_text, pygame.scrap.put, pygame.scrap.get_text)
def _boom(*a, **k):
    raise RuntimeError('clipboard unavailable')
pygame.scrap.put_text = _boom
pygame.scrap.put = _boom
pygame.scrap.get_text = _boom
try:
    gui._copy_external_message()
finally:
    pygame.scrap.put_text, pygame.scrap.put, pygame.scrap.get_text = _orig
_msg2 = getattr(gui, '_settings_ext_msg', '')
check('AC-16c 失败兜底含令牌与端口（可人工抄送）',
      'TESTTOKEN123456' in _msg2 and str(PORT) in _msg2, repr(_msg2))
check('AC-16d 失败反馈带警示标记', getattr(gui, '_settings_ext_msg_ok', True) is False)
# AC-16f 读回校验容忍 CRLF（Windows 剪贴板换行风格差异不诬告失败）
_clip = {'text': ''}
pygame.scrap.put_text = lambda t: _clip.__setitem__('text', t)
pygame.scrap.get_text = lambda: _clip['text'].replace('\n', '\r\n')
pygame.scrap.put = _boom
try:
    gui._copy_external_message()
finally:
    pygame.scrap.put_text, pygame.scrap.get_text, pygame.scrap.put = _orig
check('AC-16f CRLF 读回不诬告失败', '已复制' in (getattr(gui, '_settings_ext_msg', '') or ''),
      repr(getattr(gui, '_settings_ext_msg', '')))
gui.draw_settings_dialog()
check('AC-16e 内联反馈参与内容高度计算（不溢出裁剪区）',
      getattr(gui, '_settings_ext_msg_lines', 0) >= 1)

# AC-17 点「下载控制教程」→ 先关设置框再开文件对话框
# （曾经的 bug：文件对话框被设置框盖住且吞掉全部事件 → 游戏假死）
pygame.event.post(pygame.event.Event(
    pygame.MOUSEBUTTONDOWN, button=1, pos=gui._settings_ext_guide_rect.center))
gui.handle_events()
check('AC-17a 教程点击后设置框已关闭', not gui.show_settings_dialog)
check('AC-17b 文件对话框已打开（可见可交互）', bool(gui.file_dialog.active))
check('AC-17c 待保存教程标志已置位', getattr(gui, '_pending_guide_save', False))
gui.file_dialog.active = False  # 还原，避免影响后续用例

# AC-18 措辞口径：请求方解释为「外部程序」，不写「AI 带令牌请求」
_rnd = open(os.path.join('gui', 'renderer.py'), encoding='utf-8').read()
check('AC-18a 控制页开关说明用「外部程序」', '外部程序须带令牌请求' in _rnd)
check('AC-18b 已无「AI 须带令牌请求」措辞', 'AI 须带令牌请求' not in _rnd)
check('AC-18c 复制话术模板面向外部程序', '外部程序' in TOKEN_MESSAGE_TEMPLATE)

# AC-19 反馈出现后必须完整可见：自动滚到底 + 反馈行不溢出裁剪区
# （曾经的 bug：内容长高但滚动量没跟上 → 反馈行被裁掉，玩家依旧像点到死按钮）
gui.show_settings_dialog = True
gui.settings_active_tab = 'control'
gui.draw_settings_dialog()
gui.settings_scrollbar.set_scroll(10**6)  # 玩家已滚到底
gui.draw_settings_dialog()
gui._set_ext_feedback(
    False, '复制失败（剪贴板不可用：x）。请手动抄送：令牌 TESTTOKEN123456，端口 5050',
    timer=600)
gui.draw_settings_dialog()  # pin 底 + 按当前消息重算内容高度
_clip_bottom = (_sh - 480) // 2 + 480 - 64
_fb_bottom = gui._settings_ext_copy_rect.bottom + 6 + 18 * gui._settings_ext_msg_lines
check('AC-19a 反馈出现后自动滚到底',
      gui.settings_scrollbar.scroll == gui.settings_scrollbar._max_scroll(),
      f'(scroll={gui.settings_scrollbar.scroll})')
check('AC-19b 反馈行完整落在内容裁剪区内', _fb_bottom <= _clip_bottom,
      f'(反馈底 {_fb_bottom} > 裁剪底 {_clip_bottom})')

# AC-15 既有端点不被鉴权破坏（POST /screenshot 带令牌）
with tempfile.TemporaryDirectory() as td:
    sp = os.path.join(td, 'shot.png')
    s, r = api('POST', '/screenshot', body={'path': sp}, headers=AUTH)
    check('AC-15 POST /screenshot 带令牌正常', s == 200 and r.get('ok')
          and os.path.isfile(sp), f'(got {s} {r.get("message", "")})')
    s, _ = api('POST', '/screenshot', body={'path': sp})
    check('AC-15b POST /screenshot 无令牌 → 401', s == 401)

# AC-20 GET /help/<端点>：单个端点的参数/返回/示例（2026-10-14 第二步）
s, r = api('GET', '/help/move', headers=AUTH)
check('AC-20a /help/move → 200 且四要素齐全',
      s == 200 and r.get('ok') and r.get('path') == '/move'
      and r.get('method') == 'POST' and bool(r.get('description'))
      and isinstance(r.get('params'), list) and len(r['params']) == 1
      and r['params'][0]['name'] == 'direction'
      and r['params'][0]['required'] is True
      and bool(r.get('returns')) and bool(r.get('example')),
      repr(r)[:200])
s, r = api('GET', '/help/status', headers=AUTH)
check('AC-20b /help/status → 200 且无参数', s == 200 and r.get('params') == [])
s, r = api('GET', '/help/nope', headers=AUTH)
check('AC-20c 未知端点 → 404 且指回 /help',
      s == 404 and not r.get('ok') and '/help' in r.get('message', ''))
s, r = api('GET', '/help/move')
check('AC-20d 详情端点也要令牌 → 401', s == 401)

# AC-21 索引与详情一一对应（双向防腐烂：谁多谁少都失败）
_index_paths = {p for p, _m, _s in API_INDEX}
missing = [p for p in _index_paths if p not in HELP_DETAILS]
extra = [p for p in HELP_DETAILS if p not in _index_paths]
check('AC-21a API_INDEX 每条都有详情条目', not missing, str(missing))
check('AC-21b 详情表没有索引外条目', not extra, str(extra))
s, r = api('GET', '/help', headers=AUTH)
check('AC-21c /help 索引含详情指路与新条目',
      bool(r.get('detail'))
      and any(e['path'] == '/help/<端点>' for e in r.get('endpoints', [])))

# AC-22 详情条目自身完整（desc/returns/example 非空、params 结构合法）
bad = []
for p, d in HELP_DETAILS.items():
    if not d.get('desc') or not d.get('returns') or not d.get('example'):
        bad.append(f'{p}:缺字段')
    for prm in d.get('params', []):
        if len(prm) != 4 or not isinstance(prm[2], bool):
            bad.append(f'{p}:param {prm}')
check('AC-22 全部详情条目结构完整', not bad, str(bad[:5]))

# AC-23 详情 method 与索引一致 + 教程文件含详情指路
_method_map = {p: m for p, m, _s in API_INDEX}
bad = [p for p in HELP_DETAILS if _method_map.get(p) != next(
    (m for (q, m, _s) in API_INDEX if q == p), None)]
check('AC-23a 详情 method 与 API_INDEX 一致', not bad, str(bad))
with tempfile.TemporaryDirectory() as td:
    gp = os.path.join(td, 'guide.md')
    ok, _msg = gui.write_external_control_guide(gp)
    txt = open(gp, encoding='utf-8').read() if ok else ''
    check('AC-23b 教程文件含 /help/<端点> 指路',
          ok and '/help/<端点>' in txt)

print()
if _failures:
    print(f"共 {len(_failures)} 项失败: {_failures}")
    sys.exit(1)
print("ALL EXTERNAL CONTROL TESTS PASS")
