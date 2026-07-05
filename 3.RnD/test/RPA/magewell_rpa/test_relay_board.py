import sys
import os
import time
import serial
import serial.tools.list_ports
import serial.tools.list_ports
from magewell_rpa.core.relay_board import RelayBoardController
from magewell_rpa.core.keycode_map import get_hid_code

def list_serial_ports():
    """사용 가능한 시리얼 포트 목록 반환"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def main():
    print("=== Relay Board Test Script ===")
    
    # 1. 포트 검색 및 선택
    available_ports = list_serial_ports()
    if not available_ports:
        print("[!] 사용 가능한 시리얼 포트가 없습니다.")
        return

    print("사용 가능한 포트:")
    for i, port in enumerate(available_ports):
        print(f"{i+1}. {port}")
    
    try:
        selection = int(input("포트 번호를 선택하세요 (1~N): "))
        port_name = available_ports[selection - 1]
    except (ValueError, IndexError):
        print("[!] 잘못된 선택입니다.")
        return

    print(f"[{port_name}]에 연결을 시도합니다...")
    
    # 2. 컨트롤러 초기화 및 연결
    rb = RelayBoardController(port=port_name)
    if not rb.connect():
        return

    print("\n=== 커맨드 모드 시작 ===")
    print("사용 가능한 명령어: help, status, remote, local, key, move x y, click l/r, reset, exit")

    try:
        while True:
            raw_input = input("\nCommad > ").strip()
            if not raw_input:
                continue
            
            cmd_line = raw_input.split()
            cmd = cmd_line[0].lower()

            if cmd in ['exit', 'quit']:
                break
            
            elif cmd == 'help':
                print("--- 명령어 목록 ---")
                print("status      : 보드 상태 확인")
                print("remote      : 리모트 모드 전환")
                print("local       : 로컬 모드 전환")
                print("key [code]  : 키 입력 테스트 (기본: 'A')")
                print("move x y    : 마우스 이동 (예: move 20 -20)")
                print("click l/r   : 마우스 클릭 (l:좌, r:우)")
                print("reset       : 마우스 좌표 초기화 (0,0)")
                print("exit        : 종료")

            elif cmd == 'status':
                rb.check_status()

            elif cmd == 'remote':
                rb.set_mode('remote')

            elif cmd == 'local':
                rb.set_mode('local')

            elif cmd == 'key':
                if len(cmd_line) < 2:
                    print("Usage: key [char] or [hex_code] (e.g., key a, key A, key 04)")
                    continue
                
                input_val = cmd_line[1]
                code = 0
                modifiers = 0
                
                # 1. Hex Code 체크 (2자리 16진수)
                if len(input_val) == 2 and all(c in '0123456789abcdefABCDEF' for c in input_val):
                     try:
                        code = int(input_val, 16)
                     except ValueError:
                        pass
                
                # 2. 문자 또는 키 이름 매핑 확인
                if code == 0:
                    hid_info = get_hid_code(input_val)
                    if hid_info:
                        code, modifiers = hid_info
                        if code is None:
                            print(f"Unknown key mapping: {input_val}")
                            continue
                    else:
                        # 매핑도 없고 Hex도 아니면 에러
                        print(f"Invalid input: {input_val}")
                        continue

                print(f"Sending Key: '{input_val}' -> Code: 0x{code:02x}, Mod: 0x{modifiers:02x}")
                rb.send_key(scancode=code, modifiers=modifiers, is_release=False) # Down
                time.sleep(0.1)
                rb.send_key(scancode=code, modifiers=modifiers, is_release=True)  # Up

            elif cmd == 'move':
                if len(cmd_line) < 3:
                    print("Usage: move x y (e.g., move 50 -20)")
                    continue
                try:
                    dx = int(cmd_line[1])
                    dy = int(cmd_line[2])
                    print(f"Moving Mouse: ({dx}, {dy})")
                    rb.send_mouse_move(dx, dy)
                except ValueError:
                    print("Invalid coordinates")

            elif cmd == 'click':
                if len(cmd_line) < 2:
                    print("Usage: click l OR click r")
                    continue
                btn_char = cmd_line[1]
                if btn_char == 'l':
                    print("Left Click")
                    rb.send_mouse_move(0, 0, buttons=0x01)
                    time.sleep(0.1)
                    rb.send_mouse_move(0, 0, buttons=0x00)
                elif btn_char == 'r':
                    print("Right Click")
                    rb.send_mouse_move(0, 0, buttons=0x02)
                    time.sleep(0.1)
                    rb.send_mouse_move(0, 0, buttons=0x00)
                else:
                    print("Unknown button (use 'l' or 'r')")

            elif cmd == 'reset':
                rb.reset_mouse()

            else:
                print(f"Unknown command: {cmd}")

    except KeyboardInterrupt:
        print("\n[!] 사용자에 의해 중단됨")
    finally:
        # 4. 연결 종료
        rb.disconnect()
        print("프로그램을 종료합니다.")

if __name__ == "__main__":
    main()
