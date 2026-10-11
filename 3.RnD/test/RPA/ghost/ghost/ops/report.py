# -*- coding: utf-8 -*-
"""운영 결과 보고서: 시나리오별 성공률·소요 시간·알람·읽은 값 통계, CSV, 단일 파일 HTML(인라인 SVG 추세).

외부 라이브러리 없이 만든다 (폐쇄망, 브라우저만 있으면 열림).
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import statistics
import time
from typing import Dict, List, Optional

from .store import Store

STATUS_KO = {"ok": "성공", "failed": "실패", "error": "장치 오류", "stopped": "중지", "cancelled": "취소",
             "interrupted": "중단", "queued": "대기", "running": "실행 중"}
STATUS_COLOR = {"ok": "#2e9d5b", "failed": "#d64545", "error": "#c77c0e", "stopped": "#7b8794",
                "cancelled": "#9aa5b1", "interrupted": "#8e6cc4"}
FINISHED = ("ok", "failed", "error", "stopped", "interrupted")


def _num(v) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _pct(xs: List[float], p: float) -> float:
    xs = sorted(xs)
    k = min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))
    return xs[k]


def summarize(store: Store, since: Optional[float] = None, until: Optional[float] = None) -> dict:
    jobs = [j for j in store.jobs(limit=100000, since=since)
            if j["status"] in FINISHED and (until is None or (j["created"] or 0) < until)]
    jobs.sort(key=lambda j: j["id"])
    per: Dict[str, dict] = {}
    for j in jobs:
        s = per.setdefault(j["scenario"], {"scenario": j["scenario"], "runs": 0, "status": {}, "durations": [],
                                           "watch": 0, "values": {}, "errors": {}, "series": []})
        s["runs"] += 1
        s["status"][j["status"]] = s["status"].get(j["status"], 0) + 1
        s["watch"] += j.get("watch") or 0
        if j["status"] == "ok" and j.get("duration") is not None:
            s["durations"].append(j["duration"])
        if j["status"] in ("failed", "error") and j.get("error"):
            key = str(j["error"])[:80]
            s["errors"][key] = s["errors"].get(key, 0) + 1
        vals = j.get("vals") if isinstance(j.get("vals"), dict) else {}
        for k, v in vals.items():
            n = _num(v)
            if n is not None:
                s["values"].setdefault(k, []).append((j["finished"] or j["created"], n))
        s["series"].append({"id": j["id"], "t": j["finished"] or j["created"], "status": j["status"],
                            "duration": j.get("duration")})
    out = []
    for s in sorted(per.values(), key=lambda s: s["scenario"]):
        ok = s["status"].get("ok", 0)
        d = s["durations"]
        s["success_rate"] = round(100.0 * ok / s["runs"], 1) if s["runs"] else 0.0
        s["duration"] = ({"mean": round(statistics.mean(d), 2), "p95": round(_pct(d, 0.95), 2),
                          "min": round(min(d), 2), "max": round(max(d), 2)} if d else None)
        s["value_stats"] = {k: {"n": len(v), "min": min(x for _, x in v), "max": max(x for _, x in v),
                                "mean": round(statistics.mean(x for _, x in v), 4),
                                "last": v[-1][1]} for k, v in s["values"].items()}
        s["top_errors"] = sorted(s["errors"].items(), key=lambda kv: -kv[1])[:5]
        out.append(s)
    ev = store.events(limit=100000, since=since)
    ev = [e for e in ev if until is None or e["t"] < until]
    kinds: Dict[str, int] = {}
    for e in ev:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    mem = []
    for e in reversed(ev):
        if e["kind"] == "health" and "memory_mb=" in (e["detail"] or ""):
            n = _num(e["detail"].split("memory_mb=")[1].split()[0])
            if n is not None:
                mem.append((e["t"], n))
    total = len(jobs)
    ok = sum(1 for j in jobs if j["status"] == "ok")
    return {
        "generated": time.time(), "since": since, "until": until,
        "first": jobs[0]["created"] if jobs else None, "last": jobs[-1]["finished"] if jobs else None,
        "total": total, "ok": ok, "success_rate": round(100.0 * ok / total, 1) if total else 0.0,
        "by_status": {k: sum(1 for j in jobs if j["status"] == k) for k in FINISHED},
        "scenarios": out, "events": kinds, "memory": mem,
        "notable": [e for e in ev if e["kind"] in ("device_error", "reconnect_ok", "reconnect_fail", "halt",
                                                   "resume", "interrupted", "operator_error", "schedule_error")][:50],
    }


# ------------------------------------------------------------------- CSV
CSV_COLS = ["id", "scenario", "status", "source", "created", "started", "finished", "duration", "attempts",
            "steps", "watch", "error", "params", "vals", "run_dir"]


def jobs_csv(store: Store, since: Optional[float] = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for j in sorted(store.jobs(limit=100000, since=since), key=lambda j: j["id"]):
        row = []
        for c in CSV_COLS:
            v = j.get(c)
            if c in ("created", "started", "finished") and v:
                v = _ts(v)
            elif c == "status":
                v = STATUS_KO.get(v, v)
            elif isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            row.append("" if v is None else v)
        w.writerow(row)
    return "﻿" + buf.getvalue()          # BOM: 엑셀에서 한글이 깨지지 않게


# ------------------------------------------------------------------- HTML
def _ts(t: Optional[float], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return dt.datetime.fromtimestamp(t).strftime(fmt) if t else "-"


def _e(s) -> str:
    return html.escape(str(s))


def _spark(points: List[tuple], w: int = 320, h: int = 64, color: str = "#3b6fd4",
           dots: Optional[List[str]] = None) -> str:
    """(t, y) 목록 → 인라인 SVG 꺾은선. dots 가 있으면 점마다 색(상태)."""
    if not points:
        return '<span class="muted">-</span>'
    ts = [p[0] for p in points]
    ys = [p[1] for p in points]
    t0, t1 = min(ts), max(ts)
    y0, y1 = min(ys), max(ys)
    if y1 == y0:
        y0, y1 = y0 - 1, y1 + 1
    pad = 6

    def X(t):
        return pad + (w - 2 * pad) * ((t - t0) / (t1 - t0) if t1 > t0 else 0.5)

    def Y(y):
        return h - pad - (h - 2 * pad) * (y - y0) / (y1 - y0)
    pts = " ".join(f"{X(t):.1f},{Y(y):.1f}" for t, y in points)
    s = [f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">',
         f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{pts}"/>']
    for i, (t, y) in enumerate(points):
        c = dots[i] if dots else color
        s.append(f'<circle cx="{X(t):.1f}" cy="{Y(y):.1f}" r="2.4" fill="{c}"><title>{_ts(t)} : {y:g}</title></circle>')
    s.append(f'<text x="{w - pad}" y="11" text-anchor="end" class="ax">{max(ys):g}</text>')
    s.append(f'<text x="{w - pad}" y="{h - 1}" text-anchor="end" class="ax">{min(ys):g}</text></svg>')
    return "".join(s)


def _strip(series: List[dict], w: int = 320) -> str:
    """실행마다 색 칸 하나: 성공/실패/장치 오류 흐름을 한눈에."""
    if not series:
        return ""
    n = len(series[-120:])
    cw = max(2.0, w / max(n, 1))
    cells = []
    for i, s in enumerate(series[-120:]):
        cells.append(f'<rect x="{i * cw:.1f}" y="0" width="{max(cw - 1, 1):.1f}" height="14" '
                     f'fill="{STATUS_COLOR.get(s["status"], "#999")}"><title>작업 {s["id"]} {_ts(s["t"])} '
                     f'{STATUS_KO.get(s["status"], s["status"])}</title></rect>')
    return f'<svg class="strip" viewBox="0 0 {n * cw:.0f} 14" width="{w}" height="14">{"".join(cells)}</svg>'


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1f2933;--muted:#7b8794;--line:#e4e7eb}
@media (prefers-color-scheme:dark){:root{--bg:#14171a;--card:#1d2125;--fg:#e4e7eb;--muted:#9aa5b1;--line:#323940}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 "Malgun Gothic","Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px}
.muted{color:var(--muted)}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px}
.kpi b{display:block;font-size:22px}.kpi span{color:var(--muted);font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:12px}
.card h3{margin:0 0 8px;font-size:15px}.row{display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}.num{text-align:right;font-variant-numeric:tabular-nums}
.spark .ax{font-size:9px;fill:var(--muted)}.spark,.strip{max-width:100%;height:auto}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 10px;vertical-align:-1px}
.badge{display:inline-block;padding:0 6px;border-radius:4px;color:#fff;font-size:12px}
.wrap{overflow-x:auto}
"""


