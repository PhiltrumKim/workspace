import sys
import time
import serial
import serial.tools.list_ports
from magewell_rpa.core.relay_board import RelayBoardController

def list_serial_ports():
    """사용 가능한 시리얼 포트 목록 반환"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def main():
    print("=== Pseudo-Absolute Mouse Test v2 (Based on RelayBoard Test) ===")
    
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

    print("\n=== 테스트 시작 (종료: q) ===")
    print("목표 좌표 (x y)를 입력하면 먼저 (0,0)으로 초기화 후 이동합니다.")

    try:
        while True:
            raw_input = input("\nTarget X Y > ").strip()
            if not raw_input or raw_input.lower() == 'q':
                break
            
            try:
                parts = raw_input.split()
                if len(parts) < 2:
                    print("Usage: x y (e.g., 500 500)")
                    continue
                
                # [2026-02-12] 사용자 리포트: 이동 거리가 2배로 측정됨 -> 0.5배 보정 적용
                input_x = int(parts[0])
                input_y = int(parts[1])
                
                target_x = int(input_x * 0.5)
                target_y = int(input_y * 0.5)
                
                print(f"Input: ({input_x}, {input_y}) -> Scaled Target: ({target_x}, {target_y})")

                # 1. Reset to (0,0) - Software Homing only
                print("1. Resetting to (0,0)...")
                rb.reset_mouse()
                # 리셋 후 안정화를 위해 잠시 대기
                time.sleep(1.0)
                
                # 2. Move to Target
                print(f"2. Moving to ({target_x}, {target_y})...")
                # Since we are at 0,0, relative move (target_x, target_y) brings us to absolute position.
                rb.move_mouse_relative(target_x, target_y)
                
                print("Done.")

            except ValueError:
                print("Invalid number format.")

    except KeyboardInterrupt:
        print("\n[!] 사용자에 의해 중단됨")
    finally:
        # 4. 연결 종료
        rb.disconnect()
        print("프로그램을 종료합니다.")

if __name__ == "__main__":
    main()
