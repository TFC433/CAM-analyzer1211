import math
import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttk
import platform

class ThemeManager:
    def __init__(self, root):
        self.root = root
        
        # 強制使用暗黑主題 (符合科技感需求)
        self.style = ttk.Style(theme='darkly')
        self.is_dark_mode = True

        # 計算縮放與字體
        self.scale_factor = self._calculate_scale_factor()
        self.font_family = self._get_system_font()
        self.fonts = self._define_fonts()
        
        self.apply_styles()

    def _calculate_scale_factor(self):
        try:
            screen_dpi = self.root.winfo_fpixels('1i')
            # Windows 標準 DPI 是 96，限制縮放比例在 1.0 ~ 2.0 之間
            return max(1.0, min(screen_dpi / 96.0, 2.0))
        except:
            return 1.0

    def _get_system_font(self):
        """偵測作業系統，回傳最適合的通用 UI 字型"""
        sys = platform.system()
        if sys == "Windows":
            # [修正] 改用標準名稱，Matplotlib 比較容易辨識
            return "Microsoft JhengHei" 
        elif sys == "Darwin": # macOS
            return "PingFang TC"
        else: # Linux
            return "WenQuanYi Micro Hei"

    def _define_fonts(self):
        # 定義統一的字級系統 (Typography System)
        base = 10 # 基礎字號
        
        s = lambda x: int(x * self.scale_factor)
        f = self.font_family
        
        return {
            'ui': (f, s(base)),              # 一般介面
            'ui_bold': (f, s(base), 'bold'), # 粗體介面
            'h1': (f, s(16), 'bold'),        # 大標題
            'h2': (f, s(12), 'bold'),        # 副標題 / 導航
            'mono': ('Consolas', s(10)),     # 程式碼 / 數值
            'kpi': ('Arial', s(24), 'bold'), # 儀表板大數字
            'kpi_lbl': (f, s(10)),           # 儀表板標籤
            'table': (f, s(9))               # 表格內文 (稍微縮小)
        }

    def apply_styles(self):
        colors = self.get_color_palette()
        
        # 1. 全局設定
        self.root.config(background=colors['bg_dark'])
        
        # 2. 側邊欄樣式
        self.style.configure('Sidebar.TFrame', background=colors['bg_darker'])
        
        # 3. 導航按鈕 (扁平化)
        self.style.configure('Nav.TButton', 
                             font=self.fonts['h2'], 
                             background=colors['bg_darker'], 
                             foreground=colors['fg_dim'], 
                             borderwidth=0, 
                             anchor='w', 
                             padding=10)
        
        self.style.map('Nav.TButton',
            foreground=[('active', 'white'), ('disabled', colors['fg_dim'])],
            background=[('active', '#333333'), ('disabled', colors['bg_darker'])]
        )
        
        self.style.configure('NavActive.TButton', 
                             font=self.fonts['h2'], 
                             background='#333333', 
                             foreground='white', 
                             borderwidth=0, anchor='w', padding=10)

        # 4. 操作按鈕 (醒目)
        self.style.configure('Action.TButton', font=self.fonts['h2'], anchor='center', padding=5)
        
        # 自定義按鈕樣式 (配合 app_ui.py 裡的呼叫)
        for style_name in ['Success', 'Primary', 'Warning', 'Accent', 'Danger']:
            self.style.configure(f'Custom.{style_name}.TButton', font=self.fonts['ui_bold'])

        # 5. 卡片樣式
        self.style.configure('Card.TFrame', background=colors['bg_card'], relief='flat')
        self.style.configure('CardLabel.TLabel', background=colors['bg_card'], foreground=colors['fg_dim'], font=self.fonts['kpi_lbl'])
        self.style.configure('CardValue.TLabel', background=colors['bg_card'], foreground=colors['accent'], font=self.fonts['kpi'])

        # 6. 軸向燈號
        self.style.configure('AxisActive.TLabel', background=colors['accent'], foreground='white', font=self.fonts['ui_bold'], padding=3, anchor='center')
        self.style.configure('AxisInactive.TLabel', background='#333333', foreground='#666666', font=self.fonts['ui_bold'], padding=3, anchor='center')

        # 7. 表格樣式
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

        # 8. 標題與一般文字
        self.style.configure('Inverse.TLabel', background=colors['bg_darker'], foreground='white')
        self.style.configure('Header.TLabel', font=self.fonts['h1'], background=colors['bg_dark'], foreground='white')

    def get_color_palette(self):
        """統一色票管理 (Dark Tech Theme)"""
        return {
            'bg_darker': '#181818', # 側邊欄最深色
            'bg_dark':   '#1e1e1e', # 主背景
            'bg_card':   '#252526', # 卡片/內容背景
            'bg_header': '#2d2d2d', # 表頭背景
            
            'fg_main':   '#e0e0e0', # 主要文字
            'fg_dim':    '#858585', # 次要文字/未選取
            
            'accent':    '#00bc8c', # 亮綠色 (重點)
            'accent_dim':'#007a5a', # 暗綠色 (選取背景)
            'warning':   '#f39c12', # 警告色
            'danger':    '#e74c3c', # 危險色
            
            # [修正] 補上這些顏色，避免 charts.py 報錯
            'grid':      '#444444', 
            'line':      '#3498db', # 藍色線條
            'star':      '#f39c12'  # 星星顏色
        }