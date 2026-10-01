# -*- coding: utf-8 -*-
"""存档文件名校验与保存反馈的非 GUI 测试

不启动 pygame 窗口：pygame 用桩模块顶替（file_ops 仅在 save_config 里
用到 pygame.display，本测试不经过它），FileOpsMixin 用最小桩类承接
_save_to_path 依赖的属性，直接调用真实保存逻辑验证：
1. 非法名 "4*4quekou" 被拦截，不写盘，提示含「非法字符」
2. 合法名正常写盘，提示含「已保存」
3. 写盘异常（目标是目录）转成可见的「保存失败」提示
"""
import sys
import os
import types
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pygame 桩：让 gui.file_ops 可导入（真实 pygame 未安装/无需窗口）
fake_pygame = types.ModuleType('pygame')
fake_pygame.display = types.ModuleType('pygame.display')
sys.modules['pygame'] = fake_pygame
sys.modules['pygame.display'] = fake_pygame.display

from gui.file_ops import FileOpsMixin, _find_illegal_filename_chars


class _StubGUI(FileOpsMixin):
    """只提供 _save_to_path 用到的属性/方法的最小桩"""

    def __init__(self):
        self.macro_notify_msg = ''
        self.macro_notify_timer = 0
        self.current_file_path = None
        self._saved_board_version = 0
        self._board_version = 0

    def _build_save_data(self):
        return {'stub': True}

    def _update_window_title(self):
        pass


print('=== 文件名非法字符校验 ===')

# 1. 用户实测的非法名
assert _find_illegal_filename_chars('4*4quekou.json') == ['*']
print('1. "4*4quekou.json" ->', _find_illegal_filename_chars('4*4quekou.json'), '(expected [*])')

# 2. 各非法字符逐个命中
for ch in '<>:"/\\|?*':
    assert _find_illegal_filename_chars(f'a{ch}b.json') == [ch]
print('2. <>:"/\\|?* 逐个命中 OK')

# 3. 合法名（含中文）返回空
assert _find_illegal_filename_chars('4x4quekou.json') == []
assert _find_illegal_filename_chars('缺口拼图-1-4-4.json') == []
print('3. 合法名/中文名返回 [] OK')

print()
print('=== _save_to_path 保存流程 ===')

tmp = tempfile.mkdtemp(prefix='_test_save_')
gui = _StubGUI()

# 4. 非法名保存：被拦截，不写盘，有明确提示
bad_path = os.path.join(tmp, '4*4quekou.json')
gui._save_to_path(bad_path)
assert not os.path.exists(bad_path), '非法名不应写盘'
assert '非法字符' in gui.macro_notify_msg, gui.macro_notify_msg
assert gui.macro_notify_timer > 0
print('4. 非法名拦截 OK：', gui.macro_notify_msg)

# 5. 合法名保存：写盘成功，提示含实际文件名
good_path = os.path.join(tmp, '4x4quekou.json')
gui._save_to_path(good_path)
assert os.path.isfile(good_path), '合法名应写出文件'
assert gui.current_file_path == good_path
assert '已保存' in gui.macro_notify_msg and '4x4quekou.json' in gui.macro_notify_msg, gui.macro_notify_msg
print('5. 合法名保存 OK：', gui.macro_notify_msg)

# 6. 异常兜底：把目录当文件保存 → open 抛 IsADirectoryError，转可见失败提示
dir_path = os.path.join(tmp, 'subdir')
os.makedirs(dir_path, exist_ok=True)
gui._save_to_path(dir_path)
assert '保存失败' in gui.macro_notify_msg, gui.macro_notify_msg
assert gui.current_file_path == good_path  # 失败时不更新 current_file_path
print('6. 异常兜底 OK：', gui.macro_notify_msg)

# 清理临时目录
import shutil
shutil.rmtree(tmp, ignore_errors=True)

print()
print('ALL TESTS PASSED!')
