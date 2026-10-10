# GHOST — GUI-based Hands-free Operation & Surveillance Technology

설비 PC에 아무것도 설치하지 않고, **캡처 영상으로 화면을 인식**하고 **HID 신호(RelayBoard)로 조작**하는 GUI 자동화 엔진.
프로젝트 개요: `../doc/GHOST_프로젝트_개요_초안_v0.10.pptx` · 전신: `../magewell_rpa` (PoC)

## 구조

```
ghost/
  hal/            하드웨어 추상화
    base.py         VideoSource / HidOutput 인터페이스
    capture.py      Magewell 등 캡처카드 (OpenCV)
    relayboard.py   TX-RelayBoard 시리얼 프로토콜 (MiTx C++ 와 바이트 단위 일치)
    keymap.py       키 이름 → (Windows VK, PS/2 Set1 make code, 확장키)
  device.py       화면 좌표 조작: 홈잉, 커서 실측, 폐루프 이동, 클릭, 키보드/텍스트
  vision/         템플릿 매칭(영역 제한, 다중 배율, 색 검증) + OCR(ocr.py)
  locator.py      target 탐색 공용 계층 (템플릿/텍스트, 실행기·감시 공용)
  surveillance.py 감시 규칙(target/no_signal/frozen), 알림
  registry.py     GUI target 레지스트리 (objects/objects.json + PNG)
  scenario/       시나리오 형식 v1 (검증·레거시 변환) + 실행기 (재시도·사후조건·하위 호출·중지)
  blackbox.py     실행 기록 (runs/<시각>_<이름>/events.jsonl + 프레임)
  sim/            시뮬레이터: 가상 분석장비 SW + 가상 커서 (장비 없이 개발/테스트)
  cli.py          python -m ghost ...
scenarios/sim/    시뮬레이터 데모 시나리오
assets/sim_objects/  시뮬레이터용 템플릿 (python -m ghost sim-assets 로 재생성)
tests/            pytest (전부 시뮬레이터 기반, 장비 불필요)
```

## 빠른 시작

```bash
py -3.9 -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m ghost fetch-models                            # 한국어 OCR 모델 (최초 1회)
.venv/Scripts/python -m pytest -q                                     # 테스트
.venv/Scripts/python -m ghost run scenarios/sim/demo_run_recipe.json --sim
.venv/Scripts/python -m ghost run scenarios/sim/demo_alarm_recovery.json --sim
```

실장비 (Magewell + RelayBoard 연결 시):

```bash
python -m ghost probe                 # COM 포트 목록 + 캡처 확인
python -m ghost probe --smoke         # 홈잉 + 3점 이동 + 커서 실측 (클릭 없음)
python -m ghost snap shot.png         # 화면 저장
python -m ghost add-target ok_btn --image shot.png --box 860,600,200,60   # 템플릿 target 등록
python -m ghost ocr shot.png --region 900,500,300,100                     # 글자·좌표 확인 (텍스트 target / read 영역 잡기)
python -m ghost add-target ok_txt --text "확인" --box 973,583,90,28         # 텍스트(OCR) target 등록
python -m ghost run scenarios/my_job.json
```

실장비 예제: `scenarios/notepad_hello.json` (Win7 대상, target 은 `objects/`)
— Win+R → 메모장 실행 → 입력 → Alt+F4 → "저장 안 함" 클릭. 각 단계는 expect 로 화면 확인 (2026-10-10 4/4 성공).
대상 화면의 target 은 해상도·테마·창 위치에 의존하므로 대상 PC 가 바뀌면 다시 캡처해 등록한다.

설정은 `ghost.json` (COM 포트, 카메라 번호, 해상도, 경로). 기본값은 `ghost/config.py`.
`--sim` 실행 시에는 `ghost.json` 의 `"sim"` 섹션이 덧씌워진다.

## 시나리오 형식 (v1)

```json
{
  "ghost": 1,
  "name": "run_recipe",
  "description": "레시피 선택 후 분석 시작",
  "steps": [
    {"action": "click", "target": "nav_recipe"},
    {"action": "click", "target": "rcp_b", "retry": 1},
    {"action": "click", "target": "nav_run", "expect": {"visible": "start_btn", "timeout": 2}},
    {"action": "type", "text": "LOT-0001"},
    {"action": "hotkey", "keys": ["ctrl", "s"]},
    {"action": "wait_for", "target": "status_done", "timeout": 600},
    {"action": "call", "scenario": "ack_alarm"}
  ]
}
```

