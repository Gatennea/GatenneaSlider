# -*- coding: utf-8 -*-
r"""§64 A 组护栏：游戏内样式改名（2026-11-21）。

判据走真实入口：design_styles.rename_style + GUI 改名态事件链 +
load_style 旧名兜底。不查「源码里有没有 rename 函数」。

运行：D:\python\python.exe test\_test_style_rename.py
"""
import json
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from GUI import SliderGUI  # noqa: E402
from gui import design_styles as ds  # noqa: E402

FAILED = []
PASSED = [0]


def check(ok, label, extra=None):
    if ok:
        PASSED[0] += 1
        print(f'  ok: {label}')
    else:
        FAILED.append(label)
        print(f'  FAIL: {label}' + (f'  <- {extra}' if extra is not None else ''))


def _kd(key):
    return pygame.event.Event(pygame.KEYDOWN,
                              {'key': key, 'unicode': '', 'mod': 0,
                               'scancode': 0})


def _ti(text):
    return pygame.event.Event(pygame.TEXTINPUT, {'text': text})


def _seed_style(config, name, *, groups=None, kind=None):
    data = {'version': 2, 'name': name,
            'cells': [[0, 0], [0, 1], [1, 0], [1, 1]],
            'm': 2, 'n': 2, 'step': 1}
    if groups is not None:
        data['groups'] = groups
    if kind:
        data['kind'] = kind
    assert ds.save_style(config, name, data)
    return data


def t1_rename_atomic():
    print('== 1. 真实改名：文件名 + 档内 name + 列表 ==')
    config = tempfile.mkdtemp(prefix='rename_atomic_')
    _seed_style(config, '捆绑甲',
                groups=[[0, 0, 1], [0, 1, 1], [1, 0, 1], [1, 1, 1]])
    _seed_style(config, '还原乙')            # 不带 groups
    _seed_style(config, '三维丙', kind='cubic')
    check({'捆绑甲', '还原乙', '三维丙'} <= set(ds.list_styles(config)),
          '改名前三类样式都在（入库示范也列出，用子集断言）',
          ds.list_styles(config))

    for old, new in [('捆绑甲', '新捆绑'), ('还原乙', '新还原'),
                     ('三维丙', '新三维')]:
        ok, res = ds.rename_style(config, old, new)
        check(ok, f'{old} → {new} 改名成功', res)
        check(new in ds.list_styles(config) and old not in ds.list_styles(config),
              f'{old} 旧名消失、新名入列', ds.list_styles(config))
        data = ds.load_style(config, new)
        check(data is not None and data.get('name') == new,
              f'{new} 档内 name 字段已同步', data and data.get('name'))

    # 两类内容没丢：捆绑还带 groups，还原不带，三维 kind 保留
    check(bool(ds.groups_from_data(ds.load_style(config, '新捆绑'))),
          '捆绑样式改后 groups 仍在')
    check(not ds.groups_from_data(ds.load_style(config, '新还原')),
          '还原样式改后仍无 groups')
    check(str(ds.load_style(config, '新三维').get('kind')) == 'cubic',
          '三维样式改后 kind=cubic 保留')


def t2_old_preset_fallback():
    print('== 2. 旧档兼容：旧 preset 载入还原目标 + HUD 显示新名 ==')
    config = tempfile.mkdtemp(prefix='rename_preset_')
    _seed_style(config, '老目标', groups=[[0, 0, 1], [0, 1, 1]])
    ok, _ = ds.rename_style(config, '老目标', '新目标')
    check(ok, '改名完成')

    # load_style 用旧名仍能读到（映射兜底）
    data = ds.load_style(config, '老目标')
    check(data is not None and data.get('name') == '新目标',
          '旧名 load_style 兜底读到新档', data and data.get('name'))
    check(ds.resolve_name(config, '老目标') == '新目标',
          'resolve_name 解析旧名')

    # 映射链 A→B→C
    ds.rename_style(config, '新目标', '最终目标')
    check(ds.load_style(config, '老目标').get('name') == '最终目标',
          '两级改名后最初旧名仍能读到')
    check(ds.resolve_name(config, '老目标') == '最终目标',
          'chain 解析到最终名')

    # 真实 GUI：存档 preset=旧名 → _ann_apply_saved_style_goal 恢复并 HUD 新名
    g = SliderGUI()
    g.config_dir = config
    g.new_puzzle(4, 4, 1)
    restored = g._ann_apply_saved_style_goal('老目标')
    check(restored, '旧 preset 通过存档入口恢复成功')
    check(g._ann_style_goal == '最终目标',
          'HUD 还原目标显示当前名（非旧名）', g._ann_style_goal)
    check(g.game.goal_pattern is not None and len(g.game.goal_pattern) == 4,
          'goal_pattern 已按样式恢复', g.game.goal_pattern)


