import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import ttkbootstrap as ttk
import os
import time
import csv
import numpy as np

from backend import GCodeAnalyzer
from frontend.styles import ThemeManager
from frontend.charts import ChartManager

class CAMApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CAM 程式分析器 v3.1 (效率統計版)")
        
        self.tm = ThemeManager(root)
        self.engine = GCodeAnalyzer()
        
        self.file_path = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        
        # 數據緩存
        self.skipped_lines = []
        self.cached_starts = [] # G01 起點
        self.cached_ends = []   # G01 終點
        self.cached_distances = []
        self.detected_axes = []
        
        # 統計數據
        self.stats = {"g00": 0.0, "g01": 0.0}
        
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

    def _init_layout(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill="both", expand=True)

        self.main_pane = ttk.Panedwindow(main_frame, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill="both", expand=True)

        # --- 左側 ---
        self.left_frame = ttk.Frame(self.main_pane, padding=10)
        self.main_pane.add(self.left_frame, weight=40)

        ttk.Label(self.left_frame, text="CAM 程式分析器", font=self.tm.fonts['header']).pack(pady=(0, 5))

        # 軸向儀表板
        self.axis_indicators = {}
        self._create_axis_dashboard(self.left_frame)
        self._create_control_group(self.left_frame)

        # 日誌控制
        log_ctrl = ttk.Frame(self.left_frame)
        log_ctrl.pack(fill='x', pady=(10, 0))
        ttk.Label(log_ctrl, text="顯示筆數:", font=self.tm.fonts['main']).pack(side='left')
        self.combo_log_limit = ttk.Combobox(log_ctrl, values=["1000", "5000", "10000"], width=8, state='readonly')
        self.combo_log_limit.current(0)
        self.combo_log_limit.pack(side='left', padx=5)
        self.combo_log_limit.bind("<<ComboboxSelected>>", self.refresh_log_display)
        
        self.btn_export = ttk.Button(log_ctrl, text="匯出完整 CSV", command=self.export_csv, state='disabled', style='Custom.Accent.TButton')
        self.btn_export.pack(side='right')

        self.notebook = ttk.Notebook(self.left_frame)
        self.notebook.pack(fill="both", expand=True, pady=5)
        self.log_text = self._create_text_tab("分析日誌")
        self.result_text = self._create_text_tab("區間統計")

        # --- 右側 ---
        self.right_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.right_frame, weight=60)
        
        self.chart_notebook = ttk.Notebook(self.right_frame)
        self.chart_notebook.pack(fill="both", expand=True)
        
        self.tab_hist = ttk.Frame(self.chart_notebook)
        self.chart_notebook.add(self.tab_hist, text="距離分佈")
        self.chart_hist = ChartManager(self.tab_hist, self.tm)
        
        self.tab_f = ttk.Frame(self.chart_notebook)
        self.chart_notebook.add(self.tab_f, text="微小單節處理能力")
        
        f_ctrl = ttk.Frame(self.tab_f)
        f_ctrl.pack(fill='x', padx=5, pady=5)
        ttk.Label(f_ctrl, text="L:", font=self.tm.fonts['main']).pack(side='left')
        self.entry_l = ttk.Entry(f_ctrl, width=8)
        self.entry_l.pack(side='left', padx=5)
        ttk.Label(f_ctrl, text="T:", font=self.tm.fonts['main']).pack(side='left')
        self.entry_t = ttk.Entry(f_ctrl, width=8)
        self.entry_t.pack(side='left', padx=5)
        ttk.Button(f_ctrl, text="計算", command=self.calc_f_curve, style='Custom.Warning.TButton').pack(side='left')
        
        self.chart_f = ChartManager(self.tab_f, self.tm)
        
        ttk.Label(main_frame, text="© 2025 TFC433", font=self.tm.fonts['copyright']).pack(side='bottom', pady=5)

    def _create_axis_dashboard(self, parent):
        frame = ttk.Labelframe(parent, text="軸向偵測儀表板", padding=10)
        frame.pack(fill="x", pady=5)
        inner = ttk.Frame(frame)
        inner.pack(fill='x', expand=True)
        for axis in ['X', 'Y', 'Z', 'A', 'B', 'C']:
            lbl = ttk.Label(inner, text=axis, style='AxisInactive.TLabel', width=4)
            lbl.pack(side='left', padx=5, expand=True)
            self.axis_indicators[axis] = lbl

    def _create_control_group(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill='x', pady=(0, 5))
        mb = ttk.Menubutton(top, text="其他功能", style='Custom.TMenubutton')
        mb.pack(side='right')
        menu = tk.Menu(mb, tearoff=0)
        mb['menu'] = menu
        
        theme_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="切換主題", menu=theme_menu)
        theme_menu.add_command(label="明亮主題", command=lambda: self.tm.toggle_theme('light'))
        theme_menu.add_command(label="暗黑主題", command=lambda: self.tm.toggle_theme('dark'))
        menu.add_separator()
        menu.add_command(label="顯示略過/指令內容", command=self.show_skipped_lines)
        
        self.lbl_file = ttk.Label(parent, text="未選擇檔案", font=self.tm.fonts['main'])
        self.lbl_file.pack(fill='x', pady=5)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="📂 選擇檔案", command=self.select_file, style='Custom.Success.TButton').pack(fill='x', pady=2)
        self.btn_analyze = ttk.Button(btn_frame, text="📊 開始分析", command=self.start_analysis, state='disabled', style='Custom.Primary.TButton')
        self.btn_analyze.pack(fill='x', pady=2)

        ctrl = ttk.Frame(parent)
        ctrl.pack(fill='x', pady=5)
        self.btn_pause = ttk.Button(ctrl, text="⏸ 暫停", command=self.toggle_pause, state='disabled', width=10)
        self.btn_pause.pack(side='left', padx=2)
        self.btn_stop = ttk.Button(ctrl, text="⏹ 停止", command=self.stop_analysis, state='disabled', width=10, style='Custom.Danger.TButton')
        self.btn_stop.pack(side='left', padx=2)
        
        self.progress = ttk.Progressbar(parent, mode='determinate')
        self.progress.pack(fill='x', pady=5)

    def _create_text_tab(self, title):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        text_area = scrolledtext.ScrolledText(frame, height=10, font=self.tm.fonts['main'])
        text_area.pack(fill="both", expand=True)
        return text_area

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("CAM Files", "*.txt *.nc *.ncd *.tap"), ("All", "*.*")])
        if path:
            self.file_path = path
            self.lbl_file.config(text=os.path.basename(path))
            self.btn_analyze.config(state='normal')
            self.reset_indicators()

    def reset_indicators(self):
        for lbl in self.axis_indicators.values():
            lbl.configure(style='AxisInactive.TLabel')

    def update_indicators(self, active_axes):
        for axis in active_axes:
            if axis in self.axis_indicators:
                self.axis_indicators[axis].configure(style='AxisActive.TLabel')

    def progress_callback(self, percentage, message):
        self.progress['value'] = percentage
        self.root.title(f"分析中... {percentage:.1f}% - {message}")
        while self.is_paused:
            self.root.update()
            time.sleep(0.1)
            if self.should_stop: return True
        return self.should_stop

    def start_analysis(self):
        if self.is_running: return
        self.is_running = True
        self.should_stop = False
        self.is_paused = False
        
        # 重置數據
        self.skipped_lines = []
        self.cached_starts = []
        self.cached_ends = []
        self.cached_distances = []
        self.stats = {"g00": 0.0, "g01": 0.0}
        
        self.btn_analyze.config(state='disabled')
        self.btn_export.config(state='disabled')
        self.btn_pause.config(state='normal', text="⏸ 暫停")
        self.btn_stop.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.result_text.delete(1.0, tk.END)
        self.reset_indicators()

        try:
            content = ""
            for chunk in self.engine.read_file_generator(self.file_path, progress_callback=self.progress_callback):
                content += chunk
                if self.should_stop: break
            
            if self.should_stop: raise InterruptedError("停止")

            # 1. 解析與初算
            data = self.engine.parse_and_calculate(content, self.progress_callback)
            if not data: raise InterruptedError("停止")
            
            self.detected_axes = data["axes"]
            self.skipped_lines = data["skipped"]
            self.stats["g00"] = data["g00_dist"]
            
            # 更新 UI
            self.update_indicators(self.detected_axes)
            self.cached_starts = data["starts"]
            self.cached_ends = data["ends"]
            
            if not self.cached_starts: raise InterruptedError("無 G01 移動路徑")

            # 2. NumPy 精算 G01
            self.cached_distances, total_g01 = self.engine.calculate_g01_metrics(data, self.progress_callback)
            self.stats["g01"] = total_g01
            
            self.btn_export.config(state='normal')

            # 3. 顯示結果 (含統計看板)
            self.refresh_log_display()

            # 4. 區間統計
            hist, _ = self.engine.calculate_histogram_data(self.cached_distances, self.bins)
            self.hist_data = hist
            total = len(self.cached_distances)
            
            self.result_text.insert(tk.END, f"{'區間':<20}{'單節數':<10}{'百分比 (%)':<15}\n")
            self.result_text.insert(tk.END, "-" * 45 + "\n")
            for i, count in enumerate(hist):
                s, e = self.fixed_intervals[i]
                lbl = f"{s:.3f}~{e:.3f}" if e != float('inf') else f"{s:.3f}以上"
                pct = (count/total*100) if total > 0 else 0
                self.result_text.insert(tk.END, f"{lbl:<20}{count:<10}{pct:.2f}\n")

            # 5. 繪圖
            self.chart_hist.plot_histogram(self.cached_distances, self.bins, self.fixed_intervals)
            self.calc_f_curve()

        except InterruptedError:
            pass
        except Exception as e:
            messagebox.showerror("錯誤", str(e))
        finally:
            self.is_running = False
            self.btn_analyze.config(state='normal')
            self.btn_pause.config(state='disabled')
            self.btn_stop.config(state='disabled')
            self.progress['value'] = 0
            self.root.title("CAM 程式分析器 v3.1")

    def refresh_log_display(self, event=None):
        if not self.cached_starts: return
        
        limit = int(self.combo_log_limit.get())
        self.log_text.delete(1.0, tk.END)
        
        # [新增] 效率統計看板
        g00 = self.stats["g00"]
        g01 = self.stats["g01"]
        total = g00 + g01
        ratio = (g00 / total * 100) if total > 0 else 0
        
        stats_msg = (
            f"=== 效率統計 (偵測軸向: {', '.join(self.detected_axes)}) ===\n"
            f"G00 總距離 (空跑): {g00:,.2f} mm\n"
            f"G01 總距離 (切削): {g01:,.2f} mm\n"
            f"總行程: {total:,.2f} mm\n"
            f"空跑佔比: {ratio:.1f}%\n"
            f"=========================================\n\n"
        )
        self.log_text.insert(tk.END, stats_msg)
        
        # 列表顯示
        axis_map = {'X':0, 'Y':1, 'Z':2, 'A':3, 'B':4, 'C':5}
        indices = [axis_map[ax] for ax in ['X','Y','Z','A','B','C'] if ax in self.detected_axes]
        
        header = f"{'NO':<6}{'Start':<30}{'End':<30}{'Dist':<10}\n"
        self.log_text.insert(tk.END, header)
        
        for i, (s, e, d) in enumerate(zip(self.cached_starts[:limit], self.cached_ends[:limit], self.cached_distances[:limit])):
            s_v = [s[idx] for idx in indices]
            e_v = [e[idx] for idx in indices]
            s_str = "(" + ",".join([f"{v:.1f}" for v in s_v]) + ")"
            e_str = "(" + ",".join([f"{v:.1f}" for v in e_v]) + ")"
            self.log_text.insert(tk.END, f"{i+1:<6}{s_str:<30}{e_str:<30}{d:.4f}\n")
            
        if len(self.cached_distances) > limit:
            self.log_text.insert(tk.END, f"\n... (僅顯示前 {limit} 筆) ...\n")

    def export_csv(self):
        if not self.cached_starts: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # 寫入統計 Header
                writer.writerow(["=== Statistics ==="])
                writer.writerow(["Total G00", self.stats["g00"]])
                writer.writerow(["Total G01", self.stats["g01"]])
                writer.writerow([])
                
                # 寫入數據
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
        except Exception as e:
            messagebox.showerror("失敗", str(e))

    def calc_f_curve(self):
        try:
            if not hasattr(self, 'cached_distances') or not self.cached_distances: return
            l, t = float(self.entry_l.get()), float(self.entry_t.get())
            x, f = self.engine.calculate_f_values(self.cached_distances, t)
            hist = getattr(self, 'hist_data', None)
            self.chart_f.plot_f_curve(x, f, t, max(self.cached_distances), hist, self.fixed_intervals)
        except ValueError: pass

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.btn_pause.config(text="⏵ 繼續" if self.is_paused else "⏸ 暫停")

    def stop_analysis(self):
        self.should_stop = True

    def show_skipped_lines(self):
        if not self.skipped_lines: return
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, "=== 略過/指令內容 (前 2000 行) ===\n\n")
        for l in self.skipped_lines[:2000]: self.log_text.insert(tk.END, l+"\n")
        self.notebook.select(self.log_text)

    def on_closing(self):
        self.should_stop = True
        self.root.destroy()
        
    def on_resize(self, event): pass