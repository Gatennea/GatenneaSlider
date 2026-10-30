# experiments/script__chk_shatter_adjacency.py
"""决定性实验：碎三角 48 块盘面的边邻接图，是否是「正则三角晶格」
（单一固定偏移表）？若是 → 直接复用 tri preset；若否 → 引擎需泛化邻接。
"""
import math, itertools
from collections import defaultdict, Counter
SQ3 = math.sqrt(3.0); EPS = 1e-9

def sub(a,b): return (a[0]-b[0], a[1]-b[1])
def add(a,b): return (a[0]+b[0], a[1]+b[1])
A=(0.0,0.0); B=(2*SQ3,0.0); C=(SQ3,3.0)
J=(SQ3,0.0); H=(SQ3/2,1.5); I=(3*SQ3/2,1.5)
F=(SQ3/2,0.5); G=(3*SQ3/2,0.5); D=(SQ3,1.0); E=(SQ3,2.0)
RED={'6':(D,F,H),'5':(D,J,F),'4':(D,G,J),'3':(D,I,G),'2':(D,E,I),'1':(D,H,E)}
GRN={'12':(A,F,H),'11':(A,F,J),'10':(B,G,J),'9':(B,G,I),'8':(C,E,I),'7':(C,H,E)}
LOCAL=list(RED.items())+list(GRN.items())
def P(i,j): return (2*SQ3*i+SQ3*j, 3.0*j)
def unit_up(i,j):
    p=P(i,j); return [(k,tuple(add(p,v) for v in t)) for k,t in LOCAL]
def unit_down(i,j):
    dx,dy=2*SQ3*i+SQ3*j+SQ3, 3.0*j+3.0
    return [(k,tuple((v[0]+dx, dy-v[1]) for v in t)) for k,t in LOCAL]

# 48 块 = 4 单元（与 _chk_iso_puzzle ② 同构）
t4=[]
for i in range(2):
    for j in range(2-i):
        t4+=unit_up(i,j)
        if i+j<=0: t4+=unit_down(i,j)

# 给每块唯一 id + 形状 + 顶点集合
blocks=[]
for idx,(k,t) in enumerate(t4):
    shape = 'R' if k in RED else 'G'
    verts = frozenset((round(v[0],9), round(v[1],9)) for v in t)
    blocks.append({'id':idx,'role':k,'shape':shape,'verts':verts,
                   'centroid':((t[0][0]+t[1][0]+t[2][0])/3,(t[0][1]+t[1][1]+t[2][1])/3)})

# 边邻接：两块的顶点集合交 2 个 → 共享一条边
def edge_adjacent(b1,b2):
    return len(b1['verts'] & b2['verts']) == 2

adj=defaultdict(list)
for b1,b2 in itertools.combinations(blocks,2):
    if edge_adjacent(b1,b2):
        adj[b1['id']].append(b2['id']); adj[b2['id']].append(b1['id'])

deg=Counter(len(adj[b['id']]) for b in blocks)
print('度分布（邻接块数）:', dict(sorted(deg.items())))
print('总边数:', sum(deg.values())//2)

# 形状 × 度
shape_deg=defaultdict(Counter)
for b in blocks:
    shape_deg[b['shape']][len(adj[b['id']])]+=1
print('红块 度分布:', dict(shape_deg['R']))
print('绿块 度分布:', dict(shape_deg['G']))

# 关键：内部块（度=3）的「邻居形状组成」是否一致？
# 红内部块邻居 = ? ; 绿内部块邻居 = ?
red_int=Counter(); grn_int=Counter()
for b in blocks:
    if len(adj[b['id']])==3:
        nbr_shapes=tuple(sorted(blocks[n]['shape'] for n in adj[b['id']]))
        if b['shape']=='R': red_int[nbr_shapes]+=1
        else: grn_int[nbr_shapes]+=1
print('红内部块(度3) 邻居形状组成:', dict(red_int))
print('绿内部块(度3) 邻居形状组成:', dict(grn_int))

# 邻居「角色差」签名：每块记 (Δrole 排序)，看是否全同
sig=Counter()
for b in blocks:
    nbrs=sorted(blocks[n]['role'] for n in adj[b['id']])
    sig[(b['shape'], len(nbrs), tuple(nbrs))]+=1
print('\n不同邻接签名数:', len(sig))
for k,v in sorted(sig.items()):
    print('  shape=%s deg=%d 邻居角色%s ×%d'%(k[0],k[1],k[2],v))

# 正则性结论判据：若存在 >=2 种「度3 且邻居形状组成不同」的内部块 → 非正则晶格
distinct_int = set(red_int) | set(grn_int)
print('\n内部块邻居形状组成种类数:', len(distinct_int), distinct_int)
print('==> 正则三角晶格可复用?' , len(distinct_int)<=1 and all(d==3 for d in deg))
