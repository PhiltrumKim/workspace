# -*- coding: utf-8 -*-
"""TX-RelayBoard 시리얼 프로토콜 (HidOutput 구현).

근거: [20250310]TX_RelayBoard_Protocol.pptx, MiTx C++ (MiTxEngine/DefMouseSerial.h, TcpServer.cpp)
패킷: 12바이트 고정 [00 00 00 00][CMD][#5..#10][FF]

키보드 (C++ TcpServer.cpp 와 동일한 배치)
  #5 USB modifier 비트마스크 / #6 Windows VK / #7 flag(bit0=Up, bit1=확장키 E0) / #8 PS/2 Set1 make code
  ※ 레거시 Python(magewell_rpa)은 #6(VK)을 0으로 보내고 USB HID 코드를 make code 자리에 넣는 경우가 있었다.

마우스 (Mouse Format 2.0)
  #5 0x00 / #6 0x08|sign|buttons / #7-#8 dx int16 LE / #9-#10 (-dy) int16 LE
  HW 검증(2026-07-05): 펌웨어는 #6 부호비트를 무시하고 int16 값만 사용. 명세 정합성 위해 설정한다.
"""
from __future__ import annotations

import struct
import time

from .base import DeviceError, HidOutput

CMD_MOUSE_SYNC = 0xE0
CMD_SW_INIT = 0xE1
CMD_ALIVE_ACK = 0xE2
CMD_INIT_ALL = 0xE3
CMD_KEYPAD_MODE = 0xF8
CMD_KEYBOARD = 0xFC
CMD_STATUS = 0xFD
CMD_MOUSE = 0xFE
CMD_MOUSE_MSTSC = 0xEE

MODE_LOCAL = 0x4C
MODE_REMOTE = 0x52

KEY_FLAG_UP = 0x01
KEY_FLAG_EXTENDED = 0x02


def packet(cmd: int, payload: bytes = b"") -> bytes:
    """#5부터 payload(최대 6바이트: #5~#10)를 채운 12바이트 패킷."""
    if len(payload) > 6:
        raise ValueError("payload > 6 bytes")
    buf = bytearray(12)
    buf[4] = cmd
    buf[5:5 + len(payload)] = payload
    buf[11] = 0xFF
    return bytes(buf)


def mouse_packet(dx: int, dy: int, buttons: int = 0, mstsc: bool = False) -> bytes:
    limit = 32767 if mstsc else 127
    dx = max(-limit, min(limit, int(dx)))
    dy = max(-limit, min(limit, int(dy)))
    sign = (0x10 if dx < 0 else 0) | (0x20 if dy > 0 else 0)
    b6 = 0x08 | sign | (buttons & 0x07)
    payload = bytes([0x00, b6]) + struct.pack("<hh", dx, -dy)
    return packet(CMD_MOUSE_MSTSC if mstsc else CMD_MOUSE, payload)


def key_packet(vk: int, scan: int, extended: bool, up: bool, modifiers: int = 0) -> bytes:
    flag = (KEY_FLAG_UP if up else 0) | (KEY_FLAG_EXTENDED if extended else 0)
    return packet(CMD_KEYBOARD, bytes([modifiers & 0xFF, vk & 0xFF, flag, scan & 0xFF, 0x00]))


def mode_packet(remote: bool) -> bytes:
    return packet(CMD_KEYPAD_MODE, bytes([MODE_REMOTE if remote else MODE_LOCAL]))


class RelayBoard(HidOutput):
    max_step = 127

    def __init__(self, port: str = "COM3", baudrate: int = 115200, tx_gap: float = 0.01,
                 log=None):
        self.port = port
        self.baudrate = baudrate
        self.tx_gap = tx_gap          # 패킷 간 최소 간격(보드 버퍼 오버플로 방지, 레거시 10ms)
        self.ser = None
        self._log = log or (lambda *a: None)

    def open(self) -> None:
        import serial  # 장비 없는 환경(시뮬레이터/테스트)에서 pyserial 없이도 import 가능하도록 지연 import
        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=0.1, write_timeout=1.0)
        except (serial.SerialException, OSError) as e:
            raise DeviceError(f"RelayBoard {self.port} 열기 실패: {e}")
        self._log(f"[relay] {self.port} open")
        self.send(mode_packet(remote=True))
        time.sleep(0.3)

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
            self._log("[relay] closed")
        self.ser = None

    def send(self, pkt: bytes) -> None:
        if not self.ser or not self.ser.is_open:
            raise DeviceError("RelayBoard 가 열려 있지 않음")
        try:
            self.ser.write(pkt)
        except Exception as e:                     # USB 분리, 쓰기 시간 초과 등
            raise DeviceError(f"RelayBoard 통신 오류: {e}")
        time.sleep(self.tx_gap)

    def set_remote(self, remote: bool = True) -> None:
        self.send(mode_packet(remote))

    def mouse_move(self, dx: int, dy: int, buttons: int = 0) -> None:
        self.send(mouse_packet(dx, dy, buttons))

    def key(self, vk: int, scan: int, extended: bool, up: bool, modifiers: int = 0) -> None:
        self.send(key_packet(vk, scan, extended, up, modifiers))
