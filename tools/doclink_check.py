# -*- coding: utf-8 -*-
"""文档引用校验器：扫 Markdown 里的「文件引用」与「待办清单 §X」节号引用。

起因（2026-10-31）：一晚上手修了 4 处过期引用 —— docs/README.md 的「§十一」实为 §七、
bandaged_mode.md 的「§六之二」实为 §一、待办清单头部关于复制粘贴的旧说明、以及
AGENTS.md §17 引的数学真源只在 feat/math-research 分支（main 上是断链）。靠人眼几周
扫一遍不现实，所以把这个判据固化成可复跑的工具，并接进 CI 的 lint job。

检查两类：
  1. file_ref  — 反引号里像路径的 token（*.md / *.py / *.json / 目录/）：目标是否存在。
     解析基准两个：仓库根，以及该 md 所在目录（文档里常写相对自己的路径）。
  2. sec_ref   — 「《某文件》§X」或「某文件 §X」：X 是不是目标文件里真实存在的编号节。
     目标文件若根本没有编号节，只提示「无法校验」而非断链（避免假阳性）。

假阳性靠两处收敛：KNOWN_BROKEN 白名单（已知断链，注明原因）+ 目标无编号节时不判。

用法：
    python tools/doclink_check.py [--root REPO] [--out report.txt]
                                  [--baseline baseline.json] [--emit-baseline PATH]
                                  [--strict]
退出码：--strict 且存在 NEW 回归（或首次跑有非白名单问题）时非零。
"""
import argparse
import json
import os
import re
import sys

# 不扫的目录（历史草稿 / 临时产物 / 第三方）
SKIP_DIRS = {
    '.git', '.workbuddy', 'archive', '__pycache__', 'node_modules',
    'video', 'voice_demo', 'build', 'dist', '.venv', '.idea', '.vscode',
}

# 扫这些地方的 md（default_root 之外不动，避免 archive/experiments 的历史笔记刷屏）
SCAN_DIRS = ['docs', 'tools']
SCAN_ROOT_MD = True

# 路径 token 的后缀白名单：只有这些才当「文件引用」检查。
# 目的：过滤掉 `python -m x.y`、`git status` 这类命令片段与 `某函数()` 之类。
FILE_EXT = ('md', 'py', 'json', 'txt', 'csv', 'yml', 'yaml', 'ini', 'cfg',
            'png', 'jpg', 'jpeg', 'svg', 'html', 'htm', 'toml', 'sh', 'bat')

# 建 basename 索引时不遍历的目录：历史草稿 + 大产物（video/disks 之类上 GB）
INDEX_SKIP = SKIP_DIRS | {
    'out', 'disks', 'math_repro',
}

# 「产物 / 资源」类扩展名：找不到只提示不断链（.txt/.csv 多为一次性实验产物，
# 本来就不入库；真正的文档与代码才纳入 strict 门禁）
ARTIFACT_EXT = {'txt', 'csv', 'png', 'jpg', 'jpeg', 'svg', 'json',
                'yml', 'yaml', 'html', 'htm', 'ini', 'cfg', 'toml'}

# 反引号内容（含路径）。允许中文文件名、下划线、连字符、点。
BT_RE = re.compile(r'`([^`\n]{2,200})`')
PATH_TOKEN_RE = re.compile(r'^[\w\u4e00-\u9fff./\\-]+$')

# 「《文件》§X」/「文件 §X」/「文件 的 §X」
SEC_RE = re.compile(
    r'([\u4e00-\u9fff\w./\\-]{2,60}?)[\s》」）\)]*(?:的)?\s*[§#]\s*'
    r'([0-9]{1,3}(?:\.[0-9]{1,3})?|[一二三四五六七八九十]{1,3})'
)

# 已知断链：不报（每条都要写清原因，否则白名单会变成垃圾桶）
KNOWN_BROKEN = {
    'docs/math/命名与集合关系_2026-10-16.md':
        '数学真源只在 feat/math-research 分支（95c3005），从未进 main；见待办清单 §十四',
}

# 整棵子树都不在 main 上（按前缀匹配）
KNOWN_BROKEN_PREFIX = {
    'experiments/math_repro/':
        '数学复现实验整包只存在于 feat/math-research 分支（6add028 归档），main 上没有',
    'web/': '本仓没有 web/ 子项目（前端在别的仓库）',
}

