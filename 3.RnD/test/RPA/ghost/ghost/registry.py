# -*- coding: utf-8 -*-
"""GUI 대상(target) 레지스트리: 템플릿 PNG + objects.json.

objects.json 항목:
  {"file": "start_btn.png",
   "threshold": 0.8,            (선택) 매칭 임계값
   "region": [x, y, w, h],      (선택) 탐색 영역 제한
   "click_offset": [dx, dy],    (선택) 매칭 중심 대비 클릭 위치 보정
   "hint": [x, y],              (선택) 템플릿 미검출 시 폴백 좌표 (스텝에 allow_hint 필요)
   "color_tol": 25}             (선택) 색 검증 허용치 — 배경색으로 상태를 구분하는 target 에 사용
텍스트(OCR) target 은 file 대신 "text" 를 둔다: {"text": "저장 안 함", "region": [...], "match": "contains"}
레거시(magewell_rpa) objects.json 의 "click" 키는 hint 로 읽는다.
"""
from __future__ import annotations

import json
import os
from typing import Dict, Optional

import cv2
import numpy as np


class Registry:
    def __init__(self, root: str):
        self.root = root
        self.index = os.path.join(root, "objects.json")
        self.targets: Dict[str, dict] = {}
        self._cache: Dict[str, np.ndarray] = {}
        if os.path.exists(self.index):
            with open(self.index, encoding="utf-8") as f:
                self.targets = json.load(f)
            for rec in self.targets.values():
                if "hint" not in rec and "click" in rec:
                    rec["hint"] = rec["click"]

    def __contains__(self, name: str) -> bool:
        return name in self.targets

    def names(self):
        return sorted(self.targets)

    def get(self, name: str) -> dict:
        if name not in self.targets:
            raise KeyError(f"unknown target: {name!r}")
        return self.targets[name]

    def template(self, name: str) -> Optional[np.ndarray]:
        if name not in self._cache:
            if "file" not in self.get(name):          # 텍스트 target
                return None
            path = os.path.join(self.root, self.get(name)["file"])
            img = cv2.imread(path) if os.path.exists(path) else None
            if img is None:
                return None
            self._cache[name] = img
        return self._cache[name]

    def add(self, name: str, img: np.ndarray, **meta) -> dict:
        os.makedirs(self.root, exist_ok=True)
        fn = f"{name}.png"
        cv2.imwrite(os.path.join(self.root, fn), img)
        rec = {"file": fn, "w": int(img.shape[1]), "h": int(img.shape[0])}
        rec.update({k: v for k, v in meta.items() if v is not None})
        self.targets[name] = rec
        self._cache[name] = img
        self.save()
        return rec

    def add_text(self, name: str, text: str, **meta) -> dict:
        rec = {"text": text}
        rec.update({k: v for k, v in meta.items() if v is not None})
        self.targets[name] = rec
        self._cache.pop(name, None)
        self.save()
        return rec

    def save(self) -> None:
        os.makedirs(self.root, exist_ok=True)
        with open(self.index, "w", encoding="utf-8") as f:
            json.dump(self.targets, f, ensure_ascii=False, indent=2)
