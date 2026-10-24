# -*- coding: utf-8 -*-
"""搭积木编辑器（GUI Mixin）——不写模型 JSON，像搭积木一样摆出新板型。

设计要点
--------
1. **会话期换 game**：打开时把 ``self.game`` 换成实时预览的 ``EngineGame``
   （包一个自建 BoardSpec），退出时原样还原（与设计画布
   ``_ann_btn_design`` 同一套备份/还原模式）。块渲染与命中**全复用通用
   多边形通道**（``_polygon_view`` / ``_draw_polygon_board`` /
   ``SpecPolygonView``）——本 Mixin 只画「调色盘 + 工具栏 + 幽灵预览」
   这些编辑器专属浮层，零重复渲染代码。
2. **几何全在 engine/editor_geom.py**（零 pygame、可单测）：本文件只做
   绘制与事件翻译（屏幕 → 世界 → 晶格）。
3. **保存 = 合成模型 JSON + 热注册**：写 ``models/<name>.json`` →
   ``model_registry.reload(name)`` → ``_refresh_puzzle_presets()``，菜单
   里立刻多一项，不用重启（register 拒绝静默覆盖，先卸后装是唯一路）。
4. **保存门**（比高级选项更严）：≥1 块 + 单一连通 + **至少 2 颗可动**
   （冻形拒存——紧凑 4 块几乎必冻，见 engine/editor_geom 的冻形真值）。

操作
----
* 左键点已有块 = 删除；点空白 = 放置当前朝向（优先贴边吸附，吸附不到
  就自由落在最近格点）；点**两块之间的缝** = 捆绑/解绑（同组整组滑动）。
* R 旋转 / F 镜像：改的是**将要放置**的朝向（已有块不能原地转——换了
  朝向多边形就变，必然重叠；删了重放即可，有撤销）。
* 滚轮缩放（Ctrl+滚轮亦可）、中键拖动平移；ESC 退出。
* U / Ctrl+Z 撤销；Enter 激活名字框、再回车保存；[试玩] 存完直接开局。
"""
import json
import math
import os

import pygame

from engine import editor_geom as eg
from engine.adapter import EngineGame
from engine.board import Block, Board
from engine.model_loader import SCHEMA_BOARD, load_model

# 布局常量（设计像素）
_PANEL_W = 218
_PANEL_X = 10
_BAR_H = 58
# 贴边吸附的命中容差（晶格单位）：点得离候选块够近才吸附，否则自由落点
_SNAP_TOL = 0.75
# 自由落点的搜索半径（格）
_FREE_R = 2


