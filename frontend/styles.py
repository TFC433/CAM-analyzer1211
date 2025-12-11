import math
import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttk
import darkdetect

class ThemeManager:
    def __init__(self, root):
        self.root = root
        
        self.is_dark_mode = darkdetect.isDark()
        self.style = ttk.Style(theme='darkly' if self.is_dark_mode else 'litera')

        self.scale_factor = self._calculate_scale_factor()
        self.fonts = self._define_fonts()
        
        self.apply_styles()

    def _calculate_scale_factor(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        screen_dpi = self.root.winfo_fpixels('1i')
        
        base_width, base_height, base_dpi = 1920, 1080, 96
        scale = math.sqrt((screen_width / base_width) ** 2 + (screen_height / base_height) ** 2) * (screen_dpi / base_dpi)
        return max(0.8, min(scale, 2.5))

    def _define_fonts(self):
        base_size = 12
        scaled_size = int(base_size * self.scale_factor)
        scaled_size = max(8, min(scaled_size, 24))
        
        return {
            'main': ('Microsoft JhengHei', scaled_size),
            'label': ('Microsoft JhengHei', scaled_size + 2),
            'button': ('Microsoft JhengHei', scaled_size + 4, 'bold'),
            'tab': ('Microsoft JhengHei', scaled_size + 1, 'bold'),
            'header': ('Microsoft JhengHei', int(16 * self.scale_factor), 'bold'),
            'copyright': ('Microsoft JhengHei', int(9 * self.scale_factor), 'italic'),
            'axis': ('Microsoft JhengHei', int(11 * self.scale_factor), 'bold')
        }

    def apply_styles(self):
        for style_name in ['Success', 'Primary', 'Warning', 'Accent', 'Danger']:
            self.style.configure(f'Custom.{style_name}.TButton', font=self.fonts['button'])
        
        self.style.configure('Custom.TMenubutton', font=self.fonts['tab'])
        self.style.configure('TNotebook.Tab', font=self.fonts['tab'])
        
        # [新增] 信號燈樣式 (使用 Toolbutton 或 Label 模擬)
        # Active: 綠底白字
        self.style.configure('AxisActive.TLabel', background='#28a745', foreground='white', 
                             font=self.fonts['axis'], padding=5, anchor='center')
        # Inactive: 灰底灰字
        self.style.configure('AxisInactive.TLabel', background='#e9ecef', foreground='#adb5bd', 
                             font=self.fonts['axis'], padding=5, anchor='center')
        
        # 暗黑模式修正
        if self.is_dark_mode:
             self.style.configure('AxisInactive.TLabel', background='#343a40', foreground='#6c757d')

        bg_color = '#1C2526' if self.is_dark_mode else '#DDE1E4'
        self.root.config(background=bg_color)

    def toggle_theme(self, mode=None):
        if mode == 'system':
            self.is_dark_mode = darkdetect.isDark()
        elif mode == 'dark':
            self.is_dark_mode = True
        elif mode == 'light':
            self.is_dark_mode = False
        else:
            self.is_dark_mode = not self.is_dark_mode

        theme_name = 'darkly' if self.is_dark_mode else 'litera'
        self.style.theme_use(theme_name)
        self.apply_styles()
        return self.is_dark_mode

    def get_color_palette(self):
        if self.is_dark_mode:
            return {
                'bg': '#3A3A3A', 'fg': '#FFFFFF', 'bar': '#FFD60A', 'grid': '#999999',
                'star': '#FFD60A', 'line': '#FFD60A', 'inactive': '#666666'
            }
        else:
            return {
                'bg': '#DDE1E4', 'fg': '#000000', 'bar': '#0000FF', 'grid': '#B0B0B0',
                'star': '#FF6F61', 'line': '#0000FF', 'inactive': '#999999'
            }