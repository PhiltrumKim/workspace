import utils_device
import sys

try:
    available, working, non_working = utils_device.list_ports()
    print(f"DEBUG_PORTS: {working}")
    with open("working_ports.txt", "w", encoding="utf-8") as f:
        f.write(str(working))
except Exception as e:
    print(f"ERROR: {e}")
