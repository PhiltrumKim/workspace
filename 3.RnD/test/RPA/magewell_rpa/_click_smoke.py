# -*- coding: utf-8 -*-
import cv2
from rpa_auto.engine import RelayVisionEngine
OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
MENU = r"C:\Users\embed\Desktop\git\MyWorkspace\3.RnD\test\RPA\magewell_rpa\Menu.png"

eng = RelayVisionEngine()
if not eng.connect():
    raise SystemExit("connect failed")
try:
    tmpl = cv2.imread(MENU)
    before = eng.screenshot(3); cv2.imwrite(f"{OUT}\\smk_before.png", before)
    m = eng.find(tmpl, thr=0.5)
    print("find menu:", m)
    if m:
        eng.click(*m["center"])
        after = eng.screenshot(4); cv2.imwrite(f"{OUT}\\smk_menu_open.png", after)
        print("clicked menu, saved smk_menu_open.png")
        # ESC 로 닫기 (HID 0x29)
        eng.key_tap(0x29)
        closed = eng.screenshot(4); cv2.imwrite(f"{OUT}\\smk_menu_closed.png", closed)
        print("ESC pressed, saved smk_menu_closed.png")
finally:
    eng.close()
