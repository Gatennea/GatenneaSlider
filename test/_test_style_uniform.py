"""畫風統一：四種形態都是「圓角塊 + 均勻灰縫」，盤內不得露出背景色。

**為什麼要這條測試**：2026-10-24 用戶指出「米字/矩形/數字是一種風格，三角和
碎三角是另一種」。拆下來是三處差異：
  1. 圓角口徑——舊實現統一「削進深度」，同樣 2px 削進下 90° 角弧半徑 4.8px、
     60° 只有 2px、45° 只有 1.2px，角越尖越尖；方形以弧半徑 5px 為準。
  2. 縫——方形/三角/米字都有 gap_width 的縫，碎三角塊貼邊、完全無縫。
  3. 描邊——碎三角 4px 亮灰（100），方形 2px（100）配 60px 塊。

修完之後最容易回歸的是「盤內露背景」：塊內縮半個縫寬 + 削圓角後，若縫帶底
沒鋪夠，頂點交會處就會露出背景色 (30,30,30)——比縫色 (80,80,80) 暗得多，
遠看是每個頂點的「梅花黑點」。純靠肉眼在 4 倍放大圖裡找，遲早漏。

本檔案用**像素**判定：把四種形態各渲染一幀，取所有塊多邊形的凸包（內縮
3px 避開抗鋸齒邊），凸包內除塊色/縫色/描邊色/提示色以外的像素必須少於
閾值。既抓住黑點，也抓住「塊被削太狠以致縫帶斷開」。

**兩種縫的畫法（2026-10-25 起，`seam_style`）**：
  - `fill`（方形/三角/米字，用戶認可的既有畫風）：縫帶**填滿** gap 灰，
    故盤內不得露出背景色——露了就是頂點黑點。
  - `line`（碎三角等模型板型）：用戶改的畫風——「沒有滑塊的地方別全部填充
    灰色，灰色按理來說只是縫隙畫線」。縫帶**露出背景**，灰色只沿格子真實
    邊界畫一條細線（＝縫延長構成的晶格）。此處露出背景是**故意**的，
    所以判據要反過來：每個內部頂點附近必須能採到那條晶格線（gap 色），
    抓的是「晶格線沒畫到頂點 / 縫帶塌掉」這類回歸。
"""

import os
import queue
import sys

import pygame

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_FAILS = []


def check(cond, msg, detail=''):
    if cond:
        print(f'  ok   {msg}')
    else:
        print(f'  FAIL {msg}' + (f'  [{detail}]' if detail else ''))
        _FAILS.append(msg)


def _gui():
    from GUI import SliderGUI
    g = SliderGUI(m=6, n=6, step=2, cmd_queue=queue.Queue(),
                  ext_state={'enabled': True, 'token': 'T', 'port': 5050})
    g.tut_show_prompt = False
    g.tutorial_active = False
    g.animation_enabled = False
    g.selected_gap = None
    g.selected_block = None
    return g


def _convex_hull(points):
    """Andrew monotone chain（順時針返回）。"""
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _block_polys(g):
    """當前局面所有塊的螢幕多邊形（走各形態自己的視圖，與繪製同源）。"""
    from game_mi import mi_key as _mi_key
    from game_triangle import tri_key as _tri_key
    out = []
    if g._is_model_kind() or g._polygon_view() is not None:
        view = g._polygon_view()
        origin = g._poly_view_origin(view)
        for block in g.game.blocks:
            key = g._visual_key(block)
            point, orient = g._poly_key_parts(key)
            out.append([g.world_to_screen(x, y) for (x, y)
                        in view.world_polygon(point, orient, origin)])
    elif g.triangle_mode:
        # 用**未內縮**的精確形狀：內縮後相鄰塊頂點各退各的，量不到共享頂點
        view = g._tri_view()
        for block in g.game.blocks:
            i, j, up = _tri_key(block)
            out.append([g.world_to_screen(*p)
                        for p in view.piece_polygon(i, j, up, inset=False)])
    elif g.mi_mode:
        view = g._mi_view()
        for block in g.game.blocks:
            r, c, q = _mi_key(block)
            out.append([g.world_to_screen(*p)
                        for p in view.piece_polygon(r, c, q, inset=False)])
    else:
        cell, _gap, step = g._board_px()
        for block in g.game.blocks:
            r, c = block.location[0], block.location[1]
            x = int(c * step + g.camera_x)
            y = int(r * step + g.camera_y)
            out.append([(x, y), (x + cell, y), (x + cell, y + cell), (x, y + cell)])
    return out


