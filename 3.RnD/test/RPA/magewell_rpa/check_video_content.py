import cv2
import numpy as np

def check_video():
    cap = cv2.VideoCapture('test_video.avi')
    if not cap.isOpened():
        print("Failed to open test_video.avi")
        return

    ret, frame = cap.read()
    if not ret:
        print("Failed to read frame")
        return

    print(f"Frame 0 Shape: {frame.shape}")
    
    # Check key points
    p_0_0 = frame[0, 0]
    p_240_0 = frame[240, 0] # y=240, x=0
    p_center = frame[240, 320]

    print(f"Pixel at (0,0) [Gray?]: {p_0_0}")
    print(f"Pixel at (0,240) [Red?]: {p_240_0}")
    print(f"Pixel at Center [Gray?]: {p_center}")

    cap.release()

    # Check template
    tpl = cv2.imread('template_red_square.png')
    if tpl is not None:
        print(f"Template TopLeft [Red?]: {tpl[0,0]}")

check_video()
