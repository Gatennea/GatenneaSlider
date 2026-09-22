# -*- coding: utf-8 -*-
"""HTTP/CLI 雙介面無頭測試：三角形密鋪（Stage B2c）。

機制與 _test_http_api.py 相同：HTTP 在背景執行緒收請求並阻塞等 resp_q，
主執行緒（本測試）循環 gui.process_commands() 排空佇列，請求執行緒才會返回。

覆蓋：/new type=triangle、/status 帶 (i,j,up)、/select_gap 3 族、
      /select_block i j up、/move 6 向、/analysis/* 回 400、
      /solve 被攔截、方形無迴歸。
"""
import os, sys, time, json, queue, threading, urllib.request, urllib.error

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from GUI import SliderGUI  # noqa: E402
from http_server import start_http_server  # noqa: E402
from game_triangle import (  # noqa: E402
    DIRECTIONS, GAP_DIRECTIONS, TriangleSliderMatrix, side_of, tri_key,
)

PORT = 5098
_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


cmd_queue = queue.Queue()
server = start_http_server(cmd_queue, PORT)
gui = SliderGUI(m=3, n=3, step=1, cmd_queue=cmd_queue)
gui.game_mode = 'practice'
gui.animation_enabled = False  # 移動立即生效，便於斷言


def _raw_request(method, path, body=None):
    url = f'http://127.0.0.1:{PORT}{path}'
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def api(method, path, body=None, timeout=15):
    """發 HTTP 請求，同時主執行緒排空命令佇列（否則請求執行緒會永遠阻塞）。"""
    box = {}

    def worker():
        try:
            box['result'] = _raw_request(method, path, body)
        except Exception as e:  # pragma: no cover - 只會在測試自身出錯時觸發
            box['error'] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t0 = time.time()
    while t.is_alive() and time.time() - t0 < timeout:
        gui.process_commands()
        t.join(0.02)
    if t.is_alive():
        raise RuntimeError(f"請求超時: {method} {path}")
    if 'error' in box:
        raise box['error']
    return box['result']


K = 4
print("=== /new type=triangle ===")
code, r = api('POST', '/new', {'m': K, 'n': K, 'step': 1, 'type': 'triangle'})
check("POST /new type=triangle 成功", code == 200 and r.get('ok'), r.get('message', ''))
check("  triangle_mode 置位", gui.triangle_mode is True)
check("  邊長/塊數正確", gui.game.k == K and len(gui.game.blocks) == K * K)
code, r = api('POST', '/new', {'m': K, 'n': K, 'step': 1, 'type': 'bogus'})
check("  非法 type 回 400", code == 400 and not r.get('ok'))

print("=== /status 三角形欄位 ===")
code, st = api('GET', '/status')
check("GET /status 200", code == 200)
check("  puzzle key 為三角標籤", st['puzzle'] == f"1~tri{K}", st['puzzle'])
check("  blocks 每條帶 up 朝向",
      all('up' in b for b in st['blocks']) and len(st['blocks']) == K * K)
check("  up 為布林值", all(isinstance(b['up'], bool) for b in st['blocks']))
check("  建局即實心大三角（目標態 = 還原）", st['solved'] is True)
check("  step_count = 0", st['step_count'] == 0)

print("=== /select_gap 3 族 ===")
ok_families = []
gaps = gui.game.all_gaps()
for gap_type in GAP_DIRECTIONS:
    # 取該族第一條合法縫
    target = next((ln for gt, ln in gaps if gt == gap_type), None)
    if target is None:
        continue
    code, r = api('POST', '/select_gap', {'type': gap_type, 'line': target})
    if code == 200 and r.get('ok'):
        ok_families.append(gap_type)
check("三族縫隙都可選中", set(ok_families) == set(GAP_DIRECTIONS),
      f"實際 {sorted(ok_families)}")
code, r = api('POST', '/select_gap', {'type': 'v', 'line': 1})
check("方形專用的 'v' 在三角模式下被拒", not r.get('ok'), r.get('message', ''))
code, r = api('POST', '/select_gap', {'type': 'p'})
check("缺 line 回 400", code == 400 and not r.get('ok'))

