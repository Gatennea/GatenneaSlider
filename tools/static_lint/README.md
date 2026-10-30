# static_lint —— 仓库内静态审查 linter

由 2026-10-30 的三份只读扫描脚本（`deadcode_scan` / `dup_scan` / `mixin_scan`）提升而来，
目标是把「改完跑一遍，确认没复发 / 没引入新问题」变成可重复、可 diff 的工具。

## 扫描范围

只扫**产品代码**：`engine/` `gui/` `solver/` `macro/` 与根目录产品文件
（`game.py` `GUI.py` `main.py` …）。`test/` 仅参与「未用 import」检查。

**不扫**：`archive/` `experiments/` `video/` `voice_demo/` 等历史草稿与资产目录；
这些目录里成堆的临时脚本不在审查范围内。

## 检查项

| 类别 | 内容 | 假阳性处理 |
| --- | --- | --- |
| `unused_import` | 未被引用的 import | 过滤 `from __future__ import ...`、框架回调（`do_POST` / `log_message` 等）、`# noqa: F401`（作者显式保留）、`__all__` 里的 re-export。报告的是**本文件生效名**（`import x as y` 报 `y`） |
| `dup_body` | 函数体完全相同的重复实现 | 排除有意的独立真值 `engine/tri_geometry.py` `engine/game_triangle.py` |
| `reverse_dep` | 反向依赖（底层 `engine` 依赖上层 `gui` 等） | 仅报 `BAD_DEPS` 表里定义的禁止方向 |
| `mixin_dead` | mixin MRO 同名遮蔽且无非显式调用 | 只报 MRO 靠后、且全文无 `Mixin.method(` 死方法 |

## 用法

```bash
# 普通跑（输出发现清单）
python -m tools.static_lint.runner --root .

# 首次：生成基线（本轮可接受结论）
python -m tools.static_lint.runner --emit-baseline tools/static_lint/baseline.json

# 之后每次改完：只报新增 / 已修复
python -m tools.static_lint.runner --baseline tools/static_lint/baseline.json

# CI 守门：有新增回归时退出码非零
python -m tools.static_lint.runner --baseline tools/static_lint/baseline.json --strict
```

### 本机沙箱注意

本环境 `& python x.py` 不会真正执行，必须用：

```powershell
Start-Process -FilePath D:/python/python.exe `
  -ArgumentList '-m','tools.static_lint.runner','--baseline','tools/static_lint/baseline.json' `
  -WorkingDirectory 'E:\program_project\other\wkbddtest\GatenneaSlider' -NoNewWindow -Wait
```

## diff 模式（回归守门原理）

`baseline.json` 存的是「当前所有发现的稳定签名串」。`--baseline` 跑时：

- **NEW** = 当前有、基线没有 → 新引入的问题（如新增了未用 import、新写了重复函数体）。
- **RESOLVED** = 基线有、当前没有 → 已修掉的问题（如清掉了死方法）。

这就实现了 §十三 要的：「下次改完跑一遍能自动确认『那 3 处没复发 + 没新引入遮蔽 / 反向依赖』」。
