# -*- coding: utf-8 -*-
"""待办 §九 第四轮：确认「无法打乱」那一半症状。

_dbg_mi2c 已证实：缺 engine_state 的 mi2 旧档载入 → 48 块掉到 ~30、连通分量
1 → 13/14（「不单连通」坐实）。但缝枚举仍有 6~10 条，打乱门的冻形预检不会拦，
所以「无法打乱」还没对上。这里直接在那个坏盘面上按一次打乱，看：
  · macro_notify_msg 会不会冒出「无法打乱…」；
  · 打乱后块数 / 连通分量变成什么（是不是越打越碎）。
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

import json  # noqa: E402
import random  # noqa: E402
import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from engine import model_registry  # noqa: E402
from gui.file_ops import _compute_checksum  # noqa: E402

_OUT = os.path.join(_PROJ, 'archive', '_mi2d.txt')
w = []


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
        return len(gui.game.spec.components(frozenset(gui.game.board.keys)))
    except Exception as exc:  # noqa: BLE001
        return 'EXC %r' % (exc,)


def snap(gui):
    return (len(gui.game.board.keys), comps(gui))


def main():
    model_registry.install()
    gui = _gui()
    if not gui.new_model_puzzle('mi2', 1):
        rec('建局失败', gui.macro_notify_msg)
        return
    rng = random.Random(7)
    b = gui.game.board
    for _ in range(10):
        ms = b.legal_moves(1)
        if not ms:
            break
        b = b.apply(rng.choice(ms))
    gui.game.board = b
    gui.game.update_matrix()
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    sd = gui._build_save_data()

    sd_bad = json.loads(json.dumps(sd, ensure_ascii=False))
    for s in sd_bad['history']['snapshots']:
        s.pop('engine_state', None)
    sd_bad['checksum'] = _compute_checksum(sd_bad)

    bad = _gui()
    bad._load_save_data(sd_bad)
    rec('坏盘载入后：', snap(bad), '（原始应为 48 块、1 个连通分量）')
    try:
        g = bad._ann_all_valid_gaps()
        rec('  缝枚举 =', len(g) if g is not None else None)
    except Exception as exc:  # noqa: BLE001
        rec('  缝枚举 EXC', repr(exc))

    bad.macro_notify_msg = ''
    try:
        bad.shuffle_puzzle()
    except Exception as exc:  # noqa: BLE001
        rec('  打乱 EXC', repr(exc))
    rec('  打乱后 msg =', repr(bad.macro_notify_msg))
    rec('  打乱后盘面：', snap(bad))

    # 对照：好盘（带 engine_state）打乱
    good = _gui()
    good._load_save_data(sd)
    rec('好盘载入后：', snap(good))
    good.macro_notify_msg = ''
    try:
        good.shuffle_puzzle()
    except Exception as exc:  # noqa: BLE001
        rec('  打乱 EXC', repr(exc))
    rec('  打乱后 msg =', repr(good.macro_notify_msg))
    rec('  打乱后盘面：', snap(good))


try:
    main()
except Exception:
    import traceback
    w.append('EXC')
    w.append(traceback.format_exc())

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(w))
