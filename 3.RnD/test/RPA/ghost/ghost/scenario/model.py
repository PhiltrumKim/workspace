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

감시: "watch": [규칙...] 또는 "규칙파일.json" (ghost/surveillance.py 참고)
안전 복귀: "on_abort": "시나리오 이름" — 스텝 실패 또는 감시 규칙(action=stop) 중단 시 실행 (사용자 중지는 제외)

공통 필드: label, retry(실패 시 재시도 횟수), expect({visible|gone: target, timeout}) 사후조건
포인터 동작(click/double/right_click/move)은 target 또는 x,y 중 하나 필요.
  target 옵션: timeout(탐색 대기, 기본 3초), threshold, allow_hint(템플릿 미검출 시 hint 좌표 사용)
  target 은 레지스트리 이름 또는 텍스트(OCR) {"text": "START", "region": [x,y,w,h], "match": "contains"}
변수·파라미터:
  "params": {"lot_id": {"default": "LOT-0001", "description": "..."}}  실행 시 --param lot_id=X 로 지정
  문자열 필드 어디서나 ${이름} 으로 치환 (read 값, set 값, 반복 변수도 변수)
제어 구조:
  {"action": "set", "name": "n", "value": "..." | "expr": "n + 1"}
  {"action": "if", "cond": 조건, "then": [스텝], "else": [스텝]}
  {"action": "repeat", "times": 3, "var": "i", "steps": [...]}              i = 1..3
  {"action": "for_each", "items": "A,B" | [..] | "${lots}", "var": "lot", "steps": [...]}   lot_index = 1..
  {"action": "while", "cond": 조건, "max": 100, "steps": [...]}
  {"action": "break"} / {"action": "continue"} (반복 안에서) / {"action": "fail", "message": "..."}
  조건: {"visible": target, "timeout": 0} | {"gone": target} | {"expr": "n > 3 and lot == 'A'"}
        | {"all": [...]} | {"any": [...]} | {"not": 조건}       (계산식: ghost/scenario/expr.py)
  call 인자: {"action": "call", "scenario": "x", "args": {"lot_id": "${lot}"}}
read: {"action": "read", "name": "elapsed", "region": [x,y,w,h] | "anchor": target + "offset": [dx,dy,w,h],
       "pattern": "정규식", "min": 0, "max": 100, "scale": 2,
       "vote": true, "min_agree": 0.5} — 화면 글자/수치 읽기 (OCR). vote: 여러 설정 판독 후 위치별 다수결
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from ..hal import keymap

