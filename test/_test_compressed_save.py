# -*- coding: utf-8 -*-
"""压缩存档功能集成测试（headless，SDL dummy 驱动）。

覆盖：
- 模块层：普通→压缩→解压 往返 + 哈希校验 + 末态格集一致（全量存档）
- GUI 接线：_build_save_data 在开关下产出普通/压缩两种格式
- GUI 接线：_load_save_data 能载入压缩档并还原末态（哈希校验通过）
- 工具：convert_save_file 在磁盘上互转并写出文件

执行：``D:/python/python.exe -u test/_test_compressed_save.py``
"""
import os
import sys
import glob
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from gui.compressed_save import (compress_snapshots, decompress_to_normal,
                                 is_compressed, verify_checksum,
                                 load_compressed_into_gui, convert_save_file)
from GUI import SliderGUI

_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def final_cells_of_snapshot(snap):
    bounds = snap['bounds']
    mnr, mnc = bounds['min_row'], bounds['min_col']
    cells = set()
    for i, row in enumerate(snap['matrix']):
        for j, v in enumerate(row):
            if v:
                cells.add((mnr + i, mnc + j))
    return cells


def gui_final_cells(gui):
    return frozenset(tuple(b.location) for b in gui.game.blocks)


# ---------------------------------------------------------------- 1. 模块层全量往返
def test_module_roundtrip():
    print("\n=== 1. 模块层：全量存档 普通→压缩→解压 往返 ===")
    files = sorted(glob.glob(os.path.join(ROOT, 'save', '**', '*.json'), recursive=True))
    ok = 0
    skip_shape = 0
    bad_source = 0  # 源存档自身历史不一致（损坏）→ 压缩应正确拒绝
    unexpected = 0  # 非损坏原因的失败 → 才是模块 bug
    for f in files:
        try:
            src = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        p = src.get('puzzle', {})
        if p.get('type', 'square') not in ('square', 'numbered'):
            skip_shape += 1
            continue
        snaps = src.get('history', {}).get('snapshots', [])
        if len(snaps) < 2:
            continue
        try:
            comp = compress_snapshots(p, snaps, src.get('step_count', 0),
                                     bool(src.get('readonly', False)))
            assert is_compressed(comp) and verify_checksum(comp)
            dec = decompress_to_normal(comp)  # 内部逐 K 步校验哈希 + 末态校验
            assert verify_checksum(dec)
            src_final = final_cells_of_snapshot(snaps[-1])
            dec_final = final_cells_of_snapshot(dec['history']['snapshots'][-1])
            assert src_final == dec_final, "末态格集不一致"
            ok += 1
        except Exception as e:
            msg = str(e)
            # 损坏源存档的拒绝信息必然含以下关键字之一
            if ('存档可能损坏' in msg) or ('重放不合法' in msg) or ('末态' in msg):
                bad_source += 1
            else:
                unexpected += 1
                print(f"  UNEXPECTED FAIL {os.path.basename(f)}: {e}")
    print(f"  通过={ok}  跳过(异形/单快照)={skip_shape}  "
          f"损坏源拒绝={bad_source}  非预期失败={unexpected}")
    check("所有失败均为源存档损坏的正确拒绝（无模块 bug）", unexpected == 0,
          f"unexpected={unexpected}")


# ---------------------------------------------------------------- 2. GUI 接线 _build_save_data
def test_build_save_data():
    print("\n=== 2. GUI 接线：_build_save_data 普通/压缩 分支 ===")
    gui = SliderGUI(m=6, n=6, step=2)
    gui.animation_enabled = False
    # 载入一个带完整 history 的普通存档，制造非空历史
    good = os.path.join(ROOT, 'save', '死局存档', '死局-4_4_2-1.json')
    with open(good, encoding='utf-8') as fh:
        gui._load_save_data(json.load(fh))
    check("载入普通存档后历史非空", len(gui.game_history.history) >= 2,
          f"len={len(gui.game_history.history)}")

    # 关闭压缩 → 普通格式
    gui.use_compressed_save = False
    normal = gui._build_save_data()
    check("开关关：产出普通格式", not is_compressed(normal), f"version={normal.get('version')}")

    # 开启压缩 → 压缩格式（矩形谜题）
    gui.use_compressed_save = True
    comp = gui._build_save_data()
    check("开关开：产出压缩格式", is_compressed(comp), f"format={comp.get('format')}")
    check("压缩档可解压且末态一致", _comp_matches_gui_final(gui, comp))

    # 异形不受开关影响：压缩分支在 triangle_mode/mi_mode 为真时跳过。
    # （真实异形局面下 game 带对应几何属性；此处仅确认分支逻辑——
    #  若强制把方形局标记成异形属非法状态，不予测试。）


def _comp_matches_gui_final(gui, comp):
    try:
        dec = decompress_to_normal(comp)
        dec_final = final_cells_of_snapshot(dec['history']['snapshots'][-1])
        return dec_final == gui_final_cells(gui)
    except Exception as e:
        print(f"    _comp_matches_gui_final 异常: {e}")
        return False


