import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import ttkbootstrap as ttk
import os
import numpy as np
import csv

from backend import GCodeAnalyzer
from frontend.styles import ThemeManager
from frontend.charts import ChartManager

class CAMApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CAM Analyzer Pro v4.1")
        
        # 1. 初始化樣式與色票
        self.tm = ThemeManager(root)
        self.colors = self.tm.get_color_palette() 
        
        self.engine = GCodeAnalyzer()
        
        # 狀態變數
        self.file_path = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.current_view = "dashboard"
        
        # 數據變數
        self.stats = {"g00": 0.0, "g01": 0.0}
        self.cached_distances = []
        self.detected_axes = []
        self.skipped_lines = []
        self.cached_starts = []
        self.cached_ends = []
        
        # 直方圖區間設定
        self.fixed_intervals = [
            (0.000, 0.001), (0.001, 0.01), (0.01, 0.02), (0.02, 0.03), 
            (0.03, 0.04), (0.04, 0.05), (0.05, 0.06), (0.06, 0.07), 
            (0.07, 0.08), (0.08, 0.09), (0.09, 0.10), (0.10, 0.20), 
            (0.20, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60), 
            (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.00),
            (1.00, float('inf'))
        ]
        self.bins = [i[0] for i in self.fixed_intervals] + [self.fixed_intervals[-1][1]]
        
        # 初始化介面
        self._init_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _init_layout(self):
        # 設定 Grid 權重：左側固定，右側延伸
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # === 1. 左側導航欄 (Sidebar) ===
        self.sidebar = ttk.Frame(self.root, style='Sidebar.TFrame', padding=10, width=240)
        self.sidebar.grid(row=0, column=0, sticky='ns')
        self.sidebar.grid_propagate(False) # 固定寬度

        # Logo 區域
        ttk.Label(self.sidebar, text="CAM ANALYZER", style='Inverse.TLabel', 
                  font=self.tm.fonts['h1']).pack(pady=(20, 30), anchor='w')

        # 操作區 (Actions)
        ttk.Label(self.sidebar, text="操作", style='Inverse.TLabel', font=self.tm.fonts['h2']).pack(anchor='w', pady=(0, 10))
        
        # [修正] 改用 bootstyle 確保顏色顯示正常
        self.btn_open = ttk.Button(self.sidebar, text="📂 開啟檔案", bootstyle="success", command=self.select_file)
        self.btn_open.pack(fill='x', pady=5)
        
        self.btn_analyze = ttk.Button(self.sidebar, text="▶ 開始分析", bootstyle="primary", 
                                      state='disabled', command=self.start_analysis)
        self.btn_analyze.pack(fill='x', pady=5)

        # 控制按鈕 (暫停/停止)
        ctrl_frame = ttk.Frame(self.sidebar, style='Sidebar.TFrame')
        ctrl_frame.pack(fill='x', pady=5)
        
        # [修正] 使用 bootstyle="warning" 和 "danger" 確保按鈕有顏色
        self.btn_pause = ttk.Button(ctrl_frame, text="暫停", bootstyle="warning", width=4, 
                                    state='disabled', command=self.toggle_pause)
        self.btn_pause.pack(side='left', fill='x', expand=True, padx=(0, 2))
        
        self.btn_stop = ttk.Button(ctrl_frame, text="停止", bootstyle="danger", width=4, 
                                   state='disabled', command=self.stop_analysis)
        self.btn_stop.pack(side='right', fill='x', expand=True, padx=(2, 0))

        ttk.Separator(self.sidebar).pack(fill='x', pady=20)

        # 導航區 (Views)
        ttk.Label(self.sidebar, text="視圖", style='Inverse.TLabel', font=self.tm.fonts['h2']).pack(anchor='w', pady=(0, 10))
        
        self.nav_btns = {}
        # 定義導航按鈕 (key, icon, label)
        for key, icon, label in [('dashboard', '📊', '儀表板'), ('table', '📝', '詳細數據'), ('code', '📜', '原始碼')]:
            btn = ttk.Button(self.sidebar, text=f"{icon}  {label}", style='Nav.TButton',
                             command=lambda k=key: self.switch_view(k))
            btn.pack(fill='x', pady=2)
            self.nav_btns[key] = btn

        # === 2. 右側內容區 (Main Content) ===
        self.content = ttk.Frame(self.root, padding=20)
        self.content.grid(row=0, column=1, sticky='nsew')
        
        # 頂部狀態列 (Header)
        header_frame = ttk.Frame(self.content)
        header_frame.pack(fill='x', pady=(0, 20))
        
        self.lbl_filename = ttk.Label(header_frame, text="尚未載入檔案", font=self.tm.fonts['h1'], foreground=self.colors['fg_main'])
        self.lbl_filename.pack(side='left')
        
        # 軸向燈號區
        axis_frame = ttk.Frame(header_frame)
        axis_frame.pack(side='right')
        self.axis_indicators = {}
        for ax in ['X', 'Y', 'Z', 'A', 'B', 'C']:
            lbl = ttk.Label(axis_frame, text=ax, style='AxisInactive.TLabel', width=3)
            lbl.pack(side='left', padx=2)
            self.axis_indicators[ax] = lbl

        # [修正] 進度條：使用 bootstyle="success-striped" 確保可見度
        self.progress = ttk.Progressbar(self.content, mode='determinate', bootstyle='success-striped')
        self.progress.pack(fill='x', pady=(0, 10))

        # 視圖容器 (View Container)
        self.view_container = ttk.Frame(self.content)
        self.view_container.pack(fill='both', expand=True)
        
        # 初始化三個子視圖
        self._init_dashboard()
        self._init_table()
        self._init_code()
        
        # 預設顯示儀表板
        self.switch_view('dashboard')

    def _init_dashboard(self):
        """初始化儀表板視圖 (KPI + 圖表)"""
        self.view_dash = ttk.Frame(self.view_container)
        
        # KPI Cards 區域
        kpi_frame = ttk.Frame(self.view_dash)
        kpi_frame.pack(fill='x', pady=(0, 20))
        
        self.kpi_vals = {}
        # [需求變更] 定義三個卡片：總行程, G01(含佔比), G00(含佔比)
        kpi_defs = [
            ('total', '總行程'), 
            ('g01', 'G01 切削距離 (佔比)'), 
            ('g00', 'G00 空跑距離 (佔比)')
        ]
        
        for i, (key, title) in enumerate(kpi_defs):
            # 卡片容器
            card = ttk.Frame(kpi_frame, style='Card.TFrame', padding=15)
            card.pack(side='left', fill='x', expand=True, padx=(0 if i==0 else 10, 0))
            
            # 卡片內容
            ttk.Label(card, text=title, style='CardLabel.TLabel').pack(anchor='w')
            val = ttk.Label(card, text="--", style='CardValue.TLabel')
            val.pack(anchor='w', pady=(5, 0))
            self.kpi_vals[key] = val

        # 圖表區域 (含分頁)
        chart_area = ttk.Frame(self.view_dash, style='Card.TFrame', padding=5)
        chart_area.pack(fill='both', expand=True)
        
        nb = ttk.Notebook(chart_area)
        nb.pack(fill='both', expand=True)
        
        # 分頁 1: 距離分佈直方圖
        f1 = ttk.Frame(nb, style='Card.TFrame')
        nb.add(f1, text="距離分佈")
        self.chart_hist = ChartManager(f1, self.tm)
        
        # 分頁 2: F 值曲線
        f2 = ttk.Frame(nb, style='Card.TFrame')
        nb.add(f2, text="微小單節 F 值")
        
        # F 值控制列
        fc = ttk.Frame(f2, style='Card.TFrame', padding=5)
        fc.pack(fill='x')
        
        ttk.Label(fc, text="L:", style='CardLabel.TLabel').pack(side='left')
        self.entry_l = ttk.Entry(fc, width=8)
        self.entry_l.pack(side='left', padx=5)
        
        ttk.Label(fc, text="T:", style='CardLabel.TLabel').pack(side='left')
        self.entry_t = ttk.Entry(fc, width=8)
        self.entry_t.pack(side='left', padx=5)
        
        ttk.Button(fc, text="計算", bootstyle="warning", command=self.calc_f_curve).pack(side='left')
        
        self.chart_f = ChartManager(f2, self.tm)

    def _init_table(self):
        """初始化表格視圖"""
        self.view_table = ttk.Frame(self.view_container)
        
        # 表格控制列
        ctrl = ttk.Frame(self.view_table)
        ctrl.pack(fill='x', pady=(0, 10))
        
        ttk.Label(ctrl, text="顯示筆數:", font=self.tm.fonts['ui']).pack(side='left')
        self.combo_limit = ttk.Combobox(ctrl, values=["1000", "5000", "10000"], width=10, state='readonly')
        self.combo_limit.current(0)
        self.combo_limit.pack(side='left', padx=5)
        self.combo_limit.bind("<<ComboboxSelected>>", self.refresh_table)
        
        ttk.Button(ctrl, text="匯出 CSV", bootstyle="success-outline", command=self.export_csv).pack(side='right')
        
        # Treeview 表格
        cols = ("No", "Start", "End", "Dist")
        self.tree = ttk.Treeview(self.view_table, columns=cols, show='headings', selectmode='browse')
        
        # 設定標題 (點擊可排序)
        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self._sort_tree(_c, False))
            
        self.tree.column("No", width=60, anchor='center')
        self.tree.column("Start", width=200)
        self.tree.column("End", width=200)
        self.tree.column("Dist", width=100, anchor='e')
        
        # 捲軸
        vsb = ttk.Scrollbar(self.view_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

    def _init_code(self):
        """初始化原始碼視圖"""
        self.view_code = ttk.Frame(self.view_container)
        
        # 使用 ScrolledText，並明確指定顏色，避免預設白色背景
        self.txt_code = scrolledtext.ScrolledText(
            self.view_code, 
            font=self.tm.fonts['mono'], 
            bg=self.colors['bg_card'],  # 背景色
            fg=self.colors['fg_main'],  # 文字色
            insertbackground='white',   # 游標顏色
            relief='flat',
            padx=10, pady=10
        )
        self.txt_code.pack(fill='both', expand=True)

    def switch_view(self, view):
        """切換右側視圖"""
        # 先隱藏所有
        self.view_dash.pack_forget()
        self.view_table.pack_forget()
        self.view_code.pack_forget()
        
        # 更新按鈕樣式 (高亮當前)
        for k, btn in self.nav_btns.items():
            if k == view:
                # 這裡 NavActive 仍然使用自定義 style，因為 ttkbootstrap 的 button style 主要是顏色
                # 我們需要改變背景色來顯示選中狀態
                btn.configure(style='NavActive.TButton')
            else:
                btn.configure(style='Nav.TButton')
        
        # 顯示目標
        if view == 'dashboard': self.view_dash.pack(fill='both', expand=True)
        elif view == 'table': self.view_table.pack(fill='both', expand=True)
        elif view == 'code': self.view_code.pack(fill='both', expand=True)
        
        self.current_view = view

    # --- 邏輯功能 ---

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("CAM Files", "*.txt *.nc *.ncd *.tap"), ("All", "*.*")])
        if path:
            self.file_path = path
            self.lbl_filename.config(text=os.path.basename(path))
            self.btn_analyze.config(state='normal')
            
            # 重置 UI 數據
            self.kpi_vals['total'].config(text="--")
            self.kpi_vals['g01'].config(text="--")
            self.kpi_vals['g00'].config(text="--")
            for lbl in self.axis_indicators.values(): lbl.configure(style='AxisInactive.TLabel')

    def start_analysis(self):
        if self.is_running: return
        self.is_running = True
        self.should_stop = False
        self.is_paused = False
        
        # 鎖定按鈕
        self.btn_analyze.config(state='disabled')
        self.btn_open.config(state='disabled')
        self.btn_pause.config(state='normal', text="暫停")
        self.btn_stop.config(state='normal')
        
        # 清空舊資料
        self.txt_code.delete(1.0, tk.END)
        for i in self.tree.get_children(): self.tree.delete(i)
        
        try:
            content = ""
            for chunk in self.engine.read_file_generator(self.file_path, progress_callback=self.progress_callback):
                content += chunk
                if self.should_stop: break
            
            if self.should_stop: raise InterruptedError("使用者停止")

            data = self.engine.parse_and_calculate(content, self.progress_callback)
            if not data: raise InterruptedError("停止")
            
            self.detected_axes = data["axes"]
            self.skipped_lines = data["skipped"]
            self.stats["g00"] = data["g00_dist"]
            
            # 更新燈號
            for ax in self.detected_axes:
                self.axis_indicators[ax].configure(style='AxisActive.TLabel')

            self.cached_starts = data["starts"]
            self.cached_ends = data["ends"]
            if not self.cached_starts: raise InterruptedError("無有效 G01 移動")

            self.cached_distances, total_g01 = self.engine.calculate_g01_metrics(data, self.progress_callback)
            self.stats["g01"] = total_g01
            
            # [修正] 更新儀表板數據 (Total, G01%, G00%)
            total = self.stats["g00"] + total_g01
            g01_pct = (total_g01 / total * 100) if total > 0 else 0
            g00_pct = (self.stats["g00"] / total * 100) if total > 0 else 0
            
            self.kpi_vals['total'].config(text=f"{total:,.2f} mm")
            self.kpi_vals['g01'].config(text=f"{total_g01:,.2f} mm ({g01_pct:.1f}%)")
            self.kpi_vals['g00'].config(text=f"{self.stats['g00']:,.2f} mm ({g00_pct:.1f}%)")
            
            # 填入表格
            self.refresh_table()
            
            # 填入 Log (原始碼)
            self.txt_code.insert(tk.END, "=== 略過/指令列表 (前 2000 行) ===\n\n")
            for l in self.skipped_lines[:2000]:
                self.txt_code.insert(tk.END, l + "\n")
                
            # 繪圖
            self.chart_hist.plot_histogram(self.cached_distances, self.bins, self.fixed_intervals)
            # 預設計算一次 F Curve (如果有值)
            if self.entry_l.get() and self.entry_t.get():
                self.calc_f_curve()
            
            # 完成後切回儀表板
            self.switch_view('dashboard')

        except InterruptedError:
            pass # 靜默停止
        except Exception as e:
            messagebox.showerror("錯誤", str(e))
        finally:
            self.is_running = False
            self.btn_analyze.config(state='normal')
            self.btn_open.config(state='normal')
            self.btn_pause.config(state='disabled')
            self.btn_stop.config(state='disabled')
            self.progress['value'] = 0

    def refresh_table(self, event=None):
        """刷新表格數據 (受限於下拉選單筆數)"""
        if not self.cached_starts: return
        
        # 清空目前表格
        for i in self.tree.get_children(): self.tree.delete(i)
        
        limit = int(self.combo_limit.get())
        
        # 決定要顯示哪些軸
        axis_map = {'X':0, 'Y':1, 'Z':2, 'A':3, 'B':4, 'C':5}
        indices = [axis_map[ax] for ax in ['X','Y','Z','A','B','C'] if ax in self.detected_axes]
        
        for i, (s, e, d) in enumerate(zip(self.cached_starts[:limit], self.cached_ends[:limit], self.cached_distances[:limit])):
            s_str = ",".join([f"{s[idx]:.2f}" for idx in indices])
            e_str = ",".join([f"{e[idx]:.2f}" for idx in indices])
            self.tree.insert('', 'end', values=(i+1, s_str, e_str, f"{d:.4f}"))

    def _sort_tree(self, col, reverse):
        """表格排序功能"""
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try:
            # 嘗試轉成浮點數排序 (處理 No 和 Dist)
            l.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            # 字串排序
            l.sort(reverse=reverse)
            
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
            
        self.tree.heading(col, command=lambda: self._sort_tree(col, not reverse))

    def progress_callback(self, pct, msg):
        self.progress['value'] = pct
        self.root.title(f"CAM Analyzer Pro - {pct:.0f}%")
        while self.is_paused:
            self.root.update()
            time.sleep(0.1)
            if self.should_stop: return True
        return self.should_stop

    def calc_f_curve(self):
        try:
            if not hasattr(self, 'cached_distances') or not self.cached_distances: return
            l_val = self.entry_l.get()
            t_val = self.entry_t.get()
            if not l_val or not t_val: return
            
            x, f = self.engine.calculate_f_values(self.cached_distances, float(t_val))
            hist = getattr(self, 'hist_data', None)
            self.chart_f.plot_f_curve(x, f, float(t_val), max(self.cached_distances), hist, self.fixed_intervals)
        except ValueError: pass

    def export_csv(self):
        if not self.cached_starts: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["=== CAM Analyzer Report ==="])
                # [修正] 匯出標題對應新版 KPI
                writer.writerow(["Total Dist", self.kpi_vals['total'].cget("text")])
                writer.writerow(["G01 Dist", self.kpi_vals['g01'].cget("text")])
                writer.writerow(["G00 Dist", self.kpi_vals['g00'].cget("text")])
                writer.writerow([])
                
                axes = [ax for ax in ['X','Y','Z','A','B','C'] if ax in self.detected_axes]
                header = ["No"] + [f"Start_{a}" for a in axes] + [f"End_{a}" for a in axes] + ["Dist"]
                writer.writerow(header)
                
                axis_map = {'X':0, 'Y':1, 'Z':2, 'A':3, 'B':4, 'C':5}
                indices = [axis_map[ax] for ax in ['X','Y','Z','A','B','C'] if ax in self.detected_axes]
                
                rows = []
                for i, (s, e, d) in enumerate(zip(self.cached_starts, self.cached_ends, self.cached_distances)):
                    s_v = [s[idx] for idx in indices]
                    e_v = [e[idx] for idx in indices]
                    rows.append([i+1] + s_v + e_v + [f"{d:.5f}"])
                    if len(rows) >= 5000:
                        writer.writerows(rows)
                        rows = []
                if rows: writer.writerows(rows)
            messagebox.showinfo("成功", "匯出完成")
        except Exception as e: messagebox.showerror("失敗", str(e))

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        # [修正] 使用中文
        self.btn_pause.config(text="繼續" if self.is_paused else "暫停")

    def stop_analysis(self):
        self.should_stop = True

    def on_closing(self):
        self.should_stop = True
        self.root.destroy()
    
    def on_resize(self, event): pass