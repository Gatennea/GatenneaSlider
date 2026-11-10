# -*- coding: utf-8 -*-
"""护栏：求解进度「深度0 节点xxx」显示修正（待办 §三十四 第 9 条）。

逐类 emitter 口径验：
  A 组：有真深度的（贪心 / IDA* 搜索中）显示正确深度，不再显示 0 / bound。
  B 组：没有深度概念的（补缺宏 / 自动规划 / 聚拢）不出现「深度」字样。
  C 组：完整通知串（stage 头 + 用时尾）行为判据。
  D 组：旧实现确实会产出「深度0」，证明修复不是空转。
  E 组：接线——GUI 必须走纯函数、IDA* 新层必须发真深度、bound 不得兜底成深度。

执行：D:/python/python.exe -u test/_test_solver_progress_text.py
"""
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gui.progress_text import (format_solver_progress,  # noqa: E402
                               format_solver_notice)

FAILS = []


def check(name, ok, detail=''):
    print(('[PASS] ' if ok else '[FAIL] ') + name
          + ('  %s' % detail if detail else ''))
    if not ok:
        FAILS.append(name)
    return ok


GREEDY = {'stage': 'GREEDY', 'depth': 4, 'bound': 0, 'nodes': 120,
          'path_preview': 'R U R'}
IDA_SEARCH = {'stage': 'IDA*', 'depth': 6, 'bound': 9, 'nodes': 5000,
              'path_preview': 'R U R D'}
IDA_NEW_LAYER = {'stage': 'IDA*', 'depth': 7, 'bound': 7, 'nodes': 0,
                 'path_preview': '开始本层搜索'}
FILL_MACRO = {'stage': '补缺宏', 'nodes': 37, 'path_preview': '封壳中'}
AUTO_PLAN = {'stage': '自动规划·混合流水线', 'nodes': 0,
             'path_preview': '聚拢+GBFS'}


def legacy_detail(p):
    """修复前 GUI.py 内联的那段（复刻，用于 D 组对照）。"""
    bound = p.get('bound', 0)
    nodes = p.get('nodes', 0)
    path_preview = p.get('path_preview', '')
    if nodes or bound:
        return f"深度{bound} 节点{nodes} {path_preview}"
    return path_preview


def text_tests():
    s = format_solver_progress(GREEDY)
    check('A1 贪心显示真深度 4（不是 bound=0）',
          '深度4' in s and '深度0' not in s, s)
    check('A2 贪心节点数保留', '节点120' in s, s)
    s = format_solver_progress(IDA_SEARCH)
    check('A3 IDA* 搜索中显示 g=6（不是迭代上限 bound=9）',
          '深度6' in s and '深度9' not in s, s)
    s = format_solver_progress(IDA_NEW_LAYER)
    check('A4 新层显示本层深度、不出现「节点0」空壳',
          '深度7' in s and '节点0' not in s, s)

    s = format_solver_progress(FILL_MACRO)
    check('B1 补缺宏（无深度概念）不出现「深度」',
          '深度' not in s and '节点37' in s, s)
    s = format_solver_progress(AUTO_PLAN)
    check('B2 自动规划（无深度、nodes=0）只留描述',
          '深度' not in s and '节点' not in s and s == '聚拢+GBFS', s)
    check('B3 空 info 返回空串', format_solver_progress(None) == '')
    s = format_solver_progress({'depth': None, 'nodes': 'x',
                                'path_preview': 'ok'})
    check('B4 非法字段不炸、不兜底出深度', s == 'ok', s)

    s = format_solver_notice(GREEDY, 3.2)
    check('C1 完整通知串（stage 头 + 用时尾）',
          s == '[GREEDY] 深度4 节点120 R U R | 3.2s', s)
    s = format_solver_notice(FILL_MACRO, 1.0)
    check('C2 无深度的通知串里没有「深度0」',
          '深度0' not in s and '深度' not in s, s)

    check('D1 旧实现确实产出「深度0」（修复不是空转）',
          '深度0' in legacy_detail(GREEDY)
          and '深度0' in legacy_detail(FILL_MACRO)
          and '深度9' in legacy_detail(IDA_SEARCH),
          legacy_detail(GREEDY))
    check('D2 新实现逐类都不含「深度0」',
          all('深度0' not in format_solver_progress(p)
              for p in (GREEDY, IDA_SEARCH, IDA_NEW_LAYER,
                        FILL_MACRO, AUTO_PLAN)))


def wiring_tests():
    gui_src = open(os.path.join(ROOT, 'GUI.py'), encoding='utf-8').read()
    check('E1 GUI 走纯函数 format_solver_notice',
          'format_solver_notice(progress, elapsed)' in gui_src
          or 'format_solver_notice(\n' in gui_src)
    check('E2 GUI 不再把 bound 当深度内联',
          '深度{bound}' not in gui_src
          and "bound = progress.get('bound', 0)" not in gui_src)

    from gui import progress_text
    src = inspect.getsource(progress_text)
    check('E3 纯函数不拿 bound 兜底成深度',
          "get('bound'" not in src and "get(\"bound\"" not in src)

    ida_src = open(os.path.join(ROOT, 'solver', 'ida_star.py'),
                   encoding='utf-8').read()
    check('E4 IDA* 新层发真深度（不是 depth=0）',
          "'depth': bound," in ida_src)
    check('E5 IDA* 不再发 depth=0 的新层进度',
          "'depth': 0," not in ida_src)

    # emitter 口径静态核对：贪心有 depth、补缺宏没有 depth 概念
    greedy_src = open(os.path.join(ROOT, 'solver', 'greedy.py'),
                      encoding='utf-8').read()
    fill_src = open(os.path.join(ROOT, 'solver', 'ml', 'fill_macro.py'),
                    encoding='utf-8').read()
    check('E6 贪心 emitter 发 depth=len(path)',
          "'depth': len(path)" in greedy_src)
    # ⚠️ 第一版写成 `... if 'def _progress' in fill_src else True`，
    # 但实际函数叫 _emit → 恒走 else True，是假判据。直接盯 emitter 本体。
    check('E7 补缺宏 emitter（_emit）没有深度概念',
          'def _emit(' in fill_src
          and "'nodes': nodes or 0" in fill_src
          and "'depth'" not in fill_src)


def main():
    text_tests()
    wiring_tests()
    print('==== %s（%d 项失败）' %
          ('全部通过' if not FAILS else '有失败', len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
