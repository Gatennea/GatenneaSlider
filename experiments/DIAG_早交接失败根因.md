# 诊断：`guided_replay_bad` 到底是哪一类问题

> ⚠️ 历史快照：记录当时的结论与数据，非现状。求解器现状以《求解器設計.md》为准，本文档用于追根因/复盘。

- 诊断脚本：`experiments/exp16_diag.py`（新建，一次性，不改动 `solver/`）
- 原始日志：`experiments/results/exp16_diag.log`
- 样本：4×4 step2，seed 1001/1008/1012 × cap 15/8（6 局），外加 cap=None 基线 2 局
- 解释器：`D:/python/python.exe`

---

## 一、一句话判定

**既不是 (a) 重放/编码错位，也不是 (b) 搜索产出的 path 不可执行 —— 是第三类 (c)：实验脚手架把 `replay_steps()` 的返回值当成了"重放是否成功"，而它返回的其实是"是否已还原"。**
段3 每一轮 `guided_reduce_one` 只保证**至少填一个洞**，不保证一次还原；早交接让残留洞数变多（2~3 个），于是第一轮合法走完却没还原，被 exp12 判成 `guided_replay_bad` 并直接 `return None`。path 本身每一步都合法、与搜索内部推进**逐位完全一致**。

---

## 二、证据链

### 证据 1：`replay_steps` 的布尔值语义是 `is_solved()`

`experiments/exp9_rep.py:16-26`

```python
def replay_steps(snap, steps):
    g = H.load_game(snap)
    for action, rep in steps:
        if rep is None:
            ok = H.apply_action(g, action, snap['step'])
        else:
            ok = _apply_with_rep(g, action, snap['step'], rep)
        if not ok:
            return False, g          # ← 只有"某一步非法"才返回 False
    return g.is_solved(), g          # ← 否则返回的是"是否已还原"，不是"重放成功"
```

两个语义被压进同一个 bool：`False` = **「有非法步」或「合法走完但没还原」**。

### 证据 2：exp12 用它当"重放是否成功"，于是第一轮就误杀

`experiments/exp12_chain.py:69-76`

```python
path, used = guided_reduce_one(H.coords_of(g), snap['m'], snap['n'], step)
if path is None:
    return None, f'guided_stuck_nodes{used}'
ok, g = replay_steps(snap, steps + path)
if not ok:
    return None, 'guided_replay_bad'   # ← ok 是 is_solved()，多洞局面必然 False
steps += path
```

`guided_reduce_one`（`experiments/exp11_guided.py:76-107`）的终止条件只是
`len(fast_window(cur)[1]) < h0`（洞数比起点少），**不是洞数=0**。所以只要交接时残留 ≥2 个洞，第 1 轮合法走完后 `ok=False` → 立即判失败，后面的 11 轮守卫根本没机会跑。

### 证据 3：实测——每一步都合法，与搜索内部推进零分叉

`exp16_diag` 关键日志（seed 1001 / cap=15，第 1 轮）：

```
  段3 第1轮：洞数=2 搜索出 13 步 (nodes=79 0.8s)
    重放(带rep) 全部步合法=True；重放(忽略rep) 合法=True；搜索内部推进 通
    与搜索序列首个分叉点：带rep=None 忽略rep=None（None=完全一致）
    结果：洞数 2→1 已还原=False
    >>> 【关键】全部步合法但未还原 ⇒ exp12 在此判为 guided_replay_bad（误判点）
  段3 第2轮：洞数=1 搜索出 9 步 (nodes=1130 11.4s)
    ...
    结果：洞数 1→0 已还原=True
  段3 结束：轮数=3 总步=42 还原=True (27s)
```

"首个分叉点 = None" 是本次诊断的核心判据：
把「搜索内部用 `expand()` 推进的局面序列」与「重放路径用 `_apply_with_rep` 推进的局面序列」逐位比对，**每一位都相同，不存在分叉点**。按任务书给的判据（分叉点存在 ⇒ (a)；第一位就不同 ⇒ (b)），**两者都不成立**。

