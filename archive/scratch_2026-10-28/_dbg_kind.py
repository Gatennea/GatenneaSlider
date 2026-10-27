# -*- coding: utf-8 -*-
"""game.kind 是不是模型名？能否据此反查 doc 的 orientations.shape。"""
import os
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.abspath(__file__))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from engine import model_registry  # noqa: E402

_OUT = os.path.join(_PROJ, 'archive', '_kind.txt')
w = []


def rec(*a):
    w.append(' '.join(str(x) for x in a))


def main():
    for name in ('shatter', 'shield'):
        try:
            gui = SliderGUI(m=4, n=4, step=1)
            gui.animation_enabled = False
            gui._readonly = False
            gui.save_readonly_flag = False
            gui.tut_show_prompt = False
            gui.tutorial_active = False
            pygame.display.set_mode((gui.screen_width, gui.screen_height))
            gui.screen = pygame.display.get_surface()
            gui.new_model_puzzle(name, 1)
            g = gui.game
            rec('===', name, 'kind=', repr(getattr(g, 'kind', None)))
            k = getattr(g, 'kind', None)
            try:
                doc = model_registry.loaded(k).doc or {}
                o = doc.get('orientations') or {}
                rec('   doc_ok n_orients=', len(o))
                rec('   shapes=', sorted({v.get('shape') for v in o.values()}))
                rec('   labels[:4]=', list(o)[:4])
            except Exception as exc:  # noqa: BLE001
                rec('   doc_FAIL', repr(exc))
            # registry 里有哪些已加载模型
            try:
                rec('   loaded=', sorted(model_registry.list_loaded()
                                         if hasattr(model_registry, 'list_loaded')
                                         else []))
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001
            rec('===', name, 'EXC', repr(exc))

    # model_registry 的可列举接口
    rec('registry attrs=', [a for a in dir(model_registry) if not a.startswith('_')])


try:
    main()
except Exception:
    import traceback
    w.append('EXC')
    w.append(traceback.format_exc())

with open(_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(w))
