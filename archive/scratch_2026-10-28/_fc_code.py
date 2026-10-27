# -*- coding: utf-8 -*-
import os, sys
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, 'E:\\program_project\\other\\wkbddtest\\GatenneaSlider')
sys.path.insert(0, 'E:\\program_project\\other\\wkbddtest\\GatenneaSlider\\test')
import _test_model_editor as m
m.t_right_click_delete()
print('FUNC_OK')
