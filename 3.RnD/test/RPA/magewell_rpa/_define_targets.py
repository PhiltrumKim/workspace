import cv2
OUT = r"C:\Users\embed\AppData\Local\Temp\claude\C--Users-embed-Desktop-git-MyWorkspace-3-RnD-test-RPA-magewell-rpa\b7030f0a-45d1-44a6-9b93-32f5fde7528d\scratchpad"

# (name, x, y, w, h)  -- 1920x1080 기준
TARGETS = [
    ("wastebasket",     78,   92, 64, 60),
    ("menu_btn",        1043, 52, 62, 28),
    ("browser_icon",    1148, 52, 32, 30),
    ("filemgr_icon",    1190, 52, 30, 30),
    ("term_taskbar",    1375, 52, 150, 28),
    ("cpu_pct",         1770, 55, 42, 22),
    ("clock",           1818, 55, 50, 22),
    ("term_titlebar",   636,  350, 34, 22),
    ("term_min_btn",    1216, 350, 22, 18),
    ("term_max_btn",    1240, 350, 22, 18),
    ("term_close_btn",  1264, 350, 22, 18),
    ("menu_File",       636,  379, 32, 20),
    ("menu_Edit",       676,  379, 32, 20),
    ("menu_Tabs",       720,  379, 36, 20),
    ("menu_Help",       768,  379, 36, 20),
]

ref = cv2.imread(f"{OUT}\\ref_frame.png")
ann = ref.copy()
for name, x, y, w, h in TARGETS:
    crop = ref[y:y+h, x:x+w]
    cv2.imwrite(f"{OUT}\\tmpl_{name}.png", crop)
    cv2.rectangle(ann, (x, y), (x+w, y+h), (0, 0, 255), 1)
    cv2.putText(ann, name, (x, y-3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
cv2.imwrite(f"{OUT}\\annotated_ref.png", ann)
print(f"{len(TARGETS)} templates saved + annotated_ref.png")
