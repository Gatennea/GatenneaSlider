"""static_lint 命令行入口。

用法：
    python -m tools.static_lint.runner [--root REPO] [--baseline baseline.json]
                                        [--out report.txt] [--format text|json]
                                        [--emit-baseline PATH] [--strict]

- 默认扫仓库根（tools/static_lint/ 的上两级）。
- 首次跑 `--emit-baseline baseline.json` 生成基线（本轮可接受结论）。
- 之后每次改完跑 `--baseline baseline.json`：只报 NEW（新引入）/ RESOLVED（已修复）。
- `--strict`：出现 NEW 时退出码非零（给 CI 当回归守门用）。
"""
import argparse
import json
import os
import sys
import warnings

# 扫描产物代码时，某些旧文件带无效转义（如 r'\p'），会产生 SyntaxWarning。
# linter 只解析 AST、不执行，这类警告与审查无关，静默掉保持输出干净。
warnings.filterwarnings('ignore', category=SyntaxWarning)

from . import deadcode, dup, mixin

CATEGORIES = ['unused_import', 'dup_body', 'reverse_dep', 'mixin_dead']


def collect_findings(root):
    """返回 (sigs_by_cat, text_lines)。sigs 为可稳定的签名串，用于 diff。"""
    sigs = {c: [] for c in CATEGORIES}
    text = []

    ui = deadcode.scan_unused_imports(root)
    for rp, ln, nm, kind in ui:
        sigs['unused_import'].append('UI|%s|%d|%s' % (rp, ln, nm))
        text.append('[未用 import] %s:%d %s (%s)' % (rp, ln, nm, kind))

    dmap = dup.scan_dups(root)
    for _k, v in dmap.items():
        names = sorted(set(x[2] for x in v))
        locs = sorted(set(x[0] for x in v))
        sigs['dup_body'].append('DB|%s|%s' % (','.join(names), ','.join(locs)))
        text.append('[重复函数体] %s x%d @ %s' % (','.join(names), len(v), ', '.join(locs)))

    bad = dup.scan_reverse_deps(root)
    for a, b in bad:
        sigs['reverse_dep'].append('RD|%s|%s' % (a, b))
        text.append('[反向依赖] %s -> %s' % (a, b))

    md = mixin.scan_mixin_shadow(root)
    for m, b, mrp, ln in md:
        sigs['mixin_dead'].append('MD|%s|%s|%s|%d' % (m, b, mrp, ln))
        text.append('[mixin 死方法] %s.%s @ %s:%d' % (b, m, mrp, ln))

    return sigs, text


def load_baseline(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return set(json.load(fh).get('signatures', []))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='static_lint',
                                 description='GatenneaSlider 静态审查 linter')
    here = os.path.dirname(os.path.abspath(__file__))
    default_root = os.path.dirname(os.path.dirname(here))
    ap.add_argument('--root', default=default_root, help='仓库根目录（默认 tools/ 的上两级）')
    ap.add_argument('--baseline', default=None, help='基线 JSON（diff 模式）')
    ap.add_argument('--out', default=None, help='报告输出文件（默认 stdout）')
    ap.add_argument('--format', choices=['text', 'json'], default='text')
    ap.add_argument('--emit-baseline', default=None, help='把当前签名集写成基线 JSON')
    ap.add_argument('--strict', action='store_true', help='出现 NEW 回归时退出码非零')
    args = ap.parse_args(argv)

    sigs, text = collect_findings(args.root)
    total = sum(len(v) for v in sigs.values())

    lines = []
    lines.append('=== GatenneaSlider 静态审查 (root=%s) ===' % args.root)
    lines.append('发现 %d 项：' % total)
    for c in CATEGORIES:
        lines.append('  - %s: %d' % (c, len(sigs[c])))
    lines.extend(text)
    lines.append('')

    if args.emit_baseline:
        cur = set()
        for v in sigs.values():
            cur.update(v)
        with open(args.emit_baseline, 'w', encoding='utf-8') as fh:
            json.dump({'signatures': sorted(cur)}, fh, ensure_ascii=False, indent=2)
        lines.append('baseline 已写入 %s（%d 条签名）' % (args.emit_baseline, len(cur)))

    if args.baseline:
        base = load_baseline(args.baseline)
        if base is None:
            lines.append('!! 基线文件不存在：%s' % args.baseline)
        else:
            cur = set()
            for v in sigs.values():
                cur.update(v)
            new = sorted(cur - base)
            resolved = sorted(base - cur)
            lines.append('=== diff vs 基线 %s ===' % args.baseline)
            lines.append('NEW（新引入）: %d' % len(new))
            lines.extend('  + ' + s for s in new)
            lines.append('RESOLVED（已修复）: %d' % len(resolved))
            lines.extend('  - ' + s for s in resolved)
            if not new:
                lines.append('OK: 无新增回归')

    out = '\n'.join(lines) + '\n'
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(out)
    else:
        print(out)

    if args.format == 'json':
        return 0

    new_count = 0
    if args.baseline and base is not None:
        cur = set()
        for v in sigs.values():
            cur.update(v)
        new_count = len(cur - base)
    return 1 if (args.strict and new_count > 0) else 0


if __name__ == '__main__':
    sys.exit(main())
