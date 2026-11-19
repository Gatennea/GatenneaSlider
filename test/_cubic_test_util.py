"""三维测试共用的小工具。

2026-11-19 起右键只接受「两块之间的内部切面」；测试里不能再随手取
`faces[-1]` 的面心当缝点——那可能是外表面，点下去现在会正确地被拒绝。
这里按渲染出的本帧面 + 画家序，找一个**真的可见、且确实命中**的内部墙点。
"""


def internal_seam_point(gui, samples=17, families=None):
    """返回 (屏幕点, 切面, 面)；找不到返回 (None, None, None)。

    只扫 `face_is_internal()` 为真的面，并且用 `hit_face()` 确认该点没有被
    更近的块面挡住——否则右键命中的会是另一块的外表面。

    `families` 可限定切面族（例如测试要沿 C 轴推，就避开 c 族切面，
    否则 C 正好是切面法向、必然被拒）。
    """
    from engine import cubic_pick as cp

    locs = {tuple(int(v) for v in b.location[:3]) for b in gui.game.blocks}
    faces = gui._cubic_scene['faces']
    for face in faces:
        if not cp.face_is_internal(face, locs):
            continue
        seam = cp.seam_of_internal_face(face, gui.game.is_valid_gap, locs)
        if seam is None:
            continue
        if families is not None and seam[0] not in families:
            continue
        pts = face['pts']
        for i in range(1, samples):
            for j in range(1, samples):
                u, v = i / samples, j / samples
                x = ((1 - u) * (1 - v) * pts[0][0] + u * (1 - v) * pts[1][0]
                     + u * v * pts[2][0] + (1 - u) * v * pts[3][0])
                y = ((1 - u) * (1 - v) * pts[0][1] + u * (1 - v) * pts[1][1]
                     + u * v * pts[2][1] + (1 - u) * v * pts[3][1])
                point = (int(round(x)), int(round(y)))
                if cp.hit_face(faces, point) is face:
                    return point, seam, face
    return None, None, None
