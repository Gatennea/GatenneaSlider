# experiments/script__chk_iso_puzzle.py
"""双形状谜题几何验证 v2（修正 SAT 触面误报 + 单元拼盘公式 + 大区域构造）。
构造（大三角形边长 L=2*√3，小正三角形边长 x=1）：
  A(0,0) B(2√3,0) C(√3,3)；J=底边中点；H、I=左/右边中点；
  F(√3/2,1/2)、G(3√3/2,1/2) 内部点；D=中心(√3,1)；E=(√3,2) 内部。
  红=正三角形(边长1)绕 D；绿=30-30-120 等腰(腰1 底√3)居三角。
  单元格点 p(i,j)=(2√3·i+√3·j, 3j)；▲(i,j)=平移模板；▼(i,j)=(x,y)->(x+dx, 3j+3-y)。
"""
import math, itertools
from collections import defaultdict
SQ3 = math.sqrt(3.0); EPS = 1e-9

def sub(a,b): return (a[0]-b[0], a[1]-b[1])
def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def add(a,b): return (a[0]+b[0], a[1]+b[1])
def centroid(t): return ((t[0][0]+t[1][0]+t[2][0])/3.0,(t[0][1]+t[1][1]+t[2][1])/3.0)
def edgelen(t,i): return math.hypot(*sub(t[(i+1)%3],t[i]))
def area(t): return abs(cross(sub(t[1],t[0]),sub(t[2],t[0])))/2.0
def side_of(t,u,off): return cross(u,centroid(t))-off
def vside(v,u,off): return cross(u,v)-off
def in_tri(p,t,eps=EPS):
    ds=[cross(sub(t[(i+1)%3],t[i]),sub(p,t[i])) for i in range(3)]
    return all(d>=-eps for d in ds) or all(d<=eps for d in ds)

def tri_overlap(t1,t2):
    """SAT：True=内部相交（面积>0）。共享边/顶点不算——投影相切即分离。"""
    axes=[]
    for tri in (t1,t2):
        for i in range(3):
            e=sub(tri[(i+1)%3],tri[i]); axes.append((e[1],-e[0]))
    for ax in axes:
        p1=[dot(v,ax) for v in t1]; p2=[dot(v,ax) for v in t2]
        if min(p1)>=max(p2)-EPS or min(p2)>=max(p1)-EPS: return False
    return True

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

def check_tiling(tiles,label,board=None):
    bad=[(n1,n2) for (n1,t1),(n2,t2) in itertools.combinations(tiles,2) if tri_overlap(t1,t2)]
    s=sum(area(t) for _,t in tiles)
    msg='%s: %d 块, 内部重叠 %d, 面积和 %.6f'%(label,len(tiles),len(bad),s)
    if board is not None:
        s2=area(board); msg+=' (盘面 %.6f, %s)'%(s2,'OK' if abs(s-s2)<1e-6 else 'MISMATCH')
        out=[n for n,t in tiles if not all(in_tri(v,board) for v in t)]
        msg+=', 越界 %s'%(out if out else '无')
    print(msg)
    for b in bad[:8]: print('   OVERLAP',b)
    return len(bad)==0

# ---------- ① 单元 ----------
u1=unit_up(0,0)
ok1=check_tiling(u1,'单元',board=(A,B,C))
for k,t in u1:
    ls=sorted(edgelen(t,i) for i in range(3))
    if k in RED:
        assert abs(ls[0]-1)<EPS and abs(ls[2]-1)<EPS, ('红块应为正三角形',k,ls)
    else:
        assert abs(ls[0]-1)<EPS and abs(ls[1]-1)<EPS and abs(ls[2]-SQ3)<EPS, ('绿块应为腰1底√3',k,ls)
print('形状断言 OK：红=边长1正三角形；绿=腰1、底√3 的 30-30-120 等腰')

# ---------- ② 四单元拼盘（大三角形：4 个单位） ----------
t4=[]
for i in range(2):
    for j in range(2-i):
        t4+=unit_up(i,j)
        if i+j<=0: t4+=unit_down(i,j)   # 中心倒三角只有 (0,0)
board4=(P(0,0),P(2,0),P(0,2))
ok2=check_tiling(t4,'四单元',board=board4)

# ---------- ③ 大区域：边长 6 个单位的大三角形 ----------
R=6
big=[]
for i in range(R):
    for j in range(R-i):
        big+=unit_up(i,j)
        if i+j<R-1: big+=unit_down(i,j)
