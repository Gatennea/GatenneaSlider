# -*- coding: utf-8 -*-
"""§五十九 护栏：帮助三页 / 三维文档 / 首次引导 / 常驻操作卡 / 入口告知。

覆盖（对应 docs/agent/待办清单.md §59 的 A–E 验收）：
- A 三页可切、每页滚动独立、默认页按局形态、检索跨页不丢、二维/三维页都有内容
- B 三份文档存在且进打包（spec datas）与 README 索引
- C 首次进三维局弹 4 步引导、跳过/走完记住、第二次不弹、菜单可重看、二维不弹
- D 右下角操作卡可开可收、卡外点击放行、二维不出现
- E 谜题菜单三维子菜单行 + 自定义框「查看操作」→ 帮助三维页

运行：python test/_test_help_cubic59.py
"""
import json
import os
import queue
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402

PASSED = 0
FAILED = 0


def check(cond, label, detail=''):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f'PASS: {label}')
    else:
        FAILED += 1
        d = f' -- {detail}' if detail else ''
        print(f'FAIL: {label}{d}')


def new_gui(config_dir=None):
    gui = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                    ext_state={'enabled': True, 'token': 'T', 'port': 7195})
    if config_dir:
        gui.config_dir = config_dir
        gui.config_path = os.path.join(config_dir, 'config.json')
        gui.temp_history_path = os.path.join(config_dir, 'temp_history.json')
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    return gui


def click(gui, pos):
    """投一次左键点击走完整分发（posted 事件 + handle_events，与真实路径同源）。"""
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    gui.handle_events()


# ----------------------------------------------------------------------
# A. 帮助三页
# ----------------------------------------------------------------------
def run_tab_a():
    print('\n== A 帮助三页 ==')
    gui = new_gui()

    # 三页都能加载、各有内容
    lines_2d = gui._load_help_lines('2d')
    lines_3d = gui._load_help_lines('3d')
    lines_common = gui._load_help_lines('common')
    check(len(lines_2d) > 10 and len(lines_3d) > 10 and len(lines_common) > 10,
          '三页均有内容', (len(lines_2d), len(lines_3d), len(lines_common)))
    hdr = lambda ls: [t for t, h in ls if h]  # noqa: E731
    check('怎么玩' in hdr(lines_2d) and '快捷键' not in hdr(lines_2d),
          '二维页有「怎么玩」、无「快捷键」（章节拆分正确）', hdr(lines_2d))
    check('快捷键' in hdr(lines_common) and '怎么玩' not in hdr(lines_common),
          '通用页有「快捷键」、无「怎么玩」（章节拆分正确）', hdr(lines_common))
    check('打开三维谜题' in hdr(lines_3d),
          '三维页含「打开三维谜题」', hdr(lines_3d)[:3])

    # 按缓存：同 tab 二次取同一对象（缓存生效）
    check(gui._load_help_lines('2d') is lines_2d, '按 tab 缓存生效')

    # 标题跟页走
    gui.help_tab = '2d'
    check('二维' in gui._help_title(), '标题含当前页', gui._help_title())
    gui.help_tab = '3d'
    check('三维' in gui._help_title(), '标题跟到三维页', gui._help_title())

    # 绘制出页签矩形，点击页签切页（真实事件路径）
    gui.help_tab = '2d'
    gui.show_help = True
    gui.draw_help_dialog()
    check(set(gui.help_tab_rects) == {'2d', '3d', 'common'}, '页签矩形齐全',
          sorted(getattr(gui, 'help_tab_rects', {})))
    click(gui, gui.help_tab_rects['3d'].center)
    check(gui.help_tab == '3d', '点击页签切到三维页', gui.help_tab)

    # 每页滚动独立：切页换出/换回一致（对 scrollbar 夹紧值免疫）
    gui.help_scrollbar.set_scroll(100)
    want = gui.help_scrollbar.scroll
    click(gui, gui.help_tab_rects['2d'].center)   # 3d → 2d：3d 的滚动换出
    check(abs(gui.help_scroll_pos.get('3d', -1) - want) < 0.01,
          '切页时旧页滚动位换出', gui.help_scroll_pos)
    check(gui.help_tab == '2d', '切回二维页', gui.help_tab)
    # 二维页换入的是自己记录的位（初始 0），不是 3d 的 100
    check(abs(gui.help_scrollbar.scroll - gui.help_scroll_pos['2d']) < 0.01,
          '切页时新页滚动位换入', gui.help_scrollbar.scroll)

    # 默认页按局形态
    gui.show_help = False
    gui.cubic_mode = False
    gui._open_help()
    check(gui.show_help and gui.help_tab == '2d', '二维局默认二维页', gui.help_tab)
    gui.show_help = False
    gui.cubic_mode = True
    gui._open_help()
    check(gui.help_tab == '3d', '三维局默认三维页', gui.help_tab)

    # 检索跨页：查询非空时结果与当前页无关，切页不丢
    gui.help_query = '撤销'
    gui.help_sel = 0
    gui.draw_help_dialog()
    n_before = len(gui.help_result_rects or [])
    check(n_before > 0, '检索有命中', n_before)
    gui.help_tab = '2d'
    gui.draw_help_dialog()
    n_after = len(gui.help_result_rects or [])
    check(n_after == n_before and n_after > 0, '切页检索结果不丢（跨页搜）',
          (n_before, n_after))

    # 打开帮助后正文用对应页文件（cache_key 含 tab，切页整张重渲）
    gui.help_query = ''
    gui.help_tab = '3d'
    gui.draw_help_dialog()
    key3 = gui._help_content_cache['key']
    gui.help_tab = '2d'
    gui.draw_help_dialog()
    key2 = gui._help_content_cache['key']
    check(key3 != key2, '正文缓存键含 tab（切页重渲）', (key2, key3))
    gui.show_help = False
    gui.cubic_mode = False