6 局（3 seed × cap 15/8）全部同构：

| seed | cap | 第1轮 洞数 | path 步数 | 全部步合法 | 与搜索分叉点 | 第1轮后已还原 |
|---|---|---|---|---|---|---|
| 1001 | 15 | 2 | 13 | True | None | False |
| 1008 | 15 | 2 | 12 | True | None | False |
| 1012 | 15 | 1 | 8 | True | None | **True** |
| 1001 | 8 | 3 | 5 | True | None | False |
| 1008 | 8 | 2 | 12 | True | None | False |
| 1012 | 8 | 2 | 12 | True | None | False |

**6/6 没有任何一局出现真正的非法步**；唯一"第1轮就还原"的 1012/cap15 恰好就是 exp12 里少数没被误杀的样本——这正好解释了为什么 exp14 的成功率是"崩到 20~40%"而不是 0%。

### 证据 4：原始 exp12 复现，确实打这个标签

```
seed 1001 cap 15 -> guided_replay_bad | steps 0
seed 1001 cap  8 -> guided_replay_bad | steps 0
seed 1008 cap 15 -> guided_replay_bad | steps 0
seed 1008 cap  8 -> guided_replay_bad | steps 0
```

### 证据 5：把判据改对后，6/6 全部解出

同一批样本、只把"是否全部步合法"与"是否已还原"分开判断（不碰 `solver/`）：

```
cap=  15 seed1001 guided  42步 倍数=6.0x
cap=  15 seed1008 guided  39步 倍数=7.8x
cap=  15 seed1012 guided  33步 倍数=4.7x
cap=   8 seed1001 guided  36步 倍数=5.1x
cap=   8 seed1008 guided  29步 倍数=5.8x
cap=   8 seed1012 guided  34步 倍数=4.9x
```

即：**早交接本身是有效的**（4.7x~7.8x，基线是 17.2x），所谓"成功率崩塌"是测量误差。

### 证据 6：为什么基线（cap=None）100% 不受影响

```
seed=1001 cap=None   段1 后：洞数=0 score=1.000 solved=True
seed=1008 cap=None   段1 后：洞数=0 score=1.000 solved=True
```

cap=None 时段1 完整聚拢**直接还原**，根本不进入段3，误判无处触发。这也解释了 exp14 里 `cap=None` 一栏永远是 100%。

### 证据 7（顺带解释 exp15 的 0/5）

`experiments/exp15_repchain.py:77-102` 有两处同样的误用，且第二处放大了危害：

```python
ok, g_tent = replay_steps(snap, steps + fsteps)
if ok:                       # ← 这里 ok 是"填洞后已还原"，几乎永假
    ...  if after >= before: steps += fsteps   # ← 段2 成果被整段丢弃
...
ok, g = replay_steps(snap, steps + path)
if not ok:
    return None, 'guided_replay_bad'          # ← 同 exp12
```

段2 的采纳被 `is_solved()` 门控后基本永不采纳 → 进段3 的局面更乱 → 残留洞更多 → 第1轮必不还原 → 0/5。
**所以 exp15 "比不补更差"不是因为 rep 补错了，而是同一个判据 bug 在段2 又踩了一次。**（与"rep 歧义 bug 已被排除"的结论一致。）

---

## 三、影响面

