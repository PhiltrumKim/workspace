import argparse
import tkinter as tk
from magewell_rpa.ui.main_window import MainWindow

def main():
    parser = argparse.ArgumentParser(description="Magewell RPA Motion & Tracking (OOP)")
    parser.add_argument('--video', type=str, help='비디오 파일 경로')
    parser.add_argument('--template', type=str, help='템플릿 이미지 경로')
    args = parser.parse_args()

    root = tk.Tk()
    app = MainWindow(root, args)
    root.mainloop()

if __name__ == "__main__":
    main()
