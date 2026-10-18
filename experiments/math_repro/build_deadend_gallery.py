# -*- coding: utf-8 -*-
"""生成官网图解页 ⑤「死局」段：真实死局棋盘画廊 + 口径澄清。

死局口径（用户拍板）：打乱能踩到（在 cone 内），但回不到还原态（不在 B 内）= cone\\B。
对照概念：一步都动不了（出度 0 的 sink）——全图 52 个，但绝大多数打乱走不到。
"""
import json, os, re, sys

ROOT = r"E:\program_project\other\wkbddtest\GatenneaSlider"
WEB = r"E:\program_project\other\wkbddtest\GatenneaSliderWeb"
HERE = os.path.join(ROOT, "experiments", "math_repro")

C_TEXT = "#e6e6e6"
C_DIM = "#8a8a8a"
C_FAINT = "#5f5f68"
C_BLUE = "#3c96c8"
C_RED = "#ff5a4a"
C_REDT = "#ff8a7e"
C_AMBER = "#e8b04b"

data = json.load(open(os.path.join(HERE, "deadend_coneB.json"), encoding="utf-8"))
items2 = data["4x4x2"]
items3 = data["4x4x3"]
assert len(items2) == 9 and len(items3) == 6


def board_svg(x, y, grid, csz=20, gap=2):
    """grid: list[str]，'#' 为有块。返回 (svg片段, 宽, 高)"""
    h = len(grid)
    w = max(len(r) for r in grid)
    out = []
    for r in range(h):
        for c in range(w):
            if c < len(grid[r]) and grid[r][c] == "#":
                out.append(
                    f'<rect x="{x + c * (csz + gap):.1f}" y="{y + r * (csz + gap):.1f}" '
                    f'width="{csz}" height="{csz}" rx="3" fill="{C_BLUE}"/>'
                )
    bw = w * csz + (w - 1) * gap
    bh = h * csz + (h - 1) * gap
    return "".join(out), bw, bh


def gallery(items, title, subtitle):
    """两行画廊：第一行 5 个，第二行 4 个；统一槽位，棋盘在槽内居中"""
    rows = [items[:5], items[5:]]
    csz, gap = 20, 2
    slot_w = 86                     # 4 列棋盘宽
    colgap = 44
    y = 60
    bh = 4 * csz + 3 * gap          # 86
    out = [f'<div class="diag">', f'<svg viewBox="0 0 680 404" role="img" aria-label="{title}">']
    out.append(f'<text x="20" y="27" font-size="13.5" fill="{C_TEXT}">{title}</text>')
    out.append(f'<text x="20" y="45" font-size="10.5" fill="{C_DIM}">{subtitle}</text>')
    for row in rows:
        if not row:
            continue
        total = len(row) * slot_w + (len(row) - 1) * colgap
        x = (680 - total) / 2
        for it in row:
            bw = len(it["grid"][0]) * csz + (len(it["grid"][0]) - 1) * gap
            bx = x + (slot_w - bw) / 2
            g, bw2, bh2 = board_svg(bx, y, it["grid"], csz, gap)
            out.append(g)
            stuck = it["outdeg"] == 0
            col = C_RED if stuck else C_AMBER
            out.append(
                f'<rect x="{bx - 4:.1f}" y="{y - 4:.1f}" width="{bw2 + 8:.1f}" height="{bh2 + 8:.1f}" rx="5" '
                f'fill="none" stroke="{col}" stroke-width="1.4"/>'
            )
            label = "一步都动不了" if stuck else f"还能走 {it['outdeg']} 步"
            out.append(
                f'<text x="{x + slot_w / 2:.1f}" y="{y + bh + 18:.1f}" text-anchor="middle" '
                f'font-size="9.5" fill="{C_REDT if stuck else C_AMBER}">{label}</text>'
            )
            out.append(
                f'<text x="{x + slot_w / 2:.1f}" y="{y + bh + 32:.1f}" text-anchor="middle" '
                f'font-size="9" fill="{C_FAINT}">{it["h"]}×{it["w"]}</text>'
            )
            x += slot_w + colgap
        y += bh + 62
    # 图例
    ly = 364
    out.append(f'<rect x="20" y="{ly - 9}" width="11" height="11" rx="2" fill="none" stroke="{C_RED}" stroke-width="1.4"/>')
    out.append(f'<text x="37" y="{ly}" font-size="10.5" fill="{C_DIM}">红框＝已经一步都动不了（彻底卡死）</text>')
    out.append(f'<rect x="330" y="{ly - 9}" width="11" height="11" rx="2" fill="none" stroke="{C_AMBER}" stroke-width="1.4"/>')
    out.append(f'<text x="347" y="{ly}" font-size="10.5" fill="{C_DIM}">黄框＝还能动，但只能在小圈里打转</text>')
    out.append(f'<text x="20" y="{ly + 20}" font-size="10" fill="{C_FAINT}">尺寸标注是这个局面的边界盒（能框住它的最小矩形）</text>')
    out.append("</svg></div>")
    return "\n".join(out)


