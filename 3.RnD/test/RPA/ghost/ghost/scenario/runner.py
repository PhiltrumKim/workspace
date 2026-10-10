# -*- coding: utf-8 -*-
"""시나리오 실행기: 스텝 실행 + 사후조건 확인 + 재시도 + 블랙박스 기록."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .. import config as config_mod
from ..blackbox import Blackbox, NullBlackbox
from ..device import Device
from ..hal.base import LEFT, RIGHT
from ..registry import Registry
from ..vision import Match, find
from . import model

MAX_DEPTH = 8


@dataclass
class StepResult:
    index: str
    action: str
    desc: str
    ok: bool
    message: str
    elapsed: float


@dataclass
class RunResult:
    name: str
    ok: bool
    steps: List[StepResult] = field(default_factory=list)
    run_dir: str = ""
    stopped: bool = False


class StepFailed(Exception):
    pass


class Runner:
    def __init__(self, device: Device, registry: Registry, cfg: dict,
                 blackbox: Optional[Blackbox] = None, log: Optional[Callable[[str], None]] = None):
        self.dev = device
        self.reg = registry
        self.cfg = cfg
        self.bb = blackbox or NullBlackbox()
        self.log = log or print
        self.stop_event = threading.Event()
        self.scenario_dirs = [config_mod.path(cfg, "scenarios")]

    # ------------------------------------------------------------ 비전 조회
    def find(self, target: str, frame=None) -> Optional[Match]:
        rec = self.reg.get(target)
        tmpl = self.reg.template(target)
        if tmpl is None:
            raise StepFailed(f"target '{target}' 템플릿 파일 없음")
        frame = self.dev.frame() if frame is None else frame
        return find(frame, tmpl,
                    threshold=rec.get("threshold", self.cfg["vision"]["threshold"]),
                    region=tuple(rec["region"]) if rec.get("region") else None,
                    scales=rec.get("scales", self.cfg["vision"]["scales"]))

    def wait_for(self, target: str, timeout: float, gone: bool = False) -> Optional[Match]:
        """visible: 찾으면 Match 반환 / gone: 사라지면 None 반환. 시간 초과 시 StepFailed."""
        deadline = time.monotonic() + timeout
        while True:
            m = self.find(target)
            if (m is None) == gone:
                return m
            if time.monotonic() >= deadline or self.stop_event.is_set():
                state = "사라지지 않음" if gone else "미검출"
                raise StepFailed(f"{target} {state} ({timeout}s)")
            time.sleep(self.cfg["timing"]["poll"])

    def _point(self, st: dict) -> Tuple[Tuple[int, int], str]:
        if "target" not in st:
            return (int(st["x"]), int(st["y"])), f"({st['x']},{st['y']})"
        t = st["target"]
        rec = self.reg.get(t)
        try:
            m = self.wait_for(t, st.get("timeout", 3.0))
        except StepFailed:
            if st.get("allow_hint") and "hint" in rec:
                hx, hy = rec["hint"]
                return (int(hx), int(hy)), f"{t} 힌트좌표({hx},{hy}) — 템플릿 미검출"
            raise
        ox, oy = rec.get("click_offset", (0, 0))
        cx, cy = m.center
        return (cx + ox, cy + oy), f"{t}@({cx + ox},{cy + oy}) score={m.score}"

    # ------------------------------------------------------------ 실행
    def run(self, sc: dict) -> RunResult:
        self.stop_event.clear()
        res = RunResult(sc["name"], ok=False)
        res.run_dir = self.bb.start(sc["name"])
        self.bb.event("scenario", scenario=sc)
        self.log(f"▶ {sc['name']} — {sc.get('description', '')}")
        try:
            res.ok = self._run_steps(sc["steps"], res, prefix="", depth=0)
        except Exception as e:                  # 장비 오류 등: 기록하고 안전하게 종료
            self.log(f"✖ 실행 중단: {e!r}")
            self.bb.event("error", error=repr(e))
            res.ok = False
        finally:
            try:
                self.dev.release_all_keys()
            except Exception:
                pass
        res.stopped = self.stop_event.is_set()
        self.bb.end(res.ok, stopped=res.stopped, device_stats=self.dev.stats)
        self.log(f"{'✔ 성공' if res.ok else '✖ 실패'}: {sc['name']}" + (" (중지됨)" if res.stopped else ""))
        return res

    def _run_steps(self, steps: List[dict], res: RunResult, prefix: str, depth: int) -> bool:
        for i, st in enumerate(steps):
            if self.stop_event.is_set():
                return False
            idx = f"{prefix}{i}"
            desc = model.describe(st)
            t0 = time.monotonic()
            ok, msg = self._attempt(st, res, idx, depth)
            sr = StepResult(idx, st["action"], desc, ok, msg, round(time.monotonic() - t0, 2))
            res.steps.append(sr)
            self.bb.event("step", index=idx, action=st["action"], desc=desc, ok=ok, message=msg,
                          elapsed=sr.elapsed, cursor=self.dev.pos)
            self.log(f"  [{idx}] {'✓' if ok else '✗'} {desc} → {msg}")
            bbc = self.cfg["blackbox"]
            if (not ok and bbc["frame_on_fail"]) or bbc["frame_every_step"]:
                try:
                    self.bb.frame(self.dev.frame(), f"step{idx}_{'ok' if ok else 'FAIL'}")
                except Exception:
                    pass
            if not ok:
                return False
        return True

    def _attempt(self, st: dict, res: RunResult, idx: str, depth: int) -> Tuple[bool, str]:
        tries = 1 + int(st.get("retry", 0))
        msg = ""
        for n in range(tries):
            try:
                msg = self._exec(st, res, idx, depth)
                exp = st.get("expect")
                if exp:
                    gone = "gone" in exp
                    self.wait_for(exp.get("gone") or exp.get("visible"), exp.get("timeout", 3.0), gone=gone)
                    msg += f" / 확인: {exp.get('gone') or exp.get('visible')} {'사라짐' if gone else '표시'}"
                return True, msg if n == 0 else f"{msg} (재시도 {n}회)"
            except StepFailed as e:
                msg = str(e)
                if n + 1 < tries and not self.stop_event.is_set():
                    self.log(f"  [{idx}] 재시도 {n + 1}/{tries - 1}: {msg}")
        return False, msg

    def _exec(self, st: dict, res: RunResult, idx: str, depth: int) -> str:
        a = st["action"]
        d = self.dev
        if a in model.POINTER:
            (x, y), where = self._point(st)
            if a == "move":
                d.move_to(x, y)
            else:
                d.click(x, y, button=RIGHT if a == "right_click" else LEFT, double=(a == "double"))
            return where
        if a == "key":
            d.press(st["key"])
            return f"key {st['key']}"
        if a == "hotkey":
            d.hotkey(*st["keys"])
            return f"hotkey {'+'.join(st['keys'])}"
        if a == "type":
            d.type_text(st["text"])
            return f"{len(st['text'])}자 입력"
        if a == "wait":
            self.stop_event.wait(float(st["sec"]))
            return f"{st['sec']}s"
        if a in ("wait_for", "expect"):
            m = self.wait_for(st["target"], st.get("timeout", 10.0 if a == "wait_for" else 0.0))
            return f"{st['target']} 표시 score={m.score}"
        if a == "wait_gone":
            self.wait_for(st["target"], st.get("timeout", 10.0), gone=True)
            return f"{st['target']} 사라짐"
        if a == "screenshot":
            p = self.bb.frame(d.frame(), st.get("label", "shot"))
            return p or "blackbox 비활성"
        if a == "home":
            return f"origin={d.home()}"
        if a == "call":
            if depth >= MAX_DEPTH:
                raise StepFailed("call 깊이 초과")
            path = model.find_path(st["scenario"], self.scenario_dirs)
            if not path:
                raise StepFailed(f"시나리오 '{st['scenario']}' 없음")
            sub = model.load(path, self.reg)
            if not self._run_steps(sub["steps"], res, prefix=f"{idx}.", depth=depth + 1):
                raise StepFailed(f"하위 '{st['scenario']}' 실패")
            return f"하위 '{st['scenario']}' 완료"
        raise StepFailed(f"알 수 없는 action {a}")
