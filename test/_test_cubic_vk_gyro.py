# -*- coding: utf-8 -*-
"""回归：虚拟键盘「旋转弧轨」+ 条件键高亮/隐藏。

钉住用户 2026-11-21 的口径：
  A. 仍然只有一个六轴区：六个端点键 + 三条轴中段的旋转弧轨（可拖把手）+
     弧两端的 15° 步进点 + 中心复位键。
  B. 条件键：没选中时六端都是「平移」；选中后只显示真能推的端点，法线轴只
     显示真有下一条的切面键；不可用的键不画、也不吃点击。
  C. 弧轨拖动 = 相机绕该轴连续转，松手停在当前位置；两端点一次 = 15°。
     旋转不推块、不算步、不写历史。
  D. 中心复位只在视角离开默认斜视时出现，回正后消失。
  E. 换视角 / 回正 / 新开三维局时，弧轨把手回到中点。

跑法：D:/python/python.exe test/_test_cubic_vk_gyro.py
"""
import os
import sys
import tempfile

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)
os.chdir(_PROJ)

import math  # noqa: E402
import pygame  # noqa: E402

_ok = [0]
_fail = []


def check(cond, msg, extra=''):
    if cond:
        _ok[0] += 1
        print(f'  ok: {msg}')
    else:
        _fail.append(msg)
        print(f'  FAIL: {msg} {extra}')
    return bool(cond)


from GUI import SliderGUI  # noqa: E402

pygame.init()
gui = SliderGUI(m=4, n=4, step=1)
gui.tut_show_prompt = False
gui.tutorial_active = False
gui.config_dir = tempfile.mkdtemp(prefix='gs_cubic_vk_gyro_')
gui.temp_history_path = os.path.join(gui.config_dir, 'temp_history.json')
gui.config_path = os.path.join(gui.config_dir, 'config.json')
gui._readonly = False
gui.save_readonly_flag = False
gui.animation_enabled = False
gui.screen = pygame.display.set_mode((gui.screen_width, gui.screen_height))
gui.show_virtual_keyboard = True
gui.new_cubic_puzzle(4, 4, 4, 1)
gui.draw_cubic_board()


def arm_gap(fam='c', line=1):
    gui._cubic_clear_selection()
    gui.selected_gap = (fam, line)
    ref = gui.game.blocks[0]
    gui.game.opt(fam, line, ref)
    gui.selected_block = ref
    gui.draw_cubic_board()
    return ref


def post_click(pos):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {'pos': pos, 'button': 1}))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {'pos': pos, 'button': 1}))
    gui.handle_events()


def post_drag(start, end):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {'pos': start, 'button': 1}))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, {'pos': end, 'rel': (0, 0), 'buttons': (1, 0, 0)}))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {'pos': end, 'button': 1}))
    gui.handle_events()


def q_angle(qa, qb):
    dot = min(1.0, abs(sum(a * b for a, b in zip(qa, qb))))
    return math.degrees(2.0 * math.acos(dot))


print('=' * 60)
print('A. 布局：六端 + 三条旋转弧轨 + 中心复位')
rects = gui._vk_build_layout()
cubic = [k for k in rects if k.startswith('cubic_')]
gyro = [k for k in rects if k.startswith('gyro_')]
check(len(cubic) == 6, f'六个端点键仍在（{len(cubic)}）')
check(all('gyro_ccw_' + f in rects and 'gyro_cw_' + f in rects
          for f in ('r', 'c', 'd')), '三条轴各有一对步进点（6 键）')
check(len([k for k in gyro if k != 'gyro_reset']) == 6,
      f'弧轨步进动作数正确（{sorted(k for k in gyro if k != "gyro_reset")}）')
check('gyro_reset' not in rects, '默认斜视下不显示中心复位')
check(len(gui._vk_cubic_rot_tracks) == 3,
      f'默认斜视三条轴都有弧轨（{sorted(gui._vk_cubic_rot_tracks)}）')
check(all(d['theta'] is not None for d in gui._vk_cubic_rot_tracks.values()),
      '每条弧轨都有轴向角')
