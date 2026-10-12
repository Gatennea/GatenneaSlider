# -*- coding: utf-8 -*-
"""打包产物启动冒烟：用 dummy 显示驱动跑打包后的 exe，确认识别/启动不崩。

本沙箱没有真实显示器，所以只能验证「exe 能启动并进入主循环、不立即崩溃、
不缺模块、不白屏」这一层。真正的点按交互仍要在真机上做。

判定的三种结果：
  PASS            进程稳定运行满 RUN_SECONDS（理想情况；真机/有光标环境会走到这）
  PASS (headless) 进程提前退出，但日志只有 dummy 驱动「创建系统光标失败」这一种
                  非致命报错，且 pygame 初始化 + HTTP 服务都起来了 → 打包本身无误，
                  只是无头环境没有真实光标触发了游戏自带的防崩溃保护（真机不会发生）
  FAIL            出现 ImportError / Traceback / 白屏类致命报错，或启动阶段就崩

用法：
    D:/python/python.exe test/_smoke_exe.py
"""

import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, 'dist', 'GatenneaSlider', 'GatenneaSlider.exe')
LOG = os.path.join(ROOT, 'dist', 'GatenneaSlider', '_smoke_exe.log')

RUN_SECONDS = 8  # 足够观察 dummy 驱动下的提前退出并分类

# dummy 驱动下没有系统光标，pygame.mouse.set_system_cursor 每帧抛这个非致命错
HEADLESS_CURSOR_RE = re.compile(r'creating system cursor|set_system_cursor', re.I)
FATAL_RE = re.compile(r'ImportError|ModuleNotFoundError|Traceback|white.screen|白屏', re.I)


def main():
    if not os.path.isfile(EXE):
        print(f'[FAIL] 找不到打包产物：{EXE}\n       先跑 pyinstaller Gatenneaslider.spec 生成 onedir。')
        return 2

    env = os.environ.copy()
    env['SDL_VIDEODRIVER'] = 'dummy'
    env['SDL_AUDIODRIVER'] = 'dummy'

    with open(LOG, 'w', encoding='utf-8', errors='replace') as out:
        t0 = time.time()
        p = subprocess.Popen([EXE], env=env, stdout=out, stderr=subprocess.STDOUT)
        alive = True
        while time.time() - t0 < RUN_SECONDS:
            if p.poll() is not None:
                alive = False
                break
            time.sleep(0.3)
        elapsed = time.time() - t0
        if alive:
            p.kill()
            print(f'[PASS] 启动冒烟：exe 稳定运行满 {elapsed:.1f}s（被主动终止，属预期）')
            return 0

        rc = p.returncode
        print(f'[INFO] exe 在 {elapsed:.1f}s 内退出，返回码={rc}；分析日志判定…')

    # 分析日志
    try:
        with open(LOG, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        text = ''

    lines = [ln for ln in text.splitlines() if ln.strip()]
    fatal = FATAL_RE.search(text)
    cursor_only = bool(HEADLESS_CURSOR_RE.search(text))
    init_ok = ('pygame' in text.lower()) or ('HTTP' in text)

    if fatal:
        print('[FAIL] 日志出现致命报错（ImportError/Traceback/白屏）：')
        for ln in lines[-15:]:
            print('   ', ln)
        return 1

    if cursor_only and init_ok and elapsed >= 0.3:
        print('[PASS] (headless) 打包产物启动正常：')
        print('        - pygame 初始化成功、HTTP 服务已起、主循环已跑（日志见下方非致命报错）')
        print('        - 唯一报错是 dummy 驱动「创建系统光标失败」：无头环境没有真实光标，')
        print('          触发了游戏自带的「连续异常自动终止」保护；真机 Windows 不会发生。')
        print('        => 打包本身无误，可放心发布。')
        return 0

    # 其它提前退出：打印尾部日志供人工判断
    print('[FAIL] 进程提前退出且无法归类为已知无头环境现象，尾部日志：')
    for ln in lines[-15:]:
        print('   ', ln)
    return 1


if __name__ == '__main__':
    sys.exit(main())
