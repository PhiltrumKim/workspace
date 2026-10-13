# -*- coding: utf-8 -*-
"""Locator: target 을 화면에서 찾는 공용 계층 (실행기·감시가 함께 사용).

target 지정 방법
  "start_btn"                                   레지스트리 이름 (템플릿 또는 텍스트 항목)
  {"text": "저장 안 함", "region": [x,y,w,h],    텍스트(OCR) — 인라인 지정
   "match": "contains", "scale": 2,             match: exact | contains(기본) | regex | fuzzy
   "line": true,                                line: 영역을 한 줄로 바로 인식 (좁은 버튼·수치창, 생략 시 높이≤40 자동)
   "vote": true,                                vote: 다수결 판독 결과로 비교 (세그먼트 숫자 표시창)
   "axis": "1-13",                              axis: 축 라벨(웨이퍼 맵 A~M·1~13 등) — 읽힌 라벨로 못 읽은 라벨 위치도 추정
   "anchor": "dlg_title", "offset": [dx,dy,w,h]} anchor: 다른 target(보통 빠른 템플릿)을 먼저 찾고 그 좌상단 기준
                                                상대 영역에서만 OCR — 위치가 바뀌는 대화상자도 작은 영역 OCR 로 빠르게

레지스트리(objects.json)에 템플릿 대신 "text" 를 가진 항목을 두면 이름으로도 텍스트 target 을 쓸 수 있다.
  "dont_save": {"text": "저장 안 함", "region": [900, 500, 200, 60]}
"""
from __future__ import annotations

from typing import Optional, Union

import numpy as np

from .registry import Registry
from .vision import Match, find
from .vision.ocr import MODES, OcrEngine

Target = Union[str, dict]


def is_text_spec(spec: dict) -> bool:
    return "text" in spec


def describe(target: Target) -> str:
    if isinstance(target, str):
        return target
    return f'"{target["text"]}"' + (f"@{target['region']}" if target.get("region") else "")


class Locator:
    def __init__(self, registry: Registry, cfg: dict, log=None):
        self.reg = registry
        self.cfg = cfg
        self.log = log or (lambda m: None)
        self._ocr: Optional[OcrEngine] = None

    @property
    def ocr(self) -> OcrEngine:
        if self._ocr is None:
            self._ocr = OcrEngine(self.cfg, self.cfg.get("_base_dir", "."), self.log)
        return self._ocr

    def spec(self, target: Target) -> dict:
        """target → 통합 사양 dict (레지스트리 항목이면 그 내용)."""
        return target if isinstance(target, dict) else self.reg.get(target)

    def validate(self, target: Target) -> Optional[str]:
        if isinstance(target, str):
            return None if target in self.reg else f"등록되지 않은 target '{target}'"
        if not isinstance(target, dict) or not is_text_spec(target):
            return f"target 형식 오류: {target!r}"
        if target.get("match", "contains") not in MODES:
            return f"알 수 없는 match '{target.get('match')}'"
        if target.get("anchor"):
            if len(target.get("offset", [])) != 4:
                return "anchor 사용 시 offset [dx,dy,w,h] 필요"
            return self.validate(target["anchor"])
        return None

    def _axis(self, spec: dict, frame: np.ndarray, region) -> Optional[Match]:
        """축 라벨 대상: {"text": "5", "axis": "1-13", "region": [...]} — 읽힌 라벨로 못 읽은 라벨 위치까지 추정."""
        from .vision.ocr import axis_labels, axis_locate
        if region is None:
            raise ValueError("axis 대상은 region 필요")
        x, y, w, h = region
        orient = spec.get("orient") or ("h" if w >= h else "v")
        hits = self.ocr.read(frame, region, scale=spec.get("scale"), line=spec.get("line"))
        r = axis_locate(hits, axis_labels(spec["axis"]), str(spec["text"]), orient)
        if r is None:
            return None
        (px, py), ratio, direct = r
        if ratio < spec.get("min_found", 0.3):
            return None
        return Match((px - 4, py - 4, 9, 9), round(ratio if not direct else max(ratio, 0.9), 3))

    def locate(self, target: Target, frame: np.ndarray, **overrides) -> Optional[Match]:
        spec = {**self.spec(target), **{k: v for k, v in overrides.items() if v is not None}}
        region = tuple(spec["region"]) if spec.get("region") else None
        if is_text_spec(spec) and spec.get("anchor"):
            a = self.locate(spec["anchor"], frame)
            if a is None:
                return None
            dx, dy, w, h = spec["offset"]
            region = (a.box[0] + dx, a.box[1] + dy, w, h)
        if is_text_spec(spec) and spec.get("axis"):
            return self._axis(spec, frame, region)
        if is_text_spec(spec):
            if region is None and not getattr(self, "_warned", {}).get(str(target)):
                self._warned = {**getattr(self, "_warned", {}), str(target): True}
                self.log(f"[ocr] {describe(target)}: region/anchor 없음 → 전체 화면 OCR (~2.6s). 영역 지정 권장")
            hit = self.ocr.find_text(frame, spec["text"], region=region, mode=spec.get("match", "contains"),
                                     min_ratio=spec.get("min_ratio", 0.9), scale=spec.get("scale"),
                                     line=spec.get("line"), vote=spec.get("vote", False))
            return Match(hit.box, hit.conf) if hit else None
        tmpl = self.reg.template(target)
        if tmpl is None:
            raise FileNotFoundError(f"target '{target}' 템플릿 파일 없음")
        return find(frame, tmpl,
                    threshold=spec.get("threshold", self.cfg["vision"]["threshold"]),
                    region=region,
                    scales=spec.get("scales", self.cfg["vision"]["scales"]),
                    color_tol=spec.get("color_tol"))
