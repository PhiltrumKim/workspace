# -*- coding: utf-8 -*-
"""한글 → 두벌식 자판 키 순서. 대상 PC 의 한글 입력기(IME)가 자판 순서를 다시 한글로 조합한다.

  "한글" → "gksrmf",  "값" → "rkqt"
  segments("GHOST 한글 123") → [("en", "GHOST "), ("ko", "gksrmf"), ("en", " 123")]
    공백·숫자·기호는 어느 모드에서나 그대로 입력되므로 앞 구간에 붙인다 (한/영 전환 횟수 최소화)
"""
from __future__ import annotations

from typing import List, Tuple

CHO = ["r", "R", "s", "e", "E", "f", "a", "q", "Q", "t", "T", "d", "w", "W", "c", "z", "x", "v", "g"]
JUNG = ["k", "o", "i", "O", "j", "p", "u", "P", "h", "hk", "ho", "hl", "y", "n", "nj", "np", "nl", "b", "m", "ml", "l"]
JONG = ["", "r", "R", "rt", "s", "sw", "sg", "e", "f", "fr", "fa", "fq", "ft", "fx", "fv", "fg", "a", "q", "qt", "t",
        "T", "d", "w", "c", "z", "x", "v", "g"]
# 낱자 (ㄱ ~ ㅣ, U+3131 ~ U+3163)
JAMO = {
    "ㄱ": "r", "ㄲ": "R", "ㄳ": "rt", "ㄴ": "s", "ㄵ": "sw", "ㄶ": "sg", "ㄷ": "e", "ㄸ": "E", "ㄹ": "f", "ㄺ": "fr",
    "ㄻ": "fa", "ㄼ": "fq", "ㄽ": "ft", "ㄾ": "fx", "ㄿ": "fv", "ㅀ": "fg", "ㅁ": "a", "ㅂ": "q", "ㅃ": "Q", "ㅄ": "qt",
    "ㅅ": "t", "ㅆ": "T", "ㅇ": "d", "ㅈ": "w", "ㅉ": "W", "ㅊ": "c", "ㅋ": "z", "ㅌ": "x", "ㅍ": "v", "ㅎ": "g",
    "ㅏ": "k", "ㅐ": "o", "ㅑ": "i", "ㅒ": "O", "ㅓ": "j", "ㅔ": "p", "ㅕ": "u", "ㅖ": "P", "ㅗ": "h", "ㅘ": "hk",
    "ㅙ": "ho", "ㅚ": "hl", "ㅛ": "y", "ㅜ": "n", "ㅝ": "nj", "ㅞ": "np", "ㅟ": "nl", "ㅠ": "b", "ㅡ": "m", "ㅢ": "ml",
    "ㅣ": "l",
}


def is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣" or ch in JAMO


def to_keys(ch: str) -> str:
    """한글 한 글자 → 두벌식 키 문자열."""
    if ch in JAMO:
        return JAMO[ch]
    code = ord(ch) - 0xAC00
    if not 0 <= code < 11172:
        raise ValueError(f"한글이 아님: {ch!r}")
    cho, rest = divmod(code, 21 * 28)
    jung, jong = divmod(rest, 28)
    return CHO[cho] + JUNG[jung] + JONG[jong]


def segments(text: str) -> List[Tuple[str, str]]:
    """[(모드 'en'|'ko', 칠 키 문자열)]. 영문 글자만 영문 모드가 필요하고, 그 밖의 글자는 현재 모드에 붙인다."""
    out: List[Tuple[str, str]] = []
    mode = "en"
    for ch in text:
        if is_hangul(ch):
            want, keys = "ko", to_keys(ch)
        elif ch.isascii() and ch.isalpha():
            want, keys = "en", ch
        else:
            want, keys = mode, ch                       # 공백·숫자·기호: 모드 무관
        if out and out[-1][0] == want:
            out[-1] = (want, out[-1][1] + keys)
        else:
            out.append((want, keys))
        mode = want
    return out
