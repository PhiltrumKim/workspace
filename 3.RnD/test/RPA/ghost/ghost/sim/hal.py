# -*- coding: utf-8 -*-
"""시뮬레이터 HAL: 가상 화면 + 가상 커서로 VideoSource/HidOutput 을 구현.

실장비에서 관찰된 비이상성을 재현할 수 있다.
  offset : 캡처 오버스캔으로 화면(0,0)이 프레임의 (ox,oy)에 찍히는 현상 (실장비 약 48,48)
  gain   : mickey → 화면 px 배율 (OS 포인터 속도 설정)
  accel  : 이동 속도 비례 가속 (Windows '포인터 정확도 향상')
  noise  : 캡처 노이즈 표준편차
  desktop_icon : 좌상단 바탕화면 아이콘 + 호버 하이라이트 (Windows 바탕화면 재현)
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from ..hal.base import DeviceError, HidOutput, VideoSource
from ..hal.relayboard import key_packet, mouse_packet
from .app import DemoEquipmentApp

# 바탕화면 아이콘 셀(화면 좌표). 커서가 들어오면 테두리 하이라이트 + 라벨 배경이 바뀐다
ICON_CELL = (4, 2, 73, 87)
ICON_LABEL = (14, 66, 52, 14)

_CURSOR = np.array([(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)], np.int32)


class SimWorld:
    def __init__(self, app=None, offset: Tuple[int, int] = (0, 0), gain: Tuple[float, float] = (1.0, 1.0),
                 accel: float = 0.0, noise: float = 0.0, seed: int = 0, desktop_icon: bool = False):
        self.app = app or DemoEquipmentApp()
        self.w, self.h = self.app.w, self.app.h
        self.offset = offset
        self.gain = gain
        self.accel = accel
        self.noise = noise
        self.desktop_icon = desktop_icon
        self.signal = True              # False: 영상 끊김(검은 화면) 재현
        # 장애 주입 (운영 자동 복구 시험): hid_fail/video_fail 이면 통신 오류. 장치를 다시 열면 해소
        # (stubborn > 0 이면 그 횟수만큼 다시 열어도 해소되지 않음)
        self.hid_fail = False
        self.video_fail = False
        self.stubborn = 0
        self.opens = 0
        self.rng = np.random.default_rng(seed)
        self.cx, self.cy = self.w / 2, self.h / 2   # 커서(화면 좌표)
        self.buttons = 0
        self.packets: List[bytes] = []               # 실장비와 동일한 패킷 기록(검증용)

    def _reopen(self) -> None:
        self.opens += 1
        if self.stubborn > 0 and (self.hid_fail or self.video_fail):
            self.stubborn -= 1
            raise DeviceError("Sim: 장치가 아직 복구되지 않음 (주입)")
        self.hid_fail = self.video_fail = False

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
        if not self.signal:
            return np.zeros((self.h, self.w, 3), np.uint8)
        img = self.app.render()
        if self.desktop_icon:
            self._draw_icon(img)
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


    def _draw_icon(self, img: np.ndarray) -> None:
        x, y, w, h = ICON_CELL
        lx, ly, lw, lh = ICON_LABEL
        cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), (30, 30, 30), -1)
        cv2.rectangle(img, (18, 12), (61, 55), (200, 120, 40), -1)          # 아이콘 그림
        if x <= self.cx < x + w and y <= self.cy < y + h:                  # 호버
            cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), (230, 190, 120), 1)
            cv2.rectangle(img, (lx, ly), (lx + lw - 1, ly + lh - 1), (120, 80, 50), -1)
        cv2.putText(img, "PC", (30, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (240, 240, 240), 1)


class SimVideo(VideoSource):
    def __init__(self, world: SimWorld):
        self.world = world

    def open(self) -> None:
        self.world._reopen()

    def read(self) -> Optional[np.ndarray]:
        if self.world.video_fail:
            return None
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
        if self.world.hid_fail:
            raise DeviceError("SimHid: 통신 오류 (주입)")
        dx = max(-127, min(127, dx))
        dy = max(-127, min(127, dy))
        self.world.packets.append(mouse_packet(dx, dy, buttons))
        self.world.move(dx, dy, buttons)

    def key(self, vk: int, scan: int, extended: bool, up: bool, modifiers: int = 0) -> None:
        if self.world.hid_fail:
            raise DeviceError("SimHid: 통신 오류 (주입)")
        self.world.packets.append(key_packet(vk, scan, extended, up, modifiers))
        self.world.app.key(vk, scan, extended, up, modifiers)
