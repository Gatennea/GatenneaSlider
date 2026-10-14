# -*- coding: utf-8 -*-
"""pytest 适配层：让 pytest 收集本仓库的脚本型回归测试，存量测试零改动。

背景——仓库现存测试都是「自包含脚本」形态：模块级直接执行、check()
收集失败、sys.exit(1)。pytest 默认只收集 ``test_*.py`` / ``*_test.py``
且要求 ``test_`` 函数，两者都不匹配 ``_test_*.py``；而且 import 一个
脚本型模块就等于把它跑一遍（还会撞上 sys.exit）。

做法——``pytest_collect_file`` 钩子 + ast 静态判别：
  · 模块级有 ``def test_*``      → 返回 None，走 pytest 原生收集
    （test/test/ 下 4 个求解器测试即此形态）；
  · 没有（纯脚本）               → 收成一个 ScriptTestItem：子进程跑脚本，
    退出码 0 = PASS，非 0 = FAIL，stdout 全文附进报告。
    ``_test_*.py`` 全部 80+ 个存量测试由此接入，一行不用改。

新测试可以直接写 pytest 原生风格（def test_xxx + assert），与脚本型
共存；也可以继续写脚本型（如 _test_basic_ops.py），都会被收集。

运行：
    pytest test/                      # 全量
    pytest test/ -k basic             # 按名字筛
    pytest test/ -x                   # 失败即停
    pytest test/ -n auto              # 并行（需 pytest-xdist）

环境约定：
  · 子进程解释器由 ``GATENNEA_PY`` 指定（游戏测试要 pygame-ce，本机
    在 ``D:/python/python.exe``；CI 上设成 ``python``）。
  · 子进程 cwd = 仓库根（兼容 sys.path.insert(0,'.') 与 abspath 两种写法）。
  · 环境敏感脚本（要真实显示器/打包产物/特定机器路径）进 _SKIP，
    收集即跳过，不在 CI 误红。
"""

import ast
import os
import subprocess
import sys

import pytest

# 仓库根 = test/ 的上一级。pytest 进程（收集方）从一开始就要认得出顶层包
# （solver/gui/GUI）：test/test/ 下的 pytest 原生文件 import 链依赖它，
# 且不受这些文件自身 __file__ 算法的影响。conftest 是收集前第一个加载的
# 模块，放这里最稳。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 跑子进程用的解释器：默认本机 pygame-ce 所在；CI 用 GATENNEA_PY=python 覆盖
PYTHON = os.environ.get('GATENNEA_PY', 'D:/python/python.exe')

# 单个脚本的墙上时钟上限（秒）：求解器全图测试最慢约百秒级，留足余量；
# 超时按失败处理并保留已捕获的输出——CI 上挂死比失败更难诊断。
SCRIPT_TIMEOUT = 600

# 环境敏感、不参与自动回归的脚本（收集即 skip）。
#   _test_full          sys.path 硬编码项目旧家 'e:/program_project/py/貓九的滑塊遊戲'
#                       ——该目录在本机真实存在，import 到的是**旧版代码**，
#                       本机「假绿」、CI 上必红；其覆盖（TextInput 组件）
#                       与 _test_quick.py 重叠，不修不删，就此搁置。
#   _smoke_exe          要打包产物 dist/GatenneaSlider/，只在发版前手动跑。
_SKIP = {
    '_test_full.py',
    '_smoke_exe.py',
}


def _has_native_tests(path):
    """ast 判别：模块级是否有 def test_* （不 import，零副作用）。"""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), str(path))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith('test'):
            return True
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name.startswith('test'):
                    return True
    return False


def pytest_collect_file(file_path, parent):
    """test/ 直属的 _test_*.py：有原生 test_ 函数走默认，否则按脚本收集。

    只接管 ``_test_`` 前缀（仓库约定 = 回归测试）。其余前缀不碰：
      _check_/_mi_/_dbg_/_draw_  一次性核查 / 调试
      _gen_                      资源生成（跑了会写文件，绝不进 CI）
      _shot_                     截图工具（产出图片，非断言）
      _smoke_exe                 打包产物冒烟（进 _SKIP，手动跑）
    test/test/ 子目录由 pytest 默认机制管（那 4 个是 pytest 原生）。
    """
    if file_path.suffix != '.py':
        return None
    if file_path.parent != parent.path:
        return None
    if not file_path.name.startswith('_test_'):
        return None
    if _has_native_tests(file_path):
        return None
    return ScriptTestFile.from_parent(parent, path=file_path)


class ScriptTestFile(pytest.File):
    """一个脚本型测试文件 = 一个用例（脚本内部多断言，颗粒度是文件级）。"""

    def collect(self):
        yield ScriptTestItem.from_parent(self, name=self.path.stem)


class ScriptTestItem(pytest.Item):
    def runtest(self):
        if self.path.name in _SKIP:
            pytest.skip(f'环境敏感脚本（{self.path.name}），手动运行')
        env = dict(os.environ)
        env.setdefault('SDL_VIDEODRIVER', 'dummy')
        env.setdefault('SDL_AUDIODRIVER', 'dummy')
        try:
            proc = subprocess.run(
                [PYTHON, '-u', str(self.path)],
                cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=SCRIPT_TIMEOUT,
                errors='replace')
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or '')
            if isinstance(out, bytes):
                out = out.decode('utf-8', 'replace')
            raise AssertionError(
                f'脚本超过 {SCRIPT_TIMEOUT}s 未退出（疑似卡死）\n{out}') from None
        if proc.returncode != 0:
            raise AssertionError(
                f'退出码 {proc.returncode}\n'
                f'----- stdout -----\n{proc.stdout}\n'
                f'----- stderr -----\n{proc.stderr}')

    def repr_failure(self, excinfo, style=None):
        return str(excinfo.value)

    def reportinfo(self):
        return self.path, 0, f'script: {self.path.name}'