print('大区域块数',len(big))

# 候选缝线=块边的延长线
lines={}
for n,t in big:
    for i2 in range(3):
        p,q=t[i2],t[(i2+1)%3]
        d=sub(q,p); Ln=math.hypot(*d)
        if Ln<EPS: continue
        u=(d[0]/Ln,d[1]/Ln)
        if u[0]<-EPS or (abs(u[0])<EPS and u[1]<0): u=(-u[0],-u[1])
        off=cross(u,p)
        key=(round(u[0],9),round(u[1],9),round(off,9))
        e=lines.setdefault(key,{'u':u,'off':off,'elen':Ln,'n':0}); e['n']+=1
print('候选直线数',len(lines))

def shear_steps(tiles,u,off,step,sgn,maxsteps=4):
    mv=[(n,t) for n,t in tiles if side_of(t,u,off)*sgn>EPS]
    fx=[(n,t) for n,t in tiles if side_of(t,u,off)*sgn<=EPS]
    if not mv or not fx: return 0
    k=0
    while k<maxsteps:
        k+=1
        d=(sgn*k*step*u[0], sgn*k*step*u[1])
        moved=[(n,tuple(add(v,d) for v in t)) for n,t in mv]
        if any(tri_overlap(t1,t2) for (n1,t1) in moved for (n2,t2) in fx): return k-1
    return k

valid=[]
for key,info in lines.items():
    u,off,elen=info['u'],info['off'],info['elen']
    if any(any(vside(v,u,off)>EPS for v in t) and any(vside(v,u,off)<-EPS for v in t) for _,t in big):
        continue  # 线切过某块内部
    if not (any(side_of(t,u,off)>EPS for _,t in big) and any(side_of(t,u,off)<-EPS for _,t in big)):
        continue  # 一侧没块
    valid.append((u,off,elen))
print('合法缝线数',len(valid))

stat=defaultdict(lambda:[0,0,0,set()])
for u,off,elen in valid:
    r1=shear_steps(big,u,off,elen,+1)
    r2=shear_steps(big,u,off,elen,-1)
    ang=round(math.degrees(math.atan2(u[1],u[0]))%180)
    key=(ang,round(elen,6))
    stat[key][0]+=1
    stat[key][1]+= (1 if r1>=1 else 0)
    stat[key][2]+= (1 if r2>=1 else 0)
    stat[key][3].add(round(off,6))
print('\n按(方向°,边长)汇总：合法缝线数 / +侧可剪 / -侧可剪 / 不同偏移数')
for key in sorted(stat):
    c,p,m,offs=stat[key]
    print('  方向 %3d° 边长 %.3f : 缝 %3d 条, +侧可剪 %3d, -侧可剪 %3d, 偏移 %d 种 %s'%(
        key[0],key[1],c,p,m,len(offs),sorted(offs)[:8]))

# 细看：过单元中心 D 的三条中轴线缝
print('\n过单元中心 D 的缝线细查（step=边长）：')
for ang in (90.0,30.0,150.0,0.0):
    u=(math.cos(math.radians(ang)),math.sin(math.radians(ang)))
    off=cross(u,D)
    if any(any(vside(v,u,off)>EPS for v in t) and any(vside(v,u,off)<-EPS for v in t) for _,t in big):
        print('  %3.0f°: 非法（切块）'%ang); continue
    el=1.0 if ang in (30.0,90.0,150.0) else SQ3
    r1=shear_steps(big,u,off,el,+1); r2=shear_steps(big,u,off,el,-1)
    print('  %3.0f°: +侧 %d 步, -侧 %d 步'%(ang,r1,r2))

# 具体演试：中轴缝 x=√3（过 J-D-E-C），右侧下移一步，点名落点
print('\n演试：中轴缝 x=√3，右側沿缝下移 1 步——落点命名：')
u=(0.0,1.0); off=cross(u,J)
mv=[(n,t) for n,t in big if side_of(t,u,off)>EPS]
names={}
for n,t in u1: names[tuple(sorted(t))]=n
d=(0.0,-1.0)
for n,t in mv[:40]:
    mt=tuple(add(v,d) for v in t)
    key=tuple(sorted(mt))
    if key in names and abs(mt[0][0]-SQ3)<1e-6:
        print('   右塊 %-3s -> 原 %s 位'%(n,names[key]))
