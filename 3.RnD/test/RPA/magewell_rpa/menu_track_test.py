"""
Menu.png 템플릿으로 라이브 화면 매칭 → 앱 추종 알고리즘으로 커서가 그 위치까지
도달하는지 확인. 매칭/최종 위치를 이미지에 표시해 저장.
"""
import time
import cv2
import numpy as np
from magewell_rpa.core.relay_board import RelayBoardController

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
TEMPLATE = r"C:\Users\embed\Desktop\git\MyWorkspace\3.RnD\test\RPA\magewell_rpa\Menu.png"

def grab(cap, n=3):
    f = None
    for _ in range(n):
        r, fr = cap.read()
        if r and fr is not None:
            f = fr
        time.sleep(0.02)
    return f

def locate(cap, rb):
    a = grab(cap)
    rb.send_mouse_move(8, 8, quiet=True); time.sleep(0.3)
    b = grab(cap)
    rb.send_mouse_move(-8, -8, quiet=True); time.sleep(0.3)
    d = (np.abs(a.astype(int) - b.astype(int)).sum(2) > 40)
    ys, xs = np.nonzero(d)
    if len(xs) < 5:
        return None
    return (int(xs.min()), int(ys.min()))

def main():
    tmpl = cv2.imread(TEMPLATE)
    if tmpl is None:
        print("template load failed"); return
    th, tw = tmpl.shape[:2]
    print(f"template {TEMPLATE} = {tw}x{th}")

    rb = RelayBoardController(port="COM3", verbose=False)
    if not rb.connect():
        print("relay connect failed"); return
    rb.set_mode("remote"); time.sleep(0.3)
    for _ in range(4):
        rb.send_mouse_move(40, 0, quiet=True); time.sleep(0.1)
        rb.send_mouse_move(-40, 0, quiet=True); time.sleep(0.1)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    time.sleep(0.5)

    try:
        base = grab(cap, 5)
        res = cv2.matchTemplate(base, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        TX, TY = maxloc
        print(f"매칭 score={maxv:.3f}  target(frame top-left)=({TX},{TY})")
        ann = base.copy()
        cv2.rectangle(ann, (TX, TY), (TX+tw, TY+th), (0, 0, 255), 2)
        cv2.imwrite(f"{OUT}\\menu_match.png", ann)
        if maxv < 0.5:
            print("매칭 점수 낮음 - 스케일/해상도 불일치 가능. 중단."); return

        rb.reset_mouse(); time.sleep(0.6)
        cur_x, cur_y = 0, 0
        DEAD, STEP = 2, 127
        for i in range(80):
            frame = grab(cap, 2)
            if frame is None: continue
            res = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(res)
            tx, ty = ml
            dx, dy = tx - cur_x, ty - cur_y
            if i % 6 == 0:
                print(f"i={i:2d} score={mv:.2f} target=({tx},{ty}) cur=({cur_x},{cur_y}) d=({dx},{dy})")
            if abs(dx) <= DEAD and abs(dy) <= DEAD:
                print(f"수렴 at i={i}: cur=({cur_x},{cur_y})")
                break
            sx = max(min(dx, STEP), -STEP)
            sy = max(min(dy, STEP), -STEP)
            rb.send_mouse_move(sx, sy, quiet=True)
            cur_x += sx; cur_y += sy
            time.sleep(0.05)

        actual = locate(cap, rb)
        fin = grab(cap)
        if fin is not None:
            af = fin.copy()
            cv2.rectangle(af, (TX, TY), (TX+tw, TY+th), (0, 0, 255), 2)
            if actual:
                cv2.drawMarker(af, actual, (0, 255, 0), cv2.MARKER_CROSS, 30, 2)
            cv2.imwrite(f"{OUT}\\menu_final.png", af)
        print(f"\n최종 모델 cur=({cur_x},{cur_y})  target(frame)=({TX},{TY})")
        print(f"실제 커서(측정)= {actual}")
        if actual:
            print(f"실제 vs 템플릿 top-left 오차: dx={actual[0]-TX}, dy={actual[1]-TY}")
    finally:
        cap.release()
        rb.disconnect()

if __name__ == "__main__":
    main()
