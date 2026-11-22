"""印出某個還原態與其一步鄰居的出邊數，看「窄盤的孩子是不是全是死胡同」。

用法：D:\\python\\python.exe _chk_cone_depth.py <dump_dir> <goal_id>
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def main(d, g):
    mem = np.fromfile(os.path.join(d, 'membership.bin'), dtype=np.uint8).reshape(-1, 16)
    ed = np.fromfile(os.path.join(d, 'edges.bin'), dtype='<u4').reshape(-1, 2)
    print('狀態 %d、邊 %d' % (len(mem), len(ed)))
    print('還原態出邊 %d' % int(mem[g][6]))
    kids = [int(b) for a, b in ed if int(a) == g]
    for k in kids:
        print('  孩子 %d：出邊 %d、flags %d' % (k, int(mem[k][6]), int(mem[k][4])))


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
