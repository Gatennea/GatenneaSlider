# -*- coding: utf-8 -*-
r"""粘上接走（band_shift）前置共轭（长共轭原语）护栏 — 存档 step120 盘面回归锁。

来源：save/2-8-8-20261111-220716waiting_optimize.json 第 120 步（已内嵌
盘面，不依赖存档文件）。该盘面聚拢度 62/64，两洞 (6,0) 与 (-1,-1)、
窗外凸起 (-2,-2) 与 (7,3)；用户手解 121~134 是 14 步长共轭（外层 v0 下/
上 夹「洞带上滑 8 格→顶部交棒→带回位」），段末 62→63。

修复前（2026-11-12 解码）：_band_shift_chain 无前置相位——洞带深滑第 4
步被引擎以 'disconnected' 拒（121 右带下移加长锚固 + 122 底部凸出部左移
对齐锚位缺一不可，实测「仅121」也在第 4 滑断开），所有 d='w' 候选只能
产出 62→38/47 的搅盘解、被聚拢度闸门正确拒收 → 粘上接走（band_shift）返回 None。

修复后：两阶段搜索——阶段A 无前置（原行为）；阶段B 仅对「无前置让位
半途而废」（1 ≤ 深度 < k）的候选搜前置共轭（1~2 步邻域滑动，链尾逆序
撤销），终态由整链重放＋聚拢度闸门终裁。生成器自产出与用户手解同构的
14 步段（前置2 + 让位4 + 接应2 + 回位4 + 撤前置2）。

反向验证：
  P2 把 max_prep 关到 0（纯行为开关，非 monkeypatch）→ 同盘必返回 None，
  证明前置共轭是充要改动；
  P3 spy 统计 _undo_entry 在成功路径被真调用（撤前置不是摆设）；
  P1 的「终态 == 段首 − 凸起 + 洞」精确断言本身就行为级锁死了撤前置的
  正确性（不撤干净终态不可能精确还原）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import solver.ml.fill_macro as fm  # noqa: E402

M, N, STEP = 8, 8, 2
HOLE = (6, 0)
BUMP = (-2, -2)

# 存档 step120 的完整盘面（64 块）
COORDS = frozenset([
    (-2, -2),
    (-1, -3), (-1, -2), (-1, 0), (-1, 1), (-1, 2), (-1, 3), (-1, 4),
    (0, -3), (0, -2), (0, -1), (0, 0), (0, 1), (0, 2), (0, 3), (0, 4),
    (1, -3), (1, -2), (1, -1), (1, 0), (1, 1), (1, 2), (1, 3), (1, 4),
    (2, -3), (2, -2), (2, -1), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4),
    (3, -3), (3, -2), (3, -1), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4),
    (4, -3), (4, -2), (4, -1), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4),
    (5, -3), (5, -2), (5, -1), (5, 0), (5, 1), (5, 2), (5, 3), (5, 4),
    (6, -3), (6, -2), (6, -1), (6, 1), (6, 2), (6, 3), (6, 4),
    (7, 3)
])

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


def run():
    ov0 = fm.window_of(COORDS, M, N, STEP)[1]
    check('P0 盘面 64 块 / 段首聚拢 62',
          len(COORDS) == M * N and ov0 == 62,
          '块=%d ov=%d' % (len(COORDS), ov0))

    # P1 粘上接走（band_shift）默认参数（含前置共轭）：产出合法 14 步段，62→63
    # 注：测试只验证「长共轭原语正确性」，故显式放宽 time_budget；生产侧
    # _BAND_SHIFT_BUDGET 仍是约 10s 的延迟预算（用户机器实测约 8s 命中，
    # 慢机可能超时属可接受降级，不影响正确性护栏）。
    acts, info = fm._band_shift_chain(COORDS, M, N, STEP, HOLE, BUMP,
                                      time_budget=40.0)
    g = fm.build_game(COORDS, M, N)
    ok = fm._replay_apply(g, acts, M, N, STEP) if acts else False
    end = fm.gcoords(g)
    end_ov = fm.window_of(frozenset(end), M, N, STEP)[1] if ok else None
    check('P1 粘上接走（band_shift）产出动作且整链重放合法', acts is not None and ok,
          '%s' % ('None' if acts is None else '%d 步' % len(acts)))
    check('P1 段末聚拢 62→63', end_ov == 63, '段末 ov=%s' % end_ov)
    check('P1 终态精确还原（== 段首 − 凸起 + 洞）',
          ok and frozenset(end) == (COORDS - {BUMP}) | {HOLE},
          'diff=%s' % (sorted(set(end) ^ (COORDS - {BUMP} | {HOLE}))[:6],))
    check('P1 生成链用了前置共轭（info prep==2）',
          info is not None and info.get('prep') == 2,
          'prep=%s' % (info.get('prep') if info else None))

    # P2 反向验证：关掉前置共轭（max_prep=0），同盘必返回 None
    acts0, info0 = fm._band_shift_chain(COORDS, M, N, STEP, HOLE, BUMP,
                                        max_prep=0)
    check('P2 无前置（max_prep=0）同盘返回 None（撤修复即转红）',
          acts0 is None, 'info=%s' % str(info0)[:60])

    # P3 撤前置真被调用：spy 统计 _undo_entry
    orig_undo = fm._undo_entry
    cnt = {'n': 0}

    def spy_undo(act5, step):
        cnt['n'] += 1
        return orig_undo(act5, step)
    fm._undo_entry = spy_undo
    try:
        acts_s, _info_s = fm._band_shift_chain(COORDS, M, N, STEP, HOLE, BUMP,
                                              time_budget=40.0)
    finally:
        fm._undo_entry = orig_undo
    check('P3 成功路径真调用 _undo_entry（次数>0）',
          acts_s is not None and cnt['n'] > 0, 'calls=%d' % cnt['n'])

    print()
    if FAILS:
        print('FAILED %d:' % len(FAILS))
        for f in FAILS:
            print('  -', f)
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
