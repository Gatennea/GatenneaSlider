#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 repro_fast -dump 输出的完整着色集 A 状态图落盘，做集合计数 / 筛选 / 解码。

用法：
  python read_full_A.py <dir>                 # 打印集合计数摘要
  python read_full_A.py <dir> --decode ID      # 把状态 ID 解码成 ASCII 多联骨牌
  python read_full_A.py <dir> --list SET [N]   # 列出属于 SET 的前 N 个状态 ID
                                              #   SET ∈ {A,cone,B,solvable,sink,ext_pred,
                                              #           cone_notB,two_not_touching,basin_true}
  python read_full_A.py <dir> --edges          # 打印边总数与若干示例

记录格式（每个状态 16 字节，小端）：
  off 0  u32 id
  off 4  u8  flags : bit0=inCone,1=inB,2=sink,3=inBasinTrue,
                     4=cone_notB,5=ext_pred,6=two_not_touching,7=solvable
  off 5  u8  pad
  off 6  u16 outdeg
  off 8  u16 indeg
  off 10 i32 dist   (回程距离；不在 B 内为 -1)
boards.bin：每个状态 16×u16（规范形，行 r 的位 c 表示第 c 列有格）。
"""
import sys, struct, os

SET_BITS = {
    "A": None,            # 全集（始终成立）
    "cone": 1 << 0,
    "B": 1 << 1,
    "sink": 1 << 2,
    "basin_true": 1 << 3,
    "cone_notB": 1 << 4,
    "ext_pred": 1 << 5,
    "two_not_touching": 1 << 6,
    "solvable": 1 << 7,
}


def load_membership(d):
    p = os.path.join(d, "membership.bin")
    recs = []
    with open(p, "rb") as f:
        data = f.read()
    n = len(data) // 16
    for i in range(n):
        id_, flags, pad, outdeg, indeg, dist = struct.unpack_from("<I B B H H i", data, i * 16)
        recs.append((id_, flags, outdeg, indeg, dist))
    return recs


def decode_board(d, idx):
    p = os.path.join(d, "boards.bin")
    with open(p, "rb") as f:
        f.seek(idx * 32)
        rows = struct.unpack("<16H", f.read(32))
    # 找实际范围
    nonempty = [i for i in range(16) if rows[i]]
    if not nonempty:
        return "(empty)"
    rmin, rmax = nonempty[0], max(nonempty)
    lines = []
    for i in range(rmin, rmax + 1):
        mask = rows[i]
        s = "".join("#" if (mask >> c) & 1 else "." for c in range(16))
        s = s.rstrip(".")
        lines.append(s)
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    d = sys.argv[1]
    recs = load_membership(d)

    if "--decode" in sys.argv:
        idx = int(sys.argv[sys.argv.index("--decode") + 1])
        r = recs[idx]
        print(f"id={r[0]} flags=0x{r[1]:02x} outdeg={r[2]} indeg={r[3]} dist={r[4]}")
        print(decode_board(d, idx))
        return

    if "--list" in sys.argv:
        pos = sys.argv.index("--list")
        setname = sys.argv[pos + 1]
        n = int(sys.argv[pos + 2]) if len(sys.argv) > pos + 2 else 20
        bit = SET_BITS[setname]
        out = []
        for r in recs:
            if setname == "A" or (r[1] & bit):
                out.append(r[0])
                if len(out) >= n:
                    break
        print(f"{setname}: showing {len(out)} ids ->", out)
        return

    if "--edges" in sys.argv:
        ep = os.path.join(d, "edges.bin")
        if not os.path.exists(ep):
            print("edges.bin 不存在（可能用了 -noedges）")
            return
        with open(ep, "rb") as f:
            data = f.read()
        ne = len(data) // 8
        print(f"edges 总数 = {ne}")
        for i in range(min(10, ne)):
            u, v = struct.unpack_from("<II", data, i * 8)
            print(f"  {u} -> {v}")
        return

    # 默认：集合计数摘要
    cnt = {k: 0 for k in SET_BITS}
    n = len(recs)
    for r in recs:
        fl = r[1]
        for k, bit in SET_BITS.items():
            if k == "A" or (fl & bit):
                cnt[k] += 1
    print(f"目录: {d}")
    print(f"|A| = {n}")
    for k in ["cone", "B", "solvable", "sink", "cone_notB", "ext_pred", "basin_true", "two_not_touching"]:
        print(f"  {k:18s} = {cnt[k]}")


if __name__ == "__main__":
    main()
