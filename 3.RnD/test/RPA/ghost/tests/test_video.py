"""블랙박스 영상: FrameHub(캡처 전담 스레드) + 이벤트 전후 클립 + 연속 녹화 — 시뮬레이터."""
import json
import os

import cv2
import pytest

from ghost import build_device, build_runner
from ghost.hal.hub import FrameHub
from ghost.sim import DemoEquipmentApp, SimWorld

ALARM = {"name": "alarm_popup", "type": "target", "target": "alarm_title", "severity": "critical", "action": "notify"}


@pytest.fixture
def vcfg(cfg):
    cfg["blackbox"]["video"].update(enabled=True, fps=10, pre_seconds=1.0, post_seconds=0.6, max_fps=30)
    return cfg


def _runner(cfg):
    w = SimWorld(DemoEquipmentApp(run_duration=0.5), offset=(48, 48))
    d = build_device(cfg, sim=True, world=w)
    r = build_runner(cfg, d, log=lambda m: None)
    d.open()
    return r, w, d


def _frames(path):
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, f = cap.read()
    cap.release()
    return n, (f.shape if ok else None)


def _events(run_dir):
    with open(os.path.join(run_dir, "events.jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def test_hub_frames_are_fresh(vcfg):
    r, w, d = _runner(vcfg)
    try:
        assert isinstance(d.video, FrameHub)
        assert d.origin == (48, 48)                       # 홈잉(흔들기 차분)이 허브 프레임으로 동작
        d.move_to(700, 500)
        assert w.cursor_frame_pos() == (700, 500)
        assert d.video.frames > 5
    finally:
        d.close()


def test_step_failure_saves_clip(vcfg):
    r, w, d = _runner(vcfg)
    try:
        sc = {"ghost": 1, "name": "fail_clip", "steps": [
            {"action": "wait", "sec": 1.2},
            {"action": "wait_for", "target": "status_done", "timeout": 0.2}]}
        res = r.run(sc)
    finally:
        d.close()
    assert not res.ok
    clips = [f for f in os.listdir(res.run_dir) if f.startswith("clip")]
    assert len(clips) == 1 and "step1_FAIL" in clips[0]
    n, shape = _frames(os.path.join(res.run_dir, clips[0]))
    expect = (1.0 + 0.6) * 10                              # (pre + post) * fps
    assert 0.6 * expect <= n <= 1.5 * expect, n
    assert shape == (540, 960, 3)                          # 0.5 배 축소
    ev = _events(res.run_dir)
    assert any(e["kind"] == "clip" for e in ev) and any(e["kind"] == "video" for e in ev)


def test_watch_event_clip_and_merge(vcfg):
    """critical 감시 이벤트 → 클립. 직후 구간(post) 안에 난 스텝 실패는 같은 클립에 합쳐진다."""
    vcfg["blackbox"]["video"]["post_seconds"] = 2.5
    r, w, d = _runner(vcfg)
    w.app.schedule_alarm(0.3, "PRESSURE LOW")
    try:
        sc = {"ghost": 1, "name": "watch_clip", "watch": [ALARM], "steps": [
            {"action": "wait", "sec": 0.8},
            {"action": "click", "target": "nav_run", "expect": {"visible": "start_btn", "timeout": 0.3}}]}
        res = r.run(sc)
    finally:
        d.close()
    clips = [f for f in os.listdir(res.run_dir) if f.startswith("clip")]
    assert len(clips) == 1 and "watch_alarm_popup" in clips[0], clips
    labels = [e["label"] for e in _events(res.run_dir) if e["kind"] == "clip"]
    assert labels[0] == "watch_alarm_popup" and any("FAIL" in lb for lb in labels)


def test_info_watch_event_no_clip(vcfg):
    r, w, d = _runner(vcfg)
    w.app.trigger_alarm("INFO ONLY")
    try:
        res = r.run({"ghost": 1, "name": "info", "watch": [dict(ALARM, severity="info")],
                     "steps": [{"action": "wait", "sec": 0.5}]})
    finally:
        d.close()
    assert res.ok and not [f for f in os.listdir(res.run_dir) if f.startswith("clip")]


def test_continuous_recording(vcfg):
    vcfg["blackbox"]["video"]["continuous"] = True
    r, w, d = _runner(vcfg)
    try:
        res = r.run({"ghost": 1, "name": "cont", "steps": [
            {"action": "click", "target": "nav_run"}, {"action": "wait", "sec": 1.5}]})
    finally:
        d.close()
    n, shape = _frames(os.path.join(res.run_dir, "run.mp4"))
    assert res.ok and n >= 12                              # ~1.5s 이상 * 10fps
