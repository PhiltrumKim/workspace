# -*- coding: utf-8 -*-
"""
최종 목표 데모: 사용자 없이 워크플로우 기반으로 웹 브라우저 자동 실행.
Menu > Internet 서브메뉴를 발견/등록 → launch_web_browser 워크플로우 생성 → 실행 → 브라우저 기동.
"""
import os, time, cv2, numpy as np
from rpa_auto.engine import RelayVisionEngine
from rpa_auto.registry import Registry
from rpa_auto import discover, workflow

SHOTS = r"C:\Users\embed\Desktop\git\MyWorkspace_1\3.RnD\test\RPA\magewell_rpa\rpa_demo_20260705"
SCRATCH = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"

eng = RelayVisionEngine()
if not eng.connect():
    raise SystemExit("connect failed")
reg = Registry()
try:
    # 사전: menu_btn, menu_01(Internet) 객체 필요 (앞선 발견 데모에서 등록됨)
    assert reg.template("menu_btn") is not None and reg.template("menu_01") is not None, "먼저 demo_autonomous.py 실행 필요"

    # 1) Internet 서브메뉴 열기: Menu -> Internet
    eng.dismiss()
    f = eng.find(reg.template("menu_btn"), thr=0.5); eng.click(*f["center"]); time.sleep(0.5)
    A = eng.screenshot(4)                                   # 메인 메뉴만 열린 상태
    f = eng.find(reg.template("menu_01"), thr=0.6); eng.click(*f["center"]); time.sleep(0.6)
    B = eng.screenshot(4)                                   # + Internet 서브메뉴
    cv2.imwrite(f"{SCRATCH}\\lb_submenu.png", B)

    # 2) 서브메뉴 영역(메인 메뉴 오른쪽) 분리 후 항목 분할/등록
    diff = (np.abs(A.astype(int) - B.astype(int)).sum(2) > 40)
    region = np.zeros(diff.shape, bool); region[90:540, 268:620] = True
    ys, xs = np.nonzero(diff & region)
    px0, px1, py0, py1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    rows = discover._segment_rows(B, (px0, py0, px1, py1))
    print(f"Internet 서브메뉴 패널=({px0},{py0},{px1},{py1}) 항목 {len(rows)}개")
    names = []
    for k, (a, b) in enumerate(rows):
        y0, y1 = py0 + a, py0 + b; cy, cx = (y0+y1)//2, (px0+px1)//2
        crop = B[max(0, y0-3):y1+3, px0:px1].copy()
        nm = f"internet_{k:02d}"
        reg.add(nm, crop, {"kind": "menu_item", "click": [cx, cy], "from": "menu_01"})
        names.append(nm)
        print(f"  {nm} center=({cx},{cy})")
    # Web Browser = 서브메뉴 마지막 항목(Pi Store / RPi Resources / Web Browser)
    browser_obj = names[-1]

    # 3) launch_web_browser 워크플로우 생성 (Menu -> Internet -> Web Browser)
    wf = {"name": "launch_web_browser", "goal": "Menu > Internet > Web Browser 자동 실행",
          "steps": [
              {"action": "click", "object": "menu_btn"}, {"action": "wait", "sec": 0.6},
              {"action": "click", "object": "menu_01"},  {"action": "wait", "sec": 0.6},
              {"action": "click", "object": browser_obj}, {"action": "wait", "sec": 1.0}]}
    workflow.save_workflow(wf)
    print(f"\n워크플로우 저장: launch_web_browser (browser 객체={browser_obj})")

    # 4) 실행: 깨끗한 상태에서 워크플로우로 브라우저 자동 실행
    eng.dismiss()
    print("\n=== launch_web_browser 실행 ===")
    out = workflow.run(eng, reg, wf, thr=0.55, shots_dir=SHOTS)
    print("ok =", out["ok"])

    # 5) 브라우저 기동 대기 후 캡처
    print("브라우저 기동 대기...")
    time.sleep(12)
    shot = eng.screenshot(5)
    cv2.imwrite(f"{SHOTS}\\browser_launched.png", shot)
    cv2.imwrite(f"{SCRATCH}\\lb_browser_launched.png", shot)
    print("saved browser_launched.png  (mean brightness %.1f)" % float(shot.mean()))
finally:
    eng.close()
