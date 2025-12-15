# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
# Project:      CAM Analyzer
# File:         app_ui.py
# Author:       TFC-CRM
# Created:      2025-12-12
# Copyright:    (c) 2025 TFC-CRM. All rights reserved.
# License:      Proprietary / Confidential
# Description:  Main UI Controller using Tkinter & ttkbootstrap.
#               v10.10: Rectangular Logo & Resolution Based Scaling (Standard).
# ------------------------------------------------------------------------------

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import ttkbootstrap as ttk
import os
import csv
import time
import threading
import queue
import numpy as np 
import platform
import sys
from PIL import Image, ImageTk, ImageDraw 

from backend import GCodeAnalyzer
from frontend.styles import ThemeManager
from frontend.charts import ChartManager

class CAMApp:
    def __init__(self, root, project_root="."):
        self.root = root
        self.project_root = project_root
        
        self.APP_NAME = "CAM Analyzer"
        self.APP_VERSION = "v10.10"
        self.COPYRIGHT = "Copyright © 2025 TFC-CRM. All rights reserved."
        
        self.root.title(f"{self.APP_NAME} {self.APP_VERSION}")
        self.root.minsize(1280, 800)
        
        self.tm = ThemeManager(root)
        self.colors = self.tm.get_color_palette() 
        
        self.engine = GCodeAnalyzer()
        self.msg_queue = queue.Queue()
        
        # State Variables
        self.file_path = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.status_var = tk.StringVar(value="Ready")
        self.after_id = None 
        
        # Data
        self.raw_data = None 
        self.detected_axes = []
        self.top_10_stats = []
        self.top_3_stats = []
        self.current_calc_mode = "" 
        
        # Bins
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

    def _load_image(self, filename, box_size, radius=0):
        """
        讀取圖片，等比例縮放至 box_size 內並置中，最後裁切圓角。
        radius=0 代表不裁切圓角 (矩形顯示)
        """
        try:
            img_path = os.path.join(self.project_root, filename)
            if not os.path.exists(img_path):
                return None
            
            # 1. 根據螢幕 DPI 縮放計算目標像素
            scale = self.tm.scale_factor
            box_w = int(box_size[0] * scale)
            box_h = int(box_size[1] * scale)
            r_val = int(radius * scale)
            
            # 2. 開啟圖片
            im = Image.open(img_path)
            
            # 4倍超取樣 (Super-Sampling) 以抗鋸齒
            ss = 4 
            ss_box_w = box_w * ss
            ss_box_h = box_h * ss
            ss_radius = r_val * ss
            
            # 3. 等比例縮放原圖
            im_ratio = im.copy()
            im_ratio.thumbnail((ss_box_w, ss_box_h), Image.Resampling.LANCZOS)
            new_w, new_h = im_ratio.size
            
            # 4. 建立透明背景 (全尺寸)
            bg = Image.new('RGBA', (ss_box_w, ss_box_h), (0, 0, 0, 0))
            
            # 5. 處理圓角 (Mask)
            if ss_radius > 0:
                mask = Image.new('L', (new_w, new_h), 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle([(0, 0), (new_w, new_h)], radius=ss_radius, fill=255)
                
                im_rounded = Image.new('RGBA', (new_w, new_h), (0, 0, 0, 0))
                im_rounded.paste(im_ratio, (0, 0), mask=mask)
                im_ratio = im_rounded
            
            # 6. 置中貼上
            offset_x = (ss_box_w - new_w) // 2
            offset_y = (ss_box_h - new_h) // 2
            bg.paste(im_ratio, (offset_x, offset_y))
            
            # 7. 最終縮小
            final_img = bg.resize((box_w, box_h), Image.Resampling.LANCZOS)
            
            return ImageTk.PhotoImage(final_img)
            
        except Exception:
            return None

    def _init_layout(self):
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # === Left Sidebar ===
        self.sidebar = ttk.Frame(self.root, style='Sidebar.TFrame', padding=20, width=250)
        self.sidebar.grid(row=0, column=0, sticky='ns')
        self.sidebar.grid_propagate(False)

        # [Logo Area]
        # [修改] 上方間距減為 20px (緊湊佈局)
        logo_frame = ttk.Frame(self.sidebar, style='Sidebar.TFrame')
        logo_frame.pack(pady=(20, 15), anchor='center') 
        
        # [修改] 改為長方形顯示，取消圓角
        # 原尺寸 (140, 140), radius=70 -> 改為 (210, 110), radius=0
        self.logo_img = self._load_image("logo.png", (210, 110), radius=0)
        
        if self.logo_img:
            logo_lbl = ttk.Label(logo_frame, image=self.logo_img, background=self.colors['bg_darker'])
            logo_lbl.pack(side='top')
        else:
            s = self.tm.scale_factor
            size = int(140 * s)
            self.logo_canvas = tk.Canvas(logo_frame, width=size, height=size, 
                                       bg=self.colors['bg_darker'], highlightthickness=0)
            self.logo_canvas.pack(side='top')
            self.logo_canvas.create_oval(0, 0, size, size, fill=self.colors['accent'], outline="")
            self.logo_canvas.create_text(size//2, size//2, text="C", fill="white", font=("Arial", int(50*s), "bold"))
        
        # Operations
        ttk.Label(self.sidebar, text="操作功能", style='Inverse.TLabel', font=self.tm.fonts['h2']).pack(anchor='w', pady=(0, 10))
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

        # Navigation
        ttk.Label(self.sidebar, text="視圖切換", style='Inverse.TLabel', font=self.tm.fonts['h2']).pack(anchor='w', pady=(0, 10))
        self.nav_btns = {}
        nav_items = [('dashboard', '📊', '儀表板'), ('detail', '📝', '詳細數據'), ('log', '📜', '執行紀錄')]
        for key, icon, label in nav_items:
            btn = ttk.Button(self.sidebar, text=f"{icon}  {label}", style='Nav.TButton',
                             command=lambda k=key: self.switch_view(k))
            btn.pack(fill='x', pady=2)
            self.nav_btns[key] = btn

        self.btn_about = ttk.Button(self.sidebar, text="ℹ️  關於本軟體", style='Nav.TButton',
                                    command=lambda: self.switch_view('about'))
        self.btn_about.pack(side='bottom', fill='x', pady=10)
        self.nav_btns['about'] = self.btn_about

        # === Right Main Area ===
        self.main_area = ttk.Frame(self.root)
        self.main_area.grid(row=0, column=1, sticky='nsew')
        
        # Header
        self.header = ttk.Frame(self.main_area, padding=0, style='Card.TFrame') 
        self.header.pack(fill='x')
        
        header_inner = ttk.Frame(self.header, padding=(20, 15), style='Card.TFrame')
        header_inner.pack(fill='x')

        ttk.Label(header_inner, text="當前檔案", style='CardLabel.TLabel').pack(anchor='w')
        self.lbl_filename = ttk.Label(header_inner, text="尚未載入", style='Header.TLabel')
        self.lbl_filename.pack(anchor='w', pady=(0, 5))
        
        self.axis_row = ttk.Frame(header_inner, style='Card.TFrame')
        self.axis_row.pack(anchor='w')
        ttk.Label(self.axis_row, text="偵測軸向: ", style='CardLabel.TLabel').pack(side='left')
        
        self.axis_indicators = {}
        for ax in ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'K']:
            lbl = ttk.Label(self.axis_row, text=ax, style='AxisInactive.TLabel', width=3, anchor='center')
            self.axis_indicators[ax] = lbl
        
        for ax in ['X', 'Y', 'Z', 'A', 'B', 'C']:
            self.axis_indicators[ax].pack(side='left', padx=2)

        self.lbl_calc_mode = ttk.Label(self.axis_row, text="", style='Inverse.TLabel', font=self.tm.fonts['ui_bold'])
        self.lbl_calc_mode.pack(side='left', padx=(20, 0))

        self.lbl_status = ttk.Label(header_inner, textvariable=self.status_var, style='Status.TLabel')
        self.lbl_status.pack(anchor='w', pady=(5, 0))

        self.progress = ttk.Progressbar(self.header, mode='determinate', bootstyle='success-striped', style='Thick.Horizontal.TProgressbar')
        self.progress.pack(fill='x', side='bottom')
        self.tm.style.configure('Thick.Horizontal.TProgressbar', thickness=10)

        # Content
        self.content = ttk.Frame(self.main_area, padding=20)
        self.content.pack(fill='both', expand=True)
        self.view_container = ttk.Frame(self.content)
        self.view_container.pack(fill='both', expand=True)
        
        self._init_dashboard()
        self._init_detail_text()
        self._init_log()
        self._init_about() 
        
        self.switch_view('dashboard')

    def _init_dashboard(self):
        self.view_dash = ttk.Frame(self.view_container)
        
        row1 = ttk.Frame(self.view_dash)
        row1.pack(fill='x', pady=(0, 10))
        for i in range(5): row1.grid_columnconfigure(i, weight=1)
        
        self.kpi_vals = {}
        kpi_defs_r1 = [
            (0, 'lines', '總解析單節'), (1, 'total', '總行程'), 
            (2, 'g01', 'G01 切削距離'), (3, 'g00', 'G00 空跑距離'), (4, 'time', '預估切削時間')
        ]
        
        for col_idx, key, title in kpi_defs_r1:
            card = ttk.Frame(row1, style='Card.TFrame', padding=15)
            card.grid(row=0, column=col_idx, sticky='nsew', padx=(0 if col_idx==0 else 10, 0))
            ttk.Label(card, text=title, style='CardLabel.TLabel').pack(anchor='w')
            val = ttk.Label(card, text="--", style='CardValue.TLabel')
            val.pack(anchor='w', pady=(5, 0))
            self.kpi_vals[key] = val

        row2 = ttk.Frame(self.view_dash)
        row2.pack(fill='x', pady=(0, 20))
        for i in range(4): row2.grid_columnconfigure(i, weight=1)

        kpi_defs_r2 = [
            (0, 'bpt', '最適合 BPT (ms)'), (1, 'top1', 'Top 1 分佈'),
            (2, 'top2', 'Top 2 分佈'), (3, 'top3', 'Top 3 分佈')
        ]
        
        for col_idx, key, title in kpi_defs_r2:
            card = ttk.Frame(row2, style='Card.TFrame', padding=15)
            card.grid(row=0, column=col_idx, sticky='nsew', padx=(0 if col_idx==0 else 10, 0))
            ttk.Label(card, text=title, style='CardLabel.TLabel').pack(anchor='w')
            val = ttk.Label(card, text="--", style='CardValue.TLabel', font=self.tm.fonts['h2'])
            val.pack(anchor='w', pady=(5, 0))
            self.kpi_vals[key] = val

        chart_area = ttk.Frame(self.view_dash, style='Card.TFrame', padding=5)
        chart_area.pack(fill='both', expand=True)
        self.chart_hist = ChartManager(chart_area, self.tm)

    def _init_detail_text(self):
        self.view_detail = ttk.Frame(self.view_container)
        
        ctrl = ttk.Frame(self.view_detail)
        ctrl.pack(fill='x', pady=(0, 10))
        ttk.Label(ctrl, text="顯示範圍:", font=self.tm.fonts['ui']).pack(side='left')
        
        self.combo_limit = ttk.Combobox(ctrl, values=["前 1000 筆", "前 5000 筆", "前 10000 筆"], width=15, state='readonly')
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

    def _init_about(self):
        self.view_about = ttk.Frame(self.view_container)
        center_frame = ttk.Frame(self.view_about, style='Card.TFrame', padding=40)
        center_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        # About Logo: 100x100, radius 20
        self.logo_img_big = self._load_image("logo.png", (100, 100), radius=20)
        
        if self.logo_img_big:
            logo_lbl_big = ttk.Label(center_frame, image=self.logo_img_big, background=self.colors['bg_card'])
            logo_lbl_big.pack(pady=(0, 20))
        else:
            s = self.tm.scale_factor
            size = int(100 * s)
            canvas = tk.Canvas(center_frame, width=size, height=size, bg=self.colors['accent'], highlightthickness=0)
            canvas.pack(pady=(0, 20))
            canvas.create_text(size//2, size//2, text="C", fill="white", font=("Arial", int(50*s), "bold"))
        
        ttk.Label(center_frame, text=self.APP_NAME, font=self.tm.fonts['h1'], style='CardValue.TLabel').pack()
        ttk.Label(center_frame, text=self.APP_VERSION, font=self.tm.fonts['h2'], style='CardLabel.TLabel').pack(pady=(5, 30))
        
        ttk.Separator(center_frame).pack(fill='x', pady=20)
        
        sys_info = f"Python: {platform.python_version()}  |  Numpy: {np.__version__}"
        os_info = f"OS: {platform.system()} {platform.release()}"
        ttk.Label(center_frame, text=sys_info, style='CardLabel.TLabel').pack()
        ttk.Label(center_frame, text=os_info, style='CardLabel.TLabel').pack(pady=(5, 20))
        
        ttk.Label(center_frame, text=self.COPYRIGHT, style='CardLabel.TLabel', font=self.tm.fonts['ui']).pack(side='bottom')

    def switch_view(self, view):
        self.view_dash.pack_forget()
        self.view_detail.pack_forget()
        self.view_log.pack_forget()
        self.view_about.pack_forget()
        for k, btn in self.nav_btns.items():
            btn.configure(style=('NavActive.TButton' if k == view else 'Nav.TButton'))
        if view == 'dashboard': self.view_dash.pack(fill='both', expand=True)
        elif view == 'detail': self.view_detail.pack(fill='both', expand=True)
        elif view == 'log': self.view_log.pack(fill='both', expand=True)
        elif view == 'about': self.view_about.pack(fill='both', expand=True)

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("CAM Files", "*.txt *.nc *.ncd *.tap"), ("All", "*.*")])
        if path:
            self.file_path = path
            self.lbl_filename.config(text=os.path.basename(path))
            self.btn_analyze.config(state='normal')
            self.status_var.set("Ready")
            
            for k in self.kpi_vals: self.kpi_vals[k].config(text="--")
            for lbl in self.axis_indicators.values(): lbl.configure(style='AxisInactive.TLabel')
            self.lbl_calc_mode.config(text="")
            self.txt_detail.delete(1.0, tk.END)
            self.txt_log.delete(1.0, tk.END)
            self.raw_data = None 

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
        self.txt_log.insert(tk.END, "Starting High-Performance Analysis Engine (Numpy Float64)...\n")
        
        thread = threading.Thread(target=self.run_analysis)
        thread.daemon = True
        thread.start()

    def run_analysis(self):
        try:
            content = ""
            for chunk in self.engine.read_file_generator(self.file_path, progress_callback=self.thread_callback):
                content += chunk
                if self.should_stop: break
            
            if self.should_stop: raise InterruptedError("Stopped by user")

            data_dict = self.engine.parse_and_calculate(content, self.thread_callback)
            if not data_dict: raise InterruptedError("Stopped")
            
            dists, g01, time_m, top10, top3, bpt = self.engine.calculate_metrics_and_stats(
                data_dict, self.bins, self.fixed_intervals, self.thread_callback
            )

            result_payload = {
                "raw_data": data_dict, 
                "top10": top10,
                "top3": top3,
                "bpt": bpt,
                "hist_dists": dists 
            }
            self.msg_queue.put(("DONE", result_payload))

        except InterruptedError:
            self.msg_queue.put(("STATUS", "Cancelled"))
        except Exception as e:
            self.msg_queue.put(("ERROR", str(e)))
        finally:
            self.msg_queue.put(("FINISH", None))

    def thread_callback(self, pct, msg):
        self.msg_queue.put(("PROGRESS", (pct, msg)))
        while self.is_paused:
            self.msg_queue.put(("STATUS", "Paused..."))
            time.sleep(0.2)
            if self.should_stop: return True
        return self.should_stop

    def check_queue(self):
        if self.should_stop: return
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
                    messagebox.showerror("Error", data)
                elif msg_type == "FINISH":
                    self.is_running = False
                    self.btn_analyze.config(state='normal')
                    self.btn_open.config(state='normal')
                    self.btn_pause.config(state='disabled')
                    self.btn_stop.config(state='disabled')
                    self.progress['value'] = 0
                    if "Error" not in self.status_var.get():
                        self.status_var.set("Ready")
        except queue.Empty:
            pass
        if not self.should_stop:
            self.after_id = self.root.after(100, self.check_queue)

    def update_results(self, payload):
        self.raw_data = payload["raw_data"]
        self.detected_axes = self.raw_data["axes"]
        self.top_10_stats = payload["top10"]
        self.top_3_stats = payload["top3"]
        self.current_calc_mode = self.raw_data["calc_mode"]
        
        for lbl in self.axis_indicators.values():
            lbl.pack_forget()
            lbl.configure(style='AxisInactive.TLabel')
            
        visible_axes = ['X', 'Y', 'Z', 'A', 'B', 'C']
        is_tcp = self.raw_data["is_tcp"]
        if is_tcp:
            visible_axes.extend(['I', 'J', 'K'])
            
        for ax in visible_axes:
            self.axis_indicators[ax].pack(side='left', padx=2)
            if ax in self.detected_axes:
                self.axis_indicators[ax].configure(style='AxisActive.TLabel')

        self.lbl_calc_mode.pack_forget()
        self.lbl_calc_mode.pack(side='left', padx=(20, 0))
        self.lbl_calc_mode.config(text=f"[ {self.current_calc_mode} ]")
        self.lbl_calc_mode.configure(foreground=self.colors['accent'] if is_tcp else self.colors['fg_main'])
            
        total_lines = len(self.raw_data['matrix']) - 1
        self.kpi_vals['lines'].config(text=f"{total_lines:,}")
        
        total = self.raw_data["g00_dist"] + self.raw_data["g01_dist"]
        g01 = self.raw_data["g01_dist"]
        g00 = self.raw_data["g00_dist"]
        
        g01_pct = (g01 / total * 100) if total > 0 else 0
        g00_pct = (g00 / total * 100) if total > 0 else 0
        
        self.kpi_vals['total'].config(text=f"{total:,.2f} mm")
        self.kpi_vals['g01'].config(text=f"{g01:,.2f} mm ({g01_pct:.1f}%)")
        self.kpi_vals['g00'].config(text=f"{g00:,.2f} mm ({g00_pct:.1f}%)")
        
        total_seconds = int(self.raw_data["time"] * 60)
        h, m, s = total_seconds // 3600, (total_seconds % 3600) // 60, total_seconds % 60
        self.kpi_vals['time'].config(text=f"{h:02d}:{m:02d}:{s:02d}")
        
        if payload['bpt']:
            self.kpi_vals['bpt'].config(text=f"{payload['bpt']['range_str']}")
        else:
            self.kpi_vals['bpt'].config(text="N/A")

        for i in range(3):
            key = f'top{i+1}'
            if i < len(self.top_3_stats):
                item = self.top_3_stats[i]
                self.kpi_vals[key].config(text=f"{item['label']} ({item['pct']:.1f}%)")
            else:
                self.kpi_vals[key].config(text="--")

        self.txt_log.insert(tk.END, f"=== Analysis Mode: {self.current_calc_mode} ===\n")
        self.txt_log.insert(tk.END, f"=== Total Lines: {total_lines} ===\n")
        MAX_LOG = 2000
        skipped = self.raw_data["skipped"]
        for i, l in enumerate(skipped):
            if i < MAX_LOG: self.txt_log.insert(tk.END, l + "\n")
            else: 
                self.txt_log.insert(tk.END, f"... ({len(skipped)-MAX_LOG} more lines hidden) ...\n")
                break
        
        self.refresh_detail_view()
        self.chart_hist.plot_histogram(payload["hist_dists"], self.bins, self.fixed_intervals)
        
        self.status_var.set("Analysis Complete")
        self.switch_view('dashboard')

    def refresh_detail_view(self, event=None):
        if self.raw_data is None: return
        self.txt_detail.delete(1.0, tk.END)
        selection = self.combo_limit.get()
        if "1000" in selection: limit = 1000
        elif "5000" in selection: limit = 5000
        elif "10000" in selection: limit = 10000
        else: limit = 1000
        matrix = self.raw_data["matrix"] 
        dists = self.raw_data["dists"]   
        modes = self.raw_data["modes"]
        feeds = self.raw_data["feeds"]
        total_records = len(dists)
        limit = min(limit, total_records)
        self.txt_detail.insert(tk.END, f"=== Displaying First {limit} Records (Total {total_records}) ===\n")
        self.txt_detail.insert(tk.END, "="*90 + "\n\n")
        all_axes_priority = ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'K']
        active_cols = [ax for ax in all_axes_priority if ax in self.detected_axes]
        s_headers = [f"Start_{ax}" for ax in active_cols]
        e_headers = [f"End_{ax}" for ax in active_cols]
        is_tcp = self.raw_data["is_tcp"]
        if is_tcp: dist_header = f"{'XYZ_Dist':<8} | {'Rot_Deg':<7} | {'Total_Dist':<10}"
        else: dist_header = f"{'Dist':<8}"
        header_str = f"{'Line':<6} | {' '.join(s_headers):<30} | {' '.join(e_headers):<30} | {dist_header} | {'Feed':<6} | {'Info'}\n"
        self.txt_detail.insert(tk.END, header_str)
        self.txt_detail.insert(tk.END, "-"*len(header_str) + "\n")
        axis_map_full = {ax: i for i, ax in enumerate(all_axes_priority)}
        col_indices = [axis_map_full[ax] for ax in active_cols]
        buffer = ""
        for i in range(limit):
            line_num = self.raw_data["lines"][i+1] 
            row_s = matrix[i]
            row_e = matrix[i+1]
            s_str = " ".join([f"{row_s[c]:.1f}" for c in col_indices])
            e_str = " ".join([f"{row_e[c]:.1f}" for c in col_indices])
            d_total = dists[i]
            if is_tcp:
                d_xyz = self.raw_data["dists_xyz"][i]
                d_rot = self.raw_data["rots_deg"][i]
                d_str = f"{d_xyz:<8.3f} | {d_rot:<7.1f} | {d_total:<10.3f}"
            else:
                d_str = f"{d_total:<8.3f}"
            mode_val = modes[i+1]
            feed_val = feeds[i+1]
            mode_str = 'G00' if mode_val == 0.0 else 'G01'
            info = f"{mode_str}"
            if is_tcp and mode_val == 1.0: info += " (TCP)"
            buffer += f"{line_num:<6} | {s_str:<30} | {e_str:<30} | {d_str} | {int(feed_val):<6} | {info}\n"
            if i % 500 == 0:
                self.txt_detail.insert(tk.END, buffer)
                buffer = ""
                self.root.update_idletasks() 
        if buffer: self.txt_detail.insert(tk.END, buffer)

    def export_csv(self):
        if self.raw_data is None: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        def _export():
            try:
                self.msg_queue.put(("STATUS", "Exporting CSV..."))
                matrix = self.raw_data["matrix"]
                dists = self.raw_data["dists"]
                lines = self.raw_data["lines"]
                modes = self.raw_data["modes"]
                feeds = self.raw_data["feeds"]
                count = len(dists)
                all_axes_priority = ['X', 'Y', 'Z', 'A', 'B', 'C', 'I', 'J', 'K']
                active_cols = [ax for ax in all_axes_priority if ax in self.detected_axes]
                col_indices = [{ax: i for i, ax in enumerate(all_axes_priority)}[ax] for ax in active_cols]
                with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    s_h = [f"Start_{ax}" for ax in active_cols]
                    e_h = [f"End_{ax}" for ax in active_cols]
                    is_tcp = self.raw_data["is_tcp"]
                    d_h = ["XYZ_Dist", "Rot_Deg", "Total_Dist"] if is_tcp else ["Dist"]
                    writer.writerow(["Line", "Mode"] + s_h + e_h + d_h + ["Feed", "Info"])
                    rows = []
                    BATCH = 5000
                    for i in range(count):
                        l_num = lines[i+1]
                        row_s = matrix[i]
                        row_e = matrix[i+1]
                        s_vals = [row_s[c] for c in col_indices]
                        e_vals = [row_e[c] for c in col_indices]
                        if is_tcp:
                            d_vals = [self.raw_data["dists_xyz"][i], self.raw_data["rots_deg"][i], dists[i]]
                        else:
                            d_vals = [dists[i]]
                        mode_val = modes[i+1]
                        feed_val = feeds[i+1]
                        mode_str = 'G00' if mode_val == 0.0 else 'G01'
                        rows.append([l_num, self.current_calc_mode] + s_vals + e_vals + d_vals + [feed_val, mode_str])
                        if len(rows) >= BATCH:
                            writer.writerows(rows)
                            rows = []
                    if rows: writer.writerows(rows)
                self.msg_queue.put(("STATUS", "Export Complete"))
                messagebox.showinfo("Success", "Export Complete")
            except Exception as e:
                messagebox.showerror("Failed", str(e))
        threading.Thread(target=_export).start()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.btn_pause.config(text="繼續" if self.is_paused else "暫停")

    def stop_analysis(self):
        self.should_stop = True

    def on_closing(self):
        self.should_stop = True
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.root.destroy()
    def on_resize(self, event): pass