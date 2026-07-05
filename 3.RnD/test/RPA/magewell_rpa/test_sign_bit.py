"""
Δy 부호 비트(#6 bit5, 0x20) 검증용 테스트 스크립트

배경:
  [20250310]TX_RelayBoard_Protocol.pptx (p.8, Mouse Format 2.0) 의 부호 규칙은
  "패킷에 저장되는 값(#7~#10)이 음수일 때 해당 부호 비트를 set" 으로 일관된다.
    - Δx 저장값 = dx        -> dx < 0  일 때 bit4(0x10)
    - Δy 저장값 = -dy (반전) -> dy > 0  일 때 bit5(0x20)   (문서: "001x 1xxx : delta y > 0")

  그런데 relay_board.py (send_mouse_move) 는 bit5 를
    if delta_y < 0: sign_bits |= 0x20
  즉 dy < 0 일 때 set 하고 있어 문서와 반대다.
  (코드 주석 line 171 은 "저장값이 음수이면 bit5=1" 이라고 올바르게 적혀 있어 구현만 뒤집힌 것으로 보인다.)

  Δx 비트/버튼/저장값(struct '<h', Δy*-1)은 두 방식이 완전히 동일하고,
  오직 bit5 를 켜는 조건만 다르다. 실제 하드웨어에서 어느 쪽이 맞는지 확인하기 위한 스크립트.

사용법:
  py test_sign_bit.py                 # 두 방식 패킷 비교표 출력 (하드웨어 불필요)
  py test_sign_bit.py --hw COM3 0 -30 # COM3 에 current/spec 두 방식을 순서대로 전송하여 실제 이동 비교
"""

import struct
import time
import argparse


def build_mouse_data(dx, dy, buttons=0, mode="current", rdp_mode=False):
    """send_mouse_move 와 동일한 페이로드(6바이트, #5~#10)를 만들되 bit5 규칙만 mode 로 분기."""
    limit = 32767 if rdp_mode else 127
    dx = max(min(dx, limit), -limit)
    dy = max(min(dy, limit), -limit)

    sign_bits = 0
    if dx < 0:                       # Δx: 두 방식 공통 (dx < 0)
        sign_bits |= 0x10
    if mode == "current":            # 현재 relay_board.py 구현
        if dy < 0:
            sign_bits |= 0x20
    else:                            # 문서 규칙 (dy > 0 == 저장값 -dy < 0)
        if dy > 0:
            sign_bits |= 0x20

    byte_6 = sign_bits | (buttons & 0x07) | 0x08   # bit3 항상 set

    dy_pkt = -dy                     # 문서: 패킷에는 Δy * -1 저장 (두 방식 공통)
    px = struct.pack("<h", dx)
    py = struct.pack("<h", dy_pkt)

    data = bytearray(6)
    data[0] = 0x00                   # #5 reserved
    data[1] = byte_6                 # #6 button/sign
    data[2], data[3] = px[0], px[1]  # #7~#8 dx (LE)
    data[4], data[5] = py[0], py[1]  # #9~#10 dy_pkt (LE)
    return data, byte_6


def full_packet(cmd, data):
    """디버그 출력을 위한 12바이트 전체 패킷 구성 (relay_board._create_packet 과 동일 규칙)."""
    p = bytearray(12)
    p[4] = cmd
    for i, b in enumerate(data):
        if 5 + i < 12:
            p[5 + i] = b
    if len(data) <= 5:
        p[10] = 0x00
    p[11] = 0xFF
    return p


def hexs(b):
    return " ".join(f"{x:02x}" for x in b)


# (dx, dy) 대표 케이스 — 사분면 + 축 방향
CASES = [
    (20, 20), (20, -20), (-20, 20), (-20, -20),
    (0, 20), (0, -20), (20, 0), (-20, 0),
]


