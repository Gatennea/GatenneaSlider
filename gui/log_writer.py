# -*- coding: utf-8 -*-
"""错误/运行日志：一行一条 JSON，追加到 config/error_log.jsonl。

与 gui/op_log.py 同一套写法（同为调试附属品，同样克制），但这条流**常开**：
它记的是异常和启动痕迹，关掉等于把崩溃现场扔掉。两条流分开，别混——
查「点了什么」看 op_log.jsonl，查「炸在哪」看 error_log.jsonl。

放进 config/ 而不是仓库根目录：config/ 已经是运行时用户数据的家
（config.json / keyboard_shortcut.json / temp_history.json / records），
也已在 .gitignore 里；根目录只留代码。打包成 exe 后 config/ 可能不可写
（装进 Program Files 之类），这时退回系统 temp 目录——宁可写到别处，也不
能让「记日志」这件事本身把程序搞崩。

traceback 按行拆成数组，不塞成一个带 \n 的字符串：转义后在编辑器里是一
长条，肉眼和 grep 都用不了；拆开后复制每一帧都方便，要机器读也照样 parse。

只保留一份实现：main.py 的 excepthook 必须在 import 之前装好，本模块只
依赖标准库，import 它没有额外风险。
"""
import json
import os
import sys
import tempfile
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(_HERE)

LOG_PATH = os.path.join(BASE_DIR, 'config', 'error_log.jsonl')
_FALLBACK_PATH = os.path.join(tempfile.gettempdir(), 'gatenneaslider_error_log.jsonl')


def log_paths():
    """按优先级返回候选日志路径（write 逐个试，写进第一个成功的）。

    打包后 ``__file__`` 落在 PyInstaller 的临时解压目录（_MEIxxxx），程序一退
    出整个目录就被删 —— 日志跟着消失，等于没记。2026-10-06 打包版白屏就是
    这么变成悬案的：dist/config/ 里永远找不到 error_log.jsonl。

    所以冻结环境下改写到 **exe 同级的 config/**（用户找得到的地方），
    写不进去再退 %APPDATA%/GatenneaSlider/，最后才退系统 temp。
    """
    if getattr(sys, 'frozen', False):
        paths = [os.path.join(os.path.dirname(sys.executable),
                              'config', 'error_log.jsonl')]
        appdata = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
        if appdata:
            paths.append(os.path.join(appdata, 'GatenneaSlider',
                                      'error_log.jsonl'))
    else:
        paths = [LOG_PATH]
    paths.append(_FALLBACK_PATH)
    return paths

# 单个备份代：超限就把当前文件整体让位给 .old，从零开张。原来那份三个半月
# （2026-06-10 ~ 09-23）就攒到 731KB/12049 行没人管，不设上限迟早把磁盘磨
# 光；只留一代是因为出问题时最近几条才要紧，再往前的基本只看开头
_MAX_BYTES = 4 * 1024 * 1024


def _rotate(path: str) -> None:
    """超限时把现有文件整体改名成 .old（覆盖上一代 .old）"""
    try:
        if os.path.exists(path) and os.path.getsize(path) > _MAX_BYTES:
            os.replace(path, path + '.old')
    except Exception:
        pass


def write(msg: str, level: str = 'error', trace=None) -> None:
    """追加一条日志。msg 是一行摘要；trace 是 traceback 的行列表（可省）。"""
    rec = {
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
        'level': level,
        'msg': msg,
    }
    if trace:
        rec['trace'] = [str(l).rstrip('\n') for l in trace]
    line = json.dumps(rec, ensure_ascii=False, default=str) + '\n'
    for path in log_paths():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _rotate(path)
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line)
            return
        except Exception:
            continue


def exception(msg: str, exc_type, exc_value, exc_tb) -> None:
    """记一条异常：msg 是一行摘要，trace 用 traceback 模块现成的三件套拼。"""
    trace = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    write(msg, trace=trace.splitlines())
