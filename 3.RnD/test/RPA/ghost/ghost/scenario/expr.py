# -*- coding: utf-8 -*-
"""시나리오 계산식·변수 치환 (안전한 평가기).

계산식: 파이썬 문법의 부분집합만 허용 (eval 사용 안 함, 구문 트리 화이트리스트).
  숫자·문자열·True/False/None, 변수 이름, + - * / // %, 비교(== != < <= > >= in not in),
  and / or / not, 리스트, 함수 int float str len abs min max round lower upper strip
  예) "lot_no > 100 and recipe == 'RCP_B'"   "count + 1"   "len(lots) - i"
변수 값이 숫자처럼 보이는 문자열('09.91', '77')이면 계산식 안에서는 숫자로 다룬다.
(판독값은 문자열로 저장되므로 'elapsed_s > 5' 같은 비교가 바로 되도록)

치환: 문자열 안의 ${이름} 을 변수 값으로 바꾼다. 문자열 전체가 ${이름} 하나면 값의 타입을 유지한다.
"""
from __future__ import annotations

import ast
import operator
import re
from typing import Any, Dict, List, Set

VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge, ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
_FUNCS = {"int": lambda x: int(float(x)) if isinstance(x, str) else int(x), "float": float, "str": str, "len": len,
          "abs": abs, "min": min, "max": max, "round": round,
          "lower": lambda s: str(s).lower(), "upper": lambda s: str(s).upper(), "strip": lambda s: str(s).strip()}
_CONST = {"True": True, "False": False, "None": None, "true": True, "false": False}


class ExprError(ValueError):
    pass


def _as_number(v: Any) -> Any:
    if isinstance(v, str) and NUM_RE.match(v.strip()):
        s = v.strip()
        return float(s) if ("." in s) else int(s)
    return v


def check(expr: str) -> List[str]:
    """허용되지 않은 구문이 있으면 오류 목록. (실행 전 검증용)"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return [f"계산식 문법 오류: {expr!r} ({e.msg})"]
    errs = []
    for node in ast.walk(tree):
        ok = isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.BinOp, ast.UnaryOp, ast.Not,
                               ast.USub, ast.UAdd, ast.Compare, ast.Name, ast.Load, ast.Constant, ast.List,
                               ast.Tuple, ast.Call)) or type(node) in _BIN or type(node) in _CMP
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS):
            ok = False
        if not ok:
            errs.append(f"계산식에 허용되지 않은 구문: {type(node).__name__} ({expr!r})")
    return errs


def names(expr: str) -> Set[str]:
    """계산식이 참조하는 변수 이름 (함수 이름·상수 제외)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return set()
    funcs = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - funcs - set(_CONST)


def evaluate(expr: str, variables: Dict[str, Any]) -> Any:
    errs = check(expr)
    if errs:
        raise ExprError(errs[0])
    return _eval(ast.parse(expr, mode="eval").body, variables, expr)


def _eval(n, v, src):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Name):
        if n.id in _CONST:
            return _CONST[n.id]
        if n.id not in v:
            raise ExprError(f"정의되지 않은 변수 '{n.id}' ({src!r})")
        return _as_number(v[n.id])
    if isinstance(n, ast.BoolOp):
        if isinstance(n.op, ast.And):
            r = True
            for x in n.values:
                r = _eval(x, v, src)
                if not r:
                    return r
            return r
        r = False
        for x in n.values:
            r = _eval(x, v, src)
            if r:
                return r
        return r
    if isinstance(n, ast.UnaryOp):
        x = _eval(n.operand, v, src)
        return (not x) if isinstance(n.op, ast.Not) else (-x if isinstance(n.op, ast.USub) else +x)
    if isinstance(n, ast.BinOp):
        a, b = _eval(n.left, v, src), _eval(n.right, v, src)
        try:
            return _BIN[type(n.op)](a, b)
        except Exception as e:
            raise ExprError(f"계산 오류 {src!r}: {e}")
    if isinstance(n, ast.Compare):
        left = _eval(n.left, v, src)
        for op, right_n in zip(n.ops, n.comparators):
            right = _eval(right_n, v, src)
            try:
                if not _CMP[type(op)](left, right):
                    return False
            except TypeError as e:
                raise ExprError(f"비교할 수 없는 값 {src!r}: {e}")
            left = right
        return True
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_eval(x, v, src) for x in n.elts]
    if isinstance(n, ast.Call):
        args = [_eval(x, v, src) for x in n.args]
        try:
            return _FUNCS[n.func.id](*args)
        except Exception as e:
            raise ExprError(f"함수 오류 {src!r}: {e}")
    raise ExprError(f"지원하지 않는 구문 ({src!r})")


def refs(obj: Any) -> Set[str]:
    """객체 안 문자열들이 참조하는 ${이름} 목록."""
    out: Set[str] = set()
    if isinstance(obj, str):
        out.update(VAR_RE.findall(obj))
    elif isinstance(obj, dict):
        for x in obj.values():
            out |= refs(x)
    elif isinstance(obj, list):
        for x in obj:
            out |= refs(x)
    return out


def render(obj: Any, variables: Dict[str, Any], skip=("steps", "then", "else", "cond")) -> Any:
    """${이름} 치환 (중첩 스텝·조건은 실행 시점에 따로 치환하므로 건너뜀)."""
    if isinstance(obj, str):
        m = VAR_RE.fullmatch(obj)
        if m:
            if m.group(1) not in variables:
                raise ExprError(f"정의되지 않은 변수 '{m.group(1)}'")
            return variables[m.group(1)]

        def sub(mm):
            if mm.group(1) not in variables:
                raise ExprError(f"정의되지 않은 변수 '{mm.group(1)}'")
            return str(variables[mm.group(1)])
        return VAR_RE.sub(sub, obj)
    if isinstance(obj, dict):
        return {k: (x if k in skip else render(x, variables, skip)) for k, x in obj.items()}
    if isinstance(obj, list):
        return [render(x, variables, skip) for x in obj]
    return obj


def as_items(value: Any) -> List[Any]:
    """for_each 항목: 리스트 그대로, 문자열은 쉼표·줄바꿈으로 나눔."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [x.strip() for x in re.split(r"[,\n]", value) if x.strip()]
    if isinstance(value, (int, float)):
        return list(range(int(value)))
    raise ExprError(f"반복할 수 없는 값: {value!r}")
