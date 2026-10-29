# -*- coding: utf-8 -*-
r"""跨档位「打乱 → 存档 → 载入」往返不变量巡检（2026-10-29 自由优化）。

背景：`_test_model_legacy_save` 只盯 **mi2 一个模型板**的往返（§九：旧档缺
`engine_state` → 掉块 + 碎盘 + 打乱 0 步）。但同一条「存档→载入」路径是
**所有档位共用**的，别的档位没人验过。本测试把同一套不变量铺开：

    square / numbered / triangle / mi / 全部已注册模型

每个档位逐条比：
  1. 块数不变；
  2. **盘面身份**不变——模型板比块身份多重集 `(point,orient)`，内置档位比整数
     矩阵。只比块数不够（同数不同构抓不到）；
  3. 连通分量不变且 == 1（只有引擎层能算，内置档位跳过）；
  4. numbered 档位：编号集合不变；
  5. 载入后仍打乱得动。

⚠️ 两条写测试时踩过的坑（别退化）：
  - **别用子串 `'0步' in msg` 判「一步没走」**：`'已打乱：40步'` 里也含 `'0步'`，
    而打乱步数每次都不同 → 约 10% 概率假红（本测试的前身实测撞出过）。必须
    `re.search(r'已打乱：(\d+)步')` 把数字取出来比。
  - **内置档位没有 `game.board`**：引擎层只在模型板上挂。去摸会
    `AttributeError: 'SliderMatrix' object has no attribute 'board'`。

跑法：D:/python/python.exe test/_test_roundtrip_sweep.py
"""
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame                                    # noqa: E402
from GUI import SliderGUI                        # noqa: E402
from engine import model_registry                # noqa: E402

FAILS = []


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


def _engine(gui):
    """引擎层只在**模型板**上挂（`game.board` / `spec`），内置档位没有。"""
    return getattr(gui.game, 'board', None) is not None


def _nblk(gui):
    if _engine(gui):
        return len(gui.game.board.keys)
    return sum(1 for row in gui.game.matrix for v in row if v)


def _state(gui):
    """盘面身份：模型板 = 块身份多重集；内置档位 = 整数矩阵。"""
    if _engine(gui):
        ids = sorted(repr(k) for k in gui.game.board.keys)
        comp = len(gui.game.spec.components(frozenset(gui.game.board.keys)))
    else:
        ids = tuple(tuple(row) for row in gui.game.matrix)
        comp = None
    try:
        nums = tuple(sorted(getattr(b, 'number', None) for b in gui.game.blocks
                            if getattr(b, 'number', None)))
    except Exception:
        nums = ()
    return dict(nblk=_nblk(gui), ids=ids, comp=comp, nums=nums)


def _open(gui, tgt):
    kind = tgt[0]
    if kind == 'square':
        _, m, n, step = tgt
        return bool(gui.new_puzzle(m, n, step))
    if kind == 'numbered':
        _, m, n, step = tgt
        return bool(gui.new_puzzle(m, n, step, numbered=True))
    if kind == 'triangle':
        _, k, step = tgt
        return bool(gui.new_triangle_puzzle(k, step))
    if kind == 'mi':
        _, m, n, step = tgt
        return bool(gui.new_mi_puzzle(m, n, step))
    if kind == 'model':
        _, name, step = tgt
        return bool(gui.new_model_puzzle(name, step))
    raise ValueError(kind)


def targets():
    ts = []
    for m, n, step in ((3, 3, 1), (4, 4, 1), (4, 4, 2), (5, 5, 1), (6, 5, 2)):
        ts.append(('square', m, n, step))
    for m, n, step in ((4, 4, 1), (6, 6, 2)):
        ts.append(('numbered', m, n, step))
    for k, step in ((3, 1), (4, 1), (4, 2), (5, 2)):
        ts.append(('triangle', k, step))
    for m, n, step in ((3, 3, 1), (4, 4, 2)):
        ts.append(('mi', m, n, step))
    for name in sorted(model_registry.loaded() or {}):
        ts.append(('model', name, 1))
    return ts


def main():
    model_registry.install()
    gui = _gui()
    loader = _gui()
    ts = targets()
    for tgt in ts:
        tag = '/'.join(str(x) for x in tgt)
        if not check(_open(gui, tgt), f'{tag} 应能开局'):
            continue
        gui.shuffle_puzzle()
        before = _state(gui)
        sd = gui._build_save_data()
        loader._load_save_data(json.loads(json.dumps(sd, ensure_ascii=False)))
        after = _state(loader)

        check(after['nblk'] == before['nblk'],
              f'{tag} 往返块数应不变（{after["nblk"]} vs {before["nblk"]}）')
        check(after['ids'] == before['ids'], f'{tag} 往返盘面身份应不变')
        if before['comp'] is not None:
            check(before['comp'] == 1,
                  f'{tag} 打乱后本就该单连通（实测分量 {before["comp"]}）')
            check(after['comp'] == before['comp'],
                  f'{tag} 往返连通分量应不变（{after["comp"]} vs {before["comp"]}）')
        if before['nums']:
            check(after['nums'] == before['nums'], f'{tag} 往返编号集合应不变')

        loader.macro_notify_msg = ''
        loader.shuffle_puzzle()
        m = re.search(r'已打乱：(\d+)步', loader.macro_notify_msg or '')
        check(m is not None and int(m.group(1)) > 0,
              f'{tag} 载入后仍应打乱得动（实测 msg={loader.macro_notify_msg!r}）')

    print()
    if FAILS:
        print(f'共 {len(FAILS)} 项失败：')
        for f in FAILS:
            print('  ·', f)
        sys.exit(1)
    print(f'跨档位往返巡检：{len(ts)} 个档位全部无损')


if __name__ == '__main__':
    main()