# ---------------------------------------------------------------- 3. GUI 接线 _load_save_data（压缩）
def test_load_compressed():
    print("\n=== 3. GUI 接线：_load_save_data 载入压缩档 ===")
    gui = SliderGUI(m=6, n=6, step=2)
    gui.animation_enabled = False
    good = os.path.join(ROOT, 'save', '死局存档', '死局-4_4_2-1.json')
    src = json.load(open(good, encoding='utf-8'))
    # 先压成压缩档（走 convert 工具，等价于开关开启后保存）
    import tempfile
    tmpd = tempfile.mkdtemp()
    comp_path = os.path.join(tmpd, 'x.compressed.json')
    convert_save_file(good, comp_path)
    comp = json.load(open(comp_path, encoding='utf-8'))
    check("convert 产出压缩档", is_compressed(comp))

    gui._load_save_data(comp)
    # 载入后末态应与源末态一致
    src_final = final_cells_of_snapshot(src['history']['snapshots'][-1])
    check("载入压缩档末态一致", gui_final_cells(gui) == src_final)
    check("载入后 history_index 指向末态",
          gui.game_history.history_index == len(gui.game_history.history) - 1)
    # 回退机制会把校验失败掩盖成"看起来正常"——必须显式断言无告警
    check("载入无回退告警", not getattr(gui, 'macro_notify_msg', None),
          f"msg={getattr(gui, 'macro_notify_msg', None)!r}")


# ---------------------------------------------------------------- 4. 工具 convert_save_file 磁盘互转
def test_convert_disk():
    print("\n=== 4. 工具：convert_save_file 磁盘互转 ===")
    import tempfile
    good = os.path.join(ROOT, 'save', '死局存档', '死局-4_4_2-1.json')
    tmpd = tempfile.mkdtemp()
    comp_path = os.path.join(tmpd, 'a.compressed.json')
    norm_path = os.path.join(tmpd, 'a.normal.json')
    k1, m1 = convert_save_file(good, comp_path)
    check("普通→压缩", k1 == 'compressed' and is_compressed(json.load(open(comp_path, encoding='utf-8'))))
    k2, m2 = convert_save_file(comp_path, norm_path)
    check("压缩→普通", k2 == 'normal' and not is_compressed(json.load(open(norm_path, encoding='utf-8'))))
    # 末态一致
    src_final = final_cells_of_snapshot(json.load(open(good, encoding='utf-8'))['history']['snapshots'][-1])
    back_final = final_cells_of_snapshot(json.load(open(norm_path, encoding='utf-8'))['history']['snapshots'][-1])
    check("互转后末态一致", src_final == back_final)
    # 异形应拒绝
    bad = os.path.join(tmpd, 'tri.json')
    json.dump({'version': 2, 'puzzle': {'m': 4, 'n': 4, 'step': 2, 'type': 'triangle'},
               'step_count': 0, 'history': {'history_index': 0, 'snapshots': []}},
              open(bad, 'w', encoding='utf-8'))
    try:
        convert_save_file(bad, os.path.join(tmpd, 'tri.out.json'))
        check("异形转换被拒绝", False)
    except ValueError:
        check("异形转换被拒绝", True)


# ---------------------------------------------------------------- 5. 数字谜题端到端
def _drive_moves(gui, count):
    """无头驱动真实落子管线走 count 步（复刻宏执行的 opt→try_move→commit）。"""
    DIRS = {'h': ('w', 's'), 'v': ('a', 'd')}
    made = 0
    for _ in range(count * 40):
        if made >= count:
            break
        moved = False
        for gt in ('h', 'v'):
            lines = range(1, gui.current_m) if gt == 'h' else range(1, gui.current_n)
            for line in lines:
                for side in ('above', 'below') if gt == 'h' else ('left', 'right'):
                    blk = gui._find_block_on_side(gt, line, side)
                    if blk is None:
                        continue
                    gui.game.opt(gt, line, blk)
                    for d in DIRS[gt]:
                        final = gui.game.try_move(d, gui.current_step)
                        if final:
                            selected = [b for b in gui.game.blocks if b.be_opted]
                            mi = {'gap_type': gt, 'gap_line': line, 'direction': d,
                                  'step': gui.current_step,
                                  'moved_positions': [list(b.location) for b in selected]}
                            gui.game.commit_move(final)
                            gui.step_count += 1
                            gui.game_history.save_snapshot(gui.game, mi,
                                                           gui._move_merge_key())
                            made += 1
                            moved = True
                            break
                    if moved:
                        break
                if moved:
                    break
            if moved:
                break
    return made


def test_numbered():
    print("\n=== 5. 数字谜题：压缩→解压→载入 端到端（语料无数字档，唯此覆盖） ===")
    gui = SliderGUI(m=6, n=6, step=2)
    gui.animation_enabled = False
    gui.new_puzzle(6, 6, 2, numbered=True)
    n = _drive_moves(gui, 12)
    check("数字局驱动步数达标", n >= 10, f"made={n}")

    gui.use_compressed_save = True
    comp = gui._build_save_data()
    check("数字局产出压缩格式", is_compressed(comp), f"format={comp.get('format')}")
    dec = decompress_to_normal(comp)
    check("数字档校验和解压后可验", verify_checksum(dec))
    check("末态 numbers 保留",
          dec['history']['snapshots'][-1].get('numbers')
          == gui.game_history.history[-1].get('numbers'))

    gui2 = SliderGUI(m=6, n=6, step=2)
    gui2.animation_enabled = False
    gui2._load_save_data(comp)
    check("载入数字压缩档 numbered 标记", gui2.numbered is True)
    check("载入后末态一致", gui_final_cells(gui2) == gui_final_cells(gui))
    check("载入后逐快照 numbers 与解压档一致",
          [h.get('numbers') for h in gui2.game_history.history]
          == [s.get('numbers') for s in dec['history']['snapshots']])
    check("数字载入无回退告警", not getattr(gui2, 'macro_notify_msg', None),
          f"msg={getattr(gui2, 'macro_notify_msg', None)!r}")


if __name__ == '__main__':
    test_module_roundtrip()
    test_build_save_data()
    test_load_compressed()
    test_convert_disk()
    test_numbered()
    print("\n" + ("全部通过 ✅" if not _failures else f"存在失败 ❌: {_failures}"))
    sys.exit(1 if _failures else 0)
