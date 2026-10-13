# -*- coding: utf-8 -*-
"""OCR: 화면 글자 인식 (RapidOCR / PP-OCR ONNX).

엔진: rapidocr-onnxruntime (검출 + 인식). 기본 인식 모델은 중국어+영어라 한글을 못 읽으므로
한국어 인식 모델(PaddlePaddle korean_PP-OCRv5_mobile_rec, Apache-2.0)을 `python -m ghost fetch-models` 로 받아 쓴다.
ONNX 모델이라 TX 엣지 장비(C++ onnxruntime)로 이식할 수 있다.

속도(1080p, CPU): 잘라낸 영역 0.1~0.7s, 전체 화면 ~2.6s → region 을 지정해서 쓰는 것이 기본.
RapidOCR 기본 검출 설정(limit_type=min, 736)은 작은 영역을 짧은 변 736px 까지 확대해서 검출이 느리다
(메뉴 영역 812ms 중 검출 626ms). 긴 변 기준(max)으로 바꾸고 각도 분류(cls)를 끄면 80ms (정확도 동일).
작은 글씨는 scale(확대 배율)을 2 정도로 주면 인식률이 오른다.

한 줄 모드(line): 버튼·수치 표시창처럼 글자 한 줄만 있는 좁은 영역은 검출 단계를 건너뛰고 영역 전체를
바로 인식한다. 검출 단계가 버튼 포커스 테두리 등을 포함해 잘못 잘라내는 문제를 피한다
(실장비 Win7 '확인' 버튼: 검출+인식 '교후' 0.83 → 한 줄 모드 '확인' 0.99).
line=None 이면 region 높이가 LINE_AUTO_MAX_H 이하일 때 자동으로 한 줄 모드.
"""
from __future__ import annotations

import difflib
import os
import re
import threading
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]
MODES = {"exact", "contains", "regex", "fuzzy"}

KOREAN_MODEL_REPO = "PaddlePaddle/korean_PP-OCRv5_mobile_rec_onnx"
KOREAN_MODEL_DIR = "models/korean_PP-OCRv5_mobile_rec"
LINE_AUTO_MAX_H = 40
LINE_TARGET_H = 40          # 한 줄 모드 기본 배율 기준 글자 높이(px) — 인식 모델 입력 높이 48 근처
# 다수결 판독: 글자 높이가 아래 값(px)이 되도록 배율을 바꿔 한 줄 모드로 여러 번 읽는다.
# 세그먼트 숫자처럼 0/8 을 오가는 글꼴에서 오인식을 줄인다
# (실장비 XNote 표시창: 단일 판독은 배율에 따라 0↔8 오인식, 다수결은 정답)
VOTE_TARGET_H = (32, 36, 42, 48, 64, 128)
_ENGINES: dict = {}


