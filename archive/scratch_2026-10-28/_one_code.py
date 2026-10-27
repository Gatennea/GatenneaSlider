import sys, traceback
sys.path.insert(0, 'test')
import _test_model_editor as m
try:
    m.t_bundle_toggle()
    print('FUNC_OK')
except SystemExit as e:
    print('SYSEXIT', e.code)
except BaseException:
    traceback.print_exc()
    print('FUNC_ERR')
