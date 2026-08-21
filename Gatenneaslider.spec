# -*- mode: python ; coding: utf-8 -*-

# 优化后的 PyInstaller 配置（体积 ~24MB，原始 ~70MB）

from PyInstaller.utils.hooks import collect_submodules

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
    'pygame.sprite',
    'pygame.freetype',
    'pygame.cursors',
    'pygame.mask',
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
    'webbrowser',
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
    datas=[('picture/cover.png', 'picture'), ('gui/操作说明.md', 'gui')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
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