| action | 필드 | 설명 |
|---|---|---|
| click / double / right_click / move | target 또는 x,y | target 은 timeout(기본 3s) 동안 탐색, allow_hint 시 미검출이면 hint 좌표 |
| key / hotkey / type | key / keys / text | type 은 ASCII(US 배열)만 |
| wait | sec | |
| wait_for / wait_gone / expect | target, timeout | expect 는 즉시 확인 |
| screenshot | label | 블랙박스에 저장 |
| call | scenario | 하위 시나리오 (같은 scenarios 폴더) |
| home | | 커서 재홈잉 |

모든 스텝 공통: `label`, `retry`, `expect: {"visible"|"gone": target, "timeout": s}` (사후조건 — 실패 시 retry).
레거시 `magewell_rpa` workflow/recipe 는 자동 변환되어 읽힌다 (`python -m ghost migrate --legacy ../magewell_rpa --out legacy`).

## 감시 (Surveillance)

실행 중(스텝 사이, `wait`/`wait_for` 대기 중) 또는 단독(`python -m ghost watch rules.json`)으로 화면을 감시한다.
규칙 파일 `{"rules": [...]}` 또는 시나리오의 `"watch"` 에 정의한다. 예: `scenarios/watch_win_alert.json`.

| type | 탐지 | 필드 |
|---|---|---|
| target | 템플릿이 화면에 나타남 (알람·에러 팝업) | target, region? |
| no_signal | 영상 끊김 (화면 전체가 거의 단색) | max_std? |
| frozen | 영역 화면이 N초간 변하지 않음 (SW 멈춤) | region, seconds |

| action | 동작 |
|---|---|
| notify | 로그·블랙박스 기록, `notify.webhook` 설정 시 JSON POST (Teams/Slack 수신 웹훅 등) |
| stop | 즉시 중단, 화면 기록, 시나리오의 `on_abort` 안전 복귀 시나리오 실행 |
| handler | 처리 시나리오 실행 후 작업 계속. 해소되지 않으면 최대 5회 후 중단 |

이벤트는 상태가 바뀔 때만 나온다: appeared(발생) / cleared(해소).

**주의**: 팝업이 끼어들면 직전 클릭이 팝업에 막혀 유실될 수 있다. 실행기는 클릭했다는 것만 알고, 반영됐는지는 모른다.
결과가 중요한 스텝에는 반드시 `expect` 로 화면 확인을 넣어 재시도되게 한다 (`scenarios/sim/demo_run_watched.json`).

실장비 예제: `scenarios/hw_watch_demo.json` — 작업 중 Windows 경고 팝업(⚠) 발생 → 탐지 → `ack_win_alert` 로 확인 클릭 → 작업 계속 (3/3 성공).

## OCR (화면 글자 인식)

- 엔진: RapidOCR (PP-OCR ONNX)
- 한국어 인식 모델: PaddlePaddle `korean_PP-OCRv5_mobile_rec` (Apache-2.0)
  - `python -m ghost fetch-models` 로 `models/` 에 받는다 (git 제외).
  - 모델이 없으면 기본 모델(중국어·영어)로 동작하며, 이때는 한글을 읽지 못한다.
- ONNX 모델이라 TX 엣지 장비(C++ onnxruntime)로 옮길 수 있다.
- 비전·OCR 기반 인식은 PPT 의 특허 회피 방향(「RPA용 GUI 오브젝트 주소 생성」)과도 맞다.

**텍스트 target**: 템플릿 대신 글자로 찾는다. click, wait_for, expect, 감시 규칙 어디서나 쓸 수 있다.
```json
{"action": "click", "target": {"text": "Remind me later"}}
{"action": "click", "target": {"text": "Close", "match": "exact", "region": [1490, 690, 320, 180]}}
```
레지스트리에 이름으로 등록할 수도 있다: `add-target menu_close --text Close --match exact --box ...`

`match` 종류: `contains`(기본), `exact`, `regex`, `fuzzy`(유사도 0.9 이상)
- 메뉴 항목은 `exact` 로 찾는다. 포함 일치로 "Stop" 을 찾으면 "Stopwatch" 가, "Close" 를 찾으면 "Close All" 이 걸린다.

