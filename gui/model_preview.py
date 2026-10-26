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
生成中…」），下一帧就有图。

⚠️ **后台线程只许算几何（像素多边形），不许碰 pygame**。2026-10-26 踩过：
把「建 Surface + 画多边形」放进后台线程后，真实显示环境下与主线程的
绘制/flip 撞车，悬停即崩。现在 `_build_pics` 纯 Python，Surface 由主线程
的 `_surfaces` 建（一次 0.4ms，之后走缓存）。
"""
import hashlib
import os
import threading
import time

import pygame

# 缩图边长（px）。104 是「28 块还能看出彼此」「菜单旁边放得下」的折中。
THUMB_SIZE = 104
# 缩图内边距：留一点白边，块不贴着框
_PAD = 5

# 两级缓存，分工不能混：
#   _pics  = 纯 Python 的「像素多边形」(model_name, size, palette) -> (goal, scr)
#   _surfs = pygame.Surface 同上 key -> (goal_surf, scr_surf)
# 为什么要拆开：后台线程只许算 _pics（纯数学），Surface 一律主线程建。
# 2026-10-26 事故：早先把「建 Surface + draw.polygon」放进了后台线程，
# 真实显示下与主线程的绘制/flip 撞车，会被 SDL 拒（或被吞成「预览不可用」）。
_pics = {}
_surfs = {}
_lock = threading.Lock()
# 正在后台算的 key：同一张图不重复起线程（悬停项每帧都会来问一次）
_inflight = set()
# 缓存世代：clear_cache() 时 +1。后台线程算完发现世代变了就**不写回**——
# 否则「编辑器存了新形状 → 清缓存 → 旧线程把旧图写回去」会留下旧预览。
_gen = [0]


def clear_cache():
    """清空缓存（模型文件热更 / 换主题后调用）。

    顺手把预热标记复位：下次 pump 会重扫一遍——改了形状的那个模型签名变了
    会重算，没改的直接命中磁盘跳过，代价可忽略。
    """
    with _lock:
        _gen[0] += 1
        _pics.clear()
        _surfs.clear()
        _warm_started[0] = False
        _pump_t0[0] = 0.0      # 重新计时，还是等一秒再开始预热


def last_error(model_name):
    """缓存里该模型上次失败的原因；没失败过返回 None。"""
    with _lock:
        items = list(_pics.items()) + list(_surfs.items())
    for (name, _size, _pal), val in items:
        if name == model_name and isinstance(val, Exception):
            return str(val)
    return None


def _log_failure(model_name, exc):
    """把预览失败写进 error_log.jsonl（含 traceback）。

    为什么必须记：`_compute` 吞掉异常后，唯一的痕迹是菜单上一行「预览不可用」，
    用户看到的却是「卡住/白屏」——2026-10-26 的崩溃就是这样丢掉了真因。
    AGENTS.md §2：except 必须打 traceback。
    """
    try:
        import traceback

        from gui.log_writer import write as _log_write
        _log_write(f'模型预览生成失败：{model_name!r}',
                   trace=traceback.format_exc().splitlines())
    except Exception:
        pass


def _palette(colors):
    """从 GUI 调色板取画缩图要用的颜色（缺项给安全缺省）。

    只用「背景 / 缝线」两色：背景与真盘同色，缝线取真盘的 `gap` 色
    （真盘的缝带就是这个颜色的深色带）。块色取 `block`，与真盘的滑块同色。
    """
    colors = colors or {}
    return (
        tuple(colors.get('background', (30, 30, 30))),
        tuple(colors.get('block', (60, 150, 200))),
        tuple(colors.get('gap', (80, 80, 80))),
    )


def _polys_goal(spec):
    """复原态：直接取板型声明的 S₀ 每一块的平面多边形。

    返回 [(多边形, 块序号), ...]——序号对「画」没用（块色统一），但它把
    「这一块是第几块」一路带下去，将来要在缩图上做标记（比如高亮某块）不必
    再回头改数据结构。
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


def _paint(fitted, size, palette):
    """把已拟合好的多边形画成一张 Surface。**只许在主线程调用**。

    输入是 `_fit` 的输出（像素坐标），不含任何引擎/GUI 状态，所以这件
    「画」的活儿可以晚于「算」，且不需要后台线程碰 pygame。

    块色一律用真盘的 `block` 色（**不按块序上彩虹**）：2026-10-26 实测，
    单色下复原态与打乱态的像素差 26~37%，本来就分得清；彩色渐变既没换来
    可读性，还和「自造谜题画风要和碎三角一致」直接冲突。
    """
    bg, fill, line = palette
    surf = pygame.Surface((size, size))
    surf.fill(bg)
    if not fitted:
        return surf
    for poly, _idx in fitted:
        if len(poly) >= 3:
            pygame.draw.polygon(surf, fill, poly)
    # 描边宽度随缩图尺寸走：104px 用 1px，更大的尺寸给 2px 免得糊
    width = 1 if size <= 160 else 2
    for poly, _idx in fitted:
        if len(poly) >= 3:
            pygame.draw.polygon(surf, line, poly, width)
    return surf


