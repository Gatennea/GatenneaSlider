"""检查项一：未使用的 import（带假阳性过滤）。"""
import ast
import re
from .common import iter_py_files, FRAMEWORK_CALLBACKS


def scan_unused_imports(root):
    """返回 [(relpath, lineno, imported_name, kind), ...]。

    过滤规则（见 docs/agent/待办清单.md §十二 / §十三）：
    - `from __future__ import ...` 是编译器指令，不算未用。
    - FRAMEWORK_CALLBACKS（do_POST / log_message 等）由框架按名调用，名字不在本仓出现也不能删。
    - 仅当整词出现次数 <= 1（即只有 import 那一行）才判未用。
    """
    findings = []
    for rp, _ap, src in iter_py_files(root, include_tests=True):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
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
            if isinstance(node, ast.Import):
                for a in node.names:
                    local = a.asname or a.name.split('.')[0]
                    if local == '*' or local in used:
                        continue
                    if len(re.findall(r'\b' + re.escape(local) + r'\b', src)) <= 1:
                        findings.append((rp, node.lineno, a.name, 'import'))
            elif isinstance(node, ast.ImportFrom):
                if node.module == '__future__':
                    continue
                for a in node.names:
                    if a.name == '*':
                        continue
                    local = a.asname or a.name
                    if local in FRAMEWORK_CALLBACKS or local in used:
                        continue
                    if len(re.findall(r'\b' + re.escape(local) + r'\b', src)) <= 1:
                        findings.append((rp, node.lineno, a.name, 'from ' + (node.module or '')))
    return findings
