# -*- coding: utf-8 -*-
"""조합키·키보드 시험: GTB-3000 Keyboard 탭에 키를 보내고 화면 표시로 바로 채점.

GTB 화면: LAST KEY = "KEY <VK> SC <스캔> E<확장> M <수식키 C/S/A/W>", COUNT = 받은 키 수, HELD = 지금 눌린 수식키,
          COPY FROM / PASTE TO / CLIPBOARD (복사·붙여넣기 시험)
판정 (키마다): 받음(COUNT +1) · VK 일치 · 스캔코드 일치 · 확장키 일치 · 수식키 일치 · 끝난 뒤 눌린 키 없음(HELD '-')

  python tools/key_bench.py [--exe "%USERPROFILE%\\Desktop\\dist\\GTB3000.exe"] [--only letters,combo,...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghost import build_device, config  # noqa: E402
from ghost.hal import keymap  # noqa: E402
from ghost.vision.ocr import OcrEngine, group_lines, narrow, text_matches  # noqa: E402

MODS = {"ctrl": "C", "rctrl": "C", "shift": "S", "rshift": "S", "alt": "A", "ralt": "A", "win": "W", "rwin": "W"}

# (묶음, 보낼 조합, 뒤처리) — 뒤처리: 상태를 되돌리는 키 (메뉴 닫기, 토글 원복 등)
def cases():
    out = []
    for c in "abcdefghijklmnopqrstuvwxyz":
        out.append(("letters", [c], None))
    for c in "1234567890":
        out.append(("digits", [c], None))
    for c in "-=[]\\;',./`":
        out.append(("punct", [c], None))
    for i in range(1, 13):
        out.append(("fkeys", [f"f{i}"], ["esc"] if i == 10 else None))      # F10 = 메뉴 활성
    for k in ["enter", "esc", "tab", "backspace", "space", "insert", "delete", "home", "end", "pageup", "pagedown",
              "up", "down", "left", "right"]:
        out.append(("edit_nav", [k], None))
    out.append(("toggle", ["capslock"], ["capslock"]))
    out.append(("toggle", ["numlock"], ["numlock"]))
    out.append(("toggle", ["scrolllock"], ["scrolllock"]))
    out.append(("special", ["printscreen"], None))
    out.append(("special", ["menu"], ["esc"]))
    for k in ["num0", "num1", "num5", "num9", "num*", "num+", "num-", "num.", "num/", "numenter"]:
        out.append(("numpad", [k], None))
    out.append(("korean", ["hangul"], ["hangul"]))
    out.append(("korean", ["hanja"], ["esc"]))
    for k in ["a", "c", "v", "x", "z", "y", "s", "f", "home", "end"]:
        out.append(("ctrl", ["ctrl", k], ["esc"] if k in ("f", "s") else None))
    for k in ["left", "right", "home", "end", "1", "/", "a"]:
        out.append(("shift", ["shift", k], None))
    for k in ["left", "right", "end", "home"]:
        out.append(("ctrl_shift", ["ctrl", "shift", k], None))
    for k in ["f", "r", "t"]:
        out.append(("alt", ["alt", k], ["esc", "esc"]))                       # 메뉴 열림 → 닫기
    out.append(("right_mods", ["rctrl", "c"], None))
    out.append(("right_mods", ["rshift", "a"], None))
    out.append(("right_mods", ["ralt", "a"], ["esc"]))
    return out


def expect(combo):
    k = keymap.key(combo[-1])
    mods = "".join(sorted({MODS[m] for m in combo[:-1]}, key="CSAW".index)) or "-"
    return {"vk": k.vk, "sc": k.scan, "ext": int(k.extended), "mods": mods}


LAST_RE = re.compile(r"KEY\s*([0-9A-FO]{2})\s*SC\s*([0-9A-FO]{2})\s*E\s*([01OI])\s*M\s*([CSAW\-]+)")


def parse_last(text):
    t = text.upper().replace(" ", " ")
    m = LAST_RE.search(t.replace("O", "0") if False else t)
    if not m:
        return None
    hx = lambda v: int(v.replace("O", "0"), 16)
    return {"vk": hx(m.group(1)), "sc": hx(m.group(2)), "ext": 1 if m.group(3) in ("1", "I") else 0, "mods": m.group(4)}


class Bench:
    def __init__(self, a):
        self.a = a
        self.cfg = config.load(a.config)
        self.cfg["blackbox"]["video"]["enabled"] = False
        self.dev = build_device(self.cfg, log=print)
        self.ocr = OcrEngine(self.cfg, self.cfg["_base_dir"], log=print)
        self.out = os.path.join(config.path(self.cfg, "runs"), "bench_keys_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.out, exist_ok=True)
        self.reg = {}

    def frame(self, wait=0.35):
        time.sleep(wait)
        return self.dev.frame()

    def read(self, f, key, h=None):
        x, y, w, hh = self.reg[key]
        return " ".join(t.text for t in self.ocr.read(f, (x, y, w, h or hh)))

    def find(self, f, label):
        hits = self.ocr.read(f)
        for mode in ("exact", "contains"):
            for t in hits + group_lines(hits):
                if text_matches(t.text, label, mode):
                    return narrow(t, label, mode)
        return None

    def launch(self):
        d = self.dev
        d.hotkey("win", "r")
        time.sleep(1.2)
        d.press("home")
        d.hotkey("shift", "end")
        d.type_text(f'"{self.a.exe}" /user=operator /seed=1 /tab=5')
        d.press("enter")
        t0 = time.time()
        while time.time() - t0 < 25:
            f = self.frame(1.0)
            cap = self.find(f, "LAST KEY")
            if cap:
                break
        else:
            raise SystemExit("GTB-3000 Keyboard 탭이 보이지 않음")
        # 캡션 기준 값 영역 (GTB 소스의 배치: 캡션 x=12 → 값 x=150, 행마다 높이)
        cx, cy = cap.box[0], cap.box[1]
        dx = 138
        self.reg = {"last": (cx + dx - 6, cy - 12, 720, 56), "held": (cx + dx - 6, cy + 50, 300, 46),
                    "count": (cx + dx + 384, cy + 50, 220, 46), "input": (cx + dx, cy + 108, 700, 120),
                    "copy": (cx + dx, cy + 250, 300, 30), "paste": (cx + dx, cy + 290, 300, 30),
                    "clip": (cx + dx - 4, cy + 328, 720, 40)}
        cv2.imwrite(os.path.join(self.out, "keyboard_tab.png"), f)
        self.click_input()

    def click_input(self):
        x, y, w, h = self.reg["input"]
        self.dev.click(x + 200, y + 40)

    def count(self, f):
        t = re.sub(r"[^0-9]", "", self.read(f, "count").replace("O", "0").replace("o", "0"))
        return int(t) if t else None

    def run_keys(self):
        res = []
        f = self.frame()
        n0 = self.count(f)
        for group, combo, after in cases():
            if self.a.only and group not in self.a.only.split(","):
                continue
            exp = expect(combo)
            t0 = time.time()
            if len(combo) == 1:
                self.dev.press(combo[0])
            else:
                self.dev.hotkey(*combo)
            f = self.frame(0.45)
            raw = self.read(f, "last")
            got = parse_last(raw)
            n1 = self.count(f)
            held = self.read(f, "held").strip() or "?"
            r = {"group": group, "combo": "+".join(combo), "expect": exp, "got": got, "raw": raw,
                 "received": None if n0 is None or n1 is None else n1 - n0, "held": held}
            r["ok"] = {"received": r["received"] == 1,
                       "vk": bool(got) and got["vk"] == exp["vk"], "sc": bool(got) and got["sc"] == exp["sc"],
                       "ext": bool(got) and got["ext"] == exp["ext"], "mods": bool(got) and got["mods"] == exp["mods"],
                       "released": held in ("-", "—", "_")}
            r["pass"] = all(r["ok"].values())
            res.append(r)
            mark = "✓" if r["pass"] else "✗ " + ",".join(k for k, v in r["ok"].items() if not v)
            print(f"  [{group}] {r['combo']:<18} → {raw!r:<36} 수신 {r['received']} 남은키 {held!r} {mark}")
            n0 = n1 if n1 is not None else n0
            if after:
                for k in after:
                    self.dev.press(k)
                    time.sleep(0.2)
                f = self.frame(0.4)
                n0 = self.count(f)
                self.click_input()
        return res

    def run_clipboard(self):
        d, out = self.dev, []
        def check(name, ok, detail):
            out.append({"test": name, "pass": ok, "detail": detail})
            print(f"  [clipboard] {name}: {'✓' if ok else '✗'} {detail}")
        x, y, w, h = self.reg["copy"]
        d.click(x + 100, y + 14)
        d.hotkey("ctrl", "a")
        d.hotkey("ctrl", "c")
        f = self.frame(0.8)
        clip = self.read(f, "clip")
        check("Ctrl+A, Ctrl+C (읽기 전용 칸)", "GHOST-COPY-7319" in clip.replace(" ", ""), clip)
        px, py, pw, ph = self.reg["paste"]
        d.click(px + 100, py + 14)
        d.hotkey("ctrl", "a")
        d.press("delete")
        d.hotkey("ctrl", "v")
        f = self.frame(0.6)
        pasted = self.read(f, "paste")
        check("Ctrl+V (붙여넣기)", "GHOST-COPY-7319" in pasted.replace(" ", ""), pasted)
        d.hotkey("ctrl", "a")
        d.hotkey("ctrl", "x")
        f = self.frame(0.6)
        after_cut, clip2 = self.read(f, "paste"), self.read(f, "clip")
        check("Ctrl+X (잘라내기: 칸 비고 클립보드 유지)", after_cut.strip() == "" and "GHOST-COPY-7319" in clip2.replace(" ", ""),
              f"칸={after_cut!r} 클립보드={clip2!r}")
        d.hotkey("ctrl", "z")
        f = self.frame(0.6)
        undo = self.read(f, "paste")
        check("Ctrl+Z (되돌리기)", "GHOST-COPY-7319" in undo.replace(" ", ""), undo)
        d.hotkey("ctrl", "a")
        d.press("delete")
        d.type_text("Hello-GHOST_42")
        d.press("home")
        d.hotkey("shift", "end")
        d.hotkey("ctrl", "c")
        f = self.frame(0.8)
        clip3 = self.read(f, "clip")
        check("입력 → Shift+End 선택 → Ctrl+C", "Hello-GHOST_42".lower() in clip3.replace(" ", "").lower(), clip3)
        return out

    def close(self):
        d = self.dev
        f = self.frame()
        t = self.find(f, "GTB-3000 Analyzer")
        if t:
            d.click(*t.center)
        d.hotkey("alt", "f4")
        time.sleep(1.2)
        d.press("y")
        time.sleep(1.5)

    def run(self):
        self.dev.open(home=True)
        try:
            self.launch()
            keys = self.run_keys()
            clip = [] if self.a.only else self.run_clipboard()
            self.close()
        finally:
            self.dev.close()
        rep = {"keys": keys, "clipboard": clip}
        json.dump(rep, open(os.path.join(self.out, "keys.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        groups = {}
        for r in keys:
            g = groups.setdefault(r["group"], [0, 0])
            g[0] += r["pass"]
            g[1] += 1
        print("\n묶음별:", ", ".join(f"{g} {p}/{n}" for g, (p, n) in groups.items()))
        print(f"전체 {sum(r['pass'] for r in keys)}/{len(keys)}, 클립보드 {sum(c['pass'] for c in clip)}/{len(clip)}")
        print("결과:", self.out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    p.add_argument("--exe", default="%USERPROFILE%\\Desktop\\dist\\GTB3000.exe")
    p.add_argument("--only", help="묶음만 (letters,digits,punct,fkeys,edit_nav,toggle,special,numpad,korean,ctrl,shift,ctrl_shift,alt,right_mods)")
    Bench(p.parse_args()).run()


if __name__ == "__main__":
    main()
