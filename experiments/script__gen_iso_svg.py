# experiments/script__gen_iso_svg.py
"""生成双形状谜题的 SVG 图：①单元 12 块构造 ②四单元拼盘 + 两类缝族。"""
import math
SQ3=math.sqrt(3.0)
A=(0.0,0.0); B=(2*SQ3,0.0); C=(SQ3,3.0)
J=(SQ3,0.0); H=(SQ3/2,1.5); I=(3*SQ3/2,1.5)
F=(SQ3/2,0.5); G=(3*SQ3/2,0.5); D=(SQ3,1.0); E=(SQ3,2.0)
RED={'6':(D,F,H),'5':(D,J,F),'4':(D,G,J),'3':(D,I,G),'2':(D,E,I),'1':(D,H,E)}
GRN={'12':(A,F,H),'11':(A,F,J),'10':(B,G,J),'9':(B,G,I),'8':(C,E,I),'7':(C,H,E)}
LOCAL=list(RED.items())+list(GRN.items())
def P(i,j): return (2*SQ3*i+SQ3*j, 3.0*j)
def unit_up(i,j):
    p=P(i,j); return [(k,tuple((p[0]+v[0],p[1]+v[1]) for v in t)) for k,t in LOCAL]
def unit_down(i,j):
    dx,dy=2*SQ3*i+SQ3*j+SQ3,3.0*j+3.0
    return [(k,tuple((v[0]+dx,dy-v[1]) for v in t)) for k,t in LOCAL]

def esc(s): return s
def poly(t,s,ox,oy):
    pts=' '.join('%.1f,%.1f'%(ox+v[0]*s,oy-v[1]*s) for v in t)
    return pts
def ctr(t,s,ox,oy):
    return (ox+(t[0][0]+t[1][0]+t[2][0])/3.0*s, oy-(t[0][1]+t[1][1]+t[2][1])/3.0*s)

# ---------- 图①：单元 ----------
s1,ox1,oy1=78.0,180.0,320.0
out=['<svg viewBox="0 0 680 400" xmlns="http://www.w3.org/2000/svg" font-family="system-ui,sans-serif">']
out.append('<rect x="0" y="0" width="680" height="400" fill="#fbfbfc"/>')
for k,t in LOCAL:
    fill='#ffd9d6' if k in RED else '#d7ecd9'
    stroke='#b3392e' if k in RED else '#3d7a44'
    out.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1.6"/>'%(poly(t,s1,ox1,oy1),fill,stroke))
    cx,cy=ctr(t,s1,ox1,oy1)
    out.append('<text x="%.1f" y="%.1f" font-size="15" text-anchor="middle" dominant-baseline="middle" fill="#222" font-weight="600">%s</text>'%(cx,cy,k))
pts={'A':A,'B':B,'C':C,'J':J,'H':H,'I':I,'F':F,'G':G,'D':D,'E':E}
off={'A':(-14,10),'B':(12,10),'C':(0,-16),'J':(0,20),'H':(-16,4),'I':(16,4),'F':(-16,4),'G':(16,4),'D':(0,22),'E':(0,-14)}
for nm,p in pts.items():
    x,y=ox1+p[0]*s1,oy1-p[1]*s1
    dx,dy=off[nm]
    out.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="#333"/>'%(x,y))
    out.append('<text x="%.1f" y="%.1f" font-size="13" fill="#333" text-anchor="middle">%s</text>'%(x+dx,y+dy,nm))
out.append('<text x="340" y="384" font-size="13.5" fill="#555" text-anchor="middle">单元（大正三角形边长 2√3）：红 1–6 = 边长 1 正三角形绕中心 D 成六边形；绿 7–12 = 30-30-120 等腰（腰 1、底 √3）居三角</text>')
out.append('</svg>')
open('experiments/_svg_unit.svg','w').write('\n'.join(out))

# ---------- 图②：四单元拼盘 + 缝族 ----------
s2,ox2,oy2=50.0,170.0,352.0
units=[unit_up(0,0),unit_up(1,0),unit_up(0,1),unit_down(0,0)]
out2=['<svg viewBox="0 0 680 420" xmlns="http://www.w3.org/2000/svg" font-family="system-ui,sans-serif">']
out2.append('<rect x="0" y="0" width="680" height="420" fill="#fbfbfc"/>')
for us in units:
    for k,t in us:
        fill='#ffd9d6' if k in RED else '#d7ecd9'
        stroke='#b3392e' if k in RED else '#3d7a44'
        out2.append('<polygon points="%s" fill="%s" stroke="%s" stroke-width="1"/>'%(poly(t,s2,ox2,oy2),fill,stroke))
# 单元边界（虚线）
for us in units:
    for a,b in ((0,1),(1,2),(2,0)):
        p,q=us[0][1][a] if False else None,None
bnds=[(P(0,0),P(1,0)),(P(1,0),P(0,1)),(P(0,1),P(0,0)),(P(0,0),P(2,0)),(P(2,0),P(0,2)),(P(0,2),P(0,0))]
for p,q in bnds:
    out2.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#999" stroke-width="1.4" stroke-dasharray="5 4"/>'%(ox2+p[0]*s2,oy2-p[1]*s2,ox2+q[0]*s2,oy2-q[1]*s2))
# 中轴晶格缝（左下单元内 x=√3, y∈[0,3]）——沿缝剪切
x0=ox2+SQ3*s2
out2.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#1f5fa8" stroke-width="3.2"/>'%(x0,oy2,x0,oy2-3*s2))
for sgn in (1,-1):
    out2.append('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="#1f5fa8"/>'%(x0,oy2-1.5*s2-14*sgn,x0-7,oy2-1.5*s2+2*sgn,x0+7,oy2-1.5*s2+2*sgn))
out2.append('<text x="%.1f" y="%.1f" font-size="13" fill="#1f5fa8" font-weight="600" text-anchor="middle">晶格缝（边长1，步长1）</text>'%(x0,oy2+18))
# 绿底缝（y=3，横贯拼盘）
y0=oy2-3*s2
out2.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#8a6d1f" stroke-width="3.2"/>'%(ox2,y0,ox2+4*SQ3*s2,y0))
for sgn in (1,-1):
    out2.append('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="#8a6d1f"/>'%(ox2+2*SQ3*s2-14*sgn,y0,ox2+2*SQ3*s2+2*sgn,y0-7,ox2+2*SQ3*s2+2*sgn,y0+7))
out2.append('<text x="%.1f" y="%.1f" font-size="13" fill="#8a6d1f" font-weight="600" text-anchor="middle">绿底缝（边长√3，步长√3）</text>'%(ox2+2*SQ3*s2,y0-12))
out2.append('<text x="340" y="404" font-size="13.5" fill="#555" text-anchor="middle">四单元拼盘（大三角形边长 4√3）：48 块；蓝=晶格缝族（30°/90°/150°，间距√3），棕=绿底缝族（0°/60°/120°，间距3），两侧均可沿缝剪切</text>')
out2.append('</svg>')
open('experiments/_svg_board.svg','w').write('\n'.join(out2))
print('written')
