# -*- coding: utf-8 -*-
"""
캡처 화면의 각 UI 요소로 커서가 도달하는지 자동 테스트.
- 각 UI를 템플릿으로 크롭 보관, 커서를 그 중심으로 추종, 실제 도달 위치 측정
- 결과 이미지 + 마크다운 보고서를 프로젝트 보고서 폴더에 저장
"""
import os
import time
import json
import cv2
import numpy as np
from magewell_rpa.core.relay_board import RelayBoardController

SCRATCH = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
REPORT = r"C:\Users\embed\Desktop\git\MyWorkspace_1\3.RnD\test\RPA\magewell_rpa\ui_reach_report_20260705"
os.makedirs(REPORT, exist_ok=True)

# (name, x, y, w, h) 1920x1080 기준 (검증 완료)
TARGETS = [
    ("wastebasket",     78,   92, 64, 60),
    ("menu_btn",        1043, 52, 62, 28),
    ("browser_icon",    1148, 52, 32, 30),
    ("filemgr_icon",    1190, 52, 30, 30),
    ("term_taskbar",    1375, 52, 150, 28),
    ("cpu_pct",         1770, 55, 42, 22),
    ("clock",           1818, 55, 50, 22),
    ("term_titlebar",   636,  350, 34, 22),
    ("term_min_btn",    1216, 350, 22, 18),
    ("term_max_btn",    1240, 350, 22, 18),
    ("term_close_btn",  1264, 350, 22, 18),
    ("menu_File",       636,  379, 32, 20),
    ("menu_Edit",       676,  379, 32, 20),
    ("menu_Tabs",       720,  379, 36, 20),
    ("menu_Help",       768,  379, 36, 20),
]
PASS_TOL = 15  # px (euclid)

def grab(cap, n=3):
    f = None
    for _ in range(n):
        r, fr = cap.read()
        if r and fr is not None:
            f = fr
        time.sleep(0.02)
    return f

def jiggle_locate(cap, rb, expect=None, win=90):
    """(+8,+8) 흔들기 전후 차분으로 커서 위치 측정.
    expect(예상 중심) 지정 시 그 주변 win px 창으로 제한해 hover 하이라이트/원거리 오검출 배제."""
    a = grab(cap)
    rb.send_mouse_move(8, 8, quiet=True); time.sleep(0.25)
    b = grab(cap)
    rb.send_mouse_move(-8, -8, quiet=True); time.sleep(0.15)
    d = (np.abs(a.astype(int) - b.astype(int)).sum(2) > 40)
    if expect is not None:
        ex, ey = expect
        m = np.zeros(d.shape, dtype=bool)
        y0, y1 = max(0, ey-win), min(d.shape[0], ey+win)
        x0, x1 = max(0, ex-win), min(d.shape[1], ex+win)
        m[y0:y1, x0:x1] = True
        d = d & m
    ys, xs = np.nonzero(d)
    if len(xs) < 5:
        return None
    return (int(xs.min()), int(ys.min()))

def track_to(cap, rb, cur, cx, cy, max_iter=70):
    x0, y0 = cur
    for _ in range(max_iter):
        dx, dy = cx - x0, cy - y0
        if abs(dx) <= 2 and abs(dy) <= 2:
            break
        sx = max(min(dx, 127), -127)
        sy = max(min(dy, 127), -127)
        rb.send_mouse_move(sx, sy, quiet=True)
        x0 += sx; y0 += sy
        time.sleep(0.05)
    return (x0, y0)

def main():
    ref = cv2.imread(f"{SCRATCH}\\ref_frame.png")
    # 템플릿 크롭 보관
    tmpls = {}
    for name, x, y, w, h in TARGETS:
        crop = ref[y:y+h, x:x+w]
        cv2.imwrite(f"{REPORT}\\tmpl_{name}.png", crop)
        tmpls[name] = crop

    rb = RelayBoardController(port="COM3", verbose=False)
    if not rb.connect():
        print("relay connect failed"); return
    rb.set_mode("remote"); time.sleep(0.3)
    for _ in range(4):
        rb.send_mouse_move(40, 0, quiet=True); time.sleep(0.1)
        rb.send_mouse_move(-40, 0, quiet=True); time.sleep(0.1)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    time.sleep(0.5)

    results = []
    try:
        # 홈 + 자동 원점 보정
        rb.reset_mouse(); time.sleep(0.6)
        origin = jiggle_locate(cap, rb, expect=(48, 48), win=130)
        cur = origin if origin else (0, 0)
        print(f"home origin = {origin}")

        for name, x, y, w, h in TARGETS:
            cx, cy = x + w // 2, y + h // 2
            # 참고용 매칭 점수(현재 프레임)
            frame = grab(cap, 3)
            res = cv2.matchTemplate(frame, tmpls[name], cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(res)
            # 중심으로 추종
            cur = track_to(cap, rb, cur, cx, cy)
            actual = jiggle_locate(cap, rb, expect=(cx, cy), win=90)
            live = grab(cap, 3)
            err = None; dist = None; ok = False
            if actual:
                err = (actual[0]-cx, actual[1]-cy)
                dist = round((err[0]**2 + err[1]**2) ** 0.5, 1)
                ok = dist <= PASS_TOL
            # 주석 이미지 저장
            ann = live.copy()
            cv2.rectangle(ann, (x, y), (x+w, y+h), (0, 0, 255), 2)
            cv2.drawMarker(ann, (cx, cy), (255, 0, 0), cv2.MARKER_CROSS, 24, 1)
            if actual:
                cv2.drawMarker(ann, actual, (0, 255, 0), cv2.MARKER_CROSS, 30, 2)
            cv2.imwrite(f"{REPORT}\\result_{name}.png", ann)
            results.append({
                "name": name, "target": [cx, cy], "actual": list(actual) if actual else None,
                "err": list(err) if err else None, "dist": dist,
                "score": round(float(score), 3), "pass": ok
            })
            print(f"{name:16s} target=({cx},{cy}) actual={actual} dist={dist} score={score:.2f} {'PASS' if ok else 'FAIL'}")

        # 커서 치우기
        rb.move_mouse_relative(3000, 3000)
    finally:
        cap.release(); rb.disconnect()

    with open(f"{REPORT}\\results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    npass = sum(1 for r in results if r["pass"])
    print(f"\n=== {npass}/{len(results)} PASS ===")

if __name__ == "__main__":
    main()
