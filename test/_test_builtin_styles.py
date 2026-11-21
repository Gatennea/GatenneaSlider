# -*- coding: utf-8 -*-
r"""§68 A 组护栏：入库示范样式（2026-11-21）。

判据走真实数据层 + GUI 入口：干净 config 下列出/开局、两类分流、只读隔离、
同名共存、另存为自建。不查「源码里有没有 buildin 目录」。

运行：D:\python\python.exe test\_test_builtin_styles.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def t1_clean_env_list_and_open():
    print('== 1. 干净环境（无 config）列出并开局 ==')
    config = tempfile.mkdtemp(prefix='builtin_clean_')   # 空 config 目录
    styles = ds.list_styles(config)
    check('示范-双连带' in styles and '示范-缺角方' in styles,
          '无 config 自建样式仍能列出两个示范', styles)
    check(all(ds.style_source(config, n) == 'builtin' for n in styles),
          '来源都识别为入库示范')
    g = SliderGUI()
    g.config_dir = config
    g._ann_design_start_style('示范-缺角方')
    check(g.game is not None and getattr(g.game, 'goal_pattern', None),
          '示范样式能真实开局并设还原目标')
    check(g._ann_style_goal == '示范-缺角方', 'HUD 显示示范样式名')


def t2_two_submenus():
    print('== 2. 两类示范各有条目（捆绑谜题 / 自定义还原态）==')
    config = tempfile.mkdtemp(prefix='builtin_submenu_')
    g = SliderGUI()
    g.config_dir = config
    g._refresh_puzzle_presets()
    bundled = g.puzzle_sub_presets.get('bundled', [])
    custom = g.puzzle_sub_presets.get('custom', [])
    b_names = [it[2] for it in bundled]
    c_names = [it[2] for it in custom]
    check('示范-双连带' in b_names, '捆绑谜题子菜单有示范项', b_names)
    check('示范-缺角方' in c_names, '自定义还原态子菜单有示范项', c_names)
    b_labels = [it[0] for it in bundled]
    check(any(lbl.endswith('·示范') for lbl in b_labels),
          '菜单显示名带「示范」角标', b_labels)


def t3_readonly():
    print('== 3. 写权隔离：示范不可就地改名/删除 ==')
    config = tempfile.mkdtemp(prefix='builtin_ro_')
    # 改名：对 builtin 直接拒（missing_old，因为 config 里没这个文件）
    ok, why = ds.rename_style(config, '示范-双连带', '乱改的名字')
    check(not ok and why == 'missing_old', '示范名改名被拒（不碰入库文件）', why)
    check('示范-双连带' in ds.list_styles(config), '改名失败后示范仍在')
    # 删除：菜单删除判据对示范返回 None（不画✕、点了也不删）
    g = SliderGUI()
    g.config_dir = config
    item = ('示范-双连带·示范', '__custom__', '示范-双连带')
    check(g._menu_item_deletable(item) is None,
          '示范项不可删（删除判据返回 None）')
    check(ds.load_style(config, '示范-双连带') is not None,
          '示范文件未被删除')


def t4_copy_then_rename():
    print('== 4. 另存为自建后可改名，且与示范共存不串 ==')
    config = tempfile.mkdtemp(prefix='builtin_copy_')
    ok, res = ds.copy_builtin_to_user(config, '示范-双连带')
    check(ok, '示范另存为自建成功', res)
    check(ds.style_source(config, '示范-双连带') == 'user',
          '同名时自建盖过示范（读取优先自建）')
    ok, why = ds.copy_builtin_to_user(config, '示范-双连带')
    check(not ok and why == 'exists', '重复另存被拒（不覆盖已有自建）', why)
    # 自建副本能改自己的名，不动入库
    ok, res = ds.rename_style(config, '示范-双连带', '我的副本')
    check(ok, '自建副本可改名', res)
    check(ds.style_source(config, '示范-双连带') == 'builtin',
          '改名后原名回落到入库示范（自建那份已改名）')
    check(ds.load_style(config, '我的副本') is not None,
          '新名的自建副本可读')


def t5_same_name_coexist():
    print('== 5. 同名共存：config 私有与示范同名，两侧都在、内容不串 ==')
    config = tempfile.mkdtemp(prefix='builtin_same_')
    # 玩家自建一个和示范同名的样式，内容不同
    ds.save_style(config, '示范-双连带', {
        'version': 2, 'name': '示范-双连带',
        'cells': [[0, 0], [1, 1]], 'm': 2, 'n': 2, 'step': 1,
    })
    data = ds.load_style(config, '示范-双连带')
    check(len(data['cells']) == 2, '同名时读到的是玩家自建（2 块）',
          len(data['cells']))
    check(ds.style_source(config, '示范-双连带') == 'user',
          '同名来源标记为自建')
    check(len(ds.list_styles(config)) == len(set(ds.list_styles(config))),
          '列表不重复列同名项')


def main():
    t1_clean_env_list_and_open()
    t2_two_submenus()
    t3_readonly()
    t4_copy_then_rename()
    t5_same_name_coexist()
    print(f'\n{PASSED[0]} passed, {len(FAILED)} failed')
    if FAILED:
        print('FAILED: ' + '; '.join(FAILED))
        sys.exit(1)
    print('ALL PASS')


if __name__ == '__main__':
    main()
