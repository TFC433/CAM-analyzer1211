# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
# Project:      CAM Analyzer
# File:         main.py
# Author:       TFC-CRM
# Created:      2025-12-12
# Copyright:    (c) 2025 TFC-CRM. All rights reserved.
# License:      Proprietary / Confidential
# Description:  Application Entry Point with Auto Path Detection.
# ------------------------------------------------------------------------------

import tkinter as tk
import os
from tkinterdnd2 import TkinterDnD
from frontend.app_ui import CAMApp

if __name__ == "__main__":
    # 1. 抓取 main.py 所在的「絕對路徑」 (這就是您的專案根目錄)
    # 這樣不管您在終端機的哪一層目錄執行，這裡永遠會是對的
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # Try using TkinterDnD
    try:
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
    
    # 2. 設定視窗 Icon (使用絕對路徑)
    icon_path = os.path.join(BASE_DIR, "icon.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass 
    
    # Initial Geometry
    root.geometry("1280x850")
    
    # 3. 啟動 App，並將 BASE_DIR 傳進去給 UI 使用
    app = CAMApp(root, project_root=BASE_DIR)
    
    root.mainloop()