**read 액션**: 화면 글자·수치를 읽어 `values` 에 저장하고, 블랙박스에 판독값과 영역 이미지를 남긴다.
```json
{"action": "read", "name": "elapsed_s", "region": [1140, 20, 770, 240], "vote": true,
 "pattern": "^00:00:(\\d\\d\\.\\d\\d)$", "min": 5, "max": 20}
```
- `anchor` + `offset`: target 위치 기준 상대 영역에서 읽는다.
- `pattern`: 정규식으로 값만 뽑는다.
- `min` / `max`: 범위를 벗어나면 스텝 실패.

**실장비에서 얻은 OCR 운용 요령**

| 현상 | 대응 |
|---|---|
| 작은 영역 OCR 도 0.8s 로 느림 | RapidOCR 기본 검출 설정이 작은 영역을 짧은 변 736px 까지 확대해서 생기는 문제였다. 긴 변 기준(`det_limit_type: max`)으로 바꾸고 각도 분류를 꺼서 메뉴 영역 812 → 80~200ms (정확도 동일) |
| 전체 화면 OCR 은 ~2.6s | 항상 `region` 을 준다. 위치가 바뀌는 대화상자는 `anchor`(빠른 템플릿) + `offset` 으로 작은 영역만 OCR 한다 (팝업 버튼 2.6s → 0.1s) |
| 한 줄 모드에서 버튼 테두리를 글자로 잡아 배율 부족 ('Remind' → 'Remin') | 글자 영역을 잡을 때 행·열을 가로지르는 선은 제외 |
| 작은 버튼 글자를 검출 단계가 잘못 자름 ("확인" → "교후") | 한 줄 모드 `line`: 검출 없이 영역 전체를 인식 ("확인" 0.99). 높이 40px 이하 영역은 자동 적용 |
| 한 줄 모드는 빈 공간이 많거나 배율이 안 맞으면 틀림 | 글자 부분만 자동으로 잘라내고, 글자 높이 ~40px 이 되도록 배율 자동 조정 |
| 검출기가 "STATUS: DONE" 을 단어별로 쪼갬 | 같은 줄 결과를 이어 붙인 문자열로도 비교 |
| 세그먼트 숫자 표시창에서 0↔8 오인식 | `vote`: 배율 6가지로 읽고 글자 위치별 다수결. 일치도가 0.5 미만이면 실패 처리 |
| 좁은 글자 "1" 앞에 공백이 끼어 정규식 불일치 | 정규식은 공백을 제거한 문자열로도 비교 |
| 판독 영역 위의 커서나 메뉴가 판독을 오염 | 읽기 전에 커서를 치운다 (`move`). 메뉴가 덮으면 일치도가 떨어져 실패로 걸러진다 |

실장비 예제 `scenarios/xnote_measure.json` (XNote Stopwatch, 3/3 성공, 재시도 0):
1. Win+R 로 실행한다.
2. 평가판 팝업은 감시 핸들러가 OCR 로 "Remind me later" 를 찾아 처리한다.
3. 우클릭 메뉴 Start → 5초 → Stop (메뉴 항목은 OCR 완전 일치로 찾는다).
4. 경과 시간을 다수결로 판독하고 범위를 검사한다 (12.52 / 12.63 / 12.60 s, 일치도 1.0).
   - OCR 속도 개선 후: 11.02 / 10.89 / 11.01 s, 시나리오 전체 56.2 → 45.1 s.
   - 커서 적응형 확인 후: 08.45 / 09.06 / 08.17 s, 시나리오 전체 36.0 s (처음 56.2 s 대비 -36%).
5. Reset 후 `00:00:00.00` 을 확인하고 Close 로 종료한다.
- 실패하면 `on_abort` 로 프로그램을 닫는다.

## 템플릿 매칭과 색 검증

`TM_CCOEFF_NORMED` 는 밝기·색 평균을 빼고 비교한다. 그래서 **배경색만 다른 상태를 구분하지 못한다**.
예: 선택된 행과 선택되지 않은 행이 0.956 으로 매칭된다.

선택 표시, 상태 램프, 경고 아이콘처럼 색이 의미를 갖는 target 에는 `color_tol` 을 지정한다.
매칭 위치의 평균 색 차이가 이 값을 넘으면 불일치로 판정한다 (`add-target --color-tol 25`).

## 커서 제어 방식

