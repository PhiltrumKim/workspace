"""Pi 화면을 릴레이보드로 깨우고 cv2 캡처가 라이브 프레임을 주는지 확인."""
import time
import cv2
import numpy as np
from magewell_rpa.core.relay_board import RelayBoardController

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"

# 1) 릴레이로 마우스 흔들어 Pi 깨우기
rb = RelayBoardController(port="COM3", verbose=False)
if rb.connect():
    rb.set_mode("remote"); time.sleep(0.3)
    for _ in range(5):
        rb.send_mouse_move(40, 0, quiet=True); time.sleep(0.1)
        rb.send_mouse_move(-40, 0, quiet=True); time.sleep(0.1)
    rb.disconnect()
    print("jiggle sent")
else:
    print("relay connect failed")

time.sleep(1.0)

# 2) cv2 캡처 확인
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
last = None
for i in range(15):
    ret, frame = cap.read()
    if ret and frame is not None:
        last = frame
    time.sleep(0.05)
cap.release()

if last is not None:
    h, w = last.shape[:2]
    print(f"frame {w}x{h} mean_brightness={last.mean():.1f}")
    cv2.imwrite(f"{OUT}\\wake_frame.png", last)
    print("saved wake_frame.png")
else:
    print("no frame")