# ----------------------------------------------------------------------
# B. 文档与打包同步
# ----------------------------------------------------------------------
def run_docs_b():
    print('\n== B 三维文档与同步 ==')
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p3d = os.path.join(root, 'docs', 'player', '三维操作说明.md')
    pcommon = os.path.join(root, 'docs', 'player', '通用说明.md')
    p2d = os.path.join(root, 'docs', 'player', '操作说明.md')
    check(os.path.isfile(p3d), 'docs/player/三维操作说明.md 存在')
    check(os.path.isfile(pcommon), 'docs/player/通用说明.md 存在')
    check(os.path.isfile(p2d), 'docs/player/操作说明.md 存在')
    with open(p3d, encoding='utf-8') as f:
        t3 = f.read()
    for kw in ('切面', '虚拟键盘', '撤销', '创造', '视角'):
        check(kw in t3, f'三维文档含「{kw}」')
    spec = open(os.path.join(root, 'Gatenneaslider.spec'), encoding='utf-8').read()
    check('三维操作说明.md' in spec, 'spec datas 收录三维文档（打包可读）')
    check('通用说明.md' in spec, 'spec datas 收录通用文档')
    readme = open(os.path.join(root, 'docs', 'README.md'), encoding='utf-8').read()
    check('三维操作说明.md' in readme and '通用说明.md' in readme,
          'docs/README.md 索引含两份新文档')
    guide = open(os.path.join(root, 'docs', 'player', '玩家指南.md'), encoding='utf-8').read()
    check('三维形态' in guide and '三维操作说明' in guide,
          '玩家指南补三维节并指到三维文档')


