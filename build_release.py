"""发版打包：把 PyInstaller 的 onedir 产物压成一个可直接分发的 zip。

背景（2026-10-06）：
- 打包模式已改成 **onedir**，产物是 dist/GatenneaSlider/ 这个文件夹（约 81MB /
  160 个文件）。直接分发文件夹不方便，压成 zip 后约 31MB。
- 分发走 GitHub Release。为了让网站的下载按钮**永远指向最新版**，附件文件名
  必须每个版本都一致（固定叫 GatenneaSlider-Windows.zip，不带版本号），
  下载链接用 .../releases/latest/download/<附件名> 这个永久重定向地址。
- zip **不能**放进网站仓库：每发一版 git 历史就永久涨 31MB。放 Release。

用法：
    D:/python/python.exe build_release.py
    D:/python/python.exe build_release.py --version v1.0.0

产出（都在 dist/ 下）：
    GatenneaSlider-Windows.zip          ← 上传到 Release 的那个文件
    GatenneaSlider-Windows.zip.sha256   ← 填进 Release 说明，给用户校验
    version.json                        ← 自动更新器要读的清单（现在先存着）
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT, 'dist', 'GatenneaSlider')
OUT_DIR = os.path.join(ROOT, 'dist')
ZIP_NAME = 'GatenneaSlider-Windows.zip'

REPO = 'Gatennea/GatenneaSlider'
# 附件名必须与这里一致 —— 改了就等于换了个下载链接，网站和自动更新器都会失效
ASSET_NAME = ZIP_NAME
LATEST_URL = f'https://github.com/{REPO}/releases/latest/download/{ASSET_NAME}'

# 运行时才会生成的目录，打包时排除：
#   config/ 本机调试跑出来的窗口位置、快捷键、历史记录（会把你的窗口坐标带给用户）
#   macro/  用户自己的宏存档目录（空目录，程序启动会自己建）
EXCLUDE_DIRS = {'config', 'macro'}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def guess_version():
    """没给 --version 时，用 git 最近的 tag；都没有就给个占位。"""
    try:
        out = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'],
                             cwd=ROOT, capture_output=True, text=True)
        tag = out.stdout.strip()
        if tag:
            return tag
    except Exception:
        pass
    return 'v0.0.0'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', default=None, help='版本号，如 v1.0.0')
    args = ap.parse_args()

    if not os.path.isdir(SRC_DIR):
        print(f'[ERROR] 找不到 {SRC_DIR}')
        print('        先跑 build_exe.bat 生成 onedir 产物，再执行本脚本。')
        return 1

    version = args.version or guess_version()
    zip_path = os.path.join(OUT_DIR, ZIP_NAME)

    n_files = 0
    t0 = time.time()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(SRC_DIR):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                arc = os.path.relpath(full, os.path.dirname(SRC_DIR))
                z.write(full, arc.replace('\\', '/'))
                n_files += 1
    dt = time.time() - t0

    size = os.path.getsize(zip_path)
    digest = sha256_of(zip_path)

    with open(zip_path + '.sha256', 'w', encoding='utf-8') as f:
        f.write(f'{digest}  {ZIP_NAME}\n')

    manifest = {
        'version': version,
        'asset': ASSET_NAME,
        'url': LATEST_URL,
        'sha256': digest,
        'size': size,
        'notes': '把本文件随 Release 一起发布；自动更新器读的就是它。',
    }
    with open(os.path.join(OUT_DIR, 'version.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    mb = size / 1048576
    print()
    print('=' * 60)
    print(f' 版本      {version}')
    print(f' 文件      {zip_path}')
    print(f' 大小      {mb:.1f} MB  （{n_files} 个文件，压缩耗时 {dt:.0f}s）')
    print(f' SHA256    {digest}')
    print('=' * 60)
    print(' 接下来（GitHub 网页操作）:')
    print(f'   1. {REPO} → Releases → Draft a new release')
    print(f'   2. tag 填 {version}，标题随意，说明里贴上面那行 SHA256')
    print(f'   3. 上传 dist/{ZIP_NAME}')
    print('       ⚠ 附件名必须一字不差，改名会让下载链接失效')
    print('   4. Publish')
    print()
    print(' 网站下载按钮（永久指向最新版，以后不用改）:')
    print(f'   {LATEST_URL}')
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
