"""检查项一：未使用的 import（带假阳性过滤）。"""
import ast
import re
from .common import iter_py_files, FRAMEWORK_CALLBACKS


def _collect_all_names(tree):
    """收集文件里 `__all__` 列出的名字 —— 这些是有意的 re-export，不能当未用。"""
    names = set()

    def _from_seq(seq):
        for e in seq:
            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                names.add(e.value)

    for node in ast.walk(tree):
        targets = []
        value = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AugAssign):
            targets, value = [node.target], node.value
        for t in targets:
            if isinstance(t, ast.Name) and t.id == '__all__' \
                    and isinstance(value, (ast.List, ast.Tuple)):
                _from_seq(value.elts)
    return names


def _noqa_exempts_f401(node, lines):
    """该 import 语句（含跨行括号）有没有显式豁免 F401。

    只有 `# noqa: F401`（或 bare `# noqa`）才算「作者有意保留」；
    `# noqa: E402` 是「import 不在文件顶部」的豁免，**与未用无关**，不能拿来
    挡 F401 —— 2026-10-31 修：原版见 noqa 就跳过，把 validate_model.py 的
    load_dir（只写了 E402）误当有意保留。
    """
    end = getattr(node, 'end_lineno', None) or node.lineno
    for i in range(node.lineno, min(end, len(lines)) + 1):
        low = lines[i - 1].lower()
        idx = low.find('noqa')
        if idx < 0:
            continue
        rest = low[idx + 4:].lstrip(':').strip()
        m = re.match(r'([a-z]*\d+(?:[,\s]+[a-z]*\d+)*)', rest)
        if not m:  # bare `# noqa` → 全豁免
            return True
        return 'f401' in re.split(r'[,\s]+', m.group(1))
    return False


def scan_unused_imports(root):
    """返回 [(relpath, lineno, local_name, kind), ...]。

    过滤规则（见 docs/agent/待办清单.md §十二 / 踩坑与搁置.md）：
    - `from __future__ import ...` 是编译器指令，不算未用。
    - FRAMEWORK_CALLBACKS（do_POST / log_message 等）由框架按名调用，名字不在本仓出现也不能删。
    - `# noqa`（尤其 F401）是作者显式声明「有意保留」（如 engine/__init__.py 的
      试运行开关 re-export、gui/annotation.py 的语义参照），**不能删** —— 2026-10-31
      修：原版不认 noqa，会把有意保留的 import 报成未用。
    - 名字出现在 `__all__` 里 = re-export，同样不能删。
    - 仅当整词出现次数 <= 1（即只有 import 那一行）才判未用。

    报告的是**本文件里实际生效的名字**（`import x as y` 报 `y` 而非 `x`）——
    2026-10-31 修：原版报原名，遇到 `from game_mi import lattice_of as mi_lattice_of`
    会报一个文件里根本不存在的裸名 `lattice_of`，照着去删会找不到。
    """
    findings = []
    for rp, _ap, src in iter_py_files(root, include_tests=True):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines()
        all_names = _collect_all_names(tree)
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                cur = node
                while isinstance(cur, ast.Attribute):
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    used.add(cur.id)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module == '__future__':
                    continue
                if _noqa_exempts_f401(node, lines):
                    continue
                for a in node.names:
                    if a.name == '*':
                        continue
                    if isinstance(node, ast.Import):
                        local = a.asname or a.name.split('.')[0]
                        kind = 'import'
                    else:
                        local = a.asname or a.name
                        kind = 'from ' + (node.module or '')
                    if local == '*' or local in used or local in all_names:
                        continue
                    if local in FRAMEWORK_CALLBACKS:
                        continue
                    if len(re.findall(r'\b' + re.escape(local) + r'\b', src)) <= 1:
                        findings.append((rp, node.lineno, local, kind))
    return findings
