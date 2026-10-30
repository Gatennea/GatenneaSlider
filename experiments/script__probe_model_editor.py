# -*- coding: utf-8 -*-
"""探针：搭积木编辑器 Mixin 的逻辑路径（无窗口，stub 掉 GUI 依赖）。

跑法：D:/python/python.exe experiments/script__probe_model_editor.py
"""
import os
import sys

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT)

from engine import editor_geom as eg
from engine.model_loader import load_shapes
from engine.model_registry import loaded, reload
from engine.registry import board_types, make_board, unregister_board_type
from gui.model_editor import ModelEditorMixin


class StubGUI(ModelEditorMixin):
    """只提供 Mixin 逻辑路径用到的属性（绘制路径不在本探针范围）。"""

    def __init__(self):
        self._med_init_state()
        self.menu_bar_height = 32
        self.status_bar_height = 28
        self.screen_width = 1000
        self.screen_height = 618
        self.right_panel_width = 132
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.zoom = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 4.0
        self.triangle_mode = False
        self.mi_mode = False
        self.numbered = False
        self.timer_state = 'idle'
        self.selected_gap = None
        self.selected_block = None
        self.drag_following = False
        self.notify = []
        self.game = object()      # 打开编辑器时会被备份/替换

    def _ann_notify(self, text):
        self.notify.append(text)

    def _ann_modal_conflict(self):
        return False

    def _is_camera_valid(self):
        return True

    def center_map(self):
        pass

    def _refresh_puzzle_presets(self):
        pass


def show(gui, tag):
    med = gui._med
    fams = gui._med_families()
    en = gui._med_enabled_families()
    n_moves, n_movable = gui._med_move_info()
    blocks = gui._med_blocks()
    conn = eg.is_connected(blocks, gui._med_orientations())
    ok, why = gui._med_gate()
    print(f'[{tag}] 块={len(blocks)} 连通={conn} 族={[(f[0], f[3]) for f in fams]} '
          f'开={[f[0] for f in en]} 移={n_moves} 可动={n_movable} 门={ok} {why}')


def main():
    shapes = load_shapes()
    print('形状库:', {k: len(eg.d6_images(v)) for k, v in shapes.items()})
    gui = StubGUI()
    gui._med_open()
    med = gui._med
    imgs = med['images']['tri']
    up = eg.normalize(((0, 0), (1, 0), (0, 1)))
    dn = eg.normalize(((0, 0), (1, 0), (1, -1)))
    i_up = next(i for i, im in enumerate(imgs) if im == up)
    i_dn = next(i for i, im in enumerate(imgs) if im == dn)
    print(f'默认形状={med["shape"]} 朝向={med["cursor"]} '
          f'▲={i_up} ▼={i_dn} 标签数={len(gui._med_orientations())} '
          f'kind={gui.game.kind}')
    show(gui, '开局一块')

    # ---- 1. 贴边吸附路径：▲ + ▼ = 菱形 ----
    gui._med_clear()
    assert gui._med_place_at(0.4, 0.3)          # 空盘自由落点
    assert gui._med_place_at(1.0, 0.5)          # 点在共享边中点 → 吸附
    show(gui, '菱形（吸附）')
    # 点已有块内部 → 删除（▲(0,0) 的平面多边形内部取一点）
    bx, by = eg.to_plane((0, 0))
    assert gui._med_delete_at(bx + 0.3, by + 0.2)
    show(gui, '删掉 ▲ 后')

    # ---- 2. 搭一个边长 3 的正三角（引擎 tri preset 的还原态）----
    gui._med_clear()
    for i in range(3):
        for j in range(3 - i):
            med['placed'][((i, j), 'tri', i_up)] = imgs[i_up]
    for i in range(2):
        for j in range(2 - i):
            med['placed'][((i, j), 'tri', i_dn)] = imgs[i_dn]
    gui._med_sync_after_edit()
    show(gui, '边长3正三角')
    n0 = len(med['placed'])

    # ---- 3. 撤销 / 重做 ----
    gui._med_undo()
    print(f'  撤销: {n0} -> {len(med["placed"])}')
    gui._med_redo()
    print(f'  重做: -> {len(med["placed"])}')

    # ---- 4. 关掉一条缝族，看计数变化 ----
    fams = gui._med_families()
    if fams:
        off = fams[0][0]
        gui._med['fam_off'].add(off)
        gui._med['cnt_sig'] = None
        show(gui, f'关掉 {off}')
        gui._med['fam_off'].discard(off)
        gui._med['cnt_sig'] = None
        show(gui, f'开回 {off}')

    # ---- 5. 文档校验 ----
    doc = gui._med_build_doc('probe_model')
    from engine.model_loader import load_model
    from engine.model_validate import validate
    m = load_model(doc)
    probs = [p for p in validate(m, deep=False) if p.level == 'error']
    print('文档校验错误:', [str(p) for p in probs])
    print('  tiles:', len(doc['tiles']), ' seams:', [s['name'] for s in doc['seams']],
          ' 朝向数:', len(doc['orientations']))
    print('  样例 tile:', doc['tiles'][0])

    # ---- 6. 保存 + 热注册（写临时目录，不污染 models/）----
    import tempfile
    import engine.model_loader as ml
    tmp = tempfile.mkdtemp(prefix='med_probe_')
    old = ml.DEFAULT_MODEL_DIR
    ml.DEFAULT_MODEL_DIR = tmp
    try:
        gui._med['name'] = 'probe_model'
        gui._med_save()
        print('保存文件存在:', os.path.exists(os.path.join(tmp, 'probe_model.json')))
        print('已装:', 'probe_model' in loaded(), ' 注册表:',
              'probe_model' in board_types())
        lm = loaded('probe_model')
        print('  块数:', len(lm.spec.goal_blocks), ' 族:',
              [f.name for f in lm.spec.seam_families])
        b = make_board('probe_model')
        print('  可建局:', b.block_count, ' 有合法移动:', b.has_legal_move(1))
        unregister_board_type('probe_model')
        print('清理后注册表含 probe_model:', 'probe_model' in board_types())
    finally:
        ml.DEFAULT_MODEL_DIR = old

    # ---- 7. 退出还原 ----
    orig = gui._med['backup']['game']
    gui._med_close()
    print('退出后 _med_active=', gui._med_active, ' game 已还原=', gui.game is orig)
    print('通知', len(gui.notify), '条：')
    for t in gui.notify:
        print('   ·', t)


if __name__ == '__main__':
    main()
