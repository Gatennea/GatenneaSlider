import sys, os, json
sys.path.insert(0, '.')
sys.path.insert(0, 'gui')
from compressed_save import _game_from_snapshot, _snapshot_cells

def game_cells(game):
    return frozenset(tuple(b.location) for b in game.blocks)

f = 'save/255/2-5-5-20260904-162859.json'
src = json.load(open(f, encoding='utf-8'))
p = src['puzzle']; snaps = src['history']['snapshots']
game = _game_from_snapshot(snaps[0], p['m'], p['n'])

print('snap0 matrix == game matrix?', snaps[0]['matrix'] == game.matrix)
print('snap0 cells == game cells?', _snapshot_cells(snaps[0]) == game_cells(game))

global_idx = 0
for si, snap in enumerate(snaps[1:], start=1):
    ms = snap.get('moves')
    if not ms:
        mi = snap.get('move_info')
        ms = [mi] if mi else []
    for mv in ms:
        if not mv:
            continue
        bmin = game.matrix_bounds
        gt = mv['gap_type']; gap_line = mv['gap_line']
        direction = mv['direction']; nstep = mv['step']
        moved = mv['moved_positions']
        ar0, ac0 = moved[0]
        anchor = next((b for b in game.blocks if b.location[0]==ar0 and b.location[1]==ac0), None)
        if anchor is None:
            print(f'step {global_idx} (snap{si}): anchor {moved[0]} NOT FOUND'); break
        game.opt(gt, gap_line, anchor)
        sel = [(b.location[0],b.location[1]) for b in game.blocks if b.be_opted]
        if set(sel) != set(tuple(x) for x in moved):
            print(f'step {global_idx} (snap{si}): SELECTED != moved')
            print('  moved=', moved[:8]); print('  sel   =', sel[:8])
            print('  gt=',gt,'gap_line=',gap_line,'dir=',direction,'n=',nstep)
            break
        final_pos, reason = game.try_move_ex(direction, nstep)
        if not final_pos:
            print(f'step {global_idx} (snap{si}): try_move failed: {reason}'); break
        game.commit_move(final_pos)
        global_idx += 1
    else:
        # finished all moves of snap si; compare
        if _snapshot_cells(snap) != game_cells(game):
            print(f'after snap {si}: cells differ')
            gc = game_cells(game); tc = _snapshot_cells(snap)
            print('  only-in-game :', sorted(list(gc-tc))[:8])
            print('  only-in-snap :', sorted(list(tc-gc))[:8])
            break
        continue
    break
else:
    print('ALL OK; final matches?', _snapshot_cells(snaps[-1])==game_cells(game))