n_stuck2 = sum(1 for it in items2 if it["outdeg"] == 0)
n_stuck3 = sum(1 for it in items3 if it["outdeg"] == 0)

g2 = gallery(items2, "4×4 二级的全部 9 个死局：打乱能踩到，踩进去就回不去",
             "全部来自完整枚举的真实局面，不是示意图；格子＝滑块，框内数字是边界盒尺寸")

html = f"""      <!-- 5. 死局：打乱能踩到但回不去 -->
      <div class="card">
        <h2>⑤ 死局：打乱能踩到，却再也回不去</h2>
        <p>
          从还原态出发一路打乱，能走到的局面有 558,286 个；其中绝大多数还能再走回还原态。
          真正麻烦的是这么一类：<strong>打乱的时候踩得到，但一旦踩进去，就再也回不来了</strong>——这就是我们说的<strong>死局</strong>。
        </p>
        <p>
          4×4 二级里这样的死局一共只有 <strong style="color:{C_REDT};">9</strong> 个（三级有 <strong style="color:{C_REDT};">6</strong> 个）。它们长这样：
        </p>
        {g2}
        <p class="cap">上面 9 个就是 4×4 二级的全部死局，一个不多一个不少。</p>
        <p>
          这 9 个里，<strong>{n_stuck2} 个已经一步都动不了</strong>（彻底卡死）；另外 <strong>{9 - n_stuck2} 个其实还能动</strong>——
          每个都还有 2 条合法走法，但不管怎么走，都只是在一个小圈里打转，永远绕不回还原态。
          三级的 6 个同理：{n_stuck3} 个卡死、{6 - n_stuck3} 个还能走 1 步。
        </p>
        <p>「一步都动不了」在游戏里是这个样子——不管选哪条缝、选哪一片，推就撞、推就断：</p>
        <img class="shot" src="images/dead_collage.png" alt="拼接在一起的若干真实游戏画面，每一个都已经一步都动不了" />
        <p class="cap">真实游戏画面：若干个一步都动不了的局面拼在一起。</p>
        <p class="note">
          顺带澄清一个特别容易混的概念：整个状态图里「一步都动不了」的点其实有 <strong>52</strong> 个（三级 <strong>327</strong> 个），
          比 9 多得多。<strong>但它们绝大多数打乱根本走不到</strong>——不在从还原态出发能到的范围里，玩家一辈子也碰不上。
          这 52 个里，真正会被玩家踩到的只有上面红框那 {n_stuck2} 个。所以「一步都动不了」和「死局」是两回事，别混着数。
        </p>
      </div>

"""

# ---- 写回官网页面 ----
page = os.path.join(WEB, "math_graph.html")
lines = open(page, encoding="utf-8").read().split("\n")
i = next(k for k, l in enumerate(lines) if "<!-- 5. 死局" in l)
j = next(k for k, l in enumerate(lines) if "<!-- 6. 结论" in l)
new = lines[:i] + html.rstrip("\n").split("\n") + [""] + lines[j:]
open(page, "w", encoding="utf-8", newline="\n").write("\n".join(new))
print("[ok] ⑤ 死局段已替换：%d 行 -> %d 行（旧 %d 行）" % (len(html.split("\n")), j - i, j - i))
print("     4x4x2 死局 9 个（卡死 %d / 还能动 %d），4x4x3 死局 6 个（卡死 %d / 还能动 %d）"
      % (n_stuck2, 9 - n_stuck2, n_stuck3, 6 - n_stuck3))
