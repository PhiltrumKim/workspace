# -*- coding: utf-8 -*-
"""가상 분석 장비 SW (시뮬레이터용 대상 화면).

페이지: RECIPE(레시피 선택) / RUN(LOT ID 입력, START, 상태) / LOG
이벤트: 레시피 미선택 START → 알람 팝업, trigger_alarm() 으로 임의 알람 발생.
widgets() 는 현재 화면에 보이는 GUI 요소의 박스를 돌려준다(템플릿 추출·테스트 정답용).
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]
FONT = cv2.FONT_HERSHEY_SIMPLEX

BG = (48, 45, 45)
PANEL = (64, 60, 58)
BTN = (110, 90, 70)
BTN_ACTIVE = (200, 140, 40)
WHITE = (240, 240, 240)

NAV: Dict[str, Tuple[Box, str]] = {
    "nav_recipe": ((20, 80, 240, 70), "RECIPE"),
    "nav_run": ((20, 170, 240, 70), "RUN"),
    "nav_log": ((20, 260, 240, 70), "LOG"),
}
RECIPES: List[Tuple[str, str]] = [
    ("rcp_a", "RCP_A   OXIDE THICKNESS"),
    ("rcp_b", "RCP_B   CD-SEM LINE WIDTH"),
    ("rcp_c", "RCP_C   PARTICLE COUNT"),
]
ROW_X, ROW_Y0, ROW_W, ROW_H, ROW_GAP = 320, 140, 700, 60, 80
LOT_LABEL: Box = (320, 140, 130, 60)
LOT_FIELD: Box = (460, 140, 400, 60)
START_BTN: Box = (320, 240, 200, 70)
STATUS: Box = (320, 350, 360, 56)
# LOG 화면: 시료 40개 중 10개만 보이는 목록(휠로 스크롤, 더블클릭=열기)과 드롭 상자(끌어다 놓기)
SAMPLES = [f"SAMPLE-{i:02d}" for i in range(1, 41)]
LIST_BOX: Box = (320, 100, 520, 600)
LIST_ROW_H, LIST_VISIBLE = 60, 10
DROP_BOX: Box = (1000, 300, 400, 200)
ALARM: Box = (660, 390, 600, 300)
ALARM_TITLE: Box = (660, 390, 600, 56)
ALARM_OK: Box = (860, 600, 200, 60)

_VK_SHIFTED = {0x30: ")", 0x31: "!", 0x32: "@", 0x33: "#", 0x34: "$", 0x35: "%", 0x36: "^", 0x37: "&",
               0x38: "*", 0x39: "(", 0xBD: "_"}


def _inside(box: Box, x: int, y: int) -> bool:
    bx, by, bw, bh = box
    return bx <= x < bx + bw and by <= y < by + bh


def _button(img, box: Box, text: str, color, scale=0.9):
    x, y, w, h = box
    cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), color, -1)
    cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), WHITE, 1)
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, 2)
    cv2.putText(img, text, (x + (w - tw) // 2, y + (h + th) // 2), FONT, scale, WHITE, 2, cv2.LINE_AA)


class DemoEquipmentApp:
    def __init__(self, width: int = 1920, height: int = 1080, run_duration: float = 1.0):
        self.w, self.h = width, height
        self.run_duration = run_duration
        self.page = "recipe"
        self.selected: Optional[str] = None
        self.lot = ""
        self.lot_focus = False
        self.run_state = "idle"
        self.run_t0 = 0.0
        self.scroll = 0                      # LOG 목록 첫 줄 번호
        self._last_click = (0.0, None)
        self.dropped: List[str] = []
        self.alarm: Optional[str] = None
        self.shift = False
        self.events: List[str] = []
        self._scheduled: List[Tuple[float, str]] = []   # (발생 시각, 메시지) — 실행 중 알람 재현용

    # ------------------------------------------------------------ 상태
    def schedule_alarm(self, delay: float, msg: str):
        """delay 초 뒤 알람 팝업 발생 (감시 기능 테스트용)."""
        self._scheduled.append((time.monotonic() + delay, msg))

    def _tick(self):
        now = time.monotonic()
        for item in [x for x in self._scheduled if x[0] <= now]:
            self._scheduled.remove(item)
            self.trigger_alarm(item[1])
        if self.run_state == "running" and time.monotonic() - self.run_t0 >= self.run_duration:
            self.run_state = "done"
            self.events.append(f"DONE {self.selected} lot={self.lot}")

    def trigger_alarm(self, msg: str):
        self.alarm = msg
        self.events.append(f"ALARM {msg}")

    def widgets(self) -> Dict[str, Box]:
        self._tick()
        out = {k: b for k, (b, _) in NAV.items()}
        if self.page == "recipe":
            for i, (name, _) in enumerate(RECIPES):
                out[name] = (ROW_X, ROW_Y0 + i * ROW_GAP, ROW_W, ROW_H)
        elif self.page == "run":
            out["lot_label"] = LOT_LABEL
            out["lot_field"] = LOT_FIELD
            out["start_btn"] = START_BTN
            out[f"status_{self.run_state}"] = STATUS
        elif self.page == "log":
            for i, name in enumerate(self.visible_samples()):
                out[name] = (LIST_BOX[0], LIST_BOX[1] + i * LIST_ROW_H, LIST_BOX[2], LIST_ROW_H)
            out["drop_box"] = DROP_BOX
        if self.alarm:
            out = {"alarm_title": ALARM_TITLE, "alarm_ok": ALARM_OK}
        return out

    def visible_samples(self) -> List[str]:
        return SAMPLES[self.scroll:self.scroll + LIST_VISIBLE]

    def _sample_at(self, x: int, y: int) -> Optional[str]:
        if self.page != "log" or not _inside(LIST_BOX, x, y):
            return None
        i = (y - LIST_BOX[1]) // LIST_ROW_H
        vis = self.visible_samples()
        return vis[i] if 0 <= i < len(vis) else None

    def wheel(self, x: int, y: int, notch: int):
        """휠 한 칸 = 3줄 (Windows 기본). +1 위로."""
        if self.alarm or self.page != "log" or not _inside(LIST_BOX, x, y):
            return
        self.scroll = max(0, min(len(SAMPLES) - LIST_VISIBLE, self.scroll - 3 * notch))
        self.events.append(f"SCROLL {self.scroll}")

    def drop(self, x0: int, y0: int, x1: int, y1: int):
        name = self._sample_at(x0, y0)
        if name and not self.alarm and _inside(DROP_BOX, x1, y1):
            self.dropped.append(name)
            self.events.append(f"DROP {name}")

    # ------------------------------------------------------------ 입력
    def click(self, x: int, y: int, button: int = 1):
        self._tick()
        if button != 1:
            return
        if self.alarm:                       # 모달: OK 외 클릭 무시
            if _inside(ALARM_OK, x, y):
                self.events.append(f"ACK {self.alarm}")
                self.alarm = None
            return
        for name, (box, _) in NAV.items():
            if _inside(box, x, y):
                self.page = name[4:]
                self.lot_focus = False
                return
        if self.page == "log":
            s = self._sample_at(x, y)
            now = time.monotonic()
            if s and self._last_click[1] == s and now - self._last_click[0] < 0.6:
                self.events.append(f"OPEN {s}")
                self._last_click = (0.0, None)
            else:
                self._last_click = (now, s)
            return
        if self.page == "recipe":
            for i, (name, _) in enumerate(RECIPES):
                if _inside((ROW_X, ROW_Y0 + i * ROW_GAP, ROW_W, ROW_H), x, y):
                    self.selected = name
                    self.events.append(f"SELECT {name}")
        elif self.page == "run":
            self.lot_focus = _inside(LOT_FIELD, x, y)
            if _inside(START_BTN, x, y) and self.run_state != "running":
                if not self.selected:
                    self.trigger_alarm("NO RECIPE SELECTED")
                else:
                    self.run_state, self.run_t0 = "running", time.monotonic()
                    self.events.append(f"START {self.selected} lot={self.lot}")

    def key(self, vk: int, scan: int, extended: bool, up: bool, modifiers: int = 0):
        if vk == 0x10:
            self.shift = not up
            return
        if up or not (self.page == "run" and self.lot_focus and not self.alarm):
            return
        shift = self.shift or bool(modifiers & 0x22)
        if vk == 0x08:
            self.lot = self.lot[:-1]
        elif vk == 0x0D:
            self.lot_focus = False
        elif 0x41 <= vk <= 0x5A:
            self.lot += chr(vk) if shift else chr(vk).lower()
        elif 0x30 <= vk <= 0x39:
            self.lot += _VK_SHIFTED[vk] if shift else chr(vk)
        elif vk == 0xBD:
            self.lot += "_" if shift else "-"

    # ------------------------------------------------------------ 렌더링
    def render(self) -> np.ndarray:
        self._tick()
        img = np.full((self.h, self.w, 3), BG, np.uint8)
        cv2.rectangle(img, (0, 0), (self.w, 50), (90, 60, 30), -1)
        cv2.putText(img, "GHOST DemoTool - Analyzer Console v1.0", (16, 34), FONT, 0.9, WHITE, 2, cv2.LINE_AA)
        for name, (box, text) in NAV.items():
            _button(img, box, text, BTN)
            if self.page == name[4:]:   # 활성 표시는 버튼 박스 밖(템플릿이 페이지와 무관하게 일치하도록)
                x, y, w, h = box
                cv2.rectangle(img, (x - 14, y), (x - 6, y + h - 1), BTN_ACTIVE, -1)
        cv2.rectangle(img, (300, 70), (self.w - 30, self.h - 30), PANEL, -1)

        if self.page == "recipe":
            for i, (name, text) in enumerate(RECIPES):
                y = ROW_Y0 + i * ROW_GAP
                sel = self.selected == name
                cv2.rectangle(img, (ROW_X, y), (ROW_X + ROW_W - 1, y + ROW_H - 1),
                              (150, 110, 40) if sel else (85, 80, 78), -1)
                cv2.putText(img, text, (ROW_X + 20, y + 40), FONT, 0.9, WHITE, 2, cv2.LINE_AA)
        elif self.page == "run":
            x, y, w, h = LOT_LABEL
            cv2.putText(img, "LOT ID", (x + 4, y + 40), FONT, 0.9, WHITE, 2, cv2.LINE_AA)
            fx, fy, fw, fh = LOT_FIELD
            cv2.rectangle(img, (fx, fy), (fx + fw - 1, fy + fh - 1), (250, 250, 250), -1)
            cv2.rectangle(img, (fx, fy), (fx + fw - 1, fy + fh - 1),
                          BTN_ACTIVE if self.lot_focus else (120, 120, 120), 2)
            cv2.putText(img, self.lot, (fx + 12, fy + 40), FONT, 0.9, (20, 20, 20), 2, cv2.LINE_AA)
            _button(img, START_BTN, "START", (60, 150, 60))
            color = {"idle": (110, 110, 110), "running": (0, 140, 230), "done": (60, 170, 60)}[self.run_state]
            _button(img, STATUS, f"STATUS: {self.run_state.upper()}", color, 0.8)
            cv2.putText(img, f"RECIPE: {(self.selected or '-').upper()}", (560, 290), FONT, 0.8, WHITE, 2,
                        cv2.LINE_AA)
        else:
            lx, ly, lw, lh = LIST_BOX
            cv2.rectangle(img, (lx, ly), (lx + lw - 1, ly + lh - 1), (85, 80, 78), -1)
            for i, name in enumerate(self.visible_samples()):
                y = ly + i * LIST_ROW_H
                cv2.line(img, (lx, y), (lx + lw - 1, y), (60, 58, 56), 1)
                cv2.putText(img, name, (lx + 20, y + 42), FONT, 0.9, WHITE, 2, cv2.LINE_AA)
            # 스크롤 막대
            frac = self.scroll / max(1, len(SAMPLES) - LIST_VISIBLE)
            cv2.rectangle(img, (lx + lw - 14, ly + int(frac * (lh - 120))), (lx + lw - 4, ly + int(frac * (lh - 120)) + 120),
                          (160, 160, 160), -1)
            dx, dy, dw, dh = DROP_BOX
            cv2.rectangle(img, (dx, dy), (dx + dw - 1, dy + dh - 1), (70, 110, 70), -1)
            cv2.putText(img, "DROP HERE", (dx + 110, dy + 90), FONT, 0.9, WHITE, 2, cv2.LINE_AA)
            for i, name in enumerate(self.dropped[-3:]):
                cv2.putText(img, name, (dx + 120, dy + 130 + i * 24), FONT, 0.6, WHITE, 1, cv2.LINE_AA)

        if self.alarm:
            x, y, w, h = ALARM
            cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), (235, 235, 235), -1)
            _button(img, ALARM_TITLE, "ALARM", (40, 40, 210))
            cv2.putText(img, self.alarm, (x + 30, y + 140), FONT, 0.9, (30, 30, 30), 2, cv2.LINE_AA)
            _button(img, ALARM_OK, "OK", BTN)
        return img
