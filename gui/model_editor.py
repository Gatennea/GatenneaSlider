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

操作（2026-10-25 用户定案：左右键分工，拖动移动）
--------------------------------------------------
* **左键点空白** = 放置当前朝向（优先贴边吸附，吸附不到就自由落在最近
  格点）。按下没移动才算「点击」，移动超过 4px 就变成「拖空白 = 平移画布」。
* **左键按住已有块拖动** = 移动它（在捆绑组里就整组一起动）。整组按**整数
  格**平移，所以只要拖到相邻就自动贴合——「坐标差一点自动拼上」是晶格
  对齐的自然结果，不靠额外的吸附半径。与组外块重叠时不应用（块停在最后
  一个合法位置）。
* **右键点块** = 删除；**右键点两块之间的缝** = 捆绑/解绑（同组整组滑动）。
  左键只负责「放」和「拖」——以前左键点块是删、点缝是捆，想贴着已有块
  放一块时常常变成删除或捆绑，看着像「点了没反应」（2026-10-25 用户实测）。
* **R 旋转 / F 镜像**：鼠标悬停在某块上 → 转**那一块**（绕自身重心，找
  最近的无重叠落点）；悬空 → 转**将要放置**的朝向。
* 滚轮缩放、中键（或左键拖空白）平移；ESC 退出。
* U / Ctrl+Z 撤销；Enter 激活名字框、再回车保存；[试玩] 存完直接开局。
* 侧栏「盘面」：**打开模型…** 把已保存的模型读回来续编（朝向按几何
  匹配，label 名不要求同款）；**清空捆绑** 一键解掉所有组（「全捆再
  逐缝剪」会留下无缝相连的余组，UI 上无缝可点，只能在这里清）。
* 保存门只在**保存时**检查（整片连通 + ≥2 颗可动）：玩家自己一眼能看出
  摆得对不对，不必边摆边拦。

