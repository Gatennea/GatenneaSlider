# -*- coding: utf-8 -*-
"""求解进度通知正文的格式化（纯函数，可单测）。

待办 §三十四 第 9 条：用户实测「深度0 节点xxx」。旧实现内联在
``GUI.py`` 的主循环里，把 ``bound``（IDA* 的迭代上限）当成深度显示，
还拿 ``if nodes or bound`` 当显示门槛，于是两类错一起冒出来：

  * 贪心 ``greedy.py`` 发 ``depth=len(path)`` / ``bound=0`` /
    ``nodes=iteration`` → 显示成「**深度0** 节点N」＝**有深度但没显示对**；
  * 补缺宏 / 自动规划 / 聚拢类发 ``nodes>0`` 却**根本没有深度概念**
    （``fill_macro._progress``、``auto_solver.emit``）→ 被套上「深度0」
    空壳＝**没深度却显示了深度**。
  * IDA* 搜索中发 ``depth=g`` / ``bound=bound`` → 显示成「深度{bound}」，
    把迭代上限当成了当前深度，同样错。

用户要求「把没深度的去掉这个显示，没显示对的改成正确的深度显示」。
正解：只认 ``depth``（真实搜索深度），>0 才印「深度{d}」；``nodes>0``
才印「节点{n}」；两者皆无就只留 ``path_preview``。``bound`` 一律不参与
显示——它是搜索上限，不是深度。
"""


def format_solver_progress(info):
    """把进度 dict 格式化成通知正文（不含 stage 头与用时尾）。

    非法 / 缺失字段一律当 0，绝不把 ``bound`` 兜底成深度。返回纯字符串，
    无 pygame / GUI 依赖，便于护栏逐个 emitter 口径验。
    """
    if not info:
        return ''
    preview = info.get('path_preview') or ''
    try:
        depth = int(info.get('depth') or 0)
    except (TypeError, ValueError):
        depth = 0
    try:
        nodes = int(info.get('nodes') or 0)
    except (TypeError, ValueError):
        nodes = 0
    parts = []
    if depth > 0:
        parts.append('深度%d' % depth)
    if nodes > 0:
        parts.append('节点%d' % nodes)
    if not parts:
        return preview
    return ' '.join(parts) + ((' ' + preview) if preview else '')


def format_solver_notice(progress, elapsed):
    """求解中的完整通知串：stage 头 + 正文 + 用时尾。

    GUI 主循环在这里只做一次调用；把拼接也放进纯函数，护栏就能直接
    断言「屏幕上会出现什么」，不必去驱动整个 pygame 主循环。
    """
    stage = (progress.get('stage', '') if progress else '') or ''
    head = '[%s] ' % stage if stage else ''
    return '%s%s | %.1fs' % (head, format_solver_progress(progress), elapsed)


# 求解算法 key → 简洁全称。完成提示 / 进度文案统一用这张表，避免各处
# 一会儿写「自动规划」、一会儿写「混合求解」的口径漂移。
SOLVER_DISPLAY_NAME = {
    'hybrid': '混合求解',
    'gather_gradient': '梯度聚拢',
    'gap_macro': '填洞补缺',
    'gather': '单次聚拢',
    'pick_fill': '选块填空',
    'table': '查表求解',
    'ida_star': 'IDA*求解',
    'fast': 'IDA*快速',
    'greedy': '贪心爬山',
}


def solver_display_name(key):
    """算法 key → 展示用全称（未知 key 原样返回，绝不编个假名字）。"""
    return SOLVER_DISPLAY_NAME.get(key, key or '求解')


def format_solve_done(name, total, elapsed_ms=None, solved=True, extra=''):
    """求解完成提示：``算法全称：已复原/完成 · N 步 · 用时 · TPS``。

    纯函数，便于护栏直接断言屏幕文案。``elapsed_ms`` 缺失或 ≤0 时**不印**
    用时与 TPS（宁可少说，也不编假数字）；``extra`` 放各算法自己的补充
    （如「停在聚拢度最高态 0.97」）。
    """
    try:
        n = max(0, int(total or 0))
    except (TypeError, ValueError):
        n = 0
    parts = ['%s：%s' % (name or '求解', '已复原' if solved else '完成'),
             '· %d 步' % n]
    try:
        ms = int(elapsed_ms) if elapsed_ms is not None else 0
    except (TypeError, ValueError):
        ms = 0
    if ms > 0:
        sec = ms / 1000.0
        parts.append('· 用时 %.1fs' % sec)
        parts.append('· TPS %.1f' % (n / sec))
    if extra:
        parts.append('· ' + str(extra))
    return ' '.join(parts)
