import argparse
import sys
import time
from magewell_rpa.core.relay_board import RelayBoardController

def test_pseudo_absolute_move(port, target_x, target_y):
    print(f"[{port}] Connecting...")
    rb = RelayBoardController(port)
    if not rb.connect():
        print("Connection failed")
        return

    try:
        # 1. Reset to (0,0)
        print("Resetting to (0,0)...")
        rb.reset_mouse()
        
        # Current inferred position is now (0,0)
        current_x, current_y = 0, 0
        
        print(f"Moving to Target ({target_x}, {target_y})...")
        
        # 2. Move to Target using Relative Moves
        # We need to move from (0,0) to (target_x, target_y)
        dx = target_x - current_x
        dy = target_y - current_y
        
        # Use existing move_mouse_relative which handles >127 chunks
        rb.move_mouse_relative(dx, dy)
        
        print(f"Move Complete. Mouse should be at ({target_x}, {target_y})")
        
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        rb.disconnect()

if __name__ == "__main__":
    import serial.tools.list_ports
    
    print("=== Pseudo-Absolute Mouse Test (Reset + Relative) ===")
    ports = [p.device for p in serial.tools.list_ports.comports()]
    
    if not ports:
        print("No ports found.")
        sys.exit(1)
        
    print("Available ports:")
    for i, p in enumerate(ports):
        print(f"{i+1}. {p}")
        
    try:
        idx = int(input("Select port (1~N): ")) - 1
        port = ports[idx]
        
        while True:
            coord = input("Enter Target X Y (e.g., 500 500) or 'q': ")
            if coord.lower() == 'q': break
            
            try:
                tx, ty = map(int, coord.split())
                test_pseudo_absolute_move(port, tx, ty)
            except ValueError:
                print("Invalid format")
                
    except Exception as e:
        print(f"Error: {e}")
