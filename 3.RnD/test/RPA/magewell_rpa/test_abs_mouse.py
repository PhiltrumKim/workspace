import argparse
import serial
import serial.tools.list_ports
import time
import struct

def list_serial_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def create_packet(command, data_bytes):
    packet = bytearray(12)
    packet[0:4] = b'\x00\x00\x00\x00'
    packet[4] = command
    if data_bytes:
        length = len(data_bytes)
        for i in range(length):
            if 5 + i < 12:
                packet[5 + i] = data_bytes[i]
    if len(data_bytes) <= 5: 
        packet[10] = 0x00
    packet[11] = 0xff 
    return packet

def test_absolute_move(port_name, x, y):
    try:
        ser = serial.Serial(port_name, 115200, timeout=1)
        print(f"Connected to {port_name}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    # CMD_MOUSE_RDP = 0xEE
    # 추정 패킷 구조: [Btn] [X_L] [X_H] [Y_L] [Y_H]
    # Desktop Resolution usually maps to 0-32767 or 0-65535 in USB HID absolute mode.
    # Or maybe pixel logic? Let's try sending literal pixel values first, assuming 1920x1080.
    
    # 0xEE Command
    CMD = 0xEE
    
    # Structure: [Button?] [X_Low] [X_High] [Y_Low] [Y_High]
    # Button: 0
    bx = struct.pack('<H', x) # H: unsigned short (2 bytes)
    by = struct.pack('<H', y)
    
    # Payload
    # byte 0: Button (0x00)
    # byte 1: X Low
    # byte 2: X High
    # byte 3: Y Low
    # byte 4: Y High
    
    # 0. Remote Mode 설정 (필수 가능성 있음)
    print("Setting Remote Mode...")
    # CMD_KEYPAD_MODE = 0xf8, MODE_REMOTE = 0x52
    mode_pkt = create_packet(0xF8, [0x52, 0x00, 0x00, 0x00, 0x00])
    ser.write(mode_pkt)
    time.sleep(0.5)

    # 1. (0,0)으로 먼저 이동 (원점 복귀 확인)
    print("Moving to (0, 0)...")
    data_0 = [0x00, 0x00, 0x00, 0x00, 0x00]
    packet_0 = create_packet(CMD, data_0)
    ser.write(packet_0)
    time.sleep(0.5)

    # 2. 목표 좌표로 이동
    data = [0x00, bx[0], bx[1], by[0], by[1]]
    
    packet = create_packet(CMD, data)
    print(f"Sending Absolute Move to ({x}, {y})")
    print(f"Packet: {packet.hex()}")
    
    ser.write(packet)
    time.sleep(0.5)
    
    ser.close()

if __name__ == "__main__":
    print("=== Absolute Mouse Position Test ===")
    ports = list_serial_ports()
    if not ports:
        print("No serial ports found.")
    else:
        print("Available ports:")
        for i, p in enumerate(ports):
            print(f"{i+1}. {p}")
        
        idx = int(input("Select port (1~N): ")) - 1
        port = ports[idx]
        
        while True:
            try:
                coord_str = input("Enter X Y (e.g., 500 500) or 'q' to quit: ")
                if coord_str.lower() == 'q': break
                parts = coord_str.split()
                if len(parts) == 2:
                    tx, ty = int(parts[0]), int(parts[1])
                    test_absolute_move(port, tx, ty)
                else:
                    print("Invalid format.")
            except ValueError:
                print("Invalid number.")
