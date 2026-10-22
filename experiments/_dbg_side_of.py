# -*- coding: utf-8 -*-
"""侧判定差分：EngineGame.side_of vs 旧模块级 side_of（三角/米字）。

回放层 `_find_block_on_side` 按形态分派到这两份实现，P3 接入引擎后
EngineGame 必须与旧函数逐项一致——否则自动求解/宏回放会选错块。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import random  # noqa: E402
import tempfile  # noqa: E402

import engine.config as ecfg  # noqa: E402
ecfg._config_path = os.path.join(tempfile.gettempdir(),
                                 '_gatennea_engine_cfg_sideof.json')

_fails = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        _fails.append(msg)


def differential(kind, m, n, step, trials=6):
    """同一种子打乱出同一个终态（两边各自打乱，再互灌位置），逐缝逐块比。"""
    import puzzle_types
    from game_triangle import side_of as tri_side_of
    from game_mi import side_of as mi_side_of

    ecfg.set_enabled(False)
    old = puzzle_types.create_puzzle(m, n, step, kind=kind)
    ecfg.set_enabled(True)
    new = puzzle_types.create_puzzle(m, n, step, kind=kind)
    ecfg.set_enabled(False)

    for t in range(trials):
        random.seed(1000 + t)
        old.shuffle(40, step, bias=0.0, min_score=0.7)
        # 把旧引擎终态灌给引擎局（位置逐个对齐）
        new.blocks = [type(b)(list(b.location)) for b in old.blocks]
        new.update_matrix()
        # 枚举全部缝 × 全部块位置
        mism = 0
        total = 0
        fams = ('h', 'p', 'n') if kind == 'triangle' else \
               ('h', 'v', 'd1', 'd2')
        for gt in fams:
            # 米字四族都可能是 ¼ 线（h/v 在错位态、d1/d2 常态就有），
            # 必须逐 ¼ 枚举——只测整数线会漏掉回放真正会遇到的线号。
            if kind == 'mi':
                lines = [x / 4 for x in range(-16, 4 * (max(m, n) + 2) + 1)]
            else:
                lines = range(-2, max(m, n) + 3)
            for line in lines:
                if not new.is_valid_gap(gt, line):
                    continue
                for pos in new.positions():
                    total += 1
                    try:
                        a = new.side_of(gt, line, pos)
                    except ValueError:
                        a = None
                    key = tuple(pos)
                    fn = tri_side_of if kind == 'triangle' else mi_side_of
                    try:
                        b = fn(gt, line, key)
                    except Exception:
                        b = None
                    if a != b:
                        mism += 1
                        if mism <= 3:
                            print(f"    分歧 {gt}{line} pos={pos}: "
                                  f"引擎={a} 旧={b}")
        check(mism == 0, f"{kind} {m}x{n} trial{t}: {total} 次判定"
                        f"（分歧 {mism}）")


print("== 侧判定差分（tri/mi，打乱态 + ¼ 线错位态）==")
differential('triangle', 5, 5, 2)
differential('mi', 3, 3, 2)
differential('mi', 4, 4, 2)

print()
if _fails:
    print(f"失败 {len(_fails)} 項")
    sys.exit(1)
print("全部通過")
