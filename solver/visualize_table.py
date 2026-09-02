# -*- coding: utf-8 -*-
"""
可视化建表数据：用 tkinter 浏览 PKL 表中每个状态的网格外观（文字版）。

运行：
    D:\\python\\python.exe -m solver.visualize_table [m n step]
    默认 m=4 n=4 step=2

操作：
    键盘  ← →    上一/下一个状态
    键盘  ↑ ↓    上一/下一个距离层
    键盘  r      随机跳转
    键盘  a      取消筛选（显示全部）
    滚轮         上一/下一个状态
    点击左侧列表  按距离筛选
"""

import os
import sys
import pickle
import random
import tkinter as tk

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

try:
    from solver import table_core as tc
except ImportError:
    import table_core as tc


class TableVisualizer:
    def __init__(self, m, n, step):
        self.m = m
        self.n = n
        self.step = step
        self.total = m * n

        data_dir = os.path.join(DATA_DIR, f'{m}_{n}_{step}')
        table_path = os.path.join(data_dir, 'table.pkl')

        if not os.path.exists(table_path):
            print(f"错误: 找不到 {table_path}")
            sys.exit(1)

        print(f"加载表...", end=' ', flush=True)
        with open(table_path, 'rb') as f:
            self.dist = pickle.load(f)
        print(f"{len(self.dist):,} 状态")

        self.by_dist = {}
        for h, d in self.dist.items():
            self.by_dist.setdefault(d, []).append(h)
        self.max_dist = max(self.by_dist.keys())

        self.filter_dist = None
        self.current_idx = 0
        self._rebuild_filtered()

        self._build_gui()

    # ==================================================================
    # 数据
    # ==================================================================
    def _rebuild_filtered(self):
        if self.filter_dist is None:
            self.filtered = list(self.dist.keys())
        elif self.filter_dist in self.by_dist:
            self.filtered = list(self.by_dist[self.filter_dist])
        else:
            self.filtered = []
        self.current_idx = max(0, min(self.current_idx, max(0, len(self.filtered) - 1)))

    @staticmethod
    def _grid_text(h, total):
        """返回 (grid_str, coords_str, bbox) — 文字网格 + 原始坐标 + 边界大小。"""
        coords = tc.int_to_coords(h, total)
        rs = [r for r, _ in coords]
        cs = [c for _, c in coords]
        mr, mc = min(rs), min(cs)
        norm = [(r - mr, c - mc) for r, c in coords]
        grid_set = set(norm)
        max_r = max(r for r, _ in norm)
        max_c = max(c for _, c in norm)

        lines = []
        for r in range(max_r + 1):
            row = ''
            for c in range(max_c + 1):
                row += '██' if (r, c) in grid_set else '··'
            lines.append('  ' + row)

        coord_strs = []
        for r, c in sorted(coords):
            coord_strs.append(f'({r},{c})')
        coords_str = ' '.join(coord_strs)

        return '\n'.join(lines), coords_str, (max_r + 1, max_c + 1)

    # ==================================================================
    # GUI
    # ==================================================================
    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title(f'建表可视化 - {self.m}x{self.n}  step={self.step}  ({len(self.dist):,} 状态)')
        self.root.geometry('800x540')
        self.root.minsize(600, 380)

        # ---- 左侧：距离分布列表 ----
        left_frame = tk.Frame(self.root, width=150)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)
        left_frame.pack_propagate(False)

        tk.Label(left_frame, text='距离分布', font=('TkDefaultFont', 10, 'bold')
                 ).pack(pady=(6, 2))

        list_f = tk.Frame(left_frame)
        list_f.pack(fill=tk.BOTH, expand=True, padx=3, pady=(0, 3))

        scroll = tk.Scrollbar(list_f, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(list_f, yscrollcommand=scroll.set,
                                  font=('Consolas', 9), exportselection=False)
        scroll.config(command=self.listbox.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for d in range(self.max_dist + 1):
            cnt = len(self.by_dist.get(d, []))
            self.listbox.insert(tk.END, f" d{d:2d}  {cnt:>6,}")
        self.listbox.bind('<<ListboxSelect>>', self._on_listbox)

        # ---- 右侧：显示区 ----
        right = tk.Frame(self.root)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 6), pady=6)

        # 信息行
        info_row = tk.Frame(right)
        info_row.pack(fill=tk.X, pady=(0, 4))

        self.lbl_dist = tk.Label(info_row, text='', font=('TkDefaultFont', 12, 'bold'))
        self.lbl_dist.pack(side=tk.LEFT)
        self.lbl_pos = tk.Label(info_row, text='', fg='#666',
                                font=('TkDefaultFont', 9))
        self.lbl_pos.pack(side=tk.RIGHT)

        # 网格显示（等宽字体）
        grid_frame = tk.Frame(right)
        grid_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.grid_text = tk.Text(grid_frame, font=('Consolas', 14), bg='#1e1e1e',
                                 fg='#4CAF50', width=30, height=10,
                                 cursor='arrow', state=tk.DISABLED, borderwidth=0)
        self.grid_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 原始坐标
        coord_lbl = tk.Label(right, text='原始坐标:', font=('TkDefaultFont', 9, 'bold'),
                             anchor='w')
        coord_lbl.pack(fill=tk.X)

        self.lbl_coords = tk.Label(right, text='', font=('Consolas', 8),
                                   fg='#555', anchor='nw', justify=tk.LEFT,
                                   wraplength=620)
        self.lbl_coords.pack(fill=tk.X, pady=(0, 2))

        # hash
        self.lbl_hash = tk.Label(right, text='', font=('Consolas', 7),
                                 fg='#999', anchor='w')
        self.lbl_hash.pack(fill=tk.X, pady=(0, 6))

        # ---- 底部控制栏 ----
        ctrl = tk.Frame(self.root, bg='#333')
        ctrl.pack(fill=tk.X, side=tk.BOTTOM)

        btns = tk.Frame(ctrl, bg='#333')
        btns.pack(side=tk.LEFT, padx=6, pady=4)

        tk.Button(btns, text='\u25c0  上一个', command=self._prev).pack(side=tk.LEFT, padx=2)
        tk.Button(btns, text='下一个  \u25b6', command=self._next).pack(side=tk.LEFT, padx=2)
        tk.Button(btns, text='随机', command=self._random).pack(side=tk.LEFT, padx=2)
        tk.Button(btns, text='全部', command=self._all).pack(side=tk.LEFT, padx=2)

        dist_f = tk.Frame(ctrl, bg='#333')
        dist_f.pack(side=tk.LEFT, padx=12)
        tk.Button(dist_f, text='距离 ▲', command=self._dist_up).pack(side=tk.LEFT, padx=1)
        tk.Button(dist_f, text='距离 ▼', command=self._dist_down).pack(side=tk.LEFT, padx=1)

        self.lbl_count = tk.Label(ctrl, text='', bg='#333', fg='#ccc',
                                  font=('TkDefaultFont', 9))
        self.lbl_count.pack(side=tk.RIGHT, padx=8, pady=4)

        # 键盘
        self.root.bind('<Left>', lambda e: self._prev())
        self.root.bind('<Right>', lambda e: self._next())
        self.root.bind('<Up>', lambda e: self._dist_up())
        self.root.bind('<Down>', lambda e: self._dist_down())
        self.root.bind('<KeyPress-r>', lambda e: self._random())
        self.root.bind('<KeyPress-a>', lambda e: self._all())
        self.root.bind('<MouseWheel>', self._wheel)

        self.root.protocol('WM_DELETE_WINDOW', self.root.destroy)

        self._refresh()

    # ==================================================================
    # 刷新
    # ==================================================================
    def _refresh(self):
        # listbox 高亮
        self.listbox.selection_clear(0, tk.END)
        if self.filter_dist is not None and self.filter_dist <= self.max_dist:
            self.listbox.selection_set(self.filter_dist)
            self.listbox.see(self.filter_dist)

        if not self.filtered:
            self.grid_text.config(state=tk.NORMAL)
            self.grid_text.delete('1.0', tk.END)
            self.grid_text.insert('1.0', '（无状态）')
            self.grid_text.config(state=tk.DISABLED)
            self.lbl_dist.config(text='距离=?')
            self.lbl_pos.config(text='')
            self.lbl_coords.config(text='')
            self.lbl_hash.config(text='')
            self.lbl_count.config(text='0 / 0')
            return

        self.current_idx = max(0, min(self.current_idx, len(self.filtered) - 1))
        h = self.filtered[self.current_idx]
        d = self.dist[h]
        grid_str, coords_str, bbox = self._grid_text(h, self.total)

        # 网格
        self.grid_text.config(state=tk.NORMAL)
        self.grid_text.delete('1.0', tk.END)
        self.grid_text.insert('1.0', grid_str)
        self.grid_text.config(state=tk.DISABLED)

        # 信息
        filter_s = f"  [筛选 d={self.filter_dist}]" if self.filter_dist is not None else ""
        self.lbl_dist.config(text=f"距离 = {d}{filter_s}")
        self.lbl_pos.config(text=f"{self.current_idx + 1:,} / {len(self.filtered):,}")

        self.lbl_coords.config(text=f"边界 {bbox[0]}x{bbox[1]}    {coords_str}")

        hash_s = str(h)
        if len(hash_s) > 80:
            hash_s = hash_s[:77] + '...'
        self.lbl_hash.config(text=f"hash: {hash_s}")

        self.lbl_count.config(text=f"当前层共 {len(self.filtered):,} 个")

    # ==================================================================
    # 事件
    # ==================================================================
    def _prev(self):
        if self.filtered:
            self.current_idx = (self.current_idx - 1) % len(self.filtered)
        self._refresh()

    def _next(self):
        if self.filtered:
            self.current_idx = (self.current_idx + 1) % len(self.filtered)
        self._refresh()

    def _random(self):
        if self.filtered:
            self.current_idx = random.randrange(len(self.filtered))
        self._refresh()

    def _all(self):
        self.filter_dist = None
        self._rebuild_filtered()
        self._refresh()

    def _dist_up(self):
        if self.filter_dist is None:
            self.filter_dist = 0
        else:
            self.filter_dist = min(self.max_dist, self.filter_dist + 1)
        self._rebuild_filtered()
        self._refresh()

    def _dist_down(self):
        if self.filter_dist is None:
            self.filter_dist = self.max_dist
        elif self.filter_dist > 0:
            self.filter_dist -= 1
            self._rebuild_filtered()
        else:
            self.filter_dist = None
            self._rebuild_filtered()
        self._refresh()

    def _on_listbox(self, event):
        sel = self.listbox.curselection()
        if sel:
            d = sel[0]
            self.filter_dist = d if d in self.by_dist else None
            self._rebuild_filtered()
            self._refresh()

    def _wheel(self, event):
        if event.delta > 0:
            self._prev()
        else:
            self._next()

    def run(self):
        self.root.mainloop()


def main():
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    TableVisualizer(m, n, step).run()


if __name__ == '__main__':
    main()
