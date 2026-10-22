"""无头验证：点击捆绑块内部缝 → 应判定为选滑块（整组随动），而非「选不动」。

核心回归：2a460bb 之前点击内部缝会弹「这条缝卡在捆绑块内部：选不动」，
用户反馈「它已经是一个整体，应该判定为选中滑块」。本测试确认：
  1. 点击内部缝不再产生「选不动」提示；
  2. 该点击被当作选滑块处理（预设一个相邻外缝后，整组被 opt 选中）。
"""
import os
import sys
import queue

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
from GUI import SliderGUI
from gui import design_styles


def _boot():
    gui = SliderGUI(m=5, n=5, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    # 启动会自动恢复上一会话（config/temp_history.json）：先建干净局面，
    # 否则残留的谜题/历史会让后面的 apply_pattern 叠在旧局上，点击判定全偏
    gui.new_puzzle(5, 5, 2)
    # 关闭会拦截棋盘点击的模态层
    for attr in ('_update_in_progress',):
        setattr(gui, attr, False)
    data = design_styles.load_style(gui.config_dir, '演示-捆绑')
    cells = [tuple(p) for p in data['cells']]
    groups = {}
    for k, v in (data.get('groups') or {}).items():
        r, c = k.split(',')
        groups[(int(r), int(c))] = int(v)
    gui.game.apply_pattern(cells, groups)
    gui.game.set_goal_pattern(cells)
    return gui


def test_bandage_internal_seam_click_selects_block():
    gui = _boot()
    bi = gui.game.bandage_internal_seams()
    assert bi, "演示-捆绑 应当有内部缝集合"
    # gid1=顶行1x5(v0..v3)，gid2=2x2(rows2-3,cols1-2)->(h2),(v1)
    assert ('v', 1) in bi and ('h', 2) in bi, f"内部缝集合异常: {sorted(bi)}"

    # 扫描出一个命中内部缝的屏幕坐标（演示-捆绑的内部缝）
    target_gap = ('h', 2)  # gid2 内部水平缝（行2与行3之间）
    W, H = gui.screen.get_width(), gui.screen.get_height()
    p = None
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            g = gui.get_gap_at_pos(x, y)
            if g == target_gap:
                p = (x, y)
                break
        if p:
            break
    assert p is not None, f"没扫到内部缝 {target_gap} 的屏幕坐标"

    # 预设一个相邻外缝（gid2 上方的 ('h',1)），模拟「已选缝、再点块」的正常流程
    gui.selected_gap = ('h', 1)
    gui.macro_notify_msg = None

    # 模拟点击内部缝
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=p)
    pygame.event.post(ev)
    gui.handle_events()

    # 断言 1：不再弹「选不动」
    assert gui.macro_notify_msg != ("这条缝卡在捆绑块内部：选不动"
                                    "（整组随动，不能单独拆开）"), \
        f"内部缝仍弹「选不动」，bug 未修复：{gui.macro_notify_msg!r}"

    # 断言 2：被当作选滑块——gid2 整组（4 块）应被 opt 选中（刚性整体）
    gid2 = {(2, 1), (2, 2), (3, 1), (3, 2)}
    opted = {(b.location[0], b.location[1]) for b in gui.game.blocks if b.be_opted}
    assert gid2.issubset(opted), f"点内部缝未把整组当滑块选中: opted={sorted(opted)}"

    # 断言 3：selected_gap 未被污染（仍是预设的外缝）
    assert gui.selected_gap == ('h', 1), f"selected_gap 异常: {gui.selected_gap}"
    print("OK: 内部缝点击 → 选滑块，整组刚性选中，无「选不动」")


if __name__ == '__main__':
    test_bandage_internal_seam_click_selects_block()
