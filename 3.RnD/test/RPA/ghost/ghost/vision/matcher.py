# -*- coding: utf-8 -*-
"""템플릿 매칭 기반 GUI 요소 탐색."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]  # x, y, w, h


@dataclass
class Match:
    box: Box
    score: float
    scale: float = 1.0

    @property
    def center(self) -> Tuple[int, int]:
        x, y, w, h = self.box
        return (x + w // 2, y + h // 2)


def find(frame: np.ndarray, template: np.ndarray, threshold: float = 0.6,
         region: Optional[Box] = None, scales: Sequence[float] = (1.0,),
         color_tol: Optional[float] = None) -> Optional[Match]:
    """frame 에서 template 의 최고점 위치. score < threshold 면 None.

    region: 탐색 영역(x,y,w,h). scales: 템플릿 배율 후보(해상도/DPI 차이 대응).
    color_tol: 매칭 위치의 픽셀 평균 색 차이(0~255) 허용치. TM_CCOEFF_NORMED 는 밝기/색 평균을 빼고
      비교하므로 배경색만 다른 상태(선택 행, 상태 램프 등)를 구분하지 못한다 → 색 차이로 추가 검증.
    """
    ox = oy = 0
    search = frame
    if region is not None:
        rx, ry, rw, rh = region
        rx, ry = max(0, rx), max(0, ry)
        search = frame[ry:ry + rh, rx:rx + rw]
        ox, oy = rx, ry
    best: Optional[Match] = None
    for s in scales:
        t = template if s == 1.0 else cv2.resize(template, None, fx=s, fy=s,
                                                 interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        th, tw = t.shape[:2]
        if search.shape[0] < th or search.shape[1] < tw:
            continue
        res = cv2.matchTemplate(search, t, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if not np.isfinite(score):
            continue
        if best is None or score > best.score:
            best = Match((loc[0] + ox, loc[1] + oy, tw, th), float(score), s)
            best_t = t
    if best is None or best.score < threshold:
        return None
    if color_tol is not None:
        x, y, w, h = best.box
        patch = frame[y:y + h, x:x + w].astype(np.int16)
        if np.abs(patch - best_t.astype(np.int16)).mean() > color_tol:
            return None
    best.score = round(best.score, 3)
    return best
