"""
앱과 동일한 추종 알고리즘을 헤드리스로 재현하여 커서가 템플릿 위치(특히 Y)에
수렴하는지 측정. 템플릿은 화면 하단(큰 Y)에서 잡아 Y 이동을 크게 만든다.
"""
import time
import cv2
import numpy as np
from magewell_rpa.core.relay_board import RelayBoardController

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"

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
        # 템플릿: 하단 터미널 프롬프트 영역 (큰 Y). frame top-left 기준.
        base = grab(cap, 5)
        TX, TY, TW, TH = 632, 735, 170, 28
        tmpl = base[TY:TY+TH, TX:TX+TW].copy()
        cv2.imwrite(f"{OUT}\\cl_template.png", tmpl)
        cv2.imwrite(f"{OUT}\\cl_base.png", base)
        print(f"template rect (frame): x={TX} y={TY} w={TW} h={TH}")

        # 앱과 동일: 연결 시 reset_mouse -> current=(0,0)
        rb.reset_mouse(); time.sleep(0.6)
        cur_x, cur_y = 0, 0

        DEAD, STEP = 2, 127
        frame_w = frame_h = None
        traj = []
        for i in range(70):
            frame = grab(cap, 2)
            if frame is None:
                continue
            frame_h, frame_w = frame.shape[:2]
            res = cv2.matchTemplate(frame, tmpl, cv2.TM_CCOEFF_NORMED)
            _, maxv, _, maxloc = cv2.minMaxLoc(res)
            tx, ty = maxloc  # target (frame px) = 앱의 target_x/y (monitor==frame==1920x1080)
            dx = tx - cur_x
            dy = ty - cur_y
            if i % 7 == 0:
                print(f"i={i:2d} score={maxv:.2f} target=({tx},{ty}) cur=({cur_x},{cur_y}) d=({dx},{dy})")
            if abs(dx) <= DEAD and abs(dy) <= DEAD:
                print(f"수렴 at i={i}: cur=({cur_x},{cur_y}) target=({tx},{ty})")
                break
            sx = max(min(dx, STEP), -STEP)
            sy = max(min(dy, STEP), -STEP)
            rb.send_mouse_move(sx, sy, quiet=True)
            cur_x += sx; cur_y += sy
            traj.append((cur_x, cur_y))
            time.sleep(0.05)

        # 최종 실제 커서 위치 측정
        actual = locate(cap, rb)
        fin = grab(cap)
        if fin is not None:
            cv2.imwrite(f"{OUT}\\cl_final.png", fin)
        print(f"\n최종 모델 cur=({cur_x},{cur_y})  target(frame)=({TX},{TY})")
        print(f"실제 커서(측정, frame px)= {actual}")
        if actual:
            print(f"실제 vs 템플릿 오차: dx={actual[0]-TX}, dy={actual[1]-TY}  (홈 원점 보정 ~+46,+41 예상)")
    finally:
        cap.release()
        rb.disconnect()

if __name__ == "__main__":
    main()
