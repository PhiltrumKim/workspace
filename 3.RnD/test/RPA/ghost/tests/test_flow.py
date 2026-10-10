"""시나리오 표현력: 계산식·치환, 파라미터, set/if/repeat/for_each/while/break/continue/fail, call 인자 — 시뮬레이터."""
import json
import os

import pytest

from ghost import build_device, build_runner, config
from ghost.scenario import load, validate
from ghost.scenario.expr import ExprError, as_items, check, evaluate, render
from ghost.scenario.runner import resolve_params
from ghost.scenario.model import ScenarioError
from ghost.sim import DemoEquipmentApp, SimWorld


def _runner(cfg):
    w = SimWorld(DemoEquipmentApp(run_duration=0.3), offset=(48, 48))
    d = build_device(cfg, sim=True, world=w)
    r = build_runner(cfg, d, log=lambda m: None)
    d.open()
    return r, w


def sc(*steps, params=None):
    out = {"ghost": 1, "name": "flow", "steps": list(steps)}
    if params:
        out["params"] = params
    return out


# ---------------------------------------------------------------- 계산식·치환 (장치 불필요)
def test_expr_evaluate_and_blocked():
    v = {"lot_no": "77", "recipe": "RCP_B", "t": "09.91", "i": 2, "lots": ["A", "B"]}
    assert evaluate("lot_no > 50 and recipe == 'RCP_B'", v) is True
    assert evaluate("t > 5", v) is True                 # 숫자 문자열은 계산식에서 숫자
    assert evaluate("i * 3 + 1", v) == 7
    assert evaluate("len(lots) - i", v) == 0
    assert evaluate("lower(recipe) in ['rcp_a', 'rcp_b']", v) is True
    for bad in ["__import__('os')", "open('x')", "lots.append(1)", "(lambda: 1)()", "[x for x in lots]",
                "recipe.__class__"]:
        assert check(bad), bad
        with pytest.raises(ExprError):
            evaluate(bad, v)
    with pytest.raises(ExprError):
        evaluate("nope + 1", v)


def test_render_and_items():
    v = {"lot": "A1", "n": 3}
    assert render({"text": "LOT-${lot}", "times": "${n}", "steps": [{"t": "${zz}"}]}, v) == \
        {"text": "LOT-A1", "times": 3, "steps": [{"t": "${zz}"}]}   # 전체 치환은 타입 유지, 중첩 스텝은 건너뜀
    with pytest.raises(ExprError):
        render({"text": "${missing}"}, v)
    assert as_items("A, B,\nC") == ["A", "B", "C"] and as_items(["x"]) == ["x"] and as_items(2) == [0, 1]


def test_params_resolution():
    s = sc({"action": "wait", "sec": 0}, params={"a": {"default": "1"}, "b": {"description": "필수"}})
    assert resolve_params(s, {"b": "x"}) == {"a": "1", "b": "x"}
    with pytest.raises(ScenarioError):
        resolve_params(s, {})


def test_validator_catches_flow_errors(sim_objects):
    from ghost.registry import Registry
    errs = validate(sc(
        {"action": "break"},
        {"action": "type", "text": "${undefined_var}"},
        {"action": "if", "cond": {"expr": "open('x')"}, "then": [{"action": "wait", "sec": 0}]},
        {"action": "repeat", "times": 2, "steps": []},
        {"action": "set", "name": "bad name", "value": 1},
        {"action": "if", "cond": {"visible": "a", "gone": "b"}, "then": [{"action": "wait", "sec": 0}]},
        {"action": "while", "cond": {"expr": "x < 3"}, "steps": [{"action": "set", "name": "x", "expr": "x + 1"}]},
    ), Registry(sim_objects))
    text = "\n".join(errs)
    for frag in ("break", "undefined_var", "허용되지 않은", "비어 있음", "변수 이름", "중 하나"):
        assert frag in text, (frag, errs)
    assert "정의되지 않은 변수 'x'" not in text          # while 안 set 으로 정의된 x 는 정의된 것으로 본다


