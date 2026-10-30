# -*- coding: utf-8 -*-
r"""experiments/ 索引生成 + 命名约定守门。

背景（2026-10-31，与用户共同定下的约定）：
    experiments/ 里混着三种东西，光看名字分不清，只能读代码。约定由**文件名前缀**
    承担「调用关系」这一个维度（不兼表用途，那是目录与索引的事）：

        script_*   独立脚本：不被任何脚本 import，`python x.py` 直接跑
        reuse_*    两者皆是：既能独立跑（有 __main__），又被别的脚本 import
        无前缀     库：被 import、自己不能独立跑（harness / exp_actions ...）

    前缀由脚本自动判定，不该手改。本工具两件事：
      ① `--emit`  重新生成 experiments/INDEX.md（三类分组 + 每个文件被谁引用）
      ② `--check` 校验「文件名前缀」与「AST 判定的真实类别」是否一致，
                  不一致就非零退出 —— 给 CI 守门，防止前缀腐化。

为什么不用「有没有 __main__」判独立（踩过的坑）：
    大量一次性探针是顶层直接写执行代码、没写 `if __name__ == '__main__'` 守卫，
    `python x.py` 照样跑。所以「是否被调用」只能看**有没有被 import**，
    `__main__` 只用来区分 reuse_ 与无前缀库。

用法（本沙箱必须 Start-Process -Wait，别用 `& python`）：
    python tools/experiments_index.py --emit
    python tools/experiments_index.py --check        # CI 用，不符就 exit 1
    python tools/experiments_index.py --root <仓库根>
"""
import argparse
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SKIP_DIRS = {'.git', '__pycache__', 'out', 'disks', 'results', '.pytest_cache',
             '.workbuddy', 'archive'}

PREFIX_SCRIPT = 'script_'
PREFIX_REUSE = 'reuse_'


def _read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def iter_py(root, rel_dir):
    base = os.path.join(root, rel_dir)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith('.')]
        for fn in sorted(filenames):
            if fn.endswith('.py'):
                yield os.path.join(dirpath, fn)


def module_name(root, path):
    """experiments/xxx.py -> experiments.xxx（用于匹配 import 目标）。"""
    rel = os.path.relpath(path, root).replace('\\', '/')
    if rel.endswith('.py'):
        rel = rel[:-3]
    return rel.replace('/', '.')


