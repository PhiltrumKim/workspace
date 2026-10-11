# -*- coding: utf-8 -*-
"""예약 판정.

  interval: {"kind": "interval", "every_min": 30}            30분마다
  daily   : {"kind": "daily", "times": ["08:00", "20:00"],   매일 정해진 시각
             "days": [0,1,2,3,4]}                             요일 제한 (0=월 … 6=일, 비우면 매일)
"""
from __future__ import annotations

import datetime as dt
import re
from typing import List, Optional

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def validate(kind: str, every_min=None, times=None, days=None) -> List[str]:
    errs = []
    if kind == "interval":
        try:
            if float(every_min) < 1:
                errs.append("간격은 1분 이상")
        except (TypeError, ValueError):
            errs.append("간격(분)을 숫자로 입력하세요")
    elif kind == "daily":
        if not times:
            errs.append("시각을 하나 이상 입력하세요 (예: 08:00)")
        for t in times or []:
            if not TIME_RE.match(str(t)):
                errs.append(f"시각 형식 오류: {t} (HH:MM)")
        for d in days or []:
            if d not in range(7):
                errs.append(f"요일 오류: {d} (0=월 … 6=일)")
    else:
        errs.append(f"알 수 없는 예약 종류: {kind}")
    return errs


def _slots(s: dict, day: dt.date) -> List[dt.datetime]:
    days = s.get("days") or []
    if days and day.weekday() not in days:
        return []
    out = []
    for t in s.get("times") or []:
        m = TIME_RE.match(str(t))
        if m:
            out.append(dt.datetime.combine(day, dt.time(int(m.group(1)), int(m.group(2)))))
    return sorted(out)


def due(s: dict, now: float) -> bool:
    """지금 실행해야 하는지. last_run·created 이후에 지난 예약 시각이 있으면 True."""
    if not s.get("enabled", 1):
        return False
    last = s.get("last_run")
    if s["kind"] == "interval":
        base = last if last else s.get("created") or now
        if not last:
            return True                             # 처음 한 번은 바로
        return now - base >= float(s["every_min"]) * 60
    floor = max(last or 0, s.get("created") or 0)
    nowdt = dt.datetime.fromtimestamp(now)
    for day in (nowdt.date() - dt.timedelta(days=1), nowdt.date()):
        for slot in _slots(s, day):
            ts = slot.timestamp()
            if floor < ts <= now:
                return True
    return False


def next_run(s: dict, now: float) -> Optional[float]:
    if not s.get("enabled", 1):
        return None
    if s["kind"] == "interval":
        last = s.get("last_run")
        return now if not last else max(now, last + float(s["every_min"]) * 60)
    nowdt = dt.datetime.fromtimestamp(now)
    for k in range(8):
        for slot in _slots(s, nowdt.date() + dt.timedelta(days=k)):
            if slot.timestamp() > now:
                return slot.timestamp()
    return None


def describe(s: dict) -> str:
    if s["kind"] == "interval":
        return f"{s['every_min']:g}분마다"
    names = "월화수목금토일"
    days = s.get("days") or []
    d = "매일" if not days else "".join(names[i] for i in sorted(days))
    return f"{d} {', '.join(s.get('times') or [])}"
