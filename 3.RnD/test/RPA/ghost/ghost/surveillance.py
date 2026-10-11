# -*- coding: utf-8 -*-
"""상시 감시(Surveillance): 화면에서 이상 상태를 탐지해 이벤트를 만든다.

규칙(rule) 형식 — 시나리오의 "watch" 또는 감시 규칙 파일({"rules": [...]})에 정의
  {"name": "alarm_popup",
   "type": "target",            target   : 템플릿이 화면에 나타남 (알람/에러 팝업)
                                no_signal: 영상 끊김 (화면 전체가 거의 단색)
                                frozen   : region 화면이 seconds 동안 변하지 않음 (장비 SW 멈춤)
   "target": "alarm_title",     (type=target)
   "region": [x, y, w, h],      (frozen 필수 / target 선택)
   "seconds": 60,               (frozen)
   "severity": "critical",      info | warning | critical
   "action": "handler",         notify(기본) | stop | handler
   "handler": "ack_alarm",      (action=handler) 실행할 시나리오 이름
   "cooldown": 5}               같은 규칙 핸들러 재실행 최소 간격(초)

상태 변화가 있을 때만 이벤트를 만든다: 나타남(appeared) / 해소(cleared).
check() 는 순수하게 프레임만 보고 판단하며, 조치(정지·핸들러·알림)는 실행기가 수행한다.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

from .locator import Locator, describe

TYPES = {"target", "no_signal", "frozen"}
ACTIONS = {"notify", "stop", "handler"}
SEVERITY = {"info": 0, "warning": 1, "critical": 2}


@dataclass
class WatchEvent:
    rule: str
    kind: str                 # appeared | cleared
    severity: str
    action: str
    detail: str = ""
    t: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {"rule": self.rule, "kind": self.kind, "severity": self.severity,
                "action": self.action, "detail": self.detail, "t": round(self.t, 3)}


def validate_rules(rules: List[dict], registry=None) -> List[str]:
    errs = []
    names = set()
    for i, r in enumerate(rules):
        w = f"watch[{i}]"
        if not r.get("name"):
            errs.append(f"{w}: name 누락")
        elif r["name"] in names:
            errs.append(f"{w}: name 중복 '{r['name']}'")
        names.add(r.get("name"))
        t = r.get("type", "target")
        if t not in TYPES:
            errs.append(f"{w}: 알 수 없는 type '{t}'")
        if t == "target":
            if "target" not in r:
                errs.append(f"{w}: target 필요")
            elif registry is not None:
                loc = registry if isinstance(registry, Locator) else Locator(registry, {})
                e = loc.validate(r["target"])
                if e:
                    errs.append(f"{w}: {e}")
        if t == "frozen" and not (r.get("region") and r.get("seconds")):
            errs.append(f"{w}: frozen 은 region, seconds 필요")
        a = r.get("action", "notify")
        if a not in ACTIONS:
            errs.append(f"{w}: 알 수 없는 action '{a}'")
        if a == "handler" and not r.get("handler"):
            errs.append(f"{w}: action=handler 는 handler 시나리오 필요")
        if r.get("severity", "warning") not in SEVERITY:
            errs.append(f"{w}: 알 수 없는 severity '{r.get('severity')}'")
    return errs


def load_rules(spec, base_dir: str = ".") -> List[dict]:
    """spec: 규칙 리스트 또는 규칙 파일 경로({"rules": [...]})."""
    if spec is None:
        return []
    if isinstance(spec, list):
        return spec
    path = spec if os.path.isabs(spec) else os.path.join(base_dir, spec)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["rules"] if isinstance(data, dict) else data


class Surveillance:
    def __init__(self, rules: List[dict], locator, cfg: dict):
        self.rules = rules
        self.loc = locator if isinstance(locator, Locator) else Locator(locator, cfg)
        self.cfg = cfg
        self.active: Dict[str, bool] = {r["name"]: False for r in rules}
        self._rearmed: set = set()
        self._last_change: Dict[str, float] = {}
        self._last_crop: Dict[str, np.ndarray] = {}

    def _present(self, r: dict, frame: np.ndarray, now: float):
        """(이상 상태 여부, 설명)"""
        t = r.get("type", "target")
        if t == "target":
            m = self.loc.locate(r["target"], frame, region=r.get("region"), threshold=r.get("threshold"),
                                color_tol=r.get("color_tol"))
            return (m is not None), (f"{describe(r['target'])}@{m.center} score={m.score}" if m else "")
        if t == "no_signal":
            std = float(frame.std())
            return std < r.get("max_std", 2.0), f"std={std:.2f}"
        # frozen
        x, y, w, h = r["region"]
        crop = frame[y:y + h, x:x + w].astype(np.int16)
        name = r["name"]
        prev = self._last_crop.get(name)
        if prev is None or np.abs(crop - prev).mean() > r.get("min_change", 1.0):
            self._last_crop[name] = crop
            self._last_change[name] = now
        idle = now - self._last_change[name]
        return idle >= r["seconds"], f"변화 없음 {idle:.0f}s"

    def check(self, frame: np.ndarray, now: Optional[float] = None) -> List[WatchEvent]:
        now = time.monotonic() if now is None else now
        events = []
        for r in self.rules:
            present, detail = self._present(r, frame, now)
            name = r["name"]
            repeat = present and name in self._rearmed      # 핸들러 후에도 여전히 존재
            if present != self.active[name] or repeat:
                self.active[name] = present
                events.append(WatchEvent(name, "appeared" if present else "cleared",
                                         r.get("severity", "warning"), r.get("action", "notify"), detail))
            self._rearmed.discard(name)
        return events

    def rule(self, name: str) -> dict:
        return next(r for r in self.rules if r["name"] == name)

    def rearm(self, name: str) -> None:
        """핸들러 실행 후: 다음 check 에서 사라졌으면 cleared, 남아 있으면 appeared 를 다시 낸다."""
        self._rearmed.add(name)


class Notifier:
    """이벤트 알림: 로그 + (선택) 웹훅 POST. 웹훅은 실행을 막지 않도록 백그라운드로 보낸다."""

    def __init__(self, cfg: dict, log: Callable[[str], None]):
        n = cfg.get("notify", {})
        self.webhook = n.get("webhook")
        self.min_sev = SEVERITY.get(n.get("min_severity", "warning"), 1)
        self.log = log
        self.sent: List[dict] = []

    def __call__(self, ev: WatchEvent, scenario: str = "") -> None:
        icon = {"appeared": "⚠", "cleared": "✓"}[ev.kind]
        self.log(f"  {icon} [감시:{ev.severity}] {ev.rule} {ev.kind} {ev.detail}")
        if SEVERITY[ev.severity] < self.min_sev:
            return
        payload = {"source": "GHOST", "scenario": scenario, **ev.as_dict(),
                   "text": f"[GHOST] {scenario} {ev.rule} {ev.kind} ({ev.severity}) {ev.detail}"}
        self.sent.append(payload)
        if self.webhook:
            threading.Thread(target=self._post, args=(payload,), daemon=True).start()

    def send(self, severity: str, text: str, **extra) -> None:
        """감시 이벤트가 아닌 알림 (운영 실행기: 작업 실패, 장치 재연결, 운영 정지)."""
        self.log(f"  [알림:{severity}] {text}")
        if SEVERITY.get(severity, 1) < self.min_sev:
            return
        payload = {"source": "GHOST", "severity": severity, "text": f"[GHOST] {text}", "t": round(time.time(), 3), **extra}
        self.sent.append(payload)
        if self.webhook:
            threading.Thread(target=self._post, args=(payload,), daemon=True).start()

    def _post(self, payload: dict) -> None:
        try:
            req = urllib.request.Request(self.webhook, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).close()
        except Exception as e:
            self.log(f"  [감시] 웹훅 전송 실패: {e}")
