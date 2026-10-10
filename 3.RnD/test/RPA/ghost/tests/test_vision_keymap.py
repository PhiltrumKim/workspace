import cv2
import numpy as np
import pytest

from ghost.hal import keymap
from ghost.vision import find


def _scene():
    img = np.full((400, 600, 3), 50, np.uint8)
    cv2.rectangle(img, (300, 200), (419, 249), (60, 150, 60), -1)
    cv2.putText(img, "START", (318, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (240, 240, 240), 2)
    return img


def test_find_basic_and_region():
    img = _scene()
    tmpl = img[200:250, 300:420].copy()
    m = find(img, tmpl)
    assert m.box == (300, 200, 120, 50) and m.center == (360, 225) and m.score > 0.99
    assert find(img, tmpl, region=(0, 0, 250, 400)) is None
    assert find(img, tmpl, region=(250, 150, 300, 200)).box == (300, 200, 120, 50)


def test_find_multiscale():
    img = _scene()
    tmpl = cv2.resize(img[200:250, 300:420], None, fx=1.25, fy=1.25)
    assert find(img, tmpl, threshold=0.9) is None
    m = find(img, tmpl, threshold=0.9, scales=(0.8, 1.0))
    assert m is not None and abs(m.center[0] - 360) <= 2 and m.scale == 0.8


def test_keymap_chars():
    assert keymap.char_to_key("A") == ("a", True)
    assert keymap.char_to_key("_") == ("-", True)
    assert keymap.char_to_key("7") == ("7", False)
    assert keymap.key("Escape") == keymap.key("esc")
    with pytest.raises(ValueError):
        keymap.char_to_key("한")
    with pytest.raises(KeyError):
        keymap.key("nokey")


def test_legacy_hid_codes():
    assert keymap.USB_HID_TO_NAME[0x29] == "esc"
    assert keymap.USB_HID_TO_NAME[0x04] == "a"
