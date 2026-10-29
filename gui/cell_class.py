# -*- coding: utf-8 -*-
"""相容轉發殼——真身已遷到 ``engine/cell_class``（2026-10-30）。

移動不變量類（``cell_class`` / ``class_index``）是零依賴純數學，卻原本住在
``gui/`` 裡，害得 ``solver/ml/mi_placement.py`` 與 ``solver/ml/tri_placement.py``
為了兩個函式去 import GUI 包（求解器依賴界面層，方向反了）。真身遷走後：

  · solver / gui 內部一律 ``from engine.cell_class import ...``；
  · 本檔案只剩轉發，**不要新增引用**（保留只為不打斷外部與實驗腳本）。

演算法與「為什麼米字用 r±c 而不是 r%step」的完整推導見 engine 版的
模組 docstring。
"""

from engine.cell_class import cell_class, class_index  # noqa: F401

__all__ = ['cell_class', 'class_index']
