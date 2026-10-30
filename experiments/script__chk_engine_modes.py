"""几何引擎下的两种特殊玩法冒烟：编号谜题 / 自由捆绑。

GUI 接入后玩家随手就能开这两种局，引擎层跑不通就是实打实的体验缺口。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import engine.config as ecfg  # noqa: E402
import puzzle_types  # noqa: E402

_fails = []


def check(cond, msg):
    print(("  ok: " if cond else "  FAIL: ") + msg)
    if not cond:
        _fails.append(msg)


# ---------------------------------------------------------------- 编号谜题
print("== 编号谜题 ==")
for enabled in (False, True):
    ecfg.set_enabled(enabled)
    g = puzzle_types.create_puzzle(3, 3, 1, 'numbered')
    nums = list(range(1, len(g.blocks) + 1))
    for b, v in zip(g.blocks, nums):
        b.number = v
    g.update_matrix()
    tag = '引擎' if enabled else '经典'
    check(g.is_solved(), f"{tag} 还原态 is_solved")
    g.shuffle(8, 1, bias=0.0, min_score=0.7)
    check(not g.is_solved(), f"{tag} 打乱后非还原")
    # 编号必须跟着块走（撤销重做 / 存档全靠它）
    got = sorted(getattr(b, 'number', None) for b in g.blocks)
    check(got == sorted(nums), f"{tag} 打乱后编号集合不变 {got[:5]}…")
    # 矩阵语义：编号即值
    g.update_matrix()
    vals = sorted(v for row in g.matrix for v in row if v)
    check(vals == sorted(nums), f"{tag} 矩阵值=编号 {vals[:5]}…")
    # 走一步，编号仍跟着走
    g.opt('h', 0, g.blocks[0])
    fin = g.try_move('a', 1)
    if fin:
        g.commit_move(fin)
        got2 = sorted(getattr(b, 'number', None) for b in g.blocks)
        check(got2 == sorted(nums), f"{tag} 走一步后编号集合不变")
ecfg.set_enabled(False)

# ---------------------------------------------------------------- 自由捆绑
print("\n== 自由捆绑（刚体组）==")
for enabled in (False, True):
    ecfg.set_enabled(enabled)
    g = puzzle_types.create_puzzle(4, 4, 1, 'square')
    tag = '引擎' if enabled else '经典'
    # 把不同行的两块捆成一组：(0,0) 与 (1,1)
    g.blocks[0].group = 1
    g.blocks[5].group = 1
    if hasattr(g, 'set_groups_from_positions'):
        g.set_groups_from_positions({tuple(g.blocks[0].location): 1,
                                     tuple(g.blocks[5].location): 1})
    else:
        g.update_matrix()
    grps = sorted({getattr(b, 'group', 0) for b in g.blocks})
    check(1 in grps, f"{tag} 组号写回 {grps}")
    # 选中 (0,0) 所在行（h:0 = 第 1 行，4 块）→ 刚体语义应把 (1,1) 也拖进来 = 5 块
    g.opt('h', 0, g.blocks[0])
    sel = [b for b in g.blocks if b.be_opted]
    check(len(sel) == 5, f"{tag} opt 刚体拖入跨行组成员（{len(sel)} 块，应为 5）")
    # 打乱仍可用（is_single_connected 要传位置集合，两边同签名）
    g.shuffle(6, 1, bias=0.0, min_score=0.7)
    cells = {tuple(b.location) for b in g.blocks}
    check(g.is_single_connected(cells), f"{tag} 带组打乱后仍单一连通")
    check(len(g.blocks) == 16, f"{tag} 打乱不丢块（{len(g.blocks)}）")
ecfg.set_enabled(False)

print()
if _fails:
    print(f"失败 {len(_fails)} 项：")
    for f in _fails:
        print("  -", f)
    sys.exit(1)
print("全部通過")
