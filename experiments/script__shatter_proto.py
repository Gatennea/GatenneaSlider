# experiments/script__shatter_proto.py
# 碎三角（双形状）引擎原型：用引擎真实滑动判据（整侧/分量平移 + 几何不重叠 + 几何连通）
# 验证"可玩"。坐标/拼盘复用 script__chk_iso_puzzle.py 的构造（L=2√3，x=1）。
import math, itertools, random
from collections import defaultdict, deque

SQ3 = math.sqrt(3.0); EPS = 1e-9

def sub(a, b): return (a[0]-b[0], a[1]-b[1])
def add(a, b): return (a[0]+b[0], a[1]+b[1])
def cross(a, b): return a[0]*b[1]-a[1]*b[0]
def dot(a, b): return a[0]*b[0]+a[1]*b[1]
def centroid(t): return ((t[0][0]+t[1][0]+t[2][0])/3.0, (t[0][1]+t[1][1]+t[2][1])/3.0)

def tri_overlap(t1, t2):
    """SAT：True=内部面积相交（共享边/顶点不算）。"""
    axes = []
    for tri in (t1, t2):
        for i in range(3):
            e = sub(tri[(i+1) % 3], tri[i]); axes.append((e[1], -e[0]))
    for ax in axes:
        p1 = [dot(v, ax) for v in t1]; p2 = [dot(v, ax) for v in t2]
        if min(p1) >= max(p2)-EPS or min(p2) >= max(p1)-EPS:
            return False
    return True

# ---- 单元 12 块（红=正三角边长1，绿=30-30-120 等腰腰1底√3） ----
A=(0.0,0.0); B=(2*SQ3,0.0); C=(SQ3,3.0)
J=(SQ3,0.0); H=(SQ3/2,1.5); I=(3*SQ3/2,1.5)
F=(SQ3/2,0.5); G=(3*SQ3/2,0.5); D=(SQ3,1.0); E=(SQ3,2.0)
RED = {'6':(D,F,H),'5':(D,J,F),'4':(D,G,J),'3':(D,I,G),'2':(D,E,I),'1':(D,H,E)}
GRN = {'12':(A,F,H),'11':(A,F,J),'10':(B,G,J),'9':(B,G,I),'8':(C,E,I),'7':(C,H,E)}
LOCAL = list(RED.items()) + list(GRN.items())

def P(i, j): return (2*SQ3*i + SQ3*j, 3.0*j)
def unit_up(i, j):
    p = P(i, j); return [(k, tuple(add(p, v) for v in t)) for k, t in LOCAL]
def unit_down(i, j):
    dx, dy = 2*SQ3*i + SQ3*j + SQ3, 3.0*j + 3.0
    return [(k, tuple((v[0]+dx, dy-v[1]) for v in t)) for k, t in LOCAL]

# ---- 48 块（4 单元拼盘） ----
def build_tiles():
    t = []
    for i in range(2):
        for j in range(2-i):
            t += unit_up(i, j)
            if i+j <= 0:
                t += unit_down(i, j)
    return t

TILES0 = build_tiles()
N = len(TILES0)
print('块数', N)

def edges_of(t): return [tuple(sorted((t[i], t[(i+1) % 3]))) for i in range(3)]
def geom_adj(tiles):
    e = [edges_of(t[1]) for t in tiles]
    adj = defaultdict(set)
    for i in range(N):
        for j in range(i+1, N):
            if set(e[i]) & set(e[j]):
                adj[i].add(j); adj[j].add(i)
    return adj

ADJ0 = geom_adj(TILES0)

def components(idxs, adj):
    seen = set(); comps = []
    for s in idxs:
        if s in seen: continue
        seen.add(s); dq = deque([s]); comp = [s]
        while dq:
            x = dq.popleft()
            for y in adj[x]:
                if y in idxs and y not in seen:
                    seen.add(y); dq.append(y); comp.append(y)
        comps.append(comp)
    return comps

def connected(nodes, adj):
    if not nodes: return True
    s = next(iter(nodes)); seen = {s}; dq = deque([s])
    while dq:
        x = dq.popleft()
        for y in adj[x]:
            if y in nodes and y not in seen:
                seen.add(y); dq.append(y)
    return len(seen) == len(nodes)

# ---- 候选缝（块边延长线，不切块 + 两侧非空） ----
def vside(v, u, off): return cross(u, v) - off
def side_of(t, u, off): return cross(u, centroid(t)) - off

