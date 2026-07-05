# -*- coding: utf-8 -*-
"""
RelayVisionEngine: 캡처 영상(비전) + 릴레이보드(제어)를 묶은 RPA 실행 엔진.
아이콘을 '클릭 가능한 객체(템플릿)'로 다루며 find/move/click/key 를 제공한다.

좌표계: 캡처 프레임 픽셀(1920x1080). 커서 위치는 홈 원점 자동 보정으로 프레임 좌표에 맞춘다.
"""
import time
import cv2
import numpy as np
from magewell_rpa.core.relay_board import RelayBoardController

LEFT, RIGHT, MIDDLE = 1, 2, 4

class RelayVisionEngine:
    def __init__(self, port="COM3", cam=0, monitor=(1920, 1080), verbose=True):
        self.port = port
        self.cam = cam
        self.monitor = monitor
        self.verbose = verbose
        self.rb = None
        self.cap = None
        self.cur = (0, 0)          # 현재 커서(프레임 좌표, 추정)
        self.origin = (0, 0)       # 홈(0,0)의 프레임 좌표

    def log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    # ---------- 연결/생명주기 ----------
    def connect(self):
        self.rb = RelayBoardController(port=self.port, verbose=False)
        if not self.rb.connect():
            self.log("[engine] relay 연결 실패"); return False
        self.rb.set_mode("remote"); time.sleep(0.3)
        self._wake()
        self.cap = cv2.VideoCapture(self.cam)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.monitor[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.monitor[1])
        time.sleep(0.5)
        self.home()
        return True

    def close(self):
        try:
            if self.cap: self.cap.release()
        finally:
            if self.rb: self.rb.disconnect()

    def _wake(self):
        for _ in range(4):
            self.rb.send_mouse_move(40, 0, quiet=True); time.sleep(0.1)
            self.rb.send_mouse_move(-40, 0, quiet=True); time.sleep(0.1)

    # ---------- 비전 ----------
    def screenshot(self, n=3):
        f = None
        for _ in range(n):
            r, fr = self.cap.read()
            if r and fr is not None:
                f = fr
            time.sleep(0.02)
        return f

    def _locate(self, expect=None, win=90):
        """(+8,+8) 흔들기 전후 차분으로 실제 커서 위치 측정(팁 근사)."""
        a = self.screenshot()
        self.rb.send_mouse_move(8, 8, quiet=True); time.sleep(0.25)
        b = self.screenshot()
        self.rb.send_mouse_move(-8, -8, quiet=True); time.sleep(0.15)
        d = (np.abs(a.astype(int) - b.astype(int)).sum(2) > 40)
        if expect is not None:
            ex, ey = expect
            m = np.zeros(d.shape, dtype=bool)
            y0, y1 = max(0, ey-win), min(d.shape[0], ey+win)
            x0, x1 = max(0, ex-win), min(d.shape[1], ex+win)
            m[y0:y1, x0:x1] = True
            d = d & m
        ys, xs = np.nonzero(d)
        if len(xs) < 5:
            return None
        return (int(xs.min()), int(ys.min()))

    def find(self, template, thr=0.6, region=None):
        """현재 프레임에서 템플릿 매칭. 반환 dict{center,(x,y,w,h),score} 또는 None.
        region=(x,y,w,h) 지정 시 그 영역 안에서만 탐색."""
        frame = self.screenshot(3)
        th, tw = template.shape[:2]
        search = frame
        ox = oy = 0
        if region:
            rx, ry, rw, rh = region
            rx, ry = max(0, rx), max(0, ry)
            search = frame[ry:ry+rh, rx:rx+rw]
            ox, oy = rx, ry
            if search.shape[0] < th or search.shape[1] < tw:
                return None
        res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < thr:
            return None
        x, y = loc[0]+ox, loc[1]+oy
        return {"center": (x+tw//2, y+th//2), "box": (x, y, tw, th), "score": round(float(score), 3)}

    # ---------- 제어 ----------
    def home(self):
        """홈(0,0)으로 이동 후 원점 자동 보정."""
        self.rb.reset_mouse(); time.sleep(0.6)
        o = self._locate(expect=(48, 48), win=140)
        self.origin = o if o else (0, 0)
        self.cur = self.origin
        self.log(f"[engine] home origin = {self.origin}")

    def move_to(self, fx, fy, max_iter=90):
        x0, y0 = self.cur
        for _ in range(max_iter):
            dx, dy = fx - x0, fy - y0
            if abs(dx) <= 2 and abs(dy) <= 2:
                break
            sx = max(min(dx, 127), -127)
            sy = max(min(dy, 127), -127)
            self.rb.send_mouse_move(sx, sy, quiet=True)
            x0 += sx; y0 += sy
            time.sleep(0.04)
        self.cur = (x0, y0)
        return self.cur

    def click(self, fx=None, fy=None, button=LEFT, double=False, settle=0.5):
        if fx is not None:
            self.move_to(fx, fy)
        n = 2 if double else 1
        for _ in range(n):
            self.rb.send_mouse_move(0, 0, buttons=button, quiet=True); time.sleep(0.06)
            self.rb.send_mouse_move(0, 0, buttons=0, quiet=True); time.sleep(0.06)
        time.sleep(settle)
        return self.cur

    def dismiss(self, spot=(1650, 760)):
        """빈 바탕화면을 클릭해 열려있는 메뉴/팝업을 닫는다(마우스 기반, 키보드보다 안정)."""
        self.click(spot[0], spot[1], settle=0.4)

    def key_tap(self, scancode, modifiers=0x00):
        self.rb.send_key(scancode=scancode, modifiers=modifiers, is_release=False)
        time.sleep(0.05)
        self.rb.send_key(scancode=scancode, modifiers=modifiers, is_release=True)
        time.sleep(0.2)
