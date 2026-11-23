# -*- coding: utf-8 -*-
"""解剖對換序列：抽象字、軸向配比、縫使用厚度。

輸入：sequences/swap_*_all*_cases.json（全部已由 verify_swap.py 驗過）
輸出：三張表——
  1. 每個 (盤, 步數) 下，抽象字有多少種不同（判「有沒有模板」）
  2. 步數 → (H,V) 配比（判「預算是否剛性」）
  3. 每個 (盤, 步數) 的縫使用：用到幾條縫、單條最多重複幾次（判「薄／厚」）

抽象字：每步只留 (縫種類 H/V, 移動軸向 ±)，丟掉縫號與具體格子。
用法：D:\\python\\python.exe experiments\\math_repro\\analyze_words.py
"""
import collections
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SEQ = os.path.join(HERE, "sequences")


def load_all():
    out = []
    for fn in sorted(glob.glob(os.path.join(SEQ, "swap_*_all*_cases.json"))):
        # 跳過 swap_432_all_cases.json：那是 1181 步時代的舊檔，已被 all14 取代
        if os.path.basename(fn) == "swap_432_all_cases.json":
            continue
        with open(fn, encoding="utf-8") as f:
            cases = json.load(f)
        if not cases:
            continue
        m, n, s = cases[0]["m"], cases[0]["n"], cases[0]["s"]
        out.append(((m, n, s), os.path.basename(fn), cases))
    return out


def word_of(step):
    u = step["unit"]
    kind = "H" if u[0] == 0 else "V"
    d = ("+r" if u[0] > 0 else "-r") if u[0] else ("+c" if u[1] > 0 else "-c")
    return kind + d


def axis_of(step):
    return "H" if step["unit"][0] == 0 else "V"


def main():
    data = load_all()

    print("### 1) 抽象字的多樣性（同一步數下，有幾種不同字）")
    for board, fn, cases in data:
        by_L = collections.defaultdict(list)
        for c in cases:
            by_L[c["steps"]].append(" ".join(word_of(st) for st in c["path"]))
        line = []
        for L in sorted(by_L):
            words = by_L[L]
            line.append("L%d:%d例/%d種" % (L, len(words), len(set(words))))
        print("  %-10s %s" % (str(board), "  ".join(line)))

    print()
    print("### 2) 步數 → 軸向配比 (H,V)")
    budget = collections.defaultdict(set)
    for board, fn, cases in data:
        for c in cases:
            h = sum(1 for st in c["path"] if axis_of(st) == "H")
            budget[c["steps"]].add((h, len(c["path"]) - h))
    for L in sorted(budget):
        print("  L=%2d  %s" % (L, sorted(budget[L])))

    print()
    print("### 3) 縫使用厚度（k = 用到幾條縫；max = 單條最多重複）")
    for board, fn, cases in data:
        per = collections.defaultdict(list)
        for c in cases:
            cnt = collections.Counter(st["seam"] for st in c["path"])
            per[c["steps"]].append((len(cnt), max(cnt.values())))
        parts = []
        for L in sorted(per):
            k = sorted(set(x[0] for x in per[L]))
            mx = sorted(set(x[1] for x in per[L]))
            parts.append("L%d:k%s/max%s" % (L, k, mx))
        print("  %-10s %s" % (str(board), "  ".join(parts)))

    print()
    print("### 4) 面積帳：Σ|moved|、每步搬動、碰到幾格（只看最短檔）")
    for board, fn, cases in data:
        Lmin = min(c["steps"] for c in cases)
        cells = board[0] * board[1]
        sel = [c for c in cases if c["steps"] == Lmin]
        tot = 0
        touched = set()
        for c in sel:
            for st in c["path"]:
                tot += len(st["moved"])
                for p in st["moved"]:
                    touched.add((p[0], p[1]))
        n = len(sel)
        sm = tot / n
        # touched 用「每例平均」比較公平
        avg_t = sum(len({(p[0], p[1]) for st in c["path"] for p in st["moved"]}) for c in sel) / n
        print("  %-10s L%d 例%2d  Σ|moved|=%5.1f  每步=%4.2f  碰到 %4.1f/%d (%.0f%%)" % (
            str(board), Lmin, n, sm, sm / Lmin, avg_t, cells, 100.0 * avg_t / cells))


if __name__ == "__main__":
    main()