def t3_ui_rename_flow():
    print('== 3. 真实 UI：点✎ → 输入中文 → 回车提交 ==')
    config = tempfile.mkdtemp(prefix='rename_ui_')
    _seed_style(config, '初始名')
    g = SliderGUI()
    g.config_dir = config
    # 进入首页样式库下拉（构造模式还原设计入口）
    g.set_game_mode('create')
    g._ann_view = 'home'
    g._ann_home_sub = 'restore'
    g._ann_btn_style_lib()
    # 构造下拉项与改名按钮矩形（绘制通常每帧做，这里直接喂真实结构）
    g._ann_design_menu_items = [('初始名', pygame.Rect(20, 100, 200, 24))]
    g._ann_style_rename_btns = [('初始名', pygame.Rect(194, 102, 22, 20), 'rename')]
    # 点✎
    consumed = g._ann_style_menu_click(200, 110)
    check(consumed, '改名按钮点击被消费')
    check(g._ann_style_renaming == '初始名', '进入改名态')
    check(g._ann_design_name_active and g._ann_design_style_name == '初始名',
          '名字输入缓冲预填旧名')
    # 全选式改名：退格清空旧名后输中文
    for _ in range(len('初始名')):
        g.handle_annotation_event(_kd(pygame.K_BACKSPACE))
    g.handle_annotation_event(_ti('游戏内改名'))
    check(g._ann_design_style_name == '游戏内改名', 'TEXTINPUT 写入中文新名',
          g._ann_design_style_name)
    g.handle_annotation_event(_kd(pygame.K_RETURN))
    check(g._ann_style_renaming is None, '回车后退出改名态')
    check('游戏内改名' in ds.list_styles(config)
          and '初始名' not in ds.list_styles(config),
          'UI 改名落到列表', ds.list_styles(config))


def t4_guards():
    print('== 4. 护栏：空名 / 重名确认 / 同名 no-op ==')
    config = tempfile.mkdtemp(prefix='rename_guard_')
    _seed_style(config, '甲')
    _seed_style(config, '乙')
    ok, why = ds.rename_style(config, '甲', '   ')
    check(not ok and why == 'empty', '空名被拒', why)
    ok, why = ds.rename_style(config, '甲', '乙')
    check(not ok and why == 'exists', '重名先要确认', why)
    ok, res = ds.rename_style(config, '甲', '乙', overwrite=True)
    check(ok, '确认后覆盖成功', res)
    ok, res = ds.rename_style(config, '乙', '甲')
    check(ok, '基础改名成功供 no-op 测试', res)
    ok, res2 = ds.rename_style(config, '甲', '甲')
    check(ok and res2.endswith('甲.json'), '同名 no-op 返回成功', res2)
    ok, why = ds.rename_style(config, '不存在', '新')
    check(not ok and why == 'missing_old', '旧名不存在被拒', why)


def main():
    t1_rename_atomic()
    t2_old_preset_fallback()
    t3_ui_rename_flow()
    t4_guards()
    print(f'\n{PASSED[0]} passed, {len(FAILED)} failed')
    if FAILED:
        print('FAILED: ' + '; '.join(FAILED))
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
