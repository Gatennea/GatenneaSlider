# -*- coding: utf-8 -*-
"""M0 前置：三角形态的 mod 不变量与放置偏移约束（計劃 §4「先寫單測再接入」）。

計劃 §4 要求「mod 約束公式先寫單測（隨機打亂 → 逐步驗證不變量不翻）再接入
過濾，別拍腦袋」。本腳本就是那份單測的前置核對，四件事：

  A  確定三族的方向向量（乾淨地、不靠配對猜）——目標框枚舉要知道每族能往哪走
  B  驗 mod 不變量在**引擎真實滑動**下守恆（這是放置偏移約束的合法性依據）
  C  驗「幾何平移」下不守恆——說明約束必須按 step 網格寫，不能按絕對座標
  D  枚舉 k=2/3/4 的合法放置偏移（平移 × 3 旋轉朝向），看 mod 網格怎麼約束

跑法：D:\\python\\python.exe -u experiments\\_tri_mod_probe.py
"""
import sys
import random
from collections import Counter, defaultdict

sys.path.insert(0, '.')

from game_triangle import TriangleSliderMatrix, GAP_DIRECTIONS
from gui.cell_class import cell_class


def A_direction_vectors():
    print('=' * 70)
    print('A  三族的方向向量（用「整組剛體平移」判定，不用猜）')
    print('=' * 70)
    # 引擎的 try_move_ex 返回的是「選中側每塊的新位置」，把選中側與新位置
    # 做配對最穩的方式：對每個朝向分組後比對集合的「重心位移」。
    for step in (1, 2, 3):
        g = TriangleSliderMatrix(4)
        g.shuffle(12, step)
        found = defaultdict(Counter)
        for _ in range(400):
            gaps = g.all_gaps()
            if not gaps:
                break
            fam, line = random.choice(gaps)
            for d in GAP_DIRECTIONS[fam]:
                g._clear_selection()
                g.opt(fam, line, random.choice(g.blocks))
                sel = [b for b in g.blocks if b.be_opted]
                if not sel:
                    continue
                old = [tuple(b.location) for b in sel]
                pos, _ = g.try_move_ex(d, step)
                if not pos:
                    continue
                new = [tuple(p) for p in pos]
                # 整組剛體平移 ⇒ 新舊集合的「坐標和之差」一致
                do = (sum(p[0] for p in old), sum(p[1] for p in old))
                dn = (sum(p[0] for p in new), sum(p[1] for p in new))
                n = len(old)
                found[(fam, d)][((dn[0] - do[0]) / n,
                                 (dn[1] - do[1]) / n)] += 1
                g.commit_move(pos)
                g.update_matrix()
        print(f'\n  step={step}:')
        for k in sorted(found):
            top = found[k].most_common(1)[0]
            print(f'    族{k[0]:2s} 方向{k[1]!r}: 最常見 delta = {top[0]}'
                  f'（{top[1]} 次，另有 {len(found[k])-1} 種噪聲）')
    print('\n  → 乾淨結論（從噪聲裡取整數倍的那個）：')
    print('    h 族沿 ±e_i（(±1,0)）   p 族沿 ±e_j（(0,±1)）   n 族沿 ±(e_i−e_j)')


def B_mod_conserved_by_engine():
    print('\n' + '=' * 70)
    print('B  mod 不變量在「引擎真實滑動」下守恆嗎？（放置約束的合法性依據）')
    print('=' * 70)

    random.seed(3)
    for k in (2, 3, 4, 5):
        for step in (1, 2, 3):
            if step > k:
                continue
            g = TriangleSliderMatrix(k)
            g.shuffle(15, step)
            before = Counter(
                cell_class((b.location[0], b.location[1]), step, 'triangle')
                + (b.location[2],) for b in g.blocks)
            bad = tot = 0
            for _ in range(200):
                gaps = g.all_gaps()
                if not gaps:
                    break
                fam, line = random.choice(gaps)
                g.opt(fam, line, random.choice(g.blocks))
                d = random.choice(GAP_DIRECTIONS[fam])
                pos, _ = g.try_move_ex(d, step)
                if not pos:
                    continue
                g.commit_move(pos)
                g.update_matrix()
                after = Counter(
                    cell_class((b.location[0], b.location[1]), step, 'triangle')
                    + (b.location[2],) for b in g.blocks)
                tot += 1
                if after != before:
                    bad += 1
                before = after
            print(f'  k={k} step={step}: 走 {tot:3d} 步，類計數變化 {bad} 次')


