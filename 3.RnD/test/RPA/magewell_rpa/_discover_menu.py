# -*- coding: utf-8 -*-
"""Menu 클릭 후 나타난 메뉴 항목들을 행 단위로 분할 (시각 검증용)."""
import cv2, numpy as np
from rpa_auto.engine import RelayVisionEngine
OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
MENU = r"C:\Users\embed\Desktop\git\MyWorkspace\3.RnD\test\RPA\magewell_rpa\Menu.png"

eng = RelayVisionEngine()
eng.connect()
try:
    before = eng.screenshot(3)
    m = eng.find(cv2.imread(MENU), thr=0.5)
    eng.click(*m["center"])
    after = eng.screenshot(4)
    cv2.imwrite(f"{OUT}\\disc_after.png", after)

    # 1) 나타난 패널 영역 (좌측, 태스크바 아래)
    diff = (np.abs(before.astype(int) - after.astype(int)).sum(2) > 40)
    region = np.zeros_like(diff); region[90:, :420] = True
    d = diff & region
    ys, xs = np.nonzero(d)
    px0, px1, py0, py1 = xs.min(), xs.max(), ys.min(), ys.max()
    print(f"panel bbox: x[{px0}..{px1}] y[{py0}..{py1}]")

    # 2) 행 분할: 좌측 아이콘 열의 채도로 아이콘(=항목) 밴드 검출
    panel = after[py0:py1, px0:px1]
    hsv = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    strip = sat[:, 4:46]                          # 아이콘 열
    prof = (strip > 45).sum(axis=1).astype(float) # 행별 유채색 픽셀 수
    prof = np.convolve(prof, np.ones(3)/3, mode="same")
    content = prof > 3
    bands = []
    s = None
    for i, c in enumerate(content):
        if c and s is None:
            s = i
        elif not c and s is not None:
            bands.append([s, i]); s = None
    if s is not None:
        bands.append([s, len(content)])
    # 가까운 밴드 병합, 작은 밴드 제거
    merged = []
    for b in bands:
        if merged and b[0] - merged[-1][1] < 8:
            merged[-1][1] = b[1]
        else:
            merged.append(b)
    items = [(a, b) for a, b in merged if b - a >= 8]
    print(f"detected {len(items)} rows")

    ann = after.copy()
    cv2.rectangle(ann, (px0, py0), (px1, py1), (255, 0, 0), 1)
    for k, (a, b) in enumerate(items):
        y0, y1 = py0 + a, py0 + b
        cy = (y0 + y1) // 2
        cx = (px0 + px1) // 2
        cv2.rectangle(ann, (px0, y0), (px1, y1), (0, 0, 255), 1)
        cv2.drawMarker(ann, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 14, 1)
        cv2.putText(ann, str(k), (px1+4, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite(f"{OUT}\\disc_rows.png", ann)
    print("saved disc_rows.png")

    eng.key_tap(0x29)  # ESC 닫기
finally:
    eng.close()
