# -*- coding: utf-8 -*-
"""把 _test_model_modes.py 的 I-2 段改成 route A 后的新口径。

原断言写的是「碎三角导不进编辑器是**预期**的」，route A 搬到「改当前盘面」
后这条不成立，留着会误导后来人（看着像已知限制，实则是已修好的缺口）。
按行号替换（中文全角冒号会让 Edit 工具匹配失败，故走脚本）。
"""
import io
import os

_PROJ = os.path.dirname(os.path.abspath(__file__))
_P = os.path.join(_PROJ, 'test', '_test_model_modes.py')

NEW = '''    # ---- I-2. 碎三角（自定义 basis + pos_scale=3）--------------------
    # shatter 的 basis 是 (0.866,0)/(0,0.5)（正三角格的矩形坐标表示），
    # 朝向标签还是裸号（'6'/'12'）。route A（2026-10-28）把「任意 basis +
    # pos_scale」的能力搬到这条路径之后，碎三角**可以**导入续编：族按朝向
    # 集闭合性判 tri（而不是按 basis 夹角误判 square）、沿用盘面自己的
    # basis、pos_scale=3 写进会话。早年这里断言「导不进是预期的」，现改为
    # 钉住「导入且保真」——退化回空盘会红。
    if gui.new_model_puzzle('shatter', 1):
        gui.set_game_mode('create')
        gui._ann_home_sub = 'restore'
        n_sh = len(gui.game.blocks)
        gui._ann_btn_blocks_current()
        if gui._med_active:
            n_imp = len(gui._med['placed'])
            check(n_imp == n_sh, 'I8 碎三角导入块数应与原局一致',
                  f'{n_sh}->{n_imp}')
            check(gui._med['pos_scale'] == 3,
                  'I8a 碎三角 pos_scale 应为 3（旧代码漏写、恒为 1）',
                  f'实得 {gui._med["pos_scale"]}')
            check(gui._med['lattice'] == 'tri',
                  'I8b 族应按朝向集闭合性判 tri（不是按 basis 夹角误判 square）',
                  f'实得 {gui._med["lattice"]}')
            if n_imp == n_sh:
                gate_ok, why = gui._med_gate()
                check(gate_ok, 'I8c 碎三角导入盘面通过保存门', f'why={why!r}')
            gui._med_close()
        else:
            check(False, 'I8 跳过（碎三角编辑器没打开）')
    else:
        check(False, 'I8 跳过（碎三角建局失败）')
'''.splitlines(keepends=True)

with io.open(_P, encoding='utf-8') as f:
    lines = f.readlines()

# 定位：从含 'I-2. 碎三角' 的注释行起，到含 "I8 跳过（碎三角编辑器没打开）" 止
start = next(i for i, l in enumerate(lines) if 'I-2. 碎三角' in l)
end = next(i for i, l in enumerate(lines)
           if i > start and 'I8 跳过（碎三角编辑器没打开）' in l)
lines[start:end + 1] = [l if l.endswith('\n') else l + '\n' for l in NEW]

with io.open(_P, 'w', encoding='utf-8', newline='') as f:
    f.writelines(lines)

with io.open(os.path.join(_PROJ, 'archive', '_splice_modes.txt'), 'w',
             encoding='utf-8') as f:
    f.write('replaced lines %d..%d (1-based %d..%d)\n'
            % (start, end, start + 1, end + 1))
