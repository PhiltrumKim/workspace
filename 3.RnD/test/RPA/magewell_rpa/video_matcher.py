import cv2
import numpy as np
import argparse
import os
import glob
import time

# --- Configuration ---
DEFAULT_THRESHOLD = 0.8

def load_templates(template_dir):
    """
    Loads all image files from the specified directory as templates.
    Returns a list of tuples: (filename, image_data, width, height)
    """
    templates = []
    if not os.path.exists(template_dir):
        print(f"Warning: Template directory '{template_dir}' not found.")
        return templates

    # Support common image formats
    extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp']
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(template_dir, ext)))

    for filepath in files:
        img = cv2.imread(filepath)
        if img is not None:
            h, w = img.shape[:2]
            templates.append({
                'name': os.path.basename(filepath),
                'image': img,
                'w': w,
                'h': h
            })
            print(f"Loaded template: {filepath} ({w}x{h})")
        else:
            print(f"Failed to load image: {filepath}")
    
    return templates

def trigger_event(template_name, location):
    """
    Callback for when a template is matched.
    """
    print(f"[EVENT] Target '{template_name}' detected at {location}!")
    # Add your custom event logic here (e.g., API call, logging, sound)

def main():
    parser = argparse.ArgumentParser(description="Magewell RPA Video Matcher")
    parser.add_argument('--source', type=str, default='0', help='Video source: Device Index (0, 1, ...) or Video File Path')
    parser.add_argument('--templates', type=str, default='templates', help='Directory containing target images to detect')
    parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD, help='Matching threshold (0.0 to 1.0)')
    parser.add_argument('--no-display', action='store_true', help='Disable video display (headless mode)')
    
    args = parser.parse_args()

    # Determine source type
    if args.source.isdigit():
        source = int(args.source)
        print(f"Opening Camera Device {source}...")
    else:
        source = args.source
        if not os.path.exists(source):
            print(f"Error: Video file '{source}' not found.")
            return
        print(f"Opening Video File '{source}'...")

    # Load Templates
    templates = load_templates(args.templates)
    if not templates:
        print("No templates loaded. Please ensure the --templates directory exists and contains images.")
        # We continue anyway, maybe they just want to view the feed.

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Error: Could not open video source {source}.")
        return

    print("Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("End of video stream or failed to read frame.")
            # If it's a file, we could loop it, but for now we'll just exit or wait.
            # Let's loop it for testing convenience if it's a file
            if isinstance(source, str):
                print("Looping video...")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            else:
                break

        display_frame = frame.copy()
        
        # --- Template Matching ---
        for template in templates:
            # Match Template requires same depth/type. 
            # If templates are color, frame must be color.
            # Ideally, convert both to grayscale for robustness, but color match can be stricter.
            # Let's use color matching if possible, or fallback to gray.
            
            # Using TM_CCOEFF_NORMED is robust
            res = cv2.matchTemplate(frame, template['image'], cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= args.threshold:
                # Match found
                top_left = max_loc
                w, h = template['w'], template['h']
                bottom_right = (top_left[0] + w, top_left[1] + h)
                
                # Draw box
                cv2.rectangle(display_frame, top_left, bottom_right, (0, 255, 0), 2)
                
                # Label
                label = f"{template['name']} ({max_val:.2f})"
                cv2.putText(display_frame, label, (top_left[0], top_left[1] - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                
                trigger_event(template['name'], top_left)

        if not args.no_display:
            cv2.imshow("Magewell RPA Video Matcher", display_frame)
            key = cv2.waitKey(1) & 0xFF # 1ms delay is enough
            if key == ord('q'):
                break
        else:
            # Just to prevent spinning too fast if headless
            time.sleep(0.01)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
