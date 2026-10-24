# -*- coding: utf-8 -*-
"""校验模型文件（结构 + 物理公理 A0–A3）。

用法::

    python validate_model.py                     # 校验 models/ 下全部模型
    python validate_model.py models/shatter.json # 校验指定文件
    python validate_model.py --deep              # 额外做 A3（逐条移动求新局面）
    python validate_model.py --quiet             # 只输出有问题的

退出码：0 = 全部通过（允许有警告）；1 = 有错误；2 = 加载阶段就失败。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.model_loader import (DEFAULT_MODEL_DIR, ModelError, load_dir,  # noqa: E402
                                 load_file)
from engine.model_validate import summarize, validate  # noqa: E402


def report(loaded, deep):
    problems = validate(loaded, deep=deep)
    n_err, n_warn = summarize(problems)
    if problems:
        print(f'  {loaded.name}（{loaded.title}）'
              f'  块 {len(loaded.spec.goal_blocks)}'
              f'  缝族 {len(loaded.spec.seam_families)}'
              f'  -> {n_err} 错误 / {n_warn} 警告')
        for p in problems:
            print(f'    {p}')
    elif not QUIET:
        print(f'  {loaded.name}（{loaded.title}）'
              f'  块 {len(loaded.spec.goal_blocks)}'
              f'  缝族 {len(loaded.spec.seam_families)}  -> 通过')
    return n_err


def main(argv=None):
    global QUIET
    ap = argparse.ArgumentParser(description='校验 GatenneaSlider 模型文件')
    ap.add_argument('paths', nargs='*', help='模型文件路径（省略 = models/）')
    ap.add_argument('--deep', action='store_true',
                    help='跑 A3（每步可逆），要对每条合法移动求新局面，较慢')
    ap.add_argument('--quiet', action='store_true', help='只输出有问题的')
    args = ap.parse_args(argv)
    QUIET = args.quiet

    paths = args.paths or [DEFAULT_MODEL_DIR]
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(sorted(
                os.path.join(p, f) for f in os.listdir(p)
                if f.endswith('.json') and f != 'shapes.json'))
        else:
            files.append(p)
    if not files:
        print('没有找到模型文件')
        return 2

    total_err = 0
    for path in files:
        if not QUIET:
            print(f'[{os.path.basename(path)}]')
        try:
            loaded = load_file(path)
        except ModelError as exc:
            print(f'  加载失败：{exc}')
            total_err += 1
            continue
        total_err += report(loaded, args.deep)

    print()
    print('全部通过' if total_err == 0 else f'共 {total_err} 条错误')
    return 0 if total_err == 0 else 1


QUIET = False

if __name__ == '__main__':
    sys.exit(main())
