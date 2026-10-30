# -*- coding: utf-8 -*-
"""从 gui/feature_index.py（单一真源）生成《功能总览》快速预览表。

用途：玩家/AI 一屏扫完「有什么功能、在哪、当前形态/模式能不能用」——
只列表不解释（解释在游戏内命令面板与玩家指南）。

用法：D:/python/python.exe tools/gen_feature_overview.py
产出：docs/player/功能总览.md
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gui.feature_index import (FEATURES, FORM_NAMES, MODE_NAMES,  # noqa: E402
                               ALL_FORMS, ALL_MODES, place_text)

OUT = os.path.join(ROOT, 'docs', 'player', '功能总览.md')

KIND_ORDER = ['action', 'setting', 'panel', 'puzzle', 'concept', 'link']
KIND_LABEL = {
    'action': '动作（做了某件事）',
    'setting': '开关 / 设置项',
    'panel': '面板',
    'puzzle': '建局（创造模式）',
    'concept': '概念（不是按钮，是规则）',
    'link': '外部链接',
}


def mark(forms, f):
    return '✓' if f in forms else '—'


def row(f):
    return '| %s | %s | %s | %s |' % (
        f['name'],
        place_text(f['place']),
        ' | '.join(mark(f['forms'], x) for x in ALL_FORMS),
        ' | '.join(mark(f['modes'], x) for x in ALL_MODES),
    )


def main():
    head = []
    head.append('# 功能总览（快速预览）')
    head.append('')
    head.append('> **受众**：玩家 / AI（一屏扫完「有什么」）')
    head.append('>')
    head.append('> 本文由 `tools/gen_feature_overview.py` 从 '
                '`gui/feature_index.py`（功能检索单一真源）自动生成，'
                '共 %d 项。**只列表不解释**——每个功能怎么用、有什么坑，'
                '游戏内按 `Ctrl+K` 开命令面板搜名字（会写位置、用法、当前'
                '形态/模式是否可用）；玩家向详解见 `docs/player/玩家指南.md`。'
                % len(FEATURES))
    head.append('>')
    head.append('> 列含义：✓=支持，—=不支持（不支持时游戏内会说明原因）。'
                '「在哪」按 菜单 → 子菜单 → 项 或 面板/快捷键 描述。')
    head.append('')
    head.append('| # | 功能 | 在哪 | %s | %s |' % (
        ' | '.join(FORM_NAMES[f] for f in ALL_FORMS),
        ' | '.join(MODE_NAMES[m] for m in ALL_MODES)))
    head.append('| --- | --- | --- | %s | %s |' % (
        ' | '.join(['---'] * len(ALL_FORMS)),
        ' | '.join(['---'] * len(ALL_MODES))))
    body = []
    for kind in KIND_ORDER:
        items = [f for f in FEATURES if f['kind'] == kind]
        if not items:
            continue
        body.append('')
        body.append('## %s（%d）' % (KIND_LABEL[kind], len(items)))
        body.append('')
        n0 = 0
        for f in items:
            n0 += 1
            r = row(f)
            # 在行首插入组内序号
            cells = r.split('|')
            r = '| %d |%s' % (n0, '|'.join(cells[1:]))
            body.append(r)
    foot = []
    foot.append('')
    foot.append('---')
    foot.append('')
    foot.append('> 生成时间：%s。功能增删改后重跑 '
                '`tools/gen_feature_overview.py` 即可刷新本表；'
                '改动功能行为请先改 `gui/feature_index.py`（单一真源）。'
                % time.strftime('%Y-%m-%d %H:%M'))
    foot.append('')

    text = '\n'.join(head + body + foot)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print('written %s (%d 功能, %d 行)' %
          (os.path.relpath(OUT, ROOT), len(FEATURES), text.count('\n') + 1))


if __name__ == '__main__':
    main()
