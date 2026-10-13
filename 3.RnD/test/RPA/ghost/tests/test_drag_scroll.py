"""휠 스크롤·드래그 앤 드롭·스크롤해서 찾기 (패킷 형식 + 시뮬레이터 엔드투엔드)."""
from ghost import build_device, build_runner
from ghost.hal.relayboard import mouse_packet
from ghost.scenario import validate

OFF = 48
LIST = [320 + OFF, 100 + OFF, 520, 600]            # 시뮬레이터 LOG 화면 목록 영역 (프레임 좌표)


def test_wheel_packet_matches_mitx():
    up, down, none = mouse_packet(0, 0, wheel=1), mouse_packet(0, 0, wheel=-1), mouse_packet(5, 0)
    assert len(up) == 12 and up[5] == 0x09 and down[5] == 0x01 and none[5] == 0x00
    assert mouse_packet(3, 0, buttons=1)[6] & 0x01            # 드래그: 누른 채 이동


def _runner(cfg):
    from ghost.sim import DemoEquipmentApp, SimWorld
    w = SimWorld(DemoEquipmentApp(run_duration=0.2), offset=(OFF, OFF))
    d = build_device(cfg, sim=True, world=w)
    r = build_runner(cfg, d, log=lambda m: None)
    d.open()
    return r, w


def test_scroll_find_open_and_drag(cfg):
    r, w = _runner(cfg)
    target = {"text": "SAMPLE-25", "match": "exact", "region": LIST}
    sc = {"ghost": 1, "name": "scroll_drag", "steps": [
        {"action": "click", "target": "nav_log"},
        {"action": "scroll_to", "target": target, "at": [LIST[0] + 200, LIST[1] + 300], "direction": "down",
         "step": 3, "max": 12},
        {"action": "double", "target": target},
        {"action": "drag", "target": target, "to": [1000 + OFF + 200, 300 + OFF + 100]},
        {"action": "scroll", "amount": 20, "x": LIST[0] + 200, "y": LIST[1] + 300},
    ]}
    assert validate(sc, r.reg) == []
    res = r.run(sc)
    assert res.ok, [(s.desc, s.message) for s in res.steps if not s.ok]
    ev = w.app.events
    assert "OPEN SAMPLE-25" in ev and "DROP SAMPLE-25" in ev
    assert w.app.scroll == 0                               # 위로 20칸 → 맨 위
    assert any(e.startswith("SCROLL") for e in ev)


def test_scroll_to_gives_up(cfg):
    r, w = _runner(cfg)
    sc = {"ghost": 1, "name": "scroll_missing", "steps": [
        {"action": "click", "target": "nav_log"},
        {"action": "scroll_to", "target": {"text": "SAMPLE-99", "match": "exact", "region": LIST},
         "at": [LIST[0] + 200, LIST[1] + 300], "max": 3},
    ]}
    res = r.run(sc)
    assert not res.ok and "3번 스크롤해도 안 보임" in res.steps[-1].message


def test_validate_drag_scroll():
    errs = validate({"name": "x", "steps": [
        {"action": "scroll"}, {"action": "scroll", "amount": "a"}, {"action": "drag", "to": [1, 2]},
        {"action": "drag", "x": 1, "y": 2, "to": [1]}, {"action": "scroll_to", "target": {"text": "a"}, "direction": "left"},
    ]})
    assert len(errs) == 5, errs


def test_hangul_keys_and_segments():
    from ghost.hal import hangul
    assert "".join(hangul.to_keys(c) for c in "한글") == "gksrmf"
    assert hangul.to_keys("값") == "rkqt" and hangul.to_keys("뷁") == "qnpfr" and hangul.to_keys("ㅘ") == "hk"
    assert hangul.segments("LOT 한글 메모 123 OK") == [("en", "LOT "), ("ko", "gksrmf apah 123 "), ("en", "OK")]


def test_type_hangul_toggles_ime(cfg):
    """한글이 섞이면 한/영 전환 키로 감싸서 두벌식 순서로 치고, 끝에 영문으로 되돌린다."""
    from ghost.hal import keymap
    from ghost.sim import DemoEquipmentApp, SimWorld
    w = SimWorld(DemoEquipmentApp(), offset=(OFF, OFF))
    d = build_device(cfg, sim=True, world=w)
    d.type_text("A 한")
    ralt = keymap.key("ralt")
    downs = [p for p in w.packets if p[4] == 0xFC and not (p[7] & 0x01)]         # 키 누름 패킷
    vks = [p[6] for p in downs]
    assert vks.count(ralt.vk) == 2                                                # 한글 앞뒤 전환
    assert vks[-1] == ralt.vk and keymap.key("g").vk in vks and keymap.key("k").vk in vks


def test_cross_point_click_and_component_validation(cfg):
    """교차점 클릭: x 는 x_of 대상, y 는 y_of 대상의 중심 (표 셀·웨이퍼 맵 칸)."""
    r, w = _runner(cfg)
    sc = {"ghost": 1, "name": "cross", "steps": [
        {"action": "click", "target": "nav_log"},
        {"action": "move", "x_of": "nav_run", "y_of": "nav_log"},
    ]}
    assert validate(sc, r.reg) == []
    res = r.run(sc)
    assert res.ok, [(s.desc, s.message) for s in res.steps if not s.ok]
    run_c = w.app.widgets()["nav_run"]
    log_c = w.app.widgets()["nav_log"]
    assert abs(r.dev.pos[0] - (run_c[0] + run_c[2] // 2 + OFF)) <= 6
    assert abs(r.dev.pos[1] - (log_c[1] + log_c[3] // 2 + OFF)) <= 6
    errs = validate({"name": "x", "steps": [
        {"action": "click", "x_of": "nav_run"}, {"action": "menu", "path": "File"}, {"action": "select", "x": 1, "y": 2},
        {"action": "adjust", "x": 1, "y": 2, "value": 3, "read": {"region": [1, 2]}},
    ]}, r.reg)
    assert len(errs) == 4, errs