# math 复现实验资产（文档里常写裸名，不带 experiments/math_repro/ 前缀）：
# 同样只存在于 feat/math-research 分支，按 basename 去扩展名匹配。
MATH_BRANCH_STEMS = {
    'forward_closure', 'deadend_structure', 'deadend_shapes', 'sweep',
    'enum_shapes', 'board_types', 'oeis_dist', 'repro', 'basin_442',
    'basin_443', 'sweep_results', 'REPRO_REPORT_2', 'read_full_A',
    'deadends_442', 'deadends_443', 'sweep_results',
}

# 一次性 / 已弃脚本：下划线开头或 _tmp_/_dbg_ 前缀，本就不入库（见 experiments 命名约定）
ONE_OFF_RE = re.compile(r'^_|_tmp_|_dbg_|_debug_')

# 溯源动词：同一行出现这些词，说明引用的是**历史位置**（"由 X 搬来"/"X 已并入"），
# 是有意的出处标注而不是指路 —— 不该判成断链。
# 例：docs/README.md 七处 `docs/豆包文档/`（2026-10-27 已拆散）、
#     `旧 文档索引.md 已并入本文件`。
HISTORY_HINT_RE = re.compile(
    r'(搬来|搬來|搬迁|搬遷|搬至|并入|併入|已删|已刪除|改名|更名|取代|'
    r'原(?:为|為|名|在)|曾(?:在|是|叫)|来自|來自|前身|旧(?:名|称|稱))'
)

# 规划动词：引用的是**打算建**的模块（"建议 gui/audio.py"、"新增 音頻模塊"），
# 文件当然还不存在。
PLANNED_HINT_RE = re.compile(r'(建議|建议|新增|計劃|计划|待建|拟建|擬建|TODO)')

# 运行期资源 / 外部素材目录：仓库里没有也不算文档断链。
# 注意这里存的是**去掉尾部斜杠**后的名字（与 norm 口径一致）。
RESOURCE_DIRS = {
    'voice_demo', 'screenshots', 'sound', 'img', 'Web/images',
    'GatenneaSlider/video/materials',
    # 下面这批是文档里「这些目录不该出现」的黑名单列举，不是引用
    '.clinerules', '.trae', '.vscode', '参考',
}


def known_broken_reason(norm):
    if norm in KNOWN_BROKEN:
        return KNOWN_BROKEN[norm]
    if norm + '.md' in KNOWN_BROKEN:
        return KNOWN_BROKEN[norm + '.md']
    for pre, why in KNOWN_BROKEN_PREFIX.items():
        if norm.startswith(pre):
            return why
    stem = os.path.basename(norm)
    if stem and '.' in stem:
        stem = stem.rsplit('.', 1)[0]
    if stem in MATH_BRANCH_STEMS:
        return 'math 复现实验资产，只存在于 feat/math-research 分支'
    return None

CN_DIGIT = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9}


def cn2int(s):
    """一 / 十一 / 二十 → int；阿拉伯数字原样。够覆盖本仓的节号。"""
    if s.isdigit():
        return int(s)
    if '十' in s:
        a, _, b = s.partition('十')
        total = (CN_DIGIT.get(a, 1) if a else 1) * 10
        return total + (CN_DIGIT.get(b, 0) if b else 0)
    return sum(CN_DIGIT.get(c, 0) for c in s)


