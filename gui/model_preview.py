# -*- coding: utf-8 -*-
"""谜题菜单悬停预览：离屏算出「复原态 / 一种打乱态」两张缩图。

用户 2026-10-26 提的「查」：菜單裡選謎題時，懸停就顯示它的復原態和一種
打亂態。模型谜题的块形状千奇百怪（三角 / 等腰直角 / 半块），列表里那行
「shield（28 块）」根本看不出這題長什麼樣，所以需要圖。

2026-10-26 晚补：**所有预设都要预览**（用户报「没给所有预设生成预览」）。
早先只做了模型板型，内置板型（矩形/三角/米字/数字）悬停要么没反应、要么
撞上「预览不可用：'triangle'」——因为判据是「条目 len==5 且第 5 项是字符串」，
而异形档位 `('边长4 等级1', 4, 4, 1, 'triangle')` 恰好也满足。现在统一走
`target_of_item()`：模型名要在注册表里、内置 kind 要在白名单里，其余一律
不给预览（宁可不画，也不画一个错的）。

「打乱态」一律**真跑引擎打乱**（与 `session.shuffle_puzzle` 同口径：
bias 0.3 / min_score 0.75），不是随手把块挪一挪——模型板型的合法形态由缝族
与朝向邻接表决定，随手挪出来的是**这题根本走不到**的局面，预览就成了骗人。

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
import re
import threading
import time

import pygame

# 缩图边长（px）。104 是「28 块还能看出彼此」「菜单旁边放得下」的折中。
THUMB_SIZE = 104
# 缩图内边距：留一点白边，块不贴着框
_PAD = 5

# 缩图算法版本，**进了磁盘签名**。改了算图方式就 +1：否则 preview_cache 里
# 上一版算法写的图会被一直复用（预热只看 `_disk_ok`）。
# 2026-10-26 用户报「打乱态就是复原态」，根因之一就是这里：当时签名只有
# 「模型内容 + 尺寸 + 配色」，算法换了签名没换，旧图原封不动留在盘上。
# v3：文件名加 step（等级1/2 曾共用一个缓存文件互相覆盖），旧命名一律清掉。
# v4：数字谜题的缩图上开始画编号（2026-10-29）。同一目标、同一尺寸下，
#     「有字」与「无字」是两张不同的图，不升版本号就会让无字的旧图一直冒充。
_CACHE_VER = 4

# 打乱口径：与 GUI 真打乱同源（gui/session.py 的 shuffle_puzzle 用
# bias=0.3 / min_score=0.75）。缩图必须画玩家真会遇到的局面。
_BIAS = 0.3
# 「够乱了」的判据不再看「多少块离开原位」——整体平移能让 100% 的块离开
# 原位却完全没打散（三角局就会这样）。改成**跑满步数**，只留一个时间兜底：
# mi 8×8 每步 ~13ms，240 步要 3s，而 0.9s 之后再多走几步，104px 上也看不出
# 差别了。
_TIME_BUDGET = 0.6
# 单张缩图最多打乱多少步（真打乱是 m*n*10，10×10 要 1000 步 ≈ 1s，太多）
_MAX_ATTEMPTS = 120
# 每片打乱步数：片间 sleep 让出 GIL。否则后台线程一口气跑几百步，
# 主循环一段时间完全抢不到解释器锁，表现为持续掉帧。
_MOVE_SLICE = 10
_SLICE_YIELD = 0.003
# 打乱「看起来没变」时换一局重打的次数（见 _polys_scrambled）
_SCRAMBLE_TRIES = 3

# 内置板型（引擎 registry 里的 kind）。'square' 是「不带 kind 的档位」缺省。
BUILTIN_KINDS = ('square', 'triangle', 'mi', 'numbered')

# 两级缓存，分工不能混：
#   _pics  = 纯 Python 的「像素多边形」(model_name, size, palette) -> (goal, scr)
#   _surfs = pygame.Surface 同上 key -> (goal_surf, scr_surf)
# 为什么要拆开：后台线程只许算 _pics（纯数学），Surface 一律主线程建。
# 2026-10-26 事故：早先把「建 Surface + draw.polygon」放进了后台线程，
# 真实显示下与主线程的绘制/flip 撞车，会被 SDL 拒（或被吞成「预览不可用」）。
_pics = {}
_surfs = {}
# 目标 → 磁盘签名用的内容哈希。算法/几何一变就会重算；不缓存的话每次
# `_disk_ok()` 都要现造一局内置板型（悬停每帧都会问到）。
_hash_cache = {}
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
        _hash_cache.clear()
        _warm_started[0] = False
        _pump_t0[0] = 0.0      # 重新计时，还是等一秒再开始预热


def forget_model(name):
    """模型文件被删除后：清掉它的内存缓存与磁盘缩图（等级1/2 一起）。

    用户 2026-10-26 的删除规则是「直接删模型文件」，但不收拾缩图会留下
    永远不会再被命中的孤儿 png（``_purge_stale`` 只按算法版本清，不管
    目标还在不在）。删除入口在 ``gui/menu_delete.py``，它调这里。

    命名知识只在本模块有一份：按 ``model_<安全名>_s<等级>.`` 精确匹配，
    不用「前缀包含」——模型名互为前缀时（``a`` / ``a_b``）会误删别人的图。
    """
    with _lock:
        _gen[0] += 1           # 在途的后台线程算完发现世代变了就不写回
        # 三个缓存的键形状不同：_pics/_surfs 是 (target, size, pal)，
        # _hash_cache 直接就是 target。用取键函数区分，别拿 k[0] 一律当 target。
        for cache, pick in ((_pics, lambda k: k[0]),
                            (_surfs, lambda k: k[0]),
                            (_hash_cache, lambda k: k)):
            for k in [k for k in cache
                      if isinstance(pick(k), tuple)
                      and _target_matches(pick(k), name)]:
                cache.pop(k, None)
        for k in [k for k in _inflight
                  if isinstance(k, tuple) and k and _target_matches(k[0], name)]:
            _inflight.discard(k)

    d = _disk_dir()
    if not os.path.isdir(d):
        return 0
    # _target_tag 的等级位是 _s<step>：拿 step=0 凑出「..._s0」再削掉末位，
    # 得到与等级无关的前缀，避免在这里重复一遍文件名清洗规则。
    prefix = _target_tag(('model', name, 0))[:-1]
    pat = re.compile(rf'^{re.escape(prefix)}\d+\.')
    n = 0
    for fn in os.listdir(d):
        if not fn.endswith('.png') or not pat.match(fn):
            continue
        try:
            os.remove(os.path.join(d, fn))
            n += 1
        except OSError:
            pass
    return n


def _target_matches(target, wanted):
    """`wanted`（目标元组 / 模型名 / 板型名）是否指同一个目标。

    传字符串时按「目标里前两项之一相等」比：这样 `last_error('shield')`
    能命中 ('model', 'shield', 1) 与 ('model', 'shield', 2) 两条（等级1/2），
    调用方不必知道档位。
    """
    if isinstance(wanted, str):
        return wanted in target[:2]
    return tuple(wanted) == tuple(target)


def last_error(wanted):
    """该目标上次失败的原因；没失败过返回 None。

    `wanted` 可以是目标元组、模型名或内置板型名（见 `_target_matches`）。
    """
    with _lock:
        items = list(_pics.items()) + list(_surfs.items())
    for (target, _size, _pal), val in items:
        if isinstance(val, Exception) and _target_matches(target, wanted):
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


# ----------------------------------------------------------------------
# 预览目标：一个元组唯一标识「哪个谜题」
#    ('model', 模型名, step)           —— models/*.json 声明的不规则板型
#    ('board', kind, m, n, step)       —— 内置板型（kind 见 BUILTIN_KINDS）
# 早先整条链路只认「模型名字符串」，于是内置预设要么没预览、要么把
# 'triangle' 当模型名去查注册表（KeyError → 面板写「预览不可用：'triangle'」）。
# ----------------------------------------------------------------------
def as_target(x, step=2):
    """把「模型名字符串」或元组统一成 target（字符串按模型 step=2 处理）。"""
    if isinstance(x, str):
        return ('model', x, int(step))
    return tuple(x)


def is_numbered(target):
    """该目标是「带编号的谜题」吗（缩图上要写号的那一类）。"""
    return target[0] == 'board' and target[1] == 'numbered'


def thumb_size_for(target):
    """该目标该用多大的缩图。"""
    return THUMB_SIZE


def preview_note(target):
    """数字谜题在悬停预览里要加的一句说明文字；其它谜题返回 None。

    2026-10-30：早先曾在缩图上逐格写编号，但①那让数字谜题预览看着和其
    它谜题明显不一样（别的只有色块）②288px 大图会溢出、压住菜单文字
    （图层错位）。改回纯色块 + 这一句文字标注，既保持一致，又点明
    「这是数字题」。
    """
    if is_numbered(target):
        return '每块滑块都有唯一编号'
    return None


def target_of_item(item):
    """菜单条目 → 预览目标；不是「可预览的谜题」时返回 None。

    条目形态（见 GUI._refresh_puzzle_presets / puzzle_sub_presets）：
      模型档位   ('shield（28 块）', 4, 4, 1, 'shield')
      内置档位   ('6×6 等级2', 6, 6, 2)  /  ('边长4 等级1', 4, 4, 1, 'triangle')
      分组标题 / 分隔线 / 当前行 / 自定义预设 —— 第 2~4 项不是三个整数，
      自然落空，不会误判。

    ⚠️ 判据必须「白名单」而不是「第 5 项是字符串」：异形档位的第 5 项
    也是字符串（kind），曾据此把它当模型名。未知 kind / 不存在的模型名
    一律返回 None —— 宁可不给预览，也不要画一个错的。
    """
    if not isinstance(item, (tuple, list)) or len(item) < 4:
        return None
    if not all(isinstance(v, int) and not isinstance(v, bool)
               for v in item[1:4]):
        return None
    m, n, step = int(item[1]), int(item[2]), int(item[3])
    kind = item[4] if len(item) >= 5 and isinstance(item[4], str) else 'square'
    if kind in BUILTIN_KINDS:
        return ('board', kind, m, n, step)
    from engine import model_registry
    if kind in model_registry.loaded():
        return ('model', kind, step)
    return None


def _target_tag(target):
    """目标 → 磁盘文件名前缀（也当失败日志里的可读标识）。

    ⚠️ **step 必须在内**：等级1/等级2 是同一块板的两种打乱口径，出的图不一样，
    但内容哈希相同（都是同一个模型文件）。曾经漏了 step，两级共用一个文件名
    互相覆盖 —— 预览只好随机显示其中一级的打乱。
    文件名还要过 Windows 的非法字符关（模型名是用户起的，可能带冒号/空格）。
    """
    if target[0] == 'model':
        raw = f'model_{target[1]}_s{target[2]}'
    else:
        _, kind, m, n, step = target
        raw = f'board_{kind}_{m}x{n}s{step}'
    return ''.join(ch if ch.isalnum() or ch in '-_.' else '_' for ch in raw)


def _new_game(target):
    """按目标造一局（引擎侧只读用，不碰 GUI）。"""
    from engine.adapter import create_adapter_puzzle

    if target[0] == 'model':
        _, name, step = target
        # 模型局固定 4×4（与菜单条目、GUI.new_model_puzzle 同口径）
        return create_adapter_puzzle(name, 4, 4, int(step))
    _, kind, m, n, step = target
    return create_adapter_puzzle(kind, int(m), int(n), int(step))


def _spec_of(target):
    """目标的板型 spec（模型取注册表里的那份，内置取现造的棋盘）。"""
    from engine import model_registry

    if target[0] == 'model':
        return model_registry.loaded(target[1]).spec
    return _new_game(target).board.spec


def _attempts_for(target):
    """该目标打乱多少步：真打乱口径 m*n*10，但封顶 _MAX_ATTEMPTS。

    封顶是为了让「预热全部预设」这件事有界：10×10 真打乱要 1000 步（≈1s），
    而缩图 104px 上 240 步与 1000 步看不出差别。
    """
    if target[0] == 'model':
        m = n = 4
    else:
        _, _kind, m, n, _step = target
    return max(40, min(int(m) * int(n) * 10, _MAX_ATTEMPTS))


def _shape_set(polys):
    """多边形集合的规范形（画出来一样 ⟺ 集合一样），用于「打乱没打乱」判据。"""
    return {tuple(sorted((round(x, 2), round(y, 2)) for x, y in poly))
            for poly, _idx in polys}


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

    ⚠️ **这里的「序号」只是列表下标，不是块身份**（2026-10-29 实测订正，
    旧注释写的「打乱之后顺序不变」是错的）：`Board.blocks` 是**按键排序**
    的元组，块一动，排序就跟着变。要「编号跟着块走」必须走下面的
    `_polygons_of_game`（编号挂在块对象上），不能拿这里算出来的下标当编号。

    几何是准确的（多边形取自块当下位置），所以非编号用途（数块、取形、
    比相似度）照旧用它。
    """
    spec = board.spec
    out = []
    for i, b in enumerate(board.blocks):
        poly = spec.cell_polygon(b.point, b.orient)
        if poly:
            out.append(([(float(x), float(y)) for x, y in poly], i))
    return out


