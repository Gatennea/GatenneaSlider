# -*- coding: utf-8 -*-
"""回归：存档必须保存「捆绑组」的刚性约束（不只是 occupancy 矩阵）

修复前：快照只落盘 matrix/bounds，恢复端虽然有能力
（`set_groups_from_positions`），但序列化端没写 groups 字段 →
载入时 `snapshot.get('groups')` 为 None → 整盘静默拆成散块。
表现：形状完全正确（块数一致），但 2×2 捆绑块变成 4 颗各走各的，
谜题被悄悄变简单，求解/成绩/死局统计全部不可比。

覆盖：
- G1 普通存档：写→读，捆绑组一致
- G2 压缩存档（replay）：写→读，捆绑组一致（且确认真的走了压缩路径）
- G3 载入后撤销：捆绑随状态一起回退
- G4 旧存档（无 groups 字段）仍可载入，行为 = 全散块（向后兼容）
- G5 无捆绑局不写 groups 字段（文件体积/格式不变）
- G6 无捆绑局的状态哈希与旧算法一致（旧压缩档不会误报校验失败）
- G7 落盘形式是 JSON 安全的 [[r,c,gid],...]（tuple key 会让 json 炸）
- G8 坏 groups 数据被 validate_snapshot 拒绝
"""
import json
import os
import queue
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui.compressed_save import _state_hash, decompress_to_normal  # noqa: E402
from gui.file_ops import _compute_checksum  # noqa: E402
from history import (validate_snapshot, groups_to_json,  # noqa: E402
                     groups_from_json)

_failures = []


def check(name, cond, detail=''):
    if cond:
        print(f'[PASS] {name} {detail}')
    else:
        print(f'[FAIL] {name} {detail}')
        _failures.append(name)


CELLS = [(r, c) for r in range(3) for c in range(3)]
BANDED = {(r, c): 1 for r in (0, 1) for c in (0, 1)}   # 左上 2×2 成一组


def first_legal_move(game):
    """在捆绑盘面上找一个合法移动（扫缝×方向）。返回 move_info 或 None。"""
    for gt in ('h', 'v'):
        for line in range(2):
            for d in ('w', 'a', 's', 'd'):
                blk = None
                for b in game.blocks:
                    r, c = b.location[0], b.location[1]
                    if gt == 'h' and r <= line:
                        blk = b
                        break
                    if gt == 'v' and c <= line:
                        blk = b
                        break
                if blk is None:
                    continue
                try:
                    game.opt(gt, line, blk)
                except Exception:
                    continue
                moved = [tuple(b.location) for b in game.blocks if b.be_opted]
                final, _reason = game.try_move_ex(d, 1)
                if final:
                    game.commit_move(final)
                    game.update_matrix()
                    return {'gap_type': gt, 'gap_line': line, 'direction': d,
                            'step': 1,
                            'moved_positions': [list(p) for p in moved]}
    return None


def build_bandaged(gui, compress):
    """搭一局「3×3 + 左上 2×2 捆绑」并走一步；返回 (载入前组, 参考态位置)。"""
    gui.use_compressed_save = compress
    gui.tut_show_prompt = False
    gui.tutorial_active = False
    gui.new_puzzle(4, 4, 1)
    g = gui.game
    g.apply_pattern(CELLS, BANDED)
    gui.current_m, gui.current_n = g.m, g.n
    gui.game_history.reset()
    gui.game_history.save_snapshot(g)                 # 参考态（带捆绑）
    home = sorted(g.groups_summary())
    mv = first_legal_move(g)
    if mv:
        gui.game_history.save_snapshot(g, mv, session_key='S1')
    return sorted(g.groups_summary()), home


gui = SliderGUI(m=4, n=4, step=1, cmd_queue=queue.Queue(),
                ext_state={'enabled': True, 'token': 'T', 'port': 5050})

# ---------------------------------------------------------------- G1 普通存档
print('--- G1 普通存档往返保留捆绑组 ---')
before, home = build_bandaged(gui, compress=False)
check('G1a 盘面确实有 1 个 4 格捆绑组',
      len(before) == 1 and len(before[0][1]) == 4, f'{before}')
data = gui._build_save_data()
check('G1b 走的是普通存档格式', data.get('format') is None)
text = json.dumps(data, ensure_ascii=False)   # tuple key 会在这里炸
check('G1c 落盘 JSON 每条快照都带 groups',
      all('groups' in s for s in data['history']['snapshots']))
check('G1d groups 是 JSON 安全三元组 [[r,c,gid],...]',
      isinstance(data['history']['snapshots'][-1]['groups'], list)
      and all(len(t) == 3 for t in data['history']['snapshots'][-1]['groups']),
      f"{data['history']['snapshots'][-1]['groups']}")
