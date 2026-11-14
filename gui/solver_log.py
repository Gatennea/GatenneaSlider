# -*- coding: utf-8 -*-
"""求解器日志：每一次求解落一份「比成绩记录更细」的复盘材料。

为什么要有它（2026-11-14 用户提的待办）：
成绩记录只回答「这盘多少步、多久」，回答不了「为什么慢」「哪一段在空转」。
排查求解器的人要的是每次求解的**过程**：什么算法、什么形态参数、开跑时
聚拢度多少、每个阶段播了几步、各阶段耗时、停机原因、终态聚拢度。
这些不写下来就只能靠口头描述，落不到具体那一段上。

开关：设置 → 求解器页「求解器日志」（config.json 的 solver_log_enabled），
默认关闭。关着时 begin() 直接返回 None，不建目录、不写文件。
存放：config/solver_log.jsonl，一行一次求解（与 op_log 同风格）；打包成
exe 后 config/ 可能不可写，按 log_writer 的优先级退 %APPDATA%/GatenneaSlider/
再退系统 temp——宁可写到别处，也不能让「记日志」把求解搞崩。
查询：HTTP GET /solver/log（列表）、GET /solver/log/<id>（单次完整明细）。

⚠️ 只记过程，不记每一帧动画；日志是排障附属品，任何写盘/序列化异常
一律静默吞掉，绝不影响求解本身。
"""
import json
import os
import sys
import tempfile
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(_HERE)
LOG_PATH = os.path.join(BASE_DIR, 'config', 'solver_log.jsonl')
_FALLBACK_PATH = os.path.join(tempfile.gettempdir(), 'gatenneaslider_solver_log.jsonl')

# 单文件上限：超过就在追加前把文件瘦身成最近 _KEEP_ENTRIES 条，避免无限长大
_MAX_BYTES = 2 * 1024 * 1024
_KEEP_ENTRIES = 200

# 单次求解最多记多少阶段（梯度/自查循环可能跨很多轮，别把文件撑爆）
_MAX_STAGES = 200

# 阶段条目里要从求解结果里抄下来的字段
_STAGE_KEYS = (
    'type', 'label', 'solved', 'reason', 'score', 'phi', 'streamed',
    'gradient_stage', 'gradient_total', 'nodes', 'expanded', 'visited',
    'iterations', 'depth', 'elapsed_ms', 'duration_ms', 'rep_cells',
)


def log_paths():
    """按优先级返回候选日志路径（写时逐个试，写进第一个成功的）。"""
    if getattr(sys, 'frozen', False):
        paths = [os.path.join(os.path.dirname(sys.executable),
                              'config', 'solver_log.jsonl')]
        appdata = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
        if appdata:
            paths.append(os.path.join(appdata, 'GatenneaSlider',
                                      'solver_log.jsonl'))
    else:
        paths = [LOG_PATH]
    paths.append(_FALLBACK_PATH)
    return paths


def _trim(path):
    """超过单文件上限时只保留最近若干条（放弃更早的，够复盘最近问题）。"""
    try:
        if not os.path.exists(path) or os.path.getsize(path) <= _MAX_BYTES:
            return
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        lines = lines[-(_KEEP_ENTRIES - 1):]   # 留一格给马上要追加的新记录
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception:
        pass


def _append(rec):
    """追加一条记录；返回实际写入路径（全失败返回 None，不抛）。"""
    line = json.dumps(rec, ensure_ascii=False, default=str) + '\n'
    for path in log_paths():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _trim(path)
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line)
            return path
        except Exception:
            continue
    return None


def _metrics(game, gui=None):
    """当前牌面的聚拢度 / Φ（算不出来就返回空 dict，绝不抛）。"""
    try:
        from solver.ml.gather_solver import gather_metrics
        from solver.auto_solver import _phi_of
        coords = frozenset(tuple(b.location) for b in game.blocks)
        m = getattr(gui, 'game', game).m
        n = getattr(gui, 'game', game).n
        info = gather_metrics(coords, m, n)
        try:
            phi = _phi_of(coords, m, n)
        except Exception:
            phi = None
        return {'score': info.get('score'), 'phi': phi,
                'coords': sorted([list(c) for c in coords])}
    except Exception:
        return {}


def _puzzle_meta(gui):
    game = getattr(gui, 'game', None)
    form = 'square'
    try:
        form = gui._current_puzzle_form()
    except Exception:
        pass
    return {
        'form': form,
        'm': getattr(game, 'm', None),
        'n': getattr(game, 'n', None),
        'step': getattr(gui, 'current_step', None),
        'blocks': len(getattr(game, 'blocks', []) or []),
        'numbered': bool(getattr(game, 'numbered', False)),
    }


def _params(gui):
    return {
        'gather_params': dict(getattr(gui, 'gather_params', {}) or {}),
        'max_wait_time': getattr(gui, 'max_wait_time', None),
        'thinking_enabled': bool(getattr(gui, 'thinking_enabled', False)),
        'animation_enabled': bool(getattr(gui, 'animation_enabled', True)),
        'ui_mode': getattr(gui, 'ui_mode', ''),
    }