check(all(gui.vk_panel_rect.contains(d['box'])
          for d in gui._vk_cubic_rot_tracks.values()), '弧轨框都在面板内')
check(all(gui.vk_panel_rect.contains(r) for _a, r in rects.items()),
      '所有动作矩形都在面板内')
bad = []
for fam, d in gui._vk_cubic_rot_tracks.items():
    for letter in ('r', 'R', 'c', 'C', 'd', 'D'):
        if d['box'].colliderect(rects['cubic_' + letter]):
            bad.append((fam, 'cubic_' + letter))
    for fam2, d2 in gui._vk_cubic_rot_tracks.items():
        if fam2 > fam and d['box'].colliderect(d2['box']):
            bad.append((fam, fam2))
check(not bad, f'弧轨框不与端点/其它弧轨抢点击（{bad[:3]}）')
overlaps = []
seen = sorted(rects.items())
for i, (a, ra) in enumerate(seen):
    for b, rb in seen[i + 1:]:
        if a.startswith('gyro_') and b.startswith('gyro_') and a[5:] == b[5:]:
            continue          # 同一条弧轨的两端允许被 36×36 轨道框包住
        if ra.colliderect(rb):
            overlaps.append((a, b))
check(not overlaps, f'默认姿态下动作键互不重叠（{overlaps[:3]}）')

print('A2. 姿态扫描：弧轨与端点在任何朝向下都不抢点击')
from engine.cubic_camera import CubicCamera  # noqa: E402
bad_pose = []
track_missing = 0
for yaw in range(-180, 181, 30):
    for pitch in (-40, -20, 0, 20, 40):
        gui.cubic_camera = CubicCamera.from_yaw_pitch(yaw, pitch)
        rr = gui._vk_build_layout()
        track_missing += 3 - len(gui._vk_cubic_rot_tracks)
        for fam, d in gui._vk_cubic_rot_tracks.items():
            if not gui.vk_panel_rect.contains(d['box']):
                bad_pose.append((yaw, pitch, fam, 'out'))
            for letter in ('r', 'R', 'c', 'C', 'd', 'D'):
                if d['box'].colliderect(rr['cubic_' + letter]):
                    bad_pose.append((yaw, pitch, fam, letter))
            for fam2, d2 in gui._vk_cubic_rot_tracks.items():
                if fam2 > fam and d['box'].colliderect(d2['box']):
                    bad_pose.append((yaw, pitch, fam, fam2))
        items = sorted(rr.items())
        for i, (a, ra) in enumerate(items):
            for b, rb in items[i + 1:]:
                if ra.colliderect(rb):
                    bad_pose.append((yaw, pitch, a, b))
check(not bad_pose,
      f'65 种姿态下所有键不冲突（{len(bad_pose)} 处）', bad_pose[:3])
check(track_missing == 0,
      f'65 种姿态三条轴都放得下弧轨（缺 {track_missing}/195）')
gui.cubic_camera = CubicCamera.oblique_default()
gui._vk_build_layout()

print('B. 条件键：没选中=平移，选中后只亮真能走的')
gui._cubic_clear_selection()
gui.draw_cubic_board()
states = {l: gui._cubic_vk_endpoint_state(l) for l in
          ('r', 'R', 'c', 'C', 'd', 'D')}
check(all(v == 'pan' for v in states.values()), f'没选中时六端全是平移（{states}）')
ref = arm_gap('c', 1)
states2 = {l: gui._cubic_vk_endpoint_state(l) for l in
           ('r', 'R', 'c', 'C', 'd', 'D')}
check(states2['c'] == 'seam' and states2['C'] == 'seam',
      '法线轴 c 两端的 c0/c2 都有效，显示切面键')
for letter in ('r', 'R', 'd', 'D'):
    allowed = gui._arrow_move_allowed(letter)
    check(states2[letter] == ('push' if allowed else 'off'),
          f'{letter} 端点按试推结果亮/隐（{states2[letter]}）')
legal = [l for l, s in states2.items() if s != 'off']
visible = [k for k in rects if k.startswith('cubic_')
           and gui._cubic_vk_action_visible(k)]
