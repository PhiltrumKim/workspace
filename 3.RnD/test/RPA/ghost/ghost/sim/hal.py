# -*- coding: utf-8 -*-
"""시뮬레이터 HAL: 가상 화면 + 가상 커서로 VideoSource/HidOutput 을 구현.

실장비에서 관찰된 비이상성을 재현할 수 있다.
  offset : 캡처 오버스캔으로 화면(0,0)이 프레임의 (ox,oy)에 찍히는 현상 (실장비 약 48,48)
  gain   : mickey → 화면 px 배율 (OS 포인터 속도 설정)
  accel  : 이동 속도 비례 가속 (Windows '포인터 정확도 향상')
  noise  : 캡처 노이즈 표준편차
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..hal.base import HidOutput, VideoSource
from ..hal.relayboard import key_packet, mouse_packet
from .app import DemoEquipmentApp

_CURSOR = np.array([(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)], np.int32)


class SimWorld:
    def __init__(self, app=None, offset: Tuple[int, int] = (0, 0), gain: Tuple[float, float] = (1.0, 1.0),
                 accel: float = 0.0, noise: float = 0.0, seed: int = 0):
        self.app = app or DemoEquipmentApp()
        self.w, self.h = self.app.w, self.app.h
        self.offset = offset
        self.gain = gain
        self.accel = accel
        self.noise = noise
        self.rng = np.random.default_rng(seed)
        self.cx, self.cy = self.w / 2, self.h / 2   # 커서(화면 좌표)
        self.buttons = 0
        self.packets: List[bytes] = []               # 실장비와 동일한 패킷 기록(검증용)

    def cursor_frame_pos(self) -> Tuple[int, int]:
        return (int(self.cx) + self.offset[0], int(self.cy) + self.offset[1])

    def move(self, dx: int, dy: int, buttons: int):
        k = 1.0 + self.accel * min(1.0, max(abs(dx), abs(dy)) / 127.0)
        self.cx = min(max(self.cx + dx * self.gain[0] * k, 0), self.w - 1)
        self.cy = min(max(self.cy + dy * self.gain[1] * k, 0), self.h - 1)
        pressed = buttons & ~self.buttons
        self.buttons = buttons
        for bit in (1, 2, 4):
            if pressed & bit:
                self.app.click(int(self.cx), int(self.cy), bit)

    def render(self) -> np.ndarray:
        img = self.app.render()
        pts = _CURSOR + np.array([int(self.cx), int(self.cy)], np.int32)
        cv2.fillPoly(img, [pts], (255, 255, 255))
        cv2.polylines(img, [pts], True, (0, 0, 0), 1)
        ox, oy = self.offset
        frame = np.zeros_like(img)
        frame[oy:, ox:] = img[:self.h - oy, :self.w - ox]
        if self.noise:
            n = self.rng.normal(0, self.noise, frame.shape)
            frame = np.clip(frame.astype(np.float32) + n, 0, 255).astype(np.uint8)
        return frame


class SimVideo(VideoSource):
    def __init__(self, world: SimWorld):
        self.world = world

    def open(self) -> None:
        pass

    def read(self) -> Optional[np.ndarray]:
        return self.world.render()

    def close(self) -> None:
        pass

    @property
    def size(self) -> Tuple[int, int]:
        return (self.world.w, self.world.h)


class SimHid(HidOutput):
    max_step = 127

    def __init__(self, world: SimWorld):
        self.world = world

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def mouse_move(self, dx: int, dy: int, buttons: int = 0) -> None:
        dx = max(-127, min(127, dx))
        dy = max(-127, min(127, dy))
        self.world.packets.append(mouse_packet(dx, dy, buttons))
        self.world.move(dx, dy, buttons)

    def key(self, vk: int, scan: int, extended: bool, up: bool, modifiers: int = 0) -> None:
        self.world.packets.append(key_packet(vk, scan, extended, up, modifiers))
        self.world.app.key(vk, scan, extended, up, modifiers)