def _read(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def rel(root, p):
    return os.path.relpath(p, root).replace('\\', '/')


def iter_md_files(root):
    """yield (relpath, abspath) —— 被扫的 md 文件。"""
    bases = []
    if SCAN_ROOT_MD:
        bases.append(root)
    for d in SCAN_DIRS:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            bases.append(p)
    seen = set()
    for base in bases:
        for cur, sub, files in os.walk(base):
            sub[:] = [s for s in sub if s not in SKIP_DIRS]
            for fn in files:
                if fn.endswith('.md'):
                    ap = os.path.join(cur, fn)
                    if ap not in seen:
                        seen.add(ap)
                        yield rel(root, ap), ap


def all_md_files(root):
    """全仓 md（用于把「待办清单」这类裸名解析成真实文件）。"""
    out = []
    for cur, sub, files in os.walk(root):
        sub[:] = [s for s in sub if s not in SKIP_DIRS]
        for fn in files:
            if fn.endswith('.md'):
                out.append(rel(root, os.path.join(cur, fn)))
    return out


HEAD_RE = re.compile(r'^(#{1,6})\s+(.*)$')
# 编号节写法一（阿拉伯）：「## 0. xxx」「### 4.2 xxx」「## 9.6 xxx」
#   数字后可跟分隔符，也可直接跟空格 —— 首版只认分隔符，漏掉了 readme_to_agent.md
#   §4.2、術語規定.md §9.6 这类，属于假阳性。
HEAD_NUM_ARABIC = re.compile(
    r'^\s*§?\s*([0-9]{1,3}(?:\.[0-9]{1,3})?)\s*[、.．:：]?\s+'
)
# 编号节写法二（中文）：「## 十一、xxx」「## §八 xxx」
#   中文数字后**必须**有分隔符，否则「## 三種控制模式」这类正常标题会被误判成编号。
HEAD_NUM_CN = re.compile(
    r'^\s*§?\s*([一二三四五六七八九十]{1,4})\s*[、.．:：]\s*'
)


def section_numbers(md_path):
    """返回该 md 的编号节集合（归一化成数字或 'a.b' 串）；无编号节返回空 set。"""
    nums = set()
    try:
        src = _read(md_path)
    except OSError:
        return nums
    for line in src.splitlines():
        m = HEAD_RE.match(line)
        if not m:
            continue
        title = m.group(2)
        raw = None
        hm = HEAD_NUM_ARABIC.match(title)
        if hm:
            raw = hm.group(1)
        else:
            hm = HEAD_NUM_CN.match(title)
            if hm:
                raw = hm.group(1)
        if raw is not None:
            nums.add(raw if '.' in raw else str(cn2int(raw)))
    return nums


def build_name_index(root):
    """全仓文件名 / 目录名索引（basename -> [relpath]），供裸文件名回退解析。

    文档里大量写裸名（`cell_class.py`、`求解器設計.md`、`script__phi_cost.py`），
    只按「相对根 / 相对本文件」解析会满屏假阳性；它们其实散落在 engine/、docs/、
    experiments/ 各处。按 basename **唯一**命中即认定有效（歧义则不判，交给人看）。
    """
    files, dirs = {}, {}
    for cur, sub, fns in os.walk(root):
        sub[:] = [s for s in sub if s not in INDEX_SKIP]
        for d in sub:
            dirs.setdefault(d, []).append(rel(root, os.path.join(cur, d)))
        for fn in fns:
            files.setdefault(fn, []).append(rel(root, os.path.join(cur, fn)))
    return files, dirs


def resolve_file_ref(root, md_rel, token, name_index=None):
    """把文档里的路径 token 解析成存在的相对路径；找不到返回 None。"""
    tok = token.strip().strip('`').rstrip('：:')
    if not tok:
        return None
    # 目录引用（以 / 结尾）
    is_dir = tok.endswith('/') or tok.endswith('\\')
    tok2 = tok.rstrip('/\\')
    if not PATH_TOKEN_RE.match(tok2):
        return None
    ext = tok2.rsplit('.', 1)[-1].lower() if '.' in tok2.rsplit('/', 1)[-1] else ''
    if not is_dir and ext not in FILE_EXT:
        return None
    # basename 为空（如单独的 `/`、`.json`）直接跳过，是伪 token
    base = os.path.basename(tok2)
    stem = base[:-len(ext) - 1] if ext and base.endswith('.' + ext) else base
    if not stem:
        return None
    cands = [os.path.join(root, tok2),
             os.path.join(root, os.path.dirname(md_rel), tok2)]
    for c in cands:
        c = os.path.normpath(c)
        if is_dir and os.path.isdir(c):
            return rel(root, c) + '/'
        if os.path.exists(c):
            return rel(root, c)
    # 回退：裸名在全仓唯一命中
    if name_index is not None:
        f_idx, d_idx = name_index
        pool = d_idx if is_dir else f_idx
        key = stem if is_dir else base
        hits = pool.get(key)
        if hits:
            if len(hits) > 1:
                # 同名多个时，先用原引用里的父目录名收窄
                # （如 `results/blindspot/汇总.md` → 只留含 blindspot 的那个）
                parent = os.path.basename(os.path.dirname(tok2))
                if parent:
                    narrowed = [h for h in hits if parent in h]
                    if len(narrowed) == 1:
                        return narrowed[0]
            if len(hits) == 1:
                return hits[0]
            # 同名多个（如 engine/cell_class.py 与 gui/cell_class.py）：不算断链，
            # 但提示「无法确定指哪一个」，免得文档写得含糊
            return 'AMBIGUOUS:' + ','.join(sorted(hits)[:3])
    return None


def resolve_target(root, md_rel, name, stem_map):
    """把「待办清单」「docs/agent/待办清单.md」解析成 md 绝对路径。"""
    n = name.strip().strip('`《》「」').rstrip('：:')
    if not n:
        return None
    if '/' in n or '\\' in n or n.endswith('.md'):
        base = n[:-3] if n.endswith('.md') else n
        for c in (os.path.join(root, base + '.md'),
                  os.path.join(root, os.path.dirname(md_rel), base + '.md')):
            c = os.path.normpath(c)
            if os.path.exists(c):
                return c
        return None
    # 裸名：按 stem 匹配（要求唯一，歧义就不判）
    hits = stem_map.get(n)
    if hits and len(hits) == 1:
        return os.path.join(root, hits[0])
    return None


def scan(root):
    """返回 [(category, sig, 人话)]。sig 用于 baseline diff。"""
    md_all = all_md_files(root)
    stem_map = {}
    for rp in md_all:
        stem = os.path.basename(rp)[:-3]
        stem_map.setdefault(stem, []).append(rp)

    name_index = build_name_index(root)
    findings = []
    sec_cache = {}

    for md_rel, md_abs in iter_md_files(root):
        src = _read(md_abs)
        lines = src.splitlines()
        for ln, line in enumerate(lines, 1):
            # --- 1. 文件引用 ---
            for bt in BT_RE.findall(line):
                tok = bt.strip()
                if not tok or ' ' in tok and '.' not in tok:
                    continue
                # 只取看起来像路径的那一段（反引号里可能夹着说明文字）
                m = re.match(r'^([\w\u4e00-\u9fff./\\-]+)$', tok)
                if not m:
                    continue
                tok = m.group(1)
                ext = tok.rsplit('.', 1)[-1].lower() if '.' in tok.rsplit('/', 1)[-1] else ''
                if not (tok.endswith('/') or ext in FILE_EXT):
                    continue
                if tok.startswith('http') or tok.startswith('~'):
                    continue
                if len(tok.rstrip('/\\')) < 2:  # 伪 token（单独的 `/` 之类）
                    continue
                r = resolve_file_ref(root, md_rel, tok, name_index)
                if r is not None:
                    if r.startswith('AMBIGUOUS:'):
                        findings.append(
                            ('ambiguous', 'AM|%s|%d|%s' % (md_rel, ln, tok.rstrip('/\\')),
                             '%s:%d  同名多个，无法确定指哪一个：`%s` → %s'
                             % (md_rel, ln, tok, r[len('AMBIGUOUS:'):])))
                    continue
                norm = tok.rstrip('/\\')
                why = known_broken_reason(norm)
                if why is None and HISTORY_HINT_RE.search(line):
                    why = '历史溯源引用（本行含搬来/并入/已删等溯源动词），非指路'
                if why is None and PLANNED_HINT_RE.search(line):
                    why = '规划中的文件（本行含建议/新增/计划等），非断链'
                if why is None and md_rel.endswith('待办清单.md'):
                    # 待办清单本来就会提到"要建的模块"，提到不存在的文件是正常的
                    why = '待办清单中提到的待建 / 待定文件，非断链'
                if why:
                    findings.append(('known_broken', 'KB|%s|%d|%s' % (md_rel, ln, norm),
                                     '%s:%d  已知断链（白名单）：`%s` —— %s'
                                     % (md_rel, ln, tok, why)))
                    continue
                # 文档与代码才当断链；产物 / 资源 / 一次性脚本只提示
                if ext in ARTIFACT_EXT or norm in RESOURCE_DIRS \
                        or (ext == 'py' and ONE_OFF_RE.match(os.path.basename(tok))):
                    findings.append(('artifact_ref', 'AR|%s|%d|%s' % (md_rel, ln, norm),
                                     '%s:%d  产物/资源不存在（不视为断链）：`%s`'
                                     % (md_rel, ln, tok)))
                    continue
                findings.append(('file_ref', 'FR|%s|%d|%s' % (md_rel, ln, norm),
                                 '%s:%d  文件不存在：`%s`' % (md_rel, ln, tok)))

            # --- 2. 节号引用 ---
            for m in SEC_RE.finditer(line):
                name, num = m.group(1), m.group(2)
                tgt = resolve_target(root, md_rel, name, stem_map)
                if tgt is None:
                    continue
                key = rel(root, tgt)
                if key not in sec_cache:
                    sec_cache[key] = section_numbers(tgt)
                nums = sec_cache[key]
                want = num if '.' in num else str(cn2int(num))
                if not nums:
                    findings.append(('sec_unverifiable',
                                     'SU|%s|%d|%s|%s' % (md_rel, ln, key, want),
                                     '%s:%d  目标无编号节，无法校验：`%s §%s`'
                                     % (md_rel, ln, key, num)))
                elif want not in nums:
                    findings.append(('sec_ref',
                                     'SR|%s|%d|%s|%s' % (md_rel, ln, key, want),
                                     '%s:%d  节号不存在：`%s §%s`（现有节号：%s）'
                                     % (md_rel, ln, key, num,
                                        ', '.join(sorted(nums, key=lambda x: cn2int(x.split('.')[0]))))))
    return findings


CATS = ['file_ref', 'sec_ref', 'ambiguous', 'artifact_ref',
        'sec_unverifiable', 'known_broken']


def main(argv=None):
    ap = argparse.ArgumentParser(prog='doclink_check',
                                 description='GatenneaSlider 文档引用校验器')
    here = os.path.dirname(os.path.abspath(__file__))
    default_root = os.path.dirname(here)
    ap.add_argument('--root', default=default_root, help='仓库根目录')
    ap.add_argument('--out', default=None, help='报告输出文件（默认 stdout）')
    ap.add_argument('--baseline', default=None, help='基线 JSON（diff 模式）')
    ap.add_argument('--emit-baseline', default=None, help='把当前签名集写成基线 JSON')
    ap.add_argument('--strict', action='store_true',
                    help='出现 NEW 回归（或无基线时有 file_ref/sec_ref）时退出码非零')
    args = ap.parse_args(argv)

    findings = scan(args.root)
    by = {c: [] for c in CATS}
    for cat, sig, text in findings:
        by[cat].append((sig, text))

    lines = ['=== GatenneaSlider 文档引用校验 (root=%s) ===' % args.root]
    for c in CATS:
        lines.append('  - %s: %d' % (c, len(by[c])))
    lines.append('')
    for c in CATS:
        if by[c]:
            lines.append('--- %s ---' % c)
            lines.extend(t for _s, t in by[c])
            lines.append('')

    cur = set(s for _c, s, _t in findings)

    if args.emit_baseline:
        with open(args.emit_baseline, 'w', encoding='utf-8') as fh:
            json.dump({'signatures': sorted(cur)}, fh, ensure_ascii=False, indent=2)
        lines.append('baseline 已写入 %s（%d 条签名）' % (args.emit_baseline, len(cur)))

    base = None
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, encoding='utf-8') as fh:
            base = set(json.load(fh).get('signatures', []))
        new = sorted(cur - base)
        resolved = sorted(base - cur)
        lines.append('=== diff vs 基线 %s ===' % args.baseline)
        lines.append('NEW（新引入）: %d' % len(new))
        lines.extend('  + ' + s for s in new)
        lines.append('RESOLVED（已修复）: %d' % len(resolved))
        lines.extend('  - ' + s for s in resolved)
        if not new:
            lines.append('OK: 无新增回归')
    elif args.baseline:
        lines.append('!! 基线文件不存在：%s' % args.baseline)

    out = '\n'.join(lines) + '\n'
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(out)
    else:
        sys.stdout.write(out)

    if not args.strict:
        return 0
    if base is not None:
        return 1 if (cur - base) else 0
    # 无基线：白名单与「无法校验」不算失败，真断链算
    return 1 if (by['file_ref'] or by['sec_ref']) else 0


if __name__ == '__main__':
    sys.exit(main())
