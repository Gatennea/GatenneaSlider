# 受众: AI
# 参数扫描驱动（幂等版）：对 (m,n,s) 跑 repro_fast 的「全枚举 / R6 群阶 / 全量粘连」，
# 解析关键数到 CSV（逐行追加，崩了不丢）+ Markdown 表。已有 out_* 文件则复用，不重跑。
import subprocess, re, os, sys, time

EXE = os.path.join(os.path.dirname(__file__), "repro_fast.exe")
OUTDIR = os.path.dirname(__file__)

# (m, n, s) 候选。K=m*n<=16（引擎上限）。(4,4,1) 为 s=1 全自由退化（≈1300万状态），
# 文档已有 Free(16)=13,079,255 闭式计数，枚举过慢且对群阶分类无新增信息，故跳过。
SIZE_LIST = [
    (2, 2, 2), (3, 2, 2), (2, 3, 2),
    (4, 2, 2), (2, 4, 2),
    (3, 3, 2), (4, 3, 2), (3, 4, 2),
    (5, 3, 2), (3, 5, 2),
    (6, 2, 2), (2, 6, 2),
    (3, 3, 1),
    (4, 3, 3), (3, 4, 3),
    (4, 4, 2), (4, 4, 3),
]

R6_STEPS = 300000
R6_SEED = 12345
FULLSTICKY_EDGE_CAP = 60000
ENUM_TIMEOUT = 900
R6_TIMEOUT = 900


def run(args, timeout):
    t0 = time.time()
    p = subprocess.run([EXE] + [str(a) for a in args],
                       capture_output=True, text=True, timeout=timeout)
    return p.stdout, p.stderr, time.time() - t0


def parse_enum(out):
    d = {}
    m = re.search(r"\|A\|\s*=\s*(\d+)", out);  d["A"] = int(m.group(1)) if m else None
    m = re.search(r"\|cone\|\s*=\s*(\d+)", out); d["cone"] = int(m.group(1)) if m else None
    m = re.search(r"\|B\|\s*=\s*(\d+)", out);  d["B"] = int(m.group(1)) if m else None
    m = re.search(r"^god\s*=\s*(\d+)", out, re.M); d["god"] = int(m.group(1)) if m else None
    m = re.search(r"dead\(cone-B\)\s*=\s*(\d+)", out); d["dead"] = int(m.group(1)) if m else None
    m = re.search(r"其中死局\s*(\d+)\s*个", out); d["dead_r7"] = int(m.group(1)) if m else None
    m = re.search(r"两端在 B 内\s*=\s*(\d+),\s*其中单步不可逆\s*=\s*(\d+)\s*\(([\d.]+)%\)", out)
    if m:
        d["B_edges"] = int(m.group(1)); d["irr_B"] = int(m.group(2)); d["irr_pct"] = float(m.group(3))
    m = re.search(r"R8\(强不可逆\):\s*B 内边\s*(\d+)\s*/\s*不可逆\s*(\d+)", out)
    if m:
        d["strong_B_edges"] = int(m.group(1)); d["strong_irr_B"] = int(m.group(2))
    return d


def parse_r6(out):
    d = {}
    m = re.search(r"trivial upper bound \(labels stay in own class\)\s*=\s*(\d+)", out)
    d["upper"] = int(m.group(1)) if m else None
    # 优先取 STRICT group order（若存在）
    m = re.search(r"STRICT group order\s*=\s*(\d+)\s*(= upper bound .*精确阶)?", out)
    if m:
        d["order"] = int(m.group(1)); d["exact"] = bool(m.group(2)); return d
    m = re.search(r"group order\s*=\s*(\d+)\s*(= upper bound .*精确阶)?", out)
    if m:
        d["order"] = int(m.group(1)); d["exact"] = bool(m.group(2)); return d
    ms = re.findall(r"closure with \d+ generators\s*=\s*(\d+)", out)
    if ms:
        d["order"] = int(ms[-1]); d["exact"] = False
    return d


def parse_fullsticky(out):
    m = re.search(r"其中移动分量落位后已不可再选中（粘性型）\s*=\s*(\d+)", out)
    return int(m.group(1)) if m else None


