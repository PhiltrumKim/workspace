# -*- coding: utf-8 -*-
"""GHOST 시나리오 형식 (v1) — 레거시 workflow/recipe 두 형식을 통합.

{
  "ghost": 1,
  "name": "run_recipe_b",
  "description": "...",
  "steps": [
    {"action": "click", "target": "nav_recipe", "label": "레시피 화면"},
    {"action": "click", "target": "rcp_b", "expect": {"visible": "rcp_b_selected", "timeout": 2}, "retry": 1},
    {"action": "type", "text": "LOT-0001"},
    {"action": "wait_for", "target": "status_done", "timeout": 30},
    {"action": "call", "scenario": "ack_alarm"}
  ]
}

공통 필드: label, retry(실패 시 재시도 횟수), expect({visible|gone: target, timeout}) 사후조건
포인터 동작(click/double/right_click/move)은 target 또는 x,y 중 하나 필요.
  target 옵션: timeout(탐색 대기, 기본 3초), threshold, allow_hint(템플릿 미검출 시 hint 좌표 사용)
"""
from __future__ import annotations

import json
from typing import List, Optional

from ..hal import keymap

POINTER = {"click", "double", "right_click", "move"}
REQUIRED = {
    "click": [], "double": [], "right_click": [], "move": [],
    "key": ["key"], "hotkey": ["keys"], "type": ["text"],
    "wait": ["sec"], "wait_for": ["target"], "wait_gone": ["target"], "expect": ["target"],
    "screenshot": [], "call": ["scenario"], "home": [],
}
FORMAT_VERSION = 1


class ScenarioError(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate(sc: dict, registry=None) -> List[str]:
    errs: List[str] = []
    if not isinstance(sc, dict):
        return ["scenario must be an object"]
    if not sc.get("name"):
        errs.append("name 누락")
    steps = sc.get("steps")
    if not isinstance(steps, list) or not steps:
        return errs + ["steps 가 비어 있음"]

    def check_target(where, t):
        if registry is not None and t not in registry:
            errs.append(f"{where}: 등록되지 않은 target '{t}'")

    for i, st in enumerate(steps):
        where = f"step[{i}]"
        a = st.get("action")
        if a not in REQUIRED:
            errs.append(f"{where}: 알 수 없는 action '{a}'")
            continue
        for f in REQUIRED[a]:
            if f not in st:
                errs.append(f"{where} {a}: '{f}' 필요")
        if a in POINTER:
            if "target" in st:
                check_target(where, st["target"])
            elif not ("x" in st and "y" in st):
                errs.append(f"{where} {a}: target 또는 x,y 필요")
        if a in ("wait_for", "wait_gone", "expect") and "target" in st:
            check_target(where, st["target"])
        if a == "key" and "key" in st:
            _check_key(errs, where, st["key"])
        if a == "hotkey" and "keys" in st:
            for k in st["keys"]:
                _check_key(errs, where, k)
        if a == "type" and "text" in st:
            try:
                for ch in st["text"]:
                    keymap.char_to_key(ch)
            except ValueError as e:
                errs.append(f"{where}: {e}")
        exp = st.get("expect")
        if exp is not None:
            keys = [k for k in ("visible", "gone") if k in exp]
            if len(keys) != 1:
                errs.append(f"{where}: expect 는 visible 또는 gone 중 하나")
            else:
                check_target(where, exp[keys[0]])
    return errs


def _check_key(errs, where, name):
    try:
        keymap.key(name)
    except KeyError:
        errs.append(f"{where}: 알 수 없는 키 '{name}'")


def load(path: str, registry=None) -> dict:
    with open(path, encoding="utf-8") as f:
        sc = json.load(f)
    if "ghost" not in sc:
        sc = from_legacy(sc)
    errs = validate(sc, registry)
    if errs:
        raise ScenarioError(errs)
    return sc


def save(sc: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sc, f, ensure_ascii=False, indent=2)


def from_legacy(old: dict) -> dict:
    """magewell_rpa 의 workflow({name,goal,steps}) / recipe({name,description,steps}) → v1."""
    steps = []
    for st in old.get("steps", []):
        a = st.get("action")
        new = {k: v for k, v in st.items() if k not in ("action", "object", "hid", "name")}
        if a in ("click", "double", "expect"):
            new.update(action=a, target=st["object"])
            if a != "expect":
                new["allow_hint"] = True          # 레거시 동작: 미검출 시 힌트 좌표 클릭
        elif a == "click_xy":
            new["action"] = "click"
        elif a == "key":
            code = int(st["hid"], 16) if isinstance(st["hid"], str) else int(st["hid"])
            if code not in keymap.USB_HID_TO_NAME:
                raise ScenarioError([f"레거시 HID 코드 0x{code:02X} 변환 불가"])
            new.update(action="key", key=keymap.USB_HID_TO_NAME[code])
        elif a in ("run", "recipe", "workflow"):
            new.update(action="call", scenario=st["name"])
        else:
            new["action"] = a
        steps.append({"action": new.pop("action"), **new})
    return {
        "ghost": FORMAT_VERSION,
        "name": old.get("name", "unnamed"),
        "description": old.get("description") or old.get("goal", ""),
        "steps": steps,
    }


def describe(st: dict) -> str:
    a = st.get("action")
    lab = f"  «{st['label']}»" if st.get("label") else ""
    if a in POINTER:
        where = st.get("target") or f"({st.get('x')},{st.get('y')})"
        return f"{a} {where}{lab}"
    if a == "key":
        return f"key {st['key']}{lab}"
    if a == "hotkey":
        return f"hotkey {'+'.join(st['keys'])}{lab}"
    if a == "type":
        return f"type {st['text']!r}{lab}"
    if a == "wait":
        return f"wait {st['sec']}s{lab}"
    if a in ("wait_for", "wait_gone", "expect"):
        return f"{a} {st['target']}{lab}"
    if a == "call":
        return f"call ▷ {st['scenario']}{lab}"
    return f"{a}{lab}"


def find_path(name: str, dirs: List[str]) -> Optional[str]:
    import os
    for d in dirs:
        p = os.path.join(d, name + ".json")
        if os.path.exists(p):
            return p
    return None
