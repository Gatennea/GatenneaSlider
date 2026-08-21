# -*- coding: utf-8 -*-
"""
solver.ml — AI 机器学习求解子包

模块：
    features       — 共享特征构建（状态特征 + 动作编码）
    export_data    — 从 BFS 表导出训练数据
    annotate       — 瓶颈标注（dist_to_bottleneck）
    train_baseline — scikit-learn MLPClassifier 基线
    train_ranker   — 评分模型训练（Learning-to-Rank）
    ai_solver      — AI 推理求解器（接入 GUI）
"""

from solver.ml.ai_solver import ai_solve

__all__ = ['ai_solve']
