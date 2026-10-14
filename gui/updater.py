# -*- coding: utf-8 -*-
"""Gatennea Slider 增量更新器（就地更新，保留玩家数据）。

设计要点
--------
- 这是个 PyInstaller onedir 程序。Windows 上**正在运行的 exe 不能覆盖自己**，
  `_internal/` 也被锁，所以「把新文件写进安装目录」必须由**游戏退出后才跑的独立
  进程**完成。
- 流程：
    1. 比对「随包发行的 version.json（当前版本）」与 GitHub 最新的 version.json。
    2. 发现新版本 → 流式下载 zip（边下边算 SHA256，下完校验，防损坏/被换包）
       → 解压到临时目录（自动剥离 zip 里的顶层 GatenneaSlider/）。
    3. 写一个临时 .cmd，等游戏退出后用**系统自带 robocopy** 把新文件合并进安装目录
       （`/e` 但不 `/purge` ⇒ 只覆盖 zip 里有的文件，**绝不删除** config/macro/save
       等用户数据），再用 `start` 重启游戏。
    4. 启动 .cmd 并立即退出游戏。
- 只在冻结环境（sys.frozen）且能读到 version.json 时启用；开发期（源码跑）不激活。
- 系统侧只依赖 robocopy（Win7+ 必带），下载/解压/校验全用 Python 标准库，零第三方依赖。

所有网络/解压/生成步骤都可被测试用「本地 HTTP 服务器」模拟，无需真实访问 GitHub。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import urllib.error
import urllib.request

REPO = 'Gatennea/GatenneaSlider'
ASSET_NAME = 'GatenneaSlider-Windows.zip'
MANIFEST_URL = 'https://github.com/{}/releases/latest/download/version.json'.format(REPO)
ZIP_LATEST_URL = 'https://github.com/{}/releases/latest/download/{}'.format(REPO, ASSET_NAME)

# 更新器只覆盖「程序文件」，绝不触碰这三个用户数据目录（它们也不在 zip 里）。
# 这里只是文档性常量；真正的保护来自 build_release 把 'save' 也排除出 zip。
PROTECTED_DIRS = ('config', 'macro', 'save')


# ----------------------------------------------------------------------------
# 版本 / 安装目录
# ----------------------------------------------------------------------------
def is_frozen():
    """是否在 PyInstaller 冻结环境运行。"""
    return getattr(sys, 'frozen', False)


def app_dir():
    """游戏安装目录（exe 所在目录）。开发期回退到本文件所在目录（仅供测试）。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def current_version():
    """读取随包发行的 version.json 里的 version 字段。读不到返回 None。"""
    p = os.path.join(app_dir(), 'version.json')
    if not os.path.isfile(p):
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f).get('version')
    except Exception:
        return None


def parse_commit_count(vstr):
    """'v197-20261006' -> 197（提交数，单调递增，用作版本先后判据）。
    解析失败返回 -1。"""
    if not vstr or not isinstance(vstr, str):
        return -1
    s = vstr[1:] if vstr.startswith('v') else vstr
    s = s.split('-')[0]
    return int(s) if s.isdigit() else -1