check(set(visible) == {'cubic_' + l for l in legal},
      f'布局里可见端点与状态一致（{visible}）')

print('C. 隐藏端点不吃点击')
gui._vk_build_layout()
off = [l for l, s in states2.items() if s == 'off']
if off:
    letter = off[0]
    before_gap = gui.selected_gap
    before_step = gui.step_count
    before_locs = sorted(tuple(int(v) for v in b.location[:3])
                         for b in gui.game.blocks)
    post_click(gui.vk_rects['cubic_' + letter].center)
    check(gui.selected_gap == before_gap, f'点隐藏端点 {letter} 不改切面')
    check(gui.step_count == before_step, '点隐藏端点不涨步数')
    check(sorted(tuple(int(v) for v in b.location[:3])
                 for b in gui.game.blocks) == before_locs, '点隐藏端点不移块')
else:
    check(True, '这一步四向都可推，没有隐藏端点可点')

print('D. 条件不满足：切面端点/推块端点都不显示、不吃点击')
gui.new_cubic_puzzle(4, 4, 4, 1)
gui.selected_gap = ('c', 2)
for b in gui.game.blocks:
    b.be_opted = True                 # 整盘选中 = 平移被规则禁止
gui.selected_block = gui.game.blocks[0]
gui.draw_cubic_board()
states3 = {l: gui._cubic_vk_endpoint_state(l) for l in
           ('r', 'R', 'c', 'C', 'd', 'D')}
check(states3['c'] == 'seam' and states3['C'] == 'off',
      f'c2 只剩负方向有下一条，正端隐藏（{states3}）')
check(all(states3[l] == 'off' for l in ('r', 'R', 'd', 'D')),
      f'整盘选中时四个推块端全隐藏（{states3}）')
gui._vk_build_layout()
before_gap = gui.selected_gap
post_click(gui.vk_rects['cubic_C'].center)
check(gui.selected_gap == before_gap, '点隐藏的 c2 正端不切面')
post_click(gui.vk_rects['cubic_r'].center)
check(gui.selected_gap == before_gap and gui.step_count == 0,
      '点隐藏的推块端不选/不推')

print('E. 弧轨两端：点一次转 15°，不推块/不算步')
gui.new_cubic_puzzle(4, 4, 4, 1)
gui.draw_cubic_board()
q0 = gui.cubic_camera.q
n0 = gui.step_count
h0 = len(gui.game_history.history)
check(gui._vk_trigger_action('gyro_cw_r') is None, '步进动作走独立分支')
q1 = gui.cubic_camera.q
check(abs(q_angle(q0, q1) - 15.0) < 0.5, f'点一次转 15°（{q_angle(q0, q1):.2f}°）')
check(gui.step_count == n0, '旋转不算步')
check(len(gui.game_history.history) == h0, '旋转不写历史')
t_after = gui._vk_rot_t['r']
check(abs(t_after + 1.0 / 6.0) < 1e-6,
      f'cw 步进后把手向负端移动（t={t_after:.3f}）')
gui._vk_trigger_action('gyro_ccw_r')
q2 = gui.cubic_camera.q
check(q_angle(q0, q2) < 1e-4, f'反向步进把视角转回原位（{q_angle(q0, q2):.4f}°）')
gui._vk_build_layout()
q3 = gui.cubic_camera.q
post_click(gui.vk_rects['gyro_ccw_c'].center)
check(q_angle(q3, gui.cubic_camera.q) > 1e-3,
      f'鼠标点弧轨端点真能转动视角（{q_angle(q3, gui.cubic_camera.q):.3f}°）')

print('F. 弧轨拖动：连续转，松手停；不推块/不算步')
gui.new_cubic_puzzle(4, 4, 4, 1)
gui.draw_cubic_board()
gui._vk_build_layout()
fam = 'c'
data = gui._vk_cubic_rot_tracks[fam]
center = data['box'].center
theta = data['theta']
start_ang = theta + math.pi / 2.0
start = (int(center[0] + math.cos(start_ang) * 12.0),
         int(center[1] - math.sin(start_ang) * 12.0))
