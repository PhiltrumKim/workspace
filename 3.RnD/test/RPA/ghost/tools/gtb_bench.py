# -*- coding: utf-8 -*-
"""GTB-3000 인식률 측정 (1단계: 대상 찾기).

스타일(native/classic/flat/dark)마다 GTB-3000 을 띄우고 탭 5개를 돌며
  - 화면 전체 OCR 결과(글자·위치)를 저장하고, 알려진 화면 글자 목록을 OCR 로 찾은 위치를 기록
  - 기본 스타일에서 잘라 둔 그림(탭·버튼·툴바)으로 다른 스타일에서 템플릿 매칭한 위치를 기록
채점(찾은 위치가 실제 요소 안에 드는지)은 대상 PC 의 정답 로그(logs/gtb_*.csv)를 가져온 뒤 gtb_score.py 로 한다.

  python tools/gtb_bench.py --exe "%USERPROFILE%\\Desktop\\dist\\GTB3000.exe" [--styles native,classic,flat,dark]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghost import build_device, config  # noqa: E402
from ghost.hal.base import DeviceError  # noqa: E402
from ghost.vision import matcher  # noqa: E402
from ghost.vision.ocr import OcrEngine, TextHit, group_lines, narrow, normalize, text_matches  # noqa: E402

TABS = ["Recipe", "Run Monitor", "Results", "Alarm Log", "Settings"]
# 화면 글자로 찾을 대상 (탭별). GTB-3000 소스의 컨트롤 글자 그대로
LABELS = {
    "*": ["File", "Recipe", "Run", "Tools", "Help", "Start", "Pause", "Stop", "Alarm Reset", "Export",
          "Run Monitor", "Results", "Alarm Log", "Settings"],
    "Recipe": ["Recipe Parameters (레시피 파라미터)", "LOT ID", "Sample Type", "Temperature (°C)", "Repeat (반복)",
               "Auto Calibration (자동 보정)", "Save Raw Data", "Load Recipe (불러오기)", "Apply Parameters",
               "Loaded: (없음)", "RCP-001", "RCP-002", "RCP-003", "RCP-005", "RCP-010", "Gate CD 선폭", "파티클 카운트"],
}
TEMPLATE_KEYS = ["Run Monitor", "Results", "Alarm Log", "Settings", "Load Recipe (불러오기)", "Apply Parameters",
                 "Alarm Reset", "Export", "RCP-001"]


class Bench:
    def __init__(self, args):
        self.cfg = config.load(args.config)
        self.cfg["blackbox"]["video"]["enabled"] = False
        self.dev = build_device(self.cfg, log=print)
        self.ocr = OcrEngine(self.cfg, self.cfg["_base_dir"], log=print)
        self.out = os.path.join(config.path(self.cfg, "runs"), "bench_gtb_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.out, exist_ok=True)
        self.args = args
        self.templates = {}
        self.result = {"exe": args.exe, "started": time.time(), "styles": {}}

    # ------------------------------------------------------------ 조작
    def run_dialog(self, text: str) -> None:
        d = self.dev
        d.hotkey("win", "r")
        time.sleep(1.2)
        d.press("home")
        d.hotkey("shift", "end")
        d.type_text(text)
        d.press("enter")

    def park(self) -> None:
        self.dev.move_to(1900, 1060)                # 커서가 글자를 가리지 않게

    def frame(self):
        time.sleep(0.4)
        return self.dev.frame()

    def full_ocr(self, f):
        t0 = time.time()
        hits = self.ocr.read(f)
        return hits, round(time.time() - t0, 2)

    def find_label(self, hits, label):
        """OCR 결과에서 label 찾기: 완전 일치 → 포함 순 (GHOST 텍스트 target 과 같은 비교). 첫 결과."""
        cands = hits + group_lines(hits)
        for mode in ("exact", "contains"):
            for h in cands:
                if text_matches(h.text, label, mode):
                    return narrow(h, label, mode), mode
        return None, None

    def wait_for_text(self, label, timeout=20.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            f = self.frame()
            hits = self.ocr.read(f)
            h, _ = self.find_label(hits, label)
            if h is not None:
                return f, hits
            time.sleep(1.0)
        return None, None

    # ------------------------------------------------------------ 측정
    def run_style(self, style: str) -> dict:
        print(f"\n=== 스타일 {style} ===")
        sd = os.path.join(self.out, style)
        os.makedirs(sd, exist_ok=True)
        rec = {"style": style, "tabs": {}, "launch_t": time.time()}
        self.run_dialog(f'"{self.args.exe}" /user=operator /seed=1 /style={style}')
        self.park()
        f, hits = self.wait_for_text("Recipe Parameters", 25)
        if f is None:
            rec["error"] = "GTB-3000 화면이 뜨지 않음"
            cv2.imwrite(os.path.join(sd, "launch_fail.png"), self.dev.frame())
            return rec
        for i, tab in enumerate(TABS):
            if i > 0:
                h, _ = self.find_label(hits, tab)
                if h is None:
                    rec["tabs"][tab] = {"error": "탭 글자를 못 찾음"}
                    continue
                self.dev.click(*h.center)
                self.park()
                time.sleep(1.0)
            f = self.frame()
            hits, ocr_s = self.full_ocr(f)
            cv2.imwrite(os.path.join(sd, f"tab{i}_{tab.replace(' ', '_')}.png"), f)
            found = {}
            for label in LABELS["*"] + LABELS.get(tab, []):
                h, mode = self.find_label(hits, label)
                found[label] = None if h is None else {"box": list(h.box), "center": list(h.center), "text": h.text,
                                                       "conf": h.conf, "mode": mode}
            tm = {}
            if style == "native":
                for key in TEMPLATE_KEYS:
                    if found.get(key) and key not in self.templates:
                        x, y, w, hh = found[key]["box"]
                        pad = 6
                        crop = f[max(0, y - pad):y + hh + pad, max(0, x - pad):x + w + pad].copy()
                        self.templates[key] = crop
                        cv2.imwrite(os.path.join(self.out, f"tpl_{key[:20].replace(' ', '_')}.png"), crop)
            for key, tpl in self.templates.items():
                t0 = time.time()
                m = matcher.find(f, tpl, threshold=0.0)
                tm[key] = {"center": list(m.center), "box": list(m.box), "score": round(m.score, 3),
                           "ms": round((time.time() - t0) * 1000)} if m else None
            rec["tabs"][tab] = {"t": time.time(), "ocr_s": ocr_s,
                                "ocr": [{"text": h.text, "box": list(h.box), "conf": h.conf} for h in hits],
                                "found": found, "template": tm}
            n_found = sum(1 for v in found.values() if v)
            print(f"  [{tab}] OCR {len(hits)}개 ({ocr_s}s), 글자 대상 {n_found}/{len(found)} 찾음, 템플릿 {len(tm)}개 시도")
        self.close_gtb()
        return rec

    def close_gtb(self) -> None:
        d = self.dev
        f, hits = self.frame(), None
        hits = self.ocr.read(f)
        h, _ = self.find_label(hits, "GTB-3000")
        if h is not None:                            # 제목줄을 눌러 초점
            d.click(h.center[0], h.center[1])
        d.hotkey("alt", "f4")
        time.sleep(1.2)
        d.press("y")                                 # 종료 확인 (예)
        time.sleep(1.5)
        f = self.frame()
        if self.find_label(self.ocr.read(f), "Recipe Parameters")[0] is not None:
            d.press("enter")
            time.sleep(1.5)

    def run(self):
        self.dev.open(home=True)
        try:
            for style in self.args.styles.split(","):
                try:
                    self.result["styles"][style] = self.run_style(style)
                except DeviceError as e:
                    self.result["styles"][style] = {"error": f"장치 오류: {e}"}
                with open(os.path.join(self.out, "bench.json"), "w", encoding="utf-8") as fp:
                    json.dump(self.result, fp, ensure_ascii=False, indent=1)
        finally:
            self.dev.close()
        print(f"\n결과: {self.out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    p.add_argument("--exe", default="%USERPROFILE%\\Desktop\\dist\\GTB3000.exe")
    p.add_argument("--styles", default="native,classic,flat,dark")
    Bench(p.parse_args()).run()


if __name__ == "__main__":
    main()
