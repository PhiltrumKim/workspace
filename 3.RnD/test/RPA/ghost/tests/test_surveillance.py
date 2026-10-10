"""감시(Surveillance): 규칙 판정, 실행기 연동(handler/stop/on_abort), 단독 감시, 웹훅 알림."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from ghost import build_device, build_runner, config
from ghost.registry import Registry
from ghost.scenario import load
from ghost.sim import DemoEquipmentApp, SimWorld
from ghost.surveillance import Surveillance, validate_rules

ALARM_HANDLER = {"name": "alarm_popup", "type": "target", "target": "alarm_title",
                 "severity": "critical", "action": "handler", "handler": "ack_alarm"}


def _runner(cfg, **world):
    w = SimWorld(DemoEquipmentApp(run_duration=0.5), offset=(48, 48), **world)
    d = build_device(cfg, sim=True, world=w)
    r = build_runner(cfg, d, log=lambda m: None)
    d.open()
    return r, w


def _load(cfg, name, reg):
    return load(os.path.join(config.path(cfg, "scenarios"), name + ".json"), reg)


# ---------------------------------------------------------------- 규칙 판정 (check)
def test_target_rule_edges(cfg, sim_objects):
    reg = Registry(sim_objects)
    w = SimWorld(DemoEquipmentApp())
    s = Surveillance([dict(ALARM_HANDLER, action="notify")], reg, cfg)
    assert s.check(w.render()) == []
    w.app.trigger_alarm("X")
    ev = s.check(w.render())
    assert [(e.rule, e.kind) for e in ev] == [("alarm_popup", "appeared")]
    assert s.check(w.render()) == []                     # 지속 중에는 반복 이벤트 없음
    w.app.alarm = None
    assert [e.kind for e in s.check(w.render())] == ["cleared"]


def test_no_signal_rule(cfg, sim_objects):
    s = Surveillance([{"name": "signal", "type": "no_signal", "severity": "critical"}], Registry(sim_objects), cfg)
    w = SimWorld(DemoEquipmentApp())
    assert s.check(w.render()) == []
    w.signal = False
    assert [e.kind for e in s.check(w.render())] == ["appeared"]
    w.signal = True
    assert [e.kind for e in s.check(w.render())] == ["cleared"]


def test_frozen_rule(cfg, sim_objects):
    rule = {"name": "hang", "type": "frozen", "region": [300, 70, 1590, 980], "seconds": 30}
    s = Surveillance([rule], Registry(sim_objects), cfg)
    w = SimWorld(DemoEquipmentApp())
    f = w.render()
    assert s.check(f, now=0) == [] and s.check(f, now=29) == []
    assert [e.kind for e in s.check(f, now=31)] == ["appeared"]
    w.app.page = "run"                                    # 화면 변화 → 해소
    assert [e.kind for e in s.check(w.render(), now=32)] == ["cleared"]


def test_validate_rules(sim_objects):
    errs = validate_rules([
        {"name": "a", "type": "target", "target": "nope"},
        {"name": "a", "type": "frozen"},
        {"name": "c", "type": "target", "target": "alarm_title", "action": "handler"},
        {"name": "d", "type": "bogus", "severity": "fatal"},
    ], Registry(sim_objects))
    assert len(errs) == 6


# ---------------------------------------------------------------- 실행기 연동
def test_handler_recovers_and_lost_click_is_retried(cfg):
    """실행 중 알람: 핸들러가 확인 처리 → 알람에 막혀 유실된 클릭은 expect 실패로 재시도되어 성공."""
    r, w = _runner(cfg)
    w.app.schedule_alarm(0.3, "PRESSURE LOW")
    res = r.run(_load(cfg, "demo_run_watched", r.reg))
    assert res.ok, [(s.index, s.message) for s in res.steps if not s.ok]
    kinds = [(e["rule"], e["kind"]) for e in res.watch_events]
    assert ("alarm_popup", "appeared") in kinds and ("alarm_popup", "cleared") in kinds
    assert any(s.index.startswith("W:alarm_popup#1.") for s in res.steps)
    assert "ACK PRESSURE LOW" in w.app.events and w.app.events[-1].startswith("DONE rcp_b")


def test_stop_rule_aborts_and_runs_on_abort(cfg):
    r, w = _runner(cfg)
    w.app.schedule_alarm(0.2, "VACUUM FAIL")
    sc = {"ghost": 1, "name": "stop_case", "on_abort": "ack_alarm",
          "watch": [dict(ALARM_HANDLER, action="stop")],
          "steps": [{"action": "wait", "sec": 5}, {"action": "click", "target": "nav_run"}]}
    res = r.run(sc)
    assert not res.ok and res.aborted_by == "alarm_popup"
    assert w.app.page == "recipe"                         # 중단 이후 스텝은 실행되지 않음
    assert "ACK VACUUM FAIL" in w.app.events              # 안전 복귀(on_abort) 실행됨
    assert any(s.index.startswith("R.") for s in res.steps)
    assert any("WATCH_alarm_popup" in f for f in os.listdir(res.run_dir))
    with open(os.path.join(res.run_dir, "events.jsonl"), encoding="utf-8") as fh:
        ev = [json.loads(line) for line in fh]
    assert any(e["kind"] == "abort" for e in ev) and any(e["kind"] == "on_abort" and e["ok"] for e in ev)


def test_handler_that_cannot_fix_aborts(cfg):
    """핸들러가 알람을 해소하지 못하면 무한 반복하지 않고 MAX 회 후 중단."""
    scen = config.path(cfg, "scenarios")
    with open(os.path.join(scen, "noop_handler.json"), "w", encoding="utf-8") as f:
        json.dump({"ghost": 1, "name": "noop_handler", "steps": [{"action": "wait", "sec": 0.01}]}, f)
    r, w = _runner(cfg)
    w.app.trigger_alarm("STUCK")
    sc = {"ghost": 1, "name": "stuck", "watch": [dict(ALARM_HANDLER, handler="noop_handler")],
          "steps": [{"action": "wait", "sec": 10}]}
    res = r.run(sc)
    assert not res.ok and res.aborted_by == "alarm_popup"
    assert sum(1 for e in res.watch_events if e["kind"] == "appeared") == 6   # 5회 처리 + 6번째에 중단


def test_watch_only_handles_alarm(cfg):
    r, w = _runner(cfg)
    w.app.schedule_alarm(0.3, "DOOR OPEN")
    res = r.watch_only([ALARM_HANDLER], duration=2.0)
    assert res.ok and "ACK DOOR OPEN" in w.app.events
    assert [e["kind"] for e in res.watch_events] == ["appeared", "cleared"]


# ---------------------------------------------------------------- 알림
def test_webhook_notification(cfg):
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg["notify"] = {"webhook": f"http://127.0.0.1:{srv.server_port}/hook", "min_severity": "critical"}
        r, w = _runner(cfg)
        w.app.trigger_alarm("TEMP HIGH")
        r.watch_only([dict(ALARM_HANDLER, action="notify")], duration=0.5)
        for _ in range(50):
            if got:
                break
            threading.Event().wait(0.05)
        assert got and got[0]["rule"] == "alarm_popup" and got[0]["kind"] == "appeared"
        assert got[0]["severity"] == "critical" and "GHOST" in got[0]["text"]
    finally:
        srv.shutdown()