| 组件 | 是否受影响 | 说明 |
|---|---|---|
| `experiments/exp12_chain.py` | **是（根因所在）** | 段3 判据误用；段2 的 `_okb`/`_ok` 也被忽略（潜在静默截断） |
| `experiments/exp14_truncate.py` | **是（继承）** | 直接调 `exp12_chain.solve`，成功率/倍数结论全部失真 |
| `experiments/exp15_repchain.py` | **是（继承+放大）** | 段2 采纳被 `is_solved()` 门控，导致 0/5 |
| `experiments/exp13_compress.py` | 否 | 只在**最终**用 `replay_steps(...)[0]`，此时"未还原"就该算失败，语义正确 |
| `solver/hybrid_solver.py`（生产） | **否** | 自带 `replay()`（第 63-70 行）只在**步失败**时返回 `None`；`g.is_solved()` 单独判断（第 109-113 行），两段语义天然分离 |
| `solver/search_core.py` / `exp11_guided.py` | 否 | `guided_reduce_one` 语义正确（"至少填一个洞"），是调用方理解错了 |
| table / fill_macro | 否 | 与该标签无因果关系；fill_macro 自身的"多洞停机"是另一类独立缺陷（日志中可见，非本次根因） |

### 附带发现（真实但**不是**本次根因，属潜在风险）

重放时**故意丢弃 rep、一律走 `apply_action`**（恒取 `side_blocks[0]`）在 6 局中有 4 局出现与搜索序列分叉或直接非法：

```
seed1001 cap15 第2轮：重放(忽略rep) 合法=False；与搜索序列首个分叉点：忽略rep=6
seed1008 cap 8 第2轮：重放(忽略rep) 合法=False；与搜索序列首个分叉点：忽略rep=6
seed1012 cap 8 第1轮：重放(忽略rep) 合法=False
```

即 `apply_action` 的多分量歧义**确实存在**，只是 exp12/生产链在段3 都携带了搜索给的 `rep`（`expand()` 返回的 `next(iter(comp))`），所以被正确规避。**结论：`rep` 不能丢**；这条也说明 exp15 的方向（补 rep）没错，只是被判据 bug 掩盖了效果。

段1 则相反：6 局中"带 rep / 不带 rep"两条重放轨迹**完全一致**（`两条路径轨迹一致=True`），说明在这批样本上段1 无歧义，补 rep 是无效功。

---

## 四、建议的最小修复方案（只写方案，未改动任何代码）

**方案 A（推荐，改实验脚手架，约 10 行）**

1. 在 `experiments/exp9_rep.py` 新增语义单一的函数：
   `def apply_all(snap, steps) -> (applied: bool, game, fail_index)`——逐步执行，任一步非法立即返回 `(False, g, i)`；正常走完返回 `(True, g, None)`。**不再把 `is_solved()` 混进返回值。**
2. `exp12_chain.solve` 段3 改为：
   ```python
   applied, g, _ = apply_all(snap, steps + path)
   if not applied:
       return None, 'guided_replay_bad'   # 真正的重放失败
   steps += path
   if g.is_solved():
       return steps, 'guided'
   ```
   （循环末尾的 `g.is_solved()` 已经是正确判据，保留。）
3. 同改段1/段2 的两处 `_ok` 忽略（`exp12_chain.py:38,51,58`），失败即报错而不是静默截断。
4. `exp15_repchain.py:77` 的 `if ok:` 改成 `if applied:`，否则段2 成果永远进不了链。

**方案 B（更彻底，防复发）**
把 `replay_steps` 的返回值改成三元组 `(applied, solved, game)`，或重命名为 `replay_and_check()` 并加 docstring 警示"返回的 bool 是 is_solved()，不是重放成功"。凡是需要中间态的地方一律用 `apply_all`。

**不需要动的**：`solver/` 下任何文件（生产 `hybrid_solver.py` 已经是对的）。

**修完后的预期**：cap=8/15 的成功率回到 ~100%，倍数维持 4.7x~7.8x——即"早交接"这条优化路线**可以落地**，exp14 的"成功率崩塌"结论应当作废并重跑。

---

## 五、复现命令

```bash
D:/python/python.exe -m experiments.exp16_diag --seeds 1001,1008,1012 --caps 15,8 --opt
D:/python/python.exe -m experiments.exp16_diag --seeds 1001,1008 --caps none   # 基线对照
```
