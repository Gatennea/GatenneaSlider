# -*- coding: utf-8 -*-
"""待办 §九 复现尝试：mi2（**模型文件**，48 块、标准三角基、ps=1）反复
「打乱 → 存档往返 → 检查块数 / 单连通 / 可打乱」。

已排除的两个方向（本次排查结论）：
  * 米字**档位**不是嫌疑：打乱虽每次都产生 6~12 个半格错位块，但缝枚举
    恒为 8~12 条（打乱门不会空），且存档往返 16→16 坐标集合一致（无损）。
  * mi2 不是米字档位而是 models/mi2.json（三角基模型），EngineGame 只在
    kind=='mi' 时挂 Q_ORDER，故 mi2 仍走 engine_state 无损分支。

这里压模型板型本身：看会不会出现「往返后块数变少 / 不单连通 / 缝枚举为空」。
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

_OUT = os.path.join(_PROJ, 'archive', '_mi2b.txt')
w = []
ROUNDS = 12


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
    """连通分量数（异常返回 -1）。"""
    try:
        spec = gui.game.spec
        return len(spec.components(frozenset(gui.game.board.keys)))
    except Exception as exc:  # noqa: BLE001
        w.append('    （分量计算失败：%r）' % (exc,))
        return -1


def main():
    gui = _gui()
    if not gui.new_model_puzzle('mi2', 1):
        rec('mi2 建局失败 msg=', gui.macro_notify_msg)
        return
    n0 = len(gui.game.blocks)
    rec('mi2: blocks=', n0, 'kind=', getattr(gui.game, 'kind', None),
        'has Q_ORDER=', hasattr(gui.game, 'Q_ORDER'),
        'has k=', hasattr(gui.game, 'k'))
    rec('初始 分量=', comps(gui))

    bad = []
    for i in range(ROUNDS):
        gui.macro_notify_msg = ''
        try:
            gui.shuffle_puzzle()
        except Exception as exc:  # noqa: BLE001
            rec('round', i, 'shuffle EXC', repr(exc))
            break
        sd = gui._build_save_data()
        snaps = (sd.get('history') or {}).get('snapshots') or []
        n_es = sum(1 for s in snaps if s.get('engine_state'))
        gui2 = _gui()
        try:
            gui2._load_save_data(sd)
        except Exception as exc:  # noqa: BLE001
            rec('round', i, 'load EXC', repr(exc))
            break
        n1, n2 = len(gui.game.blocks), len(gui2.game.blocks)
        c2 = comps(gui2)
        try:
            g2 = gui2._ann_all_valid_gaps()
            ng = len(g2) if g2 is not None else None
        except Exception as exc:  # noqa: BLE001
            ng = 'EXC %r' % (exc,)
        ok = (n1 == n2) and (c2 == 1) and (ng not in (0, None))
        if not ok:
            bad.append((i, n1, n2, c2, ng, n_es, len(snaps)))
            rec('  !! round', i, 'blocks', n1, '->', n2, 'comps=', c2,
                'gaps=', ng, 'es=', n_es, '/', len(snaps))
        elif i < 3:
            rec('  round', i, 'blocks', n1, '->', n2, 'comps=', c2,
                'gaps=', ng, 'es=', n_es, '/', len(snaps))
    rec('')
    rec('%d 轮：异常 %d 轮' % (ROUNDS, len(bad)))
    if not bad:
        rec('未复现：mi2 往返块数一致、恒单连通、缝枚举恒非空。')
        rec('→ §九 的根因不在「模型板型存档往返」这条路径上，需换方向：')
        rec('  ① 旧档 / 跨版本（快照缺 engine_state 的 lossy 分支）；')
        rec('  ② 启动时的恢复路径与 _load_save_data 不同步；')
        rec('  ③ 打乱后未存盘就退出（temp_history 记的是更早的快照）。')


try:
    main()
except Exception:
    import traceback
    w.append('EXC')
    w.append(traceback.format_exc())

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(w))
