"""OCR: 문자열 매칭, 텍스트 target(click/wait_for/expect/감시), read 액션 — 시뮬레이터."""
import os

import pytest

from ghost import build_device, build_runner
from ghost.registry import Registry
from ghost.scenario import validate
from ghost.sim import DemoEquipmentApp, SimWorld
from ghost.sim.app import LOT_FIELD, START_BTN, STATUS
from ghost.vision.ocr import normalize, text_matches

pytest.importorskip("rapidocr_onnxruntime")

OFF = 48                                   # 시뮬레이터 캡처 오프셋 → 프레임 좌표 = 화면 좌표 + 48


def frame_box(box, pad=6):
    x, y, w, h = box
    return [x + OFF - pad, y + OFF - pad, w + 2 * pad, h + 2 * pad]


def _runner(cfg):
    w = SimWorld(DemoEquipmentApp(run_duration=0.5), offset=(OFF, OFF))
    d = build_device(cfg, sim=True, world=w)
    r = build_runner(cfg, d, log=lambda m: None)
    d.open()
    return r, w


# ---------------------------------------------------------------- 매칭 규칙 (엔진 불필요)
def test_text_matching_rules():
    assert normalize("STATUS:  Done") == "status:done"
    assert text_matches("GHoST DemoTool – Analyzer", "ghost demotool - analyzer", "contains")
    assert text_matches("저장 안 함(N)", "저장안함", "contains")
    assert not text_matches("저장 안 함(N)", "저장", "exact")
    assert text_matches("ELAPSED 00:01:23", r"\d\d:\d\d:\d\d", "regex")
    assert text_matches("00:00: 14.00", r"^\d\d:\d\d:\d\d\.\d\d$", "regex")   # 실장비: '1' 앞 공백
    assert text_matches("STATUS: D0NE", "STATUS: DONE", "fuzzy")          # 0/O 오인식 허용
    assert not text_matches("STATUS: IDLE", "STATUS: DONE", "fuzzy")


# ---------------------------------------------------------------- 텍스트 target
def test_text_target_click_and_wait(cfg):
    r, w = _runner(cfg)
    sc = {"ghost": 1, "name": "ocr_flow", "steps": [
        {"action": "click", "target": {"text": "RECIPE", "region": [60, 120, 260, 300]}},
        {"action": "click", "target": "rcp_b", "expect": {"visible": "rcp_b_sel", "timeout": 2}, "retry": 1},
        {"action": "click", "target": {"text": "RUN", "region": [60, 120, 260, 300], "match": "exact"},
         "expect": {"visible": {"text": "START", "region": frame_box(START_BTN)}, "timeout": 3}},
        {"action": "click", "target": {"text": "START", "region": frame_box(START_BTN)}},
        {"action": "wait_for", "target": {"text": "STATUS: DONE", "region": frame_box(STATUS), "match": "fuzzy"},
         "timeout": 10},
    ]}
    assert validate(sc, r.reg) == []
    res = r.run(sc)
    assert res.ok, [(s.index, s.message) for s in res.steps if not s.ok]
    assert w.app.run_state == "done" and w.app.selected == "rcp_b"


def test_registry_text_target(cfg, tmp_path):
    reg = Registry(str(tmp_path / "obj"))
    reg.add_text("start_txt", "START", region=frame_box(START_BTN))
    assert reg.template("start_txt") is None and "start_txt" in reg
    r, w = _runner(cfg)
    r.reg = r.loc.reg = reg
    w.app.page = "run"
    w.app.selected = "rcp_a"
    res = r.run({"ghost": 1, "name": "reg_text", "steps": [{"action": "click", "target": "start_txt"}]})
    assert res.ok and w.app.run_state == "running"


def test_text_target_validation(sim_objects):
    errs = validate({"name": "x", "steps": [
        {"action": "click", "target": {"region": [0, 0, 10, 10]}},
        {"action": "read"},
        {"action": "read", "anchor": "start_btn"},
        {"action": "read", "region": [0, 0, 1, 1], "pattern": "("},
    ]}, Registry(sim_objects))
    assert len(errs) == 4


