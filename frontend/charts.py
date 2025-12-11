import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
import platform

class ChartManager:
    def __init__(self, parent_frame, theme_manager):
        self.parent = parent_frame
        self.tm = theme_manager
        self.font_size = self.tm.fonts['main'][1]
        
        # --- [字型修復] ---
        system_name = platform.system()
        if system_name == "Windows":
            font_list = ['Microsoft JhengHei', 'SimHei', 'Arial']
        elif system_name == "Darwin":
            font_list = ['Arial Unicode MS', 'PingFang TC']
        else:
            font_list = ['WenQuanYi Micro Hei', 'Droid Sans Fallback']
            
        plt.rcParams['font.sans-serif'] = font_list + plt.rcParams['font.sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
        # -----------------

        self.current_scale_hist = 1.0
        
        self.fig_width = 8
        self.fig_height = 5
        self.figure, self.ax = plt.subplots(figsize=(self.fig_width, self.fig_height), dpi=80)
        
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.parent, pack_toolbar=False)
        self.toolbar.pack(pady=5, fill="x")
        self._customize_toolbar()
        
        self.tooltip = None
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)
        
        self.bars = None
        self.hist_data = None
        self.last_plot_args = None 

    def _customize_toolbar(self):
        for tool_name in ['Back', 'Forward', 'Subplots']:
            self.toolbar.toolitems = [t for t in self.toolbar.toolitems if t[0] != tool_name]
        self.toolbar.update()

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
        self.last_plot_args = (distances, bins, fixed_intervals)
        
        self.ax.clear()
        colors = self.tm.get_color_palette()
        self.figure.set_facecolor(colors['bg'])
        self.ax.set_facecolor(colors['bg'])
        
        if not distances:
            self.ax.text(0.5, 0.5, '無數據', ha='center', va='center', color=colors['fg'])
            self.canvas.draw()
            return

        hist, _ = np.histogram(distances, bins=bins)
        self.hist_data = hist
        
        labels = [
            f"{s:.3f}<=間距<{e:.3f}" if e != float('inf') else f"{s:.3f}<間距"
            for s, e in fixed_intervals
        ]
        
        counts = hist
        
        total_segments = len(distances)
        percentages = [count / total_segments * 100 if total_segments > 0 else 0 for count in counts]
        percentages_with_index = [(percent, idx) for idx, percent in enumerate(percentages)]
        top_10 = sorted(percentages_with_index, key=lambda x: x[0], reverse=True)[:10]
        top_10_indices = [idx for _, idx in top_10]
        top_10_ranks = {idx: rank + 1 for rank, idx in enumerate(top_10_indices)}
        max_idx = top_10_indices[0] if top_10_indices else 0

        y_pos = np.arange(len(labels))
        self.bars = self.ax.barh(y_pos, counts * self.current_scale_hist, align='center', 
                                color=colors['bar'], edgecolor=colors['inactive'], alpha=0.8, height=0.8)
        
        self.ax.set_yticks(y_pos)
        self.ax.set_yticklabels(labels, fontsize=self.font_size, color=colors['fg'])
        self.ax.set_xlabel('單節數', fontsize=self.font_size, color=colors['fg'])
        self.ax.set_title('G01 移動距離分佈', fontsize=self.font_size + 2, pad=15, color=colors['fg'])
        self.ax.grid(True, alpha=0.3, linestyle='--', color=colors['grid'])
        
        max_count = max(counts * self.current_scale_hist) if max(counts) > 0 else 1
        x_max = max_count * 1.4
        self.ax.set_xlim(0, x_max)

        for i, bar in enumerate(self.bars):
            width = bar.get_width()
            percentage = percentages[i]
            text = f'{percentage:.2f}%'
            if i == max_idx:
                text += ' ★'
            
            text_x = width + (0.02 * x_max)
            self.ax.text(text_x, bar.get_y() + bar.get_height()/2, 
                        text, ha='left', va='center', fontsize=self.font_size, 
                        color=colors['star'] if i == max_idx else colors['fg'], weight='bold')
            
            if i in top_10_indices:
                bar_y = bar.get_y() + bar.get_height() / 2
                text_len_est = len(text) * (x_max * 0.02) 
                line_start = text_x + text_len_est + (0.01 * x_max)
                
                self.ax.plot([line_start, x_max], [bar_y, bar_y], 
                            color=colors['star'], linestyle='--', linewidth=1, alpha=0.7)
                
                rank = top_10_ranks[i]
                self.ax.text(x_max, bar_y, f'Top{rank}', 
                            ha='right', va='center', fontsize=self.font_size, 
                            color=colors['star'], weight='bold')

        self.ax.tick_params(axis='x', colors=colors['fg'])
        self.figure.tight_layout()
        self.canvas.draw()

    def plot_f_curve(self, x_values, f_values, t_value, max_dist, hist_data, fixed_intervals):
        self.ax.clear()
        colors = self.tm.get_color_palette()
        self.figure.set_facecolor(colors['bg'])
        self.ax.set_facecolor(colors['bg'])

        if x_values is None:
            self.ax.text(0.5, 0.5, '無效的 L 或 T 值', ha='center', color=colors['fg'])
            self.canvas.draw()
            return

        if hist_data is not None and len(hist_data) > 0:
            max_idx = np.argmax(hist_data)
            max_interval = fixed_intervals[max_idx]
            start_x, end_x = max_interval
            if end_x == float('inf'): end_x = max_dist
            if end_x > max_dist: end_x = max_dist
            if start_x < 0.001: start_x = 0.001

            start_f = (start_x / t_value) * 60000
            end_f = (end_x / t_value) * 60000

            mask1 = (x_values < start_x)
            mask2 = (x_values >= start_x) & (x_values <= end_x)
            mask3 = (x_values > end_x)
            
            if np.any(mask1): self.ax.plot(x_values[mask1], f_values[mask1], color=colors['inactive'], linewidth=2)
            if np.any(mask2): self.ax.plot(x_values[mask2], f_values[mask2], color=colors['line'], linewidth=2)
            if np.any(mask3): self.ax.plot(x_values[mask3], f_values[mask3], color=colors['inactive'], linewidth=2)

            self.ax.axvline(x=start_x, color=colors['line'], linestyle='--', alpha=0.7)
            self.ax.axvline(x=end_x, color=colors['line'], linestyle='--', alpha=0.7)
            self.ax.axhline(y=start_f, color=colors['line'], linestyle='--', alpha=0.7)
            self.ax.axhline(y=end_f, color=colors['line'], linestyle='--', alpha=0.7)
            
            mid_x = (start_x + end_x) / 2
            mid_f = (mid_x / t_value) * 60000
            self.ax.text(mid_x, mid_f, '★', fontsize=self.font_size + 4, color=colors['star'], ha='center', va='bottom')

        else:
            self.ax.plot(x_values, f_values, color=colors['line'], linewidth=2)
        
        self.ax.set_xlabel('L (mm or deg)', fontsize=self.font_size, color=colors['fg'])
        self.ax.set_ylabel('F (mm/min)', fontsize=self.font_size, color=colors['fg'])
        self.ax.set_title('微小單節處理能力', fontsize=self.font_size + 2, pad=15, color=colors['fg'])
        self.ax.grid(True, alpha=0.3, linestyle='--', color=colors['grid'])
        self.ax.set_xlim(0.001, max_dist)
        self.ax.set_ylim(0, max(f_values) * 1.2 if len(f_values) > 0 else 1)
        self.ax.tick_params(axis='both', colors=colors['fg'])
        
        self.figure.tight_layout()
        self.canvas.draw()

    def on_hover(self, event):
        if event.inaxes != self.ax or self.bars is None:
            if self.tooltip: self.tooltip.destroy()
            return

        for i, bar in enumerate(self.bars):
            if bar.contains(event)[0]:
                count = self.hist_data[i]
                self._show_tooltip(event, f"單節數: {count}")
                return
        
        if self.tooltip: self.tooltip.destroy()

    def _show_tooltip(self, event, text):
        if self.tooltip: self.tooltip.destroy()
        x, y = event.guiEvent.x_root + 15, event.guiEvent.y_root + 10
        self.tooltip = tk.Toplevel(self.parent)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tooltip, text=text, bg="#333", fg="#FFF", padx=5, pady=2).pack()