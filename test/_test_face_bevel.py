# -*- coding: utf-8 -*-
"""§六十二 护栏：立体光效（二维面内四边微倒角）开关。
并覆盖 §六十五（捆绑光效）/ §六十六（蓝色溢出=带让位边框）/ §六十九
（禁用缝族提示——本文件只测其中的就地附句，常驻文案与位置见截图验收）。

覆盖（对应 docs/agent/待办清单.md §62 验收）：
- 护栏A「开关关时渲染与改动前一致」= 关态下三形态绘制 **零次** 走
  `_draw_face_bevel`（行为判据：运行时调用计数，不用源码字符串）
- 护栏B 三形态视觉回归：开/关两帧像素不同（开关真生效）+ 关态两帧一致（确定性）
- 护栏C 方向数学：上边提亮、下边压暗（与三维 face_shade 同向）
- 三处同步（AGENTS §16）：config.json 存取 / _SETTINGS_BOOL_KEYS / http 白名单
- 设置页开关与 feature_index 登记（§3 新红线）+ 一键切换接线
- AA 路径与直出路径走同一 helper
- §65 捆绑光效：方形/三角捆绑局关态零调用、开态走 helper；组外轮廓有带、
  组内共用边无带（edges 过滤=「一整块刚体」不现分隔线，离屏像素断言）
- §66 带让位边框：edge_inset_px 让带外沿离开边界线（有区分度的单元断言：
  让位后边界线保持底色、默认 0 带压边界线）+ 三趟模拟框外侧无提亮色
- §69 就地附句：点「画得出选不中」的缝时，模型带 disabled_seams 则提示
  附「本模型关闭了…设计如此」，不带则文案不变（不静默改旧提示）

运行：python test/_test_face_bevel.py
"""
import json
import os
import queue
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui import renderer as renderer_mod  # noqa: E402
from gui import events as events_mod  # noqa: E402
from gui import feature_index as fi  # noqa: E402
from game_triangle import neighbors as tri_neighbors  # noqa: E402
import http_server  # noqa: E402

PASSED = 0
FAILED = 0
_calls = []
_orig_bevel = renderer_mod._draw_face_bevel


def _counting_bevel(*args, **kwargs):
    _calls.append(args[0] if args else None)
    return _orig_bevel(*args, **kwargs)


def check(cond, label, detail=''):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f'PASS: {label}')
    else:
        FAILED += 1
        d = f' -- {detail}' if detail else ''
        print(f'FAIL: {label}{d}')


def boot(which, *args):
    gui = SliderGUI(cmd_queue=queue.Queue(),
                    ext_state={'enabled': False, 'token': None})
    gui.game_mode = 'practice'
    gui.tutorial_active = False
    gui.tut_show_prompt = False
    gui.animation_enabled = False
    pygame.display.set_mode((gui.screen_width, gui.screen_height))
    gui.screen = pygame.display.get_surface()
    getattr(gui, which)(*args)
    gui._update_in_progress = False
    return gui


def frame_bytes(gui, draw_fn):
    draw_fn()
    return pygame.image.tobytes(gui.screen, 'RGB')


def run_form(name, which, args, draw_attr):
    """一个形态：关态零调用 + 关/开两帧像素不同 + 关态确定性。"""
    gui = boot(which, *args)
    draw = getattr(gui, draw_attr)

    gui.face_bevel_enabled = False
    _calls.clear()
    b_off1 = frame_bytes(gui, draw)
    check(len(_calls) == 0,
          f'{name} 关态不走倒角（渲染与改动前一致）', f'调用 {len(_calls)} 次')
    b_off2 = frame_bytes(gui, draw)
    check(b_off1 == b_off2, f'{name} 关态两帧一致（渲染确定性）')

    gui.face_bevel_enabled = True
    _calls.clear()
    b_on = frame_bytes(gui, draw)
    check(len(_calls) > 0, f'{name} 开态走倒角 helper', f'调用 {len(_calls)} 次')
    check(b_on != b_off1, f'{name} 开/关两帧像素不同（开关真生效）')
    gui.face_bevel_enabled = False
    return gui


