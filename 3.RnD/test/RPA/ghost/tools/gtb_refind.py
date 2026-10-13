# -*- coding: utf-8 -*-
"""저장된 화면별 OCR 결과(bench.json)로 글자 찾기를 다시 계산 (찾기 알고리즘을 바꾼 뒤 실장비 없이 비교).
  python tools/gtb_refind.py runs/bench_gtb_...   → bench_refind.json (gtb_score.py 에 같은 형식으로 넣을 수 있음)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghost.vision.ocr import TextHit, group_lines, narrow, text_matches  # noqa: E402


def find_label(hits, label):
    for mode in ("exact", "contains"):
        for h in hits + group_lines(hits):
            if text_matches(h.text, label, mode):
                return narrow(h, label, mode), mode
    return None, None


def main(d):
    b = json.load(open(os.path.join(d, "bench.json"), encoding="utf-8"))
    for rec in b["styles"].values():
        for t in rec.get("tabs", {}).values():
            if "ocr" not in t:
                continue
            hits = [TextHit(o["text"], tuple(o["box"]), o["conf"]) for o in t["ocr"]]
            for label in t["found"]:
                h, mode = find_label(hits, label)
                t["found"][label] = None if h is None else {"box": list(h.box), "center": list(h.center),
                                                            "text": h.text, "conf": h.conf, "mode": mode}
    out = os.path.join(d, "refind")
    os.makedirs(out, exist_ok=True)
    json.dump(b, open(os.path.join(out, "bench.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", out)


if __name__ == "__main__":
    main(sys.argv[1])
