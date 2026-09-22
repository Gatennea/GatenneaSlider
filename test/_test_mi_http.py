# -*- coding: utf-8 -*-
"""HTTP/CLI 雙介面無頭測試：米字格謎題（Stage M2）。

機制與 _test_http_api.py 相同：HTTP 在背景執行緒收請求並阻塞等 resp_q，
主執行緒（本測試）循環 gui.process_commands() 排空佇列，請求執行緒才會返回。

覆蓋：/new type=mi、/status 帶 q 朝向與晶格記號 lat、/select_gap 四族
      （h/v/d1/d2）、/select_block r c q（含半整數座標）、/move 八向含 q、
      非平行方向被 wrong_direction 擋下、
      進階功能（局面分析 / 宏錄製 / 宏執行 / 求解）在米字格下一律攔截、
      map/load_map 十六進位矩陣往返、/command 裸 CLI 通道、方形無迴歸。
"""
import os, sys, time, json, queue, threading, urllib.request, urllib.error

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

from GUI import SliderGUI  # noqa: E402
from http_server import start_http_server  # noqa: E402
from game_mi import (  # noqa: E402
    DIRECTIONS as MI_DIRECTIONS, GAP_DIRECTIONS as MI_GAP_DIRECTIONS,
    MiSliderMatrix, lattice_of, mi_key,
)

PORT = 5097
_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)


cmd_queue = queue.Queue()
server = start_http_server(cmd_queue, PORT)
gui = SliderGUI(m=3, n=3, step=1, cmd_queue=cmd_queue)
gui.save_readonly_flag = False
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


def pick_movable(gap_type, line):
    """在該縫隙上找一組「某方向真能滑動」的（塊, 方向）。

    用 try_move_ex 預演選組合，而不是碰運氣：米字格每格 4 塊、組很碎，
    隨便挑一塊多半撞牆或把棋盤劈開。
    """
    step = gui.current_step
    for blk in gui.game.blocks:
        for d in MI_GAP_DIRECTIONS[gap_type]:
            gui.game.opt(gap_type, line, blk)
            positions, reason = gui.game.try_move_ex(d, step)
            if positions and reason == '':
                return blk, d
    return None, None


M, N, STEP = 4, 4, 1
print("=== /new type=mi ===")
code, r = api('POST', '/new', {'m': M, 'n': N, 'step': STEP, 'type': 'mi'})
check("POST /new type=mi 成功", code == 200 and r.get('ok'), r.get('message', ''))
check("  mi_mode 置位", gui.mi_mode is True)
check("  行/列/等級正確",
      gui.game.m == M and gui.game.n == N and gui.current_step == STEP)