def C_not_conserved_by_geometry():
    print('\n' + '=' * 70)
    print('C  「幾何平移」下不守恆 —— 所以約束必須按 mod 網格寫')
    print('=' * 70)
    for k in (3, 4):
        s = set(TriangleSliderMatrix(k).positions())
        for step in (2, 3):
            if step > k:
                continue
            c1 = Counter(cell_class((i, j), step, 'triangle')
                         for (i, j, _u) in s)
            rows = []
            for di, dj in ((1, 0), (0, 1), (1, 1), (2, 0), (0, 2), (1, -1)):
                sh = {(i + di, j + dj, u) for (i, j, u) in s}
                c2 = Counter(cell_class((i, j), step, 'triangle')
                             for (i, j, _u) in sh)
                rows.append(f'({"+"}{di},{"+"}{dj})'
                            f'{"同" if c1 == c2 else "異"}')
            print(f'  k={k} step={step}: 還原態 vs 各自平移 → '
                  + '  '.join(rows))
    print('\n  → step 倍數的平移保持類計數；非 step 倍數的會翻。')
    print('    這正是「放置偏移受 mod 網格約束」的來源：合法放置偏移必須是')
    print('    step 的倍數，而目標框枚舉要把其餘偏移排除。')


def D_legal_offsets(k=3, step=2):
    print('\n' + '=' * 70)
    print(f'D  枚舉 k={k} step={step} 的合法放置偏移（平移 × 3 旋轉朝向）')
    print('=' * 70)
    goal = set(TriangleSliderMatrix(k).positions())
    # 3 個旋轉朝向：120° 輪換在斜座標下的線性變換。先量出來：
    # 試 (di,dj) ∈ {-1,0,1}² × 恆等，看哪些把 goal 映到自身。
    rots = []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            rot = {(i + di, j + dj, u) for (i, j, u) in goal}
            if rot == goal:
                rots.append((di, dj))
    print(f'  把 goal 映到自身的平移（= 對稱平移）：{rots}')
    print('  → 這就是 k 邊長大三角的平移對稱群；旋轉 120° 要另外推。')

    # 直接用引擎滑動來取「旋轉後的大三角」：k=2 時滑一格能得到什麼形狀
    g = TriangleSliderMatrix(k)
    shapes = set()
    base = set(g.positions())
    shapes.add(frozenset(base))

    random.seed(7)
    for _ in range(600):
        gg = TriangleSliderMatrix(k)
        for _s in range(random.randint(1, 12)):
            gaps = gg.all_gaps()
            if not gaps:
                break
            fam, line = random.choice(gaps)
            gg.opt(fam, line, random.choice(gg.blocks))
            d = random.choice(GAP_DIRECTIONS[fam])
            pos, _ = gg.try_move_ex(d, step)
            if pos:
                gg.commit_move(pos)
                gg.update_matrix()
        shapes.add(frozenset(gg.positions()))
    print(f'\n  隨機走出的不同塊數集合：{sorted({len(s) for s in shapes})}')
    cnt = Counter(len(s) for s in shapes)
    print(f'  塊數分佈：{dict(sorted(cnt.items()))}')
    print(f'  還原態塊數 k²={k*k}，出現 {cnt.get(k*k, 0)} 次')


def main():

    random.seed(3)
    print('三角形态 mod 不变量前置核对（計劃 §4）')
    A_direction_vectors()
    B_mod_conserved_by_engine()
    C_not_conserved_by_geometry()
    D_legal_offsets()
    print('\n' + '=' * 70)
    print('結論：B/C 合起來 = 放置偏移必須是 step 倍數，可直接用 mod 網格過濾。')
    print('D 的旋轉朝向還沒量出來，那是 M0 目標框的下一個待辦。')


if __name__ == '__main__':
    main()
