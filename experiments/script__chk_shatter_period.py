# experiments/script__chk_shatter_period.py
# 算碎三角槽位网格的真实平移周期：统计内部槽位质心差，找高频向量。
import math, io, contextlib, importlib.util, collections
spec = importlib.util.spec_from_file_location(
    "iso", __file__.replace('script__chk_shatter_period.py', 'script__chk_iso_puzzle.py'))
M = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(M)

def centroid(t):
    return ((t[0][0]+t[1][0]+t[2][0])/3, (t[0][1]+t[1][1]+t[2][1])/3)

slots = [centroid(t) for _, t in M.big]
minx = min(p[0] for p in slots); maxx = max(p[0] for p in slots)
miny = min(p[1] for p in slots); maxy = max(p[1] for p in slots)
def interior(p):
    return (minx+1 < p[0] < maxx-1) and (miny+1 < p[1] < maxy-1)
inner = [p for p in slots if interior(p)]
# 高频质心差（候选周期向量）
cnt = collections.Counter()
for a in inner:
    for b in inner:
        dx = round(b[0]-a[0], 6); dy = round(b[1]-a[1], 6)
        if dx or dy:
            cnt[(dx, dy)] += 1
print('内部槽位 %d，候选差向量 %d 种' % (len(inner), len(cnt)))
print('出现最频繁的 12 个差向量（候选周期，出现次数）：')
for v, c in cnt.most_common(12):
    print('  (%8.4f,%8.4f)  ×%4d' % (v[0], v[1], c))