print("=== /select_block + /move 6 向 ===")
# 選一塊，再逐個方向試：至少一個方向能動，且都不會整體平移
api('POST', '/deselect')
blk = gui.game.blocks[0]
code, r = api('POST', '/select_block',
              {'row': blk.location[0], 'col': blk.location[1],
               'up': int(bool(blk.location[2]))})
check("POST /select_block i j up 成功", code == 200 and r.get('ok'), r.get('message', ''))
check("  selected_block 帶 up", gui.selected_block is not None
      and len(gui.selected_block.location) == 3)

moved_dirs = []
for letter in DIRECTIONS:
    snap = set(gui.game.positions())
    code, r = api('POST', '/move', {'direction': letter})
    if r.get('ok') and set(gui.game.positions()) != snap:
        moved_dirs.append(letter)
    # 無論成功與否，都必須保持單一連通（不允許把棋盤劈成兩半）
    if not TriangleSliderMatrix.is_single_connected(gui.game.positions()):
        check(f"  方向 {letter} 移動後仍連通", False)
        break
else:
    check("6 向逐個嘗試後始終單一連通", True)
check("至少一個方向可移動", bool(moved_dirs), f"實際 {moved_dirs}")
check("步數已累計", gui.step_count > 0)

code, r = api('POST', '/move', {'direction': 'y'})
check("非法方向字母回 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/move', {'direction': 'q'})
check("米字格斜向字母 'q' 由遊戲側拒絕（HTTP 層為米字格放行）",
      code == 200 and not r.get('ok'), r.get('message', ''))

print("=== 選中縫隙後的方向平行性 ===")
# 兩次觸控語義：先選縫，再選塊，只有平行方向可動
api('POST', '/deselect')
found = False
for gap_type, line in gui.game.all_gaps():
    code, r = api('POST', '/select_gap', {'type': gap_type, 'line': line})
    if not r.get('ok'):
        continue
    cand = next((b for b in gui.game.blocks
                 if side_of(gap_type, line, tri_key(b)) is not None), None)
    if cand is None:
        continue
    api('POST', '/select_block',
        {'row': cand.location[0], 'col': cand.location[1],
         'up': int(bool(cand.location[2]))})
    parallel = [d for d in GAP_DIRECTIONS[gap_type]
                if api('POST', '/move', {'direction': d})[1].get('ok')]
    if parallel:
        bad = next(d for d in DIRECTIONS if d not in GAP_DIRECTIONS[gap_type])
        code, r = api('POST', '/move', {'direction': bad})
        check(f"縫 {gap_type} 平行方向可動", True, f"{parallel}")
        check("與選中縫隙不平行的方向被拒",
              not r.get('ok') and r.get('reason') == 'wrong_direction',
              r.get('message', ''))
        found = True
        break
check("找到一條可動的縫", found)

print("=== /analysis/* 回 400 ===")
for ep in ('/analysis/window', '/analysis/holes', '/analysis/actions'):
    code, r = api('GET', ep)
    check(f"GET {ep} 在三角模式下回 400",
          code == 400 and not r.get('ok')
          and r.get('reason') == 'unsupported', r.get('message', ''))

print("=== /solve 被攔截 ===")
code, r = api('POST', '/solve', {})
check("POST /solve 在三角模式下失敗", not r.get('ok'), r.get('message', ''))
check("  提示為尚未實現", '尚未实现' in r.get('message', ''))

print("=== 方形無迴歸 ===")
code, r = api('POST', '/new', {'m': 4, 'n': 4, 'step': 2})
check("POST /new 方形成功", code == 200 and r.get('ok'))
check("  triangle_mode 已清除", gui.triangle_mode is False)
for ep in ('/analysis/window', '/analysis/holes', '/analysis/actions'):
    code, r = api('GET', ep)
    check(f"GET {ep} 在方形模式下仍 200", code == 200 and r.get('ok'))
api('POST', '/deselect')
gui.game.opt('h', 1, gui.game.blocks[0])
code, r = api('POST', '/move', {'direction': 'e'})
check("方形模式不接受 'e'（遊戲側拒絕）",
      not r.get('ok') and 'w/s/a/d' in r.get('message', ''), r.get('message', ''))
code, r = api('POST', '/select_gap', {'type': 'p', 'line': 1})
check("方形模式不接受 'p' 縫", not r.get('ok'), r.get('message', ''))

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗")
    sys.exit(1)
print("全部通過")
