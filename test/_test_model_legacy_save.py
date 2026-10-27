# -*- coding: utf-8 -*-
r"""模型板「旧档缺 engine_state」护栏（待办 §九 定位结论的回归，2026-10-28）。

用户报：临时历史记录（temp_history）偶尔导入成**不单连通**的图案，且**无法打乱**
（mi2 谜题，仅一次，条件未知）。

**已定位**（`archive/scratch_2026-10-28/_dbg_mi2c.py` / `_dbg_mi2d.py` 实测）：
`engine_state`（无损键表）是承重字段。模型板型（mi2：48 块、标准三角基、
pos_scale=1）同 2D 格可叠多块（不同朝向），矩阵编码会把同格多块压成一格；
`restore_snapshot` 一旦拿不到 `engine_state` 就回退 lossy 的 matrix 重建 →
48 块掉到 ~30、**连通分量 1 → 13/14**（症状一：不单连通）；坏盘上打乱只能走出
**0 步**（`已打乱：0步`，好盘是 61 步）→ 症状二「无法打乱」。

触发条件因此也清楚了：**只有载入「修复前写下的旧档」才会中**（之后每次保存都带
engine_state），这与用户「仅遇到一次、条件未知」完全吻合。

本护栏固化两件事（不提修法——修法是待定项，见 `docs/agent/待办清单.md` §九）：
  1. 带 engine_state 的 mi2 存档往返：块数 / 单连通 / 打乱步数都不变（正向）；
  2. 剥掉 engine_state 的同份存档（= 旧档口径）：必丢块 + 不再单连通（反向，
     证明该字段承重、也证明旧档就是这么坏的）。

跑法：D:/python/python.exe test/_test_model_legacy_save.py
"""
import os
import sys
import json
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from engine import model_registry  # noqa: E402
from gui.file_ops import _compute_checksum  # noqa: E402

FAILS = []

# 只取一个 seed：引擎层 48 块随机游走 + 两次载入已够慢，护栏要能进全套
SEED = 7
STEPS = 10


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('    FAIL:', msg)
    return bool(cond)


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


def _components(gui):
    return len(gui.game.spec.components(frozenset(gui.game.board.keys)))


def _mi2_walked_save():
    """建 mi2 局 → 引擎层随机游走 10 步 → 存档（带 engine_state）。"""
    gui = _gui()
    if not gui.new_model_puzzle('mi2', 1):
        check(False, f'mi2 应能开局（msg={gui.macro_notify_msg}）')
        return None, None
    rng = random.Random(SEED)
    b = gui.game.board
    for _ in range(STEPS):
        ms = b.legal_moves(1)
        if not ms:
            break
        b = b.apply(rng.choice(ms))
    gui.game.board = b
    gui.game.update_matrix()
    gui.game_history.reset()
    gui.game_history.save_snapshot(gui.game)
    sd = gui._build_save_data()
    return sd, (len(gui.game.board.keys), _components(gui))


def _load(sd):
    gui = _gui()
    gui._load_save_data(sd)
    return gui


def t_good_roundtrip_is_lossless():
    sd, cur = _mi2_walked_save()
    if sd is None:
        return
    n0, c0 = cur
    check(n0 == 48, f'mi2 应为 48 块（实测 {n0}）')
    check(c0 == 1, f'游走后仍应单连通（实测分量 {c0}）')
    snaps = sd['history']['snapshots']
    check(all(s.get('engine_state') for s in snaps),
          '模型板每条快照落盘都必须带 engine_state')
    gui = _load(json.loads(json.dumps(sd, ensure_ascii=False)))
    check(len(gui.game.board.keys) == n0,
          f'完整往返块数应不变（{len(gui.game.board.keys)} vs {n0}）')
    check(_components(gui) == 1,
          f'完整往返应仍单连通（实测分量 {_components(gui)}）')


def t_missing_engine_state_is_broken():
    """反向护栏：缺 engine_state = 旧档口径，必丢块 + 不单连通（§九 的两个症状）。"""
    sd, cur = _mi2_walked_save()
    if sd is None:
        return
    n0 = cur[0]
    bad = json.loads(json.dumps(sd, ensure_ascii=False))
    for s in bad['history']['snapshots']:
        s.pop('engine_state', None)
    bad['checksum'] = _compute_checksum(bad)  # 模拟「旧档本就没这字段」，非篡改
    gui = _load(bad)
    n1 = len(gui.game.board.keys)
    c1 = _components(gui)
    check(n1 < n0, f'缺 engine_state 必丢块（{n1} < {n0}）——§九 症状一的成因')
    check(c1 > 1, f'缺 engine_state 后不再单连通（分量 {c1}）——用户看到的碎盘')


def t_bad_board_cannot_shuffle():
    """症状二：坏盘上按打乱 → `已打乱：0步`（好盘同条件下是几十步）。

    缝枚举在这种碎盘上仍非空（6~10 条），所以冻形预检**拦不住**——门过了、
    打乱却一步走不动，玩家看到的就是「按了打乱没反应」。
    """
    sd, _cur = _mi2_walked_save()
    if sd is None:
        return
    gui = _load(json.loads(json.dumps(sd, ensure_ascii=False)))
    gui.macro_notify_msg = ''
    gui.shuffle_puzzle()
    good_msg = gui.macro_notify_msg
    check('0步' not in good_msg,
          f'好盘打乱应有步数（实测 msg={good_msg!r}）')

    bad = json.loads(json.dumps(sd, ensure_ascii=False))
    for s in bad['history']['snapshots']:
        s.pop('engine_state', None)
    bad['checksum'] = _compute_checksum(bad)
    gui2 = _load(bad)
    gui2.macro_notify_msg = ''
    gui2.shuffle_puzzle()
    check('0步' in gui2.macro_notify_msg,
          f'坏盘打乱应一步都走不动（实测 msg={gui2.macro_notify_msg!r}）'
          '——§九 症状二「无法打乱」的成因')


def main():
    model_registry.install()
    t_good_roundtrip_is_lossless()
    t_missing_engine_state_is_broken()
    t_bad_board_cannot_shuffle()
    print()
    if FAILS:
        print(f'共 {len(FAILS)} 项失败：')
        for f in FAILS:
            print('  ·', f)
        sys.exit(1)
    print('模型板旧档护栏：全部通过（缺 engine_state 必丢块 + 碎成多块 + 打乱 0 步）')


if __name__ == '__main__':
    main()