def _interior_vertices(polys):
    """盤內部頂點：各塊在該點的内角和 ≈ 360°。

    不能用「被 ≥3 塊共享」代替——碎三角的盤是三角形拼出來的鋸齒輪廓，
    邊界上的凹角照樣被多塊共享，那裡露出背景是**盤外**、不是黑洞。
    """
    import math
    from collections import defaultdict

    ang = defaultdict(float)
    for poly in polys:
        n = len(poly)
        for k in range(n):
            cur = (int(round(poly[k][0])), int(round(poly[k][1])))
            prev, nxt = poly[k - 1], poly[(k + 1) % n]
            ax, ay = prev[0] - poly[k][0], prev[1] - poly[k][1]
            bx, by = nxt[0] - poly[k][0], nxt[1] - poly[k][1]
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            if la < 1e-9 or lb < 1e-9:
                continue
            cs = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
            ang[cur] += math.acos(cs)
    return {k for k, a in ang.items() if a >= 2.0 * math.pi - 0.08}


def _audit(tag, setup, expect_interior=True, seam_style='fill'):
    """渲染一幀，在**盤內部頂點**周圍檢查縫的畫法對不對。

    seam_style='fill' → 檢查「不露背景色」；'line' → 檢查「採得到晶格線」。
    兩種畫法下要抓的回歸不同，見檔案開頭說明。

    為什麼不看「凸包內背景像素佔比」：方形盤最外圈的圓角本來就露背景色
    （那是方形既有畫風，用戶也認可），佔比 0.48% 會被誤判。真正要抓的是
    「內部頂點交會處的梅花黑點」——塊內縮 + 削圓角後若縫帶底沒鋪夠，那裡
    露出的背景 (30) 比縫色 (80) 暗得多。
    """
    g = _gui()
    setup(g)
    g.draw_board()

    polys = _block_polys(g)
    check(bool(polys), f'{tag}：拿到塊多邊形（{len(polys)} 塊）')

    bg = tuple(g.colors['background'])
    gap = tuple(g.colors['gap'])

    if expect_interior:
        inner_v = _interior_vertices(polys)
        check(bool(inner_v), f'{tag}：存在盤內部頂點（{len(inner_v)} 個）')
        if seam_style == 'line':
            # 縫帶露出背景是**故意**的；要抓的是晶格線沒畫到頂點。
            missing = []
            for (x, y) in inner_v:
                hit = False
                for dy in range(-5, 6):
                    for dx in range(-5, 6):
                        px, py = x + dx, y + dy
                        if not (0 <= px < g.screen_width
                                and 0 <= py < g.screen_height):
                            continue
                        if tuple(g.screen.get_at((px, py))[:3]) == gap:
                            hit = True
                            break
                    if hit:
                        break
                if not hit:
                    missing.append((x, y))
            check(not missing,
                  f'{tag}：內部頂點附近採得到晶格線（{len(inner_v)} 個頂點，'
                  f'{len(missing)} 個採不到）',
                  str(missing[:3]))
        else:
            holes = []
            for (x, y) in inner_v:
                for dy in range(-5, 6):
                    hit = False
                    for dx in range(-5, 6):
                        px, py = x + dx, y + dy
                        if not (0 <= px < g.screen_width
                                and 0 <= py < g.screen_height):
                            continue
                        if tuple(g.screen.get_at((px, py))[:3]) == bg:
                            holes.append((x, y))
                            hit = True
                            break
                    if hit:
                        break
            check(not holes,
                  f'{tag}：內部頂點不露背景色（{len(inner_v)} 個頂點，'
                  f'{len(holes)} 個有黑洞）',
                  str(holes[:3]))
    else:
        # 方形棋盤的塊之間隔著 gap，頂點本來就不重合；它沒有這種黑洞風險，
        # 只作為「縫帶存在」的對照組
        print(f'  --   {tag}：方形棋盤無共享頂點，跳過頂點檢查（對照組）')

    # 有縫：盤面中部必須能採到縫色（否則塊貼死、不是同一套畫風）
    xs = [int(round(p[0])) for poly in polys for p in poly]
    ys = [int(round(p[1])) for poly in polys for p in poly]
    n_gap = 0
    for y in range(min(ys), max(ys), 3):
        for x in range(min(xs), max(xs), 3):
            if tuple(g.screen.get_at((x, y))[:3]) == gap:
                n_gap += 1
    check(n_gap > 200, f'{tag}：盤面能看到縫帶（gap 色採樣 {n_gap} 點）')
    return g