def main():
    cols = ["m", "n", "s", "K", "A", "cone", "B", "god", "dead", "dead_r7",
            "B_edges", "irr_B", "irr_pct", "strong_irr_B",
            "upper", "order", "exact", "sticky", "enum_sec", "r6_sec"]
    csv_path = os.path.join(OUTDIR, "sweep_results.csv")
    md_path = os.path.join(OUTDIR, "sweep_results.md")
    # 幂等：读已有 CSV 的行（跳过表头）以跳过已完成的尺寸
    done = set()
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            lines = f.read().splitlines()
        for ln in lines[1:]:
            if not ln.strip():
                continue
            parts = ln.split(",")
            if len(parts) >= 4 and parts[0].isdigit():
                done.add((int(parts[0]), int(parts[1]), int(parts[2])))

    rows = []
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            for ln in f.read().splitlines()[1:]:
                if ln.strip():
                    rows.append(dict(zip(cols, [x if x != "" else None for x in ln.split(",")])))

    for (m, n, s) in SIZE_LIST:
        tag = f"{m}_{n}_{s}"
        if (m, n, s) in done:
            print(f"[sweep] skip (already done) ({m},{n},{s})", flush=True)
            continue
        print(f"[sweep] === ({m},{n},{s}) K={m*n} ===", flush=True)
        full_path = os.path.join(OUTDIR, f"out_{tag}_full.txt")
        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
            with open(full_path) as f:
                out = f.read()
            err = ""
        else:
            out, err, sec = run([m, n, s], ENUM_TIMEOUT)
            with open(full_path, "w") as f:
                f.write(out)
                if err: f.write("\n--- STDERR ---\n" + err)
        e = parse_enum(out)
        e["enum_sec"] = round(os.path.getmtime(full_path) and 0.0, 2) if False else e.get("enum_sec")
        if err.strip():
            print(f"   enum stderr: {err.strip()[:200]}", flush=True)
        # R6
        r6_path = os.path.join(OUTDIR, f"out_{tag}_r6.txt")
        if os.path.exists(r6_path) and os.path.getsize(r6_path) > 0:
            with open(r6_path) as f:
                out6 = f.read()
        else:
            out6, err6, sec6 = run([m, n, s, "-r6", R6_STEPS, "-bias", 0, "-seed", R6_SEED], R6_TIMEOUT)
            with open(r6_path, "w") as f:
                f.write(out6)
                if err6: f.write("\n--- STDERR ---\n" + err6)
        r6 = parse_r6(out6)
        r6["r6_sec"] = None
        # 全量粘连（仅 B 内不可逆边数较小者）
        sticky = None
        if e.get("irr_B") is not None and e["irr_B"] <= FULLSTICKY_EDGE_CAP:
            st_path = os.path.join(OUTDIR, f"out_{tag}_sticky.txt")
            if os.path.exists(st_path) and os.path.getsize(st_path) > 0:
                with open(st_path) as f:
                    outf = f.read()
            else:
                outf, errf, secf = run([m, n, s, "-fullsticky"], ENUM_TIMEOUT)
                with open(st_path, "w") as f:
                    f.write(outf)
                    if errf: f.write("\n--- STDERR ---\n" + errf)
            sticky = parse_fullsticky(outf)
        row = {"m": m, "n": n, "s": s, "K": m * n, **e, **r6, "sticky": sticky}
        rows.append(row)
        # 增量写 CSV
        with open(csv_path, "w") as f:
            f.write(",".join(cols) + "\n")
            for r in rows:
                f.write(",".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
        print(f"   A={e.get('A')} B={e.get('B')} god={e.get('god')} dead={e.get('dead')} "
              f"irr_B={e.get('irr_B')} |G|={r6.get('order')}"
              f"{'(精确)' if r6.get('exact') else ''} sticky={sticky}", flush=True)

    # 写出 Markdown
    with open(md_path, "w") as f:
        f.write("受众: AI\n\n# 参数扫描结果表（repro_fast 全枚举 + R6 + 全量粘连）\n\n")
        f.write("| m | n | s | K | |A| | cone | |B| | 上帝之数 | 死局 | B内不可逆 | 不可逆% | "
                "强不可逆(B) | 群阶上界 | 群阶 | 精确? | 粘连型(全量) |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['m']} | {r['n']} | {r['s']} | {r['K']} | {r.get('A')} | {r.get('cone')} | "
                    f"{r.get('B')} | {r.get('god')} | {r.get('dead')} | {r.get('irr_B')} | "
                    f"{r.get('irr_pct')} | {r.get('strong_irr_B')} | {r.get('upper')} | "
                    f"{r.get('order')} | {'是' if r.get('exact') else '否'} | {r.get('sticky')} |\n")
        f.write(f"\n生成于 sweep.py（幂等增量版），共 {len(rows)} 个尺寸。\n")
        f.write("注：(4,4,1) 为 s=1 全自由退化（≈1300万状态），文档已有闭式 Free(16)=13,079,255，未纳入扫描。\n")
    print(f"[sweep] done: {csv_path}, {md_path}", flush=True)


if __name__ == "__main__":
    main()
