#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
聚合 full_A/<m>_<n>_<s>/summary.txt，输出总表（Markdown + CSV）。

用法：
  python aggregate_full_A.py [root]
    root 默认 = 本脚本所在目录下的 full_A/
"""
import os, sys, glob, re

FIELDS = [
    ("m", None), ("n", None), ("s", None),
    ("|A|", "A"), ("|cone|", "cone"), ("|B|", "B"), ("god", "god"),
    ("可解 cone∩B", "solvable"), ("真死局 sink(出度0)", "sink"),
    ("cone\\B(旧\"死局\"口径)", "cone_notB"), ("外部前驱 B\\cone", "ext_pred"),
    ("吸引盆(真死局口径)", "basin_true"), ("吸引盆(旧 cone\\B口径)", "basin_old"),
    ("不可解 A-B", "unsolv"), ("两不沾(真死局口径)", "TNT_true"),
    ("两不沾(旧口径)", "TNT_old"), ("edges", "edges"),
]

KEYMAP = {
    "|A|": "A", "|cone|": "cone", "|B| (逆向可达/可解集)": "B",
    "god (回程口径,B内)": "god", "可解 cone∩B": "solvable",
    "真死局 sink(出度0)": "sink", "cone\\B(旧\"死局\"口径)": "cone_notB",
    "外部前驱 B\\cone": "ext_pred", "吸引盆(真死局口径)": "basin_true",
    "吸引盆(旧 cone\\B口径)": "basin_old", "不可解 A-B": "unsolv",
    "两不沾(真死局口径)": "TNT_true", "两不沾(旧口径)": "TNT_old",
    "edges": "edges", "其中在B内": "_sink_inB",
}


def parse_summary(path):
    info = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            m = re.match(r"=== \((\d+),(\d+),(\d+)\) K=(\d+) ===", line)
            if m:
                info["m"], info["n"], info["s"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
                continue
            for k in KEYMAP:
                if line.startswith(k) and len(line) > len(k) and line[len(k)] in (" ", "="):
                    val = line[len(k):].lstrip("= ").strip()
                    val = re.split(r"\s", val)[0].replace(",", "")
                    try:
                        info[KEYMAP[k]] = int(val)
                    except ValueError:
                        pass
                    break
    return info


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "full_A")
    files = sorted(glob.glob(os.path.join(root, "*", "summary.txt")))
    rows = [parse_summary(p) for p in files]
    rows = [r for r in rows if "m" in r]
    rows.sort(key=lambda r: (r["m"], r["n"], r["s"]))

    hdr = ["m", "n", "s", "K", "A", "cone", "B", "god", "可解", "sink(真死局)", "cone\\B", "B\\cone", "吸引盆(真)", "吸引盆(旧)", "A-B", "两不沾(真)", "两不沾(旧)", "edges"]
    print("| " + " | ".join(hdr) + " |")
    print("|" + "|".join(["---"] * len(hdr)) + "|")
    for r in rows:
        K = r["m"] * r["n"]
        cells = [r.get("m", ""), r.get("n", ""), r.get("s", ""), K,
                 r.get("A", ""), r.get("cone", ""), r.get("B", ""), r.get("god", ""),
                 r.get("solvable", ""), r.get("sink", ""), r.get("cone_notB", ""),
                 r.get("ext_pred", ""), r.get("basin_true", ""), r.get("basin_old", ""),
                 r.get("unsolv", ""), r.get("TNT_true", ""), r.get("TNT_old", ""), r.get("edges", "")]
        print("| " + " | ".join(str(c) for c in cells) + " |")

    # CSV
    csvp = os.path.join(root, "ALL_SUMMARY.csv")
    with open(csvp, "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            K = r["m"] * r["n"]
            cells = [r.get("m", ""), r.get("n", ""), r.get("s", ""), K,
                     r.get("A", ""), r.get("cone", ""), r.get("B", ""), r.get("god", ""),
                     r.get("solvable", ""), r.get("sink", ""), r.get("cone_notB", ""),
                     r.get("ext_pred", ""), r.get("basin_true", ""), r.get("basin_old", ""),
                     r.get("unsolv", ""), r.get("TNT_true", ""), r.get("TNT_old", ""), r.get("edges", "")]
            f.write(",".join(str(c) for c in cells) + "\n")
    print(f"\nCSV 已写: {csvp}  ({len(rows)} 个谜题)")


if __name__ == "__main__":
    main()
