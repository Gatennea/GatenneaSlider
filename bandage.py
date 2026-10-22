# -*- coding: utf-8 -*-
"""捆綁組簿記（形態無關部分）：三種謎題共用同一套「剛體」語義。

三形態的滑塊都是 `game.Block`（`group` 欄位在 Block 上，0 = 未捆綁），
差別只在座標形狀：

    方形 (r, c)        三角 (i, j, up)      米字 (r, c, q)（r/c 可為半整數）

所以「誰和誰同組、組怎麼序列化、哪條縫卡在組內部」這些都與形態無關，
收在本模組；形態只提供兩個鉤子：

    neighbors_of(pos)            → 與該格共享一條邊的相鄰格
    seam_between_positions(a,b)  → 分隔這兩格的那條縫 (fam, line)；不相鄰回 None

為什麼剛體語義要放在選組（opt）裡而不是移動（try_move_ex）裡：捆綁魔方
的「這一面轉不動」不是靠拒絕移動實現的，而是「先把整組一起塞進選中片，
再照舊做碰撞/連通檢查」——組員被拉扯時自然撞上未選中塊而被拒。這樣
`try_move_ex` / 打亂 / 撤銷全部零改動就繼承了捆綁語義（合法移動收窄為
原遊戲的子集，見 docs/spec/bandaged_mode.md）。
"""


def group_pos(block) -> tuple:
    """Block → 位置元組（形態座標原樣，三角帶 up、米字帶 q）。"""
    return tuple(block.location)


def clear_groups(blocks) -> int:
    """清空全部捆綁組，返回被解散的組數。"""
    gids = {b.group for b in blocks if getattr(b, 'group', 0)}
    for b in blocks:
        b.group = 0
    return len(gids)


def groups_summary(blocks) -> list:
    """當前捆綁組一覽：[(gid, [位置...]), ...]，按 gid 排序（HUD/測試用）。"""
    acc = {}
    for b in blocks:
        g = getattr(b, 'group', 0)
        if g:
            acc.setdefault(g, []).append(group_pos(b))
    return sorted(acc.items())


def groups_as_positions(blocks) -> dict:
    """捆綁狀態的 {位置: gid} 序列化形式（快照/存檔用）。"""
    return {group_pos(b): b.group for b in blocks if getattr(b, 'group', 0)}


def set_groups_from_positions(blocks, mapping) -> int:
    """從 {位置: gid} 恢復捆綁（先清空再灌入）。返回真正命中的塊數。

    位置對不上當前塊（撤銷後盤面已變、存檔與盤面不符）的條目靜默忽略；
    鍵可能是 list（JSON）或 tuple，`1 == 1.0` 在 dict 查找上等價，所以
    半整數與整數混寫也能對上。
    """
    clear_groups(blocks)
    if not mapping:
        return 0
    pmap = {group_pos(b): b for b in blocks}
    hit = 0
    for pos, gid in mapping.items():
        b = pmap.get(tuple(pos))
        if b is not None:
            b.group = int(gid)
            hit += 1
    return hit


def expand_opted_groups(blocks) -> int:
    """把「已選中片裡出現的捆綁組」整組拖進選中，返回額外拉入的塊數。

    這是剛體語義的唯一實現點：opt 選完連通片後調一次，組員即使遠在盤面
    另一頭也會被帶上（隨後由 try_move_ex 判碰撞/斷開而拒絕整步）。
    """
    gids = {b.group for b in blocks
            if getattr(b, 'group', 0) and b.be_opted}
    if not gids:
        return 0
    extra = 0
    for b in blocks:
        if b.group in gids and not b.be_opted:
            b.be_opted = True
            extra += 1
    return extra


def internal_seams(blocks, neighbors_of, seam_between) -> set:
    """所有「分隔同組相鄰兩塊」的縫：{(fam, line), ...}。

    這種縫卡在剛體內部，切不開組——點它應當判定為「選中整組」而不是
    選中一條能拆開的縫。判據用形態自己的相鄰關係 + 縫反推，不寫死幾何，
    因此三角（h/p/n）與米字（h/v/d1/d2，含半整數線號）共用本函式。
    """
    pm = {group_pos(b): b.group for b in blocks}
    res = set()
    for pos, g in pm.items():
        if not g:
            continue
        for nb in neighbors_of(pos):
            nb = tuple(nb)
            if pm.get(nb) != g:
                continue
            seam = seam_between(pos, nb)
            if seam is not None:
                res.add(seam)
    return res


class BandageMixin:
    """形態類的捆綁組 mixin：子類提供兩個幾何鉤子即可獲得完整捆綁 API。

    方形 `SliderMatrix` 自己有一份等價實現（歷史包袱，行為已由測試釘住），
    本 mixin 供三角/米字使用；兩者的對外契約（方法名/返回形狀）保持一致。
    """

    # ---- 子類鉤子 ----
    def neighbors_of(self, pos) -> tuple:
        raise NotImplementedError

    def seam_between_positions(self, a, b):
        raise NotImplementedError

    # ---- 簿記 ----
    def clear_groups(self) -> int:
        return clear_groups(self.blocks)

    def groups_summary(self) -> list:
        return groups_summary(self.blocks)

    def groups_as_positions(self) -> dict:
        return groups_as_positions(self.blocks)

    def set_groups_from_positions(self, mapping) -> int:
        return set_groups_from_positions(self.blocks, mapping)

    def group_of(self, pos) -> int:
        """該位置塊的組號（無此位置/未捆綁回 0）。"""
        for b in self.blocks:
            if group_pos(b) == tuple(pos):
                return getattr(b, 'group', 0)
        return 0

    def bandage_internal_seams(self) -> set:
        return internal_seams(self.blocks, self.neighbors_of,
                              self.seam_between_positions)

    def _expand_opted_groups(self) -> int:
        return expand_opted_groups(self.blocks)