def candidate_seams(tiles):
    lines = {}
    for idx, (_, t) in enumerate(tiles):
        for i in range(3):
            p, q = t[i], t[(i+1) % 3]; d = sub(q, p); L = math.hypot(*d)
            if L < EPS: continue
            u = (d[0]/L, d[1]/L)
            if u[0] < -EPS or (abs(u[0]) < EPS and u[1] < 0):
                u = (-u[0], -u[1])
            off = cross(u, p)
            key = (round(u[0], 9), round(u[1], 9), round(off, 9))
            lines.setdefault(key, {'u': u, 'off': off, 'n': 0})['n'] += 1
    valid = []
    for key, info in lines.items():
        u, off = info['u'], info['off']
        if any(any(vside(v, u, off) > EPS for v in t)
               and any(vside(v, u, off) < -EPS for v in t)
               for _, t in tiles):
            continue  # 线切过某块内部
        if not (any(side_of(t, u, off) > EPS for _, t in tiles)
                and any(side_of(t, u, off) < -EPS for _, t in tiles)):
            continue  # 一侧没块
        valid.append((u, off))
    return valid

SEAMS0 = candidate_seams(TILES0)
print('合法缝线（不切块+两侧非空）', len(SEAMS0))

def fam_step(u):
    ang = round(math.degrees(math.atan2(u[1], u[0]) % 180))
    if abs(ang-30) < 1 or abs(ang-90) < 1 or abs(ang-150) < 1:
        return 1.0          # 晶格缝：一格 = 边长 1
    return SQ3              # 绿底缝：一格 = √3

def translate(tiles, idxs, d):
    out = []
    for i, (k, t) in enumerate(tiles):
        if i in idxs:
            out.append((k, tuple(add(v, d) for v in t)))
        else:
            out.append((k, t))
    return out

def legal_moves(tiles):
    seams = candidate_seams(tiles)
    adj = geom_adj(tiles)
    moves = []
    for u, off in seams:
        step = fam_step(u)
        for sign in (+1, -1):
            side_idx = [i for i in range(N) if side_of(tiles[i][1], u, off)*sign > EPS]
            if not side_idx: continue
            if len(side_idx) == N: continue
            rest = [i for i in range(N) if i not in side_idx]
            # 拆分量（几何连通）
            for comp in components(side_idx, adj):
                if len(comp) == N: continue
                d = (sign*step*u[0], sign*step*u[1])
                mv = set(comp)
                new = translate(tiles, mv, d)
                # 不重叠
                comp_t = {i: new[i][1] for i in comp}
                rest_t = {i: new[i][1] for i in rest}
                ok = True
                for a in comp_t.values():
                    for b in rest_t.values():
                        if tri_overlap(a, b): ok = False; break
                    if not ok: break
                if not ok: continue
                # 连通（几何）
                allnodes = set(range(N))
                if not connected(allnodes, geom_adj(new)): continue
                moves.append((u, off, sign, tuple(sorted(mv))))
    return moves

MV = legal_moves(TILES0)
print('还原态合法移动数（整侧/分量 + 几何连通）:', len(MV))
for e in MV[:8]:
    ang = round(math.degrees(math.atan2(e[0][1], e[0][0]) % 180), 1)
    print('  方向 %5.1f° 步长 %.3f 侧 %+d 选中 %d 块' % (ang, fam_step(e[0]), e[2], len(e[3])))

# ---- 打乱 + 还原验证 ----
def apply_move(tiles, mv):
    u, off, sign, picked = mv
    d = (sign*fam_step(u)*u[0], sign*fam_step(u)*u[1])
    return translate(tiles, set(picked), d)

def board_key(tiles):
    return tuple(sorted((k,) + tuple(round(c, 6) for pt in tri for c in pt)
                        for k, tri in tiles))

def is_solved(tiles):
    return board_key(tiles) == board_key(TILES0)

random.seed(20261023)
cur = TILES0
for _ in range(20):
    mvs = legal_moves(cur)
    if not mvs: break
    cur = apply_move(cur, random.choice(mvs))
print('\n打乱 20 步后：块数', len(cur), '是否还原', is_solved(cur))
# 还原：继续随机滑，看能否回到初始 key（尝试有限步，证明可达性的一例）
hit = False
for _ in range(600):
    if is_solved(cur): hit = True; break
    mvs = legal_moves(cur)
    if not mvs: break
    cur = apply_move(cur, random.choice(mvs))
print('随机滑动后能否回到还原态（一例）:', hit)
print('还原态合法移动非空 → 碎三角双形状可玩:', len(MV) > 0)
