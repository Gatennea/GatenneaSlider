# experiments/script__chk_shatter_slots.py  v2：大区域内部槽位验证（排除有限边界假阴性）
import math, io, contextlib, importlib.util
spec = importlib.util.spec_from_file_location(
    "iso", __file__.replace('script__chk_shatter_slots.py', 'script__chk_iso_puzzle.py'))
M = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(M)

SQ3 = math.sqrt(3.0)
EPS = 1e-6
# 大区域（R=6 单元，432 块）做内部验证
slots = [(('R' if n in M.RED else 'G'),
          tuple(tuple(round(c, 6) for c in v) for v in t)) for n, t in M.big]
slot_set = {pg for _, pg in slots}

def translate(pg, v):
    return tuple((round(x + v[0], 6), round(y + v[1], 6)) for (x, y) in pg)

def bbox():
    xs = [x for _, pg in slots for x, _ in pg]
    ys = [y for _, pg in slots for _, y in pg]
    return min(xs), max(xs), min(ys), max(ys)

minx, maxx, miny, maxy = bbox()
def interior(pg):
    xs = [x for x, _ in pg]; ys = [y for _, y in pg]
    cx, cy = sum(xs)/3, sum(ys)/3
    return (minx + 1 < cx < maxx - 1) and (miny + 1 < cy < maxy - 1)

SEAMS = {
    'lattice_30':  (math.cos(math.radians(30)),  math.sin(math.radians(30))),
    'lattice_90':  (0.0, 1.0),
    'lattice_150': (math.cos(math.radians(150)), math.sin(math.radians(150))),
    'green_0':     (SQ3, 0.0),
    'green_60':    (SQ3 * math.cos(math.radians(60)), SQ3 * math.sin(math.radians(60))),
    'green_120':   (SQ3 * math.cos(math.radians(120)), SQ3 * math.sin(math.radians(120))),
}
print('大区域槽位 %d，内部槽位 %d' % (len(slots), sum(1 for _, pg in slots if interior(pg))))
for name, v in SEAMS.items():
    interior_slots = [(t, pg) for t, pg in slots if interior(pg)]
    on_grid = sum(1 for _, pg in interior_slots if translate(pg, v) in slot_set)
    # 一个内点例子
    ex = interior_slots[0]
    dest = translate(ex[1], v)
    print(f'  {name:12s} v=({v[0]:.3f},{v[1]:.3f})  内部落网格 {on_grid}/{len(interior_slots)}'
          f'   例: 出发型{ex[0]} 落点{"在网格" if dest in slot_set else "脱网格"}')
