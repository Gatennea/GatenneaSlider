"""检查项二：重复函数体 + 反向依赖（底层依赖上层）。"""
import ast
import hashlib
from .common import iter_py_files

# 有意的重复（独立真值、由测试守护）：这些文件不参与重复比对。
# 见 docs/agent/踩坑与搁置.md（tri_geometry / game_triangle 是刻意保留的双份几何实现）。
DUP_EXCLUDE_FILES = {'engine/tri_geometry.py', 'engine/game_triangle.py'}

PKG_OF = {'engine': 'engine', 'gui': 'gui', 'solver': 'solver', 'macro': 'macro', 'test': 'test'}
# 允许的依赖方向；value 是被禁止依赖的上层包。
BAD_DEPS = {
    'engine': {'gui', 'solver', 'macro'},
    'solver': {'gui', 'macro'},
    'macro': {'gui'},
    'gui': set(),
}


def _norm_body(fn):
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return None
    new = ast.FunctionDef(name='_', args=fn.args, body=body,
                          decorator_list=[], returns=None, type_comment=None)
    ast.fix_missing_locations(new)
    return ast.dump(new)


def _pkg(rp):
    top = rp.split('/')[0]
    return top if top in PKG_OF else '<root>'


def scan_dups(root):
    """返回 {hash: [(relpath, lineno, name), ...]} 中 len >= 2 的组。"""
    buckets = {}
    for rp, _ap, src in iter_py_files(root, include_tests=False):
        if rp in DUP_EXCLUDE_FILES:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if len(node.body) < 3:
                    continue
                key = _norm_body(node)
                if key:
                    buckets.setdefault(hashlib.md5(key.encode()).hexdigest(), []).append(
                        (rp, node.lineno, node.name))
    return {k: v for k, v in buckets.items() if len(v) >= 2}


def scan_reverse_deps(root):
    """返回 [(src_pkg, dst_pkg), ...] 反向依赖（底层 -> 上层）。"""
    recs = list(iter_py_files(root, include_tests=True))
    mod2pkg = {}
    for rp, _ap, src in recs:
        m = rp[:-3].replace('/', '.')
        mod2pkg[m] = _pkg(rp)
        if m.endswith('.__init__'):
            mod2pkg[m[:-9]] = _pkg(rp)
    edges = set()
    for rp, _ap, src in recs:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        src_pkg = _pkg(rp)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    mods = [node.module]
            for m in mods:
                if not m:
                    continue
                b = m.split('.')[0]
                if b in mod2pkg and mod2pkg[b] != src_pkg:
                    edges.add((src_pkg, mod2pkg[b]))
    return [(a, b) for (a, b) in edges if b in BAD_DEPS.get(a, set())]
