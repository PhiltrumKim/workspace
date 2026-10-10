"""Device 커서 제어(홈잉/실측/폐루프 이동)와 키보드를 시뮬레이터로 검증."""
import numpy as np
import pytest

from ghost import build_device
from ghost.sim import DemoEquipmentApp, SimWorld

TARGETS = [(960, 540), (200, 900), (1700, 150), (1500, 1000), (400, 300)]


def _dev(cfg, **world):
    w = SimWorld(DemoEquipmentApp(), **world)
    d = build_device(cfg, sim=True, world=w)
    d.open(home=False)
    return d, w


@pytest.mark.parametrize("offset", [(0, 0), (48, 48), (12, 30)])
def test_home_finds_capture_offset(cfg, offset):
    cfg["cursor"]["home_expect"] = list(offset)
    d, w = _dev(cfg, offset=offset)
    assert d.home() == offset
    assert d.measured


@pytest.mark.parametrize("world", [
    dict(gain=(1.0, 1.0)),
    dict(gain=(1.3, 0.8), noise=2.0),
    dict(gain=(1.1, 1.1), accel=0.5, noise=2.0),       # Windows 포인터 가속 유사
])
def test_closed_loop_move_converges(cfg, world):
    d, w = _dev(cfg, offset=(48, 48), **world)
    d.home()
    tol = cfg["cursor"]["tolerance"]
    for t in TARGETS:
        p = d.move_to(*t)
        actual = w.cursor_frame_pos()
        assert abs(actual[0] - t[0]) <= tol and abs(actual[1] - t[1]) <= tol, (t, p, actual)
        assert p == actual                          # 실측값이 실제 커서 위치와 일치


def test_open_loop_drifts_with_wrong_gain(cfg):
    """폐루프가 왜 필요한지: 이득이 틀리면 개루프 이동은 크게 빗나간다."""
    d, w = _dev(cfg, offset=(48, 48), gain=(1.2, 1.2))
    d.home()
    d.move_to(1500, 900, verify=False)
    ax, ay = w.cursor_frame_pos()
    assert abs(ax - 1500) > 100


def test_locate_ignores_far_changes(cfg):
    """커서 외 화면 변화(알람 팝업 등)가 있어도 near 기준으로 커서를 고른다."""
    d, w = _dev(cfg, offset=(0, 0))
    d.home()
    d.move_to(300, 800)
    w.app.trigger_alarm("FAR CHANGE")    # 화면 중앙에 큰 변화
    p = d.locate(near=(300, 800))
    assert p == w.cursor_frame_pos()


def test_typing_and_modifier_release(cfg):
    d, w = _dev(cfg)
    w.app.page, w.app.lot_focus = "run", True
    d.type_text("Ab-_9(")
    assert w.app.lot == "Ab-_9("
    assert d._mods == 0
    d.key_down("ctrl")
    d.release_all_keys()
    assert d._mods == 0
    with pytest.raises(ValueError):
        d.type_text("ok한")
    assert w.app.lot == "Ab-_9("                       # 검증 실패 시 부분 입력 없음


def test_click_hits_widget(cfg):
    d, w = _dev(cfg, offset=(48, 48), gain=(1.15, 1.15))
    d.home()
    x, y, bw, bh = w.app.widgets()["nav_run"]
    d.click(x + bw // 2 + 48, y + bh // 2 + 48)
    assert w.app.page == "run"
