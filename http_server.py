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


# 外部控制 API 索引（GET /help 与游戏内「下载外部控制教程」同源生成）。
# ⚠️ 新增/改动端点时必须同步更新本表——test/_test_external_control.py
# 会逐条断言表内每个 (path, method) 都能在下方分派代码中找到，
# 防止索引与实际能力腐烂不一致。
# methods: 'GET' | 'POST' | 'BOTH'
API_INDEX = [
    ('/help', 'GET', '本索引：端点列表与第一条命令引导'),
    ('/help/<端点>', 'GET', '单个端点的详细用法：参数/返回/示例（如 /help/move）'),
    ('/status', 'GET', '当前局面与游戏状态（建议的第一条命令）'),
    ('/map', 'GET', '棋盘地图与编号'),
    ('/mode', 'BOTH', '查询/切换模式（练习/创造/竞速）'),
    ('/settings', 'BOTH', '查询/修改设置项'),
    ('/analysis/window', 'GET', '局面分析：目标窗'),
    ('/analysis/holes', 'GET', '局面分析：空位（缺口+孔洞）'),
    ('/analysis/actions', 'GET', '局面分析：当前可行动作'),
    ('/solver/algorithms', 'GET', '求解器算法列表'),
    ('/solver/status', 'GET', '求解器运行状态'),
    ('/solver/params', 'BOTH', '查询/修改求解器参数'),
    ('/solve', 'POST', '开始自动求解'),
    ('/solver/cancel', 'POST', '取消求解'),
    ('/solve/status', 'POST', '查询求解进度'),
    ('/macro/list', 'BOTH', '宏列表'),
    ('/macro/status', 'GET', '宏模式状态'),
    ('/macro/record/start', 'POST', '开始录制宏'),
    ('/macro/record/set_base', 'POST', '设置宏基准块'),
    ('/macro/record/stop', 'POST', '停止录制宏'),
    ('/macro/execute', 'POST', '播放指定宏'),
    ('/macro/delete', 'POST', '删除宏'),
    ('/macro/rename', 'POST', '重命名宏'),
    ('/select_gap', 'POST', '选中缝隙'),
    ('/select_block', 'POST', '选中方块'),
    ('/deselect', 'POST', '清空选中'),
    ('/move', 'POST', '移动滑块（direction: w/s/a/d，三角另加 e/z/x，米字格另加 q）'),
    ('/undo', 'POST', '撤销'),
    ('/redo', 'POST', '重做'),
    ('/shuffle', 'POST', '打乱谜题'),
    ('/reset', 'POST', '复原到初始态'),
    ('/new', 'POST', '新开谜题（m/n/step，type 可选 square/numbered/triangle/mi）'),
    ('/map/load', 'POST', '载入地图字符串'),
    ('/file/save', 'POST', '保存进度到文件'),
    ('/file/load', 'POST', '从文件载入进度'),
    ('/timer/status', 'BOTH', '查询计时状态'),
    ('/timer/start', 'POST', '开始计时'),
    ('/timer/stop', 'POST', '停止计时'),
    ('/records', 'BOTH', '成绩记录'),
    ('/screenshot', 'BOTH', '截图（path 可选指定保存位置）'),
    ('/quit', 'POST', '退出游戏'),
    ('/command', 'POST', '通用命令通道（body: {"cmd": "<CLI 指令>"}）'),
]

# 复制给外部程序的连接话术模板（{token}/{port} 占位；GUI 设置-控制页「复制」用）
# 措辞口径：请求方是「外部程序」（AI 助手只是其中一种），不把接口说成 AI 专属
TOKEN_MESSAGE_TEMPLATE = (
    "令牌：{token}。把这段话发给可以在本机发送 http 请求的外部程序（AI 助手是"
    "其中一种），它就能学会控制本机的《貓九的滑塊遊戲》（Gatennea Slider）进程：\n"
    "1. 所有请求的基址是 http://127.0.0.1:{port}，每个请求都要带请求头 "
    "Authorization: Bearer {token}（或在 URL 末尾加 ?token={token}）。\n"
    "2. 先 GET /help 拿到全部 API 索引，GET /help/<端点> 看单个端点的参数与示例，"
    "再 GET /status 查看当前局面，之后按索引自行调用。\n"
    "3. 它只能控制本机上的这个游戏进程；游戏重启后令牌失效，需要重新在游戏"
    "「设置-控制」里复制新令牌。"
)

