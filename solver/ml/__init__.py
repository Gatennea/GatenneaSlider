# -*- coding: utf-8 -*-
"""
solver.ml — AI 机器学习求解子包

⚠️ **本包分两块，别混为一谈（2026-10-31 注明）**

**A. 服役中的求解器核心** —— 产品路径在用，改它们等于改求解器，须照常走回归：
    gather_solver / shape_gather / invariants / hole_detector / fill_macro /
    gap_solver / view_rotate / ann_gen / tri_adapter / mi_adapter /
    tri_placement / mi_placement / tri_holes / mi_holes
    （另有 `strategy_solver._find_rep_cell` 被 `gather_solver` 引着，同样在服役路径上。）

**B. ML / 学习方向** —— **暂时放弃的方向**（用户 2026-10-31 原话：「ml 這些屬於
暫時放棄的方向，本來也沒什麼實際成果，基本上只剩參考意義」）：
    features / export_data / export_human_data / annotate /
    train_baseline / train_ranker / train_distance / train_human_ranker /
    train_human_value / ai_solver / human_solver / emd_solver / distance_solver
    （`strategy_solver` 除上面的 `_find_rep_cell` 外也属这一块。）

    → **不要再立项优化 / 重构 / 清理这些模块**，它们只剩参考价值；重复实现
    （如 `gap_solver` 里三份 `_to_world`）、未用 import 之类一律**不动**。
    唯一例外：它们若挡住 A 块的改动，才顺带处理。

模块：
    features       — 共享特征构建（状态特征 + 动作编码）          〔B 已搁置〕
    export_data    — 从 BFS 表导出训练数据                        〔B 已搁置〕
    annotate       — 瓶颈标注（dist_to_bottleneck）                〔B 已搁置〕
    train_baseline — scikit-learn MLPClassifier 基线               〔B 已搁置〕
    train_ranker   — 评分模型训练（Learning-to-Rank）              〔B 已搁置〕
    ai_solver      — AI 推理求解器（接入 GUI）                     〔B 已搁置〕
"""

from solver.ml.ai_solver import ai_solve

__all__ = ['ai_solve']
