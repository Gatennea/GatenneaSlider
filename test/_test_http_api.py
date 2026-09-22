# -*- coding: utf-8 -*-
"""HTTP API 端到端无头测试（对应 .trae/specs/http-api-upgrade 的 AC-1~AC-10）。

机制：HTTP 在后台线程收请求并阻塞等待 resp_q；主线程（本测试）循环
调用 gui.process_commands() 排空队列并驱动动画/求解收尾，请求线程才会返回。
"""
import os, sys, time, json, queue, threading, tempfile, urllib.request, urllib.error

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

# 收敛梯度求解速度（与 _test_gradient_pipeline 相同手法）
import solver.ml.gather_solver as gs_mod
_FAST = {'max_steps': 40, 'patience': 10, 'max_wait_time': 3,
         'target_gather_score': 1.0, 'aggressiveness': 0.0}
gs_mod.predict_params = lambda game, step: dict(_FAST)

from GUI import SliderGUI
from http_server import start_http_server

PORT = 5099
_failures = []

def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)

# ---------------------------------------------------------------- 基础设施
cmd_queue = queue.Queue()
server = start_http_server(cmd_queue, PORT)
gui = SliderGUI(m=3, n=3, step=1, cmd_queue=cmd_queue)
gui.game_mode = 'practice'
gui.animation_duration = 30  # 播放快一点

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

