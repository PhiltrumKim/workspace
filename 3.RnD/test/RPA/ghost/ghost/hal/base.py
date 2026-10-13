# -*- coding: utf-8 -*-
"""하드웨어 추상화 계층(HAL) 인터페이스.

GHOST 엔진은 이 두 인터페이스만 사용한다. 실장비(Magewell + TX-RelayBoard)와
시뮬레이터가 같은 인터페이스를 구현하므로 상위 로직은 장비 유무와 무관하게 동작한다.

좌표/단위 규약
  - VideoSource.read() 는 BGR uint8 프레임(H x W x 3)을 반환한다. 모든 화면 좌표는 이 프레임 픽셀 기준.
  - HidOutput.mouse_move() 는 상대 이동(mickey) 1회 보고. |dx|,|dy| <= max_step.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

import numpy as np

LEFT, RIGHT, MIDDLE = 1, 2, 4


class DeviceError(RuntimeError):
    """장치(캡처·입력) 통신 오류. 운영 실행기는 이 오류를 '장치 오류'로 분류해 재연결을 시도한다."""


class VideoSource(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> Optional[np.ndarray]:
        """가능한 한 최신 프레임을 반환(버퍼에 쌓인 오래된 프레임은 버린다). 실패 시 None."""

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def size(self) -> Tuple[int, int]:
        """(width, height)"""


class HidOutput(ABC):
    max_step: int = 127

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def mouse_move(self, dx: int, dy: int, buttons: int = 0) -> None:
        """상대 이동 1회 + 버튼 상태(LEFT|RIGHT|MIDDLE 비트마스크)."""

    def mouse_wheel(self, notch: int, buttons: int = 0) -> None:
        """휠 한 칸 (+1 위, -1 아래)."""
        raise NotImplementedError("이 장치는 휠을 지원하지 않음")

    @abstractmethod
    def key(self, vk: int, scan: int, extended: bool, up: bool, modifiers: int = 0) -> None:
        """키 1회 이벤트. vk=Windows Virtual-Key, scan=PS/2 Set1 make code."""