# ----------------------------------------------------------------------
# C. 首次进入三维引导
# ----------------------------------------------------------------------
def run_intro_c():
    print('\n== C 三维新手引导 ==')
    tmp = tempfile.mkdtemp(prefix='s59_intro_')
    gui = new_gui(tmp)

    # 二维局不弹
    gui.cubic_intro_seen = False
    gui.new_puzzle(6, 6, 2)
    check(not gui._cubic_intro_active, '二维局不弹引导')

    # 首次进三维局弹
    check(gui.new_cubic_puzzle(3, 3, 3, 1) is True, '三维建局成功')
    check(gui._cubic_intro_active and gui._cubic_intro_step == 0,
          '首次进三维局弹引导（第1步）', (gui._cubic_intro_active, gui._cubic_intro_step))
    check(len(gui.CUBIC_INTRO_STEPS) == 4, '引导共 4 步', len(gui.CUBIC_INTRO_STEPS))

    # 绘制登记按钮，点「下一步」推进，第 4 步完成并记住看过
    gui.draw_cubic_intro()
    check(gui._cubic_intro_rect is not None and len(gui._cubic_intro_btns) == 2,
          '引导卡绘制出卡体与两按钮')
    for i in range(3):
        gui.draw_cubic_intro()
        gui._cubic_hud_click(gui._cubic_intro_btns[1][0].center)
    check(gui._cubic_intro_active and gui._cubic_intro_step == 3,
          '三步后停在第 4 步', gui._cubic_intro_step)
    gui.draw_cubic_intro()
    gui._cubic_hud_click(gui._cubic_intro_btns[1][0].center)
    check(not gui._cubic_intro_active and gui.cubic_intro_seen,
          '第 4 步完成 → 关闭并记住看过')

    # 看过后第二次进三维局不弹
    gui.new_cubic_puzzle(3, 3, 3, 1)
    check(not gui._cubic_intro_active, '看过后第二次进三维不弹')

    # 跳过路径：弹出 → 点「跳过」→ seen 落盘
    gui.cubic_intro_seen = False
    gui.new_cubic_puzzle(3, 3, 3, 1)
    check(gui._cubic_intro_active, '重置后再次弹出')
    gui.draw_cubic_intro()
    gui._cubic_hud_click(gui._cubic_intro_btns[0][0].center)
    check(not gui._cubic_intro_active and gui.cubic_intro_seen,
          '跳过 → 关闭并记住看过')
    with open(gui.config_path, encoding='utf-8') as f:
        cfg = json.load(f)
    check(cfg.get('cubic_intro_seen') is True, 'seen 已落盘 config.json',
          cfg.get('cubic_intro_seen'))

    # 菜单重看（谜题菜单三维子菜单行 → 走真实事件分支）
    row = [p for p in gui.puzzle_sub_presets['cubic']
           if len(p) == 2 and p[1] == '__intro_replay__']
    check(bool(row), '三维子菜单含「重看新手引导」行')
    gui._cubic_intro_start()
    check(gui._cubic_intro_active and gui._cubic_intro_step == 0,
          '重看入口可重新打开引导')

    # 引导卡卡体吃点击；D 未画时卡外返回 False（放行给棋盘）
    gui.draw_cubic_intro()
    check(gui._cubic_hud_click(gui._cubic_intro_rect.center) is True,
          '引导卡卡体命中被吞')
    gui._cubic_intro_active = False   # 关掉引导，剩下的点击只受 D 影响
    check(gui._cubic_hud_click((3, 3)) is False,
          '卡外放行（引导关闭、D 折叠时）')
    gui._cubic_intro_active = True
    gui._cubic_intro_close(seen=False)
    check(not gui._cubic_intro_active, '关闭引导不置 seen')
    check(gui.cubic_intro_seen is True, 'seen 保持 True')