def run():
    global PASSED, FAILED
    renderer_mod._draw_face_bevel = _counting_bevel
    try:
        # ---------- 1 默认值与真源登记 ----------
        print('\n--- 1 默认值 / feature_index 登记（§3 红线） ---')
        gui = SliderGUI(cmd_queue=queue.Queue(),
                        ext_state={'enabled': False, 'token': None})
        check(gui.face_bevel_enabled is True, '默认开（用户点名要这效果）')
        ent = next((f for f in fi.FEATURES if f['id'] == 'face_bevel_enabled'), None)
        check(ent is not None, 'feature_index 已登记 face_bevel_enabled')
        check(ent is not None and ent['action'].get('type') == 'toggle',
              'action 接一键切换 toggle')
        check('face_bevel_enabled' in events_mod.EventsMixin._SETTINGS_BOOL_KEYS,
              '_SETTINGS_BOOL_KEYS 同步')
        check('face_bevel_enabled' in http_server.GameHTTPHandler._SETTINGS_BOOL_KEYS,
              'http 白名单同步')

        # ---------- 2 方向数学（helper 单元）----------
        print('\n--- 2 倒角方向：上提亮 / 下压暗 ---')
        surf = pygame.Surface((120, 120))
        fill = (100, 140, 190)
        surf.fill(fill)  # 真实路径：先填面底色，再压倒角带
        pts = [(10, 10), (110, 10), (110, 110), (10, 110)]
        _orig_bevel(surf, pts, fill)
        top = surf.get_at((60, 14))     # 上边带（应 > fill）
        bot = surf.get_at((60, 106))    # 下边带（应 < fill）
        left = surf.get_at((14, 60))
        right = surf.get_at((106, 60))
        check(top[0] > fill[0] and top[1] > fill[1],
              '上边提亮', f'top={tuple(top[:3])}')
        check(bot[0] < fill[0] and bot[1] < fill[1],
              '下边压暗', f'bot={tuple(bot[:3])}')
        check(left[0] > fill[0], '左边提亮', f'left={tuple(left[:3])}')
        check(right[0] < fill[0], '右边压暗', f'right={tuple(right[:3])}')
        center = surf.get_at((60, 60))
        check(tuple(center[:3]) == fill, '面心保持原色（只有窄带变）',
              f'center={tuple(center[:3])}')

        # ---------- 3 三形态行为（关态零调用 / 开关像素差）----------
        print('\n--- 3 三形态：关态一致 / 开态生效 ---')
        run_form('方形', 'new_puzzle', (6, 6, 2), 'draw_board')
        run_form('三角', 'new_triangle_puzzle', (5, 2), 'draw_triangle_board')
        run_form('米字', 'new_mi_puzzle', (4, 4, 2), 'draw_mi_board')
        # §62 补验：碎三角/模型板走 draw_board 的 _polygon_view 分流
        #（_draw_polygon_board 聚合填色趟），与三条手画路径同一 gate。
        run_form('碎三角(聚合板)', 'new_model_puzzle', ('shatter', 1), 'draw_board')

        # ---------- 3b 编号字浮雕（§六十二子项，用户 11-20 拍板）----------
        print('\n--- 3b 编号字：helper 逐位等价 / 方形路径 gate ---')
        # helper 单元：emboss=False 必须与旧画法逐位一致（关态=改动前）
        import pygame.font as _pf
        _pf.init()
        _font = _pf.Font(None, 24)
        _s1 = pygame.Surface((60, 40), pygame.SRCALPHA)
        _s2 = pygame.Surface((60, 40), pygame.SRCALPHA)
        _s1.fill((100, 140, 190))
        _s2.fill((100, 140, 190))
        renderer_mod.draw_block_number(_s1, _font, '7', (30, 20),
                                       (100, 140, 190), emboss=False)
        _t = _font.render('7', True, (0, 0, 0))
        _s2.blit(_t, _t.get_rect(center=(30, 20)))
        check(pygame.image.tobytes(_s1, 'RGBA') == pygame.image.tobytes(_s2, 'RGBA'),
              '编号字 emboss=False 与旧画法逐位一致')
        _s3 = pygame.Surface((60, 40), pygame.SRCALPHA)
        _s3.fill((100, 140, 190))
        renderer_mod.draw_block_number(_s3, _font, '7', (30, 20),
                                       (100, 140, 190), emboss=True)
        _hl = renderer_mod._shade255((100, 140, 190), 44)
        _found = any(tuple(_s3.get_at((x, y)))[:3] == _hl
                     for x in range(24, 37) for y in range(11, 29))
        check(_found, '编号字 emboss=True 有左上提亮浮雕边', f'target={_hl}')

        # 路径 gate 计数：wrap draw_block_number 记录 emboss 参数
        # （§63：编号只有方形数字形态真实存在；三角/聚合板的编号段是照搬
        #  带来的死代码，已删——见 docs/spec/几何引擎残留清理方案 §2.4）
        _num_calls = []
        _orig_num = renderer_mod.draw_block_number

        def _spy_num(*args, **kwargs):
            _num_calls.append(kwargs.get('emboss', args[5] if len(args) > 5 else None))
            return _orig_num(*args, **kwargs)

        renderer_mod.draw_block_number = _spy_num
        try:
            # 方形数字形态（建局即带编号数据）
            gui = SliderGUI(cmd_queue=queue.Queue(),
                            ext_state={'enabled': False, 'token': None})
            gui.animation_enabled = False
            gui.tutorial_active = False
            gui.tut_show_prompt = False
            pygame.display.set_mode((gui.screen_width, gui.screen_height))
            gui.screen = pygame.display.get_surface()
            gui.new_puzzle(4, 4, 1, numbered=True)
            gui.face_bevel_enabled = False
            _num_calls.clear()
            gui.draw_board()
            check(_num_calls and all(v is False for v in _num_calls),
                  '方形数字关态全部 emboss=False', str(set(_num_calls)))
            off_frame = pygame.image.tobytes(gui.screen, 'RGB')
            gui.face_bevel_enabled = True
            _num_calls.clear()
            gui.draw_board()
            check(any(v is True for v in _num_calls),
                  '方形数字开态 emboss=True', str(set(_num_calls)))
            on_frame = pygame.image.tobytes(gui.screen, 'RGB')
            check(off_frame != on_frame, '方形数字开/关两帧不同')
        finally:
            renderer_mod.draw_block_number = _orig_num

        # ---------- 4 AA 路径与直出路径同一 helper ----------
        print('\n--- 4 AA 路径 ---')
        gui = boot('new_triangle_puzzle', 5, 2)
        poly = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0)]
        _calls.clear()
        gui._draw_aa_polygon(poly, (100, 140, 190), (0, 0, 0), 2, bevel=False)
        check(len(_calls) == 0, 'AA bevel=False 不走倒角')
        _calls.clear()
        gui._draw_aa_polygon(poly, (100, 140, 190), (0, 0, 0), 2, bevel=True)
        check(len(_calls) > 0, 'AA bevel=True 走同一 helper')

        # ---------- 5 设置页开关 + 一键切换接线 ----------
        print('\n--- 5 设置页开关 / 一键切换 ---')
        gui = boot('new_puzzle', 6, 6, 2)
        gui.show_settings_dialog = True
        gui.settings_active_tab = 'animation'
        gui.draw_settings_dialog()
        rect = getattr(gui, '_settings_bevel_toggle_rect', None)
        check(rect is not None and rect.w > 0, '设置页画出「立体光效」开关')
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                pos=rect.center)
        before = gui.face_bevel_enabled
        gui._handle_settings_dialog_event(ev)
        check(gui.face_bevel_enabled != before, '设置页点击翻转生效',
              f'{before} -> {gui.face_bevel_enabled}')
        # Ctrl+K 一键切换（toggle action 同一支）
        gui._handle_right_panel_switch('face_bevel_enabled')
        check(gui.face_bevel_enabled == before, '一键切换同支翻转回来',
              f'-> {gui.face_bevel_enabled}')

        # ---------- 6 config.json 存取 roundtrip ----------
        print('\n--- 6 config 存取 roundtrip ---')
        tmp = tempfile.mkdtemp(prefix='s62_')
        gui = boot('new_puzzle', 6, 6, 2)
        gui.config_dir = tmp
        gui.config_path = os.path.join(tmp, 'config.json')
        gui.temp_history_path = os.path.join(tmp, 'temp_history.json')
        gui.face_bevel_enabled = False
        gui.save_config()
        with open(gui.config_path, encoding='utf-8') as f:
            cfg = json.load(f)
        check(cfg.get('face_bevel_enabled') is False, 'save 落盘 False',
              str(cfg.get('face_bevel_enabled')))
        # 载入侧：另起实例读回
        gui2 = boot('new_puzzle', 6, 6, 2)
        gui2.config_dir = tmp
        gui2.config_path = gui.config_path
        gui2.temp_history_path = gui.temp_history_path
        gui2.face_bevel_enabled = True
        gui2.load_last_state()
        check(gui2.face_bevel_enabled is False, 'load 读回 False')

        # ---------- 7 §六十六：倒角带让位边框（蓝色溢出修复）----------
        print('\n--- 7 §66 带让位边框 ---')
        _fill7 = (100, 140, 190)
        pts7 = [(10, 10), (110, 10), (110, 110), (10, 110)]
        # 7a 单元（有区分度）：edge_inset_px 让带外沿离开边界线
        s7 = pygame.Surface((120, 120))
        s7.fill(_fill7)
        _orig_bevel(s7, pts7, _fill7, edge_inset_px=2.0)
        check(tuple(s7.get_at((60, 10)))[:3] == _fill7,
              '§66 inset=2：边界线保持底色（带让位出框内沿）',
              str(tuple(s7.get_at((60, 10)))[:3]))
        check(tuple(s7.get_at((60, 13)))[:3] != _fill7,
              '§66 inset=2：带在框内侧存在（让位不等于不画）',
              str(tuple(s7.get_at((60, 13)))[:3]))
        s7b = pygame.Surface((120, 120))
        s7b.fill(_fill7)
        _orig_bevel(s7b, pts7, _fill7)   # 默认 edge_inset_px=0 = 旧口径
        check(tuple(s7b.get_at((60, 10)))[:3] != _fill7,
              '§66 默认0：带压边界线（旧口径零变化——证明上一条有区分度）',
              str(tuple(s7b.get_at((60, 10)))[:3]))
        # 7b 三趟模拟（方形口径 fill→bevel→描边）：框保持灰、框外侧是背景
        _bg7, _bd7 = (40, 40, 46), (120, 120, 120)
        s7c = pygame.Surface((120, 120))
        s7c.fill(_bg7)
        r7 = pygame.Rect(10, 10, 100, 100)
        pygame.draw.rect(s7c, _fill7, r7)
        _orig_bevel(s7c, (r7.topleft, r7.topright, r7.bottomright, r7.bottomleft),
                    _fill7, edge_inset_px=1.0)
        pygame.draw.rect(s7c, _bd7, r7, 2)
        check(tuple(s7c.get_at((60, 8)))[:3] == _bg7,
              '§66 框外侧是背景（提亮带不越界）',
              str(tuple(s7c.get_at((60, 8)))[:3]))
        check(tuple(s7c.get_at((60, 10)))[:3] == _bd7,
              '§66 框像素保持灰（带不压框）',
              str(tuple(s7c.get_at((60, 10)))[:3]))
        # 7c 三形态盘面：开态背景侧无提亮色越界（真实像素扫描，防回退）
        for _name7, _boot7, _draw7 in (
                ('方形', ('new_puzzle', 6, 6, 2), 'draw_board'),
                ('三角', ('new_triangle_puzzle', 5, 2), 'draw_triangle_board'),
                ('米字', ('new_mi_puzzle', 4, 4, 2), 'draw_mi_board')):
            gui7 = boot(*_boot7)
            gui7.face_bevel_enabled = True
            getattr(gui7, _draw7)()
            _d = pygame.image.tobytes(gui7.screen, 'RGB')
            _W = gui7.screen_width
            _bgp = gui7.colors.get('background', (0, 0, 0))
            _blk = gui7.colors['block']
            _hits = 0
            for _y in range(1, gui7.screen_height - 1):
                for _x in range(1, _W - 1):
                    _i = (_y * _W + _x) * 3
                    if (_d[_i], _d[_i + 1], _d[_i + 2]) != _bgp:
                        continue
                    for _dx in (-1, 0, 1):
                        for _dy in (-1, 0, 1):
                            if _dx == 0 and _dy == 0:
                                continue
                            _j = ((_y + _dy) * _W + _x + _dx) * 3
                            _n = (_d[_j], _d[_j + 1], _d[_j + 2])
                            if (_n != _bgp and _n != _blk
                                    and _n[2] > _blk[2] + 20
                                    and _n[0] > _blk[0] + 5):
                                _hits += 1
                                break
                    if _hits:
                        break
                if _hits:
                    break
            check(_hits == 0, f'§66 {_name7} 开态背景侧无提亮色越界',
                  f'hits={_hits}')

        # ---------- 8 §六十五：捆绑光效（两条捆绑路径）----------
        print('\n--- 8 §65 捆绑块光效 ---')

        def _bind_group(gui, cells):
            pos = {tuple(b.location): b for b in gui.game.blocks}
            for c in cells:
                pos[tuple(c)].group = 1

        def _band_frame(gui, draw_attr, on):
            gui.face_bevel_enabled = on
            _calls.clear()
            getattr(gui, draw_attr)()
            return pygame.image.tobytes(gui.screen, 'RGB'), len(_calls)

        # 8a 方形矩形组（2x2）：关态零调用 / 开态走 helper / 两帧不同
        gui8 = boot('new_puzzle', 6, 6, 2)
        _bind_group(gui8, [(0, 0), (0, 1), (1, 0), (1, 1)])
        f_off8, n_off8 = _band_frame(gui8, 'draw_board', False)
        check(n_off8 == 0, '方形捆绑关态不走倒角', f'调用 {n_off8} 次')
        f_on8, n_on8 = _band_frame(gui8, 'draw_board', True)
        check(n_on8 > 0, '方形捆绑开态走倒角 helper', f'调用 {n_on8} 次')
        check(f_off8 != f_on8, '方形捆绑开/关两帧不同')
        gui8.face_bevel_enabled = False
        # 8b 三角 3 块组（走 _draw_bandaged_groups_poly → draw_group_pieces）
        gui8t = boot('new_triangle_puzzle', 6, 2)
        _cells8t = sorted(tuple(b.location) for b in gui8t.game.blocks)
        _seed8t = None
        for _p in _cells8t:
            _on = [n for n in map(tuple, tri_neighbors(_p)) if n in set(_cells8t)]
            if len(_on) >= 2:
                _seed8t = [_p] + _on[:2]
                break
        check(_seed8t is not None and len(_seed8t) == 3, '三角找到可绑3块')
        if _seed8t:
            _bind_group(gui8t, _seed8t)
            f_off8t, n_off8t = _band_frame(gui8t, 'draw_triangle_board', False)
            check(n_off8t == 0, '三角捆绑关态不走倒角', f'调用 {n_off8t} 次')
            f_on8t, n_on8t = _band_frame(gui8t, 'draw_triangle_board', True)
            check(n_on8t > 0, '三角捆绑开态走倒角 helper', f'调用 {n_on8t} 次')
            check(f_off8t != f_on8t, '三角捆绑开/关两帧不同')
            gui8t.face_bevel_enabled = False
        # 8c 离屏 draw_group_pieces：组外轮廓边有带、组内共用边无带
        #    （edges 过滤 = 「一整块刚体」不现组内分隔线）
        from gui.group_render import draw_group_pieces, draw_group_chunks
        _bg8 = (40, 40, 46)
        sp8 = pygame.Surface((30, 16))
        sp8.fill(_bg8)
        _pl = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        _pr = [(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0)]
        # 左块边1(右)、右块边3(左) 是组内共用边
        draw_group_pieces(
            sp8,
            [(_pl, [False, True, False, False], False),
             (_pr, [False, False, False, True], False)],
            [], lambda x, y: (x, y),
            _fill7, (140, 180, 220), _bd7, 2, (),
            bevel=_orig_bevel, edge_inset_px=1.0,
            bevel_inset_px=5.0)
        # 组外上边（y=0，让位1后带在 y≈1）：提亮带存在
        check(tuple(sp8.get_at((5, 1)))[:3] != _fill7,
              '§65 pieces 组外轮廓边有倒角带',
              str(tuple(sp8.get_at((5, 1)))[:3]))
        # 组内共用边（x=10 左侧 x=9）：无带（保持填色，组内不分隔）
        check(tuple(sp8.get_at((9, 5)))[:3] == _fill7,
              '§65 pieces 组内共用边无带（组内不现分隔线）',
              str(tuple(sp8.get_at((9, 5)))[:3]))
        # 8d 离屏 draw_group_chunks：同口径（方形非矩形组路径）
        sp8d = pygame.Surface((30, 16))
        sp8d.fill(_bg8)
        draw_group_chunks(
            sp8d, {1: [(0, 0), (0, 1)]},
            lambda r, c: (c * 12, 0, 10), 2,
            _fill7, (140, 180, 220), _bd7, 2,
            bevel=_orig_bevel, edge_inset_px=1.0,
            bevel_inset_px=5.0)
        check(tuple(sp8d.get_at((5, 1)))[:3] != _fill7,
              '§65 chunks 组外侧边有倒角带',
              str(tuple(sp8d.get_at((5, 1)))[:3]))
        check(tuple(sp8d.get_at((9, 5)))[:3] == _fill7,
              '§65 chunks 组内相邻边无带（组内不现分隔线）',
              str(tuple(sp8d.get_at((9, 5)))[:3]))
        # 8e §65 修正（用户 11-21「厚度不一样」）：固定厚度——不同尺寸
        # 矩形走产品口径（inset_px=BEVEL_INSET_PX）带厚一致。原比例制
        # （0.15）下 60px 块带≈4.5、126px 块带≈9.5，此断言会红。
        from gui.lighting import BEVEL_INSET_PX

        def _band_thick(size):
            s = pygame.Surface((size + 20, size + 20))
            s.fill(_bg8)
            r = pygame.Rect(10, 10, size, size)
            pygame.draw.rect(s, _fill7, r)
            _orig_bevel(s, (r.topleft, r.topright, r.bottomright, r.bottomleft),
                        _fill7, inset_px=BEVEL_INSET_PX)
            mid = 10 + size // 2
            thick = 0
            for y in range(10, 10 + 40):
                if tuple(s.get_at((mid, y)))[:3] == _fill7:
                    break
                thick += 1
            return thick

        _t60 = _band_thick(60)
        _t126 = _band_thick(126)
        # 一致是硬条件；绝对值允许 ±1（多边形 rasterize 对边界行的含侧）
        check(_t60 == _t126 and abs(_t60 - int(BEVEL_INSET_PX)) <= 1,
              '§65 固定厚度：60px 与 126px 块带厚一致 ≈ 设计像素',
              f'60px={_t60} 126px={_t126} design={BEVEL_INSET_PX}')

        # 8f 长条端头不斜切（用户 11-21「最上面的长条画的不好」）：
        # 旧「端点向质心收」在 306×60 长条上把上边带内沿端点拉进 25.5px
        # ——近端 x=10 处带缺失（厚 0）；角平分线内缩后全带等厚。
        def _long_band_thick(x):
            s = pygame.Surface((326, 80))
            s.fill(_bg8)
            r = pygame.Rect(10, 10, 306, 60)
            pygame.draw.rect(s, _fill7, r)
            _orig_bevel(s, (r.topleft, r.topright, r.bottomright, r.bottomleft),
                        _fill7, inset_px=BEVEL_INSET_PX)
            thick = 0
            for y in range(10, 10 + 40):
                if tuple(s.get_at((x, y)))[:3] == _fill7:
                    break
                thick += 1
            return thick

        _near = _long_band_thick(20)      # 距左端 10px（旧几何斜切区内、左端竖带外）
        _mid = _long_band_thick(160)      # 中段
        check(_near == _mid and abs(_mid - int(BEVEL_INSET_PX)) <= 1,
              '§65 长条上边带全带等厚（端头不斜切）',
              f'near_end={_near} mid={_mid} design={BEVEL_INSET_PX}')

        # ---------- 9 §六十九：禁用缝族提示（文案 + 就地附句）----------
        print('\n--- 9 §69 禁用缝族提示 ---')
        # 用模型局（EngineGame）：SliderMatrix 有 __slots__ 挂不了
        # disabled_seams——这属性本就只有模型局才有（GUI 建局时从 json 带入）。
        gui9 = boot('new_model_puzzle', 'shatter', 1)
        check(gui9._seam_disable_hint_text() is None,
              '9a 无 disabled_seams 不提示（普通局零打扰）')
        gui9.game.disabled_seams = [{'name': 'h', 'desc': '水平缝'},
                                    {'name': 'd30', 'desc': '斜缝30°'}]
        t9 = gui9._seam_disable_hint_text() or ''
        check('本模型关闭了部分方向的缝' in t9, '9b 常驻文案开头点题', repr(t9))
        check('水平缝' in t9 and '斜缝30°' in t9, '9c 列出被关的族', repr(t9))
        check('试试其它方向' in t9, '9d 结尾给人话行动指引', repr(t9))
        gui9.screen.fill((0, 0, 0))
        gui9.draw_seam_disable_hint()
        check(pygame.image.tobytes(gui9.screen, 'RGB') != bytes(
                  [0]) * (gui9.screen_width * gui9.screen_height * 3),
              '9e draw 真画出提示框（非空屏）')
        # 9f 就地附句：端到端用方形局外沿死缝（快扫；`_test_sq_seam_hint`
        # 同款场景），附句拼装用模型局入口 `_reject_msg_with_seams`
        # （shatter 全活局没有死缝，端到端扫不出；SliderMatrix 有
        #  __slots__ 挂不了 seams——附句只有模型局才可能触发）。
        HINT9 = gui9.GAP_UNSELECTABLE_MSG
        gui9h = boot('new_puzzle', 6, 6, 2)
        gui9h.game.apply_pattern({(r, c) for r in range(6)
                                  for c in range(6)}, {})

        def _on_rim9(p):
            x, y = p
            return (gui9h.get_gap_at_pos(x, y) is None
                    and gui9h.get_block_at_pos(x, y) is None
                    and gui9h._rejected_seam_at(x, y) is not None)

        _rim9 = None
        for _y in range(0, gui9h.screen_height, 2):
            for _x in range(0, gui9h.screen_width, 2):
                if _on_rim9((_x, _y)):
                    _rim9 = (_x, _y)
                    break
            if _rim9:
                break
        check(_rim9 is not None, '9f 扫到外沿死缝点', str(_rim9))
        if _rim9:
            gui9h.macro_notify_msg = None
            gui9h.macro_notify_timer = 0
            pygame.event.post(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=_rim9))
            gui9h.handle_events()
            msg9 = gui9h.macro_notify_msg or ''
            check(msg9 == HINT9,
                  '9g 端到端：无 seams 就地提示保持旧文案（不静默改）',
                  repr(msg9))
            check('本模型关闭了' not in msg9,
                  '9h 端到端：普通局不带禁缝附句', repr(msg9))
        # 9i 附句拼装入口：有 seams 追加、无 seams 原样
        #（gui9h 是普通方形局，无 seams；gui9 上面 9b 已设过）
        check(gui9h._reject_msg_with_seams(HINT9) == HINT9,
              '9i 无 seams 附句原样返回')
        gui9.game.disabled_seams = [{'name': 'h', 'desc': '水平缝'}]
        _with9 = gui9._reject_msg_with_seams(HINT9)
        check(HINT9 in _with9 and '本模型关闭了' in _with9
              and '水平缝' in _with9,
              '9j 有 seams 追加禁缝附句', repr(_with9))
    finally:
        renderer_mod._draw_face_bevel = _orig_bevel
        pygame.quit()


if __name__ == '__main__':
    pygame.init()
    run()
    total = PASSED + FAILED
    print(f'\n{PASSED}/{total} passed' + (f', {FAILED} FAILED' if FAILED else ' — ALL PASS'))
    sys.exit(1 if FAILED else 0)
