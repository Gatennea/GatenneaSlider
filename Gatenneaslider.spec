# -*- mode: python ; coding: utf-8 -*-

# 优化后的 PyInstaller 配置（体积 ~24MB，原始 ~70MB）

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_dynamic_libs
import os

# 只包含实际使用的 pygame 子模块（及其内部依赖）
hiddenimports = [
    'pygame',
    'pygame.font',
    'pygame.display',
    'pygame.event',
    'pygame.time',
    'pygame.mouse',
    'pygame.key',
    'pygame.draw',
    'pygame.surface',
    'pygame.rect',
    'pygame.color',
    'pygame.locals',
    'pygame.scrap',
    'pygame.version',        # pygame 内部必需
    'pygame.compat',         # pygame 内部必需
    'pygame.sysfont',        # pygame.font 依赖
    'pygame.bufferproxy',    # pygame surface 内部依赖
    'pygame.joystick',       # pygame.time 内部依赖
    # numpy.random 运行时依赖的标准库模块（PyInstaller 可能漏检）
    'secrets',
    'hmac',
    'hashlib',
]

# 排除不需要的模块
excludes = [
    # pygame 扩展（不需要的）
    'pygame.mixer',
    'pygame.mixer_music',
    'pygame.movie',
    'pygame.cdrom',
    'pygame.overlay',
    'pygame.sndarray',
    'pygame.surfarray',
    'pygame.fastevent',
    'pygame._camera',
    'pygame._sdl2',
    'pygame.examples',
    'pygame.tests',
    'pygame.typing',
    'pygame.pixelarray',
    # ⚠️ pygame.sprite / pygame.cursors **不能排除**（2026-10-06 打包白屏事故）：
    # pygame.mouse.set_cursor 依赖 cursors，排掉后打包版里根本没有这个属性，
    # 而 _update_cursor 每帧调用它 —— 异常在每帧 try 块开头抛出，把整帧绘制
    # 连同 display.flip() 一起跳过，窗口永远空白且 windowed 模式下看不到报错。
    # 'pygame.sprite',
    # 'pygame.cursors',
    # 'pygame.mask',      # sprite 的依赖；一并带上，消除 import sprite 的 RuntimeWarning
    'pygame.freetype',
    'pygame.controller',

    # Python 标准库（确认不需要的才能排除）
    # 注意：email/html 是 http.server 依赖，不能排除
    'tkinter',
    'unittest',
    'pydoc',
    'doctest',
    'test',
    'tests',
    'xmlrpc',
    'multiprocessing',
    'concurrent',
    'curses',
    'pdb',
    'profile',
    'pstats',
    'optparse',
    'getpass',
    'imaplib',
    'nntplib',
    'poplib',
    'smtplib',
    'telnetlib',
    'ftplib',
    # 注意：webbrowser 不可排除 —— gui/events.py 的「官网」菜单用它开启浏览器
    'wsgiref',
    'cgi',
    'turtledemo',
    'turtle',
    'formatter',
    'macpath',
    'uu',
    'pty',
    'tty',

    # 机器学习训练依赖（仅 train_*.py 训练脚本使用，运行时不需要）
    'sklearn',
    'scipy',
    'joblib',
    'threadpoolctl',
    'matplotlib',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('picture/cover.png', 'picture'),
           ('docs/player/操作说明.md', 'docs/player'),
           # 新手教程资源：文案 JSON + 关卡存档（新增关卡只加 json，无需改 spec）
           ('gui/tutorial_texts.json', 'gui'),
           ('beginner_archive', 'beginner_archive'),
           # S1-4 箭头按键贴图（renderer._arrow_asset_path 按「仓库根/assets/...」
           # 找，打包后根 = _MEIPASS，故整目录带过去；缺了箭头不显示）
           ('assets', 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

# 排除 ucrtbase.dll：PyInstaller 會從開發環境（Anaconda/MinGW）誤打包此系統 DLL，
# 導致目標機器載入時觸發 STATUS_INVALID_IMAGE_HASH (0xc0000020)。
# 直接依賴 Windows System32 提供的版本即可。
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).lower() == 'ucrtbase.dll']

pyz = PYZ(a.pure)

# onedir（一文件夹模式）：exe 里只装引导器 + pyz，真正的依赖由下面的 COLLECT
# 摊到 exe 旁边的目录里。好处是**每次运行不再把 31MB 解压到 %TEMP%** —— 实测
# onefile 解压耗时 2.1s、到窗口出现 3.8s；onedir 没有这一步。
# 代价：分发的是文件夹不是一个 exe（以后想做安装包就交给 Inno Setup）。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Gatenneaslider',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='picture/cover.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    # strip 关掉：onedir 下依赖文件摊在目录里，strip 省的那点体积远不如
    # 「别在打包环节引入新的不确定性」重要（上次白屏就是打包侧引入的）。
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Gatenneaslider',
)
