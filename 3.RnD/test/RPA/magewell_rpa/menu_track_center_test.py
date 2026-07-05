"""
중심 타깃 + 자동 원점 보정 검증: 커서가 Menu.png 템플릿의 '중앙'에 오는지 확인.
(앱의 최종 로직 재현: 홈 보정 후 target = 검출박스 중심)
"""
import time
import cv2
import numpy as np
from magewell_rpa.core.relay_board import RelayBoardController

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
TEMPLATE = r"C:\Users\embed\Desktop\git\MyWorkspace\3.RnD\test\RPA\magewell_rpa\Menu.png"

def grab(cap, n=4):
    f = None
    for _ in range(n):
        r, fr = cap.read()
        if r and fr is not None:
            f = fr
        time.sleep(0.02)
    return f

def jiggle_locate(cap, rb):
    a = grab(cap)
    rb.send_mouse_move(8, 8, quiet=True); time.sleep(0.25)
    b = grab(cap)
    rb.send_mouse_move(-8, -8, quiet=True); time.sleep(0.15)
    d = (np.abs(a.astype(int) - b.astype(int)).sum(2) > 40)
    ys, xs = np.nonzero(d)
    if len(xs) < 5:
        return None
    return (int(xs.min()), int(ys.min()))

def main():
    tmpl = cv2.imread(TEMPLATE); th, tw = tmpl.shape[:2]
    rb = RelayBoardController(port="COM3", verbose=False)
    if not rb.connect(): return
    rb.set_mode("remote"); time.sleep(0.3)
    for _ in range(4):
        rb.send_mouse_move(40, 0, quiet=True); time.sleep(0.1)
        rb.send_mouse_move(-40, 0, quiet=True); time.sleep(0.1)
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    time.sleep(0.5)
    try:
        rb.reset_mouse(); time.sleep(0.6)
        origin = jiggle_locate(cap, rb)
        print(f"홈 원점(프레임): {origin}")
        cur_x, cur_y = (origin if origin else (0, 0))

        DEAD, STEP = 2, 127
        TLX = TLY = 0
        for i in range(80):
            frame = grab(cap, 2)
            res = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(res)
            TLX, TLY = ml
            cx = TLX + tw / 2.0   # 중심 타깃
            cy = TLY + th / 2.0
            dx, dy = int(cx - cur_x), int(cy - cur_y)
            if abs(dx) <= DEAD and abs(dy) <= DEAD:
                print(f"수렴 at i={i}: cur=({cur_x},{cur_y}) center=({int(cx)},{int(cy)})")
                break
            sx = max(min(dx, STEP), -STEP); sy = max(min(dy, STEP), -STEP)
            rb.send_mouse_move(sx, sy, quiet=True)
            cur_x += sx; cur_y += sy
            time.sleep(0.05)

        center = (int(TLX + tw / 2), int(TLY + th / 2))
        actual = jiggle_locate(cap, rb)
        fin = grab(cap)
        if fin is not None:
            af = fin.copy()
            cv2.rectangle(af, (TLX, TLY), (TLX+tw, TLY+th), (0, 0, 255), 2)
            cv2.drawMarker(af, center, (255, 0, 0), cv2.MARKER_CROSS, 20, 1)   # 파랑=목표중심
            if actual: cv2.drawMarker(af, actual, (0, 255, 0), cv2.MARKER_CROSS, 30, 2)  # 초록=실제
            cv2.imwrite(f"{OUT}\\menu_center_final.png", af)
        print(f"템플릿 중심(target)={center}  실제 커서={actual}")
        if actual:
            print(f"중심 대비 오차: dx={actual[0]-center[0]}, dy={actual[1]-center[1]}")
    finally:
        cap.release(); rb.disconnect()

if __name__ == "__main__":
    main()
