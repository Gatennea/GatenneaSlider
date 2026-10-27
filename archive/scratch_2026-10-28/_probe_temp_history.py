# -*- coding: utf-8 -*-
"""看一眼当前 config/temp_history.json 是什么局（排查 §九 时用）。"""
import os
import sys
import json

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
os.chdir(_PROJ)

out = []
p = os.path.join('config', 'temp_history.json')
out.append('exists=%s' % os.path.exists(p))
if os.path.exists(p):
    d = json.load(open(p, encoding='utf-8'))
    out.append('top keys=%s' % sorted(d.keys()))
    out.append('puzzle=%s' % json.dumps(d.get('puzzle', {}), ensure_ascii=False))
    hs = d.get('history', {})
    sn = hs.get('snapshots', [])
    out.append('snapshots=%d index=%s' % (len(sn), hs.get('history_index')))
    for i, s in enumerate(sn):
        mat = s.get('matrix', [])
        nz = sum(1 for row in mat for v in row if v)
        out.append('  #%d es=%s rows=%d nonzero=%d keys=%s'
                   % (i, bool(s.get('engine_state')), len(mat), nz,
                      sorted(k for k in s.keys() if k != 'matrix')))

with open(os.path.join(_PROJ, 'archive', '_th_probe.txt'), 'w',
          encoding='utf-8') as f:
    f.write('\n'.join(out))