# ----------------------------------------------------------------------------
# 清单获取 / 比较
# ----------------------------------------------------------------------------
def fetch_manifest(url=MANIFEST_URL, timeout=10):
    """拉取最新 version.json（GitHub 的 latest/download 会自动 302 到真实资源）。"""
    req = urllib.request.Request(url, headers={'User-Agent': 'GatenneaSlider-Updater'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def is_newer(manifest, current_vstr):
    """manifest 的版本是否比 current_vstr 新。以提交数为准；解析失败时用字符串不等兜底。"""
    mc = parse_commit_count(manifest.get('version'))
    cc = parse_commit_count(current_vstr)
    if mc >= 0 and cc >= 0:
        return mc > cc
    return manifest.get('version') != current_vstr


# ----------------------------------------------------------------------------
# 下载 / 校验 / 解压
# ----------------------------------------------------------------------------
def download_zip(url, dest, sha256_expected=None, progress_cb=None, timeout=30):
    """流式下载 zip 到 dest，边下边算 SHA256；下完与 sha256_expected 比对。
    progress_cb(downloaded_bytes, total_bytes) 可选。返回实算 SHA256。"""
    req = urllib.request.Request(url, headers={'User-Agent': 'GatenneaSlider-Updater'})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get('Content-Length', 0) or 0)
        got = 0
        with open(dest, 'wb') as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress_cb:
                    progress_cb(got, total)
    digest = h.hexdigest()
    if sha256_expected and digest.lower() != sha256_expected.lower():
        raise ValueError(
            'SHA256 不匹配：期望 {}，实得 {}（下载可能被截断或来源被篡改）'.format(
                sha256_expected.lower(), digest.lower()))
    return digest


def extract_zip(zip_path, dest):
    """解压 zip 到 dest，若所有条目都以同一顶层目录开头则自动剥离它
    （build_release 打的包顶层是 GatenneaSlider/）。返回真正的内容根目录 dest。"""
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        names = z.namelist()
        top = None
        if names:
            first = names[0].split('/')[0]
            if first and all(n.startswith(first + '/') for n in names):
                top = first
        for n in names:
            rel = n[len(top) + 1:] if (top and n.startswith(top + '/')) else n
            if not rel:
                continue
            target = os.path.join(dest, rel)
            if n.endswith('/'):
                os.makedirs(target, exist_ok=True)
            else:
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with z.open(n) as src, open(target, 'wb') as out:
                    shutil.copyfileobj(src, out)
    return dest


# ----------------------------------------------------------------------------
# 生成外部替换脚本（游戏退出后才跑）
# ----------------------------------------------------------------------------
def make_updater_cmd(staging_dir, install_dir, exe_name):
    """写一个临时 .cmd：等游戏退出后用系统 robocopy 合并覆盖安装目录，
    再重启游戏。返回 .cmd 路径（位于 %TEMP%，与 staging 分开，避免被自己清理）。

    robocopy 用 /e（含空子目录）但**不用 /purge** ⇒ 只更新 zip 里有的文件，
    绝不删除 config/macro/save 等用户数据。"""
    cmd = (
        '@echo off\n'
        'timeout /t 2 /nobreak >nul\n'                       # 等游戏释放文件句柄
        'robocopy "{stage}" "{inst}" /e /njh /njs /nfl /ndl /nc /ns /np\n'
        'start "" "{exe}"\n'
    ).format(stage=staging_dir, inst=install_dir, exe=os.path.join(install_dir, exe_name))
    fd, path = tempfile.mkstemp(suffix='.cmd', prefix='gatsli_upd_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(cmd)
    return path


def launch_updater_and_exit(cmd_path):
    """以独立（DETACHED）进程启动 .cmd，然后立即退出游戏。
    用 os._exit 保证进程立刻结束，不等待 pygame/SDL 清理，避免文件句柄拖延。"""
    subprocess.Popen(['cmd', '/c', cmd_path],
                     creationflags=0x00000008)  # CREATE_DETACHED_PROCESS
    # 给 .cmd 一点时间真正起来（它自己还有 timeout 2s 兜底）
    time.sleep(0.2)
    os._exit(0)


# ----------------------------------------------------------------------------
# 高层动作
# ----------------------------------------------------------------------------
def perform_update(manifest, progress_cb=None):
    """下载 → 校验 → 解压 → 生成 .cmd → 启动 .cmd → 退出游戏。
    任何一步失败都会抛异常，调用方据此提示用户并**不**退出游戏。"""
    install_dir = app_dir()
    exe_name = os.path.basename(sys.executable)
    tmp = tempfile.mkdtemp(prefix='gatsli_upd_')
    try:
        zip_path = os.path.join(tmp, ASSET_NAME)
        stage = os.path.join(tmp, 'stage')
        url = manifest.get('url') or ZIP_LATEST_URL
        download_zip(url, zip_path, manifest.get('sha256'), progress_cb)
        extract_zip(zip_path, stage)
        cmd = make_updater_cmd(stage, install_dir, exe_name)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    # 到此下载校验解压都成功 ⇒ 真正落地替换交给 .cmd，并退出游戏
    launch_updater_and_exit(cmd)


def check_for_update(callback, url=MANIFEST_URL, timeout=10):
    """后台线程里查更新。callback(newer: bool, manifest: dict|None, error: Exception|None)。"""
    def _run():
        try:
            manifest = fetch_manifest(url, timeout)
            cur = current_version()
            callback(is_newer(manifest, cur), manifest, None)
        except Exception as e:  # 网络/解析错误：静默视为「无更新」
            callback(False, None, e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ----------------------------------------------------------------------------
# 自测（无需网络）：用本地 HTTP 服务器模拟 GitHub Release
# ----------------------------------------------------------------------------
def _self_test():  # pragma: no cover - 手动调试用
    import http.server
    import socketserver
    import threading

    tmp = tempfile.mkdtemp(prefix='gatsli_selftest_')
    inst = os.path.join(tmp, 'install')
    os.makedirs(os.path.join(inst, 'save'), exist_ok=True)
    with open(os.path.join(inst, 'GatenneaSlider.exe'), 'wb') as f:
        f.write(b'OLD_EXE')
    with open(os.path.join(inst, 'save', 'my_puzzle.json'), 'w', encoding='utf-8') as f:
        f.write('{"keep": true}')
    # 新版内容
    newroot = os.path.join(tmp, 'newver', 'GatenneaSlider')
    os.makedirs(newroot, exist_ok=True)
    with open(os.path.join(newroot, 'GatenneaSlider.exe'), 'wb') as f:
        f.write(b'NEW_EXE')
    with open(os.path.join(newroot, 'version.json'), 'w', encoding='utf-8') as f:
        json.dump({'version': 'v999-20261014', 'url': '', 'sha256': ''}, f)
    zip_path = os.path.join(tmp, ASSET_NAME)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for dp, _, fns in os.walk(newroot):
            for fn in fns:
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, os.path.dirname(newroot)).replace('\\', '/'))
    sha = hashlib.sha256(open(zip_path, 'rb').read()).hexdigest()
    manifest = {'version': 'v999-20261014', 'url': '', 'sha256': sha}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.endswith('version.json'):
                body = json.dumps(manifest).encode()
            else:
                body = open(zip_path, 'rb').read()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = socketserver.TCPServer(('127.0.0.1', 0), H)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    base = 'http://127.0.0.1:{}/'.format(port)
    m = fetch_manifest(base + 'version.json')
    assert is_newer(m, 'v100-20260101'), 'is_newer 判断错误'
    dl = os.path.join(tmp, 'dl.zip')
    download_zip(base + ASSET_NAME, dl, sha)
    stage = os.path.join(tmp, 'stage')
    extract_zip(dl, stage)
    assert os.path.isfile(os.path.join(stage, 'GatenneaSlider.exe')), '剥离顶层失败'
    # 模拟 .cmd 的 robocopy 合并（直接用 shutil 等效：拷 stage 内容进 inst，不删 inst 原有）
    for dp, _, fns in os.walk(stage):
        for fn in fns:
            s = os.path.join(dp, fn)
            rel = os.path.relpath(s, stage)
            tgt = os.path.join(inst, rel)
            os.makedirs(os.path.dirname(tgt), exist_ok=True)
            shutil.copy2(s, tgt)
    assert open(os.path.join(inst, 'GatenneaSlider.exe'), 'rb').read() == b'NEW_EXE'
    assert os.path.isfile(os.path.join(inst, 'save', 'my_puzzle.json')), '用户存档被删！'
    print('SELF TEST PASS: 新文件到位，用户存档保留')
    httpd.shutdown()


if __name__ == '__main__':
    _self_test()
