# -*- coding: utf-8 -*-
"""
成绩记录模块

使用 pickle 二进制存储（配合 XOR 混淆，避免一眼被识别为 pickle）。
数据按谜题类型（step~m*n）分组，支持单次/最好/最差/Ao5/Ao12/DNF 统计。
"""

import os
import pickle
import time
import uuid

# 固定混淆字节（仅为让文件头不像 pickle，不涉及密钥/防篡改）
_XOR_BYTE = 0x5A


def _xor(data: bytes) -> bytes:
    """对字节做固定异或，用于隐藏 pickle 特征"""
    return bytes(b ^ _XOR_BYTE for b in data)


def format_time(ms):
    """将毫秒格式化为厘秒文本，如 12.34 或 1:23.45"""
    if ms is None:
        return '-'
    total = ms / 1000.0
    minutes = int(total // 60)
    sec = total - minutes * 60
    if minutes > 0:
        return f"{minutes}:{sec:05.2f}"
    return f"{sec:.2f}"


class Records:
    """成绩记录管理器（内存中维护，关闭游戏时统一写盘）"""

    def __init__(self, path: str):
        self.path = path
        self.data = {}  # puzzle_key -> list[record]
        self._series_cache = {}  # puzzle_key -> list[(record, ao5, ao12)]，增量维护
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, 'rb') as f:
                raw = f.read()
            raw = _xor(raw)
            data = pickle.loads(raw)
            self.data = data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"[Records] 加载失败: {e}")
            self.data = {}
        self._series_cache = {}

    def save(self):
        """将内存数据写入磁盘（游戏关闭时调用）"""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'wb') as f:
                f.write(_xor(pickle.dumps(self.data)))
        except Exception as e:
            print(f"[Records] 保存失败: {e}")

    def add_record(self, puzzle_key, m, n, step, initial_matrix, time_ms, moves, dnf):
        """追加一条成绩（仅内存），增量更新 series 缓存，返回记录"""
        record = {
            'id': uuid.uuid4().hex,
            'ts': time.time(),
            'puzzle_key': puzzle_key,
            'm': m,
            'n': n,
            'step': step,
            'initial_matrix': initial_matrix,
            'time_ms': int(round(time_ms)),
            'moves': moves,
            'dnf': bool(dnf),
        }
        records = self.data.setdefault(puzzle_key, [])
        records.append(record)
        # 增量更新缓存：只计算新纪录的 Ao5/Ao12 两次
        cache = self._series_cache.get(puzzle_key)
        if cache is not None:
            n = len(records)
            times = [None if r['dnf'] else r['time_ms'] for r in records]
            cache.append((record, self._avg_of(times[:n], 5), self._avg_of(times[:n], 12)))
        return record

    def get_records(self, puzzle_key):
        return self.data.get(puzzle_key, [])

    def delete_record(self, puzzle_key, record_id):
        """删除指定 id 的记录（仅内存），增量更新 series 缓存，返回是否成功"""
        records = self.data.get(puzzle_key, [])
        for i, r in enumerate(records):
            if r['id'] == record_id:
                del records[i]
                # 增量更新缓存：只重算被删位置起 12 行内受影响的行
                cache = self._series_cache.get(puzzle_key)
                if cache is not None and i < len(cache):
                    del cache[i]
                    times = [None if r2['dnf'] else r2['time_ms'] for r2 in records]
                    end = min(len(cache), i + 12)
                    for j in range(i, end):
                        r2 = cache[j][0]
                        cache[j] = (r2, self._avg_of(times[:j + 1], 5),
                                    self._avg_of(times[:j + 1], 12))
                if not records:
                    self.data.pop(puzzle_key, None)
                    self._series_cache.pop(puzzle_key, None)
                return True
        return False

    def series(self, puzzle_key):
        """
        按时间正序返回 [(record, ao5, ao12)]。
        ao5/ao12 以该条成绩为结尾的滑动窗口计算（csTimer 风格，供列表逐行展示）。
        结果缓存在内存中，由 add_record/delete_record 增量维护。
        """
        cache = self._series_cache.get(puzzle_key)
        if cache is None:
            records = self.data.get(puzzle_key, [])
            times = [None if r['dnf'] else r['time_ms'] for r in records]
            cache = []
            for i, r in enumerate(records):
                cache.append((r, self._avg_of(times[:i + 1], 5),
                              self._avg_of(times[:i + 1], 12)))
            self._series_cache[puzzle_key] = cache
        return cache

    def stats(self, puzzle_key):
        """返回指定谜题分组的统计信息"""
        records = self.get_records(puzzle_key)
        # None 表示 DNF
        times = [None if r['dnf'] else r['time_ms'] for r in records]
        valid = [t for t in times if t is not None]
        return {
            'count': len(records),
            'best': min(valid) if valid else None,
            'worst': max(valid) if valid else None,
            'dnf_count': len(times) - len(valid),
            'ao5': self._avg_of(times, 5),
            'ao12': self._avg_of(times, 12),
        }

    @staticmethod
    def _avg_of(times, n):
        """
        计算 AoN：取最近 n 次，去掉一个最好和一个最差，剩余取平均。
        DNF 视为最差（无穷大）。
        返回：
            None  - 不足 n 次
            'DNF' - 窗口内去掉最好最差后仍有 DNF
            float - 平均毫秒
        """
        if len(times) < n:
            return None
        window = times[-n:]
        vals = [float('inf') if t is None else t for t in window]
        sorted_vals = sorted(vals)
        trimmed = sorted_vals[1:-1]  # 去掉最小和最大
        if any(v == float('inf') for v in trimmed):
            return 'DNF'
        return sum(trimmed) / len(trimmed)
