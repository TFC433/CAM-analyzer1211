import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np

class ChartManager:
    def __init__(self, parent_frame, theme_manager):
        self.parent = parent_frame
        self.tm = theme_manager
        
        # 設定 Matplotlib 字型 (容錯機制)
        font_list = [self.tm.font_family, 'Microsoft JhengHei', 'SimHei', 'Arial', 'sans-serif']
        plt.rcParams['font.sans-serif'] = font_list
        plt.rcParams['axes.unicode_minus'] = False
        
        self.colors = self.tm.get_color_palette()
        
        # 初始化圖表
        self.fig_width = 8
        self.fig_height = 5
        self.figure, self.ax = plt.subplots(figsize=(self.fig_width, self.fig_height), dpi=96)
        
        # 設定深色背景
        self.figure.patch.set_facecolor(self.colors['bg_card'])
        self.ax.set_facecolor(self.colors['bg_card'])
        
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)
        
        self.bars = None
        self.hist_data = None
        self.last_plot_args = None
        self.current_scale_hist = 1.0
        self.tooltip = None # 懸停提示框

    def update_size(self, width_inch, height_inch):
        self.figure.set_size_inches(width_inch, height_inch)
        self.canvas.draw()

    def on_scroll(self, event):
        if not self.last_plot_args: return
        if event.button == 'up':
            self.current_scale_hist = min(1.5, self.current_scale_hist * 1.1)
        elif event.button == 'down':
            self.current_scale_hist = max(0.5, self.current_scale_hist * 0.9)
        
        if self.last_plot_args:
            self.plot_histogram(*self.last_plot_args)

    def plot_histogram(self, distances, bins, fixed_intervals):
        # 儲存參數供縮放使用
        self.last_plot_args = (distances, bins, fixed_intervals)
        
        self.ax.clear()
        self.ax.set_facecolor(self.colors['bg_card'])
        
        c_fg = self.colors['fg_main']
        c_grid = self.colors['grid']
        c_bar = self.colors['accent']
        c_star = self.colors['star']
        
        # [修正] 支援 Numpy Array 的判斷方式
        if distances is None or len(distances) == 0:
            self.ax.text(0.5, 0.5, '無數據', ha='center', va='center', color=c_fg)
            self.canvas.draw()
            return

        # Numpy histogram 運算極快，即便是百萬筆資料也是瞬間完成
        hist, _ = np.histogram(distances, bins=bins)
        self.hist_data = hist
        
        labels = [
            f"{s:.3f}<=D<{e:.3f}" if e != float('inf') else f"{s:.3f}<D"
            for s, e in fixed_intervals
        ]
        
        # 計算 Top 10
        total_segments = len(distances)
        percentages = [count / total_segments * 100 if total_segments > 0 else 0 for count in hist]
        percentages_with_index = [(pct, idx) for idx, pct in enumerate(percentages)]
        top_10 = sorted(percentages_with_index, key=lambda x: x[0], reverse=True)[:10]
        top_10_indices = [idx for _, idx in top_10]
        top_10_ranks = {idx: rank + 1 for rank, idx in enumerate(top_10_indices)}
        max_idx = top_10_indices[0] if top_10_indices else 0

        y_pos = np.arange(len(labels))
        
        # 繪製 Bar
        self.bars = self.ax.barh(y_pos, hist * self.current_scale_hist, align='center', 
                                color=c_bar, edgecolor=self.colors['bg_card'], alpha=0.8, height=0.7)
        
        self.ax.set_yticks(y_pos)
        self.ax.set_yticklabels(labels, fontsize=10, color=c_fg)
        self.ax.set_xlabel('單節數量 (Count)', fontsize=10, color=c_fg)
        
        self.ax.tick_params(axis='x', colors=c_fg)
        self.ax.tick_params(axis='y', colors=c_fg)
        
        # 邊框與格線
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['bottom'].set_color(c_grid)
        self.ax.spines['left'].set_color(c_grid)
        self.ax.grid(True, axis='x', alpha=0.2, linestyle='--', color=c_grid)

        # 設定 X 軸範圍 (留空間給標籤)
        max_val = max(hist) if len(hist) > 0 and max(hist) > 0 else 1
        x_max = max_val * (1.4 * self.current_scale_hist)
        self.ax.set_xlim(0, x_max)

        # 繪製 Top 10 標籤與虛線
        for i, bar in enumerate(self.bars):
            width = bar.get_width()
            percentage = percentages[i]
            text = f'{percentage:.1f}%'
            if i == max_idx:
                text += ' ★'
            
            # 文字位置
            text_x = width + (0.02 * x_max)
            bar_y = bar.get_y() + bar.get_height() / 2
            
            # 顯示百分比文字
            self.ax.text(text_x, bar_y, text, 
                        ha='left', va='center', fontsize=9, 
                        color=c_star if i == max_idx else c_fg, weight='bold')
            
            # 如果是 Top 10，畫虛線與排名
            if i in top_10_indices:
                text_len_est = len(text) * (x_max * 0.025) 
                line_start = text_x + text_len_est
                
                self.ax.plot([line_start, x_max], [bar_y, bar_y], 
                            color=c_star, linestyle='--', linewidth=0.8, alpha=0.5)
                
                rank = top_10_ranks[i]
                self.ax.text(x_max, bar_y, f'Top{rank}', 
                            ha='right', va='center', fontsize=9, 
                            color=c_star, weight='bold')

        self.figure.tight_layout()
        self.canvas.draw()

    def plot_f_curve(self, x_values, f_values, t_value, max_dist, hist_data, fixed_intervals):
        # 暫時保留此函式，雖然 UI 目前沒呼叫
        self.ax.clear()
        self.ax.set_facecolor(self.colors['bg_card'])
        
        c_fg = self.colors['fg_main']
        c_grid = self.colors['grid']
        c_line = self.colors['line']
        
        if x_values is None or len(x_values) == 0:
            self.ax.text(0.5, 0.5, '無效數據', ha='center', color=c_fg)
            self.canvas.draw()
            return

        self.ax.plot(x_values, f_values, color=c_line, linewidth=2)
        
        self.ax.set_xlabel('Length (mm)', color=c_fg)
        self.ax.set_ylabel('Feed (mm/min)', color=c_fg)
        
        self.ax.tick_params(axis='both', colors=c_fg)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['bottom'].set_color(c_grid)
        self.ax.spines['left'].set_color(c_grid)
        self.ax.grid(True, alpha=0.2, linestyle='--', color=c_grid)
        
        self.figure.tight_layout()
        self.canvas.draw()

    def on_hover(self, event):
        if event.inaxes != self.ax or self.bars is None:
            if self.tooltip: self.tooltip.destroy()
            return

        for i, bar in enumerate(self.bars):
            if bar.contains(event)[0]:
                count = self.hist_data[i]
                self._show_tooltip(event, f"數量: {count} 筆")
                return
        
        if self.tooltip:
            self.tooltip.destroy()

    def _show_tooltip(self, event, text):
        if self.tooltip: self.tooltip.destroy()
        x, y = event.guiEvent.x_root + 15, event.guiEvent.y_root + 10
        self.tooltip = tk.Toplevel(self.parent)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tooltip, text=text, bg="#333", fg="#FFF", padx=5, pady=2).pack()