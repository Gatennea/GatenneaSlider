# -*- coding: utf-8 -*-
"""待办 §九 复现尝试（第三轮，2026-10-28）：验证「旧档缺 engine_state」假说。

前两轮的结论：
  * mi2 是 models/mi2.json（48 块、标准三角基、ps=1）→ 走 engine_state 无损分支；
  * 米字档位、engine_state 不落盘两条已被排除；
  * mi2 打乱在本沙箱太慢，_dbg_mi2b 跑不出结果。

本轮换法：不做 shuffle（太慢），改**引擎层随机游走**造出非复原盘面，然后对比
两条载入路径：
  A. 完整存档（带 engine_state）→ 载入；
  B. 剥掉 engine_state 的同一份存档（= 修复前的旧档口径）→ 载入。

看 B 是否复现用户描述的两个症状：**块数变少 / 不单连通 / 缝枚举为空（无法打乱）**。
若是 → 「旧档跨版本」假说成立，§九 可定位；若否 → 该假说也要排除。
"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))  # archive/scratch_2026-10-28/ → 项目根
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import random  # noqa: E402
import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from engine import model_registry  # noqa: E402
from gui.file_ops import _compute_checksum  # noqa: E402

_OUT = os.path.join(_PROJ, 'archive', '_mi2c.txt')
w = []
STEPS = 10
SEEDS = (1, 7, 23)


def rec(*a):
    w.append(' '.join(str(x) for x in a))


def _gui():
    g = SliderGUI(m=4, n=4, step=1)
    g.animation_enabled = False
    g._readonly = False
    g.save_readonly_flag = False
    g.tut_show_prompt = False
    g.tutorial_active = False
    pygame.display.set_mode((g.screen_width, g.screen_height))
    g.screen = pygame.display.get_surface()
    return g


def comps(gui):
    try:
        spec = gui.game.spec
        return len(spec.components(frozenset(gui.game.board.keys)))
    except Exception as exc:  # noqa: BLE001
        return 'EXC %r' % (exc,)


def gaps(gui):
    """打乱门用的缝枚举（session.shuffle_puzzle 的冻形预检）。"""
    try:
        g2 = gui._ann_all_valid_gaps()
        return len(g2) if g2 is not None else None
    except Exception as exc:  # noqa: BLE001
        return 'EXC %r' % (exc,)


def walk(gui, steps, seed):
    """引擎层随机游走，把终态灌回适配器（不经 GUI 动画）。"""
    rng = random.Random(seed)
    b = gui.game.board
    done = 0
    for _ in range(steps):
        ms = b.legal_moves(1)
        if not ms:
            break
        b = b.apply(rng.choice(ms))
        done += 1
    gui.game.board = b
    gui.game.update_matrix()
    return done


def probe(gui, sd, tag):
    g2 = _gui()
    try:
        g2._load_save_data(sd)
    except Exception as exc:  # noqa: BLE001
        rec('   ', tag, 'load EXC', repr(exc))
        return None
    return (len(g2.game.board.keys), comps(g2), gaps(g2))


def main():
    model_registry.install()
    gui = _gui()
    if not gui.new_model_puzzle('mi2', 1):
        rec('mi2 建局失败 msg=', gui.macro_notify_msg)
        return
    n0 = len(gui.game.board.keys)
    rec('mi2 开局：keys=', n0, 'comps=', comps(gui), 'gaps=', gaps(gui))

    for seed in SEEDS:
        gui = _gui()
        gui.new_model_puzzle('mi2', 1)
        done = walk(gui, STEPS, seed)
        gui.game_history.reset()
        gui.game_history.save_snapshot(gui.game)
        sd = gui._build_save_data()
        snaps = (sd.get('history') or {}).get('snapshots') or []
        has_es = sum(1 for s in snaps if s.get('engine_state'))
        cur = (len(gui.game.board.keys), comps(gui), gaps(gui))

        sd_bad = None
        import json
        sd_bad = json.loads(json.dumps(sd, ensure_ascii=False))
        for s in sd_bad['history']['snapshots']:
            s.pop('engine_state', None)
        sd_bad['checksum'] = _compute_checksum(sd_bad)

        a = probe(_gui(), sd, 'A(带es)')
        b = probe(_gui(), sd_bad, 'B(剥es)')
        rec('seed', seed, '游走', done, '步 | 当前', cur,
            '| 快照带es', has_es, '/', len(snaps))
        rec('     A 完整往返 ->', a)
        rec('     B 缺es 旧档 ->', b)
        if a and b:
            rec('     结论：块数', a[0], '->', b[0],
                '；连通分量', a[1], '->', b[1],
                '；缝数', a[2], '->', b[2])
            if b[0] < a[0] or b[1] != 1 or b[2] in (0, None):
                rec('     !! 缺 engine_state 复现了「丢块/不连通/无法打乱」')


try:
    main()
except Exception:
    import traceback
    w.append('EXC')
    w.append(traceback.format_exc())

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(w))
