# experiments/script__gen_a_explain.py
"""碎三角「方案 A」对比图：左=原画两种形状；右=A 统一等边三角形+红绿着色。"""
import math
SQ3=math.sqrt(3.0)
# 左面板：原画单元（两种形状）
A=(0.0,0.0); B=(2*SQ3,0.0); C=(SQ3,3.0)
J=(SQ3,0.0); H=(SQ3/2,1.5); I=(3*SQ3/2,1.5)
F=(SQ3/2,0.5); G=(3*SQ3/2,0.5); D=(SQ3,1.0); E=(SQ3,2.0)
RED={'6':(D,F,H),'5':(D,J,F),'4':(D,G,J),'3':(D,I,G),'2':(D,E,I),'1':(D,H,E)}
GRN={'12':(A,F,H),'11':(A,F,J),'10':(B,G,J),'9':(B,G,I),'8':(C,E,I),'7':(C,H,E)}
LOCAL=list(RED.items())+list(GRN.items())

s,ox,oy=78.0,150.0,330.0
def poly(t): return ' '.join('%.1f,%.1f'%(ox+v[0]*s,oy-v[1]*s) for v in t)
def ctr(t): return (ox+(t[0][0]+t[1][0]+t[2][0])/3*s, oy-(t[0][1]+t[1][1]+t[2][1])/3*s)

out=['<svg viewBox="0 0 680 430" xmlns="http://www.w3.org/2000/svg" font-family="system-ui,sans-serif" role="img">']
out.append('<title>碎三角方案A对比</title><desc>左=原画两种形状，右=统一等边三角形+红绿着色</desc>')

# ---- 左面板 ----
for k,t in LOCAL:
    fill='#ffd9d6' if k in RED else '#d7ecd9'
    stroke='#b3392e' if k in RED else '#3d7a44'
    out.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.6"/>'%(poly(t),fill,stroke))
    cx,cy=ctr(t)
    out.append('<text x="%.1f" y="%.1f" font-size="14" text-anchor="middle" dominant-baseline="middle" fill="#222" font-weight="500">%s</text>'%(cx,cy,k))
out.append('<text x="170" y="30" font-size="15" fill="#b3392e" text-anchor="middle" font-weight="500">左：你原画（两种形状）</text>')
out.append('<text x="170" y="408" font-size="12.5" fill="#666" text-anchor="middle">红=边长1正三角形，绿=30-30-120等腰</text>')
out.append('<text x="170" y="424" font-size="12.5" fill="#b3392e" text-anchor="middle">红绿形状不同 → 推一格后落不到合法格（按现有滑动机制）</text>')

# ---- 右面板：A = 同大小等边三角形 + 红绿着色 ----
# 大等边三角形，边长=4 个小三角边长，三角晶格细分
rox,roy=470.0,330.0; rs=78.0/4.0*1.0*1.0  # 小三角边长屏幕值
# 用大三角边长 4 单位；屏幕 scale 让整体与左面板相当
ts=78.0*3.0/4.0  # 大三角边长屏幕 ~ 与左相当
N=4
def TP(i,j):
    # 三角晶格点：i 向右，j 向上（行）
    return (rox + (i + j/2.0)*ts/4.0*4.0*0.0 + (i + j/2.0)*(ts/ N), roy - j*(ts/N)*SQ3/2.0)
# 直接用坐标：大三角底宽 = N 单位
def tp(i,j):
    x = rox + (i + j/2.0)*(ts/N)
    y = roy - j*(ts/N)*SQ3/2.0
    return (x,y)
# 小三角（边长 = ts/N），上三角顶点 (i,j),(i+1,j),(i,j+1)；下三角 (i+1,j),(i,j+1),(i+1,j+1)
# 颜色：按 (i+j) 奇偶，红绿交替，保留「碎」观感
def tri_up(i,j): return (tp(i,j),tp(i+1,j),tp(i,j+1))
def tri_dn(i,j): return (tp(i+1,j),tp(i,j+1),tp(i+1,j+1))
def fillpoly(t,fill,stroke='#7a7a7a'):
    pts=' '.join('%.1f,%.1f'%(p[0],p[1]) for p in t)
    return '<polygon points="%s" fill="%s" stroke="%s" stroke-width="1"/>'%(pts,fill,stroke)
cnt=0
for j in range(N):
    for i in range(N-j):
        col='#ffd9d6' if (i+j)%2==0 else '#d7ecd9'
        out.append(fillpoly(tri_up(i,j),col))
        cnt+=1
        if j<N-1 and i<N-j-1:
            col2='#d7ecd9' if (i+j)%2==0 else '#ffd9d6'
            out.append(fillpoly(tri_dn(i,j),col2))
            cnt+=1
# 大三角轮廓
big=(tp(0,0),tp(N,0),tp(0,N))
out.append('<polygon points="%s" fill="none" stroke="#333" stroke-width="2.4"/>'%(' '.join('%.1f,%.1f'%p for p in big)))
# 一条缝 + 滑动箭头：j=2 行那条横缝，箭头表示推一格
seam_y = roy - 2*(ts/N)*SQ3/2.0
out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2b6cb0" stroke-width="2" stroke-dasharray="5 4"/>'%(tp(0,2)[0],seam_y, tp(N-0,2)[0],seam_y))
ax=rox+ts*0.55; ay=seam_y
out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2b6cb0" stroke-width="2.4" marker-end="url(#ar)"/>'%(ax,ay-14,ax+34,ay-14))
out.append('<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#2b6cb0"/></marker></defs>')
out.append('<text x="490" y="30" font-size="15" fill="#3d7a44" text-anchor="middle" font-weight="500">右：方案 A（统一等边三角形）</text>')
out.append('<text x="490" y="408" font-size="12.5" fill="#666" text-anchor="middle">每块都是同样大小的等边三角形，只是 6 红 / 6 绿涂色</text>')
out.append('<text x="490" y="424" font-size="12.5" fill="#3d7a44" text-anchor="middle">推一格正好落下一个三角格 → 能滑（现有引擎直接支持）</text>')

out.append('</svg>')
open('experiments/_svg_a_explain.svg','w').write('\n'.join(out))
print('written, small triangles count region =', cnt, 'N=',N)
