# -*- coding: utf-8 -*-
r"""模型板存档无损往返（2026-10-27 修 bug 的回归护栏）。

用户 2026-10-26 报：导入 shield 存档，末态明明是复原态，游戏却判「未复原」。
根因：`_build_save_data` 序列化快照时漏写 `engine_state`（模型板带朝向、同格多
块的**无损键表**），落盘只剩 lossy 的 `matrix+bounds`；载入回退到矩阵重建，把同
格多块（shield 有 11 对）永久压掉 → 还原态永不等于目标。内存态 `restore_snapshot`
本就优先用 `engine_state`，只是磁盘没带它。

本脚本验两件事：
  1. 修复后：模型板存档含 `engine_state`，JSON 往返后载入 → 复原态仍判复原、块数
     一个不丢；
  2. 反向：同一份存档若剥掉 `engine_state`（= 修复前的旧档），载入必丢块、判不到
     复原——证明该字段是承重字段，不能误删。

跑法：D:/python/python.exe test/_test_model_save_roundtrip.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from engine import model_registry  # noqa: E402
from gui.file_ops import _compute_checksum  # noqa: E402

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('    FAIL:', msg)
    return bool(cond)


def _fresh_gui():
    g = SliderGUI(m=4, n=4, step=1)
    g.animation_enabled = False
    return g


def _build_shield_save():
    """建一局 shield（开局即复原态），真实落盘，返回 (save_data, blocks_goal)。"""
    model_registry.install()
    gui = _fresh_gui()
    ok = gui.new_model_puzzle('shield', 1)
    check(ok, 'shield 应能开局')
    if not ok:
        return None, 0
    check(gui.game.is_solved(), 'shield 开局应即复原态')
    n_goal = len(gui.game.board.keys)
    if gui.game_history.history_index < 0 or not gui.game_history.history:
        gui.game_history.save_snapshot(gui.game)
    sd = gui._build_save_data()
    return sd, n_goal


def _load_into_fresh(sd):
    gui = _fresh_gui()
    gui._load_save_data(sd)
    return gui


def t_solved_survives_roundtrip():
    sd, n_goal = _build_shield_save()
    if sd is None:
        return
    snap0 = sd['history']['snapshots'][0]
    check('engine_state' in snap0, '落盘快照必须带 engine_state')
    check(len(snap0['engine_state']['keys']) == n_goal,
          f'engine_state 应保住全部 {n_goal} 块键')
    # JSON 往返（模拟磁盘）
    blob = json.dumps(sd, ensure_ascii=False)
    sd2 = json.loads(blob)
    gui = _load_into_fresh(sd2)
    check(gui.game.is_solved(), '载入后复原态应判复原（修复前这里 False）')
    check(len(gui.game.board.keys) == n_goal,
          f'载入后块数应一个不丢（{len(gui.game.board.keys)} vs {n_goal}）')
    check(gui.game.board.canonical_key() == gui.game.spec.goal_canonical(),
          '载入后 canonical 应与还原目标一致')


def t_missing_engine_state_is_lossy():
    sd, n_goal = _build_shield_save()
    if sd is None:
        return
    # 剥掉 engine_state = 复现修复前的旧档行为（重算 checksum 绕过完整性校验，
    # 因为这里要模拟的是「旧档本就没存该字段」而非「文件被篡改」）
    sd_broken = json.loads(json.dumps(sd, ensure_ascii=False))
    for s in sd_broken['history']['snapshots']:
        s.pop('engine_state', None)
    sd_broken['checksum'] = _compute_checksum(sd_broken)
    gui = _load_into_fresh(sd_broken)
    # 反向护栏：缺 engine_state 必丢块、判不到复原——证明该字段承重，不能误删
    check(len(gui.game.board.keys) < n_goal,
          f'缺 engine_state 必丢块（{len(gui.game.board.keys)} < {n_goal}）')
    check(not gui.game.is_solved(), '缺 engine_state 必判不到复原')


def main():
    t_solved_survives_roundtrip()
    t_missing_engine_state_is_lossy()
    print()
    if FAILS:
        print(f'共 {len(FAILS)} 项失败：')
        for f in FAILS:
            print('  ·', f)
        sys.exit(1)
    print('模型板存档无损往返：全部通过（含 engine_state 承重反向护栏）')


if __name__ == '__main__':
    main()
