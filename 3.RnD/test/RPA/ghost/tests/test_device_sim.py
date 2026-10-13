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
        d.type_text("oké")              # 지원하지 않는 글자 (한글은 입력기 전환으로 지원)
    assert w.app.lot == "Ab-_9("                       # 검증 실패 시 부분 입력 없음


def test_click_hits_widget(cfg):
    d, w = _dev(cfg, offset=(48, 48), gain=(1.15, 1.15))
    d.home()
    x, y, bw, bh = w.app.widgets()["nav_run"]
    d.click(x + bw // 2 + 48, y + bh // 2 + 48)
    assert w.app.page == "run"


# ---------------------------------------------------------------- 회귀: 실장비(Win7) 바탕화면 아이콘 호버
@pytest.mark.parametrize("home_expect", [(0, 0), (48, 48)])
def test_home_ignores_desktop_icon_hover(cfg, home_expect):
    """홈 위치에서 흔들면 아이콘 호버 하이라이트가 커서 흔적과 붙어 큰 덩어리가 되고,
    라벨 배경 변화만 작은 덩어리로 남는다. 2026-10-10 실장비에서 원점을 (25,69)로 오측정했던 상황."""
    cfg["cursor"]["home_expect"] = list(home_expect)
    d, w = _dev(cfg, offset=(0, 0), desktop_icon=True)
    assert d.home() == (0, 0)


def test_blob_locate_alone_misreads_icon_hover(cfg):
    """corner 모드 없이 일반 실측을 쓰면 라벨 변화를 커서로 오인한다 (corner 모드가 필요한 이유)."""
    d, w = _dev(cfg, offset=(0, 0), desktop_icon=True)
    d.home()
    p = d.locate(near=(48, 48), win=140)
    assert p is not None and p != (0, 0)


def test_move_and_locate_over_icon(cfg):
    """아이콘 셀 안팎으로 이동해도 실측이 실제 커서와 일치한다."""
    d, w = _dev(cfg, offset=(0, 0), desktop_icon=True)
    d.home()
    for t in [(40, 40), (300, 300), (20, 70)]:
        p = d.move_to(*t)
        assert p == w.cursor_frame_pos(), (t, p)


# ---------------------------------------------------------------- 적응형 확인 (실측 생략)
PATH = [(400, 300), (900, 500), (1300, 700), (700, 900), (1500, 300), (500, 600), (1100, 250), (800, 800)]


def test_adaptive_skips_after_trust(cfg):
    d, w = _dev(cfg, offset=(48, 48))
    d.home()
    for t in PATH:
        d.move_to(*t)
        assert w.cursor_frame_pos() == t
    n = cfg["cursor"]["trust_after"]
    assert d.stats["verified"] >= n and d.stats["skipped"] > 0
    assert d.stats["verified"] + d.stats["skipped"] == len(PATH)


def test_adaptive_always_policy(cfg):
    cfg["cursor"]["verify_moves"] = True
    d, w = _dev(cfg, offset=(48, 48))
    d.home()
    for t in PATH:
        d.move_to(*t)
    assert d.stats["skipped"] == 0


def test_adaptive_catches_drift_periodically(cfg):
    """신뢰 상태에서 이득이 바뀌면(예: 포인터 속도 설정 변경) 주기 실측에서 잡아내고 다시 매번 실측."""
    d, w = _dev(cfg, offset=(48, 48))
    d.home()
    for t in PATH[:4]:
        d.move_to(*t)
    assert d._streak >= cfg["cursor"]["trust_after"]
    w.gain = (1.25, 1.25)
    for t in PATH + PATH:
        p = d.move_to(*t)
    assert d.stats["corrections"] > 0
    # 드리프트 감지 이후 마지막 이동들은 다시 정확해야 한다
    assert abs(w.cursor_frame_pos()[0] - PATH[-1][0]) <= cfg["cursor"]["tolerance"]
    assert abs(w.cursor_frame_pos()[1] - PATH[-1][1]) <= cfg["cursor"]["tolerance"]


def test_adaptive_verifies_near_edge_and_after_distrust(cfg):
    d, w = _dev(cfg, offset=(0, 0))
    d.home()
    for t in PATH[:4]:
        d.move_to(*t)
    v = d.stats["verified"]
    d.move_to(1915, 540)                       # 가장자리
    assert d.stats["verified"] == v + 1
    d.move_to(900, 500)
    d.distrust()
    v = d.stats["verified"]
    d.move_to(600, 600)
    assert d.stats["verified"] == v + 1