def _polygons_of_game(game):
    """从**适配器块视图**取 ([(多边形, 序号)], None)。

    两条几何取路的区别（2026-10-29）：
      - `_polygons_of_board(board)`：几何取自排好序的 Board，但下标随位置漂移；
      - 这里遍历 `game.blocks`，块对象就是真身 → 缩图几何与真盘逐块对应。

    第二项是预留给「编号」的出口，但 2026-10-30 起数字谜题的预览改回纯色块
    （编号信息改由 `preview_note()` 在悬停面板里用文字标注），所以这里恒返
    None，下游 `_paint` 不再画字。
    """
    game.board                      # 先 sync：把块位置刷进引擎，保证 key 最新
    spec = game.spec
    polys = []
    for i, b in enumerate(game.blocks):
        key = getattr(b, 'engine_key', None)
        if key is None:
            continue
        poly = spec.cell_polygon(key[0], key[1])
        if not poly:
            continue
        polys.append(([(float(x), float(y)) for x, y in poly], i))
    return polys, None


def _polys_scrambled(target, goal_polys=None, size=THUMB_SIZE):
    """一种打乱态：真跑一遍引擎的打乱，再取各块当前位置的多边形。

    走真引擎而不是「把块随机挪一挪」：模型板型的合法形态由缝族与朝向
    邻接表决定，随手挪出来的是**这题根本走不到的局面**，预览就成了骗人。

    参数与 GUI 真打乱同源（bias 0.3），步数取 m*n*10（封顶 _MAX_ATTEMPTS），
    但**分片**执行：每片 `_MOVE_SLICE` 步之间 sleep 一下让出 GIL。一口气
    跑完时（mi 8×8 要 3s）主循环会被后台线程饿着，玩家看到的是持续掉帧。

    ⚠️「打乱没打乱」必须在**拟合之后**比，不能比原始坐标：两张缩图各自
    按包围盒居中缩放（见 `_fit`），所以「整块图形平移了一点」在缩图上跟
    复原态**像素级相同**——2026-10-26 用户看到的「打乱态就是复原态」有一半
    就是这么来的（另一半是磁盘旧图，见 `_CACHE_VER`）。
    归一化后仍与复原态一样 → 换一局重打，连试 `_SCRAMBLE_TRIES` 次都不行
    才报错，让面板写「预览不可用：…」，绝不拿复原态冒充打乱态。

    返回 `(多边形列表, 编号列表)`：编号来自这一局自己（见 `_polygons_of_game`），
    **不是**照抄复原态的下标 —— 打乱后块换了位置，编号必须跟着它走。
    """
    goal_sig = None
    if goal_polys is not None:
        goal_sig = _shape_set(_fit(goal_polys, int(size)))

    for _try in range(_SCRAMBLE_TRIES):
        game = _new_game(target)
        step = int(target[-1])
        budget = _attempts_for(target)
        done = 0
        t0 = time.time()
        while done < budget:
            n = min(_MOVE_SLICE, budget - done)
            game.shuffle(n, step, bias=_BIAS, min_score=None, record=[])
            done += n
            if time.time() - t0 >= _TIME_BUDGET:
                break
            time.sleep(_SLICE_YIELD)

        out, labels = _polygons_of_game(game)
        if goal_sig is None or _shape_set(_fit(out, int(size))) != goal_sig:
            return out, labels

    raise ValueError('这块板打乱后与复原态一样（几乎滑不动）')


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


