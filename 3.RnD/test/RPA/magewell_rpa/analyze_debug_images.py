import cv2
import numpy as np

def analyze(path):
    img = cv2.imread(path)
    if img is None:
        print(f"Failed to load {path}")
        return
    
    print(f"--- Analysis of {path} ---")
    print(f"Shape: {img.shape}")
    print(f"Dtype: {img.dtype}")
    print(f"Mean Color (BGR): {img.mean(axis=(0,1))}")
    print(f"Min: {img.min()}, Max: {img.max()}")
    
    # Check corners and center
    h, w = img.shape[:2]
    corners = {
        "Top-Left": img[0, 0],
        "Top-Right": img[0, w-1],
        "Bottom-Left": img[h-1, 0],
        "Bottom-Right": img[h-1, w-1],
        "Center": img[h//2, w//2]
    }
    for k, v in corners.items():
        print(f"{k}: {v}")

print("Analyzing generated debug images...")
analyze("debug_frame_0.png")
analyze("debug_template.png")