def classify(root, rel_dir='experiments'):
    """返回 {mod_name: {'path': 相对路径, 'imported_by': set(), 'has_main': bool}}。"""
    files = list(iter_py(root, rel_dir))
    # 1) 收集每个模块是否被 import（扫全仓，不只 experiments 内部）
    roots = []
    for d in ('experiments', 'engine', 'gui', 'solver', 'macro', 'test', 'tools'):
        p = os.path.join(root, d)
        if os.path.isdir(p):
            roots.append(p)
    for fn in ('GUI.py', 'main.py', 'game.py', 'game_triangle.py', 'game_mi.py',
               'validate_model.py', 'http_server.py'):
        p = os.path.join(root, fn)
        if os.path.isfile(p):
            roots.append(p)

    info = {}
    for path in files:
        mod = module_name(root, path)
        info[mod] = {'path': os.path.relpath(path, root).replace('\\', '/'),
                     'imported_by': set(), 'has_main': False}

    mod_set = set(info)

    def scan_file(path):
        try:
            tree = ast.parse(_read(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return
        src_rel = os.path.relpath(path, root).replace('\\', '/')
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:          # 相对导入，跳过
                    continue
                base = node.module or ''
                # from experiments.exp9_rep import x  ->  experiments.exp9_rep
                # from experiments import exp9_rep     ->  experiments.exp9_rep
                cands = [base]
                for a in node.names:
                    if base:
                        cands.append(base + '.' + a.name)
                for c in cands:
                    if c in mod_set:
                        info[c]['imported_by'].add(src_rel)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in mod_set:
                        info[a.name]['imported_by'].add(src_rel)

    def scan_path(p):
        if os.path.isdir(p):
            for dp, dns, fns in os.walk(p):
                dns[:] = [d for d in dns if d not in SKIP_DIRS
                          and not d.startswith('.')]
                for fn in fns:
                    if fn.endswith('.py'):
                        scan_path(os.path.join(dp, fn))
        elif p.endswith('.py'):
            scan_path_file(p)

    def scan_path_file(p):
        try:
            tree = ast.parse(_read(p))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return
        src_rel = os.path.relpath(p, root).replace('\\', '/')
        self_mod = None
        if src_rel.endswith('.py'):
            self_mod = src_rel[:-3].replace('/', '.')
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                base = node.module or ''
                cands = [base] + [base + '.' + a.name for a in node.names] if base \
                    else [a.name for a in node.names]
                for c in cands:
                    if c in mod_set and c != self_mod:
                        info[c]['imported_by'].add(src_rel)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in mod_set and a.name != self_mod:
                        info[a.name]['imported_by'].add(src_rel)

    for p in roots:
        scan_path(p)

    # 2) 判 __main__
    for path in files:
        mod = module_name(root, path)
        try:
            src = _read(path)
        except OSError:
            continue
        info[mod]['has_main'] = bool(re.search(
            r'^\s*if\s+__name__\s*==\s*[\'"]__main__[\'"]', src, re.M))

    return info


def expected_prefix(entry):
    base = os.path.basename(entry['path'])
    if entry['imported_by']:
        return PREFIX_REUSE if entry['has_main'] else ''
    return PREFIX_SCRIPT


def kind_of(entry):
    if entry['imported_by']:
        return 'reuse' if entry['has_main'] else 'lib'
    return 'script'


KIND_LABEL = {
    'lib': '库（被 import、不能独立跑）—— 保持无前缀',
    'reuse': '两者皆是（能独立跑 + 被 import）—— 前缀 reuse_',
    'script': '独立脚本（不被任何脚本 import）—— 前缀 script_',
}


def render_md(info, root):
    groups = {'lib': [], 'reuse': [], 'script': []}
    for mod, e in info.items():
        groups[kind_of(e)].append((mod, e))
    for g in groups.values():
        g.sort(key=lambda kv: kv[1]['path'])

    L = ['# experiments/ 索引（自动生成，勿手改）', '',
         '由 `tools/experiments_index.py --emit` 生成；改脚本后重跑即可。',
         '命名约定（前缀只承担「调用关系」一个维度，用途不在这里）：', '',
         '| 前缀 | 含义 | 判据 |',
         '|---|---|---|',
         '| `script_*` | 独立脚本 | 不被任何脚本 import |',
         '| `reuse_*` | 两者皆是 | 被 import **且**有 `__main__` |',
         '| 无前缀 | 库 | 被 import、无 `__main__` |', '',
         '> 「一次性 / 有长期参考价值」**不由文件名承担**（下划线约定早已失真），',
         '> 看下方每节的引用来源与被引用次数判断。',
         '> 注：判「是否被 import」只用 AST，**不看 `__main__`** —— 大量一次性探针',
         '> 顶层直接写执行代码、没有守卫，照样能 `python x.py` 跑。', '']
    total = len(info)
    L.append('合计 %d 个 .py —— 库 %d / reuse %d / 独立脚本 %d'
             % (total, len(groups['lib']), len(groups['reuse']),
                len(groups['script'])))
    L.append('')

    for kind in ('lib', 'reuse', 'script'):
        L.append('## %s（%d）' % (KIND_LABEL[kind], len(groups[kind])))
        L.append('')
        if not groups[kind]:
            L.append('（无）')
            L.append('')
            continue
        for mod, e in groups[kind]:
            L.append('- `%s`' % e['path'])
            if e['imported_by']:
                srcs = sorted(e['imported_by'])
                L.append('  - 被 %d 处引用：%s'
                         % (len(srcs), '、'.join('`%s`' % s for s in srcs[:6])
                            + (' 等' if len(srcs) > 6 else '')))
            else:
                L.append('  - 无引用（独立脚本）')
            if e['has_main']:
                L.append('  - 有 `__main__`，可直接 `python %s`' % e['path'])
        L.append('')

    L.append('## 守门')
    L.append('')
    L.append('`python tools/experiments_index.py --check` 会校验每个文件的前缀与')
    L.append('AST 判定的真实类别是否一致；不一致（漏加前缀 / 加了但已被人 import /')
    L.append('改名后 import 没同步）就非零退出。CI 的 lint job 已接。')
    L.append('')
    return '\n'.join(L)


def run_check(info):
    """前缀与真实类别不符 → 列出并 exit 1。"""
    bad = []
    for mod, e in sorted(info.items(), key=lambda kv: kv[1]['path']):
        base = os.path.basename(e['path'])
        want = expected_prefix(e)
        got = ''
        if base.startswith(PREFIX_REUSE):
            got = PREFIX_REUSE
        elif base.startswith(PREFIX_SCRIPT):
            got = PREFIX_SCRIPT
        if got != want:
            why = {'': '不该有前缀',
                   PREFIX_SCRIPT: '应是 ' + PREFIX_SCRIPT,
                   PREFIX_REUSE: '应是 ' + PREFIX_REUSE}[want]
            detail = ''
            if e['imported_by']:
                detail = '被 %d 处 import（%s）' % (
                    len(e['imported_by']),
                    '、'.join(sorted(e['imported_by'])[:3]))
            bad.append((e['path'], got or '（无前缀）', why, detail))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description='experiments 索引生成 / 命名守门')
    ap.add_argument('--root', default=ROOT, help='仓库根（默认：本文件上级目录）')
    ap.add_argument('--emit', action='store_true', help='生成 experiments/INDEX.md')
    ap.add_argument('--check', action='store_true',
                    help='校验前缀与真实类别一致，不符非零退出')
    ap.add_argument('--out', default=None, help='把报告写到文件（沙箱捕不到 stdout）')
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    info = classify(root)
    lines = []

    if args.emit:
        md = render_md(info, root)
        dst = os.path.join(root, 'experiments', 'INDEX.md')
        with open(dst, 'w', encoding='utf-8') as fh:
            fh.write(md)
        lines.append('已生成 %s（%d 个文件）'
                     % (os.path.relpath(dst, root).replace('\\', '/'), len(info)))

    if args.check:
        bad = run_check(info)
        if bad:
            lines.append('!! 前缀与真实类别不符 %d 个：' % len(bad))
            for path, got, why, detail in bad:
                lines.append('  · %s  当前前缀=%s → %s  %s'
                             % (path, got, why, detail))
        else:
            lines.append('OK: %d 个文件前缀与调用关系一致' % len(info))
        if not args.emit and not args.out:
            print('\n'.join(lines))
        if bad:
            if args.out:
                open(args.out, 'w', encoding='utf-8').write('\n'.join(lines))
            return 1

    if args.out:
        open(args.out, 'w', encoding='utf-8').write('\n'.join(lines) or '(无输出)')
    elif not args.check:
        print('\n'.join(lines) or '(无输出，加 --emit / --check)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