gui._load_save_data(json.loads(text))
after = sorted(gui.game.groups_summary())
check('G1e 载入后捆绑组完全一致', after == before, f'{after} vs {before}')
check('G1f 载入后块数/步数不变',
      len(gui.game.blocks) == 9 and gui.step_count == 1,
      f'{len(gui.game.blocks)} 块 / {gui.step_count} 步')

# ---------------------------------------------------------------- G2 压缩存档
print('\n--- G2 压缩存档往返保留捆绑组 ---')
before, home = build_bandaged(gui, compress=True)
data = gui._build_save_data()
check('G2a 确实生成了压缩存档（未回退普通格式）',
      data.get('format') == 'replay', f"{data.get('format')}")
check('G2b initial/final 都带 groups',
      'groups' in data['initial'] and 'groups' in data['final'])
text = json.dumps(data, ensure_ascii=False)
gui._load_save_data(json.loads(text))
after = sorted(gui.game.groups_summary())
check('G2c 压缩存档载入后捆绑组一致', after == before, f'{after} vs {before}')
check('G2d 重放历史条数正确（参考态 + 步数）',
      len(gui.game_history.history) == 2, f'{len(gui.game_history.history)}')
check('G2e 载入未触发「校验未通过」回退',
      not str(getattr(gui, 'macro_notify_msg', '') or '').startswith('压缩存档公式'),
      f'{getattr(gui, "macro_notify_msg", "")!r}')

# ---------------------------------------------------------------- G3 撤销
print('\n--- G3 载入后撤销：捆绑随状态回退 ---')
gui.game_history.restore_snapshot(gui.game, 0)
back = sorted(gui.game.groups_summary())
check('G3a 撤销到参考态后捆绑仍在', len(back) == 1 and len(back[0][1]) == 4,
      f'{back}')
check('G3b 捆绑位置回到参考态原位置', back == home, f'{back} vs {home}')
gui.game_history.restore_snapshot(gui.game, 1)
check('G3c 重做到末态捆绑仍在',
      len(gui.game.groups_summary()) == 1, f'{gui.game.groups_summary()}')

# ---------------------------------------------------------------- G4 旧存档兼容
print('\n--- G4 旧存档（无 groups 字段）向后兼容 ---')
before, _home = build_bandaged(gui, compress=False)
old = json.loads(json.dumps(gui._build_save_data(), ensure_ascii=False))
for s in old['history']['snapshots']:
    s.pop('groups', None)
old['checksum'] = _compute_checksum(old)
gui._load_save_data(old)
check('G4a 旧存档仍能载入（形状正确）',
      len(gui.game.blocks) == 9, f'{len(gui.game.blocks)}')
check('G4b 旧存档没有捆绑 = 全散块（与修复前行为一致）',
      gui.game.groups_summary() == [], f'{gui.game.groups_summary()}')

# ---------------------------------------------------------------- G5 无捆绑局
print('\n--- G5 无捆绑局不写 groups 字段 ---')
gui.use_compressed_save = False
gui.new_puzzle(4, 4, 1)
plain = gui._build_save_data()
check('G5a 普通局快照不含 groups 字段（格式/体积不变）',
      all('groups' not in s for s in plain['history']['snapshots']))
gui.use_compressed_save = True
plain = gui._build_save_data()
check('G5b 普通局压缩存档不含 groups 字段',
      plain.get('format') == 'replay'
      and 'groups' not in plain['initial'] and 'groups' not in plain['final'])

# ---------------------------------------------------------------- G6 哈希兼容
print('\n--- G6 无捆绑局状态哈希与旧算法一致 ---')
import hashlib  # noqa: E402
nums = sorted([b.location[0], b.location[1], b.number]
              for b in gui.game.blocks
              if getattr(b, 'number', None) is not None)
old_payload = json.dumps({'m': gui.game.matrix, 'n': nums}, sort_keys=True,
                         ensure_ascii=False)
old_hash = hashlib.sha256(old_payload.encode('utf-8')).hexdigest()
check('G6a 无捆绑局哈希 == 旧算法（旧压缩档不会误判损坏）',
      _state_hash(gui.game) == old_hash)
gui.game.apply_pattern(CELLS, BANDED)
check('G6b 有捆绑局哈希 != 旧算法（校验点真正覆盖捆绑态）',
      _state_hash(gui.game) != old_hash)

# ---------------------------------------------------------------- G7/G8 编解码
print('\n--- G7/G8 编解码与坏数据拒绝 ---')
j = groups_to_json({(0, 0): 1, (0, 1): 1, (1, 0): 2})
check('G7a 编码为排序三元组', j == [[0, 0, 1], [0, 1, 1], [1, 0, 2]], f'{j}')
check('G7b 解码回 tuple-key dict',
      groups_from_json(j) == {(0, 0): 1, (0, 1): 1, (1, 0): 2},
      f'{groups_from_json(j)}')
