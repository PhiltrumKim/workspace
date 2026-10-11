# -*- coding: utf-8 -*-
"""캡처카드(Magewell 등 UVC/DirectShow 장치) 영상 입력 (VideoSource 구현)."""
from __future__ import annotations

import time
from typing import Optional, Tuple

import cv2
import numpy as np

from .base import DeviceError, VideoSource

_BACKENDS = {"default": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}


class CaptureVideo(VideoSource):
    def __init__(self, index: int = 0, width: int = 1920, height: int = 1080,
                 backend: str = "default", flush: int = 2):
        self.index = index
        self.width = width
        self.height = height
        self.backend = backend
        self.flush = flush            # read() 시 버려서 최신 프레임을 얻을 grab 횟수
        self.cap = None

    def open(self) -> None:
        self.cap = cv2.VideoCapture(self.index, _BACKENDS[self.backend])
        if not self.cap.isOpened():
            raise DeviceError(f"캡처 장치 {self.index} 열기 실패")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        time.sleep(0.5)
        if self.read() is None:
            raise DeviceError(f"캡처 장치 {self.index} 에서 영상이 들어오지 않음")

    def read(self) -> Optional[np.ndarray]:
        if self.cap is None:
            return None
        for _ in range(self.flush):
            self.cap.grab()
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    @property
    def size(self) -> Tuple[int, int]:
        if self.cap is not None:
            return (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        return (self.width, self.height)
