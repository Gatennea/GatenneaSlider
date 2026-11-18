# -*- coding: utf-8 -*-
"""三维创造模式：放块 / 挖块的编辑会话（方案第 1–2 步，2026-11-18）。

设计口径（见 ``docs/spec/三维创造模式方案_2026-11-18.md``）：
* 编辑的不是一份独立的「预览游戏」，而是**当前这局**：进入时用
  ``snapshot_state`` 备份，取消时 ``restore_state`` 原样退回；每次增删
  都 ``draft.apply_to(self.game)``，所以 ``draw_cubic_board`` 画的就是真盘。
* 放/挖只借 MC 的手势：点在**可见面**上——挖 = 拿掉这块，放 = 往面外
  的邻格放一块。拖动仍然是旋转（复用事件层的 trackball）。
* 保存门只做必要条件（连通 / 有合法步 / 长方体块数与 mod 配额），不承诺
  三维可解；UI 文案必须照实说「只做必要条件」。

这个模块只放编辑会话本身；首页按钮、工具条画法留在 ``gui/annotation.py``
的钩子里（和二维创造的首页/工具栏同一套 chrome）。
"""

import pygame

from engine.cubic_edit import CubicDraft
from engine import cubic_view


# 放/挖失败的原因码 → 给玩家看的中文（保存门的原因在 cubic_edit.REASON_TEXT）
EDIT_TEXT = {
    'out_of_bounds': '超出容积，放不进去',
    'occupied': '这个格子已经有块了',
    'empty': '这个格子是空的，挖不到块',
}