check('G7c 空/None 编码为 None（不写字段）',
      groups_to_json(None) is None and groups_to_json({}) is None)
check('G7d 兼容字符串 key 的 dict（手改存档）',
      groups_from_json({'0,1': 3}) == {(0, 1): 3},
      f'{groups_from_json({"0,1": 3})}')

bad1 = {'matrix': [[1, 1]], 'bounds': {'min_row': 0, 'max_row': 0,
                                       'min_col': 0, 'max_col': 1},
        'groups': [[0, 0, -1]]}
try:
    validate_snapshot(bad1)
    ok_bad1 = False
except ValueError:
    ok_bad1 = True
check('G8a 负数 gid 被拒', ok_bad1)

bad2 = dict(bad1)
bad2['groups'] = [[0, 0]]
try:
    validate_snapshot(bad2)
    ok_bad2 = False
except ValueError:
    ok_bad2 = True
check('G8b 残缺条目被拒', ok_bad2)

good = dict(bad1)
good['groups'] = [[0, 0, 2]]
try:
    validate_snapshot(good)
    ok_good = True
except ValueError as e:
    ok_good = False
    print('   ', e)
check('G8c 合法 groups 通过校验', ok_good)

print('\n--- G9 压缩→普通转换保留捆绑 ---')
before, _home = build_bandaged(gui, compress=True)
comp = gui._build_save_data()
normal = decompress_to_normal(comp)
last = normal['history']['snapshots'][-1]
want = {(r, c): 1 for r, c in before[0][1]}
check('G9a 转换后末快照带 groups', 'groups' in last, f"{last.get('groups')}")
check('G9b 转换后捆绑组一致', groups_from_json(last.get('groups')) == want,
      f"{groups_from_json(last.get('groups'))} vs {want}")
gui.use_compressed_save = False
gui._load_save_data(json.loads(json.dumps(normal, ensure_ascii=False)))
check('G9c 转换出的普通存档可载入且捆绑在',
      sorted(gui.game.groups_summary()) == before,
      f'{gui.game.groups_summary()} vs {before}')

print('\n--- G10 合并快照下逐步撤销不丢捆绑（expand_snapshot_moves）---')


def find_move(game):
    for gt in ('h', 'v'):
        for line in range(-1, 4):
            for d in ('w', 'a', 's', 'd'):
                blk = None
                for b in game.blocks:
                    r, c = b.location[0], b.location[1]
                    if gt == 'h' and r <= line:
                        blk = b
                        break
                    if gt == 'v' and c <= line:
                        blk = b
                        break
                if blk is None:
                    continue
                try:
                    game.opt(gt, line, blk)
                except Exception:
                    continue
                moved = [tuple(b.location) for b in game.blocks if b.be_opted]
                fin, _reason = game.try_move_ex(d, 1)
                if fin:
                    return gt, line, d, moved, fin
    return None


gui.use_compressed_save = False
gui.new_puzzle(4, 4, 1)
g = gui.game
g.apply_pattern([(r, c) for r in range(4) for c in range(4)], BANDED)
gui.current_m, gui.current_n = g.m, g.n
gui.game_history.reset()
gui.game_history.save_snapshot(g)
n_moves = 0
for _i in range(3):
    res = find_move(g)
    if not res:
        break
    gt, line, d, moved, fin = res
    mv = {'gap_type': gt, 'gap_line': line, 'direction': d, 'step': 1,
          'moved_positions': [list(p) for p in moved]}
    g.commit_move(fin)
    gui.game_history.save_snapshot(g, mv, 'SAME')   # 同一会话 → 合并快照
    n_moves += 1
check('G10a 连走 3 步合并成 1 条快照',
      n_moves == 3 and len(gui.game_history.history) == 2,
      f'{n_moves} 步 / {len(gui.game_history.history)} 条')
check('G10b 合并快照记了 steps 与 groups',
      gui.game_history.history[-1].get('steps') == 3
      and bool(gui.game_history.history[-1].get('groups')),
      f"steps={gui.game_history.history[-1].get('steps')}")
all_ok = True
for i in range(n_moves, -1, -1):
    gui.game_history.restore_snapshot(g, i)
    gs = g.groups_summary()
    all_ok = all_ok and len(gs) == 1 and len(gs[0][1]) == 4
check('G10c 逐步撤销全程捆绑保留（惰性拆分中间态带 groups）', all_ok)

print('\n===', 'ALL PASS' if not _failures else f'{len(_failures)} FAILURES', '===')
sys.exit(1 if _failures else 0)