def pump_frames(seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        gui.process_commands()
        gui.update_animation()
        gui._check_auto_solve_result()
        time.sleep(0.01)

def wait_solver_state(states, timeout):
    """通过 HTTP 轮询求解状态（用于终态等待）。"""
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        pump_frames(0.1)
        code, st = api('GET', '/solver/status')
        last = st
        if st.get('state') in states:
            return st
    return last

def wait_state_direct(states, timeout):
    """主线程紧轮询（20ms）直接读状态，用于捕捉短暂的 running 窗口。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        gui.process_commands()
        gui.update_animation()
        gui._check_auto_solve_result()
        st = gui._get_solver_state()
        if st['state'] in states:
            return st
        time.sleep(0.02)
    return gui._get_solver_state()

def fresh_puzzle(m, n, step, shuffle_steps):
    gui.new_puzzle(m, n, step)
    gui.game.shuffle(shuffle_steps, step=step)
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    gui.step_count = 0

# ================================================================ AC-10 兼容
print("=== AC-10 旧端点/行为兼容 ===")
code, st = api('GET', '/status')
check("旧端点 GET /status 200", code == 200)
for k in ('puzzle', 'step_count', 'solved', 'matrix',
          'selected_gap', 'selected_block', 'animating'):
    check(f"  /status 保留旧字段 {k}", k in st)
code, r = api('GET', '/map')
check("旧端点 GET /map", code == 200 and r.get('ok') and 'map' in r)
code, r = api('GET', '/macro/list')
check("旧端点 GET /macro/list", code == 200 and 'macros' in r)
code, r = api('GET', '/timer/status')
check("旧端点 GET /timer/status", code == 200 and r.get('state') is not None)
code, r = api('GET', '/records')
check("旧端点 GET /records", code == 200 and 'puzzle' in r)
code, r = api('POST', '/solve/status')
check("旧端点 POST /solve/status", code == 200 and r.get('ok'))
code, r = api('POST', '/command', {'cmd': 'status'})
check("旧端点 POST /command 文本通道", code == 200 and r.get('puzzle'))
code, r = api('GET', '/no/such/path')
check("未知 GET 路径 404", code == 404 and not r.get('ok'))
code, r = api('POST', '/map/load', {})
check("缺参 POST /map/load 400", code == 400 and not r.get('ok'))

# ================================================================ AC-1 status 新字段
print("=== AC-1 /status 新字段 ===")
for k in ('m', 'n', 'step', 'game_mode', 'timer_state', 'readonly',
          'blocks', 'macro', 'solver'):
    check(f"  /status 新字段 {k}", k in st, str(st.get(k))[:60])
# 启动时会从 config/temp_history.json 恢复上次的谜题：若那是米字格存档，
# GUI 就在 mi_mode 下起步，此时 blocks 带 q 朝向 + 晶格记号 lat 而不是 mod
# （米字格错位态的 [r%step, c%step] 会在 0.0/0.5 之间翻，不再是不变式）
_mi_startup = 'mi' in str(st.get('puzzle', ''))
if _mi_startup:
    check("  blocks 条目含 row/col/q/lat（米字格起始局面）",
          all({'row', 'col', 'q', 'lat'} <= set(b) for b in st['blocks'])
          and all(b['lat'] in ('A', 'B') for b in st['blocks'])
          and all('mod' not in b for b in st['blocks']))
else:
    check("  blocks 条目含 row/col/mod",
          all({'row', 'col', 'mod'} <= set(b) for b in st['blocks']) and st['blocks'])
    check("  mod == [row%step, col%step]（AC-9）",
          all(b['mod'] == [b['row'] % st['step'], b['col'] % st['step']]
              for b in st['blocks']))
check("  macro 含 recording/executing",
      {'recording', 'executing'} <= set(st['macro']))
check("  solver 含 state/algorithm",
      {'state', 'algorithm'} <= set(st['solver']))

# ================================================================ AC-2 move reason
print("=== AC-2 move 失败 reason ===")
code, r = api('POST', '/move', {'direction': 'w'})
check("未选中时 move 失败", code == 200 and not r.get('ok'))
check("  reason=not_selected", r.get('reason') == 'not_selected', r.get('reason', ''))

# ================================================================ AC-3 局面分析
print("=== AC-3 局面分析 ===")
fresh_puzzle(3, 3, 1, 6)
code, r = api('GET', '/analysis/window')
check("GET /analysis/window", code == 200 and r.get('ok')
      and {'r0', 'c0', 'rh', 'cw', 'overlap'} <= set(r.get('window') or {}),
      str(r)[:80])
code, r = api('GET', '/analysis/holes')
check("GET /analysis/holes", code == 200 and r.get('ok')
      and 'holes' in r and 'protrusions' in r and 'window' in r, str(r)[:80])
if r.get('holes'):
    check("  hole 条目含 type/size/cells",
          all({'type', 'size', 'cells'} <= set(h) for h in r['holes']))
code, r = api('GET', '/analysis/actions')
check("GET /analysis/actions", code == 200 and r.get('ok')
      and isinstance(r.get('actions'), list), str(r)[:80])
if r.get('actions'):
    check("  action 条目含 gap_type/gap_line/side/move_dir",
          all({'gap_type', 'gap_line', 'side', 'move_dir'} <= set(a)
              for a in r['actions']))

# ================================================================ AC-4 求解器
print("=== AC-4 求解器指令族 ===")
code, r = api('GET', '/solver/algorithms')
# 算法数量随 solver/__init__.py 的 SOLVER_ALGORITHMS 增减（human_ai 等
# 暂时注释掉的算法不计入），这里只要求非空且带 current 字段。
check("GET /solver/algorithms", code == 200 and r.get('ok')
      and len(r.get('algorithms', [])) >= 6 and 'current' in r,
      f"alg={len(r.get('algorithms', []))}")
code, r = api('GET', '/solver/status')
check("初始 solver 状态 idle", code == 200 and r.get('state') == 'idle',
      r.get('state', ''))
code, r = api('POST', '/solver/solve', {'algorithm': 'no_such_alg'})
check("非法算法 400", code == 400 and not r.get('ok'))

# 真实求解：fast 算法解 3×3 小局面
code, r = api('POST', '/solver/solve', {'algorithm': 'fast'})
check("启动求解 ok", code == 200 and r.get('ok'), r.get('message', ''))
st = wait_solver_state(('solved', 'failed'), 40)
check("求解终态 solved", st is not None and st.get('state') == 'solved',
      str(st and st.get('state')))
check("  result_steps 为非负整数",
      st is not None and isinstance(st.get('result_steps'), int)
      and st['result_steps'] >= 0, str(st and st.get('result_steps')))

# 取消语义：用阻塞式 gather_solve 桩保证求解稳定处于 running（直到收到取消）
_real_gather_solve = gs_mod.gather_solve
def _blocking_gather_solve(snap, step, cancel_check=None, **kwargs):
    t0 = time.time()
    while time.time() - t0 < 60:
        if cancel_check and cancel_check():
            return {'type': 'gather', 'solved': False, 'actions': [],
                    'reason': 'cancelled'}
        time.sleep(0.02)
    return {'type': 'gather', 'solved': False, 'actions': [], 'reason': 'timeout'}
gs_mod.gather_solve = _blocking_gather_solve

fresh_puzzle(6, 6, 3, 40)
code, r = api('POST', '/solver/solve', {'algorithm': 'gather_gradient'})
check("启动梯度求解 ok", code == 200 and r.get('ok'), r.get('message', ''))
st = wait_state_direct(('running',), 25)
check("求解进入 running", st is not None and st.get('state') == 'running',
      str(st and st.get('state')))
code, r = api('POST', '/solver/cancel')
check("取消请求 ok", code == 200 and r.get('ok'), r.get('message', ''))
st = wait_state_direct(('cancelled', 'solved', 'failed'), 25)
check("取消后状态 cancelled", st is not None and st.get('state') == 'cancelled',
      str(st and st.get('state')))
gs_mod.gather_solve = _real_gather_solve  # 还原，后续用例不受影响

# ================================================================ AC-5 宏
print("=== AC-5 宏状态/逆序参数 ===")
code, r = api('GET', '/macro/status')
check("GET /macro/status", code == 200 and r.get('ok')
      and {'recording', 'executing', 'selecting_base', 'reverse_mode',
           'recording_steps', 'current_macro'} <= set(r), str(r)[:80])
code, r = api('POST', '/macro/execute',
              {'name': '不存在的宏', 'base_row': 0, 'base_col': 0})
check("执行不存在宏优雅失败", code == 200 and not r.get('ok'))
code, r = api('POST', '/macro/execute',
              {'name': '不存在的宏', 'base_row': 0, 'base_col': 0, 'reverse': True})
check("reverse 参数被接受（不崩溃）", code == 200 and not r.get('ok'))

# ================================================================ AC-6 局面存取
print("=== AC-6 局面存取 ===")
# export_map 按方块包围盒裁剪空白行列，故 MAP_A 导回后为 "##\n##"
MAP_A = "##_\n##_\n___"
MAP_A_TRIMMED = "##\n##"
MAP_B = "###\n###\n###"
code, r = api('POST', '/map/load', {'map': MAP_A, 'step': 1})
check("POST /map/load", code == 200 and r.get('ok'), r.get('message', ''))
code, r = api('GET', '/map')
check("  导入后 /map 一致（包围盒裁剪）", code == 200 and r.get('map') == MAP_A_TRIMMED,
      repr(r.get('map')))
code, st = api('GET', '/status')
check("  导入后 step_count=0", st.get('step_count') == 0, str(st.get('step_count')))
tmp_path = os.path.join(tempfile.gettempdir(), '_http_api_test_save.txt')
if os.path.exists(tmp_path):
    os.remove(tmp_path)
code, r = api('POST', '/file/save', {'path': tmp_path})
check("POST /file/save", code == 200 and r.get('ok') and os.path.exists(tmp_path),
      r.get('message', ''))
# 保存到目录路径（无法写文件）必须回 ok:false，不得误报成功
code, r = api('POST', '/file/save', {'path': tempfile.gettempdir()})
check("保存到目录路径回 ok:false", code == 200 and not r.get('ok'), r.get('message', ''))
code, r = api('POST', '/map/load', {'map': MAP_B, 'step': 1})
check("  换局面 B", code == 200 and r.get('ok'))
code, r = api('GET', '/map')
check("  局面 B 已生效", r.get('map') == MAP_B, repr(r.get('map')))
code, r = api('POST', '/file/load', {'path': tmp_path})
check("POST /file/load", code == 200 and r.get('ok'), r.get('message', ''))
code, r = api('GET', '/map')
check("  读档后回到局面 A", r.get('map') == MAP_A_TRIMMED, repr(r.get('map')))
code, r = api('POST', '/file/load', {'path': tmp_path + '.missing'})
check("  读不存在档失败", code == 200 and not r.get('ok'))
os.remove(tmp_path)

# ================================================================ AC-7 模式
print("=== AC-7 模式切换 ===")
code, r = api('GET', '/mode')
check("GET /mode", code == 200 and r.get('mode') in ('practice', 'timed'))
code, r = api('POST', '/mode', {'mode': 'timed'})
check("POST /mode timed", code == 200 and r.get('ok'), r.get('message', ''))
code, r = api('GET', '/mode')
check("  模式已为 timed", r.get('mode') == 'timed')
code, r = api('POST', '/mode', {'mode': 'practice'})
check("切回 practice", code == 200 and r.get('ok'))
code, r = api('POST', '/mode', {'mode': 'bad'})
check("非法 mode 400", code == 400 and not r.get('ok'))

# ================================================================ AC-8 设置
print("=== AC-8 GUI 开关 settings ===")
code, r = api('GET', '/settings')
check("GET /settings", code == 200 and r.get('ok')
      and 'animation_duration_ms' in r.get('settings', {}), str(r)[:80])
s = r['settings']
check("  含 11 个布尔键",
      sum(1 for k, v in s.items() if isinstance(v, bool)) == 11,
      str(sorted(s)))
code, r = api('POST', '/settings', {'animation_duration_ms': 200})
check("设置动画速度 ok", code == 200 and r.get('ok'), r.get('message', ''))
check("  gui.animation_duration=200", gui.animation_duration == 200,
      str(gui.animation_duration))
code, r = api('POST', '/settings', {'animation_duration_ms': 10})
check("越界动画速度 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/settings', {'no_such_key': True})
check("未知设置键 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/settings', {'coloring_enabled': 'yes'})
check("布尔键类型错误 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/settings', {'show_metrics_panel': False})
check("布尔开关设置 ok", code == 200 and r.get('ok')
      and gui.show_metrics_panel is False)

# ================================================================ AC-9 求解参数
print("=== AC-9 求解参数 solver/params ===")
code, r = api('GET', '/solver/params')
check("GET /solver/params", code == 200 and r.get('ok')
      and len(r.get('params', {})) == 5, str(r)[:80])
check("  每项含 value/enabled",
      all({'value', 'enabled'} <= set(v) for v in r['params'].values()))
code, r = api('POST', '/solver/params', {'max_steps': 123})
check("设置 max_steps ok", code == 200 and r.get('ok'), r.get('message', ''))
code, r = api('GET', '/solver/params')
check("  max_steps=123 生效", r['params']['max_steps']['value'] == 123,
      str(r['params']['max_steps']))
# FR-2.6：越界回 ok:false 且不改任何值（整体校验）；未知键在路由层 400
code, r = api('POST', '/solver/params', {'max_steps': 10})
check("越界 max_steps 回 ok:false", code in (200, 400) and not r.get('ok'),
      f"code={code}")
code, r = api('GET', '/solver/params')
check("  越界后值不变（仍 123）", r['params']['max_steps']['value'] == 123,
      str(r['params']['max_steps']))
code, r = api('POST', '/solver/params', {'bogus_param': 1})
check("未知参数 400", code == 400 and not r.get('ok'))
code, r = api('POST', '/solver/params', {'max_wait_time_enabled': False})
check("启用标志切换 ok", code == 200 and r.get('ok')
      and gui.gather_enabled['max_wait_time'] is False, r.get('message', ''))

# ================================================================ 收尾
pump_frames(0.3)
server.shutdown()
server.server_close()

print()
if _failures:
    print(f"共 {len(_failures)} 项失败:")
    for f in _failures:
        print("  -", f)
    sys.exit(1)
print("ALL PASS")
