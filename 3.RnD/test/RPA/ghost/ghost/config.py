# -*- coding: utf-8 -*-
"""설정: 기본값 + JSON 파일(ghost.json) 덮어쓰기."""
from __future__ import annotations

import copy
import json
import os
from typing import Optional

DEFAULTS = {
    "hardware": {
        "port": "COM3",
        "baudrate": 115200,
        "camera": 0,
        "backend": "default",       # default | dshow | msmf
        "width": 1920,
        "height": 1080,
    },
    "cursor": {
        "home_pushes": 35,          # 홈잉 시 (-127,-127) 반복 횟수 (4K 대응 여유)
        "home_expect": [48, 48],    # 홈 위치의 예상 프레임 좌표 (장비별: RPi 대상 48,48 / Win7 대상 0,0 — ghost.json 에서 지정)
        "home_search": 140,
        "jiggle": 8,                # 커서 위치 측정용 흔들기 크기
        "diff_threshold": 40,       # 프레임 차분 임계값(BGR 합)
        "verify_moves": True,       # 이동 후 실측 보정(폐루프)
        "tolerance": 4,             # 허용 오차(px)
        "max_corrections": 3,
        "locate_window": 120,
        "max_blob": 56,             # 커서 흔적 덩어리 최대 크기(px). 아이콘 호버 하이라이트 등 큰 변화 배제
    },
    "timing": {
        "move_step": 0.01,          # 마우스 패킷 간 추가 대기
        "capture_latency": 0.3,     # 이동 → 캡처 영상 반영 지연 (Magewell 실측 ~0.16s + 프레임 읽기)
        "jiggle_settle": 0.35,      # 흔들기 후 영상 반영 대기
        "click_hold": 0.06,
        "click_settle": 0.4,
        "key_hold": 0.03,
        "key_gap": 0.03,
        "poll": 0.2,                # wait_for 폴링 간격
    },
    "vision": {
        # 0.6(레거시 값)은 글자만 다른 버튼끼리 오탐이 난다(START 템플릿 ↔ RUN 버튼 0.62)
        "threshold": 0.8,
        "scales": [1.0],
    },
    "paths": {
        "objects": "objects",
        "scenarios": "scenarios",
        "runs": "runs",
    },
    "blackbox": {
        "enabled": True,
        "frame_on_fail": True,
        "frame_every_step": False,
    },
    # --sim 실행 시 가상 장비 특성 (실장비에서 관찰된 비이상성을 기본값으로 재현)
    "simulator": {
        "offset": [48, 48],
        "gain": [1.1, 1.1],
        "accel": 0.3,
        "noise": 2.0,
        "run_duration": 1.0,
    },
}

# 시뮬레이터는 캡처 지연이 없으므로 대기 시간을 줄인다
SIM_OVERRIDES = {
    "timing": {"move_step": 0.0, "capture_latency": 0.0, "jiggle_settle": 0.0, "click_hold": 0.0, "click_settle": 0.05,
               "key_hold": 0.0, "key_gap": 0.0, "poll": 0.05},
}


def merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(path: Optional[str] = None, sim: bool = False) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if sim:
        cfg = merge(cfg, SIM_OVERRIDES)
    if path is None and os.path.exists("ghost.json"):
        path = "ghost.json"
    if path:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        cfg = merge(cfg, user)
        if sim and "sim" in user:
            cfg = merge(cfg, user["sim"])
        cfg["_base_dir"] = os.path.dirname(os.path.abspath(path))
    else:
        cfg["_base_dir"] = os.getcwd()
    return cfg


def path(cfg: dict, key: str) -> str:
    p = cfg["paths"][key]
    return p if os.path.isabs(p) else os.path.join(cfg["_base_dir"], p)
