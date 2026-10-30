# -*- coding: utf-8 -*-
"""把本地盤面存檔渲染成一份自包含 HTML 畫廊（每個用例一張棋盘圖）。

不依賴任何外部圖片/字體/CDN，直接瀏覽器打開即可看「每個測試用例長什麼樣」。
用法：
    from render_gallery import build
    build(iter_disk_paths(), 'experiments/disks_gallery.html')
"""
import os

THEME = '#4696c8'          # 網站主色，填滿的方塊
GAP_FILL = '#f3f4f6'       # 空位（缺口/孔洞）底色
GRID = 24                  # 每格像素
PAD = 10


def _bbox(blocks):
    rs = [r for r, _ in blocks]
    cs = [c for _, c in blocks]
    return min(rs), max(rs), min(cs), max(cs)


def _svg_for(rec):
    blocks = [tuple(b) for b in rec['blocks']]
    m, n = rec['m'], rec['n']
    minr, maxr, minc, maxc = _bbox(blocks)
    rows = maxr - minr + 1
    cols = maxc - minc + 1
    occ = set(blocks)
    w = cols * GRID + 2 * PAD
    h = rows * GRID + 2 * PAD
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
             f'style="background:#fff;border:1px solid #e2e8f0;border-radius:6px">']
    for r in range(minr, maxr + 1):
        for c in range(minc, maxc + 1):
            x = PAD + (c - minc) * GRID
            y = PAD + (r - minr) * GRID
            if (r, c) in occ:
                parts.append(f'<rect x="{x}" y="{y}" width="{GRID-1}" height="{GRID-1}" '
                             f'rx="3" fill="{THEME}"/>')
            else:
                parts.append(f'<rect x="{x}" y="{y}" width="{GRID-1}" height="{GRID-1}" '
                             f'rx="3" fill="{GAP_FILL}" stroke="#d1d5db" stroke-dasharray="2 2"/>')
    parts.append('</svg>')
    # 元數據
    nblocks = len(occ)
    bbox_area = rows * cols
    ngaps = bbox_area - nblocks
    caption = (f"{m}×{n} · step{rec['step']} · seed{rec['dseed']}<br>"
               f"方塊 {nblocks} · 空位 {ngaps} · 包圍盒 {rows}×{cols}")
    return ''.join(parts), caption


def build(disk_paths, out_html):
    cards = []
    for p in disk_paths:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                rec = __import__('json').load(f)
        except Exception as e:
            cards.append(f'<div class="card"><div class="bad">讀取失敗: {e}</div></div>')
            continue
        svg, caption = _svg_for(rec)
        name = os.path.basename(p)
        cards.append(
            f'<div class="card"><div class="name">{name}</div>{svg}'
            f'<div class="cap">{caption}</div></div>'
        )
    html = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Gatennea Slider · 盤面存檔畫廊</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f8fafc; color: #1f2937; }}
  h1 {{ font-size: 18px; padding: 16px 20px 0; margin: 0; }}
  .sub {{ padding: 4px 20px 12px; color: #64748b; font-size: 13px; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 14px; padding: 0 20px 30px; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
          padding: 10px; width: 180px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
  .name {{ font-size: 11px; color: #94a3b8; word-break: break-all; margin-bottom: 6px; }}
  .cap {{ font-size: 12px; color: #475569; margin-top: 6px; line-height: 1.5; }}
  .bad {{ color: #dc2626; font-size: 12px; }}
  .legend {{ padding: 0 20px 16px; font-size: 12px; color: #64748b; }}
  .legend span {{ display: inline-block; width: 12px; height: 12px;
                 border-radius: 3px; vertical-align: -2px; margin: 0 4px 0 12px; }}
</style>
</head>
<body>
<h1>Gatennea Slider · 盤面存檔畫廊</h1>
<div class="sub">每張圖 = 一個測試用例「打亂後的第一幀」。藍格=方塊，虛線格=空位（缺口/孔洞）。</div>
<div class="legend"><span style="background:{THEME}"></span>方塊<span style="background:{GAP_FILL};border:1px solid #d1d5db"></span>空位</div>
<div class="grid">
{''.join(cards)}
</div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_html
