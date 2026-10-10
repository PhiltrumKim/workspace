"""시나리오 형식 검증/레거시 변환 + 실행기 엔드투엔드(시뮬레이터)."""
import json
import os
import threading

from ghost import build_device, build_runner, config
from ghost.registry import Registry
from ghost.scenario import from_legacy, load, validate

LEGACY_WORKFLOW = {
    "name": "launch_web_browser", "goal": "Menu > Internet > Web Browser 자동 실행",
    "steps": [{"action": "click", "object": "menu_btn"}, {"action": "wait", "sec": 0.6},
              {"action": "key", "hid": "0x29"}, {"action": "click_xy", "x": 10, "y": 20},
              {"action": "run", "name": "sub"}],
}


def test_from_legacy():
    sc = from_legacy(LEGACY_WORKFLOW)
    assert sc["ghost"] == 1 and sc["description"].startswith("Menu")
    assert sc["steps"][0] == {"action": "click", "target": "menu_btn", "allow_hint": True}
    assert sc["steps"][2] == {"action": "key", "key": "esc"}
    assert sc["steps"][3] == {"action": "click", "x": 10, "y": 20}
    assert sc["steps"][4] == {"action": "call", "scenario": "sub"}
    assert validate(sc) == []


def test_validate_errors(sim_objects):
    reg = Registry(sim_objects)
    errs = validate({"name": "x", "steps": [
        {"action": "click"}, {"action": "click", "target": "nope"}, {"action": "key", "key": "zz"},
        {"action": "type", "text": "가"}, {"action": "fly"},
        {"action": "click", "target": "nav_run", "expect": {"visible": "a", "gone": "b"}},
    ]}, reg)
    assert len(errs) == 6


def _runner(cfg, **world):
    from ghost.sim import DemoEquipmentApp, SimWorld
    w = SimWorld(DemoEquipmentApp(run_duration=0.3), offset=(48, 48), **world)
    d = build_device(cfg, sim=True, world=w)
    r = build_runner(cfg, d, log=lambda m: None)
    d.open()
    return r, w


def _load(cfg, name, reg):
    return load(os.path.join(config.path(cfg, "scenarios"), name + ".json"), reg)


def test_demo_run_recipe_e2e(cfg):
    r, w = _runner(cfg, gain=(1.1, 1.1), accel=0.3, noise=2.0)
    res = r.run(_load(cfg, "demo_run_recipe", r.reg))
    assert res.ok, [(s.desc, s.message) for s in res.steps if not s.ok]
    assert w.app.events[-2:] == ["START rcp_b lot=LOT-2026A_01", "DONE rcp_b lot=LOT-2026A_01"]
    events = [json.loads(line) for line in open(os.path.join(res.run_dir, "events.jsonl"), encoding="utf-8")]
    assert events[0]["kind"] == "run_start" and events[-1]["kind"] == "run_end" and events[-1]["ok"]
    assert any(f.endswith("_done.png") for f in os.listdir(res.run_dir))


def test_alarm_recovery_with_call(cfg):
    r, w = _runner(cfg)
    res = r.run(_load(cfg, "demo_alarm_recovery", r.reg))
    assert res.ok
    assert "ALARM NO RECIPE SELECTED" in w.app.events and "ACK NO RECIPE SELECTED" in w.app.events
    assert any(s.index == "2.2" for s in res.steps)          # 하위 시나리오 스텝 번호


def test_failure_is_recorded_with_frame(cfg):
    r, w = _runner(cfg)
    sc = {"ghost": 1, "name": "fail_case", "steps": [
        {"action": "click", "target": "start_btn", "timeout": 0.2}]}   # recipe 페이지엔 START 없음
    res = r.run(sc)
    assert not res.ok and "미검출" in res.steps[-1].message
    assert any("FAIL" in f for f in os.listdir(res.run_dir))


def test_expect_retry(cfg):
    r, w = _runner(cfg)
    # 첫 클릭 후 알람이 끼어들어 사후조건 실패 → 재시도에서 성공하는 상황 연출
    orig = w.app.click
    state = {"n": 0}

    def flaky(x, y, b=1):
        state["n"] += 1
        if state["n"] == 1:
            return                     # 첫 클릭 유실
        orig(x, y, b)
    w.app.click = flaky
    sc = {"ghost": 1, "name": "retry_case", "steps": [
        {"action": "click", "target": "nav_run", "expect": {"visible": "start_btn", "timeout": 0.3}, "retry": 2}]}
    res = r.run(sc)
    assert res.ok and "재시도 1회" in res.steps[0].message


def test_stop_event(cfg):
    r, w = _runner(cfg)
    sc = {"ghost": 1, "name": "long", "steps": [{"action": "wait", "sec": 30}, {"action": "click", "x": 1, "y": 1}]}
    threading.Timer(0.3, r.stop_event.set).start()
    res = r.run(sc)
    assert res.stopped and not res.ok


def test_cursor_parked_off_text_target(cfg):
    """커서가 글자 target 위에 있으면 OCR 이 실패하므로 찾기 전에 치운다 (편집기 E2E 에서 발견)."""
    pytest = __import__("pytest")
    pytest.importorskip("rapidocr_onnxruntime")
    r, w = _runner(cfg)
    tgt = {"text": "RCP_A", "region": [360, 180, 716, 76]}
    r.dev.move_to(420, 222)                          # 'RCP_A' 글자 위
    res = r.run({"ghost": 1, "name": "park", "steps": [{"action": "wait_for", "target": tgt, "timeout": 1}]})
    assert res.ok
    cx, cy = r.dev.pos
    assert not (336 <= cx < 1100 and 156 <= cy < 280)
    cfg["cursor"]["auto_park"] = False
    r2, w2 = _runner(cfg)
    r2.dev.move_to(420, 222)
    res2 = r2.run({"ghost": 1, "name": "nopark", "steps": [{"action": "wait_for", "target": tgt, "timeout": 0.5}]})
    assert not res2.ok                               # 치우지 않으면 가려서 실패 (문제 재현)
