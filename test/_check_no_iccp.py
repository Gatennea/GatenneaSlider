# -*- coding: utf-8 -*-
"""防回归：仓库内 PNG（含 ICO 内嵌 PNG）不得带 iCCP 块。

背景：libpng 1.6+ 对「自称 sRGB 但内容不正确」的 iCCP 块会向 stderr 打
「libpng warning: iCCP: known incorrect sRGB profile」。不同构建的
SDL_image/libpng 严格度不同，宽松的不报、严格的每帧刷屏。根因清除办法
是剥掉 ancillary 的 iCCP 块（不影响像素解码，IDAT 逐字节不动）。
新增图片资源若再带 iCCP，本检查会失败。
"""
import os
import struct
import sys

PNG_SIG = b'\x89PNG\r\n\x1a\n'
SCAN_DIRS = ('picture',)
SKIP_DIRS = {'.git', 'dist', 'build', '__pycache__', 'video', 'voice_demo',
             '.workbuddy', 'node_modules', 'screenshots'}


def png_has_iccp(data: bytes) -> bool:
    if data[:8] != PNG_SIG:
        return False
    i = 8
    while i + 8 <= len(data):
        ln = struct.unpack('>I', data[i:i + 4])[0]
        if data[i + 4:i + 8] == b'iCCP':
            return True
        i += 12 + ln
    return False


def ico_has_iccp(data: bytes) -> bool:
    if data[:4] != b'\x00\x00\x01\x00':
        return False
    count = struct.unpack('<H', data[4:6])[0]
    for k in range(count):
        off = 6 + 16 * k
        size, img_off = struct.unpack('<II', data[off + 8:off + 16])
        if png_has_iccp(data[img_off:img_off + size]):
            return True
    return False


def main() -> int:
    bad = []
    total = 0
    for base in SCAN_DIRS:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fn in files:
                p = os.path.join(root, fn)
                low = fn.lower()
                if not (low.endswith('.png') or low.endswith('.ico')):
                    continue
                total += 1
                data = open(p, 'rb').read()
                hit = ico_has_iccp(data) if low.endswith('.ico') \
                    else png_has_iccp(data)
                if hit:
                    bad.append(p)
    print(f'scanned {total} images under {SCAN_DIRS}')
    if bad:
        for p in bad:
            print(f'FAIL iCCP: {p}')
        return 1
    print('PASS: no iCCP chunks anywhere')
    return 0


if __name__ == '__main__':
    sys.exit(main())
