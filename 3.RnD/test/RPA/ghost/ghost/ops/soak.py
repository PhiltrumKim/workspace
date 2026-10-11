# -*- coding: utf-8 -*-
"""장시간 시험: 운영 실행기로 시나리오를 계속 돌리며 장치 고장을 주입하고, 끝나면 보고서를 만든다.

  python -m ghost.ops.soak --sim --minutes 10 --scenario demo_lots --scenario demo_run_watched --fault-every 60
  python -m ghost.ops.soak --minutes 20 --scenario xnote_measure --fault-every 300     (실장비: 시리얼 포트를 강제로 닫아 끊김 재현)

결과: data/soak_<시각>/ (ops.db, report.html, jobs.csv, memory.csv)
"""
from __future__ import annotations

import argparse
import os
import random
import threading
import time

from .. import build_device, build_runner, config
from . import Operator, Store, report, rss_mb


def _world(dev):
    v = dev.video
    return v.world if hasattr(v, "world") else v.source.world      # FrameHub 로 감싼 경우


def inject(dev, sim: bool, rnd: random.Random) -> str:
    if sim:
        w = _world(dev)
        kind = rnd.choice(["hid", "video"])
        setattr(w, f"{kind}_fail", True)
        if rnd.random() < 0.3:
            w.stubborn = 1                          # 첫 재연결도 실패 → backoff 후 두 번째에 복구
        return f"sim {kind}_fail" + (" (stubborn)" if w.stubborn else "")
    ser = getattr(dev.hid, "ser", None)             # 실장비: 시리얼을 닫아 USB 분리와 같은 증상
    if ser is not None:
        ser.close()
        return "RelayBoard 시리얼 강제 종료"
    return "주입 불가"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ghost.ops.soak")
    p.add_argument("--config")
    p.add_argument("--sim", action="store_true")
    p.add_argument("--minutes", type=float, default=10)
    p.add_argument("--scenario", action="append", required=True, help="번갈아 실행할 시나리오 (여러 번)")
    p.add_argument("--fault-every", type=float, default=0, help="N초마다 장치 고장 주입 (0=안 함)")
    p.add_argument("--sim-alarm-every", type=float, default=0, help="시뮬레이터: N초마다 장비 알람 팝업")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--video", action="store_true", help="시뮬레이터에서도 블랙박스 영상 녹화 켜기 (실장비와 같은 조건)")
    p.add_argument("--trace-mem", action="store_true", help="tracemalloc 으로 메모리 증가 위치 기록 (mem_top.txt)")
    a = p.parse_args(argv)

    cfg = config.load(a.config, sim=a.sim)
    cfg["ops"]["health_every_min"] = 0.5
    if a.video:
        cfg["blackbox"]["video"]["enabled"] = True
    if a.trace_mem:
        import tracemalloc
        tracemalloc.start(15)
    snap0 = None
    out = os.path.join(config.path(cfg, "data"), "soak_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out, exist_ok=True)
    logf = open(os.path.join(out, "soak.log"), "w", encoding="utf-8")

    def log(m):
        line = f"{time.strftime('%H:%M:%S')} {m}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    dev = build_device(cfg, sim=a.sim, log=None)
    runner = build_runner(cfg, dev, log=lambda m: logf.write(m + "\n"))
    dev.open(home=True)
    store = Store(os.path.join(out, "ops.db"))
    lock = threading.Lock()
    op = Operator(cfg, dev, runner, store, lock, log=log)
    rnd = random.Random(a.seed)
    end = time.time() + a.minutes * 60
    next_fault = time.time() + a.fault_every if a.fault_every else None
    next_alarm = time.time() + a.sim_alarm_every if a.sim and a.sim_alarm_every else None
    mem = [(time.time(), rss_mb())]
    i = 0
    op.start()
    log(f"[soak] 시작: {a.minutes}분, 시나리오 {a.scenario}, 고장 주입 {a.fault_every or '없음'}s, 결과 {out}")
    try:
        while time.time() < end:
            if store.counts().get("queued", 0) == 0 and op.current is None and op.state == "running":
                op.submit(a.scenario[i % len(a.scenario)], source="soak")
                i += 1
            now = time.time()
            if next_fault and now >= next_fault and op.current is not None:
                log(f"[soak] 고장 주입: {inject(dev, a.sim, rnd)} (작업 {op.current['id']} 실행 중)")
                store.add_event("fault_injected", "soak")
                next_fault = now + a.fault_every
            if next_alarm and now >= next_alarm:
                _world(dev).app.schedule_alarm(0.1, "PRESSURE LOW")
                next_alarm = now + a.sim_alarm_every
            if op.state == "halted":
                log(f"[soak] 운영 정지: {op.halt_reason} — 시험 중단")
                break
            if now - mem[-1][0] >= 30:
                mem.append((now, rss_mb()))
                if a.trace_mem and snap0 is None and i >= 3:     # 초기 적재(모델·캐시)가 끝난 뒤 기준점
                    import tracemalloc
                    snap0 = tracemalloc.take_snapshot()
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("[soak] 사용자 중단")
    op.pause()
    while op.current is not None:
        time.sleep(0.5)
    op.stop()
    mem.append((time.time(), rss_mb()))
    if a.trace_mem and snap0 is not None:
        import tracemalloc
        diff = tracemalloc.take_snapshot().compare_to(snap0, "traceback")
        with open(os.path.join(out, "mem_top.txt"), "w", encoding="utf-8") as f:
            for st in diff[:12]:
                f.write(f"{st.size_diff / 1024:+.0f} KiB  count {st.count_diff:+d}\n")
                f.write("\n".join("    " + ln for ln in st.traceback.format()[-8:]) + "\n\n")
        log(f"[soak] 메모리 증가 상위: {os.path.join(out, 'mem_top.txt')}")
    s = report.summarize(store)
    with open(os.path.join(out, "report.html"), "w", encoding="utf-8") as f:
        f.write(report.render_html(s, "GHOST 장시간 시험 보고서"))
    with open(os.path.join(out, "jobs.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(report.jobs_csv(store))
    with open(os.path.join(out, "memory.csv"), "w", encoding="utf-8") as f:
        f.write("t,memory_mb\n" + "".join(f"{t:.0f},{m}\n" for t, m in mem))
    ev = s["events"]
    log(f"[soak] 끝: 작업 {s['total']}회, 성공률 {s['success_rate']}%, 상태 {s['by_status']}, "
        f"고장 주입 {ev.get('fault_injected', 0)} / 재연결 성공 {ev.get('reconnect_ok', 0)} 실패 {ev.get('reconnect_fail', 0)}, "
        f"메모리 {mem[0][1]} → {mem[-1][1]} MB (최대 {max(m for _, m in mem if m) if any(m for _, m in mem) else '-'})")
    for sc in s["scenarios"]:
        d = sc["duration"]
        log(f"  {sc['scenario']}: {sc['runs']}회 성공률 {sc['success_rate']}% " + (f"평균 {d['mean']}s p95 {d['p95']}s" if d else ""))
        for m, n in sc["top_errors"]:
            log(f"    ✗ {n}회 {m}")
    log(f"[soak] 보고서: {os.path.join(out, 'report.html')}")
    dev.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
