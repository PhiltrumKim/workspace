"""시나리오 편집기 API (브라우저 없이) — 시뮬레이터."""
import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from ghost.editor import EditorApp, serve
from ghost.sim import DemoEquipmentApp, SimWorld


@pytest.fixture
def editor(cfg):
    w = SimWorld(DemoEquipmentApp(run_duration=0.4), offset=(48, 48))
    app = EditorApp(cfg, sim=True, world=w)
    app.open()
    httpd = serve(app, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method, headers={"Content-Type": "application/json"},
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                ctype = r.headers.get("Content-Type", "")
                return r.status, json.loads(raw) if "json" in ctype else raw
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield call, app, w
    httpd.shutdown()
    app.close()


def test_state_frame_and_static(editor):
    call, app, w = editor
    code, st = call("GET", "/api/state")
    assert code == 200 and st["mode"] == "sim" and st["width"] == 1920 and "enter" in st["keys"]
    code, jpg = call("GET", "/api/frame.jpg?scale=0.5")
    assert code == 200 and jpg[:2] == b"\xff\xd8"
    code, html = call("GET", "/")
    assert code == 200 and "시나리오 편집기".encode() in html
    assert call("GET", "/static/app.js")[0] == 200
    assert call("GET", "/static/../server.py")[0] == 404


def test_register_targets_from_snapshot(editor):
    call, app, w = editor
    assert call("POST", "/api/snapshot")[0] == 200
    code, r = call("POST", "/api/ocr", {"box": [362, 182, 712, 72]})
    assert code == 200 and any("RCP_A" in x["text"] for x in r["hits"])
    code, r = call("POST", "/api/targets", {"name": "rcp_a_txt", "kind": "text", "text": "RCP_A",
                                            "box": [362, 182, 712, 72], "match": "contains"})
    assert code == 200 and r["text"] == "RCP_A"
    code, r = call("POST", "/api/targets", {"name": "rcp_a_img", "kind": "template", "box": [368, 188, 700, 60],
                                            "threshold": 0.9})
    assert code == 200 and r["file"] == "rcp_a_img.png"
    assert call("GET", "/api/targets/rcp_a_img.png")[1][:4] == b"\x89PNG"
    for name in ("rcp_a_txt", "rcp_a_img"):
        code, r = call("POST", "/api/locate", {"target": name})
        assert code == 200 and r["found"] and abs(r["center"][1] - 218) < 12
    assert call("POST", "/api/targets", {"name": "rcp_a_txt", "kind": "text", "text": "x"})[0] == 409
    assert call("POST", "/api/targets", {"name": "../evil", "kind": "text", "text": "x"})[0] == 400
    assert call("POST", "/api/targets", {"name": "nobox", "kind": "template"})[0] == 400
    assert call("DELETE", "/api/targets/rcp_a_img")[0] == 200
    assert not os.path.exists(os.path.join(app.reg.root, "rcp_a_img.png"))
    call("DELETE", "/api/targets/rcp_a_txt")


def test_scenario_save_validate_load(editor):
    call, app, w = editor
    bad = {"description": "x", "steps": [{"action": "click", "target": "nope"}]}
    code, r = call("PUT", "/api/scenarios/editor_case", bad)
    assert code == 200 and not r["saved"] and "nope" in r["errors"][0]
    good = {"description": "편집기 테스트", "steps": [{"action": "click", "target": "nav_run"},
                                                  {"action": "wait", "sec": 0.1}]}
    code, r = call("PUT", "/api/scenarios/editor_case", good)
    assert r["saved"]
    code, sc = call("GET", "/api/scenarios/editor_case")
    assert sc["name"] == "editor_case" and sc["ghost"] == 1 and len(sc["steps"]) == 2
    names = {s["name"]: s["kind"] for s in call("GET", "/api/scenarios")[1]}
    assert names["editor_case"] == "scenario" and names["watch_alarm"] == "watch"
    assert call("PUT", "/api/scenarios/..%2Fx", good)[0] == 400
    assert call("GET", "/api/scenarios/missing")[0] == 404


def test_step_run_stop_and_control(editor):
    call, app, w = editor
    code, r = call("POST", "/api/step", {"action": "click", "target": "nav_run",
                                         "expect": {"visible": "start_btn", "timeout": 2}})
    assert code == 200 and r["ok"] and w.app.page == "run"
    code, r = call("POST", "/api/step", {"action": "click", "target": "no_such"})
    assert code == 200 and not r["ok"]
    sc = {"name": "editor_run", "steps": [
        {"action": "click", "target": "nav_recipe"},
        {"action": "click", "target": "rcp_c", "expect": {"visible": "rcp_c_sel", "timeout": 2}},
        {"action": "read", "name": "recipe", "anchor": "rcp_c_sel", "offset": [0, 0, 700, 60], "pattern": r"RCP_\w"}]}
    assert call("POST", "/api/run", sc)[1]["started"]
    assert call("POST", "/api/step", {"action": "wait", "sec": 0.1})[0] == 409     # 실행 중 다른 조작 거부
    for _ in range(100):
        run = call("GET", "/api/run")[1]
        if not run["running"]:
            break
        time.sleep(0.1)
    assert run["ok"] and run["values"]["recipe"] == "RCP_C" and len(run["steps"]) == 3
    # 중지
    call("POST", "/api/run", {"name": "long", "steps": [{"action": "wait", "sec": 30}]})
    time.sleep(0.3)
    call("POST", "/api/run/stop")
    for _ in range(50):
        run = call("GET", "/api/run")[1]
        if not run["running"]:
            break
        time.sleep(0.1)
    assert not run["running"] and run.get("stopped")
    # 직접 조작
    code, r = call("POST", "/api/control", {"kind": "click", "x": 188, "y": 253})
    assert code == 200 and w.app.page == "run"
    assert call("POST", "/api/control", {"kind": "fly"})[0] == 400
    # 실행 기록
    runs = call("GET", "/api/runs")[1]
    assert runs and runs[0]["dir"].endswith("long")
    d = call("GET", f"/api/runs/{runs[1]['dir']}")[1]
    assert any(e["kind"] == "read" for e in d["events"])
    assert call("GET", f"/api/runs/{runs[0]['dir']}/..%5C..%5Cghost.json")[0] == 404
    logs = call("GET", "/api/logs?after=0")[1]
    assert logs["seq"] > 0 and any("직접 조작" in x["msg"] for x in logs["lines"])
