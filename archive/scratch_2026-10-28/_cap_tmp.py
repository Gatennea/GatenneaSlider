import os, sys
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, 'E:\\program_project\\other\\wkbddtest\\GatenneaSlider\\test')
sys.path.insert(0, 'E:\\program_project\\other\\wkbddtest\\GatenneaSlider')
os.chdir('E:\\program_project\\other\\wkbddtest\\GatenneaSlider')
import _test_model_editor as m
m.t_seed_current_route_a()
_f = getattr(m, 'FAILS', [])
print('FAILS=%d' % len(_f))
for _x in _f:
    print('  FAILLIST:', _x)
print('FUNC_OK _test_model_editor.t_seed_current_route_a')
