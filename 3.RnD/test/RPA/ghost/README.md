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
  vision/         템플릿 매칭 (영역 제한, 다중 배율)
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
.venv/Scripts/python -m pytest -q                                     # 테스트
.venv/Scripts/python -m ghost run scenarios/sim/demo_run_recipe.json --sim
.venv/Scripts/python -m ghost run scenarios/sim/demo_alarm_recovery.json --sim
```

실장비 (Magewell + RelayBoard 연결 시):

```bash
python -m ghost probe                 # COM 포트 목록 + 캡처 확인
python -m ghost probe --smoke         # 홈잉 + 3점 이동 + 커서 실측 (클릭 없음)
python -m ghost snap shot.png         # 화면 저장
python -m ghost add-target ok_btn --image shot.png --box 860,600,200,60   # target 등록
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
Windows 대상은 **'포인터 정확도 향상'(마우스 가속)을 끄는 것을 권장**한다. 켜져 있어도 수렴하지만 보정 횟수가 늘어난다.

## 레거시 대비 수정 사항

- **키보드 패킷**: `#6`에 Windows VK, `#7` flag에 확장키 비트(bit1)를 채운다. C++ `TcpServer.cpp`와 동일하다.
  - 레거시는 VK=0으로 보냈고, USB HID 코드(ESC=0x29)와 PS/2 Set1 코드(ESC=0x01)가 섞여 있었다.
- **템플릿 임계값**: 기본값을 0.6에서 0.8로 올렸다. 0.6에서는 글자만 다른 버튼끼리 오탐이 났다.
- **설정 분리**: 하드코딩 값(COM3, 1920×1080, 홈 위치 등)을 설정 파일로 옮겼다.

## 다음 단계 (로드맵)

1. ~~기반 정리 + 시뮬레이터~~
2. 조작 신뢰성
   - ~~실장비(Windows 대상) 커서·키보드 검증~~
   - 속도 구간별 이득 학습
   - 드래그·스크롤
3. 인식 강화
   - OCR로 텍스트 기반 target 지정
   - 화면 상태 판별
   - 다중 매칭
4. 감시
   - ~~알람·에러 팝업 상시 감시 루프와 알림~~ (target / no_signal / frozen, 웹훅)
   - ~~이상 시 안전 정지~~ (stop + on_abort)
   - 블랙박스 영상 기록 (현재는 이벤트 시점 프레임만 저장)
   - 알림 채널 실연동 (Teams/Slack/ATOMS)
5. 연동
   - ATOMS 연동 인터페이스
   - TX(C++/엣지 장비) 탑재 전략
