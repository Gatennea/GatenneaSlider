# -*- coding: utf-8 -*-
"""用游戏自身的 _load_save_data 原代码试载反例存档，定位「打不开」的原因。

不启 GUI：构造一个只实现 _load_save_data 所需属性的最小宿主，
对 save/反例存档/ 下每个 JSON 走一遍与「文件-打开」完全相同的代码路径
（_do_load_from_path 去掉文件对话框部分：json.load → _load_save_data），
捕获并报告第一步抛出的异常——与游戏控制台打印的
「文件格式错误: ...」等价。

用法：
  D:\\python\\python.exe test\\test_open_saves.py
"""

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gui.file_ops import FileOpsMixin  # noqa: E402
from history import GameHistory  # noqa: E402

SAVE_DIR = ROOT / 'save' / '反例存档'


class _LoadStub(FileOpsMixin):
    """只承载 _load_save_data 所需的最小状态（镜像 GUI 载入时的字段）。"""

    def __init__(self):
        self.game_history = GameHistory()
        self._ann_cancel_session = lambda *a, **k: None  # 标注会话：仿真无操作

    # _load_save_data 内部会赋值的字段，预先给默认值
    _readonly = False
    numbered = False
    triangle_mode = False
    mi_mode = False
    zoom = 1.0
    selected_gap = None
    selected_block = None
    animating = False
    anim_blocks = []
    _ann_style_goal = None

    def _ann_apply_saved_style_goal(self, name=None):
        """镜像 GUI 的样式目标恢复（本 stub 不涉标注混入，只清标记）。"""
        self._ann_style_goal = None
        return False


def main():
    files = sorted(SAVE_DIR.glob('反例-*.json'))
    if not files:
        print(f'未找到存档：{SAVE_DIR}')
        return 1
    ok = 0
    for path in files:
        stub = _LoadStub()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)          # 同 _do_load_from_path
            stub._load_save_data(data)       # 游戏原代码
            snap = data['history']['snapshots'][0]
            ones = sum(sum(r) for r in snap['matrix'])
            n_blocks = len(stub.game.blocks)
            print(f'✓ {path.name}  载入成功  blocks={n_blocks} (矩阵1数={ones})')
            ok += 1
        except Exception as e:
            print(f'✗ {path.name}  {type(e).__name__}: {e}')
            traceback.print_exc(limit=6)
    print(f'\n{ok}/{len(files)} 个载入成功')
    return 0 if ok == len(files) else 1


if __name__ == '__main__':
    sys.exit(main())