def hull_left(hull):
    return max(0, int(min(p[0] for p in hull)))


def hull_right(hull):
    return int(max(p[0] for p in hull))


def hull_top(hull):
    return max(0, int(min(p[1] for p in hull)))


def hull_bottom(hull):
    return int(max(p[1] for p in hull))


def test_four_forms_same_style():
    print('\n== U1 四形態：盤內不露背景 + 都有縫 ==')
    _audit('矩形', lambda g: g.new_puzzle(6, 6, 2), expect_interior=False)
    _audit('數字', lambda g: g.new_puzzle(6, 6, 2, numbered=True),
           expect_interior=False)
    # 米字/三角自 2026-10-25 起也改成 line：縫帶不再整片鋪灰（移除舊 _seal），
    # 灰色只沿縫畫線；頂點交會處露出背景是**故意**的（用戶拍板「就這樣」）——
    # 曾在頂點補灰圓「節點」被用戶判畫蛇添足，已刪，勿再加回。
    _audit('米字', lambda g: g.new_mi_puzzle(4, 4, 2), seam_style='line')
    _audit('三角', lambda g: g.new_triangle_puzzle(6, 2), seam_style='line')
    _audit('碎三角', lambda g: g.new_shatter_puzzle(1), seam_style='line')


def test_corner_radius_proportional():
    """圓角半徑必須隨塊尺寸走（固定像素會把碎三角的小塊削穿）。"""
    print('\n== U2 圓角半徑按塊最短邊比例 ==')
    g = _gui()
    sq = [(0, 0), (60, 0), (60, 60), (0, 60)]
    tri = [(0, 0), (91, 0), (45.5, 79)]        # 邊長 91/91/91
    tiny = [(0, 0), (30, 0), (0, 30)]          # 碎三角的小塊量級
    r_sq = g._corner_radius_for(sq, 99)
    r_tri = g._corner_radius_for(tri, 99)
    r_tiny = g._corner_radius_for(tiny, 99)
    print(f'  方形邊 60 -> r={r_sq:.1f}；三角邊 91 -> r={r_tri:.1f}；'
          f'小塊邊 30 -> r={r_tiny:.1f}')
    check(abs(r_sq - 60 * 0.083) < 0.01, '方形邊 60px 對應 r≈5（8.3%）')
    check(r_tri > r_tiny * 1.5, '大塊的圓角半徑明顯大於小塊（按比例，不是固定值）')
    check(r_tiny >= 1.5, '小塊仍有可見圓角（不為 0）')
    check(g._corner_radius_for(sq, 3) <= 3, 'cap 生效（不會超過傳入上限）')


def test_border_width_proportional():
    print('\n== U3 描邊寬度按塊最短邊比例 ==')
    g = _gui()
    sq = [(0, 0), (60, 0), (60, 60), (0, 60)]
    tiny = [(0, 0), (30, 0), (0, 30)]
    w_sq = g._border_width_for(sq, 2)
    w_tiny = g._border_width_for(tiny, 2)
    print(f'  方形邊 60 -> w={w_sq}；小塊邊 30 -> w={w_tiny}')
    check(w_sq == 2, '方形 60px 塊仍是 2px 邊（與舊觀感一致）')
    check(w_tiny == 1, '小塊自動降到 1px（避免每條邊比縫還搶眼）')


def main():
    test_four_forms_same_style()
    test_corner_radius_proportional()
    test_border_width_proportional()
    print()
    if _FAILS:
        print(f'失敗 {len(_FAILS)} 項：')
        for m in _FAILS:
            print('  -', m)
        sys.exit(1)
    print('全部通過')


if __name__ == '__main__':
    main()
