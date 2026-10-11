# -*- coding: utf-8 -*-
"""무인 운영 실행기: 대기열의 작업을 하나씩 실행하고, 예약을 대기열에 넣고, 장치 오류를 복구한다.

- 장치는 하나이므로 작업은 한 번에 하나. 편집기와 같은 장치 잠금(lock)을 쓴다.
- 결과 분류: ok / failed(시나리오 실패) / error(장치 오류) / stopped(사용자 중지)
- 장치 오류: 재연결(Device.reconnect)을 backoff 간격으로 시도 → 성공하면 작업을 다시 대기열에 (max_attempts 까지)
  끝내 실패하면 실행기를 halted 로 멈추고 critical 알림. (설비를 계속 두드리지 않기 위해)
- 시나리오 실패는 기본으로 재시도하지 않는다 (같은 시료를 두 번 처리하는 등 위험할 수 있음, ops.retry_failed)
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable, Optional

from ..scenario import model
from ..scenario.runner import resolve_params
from . import schedule as sched
from .store import Store


_PMC_FN = None


def _pmc_fn():
    """Windows 메모리 조회 함수 (한 번만 준비 — 매번 ctypes 구조체를 만들면 그 자체가 조금씩 샌다)."""
    global _PMC_FN
    if _PMC_FN is None:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        fn = k32.K32GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        h = k32.GetCurrentProcess()

        def query():
            return c.WorkingSetSize if fn(h, ctypes.byref(c), c.cb) else None
        _PMC_FN = query
    return _PMC_FN


def rss_mb() -> Optional[float]:
    """현재 프로세스 메모리(MB). 장시간 운영 시 누수 감시용."""
    try:
        if sys.platform == "win32":
            ws = _pmc_fn()()
            return round(ws / 1048576, 1) if ws else None
        with open("/proc/self/statm") as f:
            return round(int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1048576, 1)
    except Exception:
        return None


class Operator:
    def __init__(self, cfg: dict, device, runner, store: Store, lock: threading.Lock,
                 log: Optional[Callable[[str], None]] = None):
        self.cfg = cfg
        self.o = cfg["ops"]
        self.dev = device
        self.runner = runner
        self.store = store
        self.lock = lock
        self.log = log or (lambda m: None)
        self.state = "stopped"              # stopped | running | paused | halted
        self.current: Optional[dict] = None
        self.halt_reason = ""
        self.started_at: Optional[float] = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_health = 0.0
        n = store.recover_interrupted()
        if n:
            store.add_event("interrupted", f"이전 실행 중 종료된 작업 {n}건")

    # ---------------------------------------------------------------- 제어
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.resume()
            return
        self._stop.clear()
        self.state = "running"
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._loop, name="ghost-operator", daemon=True)
        self._thread.start()
        self.store.add_event("start", "운영 시작")
        self.log("[운영] 시작")

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        self._wake.set()
        self.runner.stop_event.set()
        if self._thread:
            self._thread.join(timeout)
        self.state = "stopped"
        self.store.add_event("stop", "운영 중지")
        self.log("[운영] 중지")

    def pause(self) -> None:
        if self.state == "running":
            self.state = "paused"
            self.store.add_event("pause", "운영 일시정지 (진행 중 작업은 끝까지 실행)")

    def resume(self) -> None:
        if self.state in ("paused", "halted"):
            if self.state == "halted":
                self.store.add_event("resume", f"정지 해제 (사유였던 것: {self.halt_reason})")
                self.halt_reason = ""
            self.state = "running"
            self._wake.set()

    def stop_current(self) -> bool:
        if self.current is None:
            return False
        self.runner.stop_event.set()
        return True

    def submit(self, scenario: str, params: Optional[dict] = None, source: str = "manual",
               schedule_id: Optional[int] = None, max_attempts: Optional[int] = None) -> int:
        self._load(scenario, params)                 # 이름·파라미터 확인 (잘못된 작업은 넣지 않음)
        jid = self.store.add_job(scenario, params, source, max_attempts or self.o["max_attempts"], schedule_id)
        self._wake.set()
        return jid

    # ---------------------------------------------------------------- 상태
    def status(self) -> dict:
        cur = None
        if self.current:
            cur = {k: self.current.get(k) for k in ("id", "scenario", "params", "attempts", "source")}
            cur["elapsed"] = round(time.time() - (self.current.get("started") or time.time()), 1)
        return {"state": self.state, "halt_reason": self.halt_reason, "current": cur,
                "counts": self.store.counts(), "started_at": self.started_at,
                "device": dict(self.dev.stats), "memory_mb": rss_mb()}

    # ---------------------------------------------------------------- 내부
    def _load(self, name: str, params: Optional[dict]) -> dict:
        path = model.find_path(name, self.runner.scenario_dirs)
        if not path:
            raise ValueError(f"시나리오 '{name}' 없음")
        sc = model.load(path, self.runner.reg)
        resolve_params(sc, params)                   # 필수 파라미터 누락이면 ScenarioError
        return sc

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._health()
                if self.state == "running":
                    self._schedule_tick()
                    job = self.store.claim_next()
                    if job is not None:
                        self._run_job(job)
                        continue
            except Exception as e:                   # 실행기 자체는 죽지 않는다
                self.log(f"[운영] 내부 오류: {e!r}")
                self.store.add_event("operator_error", repr(e))
            self._wake.wait(self.o["poll_sec"])
            self._wake.clear()

    def _health(self) -> None:
        now = time.time()
        if now - self._last_health >= self.o["health_every_min"] * 60:
            self._last_health = now
            self.store.add_event("health", f"memory_mb={rss_mb()} device={self.dev.stats}")

    def _schedule_tick(self) -> None:
        now = time.time()
        for s in self.store.schedules(enabled_only=True):
            if not sched.due(s, now):
                continue
            self.store.set_schedule(s["id"], last_run=now)
            if self.store.pending_for_schedule(s["id"]):
                self.store.add_event("schedule_skip", f"'{s['name']}' 이전 작업이 아직 대기·실행 중이라 건너뜀")
                continue
            try:
                jid = self.submit(s["scenario"], s.get("params") or {}, source=f"예약:{s['name']}", schedule_id=s["id"])
                self.store.add_event("schedule_fire", f"'{s['name']}' → 작업 {jid}")
            except Exception as e:
                self.store.add_event("schedule_error", f"'{s['name']}': {e}")

    def _run_job(self, job: dict) -> None:
        self.current = job
        jid = job["id"]
        self.log(f"[운영] 작업 {jid} 시작: {job['scenario']} {job.get('params') or ''} ({job['attempts']}회째)")
        t0 = time.time()
        try:
            sc = self._load(job["scenario"], job.get("params") or {})
        except Exception as e:
            self.store.finish_job(jid, "failed", error=f"시나리오 오류: {e}", duration=0)
            self.current = None
            return
        while not self.lock.acquire(timeout=1.0):    # 편집기에서 수동 조작 중이면 끝날 때까지 기다림
            if self._stop.is_set():
                self.store.requeue(jid, "운영 중지로 대기열 복귀")
                self.current = None
                return
        try:
            res = self.runner.run(sc, job.get("params") or {})
        finally:
            self.lock.release()
        dur = round(time.time() - t0, 2)
        fields = dict(run_dir=os.path.basename(res.run_dir or ""), steps=len(res.steps), duration=dur,
                      watch=sum(1 for e in res.watch_events if e.get("kind") == "appeared"), vals=res.values)
        self.current = None
        if res.device_error:
            self.store.finish_job(jid, "error", error=res.error, **fields)
            self.store.add_event("device_error", f"작업 {jid}: {res.error}")
            self.log(f"[운영] 작업 {jid} 장치 오류: {res.error}")
            if self._recover():
                if sc.get("on_abort"):               # 끊긴 동안 못 한 안전 복귀를 복구 직후 실행 (재시도 전 화면 정리)
                    self._cleanup(sc["on_abort"], jid)
                if job["attempts"] < job["max_attempts"]:
                    nid = self.store.add_job(job["scenario"], job.get("params"), f"재시도:{jid}",
                                             job["max_attempts"] - job["attempts"], job.get("schedule_id"))
                    self.store.add_event("retry", f"작업 {jid} → {nid} (장치 복구 후 재시도)")
            return
        if res.stopped:
            self.store.finish_job(jid, "stopped", error="사용자 중지", **fields)
        elif res.ok:
            self.store.finish_job(jid, "ok", **fields)
        else:
            last = next((s.message for s in reversed(res.steps) if not s.ok), res.error or "실패")
            self.store.finish_job(jid, "failed", error=last, **fields)
            self._notify("warning", f"작업 {jid} 실패: {job['scenario']} — {last}")
            if self.o.get("retry_failed") and job["attempts"] < job["max_attempts"]:
                self.store.requeue(jid, last)
        self.log(f"[운영] 작업 {jid} 끝: {'성공' if res.ok else '중지' if res.stopped else '실패'} ({dur}s)")

    def _recover(self) -> bool:
        for i, wait in enumerate(self.o["reconnect_backoff"]):
            if self._stop.is_set():
                return False
            try:
                with self.lock:
                    self.dev.reconnect()
                self.store.add_event("reconnect_ok", f"{i + 1}회째 재연결 성공")
                self._notify("info", f"장치 재연결 성공 ({i + 1}회째)")
                return True
            except Exception as e:
                self.store.add_event("reconnect_fail", f"{i + 1}회째: {e}")
                self.log(f"[운영] 재연결 실패 {i + 1}회째: {e} — {wait}s 후 재시도")
                self._stop.wait(wait)
        self.state = "halted"
        self.halt_reason = "장치 재연결 실패 (캡처카드·RelayBoard 연결을 확인하세요)"
        self.store.add_event("halt", self.halt_reason)
        self._notify("critical", f"운영 정지: {self.halt_reason}")
        return False

    def _cleanup(self, name: str, jid: int) -> None:
        try:
            sub = self._load(name, {})
            with self.lock:
                r = self.runner.run(sub)
            self.store.add_event("cleanup", f"작업 {jid} 안전 복귀 '{name}': {'성공' if r.ok else '실패(이미 정리된 상태일 수 있음)'}")
        except Exception as e:
            self.store.add_event("cleanup", f"작업 {jid} 안전 복귀 '{name}' 오류: {e}")

    def _notify(self, severity: str, text: str) -> None:
        try:
            self.runner.notifier.send(severity, text, source="ops")
        except Exception:
            pass
