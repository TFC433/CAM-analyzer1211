import tkinter as tk
from tkinterdnd2 import TkinterDnD
from frontend.app_ui import CAMApp

if __name__ == "__main__":
    # 嘗試使用支援拖放的 Tkinter，如果沒有則使用標準版
    try:
        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()
    
    # 設定初始大小
    root.geometry("1280x850")
    
    # 啟動應用程式
    app = CAMApp(root)
    
    root.mainloop()