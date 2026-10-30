"""GatenneaSlider 静态审查 linter。

由 2026-10-30 的三份只读扫描脚本（deadcode_scan / dup_scan / mixin_scan）提升而来，
落点 tools/static_lint/。只扫产品代码、不碰既有游戏逻辑；输出可 diff 本轮结论做回归守门。
"""

__version__ = "0.1.0"
