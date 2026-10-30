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
* **右键拖动** = 框选（2026-10-28 加，为复制服务）。右键的动作**推迟到松手**
  才执行：按下后位移超过 4px 就改判成框选，没超过就还是原来的「删块 /
  捆绑」。所以纯右键点击的行为一字未改。
* **R 旋转 / F 镜像**：鼠标悬停在某块上 → 转**那一块**（绕自身重心，找
  最近的无重叠落点）；悬空 → 转**将要放置**的朝向。
* 滚轮缩放、中键（或左键拖空白）平移；ESC 退出。
* U / Ctrl+Z 撤销；Enter 激活名字框、再回车保存；[试玩] 存完直接开局。
* 侧栏「盘面」：**打开模型…** 把已保存的模型读回来续编（朝向按几何
  匹配，label 名不要求同款）；**清空捆绑** 一键解掉所有组（「全捆再
  逐缝剪」会留下无缝相连的余组，UI 上无缝可点，只能在这里清）。
* **复制 / 粘贴 / 阵列**（2026-10-28 加；目的 = 把一个密铺单元复制成更大的
  相同密铺图形）：右键拖框选出一个单元 → Ctrl+C 或 [复制] → Ctrl+V 或
  [粘贴]，浮动副本跟着鼠标走（放得下绿、放不下红），左键点一下落位 →
  [阵列] 选尺寸，按刚才那一份贴出来的间距整片铺开。副本内部保留捆绑，但
  **每份副本各起新号段**，不会一次剪缝把所有副本一起剪开。
  阵列周期**不靠猜形状**：方向一 = 玩家手动贴的那一份的真实位移（贴得下才
  记得下来），方向二 = 它在**世界坐标**里转一个晶格步长（三角 60°、方形
  90°）。⚠️ 这里必须用 ``eg.rotate_vector`` 而不是 ``eg.rot60`` / ``rot90``
  ——后两者是标准基的整系数矩阵，套在碎三角那种自定义基 (0.866,0)/(0,0.5)
  上根本不是 60° 方向（实测把位移 (24,0) 算成 (0,24)，一份都铺不出来）。
  每份都过 ``can_place``，铺不下就跳过：圈错了也只会少铺几份，不会画出
  重叠盘面。
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

# 左侧竖排图标工具栏（几何画板风，2026-10-28 重做）
_TOOL_W = 34                       # 图标方块边长
_TOOL_GAP = 5                      # 图标间距
_TOOL_GROUP_GAP = 8                # 分组间隔
_TOOLBAR_X = 10                    # 工具栏左缘
_TOOLBAR_TOP_PAD = 22              # 顶部标题留白
# 工具定义：(label, shortcut, kind)  kind='tool' 切换激活 / 'action' 瞬时执行
MED_TOOLS = {
    'select': ('选择', '', 'tool'),
    'place': ('放置', '', 'tool'),
    'erase': ('删除', 'Del', 'tool'),
    'band': ('捆绑', '', 'tool'),
    'copy': ('复制', 'C', 'action'),
    'paste': ('粘贴', 'V', 'action'),
    'array': ('阵列', '', 'action'),
    'rotate': ('旋转', 'R', 'action'),
    'mirror': ('镜像', 'F', 'action'),
}
MED_TOOL_ORDER = ['select', 'place', 'erase', 'band',
                  'copy', 'paste', 'array', 'rotate', 'mirror']
# 分组（纯视觉分隔，标签留空）：工具 / 复制 / 变换
MED_TOOL_GROUPS = [['select', 'place', 'erase', 'band'],
                   ['copy', 'paste', 'array'],
                   ['rotate', 'mirror']]