def render_html(summary: dict, title: str = "GHOST 운영 보고서") -> str:
    s = summary
    period = f"{_ts(s['since'] or s['first'])} ~ {_ts(s['until'] or s['last'] or s['generated'])}"
    p = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)}</title>'
         f'<style>{CSS}</style></head><body><main>',
         f'<h1>{_e(title)}</h1><div class="muted">기간 {period} · 생성 {_ts(s["generated"])}</div>']
    ev = s["events"]
    kpis = [(s["total"], "실행"), (f'{s["success_rate"]}%', "성공률"), (s["by_status"].get("failed", 0), "시나리오 실패"),
            (s["by_status"].get("error", 0), "장치 오류"), (ev.get("reconnect_ok", 0), "장치 재연결"),
            (ev.get("halt", 0), "운영 정지"),
            (sum(x["watch"] for x in s["scenarios"]), "감시 알람")]
    p.append('<div class="kpis">' + "".join(f'<div class="kpi"><b>{_e(v)}</b><span>{_e(k)}</span></div>'
                                            for v, k in kpis) + "</div>")
    p.append('<h2>시나리오별</h2><div class="legend muted">' +
             "".join(f'<i style="background:{STATUS_COLOR[k]}"></i>{STATUS_KO[k]}' for k in FINISHED) + "</div>")
    if not s["scenarios"]:
        p.append('<div class="card muted">기간 안에 끝난 작업이 없습니다.</div>')
    for sc in s["scenarios"]:
        d = sc["duration"]
        st = ", ".join(f'{STATUS_KO.get(k, k)} {v}' for k, v in sorted(sc["status"].items(), key=lambda kv: -kv[1]))
        p.append(f'<div class="card"><h3>{_e(sc["scenario"])} '
                 f'<span class="muted">— {sc["runs"]}회, 성공률 {sc["success_rate"]}% ({_e(st)})</span></h3>')
        p.append(f'<div>{_strip(sc["series"])}</div><div class="row" style="margin-top:10px">')
        durs = [(x["t"], x["duration"]) for x in sc["series"] if x["duration"] is not None and x["status"] == "ok"]
        dtxt = (f'평균 {d["mean"]}s · p95 {d["p95"]}s · 최소 {d["min"]}s · 최대 {d["max"]}s' if d else "성공한 실행 없음")
        p.append(f'<div><div class="muted">소요 시간(성공) — {dtxt}</div>{_spark(durs)}</div>')
        for k, vs in sc["values"].items():
            vst = sc["value_stats"][k]
            p.append(f'<div><div class="muted">읽은 값 <b>{_e(k)}</b> — n={vst["n"]} · 최소 {vst["min"]:g} · '
                     f'최대 {vst["max"]:g} · 평균 {vst["mean"]:g}</div>{_spark(vs, color="#8e44ad")}</div>')
        p.append("</div>")
        if sc["top_errors"]:
            p.append('<table style="margin-top:10px"><tr><th>주요 실패 원인</th><th class="num">횟수</th></tr>' +
                     "".join(f'<tr><td>{_e(m)}</td><td class="num">{n}</td></tr>' for m, n in sc["top_errors"]) +
                     "</table>")
        p.append("</div>")
    if s["memory"]:
        p.append(f'<h2>메모리 (장시간 운영 누수 감시)</h2><div class="card">'
                 f'{_spark(s["memory"], w=640, h=90, color="#2e9d5b")}<div class="muted">MB, health 기록 기준</div></div>')
    p.append('<h2>장치·운영 이벤트</h2><div class="card wrap">')
    if s["notable"]:
        p.append("<table><tr><th>시각</th><th>종류</th><th>내용</th></tr>" +
                 "".join(f'<tr><td>{_ts(e["t"])}</td><td>{_e(e["kind"])}</td><td>{_e(e["detail"])}</td></tr>'
                         for e in s["notable"]) + "</table>")
    else:
        p.append('<span class="muted">장치 오류·재연결·정지 없음</span>')
    p.append("</div></main></body></html>")
    return "".join(p)


def period(days: Optional[float] = None, since: Optional[str] = None, until: Optional[str] = None):
    """CLI/API 기간 인자 → (since_ts, until_ts). since/until 은 'YYYY-MM-DD' 또는 'YYYY-MM-DD HH:MM'."""
    def parse(s):
        for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(s, f).timestamp()
            except ValueError:
                pass
        raise ValueError(f"날짜 형식 오류: {s} (YYYY-MM-DD[ HH:MM])")
    a = parse(since) if since else (time.time() - days * 86400 if days else None)
    b = parse(until) if until else None
    return a, b