def _build_pics(key):
    """算出两张缩图的**像素多边形**（纯数学，可在后台线程跑），写进 `_pics`。

    失败时把异常本身留在缓存里（见模块头「失败不静默」），并记日志。
    """
    from engine import model_registry

    with _lock:
        gen = _gen[0]
    model_name, size, _pal = key
    try:
        model = model_registry.loaded(model_name)
        spec = model.spec
        if not spec.goal_blocks or spec.cell_polygon is None:
            raise ValueError('该板型没有声明 goal_blocks / cell_polygon')
        val = (_fit(_polys_goal(spec), int(size)),
               _fit(_polys_scrambled(model_name), int(size)))
    except Exception as exc:      # noqa: BLE001 —— 见模块头「失败不静默」
        val = exc
        _log_failure(model_name, exc)
    with _lock:
        if _gen[0] == gen:        # 算的途中被 clear_cache() 过 → 作废，不写回
            _pics[key] = val
    return val


def _surfaces(key, pics):
    """把像素多边形升级成 Surface（主线程；顺手缓存）。返回 (goal, scr) 或异常。"""
    with _lock:
        got = _surfs.get(key)
        gen = _gen[0]
    if got is not None:
        return got
    size, pal = key[1], key[2]
    try:
        val = (_paint(pics[0], size, pal), _paint(pics[1], size, pal))
    except Exception as exc:      # noqa: BLE001 —— 画不出来也只是没有预览
        val = exc
        _log_failure(key[0], exc)
    with _lock:
        if _gen[0] == gen:
            _surfs[key] = val
    return val


def _disk_sig(key):
    """该缩图在磁盘上的身份串：模型内容哈希 + 尺寸 + 配色。

    为什么要模型**内容哈希**而不是文件 mtime：编辑器存盘会重写文件（mtime
    必变），但内容没变时没必要重算；反过来拷机器/回滚代码会让 mtime 倒退而
    内容其实变了。`LoadedModel.hash()` 就是模型身份哈希（存档头也用同一个），
    内容一变即失配，天然自愈。
    """
    from engine import model_registry

    name, size, pal = key
    model = model_registry.loaded(name)
    ph = hashlib.sha1(repr(pal).encode('utf-8')).hexdigest()[:8]
    return f'{name}.{model.hash()}.{int(size)}.{ph}'


def _disk_dir():
    """缩图落盘目录：与 error_log 同一个 config/ 根下（打包后随之退 APPDATA/temp）。"""
    from gui.log_writer import log_paths
    return os.path.join(os.path.dirname(log_paths()[0]), 'preview_cache')


def _disk_paths(key):
    """磁盘路径。**未知模型返回 (None, None)**——不能在这里抛。

    签名取自 `LoadedModel.hash()`，模型名不存在时它会抛 KeyError；若任其外抛，
    「预览算不出来」就会变成「整个预览面板不见」，连「预览不可用：…」都没了。
    真正的失败判定统一交给 `_build_pics`。
    """
    try:
        sig = _disk_sig(key)
    except Exception:      # noqa: BLE001 —— 见 docstring
        return None, None
    base = os.path.join(_disk_dir(), sig)
    return base + '.goal.png', base + '.scr.png'


def _load_disk(key):
    """从磁盘读回两张缩图；没有/坏了返回 None（坏了不留残图，下次重算覆盖）。"""
    gp, sp = _disk_paths(key)
    if gp is None or not (os.path.exists(gp) and os.path.exists(sp)):
        return None
    try:
        goal = pygame.image.load(gp)
        scr = pygame.image.load(sp)
    except Exception as exc:      # noqa: BLE001
        _log_failure(key[0], exc)
        return None
    with _lock:
        _surfs[key] = (goal, scr)
    return goal, scr


def _save_disk(key, surfs):
    """把刚画好的两张缩图存盘（下一次启动直接读，零计算）。"""
    gp, sp = _disk_paths(key)
    if gp is None:
        return
    try:
        os.makedirs(os.path.dirname(gp), exist_ok=True)
        pygame.image.save(surfs[0], gp)
        pygame.image.save(surfs[1], sp)
    except Exception as exc:      # noqa: BLE001 —— 存盘失败只是下次要重算
        _log_failure(key[0], exc)
        return
    # 同一模型的历史世代（改过形状/尺寸/配色）顺手清掉，别让缓存目录长草
    name, size, pal = key
    keep = os.path.basename(gp)[:-len('.goal.png')]
    try:
        for fn in os.listdir(_disk_dir()):
            if fn.startswith(f'{name}.') and fn.endswith('.png') \
                    and not fn.startswith(keep):
                os.remove(os.path.join(_disk_dir(), fn))
    except OSError:
        pass


