# -*- coding: utf-8 -*-
"""术语审计：代码注释/docstring 高频词 vs docs/spec/術語規定.md 登记项。

只读扫描，不改任何文件。输出未登记的高频中文术语与英文行话候选。
"""
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CODE_DIRS = ['solver', 'gui', 'experiments', '.']
CODE_FILES = ['game.py', 'GUI.py', 'history.py', 'main.py', 'http_server.py']

# 英文行话/缩写候选（人工预置模式，按词边界匹配，大小写不敏感分开处理）
EN_PATTERNS = [
    'GBFS', 'IDA\\*', 'PDB', 'A\\*', 'ABAB', 'checkpoint', 'stage_cb',
    'keep_partial', 'fill_partial', 'fill_fail', 'use_fill', 'hybrid',
    'gather', 'gap_macro', 'fill_macro', 'rep_cell', 'profile_defect',
    'deadend', 'blacklist', 'Metropolis', 'fuzz', 'worktree', 'jsonl',
    'Couple', 'couple', 'SCC', 'Cayley', 'bitboard', 'Φ', 'Phi', 'phi',
    'DLL', 'numpy', 'py-spy', 'headless', 'smoke',
]
EN_RE = re.compile('|'.join('(?:%s)' % p for p in EN_PATTERNS))

# 中文停用词（太泛，不是术语）
CN_STOP = set('''
我们 你们 他们 它们 这个 那个 这种 那种 这样 那样 什么 怎么 为什么 因为 所以 但是 而且
如果 那么 于是 接着 然后 最后 首先 其次 已经 还在 不会 不能 可以 应该 需要 必须 可能
一个 一些 一遍 一次 一起 一直 一定 没有 不是 不会 这是 那是 就是 也是 也是的 自己的
时候 地方 方面 问题 情况 东西 事情 样子 意思 意义 目的 原因 结果 过程 方法 方式 办法
使用 用时 用来 通过 根据 按照 对于 关于 由于 之后 之前 以前 以后 上面 下面 里面 外面
这里 那里 哪个 哪些 这样 那样 如此 此外 另外 同时 最后 最终 目前 当前 现在 原来 本来
新的 旧的 好的 坏的 大的 小的 多的 少的 高的 低的 长的 短的 快得 慢得 多的 少的
不要 不用 不可 无非 无论 不管 除了 除非 只要 只有 即使 尽管 虽然 或者 还是 并且
用户 玩家 作者 开发者 工程师 调用 返回 执行 处理 计算 判断 检测 检查 测试 验证 确认
代码 文件 目录 模块 函数 变量 参数 字段 配置 选项 开关 按钮 菜单 界面 窗口 对话框
游戏 关卡 局面 盘面 棋盘 方块 滑快 滑块 移动 滑动 打乱 还原 解决 求解 搜索 算法
第一 第二 第三 一层 两层 三层 一段 两段 三步 四步 几步 每步 每层 每局 每局
'''.split())

CN_RE = re.compile(r'[一-鿿]{2,7}')


def iter_code_files():
    for d in CODE_DIRS:
        base = os.path.join(ROOT, d) if d != '.' else ROOT
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames
                           if x not in ('__pycache__', 'results', 'video',
                                        'voice_demo', 'save', 'archives',
                                        'docs', '.git', 'fixtures')
                           and not x.startswith('.')]
            for fn in filenames:
                if fn.endswith('.py') and not fn.startswith('test_'):
                    yield os.path.join(dirpath, fn)
    for f in CODE_FILES:
        p = os.path.join(ROOT, f)
        if os.path.isfile(p):
            yield p


def extract_comments(text):
    """提取注释行与 docstring 文本（粗粒度：# 后内容 + 三引号块）。"""
    out = []
    in_doc = False
    doc_buf = []
    for line in text.splitlines():
        s = line.strip()
        if in_doc:
            doc_buf.append(s)
            if '"""' in s or "'''" in s:
                in_doc = False
                out.append('\n'.join(doc_buf))
                doc_buf = []
            continue
        if s.startswith('#'):
            out.append(s.lstrip('#').strip())
            continue
        if s.startswith('"""') or s.startswith("'''"):
            q = s[:3]
            rest = s[3:]
            if q in rest:
                out.append(rest.replace(q, '').strip())
            else:
                in_doc = True
                doc_buf = [rest]
            continue
        # 行尾注释
        idx = line.find('#')
        if idx > 0:
            out.append(line[idx + 1:].strip())
    return out


def main():
    cn = Counter()
    en = Counter()
    files = 0
    for path in iter_code_files():
        try:
            text = open(path, encoding='utf-8').read()
        except Exception:
            continue
        files += 1
        blob = '\n'.join(extract_comments(text))
        for w in CN_RE.findall(blob):
            if w not in CN_STOP and not w.isdigit():
                cn[w] += 1
        for m in EN_RE.finditer(blob):
            en[m.group(0)] += 1

    spec_path = os.path.join(ROOT, 'docs', 'spec', '術語規定.md')
    spec = open(spec_path, encoding='utf-8').read()
    spec_low = spec.lower()

    print('扫描 %d 个文件' % files)
    print()
    print('=== 未登记英文行话（代码出现 ≥2 次，术语文档无匹配）===')
    for w, c in en.most_common():
        if c < 2:
            continue
        if w.lower() not in spec_low and w not in spec:
            print('  %-18s %3d' % (w, c))
    print()
    print('=== 未登记中文术语候选（出现 ≥3 次，术语文档无匹配）===')
    shown = 0
    for w, c in cn.most_common(400):
        if c < 3:
            break
        if w not in spec:
            print('  %-12s %3d' % (w, c))
            shown += 1
        if shown >= 60:
            break


if __name__ == '__main__':
    main()
