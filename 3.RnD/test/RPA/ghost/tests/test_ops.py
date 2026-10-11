"""무인 운영: 저장소·예약 판정·작업 실행기(시뮬레이터, 장치 고장 주입)."""
import datetime as dt
import os
import threading
import time

from ghost import build_device, build_runner, config
from ghost.ops import Operator, Store
from ghost.ops import schedule as sched


def _ops(cfg, **world):
    from ghost.sim import DemoEquipmentApp, SimWorld
    w = SimWorld(DemoEquipmentApp(run_duration=0.2), offset=(48, 48), **world)
    d = build_device(cfg, sim=True, world=w)
    r = build_runner(cfg, d, log=lambda m: None)
    d.open()
    store = Store(os.path.join(config.path(cfg, "data"), "ops.db"))
    op = Operator(cfg, d, r, store, threading.Lock())
    return op, w, store


def _wait(store, pred, timeout=30.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.05)
    return False


def _done(store, n):
    return lambda: sum(v for k, v in store.counts().items() if k not in ("queued", "running")) >= n


def test_store_queue(tmp_path):
    s = Store(str(tmp_path / "x.db"))
    a = s.add_job("a", {"p": 1})
    b = s.add_job("b")
    assert s.claim_next()["id"] == a
    assert s.cancel(b) and not s.cancel(a)            # 실행 중인 작업은 취소 대상 아님
    assert s.claim_next() is None
    s.finish_job(a, "ok", vals={"v": 1.5}, duration=2.0)
    j = s.job(a)
    assert j["status"] == "ok" and j["vals"] == {"v": 1.5} and j["params"] == {"p": 1} and j["attempts"] == 1
    s.add_job("c")
    s.claim_next()
    s2 = Store(str(tmp_path / "x.db"))                # 실행 중 프로그램 종료 → 다시 열면 interrupted
    assert s2.recover_interrupted() == 1
    assert s2.counts() == {"ok": 1, "cancelled": 1, "interrupted": 1}


def test_schedule_due():
    base = dt.datetime(2026, 10, 12, 7, 0).timestamp()     # 월요일 07:00
    iv = {"kind": "interval", "every_min": 30, "created": base, "last_run": None, "enabled": 1}
    assert sched.due(iv, base)                               # 처음은 바로
    iv["last_run"] = base
    assert not sched.due(iv, base + 29 * 60) and sched.due(iv, base + 30 * 60)
    daily = {"kind": "daily", "times": ["08:00", "20:00"], "days": [0, 1, 2, 3, 4],
             "created": base, "last_run": None, "enabled": 1}
    assert not sched.due(daily, base + 59 * 60)
    assert sched.due(daily, base + 60 * 60)
    daily["last_run"] = base + 60 * 60
    assert not sched.due(daily, base + 2 * 3600)
    assert sched.next_run(daily, base + 2 * 3600) == dt.datetime(2026, 10, 12, 20, 0).timestamp()
    sat = dt.datetime(2026, 10, 17, 9, 0).timestamp()       # 토요일: 요일 제한으로 실행 안 함
    daily["last_run"] = sat - 3600 * 2
    assert not sched.due(daily, sat)
    assert sched.describe(daily) == "월화수목금 08:00, 20:00"
    assert sched.validate("daily", times=["25:00"]) and sched.validate("interval", every_min=0.5)
    assert sched.validate("daily", times=["08:30"], days=[0, 6]) == []


def test_operator_runs_queue(cfg):
    op, w, store = _ops(cfg)
    op.submit("demo_run_recipe")
    op.submit("demo_lots", {"lots": "L1,L2"})
    try:
        op.submit("nope")
        assert False, "없는 시나리오는 대기열에 넣지 않아야 함"
    except ValueError:
        pass
    op.start()
    assert _wait(store, _done(store, 2))
    op.stop()
    jobs = store.jobs()
    assert [j["status"] for j in jobs] == ["ok", "ok"], [(j["scenario"], j["error"]) for j in jobs]
    assert jobs[0]["vals"].get("lot_read") == "L2" and jobs[0]["steps"] > 0
    assert jobs[1]["run_dir"] and os.path.isdir(os.path.join(config.path(cfg, "runs"), jobs[1]["run_dir"]))


