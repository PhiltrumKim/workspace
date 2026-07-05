# PS/2 Scan Code Set 1 (Make Codes)
# Format: 'Char': (MakeCode, Modifier)
# Modifiers: Not standard in PS/2. Assuming RelayBoard handles modifier flag separately.
# RelayBoard Protocol #5: USB Key Modifier (L-Shift: 0x02)

MOD_NONE = 0x00
MOD_L_SHIFT = 0x02

ASCII_TO_MAKECODE = {
    # Numbers (1-0)
    '1': (0x02, MOD_NONE), '2': (0x03, MOD_NONE), '3': (0x04, MOD_NONE), '4': (0x05, MOD_NONE),
    '5': (0x06, MOD_NONE), '6': (0x07, MOD_NONE), '7': (0x08, MOD_NONE), '8': (0x09, MOD_NONE),
    '9': (0x0A, MOD_NONE), '0': (0x0B, MOD_NONE),

    # Letters (QWERTY Row 1)
    'q': (0x10, MOD_NONE), 'w': (0x11, MOD_NONE), 'e': (0x12, MOD_NONE), 'r': (0x13, MOD_NONE),
    't': (0x14, MOD_NONE), 'y': (0x15, MOD_NONE), 'u': (0x16, MOD_NONE), 'i': (0x17, MOD_NONE),
    'o': (0x18, MOD_NONE), 'p': (0x19, MOD_NONE),

    # Letters (QWERTY Row 2)
    'a': (0x1E, MOD_NONE), 's': (0x1F, MOD_NONE), 'd': (0x20, MOD_NONE), 'f': (0x21, MOD_NONE),
    'g': (0x22, MOD_NONE), 'h': (0x23, MOD_NONE), 'j': (0x24, MOD_NONE), 'k': (0x25, MOD_NONE),
    'l': (0x26, MOD_NONE),

    # Letters (QWERTY Row 3)
    'z': (0x2C, MOD_NONE), 'x': (0x2D, MOD_NONE), 'c': (0x2E, MOD_NONE), 'v': (0x2F, MOD_NONE),
    'b': (0x30, MOD_NONE), 'n': (0x31, MOD_NONE), 'm': (0x32, MOD_NONE),

    # Uppercase Letters (Shifted)
    'Q': (0x10, MOD_L_SHIFT), 'W': (0x11, MOD_L_SHIFT), 'E': (0x12, MOD_L_SHIFT), 'R': (0x13, MOD_L_SHIFT),
    'T': (0x14, MOD_L_SHIFT), 'Y': (0x15, MOD_L_SHIFT), 'U': (0x16, MOD_L_SHIFT), 'I': (0x17, MOD_L_SHIFT),
    'O': (0x18, MOD_L_SHIFT), 'P': (0x19, MOD_L_SHIFT),
    'A': (0x1E, MOD_L_SHIFT), 'S': (0x1F, MOD_L_SHIFT), 'D': (0x20, MOD_L_SHIFT), 'F': (0x21, MOD_L_SHIFT),
    'G': (0x22, MOD_L_SHIFT), 'H': (0x23, MOD_L_SHIFT), 'J': (0x24, MOD_L_SHIFT), 'K': (0x25, MOD_L_SHIFT),
    'L': (0x26, MOD_L_SHIFT),
    'Z': (0x2C, MOD_L_SHIFT), 'X': (0x2D, MOD_L_SHIFT), 'C': (0x2E, MOD_L_SHIFT), 'V': (0x2F, MOD_L_SHIFT),
    'B': (0x30, MOD_L_SHIFT), 'N': (0x31, MOD_L_SHIFT), 'M': (0x32, MOD_L_SHIFT),

    # Symbols (Shifted Numbers)
    '!': (0x02, MOD_L_SHIFT), '@': (0x03, MOD_L_SHIFT), '#': (0x04, MOD_L_SHIFT), '$': (0x05, MOD_L_SHIFT),
    '%': (0x06, MOD_L_SHIFT), '^': (0x07, MOD_L_SHIFT), '&': (0x08, MOD_L_SHIFT), '*': (0x09, MOD_L_SHIFT),
    '(': (0x0A, MOD_L_SHIFT), ')': (0x0B, MOD_L_SHIFT),

    # Special Characters
    '-': (0x0C, MOD_NONE), '_': (0x0C, MOD_L_SHIFT),
    '=': (0x0D, MOD_NONE), '+': (0x0D, MOD_L_SHIFT),
    '[': (0x1A, MOD_NONE), '{': (0x1A, MOD_L_SHIFT),
    ']': (0x1B, MOD_NONE), '}': (0x1B, MOD_L_SHIFT),
    '\\':(0x2B, MOD_NONE), '|': (0x2B, MOD_L_SHIFT),
    ';': (0x27, MOD_NONE), ':': (0x27, MOD_L_SHIFT),
    '\'':(0x28, MOD_NONE), '"': (0x28, MOD_L_SHIFT),
    ',': (0x33, MOD_NONE), '<': (0x33, MOD_L_SHIFT),
    '.': (0x34, MOD_NONE), '>': (0x34, MOD_L_SHIFT),
    '/': (0x35, MOD_NONE), '?': (0x35, MOD_L_SHIFT),
    ' ': (0x39, MOD_NONE), 

    # Key Names
    'enter': (0x1C, MOD_NONE),
    'esc':   (0x01, MOD_NONE),
    'bs':    (0x0E, MOD_NONE),
    'tab':   (0x0F, MOD_NONE),
    'ctrl':  (0x1D, MOD_NONE),
    'shift': (0x2A, MOD_NONE),
    'alt':   (0x38, MOD_NONE),
}

def get_hid_code(char_key):
    """
    문자 또는 키 이름을 받아 (MakeCode, Modifier) 튜플을 반환
    """
    # 1. 단일 문자인 경우 바로 매핑 확인
    if len(char_key) == 1:
        return ASCII_TO_MAKECODE.get(char_key, (None, None))
    
    # 2. 'enter', 'tab' 등 특수 키 이름인 경우
    return ASCII_TO_MAKECODE.get(char_key.lower(), (None, None))
