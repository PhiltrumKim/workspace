from .config import DEFAULT_MATCH_THRESHOLD, DEFAULT_DETECT_INTERVAL, DEFAULT_FPS

class AppState:
    def __init__(self):
        self.source_type = "CAMERA" # 소스 타입: CAMERA 또는 FILE
        self.source_path = 0 # 기본 카메라 인덱스
        self.paused = False
        self.roi_selected = False
        self.roi_rect = None # (x, y, w, h)
        self.templates = [] # 로드된 템플릿 목록
        self.pixel_diff_threshold = 25 # 배경 제거를 위한 픽셀 차이 임계값
        
        # 성능 및 튜닝 (Performance & Tuning)
        self.match_threshold = DEFAULT_MATCH_THRESHOLD # 기본 매칭 임계값
        self.frame_count = 0
        self.detect_interval = DEFAULT_DETECT_INTERVAL # N 프레임마다 매칭 수행
        self.last_detected_rects = [] # 마지막 검출 결과 저장
        
        # 재생 제어 (Playback Control)
        self.fps = DEFAULT_FPS # 기본 FPS
        self.playback_speed = 1.0 # 배속 (Multiplier)
        
        # 릴레이 보드 (Relay Board)
        self.relay_controller = None
        self.relay_connected = False
        self.target_monitor_size = (1920, 1080) # 목표 모니터 해상도 (FHD)
        self.current_mouse_x = 0 # 현재 추정 마우스 X (0~1920)
        self.current_mouse_y = 0 # 현재 추정 마우스 Y (0~1080)
        self.mouse_speed_scale = 1.0  # 마우스 감도 배율 (1.0 = 기준, 하드웨어 Gain은 HARDWARE_GAIN 상수로 별도 관리)