# 单个端点详情（GET /help/<端点> 与游戏内「下载外部控制教程」同源生成）。
# 每条 = desc 完整说明 / params body 字段表 (name, type, required, desc) /
#       returns 返回字段 / example curl 示例（示例里 $BASE/$TOKEN 为占位）。
# ⚠️ 端点行为变更必须同步改这里——test/_test_external_control.py 断言
# API_INDEX 每条都有详情条目（防止索引与详情腐烂不一致）。
HELP_DETAILS = {
    '/help': {
        'desc': '全部端点索引：路径、方法（GET/POST/BOTH）、一句话说明。'
                '这是外部程序读到的第一份地图，先看它再决定调谁。',
        'params': [],
        'returns': 'JSON：{ok, endpoints:[{path,method,summary}], auth, first_step, note}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/help',
    },
    '/help/<端点>': {
        'desc': '单个端点的详细用法。把索引里的 path 原样接在 /help/ 后面'
                '（如 /help/move），返回完整说明、body 字段表、返回字段和'
                'curl 示例。未知端点返回 404 并提示回 /help 查索引。',
        'params': [],
        'returns': 'JSON：{ok, path, method, summary, description, params:[...], returns, example}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/help/move',
    },
    '/status': {
        'desc': '当前局面全景：谜题描述、步数、是否已复原、矩阵、选中态、'
                'm/n/step、模式、计时器状态、方块列表（含 mod 分组；三角形附 '
                'up 朝向，米字格附 q 朝向与晶格记号）、宏与求解器状态。'
                '建议作为第一条命令——先看清局面再决定动作。',
        'params': [],
        'returns': 'JSON：{ok, puzzle, step_count, solved, matrix, selected_gap, '
                   'selected_block, animating, m, n, step, game_mode, timer_state, '
                   'readonly, blocks:[{row,col,mod,num,(up|q|lat)}], macro, solver}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/status',
    },
    '/map': {
        'desc': '导出当前棋盘的地图字符串（# 墙 / _ 空；数字形态带编号）。'
                '导出的字符串可以原样回灌给 /map/load。',
        'params': [],
        'returns': 'JSON：{ok, map}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/map',
    },
    '/mode': {
        'desc': '查询/切换游戏模式。GET 返回当前模式；POST 切换。'
                '注意：只有 practice（练习）和 timed（竞速）能经接口切换，'
                '创造模式不开放给接口。',
        'params': [('mode', 'string', True, 'practice 或 timed（仅 POST 需要）')],
        'returns': 'JSON：{ok, mode, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"mode":"practice"}\' $BASE/mode',
    },
    '/settings': {
        'desc': '查询/修改设置项。GET 返回当前值；POST 批量修改，只接受白名单'
                '键：16 个布尔开关（coloring_enabled / chain_hint_enabled / '
                'show_metrics_panel / board_marks_enabled / arrows_enabled / '
                'show_virtual_keyboard / show_records_panel / animation_enabled / '
                'selection_animation_enabled / control_single_touch / '
                'control_two_touch / control_mouse_kb / macro_reverse_mode / '
                'save_readonly_flag / prevent_overwrite_flag）加整数项 '
                'animation_duration_ms（50~1000）。未知键或类型不对返回 400。',
        'params': [('<白名单键>', 'bool|int', True, '设置键值对（仅 POST 需要）')],
        'returns': 'JSON：{ok, settings:{...}, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"coloring_enabled":true}\' $BASE/settings',
    },
    '/analysis/window': {
        'desc': '局面分析：目标窗（判定复原用的行/列剖面窗口结构）。'
                '三角形密铺暂不支持，返回 400 且 reason=unsupported。',
        'params': [],
        'returns': 'JSON：{ok, window:[...]}；不支持时 {ok:false, reason:"unsupported"} + HTTP 400',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/analysis/window',
    },
    '/analysis/holes': {
        'desc': '局面分析：空位清单（缺口+孔洞，含坐标与类型），填洞类求解的'
                '决策依据。三角形密铺暂不支持（400 unsupported）。',
        'params': [],
        'returns': 'JSON：{ok, holes:[...]}；不支持时 400 unsupported',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/analysis/holes',
    },
    '/analysis/actions': {
        'desc': '局面分析：当前全部可行动作（含未选中态与选中缝隙态两种口径）。'
                '三角形密铺暂不支持（400 unsupported）。',
        'params': [],
        'returns': 'JSON：{ok, actions:[...]}；不支持时 400 unsupported',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/analysis/actions',
    },
    '/solver/algorithms': {
        'desc': '求解器算法列表（key + 显示名，顺序即游戏设置页展示顺序），'
                '以及当前选中的算法。不同谜题形态的支持范围以设置页选择时的'
                '提示为准（异形上多数算法会明确拒绝）。',
        'params': [],
        'returns': 'JSON：{ok, current, algorithms:[{key,name}]}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/solver/algorithms',
    },
    '/solver/status': {
        'desc': '求解器运行状态：state（idle/running/…）、当前算法、'
                '解法步数（完成后）、梯度聚拢的阶段进度。',
        'params': [],
        'returns': 'JSON：{ok, state, algorithm, result_steps, gradient:{stage,total}}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/solver/status',
    },
    '/solver/params': {
        'desc': '查询/修改聚拢求解参数。GET 返回当前值；POST 修改。'
                '可设键：max_steps / patience / max_wait_time / '
                'target_gather_score / aggressiveness，以及各自的 '
                '<键>_enabled 布尔（false 表示不限制该项）。'
                '注意这些参数只对「单次聚拢」生效。',
        'params': [('<参数键>[|_enabled]', 'number|bool', True, '键值对（仅 POST 需要）')],
        'returns': 'JSON：{ok, params:{key:{value,enabled}}, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"patience":30}\' $BASE/solver/params',
    },
    '/solve': {
        'desc': '开始自动求解（混合求解自动规划）。body 的 algorithm 可选，'
                '缺省用游戏当前设置；求解运行中再调一次 = 取消。'
                '未知算法返回 400 并列出合法值。别名 /solver/solve 同效。',
        'params': [('algorithm', 'string', False, '算法 key，见 /solver/algorithms')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"algorithm":"hybrid"}\' $BASE/solve',
    },
    '/solver/cancel': {
        'desc': '取消正在运行的求解。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/solver/cancel',
    },
    '/solve/status': {
        'desc': '求解进度的一句话状态（旧文本指令保留兼容）：idle / running / '
                'solved(N步) / failed (无解)。',
        'params': [],
        'returns': 'JSON：{ok, message:"idle|running|solved(N步)|failed (无解)"}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/solve/status',
    },
    '/macro/list': {
        'desc': '全部已保存的宏（名称、基准块、步数等）。',
        'params': [],
        'returns': 'JSON：{ok, macros:[...]}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/macro/list',
    },
    '/macro/status': {
        'desc': '宏模式状态：是否录制中、基准块、已录步数。',
        'params': [],
        'returns': 'JSON：{ok, recording, base, steps, ...}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/macro/status',
    },
    '/macro/record/start': {
        'desc': '进入宏录制态（之后的操作会被记录）。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/macro/record/start',
    },
    '/macro/record/set_base': {
        'desc': '设置宏的基准块（宏回放时以哪个方块为锚）。坐标从 1 数。',
        'params': [('row', 'int', True, '行（从 1 数）'),
                   ('col', 'int', True, '列（从 1 数）')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"row":2,"col":3}\' $BASE/macro/record/set_base',
    },
    '/macro/record/stop': {
        'desc': '停止录制并以给定名称保存宏。',
        'params': [('name', 'string', True, '宏名称')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"name":"我的宏"}\' $BASE/macro/record/stop',
    },
    '/macro/execute': {
        'desc': '播放指定宏。base_row/base_col 是回放时对应的基准块坐标；'
                'reverse 可选（默认 false，倒放）。',
        'params': [('name', 'string', True, '宏名称'),
                   ('base_row', 'int', True, '基准块行（从 1 数）'),
                   ('base_col', 'int', True, '基准块列（从 1 数）'),
                   ('reverse', 'bool', False, '倒放，默认 false')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"name":"我的宏","base_row":2,"base_col":3}\' $BASE/macro/execute',
    },
    '/macro/delete': {
        'desc': '删除指定宏。',
        'params': [('name', 'string', True, '宏名称')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"name":"我的宏"}\' $BASE/macro/delete',
    },
    '/macro/rename': {
        'desc': '重命名宏。',
        'params': [('old_name', 'string', True, '原名称'),
                   ('new_name', 'string', True, '新名称')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"old_name":"a","new_name":"b"}\' $BASE/macro/rename',
    },
    '/select_gap': {
        'desc': '选中一条缝隙（刀缝）。选中后 /move 会沿这条缝移动整片。'
                'type：方形 h/v；三角形密铺另加 p/n（3 族缝隙）；米字格另加 '
                'd1/d2（两条对角缝族）。线号合法性由游戏侧判定。',
        'params': [('type', 'string', True, 'h/v（三角加 p/n，米字格加 d1/d2）'),
                   ('line', 'int', True, '缝号线号')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"type":"v","line":3}\' $BASE/select_gap',
    },
    '/select_block': {
        'desc': '选中一个方块。米字格可加 q（N/E/S/W，斜边朝向哪条格边）；'
                '省略时游戏侧取该格第一块。',
        'params': [('row', 'int', True, '行（从 1 数）'),
                   ('col', 'int', True, '列（从 1 数）'),
                   ('q', 'string', False, '仅米字格：N/E/S/W')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"row":2,"col":3}\' $BASE/select_block',
    },
    '/deselect': {
        'desc': '清空当前选中（缝隙/方块）。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/deselect',
    },
    '/move': {
        'desc': '移动滑块。direction：方形 w/s/a/d（上/下/左/右）；三角形密铺'
                '另加 e/z/x（六向）；米字格八向再加 q。合法性由游戏侧判定'
                '（须平行于选中缝隙，或该方向存在可移动的块）。',
        'params': [('direction', 'string', True, 'w/s/a/d；三角另加 e/z/x；米字格另加 q')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"direction":"w"}\' $BASE/move',
    },
    '/undo': {
        'desc': '撤销一步。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/undo',
    },
    '/redo': {
        'desc': '重做一步（撤销的逆操作）。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/redo',
    },
    '/shuffle': {
        'desc': '按当前等级（m/n/step）打乱谜题。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/shuffle',
    },
    '/reset': {
        'desc': '复原到本局初始态（回到这局开始时的局面，不是直接解开）。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/reset',
    },
    '/new': {
        'desc': '新开一局。m/n/step 必填；type 可选 square（默认）/ numbered / '
                'triangle / mi。三角形把 m 当大三角边长 k 用（n 仍须给出）；'
                '米字格 m 行 n 列，每格 4 个单元三角。',
        'params': [('m', 'int', True, '行数（三角为大三角边长 k）'),
                   ('n', 'int', True, '列数'),
                   ('step', 'int', True, '等级（步长）'),
                   ('type', 'string', False, 'square/numbered/triangle/mi，默认 square')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"m":6,"n":6,"step":2}\' $BASE/new',
    },
    '/map/load': {
        'desc': '载入地图字符串（/map 导出的格式：# 墙 / _ 空，数字形态带编号）。',
        'params': [('map', 'string', True, '地图字符串')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"map":"# # # #\\n# _ _ #\\n# # # #"}\' $BASE/map/load',
    },
    '/file/save': {
        'desc': '保存当前进度到文件（绝对路径或相对游戏目录）。',
        'params': [('path', 'string', True, '目标文件路径')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"path":"save1.json"}\' $BASE/file/save',
    },
    '/file/load': {
        'desc': '从文件载入进度。',
        'params': [('path', 'string', True, '存档文件路径')],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"path":"save1.json"}\' $BASE/file/load',
    },
    '/timer/status': {
        'desc': '查询计时状态：ready / running / stopped 及用时。',
        'params': [],
        'returns': 'JSON：{ok, timer_state, elapsed, ...}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/timer/status',
    },
    '/timer/start': {
        'desc': '开始计时（竞速模式）。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/timer/start',
    },
    '/timer/stop': {
        'desc': '停止计时。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/timer/stop',
    },
    '/records': {
        'desc': '成绩记录列表（竞速成绩）。',
        'params': [],
        'returns': 'JSON：{ok, records:[...]}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" $BASE/records',
    },
    '/screenshot': {
        'desc': '给当前画面截图。GET 可带 ?path=<目标>；POST 用 body {"path":...}。'
                'path 缺省时存到游戏目录 screenshots/ 下自动命名（同秒连拍自动加序号）。',
        'params': [('path', 'string', False, '保存路径（query 或 body，均可选）')],
        'returns': 'JSON：{ok, path, width, height}',
        'example': 'curl -H "Authorization: Bearer $TOKEN" "$BASE/screenshot?path=shot.png"',
    },
    '/quit': {
        'desc': '退出游戏进程。',
        'params': [],
        'returns': 'JSON：{ok, message}',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" $BASE/quit',
    },
    '/command': {
        'desc': '通用文本命令通道：body 带 {"cmd":"<指令>"}，等价于 stdin 管道'
                '指令（如 status / map / move w）。适合批量脚本或不便拼 REST '
                '路径的场景；出错时 message 会说明原因。',
        'params': [('cmd', 'string', True, '文本指令，如 "status"、"move w"')],
        'returns': 'JSON：该指令的响应（通常 {ok, message, ...}）',
        'example': 'curl -X POST -H "Authorization: Bearer $TOKEN" '
                   '-H "Content-Type: application/json" '
                   '-d \'{"cmd":"status"}\' $BASE/command',
    },
}


class GameHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器，将请求转化为命令放入 cmd_queue"""

    # 由 start_http_server 设置
    cmd_queue = None

    # 外部控制共享状态（与 GUI 设置-控制页同一个 dict 对象）：
    #   {'enabled': bool, 'token': str|None}
    # enabled=False 或 token 为空时拒绝一切请求；开关重开会换新 token。
    ext_state = None

    # settings 白名单（须与 gui/events.py EventsMixin._SETTINGS_* 保持一致）
    _SETTINGS_BOOL_KEYS = (
        'coloring_enabled', 'chain_hint_enabled', 'show_metrics_panel',
        'board_marks_enabled', 'arrows_enabled',
        'show_virtual_keyboard', 'show_records_panel',
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
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def _check_auth(self):
        """外部控制鉴权（每个业务请求调用）。

        语义：
            开关关闭（enabled=False 或 token 空） → 403 一切拒绝；
            令牌缺失 → 401；令牌不匹配 → 401。
        令牌传递（两种都支持）：
            Authorization: Bearer <token> 请求头（推荐）；
            URL 查询参数 ?token=<token>（不方便加头的客户端）。
        注：stdin 命令通道不设防——能写 stdin 的只有启动它的父进程，天然可信。
        """
        ext = getattr(self, 'ext_state', None) or {}
        if not ext.get('enabled') or not ext.get('token'):
            self._send_json(
                {"ok": False,
                 "message": "外部控制未开启：请在游戏「设置-控制」里打开「允许外部控制」"},
                403)
            return False
        tok = ''
        auth = self.headers.get('Authorization', '')
        if auth.lower().startswith('bearer '):
            tok = auth[7:].strip()
        if not tok:
            from urllib.parse import urlparse, parse_qs
            tok = (parse_qs(urlparse(self.path).query).get('token') or [''])[0].strip()
        if not tok:
            self._send_json(
                {"ok": False,
                 "message": "缺少令牌：请带请求头 Authorization: Bearer <token>，"
                            "或在 URL 上加 ?token=<token>（令牌在游戏「设置-控制」页复制）"},
                401)
            return False
        if tok != ext['token']:
            self._send_json({"ok": False, "message": "令牌无效"}, 401)
            return False
        return True

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
            if not self._check_auth():
                return
            self._dispatch_get(path)
        except Exception:
            # 非致命：控制台输出完整堆栈，HTTP 返回错误
            traceback.print_exc()
            try:
                self._send_json({"ok": False, "message": "服务器内部错误"}, 500)
            except Exception:
                pass

    def _serve_help_detail(self, ep_suffix):
        """GET /help/<端点>：返回单个端点的完整用法（与 HELP_DETAILS 同源）。

        未知端点 → 404 并指回 /help 索引（不静默 404，让调用方知道下一步）。
        """
        ep = '/' + ep_suffix.strip('/')
        detail = HELP_DETAILS.get(ep)
        if detail is None:
            self._send_json({
                "ok": False,
                "message": f"未知端点: {ep}；GET /help 获取全部端点索引",
            }, 404)
            return
        method = next((m for (p, m, _s) in API_INDEX if p == ep), 'GET')
        summary = next((s for (p, _m, s) in API_INDEX if p == ep), '')
        self._send_json({
            "ok": True,
            "path": ep,
            "method": method,
            "summary": summary,
            "description": detail['desc'],
            "params": [
                {"name": n, "type": t, "required": r, "desc": d}
                for (n, t, r, d) in detail.get('params', [])
            ],
            "returns": detail.get('returns', ''),
            "example": detail.get('example', ''),
        })

    def _dispatch_get(self, path):
        # —— 外部控制索引（静态注册表，无需进命令队列）——
        if path == '/help':
            self._send_json({
                "ok": True,
                "message": "Gatennea Slider 外部控制 API 索引",
                "auth": "所有请求带请求头 Authorization: Bearer <token>，"
                        "或 URL 加 ?token=<token>",
                "first_step": "GET /status 查看当前局面，再按下方索引调用",
                "detail": "GET /help/<端点> 查看单个端点的参数/返回/示例，"
                          "如 GET /help/move",
                "note": "stdin 命令通道（子进程管道）不设防，只有启动游戏的父进程能写",
                "endpoints": [
                    {"path": p, "method": m, "summary": s}
                    for (p, m, s) in API_INDEX
                ],
            })
            return
        # '/help/<端点>'：单个端点的参数/返回/示例，如 GET /help/move
        elif path.startswith('/help/'):
            self._serve_help_detail(path[len('/help/'):])
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
        elif path == '/screenshot':
            # 截图：GET /screenshot 或 GET /screenshot?path=<目标>；
            # 缺省存到游戏目录 screenshots/ 下自动命名。回 {ok,path,width,height}
            from urllib.parse import parse_qs, urlparse
            target = (parse_qs(urlparse(self.path).query).get('path') or [''])[0].strip()
            self._send_json(self._post_command(
                f'screenshot {target}' if target else 'screenshot'))
        else:
            self._send_json({"ok": False, "message": f"未知 GET 路径: {path}"}, 404)

    def do_POST(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path.rstrip('/')
        body = self._read_body()
        try:
            if not self._check_auth():
                return
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

        elif path == '/screenshot':
            # 截图（POST）：body 可带 {"path":"<目标路径>"}；缺省自动命名
            result = self._post_command('screenshot', body if body else None)
            self._send_json(result if result else {"ok": False, "message": "未响应"})

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


def start_http_server(cmd_queue, port=5050, ext_state=None):
    """
    启动 HTTP 服务器（daemon 线程）

    参数：
        cmd_queue: 命令队列，HTTP 请求会转化为 (cmd, resp_q) 元组放入
        port: 监听端口，默认 5050
        ext_state: 外部控制共享状态 {'enabled': bool, 'token': str|None}
    返回：
        HTTPServer 实例
    """
    GameHTTPHandler.cmd_queue = cmd_queue
    GameHTTPHandler.ext_state = ext_state if ext_state is not None else {
        'enabled': False, 'token': None}
    server = HTTPServer(('127.0.0.1', port), GameHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[HTTP] 服务已启动: http://127.0.0.1:{port}")
    print(f"[HTTP] 示例: curl http://127.0.0.1:{port}/status")
    return server