# -*- coding: utf-8 -*-
"""生成缺失的盤面存檔（已存在則跳過，除非 --force），並產生可視化畫廊。

用法：
    D:/python/python.exe experiments/make_disks.py            # 只補缺失
    D:/python/python.exe experiments/make_disks.py --force    # 全量重生成
    D:/python/python.exe experiments/make_disks.py --no-gallery

盤面計劃來自 disk_plan.DISK_SPECS / DISK_SEEDS（進倉庫的「種子真相」）。
"""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from disk_plan import (DISK_DIR, all_specs_seeds, all_large_specs_seeds, disk_path, save_disk, iter_disk_paths)
from render_gallery import build

HERE = os.path.dirname(os.path.abspath(__file__))
GALLERY = os.path.join(HERE, 'disks_gallery.html')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true', help='重新生成所有存檔')
    ap.add_argument('--no-gallery', action='store_true', help='不生成畫廊')
    ap.add_argument('--large', action='store_true', help='只生成大尺寸盤面 (LARGE_SPECS)')
    args = ap.parse_args()

    os.makedirs(DISK_DIR, exist_ok=True)
    total = made = skipped = 0
    t0 = time.time()
    specs_src = all_large_specs_seeds() if args.large else all_specs_seeds()
    for (m, n, step, attempts, dseed, cap) in specs_src:
        p = disk_path(m, n, step, attempts, dseed)
        if os.path.exists(p) and not args.force:
            skipped += 1
        else:
            save_disk(m, n, step, attempts, dseed, cap)
            made += 1
        total += 1

    print(f"盤面存檔：共 {total}，新建 {made}，跳過 {skipped}，耗時 {time.time()-t0:.1f}s")
    print(f"存檔目錄：{DISK_DIR}")

    if not args.no_gallery:
        out = build(iter_disk_paths(), GALLERY)
        print(f"畫廊已生成：{out}")


if __name__ == '__main__':
    main()