def enabled(gui) -> bool:
    return bool(getattr(gui, 'solver_log_enabled', False))


def begin(gui, algorithm):
    """一次求解开始时调用。返回记录 dict（开关关着返回 None）。"""
    gui._solver_log_rec = None
    gui._solver_log_t0 = None
    if not enabled(gui):
        return None
    try:
        rec = {
            'id': time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:4],
            'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'algorithm': algorithm,
            'puzzle': _puzzle_meta(gui),
            'params': _params(gui),
            'start_metrics': _metrics(getattr(gui, 'game', None), gui),
            'stages': [],
        }
    except Exception:
        return None
    gui._solver_log_rec = rec
    gui._solver_log_t0 = time.time()
    return rec


def stage(gui, label, payload):
    """记一个阶段（段到货 / 梯度一轮 / 聚拢一轮）。无记录时什么都不做。"""
    rec = getattr(gui, '_solver_log_rec', None)
    if not rec:
        return
    if len(rec['stages']) >= _MAX_STAGES:
        return
    try:
        t0 = getattr(gui, '_solver_log_t0', None) or time.time()
        ent = {
            'i': len(rec['stages']) + 1,
            'label': str(label),
            't_ms': int(round((time.time() - t0) * 1000)),
        }
        if isinstance(payload, dict):
            for k in _STAGE_KEYS:
                if k in payload:
                    v = payload[k]
                    if k == 'actions':
                        v = len(v or [])
                    elif k == 'rep_cells':
                        v = len(v or [])
                    ent[k] = v if isinstance(v, (int, float, str, bool, type(None))) \
                        else str(v)
            if 'actions' in payload:
                ent['actions'] = len(payload.get('actions') or [])
            # 聚拢结果把指标放在 start/end 两段里（方形单次/梯度都是这套口径），
            # 只抄 score/phi，别把整张坐标表再存一遍。
            for k in ('start', 'end'):
                v = payload.get(k)
                if isinstance(v, dict):
                    ent[k] = {kk: v.get(kk) for kk in ('score', 'phi')
                              if kk in v}
        rec['stages'].append(ent)
    except Exception:
        pass


def finish(gui, outcome, reason='', steps=None):
    """一次求解结束时调用：补齐终态、写盘、清空当前记录（幂等）。"""
    rec = getattr(gui, '_solver_log_rec', None)
    if not rec:
        return None
    gui._solver_log_rec = None
    try:
        t0 = getattr(gui, '_solver_log_t0', None) or time.time()
        rec['ended_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        rec['duration_ms'] = int(round((time.time() - t0) * 1000))
        rec['outcome'] = str(outcome or '')
        rec['reason'] = str(reason or '')
        if steps is None:
            # 没给总步数（梯度各轮没有总账）：按已记阶段的动作数累加
            steps = sum(int(s.get('actions') or 0) for s in rec.get('stages') or [])
        rec['steps'] = steps
        rec['end_metrics'] = _metrics(getattr(gui, 'game', None), gui)
        # 求解器自己报的终态指标优先：写日志时盘面还没播完动画，按盘面算出来
        # 的其实是「开跑态」，会误导复盘。末段的 end 才是求解器给出的结果。
        last_end = None
        for s in reversed(rec.get('stages') or []):
            if s.get('end'):
                last_end = s['end']
                break
        if last_end:
            rec['end_metrics'] = dict(last_end, source='solver_stage')
        try:
            rec['solved'] = bool(gui.is_solved())
        except Exception:
            pass
        _append(rec)
    except Exception:
        return None
    return rec


# ---------------------------------------------------------------- 读取侧
def _read_lines():
    for path in log_paths():
        try:
            if not os.path.exists(path):
                continue
            with open(path, 'r', encoding='utf-8') as f:
                return path, f.readlines()
        except Exception:
            continue
    return None, []


def list_entries(limit=20):
    """最近若干次求解的摘要（新的在前），供 HTTP /solver/log 用。"""
    path, lines = _read_lines()
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        out.append({
            'id': rec.get('id'),
            'started_at': rec.get('started_at'),
            'algorithm': rec.get('algorithm'),
            'form': (rec.get('puzzle') or {}).get('form'),
            'm': (rec.get('puzzle') or {}).get('m'),
            'n': (rec.get('puzzle') or {}).get('n'),
            'step': (rec.get('puzzle') or {}).get('step'),
            'outcome': rec.get('outcome'),
            'reason': rec.get('reason'),
            'steps': rec.get('steps'),
            'duration_ms': rec.get('duration_ms'),
            'stage_count': len(rec.get('stages') or []),
        })
        if len(out) >= max(1, int(limit)):
            break
    return {'ok': True, 'dir': os.path.dirname(path) if path else None,
            'path': path, 'count': len(out), 'entries': out}


def load_entry(sid):
    """按 id 取一次求解的完整记录；找不到返回 None。"""
    if not sid:
        return None
    sid = str(sid)
    if not all(ch.isalnum() or ch in '-_' for ch in sid):
        return None  # 防路径/注入：id 只可能是生成时的字母数字与横线
    _path, lines = _read_lines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get('id') == sid:
            return rec
    return None