class ModelEditorMixin:
    """搭积木编辑器 Mixin（挂在 SliderGUI 的 bases 上；见模块 docstring）。"""

    # ==================================================================
    # 状态
    # ==================================================================
    def _med_init_state(self):
        """编辑器状态（``SliderGUI.__init__`` 里调；会话期外全部为空）。"""
        self._med_active = False
        self._med = None
        self._med_panning = False
        self._med_pan_origin = None

    @property
    def med_active(self) -> bool:
        """编辑器会话是否进行中（绘制/事件钩子据此分流）。"""
        return bool(getattr(self, '_med_active', False))

    def _med_notify(self, text):
        """走通用通知（与标注画布同一条通道）。"""
        self._ann_notify(text)

    # ==================================================================
    # 打开 / 退出
    # ==================================================================
    def _med_open(self):
        """从「谜题 → 模型谜题 ▸ → ＋ 搭建新模型...」进入编辑器。"""
        if self._med_active:
            self._med_notify('已在搭积木编辑器中（ESC 或[退出]返回）')
            return
        if self.timer_state == 'running':
            self._med_notify('计时进行中无法进入搭积木编辑器')
            return
        from engine.model_loader import load_shapes
        shapes = load_shapes()
        if not shapes:
            self._med_notify('models/shapes.json 里没有可用形状，编辑器无从搭起')
            return
        # ---- 会话数据 ----
        images = {}
        for sname, verts in shapes.items():
            imgs = eg.d6_images(verts)
            if imgs:
                images[sname] = imgs
        if not images:
            self._med_notify('形状库全是空形状，编辑器无从搭起')
            return
        med = {
            'images': images,                 # {形状名: 像元组}
            # 默认形状优先 'tri'（单位等边三角，最「搭积木」的那块）；
            # 库里没有才退回字典序第一个
            'shape': 'tri' if 'tri' in images else sorted(images)[0],
            'cursor': 0,                      # 当前朝向索引
            'placed': {},                     # {(p, shape, idx): offs}
            'groups': {},                     # {(p, shape, idx): gid}
            'next_gid': 1,
            'name': '',
            'name_active': False,
            'confirm_overwrite': False,
            'fam_off': set(),                 # 被玩家关掉的缝族名
            'fam_sig': None,                  # 推导缓存签名
            'families': [],                   # [(name, coeffs, step, n_moves)]
            'cnt_sig': None,
            'move_info': (0, 0),              # (合法移动数, 可动块数)
            'ghost': None,                    # (世界多边形, 是否放得下)
            'undo': [],
            'redo': [],
            'panel_items': [],
            'shape_rows': [],
            'fam_rows': [],
            'bar_btns': [],
            'name_rect': None,
            'backup': None,
            'game': None,                   # 预览局（判「是否被中途换掉」）
        }
        # ---- 备份原局（退出时原样还原）----
        med['backup'] = {
            'game': self.game,
            'camera_x': self.camera_x,
            'camera_y': self.camera_y,
            'zoom': self.zoom,
            'triangle_mode': getattr(self, 'triangle_mode', False),
            'mi_mode': getattr(self, 'mi_mode', False),
            'numbered': getattr(self, 'numbered', False),
            'selected_gap': getattr(self, 'selected_gap', None),
            'selected_block': getattr(self, 'selected_block', None),
        }
        self._med = med
        self._med_active = True
        # 会话期清掉旧局的选中/拖拽态（块对象马上被换掉）
        self.selected_gap = None
        self.selected_block = None
        self.drag_following = False
        self.triangle_mode = False
        self.mi_mode = False
        self.numbered = False
        # ---- 预览 spec + 首块 ----
        spec = self._med_spec()
        seed_shape = med['shape']
        med['placed'][((0, 0), seed_shape, 0)] = med['images'][seed_shape][0]
        preview = EngineGame(Board(spec, self._med_blocks()), kind='__editor__')
        med['game'] = preview
        self.game = preview
        self._med_sync_after_edit(center=True)
        self._med_notify('搭积木编辑器：左键放置/删除，点缝捆绑/解绑，'
                         'R 旋转 F 镜像，U 撤销，命名后回车保存（ESC 退出）')

    def _med_close(self):
        """退出编辑器，原样还原进入前的局面与相机。"""
        med = self._med
        if med is None:
            self._med_active = False
            return
        bak = med.get('backup') or {}
        self.game = bak.get('game', self.game)
        self.camera_x = bak.get('camera_x', self.camera_x)
        self.camera_y = bak.get('camera_y', self.camera_y)
        self.zoom = bak.get('zoom', self.zoom)
        self.triangle_mode = bak.get('triangle_mode', False)
        self.mi_mode = bak.get('mi_mode', False)
        self.numbered = bak.get('numbered', False)
        self.selected_gap = bak.get('selected_gap')
        self.selected_block = bak.get('selected_block')
        self.drag_following = False
        self._med_active = False
        self._med = None
        self._med_panning = False
        self._med_pan_origin = None
        # 还原后清一次通用通道的原点缓存（spec 变了，缓存键自然失效，
        # 这里显式清是为了别留着一个已退出会话的 spec 引用）
        self._poly_origin_cache = None

    def _med_abandon(self):
        """会话被中途换局（菜单/命令面板/HTTP 开了新谜题）：就地收摊。

        此时 ``self.game`` 已经属于新谜题，备份里的旧局还原回去反而会
        把新局覆盖掉——所以**只丢会话状态，不还原**。检测点有两处
        （每帧绘制 + 每个事件），保证同一帧内就把浮层撤掉。
        """
        self._med_active = False
        self._med = None
        self._med_panning = False
        self._med_pan_origin = None
        self._poly_origin_cache = None

    # ==================================================================
    # 预览 spec / 局面
    # ==================================================================
    def _med_spec(self):
        """编辑器的预览 BoardSpec（**同一会话内是同一个对象**）。

        为什么 goal_blocks 只放一颗种子：``_poly_view_origin`` 按
        ``spec.goal_blocks`` 定世界原点，原点必须在会话内恒定，否则每放
        一块整个盘面跳一次。而 ``load_model`` 要求 tiles 非空且单一连通
        （编辑器中途完全可能摆出不连通的半成品）——所以 spec 的还原态
        恒为那一颗种子，**当前摆放**另走 ``Board(spec, blocks)``（Board
        不查连通性，只查重复键/在格/朝向合法）。

        朝向表收**整个形状库**的全部像：玩家随时可换形状，朝向集必须
        在会话内恒定，否则 spec 一换、原点缓存失效、盘面又跳。
        """
        med = self._med
        cached = med.get('spec')
        if cached is not None:
            return cached
        labels = {}
        for shape, imgs in med['images'].items():
            for idx, offs in enumerate(imgs):
                labels[f'{shape}:{idx}'] = offs
        # 缝族方向 = 库内全部形状边方向的并集（会话期恒定）。同名只留一个
        # （direction_name 按落屏角取 30° 倍数，理论上可能撞名）。
        dirs = set()
        for offs in labels.values():
            n = len(offs)
            for i in range(n):
                d = (offs[(i + 1) % n][0] - offs[i][0],
                     offs[(i + 1) % n][1] - offs[i][1])
                if d != (0, 0):
                    dirs.add(eg._primitive(d))
        seams, seen_names = [], set()
        for d in sorted(dirs):
            nm = eg.direction_name(d)
            if nm in seen_names:
                continue
            seen_names.add(nm)
            seams.append({'name': nm, 'coeffs': list(eg._normal_of(d)),
                          'step': list(d), 'rank': 'centroid'})
        seed = sorted(labels)[0]
        doc = {
            'schema': SCHEMA_BOARD,
            'name': '__editor_preview__',
            'basis': [[1.0, 0.0], [0.5, math.sqrt(3.0) / 2.0]],
            'pos_scale': 1,
            'solved': 'exact',
            'orientations': {lb: {'shape': 'x', 'off': [list(v) for v in offs]}
                             for lb, offs in labels.items()},
            'tiles': [{'p': [0, 0], 'o': seed}],
            'seams': seams,
        }
        spec = load_model(doc).spec
        med['spec'] = spec
        return spec

    def _med_blocks(self):
        """当前摆放 → Block 元组（供 Board / EngineGame 用）。"""
        med = self._med
        out = []
        for (p, shape, idx) in med['placed']:
            out.append(Block(tuple(p), f'{shape}:{idx}',
                             med['groups'].get((p, shape, idx), 0)))
        return tuple(out)

    def _med_orientations(self):
        """编辑器全部朝向表（label → 整数顶点），喂给 editor_geom。"""
        med = self._med
        out = {}
        for shape, imgs in med['images'].items():
            for idx, offs in enumerate(imgs):
                out[f'{shape}:{idx}'] = offs
        return out

    def _med_rebuild(self):
        """把当前摆放推进预览局（EngineGame 的 board setter 会重建块）。"""
        med = self._med
        # 清掉已删除块的捆绑记录（否则 next_gid 会白白上涨、存档里留噪声）
        med['groups'] = {k: g for k, g in med['groups'].items()
                         if k in med['placed']}
        self.game.board = Board(self._med_spec(), self._med_blocks())

    def _med_sync_after_edit(self, center=False):
        """编辑后统一收尾：重建局面 + 废缓存 + 需要时把盘面拉回视口。"""
        self._med_rebuild()
        med = self._med
        med['fam_sig'] = None
        med['cnt_sig'] = None
        med['ghost'] = None
        med['confirm_overwrite'] = False
        if center or not self._is_camera_valid():
            self.center_map()

    # ==================================================================
    # 撤销
    # ==================================================================
    def _med_undo_push(self):
        med = self._med
        med['undo'].append((dict(med['placed']), dict(med['groups']),
                            med['next_gid']))
        if len(med['undo']) > 60:
            med['undo'].pop(0)
        med['redo'].clear()

    def _med_undo(self):
        med = self._med
        if not med['undo']:
            self._med_notify('没有可撤销的编辑')
            return
        med['redo'].append((dict(med['placed']), dict(med['groups']),
                            med['next_gid']))
        placed, groups, nxt = med['undo'].pop()
        med['placed'], med['groups'], med['next_gid'] = placed, groups, nxt
        self._med_sync_after_edit()
        self._med_notify(f'已撤销（{len(med["placed"])} 块）')

    def _med_redo(self):
        med = self._med
        if not med['redo']:
            return
        med['undo'].append((dict(med['placed']), dict(med['groups']),
                            med['next_gid']))
        placed, groups, nxt = med['redo'].pop()
        med['placed'], med['groups'], med['next_gid'] = placed, groups, nxt
        self._med_sync_after_edit()

    # ==================================================================
    # 放置 / 删除 / 整形
    # ==================================================================
    def _med_place_at(self, wx, wy):
        """在世界坐标 (wx, wy) 处放置当前朝向；返回 True=放上了。"""
        med = self._med
        img = med['images'][med['shape']][med['cursor']]
        placed = med['placed']
        p = None
        cands = eg.snap_candidates((img,), placed, (wx, wy))
        if cands and cands[0][3] <= _SNAP_TOL:
            p = cands[0][0]          # 贴边吸附：整条边贴上，取最近候选
        else:
            p = self._med_free_point(img, (wx, wy), placed)
        if p is None:
            self._med_notify('这里放不下（与已有块重叠）')
            return False
        self._med_undo_push()
        med['placed'][(p, med['shape'], med['cursor'])] = img
        self._med_sync_after_edit()
        return True

    def _med_free_point(self, img, click_xy, placed):
        """自由落点：点击的最近整数格，重叠则在小窗里找最近的空格。"""
        li, lj = eg.to_lattice(click_xy)
        cx = sum(v[0] for v in img) / len(img)
        cy = sum(v[1] for v in img) / len(img)
        bi, bj = int(round(li - cx)), int(round(lj - cy))
        best = None
        for di in range(-_FREE_R, _FREE_R + 1):
            for dj in range(-_FREE_R, _FREE_R + 1):
                p = (bi + di, bj + dj)
                if not eg.can_place((img,), 0, p, placed):
                    continue
                d = ((p[0] + cx - li) ** 2 + (p[1] + cy - lj) ** 2)
                if best is None or d < best[0]:
                    best = (d, p)
        return None if best is None else best[1]

    def _med_delete_at(self, wx, wy):
        hit = eg.block_at(self._med['placed'], (wx, wy))
        if hit is None:
            return False
        med = self._med
        self._med_undo_push()
        del med['placed'][hit]
        med['groups'].pop(hit, None)
        self._med_sync_after_edit()
        return True

    # ---- 捆绑 / 解绑（点缝；与设计态同一交互）----
    def _med_seam_at(self, wx, wy, tol=0.22):
        """点击命中了哪条**块间共享边**（返回 (key_a, key_b) 或 None）。

        容差按晶格单位给：单位三角形的边中点离块内部也就半个边长，
        给太宽会和「点块删除」抢事件。
        """
        best = None
        for ka, kb, mid in eg.shared_edges(self._med['placed']):
            d = ((mid[0] - wx) ** 2 + (mid[1] - wy) ** 2) ** 0.5
            if d <= tol and (best is None or d < best[0]):
                best = (d, ka, kb)
        return None if best is None else (best[1], best[2])

    def _med_toggle_bundle(self, ka, kb):
        """点一条共享边：已同组 → 切开；否则 → 两侧整族并成一组。

        切的时候给 ``ka`` 一个新组号而不是清 0——它可能还和第三块同组，
        清 0 会把那条关系一起剪掉。保存时再把「只有一块的组」归一成 0
        （见 ``_med_build_doc``），文件里不会留下噪声。
        """
        med = self._med
        ga = med['groups'].get(ka, 0)
        gb = med['groups'].get(kb, 0)
        self._med_undo_push()
        if ga and gb and ga == gb:
            med['groups'][ka] = med['next_gid']
            med['next_gid'] += 1
            self._med_notify('已解开这一缝的捆绑')
        else:
            target = ga or gb or med['next_gid']
            if not (ga or gb):
                med['next_gid'] += 1
            members = {ka, kb}
            for k, g in med['groups'].items():
                if g and g in (ga, gb):
                    members.add(k)
            for k in members:
                med['groups'][k] = target
            self._med_notify(f'已捆绑：{len(members)} 块现在整组滑动')
        self._med_sync_after_edit()

    def _med_image_index(self, verts):
        """一组顶点（已归一化）在像元组里的下标；找不到回 None。"""
        target = eg.normalize(verts)
        for i, img in enumerate(self._med['images'][self._med['shape']]):
            if img == target:
                return i
        return None

    def _med_rotate(self, step=1):
        med = self._med
        imgs = med['images'][med['shape']]
        cur = imgs[med['cursor']]
        nxt = self._med_image_index(tuple(eg.rot60(v) for v in cur))
        if nxt is None:
            nxt = (med['cursor'] + step) % len(imgs)
        med['cursor'] = nxt
        med['ghost'] = None
        self._med_notify(f'朝向 {nxt + 1}/{len(imgs)}')

    def _med_mirror(self):
        med = self._med
        imgs = med['images'][med['shape']]
        cur = imgs[med['cursor']]
        nxt = self._med_image_index(tuple(eg.mirror(v) for v in cur))
        if nxt is None:
            return
        med['cursor'] = nxt
        med['ghost'] = None
        self._med_notify(f'朝向 {nxt + 1}/{len(imgs)}（镜像）')

    def _med_clear(self):
        med = self._med
        if not med['placed']:
            return
        self._med_undo_push()
        med['placed'].clear()
        med['groups'].clear()
        self._med_sync_after_edit()
        self._med_notify('已清空（U 可撤销）')

    # ==================================================================
    # 缝族推导 / 状态
    # ==================================================================
    def _med_families(self):
        """推导缝族（按摆放签名缓存；编辑后签名变才重算）。"""
        med = self._med
        sig = frozenset(med['placed'])
        if med['fam_sig'] != sig:
            blocks = self._med_blocks()
            med['families'] = eg.derive_families(blocks, self._med_orientations())
            med['fam_sig'] = sig
        return med['families']

    def _med_enabled_families(self):
        """玩家开关之后的缝族（保存与计数都用这份）。"""
        return [f for f in self._med_families() if f[0] not in self._med['fam_off']]

    def _med_move_info(self):
        """(合法移动数, 可动块数)（按签名+开关缓存）。

        ⚠️ 计数必须走 ``editor_geom.move_stats``（按**当前开着的族**另造
        spec）：预览 spec 收的是形状库全部方向的族，拿它数会让缝族开关
        完全失效（2026-10-25 实测：关掉 d120 后移动数一分不降）。
        """
        med = self._med
        fams = self._med_enabled_families()
        sig = (frozenset(med['placed']), frozenset(f[0] for f in fams))
        if med['cnt_sig'] != sig:
            med['move_info'] = eg.move_stats(
                self._med_blocks(), self._med_orientations(), fams)
            med['cnt_sig'] = sig
        return med['move_info']

    def _med_gate(self):
        """保存门：≥1 块 + 单一连通 + ≥2 颗可动。返回 (ok, 原因)。"""
        med = self._med
        blocks = self._med_blocks()
        if not blocks:
            return False, '空盘无处保存（至少放一块）'
        if not eg.is_connected(blocks, self._med_orientations()):
            return False, '当前摆放不连通（保存要求整片单一连通）'
        if not self._med_enabled_families():
            return False, '没有可用的缝族（这条形状滑不动，是冻形）'
        n_moves, n_movable = self._med_move_info()
        if n_moves < 1:
            return False, '当前形态是冻形（一步都滑不动），无法保存'
        if n_movable < 2:
            return False, (f'只有 {n_movable} 颗滑块动得了（≥2 才存）'
                           '——试着摆成条带，或给紧凑的簇加挂一块')
        return True, ''

    # ==================================================================
    # 保存
    # ==================================================================
    def _med_build_doc(self, name):
        """合成模型文档（与 experiments/_gen_model_shatter.py 同款结构）。"""
        med = self._med
        orients = {}
        for shape, imgs in med['images'].items():
            for idx, offs in enumerate(imgs):
                orients[f'{shape}:{idx}'] = {
                    'shape': shape,
                    'off': [[int(x), int(y)] for x, y in offs]}
        tiles = []
        # 「只有一块的组」归一成 0：切捆绑时给的是新组号，剪完会留下一堆
        # 单人组，写进文件纯粹是噪声（引擎语义上组 of 1 == 无组）。
        counts = {}
        for g in med['groups'].values():
            if g:
                counts[g] = counts.get(g, 0) + 1
        for (p, shape, idx) in sorted(med['placed'],
                                      key=lambda k: (k[0], k[1], k[2])):
            t = {'p': [int(p[0]), int(p[1])], 'o': f'{shape}:{idx}'}
            gid = med['groups'].get((p, shape, idx), 0)
            if gid and counts.get(gid, 0) >= 2:
                t['g'] = int(gid)
            tiles.append(t)
        seams = [{'name': nm, 'coeffs': [int(cf[0]), int(cf[1])],
                  'step': [int(st[0]), int(st[1])], 'rank': 'centroid'}
                 for (nm, cf, st, _n) in self._med_enabled_families()]
        return {
            'schema': SCHEMA_BOARD,
            'name': name,
            'title': name,
            'basis': [[1.0, 0.0], [0.5, math.sqrt(3.0) / 2.0]],
            'pos_scale': 1,
            'solved': 'exact',
            'shapes_ref': 'shapes.json',
            'orientations': orients,
            'tiles': tiles,
            'seams': seams,
        }

    def _med_save(self):
        """保存成模型文件并热注册。返回 True=已保存（可接着试玩）。"""
        med = self._med
        name = med['name'].strip()
        if not name:
            med['name_active'] = True
            self._med_notify('先给模型起个名字（字母/数字/_/-）')
            return False
        if not all(c.isalnum() or c in '_-' for c in name):
            self._med_notify('名字只能含字母、数字、_ 和 -')
            return False
        from engine.model_loader import DEFAULT_MODEL_DIR
        path = os.path.join(DEFAULT_MODEL_DIR, f'{name}.json')
        if os.path.exists(path) and not med['confirm_overwrite']:
            med['confirm_overwrite'] = True
            self._med_notify(f'「{name}」已存在——再按一次[保存]确认覆盖')
            return False
        med['confirm_overwrite'] = False
        ok, why = self._med_gate()
        if not ok:
            self._med_notify(f'保存被拒：{why}')
            return False
        doc = self._med_build_doc(name)
        try:
            os.makedirs(DEFAULT_MODEL_DIR, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
                f.write('\n')
            from engine import model_registry
            model_registry.reload(name)
        except Exception as exc:      # noqa: BLE001 —— 通知要把原因带给玩家
            self._med_notify(f'保存失败：{exc}')
            return False
        try:
            self._refresh_puzzle_presets()
        except Exception:
            pass
        n = len(med['placed'])
        self._med_notify(
            f'已保存「{name}」（{n} 块、{len(doc["seams"])} 条缝族）：'
            f'谜题 → 模型谜题 ▸ 里可开局，ESC 退出编辑器')
        return True

    def _med_playtest(self):
        """[试玩]：保存是前置（过门才存），存完直接开局。

        开局走 ``new_model_puzzle``——它会换掉 ``self.game``。开局成功即
        「会话期被换局」，**当场就地收摊**（``_med_abandon``：只丢会话状
        态、不还原备份——还原会把刚开的新局覆盖掉）。不等下一帧绘制：否
        则那一帧编辑器浮层会画在新局上面，且调用方（菜单/按钮）返回后立
        即检查 ``med_active`` 会看到还没收摊的中间态。
        """
        med = self._med
        ok, why = self._med_gate()
        if not ok:
            self._med_notify(f'还试玩不了：{why}')
            return
        name = med['name'].strip()
        if not name:
            med['name_active'] = True
            self._med_notify('试玩也要先起个名字（保存是试玩的前置）')
            return
        if not self._med_save():
            return
        if self.new_model_puzzle(name, 1):
            self._med_abandon()

    # ==================================================================
    # 布局几何（绘制与命中共用同一套矩形）
    # ==================================================================
    def _med_panel_rect(self):
        return pygame.Rect(_PANEL_X, self.menu_bar_height + 10,
                           _PANEL_W, self._med_panel_height())

    def _med_panel_height(self):
        med = self._med
        h = 30                                    # 标题
        h += 22 + 30 * len(med['images'])         # 形状区
        h += 22 + 66                              # 朝向预览
        h += 22 + 24 * max(1, len(self._med_families()))
        h += 22 + 5 * 18                          # 状态区
        return h + 12

    def _med_bar_rect(self):
        w = self.screen_width - self.right_panel_width
        return pygame.Rect(0, self.screen_height - self.status_bar_height
                           - 8 - _BAR_H, w, _BAR_H)

    # ==================================================================
    # 事件
    # ==================================================================
    def _med_handle_event(self, event) -> bool:
        """编辑器事件入口（挂在 handle_annotation_event 之后）。

        返回 True = 已消费。顶栏菜单区与已展开下拉**放行**给常规菜单
        逻辑（与标注画布同口径）；模态对话框开着时不抢。
        """
        if not self._med_active:
            return False
        med = self._med
        if med is None or self.game is not med.get('game'):
            # 会话期被换了局（菜单/命令面板/HTTP 开了新谜题）：收摊
            self._med_abandon()
            return False
        if self._ann_modal_conflict():
            return False
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.pos[1] < self.menu_bar_height:
                return False
            if (getattr(self, 'show_file_menu', False)
                    or getattr(self, 'show_edit_menu', False)
                    or getattr(self, 'show_puzzle_menu', False)
                    or getattr(self, 'show_macro_menu', False)):
                return False
        if event.type == pygame.KEYDOWN:
            return self._med_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._med_mouse_down(event)
        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self._med_panning = False
                self._med_pan_origin = None
            return True
        if event.type == pygame.MOUSEMOTION:
            return self._med_mouse_motion(event)
        if event.type == pygame.MOUSEWHEEL:
            return self._med_wheel(event)
        return True     # 模态会话：其余事件一并吞掉

    def _med_key(self, event) -> bool:
        med = self._med
        k = event.key
        if med['name_active']:
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                med['name_active'] = False
                self._med_save()
            elif k == pygame.K_ESCAPE:
                med['name_active'] = False
            elif k == pygame.K_BACKSPACE:
                med['name'] = med['name'][:-1]
            else:
                ch = event.unicode
                if ch and len(ch) == 1 and (ch.isalnum() or ch in '_-'):
                    med['name'] += ch
            return True
        ctrl = bool(event.mod & pygame.KMOD_CTRL) if hasattr(event, 'mod') else False
        if k == pygame.K_ESCAPE:
            self._med_close()
        elif k == pygame.K_r:
            self._med_rotate()
        elif k == pygame.K_f:
            self._med_mirror()
        elif k == pygame.K_u or (ctrl and k == pygame.K_z):
            self._med_undo()
        elif ctrl and k == pygame.K_y:
            self._med_redo()
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            med['name_active'] = True
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._med_clear()
        return True

    def _med_mouse_down(self, event) -> bool:
        med = self._med
        x, y = event.pos
        if self._med_bar_rect().collidepoint(x, y):
            return self._med_bar_click(x, y)
        if self._med_panel_rect().collidepoint(x, y):
            return self._med_panel_click(x, y)
        if event.button == 2:
            self._med_panning = True
            self._med_pan_origin = (x, y)
            return True
        if event.button != 1:
            med['ghost'] = None
            return True
        wx, wy = self.screen_to_world(x, y)
        seam = self._med_seam_at(wx, wy)
        if seam is not None:
            self._med_toggle_bundle(*seam)
            return True
        if not self._med_delete_at(wx, wy):
            self._med_place_at(wx, wy)
        return True

    def _med_mouse_motion(self, event) -> bool:
        med = self._med
        if self._med_panning and self._med_pan_origin is not None:
            ox, oy = self._med_pan_origin
            self.camera_x += event.pos[0] - ox
            self.camera_y += event.pos[1] - oy
            self._med_pan_origin = event.pos
            return True
        x, y = event.pos
        if y < self.menu_bar_height or self._med_panel_rect().collidepoint(x, y) \
                or self._med_bar_rect().collidepoint(x, y):
            med['ghost'] = None
            return True
        wx, wy = self.screen_to_world(x, y)
        img = med['images'][med['shape']][med['cursor']]
        placed = med['placed']
        cands = eg.snap_candidates((img,), placed, (wx, wy))
        if cands and cands[0][3] <= _SNAP_TOL:
            poly = cands[0][2]
        else:
            p = self._med_free_point(img, (wx, wy), placed)
            poly = None if p is None else eg.poly_of(p, img)
        med['ghost'] = None if poly is None else tuple(poly)
        return True

    def _med_wheel(self, event) -> bool:
        factor = 1.1 if event.y > 0 else 0.9
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        mx, my = pygame.mouse.get_pos()
        wx = (mx - self.camera_x) / self.zoom
        wy = (my - self.camera_y) / self.zoom
        self.zoom = new_zoom
        self.camera_x = mx - wx * self.zoom
        self.camera_y = my - wy * self.zoom
        return True

    # ---- 面板 / 工具栏点击 ----
    def _med_panel_click(self, x, y) -> bool:
        med = self._med
        for rect, shape in med['shape_rows']:
            if rect.collidepoint(x, y):
                if shape == med['shape']:
                    self._med_rotate()
                else:
                    med['shape'] = shape
                    med['cursor'] = 0
                    med['ghost'] = None
                    self._med_notify(f'形状切换到 {shape}')
                return True
        for rect, fname in med['fam_rows']:
            if rect.collidepoint(x, y):
                if fname in med['fam_off']:
                    med['fam_off'].discard(fname)
                else:
                    med['fam_off'].add(fname)
                med['cnt_sig'] = None
                return True
        return True

    def _med_bar_click(self, x, y) -> bool:
        med = self._med
        if med['name_rect'] is not None and med['name_rect'].collidepoint(x, y):
            med['name_active'] = True
            return True
        for rect, action in med['bar_btns']:
            if not rect.collidepoint(x, y):
                continue
            if action == 'exit':
                self._med_close()
            elif action == 'clear':
                self._med_clear()
            elif action == 'undo':
                self._med_undo()
            elif action == 'save':
                self._med_save()
            elif action == 'play':
                self._med_playtest()
            return True
        return True

    # ==================================================================
    # 绘制
    # ==================================================================
    def _med_draw_overlay(self):
        """编辑器浮层（在 draw_annotation_mode 之后画；块本体走通用通道）。"""
        if not self._med_active:
            return
        if self._med is None or self.game is not self._med.get('game'):
            # 同一帧内被换局：撤掉浮层（详见 _med_abandon）
            self._med_abandon()
            return
        self._med_draw_ghost()
        self._med_draw_groups()
        self._med_draw_panel()
        self._med_draw_bar()

    # ---- 小工具 ----
    def _med_font(self, size):
        from GUI import _gui_safe_font
        cache = getattr(self, '_med_font_cache', None)
        if cache is None:
            cache = {}
            self._med_font_cache = cache
        f = cache.get(size)
        if f is None:
            f = _gui_safe_font('SimHei', size)
            cache[size] = f
        return f

    def _med_mini_pts(self, offs, box, origin):
        """形状 → 面板里的小预览多边形（等比缩放进 box 内）。"""
        xs = [eg.to_plane(v)[0] for v in offs]
        ys = [eg.to_plane(v)[1] for v in offs]
        w = max(max(xs) - min(xs), 1e-6)
        h = max(max(ys) - min(ys), 1e-6)
        s = min(box[0] / w, box[1] / h) * 0.82
        cx, cy = origin[0] + box[0] / 2, origin[1] + box[1] / 2
        mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        out = []
        for v in offs:
            px, py = eg.to_plane(v)
            out.append((cx + (px - mx) * s, cy + (py - my) * s))
        return out

    def _med_draw_groups(self):
        """捆绑组的视觉反馈：橙色描边 + 组内缝加粗，读成一块刚体。

        不走 ``_draw_bandaged_groups_poly``：那条路要 ``spec.lattice`` 的
        邻接偏移表，而编辑器预览 spec 的 ``orient_steps`` 是自环占位
        （几何邻接由 ``components`` 钩子给，与偏移表无关）。在浮层里按
        几何直接画更诚实，也顺带避开「占位表把组内桥接全吞」的坑。
        """
        med = self._med
        by_gid = {}
        for k, g in med['groups'].items():
            if g and k in med['placed']:
                by_gid.setdefault(g, []).append(k)
        by_gid = {g: ks for g, ks in by_gid.items() if len(ks) >= 2}
        if not by_gid:
            return
        color = (235, 150, 40)
        lw = max(2, int(2 * self.zoom))
        for _gid, keys in sorted(by_gid.items()):
            sub = {k: med['placed'][k] for k in keys}
            for k in keys:
                pts = [self.world_to_screen(x, y)
                       for (x, y) in eg.poly_of(k[0], med['placed'][k])]
                pygame.draw.polygon(self.screen, color, pts, lw)
            # 组内共享边加粗：剪断某条缝，那条线就消失——「这族还连着吗」
            # 的直接反馈
            for _ka, _kb, seg in eg.shared_edge_segments(sub):
                pygame.draw.line(self.screen, color,
                                 self.world_to_screen(*seg[0]),
                                 self.world_to_screen(*seg[1]), lw + 1)

    def _med_draw_ghost(self):
        med = self._med
        poly = med.get('ghost')
        if not poly:
            return
        pts = [self.world_to_screen(x, y) for (x, y) in poly]
        if len(pts) < 3:
            return
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (120, 200, 255, 90), pts)
        pygame.draw.polygon(surf, (200, 230, 255, 220), pts, 2)
        self.screen.blit(surf, (0, 0))

    def _med_draw_panel(self):
        med = self._med
        c = self.colors
        rect = self._med_panel_rect()
        pygame.draw.rect(self.screen, c['menu_bg'], rect)
        pygame.draw.rect(self.screen, c['dialog_border'], rect, 1)
        pad = 10
        x0 = rect.x + pad
        y = rect.y + 10
        f_title = self._med_font(17)
        f_sec = self._med_font(14)
        f_item = self._med_font(15)
        f_small = self._med_font(12)

        def _text(txt, font, color, x, yy):
            s = font.render(txt, True, color)
            self.screen.blit(s, (x, yy))
            return s.get_height()

        _text('搭积木编辑器', f_title, c['dialog_title'], x0, y)
        y += 26
        # ---- 形状 ----
        _text('形状（点一下切换）', f_sec, c['menu_selected'], x0, y)
        y += 20
        med['shape_rows'] = []
        for shape in sorted(med['images']):
            row = pygame.Rect(rect.x + 6, y - 3, rect.width - 12, 30)
            med['shape_rows'].append((row, shape))
            if shape == med['shape']:
                pygame.draw.rect(self.screen, c['selection_bg'], row)
            imgs = med['images'][shape]
            pts = self._med_mini_pts(imgs[0], (26, 26), (row.x + 8, row.y + 2))
            pygame.draw.polygon(self.screen, c['block'], pts)
            pygame.draw.polygon(self.screen, c['border'], pts, 1)
            _text(f'{shape}（{len(imgs)} 像）', f_item, c['menu_text'],
                  row.x + 42, row.y + 6)
            y += 30
        y += 8
        # ---- 朝向 ----
        _text('朝向（R 旋转 / F 镜像）', f_sec, c['menu_selected'], x0, y)
        y += 20
        imgs = med['images'][med['shape']]
        cur = imgs[med['cursor']]
        box = pygame.Rect(rect.x + 10, y, 60, 56)
        pts = self._med_mini_pts(cur, (56, 52), (box.x, box.y))
        pygame.draw.polygon(self.screen, c['block_selected'], pts)
        pygame.draw.polygon(self.screen, c['border'], pts, 1)
        _text(f'{med["cursor"] + 1} / {len(imgs)}', f_item, c['menu_text'],
              box.right + 12, box.y + 20)
        y += 62
        # ---- 缝族 ----
        fams = self._med_families()
        _text('缝族（点一下开关）', f_sec, c['menu_selected'], x0, y)
        y += 20
        med['fam_rows'] = []
        if not fams:
            _text('（没有推导出活缝）', f_small, c['status_text'], x0, y)
            y += 22
        for (nm, _cf, _st, n_mv) in fams:
            row = pygame.Rect(rect.x + 6, y - 2, rect.width - 12, 24)
            med['fam_rows'].append((row, nm))
            on = nm not in med['fam_off']
            if on:
                pygame.draw.rect(self.screen, c['selection_bg'], row)
            mark = '✓' if on else '✗'
            _text(f'{mark} {nm}', f_item,
                  c['menu_text'] if on else c['status_text'], row.x + 6, row.y + 3)
            _text(f'{n_mv} 移', f_small, c['status_text'],
                  row.right - 44, row.y + 6)
            y += 24
        y += 8
        # ---- 状态 ----
        _text('状态', f_sec, c['menu_selected'], x0, y)
        y += 20
        n = len(med['placed'])
        blocks = self._med_blocks()
        conn = eg.is_connected(blocks, self._med_orientations()) if blocks else False
        n_moves, n_movable = self._med_move_info()
        n_grp = len({g for g in med['groups'].values() if g})
        rows = [
            f'块数 {n}',
            f'连通 {"是" if conn else "否"}',
            f'捆绑组 {n_grp}',
            f'可动滑块 {n_movable}（合法移动 {n_moves}）',
            f'缝族 {len(self._med_enabled_families())}/{len(fams)} 开',
        ]
        for t in rows:
            _text(t, f_small, c['status_text'], x0, y)
            y += 18

    def _med_draw_bar(self):
        med = self._med
        c = self.colors
        bar = self._med_bar_rect()
        pygame.draw.rect(self.screen, c['status_bg'], bar)
        pygame.draw.line(self.screen, c['separator'],
                         (bar.x, bar.y), (bar.right, bar.y), 1)
        f = self._med_font(15)
        f_small = self._med_font(12)
        cy = bar.y + 12
        # 名字输入框
        label = f.render('名字', True, c['status_text'])
        self.screen.blit(label, (bar.x + 12, cy + 6))
        nx = bar.x + 12 + label.get_width() + 8
        nr = pygame.Rect(nx, cy + 2, 170, 26)
        med['name_rect'] = nr
        pygame.draw.rect(self.screen,
                         c['input_active'] if med['name_active'] else c['input_bg'], nr)
        pygame.draw.rect(self.screen, c['dialog_border'], nr, 1)
        nm = med['name'] or ''
        shown = nm if nm else '（未命名）'
        col = c['input_text'] if nm else c['status_text']
        self.screen.blit(f.render(shown, True, col), (nr.x + 6, nr.y + 4))
        if med['name_active']:
            tw = f.size(nm)[0]
            if pygame.time.get_ticks() % 1000 < 550:
                pygame.draw.line(self.screen, c['input_text'],
                                 (nr.x + 6 + tw, nr.y + 5),
                                 (nr.x + 6 + tw, nr.y + 21), 1)
        # 按钮
        med['bar_btns'] = []
        bx = nr.right + 16
        for caption, action in (('退出 ESC', 'exit'), ('清空', 'clear'),
                                ('撤销 U', 'undo'), ('保存 ↵', 'save'),
                                ('试玩 ▶', 'play')):
            w = max(64, f.size(caption)[0] + 22)
            br = pygame.Rect(bx, cy + 2, w, 26)
            med['bar_btns'].append((br, action))
            hover = br.collidepoint(*pygame.mouse.get_pos())
            pygame.draw.rect(self.screen,
                             c['button_hover'] if hover else c['button_bg'], br)
            pygame.draw.rect(self.screen, c['dialog_border'], br, 1)
            self.screen.blit(f.render(caption, True, c['dialog_title']),
                             (br.x + 11, br.y + 4))
            bx += w + 8
        # 右侧状态
        n = len(med['placed'])
        n_moves, n_movable = self._med_move_info()
        txt = f'{n} 块 · 可动 {n_movable} · 合法移动 {n_moves}'
        if med['confirm_overwrite']:
            txt += ' · 再按一次[保存]覆盖'
        s = f_small.render(txt, True, c['status_text'])
        self.screen.blit(s, (bar.right - s.get_width() - 12, bar.y + 30))
        hint = '左键放置/删除 · 点缝捆绑/解绑 · R 旋转 · F 镜像 · 滚轮缩放 · 中键拖动'
        s2 = f_small.render(hint, True, c['status_text'])
        self.screen.blit(s2, (bar.right - s2.get_width() - 12, cy + 6))
