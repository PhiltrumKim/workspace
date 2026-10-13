# -*- coding: utf-8 -*-
"""Device: 영상(VideoSource) + 입력(HidOutput)을 묶어 '화면 좌표로 조작'하는 계층.

RelayBoard 는 상대 이동만 지원하므로 다음 방식으로 절대 좌표를 만든다.
  1) home(): 좌상단으로 밀어붙인 뒤 커서 위치를 영상으로 실측 → 원점
  2) move_to(): 추정 이득(gain, 프레임px/mickey)으로 이동량을 계산해 이동
  3) 이동 후 커서를 실측하고(locate) 잔여 오차를 보정 (폐루프). 실측값으로 gain 도 갱신.
커서 실측은 작은 흔들기(jiggle) 전후 프레임 차분으로 커서 끝점을 찾는다.

대상 PC 가 Windows 이면 '포인터 정확도 향상'(마우스 가속)을 끄는 것을 권장한다.
켜져 있어도 폐루프 보정으로 수렴하지만 보정 횟수가 늘어난다.

적응형 확인(verify_moves="adaptive", 기본): 실측 1회는 ~0.9s 로 클릭마다 하면 비싸다.
보정 없이 허용오차 안에 도착한 이동이 trust_after 번 연속되면 이후 이동은 실측을 건너뛴다.
단, verify_every 번마다 한 번, 화면 가장자리(edge_margin) 근처, 원점 재설정·스텝 실패(distrust) 후에는 다시 실측한다.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

from .hal import keymap
from .hal.base import LEFT, DeviceError, HidOutput, VideoSource  # noqa: F401  (DeviceError 재노출)

Point = Tuple[int, int]


def _accepts_timeout(video) -> bool:
    import inspect
    try:
        return "timeout" in inspect.signature(video.read).parameters
    except (TypeError, ValueError):
        return False


class Device:
    def __init__(self, video: VideoSource, hid: HidOutput, cfg: dict,
                 log: Optional[Callable[[str], None]] = None):
        self.video = video
        self.hid = hid
        self.cfg = cfg
        self.c = cfg["cursor"]
        self.t = cfg["timing"]
        self.log = log or (lambda msg: None)
        self.pos: Point = (0, 0)          # 커서 위치(프레임 좌표). measured=False 면 추정값
        self.measured = False
        self.origin: Optional[Point] = None
        self.gain = [1.0, 1.0]            # 프레임 px / mickey (x, y)
        self._mods = 0
        self._streak = 0                  # 보정 없이 허용오차 안에 도착한 연속 횟수
        self._unverified = 0              # 마지막 실측 이후 실측 없이 한 이동 수
        self.stats = {"moves": 0, "verified": 0, "skipped": 0, "corrections": 0, "locate_fail": 0}

    # ------------------------------------------------------------ 수명주기
    def open(self, home: bool = True) -> None:
        self.hid.open()
        self.video.open()
        self.wake()
        if home:
            self.home()

    def close(self) -> None:
        try:
            self.release_all_keys()
        except Exception:
            pass
        try:
            self.video.close()
        finally:
            self.hid.close()

    def reconnect(self, home: bool = True) -> None:
        """장치를 닫고 다시 연다 (영상 끊김·시리얼 오류 복구). 실패하면 DeviceError."""
        self.log("[device] 장치 재연결 시도")
        for close in (self.video.close, self.hid.close):
            try:
                close()
            except Exception:
                pass
        self._mods = 0
        time.sleep(0.5)
        try:
            self.hid.open()
            self.video.open()
        except DeviceError:
            raise
        except Exception as e:
            raise DeviceError(f"장치 재연결 실패: {e!r}")
        self.frame()                                # 영상이 실제로 들어오는지 확인
        self._mods = sum(keymap.MODIFIER_BITS.values())   # 끊길 때 눌려 있던 수식키가 대상 PC 에 남았을 수 있음 → 모두 해제
        self.release_all_keys()
        if home:
            self.home()
        self.stats["reconnects"] = self.stats.get("reconnects", 0) + 1
        self.log("[device] 장치 재연결 완료")

    # ------------------------------------------------------------ 영상
    def frame(self) -> np.ndarray:
        f = self.video.read()
        if f is None:                               # 캡처가 순간 멈춘 경우(실장비 밤샘 시험에서 확인) 한 번 더 길게 기다림
            self.stats["frame_retries"] = self.stats.get("frame_retries", 0) + 1
            f = self.video.read(timeout=3.0) if _accepts_timeout(self.video) else self.video.read()
        if f is None:
            raise DeviceError("no video frame")
        return f

    # ------------------------------------------------------------ 저수준 마우스
    def _send(self, dx: int, dy: int, buttons: int = 0) -> None:
        self.hid.mouse_move(int(dx), int(dy), buttons)
        if self.t["move_step"]:
            time.sleep(self.t["move_step"])

    def _push(self, mx: int, my: int, buttons: int = 0, step: Optional[int] = None) -> None:
        """mickey 단위 상대 이동을 max_step 단위로 쪼개 전송. buttons: 누른 채 이동(드래그)."""
        step = step or self.hid.max_step
        while mx or my:
            sx = max(-step, min(step, mx))
            sy = max(-step, min(step, my))
            self._send(sx, sy, buttons)
            mx -= sx
            my -= sy

    def _move_by(self, dx: float, dy: float) -> Tuple[int, int]:
        mx = int(round(dx / self.gain[0]))
        my = int(round(dy / self.gain[1]))
        self._push(mx, my)
        return mx, my

    def wake(self) -> None:
        """화면보호기/절전 해제용 좌우 흔들기."""
        for _ in range(4):
            self._send(40, 0)
            time.sleep(0.05)
            self._send(-40, 0)
            time.sleep(0.05)

    # ------------------------------------------------------------ 커서 실측
    def locate(self, near: Optional[Point] = None, win: Optional[int] = None,
               corner: bool = False) -> Optional[Point]:
        """흔들기 전후 프레임 차분으로 커서 끝점(좌상단)을 측정. 실패 시 None.

        near 주변 ±win 안에서 찾는다. win <= 0 이면 전체 화면에서 near 에 가장 가까운 변화를 고른다.

        +J 방향 흔들기에서 차분 영역의 좌상단 = 원래 커서 끝점.
        화면 우하단 가장자리 등에서 +J 가 막히면 -J 방향으로 재시도.
        corner=True (홈잉 직후): 커서가 화면 구석에 있으므로 모든 변화 중 가장 좌상단 점을 커서 끝으로 본다.
          구석의 아이콘 호버 하이라이트가 커서 흔적과 붙어 큰 덩어리가 되는 경우(Windows 바탕화면)에 대응.
        """
        J = self.c["jiggle"]
        win = win or self.c["locate_window"]
        settle = self.t["jiggle_settle"]
        time.sleep(self.t["capture_latency"])   # 직전 이동이 영상에 반영된 뒤 기준 프레임 확보
        for sgn in (1, -1):
            if sgn < 0:
                time.sleep(settle)                  # 되돌린 흔들기가 영상에 반영된 뒤 재시도
            a = self.frame()
            self._send(sgn * J, sgn * J)
            time.sleep(settle)
            b = self.frame()
            self._send(-sgn * J, -sgn * J)          # 되돌린 뒤에는 프레임을 안 쓰므로 기다리지 않는다
            box = self._diff_blob(a, b, near, win, corner)
            if box is None:
                continue
            x0, y0 = box
            if sgn > 0:
                return (x0, y0)
            return (int(round(x0 + J * self.gain[0])), int(round(y0 + J * self.gain[1])))
        self.stats["locate_fail"] += 1
        return None

    def _diff_blob(self, a: np.ndarray, b: np.ndarray, near: Optional[Point], win: int,
                   corner: bool = False) -> Optional[Point]:
        d = np.abs(a.astype(np.int16) - b.astype(np.int16)).sum(axis=2) > self.c["diff_threshold"]
        if near is not None and win > 0:
            m = np.zeros_like(d)
            nx, ny = near
            m[max(0, ny - win):ny + win, max(0, nx - win):nx + win] = True
            d &= m
        n, _, stats, _ = cv2.connectedComponentsWithStats(d.astype(np.uint8), connectivity=8)
        # 커서 흔적은 하나의 덩어리. 툴팁/호버 효과 등 다른 변화가 있으면 near 에 가장 가까운 덩어리 선택
        if corner:
            blobs = [stats[i] for i in range(1, n) if stats[i][cv2.CC_STAT_AREA] >= 5]
            if not blobs:
                return None
            return (int(min(s[cv2.CC_STAT_LEFT] for s in blobs)), int(min(s[cv2.CC_STAT_TOP] for s in blobs)))
        big = self.c["max_blob"]
        cands = [stats[i] for i in range(1, n)
                 if stats[i][cv2.CC_STAT_AREA] >= 5
                 and stats[i][cv2.CC_STAT_WIDTH] <= big and stats[i][cv2.CC_STAT_HEIGHT] <= big]
        if not cands:
            return None
        if near is not None:
            cands.sort(key=lambda s: (s[0] - near[0]) ** 2 + (s[1] - near[1]) ** 2)
        else:
            cands.sort(key=lambda s: -s[cv2.CC_STAT_AREA])
        s = cands[0]
        return (int(s[cv2.CC_STAT_LEFT]), int(s[cv2.CC_STAT_TOP]))

    def home(self) -> Point:
        step = self.hid.max_step
        for _ in range(self.c["home_pushes"]):
            self._send(-step, -step)
        time.sleep(self.t["jiggle_settle"])
        expect = tuple(self.c["home_expect"])
        p = self.locate(near=expect, win=self.c["home_search"], corner=True)
        if p is None:
            self.log(f"[device] home: 커서 실측 실패, 예상값 {expect} 사용")
            self.pos, self.measured = expect, False
        else:
            self.pos, self.measured = p, True
        self.origin = self.pos
        self.distrust()
        self.log(f"[device] home origin = {self.origin}")
        return self.pos

    def distrust(self) -> None:
        """다음 이동부터 다시 실측하게 한다 (스텝 실패, 원점 재설정 후)."""
        self._streak = 0

    def _need_verify(self, target: Point) -> bool:
        policy = self.c["verify_moves"]
        if policy is True or policy == "always":
            return True
        if policy is False or policy == "never":
            return False
        if self._streak < self.c["trust_after"] or self._unverified >= self.c["verify_every"] - 1:
            return True
        w, h = self.video.size
        m = self.c["edge_margin"]                   # 가장자리: 커서가 화면 끝에 막혀 누적 오차가 생길 수 있음
        return not (m <= target[0] < w - m and m <= target[1] < h - m)

    # ------------------------------------------------------------ 고수준 마우스
    def _learn_gain(self, start: Point, end: Point, mx: int, my: int) -> None:
        for axis, m in ((0, mx), (1, my)):
            if abs(m) >= 20:
                r = (end[axis] - start[axis]) / m
                if 0.2 < r < 5.0:
                    self.gain[axis] = 0.5 * self.gain[axis] + 0.5 * r

    def move_to(self, x: int, y: int, verify: Optional[bool] = None) -> Point:
        target = (int(x), int(y))
        verify = self._need_verify(target) if verify is None else verify
        start, start_measured = self.pos, self.measured
        dist = max(abs(target[0] - start[0]), abs(target[1] - start[1]))
        mx, my = self._move_by(target[0] - start[0], target[1] - start[1])
        self.pos, self.measured = target, False
        self.stats["moves"] += 1
        if not verify:
            self._unverified += 1
            self.stats["skipped"] += 1
            return self.pos
        self._unverified = 0
        self.stats["verified"] += 1
        tol = self.c["tolerance"]
        for i in range(self.c["max_corrections"] + 1):
            win = max(self.c["locate_window"], int(dist * 0.3) + 20)
            p = self.locate(near=target, win=win)
            if p is None:                         # 예상보다 크게 빗나간 경우: 전체 화면 탐색
                p = self.locate(near=target, win=-1)
            if p is None:
                self.log(f"[device] move_to{target}: 커서 실측 실패 (추정 위치 유지)")
                self._streak = 0
                return self.pos
            if start_measured:
                self._learn_gain(start, p, mx, my)
            self.pos, self.measured = p, True
            ex, ey = target[0] - p[0], target[1] - p[1]
            if i == 0:                                # 계산만으로 도착했는지 → 신뢰도 갱신
                self._streak = self._streak + 1 if abs(ex) <= tol and abs(ey) <= tol else 0
            if abs(ex) <= tol and abs(ey) <= tol:
                return p
            if i == self.c["max_corrections"]:
                break
            self.stats["corrections"] += 1
            start, start_measured, dist = p, True, max(abs(ex), abs(ey))
            mx, my = self._move_by(ex, ey)
            self.pos, self.measured = target, False
        self.log(f"[device] move_to{target}: 허용오차 미달, 최종 {self.pos}")
        return self.pos

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: int = LEFT,
              double: bool = False) -> Point:
        if x is not None and y is not None:
            self.move_to(x, y)
        for _ in range(2 if double else 1):
            self._send(0, 0, button)
            time.sleep(self.t["click_hold"])
            self._send(0, 0, 0)
            time.sleep(self.t["click_hold"])
        time.sleep(self.t["click_settle"])
        return self.pos

    # ------------------------------------------------------------ 휠·드래그
    def scroll(self, notches: int, x: Optional[int] = None, y: Optional[int] = None) -> Point:
        """휠 notches 칸 (+위, -아래). x,y 를 주면 그 위치로 커서를 옮긴 뒤 굴린다 (휠은 커서 아래 창에 감)."""
        if x is not None and y is not None:
            self.move_to(x, y)
        for _ in range(abs(int(notches))):
            self.hid.mouse_wheel(1 if notches > 0 else -1)
            time.sleep(self.t["wheel_gap"])
        time.sleep(self.t["click_settle"])
        return self.pos

    def drag(self, x0: int, y0: int, x1: int, y1: int, button: int = LEFT) -> Point:
        """(x0,y0) 에서 눌러 (x1,y1) 에서 놓기. 누른 동안에는 커서 실측(흔들기)을 할 수 없으므로
        시작점을 확인해 맞춘 뒤 작은 걸음으로 이동하고, 놓은 뒤 위치를 다시 잰다."""
        self.move_to(x0, y0, verify=True)
        self._send(0, 0, button)
        time.sleep(self.t["drag_hold"])
        sx, sy = self.pos
        mx = int(round((x1 - sx) / self.gain[0]))
        my = int(round((y1 - sy) / self.gain[1]))
        n0 = 4 if abs(mx) + abs(my) > 8 else 1                 # 끌기 시작 인식 (Windows 드래그 문턱 ~4px)
        self._push(mx // n0, my // n0, button, step=8)
        time.sleep(self.t["drag_hold"])
        self._push(mx - mx // n0, my - my // n0, button, step=self.t["drag_step"])
        time.sleep(self.t["drag_hold"])
        self._send(0, 0, 0)
        time.sleep(self.t["click_settle"])
        self.pos, self.measured = (int(x1), int(y1)), False
        self.distrust()                                         # 다음 이동은 실측부터
        return self.pos

    # ------------------------------------------------------------ 키보드
    def key_down(self, name: str) -> None:
        n = keymap.normalize(name)
        k = keymap.key(n)
        self._mods |= keymap.MODIFIER_BITS.get(n, 0)
        self.hid.key(k.vk, k.scan, k.extended, up=False, modifiers=self._mods)
        time.sleep(self.t["key_hold"])

    def key_up(self, name: str) -> None:
        n = keymap.normalize(name)
        k = keymap.key(n)
        self._mods &= ~keymap.MODIFIER_BITS.get(n, 0)
        self.hid.key(k.vk, k.scan, k.extended, up=True, modifiers=self._mods)
        time.sleep(self.t["key_gap"])

    def press(self, name: str) -> None:
        self.key_down(name)
        self.key_up(name)

    def hotkey(self, *names: str) -> None:
        for n in names:
            self.key_down(n)
        for n in reversed(names):
            self.key_up(n)

    def type_text(self, text: str) -> None:
        """글자 입력. 한글은 대상 입력기를 한글 모드로 바꿔 두벌식 자판 순서로 치고 영문 모드로 되돌린다."""
        from .hal import hangul
        segs = hangul.segments(text) if any(hangul.is_hangul(c) for c in text) else [("en", text)]
        plans = [(mode, [keymap.char_to_key(ch) for ch in keys]) for mode, keys in segs]   # 입력 전에 전체 검증
        kb = self.cfg.get("keyboard", {})
        toggle, wait = kb.get("hangul_toggle", "ralt"), kb.get("toggle_wait", 0.15)
        mode = "en"
        for want, plan in plans:
            if want != mode:
                self.press(toggle)
                time.sleep(wait)
                mode = want
            for name, shift in plan:
                if shift:
                    self.hotkey("shift", name)
                else:
                    self.press(name)
        if mode != "en":
            self.press(toggle)
            time.sleep(wait)

    def release_all_keys(self) -> None:
        """눌린 채 남은 수식키 해제 (C++ 키클리어와 같은 목적)."""
        for n, bit in keymap.MODIFIER_BITS.items():
            if self._mods & bit:
                self.key_up(n)
