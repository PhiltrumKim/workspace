# -*- coding: utf-8 -*-
"""GHOST 시나리오 편집기 — 로컬 웹 서버 (표준 라이브러리만 사용).

  python -m ghost editor [--sim] [--port 8765]   →  브라우저에서 http://127.0.0.1:8765

편집기 프로세스가 장치(실장비 또는 시뮬레이터)를 하나 열어 둔다.
- 화면: FrameHub 의 최신 프레임 (실시간), 정지 화면(스냅샷) 위에서 대상 지정
- 장치 조작(스텝 실행·전체 실행·직접 조작)은 잠금으로 한 번에 하나만
- 127.0.0.1 에만 바인딩 (외부 접속 불가)
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import cv2
import numpy as np

from .. import build_device, build_runner, config
from ..hal import keymap
from ..scenario import model

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,60}$")
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
        ".mp4": "video/mp4", ".avi": "video/x-msvideo", ".json": "application/json; charset=utf-8",
        ".jsonl": "text/plain; charset=utf-8"}


class ApiError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


class EditorApp:
    def __init__(self, cfg: dict, sim: bool = False, world=None):
        cfg["blackbox"]["video"]["enabled"] = True      # 실시간 화면에 FrameHub 필요 (실행 시 영상 클립도 남음)
        self.cfg = cfg
        self.sim = sim
        self._logs: deque = deque(maxlen=800)
        self._seq = 0
        self._log_lock = threading.Lock()
        self.dev = build_device(cfg, sim=sim, world=world, log=self.log)
        self.runner = build_runner(cfg, self.dev, log=self.log)
        self.reg = self.runner.reg
        self.lock = threading.Lock()                    # 장치 조작 직렬화
        self.snapshot: Optional[np.ndarray] = None
        self.run = {"running": False, "name": "", "steps": [], "ok": None, "run_dir": "", "values": {},
                    "started": 0.0}
        self.runner.on_step = self._on_step
        self.scen_dir = config.path(cfg, "scenarios")
        self.runs_dir = config.path(cfg, "runs")

    # ------------------------------------------------------------ 수명주기·로그
    def open(self) -> None:
        self.dev.open(home=True)

    def close(self) -> None:
        self.runner.stop_event.set()
        self.dev.close()

    def log(self, msg: str) -> None:
        with self._log_lock:
            self._seq += 1
            self._logs.append({"seq": self._seq, "t": time.time(), "msg": str(msg)})

    def logs(self, after: int = 0) -> dict:
        with self._log_lock:
            return {"seq": self._seq, "lines": [x for x in self._logs if x["seq"] > after]}

    def _on_step(self, sr) -> None:
        self.run["steps"].append(sr.__dict__.copy())

    # ------------------------------------------------------------ 화면
    def frame(self) -> np.ndarray:
        f = self.dev.video.read(timeout=1.0)
        if f is None:
            raise ApiError(503, "화면 없음 (캡처 장치 확인)")
        return f

    def jpeg(self, img: np.ndarray, scale: float = 1.0, quality: int = 75) -> bytes:
        if scale != 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()

    def take_snapshot(self) -> dict:
        self.snapshot = self.frame()
        h, w = self.snapshot.shape[:2]
        return {"width": w, "height": h, "t": time.time()}

    def _snap(self) -> np.ndarray:
        if self.snapshot is None:
            self.take_snapshot()
        return self.snapshot

    def state(self) -> dict:
        w, h = self.dev.video.size
        return {"mode": "sim" if self.sim else "hw", "width": w, "height": h,
                "port": None if self.sim else self.cfg["hardware"]["port"],
                "busy": self.lock.locked(), "running": self.run["running"],
                "cursor": list(self.dev.pos), "targets": len(self.reg.targets),
                "keys": sorted(keymap.KEYS)}

    # ------------------------------------------------------------ 대상(target)
    def targets(self) -> list:
        out = []
        for name in self.reg.names():
            rec = self.reg.get(name)
            out.append({"name": name, "kind": "text" if "text" in rec else "template",
                        **{k: v for k, v in rec.items() if k not in ("file",)}})
        return out

    def add_target(self, d: dict) -> dict:
        name = d.get("name", "")
        if not NAME_RE.match(name):
            raise ApiError(400, "이름은 영문·숫자·_·- 1~60자")
        if name in self.reg and not d.get("overwrite"):
            raise ApiError(409, f"이미 있는 이름: {name}")
        box = [int(v) for v in d.get("box", [])] if d.get("box") else None
        meta = {}
        for k in ("threshold", "color_tol"):
            if d.get(k) not in (None, ""):
                meta[k] = float(d[k])
        if d.get("click_offset"):
            meta["click_offset"] = [int(v) for v in d["click_offset"]]
        if d.get("kind") == "text":
            if not d.get("text"):
                raise ApiError(400, "찾을 글자를 입력하세요")
            if box:
                meta["region"] = box
            if d.get("match"):
                meta["match"] = d["match"]
            rec = self.reg.add_text(name, d["text"], **meta)
        else:
            if not box or box[2] < 4 or box[3] < 4:
                raise ApiError(400, "화면에서 영역을 드래그해 지정하세요")
            x, y, w, h = box
            img = self._snap()[y:y + h, x:x + w].copy()
            meta["hint"] = [x + w // 2, y + h // 2]
            rec = self.reg.add(name, img, **meta)
        self.log(f"[편집기] target '{name}' 저장 ({'글자' if 'text' in rec else '그림'})")
        return {"name": name, **rec}

    def delete_target(self, name: str) -> dict:
        if name not in self.reg:
            raise ApiError(404, f"없는 target: {name}")
        rec = self.reg.targets.pop(name)
        self.reg._cache.pop(name, None)
        self.reg.save()
        if "file" in rec:
            p = os.path.join(self.reg.root, rec["file"])
            if os.path.exists(p):
                os.remove(p)
        self.log(f"[편집기] target '{name}' 삭제")
        return {"deleted": name}

    def target_png(self, name: str) -> bytes:
        img = self.reg.template(name) if name in self.reg else None
        if img is None:
            raise ApiError(404, "이미지 없는 target")
        return cv2.imencode(".png", img)[1].tobytes()

    def ocr(self, box) -> dict:
        t0 = time.monotonic()
        hits = self.runner.loc.ocr.read(self._snap(), [int(v) for v in box] if box else None)
        return {"hits": [{"text": h.text, "conf": h.conf, "box": list(h.box)} for h in hits],
                "ms": int((time.monotonic() - t0) * 1000), "model": self.runner.loc.ocr.model}

    def locate(self, target, use_snapshot: bool = False) -> dict:
        img = self._snap() if use_snapshot else self.frame()
        t0 = time.monotonic()
        try:
            m = self.runner.loc.locate(target, img)
        except (KeyError, FileNotFoundError) as e:
            raise ApiError(400, str(e))
        ms = int((time.monotonic() - t0) * 1000)
        if m is None:
            return {"found": False, "ms": ms}
        return {"found": True, "box": list(m.box), "score": m.score, "center": list(m.center), "ms": ms}

    # ------------------------------------------------------------ 시나리오 파일
    def _scen_path(self, name: str) -> str:
        if not NAME_RE.match(name):
            raise ApiError(400, "시나리오 이름은 영문·숫자·_·- 1~60자")
        return os.path.join(self.scen_dir, name + ".json")

    def scenarios(self) -> list:
        out = []
        for fn in sorted(os.listdir(self.scen_dir)) if os.path.isdir(self.scen_dir) else []:
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.scen_dir, fn), encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            kind = "watch" if isinstance(data, dict) and "rules" in data and "steps" not in data else "scenario"
            out.append({"name": fn[:-5], "kind": kind,
                        "description": data.get("description", "") if isinstance(data, dict) else "",
                        "steps": len(data.get("steps", [])) if isinstance(data, dict) else 0})
        return out

    def load_scenario(self, name: str) -> dict:
        p = self._scen_path(name)
        if not os.path.exists(p):
            raise ApiError(404, f"없는 시나리오: {name}")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def validate(self, sc: dict) -> list:
        sc = dict(sc)
        if isinstance(sc.get("watch"), str):
            from ..surveillance import load_rules
            try:
                sc["watch"] = load_rules(sc["watch"], self.scen_dir)
            except (OSError, ValueError) as e:
                return [f"감시 규칙 파일 읽기 실패: {e}"]
        return model.validate(sc, self.reg)

    def save_scenario(self, name: str, sc: dict) -> dict:
        sc = {"ghost": 1, **sc, "name": name}
        errs = self.validate(sc)
        if errs:
            return {"saved": False, "errors": errs}
        os.makedirs(self.scen_dir, exist_ok=True)
        model.save(sc, self._scen_path(name))
        self.log(f"[편집기] 시나리오 '{name}' 저장 ({len(sc['steps'])} 스텝)")
        return {"saved": True, "errors": []}

    # ------------------------------------------------------------ 실행
    def _acquire(self):
        if not self.lock.acquire(blocking=False):
            raise ApiError(409, "다른 동작이 실행 중입니다")

    def run_step(self, st: dict, variables: Optional[dict] = None) -> dict:
        self._acquire()
        try:
            sr, values = self.runner.run_step(st, variables=variables)
        finally:
            self.lock.release()
        return {**sr.__dict__, "values": values, "cursor": list(self.dev.pos)}

    def start_run(self, sc: dict, params: Optional[dict] = None) -> dict:
        from ..scenario.runner import resolve_params
        sc = {"ghost": 1, "name": "editor_run", **sc}
        if isinstance(sc.get("watch"), str):
            from ..surveillance import load_rules
            sc["watch"] = load_rules(sc["watch"], self.scen_dir)
        errs = model.validate(sc, self.reg)
        if errs:
            raise ApiError(400, "; ".join(errs))
        try:
            resolve_params(sc, params)
        except model.ScenarioError as e:
            raise ApiError(400, str(e))
        self._acquire()
        self.run = {"running": True, "name": sc["name"], "steps": [], "ok": None, "run_dir": "",
                    "values": {}, "started": time.time(), "total": len(sc["steps"])}

        def work():
            try:
                res = self.runner.run(sc, params)
                self.run.update(ok=res.ok, run_dir=os.path.basename(res.run_dir), values=res.values,
                                stopped=res.stopped, aborted_by=res.aborted_by)
            except Exception as e:
                self.log(f"[편집기] 실행 오류: {e!r}")
                self.run.update(ok=False)
            finally:
                self.run["running"] = False
                self.lock.release()

        threading.Thread(target=work, name="editor-run", daemon=True).start()
        return {"started": True}

    def stop_run(self) -> dict:
        self.runner.stop_event.set()
        return {"stopping": self.run["running"]}

    def control(self, d: dict) -> dict:
        """편집 중 장비를 원하는 화면 상태로 옮기기 위한 직접 조작."""
        self._acquire()
        try:
            kind = d.get("kind")
            if kind in ("click", "double", "right_click", "move"):
                x, y = int(d["x"]), int(d["y"])
                if kind == "move":
                    self.dev.move_to(x, y)
                else:
                    self.dev.click(x, y, button=2 if kind == "right_click" else 1, double=kind == "double")
            elif kind == "type":
                self.dev.type_text(d.get("text", ""))
            elif kind == "key":
                self.dev.press(d["key"])
            elif kind == "hotkey":
                self.dev.hotkey(*d["keys"])
            elif kind == "home":
                self.dev.home()
            else:
                raise ApiError(400, f"알 수 없는 조작: {kind}")
        except (KeyError, ValueError) as e:
            raise ApiError(400, f"조작 오류: {e}")
        finally:
            self.lock.release()
        self.log(f"[편집기] 직접 조작 {kind} {d.get('x', '')} {d.get('y', '')} {d.get('text', '') or d.get('key', '') or ''}")
        return {"ok": True, "cursor": list(self.dev.pos)}

    # ------------------------------------------------------------ 실행 기록
    def runs(self, limit: int = 30) -> list:
        if not os.path.isdir(self.runs_dir):
            return []
        dirs = sorted((d for d in os.listdir(self.runs_dir) if re.match(r"^\d{8}_\d{6}_", d)), reverse=True)
        out = []
        for d in dirs[:limit]:
            ev = self._events(d)
            end = next((e for e in reversed(ev) if e.get("kind") == "run_end"), {})
            out.append({"dir": d, "ok": end.get("ok"), "t": end.get("t"),
                        "files": sorted(f for f in os.listdir(os.path.join(self.runs_dir, d)) if f != "events.jsonl")})
        return out

    def _events(self, d: str) -> list:
        p = os.path.join(self.runs_dir, d, "events.jsonl")
        if not os.path.exists(p):
            return []
        out = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
        return out

    def run_detail(self, d: str) -> dict:
        if not re.match(r"^\d{8}_\d{6}_[\w.-]+$", d) or not os.path.isdir(os.path.join(self.runs_dir, d)):
            raise ApiError(404, "없는 실행 기록")
        ev = self._events(d)
        return {"dir": d, "events": [e for e in ev if e.get("kind") != "scenario"],
                "files": sorted(f for f in os.listdir(os.path.join(self.runs_dir, d)) if f != "events.jsonl")}

    def run_file(self, d: str, fn: str) -> str:
        base = os.path.realpath(self.runs_dir)
        p = os.path.realpath(os.path.join(self.runs_dir, d, fn))
        if not p.startswith(base + os.sep) or not os.path.isfile(p):
            raise ApiError(404, "없는 파일")
        return p


# ---------------------------------------------------------------- HTTP
def make_handler(app: EditorApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GHOSTEditor/0.1"

        def log_message(self, fmt, *args):            # 콘솔 소음 억제
            pass

        # 응답 도우미
        def _send(self, status: int, body: bytes, ctype: str, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200):
            self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except ValueError:
                raise ApiError(400, "JSON 형식 오류")

        def _file(self, path: str):
            with open(path, "rb") as f:
                data = f.read()
            self._send(200, data, MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))

        def _dispatch(self, method: str):
            u = urllib.parse.urlparse(self.path)
            q = dict(urllib.parse.parse_qsl(u.query))
            parts = [urllib.parse.unquote(p) for p in u.path.strip("/").split("/") if p]
            try:
                if method == "GET" and (not parts or parts[0] in ("index.html",)):
                    return self._file(os.path.join(STATIC, "index.html"))
                if method == "GET" and parts[0] == "static" and len(parts) == 2 and "/" not in parts[1] \
                        and os.path.isfile(os.path.join(STATIC, parts[1])):
                    return self._file(os.path.join(STATIC, parts[1]))
                if parts[0] != "api":
                    raise ApiError(404, "없는 경로")
                return self._api(method, parts[1:], q)
            except ApiError as e:
                self._json({"error": str(e)}, e.status)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass                                    # 브라우저가 응답 도중 연결을 끊음 (페이지 닫힘·새로고침)
            except Exception as e:                      # 예상 못한 오류도 JSON 으로
                app.log(f"[편집기] API 오류 {self.path}: {e!r}")
                self._json({"error": f"서버 오류: {e!r}"}, 500)

        def _api(self, m: str, p: list, q: dict):
            a = app
            key = (m, p[0] if p else "")
            if key == ("GET", "state"):
                return self._json(a.state())
            if key == ("GET", "frame.jpg"):
                return self._send(200, a.jpeg(a.frame(), float(q.get("scale", 0.5))), "image/jpeg")
            if key == ("POST", "snapshot"):
                return self._json(a.take_snapshot())
            if key == ("GET", "snapshot.jpg"):
                return self._send(200, a.jpeg(a._snap(), float(q.get("scale", 1.0)), 85), "image/jpeg")
            if key == ("GET", "targets") and len(p) == 1:
                return self._json(a.targets())
            if key == ("GET", "targets") and len(p) == 2 and p[1].endswith(".png"):
                return self._send(200, a.target_png(p[1][:-4]), "image/png")
            if key == ("POST", "targets"):
                return self._json(a.add_target(self._body()))
            if key == ("DELETE", "targets") and len(p) == 2:
                return self._json(a.delete_target(p[1]))
            if key == ("POST", "ocr"):
                return self._json(a.ocr(self._body().get("box")))
            if key == ("POST", "locate"):
                b = self._body()
                return self._json(a.locate(b.get("target"), bool(b.get("snapshot"))))
            if key == ("GET", "scenarios") and len(p) == 1:
                return self._json(a.scenarios())
            if key == ("GET", "scenarios") and len(p) == 2:
                return self._json(a.load_scenario(p[1]))
            if key == ("PUT", "scenarios") and len(p) == 2:
                return self._json(a.save_scenario(p[1], self._body()))
            if key == ("POST", "validate"):
                return self._json({"errors": a.validate(self._body())})
            if key == ("POST", "step"):
                b = self._body()                         # {"step": .., "vars": ..} 또는 스텝 자체
                return self._json(a.run_step(b["step"], b.get("vars")) if "step" in b else a.run_step(b))
            if key == ("POST", "run") and len(p) == 1:
                b = self._body()                         # {"scenario": .., "params": ..} 또는 시나리오 자체
                return self._json(a.start_run(b["scenario"], b.get("params")) if "scenario" in b else a.start_run(b))
            if key == ("GET", "run"):
                return self._json(a.run)
            if key == ("POST", "run") and p[1:] == ["stop"]:
                return self._json(a.stop_run())
            if key == ("POST", "control"):
                return self._json(a.control(self._body()))
            if key == ("GET", "logs"):
                return self._json(a.logs(int(q.get("after", 0))))
            if key == ("GET", "runs") and len(p) == 1:
                return self._json(a.runs())
            if key == ("GET", "runs") and len(p) == 2:
                return self._json(a.run_detail(p[1]))
            if key == ("GET", "runs") and len(p) == 3:
                return self._file(a.run_file(p[1], p[2]))
            raise ApiError(404, f"없는 API: {m} /{'/'.join(p)}")

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

    return Handler


def serve(app: EditorApp, port: int = 8765, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
