import argparse
import tkinter as tk
import sys
import os

# 현재 디렉토리를 path에 추가하여 패키지 인식 보장
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from magewell_rpa.ui.main_window import MainWindow
except ImportError as e:
    print(f"Import Error: {e}")
    print("패키지 구조를 확인하세요.")
    sys.exit(1)

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