# 工具条高：与格子画布（gui/annotation.py 的 design 视图，82）同高，
# 两个编辑器切换时工具条不上下跳（用户要求「同一套 UI」）。
_BAR_H = 82
# 贴边吸附的命中容差（晶格单位）：点得离候选块够近才吸附，否则自由落点
_SNAP_TOL = 0.75
# 玩家**显式**选了朝向（按过 R/F）时，为这个朝向放宽到的容差。为什么需要
# 放宽：贴哪条边决定朝向，同一个落点附近往往只有一个朝向贴得上（贴另一条
# 边才是另一个朝向），于是玩家按 R 选的方向「选不到」——而那个方向其实是
# 合法可玩的（2026-10-26 用户报）。放宽到 1.2 格（< 一格半）既有一定自由
# 度，又不会让块飞到玩家没看的那一侧：悬停预览走同一判据，点前就看得见。
_SNAP_LOCK_TOL = 1.2
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
    def _med_open(self, seed_current: bool = False):
        """打开搭积木编辑器。

        ``seed_current=True`` 是「改谜题」入口（用户 2026-10-26 定）：把**当前
        模型谜题的盘面**原样导入编辑器接着改，而不是从一颗空块开始。导入不成
        （不是模型板型 / 形状标签无法识别 / 晶格族认不出）就退回空盘并说明。
        """
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
            'pos_scale': 1,                    # 当前细分度（route A：支持 >1）
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
            'orient_lock': None,            # 玩家显式按 R/F 选的朝向号（见
                                            # _med_pick_orient；None=交给几何）
            # ---- 选区 / 复制 / 阵列（2026-10-28 加）----
            'sel': set(),                   # 选中的块键（右键拖框选出）
            'clip': None,                   # 剪贴板（见 _med_copy_sel）
            'paste': None,                  # 粘贴中的浮动副本（见 _med_paste_begin）
            'rband': None,                  # 框选橡皮筋（屏幕坐标 Rect）
            'rmb': None,                    # 右键手势记录（按下→松手之间）
            'last_delta': None,             # 上次粘贴落位的位移 = 阵列周期 d1
            'array_dlg': None,              # 「阵列」尺寸选择弹窗（None=关）
            'tool': 'place',                 # 当前激活工具：select/place/erase/band
            'tool_rects': [],                # 左侧工具栏图标热区（绘制时生成）
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
        # ---- 预览 spec + 首块（或导入当前盘面）----
        seeded = self._med_seed_from_model(med) if seed_current else False
        note = ''
        if not seeded:
            if seed_current:
                # 提示要能活到会话里：下面那句操作说明会覆盖通知，所以拼进去
                note = ('当前盘面无法导入编辑器（不是模型板型，或形状/晶格族'
                        '与编辑器不相容），已按空盘打开 · ')
            seed_shape = med['shape']
            med['placed'][((0, 0), seed_shape, 0)] = med['images'][seed_shape][0]
        spec = self._med_spec()
        preview = EngineGame(Board(spec, self._med_blocks()), kind=PREVIEW_KIND)
        med['game'] = preview
        self.game = preview
        self._med_sync_after_edit(center=True)
        if seeded:
            self._med_notify(
                f'已导入当前盘面（{len(med["placed"])} 块，含原有捆绑）：'
                '左键放、拖块移动；右键删块/点缝捆绑；R/F 转向；U 撤销；'
                '命名后回车另存为新模型（ESC 退出）')
        else:
            self._med_notify(note + '搭积木：左键放、按住拖块移动；右键删块、'
                             '右键点缝＝捆绑；R/F 转向（悬停某块＝转那块），'
                             'U 撤销，命名后回车保存（ESC 退出）')

    def _med_seed_from_model(self, med) -> bool:
        """把**当前模型谜题的盘面**灌进编辑器会话（「改谜题」用）。

        为什么这么绕：编辑器的会话 spec 是从「形状库 + 晶格族」现搭的
        （``_med_spec``），朝向标签一律重排成 ``形状:序号``。模型文件里的标签
        也是这个格式（``tri:0`` / ``half:9``），但序号集可能带空洞（只存被用到
        的像），所以这里按形状把序号**压缩重排**，同时记住「旧标签 → 新序号」
        的映射，块才落得回原位。

        只做转换、不校验棋形：块数、连通、可动由保存门在保存时判（编辑器
        全程允许半成品）。返回 False 表示这批块没法导入（标签不是
        ``形状:序号`` / 晶格族认不出 / 有重复键），调用方退回空盘。

        几何保证：``spec.orientations`` 只存**标签**，偏移藏在 model_loader
        的闭包里；公开可拿的是 ``spec.cell_polygon(point, orient)``（平面
        坐标）。这里用 ``spec.basis`` 的逆矩阵把它解回格坐标，再按
        ``pos_scale`` 除回整数格（除不尽就放弃导入，绝不四舍五入——半格
        偏移会把整盘悄悄挪位）。这样不依赖 loader 内部结构。
        """
        game = getattr(self, 'game', None)
        spec = getattr(game, 'spec', None)
        orients = getattr(spec, 'orientations', None) if spec is not None else None
        if not orients:
            return False
        basis = getattr(spec, 'basis', None)
        if not basis or len(basis) != 2:
            return False
        try:
            scale = float(getattr(spec, 'pos_scale', 1.0) or 1.0)
        except (TypeError, ValueError):
            return False
        if scale <= 0:
            return False
        b00, b01 = float(basis[0][0]), float(basis[0][1])
        b10, b11 = float(basis[1][0]), float(basis[1][1])
        det = b00 * b11 - b10 * b01
        if abs(det) < 1e-12:
            return False

        def _poly_to_grid(poly):
            """平面顶点 → 整数格偏移（int_verts = point + offs）。"""
            out = []
            for px, py in poly:
                a = (px * b11 - py * b10) / det * scale
                c = (b00 * py - b01 * px) / det * scale
                ia, ic = int(round(a)), int(round(c))
                if abs(a - ia) > 1e-6 or abs(c - ic) > 1e-6:
                    raise ValueError((a, c))
                out.append((ia, ic))
            return tuple(out)

        # 形状名从哪来（route A）：spec.orientations **只是标签元组**，没有
        # shape 字段。优先回模型文件查（碎三角的标签是裸号 '6'/'12'，只有
        # 文件里的 orientations 才记着它属于 tri 还是 iso30）；查不到再按
        # '形状:序号' 解析；都没有就按几何起稳定名——绝不因为标签不合规就
        # 整盘退回空盘（旧代码正是这么把碎三角挡在门外的）。
        shape_of = {}
        kind = getattr(game, 'kind', None)
        if kind:
            try:
                from engine import model_registry
                _doc = model_registry.loaded(kind).doc or {}
                for _lb, _it in (_doc.get('orientations') or {}).items():
                    if isinstance(_it, dict) and _it.get('shape'):
                        shape_of[str(_lb)] = str(_it['shape'])
            except Exception:               # noqa: BLE001 —— 拿不到就走后面的兜底
                shape_of = {}

        # 标签 → (形状名, 格偏移)（原始，未归一）
        raw_by_label = {}
        anon = {}                      # 归一化几何 -> 兜底形状名
        try:
            for label in orients:
                lb = str(label)
                shape = shape_of.get(lb)
                if shape is None:
                    _s, sep, idx = lb.rpartition(':')
                    if sep and _s and idx.isdigit():
                        shape = _s
                raw = _poly_to_grid(spec.cell_polygon((0, 0), label))
                if shape is None:
                    # 兜底：按几何给名，同一多边形共名、不同多边形分开
                    _key = eg.normalize(raw)
                    shape = anon.get(_key)
                    if shape is None:
                        shape = 's%d' % len(anon)
                        anon[_key] = shape
                raw_by_label[lb] = (shape, raw)
        except Exception:                   # noqa: BLE001 —— 任何几何异常都退回空盘
            return False
        if not raw_by_label:
            return False
        # 族判定（route A）：按**朝向集的世界旋转闭合性**，与「打开模型…」
        # 共用 infer_lattice。旧口径 family_of_basis 只看 basis 两向量夹角，
        # 会把碎三角那种「正交不等长基」(0.866,0)/(0,0.5) 误判成方形 → 编辑
        # 器按 D4 去转它，转一次就散。伪 doc 只给 infer_lattice 用到的三键。
        try:
            lattice = eg.infer_lattice({
                'basis': basis, 'pos_scale': int(scale),
                'orientations': {lb: {'shape': sh,
                                      'off': [list(v) for v in raw]}
                                 for lb, (sh, raw) in raw_by_label.items()},
            })
        except Exception:
            lattice = None
        if lattice not in eg.LATTICES:
            lattice = 'tri'          # 与载入侧同兜底：几何照导，旋转退化
        # route A：归一化 + **几何去重**建档（同一几何形状在盘里常以多种顶点
        # 排列重复出现），并记下各自减掉的最小角——落块时补回锚点，否则不同
        # 朝向的块被各自平移不同的量，整盘会判不连通（与载入侧 _med_load_model
        # 同一个坑）。标准盘面 off 的 min=(0,0)，零影响。
        norm = eg.normalize

        def _sort_key(l):
            """按「形状名、序号」定序（裸号/非数字标签排最后，不炸）。"""
            _s, _, _i = l.rpartition(':')
            try:
                return (_s, int(_i))
            except ValueError:
                return (_s, 1 << 30)

        shift_of, label_of, by_shape = {}, {}, {}
        for label in sorted(raw_by_label, key=_sort_key):
            shape, raw = raw_by_label[label]
            n = norm(raw)
            shift_of[label] = (min(v[0] for v in raw), min(v[1] for v in raw))
            bucket = by_shape.setdefault(shape, [])
            if n not in bucket:
                bucket.append(n)
            label_of[label] = (shape, bucket.index(n))
        images = {s: tuple(v) for s, v in by_shape.items()}
        # 块源：用引擎局面的 Board.blocks（真正的 engine Block），不是 GUI 的
        # 适配层列表——_AdapterBlock 只有 .location 列表，没有 .point/.orient。
        board = getattr(game, 'board', None)
        placed, groups, gid_map = {}, {}, {}
        for b in (getattr(board, 'blocks', ()) if board is not None else ()):
            label = str(getattr(b, 'orient', ''))
            if label not in label_of:
                return False
            shape, idx = label_of[label]
            # 块坐标本身已是整数格（Board 校验 Lattice.valid(point)），
            # 不能按 pos_scale 再除一次——那是顶点偏移的单位，不是锚点。
            try:
                if any(float(v) != int(v) for v in b.point):
                    return False
                p = tuple(int(v) for v in b.point)
            except (TypeError, ValueError):
                return False
            # 锚点补偿：images 里的偏移已归一化（减去各自最小角），把该 label
            # 减掉的最小角加回锚点，物理位置才与盘面原来的一致。
            _sh = shift_of.get(label, (0, 0))
            p = (p[0] + _sh[0], p[1] + _sh[1])
            key = (p, shape, idx)
            if key in placed:
                return False
            placed[key] = images[shape][idx]
            g = getattr(b, 'group', 0) or 0
            if g:
                if g not in gid_map:
                    gid_map[g] = len(gid_map) + 1
                groups[key] = gid_map[g]
        if not placed:
            return False
        info = eg.lattice_info(lattice)
        med['lattice'] = lattice
        # route A：用盘面**自己的基**（碎三角那种自定义基也照用），族只决定
        # 旋转粒度 deg。旧代码写死成族的标准基，配上 ps≠1 / 自定义基的盘面
        # 会把块按错误基换算——尺寸、点击、存档全错。
        med['basis'] = [list(r) for r in basis]
        med['deg'] = info['deg']
        # ⚠️ 必须写盘面自己的细分度：_med_screen_to_geom/_med_geom_to_screen
        # 与 _med_spec 全按它换算。旧代码漏写（恒为 1），ps=3 的盘面导入后
        # 屏幕↔几何差 3 倍（点哪都不中、存回去尺寸也错）。
        med['pos_scale'] = int(scale)
        med['spec'] = None              # basis/images 变了，预览 spec 重建
        med['lib'].update(images)
        for s in images:
            med['lib_lattice'][s] = lattice
        med['images'] = images
        med['placed'] = placed
        med['groups'] = groups
        med['next_gid'] = len(gid_map) + 1
        med['shape'] = self._med_default_shape(images)
        med['cursor'] = 0
        med['orient_lock'] = None       # 载入/导入的盘面不由玩家挑朝向
        return True

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
            # ⚠️ 必须写模型自己的 pos_scale（route A：任意 basis + pos_scale）。
            # spec 的 cell_polygon 会按 pos_scale 把整数顶点除回真格坐标
            # （engine/model_loader.plane_of），否则碎三角 ps=3 的块会按
            # ×3 尺寸画（物理尺寸爆炸）。编辑器全程在「原生分辨率」坐标里
            # 工作（placed 存的 p 是 ×ps 整数顶点），渲染/事件换算的 /ps
            # 统一由 _med_geom_to_screen / _med_screen_to_geom 负责。
            'pos_scale': med['pos_scale'],
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
    def _med_pick_orient(self, cands):
        """贴边吸附用哪个朝向（**放置与悬停预览共用**，别各写一套）。

        旧行为：一律取「离点击最近」的候选，朝向纯由几何定——玩家按 R 只影响
        **自由落点**那块，于是「想选的方向选不到」（2026-10-26 用户报），而
        那个方向其实完全可玩（不重叠、也照样连通）。

        新行为：玩家**显式**按过 R/F 就优先那个朝向——先在普通吸附带里找，
        找不到再放宽到 ``_SNAP_LOCK_TOL``（1.2 格）：贴哪条边决定朝向，同一
        个落点附近常常只有一种朝向贴得上，不放宽的话玩家按了 R 也白按。仍
        找不到才退回最近的（绝不为了迁就朝向把块甩到天边）。
        没显式选过（``orient_lock`` 为 None）时行为与旧版完全一致。

        ``cands`` 已按 dist 升序（``eg.snap_candidates`` 保证）。
        """
        want = self._med.get('orient_lock')
        if want is not None:
            for lim in (_SNAP_TOL, _SNAP_LOCK_TOL):
                for c in cands:
                    if c[1] == want and c[3] <= lim:
                        return want
        return cands[0][1]

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
            idx = self._med_pick_orient(cands)
            p = next(c[0] for c in cands if c[1] == idx)
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

    # ==================================================================
    # 选区 / 复制 / 粘贴 / 阵列（2026-10-28）
    #
    # 要解决的问题：想把一个「密铺单元」复制成更大的相同密铺图形，得一块块
    # 重摆。复制的单位是**块**——模型文件里没有「单元」这种标记（shatter 的
    # 48 块只是 48 个锚点，看不出哪 12 块构成一个单元），所以先框选出构成
    # 一个单元的那些块，复制后整体平移一份即可。平移量与 _med_drag_to 同
    # 口径（整数格），同晶格 ⇒ 自动贴合，不需要额外吸附。
    # ==================================================================
    _RMB_DRAG_PX = 4     # 右键位移超过这个像素＝「拖」（框选），否则＝「点」

    def _med_right_move(self, x, y):
        """右键拖动中：超过阈值就进入框选，画出橡皮筋。"""
        med = self._med
        r = med['rmb']
        if abs(x - r['sx']) > self._RMB_DRAG_PX or abs(y - r['sy']) > self._RMB_DRAG_PX:
            r['moved'] = True
            med['rband'] = pygame.Rect(min(x, r['sx']), min(y, r['sy']),
                                       abs(x - r['sx']), abs(y - r['sy']))

    def _med_right_up(self):
        """右键松手：没拖动＝原点击语义（缝捆绑 / 删块）；拖动过＝框选。"""
        med = self._med
        r = med.pop('rmb')
        band = med.pop('rband', None)
        if not r['moved']:
            seam = self._med_seam_at(r['gx'], r['gy'])
            if seam is not None:
                self._med_toggle_bundle(*seam)
            else:
                self._med_delete_at(r['gx'], r['gy'])
            return
        self._med_select_box(band)

    def _med_boxsel_move(self, x, y):
        """选择工具：左键拖动中超过阈值 → 进入框选，画橡皮筋。"""
        med = self._med
        p = med['press']
        if abs(x - p['sx']) > self._RMB_DRAG_PX or abs(y - p['sy']) > self._RMB_DRAG_PX:
            p['moved'] = True
            med['rband'] = pygame.Rect(min(x, p['sx']), min(y, p['sy']),
                                       abs(x - p['sx']), abs(y - p['sy']))

    def _med_boxsel_up(self):
        """选择工具松手：拖过＝框选；没拖＝点选单块/取消选择。"""
        med = self._med
        p = med.pop('press')
        band = med.pop('rband', None)
        if not p.get('moved'):
            key = eg.block_at(med['placed'], (p['gx'], p['gy']), med['basis'])
            med['sel'] = {key} if key is not None else set()
            if key is not None:
                self._med_notify('已选中 1 块')
            else:
                self._med_notify('已取消选择')
            return
        self._med_select_box(band)

    def _med_select_box(self, band):
        """橡皮筋 → 选中集合：**任一顶点在框内 或 质心在框内** 即选中。

        旧版只认单点质心，碎三角 / 长条块质心偏在一侧会漏选（玩家框住了
        块却选不中）。改为「顶点进框即选中」（见 ``eg.box_hits_block`` 的
        说明，不会像「相交」那样过度选中互锁单元）。坐标口径：屏幕矩形先
        经 ``_med_screen_to_geom`` 换算成几何框，再交给纯函数判定。
        """
        med = self._med
        if band is None or band.w < 2 or band.h < 2:
            med['sel'] = set()
            return
        a = self._med_screen_to_geom(band.left, band.top)
        b = self._med_screen_to_geom(band.right, band.bottom)
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        sel = eg.select_blocks_in_box(med['placed'], (x0, x1, y0, y1))
        med['sel'] = sel
        self._med_notify(f'已选中 {len(sel)} 块' if sel else '框内没有块')

    def _med_copy_sel(self):
        """选中集合 → 剪贴板（相对坐标；锚点取排在最前那块，排序确定）。"""
        med = self._med
        sel = med['sel']
        # 选区里可能夹着已被删掉/撤销掉的键（块没了但 sel 还留着），先过滤
        keys = sorted((k for k in sel if k in med['placed']),
                      key=lambda k: (k[0][0], k[0][1], k[1], k[2]))
        if not keys:
            self._med_notify('先右键拖框选要复制的块')
            return False
        ref = keys[0][0]
        gids = sorted({med['groups'][k] for k in keys if k in med['groups']})
        gmap = {g: i + 1 for i, g in enumerate(gids)}
        med['clip'] = {
            'ref': ref,
            'items': tuple((k[0][0] - ref[0], k[0][1] - ref[1], k[1], k[2],
                            med['placed'][k], gmap.get(med['groups'].get(k), 0))
                           for k in keys),
        }
        self._med_notify(f'已复制 {len(keys)} 块（Ctrl+V 或点[粘贴]）')
        return True

    def _med_paste_begin(self):
        """开始粘贴：浮动副本跟着鼠标，左键点一下落位，ESC 取消。"""
        med = self._med
        if med['clip'] is None:
            self._med_notify('剪贴板是空的（先框选再[复制]）')
            return False
        mx, my = pygame.mouse.get_pos()
        gx, gy = self._med_screen_to_geom(mx, my)
        med['paste'] = {'items': med['clip']['items'], 'base': None, 'ok': False}
        self._med_paste_update(gx, gy)
        return True

    def _med_paste_update(self, gx=None, gy=None):
        """浮动副本跟随鼠标 + 整份合法性预检（预览与落位同一口径）。"""
        med = self._med
        pa = med['paste']
        if pa is None:
            return
        if gx is None:
            mx, my = pygame.mouse.get_pos()
            gx, gy = self._med_screen_to_geom(mx, my)
        base = (int(round(gx)), int(round(gy)))
        if base == pa['base']:
            return
        pa['base'] = base
        pa['ok'] = self._med_copy_fits(pa['items'], base)

    def _med_copy_fits(self, items, base):
        """这一份摆在这儿放不放得下（逐块 can_place，整份一票否决）。"""
        med = self._med
        others = med['placed']
        seen = set()
        for dx, dy, shape, idx, offs, _g in items:
            p = (base[0] + dx, base[1] + dy)
            nk = (p, shape, idx)
            if nk in others or nk in seen:
                return False
            seen.add(nk)
            if not eg.can_place((offs,), 0, p, others, med['basis']):
                return False
        return True

    def _med_stamp(self, items, base):
        """把一份副本写进 placed（不做校验，调用方先过 _med_copy_fits）。

        捆绑组按新号段重排：每份副本各自成组，副本之间不共组（否则一次
        剪缝会把所有副本一起剪开）。
        """
        med = self._med
        n_g = max((it[5] for it in items), default=0)
        gid_base = med['next_gid']
        for dx, dy, shape, idx, offs, rel_g in items:
            p = (base[0] + dx, base[1] + dy)
            nk = (p, shape, idx)
            med['placed'][nk] = offs
            if rel_g:
                med['groups'][nk] = gid_base + rel_g - 1
        if n_g:
            med['next_gid'] = gid_base + n_g

    def _med_paste_commit(self):
        """落位：写进 placed，并记下这次的位移当阵列周期。"""
        med = self._med
        pa = med['paste']
        if pa is None:
            return False
        if not pa['ok']:
            self._med_notify('这个位置放不下（与已有块重叠），换个位置')
            return False
        base = pa['base']
        n = len(pa['items'])
        self._med_undo_push()
        self._med_stamp(pa['items'], base)
        # 阵列周期 = 这一份相对原件锚点的位移（玩家贴出来的真实可用间距）
        med['last_delta'] = (base[0] - med['clip']['ref'][0],
                             base[1] - med['clip']['ref'][1])
        med['paste'] = None
        med['sel'] = set()
        self._med_sync_after_edit()
        self._med_notify(f'已粘贴 {n} 块')
        return True

    def _med_paste_cancel(self):
        med = self._med
        if med.get('paste') is not None:
            med['paste'] = None
            return True
        return False

    # ---- 阵列：把选中的单元铺成更大的相同密铺 ----
    def _med_array_dlg_open(self):
        """打开「阵列」尺寸弹窗（预设档位，纯鼠标点选，不手输数字）。"""
        med = self._med
        if med['clip'] is None:
            self._med_notify('剪贴板是空的（先框选再[复制]）')
            return False
        if not med.get('last_delta'):
            self._med_notify('先[粘贴]一份贴到相邻位置，阵列才知道按什么间距铺')
            return False
        med['array_dlg'] = {'items': ((2, 2), (3, 3), (4, 4), (2, 3), (3, 4), (5, 5)),
                            'rects': []}
        return True

    def _med_array_dlg_click(self, x, y) -> bool:
        med = self._med
        dlg = med.get('array_dlg')
        if dlg is None:
            return False
        for rect, (rows, cols) in dlg['rects']:
            if rect.collidepoint(x, y):
                med['array_dlg'] = None
                self._med_paste_array(rows, cols)
                return True
        med['array_dlg'] = None            # 点外面 = 取消
        return True

    def _med_paste_array(self, rows, cols):
        """沿 d1（上次粘贴的位移）和 d2（d1 转一个晶格步长）铺 rows×cols 份。

        d1 是玩家手动贴出来的**真实可用间距**，不是猜的；三角格对 60°、
        方形格对 90° 旋转自同构，所以 d2 仍是整数格向量（eg.rot60/rot90）。
        每份都过 _med_copy_fits，放不下就跳过——即使圈出来的不是平移密铺
        单元，也只会少铺几份，不会画出重叠盘面。
        """
        med = self._med
        clip = med['clip']
        d1 = med.get('last_delta')
        if clip is None:
            self._med_notify('剪贴板是空的（先框选再[复制]）')
            return False
        if not d1 or d1 == (0, 0):
            self._med_notify('先[粘贴]一份贴到相邻位置，阵列才知道按什么间距铺')
            return False
        # 第二方向 = d1 在世界坐标里转一个晶格步长。**不能**用 eg.rot60/rot90
        # （标准基的整系数矩阵，碎三角那种自定义基套上去不是 60° 方向）。
        deg = 60 if med['lattice'] == 'tri' else 90
        d2 = eg.rotate_vector(d1, deg, med['basis'], med['pos_scale'])
        ref = clip['ref']
        items = clip['items']
        plan = []
        for i in range(rows):
            for j in range(cols):
                di = i * d2[0] + j * d1[0]
                dj = i * d2[1] + j * d1[1]
                if (di, dj) == (0, 0):
                    continue                      # 原件本身，已经在那儿
                base = (ref[0] + di, ref[1] + dj)
                if self._med_copy_fits(items, base):
                    plan.append(base)
        if not plan:
            self._med_notify('这些位置放不下（都被占了或越界），没铺出新的')
            return False
        self._med_undo_push()
        for base in plan:
            self._med_stamp(items, base)
        self._med_sync_after_edit()
        n_new = len(items) * len(plan)
        skipped = rows * cols - len(plan) - 1
        self._med_notify(f'已阵列铺出 {len(plan)} 份（新增 {n_new} 块'
                         + (f'，跳过 {skipped} 份' if skipped > 0 else '') + '）')
        return True

    # ---- 绘制：选区 / 浮动副本 / 橡皮筋 / 阵列弹窗 ----
    def _med_draw_sel(self):
        """选区高亮（描边加粗，不改填充——§3 不给滑块加新填充色）。"""
        med = self._med
        sel = med.get('sel')
        if not sel:
            return
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for k in sel:
            if k not in med['placed']:
                continue
            pts = [self._med_geom_to_screen(x, y)
                   for (x, y) in eg.poly_of(k[0], med['placed'][k], med['basis'])]
            if len(pts) < 3:
                continue
            pygame.draw.polygon(surf, (255, 214, 90, 220), pts, 3)
        self.screen.blit(surf, (0, 0))

    def _med_draw_paste(self):
        """浮动副本预览：可落位画绿、放不下画红（与落位判据同一口径）。"""
        med = self._med
        pa = med.get('paste')
        if pa is None or pa['base'] is None:
            return
        col = (120, 230, 140, 110) if pa['ok'] else (235, 110, 110, 110)
        edge = (170, 255, 190, 235) if pa['ok'] else (255, 160, 160, 235)
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        base = pa['base']
        for dx, dy, _shape, _idx, offs, _g in pa['items']:
            p = (base[0] + dx, base[1] + dy)
            pts = [self._med_geom_to_screen(x, y)
                   for (x, y) in eg.poly_of(p, offs, med['basis'])]
            if len(pts) < 3:
                continue
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, edge, pts, 2)
        self.screen.blit(surf, (0, 0))

    def _med_draw_rband(self):
        med = self._med
        band = med.get('rband')
        if band is None:
            return
        surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(surf, (255, 214, 90, 60), band)
        pygame.draw.rect(surf, (255, 214, 90, 220), band, 1)
        self.screen.blit(surf, (0, 0))

    def _med_draw_array_dlg(self):
        """「阵列」尺寸弹窗（与「打开模型」列表同一套模态外观）。"""
        med = self._med
        dlg = med.get('array_dlg')
        if dlg is None:
            return
        c = self.colors
        f_title = self._med_font(17)
        f_item = self._med_font(15)
        f_small = self._med_font(12)
        items = dlg['items']
        w, rh = 360, 30
        h = 40 + len(items) * rh + 30
        panel = pygame.Rect(0, 0, w, h)
        panel.center = (self.screen_width // 2, self.screen_height // 2)
        shade = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 90))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, c['menu_bg'], panel)
        pygame.draw.rect(self.screen, c['dialog_border'], panel, 1)
        t = f_title.render('阵列：铺几份？', True, c['dialog_title'])
        self.screen.blit(t, (panel.x + 14, panel.y + 10))
        y = panel.y + 40
        dlg['rects'] = []
        for rows, cols in items:
            row = pygame.Rect(panel.x + 8, y, panel.width - 16, rh - 4)
            dlg['rects'].append((row, (rows, cols)))
            if row.collidepoint(*pygame.mouse.get_pos()):
                pygame.draw.rect(self.screen, c['selection_bg'], row)
            s = f_item.render(f'{rows} × {cols}', True, c['menu_text'])
            self.screen.blit(s, (row.x + 8, row.y + 4))
            s2 = f_small.render(f'共 {rows * cols} 份', True, c['status_text'])
            self.screen.blit(s2, (row.right - s2.get_width() - 8, row.y + 7))
            y += rh
        self.screen.blit(f_small.render('按上次粘贴的间距铺；点外面或 ESC 取消',
                                        True, c['status_text']),
                         (panel.x + 14, panel.bottom - 24))

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

    def _med_shape_index(self, images=None):
        """形状库 → {规范化顶点元组: (形状名, 朝向号)}（按几何认朝向用）。

        模型文件自带的 label 是文件作者起的（编辑器自己写的才是
        ``'shape:idx'``），所以载入时按**顶点像**认朝向，不认字符串。

        ``images`` 缺省 = 当前族（``med['images']``）；预检要不要给**全库**
        （``med['lib']``）——方形模型在三角会话里预检时，它的形状根本不在
        当前族的 ``images`` 里，用当前族判会误报「形状对不上库」。
        """
        src = self._med['images'] if images is None else images
        index = {}
        for shape, imgs in src.items():
            for idx, offs in enumerate(imgs):
                index[offs] = (shape, idx)
        return index

    def _med_matchable(self, doc):
        """文档是否至少带可用的朝向表与块（route A：直接用模型自带朝向，

        不再要求与形状库做几何匹配——``normalize`` 不吃尺度，库的 ×1 朝向
        匹配不上模型的 ×ps 朝向）。有朝向表 + 有块即可续编。"""
        return bool((doc.get('orientations') or {}) and (doc.get('tiles') or []))

    def _med_load_blocker(self, doc):
        """这份模型能不能续编？能 → ``None``；不能 → ``(短因, 长提示)``。

        **列表侧**（``_med_open_model_list``，用短因标灰）与**载入侧**
        （``_med_load_model``，用长提示）共用这一个判据——2026-10-27 修的坑：
        碎三角那份 basis（0.866/0.5、90°）两族都认不出，列表里却照常列着，
        玩家一点必然弹「认不出属于哪个晶格」，等于给了一条走不通的路。

        ⚠️ 这里**只收窄入口、不放宽几何**：``lattice_of_basis`` 的判据一字不
        动，认不出就是认不出——放宽会让块落到错的格子上，比拒载更糟。
        """
        nm = doc.get('name') or '该模型'
        # ⚠️ 与载入侧（``_med_load_model``）共用 ``infer_lattice``：碎三角那种
        # 「正交不等长基」必须按朝向集闭合性判成三角族（route A），不能再用
        # ``family_of_basis``（只看夹角会误判方形），否则列表标灰与载入行为
        # 自相矛盾——列表说「不可续编」、一点却又能载入。
        lat = eg.infer_lattice(doc)
        if lat is None:
            return ('坐标基非三角/方形晶格',
                    f'「{nm}」的坐标基不是编辑器支持的三角/方形晶格，'
                    '续编会按错的几何画——改用[新建]搭一个，或先把它改成'
                    '三角/方形基（见 docs/spec/搭积木编辑器.md §7）')
        if lat != self._med['lattice'] and len(self._med['placed']) > 1:
            # 文件是另一族：盘面还有东西就不能换（换族要清盘）
            return ('另一晶格·需先清空',
                    f'「{nm}」属于{eg.lattice_info(lat)["label"]}晶格，'
                    f'当前盘面是{eg.lattice_info(self._med["lattice"])["label"]}'
                    '——先[清空]（或切晶格）再打开')
        if not self._med_matchable(doc):
            return ('形状对不上库',
                    f'「{nm}」里没有一块能对上 models/shapes.json 的形状'
                    '（续编按顶点认朝向）——把它用到的形状加进形状库再打开')
        return None

    def _med_open_model_list(self):
        """弹出「打开模型」列表（models/ 下已注册的模型，续编用）。

        开不了的**照样列出来但标灰并在行尾写明原因**——不隐藏（玩家才知道
        为什么没有），也不让它可点（点了只会弹一个走不通的提示）。
        """
        from engine import model_registry
        try:
            loaded = model_registry.loaded()
        except Exception as exc:           # noqa: BLE001 —— 通知要带原因
            self._med_notify(f'读不到模型列表：{exc}')
            return
        items = sorted(
            (nm, m.title, len(m.spec.goal_blocks),
             (self._med_load_blocker(m.doc or {}) or (None, None))[0])
            for nm, m in loaded.items())
        if not items:
            self._med_notify('models/ 下还没有可打开的模型（先保存一个）')
            return
        self._med['name_active'] = False     # 弹列表 = 名字框失焦
        self._med['open_list'] = {'items': items, 'rects': []}

    def _med_load_model(self, name):
        """把已注册模型读回编辑器（续编）。返回 True=载入成功。

        route A（任意 basis + pos_scale）：直接用模型**自带**的朝向表建档，
        不再与形状库做几何匹配——``normalize`` 不吃尺度，库的 ×1 朝向匹配
        不上模型的 ×ps 朝向（碎三角 pos_scale=3 的偏移是 ×3）。库里同形状
        按 pos_scale 缩放补齐，供续编时加新块。换族/换基只改字段、清盘由
        blocker 把关（盘面 >1 块时拦「需先清空」），绝不把基归一化成标准
        基（否则重开失真）。
        """
        from engine import model_registry
        try:
            m = model_registry.loaded(name)
        except KeyError:
            self._med_notify(f'模型 {name!r} 不可用')
            return False
        doc = m.doc or {}
        blocker = self._med_load_blocker(doc)
        if blocker is not None:
            self._med_notify(blocker[1])       # 与列表标灰同一判据
            return False
        med = self._med
        lat = eg.infer_lattice(doc)          # 朝集闭合性判定（碎三角→tri）
        if lat is None:                       # 两族都不闭合：几何仍可导，但
            lat = 'tri'                       # 旋转退化；给个兜底族不阻塞导入
        ps = int(doc.get('pos_scale', 1) or 1)
        # 1) 模型自带朝向（已是 ×ps）按形状**几何去重**建档。重要：模型文件
        #    里同一几何形状常以多种顶点排列（permutation）重复出现（碎三角
        #    12 个 label 实为 2 个朝向的全排列），编辑器只认「几何朝向」——
        #    故先 normalize 去重成「不重复朝向表」，再记 label -> 最终下标，
        #    落块时统一用去重下标。库同形状按 ps 缩放补齐、按几何合并去重，
        #    供续编时加新块（库的朝向优先命中）。
        orients = doc.get('orientations') or {}
        norm = eg.normalize
        model_norm = {}          # shape -> [归一化多边形]（模型内去重、保序）
        label_norm = {}          # 模型label -> (shape, 归一化多边形)
        label_shift = {}         # 模型label -> 归一化时减掉的最小角（补锚点用）
        for _lb, _o in orients.items():
            if ':' in _lb:                      # 形如 "tri:3"
                _s = _lb.rpartition(':')[0]
            else:                                # 裸号 / "r12" 等
                _s = _o.get('shape')
            _raw = tuple(tuple(int(x) for x in v) for v in _o['off'])
            _n = norm(_raw)
            # ⚠️ normalize 把多边形平移到「最小角在原点」，落块若直接用它配
            # 文件里的原锚点，每块会被各自平移不同的量（碎三角两类朝向最小
            # 角 (-1,-3)/(-2,-3) 不同）→ 相邻 A/B 块错位、整盘判不连通。故记
            # 下减掉的最小角，落块时把它加回锚点补偿（存回的 offsets 已归一
            # 化、shift=0，重开不会二次叠加）。标准模型 min=(0,0) 零影响。
            label_shift[_lb] = (min(v[0] for v in _raw),
                                min(v[1] for v in _raw))
            label_norm[_lb] = (_s, _n)
            bucket = model_norm.setdefault(_s, [])
            if _n not in bucket:
                bucket.append(_n)
        images = {}
        for _sname, _imgs in med['lib'].items():
            merged = []
            for _off in _imgs:
                _n = norm(tuple(tuple(ps * v for v in vert)
                                for vert in _off))
                if _n not in merged:
                    merged.append(_n)
            images[_sname] = merged
        for _s, bucket in model_norm.items():
            merged = images.setdefault(_s, [])
            for _n in bucket:
                if _n not in merged:
                    merged.append(_n)
        images = {s: tuple(merged) for s, merged in images.items()}
        med['images'] = images
        med['lib'] = images
        med['lib_lattice'] = {s: lat for s in images}
        # label -> 最终（合并去重后）下标：落块去重下标统一出处
        med['label_remap'] = {_lb: (_s, images[_s].index(_n))
                              for _lb, (_s, _n) in label_norm.items()}
        # 2) 换族/换基/换细分度：只改字段，绝不清盘、绝不归一化基
        if (lat != med['lattice']
                or [list(r) for r in med['basis']]
                != [list(r) for r in doc['basis']]
                or med.get('pos_scale') != ps):
            med['lattice'] = lat
            med['basis'] = [list(r) for r in doc['basis']]
            med['deg'] = eg.lattice_info(lat)['deg']
            med['pos_scale'] = ps
            med['spec'] = None              # basis/images 变了，预览 spec 重建
        # 3) 按模型自带 label 直接落块（去重下标从 label_remap 取）
        placed, groups, skipped = {}, {}, 0
        for t in doc.get('tiles') or []:
            try:
                p = (int(t['p'][0]), int(t['p'][1]))
                _lb = t['o']
                _s, _idx = med['label_remap'][_lb]   # 形状/下标都从去重映射取
            except (KeyError, TypeError, ValueError, IndexError):
                skipped += 1
                continue
            # 锚点补偿：images 里的偏移已 normalize（减去各自最小角），把该
            # label 的最小角加回锚点，物理位置才与文件原来的 p+off 一致。
            _sh = label_shift.get(_lb, (0, 0))
            p = (p[0] + _sh[0], p[1] + _sh[1])
            if _s not in images or _idx >= len(images[_s]):
                skipped += 1
                continue
            if (p, _s, _idx) in placed:
                skipped += 1
                continue
            placed[(p, _s, _idx)] = images[_s][_idx]
            gid = int(t.get('g', 0) or 0)
            if gid:
                groups[(p, _s, _idx)] = gid
        if not placed:
            self._med_notify(f'「{name}」里没有一块能落到棋盘，载入失败')
            return False
        self._med_undo_push()
        med['placed'] = placed
        med['groups'] = groups
        med['next_gid'] = max(list(groups.values()) + [0]) + 1
        med['name'] = name
        med['name_active'] = False
        med['orient_lock'] = None       # 续编不继承「玩家刚才挑的朝向」
        # 缝族开关按文件里写了的族（续编语义：推导出但文件没有的族默认关）
        on = {s.get('name') for s in (doc.get('seams') or []) if s.get('name')}
        med['fam_off'] = {f[0] for f in self._med_families() if f[0] not in on}
        self._med_sync_after_edit(center=True)
        msg = f'已载入「{name}」（{len(placed)} 块'
        if groups:
            msg += f'、{len(set(groups.values()))} 个捆绑组'
        if skipped:
            msg += f'；{skipped} 块落不进棋盘被跳过'
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

    def _med_is_standard_basis(self):
        """当前是否标准基 + scale=1（可用整系数 rot60/rot90，零回归路径）。"""
        med = self._med
        return med['pos_scale'] == 1 and \
            med['basis'] == eg.lattice_info(med['lattice'])['basis']

    def _med_xform_poly(self, offs, mirror):
        """旋转/镜像一块顶点：标准基走整系数矩阵；自定义基走世界坐标旋转。

        自定义基（碎三角正交不等长基等）没有对应的整系数 60°/90° 矩阵，
        必须用 ``eg.world_rotate`` 在世界坐标里转——这是 route A「导入后
        还能旋转」成立的几何前提；标准基 + scale=1 时退化回原整系数路径。
        """
        if self._med_is_standard_basis():
            xf = self._med_mirror_v if mirror else self._med_rot_v
            return eg.normalize(tuple(xf(v) for v in offs))
        deg = 90 if self._med['lattice'] == 'square' else 60
        return eg.world_rotate(offs, deg, self._med['basis'],
                               self._med['pos_scale'], mirror=mirror)

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
        med['orient_lock'] = None       # 换族后朝向号是另一套，锁不住
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
        shape = self._med['shape']
        for i, img in enumerate(self._med['images'][shape]):
            if img == target:
                return i
        # 自定义基/低对称形状：几何旋转可能落不到整数格点，吸附到最近朝向
        return self._med_nearest_image(shape, target, self._med['cursor'])

    def _med_nearest_image(self, shape, target, current_idx=None):
        """几何旋转落不到整数格点时，吸附到最近的一个已存朝向（route A

        「导入后还能转」的兜底）。用「质心对齐后的顶点距离」比朝向，且排除
        当前下标——保证总能切到另一个合法朝向（低对称形状退化为 2 个朝向时
        也能 ▲↔▼ 切换，不会卡在自身）。无候选回 None。
        """
        imgs = self._med['images'].get(shape)
        if not imgs or len(imgs) < 2:
            return None

        def _centered(poly):
            n = len(poly)
            cx = sum(v[0] for v in poly) / n
            cy = sum(v[1] for v in poly) / n
            return sorted((v[0] - cx, v[1] - cy) for v in poly)

        tk = _centered(target)
        best = None
        for i, img in enumerate(imgs):
            if i == current_idx:
                continue
            d = sum((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                    for a, b in zip(tk, _centered(img)))
            if best is None or d < best[0]:
                best = (d, i)
        return best[1] if best else None

    def _med_rotate(self, step=1):
        key = self._med.get('hover')
        if key is not None and key in self._med['placed']:
            self._med_turn_block(key, mirror=False)
            return
        med = self._med
        imgs = med['images'][med['shape']]
        cur = imgs[med['cursor']]
        nxt = self._med_image_index(self._med_xform_poly(cur, mirror=False))
        if nxt is None:
            nxt = (med['cursor'] + step) % len(imgs)
        med['cursor'] = nxt
        med['orient_lock'] = nxt        # 玩家自己选的朝向：吸附要认（§三）
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
        nxt = self._med_image_index(self._med_xform_poly(cur, mirror=True))
        if nxt is None:
            return
        med['cursor'] = nxt
        med['orient_lock'] = nxt        # 同 _med_rotate
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
        new = self._med_xform_poly(offs, mirror=mirror)
        try:
            idx = med['images'][shape].index(new)
        except ValueError:
            # 自定义基/低对称形状：几何旋转落不到整数格点，吸附到最近朝向
            idx = self._med_nearest_image(shape, new, old_idx)
            if idx is None:
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
        """合成模型文档（与 experiments/script__gen_model_shatter.py 同款结构）。"""
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
        # 被玩家关掉的缝族也要记进文件：谜题开局时据此提示玩家「这些缝
        # 不滑动（设计如此）」，否则玩家看到缝却滑不动会以为出 bug。
        disabled = []
        fam_by_name = {nm: st for (nm, _cf, st, _n) in self._med_families()}
        for nm in med['fam_off']:
            st = fam_by_name.get(nm)
            if st is None:
                continue
            desc, _ = eg.direction_desc(st, med['basis'], med['deg'])
            disabled.append({'name': nm, 'desc': desc})
        from engine.model_loader import (DEFAULT_CORNER_RADIUS,
                                         DEFAULT_SEAM_WIDTH)
        return {
            'schema': SCHEMA_BOARD,
            'name': name,
            'title': name,
            'basis': [list(r) for r in med['basis']],
            'pos_scale': med['pos_scale'],
            'solved': 'exact',
            'shapes_ref': 'shapes.json',
            # 显式写死画风参数：与碎三角同款（6 / 3），这样文件自解释，
            # 不依赖 loader 的缺省值将来怎么改（用户 2026-10-26 要「和碎三角
            # 完全一致」）。
            'seam_width': DEFAULT_SEAM_WIDTH,
            'corner_radius': DEFAULT_CORNER_RADIUS,
            'orientations': orients,
            'tiles': tiles,
            'seams': seams,
            'disabled_seams': disabled,
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
            # 菜单悬停缩图是按模型名缓存的：模型文件刚被改写，旧缩图必须作废
            # （不清的话玩家会看到「改了形状、预览还是老样子」）。
            from gui import model_preview
            model_preview.clear_cache()
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
        ps = float(self._med.get('pos_scale', 1) or 1)
        # 编辑器在「原生分辨率」坐标里工作（placed 的 p 是 ×ps 整数顶点）。
        # 画面世界坐标 = 原生/ps × cell_size，故反算原生坐标要 ×ps。
        return wx / s * ps, wy / s * ps

    def _med_geom_to_screen(self, gx, gy):
        """几何单位 → 屏幕（``_med_screen_to_geom`` 的逆）。

        编辑器坐标 = 原生分辨率（×ps 整数顶点）；渲染通道世界坐标 =
        原生/ps × cell_size（spec.cell_polygon 已除回真格坐标）。所以这里
        先把原生坐标除 ps 再乘 cell_size，与棋盘块（cell_polygon × cell_size）
        严格对齐——ps=1 时退化为原行为（零回归）。
        """
        s = float(self.cell_size) or 1.0
        ps = float(self._med.get('pos_scale', 1) or 1)
        return self.world_to_screen(gx / ps * s, gy / ps * s)

    # ==================================================================
    # 左侧竖排图标工具栏（几何画板风，2026-10-28 重做）
    # ==================================================================
    def _med_toolbar_rect(self):
        n = len(MED_TOOL_ORDER)
        groups = len(MED_TOOL_GROUPS)
        h = (_TOOLBAR_TOP_PAD + n * (_TOOL_W + _TOOL_GAP)
             + (groups - 1) * _TOOL_GROUP_GAP + 8)
        return pygame.Rect(_TOOLBAR_X, self.menu_bar_height + 8,
                           _TOOL_W + 12, h)

    def _med_tool_icon_rects(self):
        """按 MED_TOOL_ORDER / MED_TOOL_GROUPS 算每个图标的方块 Rect（热区）。"""
        med = self._med
        rail = self._med_toolbar_rect()
        x = rail.x + 6
        y = rail.y + _TOOLBAR_TOP_PAD
        rects = []
        for gi, grp in enumerate(MED_TOOL_GROUPS):
            if gi:
                y += _TOOL_GROUP_GAP
            for tid in grp:
                rects.append((pygame.Rect(x, y, _TOOL_W, _TOOL_W), tid))
                y += _TOOL_W + _TOOL_GAP
        med['tool_rects'] = rects
        return rects

    def _med_draw_tools(self):
        med = self._med
        rail = self._med_toolbar_rect()
        c = self.colors
        pygame.draw.rect(self.screen, c['menu_bg'], rail)
        pygame.draw.rect(self.screen, c['dialog_border'], rail, 1)
        f = self._med_font(13)
        self.screen.blit(f.render('工具', True, c['menu_selected']),
                         (rail.x + 6, rail.y + 4))
        rects = self._med_tool_icon_rects()
        mx, my = pygame.mouse.get_pos()
        hover_tid = None
        for rect, tid in rects:
            label, shortcut, kind = MED_TOOLS[tid]
            on = (kind == 'tool' and med['tool'] == tid)
            hover = rect.collidepoint(mx, my)
            if hover:
                hover_tid = tid
            bg = (c['selection_bg'] if on
                  else (c['button_hover'] if hover else c['button_bg']))
            pygame.draw.rect(self.screen, bg, rect, border_radius=6)
            pygame.draw.rect(self.screen,
                             c['border'] if on else c['dialog_border'],
                             rect, 2 if on else 1, border_radius=6)
            self._med_tool_glyph(tid, rect, on or hover)
        # tooltip：hover 的工具在右侧画名 + 快捷键
        if hover_tid is not None:
            label, shortcut, _k = MED_TOOLS[hover_tid]
            tip = label + (('  ' + shortcut) if shortcut else '')
            tf = self._med_font(13)
            tw = tf.size(tip)[0] + 14
            tr = pygame.Rect(rail.right + 6, my - 12, tw, 24)
            pygame.draw.rect(self.screen, c['menu_bg'], tr)
            pygame.draw.rect(self.screen, c['dialog_border'], tr, 1)
            self.screen.blit(tf.render(tip, True, c['dialog_title']),
                             (tr.x + 7, tr.y + 4))

    def _med_tool_glyph(self, tid, rect, active):
        """工具栏图标（简单几何符号，几何画板风）。"""
        col = (235, 210, 90) if active else (200, 200, 210)
        cx, cy = rect.center
        g = min(rect.w, rect.h)
        if tid == 'select':
            pygame.draw.line(self.screen, col, (cx - g * 0.25, cy + g * 0.25),
                            (cx + g * 0.1, cy - g * 0.25), 3)
            pygame.draw.line(self.screen, col, (cx + g * 0.1, cy - g * 0.25),
                            (cx - g * 0.05, cy - g * 0.1), 3)
            pygame.draw.line(self.screen, col, (cx + g * 0.1, cy - g * 0.25),
                            (cx + g * 0.25, cy - g * 0.05), 3)
        elif tid == 'place':
            pygame.draw.polygon(self.screen, col,
                [(cx, cy - g * 0.3), (cx + g * 0.3, cy + g * 0.2),
                 (cx - g * 0.3, cy + g * 0.2)])
        elif tid == 'erase':
            pygame.draw.rect(self.screen, col,
                (cx - g * 0.22, cy - g * 0.22, g * 0.44, g * 0.3), 0, border_radius=2)
            pygame.draw.line(self.screen, col, (cx + g * 0.18, cy - g * 0.3),
                            (cx + g * 0.3, cy - g * 0.18), 3)
        elif tid == 'band':
            pygame.draw.circle(self.screen, col, (cx - g * 0.12, cy), g * 0.13, 2)
            pygame.draw.circle(self.screen, col, (cx + g * 0.12, cy), g * 0.13, 2)
        elif tid in ('copy', 'paste'):
            if tid == 'copy':
                pygame.draw.rect(self.screen, col,
                    (cx - g * 0.2, cy - g * 0.2, g * 0.26, g * 0.34), 2)
                pygame.draw.rect(self.screen, col,
                    (cx - g * 0.02, cy - g * 0.12, g * 0.26, g * 0.34), 2)
            else:
                pygame.draw.rect(self.screen, col,
                    (cx - g * 0.22, cy - g * 0.22, g * 0.34, g * 0.36), 2)
                pygame.draw.rect(self.screen, col,
                    (cx - g * 0.12, cy - g * 0.3, g * 0.2, g * 0.1), 2)
        elif tid == 'array':
            for dx in (-0.18, 0.06):
                for dy in (-0.18, 0.06):
                    pygame.draw.rect(self.screen, col,
                        (cx + dx * g, cy + dy * g, g * 0.16, g * 0.16), 2)
        elif tid == 'rotate':
            r = g * 0.26
            pygame.draw.arc(self.screen, col, (cx - r, cy - r, 2 * r, 2 * r),
                           -2.2, 1.2, 3)
            pygame.draw.line(self.screen, col, (cx + r * 0.7, cy - r * 0.7),
                            (cx + r * 0.95, cy - r * 0.95), 3)
        elif tid == 'mirror':
            pygame.draw.line(self.screen, col, (cx, cy - g * 0.28),
                            (cx, cy + g * 0.28), 2)
            pygame.draw.polygon(self.screen, col,
                [(cx - g * 0.28, cy - g * 0.2), (cx - g * 0.05, cy),
                 (cx - g * 0.28, cy + g * 0.2)])
            pygame.draw.polygon(self.screen, col,
                [(cx + g * 0.28, cy - g * 0.2), (cx + g * 0.05, cy),
                 (cx + g * 0.28, cy + g * 0.2)])

    def _med_tools_click(self, x, y):
        med = self._med
        for rect, tid in med['tool_rects']:
            if rect.collidepoint(x, y):
                self._med_tool_activate(tid)
                return True
        return True

    def _med_tool_activate(self, tid):
        med = self._med
        label, shortcut, kind = MED_TOOLS[tid]
        if kind == 'tool':
            med['tool'] = tid
            if tid != 'place':
                med['ghost'] = None
            self._med_notify('工具：' + label)
            return
        if tid == 'copy':
            self._med_copy_sel()
        elif tid == 'paste':
            self._med_paste_begin()
        elif tid == 'array':
            self._med_array_dlg_open()
        elif tid == 'rotate':
            self._med_rotate()
        elif tid == 'mirror':
            self._med_mirror()

    def _med_panel_rect(self):
        # 几何画板风：属性/库面板放画布右侧（2026-10-28 重做）
        x = self.screen_width - _PANEL_W - 10
        return pygame.Rect(x, self.menu_bar_height + 10,
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
        """工具条矩形：介于左侧工具栏与右侧属性面板之间（2026-10-28 重做）。

        不再走 ``chrome.bar_rect`` 的 ``right_panel_width`` 机制——那个 132 是
        主游戏右侧信息面板的宽，与本编辑器的属性面板（``_PANEL_W``）不是一回事；
        直接用本面板左缘当右界，避免工具条压到右面板（实测 bar.right=861 >
        panel.left=775 的重叠）。
        """
        left = _TOOLBAR_X + _TOOL_W + 18
        right = self._med_panel_rect().left - 10
        top = self.screen_height - self.status_bar_height - _BAR_H - 8
        return pygame.Rect(left, top, max(240, right - left), _BAR_H)

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
                if med['press'].get('mode') == 'boxselect':
                    self._med_boxsel_up()
                else:
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
        if med.get('array_dlg') is not None:
            # 「阵列」弹窗开着时只认 ESC（取消），其余键一并吞掉
            if k == pygame.K_ESCAPE:
                med['array_dlg'] = None
            return True
        if ctrl and k == pygame.K_c:
            self._med_copy_sel()
            return True
        if ctrl and k == pygame.K_v:
            self._med_paste_begin()
            return True
        if k == pygame.K_ESCAPE:
            if self._med_paste_cancel():     # 粘贴浮动中：ESC 先撤副本
                return True
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
        """左键语义由当前工具决定（几何画板风，2026-10-28 重做）：

        * select：左键拖＝框选、点＝选单块/取消选择
        * place（默认）：左键点空白＝放块、按已有块拖＝移动（见 _med_press_down）
        * erase：左键点块＝删除
        * band：左键点缝＝捆绑/解绑
        右键＝取消选择（与 ESC 取消选区同义）。中键＝平移。
        """
        med = self._med
        x, y = event.pos
        if med.get('open_list') is not None:
            # 「打开模型」列表模态中：一切点击只归列表（命中/取消）
            return self._med_open_list_click(x, y)
        if med.get('array_dlg') is not None:
            return self._med_array_dlg_click(x, y)
        if self._med_toolbar_rect().collidepoint(x, y):
            return self._med_tools_click(x, y)
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
            # 右键 = 取消选择（与 ESC 取消选区同义）
            med['sel'] = set()
            med['ghost'] = None
            return True
        if event.button != 1:
            med['ghost'] = None
            return True
        if med.get('paste') is not None:
            self._med_paste_commit()      # 粘贴浮动中：左键＝落位
            return True
        tool = med['tool']
        if tool == 'select':
            # 左键拖=框选（推迟到松手），点=选单块/取消
            med['press'] = {'sx': x, 'sy': y, 'gx': gx, 'gy': gy,
                            'moved': False, 'mode': 'boxselect'}
            return True
        if tool == 'erase':
            self._med_delete_at(gx, gy)
            return True
        if tool == 'band':
            seam = self._med_seam_at(gx, gy)
            if seam is not None:
                self._med_toggle_bundle(*seam)
            return True
        # 默认 place（含拖动已有块）：现有 press_down 语义
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
        if med.get('press') is not None and med['press'].get('mode') == 'boxselect':
            self._med_boxsel_move(x, y)     # 选择工具：左键拖动 = 框选橡皮筋
            return True
        if med.get('paste') is not None:
            self._med_paste_update(gx, gy)  # 浮动副本跟着鼠标
            return True
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
            # 与放置同口径：玩家锁了朝向就先给锁的那个（否则悬停预览和真放
            # 下的不是同一个朝向，按 R 看起来「没反应」）
            want = self._med_pick_orient(cands)
            poly = next(c[2] for c in cands if c[1] == want)
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
                    med['orient_lock'] = None   # 换形状=重新挑，不继承旧朝向
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
            elif action == 'copy':
                self._med_copy_sel()
            elif action == 'paste':
                self._med_paste_begin()
            elif action == 'array':
                self._med_array_dlg_open()
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
        self._med_draw_sel()
        self._med_draw_paste()
        self._med_draw_rband()
        self._med_draw_tools()
        self._med_draw_panel()
        self._med_draw_bar()
        self._med_draw_open_list()
        self._med_draw_array_dlg()

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
        for (nm, _cf, st, n_mv) in fams:
            row = pygame.Rect(rect.x + 6, y - 2, rect.width - 12, 24)
            med['fam_rows'].append((row, nm))
            on = nm not in med['fam_off']
            if on:
                pygame.draw.rect(self.screen, c['selection_bg'], row)
            mark = '[开]' if on else '[关]'
            desc, screen_ang = eg.direction_desc(st, med['basis'], med['deg'])
            # 左侧小箭头：屏幕方向，一眼看出这族缝朝哪（比文字直觉）
            self._med_fam_arrow(row, screen_ang, on)
            _text(f'{mark} {desc}', f_item,
                  c['menu_text'] if on else c['status_text'], row.x + 26, row.y + 3)
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

    def _med_fam_arrow(self, row, screen_ang, on):
        """缝族行左侧的小箭头：屏幕方向，直观表示这族缝朝哪。"""
        c = self.colors
        cx, cy = row.x + 13, row.y + row.height // 2
        r = 8
        rad = math.radians(screen_ang)
        dx, dy = math.cos(rad) * r, math.sin(rad) * r
        col = c['menu_text'] if on else c['status_text']
        pygame.draw.line(self.screen, col,
                        (cx - dx, cy - dy), (cx + dx, cy + dy), 2)
        # 箭头：在终点画一个「<」形双翼（指向 (dx,dy) 方向）
        back = math.radians(screen_ang + 180)
        left = back + math.radians(30)
        right = back - math.radians(30)
        for a in (left, right):
            ax, ay = math.cos(a) * 5, math.sin(a) * 5
            pygame.draw.line(self.screen, col,
                            (cx + dx, cy + dy), (cx + dx + ax, cy + dy + ay), 2)

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
        w, rh = 440, 30
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
        n_ok = 0
        for name, title, n, why in items:
            row = pygame.Rect(panel.x + 8, y, panel.width - 16, rh - 4)
            lst['rects'].append((row, name))
            if why is None:
                n_ok += 1
            # 开不了的：整行灰、不响应悬停（悬停高亮＝「可点」的承诺）
            hover = why is None and row.collidepoint(*pygame.mouse.get_pos())
            if hover:
                pygame.draw.rect(self.screen, c['selection_bg'], row)
            s = f_item.render(f'{title}（{n} 块）', True,
                              c['menu_text'] if why is None else c['status_text'])
            self.screen.blit(s, (row.x + 8, row.y + 4))
            s2 = f_small.render(name if why is None else why, True,
                                c['status_text'])
            self.screen.blit(s2, (row.right - s2.get_width() - 8, row.y + 7))
            y += rh
        hint = (f'{n_ok} 个可续编；点一项载入，点外面或 ESC 取消' if n_ok
                else '没有可续编的模型；点灰项看原因（点外面或 ESC 取消）')
        self.screen.blit(f_small.render(hint, True, c['status_text']),
                         (panel.x + 14, panel.bottom - 24))

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
                                ('保存 ↵', 'save'), ('阵列', 'array'),
                                ('粘贴', 'paste'), ('复制', 'copy')):
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
        hint = ('左键放/拖块 · 选择工具拖＝框选 · 右键取消选择 · 橡皮点删块 · '
                '捆绑工具点缝 · Ctrl+C/V 复制粘贴 · R/F 转向 · 滚轮缩放')
        hs = f_small.render(hint, True, c['status_text'])
        if hs.get_width() <= rx - (bar.x + 12) - 8:
            self.screen.blit(hs, (bar.x + 12, row2 + 6))
