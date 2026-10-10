# -*- coding: utf-8 -*-
"""시나리오 실행기: 스텝 실행 + 사후조건 확인 + 재시도 + 블랙박스 기록."""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .. import config as config_mod
from ..blackbox import Blackbox, NullBlackbox
from ..device import Device
from ..hal.base import LEFT, RIGHT
from ..locator import Locator, describe as tdesc
from ..registry import Registry
from ..surveillance import SEVERITY, Notifier, Surveillance, WatchEvent, validate_rules
from ..vision import Match
from . import model

MAX_DEPTH = 8
MAX_HANDLER_RUNS = 5          # 실행 1회당 같은 규칙 핸들러 최대 실행 횟수 (처리 안 되는 알람 무한 반복 방지)


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
    aborted_by: str = ""                       # 감시 규칙에 의해 중단된 경우 규칙 이름
    values: dict = field(default_factory=dict) # read 액션으로 읽은 값
    watch_events: List[dict] = field(default_factory=list)


class StepFailed(Exception):
    pass


class WatchAbort(Exception):
    def __init__(self, ev: WatchEvent, reason: str = ""):
        super().__init__(reason or f"감시 규칙 '{ev.rule}' 에 의해 중단")
        self.ev = ev


class Runner:
    def __init__(self, device: Device, registry: Registry, cfg: dict,
                 blackbox: Optional[Blackbox] = None, log: Optional[Callable[[str], None]] = None):
        self.dev = device
        self.reg = registry
        self.cfg = cfg
        self.bb = blackbox or NullBlackbox()
        self.log = log or print
        self.loc = Locator(registry, cfg, self.log)
        self.stop_event = threading.Event()
        self.scenario_dirs = [config_mod.path(cfg, "scenarios")]
        self.base_watch: List[dict] = []       # 모든 실행에 적용할 감시 규칙 (CLI --watch)
        self.watch: Optional[Surveillance] = None
        self.notifier = Notifier(cfg, self.log)
        self._handling = False
        self._handler_runs: dict = {}
        self._handler_last: dict = {}
        self._res: Optional[RunResult] = None
        self._name = ""
        self.on_step: Optional[Callable[[StepResult], None]] = None   # 스텝 완료 알림 (편집기 진행 표시용)
        self._last_box: dict = {}                                         # target 별 마지막 발견 위치

    # ------------------------------------------------------------ 감시
    def _set_watch(self, rules: List[dict]) -> None:
        errs = validate_rules(rules, self.loc)
        if errs:
            raise model.ScenarioError(errs)
        self.watch = Surveillance(rules, self.loc, self.cfg) if rules else None
        self._handler_runs, self._handler_last = {}, {}

    def _tick(self, frame=None) -> None:
        """감시 1회: 이벤트 기록·알림 후 규칙의 action 수행. 핸들러 실행 중에는 감시하지 않는다."""
        if self.watch is None or self._handling:
            return
        frame = self.dev.frame() if frame is None else frame
        for ev in self.watch.check(frame):
            self.bb.event("watch", event=ev.as_dict())
            if self._res is not None:
                self._res.watch_events.append(ev.as_dict())
            self.notifier(ev, self._name)
            if ev.kind != "appeared":
                continue
            vcfg = self.cfg["blackbox"].get("video", {})
            if SEVERITY[ev.severity] >= SEVERITY.get(vcfg.get("clip_min_severity", "warning"), 1):
                self.bb.clip(f"watch_{ev.rule}", ev.detail)
            if ev.action == "stop":
                self.bb.frame(frame, f"WATCH_{ev.rule}")
                raise WatchAbort(ev)
            if ev.action == "handler":
                self.bb.frame(frame, f"WATCH_{ev.rule}")
                self._handle(ev)

    def _handle(self, ev: WatchEvent) -> None:
        rule = self.watch.rule(ev.rule)
        n = self._handler_runs.get(ev.rule, 0)
        if n >= MAX_HANDLER_RUNS:
            raise WatchAbort(ev, f"'{ev.rule}' 핸들러 {n}회 실행에도 반복 발생 → 중단")
        wait = rule.get("cooldown", 0) - (time.monotonic() - self._handler_last.get(ev.rule, -1e9))
        if wait > 0:
            time.sleep(wait)
        self._handler_runs[ev.rule] = n + 1
        self._handler_last[ev.rule] = time.monotonic()
        self.log(f"  ↳ 핸들러 '{rule['handler']}' 실행 ({ev.rule}, {n + 1}회째)")
        sub = self._load_sub(rule["handler"])
        self._handling = True
        try:
            ok = self._run_steps(sub["steps"], self._res, prefix=f"W:{ev.rule}#{n + 1}.", depth=1)
        finally:
            self._handling = False
        if not ok:
            raise WatchAbort(ev, f"핸들러 '{rule['handler']}' 실패 → 중단")
        self.watch.rearm(ev.rule)          # 다음 감시: 사라졌으면 cleared, 남아 있으면 다시 처리

    def _load_sub(self, name: str) -> dict:
        path = model.find_path(name, self.scenario_dirs)
        if not path:
            raise StepFailed(f"시나리오 '{name}' 없음")
        return model.load(path, self.reg)

    def _sleep(self, sec: float) -> None:
        """감시를 계속하면서 대기."""
        end = time.monotonic() + sec
        while not self.stop_event.is_set():
            left = end - time.monotonic()
            if left <= 0:
                break
            self.stop_event.wait(min(self.cfg["timing"]["poll"], left) if self.watch else left)
            self._tick()

    # ------------------------------------------------------------ 비전 조회
    def find(self, target, frame=None) -> Optional[Match]:
        frame = self.dev.frame() if frame is None else frame
        try:
            return self.loc.locate(target, frame)
        except FileNotFoundError as e:
            raise StepFailed(str(e))

    @staticmethod
    def _tkey(target) -> str:
        return target if isinstance(target, str) else json.dumps(target, sort_keys=True, ensure_ascii=False)

    def _clear_cursor(self, target) -> bool:
        """커서가 target 의 검색 영역·마지막 발견 위치·등록 위치를 가리고 있으면 바깥으로 치운다.
        (가린 채로 찾으면 OCR·템플릿이 실패하고, '사라짐' 확인은 거짓 성공할 수 있다)"""
        if not self.cfg["cursor"].get("auto_park", True):
            return False
        try:
            spec = self.loc.spec(target)
        except KeyError:
            return False
        boxes = []
        if spec.get("region"):
            boxes.append(spec["region"])
        if self._last_box.get(self._tkey(target)):
            boxes.append(self._last_box[self._tkey(target)])
        if "hint" in spec and spec.get("w"):
            boxes.append([spec["hint"][0] - spec["w"] // 2, spec["hint"][1] - spec["h"] // 2, spec["w"], spec["h"]])
        cx, cy = self.dev.pos
        mg = 24                                       # 커서 그림 크기 여유
        hit = next((b for b in boxes if b[0] - mg <= cx < b[0] + b[2] + mg and b[1] - mg <= cy < b[1] + b[3] + mg), None)
        if hit is None:
            return False
        W, H = self.dev.video.size
        x, y, w, h = hit
        gap = mg + 30
        for px, py in ((cx, y + h + gap), (cx, y - gap), (x + w + gap, cy), (x - gap, cy)):
            if 10 <= px < W - 10 and 10 <= py < H - 10:
                self.dev.move_to(px, py, verify=False)
                time.sleep(self.cfg["timing"]["capture_latency"])
                return True
        return False

    def wait_for(self, target, timeout: float, gone: bool = False) -> Optional[Match]:
        """visible: 찾으면 Match 반환 / gone: 사라지면 None 반환. 시간 초과 시 StepFailed."""
        deadline = time.monotonic() + timeout
        while True:
            self._clear_cursor(target)
            frame = self.dev.frame()
            self._tick(frame)
            m = self.find(target, frame)
            if m is not None:
                self._last_box[self._tkey(target)] = list(m.box)
            if (m is None) == gone:
                return m
            if time.monotonic() >= deadline or self.stop_event.is_set():
                state = "사라지지 않음" if gone else "미검출"
                raise StepFailed(f"{tdesc(target)} {state} ({timeout}s)")
            time.sleep(self.cfg["timing"]["poll"])

    def _point(self, st: dict) -> Tuple[Tuple[int, int], str]:
        if "target" not in st:
            return (int(st["x"]), int(st["y"])), f"({st['x']},{st['y']})"
        t = st["target"]
        rec = self.loc.spec(t)
        try:
            m = self.wait_for(t, st.get("timeout", 3.0))
        except StepFailed:
            if st.get("allow_hint") and "hint" in rec:
                hx, hy = rec["hint"]
                return (int(hx), int(hy)), f"{tdesc(t)} 힌트좌표({hx},{hy}) — 미검출"
            raise
        ox, oy = rec.get("click_offset", (0, 0))
        cx, cy = m.center
        return (cx + ox, cy + oy), f"{tdesc(t)}@({cx + ox},{cy + oy}) score={m.score}"

    def _read(self, st: dict, res: RunResult) -> str:
        """화면 영역의 글자를 읽어 값으로 저장. anchor 지정 시 anchor target 위치 기준 상대 영역."""
        region = st.get("region")
        if "anchor" in st:
            m = self.wait_for(st["anchor"], st.get("timeout", 3.0))
            dx, dy, w, h = st["offset"]
            region = [m.box[0] + dx, m.box[1] + dy, w, h]
        frame = self.dev.frame()
        name = st.get("name", "value")
        extra = {}
        if st.get("vote"):                       # 다수결 판독 (세그먼트 숫자 등 오인식이 잦은 글꼴)
            raw, agree, cands = self.loc.ocr.read_vote(frame, region)
            extra = {"agree": agree, "candidates": cands}
            if agree < st.get("min_agree", 0.5):
                self.bb.event("read", name=name, value=None, raw=raw, region=region, **extra)
                raise StepFailed(f"{name}: 판독 불일치 (일치도 {agree}) {cands}")
            hits = []
        else:
            hits = self.loc.ocr.read(frame, region, st.get("scale"), st.get("line"))
            raw = " ".join(h.text for h in sorted(hits, key=lambda h: (h.center[1] // 12, h.box[0])))
        value = raw
        if "pattern" in st:
            mt = re.search(st["pattern"], raw)
            if not mt:
                raise StepFailed(f"{name}: '{raw}' 에서 패턴 불일치")
            value = mt.group(1) if mt.groups() else mt.group(0)
        res.values[name] = value                 # 범위 검사 실패여도 판독값은 남긴다 (감사 추적)
        self.bb.event("read", name=name, value=value, raw=raw, region=region,
                      hits=[(h.text, h.conf) for h in hits], **extra)
        if region is not None:
            x, y, w, h = (int(v) for v in region)
            self.bb.frame(frame[max(0, y):y + h, max(0, x):x + w], f"read_{name}")
        if "min" in st or "max" in st:
            try:
                num = float(value.replace(",", ""))
            except ValueError:
                raise StepFailed(f"{name}: 수치가 아님 {value!r}")
            if ("min" in st and num < st["min"]) or ("max" in st and num > st["max"]):
                raise StepFailed(f"{name}={num} 허용 범위 [{st.get('min', '-')}, {st.get('max', '-')}] 밖")
        return (f"{name} = {value!r}" + (f" (원문 {raw!r})" if raw != value else "")
                + (f" [다수결 일치도 {extra['agree']}]" if extra else ""))

    # ------------------------------------------------------------ 실행
    def run(self, sc: dict) -> RunResult:
        self.stop_event.clear()
        res = RunResult(sc["name"], ok=False)
        self._res, self._name = res, sc["name"]
        self._set_watch(self.base_watch + list(sc.get("watch") or []))
        res.run_dir = self.bb.start(sc["name"])
        self.bb.event("scenario", scenario=sc)
        self.log(f"▶ {sc['name']} — {sc.get('description', '')}")
        if self.watch:
            self.log(f"  감시 규칙: {', '.join(r['name'] for r in self.watch.rules)}")
        try:
            res.ok = self._run_steps(sc["steps"], res, prefix="", depth=0)
            if not res.ok and not self.stop_event.is_set():
                self._on_abort(sc, res)          # 스텝 실패도 안전 복귀 (사용자 중지는 제외)
        except WatchAbort as e:
            res.ok, res.aborted_by = False, e.ev.rule
            self.log(f"■ {e}")
            self.bb.event("abort", rule=e.ev.rule, reason=str(e))
            self.bb.clip(f"abort_{e.ev.rule}", str(e))
            self._on_abort(sc, res)
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
        self.bb.end(res.ok, stopped=res.stopped, aborted_by=res.aborted_by, device_stats=self.dev.stats)
        self.log(f"{'✔ 성공' if res.ok else '✖ 실패'}: {sc['name']}" + (" (중지됨)" if res.stopped else ""))
        return res

    def _on_abort(self, sc: dict, res: RunResult) -> None:
        """실패·감시 중단 후 안전 복귀 시나리오(on_abort) 실행. 복귀 중에는 감시하지 않는다."""
        name = sc.get("on_abort")
        if not name:
            return
        self.log(f"  ↳ 안전 복귀 '{name}' 실행")
        self._handling = True
        try:
            ok = self._run_steps(self._load_sub(name)["steps"], res, prefix="R.", depth=1)
            self.bb.event("on_abort", scenario=name, ok=ok)
        except Exception as e:
            self.log(f"  ✖ 안전 복귀 실패: {e!r}")
            self.bb.event("on_abort", scenario=name, ok=False, error=repr(e))
        finally:
            self._handling = False

    def watch_only(self, rules: List[dict], duration: Optional[float] = None,
                   interval: Optional[float] = None) -> RunResult:
        """시나리오 없이 화면만 감시 (handler 규칙은 실행, stop 규칙이면 종료)."""
        self.stop_event.clear()
        res = RunResult("watch", ok=True)
        self._res, self._name = res, "watch"
        self._set_watch(rules)
        res.run_dir = self.bb.start("watch")
        self.log(f"감시 시작: {', '.join(r['name'] for r in rules)}" + (f" ({duration}s)" if duration else ""))
        interval = interval or self.cfg["timing"]["poll"]
        end = None if duration is None else time.monotonic() + duration
        try:
            while not self.stop_event.is_set() and (end is None or time.monotonic() < end):
                self._tick()
                self.stop_event.wait(interval)
        except WatchAbort as e:
            res.ok, res.aborted_by = False, e.ev.rule
            self.log(f"■ {e}")
        except KeyboardInterrupt:
            pass
        self.bb.end(res.ok, aborted_by=res.aborted_by, events=len(res.watch_events))
        return res

    def _run_steps(self, steps: List[dict], res: RunResult, prefix: str, depth: int) -> bool:
        for i, st in enumerate(steps):
            if self.stop_event.is_set():
                return False
            self._tick()
            idx = f"{prefix}{i}"
            desc = model.describe(st)
            self.bb.annotate(f"[{idx}] {model.describe({**st, 'label': None})}")   # 영상 표시는 ASCII 라 한글 라벨 제외
            t0 = time.monotonic()
            ok, msg = self._attempt(st, res, idx, depth)
            sr = StepResult(idx, st["action"], desc, ok, msg, round(time.monotonic() - t0, 2))
            res.steps.append(sr)
            if self.on_step is not None:
                try:
                    self.on_step(sr)
                except Exception:
                    pass
            self.bb.event("step", index=idx, action=st["action"], desc=desc, ok=ok, message=msg,
                          elapsed=sr.elapsed, cursor=self.dev.pos)
            self.log(f"  [{idx}] {'✓' if ok else '✗'} {desc} → {msg}")
            bbc = self.cfg["blackbox"]
            if not ok:
                self.bb.clip(f"step{idx}_FAIL", msg)
            if (not ok and bbc["frame_on_fail"]) or bbc["frame_every_step"]:
                try:
                    self.bb.frame(self.dev.frame(), f"step{idx}_{'ok' if ok else 'FAIL'}")
                except Exception:
                    pass
            if not ok:
                return False
        return True

    def run_step(self, st: dict, index: str = "편집") -> Tuple[StepResult, dict]:
        """스텝 하나만 실행 (편집기의 '이 스텝 실행'). 감시·블랙박스 실행 기록 없이 재시도·사후조건은 적용.
        반환: (결과, read 로 읽은 값)"""
        desc = model.describe(st)
        errs = model.validate({"name": "step", "steps": [st]}, self.reg)
        if errs:
            return StepResult(index, st.get("action", "?"), desc, False, "; ".join(errs), 0.0), {}
        res = RunResult("step", ok=False)
        saved, self._res, self.watch = self._res, res, None
        self.stop_event.clear()
        t0 = time.monotonic()
        try:
            ok, msg = self._attempt(st, res, index, 0)
        except Exception as e:
            ok, msg = False, f"오류: {e!r}"
        finally:
            self._res = saved
            try:
                self.dev.release_all_keys()
            except Exception:
                pass
        sr = StepResult(index, st["action"], desc, ok, msg, round(time.monotonic() - t0, 2))
        self.log(f"  [{index}] {'✓' if ok else '✗'} {desc} → {msg}")
        return sr, res.values

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
                    msg += f" / 확인: {tdesc(exp.get('gone') or exp.get('visible'))} {'사라짐' if gone else '표시'}"
                return True, msg if n == 0 else f"{msg} (재시도 {n}회)"
            except StepFailed as e:
                msg = str(e)
                self.dev.distrust()               # 실패 원인이 커서 오차일 수 있으므로 다음 이동은 실측
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
            self._sleep(float(st["sec"]))
            return f"{st['sec']}s"
        if a in ("wait_for", "expect"):
            m = self.wait_for(st["target"], st.get("timeout", 10.0 if a == "wait_for" else 0.0))
            return f"{tdesc(st['target'])} 표시 score={m.score}"
        if a == "wait_gone":
            self.wait_for(st["target"], st.get("timeout", 10.0), gone=True)
            return f"{tdesc(st['target'])} 사라짐"
        if a == "read":
            return self._read(st, res)
        if a == "screenshot":
            p = self.bb.frame(d.frame(), st.get("label", "shot"))
            return p or "blackbox 비활성"
        if a == "home":
            return f"origin={d.home()}"
        if a == "call":
            if depth >= MAX_DEPTH:
                raise StepFailed("call 깊이 초과")
            sub = self._load_sub(st["scenario"])
            if not self._run_steps(sub["steps"], res, prefix=f"{idx}.", depth=depth + 1):
                raise StepFailed(f"하위 '{st['scenario']}' 실패")
            return f"하위 '{st['scenario']}' 완료"
        raise StepFailed(f"알 수 없는 action {a}")
