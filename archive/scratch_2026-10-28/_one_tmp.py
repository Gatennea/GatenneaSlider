import os, sys
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
sys.path.insert(0, r'E:\program_project\other\wkbddtest\GatenneaSlider\test')
sys.path.insert(0, r'E:\program_project\other\wkbddtest\GatenneaSlider')
os.chdir(r'E:\program_project\other\wkbddtest\GatenneaSlider')
import _test_model_editor as m
m.t_gate()
print('FUNC_OK t_gate')