# ---------------------------------------------------------------- 실행
def test_set_if_else_with_screen_condition(cfg):
    r, w = _runner(cfg)
    res = r.run(sc(
        {"action": "set", "name": "n", "value": 5},
        {"action": "if", "cond": {"visible": "nav_run"},
         "then": [{"action": "set", "name": "seen", "value": "yes"}],
         "else": [{"action": "fail", "message": "없음"}]},
        {"action": "if", "cond": {"any": [{"visible": "start_btn"}, {"expr": "n > 10"}]},
         "then": [{"action": "fail", "message": "여기 오면 안 됨"}],
         "else": [{"action": "set", "name": "branch", "expr": "'else-' + str(n)"}]},
    ))
    assert res.ok and r.vars["seen"] == "yes" and r.vars["branch"] == "else-5"


def test_loops_break_continue(cfg):
    r, w = _runner(cfg)
    res = r.run(sc(
        {"action": "set", "name": "sum", "value": 0},
        {"action": "repeat", "times": 10, "var": "i", "steps": [
            {"action": "if", "cond": {"expr": "i % 2 == 0"}, "then": [{"action": "continue"}]},
            {"action": "if", "cond": {"expr": "i > 7"}, "then": [{"action": "break"}]},
            {"action": "set", "name": "sum", "expr": "sum + i"}]},          # 1+3+5+7
        {"action": "set", "name": "names", "value": ""},
        {"action": "for_each", "items": ["x", "y", "z"], "var": "it", "steps": [
            {"action": "set", "name": "names", "expr": "names + it + str(it_index)"}]},
        {"action": "set", "name": "k", "value": 0},
        {"action": "while", "cond": {"expr": "k < 4"}, "steps": [{"action": "set", "name": "k", "expr": "k + 1"}]},
    ))
    assert res.ok, [(s.index, s.message) for s in res.steps if not s.ok]
    assert r.vars["sum"] == 16 and r.vars["names"] == "x1y2z3" and r.vars["k"] == 4
    assert any(s.index == "1[3].2" for s in res.steps)                  # 반복 회차가 스텝 번호에 남는다


def test_while_limit_and_fail_message(cfg):
    r, w = _runner(cfg)
    res = r.run(sc({"action": "while", "cond": {"expr": "True"}, "max": 5,
                    "steps": [{"action": "wait", "sec": 0}]}))
    assert not res.ok and "상한" in res.steps[-1].message
    res = r.run(sc({"action": "set", "name": "v", "value": "B7"},
                   {"action": "fail", "message": "값 ${v} 이상"}))
    assert not res.ok and res.steps[-1].message == "값 B7 이상"


def test_call_with_args_and_exports(cfg):
    scen = config.path(cfg, "scenarios")
    with open(os.path.join(scen, "sub_calc.json"), "w", encoding="utf-8") as f:
        json.dump({"ghost": 1, "name": "sub_calc", "params": {"x": {"default": 1}},
                   "steps": [{"action": "set", "name": "doubled", "expr": "x * 2"}]}, f)
    r, w = _runner(cfg)
    res = r.run(sc({"action": "set", "name": "base", "value": 21},
                   {"action": "call", "scenario": "sub_calc", "args": {"x": "${base}"}},
                   {"action": "if", "cond": {"expr": "doubled != 42"}, "then": [{"action": "fail"}]}))
    assert res.ok and r.vars["doubled"] == 42 and "x" not in r.vars       # 하위 파라미터는 새지 않음


def test_demo_lots_with_params_and_alarm(cfg):
    pytest.importorskip("rapidocr_onnxruntime")
    r, w = _runner(cfg)
    w.app.schedule_alarm(1.5, "PRESSURE LOW")
    s = load(os.path.join(config.path(cfg, "scenarios"), "demo_lots.json"), r.reg)
    res = r.run(s, {"lots": "LOT-K1,LOT-K2", "recipe": "rcp_c"})
    assert res.ok, [(st.index, st.message) for st in res.steps if not st.ok]
    done = [e for e in w.app.events if e.startswith("DONE")]
    assert done == ["DONE rcp_c lot=LOT-K1", "DONE rcp_c lot=LOT-K2"]
    assert r.vars["done"] == 2 and res.values["lot_read"] == "LOT-K2"
    assert any(e["kind"] == "appeared" for e in res.watch_events)


def test_runtime_unknown_target_from_variable_fails_cleanly(cfg):
    r, w = _runner(cfg)
    res = r.run(sc({"action": "click", "target": "${t}", "timeout": 0.2}, params={"t": {"default": "no_such"}}))
    assert not res.ok and "등록되지 않은 target" in res.steps[-1].message
