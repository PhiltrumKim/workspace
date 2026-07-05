# -*- coding: utf-8 -*-
"""
자율 RPA 데모: 아이콘=클릭가능객체 → 클릭 → 신규 항목 발견/등록 → 워크플로우 생성 → 재실행.
1) Menu 객체 시드
2) Menu 클릭 → 나타난 메뉴 항목 자동 발견/등록 + 각 항목 클릭 워크플로우 생성
3) 생성된 워크플로우(click_menu_01 = Internet)로 재실행 → 서브메뉴 열림 확인
"""
import os, cv2
from rpa_auto.engine import RelayVisionEngine
from rpa_auto.registry import Registry
from rpa_auto import discover, workflow

MENU_PNG = r"C:\Users\embed\Desktop\git\MyWorkspace\3.RnD\test\RPA\magewell_rpa\Menu.png"
SHOTS = r"C:\Users\embed\Desktop\git\MyWorkspace_1\3.RnD\test\RPA\magewell_rpa\rpa_demo_20260705"
SCRATCH = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"
os.makedirs(SHOTS, exist_ok=True)

eng = RelayVisionEngine()
if not eng.connect():
    raise SystemExit("connect failed")
reg = Registry()
try:
    # 1) 시드
    reg.add("menu_btn", cv2.imread(MENU_PNG), {"kind": "launcher", "note": "메인 메뉴 버튼"})
    print("seeded menu_btn")

    # 2) 발견
    print("\n=== 발견: Menu 클릭 → 항목 등록 ===")
    res = discover.discover_submenu(eng, reg, "menu_btn", "menu")
    if not res:
        raise SystemExit("discover 실패")
    cv2.imwrite(f"{SHOTS}\\discovered_menu.png", res["annotated"])
    cv2.imwrite(f"{SCRATCH}\\demo_discovered.png", res["annotated"])
    print(f"패널={res['panel']}  발견 항목 {len(res['items'])}개:")
    for it in res["items"]:
        print(f"  {it['name']}  center={it['center']}  서브메뉴={it['has_submenu']}  -> workflow: click_{it['name']}")

    # 3) 재실행: 생성된 워크플로우로 Internet(=menu_01) 다시 클릭
    print("\n=== 재실행: click_menu_01 (Internet) 워크플로우 ===")
    wf = workflow.load_workflow("click_menu_01")
    print("goal:", wf["goal"])
    out = workflow.run(eng, reg, wf, thr=0.55, shots_dir=SHOTS)
    print("workflow ok =", out["ok"])
    sub = eng.screenshot(4)
    cv2.imwrite(f"{SHOTS}\\replay_internet_submenu.png", sub)
    cv2.imwrite(f"{SCRATCH}\\demo_replay_internet.png", sub)

    # 정리: 서브메뉴/메뉴 닫기(빈 바탕화면 클릭)
    eng.dismiss()
    print("\n총 등록 객체:", len(reg.names()), "| 생성 워크플로우:", len(workflow.list_workflows()))
finally:
    eng.close()