def test_operator_failed_job_not_retried(cfg):
    op, w, store = _ops(cfg)
    op.submit("ack_alarm")                            # 알람이 없으므로 확인 버튼을 못 찾고 실패
    op.start()
    assert _wait(store, _done(store, 1))
    op.stop()
    jobs = store.jobs()
    assert len(jobs) == 1 and jobs[0]["status"] == "failed" and jobs[0]["error"]
    assert any("실패" in p["text"] for p in op.runner.notifier.sent)


def test_operator_recovers_device_error(cfg):
    op, w, store = _ops(cfg)
    w.hid_fail = True                                 # 입력 장치 끊김 → 첫 이동에서 DeviceError
    op.submit("demo_run_recipe")
    op.start()
    assert _wait(store, _done(store, 2))
    op.stop()
    jobs = store.jobs()[::-1]
    assert [j["status"] for j in jobs] == ["error", "ok"], [(j["status"], j["error"]) for j in jobs]
    assert jobs[1]["source"] == f"재시도:{jobs[0]['id']}"
    assert op.dev.stats["reconnects"] == 1
    kinds = [e["kind"] for e in store.events()]
    assert "device_error" in kinds and "reconnect_ok" in kinds and "retry" in kinds


def test_operator_halts_when_device_gone(cfg):
    op, w, store = _ops(cfg)
    w.video_fail, w.stubborn = True, 99               # 영상이 끊기고 재연결도 계속 실패
    op.submit("demo_run_recipe")
    op.submit("demo_run_recipe")
    op.start()
    assert _wait(store, lambda: op.state == "halted")
    assert store.counts() == {"error": 1, "queued": 1}     # 남은 작업은 정지 상태로 대기
    assert any(p["severity"] == "critical" for p in op.runner.notifier.sent)
    w.stubborn = 0                                    # 운영자가 케이블을 다시 연결했다고 가정
    w._reopen()
    op.resume()
    assert _wait(store, _done(store, 2))
    op.stop()
    assert store.counts() == {"error": 1, "ok": 1}


def test_operator_schedule_fires_and_skips(cfg):
    op, w, store = _ops(cfg)
    sid = store.add_schedule("주기 점검", "demo_run_recipe", "interval", every_min=1)
    op.start()
    assert _wait(store, _done(store, 1))
    op._schedule_tick()                               # 1분 안 지남 → 추가 안 됨
    assert len(store.jobs()) == 1
    store.set_schedule(sid, last_run=time.time() - 61)
    op.pause()
    op._schedule_tick()                               # 대기열에 넣고
    store.set_schedule(sid, last_run=time.time() - 61)
    op._schedule_tick()                               # 이전 것이 아직 대기 중 → 건너뜀
    op.stop()
    assert len(store.jobs()) == 2
    assert any(e["kind"] == "schedule_skip" for e in store.events())
    assert store.schedule(sid)["last_run"] > time.time() - 5


def test_report(tmp_path):
    from ghost.ops import report
    s = Store(str(tmp_path / "r.db"))
    for i, (st, dur, v) in enumerate([("ok", 10.0, "12.5"), ("ok", 12.0, "13.0"), ("failed", 3.0, None),
                                      ("error", 1.0, None), ("ok", 11.0, "x")]):
        j = s.add_job("measure")
        s.claim_next()
        s.finish_job(j, st, duration=dur, vals={"elapsed": v} if v else {}, watch=1 if i == 2 else 0,
                     error="버튼 못 찾음" if st == "failed" else ("no video frame" if st == "error" else None))
    s.add_event("reconnect_ok", "1회째")
    s.add_event("health", "memory_mb=123.4 device={}")
    sm = report.summarize(s)
    assert sm["total"] == 5 and sm["success_rate"] == 60.0 and sm["events"]["reconnect_ok"] == 1
    sc = sm["scenarios"][0]
    assert sc["duration"]["mean"] == 11.0 and sc["watch"] == 1
    assert sc["value_stats"]["elapsed"] == {"n": 2, "min": 12.5, "max": 13.0, "mean": 12.75, "last": 13.0}
    assert ("버튼 못 찾음", 1) in sc["top_errors"] and sm["memory"][0][1] == 123.4
    h = report.render_html(sm)
    assert h.startswith("<!doctype html>") and "<svg" in h and "measure" in h and "60.0%" in h
    c = report.jobs_csv(s)
    assert c.startswith("\ufeffid,scenario,status") and c.count("\n") == 6 and "장치 오류" in c
    assert report.summarize(s, since=time.time() + 10)["total"] == 0


