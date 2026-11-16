# -*- coding: utf-8 -*-
"""滚动条滚轮自适应步长护栏（2026-11-17，§四十四.4）。

用户报：「帮助的滑动条灵敏度太低，似乎和设置用的不是同一个，需要和后者
一致」。根因：两处共用同一 Scrollbar、同一 step=30px，差异全在**步长占
总内容的比例**——设置内容短（30px ≈ 2~6%），帮助全文数千 px（30px ≈
0.6%），观感差数倍。

修法：on_wheel 默认 step=None → `max(30, max_scroll × 4%)`。短内容
（max_scroll ≤ 750）完全退化为旧 30px（设置侧基准零变化），长内容步长
随长度放大，两处相对灵敏度一致。

判据（组件级，不需要 GUI）：
  W1 短内容（max_scroll=600 < 750）→ 一格仍滚 30px（旧行为不变）；
  W2 长内容（max_scroll=4500）→ 一格滚 4500×4%=180px（>30，提速生效）；
  W3 显式传 step → 走固定步长语义；
  W4 反向滚（dy<0）与边界夹紧照常（不越界）。

执行：D:/python/python.exe test/_test_scrollbar_wheel_step.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gui.scrollbar import Scrollbar                        # noqa: E402

_failures = []


def check(name, cond, extra=''):
    print('[%s] %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        _failures.append(name)


def make_sb(content, viewport):
    sb = Scrollbar()
    sb.layout(0, 0, 200, content, viewport)
    return sb


def main():
    # on_wheel 语义：scroll_new = scroll - dy*step（dy=+1 向回看、dy=-1 往下看）。
    # 步长判据一律从中点起算，避免顶/底夹紧把步长吞掉。
    # W1 短内容：max_scroll=600，4%=24 < 30 → 下限 30（旧口径）
    sb = make_sb(1100, 500)            # max=600
    sb.set_scroll(300)
    sb.on_wheel(-1)                    # 往下看一格 → +step
    check('W1 短内容一格仍滚 30px（设置侧基准不变）', sb.scroll == 330,
          f'scroll={sb.scroll}')

    # W2 长内容：max=4500，4%=180 > 30 → 自适应提速
    sb = make_sb(4970, 470)            # max=4500
    sb.set_scroll(2250)
    sb.on_wheel(-1)
    check('W2 长内容一格滚 4%（180px，帮助侧提速）', sb.scroll == 2430,
          f'scroll={sb.scroll}')

    # W3 显式 step：固定步长语义保留
    sb = make_sb(4970, 470)
    sb.set_scroll(2250)
    sb.on_wheel(-1, step=99)
    check('W3 显式 step=99 走固定步长', sb.scroll == 2349, f'scroll={sb.scroll}')

    # W4 反向 + 夹紧：顶部向上滚不越 0；往下滚到底不越 max
    sb = make_sb(4970, 470)
    sb.set_scroll(0)
    sb.on_wheel(1)
    check('W4a 顶部向回看不越界', sb.scroll == 0, f'scroll={sb.scroll}')
    sb.on_wheel(-999)
    check('W4b 满格往下看到底夹紧', sb.scroll == sb._max_scroll(),
          f'scroll={sb.scroll}/{sb._max_scroll()}')

    # 附：无内容（不需要滚）时 on_wheel 静默无效果
    sb = make_sb(100, 200)
    sb.on_wheel(1)
    check('W5 无滚动内容时不动', sb.scroll == 0, f'scroll={sb.scroll}')

    print('==== %s（%d 项失败）'
          % ('全部通过' if not _failures else '有失败', len(_failures)))
    return 1 if _failures else 0


if __name__ == '__main__':
    sys.exit(main())
