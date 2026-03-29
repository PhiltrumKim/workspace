import cv2

def list_ports():
    """
    Test the ports and returns a tuple with the available ports and the ones that are working.
    """
    non_working_ports = []
    dev_port = 0
    working_ports = []
    available_ports = []
    
    # Check up to 10 ports
    while dev_port < 10:
        camera = cv2.VideoCapture(dev_port)
        if not camera.isOpened():
            non_working_ports.append(dev_port)
            print(f"Port {dev_port} is not working.")
        else:
            is_reading, img = camera.read()
            w = camera.get(3)
            h = camera.get(4)
            if is_reading:
                print(f"Port {dev_port} is working and reads images ({w}x{h})")
                working_ports.append(dev_port)
            else:
                print(f"Port {dev_port} for camera ( {w}x{h}) is present but does not reads.")
                available_ports.append(dev_port)
        dev_port += 1
    return available_ports, working_ports, non_working_ports

if __name__ == '__main__':
    print("Searching for camera ports...")
    available, working, non_working = list_ports()
    print(f"\nWorking ports: {working}")
    print("\nNote: Magewell capture cards usually appear as a standard webcam.")
    print("If multiple ports are found, try the one with the resolution matching your input source.")
