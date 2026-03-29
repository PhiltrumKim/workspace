import cv2
import numpy as np
import time
import tkinter as tk
from tkinter import filedialog
import os

# --- Configuration ---
# You might need to change this index based on utils_device.py output
DEFAULT_DEVICE_INDEX = 0 
MIN_AREA = 500  # Minimum area of contour to be considered motion
THRESHOLD_SENSITIVITY = 25  # Difference threshold
MATCH_THRESHOLD = 0.6 # Template matching threshold (Lowered for video compression)

class AppState:
    def __init__(self):
        self.source_type = "CAMERA" # CAMERA or FILE
        self.source_path = 0 # Default camera index
        self.paused = False
        self.roi_selected = False
        self.roi_rect = None # (x, y, w, h)
        self.templates = [] # List of loaded templates
        self.pixel_diff_threshold = 25 # For bg subtraction
        
        # Playback Control
        self.fps = 30 # Default
        self.playback_speed = 1.0 # Multiplier

def trigger_event(msg):
    """
    Callback function for events.
    """
    print(f"[EVENT] {msg}")

def load_template_file():
    root = tk.Tk()
    root.withdraw() # Hide the main window
    file_path = filedialog.askopenfilename(
        title="Select Template Image",
        filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")]
    )
    root.destroy()
    
    if file_path:
        print(f"Selected file: {file_path}")
        img = cv2.imread(file_path)
        if img is not None:
             h, w = img.shape[:2]
             print(f"Loaded image shape: {w}x{h}")
             template = {
                 'name': os.path.basename(file_path),
                 'image': img,
                 'w': w,
                 'h': h
             }
             print(f"Loaded template: {template['name']}")
             return template
        else:
             print("Failed to load image.")
    return None

def select_video_file():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="Select Video File",
        filetypes=[("Video Files", "*.mp4;*.avi;*.mov;*.mkv")]
    )
    root.destroy()
    return file_path