def test_ops_api(cfg):
    import json
    import urllib.error
    import urllib.request
    from ghost.editor import EditorApp, serve
    from ghost.sim import DemoEquipmentApp, SimWorld
    app = EditorApp(cfg, sim=True, world=SimWorld(DemoEquipmentApp(run_duration=0.2), offset=(48, 48)))
    app.open()
    httpd = serve(app, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/api/ops/"

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method, headers={"Content-Type": "application/json"},
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert call("POST", "jobs", {"scenario": "nope"})[0] == 400
        code, r = call("POST", "jobs", {"scenario": "demo_run_recipe", "count": 2})
        assert code == 200 and len(r["ids"]) == 2
        assert call("DELETE", f"jobs/{r['ids'][1]}")[1] == {"cancelled": True}
        code, e = call("POST", "schedules", {"name": "x", "scenario": "demo_run_recipe", "kind": "daily",
                                             "times": ["25:00"]})
        assert code == 400 and "시각" in e["error"]
        code, sc = call("POST", "schedules", {"name": "점검", "scenario": "demo_run_recipe", "kind": "daily",
                                              "times": ["08:00"], "days": [0, 1, 2, 3, 4], "enabled": False})
        assert code == 200 and sc["enabled"] == 0
        code, lst = call("GET", "schedules")
        assert lst[0]["describe"] == "월화수목금 08:00" and lst[0]["next_run"] is None
        assert call("PUT", f"schedules/{sc['id']}", {"enabled": True})[1]["enabled"] == 1
        assert call("POST", "control", {"action": "start"})[1]["state"] == "running"
        assert _wait(app.store, _done(app.store, 2))
        st = call("GET", "status")[1]
        assert st["counts"] == {"ok": 1, "cancelled": 1} and (st["memory_mb"] or 1) > 0
        assert call("POST", "control", {"action": "pause"})[1]["state"] == "paused"
        assert call("GET", "report?days=1")[1]["total"] == 1
        code, h = call("GET", "report.html?days=1")
        assert code == 200 and b"<svg" in h
        code, c = call("GET", "jobs.csv")
        assert code == 200 and "demo_run_recipe".encode() in c
        assert call("GET", "report?since=bad")[0] == 400
        assert call("DELETE", f"schedules/{sc['id']}")[1] == {"deleted": True}
        assert any(ev["kind"] == "start" for ev in call("GET", "events")[1])
    finally:
        httpd.shutdown()
        app.close()


def test_operator_cleanup_after_device_error(cfg):
    import json
    d = config.path(cfg, "scenarios")
    with open(os.path.join(d, "go_log.json"), "w", encoding="utf-8") as f:
        json.dump({"ghost": 1, "name": "go_log", "steps": [{"action": "click", "target": "nav_log"}]}, f)
    with open(os.path.join(d, "recipe_safe.json"), "w", encoding="utf-8") as f:
        json.dump({"ghost": 1, "name": "recipe_safe", "on_abort": "go_log",
                   "steps": [{"action": "click", "target": "nav_recipe"}]}, f)
    op, w, store = _ops(cfg)
    w.hid_fail = True
    op.submit("recipe_safe")
    op.start()
    assert _wait(store, _done(store, 2))
    op.stop()
    assert [j["status"] for j in store.jobs()[::-1]] == ["error", "ok"]
    ev = [e for e in store.events() if e["kind"] == "cleanup"]
    assert ev and "'go_log': 성공" in ev[0]["detail"]
