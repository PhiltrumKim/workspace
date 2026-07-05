# -*- coding: utf-8 -*-
"""워크플로우(재사용 가능한 클릭 동작 시퀀스) 저장/실행.

워크플로우 = {"name","goal","steps":[{action,...}]}
지원 action:
  click     {object}          객체 템플릿을 현재 화면에서 찾아 중심 클릭 (없으면 click 힌트 좌표 폴백)
  click_xy  {x,y}             절대 프레임 좌표 클릭
  double    {object}          더블클릭
  key       {hid}             키 탭 (HID 스캔코드, 예: "0x29"=ESC)
  wait      {sec}             대기
  screenshot{label}           스크린샷 저장
  expect    {object}          객체가 보이는지 확인(없으면 실패)
"""
import os, json, time, cv2

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = os.path.join(BASE, "workflows")

def save_workflow(wf):
    os.makedirs(WF_DIR, exist_ok=True)
    with open(os.path.join(WF_DIR, wf["name"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)

def load_workflow(name):
    with open(os.path.join(WF_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)

def list_workflows():
    if not os.path.isdir(WF_DIR):
        return []
    return sorted(n[:-5] for n in os.listdir(WF_DIR) if n.endswith(".json"))

def _hid(v):
    return int(v, 16) if isinstance(v, str) else int(v)

def run(engine, registry, wf, thr=0.55, shots_dir=None):
    log = []
    def rec(i, a, tgt, msg):
        log.append({"i": i, "action": a, "target": tgt, "result": msg})
        engine.log(f"  [{i}] {a} {tgt or ''} -> {msg}")
    for i, st in enumerate(wf["steps"]):
        a = st["action"]
        if a in ("click", "double"):
            obj = st["object"]; tmpl = registry.template(obj)
            found = engine.find(tmpl, thr=thr) if tmpl is not None else None
            if found:
                engine.click(*found["center"], double=(a == "double"))
                rec(i, a, obj, f"clicked@{found['center']} score={found['score']}")
            elif "click" in registry.objs.get(obj, {}):
                engine.click(*registry.objs[obj]["click"], double=(a == "double"))
                rec(i, a, obj, "clicked(hint 좌표, 템플릿 미검출)")
            else:
                rec(i, a, obj, "NOT FOUND")
                return {"ok": False, "log": log}
        elif a == "click_xy":
            engine.click(st["x"], st["y"]); rec(i, a, None, f"clicked@({st['x']},{st['y']})")
        elif a == "key":
            engine.key_tap(_hid(st["hid"])); rec(i, a, None, f"key {st['hid']}")
        elif a == "wait":
            time.sleep(st.get("sec", 0.5)); rec(i, a, None, f"wait {st.get('sec',0.5)}s")
        elif a == "screenshot":
            fr = engine.screenshot(3)
            if shots_dir and fr is not None:
                os.makedirs(shots_dir, exist_ok=True)
                cv2.imwrite(os.path.join(shots_dir, f"{wf['name']}_{st.get('label','shot')}.png"), fr)
            rec(i, a, None, st.get("label", "shot"))
        elif a == "expect":
            obj = st["object"]; tmpl = registry.template(obj)
            found = engine.find(tmpl, thr=thr) if tmpl is not None else None
            rec(i, a, obj, "found" if found else "MISSING")
            if not found:
                return {"ok": False, "log": log}
        else:
            rec(i, a, None, "unknown action")
    return {"ok": True, "log": log}
