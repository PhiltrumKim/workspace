"""
자율 X/Y 축 응답 측정.
릴레이보드로 커서를 각 축으로 상대이동시키고, cv2 캡처 프레임에서 실제 커서
위치를 측정하여 X/Y 방향·크기를 비교한다. (앱 없이 헤드리스로 전부 구동/측정)

커서 위치 측정: 작게 (+8,+8) 흔들어 전후 프레임을 차분 → 변화영역 top-left ≈ 커서 팁.
"""
import time
import cv2
import numpy as np
from magewell_rpa.core.relay_board import RelayBoardController

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"

def grab(cap, n=6):
    f = None
    for _ in range(n):
        r, fr = cap.read()
        if r and fr is not None:
            f = fr
        time.sleep(0.03)
    return f

def locate(cap, rb):
    """jiggle-diff 로 커서 절대 위치(팁 근사) 반환."""
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
    # wake
    for _ in range(4):
        rb.send_mouse_move(40, 0, quiet=True); time.sleep(0.1)
        rb.send_mouse_move(-40, 0, quiet=True); time.sleep(0.1)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    time.sleep(0.5)

    frames = {}
    try:
        # 시작점을 화면 중앙 근처로: 먼저 홈(좌상단)으로 크게 이동 후 중앙으로
        rb.move_mouse_relative(-3000, -3000); time.sleep(0.6)   # home (0,0)
        rb.move_mouse_relative(700, 400); time.sleep(0.6)       # 중앙 근처로
        p0 = locate(cap, rb); frames["p0"] = grab(cap)
        print("P0 (start):", p0)

        # --- X축 +500 ---
        rb.move_mouse_relative(500, 0); time.sleep(0.6)
        p1 = locate(cap, rb); frames["p1_afterX"] = grab(cap)
        print("P1 after +X500:", p1)

        # --- Y축 +500 ---
        rb.move_mouse_relative(0, 500); time.sleep(0.6)
        p2 = locate(cap, rb); frames["p2_afterY"] = grab(cap)
        print("P2 after +Y500:", p2)
    finally:
        cap.release()
        rb.disconnect()

    for k, f in frames.items():
        if f is not None:
            cv2.imwrite(f"{OUT}\\trk_{k}.png", f)

    if p0 and p1 and p2:
        print(f"\n[X test] commanded (+500, 0) -> actual delta = ({p1[0]-p0[0]}, {p1[1]-p0[1]})")
        print(f"[Y test] commanded (0, +500) -> actual delta = ({p2[0]-p1[0]}, {p2[1]-p1[1]})")
        print("\n기대: X test는 dx>0/dy~0, Y test는 dx~0/dy>0 (화면 +y=아래)")

if __name__ == "__main__":
    main()
