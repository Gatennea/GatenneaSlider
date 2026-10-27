# -*- coding: utf-8 -*-
"""排查待办 §九：mi 板型「导入后不单连通 + 无法打乱」。

清单原本推测「仅限模型谜题」，但用户报的是 **mi2（米字档位）**——米字
走 Q_ORDER 8-bit 无损分支（history.py:468），根本不写 engine_state，与模型
板的 lossy 丢块是两回事。这里验证另一条假设：米字有 A/B 两套错开半格的
晶格（history.py:470 注释「斜向一格会产生这种错位态」），一旦打乱进入错位
态，A/B 互不共边 → 连通判定可能判不单连通 → 打乱门（缝枚举为空 / 连通门）
被拦。这解释了「偶发、条件未知」：条件是**随机打乱走出了错位态**。
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

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

_OUT = os.path.join(_PROJ, 'archive', '_mi2.txt')
w = []


def rec(*a):
    w.append(' '.join(str(x) for x in a))


def pts_of(game):
    """块坐标（统一成 (x, y) 二元组）。"""
    out = []
    for b in getattr(game, 'blocks', ()):
        p = getattr(b, 'point', None)
        if p is None:
            p = getattr(b, 'location', None)
        if p is None:
            continue
        out.append(tuple(float(v) for v in list(p)[:2]))
    return out


def main():
    gui = SliderGUI(m=4, n=4, step=1)
    gui.animation_enabled = False
    gui._readonly = False
    gui.save_readonly_flag = False
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()

    if not gui.new_mi_puzzle(2, 2, 1):
        rec('new_mi_puzzle(2,2,1) 失败 msg=', gui.macro_notify_msg)
        return
    rec('mi 局建立：blocks=', len(gui.game.blocks),
        'kind=', getattr(gui.game, 'kind', None))
    rec('has Q_ORDER=', hasattr(gui.game, 'Q_ORDER'),
        'has k=', hasattr(gui.game, 'k'))

    half_seen = 0
    empty_gaps = 0
    for trial in range(25):
        gui.macro_notify_msg = ''
        try:
            gui.shuffle_puzzle()
        except Exception as exc:  # noqa: BLE001
            rec('trial', trial, 'shuffle EXC', repr(exc))
            break
        msg = gui.macro_notify_msg
        pts = pts_of(gui.game)
        half = [p for p in pts if any(abs(v % 1) > 1e-9 for v in p)]
        if half:
            half_seen += 1
        try:
            gaps = gui._ann_all_valid_gaps()
            n_gaps = len(gaps) if gaps is not None else None
        except Exception as exc:  # noqa: BLE001
            n_gaps = 'EXC %r' % (exc,)
        if n_gaps == 0:
            empty_gaps += 1
            rec('  !! trial', trial, 'gaps=0 msg=', repr(msg),
                'blocks=', len(pts), 'half=', len(half))
        if trial < 5:
            rec('  trial', trial, 'blocks=', len(pts), 'half=', len(half),
                'gaps=', n_gaps, 'msg=', repr(msg))
    rec('')
    rec('25 次打乱：出现半格错位块 %d 次；缝枚举为空 %d 次' % (half_seen, empty_gaps))

    # 存档往返（temp_history 同路径）
    sd = gui._build_save_data()
    snap = (sd.get('history') or {}).get('snapshots') or []
    rec('snapshots=', len(snap),
        '带 engine_state 的快照数=',
        sum(1 for s in snap if s.get('engine_state')))
    gui2 = SliderGUI(m=4, n=4, step=1)
    gui2.animation_enabled = False
    gui2._readonly = False
    gui2.save_readonly_flag = False
    gui2.tut_show_prompt = False
    gui2.tutorial_active = False
    pygame.display.set_mode((gui2.screen_width, gui2.screen_height))
    gui2.screen = pygame.display.get_surface()
    gui2._load_save_data(sd)
    p1, p2 = pts_of(gui.game), pts_of(gui2.game)
    rec('往返：块数 %d -> %d' % (len(p1), len(p2)))
    rec('往返：坐标集合一致 =', set(p1) == set(p2))
    rec('载入后 kind=', getattr(gui2.game, 'kind', None),
        'mi_mode=', getattr(gui2, 'mi_mode', None))
    try:
        g2 = gui2._ann_all_valid_gaps()
        rec('载入后 gaps=', len(g2) if g2 is not None else None)
    except Exception as exc:  # noqa: BLE001
        rec('载入后 gaps EXC', repr(exc))


try:
    main()
except Exception:
    import traceback
    w.append('EXC')
    w.append(traceback.format_exc())

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(w))