def print_comparison():
    print("=" * 74)
    print(" Δy 부호비트 비교 (CMD=0xFE 일반모드)   CURRENT=현재코드 / SPEC=문서규칙")
    print("=" * 74)
    print(f"{'dx':>4} {'dy':>4} | {'CURRENT #6':>18} | {'SPEC #6':>18} | 비고")
    print("-" * 74)
    for dx, dy in CASES:
        _, b_cur = build_mouse_data(dx, dy, mode="current")
        _, b_spec = build_mouse_data(dx, dy, mode="spec")
        note = "" if b_cur == b_spec else "<-- bit5 다름"
        print(f"{dx:>4} {dy:>4} | 0x{b_cur:02x} ({b_cur:08b}) | 0x{b_spec:02x} ({b_spec:08b}) | {note}")
    print("-" * 74)
    print("두 방식은 dy 부호가 있을 때만 #6 이 갈린다 (dx/버튼/데이터 바이트는 동일).")
    print("전체 패킷 예시 (dx=0, dy=-30):")
    for mode in ("current", "spec"):
        data, _ = build_mouse_data(0, -30, mode=mode)
        print(f"  [{mode:>7}] {hexs(full_packet(0xFE, data))}")


def list_ports():
    """사용 가능한 시리얼 포트 목록 출력."""
    try:
        import serial.tools.list_ports as lp
    except ImportError:
        print("pyserial 미설치. .venv 파이썬으로 실행하세요.")
        return
    ports = lp.comports()
    if not ports:
        print("사용 가능한 시리얼 포트 없음.")
        return
    print("=== 시리얼 포트 ===")
    for p in ports:
        print(f"  {p.device} | {p.description} | {p.hwid}")


def _send_both(rb, dx, dy, wait):
    """current -> spec 순으로 두 방식 전송. wait 초 만큼 사이에 대기(관찰용)."""
    print(f"\n대상 이동량: dx={dx}, dy={dy}")
    print("화면 좌표계: +x=오른쪽, +y=아래  (예: dy=-30 이면 위로 이동해야 정상)")
    for mode in ("current", "spec"):
        data, b6 = build_mouse_data(dx, dy, mode=mode)
        print(f"[{mode:>7}] #6=0x{b6:02x} | packet: {hexs(full_packet(0xFE, data))}")
        rb.send_packet(0xFE, data)
        time.sleep(wait)
    print("어느 방식에서 포인터가 의도한 방향으로 움직였는지가 정답입니다.")


def hw_test(port, dx, dy, baud=115200, auto=False, wait=2.0):
    """실제 하드웨어에 current -> spec 순으로 전송하여 이동 방향을 비교.

    auto=False : 각 전송 전 Enter 대기(대화형)
    auto=True  : Enter 없이 wait 초 간격으로 자동 전송(비대화형 셸용)
    """
    from magewell_rpa.core.relay_board import RelayBoardController

    rb = RelayBoardController(port=port, baudrate=baud)
    if not rb.connect():
        return
    try:
        rb.set_mode("remote")
        time.sleep(0.3)
        if auto:
            _send_both(rb, dx, dy, wait)
        else:
            print(f"\n대상 이동량: dx={dx}, dy={dy}")
            print("화면 좌표계: +x=오른쪽, +y=아래  (dy=-30 이면 위로 이동해야 정상)")
            for mode in ("current", "spec"):
                input(f"\n[{mode}] 전송하려면 Enter (Ctrl+C 로 중단)...")
                data, b6 = build_mouse_data(dx, dy, mode=mode)
                print(f"  #6=0x{b6:02x} | packet: {hexs(full_packet(0xFE, data))}")
                rb.send_packet(0xFE, data)
            print("\n어느 방식에서 포인터가 의도한 방향으로 움직였는지가 정답입니다.")
    except KeyboardInterrupt:
        print("\n[!] 중단됨")
    finally:
        rb.disconnect()


def main():
    ap = argparse.ArgumentParser(description="Δy 부호비트 current vs spec 검증")
    ap.add_argument("--list", action="store_true", help="시리얼 포트 목록 출력")
    ap.add_argument("--hw", nargs="+", metavar=("PORT", "DX DY"),
                    help="하드웨어 전송 모드: --hw COM3 0 -30")
    ap.add_argument("--auto", action="store_true",
                    help="--hw 시 Enter 없이 자동 전송(비대화형 셸용)")
    ap.add_argument("--wait", type=float, default=2.0,
                    help="--auto 시 current/spec 전송 간 대기 초 (기본 2.0)")
    args = ap.parse_args()

    if args.list:
        list_ports()
    elif args.hw:
        if len(args.hw) < 3:
            print("사용법: --hw PORT DX DY   (예: --hw COM3 0 -30)")
            return
        port = args.hw[0]
        dx, dy = int(args.hw[1]), int(args.hw[2])
        hw_test(port, dx, dy, auto=args.auto, wait=args.wait)
    else:
        print_comparison()


if __name__ == "__main__":
    main()