"""
import json
import math
import os

import pygame

from engine import editor_geom as eg
from engine.adapter import EngineGame
from engine.board import Block, Board
from engine.model_loader import SCHEMA_BOARD, load_model
from gui import editor_chrome as chrome

# 布局常量（设计像素）
_PANEL_W = 218
_PANEL_X = 10
# 工具条高：与格子画布（gui/annotation.py 的 design 视图，82）同高，
# 两个编辑器切换时工具条不上下跳（用户要求「同一套 UI」）。
_BAR_H = 82
# 贴边吸附的命中容差（晶格单位）：点得离候选块够近才吸附，否则自由落点
_SNAP_TOL = 0.75
# 自由落点的搜索半径（格）——以**盘面 bbox 中心**为圆心，不是以点击处为
# 圆心：滑块游戏的盘面是一个整体，新块只能长在已有积木旁边。若以点击处
# 为圆心，用户缩得太小点屏幕边缘就会把锚点放到几千格外，Board 据此建出
# 7000×4000 的 matrix——先卡半分钟再 MemoryError（2026-10-25 用户实测）。
_FREE_R = 4
# 锚点 sanity 护栏（格）：距盘面 bbox 中心超过这个距离的块拒绝进预览局。
# 正常编辑永远到不了（自由落点被 _FREE_R 管着）；这是给「打开模型」读入
# 手写文件、或未来新路径兜底的，防的仍是那种巨大 matrix。
_MED_MAX_REACH = 64
# 预览局的形态名。**这是个哨兵，不是一个模型名**：它没有 models/*.json，
# 也不该出现在任何存档里——``save_config``（退出自动存）与 ``save_to_file``
# 都要按它跳过/拦下，载入端遇到它按「上次退出停在编辑器里」安静忽略。
# 2026-10-25 用户实测：编辑器里退出 → temp_history 写下
# ``type: '__editor__'`` → 下次启动报「存档需要模型 '__editor__'，但它没有
# 安装」，每次启动都弹一次，且所有从 temp_history 恢复的测试跟着连锁假红。
PREVIEW_KIND = '__editor__'


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
        from engine.model_loader import load_shape_lib
        lib = load_shape_lib()
        if not lib:
            self._med_notify('models/shapes.json 里没有可用形状，编辑器无从搭起')
            return
        bad = sorted({it['lattice'] for it in lib.values()
                      if it['lattice'] not in eg.LATTICES})
        if bad:
            self._med_notify(f'形状库里有未知晶格族 {bad}，'
                             f'可用：{sorted(eg.LATTICES)}（改 shapes.json 的 '
                             'lattice 字段）')
            return
        # 每形状按**自己声明的族**生成朝向像（三角 D6 / 方形 D4）
        opts = {}
        for sname, item in lib.items():
            imgs = eg.images_of(item['verts'], item['lattice'])
            if imgs:
                opts[sname] = imgs
        if not opts:
            self._med_notify('形状库全是空形状，编辑器无从搭起')
            return
        # 默认族：有三角就用三角（老习惯），否则取字典序第一族
        avail = sorted({lib[s]['lattice'] for s in opts})
        lattice = 'tri' if 'tri' in avail else avail[0]
        info = eg.lattice_info(lattice)
        images = {s: opts[s] for s in opts if lib[s]['lattice'] == lattice}
        med = {
            'lib': opts,                      # 全库 {形状名: 像元组}
            'lib_lattice': {s: lib[s]['lattice'] for s in opts},
            'lattice': lattice,               # 当前晶格族（tri / square）
            'basis': info['basis'],           # 族基（会话期恒定）
            'deg': info['deg'],               # 缝族命名角粒度
            'lat_rows': [],                   # 面板「晶格」节热区
            'images': images,                 # 当前族的 {形状名: 像元组}
            # 默认形状优先 'tri'（单位等边三角，最「搭积木」的那块）；
            # 库里没有才退回字典序第一个
            'shape': self._med_default_shape(images),
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
            'hover': None,                    # 鼠标下的块键（高亮 + R/F 作用对象）
            'press': None,                    # 左键按下中的手势（见 _med_press_down）
            'undo': [],
            'redo': [],
            'panel_items': [],
            'shape_rows': [],
            'fam_rows': [],
            'bar_btns': [],
            'name_rect': None,
            'backup': None,
            'game': None,                   # 预览局（判「是否被中途换掉」）
            'open_list': None,              # 「打开模型」模态列表（None=关）
            'act_rows': [],                 # 面板「盘面」节按钮热区
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
            'ann_home_sub': getattr(self, '_ann_home_sub', None),
        }
        # ---- 与标注/设计画布互斥（2026-10-25 创造模式重组后从创造首页进）----
        # 玩家入口：模式开关 → 创造 → ② 还原态设计 → 搭积木。此时
        # annotation_mode/create_mode 可能都开着（创造首页工具条），工具条
        # 与事件由 _med_active 闸门让路（annotation.py 的
        # handle_annotation_event / draw_annotation_mode 开头两处放行）；
        # 这里只收掉可能残留的**子对话框/设计会话**，防两个模态状态机叠加。
        # game_mode 不动——退出编辑器后 draw_annotation_mode 依 create_mode
        # 自动恢复创造首页，体验连贯。
        if getattr(self, '_ann_design_session', False):
            self._ann_design_cancel()
        self._ann_sub_dialog = None
        self._ann_home_sub = None
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
        preview = EngineGame(Board(spec, self._med_blocks()), kind=PREVIEW_KIND)
        med['game'] = preview
        self.game = preview
        self._med_sync_after_edit(center=True)
        self._med_notify('搭积木：左键放、按住拖块移动；右键删块、'
                         '右键点缝＝捆绑；R/F 转向（悬停某块＝转那块），'
                         'U 撤销，命名后回车保存（ESC 退出）')

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
        # 创造首页的展开态还原（从「② 还原态设计」二级进来的，退出回到那一级）
        self._ann_home_sub = bak.get('ann_home_sub')
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
            nm = eg.direction_name(d, med['basis'], med['deg'])
            if nm in seen_names:
                continue
            seen_names.add(nm)
            seams.append({'name': nm, 'coeffs': list(eg._normal_of(d)),
                          'step': list(d), 'rank': 'centroid'})
        seed = sorted(labels)[0]
        doc = {
            'schema': SCHEMA_BOARD,
            'name': '__editor_preview__',
            'basis': [list(r) for r in med['basis']],
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
        # sanity 护栏：锚点离盘面 bbox 中心太远就拒绝重建。正常编辑到不了
        # （自由落点被 _FREE_R 管着、吸附受已有块约束）；这是给「打开模型」
        # 读入手写文件等路径兜底——PreviewBoard.update_matrix 会按坐标跨度
        # 建 matrix，几千格外的锚点能建出 7000×4000（先卡死再 MemoryError，
        # 2026-10-25 用户实测）。宁可拒收也不让主循环卡死。
        if med['placed']:
            vs = [v for k, offs in med['placed'].items() for v in
                  ((k[0][0] + o[0], k[0][1] + o[1]) for o in offs)]
            ci = (min(v[0] for v in vs) + max(v[0] for v in vs)) / 2.0
            cj = (min(v[1] for v in vs) + max(v[1] for v in vs)) / 2.0
            far = [k[0] for k in med['placed']
                   if abs(k[0][0] - ci) > _MED_MAX_REACH
                   or abs(k[0][1] - cj) > _MED_MAX_REACH]
            if far:
                self._med_notify(
                    f'有 {len(far)} 个块离盘面太远（>{_MED_MAX_REACH} 格），'
                    '已拒绝刷新——撤销或删掉它们')
                return
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
    def _med_place_at(self, gx, gy):
        """在几何坐标 (gx, gy) 处放置当前朝向；返回 True=放上了。

        ⚠️ 参数是**几何单位**（1 = 一格），不是屏幕/世界像素——换算在
        事件入口（``_med_screen_to_geom``）统一做掉。
        """
        med = self._med
        imgs = med['images'][med['shape']]
        idx = med['cursor']
        img = imgs[idx]
        placed = med['placed']
        p = None
        # ⚠️ 贴边吸附要试**形状的全部朝向**，不能只试当前朝向：三角晶格上
        # 同朝向的两块只共享顶点不共享边（▲(0,0) 与 ▲(1,0)），拿单一朝向
        # 去贴永远拼不成连通的一片（2026-10-25 实测「块是散的」）。贴哪条
        # 边决定朝向，本来就该由几何选，玩家按 R 只影响**自由落点**那块。
        cands = eg.snap_candidates(imgs, placed, (gx, gy), basis=self._med['basis'])
        if cands and cands[0][3] <= _SNAP_TOL:
            p, idx = cands[0][0], cands[0][1]
            img = imgs[idx]
        else:
            p = self._med_free_point(img, (gx, gy), placed)
        if p is None:
            self._med_notify('这里放不下（与已有块重叠）')
            return False
        self._med_undo_push()
        med['placed'][(p, med['shape'], idx)] = img
        self._med_sync_after_edit()
        return True

    def _med_free_point(self, img, click_xy, placed):
        """自由落点：盘面 bbox 中心附近最近的非重叠格（见 _FREE_R 注释）。

        ⚠️ 搜索圆心必须是**盘面中心**（已有块物理顶点的 bbox 中心；空盘回
        原点），不能是点击处：以点击处为圆心时，最小缩放下点一下屏幕边缘
        就能把锚点放到 (7398, -3107) 这种几千格外，预览局据此建 7000×4000
        matrix——先卡半分钟再 MemoryError（2026-10-25 用户实测复现）。
        滑块盘面是整体，想摆到别处请中键拖动镜头，块始终长在积木旁。
        """
        li, lj = eg.to_lattice(click_xy, self._med['basis'])
        cx = sum(v[0] for v in img) / len(img)
        cy = sum(v[1] for v in img) / len(img)
        # 盘面物理顶点 bbox（空盘 = 原点一个点）
        if placed:
            vs = [v for k, offs in placed.items() for v in
                  ((k[0][0] + o[0], k[0][1] + o[1]) for o in offs)]
            imin, imax = min(v[0] for v in vs), max(v[0] for v in vs)
            jmin, jmax = min(v[1] for v in vs), max(v[1] for v in vs)
        else:
            imin = imax = jmin = jmax = 0
        # 先按点击处算锚点（让**形状中心**落在点击格），再把它夹到
        # 「盘面 bbox 外扩 _FREE_R」——既有界（不建巨大 matrix），又尽量
        # 贴近用户点的方向（点在右边就长在右边，不是甩回盘面中心）。
        bi = int(round(li - cx))
        bj = int(round(lj - cy))
        bi = max(imin - _FREE_R, min(bi, imax + _FREE_R))
        bj = max(jmin - _FREE_R, min(bj, jmax + _FREE_R))
        best = None
        for di in range(-_FREE_R, _FREE_R + 1):
            for dj in range(-_FREE_R, _FREE_R + 1):
                p = (bi + di, bj + dj)
                if not eg.can_place((img,), 0, p, placed, self._med['basis']):
                    continue
                d = ((p[0] + cx - li) ** 2 + (p[1] + cy - lj) ** 2)
                if best is None or d < best[0]:
                    best = (d, p)
        return None if best is None else best[1]

    def _med_delete_at(self, gx, gy):
        hit = eg.block_at(self._med['placed'], (gx, gy), self._med['basis'])
        if hit is None:
            return False
        med = self._med
        self._med_undo_push()
        del med['placed'][hit]
        med['groups'].pop(hit, None)
        if med.get('hover') == hit:
            med['hover'] = None
        self._med_sync_after_edit()
        return True

    # ---- 左键手势：点放 / 拖块 / 拖空白平移 ------------------------------
    # 按下时只**记账**，松手才判定是「点击」还是「拖动」：同一颗左键
    # 既要放、又要拖，靠位移阈值分流（4px）。
    _PRESS_SLOP = 4.0

    def _med_press_down(self, gx, gy, sx, sy):
        """左键按下：登记手势（拖块 / 待放置）。"""
        med = self._med
        med['ghost'] = None
        key = eg.block_at(med['placed'], (gx, gy), self._med['basis'])
        if key is not None:
            med['press'] = self._med_move_press(key, gx, gy, sx, sy)
            return
        med['press'] = {'kind': 'place', 'grab': (gx, gy),
                        'screen': (sx, sy), 'moved': False,
                        'cam': (self.camera_x, self.camera_y)}

    def _med_move_press(self, key, gx, gy, sx, sy, moved=False):
        """构造「拖块」手势（组内则整组）。``grab`` 记按下点，位移从它算。

        ``items`` 是 ``[(当前键, 按下时的锚点, 顶点)]``：拖动会改键，旧键
        作废，所以基准（按下时的锚点）与块身份必须分开存——每次 apply 都
        从基准 + 位移重算，块不会被越拖越偏。
        """
        med = self._med
        gid = med['groups'].get(key, 0)
        keys = ([k for k in med['placed']
                 if gid and med['groups'].get(k, 0) == gid] if gid else [])
        if key not in keys:
            keys = [key]
        return {'kind': 'move', 'key': key, 'keys': keys,
                'items': [(k, tuple(k[0]), med['placed'][k]) for k in keys],
                'grab': (gx, gy), 'screen': (sx, sy),
                'moved': moved, 'pushed': False, 'delta': (0, 0)}

    def _med_press_move(self, sx, sy, gx, gy):
        """左键移动：超阈值后分派成拖动块 / 平移画布。"""
        med = self._med
        pr = med.get('press')
        if pr is None:
            return False
        if not pr['moved']:
            dx = sx - pr['screen'][0]
            dy = sy - pr['screen'][1]
            if dx * dx + dy * dy < self._PRESS_SLOP ** 2:
                return True
            pr['moved'] = True
            if pr['kind'] == 'place':
                pr['kind'] = 'pan'      # 空白处拖动 = 平移画布（不放置）
        if pr['kind'] == 'pan':
            self.camera_x = pr['cam'][0] + (sx - pr['screen'][0])
            self.camera_y = pr['cam'][1] + (sy - pr['screen'][1])
            return True
        if pr['kind'] == 'move':
            self._med_drag_to(gx, gy)
        return True

    def _med_press_up(self, gx, gy):
        """左键松开：按手势种类收尾。

        单击（无论落在空白还是**已有块里**）都是「放一块」——点在块里就是
        「接着这块搭」，贴边吸附把新块放到最近空位；只有拖起来过的手势才
        算移动，不会误放。
        """
        med = self._med
        pr = med.pop('press', None)
        if pr is None:
            return
        if pr['kind'] in ('place', 'move') and not pr['moved']:
            self._med_place_at(gx, gy)
        elif pr['kind'] == 'move':
            # 拖出去又拖回原位：撤销栈里那条等于空操作，摘掉
            if pr['pushed'] and all(p0 == k[0] for k, p0, _o in pr['items']):
                if med['undo']:
                    med['undo'].pop()
            med['hover'] = eg.block_at(med['placed'], (gx, gy), self._med['basis'])

    def _med_drag_to(self, gx, gy):
        """拖动中：整组按**整数格**平移（同晶格 ⇒ 自动贴合，无需再吸附）。

        位移取整是关键——块锚点永远落在整数格上，两块只要相邻就共享整条
        边，「坐标差一点自动拼上」是这么来的，不是靠额外的吸附半径。

        目标位置与组外块重叠 / 键冲突时**不应用**：块停在最后一个合法位置，
        松手即定格（不会把盘面拖成重叠状态）。
        """
        med = self._med
        pr = med['press']
        di = int(round(gx - pr['grab'][0]))
        dj = int(round(gy - pr['grab'][1]))
        if (di, dj) == pr['delta']:
            return
        items = pr['items']
        cur_keys = [it[0] for it in items]
        others = {k: v for k, v in med['placed'].items() if k not in cur_keys}
        moves = {}
        for k, p0, offs in items:
            p = (p0[0] + di, p0[1] + dj)
            nk = (p, k[1], k[2])
            if nk in others or nk in moves:
                return
            if not eg.can_place((offs,), 0, p, others, self._med['basis']):
                return
            moves[k] = nk
        if not pr['pushed']:
            self._med_undo_push()
            pr['pushed'] = True
        gmap = {k: med['groups'].pop(k) for k in cur_keys if k in med['groups']}
        offs_by_key = {k: offs for k, _p0, offs in items}
        for k in cur_keys:
            med['placed'].pop(k, None)
        for k, nk in moves.items():
            med['placed'][nk] = offs_by_key[k]
        for k, g in gmap.items():
            med['groups'][moves[k]] = g
        # 键换了：基准仍绑定「按下时的锚点」，下一帧从它重算（不会累积漂移）
        pr['items'] = [(moves[k], p0, offs) for k, p0, offs in items]
        pr['keys'] = list(moves.values())
        pr['delta'] = (di, dj)
        # 轻量收尾：拖动中不居中（中心会跟着块跑，手感像甩镜头）
        self._med_rebuild()
        med['fam_sig'] = None
        med['cnt_sig'] = None
        med['hover'] = None

    # ---- 捆绑 / 解绑（点缝；与设计态同一交互）----
    def _med_seam_at(self, wx, wy, tol=0.22):
        """点击命中了哪条**块间共享边**（返回 (key_a, key_b) 或 None）。

        容差按晶格单位给：单位三角形的边中点离块内部也就半个边长，
        给太宽会和「点块删除」抢事件。
        """
        best = None
        for ka, kb, mid in eg.shared_edges(self._med['placed'], self._med['basis']):
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

    def _med_unbundle_all(self):
        """清空全部捆绑组（块不动）。

        存在的理由：「全捆 → 逐缝剪」会留下**无缝相连**的余组（剪开只摘
        ``ka`` 侧、``kb`` 保留旧组号），那些组在 UI 上没有任何缝可点，
        玩家会被卡死。给一个一键清空，U 可撤销。
        """
        med = self._med
        if not any(med['groups'].values()):
            self._med_notify('当前没有捆绑组')
            return
        self._med_undo_push()
        med['groups'] = {}
        self._med_sync_after_edit()
        self._med_notify('已清空全部捆绑（U 可撤销）')

    # ---- 打开既有模型续编 ----
    # 编辑器预览 spec 的坐标基（三角晶格）；basis/pos_scale 不同的模型
    # 读回来会按另一套几何画，直接拒载并说明，不留一个错位的盘。

    def _med_open_model_list(self):
        """弹出「打开模型」列表（models/ 下已注册的模型，续编用）。"""
        from engine import model_registry
        try:
            loaded = model_registry.loaded()
        except Exception as exc:           # noqa: BLE001 —— 通知要带原因
            self._med_notify(f'读不到模型列表：{exc}')
            return
        items = sorted((nm, m.title, len(m.spec.goal_blocks))
                       for nm, m in loaded.items())
        if not items:
            self._med_notify('models/ 下还没有可打开的模型（先保存一个）')
            return
        self._med['name_active'] = False     # 弹列表 = 名字框失焦
        self._med['open_list'] = {'items': items, 'rects': []}

    def _med_load_model(self, name):
        """把已注册模型读回编辑器（续编）。返回 True=载入成功。

        朝向按**几何**匹配而不是 label 字符串：模型文件的 label 是文件
        自带的（编辑器自己写的才是 ``'shape:idx'``），手写文件可能叫任何
        名字——``normalize(off)`` 与形状库的像相等即同一个朝向，对不上
        的块跳过并计数。
        """
        from engine import model_registry
        try:
            m = model_registry.loaded(name)
        except KeyError:
            self._med_notify(f'模型 {name!r} 不可用')
            return False
        doc = m.doc or {}
        basis = doc.get('basis')
        lat = None
        if isinstance(basis, (list, tuple)) and len(basis) == 2:
            lat = eg.lattice_of_basis(basis)
        if lat is None:
            self._med_notify(f'「{name}」的坐标基认不出属于哪个晶格'
                             f'（{basis!r}），暂不支持续编')
            return False
        if lat != self._med['lattice']:
            # 文件是另一族：盘面还有东西就不能换（换族要清盘）
            if len(self._med['placed']) > 1:
                self._med_notify(
                    f'「{name}」属于{eg.lattice_info(lat)["label"]}晶格，'
                    f'当前盘面是{eg.lattice_info(self._med["lattice"])["label"]}'
                    '——先[清空]（或切晶格）再打开')
                return False
            self._med_set_lattice(lat)
        if int(doc.get('pos_scale', 1)) != 1:
            self._med_notify(f'「{name}」的 pos_scale 不是 1，暂不支持续编')
            return False
        orients = doc.get('orientations') or {}
        index = {}
        for shape, imgs in self._med['images'].items():
            for idx, offs in enumerate(imgs):
                index[offs] = (shape, idx)
        placed, groups, skipped = {}, {}, 0
        for t in doc.get('tiles') or []:
            try:
                p = (int(t['p'][0]), int(t['p'][1]))
                off = orients[t['o']]['off']
            except (KeyError, TypeError, ValueError, IndexError):
                skipped += 1
                continue
            hit = index.get(eg.normalize(off))
            if hit is None or (p, hit[0], hit[1]) in placed:
                skipped += 1
                continue
            placed[(p, hit[0], hit[1])] = self._med['images'][hit[0]][hit[1]]
            gid = int(t.get('g', 0) or 0)
            if gid:
                groups[(p, hit[0], hit[1])] = gid
        if not placed:
            self._med_notify(f'「{name}」里没有一块能对上形状库，载入失败')
            return False
        med = self._med
        self._med_undo_push()
        med['placed'] = placed
        med['groups'] = groups
        med['next_gid'] = max(list(groups.values()) + [0]) + 1
        med['name'] = name
        med['name_active'] = False
        # 缝族开关按文件里写了的族（续编语义：推导出但文件没有的族默认关）
        on = {s.get('name') for s in (doc.get('seams') or []) if s.get('name')}
        med['fam_off'] = {f[0] for f in self._med_families() if f[0] not in on}
        self._med_sync_after_edit(center=True)
        msg = f'已载入「{name}」（{len(placed)} 块'
        if groups:
            msg += f'、{len(set(groups.values()))} 个捆绑组'
        if skipped:
            msg += f'；{skipped} 块对不上形状库被跳过'
        self._med_notify(msg + '）')
        return True

    @staticmethod
    def _med_default_shape(images):
        """默认形状：三角族用 tri、方形族用 square，其余取字典序第一。

        不能一律取 sorted()[0]：方形族里 'rt45' 排在 'square' 前，一进编辑
        器手里就攥着半个正方形，用户第一块就懵。
        """
        for want in ('tri', 'square'):
            if want in images:
                return want
        return sorted(images)[0]

    def _med_rot_v(self, v):
        """格坐标的「转一次」（三角 60° / 方形 90°）。

        名字带 _v（vertex）是必须的：``_med_mirror`` 已经是「F 键镜像」
        的方法名，用同名会把它盖掉，F 键一按就 TypeError。
        """
        return eg.rot90(v) if self._med['lattice'] == 'square' else eg.rot60(v)

    def _med_mirror_v(self, v):
        """格坐标的 x 轴反射（按族选，与 basis 一致才跑不坏晶格）。"""
        return (eg.mirror_sq(v) if self._med['lattice'] == 'square'
                else eg.mirror(v))

    def _med_set_lattice(self, name):
        """切晶格族（三角 ↔ 方形）。只有空盘（或只剩种子）才允许。

        为什么必须清盘：一个模型文件只有一个 ``basis``，方形块和三角块
        的坐标系根本不可比（单位长度、基向量夹角都不同），同一盘面混放
        没有合法 basis——这不是 UI 限制，是格式约束。所以换族 = 重开
        一张空盘。
        """
        med = self._med
        if name == med['lattice']:
            return
        avail = sorted({med['lib_lattice'][s] for s in med['lib']})
        if name not in avail:
            self._med_notify(f'形状库里没有 {name} 族（可用：{avail}）')
            return
        if len(med['placed']) > 1:
            self._med_notify(
                f'盘上已有 {len(med["placed"])} 块——换晶格得先[清空]：'
                '两族的坐标基不同，不能混在一个盘面里')
            return
        info = eg.lattice_info(name)
        med['lattice'] = name
        med['basis'] = info['basis']
        med['deg'] = info['deg']
        med['images'] = {s: med['lib'][s] for s in med['lib']
                         if med['lib_lattice'][s] == name}
        med['placed'].clear()
        med['groups'].clear()
        med['undo'].clear()
        med['redo'].clear()
        med['hover'] = None
        med['ghost'] = None
        med['press'] = None
        med['fam_sig'] = None
        med['cnt_sig'] = None
        med['spec'] = None            # basis 变了，预览 spec 必须重建
        med['shape'] = self._med_default_shape(med['images'])
        med['cursor'] = 0
        seed = med['shape']
        med['placed'][((0, 0), seed, 0)] = med['images'][seed][0]
        preview = EngineGame(Board(self._med_spec(), self._med_blocks()),
                             kind=PREVIEW_KIND)
        med['game'] = preview
        self.game = preview
        self._med_sync_after_edit(center=True)
        self._med_notify(
            f'已切到{info["label"]}晶格（{len(med["images"])} 种形状：'
            f'{"、".join(sorted(med["images"]))}）')

    def _med_image_index(self, verts):
        """一组顶点（已归一化）在像元组里的下标；找不到回 None。"""
        target = eg.normalize(verts)
        for i, img in enumerate(self._med['images'][self._med['shape']]):
            if img == target:
                return i
        return None

    def _med_rotate(self, step=1):
        key = self._med.get('hover')
        if key is not None and key in self._med['placed']:
            self._med_turn_block(key, mirror=False)
            return
        med = self._med
        imgs = med['images'][med['shape']]
        cur = imgs[med['cursor']]
        nxt = self._med_image_index(
            tuple(self._med_rot_v(v) for v in cur))
        if nxt is None:
            nxt = (med['cursor'] + step) % len(imgs)
        med['cursor'] = nxt
        med['ghost'] = None
        self._med_notify(f'朝向 {nxt + 1}/{len(imgs)}')

    def _med_mirror(self):
        key = self._med.get('hover')
        if key is not None and key in self._med['placed']:
            self._med_turn_block(key, mirror=True)
            return
        med = self._med
        imgs = med['images'][med['shape']]
        cur = imgs[med['cursor']]
        nxt = self._med_image_index(
            tuple(self._med_mirror_v(v) for v in cur))
        if nxt is None:
            return
        med['cursor'] = nxt
        med['ghost'] = None
        self._med_notify(f'朝向 {nxt + 1}/{len(imgs)}（镜像）')

    def _med_turn_block(self, key, mirror=False):
        """原地转/镜像**已有的一块**（鼠标悬停在那块上按 R / F）。

        锚点重算：保持「块的重心」不动（``p + 顶点均值``），再取最近的无
        重叠位置。晶格旋转是整系数变换，重心未必落回格点，所以只能取整后
        在 ±2 格里找最接近原重心且不重叠的落点——找不到就拒绝（提示「转不
        开」），绝不把两块叠在一起。
        """
        med = self._med
        offs = med['placed'][key]
        shape, old_idx = key[1], key[2]
        xform = self._med_mirror_v if mirror else self._med_rot_v
        new = eg.normalize(tuple(xform(v) for v in offs))
        try:
            idx = med['images'][shape].index(new)
        except ValueError:
            self._med_notify('这个形状没有镜像/旋转后的像')
            return
        if idx == old_idx:
            self._med_notify('这块是对称的，转过去还是它自己')
            return
        # 原重心（格坐标，含锚点）
        cx = sum(key[0][0] + o[0] for o in offs) / len(offs)
        cy = sum(key[0][1] + o[1] for o in offs) / len(offs)
        ncx = sum(o[0] for o in new) / len(new)
        ncy = sum(o[1] for o in new) / len(new)
        base = (int(round(cx - ncx)), int(round(cy - ncy)))
        others = {k: v for k, v in med['placed'].items() if k != key}
        best = None
        for di in range(-2, 3):
            for dj in range(-2, 3):
                q = (base[0] + di, base[1] + dj)
                nk = (q, shape, idx)
                if nk in others:
                    continue
                if not eg.can_place((new,), 0, q, others, self._med['basis']):
                    continue
                d = (q[0] + ncx - cx) ** 2 + (q[1] + ncy - cy) ** 2
                if best is None or d < best[0]:
                    best = (d, nk)
        if best is None:
            self._med_notify('这块转不开（新朝向在附近放不下）')
            return
        self._med_undo_push()
        g = med['groups'].pop(key, 0)
        del med['placed'][key]
        med['placed'][best[1]] = new
        if g:
            med['groups'][best[1]] = g
        med['hover'] = best[1]
        self._med_sync_after_edit()
        self._med_notify(f'已{"镜像" if mirror else "旋转"}这块'
                         f'（{best[1][1]}:{best[1][2]}）')


    def _med_clear(self):
        med = self._med
        if not med['placed']:
            return
        self._med_undo_push()
        med['placed'].clear()
        med['groups'].clear()
        med['hover'] = None
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
            med['families'] = eg.derive_families(blocks, self._med_orientations(),
                                                 med['basis'])
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
                self._med_blocks(), self._med_orientations(), fams,
                med['basis'])
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
            'basis': [list(r) for r in med['basis']],
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
    def _med_screen_to_geom(self, sx, sy):
        """屏幕 → **几何单位**（1 = 一格）。

        渲染通道的世界坐标约定是 ``world = 几何 × cell_size``（见
        ``renderer._polygon_view``：cell_size 只在这里乘一次，缩放由
        ``world_to_screen`` 负责）。编辑器所有的几何量（吸附、落点、
        命中、缝的中点、幽灵多边形）都以**几何单位**为准，所以事件入口
        必须在 ``screen_to_world`` 之后**再除以 cell_size**。

        ⚠️ 漏这步的后果（2026-10-25 用户实测「只显示一个滑块」）：点击
        位置被当成几何坐标（相当于放大 60 倍），第二块直接落到屏幕外，
        画面上永远只剩种子那一块；同时点块删除、点缝捆绑、幽灵预览全部
        失配（它们拿世界坐标去比几何多边形）。
        """
        wx, wy = self.screen_to_world(sx, sy)
        s = float(self.cell_size) or 1.0
        return wx / s, wy / s

    def _med_geom_to_screen(self, gx, gy):
        """几何单位 → 屏幕（``_med_screen_to_geom`` 的逆）。"""
        s = float(self.cell_size) or 1.0
        return self.world_to_screen(gx * s, gy * s)

    def _med_panel_rect(self):
        return pygame.Rect(_PANEL_X, self.menu_bar_height + 10,
                           _PANEL_W, self._med_panel_height())

    def _med_panel_height(self):
        med = self._med
        h = 30                                    # 标题
        h += 22 + 32                              # 晶格节（一行按钮）
        h += 22 + 30 * len(med['images'])         # 形状区
        h += 22 + 66                              # 朝向预览
        h += 22 + 24 * max(1, len(self._med_families()))  # 缝族
        h += 22 + 5 * 18                          # 状态区
        h += 8 + 20 + 2 * 30                      # 盘面节（打开/清捆绑）
        return h + 12

    def _med_bar_rect(self):
        """工具条矩形：走共用骨架，让出左面板（格子画布那边没有左面板）。"""
        return chrome.bar_rect(self, _BAR_H, left=_PANEL_X + _PANEL_W + 8)

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
            elif event.button == 1 and med.get('press') is not None:
                gx, gy = self._med_screen_to_geom(*event.pos)
                self._med_press_up(gx, gy)
            return True
        if event.type == pygame.MOUSEMOTION:
            return self._med_mouse_motion(event)
        if event.type == pygame.MOUSEWHEEL:
            return self._med_wheel(event)
        return True     # 模态会话：其余事件一并吞掉

    def _med_open_list_click(self, x, y) -> bool:
        """「打开模型」列表的点击：命中一项载入，点外面取消。"""
        med = self._med
        lst = med.get('open_list')
        if lst is None:
            return False
        for rect, name in lst['rects']:
            if rect.collidepoint(x, y):
                med['open_list'] = None
                self._med_load_model(name)
                return True
        med['open_list'] = None            # 点外面 = 取消
        return True

    def _med_key(self, event) -> bool:
        med = self._med
        k = event.key
        if med.get('open_list') is not None:
            # 列表模态：只认 ESC（取消），其余键一并吞掉
            if k == pygame.K_ESCAPE:
                med['open_list'] = None
            return True
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
        """左键＝点放/拖块、右键＝删、中键＝平移（见 _med_press_down）。"""
        med = self._med
        x, y = event.pos
        if med.get('open_list') is not None:
            # 「打开模型」列表模态中：一切点击只归列表（命中/取消）
            return self._med_open_list_click(x, y)
        if self._med_bar_rect().collidepoint(x, y):
            return self._med_bar_click(x, y)
        if self._med_panel_rect().collidepoint(x, y):
            return self._med_panel_click(x, y)
        if event.button == 2:
            self._med_panning = True
            self._med_pan_origin = (x, y)
            return True
        gx, gy = self._med_screen_to_geom(x, y)
        if event.button == 3:
            # 右键 = 「缝 / 块」：点缝捆绑（解绑），点块删除。放在右键上
            # 是为了让左键**只**管放和拖——否则想贴着已有块放一块时，落点
            # 正好压在缝上就变成捆绑，看着像「点了没放上」（2026-10-25 实测）。
            med['ghost'] = None
            seam = self._med_seam_at(gx, gy)
            if seam is not None:
                self._med_toggle_bundle(*seam)
            else:
                self._med_delete_at(gx, gy)
            return True
        if event.button != 1:
            med['ghost'] = None
            return True
        self._med_press_down(gx, gy, x, y)
        return True

    def _med_mouse_motion(self, event) -> bool:
        med = self._med
        if med.get('open_list') is not None:
            med['ghost'] = None            # 列表模态中不产幽灵预览
            return True
        if self._med_panning and self._med_pan_origin is not None:
            ox, oy = self._med_pan_origin
            self.camera_x += event.pos[0] - ox
            self.camera_y += event.pos[1] - oy
            self._med_pan_origin = event.pos
            return True
        x, y = event.pos
        gx, gy = self._med_screen_to_geom(x, y)
        if med.get('press') is not None:
            self._med_press_move(x, y, gx, gy)
            return True
        if y < self.menu_bar_height or self._med_panel_rect().collidepoint(x, y) \
                or self._med_bar_rect().collidepoint(x, y):
            med['ghost'] = None
            med['hover'] = None
            return True
        # 悬停高亮（R/F 转的就是这一块）
        med['hover'] = eg.block_at(med['placed'], (gx, gy), self._med['basis'])
        imgs = med['images'][med['shape']]
        placed = med['placed']
        # 预览必须与放置同口径：试**全部朝向**（贴哪条边决定朝向）
        cands = eg.snap_candidates(imgs, placed, (gx, gy), basis=self._med['basis'])
        if cands and cands[0][3] <= _SNAP_TOL:
            poly = cands[0][2]
        else:
            p = self._med_free_point(imgs[med['cursor']], (gx, gy), placed)
            poly = None if p is None else eg.poly_of(p, imgs[med['cursor']], self._med['basis'])
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
        for rect, lname in med['lat_rows']:
            if rect.collidepoint(x, y):
                self._med_set_lattice(lname)
                return True
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
        for rect, action in med.get('act_rows') or []:
            if rect.collidepoint(x, y):
                if action == 'open':
                    self._med_open_model_list()
                elif action == 'unbundle':
                    self._med_unbundle_all()
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
        self._med_draw_hover()
        self._med_draw_panel()
        self._med_draw_bar()
        self._med_draw_open_list()

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
        xs = [eg.to_plane(v, self._med['basis'])[0] for v in offs]
        ys = [eg.to_plane(v, self._med['basis'])[1] for v in offs]
        w = max(max(xs) - min(xs), 1e-6)
        h = max(max(ys) - min(ys), 1e-6)
        s = min(box[0] / w, box[1] / h) * 0.82
        cx, cy = origin[0] + box[0] / 2, origin[1] + box[1] / 2
        mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        out = []
        for v in offs:
            px, py = eg.to_plane(v, self._med['basis'])
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
                pts = [self._med_geom_to_screen(x, y)
                       for (x, y) in eg.poly_of(k[0], med['placed'][k], self._med['basis'])]
                pygame.draw.polygon(self.screen, color, pts, lw)
            # 组内共享边加粗：剪断某条缝，那条线就消失——「这族还连着吗」
            # 的直接反馈
            for _ka, _kb, seg in eg.shared_edge_segments(sub, self._med['basis']):
                pygame.draw.line(self.screen, color,
                                 self._med_geom_to_screen(*seg[0]),
                                 self._med_geom_to_screen(*seg[1]), lw + 1)

    def _med_draw_ghost(self):
        med = self._med
        poly = med.get('ghost')
        if not poly:
            return
        pts = [self._med_geom_to_screen(x, y) for (x, y) in poly]
        if len(pts) < 3:
            return
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (120, 200, 255, 90), pts)
        pygame.draw.polygon(surf, (200, 230, 255, 220), pts, 2)
        self.screen.blit(surf, (0, 0))

    def _med_draw_hover(self):
        """悬停块高亮：R/F 转的是它，拖动/右键删也从这里看出「选中的是哪块」。"""
        med = self._med
        key = med.get('hover')
        if key is None or key not in med['placed']:
            return
        if med.get('press') is not None:
            return                       # 拖动/按压中不画，免得跟目标位置打架
        pts = [self._med_geom_to_screen(x, y)
               for (x, y) in eg.poly_of(key[0], med['placed'][key], self._med['basis'])]
        if len(pts) < 3:
            return
        pygame.draw.polygon(self.screen, (255, 210, 90), pts, 2)

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
        # ---- 晶格 ----
        _text('晶格（空盘可切）', f_sec, c['menu_selected'], x0, y)
        y += 20
        med['lat_rows'] = []
        avail = [n for n in eg.LATTICES
                 if n in {med['lib_lattice'][s] for s in med['lib']}]
        bw = max(1, (rect.width - 16) // max(1, len(avail)))
        for i, lname in enumerate(avail):
            row = pygame.Rect(rect.x + 6 + i * bw, y - 2, bw - 4, 26)
            med['lat_rows'].append((row, lname))
            on = lname == med['lattice']
            hover = row.collidepoint(*pygame.mouse.get_pos())
            pygame.draw.rect(
                self.screen,
                c['selection_bg'] if on
                else (c['button_hover'] if hover else c['button_bg']), row)
            pygame.draw.rect(self.screen,
                             c['border'] if on else c['dialog_border'], row,
                             2 if on else 1)
            _text(eg.lattice_info(lname)['label'], f_item,
                  c['dialog_title'], row.x + 10, row.y + 4)
        y += 32
        # ---- 形状 ----
        _text('形状（点一下切换）', f_sec, c['menu_selected'], x0, y)
        y += 20
        med['shape_rows'] = []
        for shape in med['images']:
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
        _text('朝向（R/F；悬停某块＝转那块）', f_sec, c['menu_selected'], x0, y)
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
            mark = '[开]' if on else '[关]'
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
        y += 8
        # ---- 盘面 ----
        _text('盘面', f_sec, c['menu_selected'], x0, y)
        y += 20
        med['act_rows'] = []
        for caption, action in (('打开模型…', 'open'), ('清空捆绑', 'unbundle')):
            row = pygame.Rect(rect.x + 6, y - 2, rect.width - 12, 26)
            med['act_rows'].append((row, action))
            hover = row.collidepoint(*pygame.mouse.get_pos())
            pygame.draw.rect(self.screen,
                             c['button_hover'] if hover else c['button_bg'], row)
            pygame.draw.rect(self.screen, c['dialog_border'], row, 1)
            _text(caption, f_item, c['dialog_title'], row.x + 10, row.y + 4)
            y += 30

    def _med_draw_open_list(self):
        """「打开模型」模态列表（编辑器内自绘，不另开对话框）。"""
        med = self._med
        lst = med.get('open_list')
        if lst is None:
            return
        c = self.colors
        f_title = self._med_font(17)
        f_item = self._med_font(15)
        f_small = self._med_font(12)
        items = lst['items']
        w, rh = 380, 30
        h = 40 + len(items) * rh + 30
        panel = pygame.Rect(0, 0, w, h)
        panel.center = (self.screen_width // 2, self.screen_height // 2)
        shade = pygame.Surface((self.screen_width, self.screen_height),
                               pygame.SRCALPHA)
        shade.fill((0, 0, 0, 90))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, c['menu_bg'], panel)
        pygame.draw.rect(self.screen, c['dialog_border'], panel, 1)
        t = f_title.render('打开模型（载入续编）', True, c['dialog_title'])
        self.screen.blit(t, (panel.x + 14, panel.y + 10))
        y = panel.y + 40
        lst['rects'] = []
        for name, title, n in items:
            row = pygame.Rect(panel.x + 8, y, panel.width - 16, rh - 4)
            lst['rects'].append((row, name))
            hover = row.collidepoint(*pygame.mouse.get_pos())
            if hover:
                pygame.draw.rect(self.screen, c['selection_bg'], row)
            s = f_item.render(f'{title}（{n} 块）', True, c['menu_text'])
            self.screen.blit(s, (row.x + 8, row.y + 4))
            s2 = f_small.render(name, True, c['status_text'])
            self.screen.blit(s2, (row.right - s2.get_width() - 8, row.y + 7))
            y += rh
        hint = f_small.render('点一项载入；点外面或 ESC 取消', True,
                              c['status_text'])
        self.screen.blit(hint, (panel.x + 14, panel.bottom - 24))

    def _med_draw_bar(self):
        """工具条：右对齐悬浮圆角条，与格子画布**同一套外观**。

        外观走 ``gui/editor_chrome``（两个还原态编辑器共用骨架），两行布局
        与画布 design 视图对齐：

          第 1 行  名字输入 + [撤销 U] [清空]
          第 2 行  操作提示（左） + [退出] [试玩 ▶] [保存 ↵]（右）

        命中矩形仍记在 ``med['bar_btns']`` / ``med['name_rect']``，事件侧
        （``_med_bar_click`` / ``_med_mouse_down``）不用跟着改。
        """
        med = self._med
        c = self.colors
        bar = self._med_bar_rect()
        f = self._med_font(15)
        f_small = self._med_font(12)
        n = len(med['placed'])
        n_moves, n_movable = self._med_move_info()

        # 条上方的小标题：身份 + 关键计数（与画布的标题行同位置同字号）
        title = (f'搭积木 · 还原状态设计（自由板型） · {n} 块 · '
                 f'可动 {n_movable} · 合法移动 {n_moves}')
        if med['confirm_overwrite']:
            title += ' · 再按一次[保存]覆盖'
        chrome.shell(self, bar, title, font=f_small)

        row1 = bar.y + 8
        row2 = bar.y + 48
        bh = 26
        med['bar_btns'] = []

        # ---- 第 2 行右侧：主操作（从右往左：退出 / 试玩 / 保存）----
        rx = bar.right - 8
        for caption, action in (('退出 ESC', 'exit'), ('试玩 ▶', 'play'),
                                ('保存 ↵', 'save')):
            w = max(56, chrome.btn_width(caption, f, 20))
            br = pygame.Rect(rx - w, row2, w, bh)
            rx = br.left - 8
            chrome.btn(self, br, caption, font=f)
            med['bar_btns'].append((br, action))

        # ---- 第 1 行：名字输入 + [撤销][清空]（窄窗口下名字框让位）----
        label = f.render('名字', True, c['status_text'])
        self.screen.blit(label, (bar.x + 12, row1 + 6))
        nx = bar.x + 12 + label.get_width() + 8
        tail = 16 + max(56, chrome.btn_width('撤销 U', f, 20)) + 8 \
            + max(56, chrome.btn_width('清空', f, 20))
        name_w = max(96, min(170, bar.right - 8 - nx - tail))
        nr = pygame.Rect(nx, row1, name_w, bh)
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
                cx = min(nr.right - 4, nr.x + 6 + tw)
                pygame.draw.line(self.screen, c['input_text'],
                                 (cx, nr.y + 5), (cx, nr.y + 21), 1)
        bx = nr.right + 12
        for caption, action in (('撤销 U', 'undo'), ('清空', 'clear')):
            w = max(56, chrome.btn_width(caption, f, 20))
            br = pygame.Rect(bx, row1, w, bh)
            chrome.btn(self, br, caption, font=f)
            med['bar_btns'].append((br, action))
            bx = br.right + 8

        # ---- 第 2 行左侧：操作提示（空间不够就不画，别糊成一团）----
        hint = '左键放 · 拖块移动 · 右键删/缝 · R/F 转向 · 滚轮缩放'
        hs = f_small.render(hint, True, c['status_text'])
        if hs.get_width() <= rx - (bar.x + 12) - 8:
            self.screen.blit(hs, (bar.x + 12, row2 + 6))
