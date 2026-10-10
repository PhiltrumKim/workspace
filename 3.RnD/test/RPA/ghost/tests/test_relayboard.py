"""RelayBoard 패킷이 MiTx C++(DefMouseSerial.h)와 바이트 단위로 일치하는지 확인."""
from ghost.hal import keymap
from ghost.hal.relayboard import key_packet, mode_packet, mouse_packet, packet


def kp(name, up):
    k = keymap.key(name)
    return key_packet(k.vk, k.scan, k.extended, up)


def test_packet_frame():
    p = packet(0xFD, bytes([0x70, 0x80]))
    assert len(p) == 12 and p[:4] == bytes(4) and p[4] == 0xFD and p[11] == 0xFF


def test_key_release_matches_cpp_keyclear_table():
    # MI_SERIAL_SENDKEY_*_CMD (키 Up 패킷)
    assert kp("alt", True) == bytes([0, 0, 0, 0, 0xFC, 0x00, 0x12, 0x01, 0x38, 0, 0, 0xFF])
    assert kp("ctrl", True) == bytes([0, 0, 0, 0, 0xFC, 0x00, 0x11, 0x01, 0x1D, 0, 0, 0xFF])
    assert kp("shift", True) == bytes([0, 0, 0, 0, 0xFC, 0x00, 0x10, 0x01, 0x2A, 0, 0, 0xFF])
    assert kp("ralt", True) == bytes([0, 0, 0, 0, 0xFC, 0x00, 0x12, 0x03, 0x38, 0, 0, 0xFF])
    assert kp("rctrl", True) == bytes([0, 0, 0, 0, 0xFC, 0x00, 0x11, 0x03, 0x1D, 0, 0, 0xFF])
    assert kp("rshift", True) == bytes([0, 0, 0, 0, 0xFC, 0x00, 0x10, 0x01, 0x36, 0, 0, 0xFF])


def test_key_down_esc():
    assert kp("esc", False) == bytes([0, 0, 0, 0, 0xFC, 0x00, 0x1B, 0x00, 0x01, 0, 0, 0xFF])


def test_mouse_idle_matches_cpp():
    # MI_SERIAL_MOUSE_CMD
    assert mouse_packet(0, 0) == bytes([0, 0, 0, 0, 0xFE, 0x00, 0x08, 0, 0, 0, 0, 0xFF])


def test_mouse_move_encoding():
    p = mouse_packet(-5, 10, buttons=1)
    assert p[4] == 0xFE
    assert p[6] == 0x08 | 0x10 | 0x20 | 0x01          # sign(x<0) | sign(y>0) | left
    assert p[7:9] == (-5).to_bytes(2, "little", signed=True)
    assert p[9:11] == (-10).to_bytes(2, "little", signed=True)   # Y 반전 저장


def test_mouse_clamp_and_mstsc():
    assert mouse_packet(500, -500)[7:9] == (127).to_bytes(2, "little", signed=True)
    m = mouse_packet(1000, 0, mstsc=True)
    assert m[4] == 0xEE and m[7:9] == (1000).to_bytes(2, "little", signed=True)


def test_mode_remote():
    assert mode_packet(True)[4:6] == bytes([0xF8, 0x52])