import tkinter as tk
from tkinter import filedialog, messagebox, Menu
from PIL import Image, ImageTk

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', type=str, help='Path to video file')
    parser.add_argument('--template', type=str, help='Path to template image')
    args = parser.parse_args()

    # --- GUI Setup ---
    root = tk.Tk()
    root.title("Magewell RPA Motion & Tracking")
    root.geometry("800x600")

    # State Container
    state = AppState()
    
    # Check CLI Args
    if args.video:
        state.source_type = "FILE"
        state.source_path = args.video
        cap = cv2.VideoCapture(state.source_path)
        if cap.isOpened():
            state.fps = cap.get(cv2.CAP_PROP_FPS) or 30
            print(f"CLI: Loaded video {args.video} (FPS: {state.fps:.2f})")
        else:
            print(f"CLI: Failed to open video {args.video}")
    
    if args.template:
        img = cv2.imread(args.template)
        if img is not None:
             h, w = img.shape[:2]
             state.templates.append({
                 'name': os.path.basename(args.template),
                 'image': img,
                 'w': w,
                 'h': h
             })
             print(f"CLI: Loaded template {args.template}")

    # Video Capture Setup
    cap = cv2.VideoCapture(state.source_path)
    if not cap.isOpened():
        print(f"Error: Could not open source {state.source_path}")
        # If camera fails, maybe fallback? For now just warn.

    bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)

    # --- UI Widgets ---
    video_label = tk.Label(root)
    video_label.pack(expand=True, fill="both")
    
    status_var = tk.StringVar()
    status_var.set("Ready")
    status_bar = tk.Label(root, textvariable=status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
    status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # --- Functions ---
    def load_video_file(event=None):
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video Files", "*.mp4;*.avi;*.mov;*.mkv")]
        )
        if file_path:
            state.source_type = "FILE"
            state.source_path = file_path
            # Re-init cap
            nonlocal cap
            cap.release()
            cap = cv2.VideoCapture(state.source_path)
            state.fps = cap.get(cv2.CAP_PROP_FPS) or 30
            state.paused = False
            status_var.set(f"Source: {os.path.basename(file_path)} (FPS: {state.fps:.2f})")

    def connect_camera(event=None):
        state.source_type = "CAMERA"
        state.source_path = DEFAULT_DEVICE_INDEX
        # Re-init cap
        nonlocal cap
        cap.release()
        cap = cv2.VideoCapture(state.source_path)
        status_var.set("Source: Live Camera")

    def load_template_image(event=None):
        file_path = filedialog.askopenfilename(
            title="Select Template Image",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")]
        )
        if file_path:
            img = cv2.imread(file_path)
            if img is not None:
                h, w = img.shape[:2]
                state.templates = [{
                    'name': os.path.basename(file_path),
                    'image': img,
                    'w': w,
                    'h': h
                }]
                status_var.set(f"Template Loaded: {os.path.basename(file_path)}")
                
                # Debug Pixel Stats (Once per new template)
                if hasattr(state, 'debug_printed'):
                    del state.debug_printed

    def set_manual_roi(event=None):
        if not state.templates:
            # We can't easily do mouse drag in this simple loop structure quickly without complex bindings
            # For now, let's keep the existing logic: Press 'r', user draws on the CV2 window? 
            # Wait, we are now in Tkinter. CV2 imshow is gone.
            # We need mouse bindings on the video_label.
            # For this MVP refactor, let's stick to Auto-ROI being the primary way.
            # Or use cv2.selectROI if we pop up a temporary window?
            # Let's use a temporary CV2 window for manual ROI as a bridge.
            status_var.set("Manual ROI: Press SPACE to capture frame for selection")
            ret, frame = cap.read()
            if ret:
                r = cv2.selectROI("Select ROI", frame, fromCenter=False, showCrosshair=True)
                cv2.destroyWindow("Select ROI")
                if r[2] > 0 and r[3] > 0: # w, h > 0
                    state.roi_rect = r
                    state.roi_selected = True
                    status_var.set("Manual ROI Set")
        else:
             status_var.set("Error: Clear templates first for Manual ROI")

    def quit_app(event=None):
        root.quit()

    def set_playback_speed(speed):
        state.playback_speed = float(speed)
        # Update status immediately if playing
        status_var.set(f"Speed: {state.playback_speed}x | Source: {os.path.basename(state.source_path) if state.source_type == 'FILE' else 'Camera'}")

    def increase_speed(event=None):
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
        try:
            current_idx = speeds.index(state.playback_speed)
            if current_idx < len(speeds) - 1:
                set_playback_speed(speeds[current_idx + 1])
        except ValueError:
            set_playback_speed(1.0) # Reset if weird

    def decrease_speed(event=None):
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
        try:
            current_idx = speeds.index(state.playback_speed)
            if current_idx > 0:
                set_playback_speed(speeds[current_idx - 1])
        except ValueError:
            set_playback_speed(1.0)

    # --- Menu Bar ---
    menu_bar = tk.Menu(root)
    
    # Source Menu
    source_menu = tk.Menu(menu_bar, tearoff=0)
    source_menu.add_command(label="Live Camera (c)", command=connect_camera)
    source_menu.add_command(label="Test Video (v)", command=load_video_file)
    source_menu.add_separator()
    source_menu.add_command(label="Exit (q)", command=quit_app)
    menu_bar.add_cascade(label="Source", menu=source_menu)

    # Tracking Menu
    track_menu = tk.Menu(menu_bar, tearoff=0)
    track_menu.add_command(label="Import Template (i)", command=load_template_image)
    track_menu.add_command(label="Manual ROI (r)", command=set_manual_roi)
    menu_bar.add_cascade(label="Tracking", menu=track_menu)
    
    # Playback Menu
    play_menu = tk.Menu(menu_bar, tearoff=0)
    play_menu.add_command(label="0.5x (Slow)", command=lambda: set_playback_speed(0.5))
    play_menu.add_command(label="1.0x (Normal)", command=lambda: set_playback_speed(1.0))
    play_menu.add_command(label="2.0x (Fast)", command=lambda: set_playback_speed(2.0))
    play_menu.add_command(label="4.0x (Very Fast)", command=lambda: set_playback_speed(4.0))
    menu_bar.add_cascade(label="Playback", menu=play_menu)

    root.config(menu=menu_bar)

    # --- Shortcuts ---
    root.bind('v', load_video_file)
    root.bind('c', connect_camera)
    root.bind('i', load_template_image)
    root.bind('r', set_manual_roi)
    root.bind('q', quit_app)
    root.bind('+', increase_speed)
    root.bind('=', increase_speed) # Support both + and =
    root.bind('-', decrease_speed)


    # --- Main Loop Logic ---
    def update_frame():
        # Handle Frame Skipping for Fast Forward
        if state.playback_speed > 1.0 and state.source_type == "FILE":
            # Example: 2.0x -> Skip 1 frame, Show 1 frame.
            # Example: 4.0x -> Skip 3 frames, Show 1 frame.
            skip_count = int(state.playback_speed) - 1
            for _ in range(skip_count):
                cap.grab() # Efficiently skip frames without decoding
        
        ret, frame = cap.read()
        
        # Calculate delay
        fps = state.fps if state.fps > 0 else 30
        
        if state.playback_speed >= 1.0:
            # For 1.0x or faster, we use the standard frame delay.
            # The speedup comes from skipping frames (above) logic.
            # E.g. 60fps video at 2x: display every 2nd frame, update every 1/60s.
            delay_ms = int(1000 / fps)
        else:
            # For Slow Motion (< 1.0x), we don't skip frames.
            # We just increase the delay between updates.
            # E.g. 0.5x -> delay is doubled.
            delay_ms = int(1000 / (fps * state.playback_speed))
            
        if delay_ms < 1: delay_ms = 1
        
        if not ret:
            if state.source_type == "FILE":
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                # Loop immediately
                root.after(10, update_frame)
                return
            else:
                # Camera fail? Retry
                root.after(100, update_frame)
                return

        display_frame = frame.copy()
        
        # --- 1. Auto-Tracking (Template Matching) ---
        if state.templates:
            # Template Matching Logic (SQDIFF_NORMED)
            best_val = 1.0 
            best_rect = None
            best_name = ""

            for template in state.templates:
                # Check Dimensions
                t_h, t_w = template['h'], template['w']
                f_h, f_w = frame.shape[:2]
                if t_h > f_h or t_w > f_w: continue

                res = cv2.matchTemplate(frame, template['image'], cv2.TM_SQDIFF_NORMED)
                min_val, _, min_loc, _ = cv2.minMaxLoc(res)

                if min_val < best_val:
                    best_val = min_val
                    top_left = min_loc
                    w, h = template['w'], template['h']
                    best_rect = (top_left[0], top_left[1], w, h)
                    best_name = template['name']

            if best_rect:
                x, y, w, h = best_rect
                center_x = x + w // 2
                center_y = y + h // 2

                if best_val <= 0.15:
                    # FOUND
                    state.roi_rect = best_rect
                    state.roi_selected = True
                    color = (255, 0, 0) # Blue (BGR) -> RGB handled by cvtColor later
                    # Note: CV2 uses BGR, PIL uses RGB. 
                    # We usually draw on CV2 frame in BGR, then convert.
                    # So Blue is (255, 0, 0) in BGR.
                    cv2.rectangle(display_frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
                    cv2.drawMarker(display_frame, (center_x, center_y), (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
                    label = f"{best_name} (Diff: {best_val:.2f}) TRACKING"
                    cv2.putText(display_frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                else:
                    # SEARCHING
                    state.roi_selected = False
                    # Yellow in BGR is (0, 255, 255)
                    cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                    label = f"{best_name} (Diff: {best_val:.2f}) SEARCHING"
                    cv2.putText(display_frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            else:
                state.roi_selected = False

        # --- 2. Motion Detection ---
        if state.roi_selected and state.roi_rect:
            x, y, w, h = state.roi_rect
            # Ensure bounds
            img_h, img_w = frame.shape[:2]
            x = max(0, x); y = max(0, y)
            w = min(w, img_w - x); h = min(h, img_h - y)

            if w > 0 and h > 0:
                roi_frame = frame[y:y+h, x:x+w]
                fg_mask = bg_subtractor.apply(roi_frame)
                
                # Threshold logic
                _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                motion_detected = False
                for contour in contours:
                    if cv2.contourArea(contour) > MIN_AREA:
                        motion_detected = True
                        cx, cy, cw, ch = cv2.boundingRect(contour)
                        # Draw RED box on display frame relative to ROI
                        cv2.rectangle(display_frame, (x+cx, y+cy), (x+cx+cw, y+cy+ch), (0, 0, 255), 2)

                if motion_detected:
                     cv2.putText(display_frame, "MOTION DETECTED", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # --- Convert to Tkinter Image ---
        # CV2 BGR -> RGB
        rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_frame)
        
        # Resize to fit window? For now, let's just show raw size or scale slightly if too big?
        # Let's keep raw size for accuracy, or simple aspect ratio fit
        # For MVP, raw size is safer to avoid coordinate confusion.
        
        tk_image = ImageTk.PhotoImage(image=pil_image)
        video_label.imgtk = tk_image # Prevent GC
        video_label.configure(image=tk_image)

        root.after(delay_ms, update_frame)

    # Start loop
    update_frame()
    root.mainloop()

    # Cleanup
    cap.release()

if __name__ == "__main__":
    main()