# ---------------------------------------------------------------- read 액션
def test_read_values(cfg):
    r, w = _runner(cfg)
    w.app.page, w.app.lot, w.app.selected = "run", "LOT-77A", "rcp_c"
    sc = {"ghost": 1, "name": "read_case", "steps": [
        {"action": "read", "name": "lot", "region": frame_box(LOT_FIELD)},
        {"action": "read", "name": "lot_no", "region": frame_box(LOT_FIELD), "pattern": r"LOT-(\d+)",
         "min": 1, "max": 100},
        {"action": "read", "name": "recipe", "anchor": "start_btn", "offset": [230, 20, 300, 40],
         "pattern": r"RCP_\w"},
    ]}
    assert validate(sc, r.reg) == []
    res = r.run(sc)
    assert res.ok, [(s.index, s.message) for s in res.steps if not s.ok]
    assert res.values == {"lot": "LOT-77A", "lot_no": "77", "recipe": "RCP_C"}
    assert any(f.endswith("read_lot_no.png") for f in os.listdir(res.run_dir))


def test_read_range_violation_fails(cfg):
    r, w = _runner(cfg)
    w.app.page, w.app.lot = "run", "LOT-500"
    res = r.run({"ghost": 1, "name": "range", "steps": [
        {"action": "read", "name": "n", "region": frame_box(LOT_FIELD), "pattern": r"(\d+)", "max": 100}]})
    assert not res.ok and "허용 범위" in res.steps[-1].message


# ---------------------------------------------------------------- 감시에 텍스트 target
def test_watch_rule_with_text_target(cfg):
    r, w = _runner(cfg)
    w.app.schedule_alarm(0.2, "COOLANT LOW")
    rule = {"name": "alarm_text", "type": "target", "severity": "critical", "action": "notify",
            "target": {"text": "COOLANT", "region": [700, 480, 600, 140]}}
    res = r.watch_only([rule], duration=2.5)
    assert [e["kind"] for e in res.watch_events] == ["appeared"]


def test_read_vote(cfg):
    r, w = _runner(cfg)
    w.app.page, w.app.lot = "run", "LOT-123"
    res = r.run({"ghost": 1, "name": "vote", "steps": [
        {"action": "read", "name": "lot", "region": frame_box(LOT_FIELD), "vote": True, "pattern": r"LOT-(\d+)"}]})
    assert res.ok and res.values["lot"] == "123"


def test_on_abort_runs_on_step_failure(cfg):
    """스텝 실패 시에도 안전 복귀(on_abort) 실행 — 실장비에서 실패 후 프로그램이 열린 채 남던 문제."""
    import json
    with open(os.path.join(cfg["paths"]["scenarios"], "to_run_page.json"), "w", encoding="utf-8") as f:
        json.dump({"ghost": 1, "name": "to_run_page", "steps": [{"action": "click", "target": "nav_run"}]}, f)
    r, w = _runner(cfg)
    res = r.run({"ghost": 1, "name": "fail_then_recover", "on_abort": "to_run_page", "steps": [
        {"action": "wait_for", "target": "status_done", "timeout": 0.2}]})
    assert not res.ok and w.app.page == "run" and any(s.index.startswith("R.") for s in res.steps)


def test_narrow_to_matched_words():
    """줄로 묶인 결과에서 찾는 글자 부분으로 상자를 좁힌다 (GTB-3000 탭 줄 오클릭 회귀)."""
    from ghost.vision.ocr import TextHit, group_lines, narrow
    words = [TextHit("Recipe", (10, 100, 50, 20), 0.9), TextHit("Run", (70, 100, 30, 20), 0.9),
             TextHit("Monitor", (104, 100, 60, 20), 0.9), TextHit("Results", (175, 100, 55, 20), 0.9)]
    line = [g for g in group_lines(words)][0]
    h = narrow(line, "Run Monitor")
    assert h.box == (70, 100, 94, 20) and h.text == "Run Monitor"
    one = TextHit("Recipe Run Monitor Results", (0, 0, 260, 20), 0.9)      # 검출기가 한 덩어리로 낸 경우
    c = narrow(one, "Results").center
    assert 190 < c[0] < 260
    assert narrow(one, "Recipe Run Monitor Results") is one


def test_confusable_chars_match():
    """OCR 이 o↔0, l↔1 을 헷갈려도 찾는다 (GTB-3000 'Tool-B2' → 'T001-B2')."""
    from ghost.vision.ocr import text_matches
    assert text_matches("T001-B2", "Tool-B2") and text_matches("+ Fab-l", "Fab-1", "contains")
    assert text_matches("CH-B2-3", "CH-B2-3", "exact") and not text_matches("Tool-B3", "Tool-B2")
