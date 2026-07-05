"""
X/Y 축 이동 진단: 릴레이보드로 홈(0,0) → +X → +Y 순으로 이동시키며
Magewell Capture Express 캡처로 커서 위치를 잡아 X/Y 방향/크기를 분리 관찰.

기대(화면 좌표 +x=오른쪽, +y=아래):
  base   : 좌상단 부근
  +X 후  : 오른쪽으로 이동
  +Y 후  : 아래로 이동
"""
import time
import ctypes
from ctypes import wintypes

import numpy as np
from PIL import ImageGrab, Image

from magewell_rpa.core.relay_board import RelayBoardController

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
STEP = 120  # 한 패킷 이동량(±127 이내)

def get_bbox(title="Magewell Capture Express"):
    u = ctypes.windll.user32
    hwnd = u.FindWindowW(None, title)
    if not hwnd:
        return None
    u.ShowWindow(hwnd, 9); u.SetForegroundWindow(hwnd); u.BringWindowToTop(hwnd)
    time.sleep(0.6)
    r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)

def shot(bbox):
    img = ImageGrab.grab(all_screens=True)
    a = np.asarray(img.convert("RGB"))
    if bbox:
        L, T, R, B = bbox
        a = a[max(0,T):B, max(0,L):R]
    return a

def main():
    try: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass
    bbox = get_bbox(); print("bbox:", bbox)

    rb = RelayBoardController(port="COM3", verbose=False)
    if not rb.connect():
        return
    frames = {}
    try:
        rb.set_mode("remote"); time.sleep(0.4)
        # 홈으로 (좌상단). reset_mouse = (-127,-127)*35 상대이동
        rb.reset_mouse(); time.sleep(0.6)
        frames["0_home"] = shot(bbox)

        print(f"send +X: send_mouse_move({STEP}, 0)")
        rb.send_mouse_move(STEP, 0, quiet=True); time.sleep(0.8)
        frames["1_plusX"] = shot(bbox)

        print(f"send +Y: send_mouse_move(0, {STEP})")
        rb.send_mouse_move(0, STEP, quiet=True); time.sleep(0.8)
        frames["2_plusY"] = shot(bbox)
    finally:
        rb.disconnect()

    for k, a in frames.items():
        Image.fromarray(a).save(f"{OUT}\\ax_{k}_full.png")

    def mask(a, b, thr=45):
        return (np.abs(a.astype(int)-b.astype(int)).sum(2) > thr)
    def bboxof(m):
        ys, xs = np.nonzero(m)
        if len(xs)==0: return None
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
    def centroid(m):
        ys, xs = np.nonzero(m)
        if len(xs)==0: return None
        return round(float(xs.mean()),1), round(float(ys.mean()),1), int(len(xs))

    m1 = mask(frames["0_home"], frames["1_plusX"])
    m2 = mask(frames["1_plusX"], frames["2_plusY"])
    print("diff home->+X : bbox", bboxof(m1), "centroid", centroid(m1))
    print("diff +X->+Y   : bbox", bboxof(m2), "centroid", centroid(m2))

    m = m1 | m2
    bb = bboxof(m)
    if bb:
        x0,y0,x1,y1 = bb; mx=50
        cx0,cy0 = max(0,x0-mx), max(0,y0-mx); cx1,cy1 = x1+mx, y1+mx
        for k, a in frames.items():
            crop = a[cy0:cy1, cx0:cx1]
            im = Image.fromarray(crop)
            sc = max(1, min(3, 480//max(1,crop.shape[0])))
            if sc>1: im = im.resize((crop.shape[1]*sc, crop.shape[0]*sc), Image.NEAREST)
            im.save(f"{OUT}\\ax_{k}_crop.png")
        print("crop region:", (cx0,cy0,cx1,cy1))
    print("done")

if __name__ == "__main__":
    main()
