import cv2

OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"

for idx in [0, 1, 2]:
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        print(f"index {idx}: not opened")
        cap.release()
        continue
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    ret, frame = cap.read()
    if ret and frame is not None:
        h, w = frame.shape[:2]
        print(f"index {idx}: OPENED, frame {w}x{h}")
        cv2.imwrite(f"{OUT}\\probe_idx{idx}.png", frame)
    else:
        print(f"index {idx}: opened but read failed")
    cap.release()
print("done")
