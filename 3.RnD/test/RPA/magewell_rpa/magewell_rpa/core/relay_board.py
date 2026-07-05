import serial
import time
import struct

class RelayBoardController:
    """
    TX-RelayBoard 프로토콜을 구현한 제어 클래스
    문서 기반: [20250310]TX_RelayBoard_Protocol.pptx
    """

    # --- Protocol Constants ---
    # Command Types [cite: 7, 9, 11, 13, 20, 23, 26, 28]
    CMD_MOUSE_RESET = 0xe0  # 마우스 좌표 초기화
    CMD_SW_RESET    = 0xe1  # S/W 초기화 (PIC32)
    CMD_ALIVE_ACK   = 0xe2  # Alive ACK
    CMD_ALL_RESET   = 0xe3  # 전체 초기화
    CMD_PCC_SET     = 0xe4  # PCC Interval 설정
    CMD_KEYPAD_MODE = 0xf8  # LOCAL/REMOTE 전환
    CMD_SET_KM_CFG  = 0xf9  # Scancode 설정
    CMD_KEYBOARD    = 0xfc  # 키보드 데이터
    CMD_STATUS_CHK  = 0xfd  # 상태 확인
    CMD_MOUSE_NORM  = 0xfe  # 마우스 데이터 (일반)
    CMD_MOUSE_RDP   = 0xee  # 마우스 데이터 (MSTSC 모드)

    # Keypad Mode [cite: 57, 58]
    MODE_LOCAL  = 0x4C
    MODE_REMOTE = 0x52

    def __init__(self, port, baudrate=115200, verbose=True):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.verbose = verbose
        self._cur_x = 0  # 소프트웨어 추적 마우스 X 좌표
        self._cur_y = 0  # 소프트웨어 추적 마우스 Y 좌표

    def connect(self):
        """시리얼 포트 연결 """
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1
            )
            print(f"[Connect] {self.port} Open Success.")
            return True
        except Exception as e:
            print(f"[Error] Connection failed: {e}")
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[Disconnect] Port closed.")

    def _create_packet(self, command, data_bytes):
        """
        12 Byte 고정 길이 패킷 생성
        Format: [00 00 00 00] [CMD] [DATA 5bytes] [00] [FF]
        """
        packet = bytearray(12)
        
        # #0~#3: Reserved (Target ID) [cite: 34-41]
        packet[0:4] = b'\x00\x00\x00\x00'
        
        # #4: Command Type
        packet[4] = command
        
        # #5~#9: Data Payload
        if data_bytes:
            length = len(data_bytes)
            # 데이터가 5바이트를 넘어가면 #10 영역까지 침범 가능 (마우스 등)
            for i in range(length):
                if 5 + i < 12:
                    packet[5 + i] = data_bytes[i]

        # #10, #11: Footer (기본값) [cite: 60-63]
        # 데이터가 #10을 덮어쓰지 않은 경우에만 0x00 설정
        if len(data_bytes) <= 5: 
            packet[10] = 0x00
        
        packet[11] = 0xff 
        
        return packet

    def send_packet(self, command, data_bytes, quiet=False):
        if not self.ser or not self.ser.is_open:
            if self.verbose: print("[Error] Port not open.")
            return

        packet = self._create_packet(command, data_bytes)
        self.ser.write(packet)
        # Debug: 16진수로 출력
        if self.verbose and not quiet:
            hex_str = ' '.join(f'0x{b:02x}' for b in packet)
            print(f"[TX] {hex_str}")

        # 응답 수신 (옵션) - 안정성을 위해 전송 후 잠깐 대기 (Buffer Overflow 방지)
        time.sleep(0.01)
        # response = self.ser.read(12)
        # if response:
        #     print(f"[RX] {' '.join(f'0x{b:02x}' for b in response)}")

    def set_mode(self, mode_type):
        """
        Keypad Local/Remote 전환 [cite: 21, 54-58]
        mode_type: 'local' or 'remote'
        """
        if mode_type == 'local':
            val = self.MODE_LOCAL
        else:
            val = self.MODE_REMOTE
            
        # #5: Local/Remote Value
        data = [val, 0x00, 0x00, 0x00, 0x00]
        print(f"Setting Mode to {mode_type.upper()}...")
        self.send_packet(self.CMD_KEYPAD_MODE, data)

    def send_key(self, scancode, modifiers=0x00, flag=None, is_release=False):
        """
        키보드 입력 전송
        #5: USB Key Modifier
        #6: Virtual Key (보통 0x00)
        #7: Flag (Down: 0x00, Up: 0x01)
        #8: MakeCode (Scancode)
        #9: Break Code (Always 0x00 observed)
        """
        if flag is None:
            # 기본 동작: Down=0x00, Up=0x01
            flag = 0x01 if is_release else 0x00
            
        # Break Code는 0x00으로 고정 (사용자 예시 기준)
        break_code = 0x00 
        data = [modifiers, 0x00, flag, scancode, break_code]
        self.send_packet(self.CMD_KEYBOARD, data)

    def send_mouse_move(self, delta_x, delta_y, buttons=0, rdp_mode=False, quiet=False):
        """
        마우스 이동 및 클릭 전송 (Mouse Format 2.0)

        Packet layout (12 bytes):
          #0~#3 : 0x00 (reserved)
          #4    : CMD  (0xfe 일반 Mode / 0xee MSTSC Mode)
          #5    : 0x00 (reserved)
          #6    : 버튼 타입 & Sign bit
                  (※ HW 검증결과 펌웨어는 부호비트를 무시하고 #7~#10 signed int16 값만 사용.
                     아래는 프로토콜 명세 표기 기준 = "패킷 저장값이 음수일 때 set")
                    bit4 (0x10): delta_x < 0            (저장값 delta_x < 0)
                    bit5 (0x20): delta_y > 0            (저장값 -delta_y < 0)
                    bit3 (0x08): 항상 1
                    bit2~0    : 버튼 마스크 (Left=1, Right=2, Middle=4)
          #7~#8 : delta_x  little-endian int16
          #9~#10: delta_y * -1  little-endian int16  (프로토콜 명세: Y축 반전)
          #11   : 0xff

        Args:
            delta_x  : X 이동량. 일반모드 -127~127 / RDP모드 -32767~32767
            delta_y  : Y 이동량. 일반모드 -127~127 / RDP모드 -32767~32767
            buttons  : 버튼 비트마스크 (Left=1, Right=2, Middle=4)
            rdp_mode : True → 0xee (MSTSC Mode), False → 0xfe (일반 Mode)
            quiet    : True → 디버그 출력 억제
        """
        cmd   = self.CMD_MOUSE_RDP  if rdp_mode else self.CMD_MOUSE_NORM
        limit = 32767               if rdp_mode else 127

        # 값 범위 제한
        delta_x = max(min(delta_x, limit), -limit)
        delta_y = max(min(delta_y, limit), -limit)

        # #6: Sign bit — 문서 규칙 "패킷 저장값(#7~#10)이 음수일 때 set"
        # - delta_x 저장값 = delta_x        → delta_x < 0 일 때 bit4 (0x10)  "00x1 1xxx"
        # - delta_y 저장값 = -delta_y(반전)  → delta_y > 0 일 때 bit5 (0x20)  "001x 1xxx"
        #   ※ HW 검증(2026-07-05): 펌웨어는 이 부호비트를 실제로 사용하지 않음(이동은 int16 값으로 결정).
        #     동작에는 영향 없으나 명세와의 정합성을 위해 맞춰 둔다.
        sign_bits = 0
        if delta_x < 0:
            sign_bits |= 0x10
        if delta_y > 0:
            sign_bits |= 0x20

        byte_6 = sign_bits | (buttons & 0x07) | 0x08  # bit3 항상 set

        # 프로토콜 명세: 패킷에는 delta_y * -1 을 저장
        delta_y_pkt = -delta_y

        packed_x = struct.pack('<h', delta_x)
        packed_y = struct.pack('<h', delta_y_pkt)

        data = bytearray(6)
        data[0] = 0x00          # #5 reserved
        data[1] = byte_6        # #6 button/sign
        data[2] = packed_x[0]  # #7 dx low
        data[3] = packed_x[1]  # #8 dx high
        data[4] = packed_y[0]  # #9 dy low
        data[5] = packed_y[1]  # #10 dy high

        if not quiet and self.verbose:
            print(f"[Mouse] dx={delta_x}, dy={delta_y} (pkt_dy={delta_y_pkt}), btn=0x{byte_6:02x}")

        self.send_packet(cmd, data, quiet=quiet)

        # 실제 전송된 (clamped) delta로 추적 좌표 갱신
        self._cur_x += delta_x
        self._cur_y += delta_y

    def send_mouse_abs(self, abs_x, abs_y, buttons=0, rdp_mode=False, quiet=False):
        """
        절대 좌표로 마우스 이동 (C++ SendAbsoluteMouseMoveCtl 대응)

        현재 추적 위치(_cur_x, _cur_y)에서 목표 절대 좌표까지의
        delta를 자동 계산하여 move_mouse_relative로 전송한다.

        Args:
            abs_x, abs_y : 목표 절대 좌표
            buttons      : 버튼 비트마스크 (Left=1, Right=2, Middle=4)
            rdp_mode     : True → 0xee (MSTSC Mode), False → 0xfe (일반 Mode)
            quiet        : True → 디버그 출력 억제
        """
        delta_x = abs_x - self._cur_x
        delta_y = abs_y - self._cur_y

        if not quiet and self.verbose:
            print(f"[MouseAbs] ({self._cur_x},{self._cur_y}) → ({abs_x},{abs_y}), delta=({delta_x},{delta_y})")

        self.move_mouse_relative(delta_x, delta_y, buttons=buttons, rdp_mode=rdp_mode)

    def move_mouse_relative(self, dx, dy, buttons=0, rdp_mode=False):
        """
        큰 거리 이동을 위해 step 단위로 쪼개서 전송
        일반모드: 최대 127 step / RDP모드: 최대 32767 step
        """
        step_limit = 32767 if rdp_mode else 127
        while dx != 0 or dy != 0:
            step_x = max(min(dx, step_limit), -step_limit)
            step_y = max(min(dy, step_limit), -step_limit)

            self.send_mouse_move(step_x, step_y, buttons=buttons, rdp_mode=rdp_mode)

            dx -= step_x
            dy -= step_y

            # 너무 빠른 전송 방지
            # time.sleep(0.005)

    def reset_mouse(self):
        """마우스 좌표 초기화 (0,0으로 이동) [cite: 7]"""
        print("Resetting Mouse to (0,0)...")
        # 1. 하드웨어 리셋 커맨드 전송 (0xE0 제거 - 사용자 리포트 반영)
        # data = [0x00, 0x00, 0x00, 0x00, 0x00]
        # self.send_packet(self.CMD_MOUSE_RESET, data)
        
        # 2. 소프트웨어 호밍 (0,0 강제 이동)
        # 0xE0 커맨드가 동작하지 않을 경우를 대비해, 
        # 상대 좌표(-127, -127)를 반복 전송하여 화면 좌상단으로 이동시킴
        # 4K 해상도 대응 (3840 / 127 = 30.2, FHD는 15회) -> 넉넉히 35회
        print("Performing Software Homing to (0,0)...")
        for _ in range(35): 
            self.send_mouse_move(-127, -127, quiet=True)
            # time.sleep(0.005) # 전송 속도 조절 필요 시 주석 해제

    def check_status(self):
        """릴레이보드 상태 확인 [cite: 205-219]"""
        # #5: 0x70, #6: 0x80
        data = [0x70, 0x80, 0x00, 0x00, 0x00]
        print("Checking RelayBoard Status...")
        self.send_packet(self.CMD_STATUS_CHK, data)
