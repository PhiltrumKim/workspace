# -*- coding: utf-8 -*-
"""발견(discovery): 트리거 객체를 클릭해 나타난 메뉴 항목들을 자동 분할·등록하고,
각 항목을 클릭하는 워크플로우를 생성한다. (아이콘=클릭 가능 객체)
"""
import cv2, numpy as np
from . import workflow

def _segment_rows(after, bbox):
    """패널 내부를 좌측 아이콘 열의 그레이 표준편차로 행(=항목) 분할."""
    px0, py0, px1, py1 = bbox
    panel = after[py0:py1, px0:px1]
    gray = cv2.cvtColor(panel, cv2.COLOR_BGR2GRAY)
    strip = gray[:, 6:46].astype(float)
    prof = np.convolve(strip.std(axis=1), np.ones(3)/3, mode="same")
    thr = max(8.0, prof.mean() * 0.8)
    content = prof > thr
    bands, s = [], None
    for i, c in enumerate(content):
        if c and s is None:
            s = i
        elif not c and s is not None:
            bands.append([s, i]); s = None
    if s is not None:
        bands.append([s, len(content)])
    merged = []
    for b in bands:
        if merged and b[0] - merged[-1][1] < 6:
            merged[-1][1] = b[1]
        else:
            merged.append(list(b))
    return [(a, b) for a, b in merged if b - a >= 10]

def _open_and_capture(engine, trigger_center):
    """빈 바탕화면 클릭으로 정리 → 트리거 클릭(메뉴 오픈) → before/after 반환."""
    engine.dismiss()
    before = engine.screenshot(3)
    engine.click(*trigger_center)
    after = engine.screenshot(4)
    return before, after

def discover_submenu(engine, registry, trigger, prefix, close_key=0x29):
    """trigger 객체를 클릭 → 나타난 항목들을 신규 객체로 등록 + 클릭 워크플로우 생성.
    반환: {panel, items:[{name,center,has_submenu}], annotated}"""
    tt = registry.template(trigger)
    engine.dismiss()  # 이전 팝업 정리(닫힌 상태 보장)
    f = engine.find(tt, thr=0.5) if tt is not None else None
    if not f:
        return None
    tc = f["center"]

    rows, before, after, bbox = [], None, None, None
    for attempt in range(2):  # 메뉴가 안 열리면 1회 재시도
        before, after = _open_and_capture(engine, tc)
        diff = (np.abs(before.astype(int) - after.astype(int)).sum(2) > 40)
        region = np.zeros(diff.shape, dtype=bool); region[90:, :430] = True
        ys, xs = np.nonzero(diff & region)
        if len(xs) < 20:
            continue
        px0, px1, py0, py1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        bbox = (px0, py0, px1, py1)
        rows = _segment_rows(after, bbox)
        if len(rows) >= 3:   # 정상 오픈으로 판단
            break
        engine.dismiss()     # 토글로 닫혔을 수 있음 → 정리 후 재시도
    if not rows or bbox is None:
        engine.dismiss()
        return None
    px0, py0, px1, py1 = bbox

    items = []
    ann = after.copy()
    cv2.rectangle(ann, (px0, py0), (px1, py1), (255, 0, 0), 1)
    for k, (a, b) in enumerate(rows):
        y0, y1 = py0 + a, py0 + b
        cy, cx = (y0 + y1) // 2, (px0 + px1) // 2
        crop = after[max(0, y0-3):y1+3, px0:px1].copy()
        rc = cv2.cvtColor(after[y0:y1, max(0, px1-22):px1], cv2.COLOR_BGR2GRAY)
        has_sub = bool((cv2.Canny(rc, 40, 120) > 0).sum() > 8)
        name = f"{prefix}_{k:02d}"
        registry.add(name, crop, {"kind": "menu_item", "click": [cx, cy],
                                   "has_submenu": has_sub, "from": trigger})
        wf = {"name": f"click_{name}", "goal": f"{trigger} > {name} 클릭",
              "steps": [
                  {"action": "click", "object": trigger},
                  {"action": "wait", "sec": 0.5},
                  {"action": "click", "object": name},
                  {"action": "wait", "sec": 0.6},
                  {"action": "screenshot", "label": "result"}]}
        workflow.save_workflow(wf)
        items.append({"name": name, "center": [cx, cy], "has_submenu": has_sub})
        cv2.rectangle(ann, (px0, y0), (px1, y1), (0, 0, 255), 1)
        cv2.putText(ann, name, (px1 + 4, cy + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    engine.dismiss()  # 메뉴 닫기(마우스 기반)
    return {"panel": (px0, py0, px1, py1), "items": items, "annotated": ann}
