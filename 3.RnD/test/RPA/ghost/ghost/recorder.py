# -*- coding: utf-8 -*-
"""블랙박스 영상 녹화기.

FrameHub 의 모든 프레임을 받아 축소·JPEG 압축해 최근 pre_seconds 만큼 링 버퍼에 둔다.
이벤트(스텝 실패, 감시 이벤트, 중단)가 trigger 되면 직전 pre_seconds + 직후 post_seconds 를
영상 파일(clipNN_<label>.mp4)로 저장한다. 가까운 시간에 이벤트가 겹치면 클립 하나로 합친다.
continuous=True 면 실행 전체도 run.mp4 로 녹화한다.

영상 위 표시: 시각, 현재 스텝(ASCII — OpenCV 글꼴은 한글 불가), 이벤트 표시와 T±초.
한글 설명은 블랙박스 events.jsonl 에 남는다.
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX


def ascii_only(s: str) -> str:
    return re.sub(r"[^\x20-\x7e]+", "", s).strip()


class VideoRecorder:
    def __init__(self, cfg: dict, log=None):
        self.fps = float(cfg.get("fps", 5))
        self.pre = float(cfg.get("pre_seconds", 10))
        self.post = float(cfg.get("post_seconds", 5))
        self.scale = float(cfg.get("scale", 0.5))
        self.quality = int(cfg.get("jpeg_quality", 70))
        self.continuous = bool(cfg.get("continuous", False))
        self.log = log or (lambda m: None)
        self._lock = threading.Lock()
        self._buf: deque = deque()                  # (mono_ts, wall_ts, jpeg, overlay)
        self._active: List[dict] = []
        self._writers: List[threading.Thread] = []
        self._last = 0.0
        self._n = 0
        self.overlay = ""
        self.run_dir: Optional[str] = None
        self._cont = None
        self._cont_path = None
        self.saved: List[str] = []

    # 실행 수명주기 -------------------------------------------------------
    def begin(self, run_dir: str) -> None:
        with self._lock:
            self.run_dir, self._n, self._active = run_dir, 0, []
            if self.continuous:
                self._cont_path = os.path.join(run_dir, "run.mp4")
                self._cont = None                   # 첫 프레임 크기를 알면 연다

    def end(self) -> None:
        """진행 중 클립의 직후 구간이 찰 때까지(최대 post_seconds) 기다린 뒤 저장하고, 쓰기 완료까지 기다린다.
        (실패 직후 무슨 일이 있었는지가 사고 분석에 중요하므로 잘라내지 않는다)"""
        with self._lock:
            remain = max([c["end"] for c in self._active], default=0) - time.monotonic()
        if remain > 0:
            time.sleep(min(remain, self.post) + 1.0 / self.fps)
        with self._lock:
            pending, self._active = self._active, []
            if self._cont is not None:
                self._cont.release()
                self.saved.append(self._cont_path)
                self._cont = None
            self.run_dir = None
            for c in pending:
                self._write_async(c)
            writers, self._writers = self._writers, []   # 프레임 스레드가 띄운 쓰기도 포함 (잠금 안에서 등록됨)
        for t in writers:
            t.join(timeout=30)

    def annotate(self, text: str) -> None:
        self.overlay = ascii_only(text)[:90]

    def trigger(self, label: str, reason: str = "") -> Optional[str]:
        """이벤트 클립 예약. 저장될 파일 경로(진행 중 클립에 합쳐지면 그 경로)를 반환."""
        now = time.monotonic()
        with self._lock:
            if self.run_dir is None:
                return None
            for c in self._active:                  # 겹치면 합친다
                if now <= c["end"]:
                    c["end"] = max(c["end"], now + self.post)
                    c["events"].append((now, ascii_only(label)))
                    return c["path"]
            self._n += 1
            safe = re.sub(r"[^\w.-]+", "_", ascii_only(label) or "event")[:40]
            path = os.path.join(self.run_dir, f"clip{self._n:02d}_{safe}.mp4")
            self._active.append({"path": path, "end": now + self.post, "reason": reason,
                                 "events": [(now, ascii_only(label))],
                                 "frames": [it for it in self._buf if it[0] >= now - self.pre]})
            return path

    # 프레임 입력 (FrameHub listener) --------------------------------------
    def on_frame(self, ts: float, frame: np.ndarray) -> None:
        if ts - self._last < 1.0 / self.fps:
            return
        self._last = ts
        small = cv2.resize(frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            return
        item = (ts, time.time(), jpg.tobytes(), self.overlay)
        done = []
        with self._lock:
            self._buf.append(item)
            while self._buf and self._buf[0][0] < ts - self.pre:
                self._buf.popleft()
            for c in self._active:
                c["frames"].append(item)
            done = [c for c in self._active if ts >= c["end"]]
            self._active = [c for c in self._active if c not in done]
            for c in done:                          # 쓰기 스레드 등록은 잠금 안에서 (end() 가 놓치지 않도록)
                self._write_async(c)
            if self.continuous and self.run_dir is not None:
                if self._cont is None:
                    self._cont = self._open_writer(self._cont_path, small.shape[1], small.shape[0])
                if self._cont is not None:
                    self._cont.write(self._draw(small, item, []))

    # 영상 쓰기 -----------------------------------------------------------
    def _open_writer(self, path: str, w: int, h: int):
        vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
        if vw.isOpened():
            return vw
        alt = os.path.splitext(path)[0] + ".avi"     # mp4 코덱이 없으면 MJPG
        vw = cv2.VideoWriter(alt, cv2.VideoWriter_fourcc(*"MJPG"), self.fps, (w, h))
        if vw.isOpened():
            self.log(f"[recorder] mp4 코덱 없음 → {os.path.basename(alt)}")
            return vw
        self.log(f"[recorder] 영상 파일 열기 실패: {path}")
        return None

    def _write_async(self, clip: dict) -> None:
        """호출자는 self._lock 을 잡고 있어야 한다."""
        t = threading.Thread(target=self._write, args=(clip,), daemon=True)
        t.start()
        self._writers.append(t)

    def _write(self, clip: dict) -> None:
        frames = clip["frames"]
        if not frames:
            self.log(f"[recorder] 프레임 없음: {os.path.basename(clip['path'])}")
            return
        first = cv2.imdecode(np.frombuffer(frames[0][2], np.uint8), cv2.IMREAD_COLOR)
        vw = self._open_writer(clip["path"], first.shape[1], first.shape[0])
        if vw is None:
            return
        for it in frames:
            img = cv2.imdecode(np.frombuffer(it[2], np.uint8), cv2.IMREAD_COLOR)
            vw.write(self._draw(img, it, clip["events"]))
        vw.release()
        self.saved.append(clip["path"])

    def _draw(self, img: np.ndarray, item, events) -> np.ndarray:
        ts, wall, _, overlay = item
        h, w = img.shape[:2]
        s = max(0.35, w / 1920 * 1.1)
        bar = int(30 * s / 0.55)
        cv2.rectangle(img, (0, 0), (w, bar), (20, 20, 20), -1)
        stamp = datetime.fromtimestamp(wall).strftime("%Y-%m-%d %H:%M:%S.") + f"{int(wall % 1 * 10)}"
        cv2.putText(img, f"GHOST  {stamp}  {overlay}", (8, int(bar * 0.7)), FONT, s, (235, 235, 235), 1, cv2.LINE_AA)
        past = [(t, lb) for t, lb in events if t <= ts]
        if events:
            t_ev, lb = past[-1] if past else events[0]
            dt = ts - t_ev
            color = (40, 40, 220) if past else (0, 170, 230)
            text = f"EVENT {lb}  T{dt:+.1f}s"
            cv2.rectangle(img, (0, h - bar), (w, h), color, -1)
            cv2.putText(img, text, (8, h - int(bar * 0.3)), FONT, s, (255, 255, 255), 1, cv2.LINE_AA)
        return img
