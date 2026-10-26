# -*- coding: utf-8 -*-
"""谜题菜单悬停预览：从模型文件离屏算出「复原态 / 一种打乱态」两张缩图。

用户 2026-10-26 提的「查」：菜單裡選謎題時，懸停就顯示它的復原態和一種
打亂態。模型谜题的块形状千奇百怪（三角 / 等腰直角 / 半块），列表里那行
「shield（28 块）」根本看不出這題長什麼樣，所以需要圖。

为什么**不**复用 `renderer._draw_polygon_board`
---------------------------------------------
那条通道固定画到 `self.screen`，而且吃 zoom / camera / 选中 / 动画 / 拖拽
一整套 GUI 状态；为了画两张 100px 缩图去换 `self.screen`、再伪造一整套
状态，是拿主渲染开玩笑（任何一处没对上就是主画面闪一下或留脏）。

这里只取 `spec.cell_polygon(point, orient)` 的**平面顶点**——与通用渲染通道
同一个数据源，所以缩图里块的形状、接缝走向与真盘一致；只是把「缝宽内缩 +
圆角」换成 1px 描边（缩到 100px 时缝带本来也不足 1px，内缩只会糊成一团）。

本模块**不碰 pygame.display**、不改任何全局状态；`pygame.Surface` 可以在
display 初始化之前创建，所以单元测试里无头就能跑。

失败不静默
----------
模型文件坏掉 / 打乱抛异常时，返回 `(None, None)` 并把原因放在
`last_error(model_name)`；菜单那边会把「预览不可用：<原因>」画出来，
而不是假装这题没有预览。

为什么有 `request()` 这个异步入口
--------------------------------
首算要真跑一遍引擎打乱。实测最坏的 models/222 首次要 ~500ms（引擎里头
一次会懒建几何/邻接缓存，第二次只要 44ms）——悬停时同步算会卡掉半秒。
`request()` 把首算丢到后台线程，本帧先返回 (None, None)（菜单画「预览
生成中…」），下一帧就有图。线程只做纯计算 + 往普通 Surface 上画
（不碰 display、不建字体），所以不需要 pygame 的主线程约束。
"""
import threading

import pygame

# 缩图边长（px）。104 是「28 块还能看出彼此」「菜单旁边放得下」的折中。
THUMB_SIZE = 104
# 缩图内边距：留一点白边，块不贴着框
_PAD = 5

# (model_name, size, palette) -> (goal_surf, scrambled_surf) 或异常消息
_cache = {}
_lock = threading.Lock()
# 正在后台算的 key：同一张图不重复起线程（悬停项每帧都会来问一次）
_inflight = set()
# 缓存世代：clear_cache() 时 +1。后台线程算完发现世代变了就**不写回**——
# 否则「编辑器存了新形状 → 清缓存 → 旧线程把旧图写回去」会留下旧预览。
_gen = [0]


def clear_cache():
    """清空缓存（模型文件热更 / 换主题后调用）。"""
    with _lock:
        _gen[0] += 1
        _cache.clear()


def last_error(model_name):
    """缓存里该模型上次失败的原因；没失败过返回 None。"""
    with _lock:
        items = list(_cache.items())
    for (name, _size, _pal), val in items:
        if name == model_name and isinstance(val, Exception):
            return str(val)
    return None


def _palette(colors):
    """从 GUI 调色板取画缩图要用的颜色（缺项给安全缺省）。

    只用「背景 / 缝线」两色：背景与真盘同色，缝线取真盘的 `gap` 色
    （真盘的缝带就是这个颜色的深色带）。块色不取 `block`——块按序上色，
    见 `_block_color`。
    """
    colors = colors or {}
    return (
        tuple(colors.get('background', (30, 30, 30))),
        tuple(colors.get('block', (60, 150, 200))),
        tuple(colors.get('gap', (80, 80, 80))),
    )


def _polys_goal(spec):
    """复原态：直接取板型声明的 S₀ 每一块的平面多边形。

    返回 [(像素前多边形, 块序号), ...]——**块序号必须一路带着走**：缩图
    靠它上色（见 `_block_color`），丢了序号就分不出哪块挪到哪了。
    """
    out = []
    for i, b in enumerate(spec.goal_blocks):
        poly = spec.cell_polygon(b.point, b.orient)
        if poly:
            out.append(([(float(x), float(y)) for x, y in poly], i))
    return out


def _polygons_of_board(board):
    """从一局真实棋盘取 [(多边形, 块序号), ...]。

    序号 = 块在 `board.blocks` 里的下标。实测 `board.blocks` 的**顺序**
    与 `spec.goal_blocks` 逐项相同，且打乱（合法滑动只改位置不改对象）
    之后顺序不变 → 下标就是跨状态的块身份，两张缩图靠它对上颜色。
    """
    spec = board.spec
    out = []
    for i, b in enumerate(board.blocks):
        poly = spec.cell_polygon(b.point, b.orient)
        if poly:
            out.append(([(float(x), float(y)) for x, y in poly], i))
    return out


def _polys_scrambled(model_name, step=2, attempts=None):
    """一种打乱态：真跑一遍引擎的打乱，再取各块当前位置的多边形。

    走真引擎而不是「把块随机挪一挪」：模型板型的合法形态由缝族与朝向
    邻接表决定，随手挪出来的是**这题根本走不到的局面**，预览就成了骗人。

    attempts 取 GUI 打乱口径（m*n*10 = 160）的 **1/4**：缩图只有 104px，
    160 步和 40 步看起来一样散，但 222 那盘实测 160 步要 625ms（悬停时
    同步算会明显卡一下），40 步降到 ~160ms。难度门槛（min_score）整段
    跳过：缩图不在乎难度，只在乎看得出散开了。
    """
    from engine.adapter import create_adapter_puzzle

    if attempts is None:
        attempts = 4 * 4 * 10 // 4
    game = create_adapter_puzzle(model_name, 4, 4, step)
    game.shuffle(attempts, step, bias=0.0, min_score=None, record=[])
    return _polygons_of_board(game.board)


