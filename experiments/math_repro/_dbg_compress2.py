import sys, json
sys.path.insert(0, '.')
sys.path.insert(0, 'gui')
from compressed_save import (compress_snapshots, decompress_to_normal, _game_from_snapshot,
                             _snapshot_cells, _apply_step)

def gc(game):
    return frozenset(tuple(b.location) for b in game.blocks)

f = 'save/255/2-5-5-20260904-162859.json'
src = json.load(open(f, encoding='utf-8'))
p = src['puzzle']; snaps = src['history']['snapshots']

comp = compress_snapshots(p, snaps, src['step_count'], bool(src.get('readonly', False)))
print('compressed steps:', len(comp['steps']), 'formulas[0..3]:', comp['formulas'][:4])
print('step0:', comp['steps'][0])
print('snap0 bounds:', snaps[0]['bounds'])
print('snap1 bounds:', snaps[1]['bounds'])
print('snap1 move_info:', snaps[1]['move_info'])

# decompress and compare step-by-step
game = _game_from_snapshot(comp['initial'], p['m'], p['n'])
print('dec game bbox after init:', game.matrix_bounds)
print('dec init cells == snap0 cells?', _snapshot_cells(snaps[0])==gc(game))

# map compressed steps to original snapshots: each original snapshot has >=1 move
gi = 0
for si, snap in enumerate(snaps[1:], start=1):
    ms = snap.get('moves')
    if not ms:
        mi = snap.get('move_info'); ms = [mi] if mi else []
    for mv in ms:
        if not mv: continue
        stepd = comp['steps'][gi]
        fp, reason = _apply_step(game, stepd)
        if not fp:
            print(f'dec step {gi} FAILED: {reason}'); break
        gi += 1
    else:
        if _snapshot_cells(snap) != gc(game):
            print(f'dec after snap {si}: cells differ')
            a = gc(game); b = _snapshot_cells(snap)
            print('  only-game:', sorted(a-b)[:8])
            print('  only-snap:', sorted(b-a)[:8])
            print('  stepd=', comp['steps'][gi-1] if gi>0 else None)
            break
        continue
    break
else:
    print('dec final matches?', _snapshot_cells(snaps[-1])==gc(game))
