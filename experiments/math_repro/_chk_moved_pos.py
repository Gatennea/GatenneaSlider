import json, glob, os

def inspect(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return f"{os.path.basename(path)} PARSE-ERR {e}"
    p = d.get('puzzle', {})
    if p.get('type', 'square') not in ('square', 'numbered'):
        return None
    snaps = d.get('history', {}).get('snapshots', [])
    bad = 0
    multi = 0
    tot = 0
    for s in snaps:
        ms = s.get('moves') or ([s['move_info']] if s.get('move_info') else [])
        if len(ms) > 1:
            multi += 1
        for m in ms:
            tot += 1
            if 'moved_positions' not in m or 'gap_line' not in m \
               or 'gap_type' not in m or 'direction' not in m or 'step' not in m:
                bad += 1
    return f"{os.path.basename(path)} puzzle={p} steps={d.get('step_count')} moves={tot} bad={bad} multi={multi}"

print("=== 指定两个 ===")
for f in ['save/can\'t-gather.json', 'save/gathertest2-8-8-20261010-170304.json']:
    print(inspect(f))

print("=== 全部方形/数字存档（递归，前60）===")
cnt = 0
for f in sorted(glob.glob('save/**/*.json', recursive=True)):
    r = inspect(f)
    if r is None:
        continue
    print(r)
    cnt += 1
    if cnt >= 60:
        break
