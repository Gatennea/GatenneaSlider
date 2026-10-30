"""检查项三：mixin MRO 同名方法遮蔽（被遮蔽且无非显式调用 = 死方法）。"""
import ast
import re
from .common import iter_py_files


def _find_class(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def scan_mixin_shadow(root):
    """返回 [(method, mixin, relpath, lineno), ...] —— 被遮蔽且无显式 Mixin.method 调用的死方法。"""
    src_map = {rp: src for rp, _ap, src in iter_py_files(root, include_tests=False)}
    if 'GUI.py' not in src_map:
        return []
    gui_tree = ast.parse(src_map['GUI.py'])
    slider = _find_class(gui_tree, 'SliderGUI')
    if slider is None:
        return []

    bases = [ast.unparse(b) for b in slider.bases]

    def find_def(name):
        for rp, src in src_map.items():
            try:
                t = ast.parse(src)
            except SyntaxError:
                continue
            if _find_class(t, name):
                return name, rp
        return None

    mixins = []
    for b in bases:
        d = find_def(b)
        if d:
            mixins.append(d)

    owner = {}
    for order, (b, mrp) in enumerate(mixins):
        try:
            t = ast.parse(src_map.get(mrp, ''))
        except SyntaxError:
            continue
        cls = _find_class(t, b)
        if cls is None:
            continue
        for ch in cls.body:
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if ch.name.startswith('__'):
                    continue
                owner.setdefault(ch.name, []).append((order, b, mrp, ch.lineno))

    conflicts = {m: v for m, v in owner.items() if len(v) >= 2}
    all_text = '\n'.join(src_map.values())
    findings = []
    for m, v in conflicts.items():
        v = sorted(v)
        for _order, b, mrp, ln in v[1:]:  # v[0] 是 MRO 靠前的生效份
            pat = re.compile(r'\b' + re.escape(b) + r'\.' + re.escape(m) + r'\s*\(')
            if not pat.search(all_text):
                findings.append((m, b, mrp, ln))
    return findings
