# -*- coding: utf-8 -*-
"""블랙박스 레코더: 실행별 이벤트 로그(JSONL) + 화면 프레임.

runs/<YYYYmmdd_HHMMSS>_<scenario>/
  events.jsonl   {"t": 경과초, "kind": ..., ...}
  NNN_<label>.png
  clipNN_<label>.mp4   (영상 녹화기 연결 시: 이벤트 전후 영상)
  run.mp4              (continuous 녹화 시)
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Optional

import cv2


class Blackbox:
    def __init__(self, root: str, recorder=None):
        self.root = root
        self.recorder = recorder
        self.dir: Optional[str] = None
        self._f = None
        self._t0 = 0.0
        self._n = 0

    def start(self, name: str) -> str:
        safe = re.sub(r"[^\w.-]+", "_", name)
        self.dir = os.path.join(self.root, f"{datetime.now():%Y%m%d_%H%M%S}_{safe}")
        os.makedirs(self.dir, exist_ok=True)
        self._f = open(os.path.join(self.dir, "events.jsonl"), "a", encoding="utf-8")
        self._t0 = time.monotonic()
        self._n = 0
        self.event("run_start", scenario=name)
        if self.recorder is not None:
            self._saved0 = len(self.recorder.saved)
            self.recorder.begin(self.dir)
        return self.dir

    def annotate(self, text: str) -> None:
        """영상에 표시할 현재 상태(스텝)."""
        if self.recorder is not None:
            self.recorder.annotate(text)

    def clip(self, label: str, reason: str = "") -> Optional[str]:
        """이벤트 전후 영상 클립 저장 예약."""
        if self.recorder is None or not self.dir:
            return None
        p = self.recorder.trigger(label, reason)
        if p:
            self.event("clip", file=os.path.basename(p), label=label, reason=reason)
        return p

    def event(self, kind: str, **data) -> None:
        if not self._f:
            return
        rec = {"t": round(time.monotonic() - self._t0, 3), "kind": kind, **data}
        self._f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self._f.flush()

    def frame(self, img, label: str) -> Optional[str]:
        if not self.dir or img is None:
            return None
        self._n += 1
        safe = re.sub(r"[^\w.-]+", "_", label)
        p = os.path.join(self.dir, f"{self._n:03d}_{safe}.png")
        cv2.imwrite(p, img)
        self.event("frame", file=os.path.basename(p), label=label)
        return p

    def end(self, ok: bool, **data) -> None:
        if self.recorder is not None and self.dir:
            self.recorder.end()                     # 진행 중 클립 마무리 (파일 쓰기 완료까지 대기)
            files = [os.path.basename(p) for p in self.recorder.saved[self._saved0:]]
            if files:
                self.event("video", files=files)
        self.event("run_end", ok=ok, **data)
        if self._f:
            self._f.close()
            self._f = None


class NullBlackbox(Blackbox):
    def __init__(self):
        super().__init__("")

    def start(self, name: str) -> str:
        return ""