def _paint(fitted, size, palette, labels=None):
    """把已拟合好的多边形画成一张 Surface。**只许在主线程调用**（要碰字体）。

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
    with _lock:
        gen = _gen[0]
    target, size, _pal = key
    try:
        spec = _spec_of(target)
        if not spec.goal_blocks or spec.cell_polygon is None:
            raise ValueError('该板型没有声明 goal_blocks / cell_polygon')
        # 两张图都从同一个块视图取（`_polygons_of_game`），几何与真盘逐块对应。
        game = _new_game(target)
        goal, glabels = _polygons_of_game(game)
        scr, slabels = _polys_scrambled(target, goal, int(size))
        gfit = _fit(goal, int(size))
        sfit = _fit(scr, int(size))
        val = ((gfit, glabels), (sfit, slabels))
    except Exception as exc:      # noqa: BLE001 —— 见模块头「失败不静默」
        val = exc
        _log_failure(_target_tag(target), exc)
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
        val = (_paint(pics[0][0], size, pal, pics[0][1]),
               _paint(pics[1][0], size, pal, pics[1][1]))
    except Exception as exc:      # noqa: BLE001 —— 画不出来也只是没有预览
        val = exc
        _log_failure(_target_tag(key[0]), exc)
    with _lock:
        if _gen[0] == gen:
            _surfs[key] = val
    return val


def _target_hash(target):
    """目标的内容哈希：模型取 `LoadedModel.hash()`，内置板型取 S₀ 几何哈希。

    为什么不用文件 mtime：编辑器存盘会重写文件（mtime 必变）但内容可能没变；
    反过来拷机器/回滚代码会让 mtime 倒退而内容真变了。
    内置板型的形状由代码产生，改用「复原态各块 (point, orient)」的哈希——
    板型定义一改，哈希就变，旧缩图自动失效。
    """
    with _lock:
        hit = _hash_cache.get(target)
    if hit is not None:
        return hit
    from engine import model_registry

    if target[0] == 'model':
        got = model_registry.loaded(target[1]).hash()
    else:
        spec = _spec_of(target)
        raw = repr(sorted((tuple(b.point), b.orient) for b in spec.goal_blocks))
        got = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]
    with _lock:
        _hash_cache[target] = got
    return got


def _disk_sig(key):
    """该缩图在磁盘上的身份串：目标名 + 内容哈希 + **算法版本** + 尺寸 + 配色。

    版本号必须在内：算法换了（比如改了打乱口径、去掉彩虹渐变）而签名不变
    时，预热会以为「盘上已有」而跳过，错的旧图就一直留在预览里。
    """
    target, size, pal = key
    ph = hashlib.sha1(repr(pal).encode('utf-8')).hexdigest()[:8]
    return (f'{_target_tag(target)}.{_target_hash(target)}.v{_CACHE_VER}'
            f'.{int(size)}.{ph}')


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


def _purge_stale():
    """删掉版本号对不上的旧缩图（命名规则/算法换代时清一次）。

    2026-10-26 用户报「打乱态就是复原态」：磁盘里留着上一版算法写的图，
    而当时的签名只含「内容 + 尺寸 + 配色」→ 预热看到文件就跳过，错的图
    一直留着。现在版本号进签名，顺手把旧世代清掉，directory 也不会长草。
    """
    d = _disk_dir()
    if not os.path.isdir(d):
        return
    marker = f'.v{_CACHE_VER}.'
    for fn in os.listdir(d):
        if not fn.endswith('.png') or marker in fn:
            continue
        try:
            os.remove(os.path.join(d, fn))
        except OSError:
            pass


def _load_disk(key):
    """从磁盘读回两张缩图；没有/坏了返回 None（坏了不留残图，下次重算覆盖）。"""
    gp, sp = _disk_paths(key)
    if gp is None or not (os.path.exists(gp) and os.path.exists(sp)):
        return None
    try:
        goal = pygame.image.load(gp)
        scr = pygame.image.load(sp)
    except Exception as exc:      # noqa: BLE001
        _log_failure(_target_tag(key[0]), exc)
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
        _log_failure(_target_tag(key[0]), exc)
        return
    # 同一目标的历史世代（改过形状/尺寸/配色/算法版本）顺手清掉，别让目录长草
    prefix = _target_tag(key[0]) + '.'
    keep = os.path.basename(gp)[:-len('.goal.png')]
    try:
        for fn in os.listdir(_disk_dir()):
            if fn.startswith(prefix) and fn.endswith('.png') \
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

    第一个参数可以是模型名（按 step=2 处理）或 `as_target()` 造的目标元组。
    结果按 (目标, 尺寸, 配色) 缓存——菜单每帧都会调用，重算一次要真跑
    一遍打乱（首算最坏 ~500ms），悬停时逐帧重算必然卡。
    菜单渲染请用 `request()`（异步版），这里留给测试与需要确定结果的场合。
    """
    key = (as_target(model_name), int(size), _palette(colors))
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

    第一个参数可以是模型名或 `as_target()` 造的目标元组（内置板型）。
    后台线程只算像素多边形（纯 Python），Surface 由**本函数在主线程**创建，
    见模块头「两级缓存」。
    """
    key = (as_target(model_name), int(size), _palette(colors))
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
# 空闲预热：启动后把**菜单里每个预设**的两张缩图都算一遍并落盘
# ----------------------------------------------------------------------
# 用户 2026-10-26 提的做法：与其悬停时现算，不如开局后空闲时挨个算好导出。
# 比「悬停现算」好在三处：①悬停零等待（只读盘）②不用在游戏进行中起
# 线程算几何 ③第二次启动连算都不算。
# 预热对象由 GUI 传进来（renderer._preview_targets 扫自己菜单），这样
# 「菜单里有哪些档位」只有一处真相；`warm_targets()` 只是无 GUI 时的兜底。
_warm_started = [False]
# 预热起点：第一次 pump 的时刻。预热要错开开局那一下——后台跑打乱是纯 Python
# 重活，会抢 GIL，实测单模型能把某一帧顶到 ~128ms（掉 7 帧）。等一秒再开始，
# 用户已经看清盘面了，卡顿也落在「还没动手」的时候。
_pump_t0 = [0.0]
_WARM_DELAY = 1.0
# 目标之间让路：每个目标之间睡一下，把长卡顿摊成几次短卡顿
_WARM_GAP = 0.12


def warm_targets():
    """兜底预热清单：注册表里所有模型的等级1/等级2。

    GUI 会传自己的菜单目标（见 `renderer._preview_targets`），这里只是让
    「没有 GUI 入口」的场合（测试、脚本）也能预热出东西来。
    """
    from engine import model_registry
    out = []
    for name in sorted(model_registry.loaded()):
        out.append(('model', name, 1))
        out.append(('model', name, 2))
    return out


def _warm_worker(targets, size, pal):
    """后台：逐个算像素多边形（纯 Python）。已落盘且签名一致的直接跳过。"""
    try:
        _purge_stale()
    except Exception:      # noqa: BLE001 —— 清旧图失败不影响预热
        pass
    for i, target in enumerate(targets):
        # 每个目标用自己的缩图尺寸（数字谜题要大一号，见 thumb_size_for）：
        # 预热若按 104 算，悬停要的却是 256 → 磁盘签名不命中、白算一遍。
        key = (target, thumb_size_for(target), pal)
        try:
            if _disk_ok(key):
                continue
        except Exception:      # noqa: BLE001 —— 签名算不出来的目标直接跳过
            continue
        if i:
            time.sleep(_WARM_GAP)
        _build_pics(key)


def _disk_ok(key):
    gp, sp = _disk_paths(key)
    return gp is not None and os.path.exists(gp) and os.path.exists(sp)


def pump(colors=None, size=THUMB_SIZE, budget=1, targets=None):
    """**每帧调一次**：启动预热 + 把后台算好的图在主线程画出来并存盘。

    budget 限制单帧最多处理几个目标：画一张 0.4ms、存两张 PNG 约 2~5ms，
    一个目标 ~6ms 已够小；设上限是防止「第一次启动同时收到一批」把某一帧
    撑到 30ms 掉帧。返回本帧实际处理的数量（给测试用）。

    尺寸按**目标各自**的来（`thumb_size_for`，数字谜题大一号），`size` 只是
    兼容旧调用的缺省值：预热若按别的尺寸算，悬停时签名对不上，等于白算。

    失败一律不抛：预热是纯锦上添花，绝不许影响主循环。
    """
    pal = _palette(colors)
    n = 0
    try:
        if not _pump_t0[0]:
            _pump_t0[0] = time.time()
        if not _warm_started[0] and time.time() - _pump_t0[0] >= _WARM_DELAY:
            _warm_started[0] = True
            want = warm_targets() if targets is None else list(targets)
            threading.Thread(target=_warm_worker,
                             args=(want, int(size), pal),
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
