# -*- coding: utf-8 -*-
from __future__ import annotations

from .app import DemoEquipmentApp
from .hal import SimHid, SimVideo, SimWorld

# 템플릿별 매칭 설정 (비슷한 모양끼리 구분되도록 임계값을 높인다)
_TARGET_META = {
    "rcp_a": {"threshold": 0.9}, "rcp_b": {"threshold": 0.9}, "rcp_c": {"threshold": 0.9},
    "status_idle": {"threshold": 0.9}, "status_running": {"threshold": 0.9}, "status_done": {"threshold": 0.9},
    "lot_label": {"threshold": 0.8, "click_offset": [330, 0]},   # 라벨을 찾아 오른쪽 입력칸 클릭
}


def export_templates(registry) -> list:
    """데모 앱의 각 화면 상태를 렌더링해 GUI 요소 템플릿을 레지스트리에 등록."""
    app = DemoEquipmentApp(run_duration=3600)
    shots = []
    app.page = "recipe"
    shots.append((app.render(), app.widgets()))
    app.page = "run"
    shots.append((app.render(), app.widgets()))
    app.selected = "rcp_a"
    app.click(*_center(app.widgets()["start_btn"]))          # running 상태
    shots.append((app.render(), app.widgets()))
    app.run_t0 -= 7200                                         # 즉시 done
    shots.append((app.render(), app.widgets()))
    app.trigger_alarm("TEMPLATE")
    shots.append((app.render(), app.widgets()))

    names = []
    for img, widgets in shots:
        for name, (x, y, w, h) in widgets.items():
            if name in names or name == "lot_field":
                continue
            registry.add(name, img[y:y + h, x:x + w].copy(), **_TARGET_META.get(name, {}))
            names.append(name)
    return names


def _center(box):
    x, y, w, h = box
    return x + w // 2, y + h // 2


__all__ = ["DemoEquipmentApp", "SimWorld", "SimVideo", "SimHid", "export_templates"]
