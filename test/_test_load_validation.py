# -*- coding: utf-8 -*-
"""载入存档校验（方向①状态栏提示 + 方向③矩阵校验）回归与反例测试。

覆盖：
  - 合法方形/编号存档仍可正常载入（不误伤）
  - matrix 存成字符串 / 标量 / 行宽不齐 / 与 bounds 尺寸不符 / 单元非整数
    → 抛 ValueError，且当前局面不变、状态栏给出「打开失败」提示
"""
import os
import sys
import json
import tempfile

os.environ['SDL_VIDEODRIVER'] = 'dummy'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame
pygame.init()

from history import validate_snapshot
from GUI import SliderGUI


def _make_valid_numbered():
    """生成一个真实编号存档 dict（含多快照）。"""
    gui = SliderGUI(6, 6, 2, 4)
    gui.new_puzzle(4, 4, 1, numbered=True)
    gui.animation_enabled = False
    gui.save_readonly_flag = False
    gui._bump_move_session()
    gui.selected_gap = ('h', 1)
    blk = next(b for b in gui.game.blocks if b.location == [0, 0])
    gui.game.opt('h', 1, blk)
    gui.selected_block = blk
    gui.move_selected_blocks('a')
    p = os.path.join(tempfile.gettempdir(), '_tv_valid.json')
    gui._save_to_path(p)
    data = json.load(open(p, encoding='utf-8'))
    os.remove(p)
    return data


FAIL_CASES = {
    'matrix 是字符串': {
        'version': 1, 'puzzle': {'m': 4, 'n': 4, 'step': 2}, 'step_count': 0,
        'history': {'history_index': 0, 'snapshots': [
            {'matrix': 'not-a-matrix',
             'bounds': {'min_row': 0, 'max_row': 3, 'min_col': 0, 'max_col': 3},
             'move_info': None}]}},
    'matrix 是标量': {
        'version': 1, 'puzzle': {'m': 4, 'n': 4, 'step': 2}, 'step_count': 0,
        'history': {'history_index': 0, 'snapshots': [
            {'matrix': 42,
             'bounds': {'min_row': 0, 'max_row': 3, 'min_col': 0, 'max_col': 3},
             'move_info': None}]}},
    'matrix 行宽不齐': {
        'version': 1, 'puzzle': {'m': 4, 'n': 4, 'step': 2}, 'step_count': 0,
        'history': {'history_index': 0, 'snapshots': [
            {'matrix': [[1, 1], [1, 1, 1], [1, 1], [1, 1]],
             'bounds': {'min_row': 0, 'max_row': 3, 'min_col': 0, 'max_col': 3},
             'move_info': None}]}},
    'matrix 尺寸与 bounds 不符': {
        'version': 1, 'puzzle': {'m': 4, 'n': 4, 'step': 2}, 'step_count': 0,
        'history': {'history_index': 0, 'snapshots': [
            {'matrix': [[1] * 4 for _ in range(4)],
             'bounds': {'min_row': 0, 'max_row': 99, 'min_col': 0, 'max_col': 99},
             'move_info': None}]}},
    'matrix 单元非整数': {
        'version': 1, 'puzzle': {'m': 4, 'n': 4, 'step': 2}, 'step_count': 0,
        'history': {'history_index': 0, 'snapshots': [
            {'matrix': [['x'] * 4 for _ in range(4)],
             'bounds': {'min_row': 0, 'max_row': 3, 'min_col': 0, 'max_col': 3},
             'move_info': None}]}},
    'bounds 缺失键': {
        'version': 1, 'puzzle': {'m': 4, 'n': 4, 'step': 2}, 'step_count': 0,
        'history': {'history_index': 0, 'snapshots': [
            {'matrix': [[1] * 4 for _ in range(4)],
             'bounds': {'min_row': 0, 'max_row': 3, 'min_col': 0},  # 缺 max_col
             'move_info': None}]}},
}


def test_unit_validation():
    # 合法方形
    ok = {'matrix': [[1, 0], [0, 1]],
          'bounds': {'min_row': 0, 'max_row': 1, 'min_col': 0, 'max_col': 1}}
    validate_snapshot(ok, 'square')
    # 合法编号（含编号值）
    num = {'matrix': [[1, 2], [3, 0]],
           'bounds': {'min_row': 0, 'max_row': 1, 'min_col': 0, 'max_col': 1}}
    validate_snapshot(num, 'numbered')
    print('单元测试：合法 snapshot 校验通过')
    for name, bad in FAIL_CASES.items():
        snap = bad['history']['snapshots'][0]
        try:
            validate_snapshot(snap, 'square')
            raise AssertionError(f'[{name}] 未抛异常（应为非法）')
        except ValueError as e:
            print(f'单元测试：[{name}] 正确拒绝 -> {e}')
    # 三角形值域
    try:
        validate_snapshot({'matrix': [[4]],
                           'bounds': {'min_row': 0, 'max_row': 0, 'min_col': 0, 'max_col': 0}},
                          'triangle')
        raise AssertionError('三角形超值域未拒绝')
    except ValueError:
        print('单元测试：三角形 matrix>3 正确拒绝')


def test_integration_not_polluted():
    gui = SliderGUI(6, 6, 2, 4)
    gui.new_puzzle(4, 4, 2, numbered=True)
    gui.animation_enabled = False
    gui.save_readonly_flag = False
    # 制造一个已知状态：16 块、编号 1..16、是当前文件路径
    before_blocks = len(gui.game.blocks)
    before_numbered = gui.numbered
    before_path = gui.current_file_path

    for name, data in FAIL_CASES.items():
        p = os.path.join(tempfile.gettempdir(), f'_tv_{name}.json')
        json.dump(data, open(p, 'w', encoding='utf-8'))
        gui._do_load_from_path(p)
        os.remove(p)
        # 状态栏应有失败提示
        assert gui.macro_notify_msg.startswith('打开失败'), \
            f'[{name}] 无失败提示: {gui.macro_notify_msg!r}'
        # 当前局面不应被污染
        assert len(gui.game.blocks) == before_blocks, \
            f'[{name}] 块数被改: {len(gui.game.blocks)} != {before_blocks}'
        assert gui.numbered == before_numbered, \
            f'[{name}] numbered 被改: {gui.numbered}'
        assert gui.current_file_path == before_path, \
            f'[{name}] 当前文件路径被改: {gui.current_file_path!r}'
        print(f'集成测试：[{name}] 被拒 + 提示 + 局面未污染 OK')
    pygame.quit()


def test_integration_valid_loads():
    gui = SliderGUI(6, 6, 2, 4)
    gui.animation_enabled = False
    gui.save_readonly_flag = False
    data = _make_valid_numbered()
    p = os.path.join(tempfile.gettempdir(), '_tv_run.json')
    json.dump(data, open(p, 'w', encoding='utf-8'))
    gui._do_load_from_path(p)
    os.remove(p)
    assert gui.numbered is True, '编号存档未正确识别'
    nums = sorted(b.number for b in gui.game.blocks if getattr(b, 'number', None))
    assert nums == list(range(1, 17)), f'编号未还原: {nums}'
    assert gui.macro_notify_msg.startswith('已打开'), \
        f'成功载入却无已打开提示: {gui.macro_notify_msg!r}'
    print('集成测试：合法编号存档成功载入 + 编号 1..16 还原 + 已打开提示 OK')
    pygame.quit()


if __name__ == '__main__':
    test_unit_validation()
    test_integration_not_polluted()
    test_integration_valid_loads()
    print('\n_test_load_validation PASS')