end_ang = start_ang + math.radians(30.0)
end = (int(center[0] + math.cos(end_ang) * 12.0),
       int(center[1] - math.sin(end_ang) * 12.0))
q_before = gui.cubic_camera.q
n_before = gui.step_count
h_before = len(gui.game_history.history)
post_drag(start, end)
ang = q_angle(q_before, gui.cubic_camera.q)
check(abs(ang - 30.0) < 4.0, f'拖 30° 相机转 30°（{ang:.2f}°）')
check(abs(gui._vk_rot_t[fam] - 1.0 / 3.0) < 0.02,
      f'把手跟着拖到 1/3 处（t={gui._vk_rot_t[fam]:.3f}）')
check(gui.vk_rot_drag is None, '松手后拖拽状态清空')
check(gui.step_count == n_before, '拖动不算步')
check(len(gui.game_history.history) == h_before, '拖动不写历史')
q_hold = gui.cubic_camera.q
gui._vk_build_layout()
data2 = gui._vk_cubic_rot_tracks[fam]
center2 = data2['box'].center
theta2 = data2['theta']
span2 = data2.get('span', math.pi / 2.0)
t_now = gui._vk_rot_t[fam]
end2 = (int(center2[0] + math.cos(theta2 + math.pi / 2.0
                                  + t_now * span2) * 12.0),
        int(center2[1] - math.sin(theta2 + math.pi / 2.0
                                  + t_now * span2) * 12.0))
post_drag(end2, end2)
check(q_angle(q_hold, gui.cubic_camera.q) < 1e-6, '松手后再动鼠标不再旋转')
# 反向拖回：抓新位置上的把手，沿弧退回中点
start2 = (int(center2[0] + math.cos(theta2 + math.pi / 2.0
                                    + gui._vk_rot_t[fam] * span2) * 12.0),
          int(center2[1] - math.sin(theta2 + math.pi / 2.0
                                    + gui._vk_rot_t[fam] * span2) * 12.0))
back2 = (int(center2[0] + math.cos(theta2 + math.pi / 2.0) * 12.0),
         int(center2[1] - math.sin(theta2 + math.pi / 2.0) * 12.0))
q_b = q_before
post_drag(start2, back2)
check(q_angle(q_b, gui.cubic_camera.q) < 8.0,
      f'反向拖回接近起始视角（{q_angle(q_b, gui.cubic_camera.q):.2f}°）')
check(abs(gui._vk_rot_t[fam]) < 0.2, f'把手回到中点附近（t={gui._vk_rot_t[fam]:.3f}）')

print('G. 换视角/回正/新局重置把手')
gui._vk_rot_t = {'r': 0.8, 'c': -0.5, 'd': 0.25}
gui._cubic_view(0)
check(gui._vk_rot_t == {} and gui.vk_rot_drag is None, '切朝向清空把手')
gui._vk_rot_t = {'r': 0.8}
gui._cubic_view_oblique()
check(gui._vk_rot_t == {}, '回正清空把手')
gui._vk_rot_t = {'c': 0.6}
gui.new_cubic_puzzle(4, 4, 4, 1)
check(gui._vk_rot_t == {}, '新开三维局清空把手')

print('H. 中心复位只在偏离默认视角时出现')
gui.new_cubic_puzzle(4, 4, 4, 1)
gui._vk_trigger_action('gyro_cw_r')
rects3 = gui._vk_build_layout()
check('gyro_reset' in rects3, '转过视角后中心出现复位键')
check(not gui._cubic_camera_is_default(), '当前确实不是默认斜视')
check(gui._vk_trigger_action('gyro_reset') is None, '复位动作走独立分支')
check(gui._cubic_camera_is_default(), '复位回到默认斜视')
check('gyro_reset' not in gui._vk_build_layout(), '回正后复位键隐藏')
check(gui._vk_rot_t == {}, '复位同时把把手归中')

print('=' * 60)
print(f'结果：{"全部通过" if not _fail else "有失败"}'
      f'（{_ok[0]} 项通过，{len(_fail)} 项失败）')
if _fail:
    for f in _fail:
        print('  ·', f)
pygame.quit()
sys.exit(1 if _fail else 0)
