# -*- coding: utf-8 -*-
"""操作日志：玩家点了什么、系统判成了什么、给了一句什么反馈。

存在的唯一理由是排障。「点了没反应」「提示不对」这类问题靠口头描述很难
落到具体坐标和代码分支上——玩家说得清的是「我点了这道缝」，说不清的是
这个点击在哪个分支被吞掉、裁定出的缝隙是不是他想点的那条。有了这份日志，
照着时间戳就能复盘每一击：落点的屏幕/世界坐标、命中判定的结果、右下角
提示原文，以及米字格两条「只给提示不动作」路径的具体理由。

默认关闭，在 设置 → 文件 → 操作日志 里打开（开关状态记进 config.json）。
禁用时 log() 直接返回，不建目录、不写文件。写盘失败一律静默：日志是调试
附属品，绝不能因为它把游戏搞崩。

只记决策点，不记渲染和动画帧——那会把文件瞬间撑爆，也没有诊断价值。
"""
import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(_HERE)
LOG_PATH = os.path.join(BASE_DIR, 'config', 'op_log.jsonl')

_enabled = False
_t0 = time.time()


def set_enabled(flag: bool) -> None:
    """开/关日志（设置对话框点一下，或启动时按 config.json 恢复）"""
    global _enabled
    _enabled = bool(flag)


def log(event: str, **fields) -> None:
    """追加一条日志。event 是事件名，其余是要记的字段。"""
    if not _enabled:
        return
    rec = {
        'ts': time.strftime('%H:%M:%S'),
        'dt': round(time.time() - _t0, 3),
        'event': event,
    }
    rec.update(fields)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
    except Exception:
        pass
