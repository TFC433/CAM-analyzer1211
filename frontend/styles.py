# -*- coding: utf-8 -*-
import math
import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttk
import platform

class ThemeManager:
    def __init__(self, root):
        self.root = root
        
        # 強制使用暗黑主題
        self.style = ttk.Style(theme='darkly')
        self.is_dark_mode = True

        # [修改] 計算縮放比例
        self.scale_factor = self._calculate_scale_factor()
        self.font_family = self._get_system_font()
        self.fonts = self._define_fonts()
        
        self.apply_styles()

    def _calculate_scale_factor(self):
        """
        智慧縮放邏輯 v10.8:
        1. 基準寬度 1920px = 1.0x
        2. 限制最小值為 1.0 (只放大不縮小)，避免在高 DPI 筆電上字體過小。
        3. 限制最大值為 2.5 (避免在超寬螢幕過大)。
        """
        try:
            screen_width = self.root.winfo_screenwidth()
            base_width = 1920.0
            
            scale = screen_width / base_width
            
            # [關鍵修改] max(1.0, ...) 確保不會縮小
            final_scale = max(1.0, min(scale, 2.5))
            return final_scale
        except:
            return 1.0

    def _get_system_font(self):
        sys_name = platform.system()
        if sys_name == "Windows":
            return "Microsoft JhengHei" 
        elif sys_name == "Darwin":
            return "PingFang TC"
        else:
            return "WenQuanYi Micro Hei"

    def _define_fonts(self):
        # 根據縮放比例調整字體大小
        base = 10 
        s = lambda x: int(x * self.scale_factor)
        f = self.font_family
        
        return {
            'ui': (f, s(base)),              
            'ui_bold': (f, s(base), 'bold'), 
            'h1': (f, s(16), 'bold'),        
            'h2': (f, s(12), 'bold'),        
            'mono': ('Consolas', s(10)),     
            'kpi': ('Arial', s(24), 'bold'), 
            'kpi_lbl': (f, s(10)),           
            'table': (f, s(9))               
        }

    def apply_styles(self):
        colors = self.get_color_palette()
        s = lambda x: int(x * self.scale_factor)
        
        self.root.config(background=colors['bg_dark'])
        self.style.configure('Sidebar.TFrame', background=colors['bg_darker'])
        
        # 根據比例調整 Padding
        pad_nav = s(10)
        self.style.configure('Nav.TButton', 
                             font=self.fonts['h2'], 
                             background=colors['bg_darker'], 
                             foreground=colors['fg_dim'], 
                             borderwidth=0, 
                             anchor='w', 
                             padding=pad_nav)
        
        self.style.map('Nav.TButton',
            foreground=[('active', 'white'), ('disabled', colors['fg_dim'])],
            background=[('active', '#333333'), ('disabled', colors['bg_darker'])]
        )
        
        self.style.configure('NavActive.TButton', 
                             font=self.fonts['h2'], 
                             background='#333333', 
                             foreground='white', 
                             borderwidth=0, anchor='w', padding=pad_nav)

        self.style.configure('Action.TButton', font=self.fonts['h2'], anchor='center', padding=s(5))
        
        for style_name in ['Success', 'Primary', 'Warning', 'Accent', 'Danger']:
            self.style.configure(f'Custom.{style_name}.TButton', font=self.fonts['ui_bold'])

        self.style.configure('Card.TFrame', background=colors['bg_card'], relief='flat')
        self.style.configure('CardLabel.TLabel', background=colors['bg_card'], foreground=colors['fg_dim'], font=self.fonts['kpi_lbl'])
        self.style.configure('CardValue.TLabel', background=colors['bg_card'], foreground=colors['accent'], font=self.fonts['kpi'])

        self.style.configure('AxisActive.TLabel', background=colors['accent'], foreground='white', font=self.fonts['ui_bold'], padding=s(3), anchor='center')
        self.style.configure('AxisInactive.TLabel', background='#333333', foreground='#666666', font=self.fonts['ui_bold'], padding=s(3), anchor='center')

        row_height = int(28 * self.scale_factor)
        self.style.configure('Treeview', 
                             font=self.fonts['table'], 
                             rowheight=row_height, 
                             background=colors['bg_card'], 
                             fieldbackground=colors['bg_card'], 
                             foreground=colors['fg_main'], 
                             borderwidth=0)
        
        self.style.configure('Treeview.Heading', 
                             font=self.fonts['ui_bold'], 
                             background=colors['bg_header'], 
                             foreground='white', 
                             relief='flat')
        
        self.style.map('Treeview', 
                       background=[('selected', colors['accent_dim'])], 
                       foreground=[('selected', 'white')])

        self.style.configure('Inverse.TLabel', background=colors['bg_darker'], foreground='white')
        self.style.configure('Header.TLabel', font=self.fonts['h1'], background=colors['bg_card'], foreground='white')
        
        self.style.configure('Status.TLabel', 
                             font=self.fonts['ui'], 
                             background=colors['bg_card'], 
                             foreground=colors['accent'])

    def get_color_palette(self):
        return {
            'bg_darker': '#181818', 
            'bg_dark':   '#1e1e1e', 
            'bg_card':   '#252526', 
            'bg_header': '#2d2d2d', 
            'fg_main':   '#e0e0e0', 
            'fg_dim':    '#858585', 
            'accent':    '#00bc8c', 
            'accent_dim':'#007a5a', 
            'warning':   '#f39c12', 
            'danger':    '#e74c3c', 
            'grid':      '#444444', 
            'line':      '#3498db', 
            'star':      '#f39c12'  
        }