def _lookup(key):
    """读「像素多边形」缓存：命中返回 (True, 值)，未命中返回 (False, None)。"""
    with _lock:
        if key in _pics:
            return True, _pics[key]
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
        val = _build_pics(key)
    if isinstance(val, Exception):
        return None, None
    val = _surfaces(key, val)
    return val if isinstance(val, tuple) else (None, None)


def request(model_name, size=THUMB_SIZE, colors=None):
    """**异步**版：已算好就立刻返回；没算好就丢给后台线程，本帧返回 (None, None)。

    返回 `(goal_surf, scrambled_surf, state)`，state 取值：
      - `'ready'`   图已就绪（失败时两图为 None，原因见 `last_error`）
      - `'pending'` 正在后台算，下一帧再问

    后台线程只算像素多边形（纯 Python），Surface 由**本函数在主线程**创建，
    见模块头「两级缓存」。
    """
    key = (model_name, int(size), _palette(colors))
    hit, val = _lookup(key)
    if hit:
        if isinstance(val, Exception):
            return None, None, 'ready'
        val = _surfaces(key, val)
        if isinstance(val, Exception):
            return None, None, 'ready'
        return val[0], val[1], 'ready'
    # 磁盘上已有（上次启动预热过）→ 直接读图，本帧就 ready，不起线程
    got = _load_disk(key)
    if got is not None:
        return got[0], got[1], 'ready'
    with _lock:
        spawn = key not in _inflight
        if spawn:
            _inflight.add(key)
    if spawn:
        def _worker():
            try:
                _build_pics(key)
            finally:
                with _lock:
                    _inflight.discard(key)
        threading.Thread(target=_worker, name='model-preview',
                         daemon=True).start()
    return None, None, 'pending'


# ----------------------------------------------------------------------
# 空闲预热：启动后把**所有**模型的两张缩图都算一遍并落盘
# ----------------------------------------------------------------------
# 用户 2026-10-26 提的做法：与其悬停时现算，不如开局后空闲时挨个算好导出。
# 比「悬停现算」好在三处：①悬停零等待（只读盘）②不用在游戏进行中起
# 线程算几何 ③第二次启动连算都不算。
_warm_started = [False]
# 预热起点：第一次 pump 的时刻。预热要错开开局那一下——后台跑打乱是纯 Python
# 重活，会抢 GIL，实测单模型能把某一帧顶到 ~128ms（掉 7 帧）。等一秒再开始，
# 用户已经看清盘面了，卡顿也落在「还没动手」的时候。
_pump_t0 = [0.0]
_WARM_DELAY = 1.0
# 模型之间让路：每个模型之间睡一下，把长卡顿摊成几次短卡顿
_WARM_GAP = 0.12


def warm_names():
    """预热对象：注册表里所有已装模型的等级1/等级2 都画同一张缩图，故只需名字。"""
    from engine import model_registry
    return sorted(model_registry.loaded())


def _warm_worker(names, size, pal):
    """后台：逐个算像素多边形（纯 Python）。已落盘且签名一致的直接跳过。"""
    for i, name in enumerate(names):
        key = (name, int(size), pal)
        if _disk_ok(key):
            continue
        if i:
            time.sleep(_WARM_GAP)
        _build_pics(key)


def _disk_ok(key):
    gp, sp = _disk_paths(key)
    return gp is not None and os.path.exists(gp) and os.path.exists(sp)


def pump(colors=None, size=THUMB_SIZE, budget=1):
    """**每帧调一次**：启动预热 + 把后台算好的图在主线程画出来并存盘。

    budget 限制单帧最多处理几个模型：画一张 0.4ms、存两张 PNG 约 2~5ms，
    一个模型 ~6ms 已够小；设上限是防止「第一次启动同时收到 5 个模型」把
    某一帧撑到 30ms 掉帧。返回本帧实际处理的数量（给测试用）。

    失败一律不抛：预热是纯锦上添花，绝不许影响主循环。
    """
    pal = _palette(colors)
    n = 0
    try:
        if not _pump_t0[0]:
            _pump_t0[0] = time.time()
        if not _warm_started[0] and time.time() - _pump_t0[0] >= _WARM_DELAY:
            _warm_started[0] = True
            threading.Thread(target=_warm_worker,
                             args=(warm_names(), int(size), pal),
                             name='model-preview-warm', daemon=True).start()
        with _lock:
            pending = [(k, v) for k, v in _pics.items()
                       if isinstance(v, tuple) and k not in _surfs]
        for key, pics in pending[:budget]:
            val = _surfaces(key, pics)
            if isinstance(val, tuple):
                _save_disk(key, val)
            n += 1
    except Exception:      # noqa: BLE001 —— 见 docstring
        pass
    return n
