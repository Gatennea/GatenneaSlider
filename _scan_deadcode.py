# -*- coding: utf-8 -*-
"""一次性死代碼掃描器：未用 import / 零引用定義 / 未用局部變數 / 不可達代碼。"""
import ast
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {'.git', '__pycache__', '_tmp_save', '.venv', 'venv', 'node_modules'}
SKIP_FILES = {'_scan_deadcode.py'}


def iter_py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.endswith('.py') and fn not in SKIP_FILES:
                yield os.path.join(dirpath, fn)


def rel(p):
    return os.path.relpath(p, ROOT).replace('\\', '/')


def short(src):
    return src.split(' ')[0]


FILES = {}
for p in iter_py_files():
    try:
        FILES[p] = ast.parse(open(p, encoding='utf-8').read())
    except SyntaxError as e:
        print('SYNTAX ERROR', rel(p), e)
        continue

src_by_line = {}
for p, tree in FILES.items():
    lines = open(p, encoding='utf-8').read().splitlines()
    src_by_line[p] = lines


def line_text(p, node):
    lines = src_by_line[p]
    if isinstance(node, ast.AST):
        try:
            start = node.lineno
        except AttributeError:
            return ''
        return lines[start - 1].strip() if start - 1 < len(lines) else ''
    return str(node)


# ---------------- A. 未用 import ----------------
def a_unused_imports():
    out = []
    for p, tree in FILES.items():
        if os.path.basename(p) == '__init__.py':
            continue  # __init__ 常用作 re-export，單獨人工確認
        bindings = {}  # name -> (import_stmt_node, is_from)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    bindings[a.asname or a.name.split('.')[0]] = node
            elif isinstance(node, ast.ImportFrom):
                if any(n.name == '*' for n in node.names):
                    bindings = {}  # 星號導入後無法判斷，放棄整檔
                    break
                for a in node.names:
                    bindings[a.asname or a.name] = node
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)
        for name, node in sorted(bindings.items()):
            if name not in used:
                out.append((rel(p), node.lineno, name, line_text(p, node)))
    return out


# ---------------- B. 全庫零引用定義 ----------------
def b_zero_ref_defs():
    # 收集所有 Name Load / Attribute attr / import 名稱，按字串記數
    ref_count_name = defaultdict(int)
    ref_count_attr = defaultdict(int)
    for p, tree in FILES.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                ref_count_name[node.id] += 1
            elif isinstance(node, ast.Attribute):
                ref_count_attr[node.attr] += 1
            elif isinstance(node, ast.Import):
                for a in node.names:
                    ref_count_name[a.asname or a.name.split('.')[0]] += 1
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    ref_count_name[a.asname or a.name] += 1
            elif isinstance(node, ast.arg) or isinstance(node, ast.FunctionDef):
                pass
            # 字串形式的動態名稱（getattr/globals 等）
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                pass  # 名字比對改到下方處理

    # 每個檔案的頂層定義
    defs = []  # (file, line, kind, name)
    for p, tree in FILES.items():
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.append((p, node.lineno, 'def', node.name, node))
            elif isinstance(node, ast.ClassDef):
                defs.append((p, node.lineno, 'class', node.name, node))

    # 字串值是否包含該名字（動態分發/測試名單列），保守：只要字串值恰好等於名字
    str_set = set()
    for p, tree in FILES.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                str_set.add(s)
                # 'module.func' 形式也取最後一段
                if '.' in s:
                    str_set.add(s.split('.')[-1])

    out = []
    for p, line, kind, name, node in defs:
        if name.startswith('__'):
            continue
        base = name.split('.')[0]
        n = ref_count_name.get(name, 0)
        a = ref_count_attr.get(name, 0)
        if n == 0 and a == 0 and name not in str_set:
            out.append((rel(p), line, kind, name, line_text(p, node)))
    return out


# ---------------- C. 函數內 assign 但從未讀取 ----------------
def c_unused_locals():
    out = []
    for p, tree in FILES.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith('__'):
                pass
            reads = set()
            writes = {}  # name -> list of (line, src)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name):
                    if isinstance(sub.ctx, ast.Load):
                        reads.add(sub.id)
                    elif isinstance(sub.ctx, (ast.Store, ast.Del)):
                        pass
            # 收集寫入(Store)目標，排除 function/class 定義本身的名字與參數
            defined = {a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs}
            if node.args.vararg:
                defined.add(node.args.vararg.arg)
            if node.args.kwarg:
                defined.add(node.args.kwarg.arg)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store) and sub.id not in defined:
                    # 若該名字在全函數無 Load → 可疑；但同一名字可能同時 Store 過多次，有 Load 即算用過
                    pass
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.ClassDef)):
                    defined.add(sub.name)
                if isinstance(sub, (ast.arg,)):
                    pass
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    pass
            # 直接法：所有 Store 到 name 的地方，若 name 未在任何 Load 出現→整檔未用
            store_names = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    store_names.add(sub.id)
            for name in sorted(store_names):
                if name not in reads and name not in defined:
                    # 找到該檔案中相關行
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store) and sub.id == name:
                            out.append((rel(p), node.lineno, node.name, name, line_text(p, sub)))
                            break
    return out


# ---------------- D. 不可達代碼 ----------------
def d_unreachable():
    out = []
    for p, tree in FILES.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.If, ast.Try,
                                ast.While, ast.For)):
                body = node.body if hasattr(node, 'body') else []
                dead = False
                for i, stmt in enumerate(body):
                    if dead:
                        out.append((rel(p), stmt.lineno, 'unreachable', '', line_text(p, stmt)))
                        break
                    if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                        # return/raise 後同層語句即不可達（continue/break 後在迴圈外也可能有，忽略）
                        if i + 1 < len(body):
                            nxt = body[i + 1]
                            if isinstance(node, (ast.While, ast.For)) and isinstance(stmt, (ast.Break, ast.Continue)):
                                continue
                            out.append((rel(p), nxt.lineno, 'unreachable', '', line_text(p, nxt)))
                            dead = True
    return out


def main():
    print('========== A. 未用 import（不含 __init__.py） ==========')
    for r in a_unused_imports():
        print('%-40s L%-4d %-22s # %s' % (r[0], r[1], r[2], r[3]))
    print('\n========== B. 全庫零引用 def/class ==========')
    for r in b_zero_ref_defs():
        print('%-40s L%-4d %-6s %-24s # %s' % (r[0], r[1], r[2], r[3], r[4]))
    print('\n========== C. 函數內 assign 但從未讀取 ==========')
    for r in c_unused_locals():
        print('%-40s L%-4d fn=%-22s var=%-20s # %s' % (r[0], r[1], r[2], r[3], r[4]))
    print('\n========== D. 不可達代碼 ==========')
    for r in d_unreachable():
        print('%-40s L%-4d %-10s # %s' % (r[0], r[1], r[3], r[4]))


if __name__ == '__main__':
    main()
