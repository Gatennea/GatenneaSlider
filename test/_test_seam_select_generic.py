# -*- coding: utf-8 -*-
"""回归：通用通道（自造模型）缝命中修复 + 选不中提示文案统一（2026-11-02）。

背景
====
用户报两类问题（临时存档 = shield 自造模型局可复现）：

  B. 缝命中 bug：预期「在一条缝的任何位置，只要该位置两侧有滑块且贯穿谜题，
     就可以选中」；但通用通道（碎三角/shield 等）在某些「两侧有块、缝贯穿
     谜题」的位置却选不中——无白线预览、点击显示选不动。

     根因：缝的视觉身份是接触边足迹（多段锯齿），gap_candidates 只命中距某
     段 ≤ tolerance 的点；足迹在顶点/错位处断开时，断点处及缝线延伸段上的点
     虽合法却 get_gap_at_pos 返回 None。

     修复：get_gap_at_pos 通用通道在「接触边」路径未命中后，加一条「代数缝线
     兜底」——遍历所有合法+活缝，取「点到该缝无限直线垂距 ≤ tol 且两侧局部
     都有块」的缝中垂距最小者（见 GUI.py _generic_gap_at_line /
     _both_sides_blocked）。修复前 shield 局漏选 28 处；修复后 0 处。

  A. 文案统一：一切「选不动」的提示原因一律写「缝没有贯穿滑块组」（用户定调）。

确定性复现（关键）
================
bug 只在「某条缝足迹断开」的**具体盘面**才暴露；new_model_puzzle('shield', 1)
建的是初始解态，足迹连续，复现不出。用户临时存档是一个 shield 局**走完 1 步**
（d60 线 1、方向 E、步长 1）后的盘面——正是足迹断开的那一局。本测试把该盘面
固化为 fixtures/seam_select_bug_shield.json，运行前临时替换 config/temp_history.json，
让 SliderGUI 走与用户完全相同的「自动恢复」路径载入这一确定盘面（结束再还原，
绝不污染用户存档）。

护栏
====
  B1（关键）：沿每条合法+活缝全程采样，凡「两侧局部有块」的点必须被
      get_gap_at_pos 命中（返回非 None）。修复前 FAIL（漏选 28 处），修复后 PASS。
  A3：GAP_UNSELECTABLE_MSG 常量文案含「缝没有贯穿滑块组」。
  A6：拒绝路径（_sq_click_query）静态引用该常量（防止未来又把文案改回内联分支）。
  A5（尽力）：点一条死缝，运行时提示必含「缝没有贯穿滑块组」。

执行：D:/python/python.exe -u test/_test_seam_select_generic.py
"""
import os
import sys
import json
import shutil
import queue
import inspect

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import pygame  # noqa: E402
from GUI import SliderGUI  # noqa: E402
from gui.board_view import point_in_polygon  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures',
                        'seam_select_bug_shield.json')
_failures = []


