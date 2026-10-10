# -*- coding: utf-8 -*-
"""FrameHub: 캡처 장치를 백그라운드 스레드 하나가 전담해 계속 읽는 VideoSource 래퍼.

- 엔진(커서 실측·인식)은 read() 로 '호출 이후에 캡처된' 최신 프레임을 받는다
  (직접 읽을 때처럼 버퍼에 쌓인 오래된 프레임을 받지 않는다).
- 블랙박스 녹화기 등 구독자(listener)는 모든 프레임을 (시각, 프레임)으로 받는다.
- 캡처 장치를 여러 곳에서 동시에 읽지 않으므로 OpenCV VideoCapture 스레드 안전 문제가 없다.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

import numpy as np

from .base import VideoSource

Listener = Callable[[float, np.ndarray], None]


class FrameHub(VideoSource):
    def __init__(self, source: VideoSource, max_fps: float = 30.0, log=None):
        self.source = source
        self.min_interval = 1.0 / max_fps if max_fps else 0.0
        self.listeners: List[Listener] = []
        self.log = log or (lambda m: None)
        self._cond = threading.Condition()
        self._latest: Optional[np.ndarray] = None
        self._latest_t = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.frames = 0
        self.errors = 0

    # VideoSource -------------------------------------------------------
    def open(self) -> None:
        if hasattr(self.source, "flush"):
            self.source.flush = 0                   # 연속으로 읽으므로 버퍼 비우기 불필요
        self.source.open()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="FrameHub", daemon=True)
        self._thread.start()
        self.read(timeout=3.0)                      # 첫 프레임 확보

    def read(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """호출 시각 이후에 '캡처를 시작한' 프레임을 기다려 반환. 시간 초과 시 마지막 프레임.
        (캡처가 끝난 시각으로 판단하면, 호출 직전에 찍기 시작한 = 직전 상태의 프레임을 넘길 수 있다.
         시뮬레이터에서 커서 실측이 흔들기 크기 8px 만큼 틀리는 간헐 오류로 확인)"""
        t_call = time.monotonic()
        with self._cond:
            self._cond.wait_for(lambda: self._latest_t >= t_call or self._stop.is_set(), timeout)
            return None if self._latest is None else self._latest.copy()

    def close(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.source.close()

    @property
    def size(self) -> Tuple[int, int]:
        return self.source.size

    # 내부 ---------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                f = self.source.read()
            except Exception as e:                  # 장치 오류: 기록하고 계속 시도
                self.errors += 1
                if self.errors in (1, 10, 100):
                    self.log(f"[hub] 캡처 오류 {self.errors}회: {e!r}")
                time.sleep(0.1)
                continue
            if f is None:
                self.errors += 1
                time.sleep(0.02)
                continue
            ts = t0                                 # 캡처 시작 시각 (read 판단 기준)
            with self._cond:
                self._latest, self._latest_t = f, ts
                self.frames += 1
                self._cond.notify_all()
            for fn in list(self.listeners):
                try:
                    fn(ts, f)
                except Exception as e:
                    self.log(f"[hub] listener 오류: {e!r}")
            wait = self.min_interval - (time.monotonic() - t0)
            if wait > 0:
                self._stop.wait(wait)
