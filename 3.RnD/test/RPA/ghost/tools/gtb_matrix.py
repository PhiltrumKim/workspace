# -*- coding: utf-8 -*-
"""난이도 조합 성공률: GTB-3000 측정 작업(gtb_measure)을 조건마다 N번 반복해 성공률·소요 시간·알람 처리를 표로.

  python tools/gtb_matrix.py [--runs 5] [--only baseline,dark]

조건마다 창 위치가 다르도록 실행마다 /seed 를 바꾼다. 결과: runs/matrix_<시각>/matrix.json, matrix.md
판독값(value)은 GTB 정답 로그(cycle_done)와 나중에 대조할 수 있게 실행 시각과 함께 남긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghost import build_device, build_runner, config  # noqa: E402
from ghost.scenario import model  # noqa: E402

TS = "/timescale=0.3"
CONDITIONS = [
    ("baseline", "기본", TS),
    ("slow_ui", "응답 지연 0.8초", f"/delay=800 {TS}"),
    ("alarms", "알람 분당 12회", f"/alarm=12 {TS}"),
    ("randompos", "창 위치 무작위", f"/randompos {TS}"),
    ("dark", "어두운 스타일", f"/style=dark {TS}"),
    ("classic", "고전 스타일", f"/style=classic {TS}"),
    ("smallfont", "작은 글꼴", f"/smallfont {TS}"),
    ("all_hard", "모두 (지연+알람+무작위 위치+어두움+작은 글꼴)", f"/delay=800 /alarm=12 /randompos /style=dark /smallfont {TS}"),
]
RECIPES = ["RCP-003", "RCP-012", "RCP-021", "RCP-027"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--only")
    a = p.parse_args()
    cfg = config.load(a.config)
    out = os.path.join(config.path(cfg, "runs"), "matrix_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=True)
    log = open(os.path.join(out, "matrix.log"), "w", encoding="utf-8")

    def say(m):
        print(m, flush=True)
        log.write(m + "\n")
        log.flush()

    dev = build_device(cfg, log=lambda m: log.write(m + "\n"))
    runner = build_runner(cfg, dev, log=lambda m: log.write(m + "\n"))
    sc = model.load(model.find_path("gtb_measure", runner.scenario_dirs), runner.reg)
    dev.open(home=True)
    results = []
    conds = [c for c in CONDITIONS if not a.only or c[0] in a.only.split(",")]
    try:
        for key, name, args in conds:
            for i in range(a.runs):
                recipe = RECIPES[i % len(RECIPES)]
                lot = f"LOT-{key[:3].upper()}{i + 1}"
                params = {"args": f"{args} /seed={101 + i}", "recipe": recipe, "lot": lot}
                t0 = time.time()
                res = runner.run(sc, params)
                fail = next((s for s in res.steps if not s.ok), None)
                r = {"cond": key, "run": i + 1, "ok": res.ok, "sec": round(time.time() - t0, 1),
                     "value": res.values.get("value"), "recipe": recipe, "lot": lot, "t": t0,
                     "alarms": sum(1 for e in res.watch_events if e.get("kind") == "appeared"),
                     "fail_step": fail and fail.desc, "fail_msg": fail and fail.message,
                     "error": res.error, "run_dir": os.path.basename(res.run_dir or "")}
                results.append(r)
                say(f"[{key} {i + 1}/{a.runs}] {'성공' if res.ok else '실패'} {r['sec']}s 값={r['value']} 알람={r['alarms']}"
                    + ("" if res.ok else f"  ✗ {r['fail_step']} → {r['fail_msg'] or r['error']}"))
                json.dump(results, open(os.path.join(out, "matrix.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                if not res.ok:                       # 다음 실행 전 정리 (GTB 가 남아 있으면 닫기)
                    try:
                        runner.run(model.load(model.find_path("gtb_close", runner.scenario_dirs), runner.reg))
                    except Exception:
                        pass
    finally:
        dev.close()
    rows = ["| 조건 | 성공 | 평균 시간 | 알람 처리 | 실패 단계 |", "|---|---|---|---|---|"]
    for key, name, _ in conds:
        rs = [r for r in results if r["cond"] == key]
        if not rs:
            continue
        ok = [r for r in rs if r["ok"]]
        avg = sum(r["sec"] for r in ok) / len(ok) if ok else 0
        fails = "; ".join(sorted({(r["fail_step"] or r["error"] or "?")[:40] for r in rs if not r["ok"]}))
        rows.append(f"| {name} | {len(ok)}/{len(rs)} | {avg:.0f}s | {sum(r['alarms'] for r in rs)}건 | {fails or '-'} |")
    total = sum(r["ok"] for r in results)
    rows.append(f"| **전체** | **{total}/{len(results)}** | | | |")
    md = "\n".join(rows)
    open(os.path.join(out, "matrix.md"), "w", encoding="utf-8").write(md + "\n")
    say("\n" + md)
    say(f"결과: {out}")


if __name__ == "__main__":
    main()