def check(name, cond, extra=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        _failures.append(name)
    return bool(cond)


def norm(v):
    m = (v[0] * v[0] + v[1] * v[1]) ** 0.5
    return (v[0] / m, v[1] / m) if m > 0 else (0.0, 0.0)


def both_sides(polys, wx, wy, n, eps=3.0):
    a = (wx + n[0] * eps, wy + n[1] * eps)
    b = (wx - n[0] * eps, wy - n[1] * eps)
    return (any(point_in_polygon(a, p) for p in polys)
            and any(point_in_polygon(b, p) for p in polys))


def main():
    # ---- 用固化盘面替换用户临时存档，构造时让 GUI 自动恢复这一确定盘面 ----
    cfg = os.path.join(_PROJ, 'config', 'temp_history.json')
    backup = cfg + '.seamtest_bak'
    had_cfg = os.path.exists(cfg)
    if had_cfg:
        shutil.copyfile(cfg, backup)
    try:
        with open(_FIXTURE, 'r', encoding='utf-8') as f:
            fixture = json.load(f)
        with open(cfg, 'w', encoding='utf-8') as f:
            json.dump(fixture, f, ensure_ascii=False)

        gui = SliderGUI(cmd_queue=queue.Queue(),
                        ext_state={'enabled': False, 'token': None})
        gui.game_mode = 'practice'
        gui.tutorial_active = False
        gui.tut_show_prompt = False
        gui.animation_enabled = False
        gui._update_in_progress = False

        board = gui.game.board
        view = gui._polygon_view()
        origin = gui._poly_view_origin(view)
        check('A1 恢复的是通用通道（spec.cell_polygon）',
              gui._generic_spec() is not None)
        check('A2 块数 = 28', len(board.blocks) == 28,
              f'blocks={len(board.blocks)}')

        tol = 10.0
        gaps = []
        for g in gui.game.all_gaps():
            if g in gaps:
                continue
            if not gui.game.is_valid_gap(*g):
                continue
            if not gui._generic_gap_live(g):
                continue
            gaps.append(g)
        check('B0 存在合法+活缝', len(gaps) > 0, f'n={len(gaps)}')

        polys = [view.world_polygon(b.point, b.orient, origin)
                 for b in board.blocks]

        # B1（关键护栏）：沿每条合法+活缝全程采样，凡「两侧局部有块」的点必须
        #     能被 get_gap_at_pos 命中。修复前 shield 局漏选 28 处 → 此检查 FAIL。
        missed = []
        for g in gaps:
            segs = view.seam_segments(board, g[0], g[1], origin)
            if not segs:
                continue
            (ax, ay), (bx, by) = segs[0]
            d = norm((bx - ax, by - ay))
            n = norm((-(by - ay), (bx - ax)))  # 世界法向 = 缝线方向旋转 90°
            proj_min = float('inf'); proj_max = float('-inf')
            for poly in polys:
                for (vx, vy) in poly:
                    p = (vx - ax) * d[0] + (vy - ay) * d[1]
                    proj_min = min(proj_min, p); proj_max = max(proj_max, p)
            margin = tol * 1.5
            span = proj_max - proj_min + 2 * margin
            nsteps = max(8, int(span / 4.0))
            for k in range(nsteps + 1):
                s = proj_min - margin + span * k / nsteps
                px, py = ax + d[0] * s, ay + d[1] * s
                if not both_sides(polys, px, py, n):
                    continue
                sx, sy = gui.world_to_screen(px, py)
                sel = gui.get_gap_at_pos(int(round(sx)), int(round(sy)))
                if sel is None:
                    missed.append((g, (round(px, 1), round(py, 1))))
                    if len(missed) <= 8:
                        print(f'   gap={g} world=({round(px,1)},{round(py,1)})')

        check('B1 两侧有块的缝位置全部可命中（0 漏选）', len(missed) == 0,
              f'missed={len(missed)}')
        if missed:
            print(f'   [repro] 共 {len(missed)} 处两侧有块却选不中 → 命中 bug 未修复')

        # A. 文案统一：选不中缝提示原因一律含「缝没有贯穿滑块组」
        msg = getattr(gui, 'GAP_UNSELECTABLE_MSG', '')
        check('A3 GAP_UNSELECTABLE_MSG 含「缝没有贯穿滑块组」',
              '缝没有贯穿滑块组' in msg, f'msg={msg!r}')

        # A6：拒绝路径静态引用该常量（防止未来把文案改回内联多分支）
        try:
            src = inspect.getsource(SliderGUI._sq_click_query)
        except (TypeError, OSError):
            src = ''
        check('A6 拒绝路径引用 GAP_UNSELECTABLE_MSG（非内联多分支）',
              'GAP_UNSELECTABLE_MSG' in src)

        # A5（尽力）：点一条「有效但死」的缝，运行时提示必含「缝没有贯穿滑块组」
        dead = None
        for g in gui.game.all_gaps():
            if gui.game.is_valid_gap(*g) and not gui._generic_gap_live(g):
                dead = g
                break
        if dead is not None:
            segs = view.seam_segments(board, dead[0], dead[1], origin)
            if segs:
                (ax, ay), (bx, by) = segs[0]
                mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
                sx, sy = gui.world_to_screen(mx, my)
                pre = gui.get_gap_at_pos(int(round(sx)), int(round(sy)))
                check('A4 死缝位置 get_gap_at_pos=None（确为选不动）',
                      pre is None, f'got={pre}')
                gui.selected_gap = None
                gui.selected_block = None
                gui.rejected_gap = None
                gui.macro_notify_msg = None
                gui._update_in_progress = False
                try:
                    pygame.mouse.set_pos((int(round(sx)), int(round(sy))))
                    ev = pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN, button=1,
                        pos=(int(round(sx)), int(round(sy))))
                    pygame.event.post(ev)
                    gui.handle_events()
                except Exception as exc:
                    check('A5 点击死缝无异常', False, f'exc={exc!r}')
                runtime_msg = getattr(gui, 'macro_notify_msg', None) or ''
                check('A5 点击死缝的提示含「缝没有贯穿滑块组」',
                      '缝没有贯穿滑块组' in runtime_msg,
                      f'msg={runtime_msg!r}')
        else:
            print('[SKIP] A4/A5：本局无死缝，跳过运行时文案验证'
                  '（结构检查 A3/A6 已覆盖）')
    finally:
        # 还原用户临时存档，绝不污染
        if had_cfg and os.path.exists(backup):
            shutil.copyfile(backup, cfg)
            os.remove(backup)
        elif os.path.exists(cfg):
            os.remove(cfg)

    print(f'\n=== {"全部通过" if not _failures else "存在失败: " + str(_failures)} ===')
    raise SystemExit(1 if _failures else 0)


if __name__ == '__main__':
    main()
