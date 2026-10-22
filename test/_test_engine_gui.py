# -*- coding: utf-8 -*-
"""幾何引擎 GUI 接入的等價性回歸（P3 試運行）。

開關打開後 GUI 走的是 ``engine.adapter.EngineGame``（三形態共用一套引擎
邏輯），關閉時走舊 game*.py。本檔回答使用者真正關心的問題：**體感是否一致**——
不是比引擎內部，而是比 GUI 真正調用的那些口子：

    A 開關       默認關→舊引擎；開→EngineGame；GUI 撥動後重建當前局、可持久化
    B 建局       三形態塊數 / 還原態 / 位置格式 / 成績鍵（puzzle_key）與舊一致
    C 移動+歷史  選縫→try_move→commit→save_snapshot→undo→redo 逐態一致
    D 動畫落位   GUI 動畫路徑直接寫 block.location（不調 commit_move），
                 引擎必須跟得上（這是「兩套真值」設計的落點）
    E 打亂       安全打亂終態有解（可逆）+ 演示 record 能被重放回終態
    F 矩陣往返   歷史快照的矩陣編碼/解碼（方形 0/1、三角 2-bit、米字 8-bit）
                 逐形態還原——撤銷重做錯位全出在這裡
    G 縫隙命中   is_valid_gap / is_valid_h_line / side_has_blocks 與舊一致

執行：python test/_test_engine_gui.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
import game  # noqa: E402
import puzzle_types  # noqa: E402
from history import GameHistory  # noqa: E402
from engine import config as ecfg  # noqa: E402
from engine.adapter import EngineGame  # noqa: E402

_failures = []

# ⚠️ H 節的 toggle_geometry_engine 會把開關寫進 config/engine.json（產品行為：
# 撥過一次就記住）。那份文件是**全局開關**——寫成 true 會讓同批並行跑的其它
# 測試也拿到 EngineGame，於是「編號丟失」「形態判錯」等假象一齊爆出來
# （實測一次污染把全套從 7 失敗頂到 26 失敗）。故這裡把持久化重定向到臨時
# 文件：既驗到 persist 行為，又不碰別人的環境。
import tempfile  # noqa: E402

_CFG_PATH = ecfg.config_path()
_TMP_CFG = os.path.join(tempfile.gettempdir(), '_gatennea_engine_cfg_test.json')
ecfg.config_path = lambda: _TMP_CFG
# ⚠️ 开机自清理：上一轮若在 _restore_config() 之前崩了（L 节的 TypeError
# 就是这么把 true 留下来的），临时文件会让本轮 A 节「默认关」误判——污染
# 会跨轮次传染，必须在读开关之前删掉。
if os.path.isfile(_TMP_CFG):
    os.remove(_TMP_CFG)
_CFG_BACKUP = None
if os.path.isfile(_CFG_PATH):
    with open(_CFG_PATH, 'r', encoding='utf-8') as _fp:
        _CFG_BACKUP = _fp.read()


def _restore_config():
    """還原測試開始前的開關文件狀態，並清掉臨時文件。"""
    try:
        if _CFG_BACKUP is None:
            if os.path.isfile(_CFG_PATH):
                os.remove(_CFG_PATH)
        else:
            with open(_CFG_PATH, 'w', encoding='utf-8') as _fp:
                _fp.write(_CFG_BACKUP)
    except OSError:
        pass
    try:
        if os.path.isfile(_TMP_CFG):
            os.remove(_TMP_CFG)
    except OSError:
        pass


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def pos_of(game):
    """位置集合（方形舊引擎沒有 positions()，從 blocks 取）。"""
    if hasattr(game, 'positions'):
        return game.positions()
    return {tuple(b.location) for b in game.blocks}


# ================================================================ A 開關
print("== A 開關 ==")
check("默認關：create_puzzle 走舊引擎",
      type(puzzle_types.create_puzzle(4, 4, 2)).__name__ == 'SliderMatrix')
ecfg.set_enabled(True)
g4 = puzzle_types.create_puzzle(4, 4, 2)
check("開：create_puzzle 走 EngineGame", isinstance(g4, EngineGame))
gt = puzzle_types.create_puzzle(3, 3, 2, kind='triangle', triangle_side=3)
gm = puzzle_types.create_puzzle(3, 3, 2, kind='mi')
check("開：三角/米字也走 EngineGame",
      isinstance(gt, EngineGame) and isinstance(gm, EngineGame))
ecfg.set_enabled(False)
check("關回去：又走舊引擎",
      type(puzzle_types.create_puzzle(4, 4, 2)).__name__ == 'SliderMatrix')

gui = SliderGUI(m=6, n=6, step=2)
gui.animation_enabled = False
gui.save_readonly_flag = False
check("GUI 起手是经典引擎", gui.engine_label() == '经典')

# ================================================================ B 建局
print("\n== B 建局（三形態）==")


def build_both(kind, m, n, step, tri_k=None):
    """同一參數分別用經典 / 幾何引擎建局，回傳 (old, new)。"""
    ecfg.set_enabled(False)
    old = puzzle_types.create_puzzle(m, n, step, kind=kind,
                                     triangle_side=tri_k)
    ecfg.set_enabled(True)
    new = puzzle_types.create_puzzle(m, n, step, kind=kind,
                                     triangle_side=tri_k)
    return old, new


for kind, m, n, tri_k, want in (('square', 4, 4, None, 16),
                                ('numbered', 4, 4, None, 16),
                                ('triangle', 3, 3, 3, 9),
                                ('mi', 3, 3, None, 36)):
    o, a = build_both(kind, m, n, 2, tri_k)
    tag = f"{kind}"
    check(f"{tag} 塊數 {want}", len(a.blocks) == want and
          len(o.blocks) == want, f"(old {len(o.blocks)} / new {len(a.blocks)})")
    check(f"{tag} 建局即還原態", o.is_solved() and a.is_solved())
    check(f"{tag} 位置集合一致", pos_of(o) == pos_of(a))
    check(f"{tag} 矩陣一致", o.get_matrix() == a.get_matrix())
    check(f"{tag} 聚攏度一致", abs(o.compute_score() - a.compute_score()) < 1e-9)
    # 成績鍵：GUI 用 self.game.k 拼三角鍵，適配器必須掛對
    if kind == 'triangle':
        check(f"{tag} 邊長 k 一致", getattr(a, 'k', None) == getattr(o, 'k', None))

# ================================================================ C 移動 + 歷史
print("\n== C 移動 + 歷史（逐態一致）==")

GAPS = {'square': ('h', 'v'), 'triangle': ('h', 'p', 'n'),
        'mi': ('h', 'v', 'd1', 'd2')}
DIRS = {'square': {'h': ('a', 'd'), 'v': ('w', 's')},
        'triangle': {'h': ('a', 'd'), 'p': ('e', 'z'), 'n': ('w', 'x')},
        'mi': {'h': ('a', 'd'), 'v': ('w', 's'),
               'd1': ('q', 'z'), 'd2': ('e', 'x')}}


def gaps_of(game, kind):
    """當前全部候選縫（方形舊引擎沒有 all_gaps，按邊界盒合成）。"""
    if hasattr(game, 'all_gaps'):
        return sorted(game.all_gaps(), key=lambda x: (str(x[0]), x[1]))
    b = game.get_boundaries()
    out = []
    for g in GAPS[kind]:
        lo, hi = ((b['min_row'], b['max_row']) if g == 'h'
                  else (b['min_col'], b['max_col']))
        out.extend((g, l) for l in range(lo, hi))
    return sorted(out, key=lambda x: (str(x[0]), x[1]))


def scripted_moves(game, count=12, seed=5):
    """同一套腳本化移動（隨機種子固定），回傳每步後的狀態列表。

    走的是 GUI 真實路徑：opt → try_move_ex → commit_move → save_snapshot。

    ⚠️ 選塊必須**按位置**而不是按 blocks 索引：兩套引擎的 blocks 順序不同，
       按索引取會選到不同的塊，序列立刻分叉（比較就沒意義了）。
    """
    rnd = random.Random(seed)
    hist = GameHistory()
    states = []
    for _ in range(count):
        gaps = gaps_of(game, kind)
        if not gaps:
            break
        gt, line = rnd.choice(gaps)
        d = rnd.choice(DIRS[kind][gt])
        cells = sorted(tuple(x) for x in pos_of(game))
        target = rnd.choice(cells)
        blk = game.block_at(target) if hasattr(game, 'block_at') else None
        if blk is None:
            blk = next((b for b in game.blocks
                        if tuple(b.location) == target), None)
        if blk is None:
            break
        game.opt(gt, line, blk)
        final, reason = game.try_move_ex(d, 1)
        if not final:
            continue
        nsel = sum(1 for b in game.blocks if b.be_opted)
        if nsel == len(game.blocks):
            continue
        game.commit_move(final)
        hist.save_snapshot(game, {'gap_type': gt, 'gap_line': line,
                                  'direction': d, 'step': 1,
                                  'moved_positions': []})
        states.append((frozenset(pos_of(game)), sorted(game.get_matrix())))
    return states, hist


for kind, m, n, tri_k in (('square', 4, 4, None), ('triangle', 3, 3, 3),
                          ('mi', 3, 3, None)):
    o, a = build_both(kind, m, n, 2, tri_k)
    # 讓兩邊從同一個非還原態出發：用舊引擎打亂後的位置
    o.shuffle(30, 2, bias=0.0, min_score=0.7)
    a.blocks = [type(a.blocks[0])(list(p), None) for p in pos_of(o)]
    check(f"{kind} 起手局面一致", pos_of(o) == pos_of(a))
    so, _ho = scripted_moves(o)
    sa, _ha = scripted_moves(a)
    check(f"{kind} 移動序列長度一致", len(so) == len(sa),
          f"({len(so)} vs {len(sa)})")
    same = all(x == y for x, y in zip(so, sa))
    check(f"{kind} 每步後 位置+矩陣 逐態一致", same and len(so) > 0)

# ================================================================ D 動畫落位
print("\n== D 動畫落位（直接寫 location，不調 commit_move）==")
from engine.compat import _norm_keys  # noqa: E402

for kind, m, n, tri_k in (('square', 4, 4, None), ('triangle', 3, 3, 3),
                          ('mi', 3, 3, None)):
    # 兩邊從同一局面出發
    o, a = build_both(kind, m, n, 2, tri_k)
    o.shuffle(25, 2, bias=0.0, min_score=0.7)
    a.blocks = [type(a.blocks[0])(list(p), None) for p in pos_of(o)]
    moved_ok = False
    for gt, line in gaps_of(o, kind):
        for d in DIRS[kind][gt]:
            o.opt(gt, line, o.blocks[0])
            blk = a.block_at(tuple(o.blocks[0].location))
            if blk is None:
                continue
            a.opt(gt, line, blk)
            of, _ro = o.try_move_ex(d, 1)
            af, _ra = a.try_move_ex(d, 1)
            if not of or not af:
                continue
            # 模擬 commit_animation：兩邊都直接寫 location，不調 commit_move
            for i, b in enumerate([b for b in o.blocks if b.be_opted]):
                b.location = list(of[i])
            for i, b in enumerate([b for b in a.blocks if b.be_opted]):
                b.location = list(af[i])
            moved_ok = True
            break
        if moved_ok:
            break
    check(f"{kind} 動畫路徑可走通", moved_ok)
    if not moved_ok:
        continue
    check(f"{kind} 落位後兩邊局面仍一致", pos_of(o) == pos_of(a))
    # 引擎必須跟得上直接改寫的座標（這是「兩套真值」設計的落點）
    want = frozenset(_norm_keys([tuple(b.location) for b in a.blocks],
                                a.spec, 'gui.sync'))
    check(f"{kind} 引擎局面已同步到新座標", frozenset(a.board.keys) == want)
    # 落位後的下一步判定必須基於新局面：與舊引擎逐項對拍
    diffs = 0
    total = 0
    for gt, line in a.all_gaps():
        for d in DIRS[kind].get(gt, ()):
            for ob in o.blocks[:6]:
                ab = a.block_at(tuple(ob.location))
                if ab is None:
                    continue
                total += 1
                o.opt(gt, line, ob)
                of, _ = o.try_move_ex(d, 1)
                a.opt(gt, line, ab)
                af, _ = a.try_move_ex(d, 1)
                if (frozenset(tuple(p) for p in of) !=
                        frozenset(tuple(p) for p in af)):
                    diffs += 1
    check(f"{kind} 落位後下一步判定與舊引擎一致", diffs == 0,
          f"({total} 組，差 {diffs})")

# ================================================================ E 打亂
print("\n== E 打亂（安全打亂 + 演示 record）==")
# 等級取 1：k=3 的三角配等級 2 是「一步都走不動」的盤（舊引擎同樣 0 步），
# 用這種盤驗打亂驗不出東西，只會把真回歸和「本來就走不動」混在一起。
for kind, m, n, tri_k in (('square', 4, 4, None), ('triangle', 4, 4, 4),
                          ('mi', 3, 3, None)):
    ecfg.set_enabled(False)
    o = puzzle_types.create_puzzle(m, n, 1, kind=kind, triangle_side=tri_k)
    random.seed(23)
    o_rec = []
    o.shuffle(30, 1, bias=0.0, min_score=0.7, record=o_rec)
    ecfg.set_enabled(True)
    a = puzzle_types.create_puzzle(m, n, 1, kind=kind, triangle_side=tri_k)
    random.seed(23)
    records = []
    pre = [tuple(p) for p in pos_of(a)]
    a.shuffle(30, 1, bias=0.0, min_score=0.7, record=records)
    check(f"{kind} 舊引擎在該盤上確實能打亂（對照組）", len(o_rec) > 0,
          f"(舊 {len(o_rec)} 步)")
    check(f"{kind} 打亂記錄非空", len(records) > 0, f"({len(records)} 步)")
    fmt_ok = all(set(('moved', 'final', 'gap', 'direction', 'step')) <= set(r)
                 for r in records)
    check(f"{kind} record 字段齊全（moved/final/gap/direction/step）", fmt_ok)
    # 演示重放：從 pre 出發，按 record 逐步寫 final，終態 == 打亂終態
    replay = set(pre)
    for r in records:
        replay -= set(r['moved'])
        replay |= set(r['final'])
    check(f"{kind} 演示 record 重放至終態", replay == pos_of(a))
    check(f"{kind} 打亂後不還原", not a.is_solved())
    check(f"{kind} 打亂後仍單一連通",
          a.is_single_connected(pos_of(a)))

# ================================================================ F 矩陣往返
print("\n== F 歷史快照矩陣往返（撤銷/重做的命脈）==")
for kind, m, n, tri_k in (('square', 4, 4, None), ('triangle', 3, 3, 3),
                          ('mi', 3, 3, None)):
    ecfg.set_enabled(True)
    a = puzzle_types.create_puzzle(m, n, 2, kind=kind, triangle_side=tri_k)
    random.seed(31)
    a.shuffle(25, 2, bias=0.0, min_score=0.7)
    hist = GameHistory()
    p0 = frozenset(pos_of(a))
    hist.save_snapshot(a, None)
    # 再走一步，然後撤銷回 p0
    done = False
    for gt, line in a.all_gaps():
        for d in DIRS[kind][gt]:
            a.opt(gt, line, a.blocks[0])
            final, _r = a.try_move_ex(d, 1)
            if final and len([b for b in a.blocks if b.be_opted]) < len(a.blocks):
                a.commit_move(final)
                hist.save_snapshot(a, {'gap_type': gt, 'gap_line': line,
                                       'direction': d, 'step': 1,
                                       'moved_positions': []})
                done = True
                break
        if done:
            break
    check(f"{kind} 走了一步", done)
    p1 = frozenset(pos_of(a))
    check(f"{kind} 走後局面變了", p1 != p0)
    hist.undo(a)
    check(f"{kind} 撤銷回到上一步（矩陣解碼無損）", pos_of(a) == p0,
          f"(差 {len(pos_of(a) ^ p0)} 塊)")
    hist.redo(a)
    check(f"{kind} 重做回到走後局面", pos_of(a) == p1)

# ================================================================ G 縫隙命中
print("\n== G 縫隙命中（GUI 點縫的判定）==")
for kind, m, n, tri_k in (('square', 4, 4, None), ('triangle', 3, 3, 3),
                          ('mi', 3, 3, None)):
    o, a = build_both(kind, m, n, 2, tri_k)
    o.shuffle(20, 2, bias=0.0, min_score=0.7)
    a.blocks = [type(a.blocks[0])(list(p), None) for p in pos_of(o)]
    diffs = 0
    total = 0
    rng = range(-3, 9)
    for gt in GAPS[kind]:
        for line in rng:
            total += 1
            try:
                ov = (o.is_valid_gap(gt, line) if hasattr(o, 'is_valid_gap')
                      else (o.is_valid_h_line(line) if gt == 'h'
                            else o.is_valid_v_line(line)))
            except Exception:
                continue
            av = a.is_valid_gap(gt, line)
            if ov != av:
                diffs += 1
    check(f"{kind} is_valid_gap/h_line/v_line 全等", diffs == 0,
          f"({total} 條線，差 {diffs})")

# ================================================================ H GUI 撥動
print("\n== H GUI 撥動開關 ==")
ecfg.set_enabled(True)
gui.new_puzzle(4, 4, 2)
check("開著建局 → EngineGame", isinstance(gui.game, EngineGame))
gui.toggle_geometry_engine()
check("拨动后 → 经典引擎", gui.engine_label() == '经典'
      and type(gui.game).__name__ == 'SliderMatrix')
gui.toggle_geometry_engine()
check("再拨回 → 几何引擎", gui.engine_label() == '几何'
      and isinstance(gui.game, EngineGame))
ecfg.set_enabled(False)
gui.new_puzzle(4, 4, 2)
check("收尾回到經典（不污染後續）",
      type(gui.game).__name__ == 'SliderMatrix')

# ================================================================ J 求解器對照
# 玩家最常用的是「指示 / 求解」。同一個打亂局面，舊引擎與幾何引擎跑同一個
# 求解器必須給出**同一條解**——不然就是實打實的體感不一致。
#
# 這一節抓到過一個真 bug（2026-10-21）：`solver/state.py:restore` 做搜索回溯
# 時是**就地改寫** `b.location[i]`（不換塊對象），塊上緩存的 `engine_key` 就此
# 過期；`opt` 若在 `_sync` 之前讀鍵，就會拿過期鍵查新局面 → 判定「選中塊不在
# 盤面上」→ 選中 0 塊 → 求解器拿到 False → 報 invalid_action。表現極有欺騙性：
# 動作空間新舊同形（28=28），只是走出的解不同（舊 5 步解完、引擎卡在第 6 步；
# 米字更明顯 14 步 vs 8 步）。
print("\n== J 求解器對照（同局面 → 同一條解）==")
import random as _rnd  # noqa: E402

import solver as _solver  # noqa: E402


def _same_start(kind, m, n, step, tri_k, attempts, seed):
    """打亂舊引擎後把同一份位置灌給兩邊，回傳 (舊局, 引擎局)。"""
    ecfg.set_enabled(False)
    old = puzzle_types.create_puzzle(m, n, step, kind, triangle_side=tri_k)
    _rnd.seed(seed)
    old.shuffle(attempts, step, bias=0.0, min_score=0.7)
    cells = sorted(tuple(b.location) for b in old.blocks)
    ecfg.set_enabled(True)
    eng = puzzle_types.create_puzzle(m, n, step, kind, triangle_side=tri_k)
    Blk = type(eng.blocks[0])
    eng.blocks = [Blk(list(p), None) for p in cells]
    eng.update_matrix()
    return old, eng, cells


for _kind, _m, _n, _step, _tk, _att in (('square', 4, 4, 2, None, 6),
                                        ('square', 3, 3, 1, None, 4),
                                        ('triangle', 3, 3, 1, 3, 6),
                                        ('mi', 3, 3, 1, None, 6)):
    _old, _eng, _cells = _same_start(_kind, _m, _n, _step, _tk, _att,
                                     20261021)
    check(f"{_kind} 灌入位置一致（{len(_cells)} 塊）",
          _eng.positions() == set(_cells))
    _rnd.seed(1)
    _ro = _solver.gather_solve_unified(_old, step=_step) or {}
    _rnd.seed(1)
    _re = _solver.gather_solve_unified(_eng, step=_step) or {}
    _ao = _ro.get('actions') or []
    _ae = _re.get('actions') or []
    check(f"{_kind} 解法動作逐項一致（{len(_ao)} vs {len(_ae)} 步）",
          _ao == _ae)
    check(f"{_kind} solved 判定一致（{_ro.get('solved')} vs "
          f"{_re.get('solved')}）",
          bool(_ro.get('solved')) == bool(_re.get('solved')))
    check(f"{_kind} 走完解 is_solved 一致",
          _old.is_solved() == _eng.is_solved())
    ecfg.set_enabled(False)

# ================================================================ I 打亂性能
# 護欄不是基準測試：只釘住「不許退回枚舉全空間那條路」。踩過的坑——
# try_move_ex 用 ``move in legal_moves(step)`` 判成員，6×6 打亂 2777ms
# （其中 98% 燒在枚舉）；改單點校驗後 26ms。這裡給 8s 的寬門檻，只在
# 快路徑被整條改回去時才響。
print("\n== I 打亂性能護欄（不許退回枚舉）==")
import time as _time  # noqa: E402


def _timed_shuffle(game, rounds):
    game.shuffle(60, 2, bias=0.0, min_score=0.7)   # 預熱（首次含懶導入）
    t0 = _time.perf_counter()
    for _ in range(rounds):
        game.shuffle(60, 2, bias=0.0, min_score=0.7)
    return (_time.perf_counter() - t0) * 1000.0 / rounds


ecfg.set_enabled(False)
_old = _timed_shuffle(game.SliderMatrix(6, 6), 20)
ecfg.set_enabled(True)
_new = _timed_shuffle(puzzle_types.create_puzzle(6, 6, 2, 'square'), 20)
ecfg.set_enabled(False)
check("6×6 s2 打亂未退化到枚舉量級", _new < 8000.0,
      f"引擎 {_new:.1f}ms/次 vs 經典 {_old:.1f}ms/次"
      f"（倍數 {_new / max(_old, 1e-6):.1f}×，門檻 8s/20 次）")
check("引擎/經典打亂在 6× 以內（體感同量級）",
      _new < max(_old, 1.0) * 6.0,
      f"{_new:.1f}ms vs {_old:.1f}ms")

# ================================================================ K 特殊玩法
# 編號謎題 / 自由捆綁是 GUI 裡玩家随手就能開的兩種局，引擎層跑不通就是
# 實打實的體驗缺口。踩過的坑：puzzle_types 的引擎分支**提前 return**，
# 走不到舊路徑的 ``g.numbered = (kind=='numbered')`` → 編號謎題矩陣值
# 全變 1（存檔 / 戰績面板靜默錯）。改由 EngineGame 從 kind 派生。
print("\n== K 編號謎題 + 自由捆紮 ==")
for _en in (False, True):
    ecfg.set_enabled(_en)
    _tag = '引擎' if _en else '經典'
    # -- 編號謎題：矩陣值 = 編號（存檔與成績面板靠它） --
    _g = puzzle_types.create_puzzle(3, 3, 1, 'numbered')
    for _b, _v in zip(_g.blocks, range(1, len(_g.blocks) + 1)):
        _b.number = _v
    _g.update_matrix()
    _vals = sorted(v for row in _g.matrix for v in row if v)
    check(f"{_tag} 編號謎題矩陣值=編號", _vals == list(range(1, 10)),
          f"{_vals}")
    _g.shuffle(8, 1, bias=0.0, min_score=0.7)
    _g.update_matrix()
    _vals2 = sorted(v for row in _g.matrix for v in row if v)
    check(f"{_tag} 打亂後矩陣值仍=編號集合", _vals2 == list(range(1, 10)),
          f"{_vals2}")
    _nums = sorted(getattr(b, 'number', None) for b in _g.blocks)
    check(f"{_tag} 打亂後編號跟著塊走", _nums == list(range(1, 10)),
          f"{_nums}")
    # -- 自由捆紮：跨行組成員必須被剛體拖入選中 --
    _g4 = puzzle_types.create_puzzle(4, 4, 1, 'square')
    _g4.blocks[0].group = 1          # (0,0)
    _g4.blocks[5].group = 1          # (1,1) 不同行
    if hasattr(_g4, 'set_groups_from_positions'):
        _g4.set_groups_from_positions({tuple(_g4.blocks[0].location): 1,
                                       tuple(_g4.blocks[5].location): 1})
    _g4.opt('h', 0, _g4.blocks[0])   # h:0 = 第 1 行整行 4 塊
    _sel = [b for b in _g4.blocks if b.be_opted]
    check(f"{_tag} 剛體語義拖入跨行組（4+1=5 塊）", len(_sel) == 5,
          f"選中 {len(_sel)} 塊")
    _g4.shuffle(6, 1, bias=0.0, min_score=0.7)
    _cells = {tuple(b.location) for b in _g4.blocks}
    check(f"{_tag} 帶組打亂後仍單一連通且不丟塊",
          _g4.is_single_connected(_cells) and len(_g4.blocks) == 16,
          f"{len(_g4.blocks)} 塊")
ecfg.set_enabled(False)

# ================================================================ L 侧判定差分
# 回放层（自动求解 / 宏回放）靠 `_find_block_on_side` 找块，异形走
# `_side_of_any` 按形态分派：旧引擎两份模块级 side_of vs 引擎自带的
# EngineGame.side_of。判据必须逐项等价——选错块 = 整步动作被静默改写
# （GUI 表现为「解法播到一半走歪」）。踩过的坑：``rank < t`` 在整数线下
# 等价、非整数线（d1 的 L=-2.5）下不等价；且 ``_line_to_t`` 的
# ``int(round(...))`` 会把半整数线吞掉一半。正解：``rank <= line_scale·line``。
print("\n== L 侧判定差分（tri/mi，含 ¼ 線）==")
from game_triangle import side_of as _tri_side_of  # noqa: E402
from game_mi import side_of as _mi_side_of  # noqa: E402
from gui.events import _side_of_any  # noqa: E402


def _side_diff(kind, m, n, step, trials=4):
    import random as _rnd
    ecfg.set_enabled(False)
    old = puzzle_types.create_puzzle(m, n, step, kind=kind)
    ecfg.set_enabled(True)
    new = puzzle_types.create_puzzle(m, n, step, kind=kind)
    ecfg.set_enabled(False)
    for t in range(trials):
        _rnd.seed(2000 + t)
        old.shuffle(40, step, bias=0.0, min_score=0.7)
        new.blocks = [game.Block(list(b.location)) for b in old.blocks]
        new.update_matrix()
        mism = total = 0
        fams = ('h', 'p', 'n') if kind == 'triangle' else \
               ('h', 'v', 'd1', 'd2')
        for gt in fams:
            # 米字四族逐 ¼ 枚举（错位态横竖缝 / 对角链中点都是非整数线）
            if kind == 'mi':
                lines = [x / 4 for x in range(-16, 4 * (max(m, n) + 2) + 1)]
            else:
                lines = range(-2, max(m, n) + 3)
            for line in lines:
                if not new.is_valid_gap(gt, line):
                    continue
                for pos in new.positions():
                    total += 1
                    a = new.side_of(gt, line, pos)
                    fn = _tri_side_of if kind == 'triangle' else _mi_side_of
                    b = fn(gt, line, tuple(pos))
                    if a != b:
                        mism += 1
        check(f"{kind} {m}x{n} trial{t} 侧判定全等（{total} 次）",
              mism == 0, f"分歧 {mism}")
        # 分派函数本体：引擎局走能力检查，不抛 ValueError
        try:
            _side_of_any(new, fams[0], 0, next(iter(new.positions())))
            check(f"{kind} trial{t} _side_of_any 引擎分派不抛", True)
        except ValueError as e:
            check(f"{kind} trial{t} _side_of_any 引擎分派不抛", False,
                  repr(e))


_side_diff('triangle', 5, 5, 2)
_side_diff('mi', 3, 3, 2)
_side_diff('mi', 4, 4, 2)
ecfg.set_enabled(False)

_restore_config()

print()
if _failures:
    print(f"失敗 {len(_failures)} 項：")
    for f in _failures:
        print("  -", f)
    sys.exit(1)
print("全部通過")
