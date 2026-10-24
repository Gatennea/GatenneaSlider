# -*- coding: utf-8 -*-
"""
謎題形態輔助：puzzle_key 與 create_puzzle 集中管理。

對外契約：
- puzzle_key(step, m, n, kind, ...) -> str
- create_puzzle(m, n, step, kind, ...) -> SliderMatrix | TriangleSliderMatrix
  | MiSliderMatrix

    kind: square / numbered / triangle / mi / shatter（碎三角，几何引擎新板型）。

    shatter 没有旧实现（无 game_shatter.py），也无「缺失回退方形」一说——
    引擎模块缺失时**直接抛 ImportError**：静默回退会把 48 块碎三角变成
    16 块矩形，那正是本项目明令禁止的静默兜底。
    """

from __future__ import annotations

from game import SliderMatrix

#: 旧四种形态（有各自的旧引擎实现与形状分支）。
#: 不在此列 = 模型文件板型（块数与形状来自 models/<name>.json）。
_NATIVE_KINDS = ('square', 'numbered', 'triangle', 'mi')


def puzzle_key(
    step: int,
    m: int,
    n: int,
    kind: str = 'square',
    *,
    numbered: bool = False,
    triangle_side: int | None = None,
) -> str:
    """生成 puzzle 分組鍵（用於成績、狀態、存檔識別）。

    - square（預設）：沿用原格式 ``f"{step}~{m}*{n}"``。
    - numbered：在 square 後綴 ``#num``。
    - triangle：格式 ``f"{step}~tri{k}"``，k 為大三角形邊長（單元三角個數）。
    - mi：格式 ``f"{step}~mi{m}*{n}"``，m/n 為棋盤行列數（每格 4 個單元）。
    - shatter（碎三角）：格式 ``f"{step}~shatter"``。板型固定 48 塊、
      無尺寸維度，故鍵裡不含 m/n——也**不能**含：碎三角的 matrix 是
      21×31（質心晶格），若按方形 4×4 計鍵會與矩形 4×4 分榜相撞，
      成績/存檔識別全部串味。
    """
    if kind == 'triangle':
        k = triangle_side if triangle_side is not None else m
        return f'{step}~tri{k}'
    if kind == 'mi':
        return f'{step}~mi{m}*{n}'
    if kind not in _NATIVE_KINDS:
        # 模型文件板型（shatter / shatter_lattice / 以后任何 <name>.json）：
        # 固定块数、无尺寸维度，键里不能含 m/n——否则会与矩形同尺寸分榜
        # 相撞，成绩/存档识别全部串味。
        return f'{step}~{kind}'
    base = f'{step}~{m}*{n}'
    if kind == 'numbered' or numbered:
        return f'{base}#num'
    return base


def create_puzzle(
    m: int,
    n: int,
    step: int,
    kind: str = 'square',
    *,
    numbered: bool = False,
    triangle_side: int | None = None,
):
    """依參數建構謎題邏輯物件（對應 GUI 的 self.game）。

    Stage 0 僅回傳 SliderMatrix；triangle/mi 分派至各自模組，模組缺失時
    回退方形（呼叫方需自行處理）。

    幾何引擎開關（engine.config.ENABLED，默認關）：打開時改走
    engine.adapter.EngineGame（方形/三角/米字一套引擎邏輯）。默認關 →
    完全走舊 game*.py 路徑，對主工作區零擾動；引擎不可用時安靜回退舊引擎。
    """
    # 試運行開關：啟用幾何引擎時改走 engine.adapter（懶導入，默認關不碰舊路徑）
    try:
        from engine.config import is_enabled
        if is_enabled():
            # 放行判据 = 「旧四种」或「注册表里已注册的新板型」——不再写死
            # 枚举，新形态登记进 board_types() 即自动可造（解释器入口侧）。
            # 注意 'triangle' 的注册名是 'tri'，故旧四种仍显式列出。
            from engine.registry import board_types
            _known = kind in ('square', 'numbered', 'triangle', 'mi') \
                or kind in set(board_types())
            if _known:
                from engine.adapter import create_adapter_puzzle
                return create_adapter_puzzle(kind, m, n, step,
                                            triangle_side=triangle_side)
            # 未登记的形态：维持既有回退行为（不在此处改变既有语义）
    except ImportError:
        # 引擎模組缺失（未安裝 / 裁剪版）→ 安靜回退舊 game*.py，不破壞既有行為。
        # ⚠️ 只吞 ImportError：引擎自身的真 bug 必須響（AGENTS.md §2 不靜默兜底），
        # 寬泛 except 會把引擎缺陷藏成「悄悄退回舊引擎」。
        pass
    if kind == 'triangle':
        # 預留接口：Stage B 實作後取消 try/except 並匯入 TriangleSliderMatrix
        try:
            from game_triangle import TriangleSliderMatrix  # type: ignore
            k = triangle_side if triangle_side is not None else m
            return TriangleSliderMatrix(k)
        except ImportError:
            # 三角形尚未實作時，回退到方形避免引入未支援型態
            pass
    if kind not in _NATIVE_KINDS:
        # 模型文件板型（碎三角及以后任何 models/<name>.json）：无旧实现，
        # 直接走 EngineGame 适配器，**不依赖全局引擎开关**（与 GUI
        # new_model_puzzle 同一建路口）。既然文件里已经有形状与缝族，
        # 这里就不该再出现「是哪个形态」的分支。
        # 未注册就**明确抛 KeyError**——回退方形 = 48 块变 16 块的静默兜底。
        from engine.registry import board_types
        if kind not in board_types():
            raise KeyError(
                f'未注册的模型板型 {kind!r}（已注册: {board_types()}）。'
                f'检查 models/{kind}.json 是否存在、是否通过 A0/A1 校验'
                f'（详见 engine.model_registry.errors()）')
        from engine.adapter import create_adapter_puzzle
        return create_adapter_puzzle(kind, m, n, step,
                                     triangle_side=triangle_side)
    if kind == 'mi':
        try:
            from game_mi import MiSliderMatrix  # type: ignore
            return MiSliderMatrix(m, n)
        except ImportError:
            pass
    g = SliderMatrix(m, n)
    # numbered 形态：矩阵直接存整数（编号即矩阵值）；块编号由调用方随后赋予
    g.numbered = (kind == 'numbered') or numbered
    return g
