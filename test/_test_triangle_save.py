# -*- coding: utf-8 -*-
"""三角形密鋪存讀檔 / 地圖編碼無頭測試（Stage B4）。

執行：python test/_test_triangle_save.py
覆蓋：v2 存檔三角分支往返（含多步歷史）、_do_load_map 三角分支
      （'#' / 純 '^' / 純 'v' 地圖）、GUI 層地圖導出→導入往返、
      records key {step}~tri{k}、HTTP /map 與 /map/load、方形無迴歸。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from GUI import SliderGUI  # noqa: E402
from game_triangle import TriangleSliderMatrix, tri_key  # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


gui = SliderGUI(m=6, n=6, step=1)
gui.animation_enabled = False
gui.save_readonly_flag = False

# ================================================================ 存檔往返
print("== v2 存檔三角分支往返 ==")
gui.new_triangle_puzzle(6, 2)
# 先走幾步，讓歷史不止一條快照（step=1：步數語義與快照 steps 一一對應）
moved = 0
for key in sorted(gui.game.positions()):
    gui.selected_gap = None
    gui.selected_block = gui.game.block_at(key)
    for d in ('d', 'e', 'w'):
        if gui.move_selected_blocks(d, step=1):
            moved += 1
            break
    if moved >= 3:
        break
check(f"建局後可滑動（實測走了 {moved} 步）", moved >= 1)
check(f"歷史含多條快照（{len(gui.game_history.history)} 條）",
      len(gui.game_history.history) > 1)
check(f"步數已累計（{gui.step_count}）", gui.step_count > 0)

data = gui._build_save_data()
check("存檔寫入 type=triangle / triangle_side / version=2",
      data['version'] == 2 and data['puzzle']['type'] == 'triangle'
      and data['puzzle']['triangle_side'] == 6)
snaps = data['history']['snapshots']
flat = [v for row in snaps[0]['matrix'] for v in row]
check("快照矩陣取值均在 0..3（2-bit 菱形網格）",
      all(v in (0, 1, 2, 3) for v in flat))
bits = sum(bin(v).count('1') for v in flat)
check(f"快照矩陣覆蓋全部 36 個單元三角（實際 {bits}）", bits == 36)
check("初始參考態不帶 move_info", 'move_info' not in snaps[0])
check(f"其後每條快照都帶 move_info（{len(snaps)} 條）",
      all('move_info' in s for s in snaps[1:]))

moved_positions = set(gui.game.positions())
moved_steps = gui.step_count
gui.new_puzzle(5, 5, 2)          # 先切到方形，確認載入會正確分派
gui._load_save_data(data)
check("載入後 triangle_mode 復原", gui.triangle_mode is True)
check("載入後 game 為三角形", isinstance(gui.game, TriangleSliderMatrix))
check("載入後邊長/塊數正確",
      gui.game.k == 6 and len(gui.game.blocks) == 36)
check("載入後位置與存檔一致", set(gui.game.positions()) == moved_positions)
check(f"載入後步數一致（{gui.step_count}）", gui.step_count == moved_steps)
check(f"載入後歷史條數一致（{len(gui.game_history.history)}）",
      len(gui.game_history.history) == len(snaps))
gui.undo()
check("載入後可撤回", gui.step_count < moved_steps)

# ================================================================ 地圖導入
print("== _do_load_map 三角分支 ==")
gui.new_triangle_puzzle(4, 1)
full_map = gui.game.export_map()
check(f"三角地圖字元集 = {sorted(set(full_map))}",
      set(full_map) <= set('#^v_\n'))

# 1) 完整實心大三角（'#' 與 '^'/'v' 混合）
ok, msg = gui._do_load_map(full_map)
check(f"完整大三角地圖可導入：{msg}", ok)
check("導入完整大三角後判還原", gui.is_solved() is True)

# 2) 純 '^'（僅▲）地圖：舊的「必須有 #」判據會誤拒
up_only = '\n'.join('^' * 4 for _ in range(4))
ok, msg = gui._do_load_map(up_only)
check(f"純 '^' 地圖可導入：{msg}", ok)
check(f"純 '^' 導入 16 個▲（實際 {len(gui.game.blocks)}）",
      len(gui.game.blocks) == 16)
check("純 '^' 地圖全是▲", all(tri_key(b)[2] for b in gui.game.blocks))
check("純▲ 菱形片不判還原", gui.is_solved() is False)

# 3) 純 'v'（僅▼）地圖
down_only = '\n'.join('v' * 4 for _ in range(4))
ok, msg = gui._do_load_map(down_only)
check(f"純 'v' 地圖可導入：{msg}", ok)
check(f"純 'v' 導入 16 個▼（實際 {len(gui.game.blocks)}）",
      len(gui.game.blocks) == 16)
check("純 'v' 地圖全是▼", all(not tri_key(b)[2] for b in gui.game.blocks))

# 4) 全空 / 非法字元仍須拒絕
ok, msg = gui._do_load_map('\n'.join('_' * 4 for _ in range(4)))
check(f"全空地圖被拒：{msg}", not ok)
ok, msg = gui._do_load_map('\n'.join('?' * 4 for _ in range(4)))
check(f"非法字元被拒：{msg}", not ok)
ok, msg = gui._do_load_map('abc')
check("行長不一致被拒", not ok)

# 5) 導入後狀態重置
gui.new_triangle_puzzle(4, 1)
gui._do_load_map(up_only)
check("導入後步數歸零", gui.step_count == 0)
check(f"導入後歷史只有導入態一條（實際 {len(gui.game_history.history)}）",
      len(gui.game_history.history) == 1)
check("導入後清空選中",
      gui.selected_gap is None and gui.selected_block is None)
gui.undo()
check("導入態是歷史起點，撤無可撤",
      len(gui.game_history.history) == 1 and gui.step_count == 0)

# 6) GUI 層導出→導入往返（ export_map 的逆向 ）
gui.new_triangle_puzzle(5, 1)
round_map = gui.game.export_map()
gui.new_triangle_puzzle(6, 1)
ok, msg = gui._do_load_map(round_map)
check(f"邊長 5 的地圖可導入邊長 6 的會話：{msg}", ok)
check(f"導入後塊數 = 25（實際 {len(gui.game.blocks)}）",
      gui.game.k == 6 and len(gui.game.blocks) == 25)

# ================================================================ records key
print("== records key ==")
gui.new_triangle_puzzle(6, 2)
key = gui._rp_current_key()
check(f"三角 records key = {key}", key == '2~tri6')
gui.new_puzzle(6, 6, 2)
check(f"方形 records key = {gui._rp_current_key()}",
      gui._rp_current_key() == '2~6*6')

# ================================================================ 方形迴歸
print("== 方形無迴歸 ==")
gui.new_puzzle(6, 6, 1)
sq_map = gui.game.export_map()
check(f"方形地圖字元集 = {sorted(set(sq_map))}",
      set(sq_map) <= set('#_\n'))
ok, msg = gui._do_load_map(sq_map)
check(f"方形地圖仍可導入：{msg}", ok)
ok, msg = gui._do_load_map('\n'.join('^' * 6 for _ in range(6)))
check(f"方形模式下純 '^' 仍被拒：{msg}", not ok)
ok, msg = gui._do_load_map('\n'.join('_' * 6 for _ in range(6)))
check(f"方形模式全空仍被拒：{msg}", not ok)

# ================================================================ 存讀檔後仍可滑
print("== 載入後可繼續滑動 ==")
gui.new_triangle_puzzle(4, 1)
gui._do_load_map(full_map if len(full_map.split('\n')) == 4 else gui.game.export_map())
snap = set(gui.game.positions())
any_move = False
for key in sorted(gui.game.positions()):
    gui.selected_gap = None
    gui.selected_block = gui.game.block_at(key)
    for d in ('d', 'e', 'w', 'a', 'z', 'x'):
        if gui.move_selected_blocks(d):
            any_move = True
            break
    if any_move:
        break
check("導入完整大三角後仍有方向可滑", any_move)
check("滑動後局面改變", set(gui.game.positions()) != snap)

# ================================================================ HTTP 介面
print("== HTTP /map 與 /map/load ==")
import json  # noqa: E402
import queue  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from http_server import start_http_server  # noqa: E402

HTTP_PORT = 5099
cmd_queue = queue.Queue()
server = start_http_server(cmd_queue, HTTP_PORT)
http_gui = SliderGUI(m=6, n=6, step=1, cmd_queue=cmd_queue)
http_gui.animation_enabled = False


def _raw_request(method, path, body=None):
    url = f'http://127.0.0.1:{HTTP_PORT}{path}'
    payload = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    if payload is not None:
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
        http_gui.process_commands()
        t.join(0.02)
    if t.is_alive():
        raise RuntimeError(f"請求超時: {method} {path}")
    if 'error' in box:
        raise box['error']
    return box['result']


try:
    code, r = api('POST', '/new', {'m': 4, 'n': 4, 'step': 1, 'type': 'triangle'})
    check("POST /new type=triangle 成功", code == 200 and r.get('ok'),
          r.get('message', ''))

    code, r = api('GET', '/map')
    check("GET /map 回傳字串", code == 200 and r.get('ok')
          and isinstance(r.get('map'), str))
    tri_map = r.get('map') or ''
    check(f"三角地圖字元集 = {sorted(set(tri_map))}",
          set(tri_map) <= set('#^v_\n'))

    code, r = api('POST', '/map/load', {'map': up_only})
    check("POST /map/load 純 '^' 成功", code == 200 and r.get('ok'),
          r.get('message', ''))
    code, st = api('GET', '/status')
    blocks = st.get('blocks') or []
    check(f"/map/load 後 /status 塊數 = {len(blocks)}", len(blocks) == 16)
    check("/status blocks 帶 up 且全為 ▲",
          bool(blocks) and all(b.get('up') is True for b in blocks))

    code, r = api('POST', '/map/load', {'map': '\n'.join('_' * 4 for _ in range(4))})
    check(f"POST /map/load 全空被拒：{r.get('message')}", not r.get('ok'))
    code, r = api('POST', '/map/load', {})
    check(f"POST /map/load 缺 map 字段被拒：{r.get('message')}",
          code == 400 or not r.get('ok'))

    # 方形會話：/map 只有 '#'/'_'，純 '^' 仍須被拒
    code, r = api('POST', '/new', {'m': 5, 'n': 5, 'step': 2})
    check("POST /new 方形成功", code == 200 and r.get('ok'), r.get('message', ''))
    code, r = api('GET', '/map')
    sq_http = r.get('map') or ''
    check(f"方形地圖字元集 = {sorted(set(sq_http))}",
          set(sq_http) <= set('#_\n'))
    code, r = api('POST', '/map/load', {'map': '\n'.join('^' * 5 for _ in range(5))})
    check(f"方形模式載入純 '^' 被拒：{r.get('message')}", not r.get('ok'))
    code, r = api('POST', '/map/load', {'map': sq_http})
    check(f"方形地圖可載入：{r.get('message')}", code == 200 and r.get('ok'))
finally:
    server.shutdown()
    server.server_close()

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗:")
    for n in _failures:
        print("  -", n)
    sys.exit(1)
print("全部通過")
