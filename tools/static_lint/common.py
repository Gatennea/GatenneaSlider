"""静态审查的共享工具：文件枚举、词频索引、路径归一。"""
import os
import re
import ast
from collections import defaultdict, Counter

# 绝不扫的目录（临时草稿 / 第三方 / 构建产物）
SKIP_DIRS = {
    '.git', '.workbuddy', 'archive', 'experiments', '__pycache__',
    'video', 'voice_demo', 'build', 'dist', '.venv', '.idea', '.vscode',
}

# 产品代码根目录（只扫这些，避免扫到 archive/experiments 的历史草稿）
PRODUCT_DIRS = ['engine', 'gui', 'solver', 'macro']
PRODUCT_ROOT_FILES = [
    'game.py', 'game_mi.py', 'game_triangle.py', 'GUI.py', 'history.py',
    'http_server.py', 'main.py', 'puzzle_types.py', 'records.py',
    'bandage.py', 'bitboard.py', 'validate_model.py', 'build_release.py',
]

# 框架回调：名字不在本仓出现也不能删（BaseHTTPRequestHandler / HTTPServer 通过框架调用）
FRAMEWORK_CALLBACKS = {
    'do_GET', 'do_POST', 'do_OPTIONS', 'do_HEAD', 'do_PUT', 'do_DELETE',
    'do_PATCH', 'do_CONNECT', 'do_TRACE', 'log_message', 'log_request',
    'log_error', 'address_string', 'version_string', 'handle_one_request',
    'handle', 'setup', 'finish', 'date_time_string', 'log_date_time_string',
    'send_response', 'send_header', 'end_headers', 'do_WRITE', 'do_READ',
    'list_directory', 'guess_type', 'copyfile', 'copyfileobj',
}

WORD_RE = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')


def _read(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def rel(root, p):
    return os.path.relpath(p, root).replace('\\', '/')


def iter_py_files(root, include_tests=True):
    """yield (relpath, abspath, src) —— 产品代码下的每个 .py。"""
    roots = [os.path.join(root, d) for d in PRODUCT_DIRS]
    for f in PRODUCT_ROOT_FILES:
        p = os.path.join(root, f)
        if os.path.isfile(p):
            roots.append(p)
    if include_tests:
        tp = os.path.join(root, 'test')
        if os.path.isdir(tp):
            roots.append(tp)
    seen = set()
    for base in roots:
        if not os.path.exists(base):
            continue
        if os.path.isfile(base):
            if base not in seen:
                seen.add(base)
                yield rel(root, base), base, _read(base)
        else:
            for cur, sub, files in os.walk(base):
                sub[:] = [s for s in sub if s not in SKIP_DIRS]
                for fn in files:
                    if fn.endswith('.py'):
                        ap = os.path.join(cur, fn)
                        if ap not in seen:
                            seen.add(ap)
                            yield rel(root, ap), ap, _read(ap)


def build_index(records):
    """records: iterable of (relpath, src)。返回 (WORD_CNT, WORD_FILES, src_map)。"""
    WORD_CNT = Counter()
    WORD_FILES = defaultdict(set)
    src_map = {}
    for rp, src in records:
        src_map[rp] = src
        c = Counter(WORD_RE.findall(src))
        for w, n in c.items():
            WORD_CNT[w] += n
            WORD_FILES[w].add(rp)
    return WORD_CNT, WORD_FILES, src_map


def parse_src(src):
    try:
        return ast.parse(src)
    except SyntaxError:
        return None