RelayBoard 는 상대 이동만 지원한다. 그래서 다음 순서로 절대 좌표처럼 다룬다.

1. 커서를 좌상단으로 밀어붙인다 (홈잉).
2. 작은 흔들기 전후의 프레임 차분으로 실제 커서 위치를 측정한다. 캡처 오버스캔 오프셋도 이때 자동 반영된다.
3. 추정 이득(px/mickey)으로 이동량을 계산해 이동한다.
4. 이동 후 다시 실측해 잔여 오차를 보정하고, 실측값으로 이득을 갱신한다 (폐루프).

레거시는 2번 측정을 홈잉 때 한 번만 하고 이후에는 계산만 하는 개루프 방식이었다.

**적응형 확인** (`cursor.verify_moves: "adaptive"`, 기본): 실측 1회는 ~0.9s 라 클릭마다 하면 비싸다.
- 보정 없이 허용오차 안에 도착한 이동이 `trust_after`(3) 번 연속되면, 이후 이동은 실측을 건너뛴다.
- 다음 경우에는 다시 실측한다: `verify_every`(5) 번마다 한 번, 화면 가장자리(`edge_margin` 16px) 근처, 원점 재설정 후, 스텝 실패 후.
- `true` 는 항상 실측, `false` 는 실측하지 않는다.

**대기시간** (실장비 실측, 긴 이동 직후 12회씩):

| capture_latency / jiggle_settle | 실측 1회 | 최대 오차 |
|---|---|---|
| 0.30 / 0.35 s | 1.17 s | 0 px |
| **0.20 / 0.25 s (기본)** | 0.88 s | 0 px |
| 0.15 / 0.20 s | 0.79 s | 8 px (이전 프레임 오측정) |

실측 마지막의 되돌리기 대기도 없앴다. 되돌린 뒤의 프레임은 쓰지 않기 때문이다.
xnote_measure: 이동 11회 중 6~7회 실측 생략, 시나리오 45.0 → 36.0 s (3/3 성공).
Windows 대상은 **'포인터 정확도 향상'(마우스 가속)을 끄는 것을 권장**한다. 켜져 있어도 수렴하지만 보정 횟수가 늘어난다.

## 레거시 대비 수정 사항

- **키보드 패킷**: `#6`에 Windows VK, `#7` flag에 확장키 비트(bit1)를 채운다. C++ `TcpServer.cpp`와 동일하다.
  - 레거시는 VK=0으로 보냈고, USB HID 코드(ESC=0x29)와 PS/2 Set1 코드(ESC=0x01)가 섞여 있었다.
- **템플릿 임계값**: 기본값을 0.6에서 0.8로 올렸다. 0.6에서는 글자만 다른 버튼끼리 오탐이 났다.
- **설정 분리**: 하드코딩 값(COM3, 1920×1080, 홈 위치 등)을 설정 파일로 옮겼다.

## 다음 단계 (로드맵)

1. ~~기반 정리 + 시뮬레이터~~
2. 조작 신뢰성·속도
   - ~~실장비(Windows 대상) 커서·키보드 검증~~
   - ~~커서 위치 확인 비용 축소~~ (대기 조정 + 적응형 확인: 시나리오 45.0 → 36.0 s)
   - 키 입력 간격 (~0.08 s/글자) — VDI·KVM 키 누락 위험과 함께 검토
   - 속도 구간별 이득 학습
   - 드래그·스크롤
3. 인식 강화
   - ~~OCR로 텍스트 기반 target 지정~~ (텍스트 target, read, vote, 한국어 모델)
   - 화면 상태 판별 (현재: 템플릿 + color_tol)
   - 다중 매칭 (같은 target 여러 개 중 n 번째)
   - ~~OCR 속도~~ (검출 설정·anchor 영역: 메뉴 조회 812 → ~200ms, 시나리오 -20%)
4. 감시
   - ~~알람·에러 팝업 상시 감시 루프와 알림~~ (target / no_signal / frozen, 웹훅)
   - ~~이상 시 안전 정지~~ (stop + on_abort)
   - 블랙박스 영상 기록 (현재는 이벤트 시점 프레임만 저장)
   - 알림 채널 실연동 (Teams/Slack/ATOMS)
5. 연동
   - ATOMS 연동 인터페이스
   - TX(C++/엣지 장비) 탑재 전략
