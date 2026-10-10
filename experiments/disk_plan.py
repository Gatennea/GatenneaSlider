# -*- coding: utf-8 -*-
"""求解器基準的「盤面存檔」計劃與讀寫工具。

盤面只存「打亂後的第一幀快照」(solver.state.snapshot)，不含任何求解結果。
種子計劃寫死在此模組 → 這就是「記住種子」，克隆倉庫後跑 make_disks.py 即可重建全部存檔。
實際 JSON 快照存本地 experiments/disks/（體積很小，進倉庫或 gitignore 皆可）。

用法：
    from disk_plan import save_disk, load_disk, iter_disk_paths, all_specs_seeds
"""
import os
import sys
import json
import random
import re

# 讓本模組可被 experiments/ 下的腳本直接 import（也能被多進程子進程重新 import）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import SliderMatrix
from solver.state import snapshot

DISK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'disks')

# 標準盤面計劃：(m, n, step, shuffle_attempts, cap_seconds)
# —— 這份計劃是「種子真相」，進倉庫；克隆後重生成存檔只需跑 make_disks.py ——
DISK_SPECS = [
    (4, 4, 2, 80, 15),
    (4, 4, 3, 60, 15),
    (5, 5, 2, 150, 20),
    (6, 6, 2, 120, 25),
]
DISK_SEEDS = [1, 2, 3, 4, 5]   # 每個配置 5 個固定盤面 → 共 20 個存檔

# 大尺寸專用計劃（測路徑優化在大尺寸是否變得有意義）：(m, n, step, shuffle_attempts, cap_seconds)
# 必須是「全新打亂」盤（類似 04/07 那種已近還原的盤 greedy 直接卡死、0 步、無物可壓縮）。
LARGE_SPECS = [
    (8, 8, 2, 200, 40),
    (8, 8, 3, 150, 40),
    (10, 10, 2, 260, 60),
]


def disk_filename(m, n, step, attempts, dseed):
    return f"disk_{m}x{n}_s{step}_a{attempts}_d{dseed}.json"


def disk_path(m, n, step, attempts, dseed):
    return os.path.join(DISK_DIR, disk_filename(m, n, step, attempts, dseed))


def generate_record(m, n, step, attempts, dseed, cap):
    """用固定種子打亂，返回含元數據的第一幀快照記錄。"""
    random.seed(dseed)
    g = SliderMatrix(m, n)
    g.shuffle(attempts=attempts, step=step)
    snap = snapshot(g)
    return {
        'm': m, 'n': n, 'step': step, 'attempts': attempts,
        'dseed': dseed, 'cap': cap, 'blocks': snap['blocks'],
    }


def save_disk(m, n, step, attempts, dseed, cap):
    rec = generate_record(m, n, step, attempts, dseed, cap)
    os.makedirs(DISK_DIR, exist_ok=True)
    p = disk_path(m, n, step, attempts, dseed)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(rec, f)
    return p


def load_disk(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


_FN_RE = re.compile(r'disk_(\d+)x(\d+)_s(\d+)_a(\d+)_d(\d+)\.json')

def parse_disk_filename(fname):
    m = _FN_RE.match(fname)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())  # (m, n, step, attempts, dseed)

def iter_disk_paths(disk_dir=DISK_DIR, specs=None):
    """specs: 可選的 {(m,n,step,attempts), ...}，只回傳匹配這些規格的盤面。"""
    if not os.path.isdir(disk_dir):
        return []
    out = []
    for f in sorted(os.listdir(disk_dir)):
        if not (f.startswith('disk_') and f.endswith('.json')):
            continue
        if specs is not None:
            p = parse_disk_filename(f)
            if p is None or (p[0], p[1], p[2], p[3]) not in specs:
                continue
        out.append(os.path.join(disk_dir, f))
    return out


def large_spec_keys():
    """LARGE_SPECS 對應的 (m,n,step,attempts) 集合，給 bench_disks 過濾用。"""
    return {(m, n, step, attempts) for (m, n, step, attempts, _cap) in LARGE_SPECS}


def all_specs_seeds():
    """yield (m, n, step, attempts, dseed, cap) —— 全部標準盤面。"""
    for (m, n, step, attempts, cap) in DISK_SPECS:
        for dseed in DISK_SEEDS:
            yield (m, n, step, attempts, dseed, cap)


def all_large_specs_seeds():
    """yield (m, n, step, attempts, dseed, cap) —— 全部大尺寸盤面。"""
    for (m, n, step, attempts, cap) in LARGE_SPECS:
        for dseed in DISK_SEEDS:
            yield (m, n, step, attempts, dseed, cap)


def cap_for(m, n, step, attempts):
    for (mm, nn, ss, aa, cc) in DISK_SPECS:
        if (mm, nn, ss, aa) == (m, n, step, attempts):
            return cc
    return 25
