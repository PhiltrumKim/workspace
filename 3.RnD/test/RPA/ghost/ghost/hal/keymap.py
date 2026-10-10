# -*- coding: utf-8 -*-
"""키 이름 → (Windows VK, PS/2 Set1 make code, 확장키 여부).

RelayBoard 키보드 패킷은 VK와 Set1 make code를 함께 받는다(MiTx C++ 와 동일).
문자 입력은 US 배열 기준이며 한글 등 비ASCII 문자는 IME 경유가 필요해 지원하지 않는다.
"""
from __future__ import annotations

from typing import Dict, NamedTuple, Tuple


class Key(NamedTuple):
    vk: int
    scan: int
    extended: bool = False


KEYS: Dict[str, Key] = {}

# 알파벳: VK = 대문자 ASCII
_LETTER_SCAN = {
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
}
for _c, _s in _LETTER_SCAN.items():
    KEYS[_c] = Key(ord(_c.upper()), _s)

# 숫자열: VK = ASCII, scan 0x02('1') ~ 0x0B('0')
for _i, _c in enumerate("1234567890"):
    KEYS[_c] = Key(ord(_c), 0x02 + _i)

# F1~F12
for _i in range(10):
    KEYS[f"f{_i + 1}"] = Key(0x70 + _i, 0x3B + _i)
KEYS["f11"] = Key(0x7A, 0x57)
KEYS["f12"] = Key(0x7B, 0x58)

KEYS.update({
    "esc": Key(0x1B, 0x01), "enter": Key(0x0D, 0x1C), "tab": Key(0x09, 0x0F),
    "backspace": Key(0x08, 0x0E), "space": Key(0x20, 0x39), "capslock": Key(0x14, 0x3A),
    # 수식키 (VK는 C++ 키클리어 테이블과 동일하게 일반 VK 사용)
    "shift": Key(0x10, 0x2A), "rshift": Key(0x10, 0x36),
    "ctrl": Key(0x11, 0x1D), "rctrl": Key(0x11, 0x1D, True),
    "alt": Key(0x12, 0x38), "ralt": Key(0x12, 0x38, True),
    "win": Key(0x5B, 0x5B, True), "menu": Key(0x5D, 0x5D, True),
    # 편집/이동 (확장키)
    "insert": Key(0x2D, 0x52, True), "delete": Key(0x2E, 0x53, True),
    "home": Key(0x24, 0x47, True), "end": Key(0x23, 0x4F, True),
    "pageup": Key(0x21, 0x49, True), "pagedown": Key(0x22, 0x51, True),
    "up": Key(0x26, 0x48, True), "down": Key(0x28, 0x50, True),
    "left": Key(0x25, 0x4B, True), "right": Key(0x27, 0x4D, True),
    # 구두점 (US)
    "-": Key(0xBD, 0x0C), "=": Key(0xBB, 0x0D), "[": Key(0xDB, 0x1A), "]": Key(0xDD, 0x1B),
    "\\": Key(0xDC, 0x2B), ";": Key(0xBA, 0x27), "'": Key(0xDE, 0x28), "`": Key(0xC0, 0x29),
    ",": Key(0xBC, 0x33), ".": Key(0xBE, 0x34), "/": Key(0xBF, 0x35),
})

ALIASES = {
    "escape": "esc", "return": "enter", "del": "delete", "ins": "insert", "pgup": "pageup", "pgdn": "pagedown",
    "control": "ctrl", "lctrl": "ctrl", "lshift": "shift", "lalt": "alt", "lwin": "win", "windows": "win",
    " ": "space", "\n": "enter", "\t": "tab",
}

# USB HID modifier 비트 (RelayBoard 패킷 #5)
MODIFIER_BITS = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "win": 0x08,
                 "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40}

_SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";", '"': "'", "~": "`", "<": ",", ">": ".", "?": "/",
}

# 레거시 워크플로우의 USB HID usage 코드 → 키 이름 (마이그레이션용)
USB_HID_TO_NAME = {0x28: "enter", 0x29: "esc", 0x2A: "backspace", 0x2B: "tab", 0x2C: "space",
                   0x4F: "right", 0x50: "left", 0x51: "down", 0x52: "up",
                   0x4A: "home", 0x4D: "end", 0x4C: "delete"}
USB_HID_TO_NAME.update({0x04 + i: chr(ord("a") + i) for i in range(26)})
USB_HID_TO_NAME.update({0x1E + i: "1234567890"[i] for i in range(10)})
USB_HID_TO_NAME.update({0x3A + i: f"f{i + 1}" for i in range(12)})


def normalize(name: str) -> str:
    if name in ALIASES:
        return ALIASES[name]
    n = name.lower() if len(name) > 1 else name
    return ALIASES.get(n, n)


def key(name: str) -> Key:
    n = normalize(name)
    if n not in KEYS:
        raise KeyError(f"unknown key: {name!r}")
    return KEYS[n]


def char_to_key(ch: str) -> Tuple[str, bool]:
    """문자 1개 → (키 이름, shift 필요 여부)."""
    if ch in ALIASES:
        return ALIASES[ch], False
    if "A" <= ch <= "Z":
        return ch.lower(), True
    if ch in _SHIFTED:
        return _SHIFTED[ch], True
    if ch in KEYS:
        return ch, False
    raise ValueError(f"cannot type character {ch!r} (ASCII/US layout only)")
