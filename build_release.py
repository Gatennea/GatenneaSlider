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
    D:/python/python.exe build_release.py --version v20261017

版本号规则（2026-10-17 改）：改为**打包日期**，形如 v20261017，不给版本号时自动取今天。
- 旧规则（2026-10-06）是「Git 提交数 + 日期」，但 squash 合并会让提交数变小、版本号
  倒退，自动更新器会误判「已是最新」。日期天然单调、与 git 历史无关，故改用之。
- 更新器只比版本号 v 后第一个 '-' 前的整数（v20261017 → 20261017），恒大于旧的
  v197 等提交数版本，过渡无碍。
- 同日要发两版：直接取下一天日期，或用 --version v20261017-2（但比较只看前导整数，
  同日真正「更新型号」需用带时分的 vYYYYMMDDHHMM 才能比旧的大）。

产出（都在 dist/ 下）：
    GatenneaSlider-Windows.zip          ← 上传到 Release 的那个文件
    GatenneaSlider-Windows.zip.sha256   ← 填进 Release 说明，给用户校验
    version.json                        ← 自动更新器要读的清单（现在先存着）
"""

import argparse
import hashlib
import json
import os
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
# 自动更新器拉「最新版本清单」用的固定地址（version.json 也作为 Release 附件发布）
MANIFEST_URL = f'https://github.com/{REPO}/releases/latest/download/version.json'

# 运行时才会生成 / 属于玩家数据的目录，打包时排除（更新器只覆盖 zip 内的程序文件，
# 绝不删除这些目录）：
#   config/ 本机调试跑出来的窗口位置、快捷键、历史记录（会把你的窗口坐标带给用户）
#   macro/  用户自己的宏存档目录（首次保存宏时才由 MacroManager.save_macro 创建）
#   save/   玩家的谜题存档 + 录像/记录（绝不进 zip，更新时原样保留）
EXCLUDE_DIRS = {'config', 'macro', 'save'}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def today_version():
    """版本号 = 打包当天日期，形如 v20261017。

    2026-10-17 起不再用 Git 提交数（squash 合并会让提交数变小、版本号倒退，导致
    自动更新器误判「已是最新」）。日期天然单调、与 git 历史无关，更新器只比较 v 后
    第一个 '-' 前的整数（v20261017 → 20261017），恒大于旧的 v197 等提交数版本。
    """
    return f'v{time.strftime("%Y%m%d")}'


def validate_version(vstr):
    """手填版本号校验（--version 覆盖时生效）。
    - 日期制 vYYYYMMDD / vYYYYMMDD-xxx：要求日期不早于今天（防倒退）。
    - 旧制 vN-YYYYMMDD：校验日期部分不晚于过去，放行。
    - 其余数字型版本号：放行（视为显式指定）。
    合法返回 True。"""
    if not vstr or not isinstance(vstr, str):
        return False
    s = vstr[1:] if vstr.startswith('v') else vstr
    head = s.split('-')[0]
    tail = s.split('-')[1] if '-' in s else ''
    today = int(time.strftime('%Y%m%d'))
    if head.isdigit() and len(head) == 8:
        return int(head) >= today            # 日期制：不能发过去的日期
    if head.isdigit() and tail.isdigit() and len(tail) == 8:
        return int(tail) >= today            # 旧制：日期部分不能晚于过去
    return head.isdigit()                    # 其他数字型放行


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', default=None, help='版本号，如 v1.0.0')
    args = ap.parse_args()

    if not os.path.isdir(SRC_DIR):
        print(f'[ERROR] 找不到 {SRC_DIR}')
        print('        先跑 build_exe.bat 生成 onedir 产物，再执行本脚本。')
        return 1

    version = args.version or today_version()
    if args.version and not validate_version(version):
        print(f'[ERROR] 版本号 {version} 不合法：须为 vYYYYMMDD 或 vYYYYMMDD-xxx，'
              f'且日期不早于今天（{time.strftime("%Y%m%d")}）')
        return 1
    zip_path = os.path.join(OUT_DIR, ZIP_NAME)

    # 把「最小 version.json」嵌进应用目录（随 zip 发出去，游戏运行时读它判断当前版本）。
    # 注意：此处只包含 version/asset/url/manifest_url，**不含 sha256/size**——
    # 否则会陷入「sha 要算 zip、zip 又含 version.json」的循环。sha/size 只写在下面
    # 那份作为 Release 附件发布的完整 version.json 里（它不在 zip 内）。
    embedded = {
        'version': version,
        'asset': ASSET_NAME,
        'url': LATEST_URL,
        'manifest_url': MANIFEST_URL,
    }
    with open(os.path.join(SRC_DIR, 'version.json'), 'w', encoding='utf-8') as f:
        json.dump(embedded, f, ensure_ascii=False, indent=2)

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

    # 完整 manifest：随 Release 一起作为独立附件发布；自动更新器拉的就是它。
    manifest = {
        'version': version,
        'asset': ASSET_NAME,
        'url': LATEST_URL,
        'manifest_url': MANIFEST_URL,
        'sha256': digest,
        'size': size,
        'notes': '本文件须与 zip 一起作为 Release 附件上传（更新器通过 manifest_url 拉取）；'
                 'zip 内含的是只带 version 的最小 version.json，不影响此处的 sha。',
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
