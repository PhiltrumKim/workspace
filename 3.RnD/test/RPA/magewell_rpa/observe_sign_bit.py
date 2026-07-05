"""
Δy 부호비트 하드웨어 관찰 스크립트.
Magewell Capture Express 창을 화면 캡처하여 current / spec 전송 전후의
마우스 포인터 이동 방향을 자동 판독한다. (test_sign_bit.py 의 인코더 재사용)

출력 PNG 는 scratchpad 로 저장한다.
"""
import time
import ctypes
from ctypes import wintypes
import sys

import numpy as np
from PIL import ImageGrab, Image

from test_sign_bit import build_mouse_data, full_packet, hexs
from magewell_rpa.core.relay_board import RelayBoardController

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"

DY = -60   # 위 방향 의도 (화면 +y = 아래)

def get_window_bbox(title="Magewell Capture Express"):
    u = ctypes.windll.user32
    hwnd = u.FindWindowW(None, title)
    if not hwnd:
        return None
    # 앞으로 가져오기
    u.ShowWindow(hwnd, 9)      # SW_RESTORE
    u.SetForegroundWindow(hwnd)
    u.BringWindowToTop(hwnd)
    time.sleep(0.6)
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)

def shot():
    img = ImageGrab.grab(all_screens=True)
    return np.asarray(img.convert("RGB"))

def main():
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    bbox = get_window_bbox()
    print("window bbox:", bbox)

    rb = RelayBoardController(port="COM3")
    if not rb.connect():
        return
    frames = {}
    try:
        rb.set_mode("remote")
        time.sleep(0.6)

        time.sleep(0.5); frames["0_base"] = shot()

        d, b6 = build_mouse_data(0, DY, mode="current")
        print("current:", hexs(full_packet(0xFE, d)))
        rb.send_packet(0xFE, d)
        time.sleep(1.0); frames["1_after_current"] = shot()

        d, b6 = build_mouse_data(0, DY, mode="spec")
        print("spec   :", hexs(full_packet(0xFE, d)))
        rb.send_packet(0xFE, d)
        time.sleep(1.0); frames["2_after_spec"] = shot()
    finally:
        rb.disconnect()

    # Magewell 창 영역으로 크롭 (보조 모니터). 전체 가상화면 캡처 기준 bbox 좌표 사용.
    if bbox:
        L, T, R, B = bbox
        L, T = max(0, L), max(0, T)
        frames = {k: arr[T:B, L:R] for k, arr in frames.items()}
        print("cropped to window; frame shape:", frames["0_base"].shape)

    # 창 영역 프레임 저장
    for k, arr in frames.items():
        Image.fromarray(arr).save(f"{OUT}\\obs_{k}_full.png")

    base = frames["0_base"]; cur = frames["1_after_current"]; spec = frames["2_after_spec"]

    def change_mask(a, b, thr=45):
        d = np.abs(a.astype(int) - b.astype(int)).sum(2)
        return d > thr

    m1 = change_mask(base, cur)
    m2 = change_mask(cur, spec)
    m = m1 | m2
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        print("변화 없음 - 포인터가 캡처 안 됐거나 이동 없음")
        return

    x0, x1 = xs.min(), xs.max(); y0, y1 = ys.min(), ys.max()
    print(f"change bbox (full-screen px): x[{x0}..{x1}] y[{y0}..{y1}]  size={x1-x0}x{y1-y0}  pts={len(xs)}")

    def centroid(mask):
        yy, xx = np.nonzero(mask)
        if len(xx) == 0: return None
        return (float(xx.mean()), float(yy.mean()), len(xx))
    print("centroid base->current:", centroid(m1))
    print("centroid current->spec:", centroid(m2))

    # 변화영역 크롭 + 확대해서 저장
    mx = 40
    cx0, cy0 = max(0, x0 - mx), max(0, y0 - mx)
    cx1, cy1 = x1 + mx, y1 + mx
    for k, arr in frames.items():
        crop = arr[cy0:cy1, cx0:cx1]
        im = Image.fromarray(crop)
        scale = max(1, min(4, 500 // max(1, crop.shape[0])))
        if scale > 1:
            im = im.resize((crop.shape[1]*scale, crop.shape[0]*scale), Image.NEAREST)
        im.save(f"{OUT}\\obs_{k}_crop.png")
    print("crop region:", (cx0, cy0, cx1, cy1))
    print("saved crops to scratchpad")

if __name__ == "__main__":
    main()