class CubicCreateMixin:
    """三维创造编辑器（由 GUI 多继承，和 AnnotationMixin 共用 self.game）。"""

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def _cubic_edit_init_state(self):
        """初始化编辑会话（GUI.__init__ → _ann_init_state 末尾调用）。"""
        self._cubic_edit_active = False
        self._cubic_edit_purpose = 'puzzle'   # 'puzzle'（造打乱局面）
        self._cubic_draft = None
        self._cubic_edit_backup = None        # game.snapshot_state()
        self._cubic_edit_goal_backup = None   # 进入前的 goal_pattern
        self._cubic_edit_vk_prev = None       # 进入前虚拟键盘开关（编辑时先收）
        self._cubic_edit_tool = 'remove'      # 'add' 放块 / 'remove' 挖块
        self._cubic_edit_hover = None         # 预览目标位置 (r, c, d)
        self._cubic_edit_hover_valid = False
        self._cubic_edit_btn_rects = {}       # 每帧重建的工具条按钮

    # ------------------------------------------------------------------
    # 进入 / 退出
    # ------------------------------------------------------------------
    def _cubic_edit_start(self, purpose='puzzle'):
        """进入三维编辑会话：以当前局为草稿。"""
        if getattr(self, '_cubic_edit_active', False):
            return False
        if not getattr(self, 'cubic_mode', False):
            self._ann_notify('三维创造只在三维谜题里可用')
            return False
        game = getattr(self, 'game', None)
        if game is None:
            self._ann_notify('还没有可编辑的谜题')
            return False
        m = int(getattr(game, 'm', 0) or getattr(self, 'current_m', 0) or 0)
        n = int(getattr(game, 'n', 0) or getattr(self, 'current_n', 0) or 0)
        d = int(getattr(game, 'depth', 0)
                or getattr(self, 'current_depth', 0) or 0)
        if min(m, n, d) < 1:
            self._ann_notify('当前三维谜题尺寸无效')
            return False
        try:
            cells = [tuple(int(v) for v in b.location[:3])
                     for b in game.blocks]
            # 等级/步长在 GUI 的 current_step，不在 EngineGame 上
            draft = CubicDraft(m, n, d,
                               int(getattr(self, 'current_step', 1) or 1),
                               cells)
        except (TypeError, ValueError) as exc:
            self._ann_notify(f'读不出当前局面：{exc}')
            return False

        self._cubic_edit_active = True
        self._cubic_edit_purpose = purpose
        self._cubic_draft = draft
        self._cubic_edit_backup = game.snapshot_state()
        self._cubic_edit_goal_backup = getattr(game, 'goal_pattern', None)
        self._cubic_edit_tool = 'remove'
        self._cubic_edit_hover = None
        self._cubic_edit_hover_valid = False
        self._cubic_edit_btn_rects = {}
        # 编辑时先收起虚拟键盘/坐标轴，把棋盘让出来；退出恢复原开关
        self._cubic_edit_vk_prev = getattr(self, 'show_virtual_keyboard', True)
        self.show_virtual_keyboard = False
        self._ann_view = 'cubic_edit'
        self._ann_home_sub = None
        self._ann_sub_dialog = None
        self._ann_design_style_menu = None
        self._ann_model_menu = None
        self._ann_pick = None
        self.selected_gap = None
        self.selected_block = None
        self._ann_notify('三维搭建：左键点块挖除，切到「放置」点面外放块；拖动旋转')
        return True

    def _cubic_edit_leave(self, silent=False, cancel=True):
        """退出编辑会话；cancel=True 时把盘面恢复到进入前。"""
        if not getattr(self, '_cubic_edit_active', False):
            return
        game = getattr(self, 'game', None)
        if cancel and game is not None and self._cubic_edit_backup is not None:
            try:
                game.restore_state(self._cubic_edit_backup)
                if self._cubic_edit_goal_backup:
                    game.set_goal_pattern(self._cubic_edit_goal_backup)
                else:
                    game.clear_goal_pattern()
            except Exception:      # noqa: BLE001 —— 取消不能把界面搞崩
                pass
        self._cubic_edit_active = False
        self._cubic_draft = None
        self._cubic_edit_backup = None
        self._cubic_edit_goal_backup = None
        self._cubic_edit_hover = None
        self._cubic_edit_hover_valid = False
        self._cubic_edit_btn_rects = {}
        if self._cubic_edit_vk_prev is not None:
            self.show_virtual_keyboard = self._cubic_edit_vk_prev
        self._cubic_edit_vk_prev = None
        self._ann_view = 'home'
        self._ann_home_sub = None
        self.selected_gap = None
        self.selected_block = None
        if not silent:
            self._ann_notify('已取消三维搭建，盘面回到进入前')

    def _cubic_edit_cancel(self):
        self._cubic_edit_leave()

    # ------------------------------------------------------------------
    # 草稿写回
    # ------------------------------------------------------------------
    def _cubic_edit_apply(self):
        """草稿 → 当前局（渲染/试玩同源）。"""
        if not getattr(self, '_cubic_edit_active', False):
            return
        try:
            self._cubic_draft.apply_to(self.game)
        except Exception as exc:   # noqa: BLE001
            self._ann_notify(f'写回局面失败：{exc}')
            return
        self.selected_gap = None
        self.selected_block = None
        # 跟随质心在块数变化后会追新中心，丢掉上一帧的插值起点
        self._cubic_follow_center = None
        self._cubic_scene = None

    def _cubic_edit_length(self):
        draft = getattr(self, '_cubic_draft', None)
        return len(draft) if draft is not None else 0

    # ------------------------------------------------------------------
    # 按钮
    # ------------------------------------------------------------------
    def _ann_btn_cubic_manual_build(self):
        """首页「① 打乱状态设计 → 三维搭建」：造一个可玩的打乱局面。"""
        self._cubic_edit_start('puzzle')

    def _ann_btn_cubic_goal_build(self):
        """首页「② 还原状态设计 → 三维搭建」：造自定义还原目标。"""
        self._cubic_edit_start('goal')

    def _cubic_edit_toggle_tool(self, tool):
        self._cubic_edit_tool = 'add' if tool == 'add' else 'remove'
        self._ann_notify('工具：放置（点面外放块）' if tool == 'add'
                         else '工具：挖除（点块拿掉）')

    def _cubic_edit_reset(self):
        if not getattr(self, '_cubic_edit_active', False):
            return
        self._cubic_draft.reset_solved()
        self._cubic_edit_apply()
        self._ann_notify('已恢复为实心还原态（只是草稿，点「完成」才落盘）')

    def _cubic_edit_clear(self):
        if not getattr(self, '_cubic_edit_active', False):
            return
        self._cubic_draft.clear()
        self._cubic_edit_apply()
        self._ann_notify('已清空（空盘不能当谜题，完成前的保存门会拦下）')

    def _cubic_edit_commit(self):
        """保存门 → 把草稿变成当前谜题。"""
        if not getattr(self, '_cubic_edit_active', False):
            return False
        if self._cubic_edit_purpose == 'goal':
            # 还原目标允许是「满实心长方体」这种冻形，所以只过 restorable
            # 必要条件（块数 + mod 配额），不套 check_save 的「必须有合法步」。
            gate = self._cubic_draft.check_restorable()
            if not gate.ok:
                self._ann_notify(f'还原目标还不能保存：{gate.message}')
                return False
            self.game.apply_pattern(sorted(self._cubic_draft.cells))
            self.game.set_goal_pattern(sorted(self._cubic_draft.cells))
            self._ann_style_goal = None
        else:
            gate = self._cubic_draft.check_save()
            if not gate.ok:
                self._ann_notify(f'还不能完成：{gate.message}')
                return False
            # 草稿在每次增删时已写回，这里只做「落盘为第 0 步」
            self._cubic_edit_apply()
        self.selected_gap = None
        self.selected_block = None
        self.step_count = 0
        self.center_map()
        self.game_history.reset()
        self.game_history.save_snapshot(self.game)
        self._mark_file_dirty()
        self._cubic_edit_leave(silent=True, cancel=False)
        self._ann_notify('三维谜题已设为当前局面（只过了必要条件；'
                         '三维求解器未接，不保证可解）')
        return True

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _cubic_edit_event(self, event):
        """编辑会话事件；返回 True=已消费。"""
        # 进入搭建后是模态会话：顶栏也吃掉，逼玩家先「完成」或「取消」，
        # 免得从文件菜单绕过保存门把半成品局面直接存出去。
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                          pygame.MOUSEMOTION) and getattr(event, 'pos', (0, 999))[1] < 34:
            if event.type == pygame.MOUSEBUTTONDOWN:
                self._ann_notify('先点「完成」或「取消」退出搭建，再用文件/设置菜单')
            return True

        if event.type == pygame.KEYDOWN:
            key = event.key
            if key == pygame.K_ESCAPE:
                self._cubic_edit_cancel()
            elif key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
                self._cubic_edit_commit()
            elif key in (pygame.K_1, pygame.K_KP1):
                self._cubic_edit_toggle_tool('add')
            elif key in (pygame.K_2, pygame.K_KP2):
                self._cubic_edit_toggle_tool('remove')
            elif key in (pygame.K_r, pygame.K_R):
                self._cubic_edit_reset()
            elif key in (pygame.K_c, pygame.K_C):
                self._cubic_edit_clear()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # 工具条优先；否则进拖动/点击二择一
                for name, rect in self._cubic_edit_btn_rects.items():
                    if rect.collidepoint(event.pos):
                        self._cubic_edit_button(name)
                        return True
                # 工具条空白处也不许穿透到后面的方块，否则点条边会误挖/误放
                bar = getattr(self, '_ann_bar_rect', None)
                if bar is not None and bar.collidepoint(event.pos):
                    return True
                self._cubic_drag_begin(*event.pos)
                self._cubic_edit_hover_update(event.pos)
                return True
            return True

        if event.type == pygame.MOUSEMOTION:
            if getattr(self, 'cubic_dragging', False):
                self._cubic_drag_update(event.pos)
            else:
                self._cubic_edit_hover_update(event.pos)
            return True

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and getattr(self, 'cubic_dragging', False):
                if not getattr(self, 'cubic_drag_moved', False):
                    start = getattr(self, 'cubic_drag_start', event.pos)
                    self._cubic_edit_click(start)
                self.cubic_dragging = False
                self._cubic_edit_hover_update(event.pos)
                return True
            return True

        if event.type == pygame.MOUSEWHEEL:
            if pygame.key.get_mods() & pygame.KMOD_CTRL:
                self._cubic_zoom_by(1.1 if event.y > 0 else 0.9)
            return True

        return True

    def _cubic_edit_button(self, name):
        if name == 'tool_add':
            self._cubic_edit_toggle_tool('add')
        elif name == 'tool_remove':
            self._cubic_edit_toggle_tool('remove')
        elif name == 'reset':
            self._cubic_edit_reset()
        elif name == 'clear':
            self._cubic_edit_clear()
        elif name == 'commit':
            self._cubic_edit_commit()
        elif name == 'cancel':
            self._cubic_edit_cancel()

    # ------------------------------------------------------------------
    # 拾取 / 预览
    # ------------------------------------------------------------------
    def _cubic_edit_hover_update(self, pos):
        self._cubic_edit_hover = None
        self._cubic_edit_hover_valid = False
        if not getattr(self, '_cubic_edit_active', False):
            return
        scene = getattr(self, '_cubic_scene', None)
        if not scene:
            return
        from engine.cubic_pick import hit_face
        face = hit_face(scene.get('faces'), pos)
        if face is None:
            return
        if self._cubic_edit_tool == 'remove':
            target = tuple(face['loc'])
            self._cubic_edit_hover = target
            self._cubic_edit_hover_valid = self._cubic_draft.contains(target)
        else:
            target = self._cubic_draft.neighbor(face['loc'],
                                                face['axis'], face['sign'])
            self._cubic_edit_hover = tuple(target)
            # 与 add() 的判定同源：容积内且当前没有块
            from engine.cubic_edit import in_volume
            self._cubic_edit_hover_valid = (
                in_volume(target, self._cubic_draft.m,
                          self._cubic_draft.n, self._cubic_draft.d)
                and not self._cubic_draft.contains(target))

    def _cubic_edit_click(self, pos):
        """一次点击：按当前工具放/挖；失败把原因原样说出来。"""
        scene = getattr(self, '_cubic_scene', None)
        if not scene:
            return
        from engine.cubic_pick import hit_face
        face = hit_face(scene.get('faces'), pos)
        if face is None:
            self._ann_notify('点空白不能放/挖；拖动画面可以旋转')
            return
        if self._cubic_edit_tool == 'remove':
            result = self._cubic_draft.remove(face['loc'])
        else:
            target = self._cubic_draft.neighbor(face['loc'],
                                                face['axis'], face['sign'])
            result = self._cubic_draft.add(target)
        if not result.ok:
            self._ann_notify(EDIT_TEXT.get(result.reason, result.reason))
            return
        self._cubic_edit_apply()
        self._ann_notify(f'{"已放一块" if self._cubic_edit_tool == "add" else "已挖掉一块"}'
                         f'（当前 {self._cubic_edit_length()} 块）')

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def _cubic_edit_draw_overlay(self):
        """在棋盘上画半透明幽灵：绿=可放/可挖，红=不可。"""
        if not getattr(self, '_cubic_edit_active', False):
            return
        target = getattr(self, '_cubic_edit_hover', None)
        scene = getattr(self, '_cubic_scene', None)
        if target is None or not scene:
            return
        color = (70, 220, 120) if self._cubic_edit_hover_valid else (235, 95, 95)
        polys = []
        if self._cubic_edit_tool == 'remove':
            # 挖：直接描出这一块现有的可见面
            for face in scene.get('faces', ()):
                if tuple(face.get('loc', ())) == target:
                    polys.append(face['pts'])
        else:
            # 放：用同一个相机/比例画一块幽灵的可见面（不进入真实拾取缓存）
            ghost = cubic_view.collect_faces(
                [target], scene['camera'], scale=scene['scale'],
                origin=scene['origin'], gap=scene.get('gap', 0.0))
            polys = [f['pts'] for f in ghost]
        if not polys:
            return
        xs = [p[0] for poly in polys for p in poly]
        ys = [p[1] for poly in polys for p in poly]
        x0, y0 = int(min(xs)) - 2, int(min(ys)) - 2
        w, h = int(max(xs)) - x0 + 3, int(max(ys)) - y0 + 3
        if w <= 0 or h <= 0:
            return
        surface = pygame.Surface((w, h), pygame.SRCALPHA)
        for poly in polys:
            shifted = [(p[0] - x0, p[1] - y0) for p in poly]
            pygame.draw.polygon(surface, (*color, 95), shifted)
            pygame.draw.polygon(surface, (*color, 230), shifted, 2)
        self.screen.blit(surface, (x0, y0))

    def _cubic_edit_draw_bar(self, rect):
        """底部工具条：放置/挖除/还原态/清空/完成/取消 + 当前块数。"""
        from gui import editor_chrome as chrome
        chrome.shell(self, rect, title='三维搭建（编辑当前局面）')
        self._cubic_edit_btn_rects = {}
        x = rect.x
        y = rect.y + 8
        h = 26

        def add(name, text, color=None):
            nonlocal x
            tw = self.menu_font.size(text)[0] + 22
            r = pygame.Rect(x + 8, y, tw, h)
            x = r.right
            chrome.btn(self, r, text, color, font=self.menu_font)
            self._cubic_edit_btn_rects[name] = r

        add('tool_add', '放置', (70, 120, 180)
            if self._cubic_edit_tool == 'add' else None)
        add('tool_remove', '挖除', (70, 120, 180)
            if self._cubic_edit_tool == 'remove' else None)
        add('reset', '还原态')
        add('clear', '清空', (150, 100, 70))
        add('commit', '完成', (60, 150, 90))
        add('cancel', '取消', (120, 90, 90))

        status = (f'当前 {self._cubic_edit_length()} 块 · '
                  f'工具 {"放置" if self._cubic_edit_tool == "add" else "挖除"}'
                  f' · 左键点面 · 拖动旋转 · Enter 完成 · Esc 取消')
        s = self.status_font.render(status, True, (210, 210, 220))
        self.screen.blit(s, (rect.x + 10, rect.y + 46))
        if self._cubic_edit_length():
            gate = (self._cubic_draft.check_restorable()
                    if self._cubic_edit_purpose == 'goal'
                    else self._cubic_draft.check_save())
            label = '还原目标' if self._cubic_edit_purpose == 'goal' else '保存门'
            note = (f'{label}：可以完成（只过必要条件）' if gate.ok
                    else f'{label}：{gate.message}')
            color = (150, 220, 170) if gate.ok else (225, 170, 120)
        else:
            note, color = '保存门：空盘不能当谜题', (225, 170, 120)
        s2 = self.status_font.render(note, True, color)
        self.screen.blit(s2, (rect.x + 10, rect.y + 64))
