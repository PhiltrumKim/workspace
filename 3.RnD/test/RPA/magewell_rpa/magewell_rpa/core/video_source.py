from ..config import DEFAULT_CAMERA_WIDTH, DEFAULT_CAMERA_HEIGHT
import cv2

class VideoSource:
    def __init__(self, source_type, source_path):
        self.source_type = source_type
        self.source_path = source_path
        self.width = 0
        self.height = 0
        self.fps = 0
        self._open_source()
        
    def _open_source(self):
        try:
            self.cap = cv2.VideoCapture(self.source_path)
            
            # 카메라일 경우 기본적으로 높은 해상도를 요청하되, 실패하면 주는대로 받음
            if self.source_type == "CAMERA":
                # Magewell 등 캡처 카드는 가능한 최고 해상도로 설정 요청
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, DEFAULT_CAMERA_WIDTH)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, DEFAULT_CAMERA_HEIGHT)
            
            if self.cap.isOpened():
                # 실제 적용된 속성 읽기
                self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.fps = self.cap.get(cv2.CAP_PROP_FPS)
                if self.fps <= 0: self.fps = 30 # Fallback
                print(f"Source Opened: {self.width}x{self.height} @ {self.fps:.2f}fps")
            else:
                 print(f"Failed to open source: {self.source_path}")

        except Exception as e:
            print(f"Error opening video source: {e}")
            self.cap = None

    def get_info(self):
        if self.is_opened():
            return f"{self.width}x{self.height} @ {self.fps:.2f} FPS"
        return "No Signal"

    def is_opened(self):
        return self.cap is not None and self.cap.isOpened()
        
    def release(self):
        if self.cap:
            self.cap.release()
            
    def read_frame(self, playback_speed=1.0):
        if not self.is_opened():
            return False, None

        try:
            # 빨리 감기 시 프레임 스킵 (Frame Skipping for Fast Forward)
            if playback_speed > 1.0 and self.source_type == "FILE":
                skip_count = int(playback_speed) - 1
                for _ in range(skip_count):
                    self.cap.grab()
                    
            ret, frame = self.cap.read()
            
            # 파일의 끝에 도달했을 경우 처리
            if not ret:
                if self.source_type == "FILE":
                    # 자동 반복 (Auto Loop)
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    return self.read_frame(playback_speed) # 재귀 호출로 첫 프레임 반환
                else:
                    # 카메라인 경우, 일시적 오류일 수 있으므로 Warning 출력 후 False 반환
                    # print("Warning: Camera read failed.") # 너무 잦은 출력 방지
                    return False, None
                
            return True, frame

        except Exception as e:
            print(f"Error reading frame: {e}")
            return False, None

    def get_delay_ms(self, playback_speed=1.0):
        fps = self.fps if self.fps > 0 else 30
        if playback_speed >= 1.0:
            delay_ms = int(1000 / fps)
        else:
            delay_ms = int(1000 / (fps * playback_speed))
        return max(1, delay_ms)
    
    def reconnect(self, source_type, source_path):
        self.release()
        self.source_type = source_type
        self.source_path = source_path
        self._open_source()
        return self.is_opened()
