# -*- coding: utf-8 -*-
"""护栏：求解器日志（2026-11-14 用户待办 §四十四 第 2 条）。

判据（行为，不查源码子串）：
  L1 开关关着：begin 返回 None，不建目录、不写文件
  L2 开关开着：begin → stage ×2 → finish 落一条完整记录（字段齐全）
  L3 finish 幂等：同一次求解只写一条，重复调用是空操作
  L4 列表 / 按 id 取明细可用；非法 id 一律取不到（不越界读文件）
  L5 步数缺省时按各阶段动作数累加；文件超限会瘦身成最近若干条
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gui import solver_log  # noqa: E402

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


class _Blk:
    def __init__(self, r, c):
        self.location = [r, c]


class _Game:
    m = 5
    n = 5
    numbered = False

    def __init__(self):
        self.blocks = [_Blk(0, 0), _Blk(0, 1), _Blk(1, 0)]


class _Gui:
    solver_log_enabled = True
    current_step = 2
    gather_params = {'max_steps': 4, 'patience': 10}
    max_wait_time = 8
    thinking_enabled = True
    animation_enabled = True
    ui_mode = 'enhanced'

    def __init__(self):
        self.game = _Game()

    def _current_puzzle_form(self):
        return 'square'

    def is_solved(self):
        return False


def _stage_payload(i, ops=2, solved=False):
    return {'type': 'gather', 'actions': [('h', 0, 'a', 'x')] * ops,
            'score': 0.5 + i * 0.1, 'phi': 0.3, 'solved': solved,
            'reason': 'max_steps', 'gradient_stage': i,
            'nodes': 1000 + i}


def main():
    td = tempfile.mkdtemp(prefix='solverlog_')
    solver_log.LOG_PATH = os.path.join(td, 'solver_log.jsonl')
    solver_log._FALLBACK_PATH = os.path.join(td, 'fallback.jsonl')
    path = solver_log.LOG_PATH

    # L1 关着不写
    g0 = _Gui()
    g0.solver_log_enabled = False
    check('L1a 关闭时 begin 返回 None', solver_log.begin(g0, 'gather') is None)
    check('L1b 关闭时 finish 不写文件',
          solver_log.finish(g0, 'solved') is None and not os.path.exists(path))

    # L2 开着落一条完整记录
    g = _Gui()
    rec = solver_log.begin(g, 'hybrid')
    check('L2a begin 返回记录且带 id/算法/形态/参数', bool(
        rec and rec.get('id') and rec['algorithm'] == 'hybrid'
        and rec['puzzle']['form'] == 'square'
        and rec['puzzle']['m'] == 5
        and 'gather_params' in rec['params']
        and isinstance(rec['stages'], list)), repr(rec and list(rec)))
    solver_log.stage(g, 'hybrid_stage', _stage_payload(1, ops=2))
    solver_log.stage(g, 'hybrid_stage', _stage_payload(2, ops=3, solved=True))
    fin = solver_log.finish(g, 'solved', 'solved', 5)
    check('L2b finish 落盘并补终态', bool(
        fin and fin['outcome'] == 'solved' and fin['steps'] == 5
        and fin['duration_ms'] >= 0 and os.path.exists(path)),
        repr(fin and (fin['outcome'], fin['steps'])))
    check('L2c 阶段动作数被规约成 int（不是整张 list）',
          [s['actions'] for s in rec['stages']] == [2, 3]
          and rec['stages'][0]['nodes'] == 1001,
          repr([s.get('actions') for s in rec['stages']]))

    with open(path, encoding='utf-8') as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    check('L2d 一次求解只占一行', len(lines) == 1, str(len(lines)))
    stored = json.loads(lines[0])
    check('L2e 落盘字段齐全',
          all(k in stored for k in ('id', 'started_at', 'algorithm', 'puzzle',
                                    'params', 'stages', 'ended_at',
                                    'duration_ms', 'outcome', 'steps')),
          str(sorted(stored)))

    # L3 幂等
    check('L3 finish 幂等（第二次空操作）',
          solver_log.finish(g, 'solved') is None
          and len(open(path, encoding='utf-8').read().splitlines()) == 1)

    # L4 读取
    lst = solver_log.list_entries(10)
    check('L4a 列表可用且新的在前',
          lst.get('ok') and lst['count'] == 1
          and lst['entries'][0]['id'] == stored['id']
          and lst['entries'][0]['stage_count'] == 2,
          repr(lst.get('entries')))
    ent = solver_log.load_entry(stored['id'])
    check('L4b 按 id 取到完整明细', bool(ent and ent['id'] == stored['id']))
    check('L4c 路径型 id 一律拒绝（types.. 遍历不出去）',
          solver_log.load_entry('../config.json') is None
          and solver_log.load_entry('x/y') is None)

    # L5 步数缺省累加 + 瘦身
    g2 = _Gui()
    solver_log.begin(g2, 'gather')
    solver_log.stage(g2, 'gather_stage', _stage_payload(1, ops=2))
    solver_log.stage(g2, 'gather_stage', _stage_payload(2, ops=4))
    f2 = solver_log.finish(g2, 'partial', 'partial_best', None)
    check('L5a steps=None 时按阶段动作数累加',
          bool(f2 and f2['steps'] == 6), repr(f2 and f2['steps']))

    solver_log._MAX_BYTES = 200   # 逼出瘦身分支
    solver_log._KEEP_ENTRIES = 2
    for i in range(6):
        gg = _Gui()
        solver_log.begin(gg, f'algo{i}')
        solver_log.stage(gg, 's', _stage_payload(1))
        solver_log.finish(gg, 'solved', 'solved', 1)
    with open(path, encoding='utf-8') as f:
        left = [l for l in f.read().splitlines() if l.strip()]
    check('L5b 超限自动瘦身（只剩最近若干条）',
          0 < len(left) <= 2, str(len(left)))

    print('==== %s（%d 项失败）====' %
          ('全部通过' if not FAILS else '有失败', len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
