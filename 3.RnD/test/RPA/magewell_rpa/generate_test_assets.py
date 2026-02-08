import cv2
import numpy as np
import os

def create_test_video(filename='test_video.avi', duration=5, fps=30, width=640, height=480):
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(filename, fourcc, fps, (width, height))

    # Define a moving object (a red square)
    square_size = 50
    x, y = 0, height // 2
    speed = 5

    print(f"Generating {filename}...")
    for i in range(duration * fps):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Background color (dark gray)
        frame[:] = (50, 50, 50) 

        # Draw the moving red square
        cv2.rectangle(frame, (x, y), (x + square_size, y + square_size), (0, 0, 255), -1)
        
        # Add some noise/distraction (random circles)
        for _ in range(5):
             cx = np.random.randint(0, width)
             cy = np.random.randint(0, height)
             cv2.circle(frame, (cx, cy), 10, (255, 255, 255), -1)

        if i == 0:
             # Verify first frame
             print(f"Frame 0 Center: {frame[height//2, width//2]}")
             print(f"Frame 0 TopLeft: {frame[0, 0]}")
             cv2.imwrite("debug_generated_frame_0.png", frame)

        out.write(frame)

        # Update position
        x += speed
        if x > width:
            x = -square_size

    out.release()
    print("Video generation complete.")

    # Generate the template image from the "object" we want to find
    template = np.zeros((square_size, square_size, 3), dtype=np.uint8)
    template[:] = (0, 0, 255) # The red square
    cv2.imwrite('template_red_square.png', template)
    print("Template image 'template_red_square.png' generated.")

if __name__ == "__main__":
    create_test_video()