def _block_color(idx, total):
    """第 idx 块（共 total 块）的缩图填充色：青→蓝→紫的色相渐变。

    为什么不能全用同一个块色：合法滑动**不改变整盘轮廓**，而缩图又把块
    压成纯色——两张图于是长得几乎一模一样（实测复原态/打乱态肉眼难分）。
    按块序上色后，打乱 = 同一批颜色散到别处，一眼可见。
    色相收在青→紫这一段：与主题蓝同族，放大看仍然「就是这盘」，
    不会变成彩虹拼盘。
    """
    import colorsys

    t = 0.0 if total <= 1 else idx / float(total - 1)
    r, g, b = colorsys.hsv_to_rgb(0.47 + 0.32 * t, 0.62, 0.82)
    return (int(r * 255), int(g * 255), int(b * 255))


def _fit(polys, size, pad=_PAD):
    """把 [(多边形, 序号)] 等比缩放并居中到 size×size，序号照旧带出来。

    每张缩图**各自**适配自己的包围盒：打乱后块会散开，若两张共用同一
    比例尺，复原态会被压成中间一小坨（模型局的散开幅度能到 3 倍以上）。
    缩图要的是「看清这题长什么样」，不是「比较两张的绝对大小」。
    """
    xs = [p[0] for poly, _ in polys for p in poly]
    ys = [p[1] for poly, _ in polys for p in poly]
    if not xs:
        return []
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    box = max(1, size - 2 * pad)
    scale = min(box / w, box / h)
    ox = (size - w * scale) / 2.0 - x0 * scale
    oy = (size - h * scale) / 2.0 - y0 * scale
    return [([(x * scale + ox, y * scale + oy) for x, y in poly], idx)
            for poly, idx in polys]


def _render(polys, size, palette):
    """画一张缩图：底色 → 全部填块色 → 全部描 1px 缝色。

    与真盘同一套「先全填、再全描」的两趟画法：逐块「填+描」时后画那块的
    填色会吃掉前一块的半条描边，缩到 100px 就是每条边粗细不一。
    """
    bg, _fill, line = palette
    surf = pygame.Surface((size, size))
    surf.fill(bg)
    fitted = _fit(polys, size)
    if not fitted:
        return surf
    total = 1 + max(idx for _poly, idx in fitted)
    for poly, idx in fitted:
        if len(poly) >= 3:
            pygame.draw.polygon(surf, _block_color(idx, total), poly)
    # 描边宽度随缩图尺寸走：104px 用 1px，更大的尺寸给 2px 免得糊
    width = 1 if size <= 160 else 2
    for poly, _idx in fitted:
        if len(poly) >= 3:
            pygame.draw.polygon(surf, line, poly, width)
    return surf


def _compute(key):
    """真算一张（同步）：写进缓存，失败时把异常本身留在缓存里。"""
    from engine import model_registry

    with _lock:
        gen = _gen[0]
    model_name, size, pal = key
    try:
        model = model_registry.loaded(model_name)
        spec = model.spec
        if not spec.goal_blocks or spec.cell_polygon is None:
            raise ValueError('该板型没有声明 goal_blocks / cell_polygon')
        goal = _render(_polys_goal(spec), int(size), pal)
        scr = _render(_polys_scrambled(model_name), int(size), pal)
        val = (goal, scr)
    except Exception as exc:      # noqa: BLE001 —— 见模块头「失败不静默」
        val = exc
    with _lock:
        if _gen[0] == gen:        # 算的途中被 clear_cache() 过 → 作废，不写回
            _cache[key] = val
    return val


def _lookup(key):
    """读缓存：命中返回 (True, 值)，未命中返回 (False, None)。"""
    with _lock:
        if key in _cache:
            return True, _cache[key]
    return False, None


def thumbs(model_name, size=THUMB_SIZE, colors=None):
    """**同步**返回 (复原态 Surface, 打乱态 Surface)；算不出来时 (None, None)。

    结果按 (模型名, 尺寸, 配色) 缓存——菜单每帧都会调用，重算一次要真跑
    一遍打乱（首算最坏 ~500ms），悬停时逐帧重算必然卡。
    菜单渲染请用 `request()`（异步版），这里留给测试与需要确定结果的场合。
    """
    key = (model_name, int(size), _palette(colors))
    hit, val = _lookup(key)
    if not hit:
        val = _compute(key)
    return val if isinstance(val, tuple) else (None, None)


def request(model_name, size=THUMB_SIZE, colors=None):
    """**异步**版：已算好就立刻返回；没算好就丢给后台线程，本帧返回 (None, None)。

    返回 `(goal_surf, scrambled_surf, state)`，state 取值：
      - `'ready'`   两张图都在（含失败情形，此时两图为 None，见 `last_error`）
      - `'pending'` 正在后台算，下一帧再问
    """
    key = (model_name, int(size), _palette(colors))
    hit, val = _lookup(key)
    if hit:
        return (val[0], val[1], 'ready') if isinstance(val, tuple) \
            else (None, None, 'ready')
    with _lock:
        spawn = key not in _inflight
        if spawn:
            _inflight.add(key)
    if spawn:
        def _worker():
            try:
                _compute(key)
            finally:
                with _lock:
                    _inflight.discard(key)
        threading.Thread(target=_worker, name='model-preview',
                         daemon=True).start()
    return None, None, 'pending'
