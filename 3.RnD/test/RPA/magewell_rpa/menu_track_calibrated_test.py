"""
자동 홈 원점 보정 검증: 홈잉 후 실제 커서 프레임 위치를 측정해 current 초기화,
그다음 Menu.png 로 추종. 오차가 ~0 으로 줄어드는지 확인. (앱의 _calibrate_home_origin 로직 재현)
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
        # 홈잉 + 자동 원점 보정
        rb.reset_mouse(); time.sleep(0.6)
        origin = jiggle_locate(cap, rb)
        print(f"측정된 홈 원점(프레임): {origin}")
        cur_x, cur_y = (origin if origin else (0, 0))

        # Menu 추종
        DEAD, STEP = 2, 127
        for i in range(80):
            frame = grab(cap, 2)
            res = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(res)
            tx, ty = ml
            dx, dy = tx - cur_x, ty - cur_y
            if abs(dx) <= DEAD and abs(dy) <= DEAD:
                print(f"수렴 at i={i}: cur=({cur_x},{cur_y}) target=({tx},{ty})")
                TX, TY = tx, ty
                break
            sx = max(min(dx, STEP), -STEP); sy = max(min(dy, STEP), -STEP)
            rb.send_mouse_move(sx, sy, quiet=True)
            cur_x += sx; cur_y += sy
            time.sleep(0.05)
        else:
            TX, TY = tx, ty

        actual = jiggle_locate(cap, rb)
        fin = grab(cap)
        if fin is not None:
            af = fin.copy()
            cv2.rectangle(af, (TX, TY), (TX+tw, TY+th), (0, 0, 255), 2)
            if actual: cv2.drawMarker(af, actual, (0, 255, 0), cv2.MARKER_CROSS, 30, 2)
            cv2.imwrite(f"{OUT}\\menu_calibrated_final.png", af)
        print(f"target(frame)=({TX},{TY})  실제 커서={actual}")
        if actual:
            print(f"보정 후 오차: dx={actual[0]-TX}, dy={actual[1]-TY}  (목표 ~0)")
    finally:
        cap.release(); rb.disconnect()

if __name__ == "__main__":
    main()