@dataclass
class TextHit:
    text: str
    box: Box
    conf: float
    parts: Optional[list] = None        # group_lines 로 묶은 줄이면 구성 단어들 (왼→오른쪽)

    @property
    def center(self) -> Tuple[int, int]:
        x, y, w, h = self.box
        return (x + w // 2, y + h // 2)


# OCR 이 자주 헷갈리는 글자: 비교할 때 양쪽을 같은 글자로 바꾼다 (GTB-3000 트리 'Tool-B2' → 'T001-B2' 로 읽음)
_CONFUSABLE = str.maketrans({"o": "0", "l": "1", "|": "1"})


def normalize(s: str) -> str:
    """비교용 정규화: 공백 제거, 대소문자 무시, 대시/콜론 변형 통일."""
    s = s.casefold()
    for a, b in (("–", "-"), ("—", "-"), ("：", ":"), ("（", "("), ("）", ")")):
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def _fold(s: str) -> str:
    """찾기 비교용: normalize + OCR 혼동 글자(o↔0, l·I↔1) 통일. 길이는 그대로."""
    return normalize(s).translate(_CONFUSABLE)


def text_matches(text: str, query: str, mode: str = "contains", min_ratio: float = 0.9) -> bool:
    if mode == "regex":                       # OCR 이 넣는 공백(좁은 글자 '1' 앞 등)에 영향받지 않도록 공백 제거본도 비교
        return re.search(query, text) is not None or re.search(query, re.sub(r"\s+", "", text)) is not None
    t, q = _fold(text), _fold(query)
    if mode == "exact":
        return t == q
    if mode == "contains":
        return q in t
    # fuzzy: 전체 비교 또는 같은 길이 부분 문자열 중 최고 유사도
    if difflib.SequenceMatcher(None, t, q).ratio() >= min_ratio:
        return True
    n = len(q)
    return any(difflib.SequenceMatcher(None, t[i:i + n], q).ratio() >= min_ratio
               for i in range(0, max(1, len(t) - n + 1)))


class OcrEngine:
    def __init__(self, cfg: dict, base_dir: str = ".", log=None):
        self.cfg = cfg.get("ocr", {})
        self.base_dir = base_dir
        self.log = log or (lambda m: None)
        self._engine = None
        self._lock = threading.Lock()
        self.model = None

    def _load(self):
        from rapidocr_onnxruntime import RapidOCR
        rec = self.cfg.get("rec_model", KOREAN_MODEL_DIR)
        rec_dir = rec if os.path.isabs(rec) else os.path.join(self.base_dir, rec)
        onnx, keys = os.path.join(rec_dir, "inference.onnx"), os.path.join(rec_dir, "dict.txt")
        det = {"det_limit_type": self.cfg.get("det_limit_type", "max"),
               "det_limit_side_len": self.cfg.get("det_limit_side_len", 960)}
        if os.path.exists(onnx) and os.path.exists(keys):
            key = (os.path.abspath(onnx), det["det_limit_type"], det["det_limit_side_len"])
            if key not in _ENGINES:                 # 모델 로딩(~1s)은 프로세스당 한 번
                _ENGINES[key] = RapidOCR(rec_model_path=onnx, rec_keys_path=keys, **det)
            self._engine = _ENGINES[key]
            self.model = os.path.basename(rec_dir)
        else:
            self.log(f"[ocr] 한국어 인식 모델 없음({rec_dir}) → 기본 모델(중/영) 사용. "
                     "한글 인식은 'python -m ghost fetch-models' 후 가능")
            self._engine = RapidOCR(**det)
            self.model = "rapidocr-default"

    def read(self, frame: np.ndarray, region: Optional[Sequence[int]] = None,
             scale: Optional[float] = None, line: Optional[bool] = None) -> List[TextHit]:
        """frame(또는 region) 의 글자 목록. 좌표는 frame 기준으로 돌려준다. 위→아래, 왼→오른쪽 순."""
        with self._lock:
            if self._engine is None:
                self._load()
            ox = oy = 0
            img = frame
            if region is not None:
                x, y, w, h = (int(v) for v in region)
                x, y = max(0, x), max(0, y)
                img = frame[y:y + h, x:x + w]
                ox, oy = x, y
            if img.size == 0:
                return []
            if line is None:
                # 짧은 한 줄 영역만 (넓고 낮은 영역, 예: 메뉴 줄 전체를 한 줄로 읽으면 글자가 망가짐 — GTB-3000 Analysis → nalsig)
                line = region is not None and img.shape[0] <= LINE_AUTO_MAX_H and img.shape[1] <= 12 * img.shape[0]
            if line:
                (tx, ty, tw, th) = _ink_box(img)          # 영역 안 글자 부분만 (빈 공간이 많으면 인식률 저하)
                img = img[ty:ty + th, tx:tx + tw]
                ox, oy = ox + tx, oy + ty
                # 기본 배율: 글자 높이가 LINE_TARGET_H 가 되도록 (작은 글씨 확대 / 큰 표시창 축소)
                ink_h = max(4, _ink_box(img, pad=0)[3])
                s = float(scale or min(4.0, max(0.1, LINE_TARGET_H / ink_h)))
            else:
                s = float(scale or self.cfg.get("scale", 1.0))
            if s != 1.0:
                img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
            if line:
                result, _ = self._engine(img, use_det=False, use_cls=False)
            else:
                result, _ = self._engine(img, use_cls=False)   # UI 글자는 회전되지 않으므로 각도 분류 생략
        min_conf = self.cfg.get("min_conf", 0.5)
        if line:
            box = (ox, oy, int(img.shape[1] / s), int(img.shape[0] / s))
            return [TextHit(str(t), box, round(float(c), 3))
                    for t, c in (result or []) if t and float(c) >= min_conf]
        hits = []
        for pts, text, conf in result or []:
            if float(conf) < min_conf:
                continue
            xs = [p[0] / s for p in pts]
            ys = [p[1] / s for p in pts]
            x0, y0 = int(min(xs)) + ox, int(min(ys)) + oy
            hits.append(TextHit(text, (x0, y0, int(max(xs) - min(xs)), int(max(ys) - min(ys))), round(float(conf), 3)))
        hits.sort(key=lambda h: (h.box[1] // 10, h.box[0]))
        return hits

    def read_vote(self, frame: np.ndarray, region=None, variants=None) -> Tuple[str, float, List[str]]:
        """여러 설정으로 읽고 글자 위치별 다수결 (공백 제거). (결과, 일치도, 개별 판독들).
        일치도 = 위치별 최다 득표 수의 최솟값 / 전체 판독 수 (길이가 다른 판독은 반대표로 본다)."""
        from collections import Counter
        if variants is None:
            x, y, w, h = (int(v) for v in region) if region is not None else (0, 0, frame.shape[1], frame.shape[0])
            ink_h = max(4, _ink_box(frame[max(0, y):y + h, max(0, x):x + w], pad=0)[3])
            variants = [(True, min(4.0, max(0.1, t / ink_h))) for t in VOTE_TARGET_H]
        texts = []
        for line, sc in variants:
            hits = self.read(frame, region, sc, line)
            t = "".join(h.text for h in sorted(hits, key=lambda h: (h.center[1] // 12, h.box[0])))
            t = re.sub(r"\s+", "", t)              # 공백은 판독마다 달라 다수결을 방해 → 제거
            if t:
                texts.append(t)
        if not texts:
            return "", 0.0, []
        n = Counter(len(t) for t in texts).most_common(1)[0][0]
        same = [t for t in texts if len(t) == n]
        votes = [Counter(t[i] for t in same).most_common(1)[0] for i in range(n)]
        text = "".join(c for c, _ in votes)
        agree = min(k for _, k in votes) / len(texts) if votes else 0.0
        return text, round(agree, 2), texts

    def find_text(self, frame: np.ndarray, query: str, region=None, mode: str = "contains",
                  min_ratio: float = 0.9, scale=None, line=None, vote: bool = False) -> Optional[TextHit]:
        """개별 인식 결과와, 같은 줄 결과를 이어 붙인 문자열 모두에 대해 비교 (검출기는 단어별로 쪼갠다).
        vote=True: region 을 다수결 판독한 결과 하나로 비교 (세그먼트 숫자 표시창 등)."""
        if vote:
            text, agree, _ = self.read_vote(frame, region)
            if text and agree >= 0.5 and text_matches(text, query, mode, min_ratio):
                x, y, w, h = (int(v) for v in region) if region is not None else (0, 0, frame.shape[1], frame.shape[0])
                return TextHit(text, (x, y, w, h), agree)
            return None
        hits = self.read(frame, region, scale, line)
        for h in hits + group_lines(hits):
            if text_matches(h.text, query, mode, min_ratio):
                return narrow(h, query, mode, min_ratio)
        return None


def _span(text: str, query: str) -> Optional[Tuple[int, int]]:
    """text 안에서 query 가 차지하는 원문 글자 범위 (공백·대소문자 무시)."""
    keep = [(i, c) for i, c in enumerate(text) if not c.isspace()]
    flat = _fold("".join(c for _, c in keep))
    q = _fold(query)
    if not q or len(flat) != len(keep):
        return None
    k = flat.find(q)
    if k < 0:
        return None
    return keep[k][0], keep[k + len(q) - 1][0] + 1


def narrow(hit: TextHit, query: str, mode: str = "contains", min_ratio: float = 0.9) -> TextHit:
    """찾은 결과가 query 보다 넓으면(줄 전체, 여러 단어가 붙은 덩어리) query 부분으로 상자를 좁힌다.
    GTB-3000 측정: 탭 줄 'Recipe Run Monitor Results ...' 를 한 덩어리로 읽으면 가운데(엉뚱한 탭)를 눌렀음.
      1) 묶인 줄이면 query 를 담는 가장 짧은 연속 단어 묶음
      2) 한 덩어리 안에 다른 글자가 섞여 있으면 글자 위치 비율로 가로 범위를 좁힘"""
    if mode in ("exact", "regex") or _fold(hit.text) == _fold(query):
        return hit
    h = hit
    if hit.parts:
        best = None
        n = len(hit.parts)
        for i in range(n):
            for j in range(i, n):
                seg = hit.parts[i:j + 1]
                if text_matches(" ".join(p.text for p in seg), query, mode, min_ratio):
                    if best is None or (j - i) < (best[1] - best[0]):
                        best = (i, j)
                    break
        if best is not None:
            seg = hit.parts[best[0]:best[1] + 1]
            x0 = min(p.box[0] for p in seg)
            y0 = min(p.box[1] for p in seg)
            x1 = max(p.box[0] + p.box[2] for p in seg)
            y1 = max(p.box[1] + p.box[3] for p in seg)
            h = TextHit(" ".join(p.text for p in seg), (x0, y0, x1 - x0, y1 - y0), round(min(p.conf for p in seg), 3))
    sp = _span(h.text, query) if mode == "contains" else None
    if sp and (sp[1] - sp[0]) < len(h.text.strip()):
        x, y, w, hh = h.box
        n = max(1, len(h.text))
        a, b = x + int(w * sp[0] / n), x + int(w * sp[1] / n)
        h = TextHit(h.text[sp[0]:sp[1]], (a, y, max(1, b - a), hh), h.conf)
    return h


def join_text(hits: List[TextHit]) -> str:
    return " ".join(h.text for h in hits)


def group_lines(hits: List[TextHit]) -> List[TextHit]:
    """세로 중심이 비슷한 결과를 한 줄로 묶어 이어 붙인 TextHit 목록 (2개 이상인 줄만)."""
    lines: List[List[TextHit]] = []
    for h in sorted(hits, key=lambda h: h.center[1]):
        if lines and abs(lines[-1][-1].center[1] - h.center[1]) <= max(6, 0.6 * h.box[3]):
            lines[-1].append(h)
        else:
            lines.append([h])
    out = []
    for ln in lines:
        if len(ln) < 2:
            continue
        ln.sort(key=lambda h: h.box[0])
        x0 = min(h.box[0] for h in ln)
        y0 = min(h.box[1] for h in ln)
        x1 = max(h.box[0] + h.box[2] for h in ln)
        y1 = max(h.box[1] + h.box[3] for h in ln)
        out.append(TextHit(" ".join(h.text for h in ln), (x0, y0, x1 - x0, y1 - y0),
                           round(min(h.conf for h in ln), 3), parts=list(ln)))
    return out


def _ink_box(img: np.ndarray, pad: int = 6, diff: int = 40) -> Tuple[int, int, int, int]:
    """배경(테두리 픽셀 중앙값)과 다른 픽셀의 외접 사각형 + 여백. 없으면 전체.
    버튼 테두리·구분선처럼 행/열 대부분을 가로지르는 선은 글자가 아니므로 제외한다
    (포함하면 글자 높이를 크게 잡아 배율이 부족해진다: 'Remind me later' → 'Remin me later')."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    border = np.concatenate([g[0], g[-1], g[:, 0], g[:, -1]])
    mask = np.abs(g.astype(np.int16) - int(np.median(border))) > diff
    h, w = g.shape
    if h > 4 and w > 4:
        mask[mask.mean(axis=1) > 0.7, :] = False      # 가로선
        mask[:, mask.mean(axis=0) > 0.7] = False      # 세로선
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return (0, 0, w, h)
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(w, xs.max() + 1 + pad), min(h, ys.max() + 1 + pad)
    return (int(x0), int(y0), int(x1 - x0), int(y1 - y0))
