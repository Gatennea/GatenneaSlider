# -*- coding: utf-8 -*-
"""移動不變量類：三形態共用的「這塊滑塊永遠出不去的位置集合」。

一次合法移動把整組滑塊平移同一個向量 v，而 v 是該形態方向生成元的
``step`` 倍。於是在 v 上取值不變的量，就是「這塊滑塊永遠出不去」的標記：

    形態     位置身份          類（不含朝向）              類（含朝向）
    方形     (r, c)            (r%step, c%step)            同左
    三角     (i, j, up)        (i%step, j%step)            + up
    米字     (r, c, q)         ((r+c)%step, (r-c)%step)    + q

米字不能用方形的 ``r%step``：斜向一步只走 (±½, ±½)×step，單一坐標的餘數
會變；不變的是 ``r+c`` 與 ``r−c``（生成元 (0,±step)、(±step,0)、
(±step/2,±step/2) 在兩者上都是 step 的整數倍）。錯位態下 ``r%step`` 會在
0 與 0.5 之間翻，``r±c`` 卻恆為整數，就是這個道理。

類（不含朝向）與「這塊真的能到哪」的關係，要看 step 的奇偶：
    step 偶數：斜向 step 格的位移 ±(step/2, step/2) 仍是整數，晶格
        （r、c 同為整數 / 同為半整數）是不變量；而 A 晶格的 ``r+c`` 與
        ``r−c`` 同奇偶、B 晶格異奇偶，類匹配自動就排除了另一晶格。
        類數只有一半：兩個餘數不能自由組合。
    step 奇數：斜向 step 格的位移是半整數，**一步就把整盤換到另一晶格**
        （實測 step=3：(0,0) 斜走 3 格 ⇒ (−1.5,−1.5)，類不變），所以同一
        類橫跨 A/B 兩個晶格；過濾晶格會把可達集合砍掉一半。
兩者的通式是「同類 ⇔ (r'+c')−(r+c) 與 (r'−c')−(r−c) 都是 step 的倍數」，
它與真實軌道 {(step/2·p, step/2·q) : p≡q (mod 2)} 完全等價。

朝向（三角的 up、米字的 q）在平移下不變，所以它也是不變量的一部分。
著色只用位置類（顏色數與方形同量級），連鎖用類含朝向（「這塊能去哪」
不含朝向就會指到別的朝向的位置，是假提示）——這個落差是刻意的。
"""

# 形態鍵：'square' / 'triangle' / 'mi'
__all__ = ['cell_class', 'class_index']


def cell_class(pos, step, kind='square'):
    """位置 → 不變量類（不含朝向）。

    pos：方形 (r, c)、三角 (i, j, up)、米字 (r, c, q)；米字的 r/c 可為
        半整數（錯位態 B 晶格），故內部一律整數化後再取模。
    step：等級。``step == 1`` 時位置類退化成朝向分組：方形只剩一組
        （全盤同類、沒有資訊，著色與連鎖都要關掉），**三角剩 up 兩組、
        米字剩 q 四組**——這兩個形態「原本就靠朝向分組」，1 級一步一格時
        一塊能去的恰是同朝向的任意位置，連鎖閘門不能關（著色不含朝向、
        1 級仍是單色，照舊關閉）。
    """
    step = max(1, int(step))
    if kind == 'triangle':
        return (int(pos[0]) % step, int(pos[1]) % step)
    if kind == 'mi':
        # ×2 整數化：(r+c) 與 (r−c) 恆為整數，×2 後是偶數，折半不失真
        s = round((pos[0] + pos[1]) * 2)
        d = round((pos[0] - pos[1]) * 2)
        return ((s // 2) % step, (d // 2) % step)
    return (int(pos[0]) % step, int(pos[1]) % step)


def class_index(key, step):
    """類 → 穩定整數索引（著色的色相輸入）。

    同一類在同一 step 下永遠得到同一個索引，跨形態也不衝突：把各分量
    乘上 step 的冪次求和，再做一次 mod 收斂到 [0, step*step)。
    """
    step = max(1, int(step))
    idx = 0
    for k in key:
        idx = idx * step + int(k)
    return idx % (step * step)