# ----------------------------------------------------------------------
# D. 三维常驻操作卡
# ----------------------------------------------------------------------
def run_ops_d():
    print('\n== D 右下角操作卡 ==')
    gui = new_gui()

    # 二维不出现
    gui.cubic_mode = False
    gui.draw_cubic_ops_card()
    check(gui._cubic_ops_toggle_rect is None and gui._cubic_ops_rect is None,
          '二维局不画操作卡')
    check(gui._cubic_hud_click((gui.screen_width - 40, gui.screen_height - 40))
          is False, '二维局卡位点击不消费')

    # 三维默认折叠 → 点开 → 收起
    gui.cubic_mode = True
    gui._cubic_ops_open = False
    gui.draw_cubic_ops_card()
    check(gui._cubic_ops_toggle_rect is not None and gui._cubic_ops_rect is None,
          '三维默认折叠只画小钮')
    toggle = gui._cubic_ops_toggle_rect
    check(gui._cubic_hud_click(toggle.center) is True, '折叠钮命中被吞')
    check(gui._cubic_ops_open, '点击展开')
    gui.draw_cubic_ops_card()
    check(gui._cubic_ops_rect is not None and len(gui._cubic_ops_btns) == 3,
          '展开画出卡体与三个按钮', len(gui._cubic_ops_btns))
    # 卡体（非按钮区）吃点击，卡外放行
    body = (gui._cubic_ops_rect.centerx, gui._cubic_ops_rect.y + 60)
    check(gui._cubic_hud_click(body) is True, '卡体吃点击（不透到棋盘）')
    check(gui._cubic_hud_click((2, 2)) is False, '卡外点击放行给棋盘')
    # 收起
    check(gui._cubic_hud_click(gui._cubic_ops_toggle_rect.center) is True,
          '卡头命中被吞')
    check(not gui._cubic_ops_open, '点击收起')
    # 「完整说明」按钮 → 帮助三维页（D↔A 联动）
    gui.draw_cubic_ops_card()
    gui._cubic_hud_click(gui._cubic_ops_toggle_rect.center)  # 展开
    gui.draw_cubic_ops_card()
    gui._cubic_hud_click(gui._cubic_ops_btns[2][0].center)
    check(gui.show_help and gui.help_tab == '3d', '「完整说明」直达帮助三维页',
          (gui.show_help, gui.help_tab))
    gui.show_help = False


# ----------------------------------------------------------------------
# E. 入口告知
# ----------------------------------------------------------------------
def run_entry_e():
    print('\n== E 三维建局入口告知 ==')
    gui = new_gui()

    # 1) 谜题菜单三维子菜单行 → 点击直达帮助三维页（真实事件路径）
    row = [p for p in gui.puzzle_sub_presets['cubic']
           if len(p) == 2 and p[1] == '__opshelp__']
    check(bool(row), '三维子菜单含「查看操作」行', row)
    gui.show_puzzle_menu = True
    gui.puzzle_sub_open = 'cubic'
    gui.puzzle_sub_hovered = -1
    gui.draw_menu_bar()
    gui.draw_puzzle_menu()
    idx = next(i for i, p in enumerate(gui.puzzle_sub_presets['cubic'])
               if len(p) == 2 and p[1] == '__opshelp__')
    click(gui, gui.puzzle_sub_rects[idx].center)
    check(gui.show_help and gui.help_tab == '3d',
          '菜单行点击 → 帮助三维页', (gui.show_help, gui.help_tab))
    gui.show_help = False
    gui.show_puzzle_menu = False
    gui.puzzle_sub_open = ''

    # 2) 自定义框三维态的「查看操作」→ 关本框 + 帮助三维页
    gui.show_custom_dialog = True
    gui.custom_kind = 'cubic'
    gui.custom_fields = {'m': '6', 'n': '6', 'd': '3', 'step': '1'}
    gui.custom_active_field = 'm'
    gui.custom_error = ''
    gui.draw_custom_puzzle_dialog()
    check(gui.custom_opshelp_rect is not None,
          '自定义框三维态画出「查看操作」')
    click(gui, gui.custom_opshelp_rect.center)
    check(not gui.show_custom_dialog and gui.show_help and gui.help_tab == '3d',
          '点击 → 关自定义框、开帮助三维页',
          (gui.show_custom_dialog, gui.show_help, gui.help_tab))
    gui.show_help = False

    # 二维态不画入口
    gui.show_custom_dialog = True
    gui.custom_kind = 'rect'
    gui.custom_fields = {'m': '6', 'n': '6', 'step': '2'}
    gui.draw_custom_puzzle_dialog()
    check(gui.custom_opshelp_rect is None, '自定义框二维态不画入口')


if __name__ == '__main__':
    pygame.init()
    try:
        run_tab_a()
        run_docs_b()
        run_intro_c()
        run_ops_d()
        run_entry_e()
    finally:
        pygame.quit()
    total = PASSED + FAILED
    print(f'\n{PASSED}/{total} passed' + (f', {FAILED} FAILED' if FAILED else ' — ALL PASS'))
    sys.exit(1 if FAILED else 0)
