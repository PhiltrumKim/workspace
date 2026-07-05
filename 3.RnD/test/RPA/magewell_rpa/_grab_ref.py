import time, cv2, numpy as np
from magewell_rpa.core.relay_board import RelayBoardController
OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
rb = RelayBoardController(port="COM3", verbose=False)
rb.connect(); rb.set_mode("remote"); time.sleep(0.3)
for _ in range(4):
    rb.send_mouse_move(40,0,quiet=True); time.sleep(0.1)
    rb.send_mouse_move(-40,0,quiet=True); time.sleep(0.1)
# 커서를 우하단 구석으로 치워 UI 가림 최소화
rb.move_mouse_relative(3000,3000); time.sleep(0.4)
rb.disconnect()
cap = cv2.VideoCapture(0); cap.set(3,1920); cap.set(4,1080); time.sleep(0.5)
f=None
for _ in range(10):
    r,fr=cap.read()
    if r: f=fr
    time.sleep(0.05)
cap.release()
cv2.imwrite(f"{OUT}\\ref_frame.png", f)
print("saved ref_frame.png", f.shape, "mean", round(float(f.mean()),1))
