# -*- coding: utf-8 -*-
"""GTB-3000 인식률 채점: gtb_bench.py 결과(bench.json) + 대상 PC 정답 로그(logs/gtb_*.csv).

  python tools/gtb_score.py runs/bench_gtb_YYYYMMDD_HHMMSS  path/to/logs

판정 (찾은 위치의 중심점 기준)
  정확    : 그 글자를 가진 실제 화면 요소(메뉴·탭·버튼·표 행 등) 안
  오인식  : 찾았다고 했지만 다른 곳 (다른 요소 위 또는 빈 곳)
  못 찾음 : 찾지 못함 (그림 찾기는 일치도 0.8 미만)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghost.vision.ocr import normalize  # noqa: E402

TPL_THRESHOLD = 0.8


def parse_detail(d: str) -> dict:
    out = {}
    head, _, text = d.partition(";text=")
    for kv in head.split(";"):
        k, _, v = kv.partition("=")
        out[k] = v
    out["text"] = text
    return out


def load_truth(path: str):
    """CSV 하나 → (style, {탭: [요소...]}). 탭마다 마지막으로 기록된 화면."""
    style, blocks, cur = None, {}, None
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ev, d = row["event"], row["detail"]
            if ev == "app_start":
                style = dict(kv.split("=", 1) for kv in d.split(";") if "=" in kv).get("style")
            elif ev == "ui_begin":
                tab = parse_detail(d).get("tab")
                cur = blocks.setdefault(tab, [])
                cur.clear()
            elif ev == "ui" and cur is not None:
                e = parse_detail(d)
                x, y, w, h = (int(v) for v in e["rect"].split())
                cur.append({"kind": e["kind"], "rect": (x, y, w, h), "text": e["text"], "enabled": e.get("enabled") == "1"})
            elif ev == "ui_end":
                cur = None
    return style, blocks


def inside(pt, r, margin=2) -> bool:
    x, y, w, h = r
    return x - margin <= pt[0] <= x + w + margin and y - margin <= pt[1] <= y + h + margin


def expected(elems: List[dict], label: str) -> List[dict]:
    q = normalize(label)
    exact = [e for e in elems if normalize(e["text"]) == q]
    return exact or [e for e in elems if q and q in normalize(e["text"])]


def judge(pt, label, elems):
    exp = expected(elems, label)
    if not exp:
        return "no_truth"
    if pt is None:
        return "missing"
    return "correct" if any(inside(pt, e["rect"]) for e in exp) else "wrong"


def score(bench_dir: str, logs_dir: str) -> dict:
    bench = json.load(open(os.path.join(bench_dir, "bench.json"), encoding="utf-8"))
    truths: Dict[str, dict] = {}
    for p in sorted(glob.glob(os.path.join(logs_dir, "gtb_*.csv"))):      # 같은 스타일이면 마지막 파일
        style, blocks = load_truth(p)
        if style and blocks:
            truths[style] = blocks
    out = {"styles": {}}
    for style, rec in bench["styles"].items():
        tb = truths.get(style)
        res = {"text": {"correct": 0, "wrong": 0, "missing": 0}, "template": {"correct": 0, "wrong": 0, "missing": 0},
               "ocr_s": [], "details": []}
        if not tb or "tabs" not in rec:
            res["error"] = "정답 로그 없음" if not tb else rec.get("error", "측정 없음")
            out["styles"][style] = res
            continue
        for tab, t in rec["tabs"].items():
            elems = tb.get(tab)
            if not elems or "found" not in t:
                continue
            res["ocr_s"].append(t["ocr_s"])
            for label, hit in t["found"].items():
                j = judge(hit["center"] if hit else None, label, elems)
                if j != "no_truth":
                    res["text"][j] += 1
                    if j != "correct":
                        res["details"].append({"tab": tab, "how": "글자", "label": label, "result": j,
                                               "got": hit and hit["text"], "at": hit and hit["center"]})
            for key, m in (t.get("template") or {}).items():
                pt = m["center"] if m and m["score"] >= TPL_THRESHOLD else None
                j = judge(pt, key, elems)
                if j != "no_truth":
                    res["template"][j] += 1
                    if j != "correct":
                        res["details"].append({"tab": tab, "how": "그림", "label": key, "result": j,
                                               "score": m and m["score"]})
        for k in ("text", "template"):
            n = sum(res[k].values())
            res[k]["n"] = n
            res[k]["rate"] = round(100.0 * res[k]["correct"] / n, 1) if n else None
        res["ocr_avg_s"] = round(sum(res["ocr_s"]) / len(res["ocr_s"]), 2) if res["ocr_s"] else None
        out["styles"][style] = res
    return out


def main():
    bench_dir, logs_dir = sys.argv[1], sys.argv[2]
    r = score(bench_dir, logs_dir)
    print(f"{'스타일':<8} {'글자 찾기':>18} {'그림 찾기':>18} {'OCR 1화면':>10}")
    for style, s in r["styles"].items():
        if "error" in s:
            print(f"{style:<8} {s['error']}")
            continue
        t, m = s["text"], s["template"]
        print(f"{style:<8} {t['rate']:>6}% ({t['correct']}/{t['n']}, 오 {t['wrong']}) "
              f"{(m['rate'] if m['rate'] is not None else '-'):>6}% ({m['correct']}/{m['n']}, 오 {m['wrong']}) {s['ocr_avg_s']:>8}s")
        for d in s["details"][:12]:
            print("   ", d)
    with open(os.path.join(bench_dir, "score.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
