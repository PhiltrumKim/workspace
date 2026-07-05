# --- 설정 (Configuration) ---

# utils_device.py 출력 결과에 따라 이 인덱스를 변경해야 할 수도 있습니다.
DEFAULT_DEVICE_INDEX = 0 
MIN_AREA = 500  # 움직임으로 간주할 최소 윤곽선 면적
THRESHOLD_SENSITIVITY = 25  # 차이 임계값
MATCH_THRESHOLD = 0.6 # 템플릿 매칭 임계값 (비디오 압축 등을 고려하여 낮춤)

# 기본값
DEFAULT_MATCH_THRESHOLD = 0.7
DEFAULT_DETECT_INTERVAL = 3
DEFAULT_FPS = 30
DEFAULT_CAMERA_WIDTH = 1920
DEFAULT_CAMERA_HEIGHT = 1080
