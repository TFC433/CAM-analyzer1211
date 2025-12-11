import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import ttkbootstrap as ttk
import os
import csv
import time
import threading
import queue

from backend import GCodeAnalyzer
from frontend.styles import ThemeManager
from frontend.charts import ChartManager

class CAMApp:
    def __init__(self, root):
        self.root = root
        
        self.APP_NAME = "CAM Analyzer"
        self.APP_VERSION = "v7.6 (TCP Vector Mode)"
        self.root.title(f"{self.APP_NAME} {self.APP_VERSION}")
        
        self.tm = ThemeManager(root)
        self.colors = self.tm.get_color_palette() 
        
        self.engine = GCodeAnalyzer()
        self.msg_queue = queue.Queue()
        
        # 狀態
        self.file_path = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.status_var = tk.StringVar(value="就緒")
        
        # 數據
        self.stats = {"g00": 0.0, "g01": 0.0, "time": 0.0}
        self.cached_distances = []
        self.detected_axes = []
        self.detailed_logs = []
        self.top_10_stats = []
        self.top_3_stats = []
        self.current_calc_mode = "" 
        
        # 直方圖 Bin 設定
        self.fixed_intervals = [
            (0.000, 0.001), (0.001, 0.01), (0.01, 0.02), (0.02, 0.03), 
            (0.03, 0.04), (0.04, 0.05), (0.05, 0.06), (0.06, 0.07), 
            (0.07, 0.08), (0.08, 0.09), (0.09, 0.10), (0.10, 0.20), 
            (0.20, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60), 
            (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.00),
            (1.00, float('inf'))
        ]
        self.bins = [i[0] for i in self.fixed_intervals] + [self.fixed_intervals[-1][1]]
        
        self._init_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.check_queue() 

    def _init_layout(self):
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # === 左側 Sidebar ===
        self.sidebar = ttk.Frame(self.root, style='Sidebar.TFrame', padding=20, width=250)
        self.sidebar.grid(row=0, column=0, sticky='ns')
        self.sidebar.grid_propagate(False)

        ttk.Label(self.sidebar, text=self.APP_NAME, style='Inverse.TLabel', 
                  font=self.tm.fonts['h1']).pack(pady=(10, 40), anchor='center')

        ttk.Label(self.sidebar, text="操作", style='Inverse.TLabel', font=self.tm.fonts['h2']).pack(anchor='w', pady=(0, 10))
        self.btn_open = ttk.Button(self.sidebar, text="📂 開啟檔案", bootstyle="success", command=self.select_file)
        self.btn_open.pack(fill='x', pady=5)
        self.btn_analyze = ttk.Button(self.sidebar, text="▶ 開始分析", bootstyle="primary", 
                                      state='disabled', command=self.start_analysis_thread)
        self.btn_analyze.pack(fill='x', pady=5)

        ctrl_frame = ttk.Frame(self.sidebar, style='Sidebar.TFrame')
        ctrl_frame.pack(fill='x', pady=5)
        self.btn_pause = ttk.Button(ctrl_frame, text="暫停", bootstyle="warning", width=4, state='disabled', command=self.toggle_pause)
        self.btn_pause.pack(side='left', fill='x', expand=True, padx=(0, 2))
        self.btn_stop = ttk.Button(ctrl_frame, text="停止", bootstyle="danger", width=4, state='disabled', command=self.stop_analysis)
        self.btn_stop.pack(side='right', fill='x', expand=True, padx=(2, 0))

        ttk.Separator(self.sidebar).pack(fill='x', pady=20)

        # 視圖按鈕
        ttk.Label(self.sidebar, text="視圖", style='Inverse.TLabel', font=self.tm.fonts['h2']).pack(anchor='w', pady=(0, 10))
        self.nav_btns = {}
        for key, icon, label in [('dashboard', '📊', '儀表板'), ('detail', '📝', '詳細數據'), ('log', '📜', 'LOG紀錄')]:
            btn = ttk.Button(self.sidebar, text=f"{icon}  {label}", style='Nav.TButton',
                             command=lambda k=key: self.switch_view(k))
            btn.pack(fill='x', pady=2)
            self.nav_btns[key] = btn

        # === 右側 Main Area ===
        self.main_area = ttk.Frame(self.root)
        self.main_area.grid(row=0, column=1, sticky='nsew')
        
        # --- Top: Header ---
        self.header = ttk.Frame(self.main_area, padding=0, style='Card.TFrame') 
        self.header.pack(fill='x')
        
        header_inner = ttk.Frame(self.header, padding=(20, 15), style='Card.TFrame')
        header_inner.pack(fill='x')

        # 1. 檔名
        ttk.Label(header_inner, text="當前檔案", style='CardLabel.TLabel').pack(anchor='w')
        self.lbl_filename = ttk.Label(header_inner, text="尚未載入", style='Header.TLabel')
        self.lbl_filename.pack(anchor='w', pady=(0, 10))
        
        # 2. 軸向與模式
        self.axis_row = ttk.Frame(header_inner, style='Card.TFrame')
        self.axis_row.pack(anchor='w')
        ttk.Label(self.axis_row, text="偵測軸向: ", style='CardLabel.TLabel').pack(side='left')
        
        self.axis_indicators = {}
        # 預先建立所有標籤，但稍後再透過 pack 控制顯示順序與隱藏
        for ax in ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'K']:
            lbl = ttk.Label(self.axis_row, text=ax, style='AxisInactive.TLabel', width=3, anchor='center')
            # 這裡不先 pack，改在 update_results 動態決定
            self.axis_indicators[ax] = lbl
            
        # 預設先顯示 X~C，隱藏 IJK
        for ax in ['X', 'Y', 'Z', 'A', 'B', 'C']:
            self.axis_indicators[ax].pack(side='left', padx=2)

        # [模式顯示標籤]
        self.lbl_calc_mode = ttk.Label(self.axis_row, text="", style='Inverse.TLabel', font=self.tm.fonts['ui_bold'])
        self.lbl_calc_mode.pack(side='left', padx=(20, 0))

        # 3. 進度條
        self.progress = ttk.Progressbar(self.header, mode='determinate', bootstyle='success-striped', style='Thick.Horizontal.TProgressbar')
        self.progress.pack(fill='x', side='bottom')
        self.tm.style.configure('Thick.Horizontal.TProgressbar', thickness=10)

        # --- Center: 內容 ---
        self.content = ttk.Frame(self.main_area, padding=20)
        self.content.pack(fill='both', expand=True)
        self.view_container = ttk.Frame(self.content)
        self.view_container.pack(fill='both', expand=True)
        
        self._init_dashboard()
        self._init_detail_text()
        self._init_log()
        
        # --- Bottom: 狀態列 ---
        self.statusbar = ttk.Frame(self.main_area, padding=(10, 5), style='Sidebar.TFrame')
        self.statusbar.pack(fill='x', side='bottom')
        self.lbl_status = ttk.Label(self.statusbar, textvariable=self.status_var, style='Inverse.TLabel')
        self.lbl_status.pack(side='left')

        self.switch_view('dashboard')

    def _init_dashboard(self):
        self.view_dash = ttk.Frame(self.view_container)
        
        # Row 1
        row1 = ttk.Frame(self.view_dash)
        row1.pack(fill='x', pady=(0, 10))
        for i in range(4): row1.grid_columnconfigure(i, weight=1)
        
        self.kpi_vals = {}
        kpi_defs_r1 = [
            (0, 'total', '總行程 (Total)'), 
            (1, 'g01', 'G01 切削距離'), 
            (2, 'g00', 'G00 空跑距離'),
            (3, 'time', '預估切削時間')
        ]
        
        for col_idx, key, title in kpi_defs_r1:
            card = ttk.Frame(row1, style='Card.TFrame', padding=15)
            card.grid(row=0, column=col_idx, sticky='nsew', padx=(0 if col_idx==0 else 10, 0))
            ttk.Label(card, text=title, style='CardLabel.TLabel').pack(anchor='w')
            val = ttk.Label(card, text="--", style='CardValue.TLabel')
            val.pack(anchor='w', pady=(5, 0))
            self.kpi_vals[key] = val

        # Row 2
        row2 = ttk.Frame(self.view_dash)
        row2.pack(fill='x', pady=(0, 20))
        for i in range(4): row2.grid_columnconfigure(i, weight=1)

        kpi_defs_r2 = [
            (0, 'bpt', '最適合 BPT (以上)'),
            (1, 'top1', 'Top 1 分佈'),
            (2, 'top2', 'Top 2 分佈'),
            (3, 'top3', 'Top 3 分佈')
        ]
        
        for col_idx, key, title in kpi_defs_r2:
            card = ttk.Frame(row2, style='Card.TFrame', padding=15)
            card.grid(row=0, column=col_idx, sticky='nsew', padx=(0 if col_idx==0 else 10, 0))
            ttk.Label(card, text=title, style='CardLabel.TLabel').pack(anchor='w')
            val = ttk.Label(card, text="--", style='CardValue.TLabel', font=self.tm.fonts['h2'])
            val.pack(anchor='w', pady=(5, 0))
            self.kpi_vals[key] = val

        # Chart
        chart_area = ttk.Frame(self.view_dash, style='Card.TFrame', padding=5)
        chart_area.pack(fill='both', expand=True)
        nb = ttk.Notebook(chart_area)
        nb.pack(fill='both', expand=True)
        
        f1 = ttk.Frame(nb, style='Card.TFrame')
        nb.add(f1, text="距離分佈")
        self.chart_hist = ChartManager(f1, self.tm)
        
        f2 = ttk.Frame(nb, style='Card.TFrame')
        nb.add(f2, text="微小單節 F 值")
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

    def _init_detail_text(self):
        self.view_detail = ttk.Frame(self.view_container)
        
        ctrl = ttk.Frame(self.view_detail)
        ctrl.pack(fill='x', pady=(0, 10))
        ttk.Label(ctrl, text="顯示筆數:", font=self.tm.fonts['ui']).pack(side='left')
        self.combo_limit = ttk.Combobox(ctrl, values=["1000", "5000", "全部"], width=10, state='readonly')
        self.combo_limit.current(0)
        self.combo_limit.pack(side='left', padx=5)
        self.combo_limit.bind("<<ComboboxSelected>>", self.refresh_detail_view)
        ttk.Button(ctrl, text="匯出 CSV", bootstyle="success-outline", command=self.export_csv).pack(side='right')
        
        self.txt_detail = scrolledtext.ScrolledText(
            self.view_detail, font=self.tm.fonts['mono'],
            bg=self.colors['bg_card'], fg=self.colors['fg_main'],
            insertbackground='white', relief='flat', padx=10, pady=10
        )
        self.txt_detail.pack(fill='both', expand=True)

    def _init_log(self):
        self.view_log = ttk.Frame(self.view_container)
        self.txt_log = scrolledtext.ScrolledText(
            self.view_log, font=self.tm.fonts['mono'],
            bg=self.colors['bg_card'], fg=self.colors['fg_main'],
            insertbackground='white', relief='flat', padx=10, pady=10
        )
        self.txt_log.pack(fill='both', expand=True)

    def switch_view(self, view):
        self.view_dash.pack_forget()
        self.view_detail.pack_forget()
        self.view_log.pack_forget()
        for k, btn in self.nav_btns.items():
            btn.configure(style=('NavActive.TButton' if k == view else 'Nav.TButton'))
        if view == 'dashboard': self.view_dash.pack(fill='both', expand=True)
        elif view == 'detail': self.view_detail.pack(fill='both', expand=True)
        elif view == 'log': self.view_log.pack(fill='both', expand=True)

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("CAM Files", "*.txt *.nc *.ncd *.tap"), ("All", "*.*")])
        if path:
            self.file_path = path
            self.lbl_filename.config(text=os.path.basename(path))
            self.btn_analyze.config(state='normal')
            self.status_var.set("已載入，等待分析")
            
            for k in self.kpi_vals: self.kpi_vals[k].config(text="--")
            # 檔案載入時，先將燈號重置為不活躍 (不改變顯示結構)
            for lbl in self.axis_indicators.values(): lbl.configure(style='AxisInactive.TLabel')
            self.lbl_calc_mode.config(text="")
            self.txt_detail.delete(1.0, tk.END)
            self.txt_log.delete(1.0, tk.END)

    def start_analysis_thread(self):
        if self.is_running: return
        self.is_running = True
        self.should_stop = False
        self.is_paused = False
        
        self.btn_analyze.config(state='disabled')
        self.btn_open.config(state='disabled')
        self.btn_pause.config(state='normal', text="暫停")
        self.btn_stop.config(state='normal')
        
        self.txt_log.delete(1.0, tk.END)
        self.txt_detail.delete(1.0, tk.END)
        self.txt_log.insert(tk.END, "正在啟動分析核心...\n")
        
        thread = threading.Thread(target=self.run_analysis)
        thread.daemon = True
        thread.start()

    def run_analysis(self):
        try:
            content = ""
            for chunk in self.engine.read_file_generator(self.file_path, progress_callback=self.thread_callback):
                content += chunk
                if self.should_stop: break
            
            if self.should_stop: raise InterruptedError("使用者停止")

            data = self.engine.parse_and_calculate(content, self.thread_callback)
            if not data: raise InterruptedError("停止")
            
            dists, total_dist, total_time, top10, top3, bpt = self.engine.calculate_metrics_and_stats(
                data, self.bins, self.fixed_intervals, self.thread_callback
            )
            
            if dists is None: raise InterruptedError("停止")

            result_payload = {
                "axes": data["axes"],
                "skipped": data["skipped"],
                "g00": data["g00_dist"],
                "g01": total_dist,
                "time": total_time,
                "dists": dists,
                "detailed_logs": data["detailed_logs"],
                "top10": top10,
                "top3": top3,
                "bpt": bpt,
                "calc_mode": data["calc_mode"]
            }
            self.msg_queue.put(("DONE", result_payload))

        except InterruptedError:
            self.msg_queue.put(("STATUS", "已取消"))
        except Exception as e:
            self.msg_queue.put(("ERROR", str(e)))
        finally:
            self.msg_queue.put(("FINISH", None))

    def thread_callback(self, pct, msg):
        self.msg_queue.put(("PROGRESS", (pct, msg)))
        while self.is_paused:
            self.msg_queue.put(("STATUS", "已暫停..."))
            time.sleep(0.2)
            if self.should_stop: return True
        return self.should_stop

    def check_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "PROGRESS":
                    pct, txt = data
                    self.progress['value'] = pct
                    self.status_var.set(f"{txt} ({pct:.1f}%)")
                elif msg_type == "STATUS":
                    self.status_var.set(data)
                elif msg_type == "DONE":
                    self.update_results(data)
                elif msg_type == "ERROR":
                    messagebox.showerror("錯誤", data)
                elif msg_type == "FINISH":
                    self.is_running = False
                    self.btn_analyze.config(state='normal')
                    self.btn_open.config(state='normal')
                    self.btn_pause.config(state='disabled')
                    self.btn_stop.config(state='disabled')
                    self.progress['value'] = 0
                    if "錯誤" not in self.status_var.get():
                        self.status_var.set("就緒")
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)

    def update_results(self, data):
        self.stats["g00"] = data["g00"]
        self.stats["g01"] = data["g01"]
        self.stats["time"] = data["time"]
        self.cached_distances = data["dists"]
        self.detected_axes = data["axes"]
        self.detailed_logs = data["detailed_logs"]
        self.top_10_stats = data["top10"]
        self.top_3_stats = data["top3"]
        self.current_calc_mode = data["calc_mode"]
        
        # 1. 軸向燈號 (動態顯示控制)
        # 先全部隱藏 (unpack)
        for lbl in self.axis_indicators.values():
            lbl.pack_forget()
            lbl.configure(style='AxisInactive.TLabel')
            
        # 決定要顯示哪些燈號
        # 基礎: X Y Z A B C (永遠顯示位置，只是狀態不同)
        visible_axes = ['X', 'Y', 'Z', 'A', 'B', 'C']
        
        # 如果是 TCP 模式，追加 I J K
        is_tcp = "TCP" in self.current_calc_mode
        if is_tcp:
            visible_axes.extend(['I', 'J', 'K'])
            
        # 依照固定順序 pack 回去
        for ax in visible_axes:
            self.axis_indicators[ax].pack(side='left', padx=2)
            # 如果該軸真的在偵測列表中，亮燈
            if ax in self.detected_axes:
                self.axis_indicators[ax].configure(style='AxisActive.TLabel')

        # 確保模式標籤還在最後面
        self.lbl_calc_mode.pack_forget()
        self.lbl_calc_mode.pack(side='left', padx=(20, 0))
            
        self.lbl_calc_mode.config(text=f"[ {self.current_calc_mode} ]")
        if is_tcp:
            # 亮色顯示 TCP 模式
            self.lbl_calc_mode.configure(foreground=self.colors['accent'])
        else:
            # 預設顏色顯示一般模式
            self.lbl_calc_mode.configure(foreground=self.colors['fg_main'])
            
        # 2. KPI - Row 1
        total = self.stats["g00"] + self.stats["g01"]
        g01_pct = (self.stats["g01"] / total * 100) if total > 0 else 0
        g00_pct = (self.stats["g00"] / total * 100) if total > 0 else 0
        
        self.kpi_vals['total'].config(text=f"{total:,.2f} mm")
        self.kpi_vals['g01'].config(text=f"{self.stats['g01']:,.2f} mm ({g01_pct:.1f}%)")
        self.kpi_vals['g00'].config(text=f"{self.stats['g00']:,.2f} mm ({g00_pct:.1f}%)")
        
        total_seconds = int(self.stats["time"] * 60)
        h, m, s = total_seconds // 3600, (total_seconds % 3600) // 60, total_seconds % 60
        self.kpi_vals['time'].config(text=f"{h:02d}:{m:02d}:{s:02d}")
        
        # KPI - Row 2
        if data['bpt']:
            self.kpi_vals['bpt'].config(text=f"{data['bpt']['range_str']}")
        else:
            self.kpi_vals['bpt'].config(text="無法計算")

        for i in range(3):
            key = f'top{i+1}'
            if i < len(self.top_3_stats):
                item = self.top_3_stats[i]
                self.kpi_vals[key].config(text=f"{item['label']} ({item['pct']:.1f}%)")
            else:
                self.kpi_vals[key].config(text="--")

        # 3. Log
        self.txt_log.insert(tk.END, f"=== 分析模式: {self.current_calc_mode} ===\n")
        self.txt_log.insert(tk.END, "=== 分析完成: 略過(G01)/警告/指令列表 ===\n")
        self.txt_log.insert(tk.END, "(已過濾正常 G01 移動，僅顯示非切削與異常指令)\n\n")
        MAX_LOG = 5000
        for i, l in enumerate(data["skipped"]):
            if i < MAX_LOG: self.txt_log.insert(tk.END, l + "\n")
            else: 
                self.txt_log.insert(tk.END, f"... (隱藏 {len(data['skipped'])-MAX_LOG} 筆) ...\n")
                break
        
        # 4. Detail
        self.refresh_detail_view()

        # 5. Chart
        self.chart_hist.plot_histogram(self.cached_distances, self.bins, self.fixed_intervals)
        if self.entry_l.get() and self.entry_t.get():
            self.calc_f_curve()
            
        self.status_var.set("分析完成")
        self.switch_view('dashboard')

    def refresh_detail_view(self, event=None):
        if not self.detailed_logs: return
        self.txt_detail.delete(1.0, tk.END)
        
        self.txt_detail.insert(tk.END, f"=== Mode: {self.current_calc_mode} ===\n")
        self.txt_detail.insert(tk.END, "=== Top 10 Distribution Stats ===\n")
        for i, item in enumerate(self.top_10_stats):
            bar = "|" * int(item['pct'] / 2)
            self.txt_detail.insert(tk.END, f"{i+1:2d}. {item['label']:<15} | Cnt:{item['count']:<5} | {item['pct']:5.1f}% | AvgF:{int(item['avg_feed'])} | {bar}\n")
        self.txt_detail.insert(tk.END, "="*90 + "\n\n")

        limit_str = self.combo_limit.get()
        limit = len(self.detailed_logs) if limit_str == "全部" else int(limit_str)
        
        # === 動態表頭生成 (易讀性優化) ===
        # 1. 決定要顯示哪些軸
        all_axes_priority = ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'K']
        active_cols = [ax for ax in all_axes_priority if ax in self.detected_axes]
        
        # 2. 生成易讀標題 (使用 Start_X, End_X)
        header_start_parts = [f"Start_{ax}" for ax in active_cols]
        header_end_parts = [f"End_{ax}" for ax in active_cols]
        header_start = " ".join(header_start_parts)
        header_end = " ".join(header_end_parts)
        
        # 3. 決定距離欄位 (依照模式)
        is_tcp = "TCP" in self.current_calc_mode
        if is_tcp:
            dist_header = f"{'XYZ_Dist':<8} | {'Rot_Deg':<7} | {'Total_Dist':<10}"
        else:
            dist_header = f"{'Dist':<8}"

        self.txt_detail.insert(tk.END, f"{'Line':<6} | {header_start:<30} | {header_end:<30} | {dist_header} | {'Feed':<6} | {'Info'}\n")
        self.txt_detail.insert(tk.END, "-"*140 + "\n")
        
        axis_map_full = {ax: i for i, ax in enumerate(all_axes_priority)}
        active_indices = [axis_map_full[ax] for ax in active_cols]
        
        count = 0
        buffer = ""
        for log in self.detailed_logs:
            if count >= limit: break
            
            # 取出 Start / End 對應欄位的數值
            s_str = " ".join([f"{log['start'][i]:.1f}" for i in active_indices])
            e_str = " ".join([f"{log['end'][i]:.1f}" for i in active_indices])
            
            # 取出距離數值
            if is_tcp:
                d_xyz = log.get('dist_xyz', 0.0)
                r_deg = log.get('rot_deg', 0.0)
                d_total = log['dist']
                dist_str = f"{d_xyz:<8.3f} | {r_deg:<7.1f} | {d_total:<10.3f}"
            else:
                dist_str = f"{log['dist']:<8.3f}"

            buffer += f"{log['line']:<6} | {s_str:<30} | {e_str:<30} | {dist_str} | {int(log['feed']):<6} | {log['info']}\n"
            count += 1
            if count % 500 == 0:
                self.txt_detail.insert(tk.END, buffer)
                buffer = ""
                self.root.update_idletasks()
        if buffer: self.txt_detail.insert(tk.END, buffer)

    def calc_f_curve(self):
        try:
            if not self.cached_distances: return
            l_val = self.entry_l.get()
            t_val = self.entry_t.get()
            if not l_val or not t_val: return
            x, f = self.engine.calculate_f_values(self.cached_distances, float(t_val))
            hist = getattr(self, 'hist_data', None)
            self.chart_f.plot_f_curve(x, f, float(t_val), max(self.cached_distances), hist, self.fixed_intervals)
        except ValueError: pass

    def export_csv(self):
        if not self.detailed_logs: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        
        def _export():
            try:
                self.msg_queue.put(("STATUS", "正在匯出 CSV..."))
                with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    
                    all_axes_priority = ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'K']
                    active_cols = [ax for ax in all_axes_priority if ax in self.detected_axes]
                    
                    # 使用易讀標題
                    s_headers = [f"Start_{ax}" for ax in active_cols]
                    e_headers = [f"End_{ax}" for ax in active_cols]
                    
                    is_tcp = "TCP" in self.current_calc_mode
                    if is_tcp:
                        dist_headers = ["XYZ_Dist", "Rot_Deg", "Total_Dist"]
                    else:
                        dist_headers = ["Dist"]
                        
                    writer.writerow(["Line", "Mode"] + s_headers + e_headers + dist_headers + ["Feed", "Info"])
                    
                    axis_map_full = {ax: i for i, ax in enumerate(all_axes_priority)}
                    active_indices = [axis_map_full[ax] for ax in active_cols]
                    
                    rows = []
                    for l in self.detailed_logs:
                        s_v = [l['start'][i] for i in active_indices]
                        e_v = [l['end'][i] for i in active_indices]
                        
                        if is_tcp:
                            d_vals = [l.get('dist_xyz', 0), l.get('rot_deg', 0), l['dist']]
                        else:
                            d_vals = [l['dist']]
                            
                        rows.append([l['line'], self.current_calc_mode] + s_v + e_v + d_vals + [l['feed'], l['info']])
                    writer.writerows(rows)
                self.msg_queue.put(("STATUS", "匯出完成"))
                messagebox.showinfo("成功", "匯出完成")
            except Exception as e:
                messagebox.showerror("失敗", str(e))
        threading.Thread(target=_export).start()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.btn_pause.config(text="繼續" if self.is_paused else "暫停")

    def stop_analysis(self):
        self.should_stop = True

    def on_closing(self):
        self.should_stop = True
        self.root.destroy()
    def on_resize(self, event): pass