check("  塊數 = 每格 4 塊", len(gui.game.blocks) == 4 * M * N)
code, r = api('POST', '/new', {'m': M, 'n': N, 'step': STEP, 'type': 'bogus'})
check("  非法 type 回 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/new', {'m': 3, 'n': 3, 'step': 3, 'type': 'mi'})
check("  等級不小於棋盤尺寸時被拒", not r.get('ok'), r.get('message', ''))

print("=== /status 米字格欄位 ===")
code, st = api('GET', '/status')
check("GET /status 200", code == 200)
check("  puzzle key 為米字格標籤", st['puzzle'] == f"{STEP}~mi{M}*{N}", st['puzzle'])
check("  blocks 每條帶 q 朝向",
      len(st['blocks']) == 4 * M * N
      and all(b.get('q') in ('N', 'E', 'S', 'W') for b in st['blocks']))
check("  每格四塊俱全（(r,c,q) 兩兩不同）",
      len({(b['row'], b['col'], b['q']) for b in st['blocks']}) == 4 * M * N
      and len({(b['row'], b['col']) for b in st['blocks']}) == M * N)
check("  建局即實心棋盤（目標態 = 還原）", st['solved'] is True)
check("  step_count = 0", st['step_count'] == 0)

print("=== /select_gap 四族 ===")
ok_families = set()
gaps = gui.game.all_gaps()
for gap_type in MI_GAP_DIRECTIONS:
    target = next((ln for gt, ln in gaps if gt == gap_type), None)
    if target is None:
        continue
    code, r = api('POST', '/select_gap', {'type': gap_type, 'line': target})
    if code == 200 and r.get('ok'):
        ok_families.add(gap_type)
check("四族縫隙都可選中", ok_families == set(MI_GAP_DIRECTIONS),
      f"實際 {sorted(ok_families)}")
code, r = api('POST', '/select_gap', {'type': 'p', 'line': 1})
check("三角形專用的 'p' 在米字格下被拒", not r.get('ok'), r.get('message', ''))
code, r = api('POST', '/select_gap', {'type': 'h'})
check("缺 line 回 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/select_gap', {'type': 'h', 'line': 99})
check("越界線號被拒", not r.get('ok'), r.get('message', ''))

print("=== /select_block r c q ===")
api('POST', '/deselect')
blk = gui.game.blocks[0]
r0, c0, q0 = mi_key(blk)
api('POST', '/select_gap', {'type': 'h', 'line': 1})
code, r = api('POST', '/select_block', {'row': r0, 'col': c0, 'q': q0})
check("POST /select_block r c q 成功", code == 200 and r.get('ok'), r.get('message', ''))
check("  selected_block 就是帶 q 的那一塊",
      gui.selected_block is not None and mi_key(gui.selected_block) == (r0, c0, q0))
code, r = api('POST', '/select_block', {'row': r0, 'col': c0, 'q': 'Z'})
check("非法 q 字母被拒", not r.get('ok'), r.get('message', ''))
code, r = api('POST', '/select_block', {'row': 99, 'col': 99})
check("不存在的格子被拒", not r.get('ok'), r.get('message', ''))
code, r = api('POST', '/select_block', {'row': r0, 'col': c0})
check("省略 q 時退回該格第一塊（合法）", code == 200 and r.get('ok'),
      r.get('message', ''))

print("=== /move 八向：斜向（含 q）真的能滑，非平行被擋 ===")
api('POST', '/deselect')
found_families = []
for gap_type in MI_GAP_DIRECTIONS:
    # 每族都要真的滑一次。棋盤每動一次縫隙集合就變（is_valid_gap 要求線兩側
    # 都有塊），因此不能沿用開局時記下的第一條線，而是每族重新列全部縫隙
    # 逐個試，找到第一個「選塊 + 某平行方向真能滑」的組合。
    done = False
    for line in [ln for gt, ln in gui.game.all_gaps() if gt == gap_type]:
        code, r = api('POST', '/select_gap', {'type': gap_type, 'line': line})
        if not r.get('ok'):
            continue
        blk, direction = pick_movable(gap_type, line)
        if blk is None:
            continue
        # 經 HTTP 重走一遍：選塊（group 由 opt 重新算出）→ 移動
        r1, c1, q1 = mi_key(blk)
        code, r = api('POST', '/select_block', {'row': r1, 'col': c1, 'q': q1})
        if not r.get('ok'):
            check(f"{gap_type} 縫選塊成功", False, r.get('message', ''))
            continue
        before = {mi_key(b) for b in gui.game.blocks if b.be_opted}
        rest_before = set(gui.game.positions()) - before
        steps_before = gui.step_count
        code, r = api('POST', '/move', {'direction': direction})
        if not (r.get('ok') and gui.step_count == steps_before + 1):
            check(f"{gap_type} 縫：{direction} 移動生效", False, r.get('message', ''))
            continue
        dr, dc = MI_DIRECTIONS[direction]
        want = {(rr + dr * STEP, cc + dc * STEP, qq) for (rr, cc, qq) in before}
        moved = {mi_key(b) for b in gui.game.blocks if b.be_opted}
        check(f"{gap_type} 縫：{direction} 提交後選中組整體平移",
              want == moved, f"期望 {sorted(want)[:3]} 實得 {sorted(moved)[:3]}")
        check(f"{gap_type} 縫：{direction} 平移後 q 不變",
              {q for (_r, _c, q) in moved} == {q for (_r, _c, q) in before})
        check(f"{gap_type} 縫：{direction} 其餘部分沒被動",
              set(gui.game.positions()) - moved == rest_before)
        check(f"{gap_type} 縫：{direction} 移動後仍單一連通",
              MiSliderMatrix.is_single_connected(gui.game.positions()))
        # 同族另一個方向合法，這裡不斷言它移不移得動；其餘六個字母必須被擋下
        bad = next(d for d in MI_DIRECTIONS if d not in MI_GAP_DIRECTIONS[gap_type])
        snap = set(gui.game.positions())
        steps_now = gui.step_count
        code, r = api('POST', '/move', {'direction': bad})
        check(f"{gap_type} 縫：{bad}（不同族）被 wrong_direction 擋下",
              not r.get('ok') and r.get('reason') == 'wrong_direction'
              and set(gui.game.positions()) == snap and gui.step_count == steps_now,
              r.get('message', ''))
        found_families.append(gap_type)
        done = True
        break
    if not done:
        check(f"{gap_type} 族找不到可動組合", False)
check("四族都走通一次完整移動", set(found_families) == set(MI_GAP_DIRECTIONS),
      f"實際 {sorted(found_families)}")
code, r = api('POST', '/move', {'direction': 'y'})
check("非法方向字母回 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/move', {'direction': 'q'})
check("米字格斜向字母 'q' 不被 HTTP 層攔（只由遊戲側判合法性）",
      code == 200, r.get('message', ''))

print("=== 錯位態 /status：半整數座標 + lat 晶格記號 ===")
api('POST', '/new', {'m': M, 'n': N, 'step': STEP, 'type': 'mi'})
# 斜向一格是 ±(½,½)：挑一條斜縫真的滑一格，棋盤立刻錯成兩個晶格
moved_gap = None
for line in [ln for gt, ln in gui.game.all_gaps() if gt == 'd1']:
    blk, direction = pick_movable('d1', line)
    if blk is not None:
        moved_gap = ('d1', line, mi_key(blk), direction)
        break
check("  开局有可動的斜縫", moved_gap is not None)
if moved_gap:
    gap_type, line, (r1, c1, q1), direction = moved_gap
    code, r = api('POST', '/select_gap', {'type': gap_type, 'line': line})
    code, r = api('POST', '/select_block', {'row': r1, 'col': c1, 'q': q1})
    check("  錯位前選塊成功", r.get('ok'), r.get('message', ''))
    steps_before = gui.step_count
    code, r = api('POST', '/move', {'direction': direction})
    check("  斜向一格提交成功", r.get('ok')
          and gui.step_count == steps_before + 1, r.get('message', ''))

    def _twice(row, col):
        return (int(round(2 * row)), int(round(2 * col)))

    positions = gui.game.positions()
    half = [k for k in positions if k[0] % 1 or k[1] % 1]
    check("  走完確實有塊落在半整數座標上", len(half) > 0,
          f"半整數塊 {len(half)}/{len(positions)}")
    code, st = api('GET', '/status')
    check("  建局態就沒有 mod 欄位（不再是那種不變式）",
          code == 200 and all('mod' not in b for b in st['blocks']))
    want = {_twice(r, c) + (q,) for (r, c, q) in positions}
    got = {_twice(b['row'], b['col']) + (b['q'],) for b in st['blocks']}
    check("  半整數 row/col JSON 原樣可過（與引擎逐塊一致）",
          want == got, f"缺 {sorted(want - got)[:3]} 多 {sorted(got - want)[:3]}")
    check("  lat 晶格記號與引擎 lattice_of 逐塊一致",
          all(b['lat'] == ('A', 'B')[lattice_of((b['row'], b['col'], b['q']))]
              for b in st['blocks']),
          str([(b['row'], b['col'], b['lat']) for b in st['blocks']][:4]))
    lats = {b['lat'] for b in st['blocks']}
    check("  錯位態兩個晶格都在（A 建局 / B 半整）", lats == {'A', 'B'},
          f"實際 {sorted(lats)}")
    n_b = sum(1 for b in st['blocks'] if b['lat'] == 'B')
    check("  B 晶格塊數 = 真正錯位的那批", n_b == len(half),
          f"B {n_b} vs 半整數塊 {len(half)}")
    # 終端/HTTP 這條路徑也吃得下半整數錨點：再選半格上的塊
    b_key = next(k for k in positions if lattice_of(k))
    code, r = api('POST', '/select_block',
                  {'row': b_key[0], 'col': b_key[1], 'q': b_key[2]})
    check("  選半整數座標的塊也成功", code == 200 and r.get('ok'),
          r.get('message', ''))

print("=== 米字格下的進階功能一律攔截 ===")
for ep in ('/analysis/window', '/analysis/holes', '/analysis/actions'):
    code, r = api('GET', ep)
    check(f"GET {ep} 在米字格下回 400",
          code == 400 and not r.get('ok') and r.get('reason') == 'unsupported',
          r.get('message', ''))
code, r = api('POST', '/solve', {})
check("POST /solve 在米字格下失敗", not r.get('ok'), r.get('message', ''))
code, r = api('POST', '/macro/record/start', {})
check("POST /macro/record/start 在米字格下失敗", not r.get('ok'), r.get('message', ''))
check("  錄製旗標沒有被打開", gui.macro_recording is False)
code, r = api('POST', '/macro/execute',
              {'name': '宏_1', 'base_row': 0, 'base_col': 0})
check("POST /macro/execute 在米字格下失敗", not r.get('ok'), r.get('message', ''))
check("  執行旗標沒有被打開", gui.macro_executing is False)

print("=== map / load_map 十六進位矩陣往返 ===")
api('POST', '/new', {'m': M, 'n': N, 'step': STEP, 'type': 'mi'})
code, r = api('GET', '/map')
check("GET /map 成功", code == 200 and r.get('ok') and r.get('map'))
map_str = r.get('map', '')
check("  每格一個十六進位位、行數=列數=M",
      len(map_str.split('\n')) == M
      and all(len(ln) == M and all(ch in '0123456789abcdefABCDEF_.' for ch in ln)
              for ln in map_str.split('\n')),
      repr(map_str))
snap_blocks = {(b['row'], b['col'], b['q']) for b in api('GET', '/status')[1]['blocks']}
gui.shuffle_puzzle()
check("  打亂後局面確實變了",
      {(b['row'], b['col'], b['q']) for b in api('GET', '/status')[1]['blocks']}
      != snap_blocks)
code, r = api('POST', '/map/load', {'map': map_str})
check("POST /map/load 成功", code == 200 and r.get('ok'), r.get('message', ''))
check("  載入後回到同一局面",
      {(b['row'], b['col'], b['q']) for b in api('GET', '/status')[1]['blocks']}
      == snap_blocks)
code, r = api('POST', '/map/load', {'map': 'not-a-map'})
check("  壞矩陣被拒", not r.get('ok'), r.get('message', ''))

print("=== /command 裸 CLI 通道 ===")
code, r = api('POST', '/command', {'cmd': 'new 4 4 1 mi'})
check("裸指令 new ... mi 成功", code == 200 and r.get('ok'), r.get('message', ''))
check("  puzzle 仍是米字格", gui.mi_mode is True and gui.game.m == 4)
code, r = api('POST', '/command', {'cmd': 'select_gap h 1'})
check("裸指令 select_gap 成功", r.get('ok'), r.get('message', ''))
code, r = api('POST', '/command', {'cmd': 'move q'})
check("裸指令 move q 不會因姿勢報錯（只是沒選塊）", code == 200,
      r.get('message', ''))
code, r = api('POST', '/command', {'cmd': 'move y'})
check("裸指令 move y 被拒", not r.get('ok'), r.get('message', ''))
code, r = api('POST', '/command', {'cmd': 'select_block 0 0 N'})
check("裸指令 select_block r c q 成功", r.get('ok'), r.get('message', ''))

print("=== 方形無迴歸 ===")
code, r = api('POST', '/new', {'m': 4, 'n': 4, 'step': 2})
check("POST /new 方形成功", code == 200 and r.get('ok'))
check("  mi_mode 已清除", gui.mi_mode is False)
check("  塊數回到 m*n", len(gui.game.blocks) == 4 * 4)
for ep in ('/analysis/window', '/analysis/holes', '/analysis/actions'):
    code, r = api('GET', ep)
    check(f"GET {ep} 在方形模式下仍 200", code == 200 and r.get('ok'),
          r.get('message', ''))
code, r = api('POST', '/command', {'cmd': 'macro_record_start'})
check("方形模式下宏錄製仍可用", r.get('ok'), r.get('message', ''))
gui.macro_recording = False  # 錄製要起對話框命名，測試到此為止
code, r = api('POST', '/solve', {})
check("方形模式下求解仍可用（僅斷言啟動成功）", r.get('ok'), r.get('message', ''))
code, r = api('POST', '/move', {'direction': 'q'})
check("方形模式下 'q' 由遊戲側拒絕",
      not r.get('ok') and 'w/s/a/d' in r.get('message', ''), r.get('message', ''))
code, r = api('POST', '/select_gap', {'type': 'd1', 'line': 1})
check("方形模式下 'd1' 縫被拒", not r.get('ok'), r.get('message', ''))

print()
if _failures:
    print(f"共 {len(_failures)} 項失敗")
    sys.exit(1)
print("全部通過")