POINTER = {"click", "double", "right_click", "move"}
REQUIRED = {
    "click": [], "double": [], "right_click": [], "move": [],
    "key": ["key"], "hotkey": ["keys"], "type": ["text"],
    "wait": ["sec"], "wait_for": ["target"], "wait_gone": ["target"], "expect": ["target"],
    "screenshot": [], "call": ["scenario"], "home": [], "read": [],
    # 휠·드래그
    "scroll": ["amount"], "drag": ["to"], "scroll_to": ["target"],
    # 제어 구조
    "set": ["name"], "if": ["cond"], "repeat": ["times", "steps"], "for_each": ["items", "steps"],
    "while": ["cond", "steps"], "break": [], "continue": [], "fail": [],
}
CONTAINERS = {"if", "repeat", "for_each", "while"}
LOOPS = {"repeat", "for_each", "while"}
FORMAT_VERSION = 1
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ScenarioError(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _templated(v) -> bool:
    return isinstance(v, str) and "${" in v


def defined_names(sc: dict) -> set:
    """시나리오 어디서든 정의되는 변수 이름 (파라미터, read, set, 반복 변수)."""
    out = set((sc.get("params") or {}).keys())

    def walk(steps):
        for st in steps or []:
            if not isinstance(st, dict):
                continue
            a = st.get("action")
            if a == "read":
                out.add(st.get("name", "value"))
            elif a == "set" and st.get("name"):
                out.add(st["name"])
            elif a == "repeat" or a == "while":
                out.add(st.get("var", "i"))
            elif a == "for_each":
                v = st.get("var", "item")
                out.update({v, f"{v}_index"})
            for k in ("steps", "then", "else"):
                walk(st.get(k))
    walk(sc.get("steps"))
    return out


def _has_call(steps) -> bool:
    for st in steps or []:
        if isinstance(st, dict) and (st.get("action") == "call" or any(_has_call(st.get(k)) for k in ("steps", "then", "else"))):
            return True
    return False


def validate(sc: dict, registry=None) -> List[str]:
    from .expr import check as expr_check, names as expr_names, refs as var_refs
    errs: List[str] = []
    if not isinstance(sc, dict):
        return ["scenario must be an object"]
    if not sc.get("name"):
        errs.append("name 누락")
    steps = sc.get("steps")
    if not isinstance(steps, list) or not steps:
        return errs + ["steps 가 비어 있음"]
    params = sc.get("params") or {}
    if not isinstance(params, dict):
        errs.append("params 는 {이름: {default, description}} 형식")
        params = {}
    for k in params:
        if not NAME_RE.match(str(k)):
            errs.append(f"파라미터 이름 오류 '{k}' (영문·숫자·_)")
    defined = defined_names(sc)
    used: List[tuple] = []                        # (where, name)

    def check_target(where, t):
        if isinstance(t, dict):
            if "text" not in t:
                errs.append(f"{where}: 인라인 target 은 text 필요 {t!r}")
        elif _templated(t):
            pass                                  # 실행 시 결정
        elif registry is not None and t not in registry:
            errs.append(f"{where}: 등록되지 않은 target '{t}'")

    def check_cond(where, c):
        if not isinstance(c, dict):
            errs.append(f"{where}: 조건은 객체여야 함")
            return
        keys = [k for k in ("visible", "gone", "expr", "all", "any", "not") if k in c]
        if len(keys) != 1:
            errs.append(f"{where}: 조건은 visible·gone·expr·all·any·not 중 하나")
            return
        k = keys[0]
        if k in ("visible", "gone"):
            check_target(where, c[k])
        elif k == "expr":
            if _templated(c["expr"]):
                errs.append(f"{where}: 계산식 안에서는 ${{}} 없이 변수 이름을 그대로 쓰세요")
            errs.extend(f"{where}: {e}" for e in expr_check(str(c["expr"])))
            used.extend((where, n) for n in expr_names(str(c["expr"])))
        elif k in ("all", "any"):
            if not isinstance(c[k], list) or not c[k]:
                errs.append(f"{where}: {k} 는 조건 목록")
            else:
                for j, x in enumerate(c[k]):
                    check_cond(f"{where}.{k}[{j}]", x)
        else:
            check_cond(f"{where}.not", c["not"])

    def walk(steps, prefix, loop_depth):
        if not isinstance(steps, list):
            errs.append(f"{prefix}: 스텝 목록이어야 함")
            return
        for i, st in enumerate(steps):
            where = f"step[{prefix}{i}]"
            if not isinstance(st, dict):
                errs.append(f"{where}: 스텝은 객체여야 함")
                continue
            a = st.get("action")
            if a not in REQUIRED:
                errs.append(f"{where}: 알 수 없는 action '{a}'")
                continue
            for f in REQUIRED[a]:
                if f not in st:
                    errs.append(f"{where} {a}: '{f}' 필요")
            plain = {k: v for k, v in st.items() if k not in ("steps", "then", "else", "cond")}
            used.extend((where, n) for n in var_refs(plain))
            if a in POINTER:
                if "target" in st:
                    check_target(where, st["target"])
                elif not ("x" in st and "y" in st):
                    errs.append(f"{where} {a}: target 또는 x,y 필요")
            if a in ("wait_for", "wait_gone", "expect", "scroll_to") and "target" in st:
                check_target(where, st["target"])
            if a == "scroll":
                if "target" in st:
                    check_target(where, st["target"])
                if "amount" in st and not _templated(st["amount"]) and not isinstance(st["amount"], int):
                    errs.append(f"{where} scroll: amount 는 정수 (+위로, -아래로 휠 칸 수)")
            if a == "drag":
                if "target" in st:
                    check_target(where, st["target"])
                elif not ("x" in st and "y" in st):
                    errs.append(f"{where} drag: 시작점 target 또는 x,y 필요")
                to = st.get("to")
                if isinstance(to, list):
                    if len(to) != 2:
                        errs.append(f"{where} drag: to 는 target 이름 또는 [x, y]")
                elif to is not None:
                    check_target(where, to)
            if a == "scroll_to":
                at = st.get("at")
                if isinstance(at, list):
                    if len(at) != 2:
                        errs.append(f"{where} scroll_to: at 은 target 이름 또는 [x, y]")
                elif at is not None:
                    check_target(where, at)
                if st.get("direction", "down") not in ("down", "up"):
                    errs.append(f"{where} scroll_to: direction 은 down 또는 up")
            if a == "read":
                if "anchor" in st:
                    check_target(where, st["anchor"])
                    if len(st.get("offset", [])) != 4:
                        errs.append(f"{where} read: anchor 사용 시 offset [dx,dy,w,h] 필요")
                elif len(st.get("region", [])) != 4:
                    errs.append(f"{where} read: region [x,y,w,h] 또는 anchor+offset 필요")
                if "pattern" in st:
                    try:
                        re.compile(st["pattern"])
                    except re.error as e:
                        errs.append(f"{where} read: pattern 오류 {e}")
                if "name" in st and not NAME_RE.match(str(st["name"])):
                    errs.append(f"{where} read: 값 이름은 영문·숫자·_ ('{st['name']}')")
            if a == "key" and "key" in st and not _templated(st["key"]):
                _check_key(errs, where, st["key"])
            if a == "hotkey" and "keys" in st:
                for k in st["keys"]:
                    if not _templated(k):
                        _check_key(errs, where, k)
            if a == "type" and "text" in st:
                try:
                    for ch in re.sub(r"\$\{[^}]*\}", "", str(st["text"])):
                        keymap.char_to_key(ch)
                except ValueError as e:
                    errs.append(f"{where}: {e}")
            if a == "set":
                if not NAME_RE.match(str(st.get("name", ""))):
                    errs.append(f"{where} set: 변수 이름은 영문·숫자·_ ('{st.get('name')}')")
                if ("value" in st) == ("expr" in st):
                    errs.append(f"{where} set: value 또는 expr 중 하나 필요")
                if "expr" in st:
                    errs.extend(f"{where}: {e}" for e in expr_check(str(st["expr"])))
                    used.extend((where, n) for n in expr_names(str(st["expr"])))
            if a in ("if", "while") and "cond" in st:
                check_cond(where, st["cond"])
            if a == "repeat" and "times" in st and not _templated(st["times"]):
                try:
                    if not 0 <= int(st["times"]) <= 100000:
                        raise ValueError
                except (TypeError, ValueError):
                    errs.append(f"{where} repeat: times 는 0~100000 정수")
            if a in LOOPS and "var" in st and not NAME_RE.match(str(st["var"])):
                errs.append(f"{where} {a}: 반복 변수 이름은 영문·숫자·_")
            if a in ("break", "continue") and loop_depth == 0:
                errs.append(f"{where}: {a} 는 반복(repeat·for_each·while) 안에서만 쓸 수 있음")
            if a == "if":
                walk(st.get("then") or [], f"{prefix}{i}.then.", loop_depth)
                walk(st.get("else") or [], f"{prefix}{i}.else.", loop_depth)
                if not st.get("then") and not st.get("else"):
                    errs.append(f"{where} if: then 또는 else 에 스텝 필요")
            if a in LOOPS and "steps" in st:
                if not st["steps"]:
                    errs.append(f"{where} {a}: 반복할 스텝이 비어 있음")
                walk(st["steps"], f"{prefix}{i}.", loop_depth + 1)
            exp = st.get("expect")
            if exp is not None:
                keys = [k for k in ("visible", "gone") if k in exp]
                if len(keys) != 1:
                    errs.append(f"{where}: expect 는 visible 또는 gone 중 하나")
                else:
                    check_target(where, exp[keys[0]])

    walk(steps, "", 0)
    if not _has_call(steps):                      # 하위 시나리오가 돌려주는 값은 정적으로 알 수 없음
        for where, n in used:
            if n not in defined:
                errs.append(f"{where}: 정의되지 않은 변수 '{n}' (params·read·set·반복 변수로 정의하세요)")
    if sc.get("watch") is not None:
        from ..surveillance import validate_rules
        if not isinstance(sc["watch"], list):
            errs.append("watch 는 규칙 리스트 또는 규칙 파일 경로")
        else:
            errs += validate_rules(sc["watch"], registry)
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
    if isinstance(sc.get("watch"), str):          # 감시 규칙 파일 참조 → 규칙 리스트로 펼침
        import os
        from ..surveillance import load_rules
        sc["watch"] = load_rules(sc["watch"], os.path.dirname(os.path.abspath(path)))
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
        where = _t(st["target"]) if "target" in st else f"({st.get('x')},{st.get('y')})"
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
        return f"{a} {_t(st['target'])}{lab}"
    if a == "scroll":
        where = f" @{_t(st['target'])}" if "target" in st else f" @({st['x']},{st['y']})" if "x" in st else ""
        return f"scroll {st['amount']}{where}{lab}"
    if a == "drag":
        src = _t(st["target"]) if "target" in st else f"({st.get('x')},{st.get('y')})"
        to = st["to"]
        return f"drag {src} → {tuple(to) if isinstance(to, list) else _t(to)}{lab}"
    if a == "scroll_to":
        return f"scroll_to {_t(st['target'])} ({st.get('direction', 'down')}){lab}"
    if a == "call":
        return f"call ▷ {st['scenario']}{lab}"
    if a == "read":
        return f"read {st.get('name', 'value')}{lab}"
    if a == "set":
        return f"set {st.get('name')} = {st.get('expr', repr(st.get('value')))}{lab}"
    if a == "if":
        return f"if {_cond(st.get('cond'))}{lab}"
    if a == "repeat":
        return f"repeat {st.get('times')}회{lab}"
    if a == "for_each":
        return f"for_each {st.get('var', 'item')} in {st.get('items')!r}{lab}"
    if a == "while":
        return f"while {_cond(st.get('cond'))}{lab}"
    if a == "fail":
        return f"fail {st.get('message', '')}{lab}"
    return f"{a}{lab}"


def _cond(c) -> str:
    if not isinstance(c, dict):
        return "?"
    if "expr" in c:
        return str(c["expr"])
    if "visible" in c:
        return f"{_t(c['visible'])} 보임"
    if "gone" in c:
        return f"{_t(c['gone'])} 없음"
    if "not" in c:
        return f"not ({_cond(c['not'])})"
    for k in ("all", "any"):
        if k in c:
            return f" {'and' if k == 'all' else 'or'} ".join(f"({_cond(x)})" for x in c[k])
    return "?"


def _t(target) -> str:
    return target if isinstance(target, str) else f'"{target.get("text")}"'


def find_path(name: str, dirs: List[str]) -> Optional[str]:
    import os
    for d in dirs:
        p = os.path.join(d, name + ".json")
        if os.path.exists(p):
            return p
    return None
