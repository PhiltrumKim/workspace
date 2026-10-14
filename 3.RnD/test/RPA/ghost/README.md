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
  blackbox.py     실행 기록 (runs/<시각>_<이름>/events.jsonl + 프레임 + 영상 클립)
  recorder.py     블랙박스 영상 녹화기 (링 버퍼, 이벤트 전후 클립)
  hal/hub.py      FrameHub: 캡처 전담 스레드
  sim/            시뮬레이터: 가상 분석장비 SW + 가상 커서 (장비 없이 개발/테스트)
  editor/         시나리오 편집기 (로컬 웹: server.py + static/)
  ops/            무인 운영: 저장소(SQLite)·작업 실행기·예약·보고서·장시간 시험
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
python -m ghost editor                # 시나리오 편집기 (브라우저 http://127.0.0.1:8765)
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

## 변수·조건·반복

실제 분석 레시피를 표현하기 위한 흐름 제어다. 형식 전체는 `ghost/scenario/model.py` 머리말에 있다.

```json
{"params": {"lots": {"default": "LOT-A,LOT-B", "description": "처리할 LOT"}},
 "steps": [
   {"action": "for_each", "items": "${lots}", "var": "lot", "steps": [
     {"action": "type", "text": "${lot}"},
     {"action": "read", "name": "lot_read", "region": [502, 182, 412, 72]},
     {"action": "if", "cond": {"expr": "lot_read != lot"},
      "then": [{"action": "fail", "message": "LOT 불일치 ${lot_read}"}]}]}]}
```

| 기능 | 내용 |
|---|---|
| 파라미터 | `params` 기본값. 실행 시 `--param lots=A,B` 또는 편집기 실행 창에서 바꾼다. |
| 변수 | 문자열 어디서나 `${이름}`. `read` 값, `set` 값, 반복 변수도 변수다. |
| set | 값 그대로(`value`) 또는 계산식(`expr`) |
| if | 조건: 대상이 보임 / 없음 / 계산식, 그리고 `all`·`any`·`not` 조합. `then`·`else` |
| repeat · for_each · while | N번 / 목록 항목마다(`이름_index` 도 제공) / 조건 동안(상한 `max`, 기본 100) |
| break · continue · fail | 반복 탈출 / 다음 회차 / 지정 메시지로 실패 |
| call 인자 | `args` 로 하위 시나리오 파라미터를 넘긴다. 하위에서 읽거나 설정한 값은 돌려받는다. |

- **계산식**은 `eval` 을 쓰지 않는다. 구문 트리 화이트리스트로 사칙·비교·논리와 허용 함수(`len`, `int`, `round` 등)만 평가한다. 숫자처럼 보이는 판독값('09.91')은 계산식 안에서 숫자로 비교된다.
- **검증기**는 중첩 스텝까지 검사한다. 다음을 저장 전에 알려 준다: 정의되지 않은 변수, 반복 밖 `break`, 금지된 계산식, 빈 반복.
- **실행 기록**의 스텝 번호에 반복 회차가 남는다 (`2[3].6` = 2번 반복의 3회차 6번째 스텝).
- **편집기**:
  - 스텝을 트리로 보여 준다. 그러면/아니면, 반복 안에 스텝을 추가·이동·복제할 수 있다.
  - 동작은 분류별 목록에서 고른다.
  - 사용 가능한 변수 목록이 표시되고, 누르면 입력칸에 넣는다.
  - 파라미터 표가 있고, 실행 직전에 값을 입력하는 창이 뜬다.

실장비 예제: `scenarios/xnote_laps.json`
- 스톱워치가 꺼져 있을 때만 실행한다 (`if gone`).
- `${count}` 번 측정하고, 판독값이 대기 시간보다 짧으면 실패 처리한다.
- 합계·평균을 계산한다 (`--param count=3 --param measure_sec=1.5`: 6.63 / 5.94 / 6.93 s, 평균 6.5 s).

시뮬레이터 예제: `scenarios/sim/demo_lots.json` (LOT 목록 일괄 처리, 입력값 재확인, 처리 건수 확인).

## 시나리오 편집기

코드를 몰라도 화면을 보며 시나리오를 만드는 로컬 웹 도구다.

```bash
python -m ghost editor          # 실장비
python -m ghost editor --sim    # 시뮬레이터
# → 브라우저에서 http://127.0.0.1:8765 (이 PC 에서만 접속 가능)
```

| 영역 | 할 수 있는 것 |
|---|---|
| 장비 화면 | 실시간 보기 / 화면 고정, **대상 지정**(드래그), **직접 조작**(클릭·우클릭·더블클릭·글자·키를 장비로 전송) |
| 대상 탭 | 드래그한 영역을 그림 또는 글자(OCR) 대상으로 등록. OCR 이 읽은 글자를 미리 채우고, 등록 즉시 찾기 테스트(초록 상자) |
| 시나리오 탭 | 불러오기·새로 만들기, 동작 목록에서 스텝 추가·편집·순서 변경, **스텝 하나만 시험 실행**, 저장 전 검증, 전체 실행·중지(진행 상황이 스텝마다 표시), JSON 직접 편집 |
| 실행 기록 탭 | 실행별 스텝 결과·감시 이벤트·판독값, 실패 화면, 영상 클립 받기 |

- 동작 이름은 사용자 언어로 표시한다 ("나타날 때까지 대기", "글자·수치 읽기" 등).
- 결과가 중요한 스텝에는 "실행 후 확인"을 넣도록 폼에서 안내한다.
- 장비 조작은 한 번에 하나다. 전체 실행 중에는 다른 조작을 거부한다 (409).
- 외부 인터넷 자원(웹 폰트·CDN)을 쓰지 않아 현장 PC 에서 오프라인으로 동작한다.
- 구현: 표준 라이브러리 HTTP 서버(`ghost/editor/server.py`) + 프레임워크 없는 HTML/JS(`ghost/editor/static/`).

실장비 시연 (Edge 자동 조작):
- 편집기에서 `xnote_measure` 를 불러와 전체 실행해 성공했다 (판독값 표시).
- 바탕화면 '휴지통' 라벨을 드래그 → OCR 이 "휴지통" 을 채움 → 글자 대상 등록 → 찾기 점수 0.999 (77 ms).

테스트:
- `tests/test_editor_api.py` (API, 브라우저 없음)
- `tests/test_editor_e2e.py` (설치된 Edge 를 Playwright 로 조작해 불러오기 → 스텝 시험 → 드래그 등록 → 스텝 추가 → 저장 → 전체 실행 → 기록 확인. 개발용으로 `pip install playwright` 필요하며, Py3.9 는 `greenlet==3.1.1` 고정. 없으면 건너뜀)

편집기 E2E 에서 발견한 문제: 직전 클릭으로 커서가 대상 글자 위에 남으면 OCR 이 실패하고, '사라짐' 확인은 거짓 성공할 수 있었다.
대상을 찾기 전에 커서가 그 대상의 영역을 가리면 바깥으로 치우도록 했다 (`cursor.auto_park`, 기본 켬. 호버로 열리는 계단식 메뉴에서는 끈다).

## 무인 운영

시나리오를 사람 없이 반복·예약 실행하고, 장치가 끊기면 스스로 복구하고, 결과를 보고서로 남긴다.

```
python -m ghost ops                    편집기 서버 + 운영 실행기 시작 → http://127.0.0.1:8765/#ops
python -m ghost ops --sim              시뮬레이터
python -m ghost report --days 7 --csv jobs.csv     최근 7일 보고서 (data/report_시각.html)
```

- **대기열**: 작업(시나리오 + 파라미터)을 넣으면 하나씩 실행한다. 장치가 하나이므로 편집기와 같은 장치 잠금을 쓴다
  (편집기에서 직접 조작 중이면 운영 작업이 기다리고, 운영 작업 중에는 편집기 조작이 막힌다).
- **예약**: `주기`(N분마다) 또는 `매일 정해진 시각`(요일 제한 가능). 같은 예약의 이전 작업이 아직 대기·실행 중이면 건너뛰고 기록한다.
- **결과 분류**: 성공 / 실패(시나리오 실패) / 장치 오류 / 중지 / 취소 / 중단(프로그램이 실행 중에 종료됨)
- **장치 자동 복구**: 캡처·RelayBoard 통신 오류(`DeviceError`)로 끝나면 장치를 닫고 다시 연 뒤 홈잉한다
  (`ops.reconnect_backoff` 간격, 기본 5·15·30초). 복구되면 그 작업을 다시 대기열에 넣고(`ops.max_attempts`),
  끝내 안 되면 **장치 정지(halted)** 로 멈추고 critical 알림을 보낸다 — 설비를 계속 두드리지 않기 위해. 케이블을 확인한 뒤 `계속`.
- **시나리오 실패는 재시도하지 않는다** (같은 시료를 두 번 처리하는 등 위험할 수 있음). 필요하면 `ops.retry_failed: true`.
  실패 시 warning 알림 (웹훅 설정 시).
- **기록**: `data/ghost_ops.db` (SQLite — jobs / schedules / events). 실행별 상세는 기존처럼 `runs/` (블랙박스).
  10분마다 메모리·장치 통계를 health 이벤트로 남긴다 (장시간 누수 감시).
- **보고서**: 시나리오별 성공률·소요 시간(평균·p95)·감시 알람·주요 실패 원인·read 로 읽은 수치 통계(최소·최대·평균)와
  추세(인라인 SVG), 장치 이벤트. 외부 라이브러리 없는 단일 HTML 이라 폐쇄망 PC 브라우저에서 바로 열린다. CSV 는 엑셀용 BOM 포함.
- 편집기 `운영` 탭: 운영 시작·일시정지·계속·중지, 현재 작업 중지, 작업 넣기(파라미터·횟수), 작업 목록(취소·실행 기록 보기),
  예약 추가·수정·켜기/끄기, 보고서 요약·HTML·CSV, 운영 이벤트.

### 장시간 시험

```
python -m ghost.ops.soak --sim --minutes 10 --scenario demo_lots --scenario demo_run_watched --fault-every 45 --sim-alarm-every 40
python -m ghost.ops.soak --minutes 20 --scenario xnote_measure --fault-every 240
```

시나리오를 번갈아 계속 실행하며 N초마다 장치 고장을 주입한다 (시뮬레이터: 입력·영상 끊김, 실장비: 시리얼 포트 강제 종료 = USB 분리 증상).
결과는 `data/soak_<시각>/` (report.html, jobs.csv, memory.csv, soak.log).

**시험 결과 (2026-10-11)** — 장시간 무인 반복에서만 드러나는 문제를 찾는 것이 목적:

| 시험 | 작업 | 고장 주입 → 자동 복구 | 결과 |
|---|---|---|---|
| 시뮬레이터 10분 (알람 40초마다) | 59회 | 13 → 13 (정지 없음) | 시나리오 결함 2건 발견 → 수정 후 재시험 |
| 시뮬레이터 6분 (알람 20초마다, 수정 후) | 17회 | 7 → 7 | 시나리오 실패 15 → 2 (모두 START 전에 멈춘 안전 실패) |
| 실장비 XNote 20분 (시리얼 강제 종료 4분마다) | 29회 | 4 → 4 (복구 ~10s) | 고장 외 실패 1건 (아래) → 수정. 평균 45.3s, p95 60.2s |
| 실장비 XNote 10분 (2.5분마다, 수정 후) | 17회 | 3 → 3, 재시도 3/3 성공 | **고장 외 실패 0**. 평균 37.3s, p95 40.1s, 메모리 ~200 MB 수준 유지 |
| **실장비 XNote 8시간 밤샘** (30분마다) | **726회** | 15 → 15 + 캡처 순간 멈춤 2 → 2 | 성공 704 (97.0%). 실패 5: 개발 작업 부하로 측정값 범위 초과 3, 메뉴 'About' 오클릭 2 → 수정. 메모리 180~220 MB 기준선 유지(순간 최대 378), 누수 없음 |

발견·수정한 것:
- **모달 팝업이 클릭을 삼킴**: 화면 전환 클릭 직후 알람이 뜨면 클릭이 팝업에 막히고, 확인(expect)이 없는 스텝은 그냥 넘어감
  → 화면을 바꾸는 스텝에는 `expect` + `retry` 를 반드시 (데모 시나리오 수정).
- **입력칸 누적**: 이전 실행이 남긴 글자에 이어 붙음 → 입력 전 비우기. 실장비 실행 창도 `home` → `shift+end` 로 덮어쓰기.
- **확인 순서**: 입력값 검증을 START 뒤에 하면 잘못된 값으로 이미 실행됨 → **되돌릴 수 없는 동작 전에 검증**.
- **끊긴 동안 못 한 안전 복귀**: 장치 오류로 끝난 작업은 on_abort 를 실행할 수 없음 → 재연결 직후 on_abort 를 실행하고 재시도.
  안전 복귀 시나리오는 "남아 있는 창이 있으면 닫기"처럼 어떤 상태에서도 동작하게 작성.
- **눌린 수식키**: 조합키 도중 끊기면 대상 PC 에 수식키가 눌린 채 남을 수 있음 → 재연결 시 전부 해제.
- **메모리**: tracemalloc 으로 Python 객체 증가 없음 확인 (상위 +59 KiB). RSS 는 영상·OCR 네이티브 버퍼로 150~300 MB 사이를 오르내림.
  운영 중 메모리 조회 함수 자체의 작은 누수(ctypes 구조체 재정의)를 수정. 수 시간 단위 실장비 시험으로 상한 확인 필요.
- **메뉴 오클릭**: 메뉴 항목 높이가 약 20px 이라 경계 근처를 누르면 위 항목이 눌릴 수 있음 → 닫기는 Alt+F4 로, 시나리오 시작 전에 이미 켜진 창 정리.
- **캡처 순간 멈춤**: 8시간 중 2회, 1초 넘게 새 화면이 없었음 → 한 번 더 길게 기다린 뒤 장치 오류로 판단 (그래도 안 되면 자동 복구).
- **운영 PC 절전**: 시험 중 개발 PC 가 절전에 들어가 8시간 멈춤 → 운영 실행기가 도는 동안 Windows 절전 진입을 막도록 함
  (`ops.keep_awake`, 전원 설정은 바꾸지 않고 프로세스가 끝나면 자동 해제). **대상 PC** 의 절전·화면 보호기는 별도로 꺼야 한다.

## 난이도 조합 성공률 (실장비, GTB-3000 측정 작업)

`python tools/gtb_matrix.py --runs 5` — `scenarios/gtb_measure.json` (좌표 없이 글자만: 레시피 더블클릭 불러오기 → LOT 입력·적용 →
시작 → 알람은 색 감시로 처리 → 완료 창에서 측정값 판독 → 종료)을 조건마다 5번 (실행마다 /seed·레시피를 바꿈).

| 조건 | 1차 | 수정 후 |
|---|---|---|
| 기본 | 5/5 | 5/5 |
| 응답 지연 0.8초 | 3/5 | 5/5 |
| 알람 분당 12회 (알람 8건 처리) | 4/5 | 5/5 |
| 창 위치 무작위 | 5/5 | 5/5 |
| 어두운 스타일 | 5/5 | 5/5 |
| 고전 스타일 | 3/5 | 5/5 |
| 작은 글꼴 | 5/5 | 5/5 |
| 모두 (지연+알람+무작위 위치+어두움+작은 글꼴) | 4/5 | 5/5 |
| **전체** | **34/40 (85%)** | **40/40** (마지막 두 조건은 수정 후 재시험) |

실패에서 찾아 고친 것:
- 'Start' 를 누른 뒤 **시작됐는지 확인하지 않음** → 측정 화면으로 넘어갔는지 확인 + 재시도.
- 사용자가 열어 둔 **다른 창(탐색기)이 앞으로 와서** 클릭이 그 창의 메뉴에 떨어짐 → 조작 전에 대상 창 제목줄을 눌러 맨 앞으로.
- **표 한 줄(23px)** 을 확인 없이 이동한 몇 px 오차로 윗줄 레시피를 불러옴 → GHOST: 높이 30px 미만 대상은 클릭 전에 커서 위치를 반드시 실측
  (`cursor.precise_below`). 시나리오: 확인 창의 레시피 번호가 맞을 때만 '예' (되돌릴 수 없는 동작 전 검증).
- 어두운 스타일의 **저대비 글자**('Loaded:' 남색 on 검정)는 OCR 이 못 읽음 → 같은 정보를 대비 좋은 상태 줄에서 확인.
- 창이 매번 다른 곳에 뜨면 첫 화면 전체 OCR 이 길어짐 → 첫 단계 대기 30초.
- 종료가 한 번에 안 될 때 → 창이 사라질 때까지 반복.

## 복잡한 UI (부품 단위 동작) — 실장비 GTB-3000 Complex UI 탭

| 동작 | 쓰임 | 예 |
|---|---|---|
| `select` | 드롭다운: 펼치기 → 항목이 보일 때까지 휠 → 클릭 → 선택값 확인 | `{"action": "select", "x": 524, "y": 258, "item": "Chamber-27", "list": [x,y,w,h]}` |
| `menu` | 메뉴 경로: 단계마다 글자로 찾아 클릭 (하위 메뉴는 직전 항목 오른쪽·아래에서) | `{"action": "menu", "path": ["Analysis", "Wafer", "Map Export", "CSV"], "bar": [x,y,w,h]}` |
| `adjust` | 값을 읽어 가며 키로 목표까지 (슬라이더·스핀 박스) | `{"action": "adjust", "x": 884, "y": 248, "value": 73, "read": {"region": [..]}, "inc": "right", "dec": "left"}` |
| 교차점 클릭 `x_of` + `y_of` | x 는 한 대상, y 는 다른 대상의 중심 → 표 셀(열 머리글 × 행), 글자 없는 그림(웨이퍼 맵 열 글자 × 행 숫자) | `{"action": "click", "x_of": {"text": "Thickness"}, "y_of": {"text": "W05"}}` |

`scenarios/gtb_complex_ui.json` — 9가지(40항목 드롭다운, 접힌 트리, 3단계 메뉴, 슬라이더, 표 셀, 탭 안의 탭·체크박스,
우클릭 메뉴, 글자 없는 웨이퍼 맵 칸, 마우스를 올려야 나타나는 버튼)를 실장비에서 3회 연속 성공 (값을 바꿔 가며, 회당 ~80초).

추가 기능 (2026-10-14):
- **축 라벨 대상** `{"text": "5", "axis": "1-13", "region": [...]}` — 읽힌 라벨들로 '위치 = a + b × 순번' 직선(중앙값 기울기)을 맞춰
  OCR 이 놓친 라벨 위치도 추정. 웨이퍼 맵 칸을 확대 없이 H5·K12 실장비 확인.
- **색 감시 규칙** `{"type": "color", "bgr": [30, 30, 200], "tol": 40, "min_area": 8000}` — 일정 크기 이상 색 덩어리(알람 창의 빨간 머리글).
  OCR 이 없어 매 감시 주기에 돌려도 빠르고, 스타일·창 위치와 무관.
- **상대 클릭** `"offset": [220, 0]` — 대상 중심에서 떨어진 곳 (글자 'LOT ID' 오른쪽 입력칸).
- **직전 위치 먼저**: 영역 없는 글자 대상은 직전에 찾은 위치 근처부터 찾고, 없을 때만 화면 전체 OCR.

만들면서 찾은 규칙·수정:
- **트리는 더블클릭 대신 항목 클릭 → `right` 키**로 펼친다 (더블클릭은 펼침·접힘이 번갈아 재시도하면 다시 접힘).
- OCR 혼동 글자 **o↔0, l·I↔1** 을 찾기 비교에서 같은 글자로 본다 ('Tool-B2' 를 'T001-B2' 로 읽음).
- 트리 펼침 표시(`+ Fab-1`), 붙어 읽히는 탭(`Sub B Sub C`) 때문에 **목록·탭 항목은 '포함' 비교** (위치는 글자 부분으로 좁혀짐).
- 높이 40px 이하 영역의 한 줄 판독은 **폭이 높이의 12배 이하일 때만** (메뉴 줄 전체를 한 줄로 읽으면 'Analysis' → 'nalsig').
- 작은 한 글자(웨이퍼 맵 행 숫자 '5')는 OCR 이 놓친다 → 대상에 `"scale": 3` (확대 판독).
- 드롭다운 목록이 8줄이 아니라 화면 높이만큼 길게 펼쳐질 수 있음 → `select` 기본 목록 영역은 아래로 700px.

## 키보드·조합키 시험 (실장비, GTB-3000 Keyboard 탭)

`python tools/key_bench.py` — 키를 하나씩 보내고 GTB 화면(받은 키·횟수·눌린 수식키)을 읽어 바로 채점.
키마다: 정확히 한 번 들어갔는지, 가상키·스캔코드·확장키·함께 눌린 수식키, 끝난 뒤 눌린 키가 남지 않았는지.

| 묶음 | 결과 |
|---|---|
| 영문 26 · 숫자 10 · 기호 11 · F1~F12 · 편집/이동 15 · 숫자 패드 10 | 전부 통과 |
| Ctrl+A/C/V/X/Z/Y/S/F/Home/End · Shift 조합 7 · Ctrl+Shift 조합 4 · Alt+메뉴 3 | 전부 통과 |
| CapsLock · NumLock (두 번 눌러 원복) · 메뉴 키 · 오른쪽 Shift | 통과 |
| PrintScreen | 앱에 '누름' 메시지가 오지 않음 (Windows 동작, 측정 한계) |
| ScrollLock · 오른쪽 Ctrl | RelayBoard 가 반영하지 않음 → 시나리오에서 쓰지 않음 (왼쪽 Ctrl 사용) |
| 한자 | 들어오지만 스캔코드가 한국어 키보드 전용(F1)으로 바뀜 |
| 복사·붙여넣기·잘라내기·되돌리기 · 선택 후 복사 | 전부 통과 |
| **Ctrl+A 전체 선택** | Win7 기본 입력칸에서 동작 안 함 → **전체 선택은 Home → Shift+End** |
| 한/영 | 표준 한/영 키 코드는 이 PC 에서 전환 안 됨, **오른쪽 Alt 로 전환됨** (키보드 종류 '101 종류 3') |

**한글 입력**: `type` 에 한글이 있으면 입력기를 한글 모드로 바꿔 두벌식 자판 순서로 치고 영문으로 되돌린다
("LOT-7 재측정 요청 (온도 25도)" 실장비 확인). 한/영 전환 키는 `keyboard.hangul_toggle` (`ralt` 기본, 한국어 103/106 키보드는 `hangul`).
입력 시작 시 대상 입력기가 영문 상태라고 가정한다.

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

## 블랙박스 영상

비행기 블랙박스처럼 **이벤트 전후 영상**을 남긴다. 설정은 `blackbox.video` 에 있다.

- 캡처는 `FrameHub` 스레드 하나가 전담한다.
  - 엔진은 허브에서 "호출 이후 캡처를 시작한" 프레임을 받는다.
  - 녹화기는 모든 프레임을 구독한다.
- 녹화기는 최근 `pre_seconds`(10s) 를 축소 JPEG 링 버퍼로 보관한다.
- 다음 이벤트가 나면 전 10s + 후 5s 를 `clipNN_<이벤트>.mp4` 로 저장한다.
  - 스텝 최종 실패
  - `clip_min_severity`(warning) 이상 감시 이벤트
  - 중단
- 직후 구간 안에 다시 난 이벤트는 같은 클립에 합친다.
- 실행이 끝날 때도 직후 구간이 찰 때까지 기다린다. 실패 직후 장면을 잘라내지 않기 위해서다.
- 영상 위 표시: 시각, 현재 스텝, 이벤트(전: 주황 `T-초`, 후: 빨강 `T+초`).
  - OpenCV 글꼴은 한글을 못 그려서 ASCII 만 표시한다. 한글 설명은 `events.jsonl` 에 있다.
- `continuous: true` 면 실행 전체를 `run.mp4` 로도 녹화한다 (데모·감사용).
- 기본 960x540, 5fps, 15초 클립 약 0.4 MB. 시뮬레이터는 기본으로 끈다.

실장비 확인:
- `hw_watch_demo`: 경고 팝업 발생부터 자동 확인까지 13.6초 클립.
- 강제 실패 시나리오: 실패 클립 저장.
- 영상을 켜도 xnote_measure 시간 차이는 편차 수준이다 (평균 36.3 → 37.2 s).

개발 중 잡은 경쟁 상태 두 가지 (테스트로 재현해 수정):
1. 허브가 프레임 시각을 캡처 **완료** 시점으로 기록해서, 이동 직전에 찍기 시작한 프레임을 이동 후 프레임으로 넘겼다. 그 결과 커서 실측이 8px 틀렸다. 캡처 **시작** 시각 기준으로 고쳤다.
2. 프레임 스레드가 완료 처리한 클립의 쓰기를 실행 종료가 기다리지 않아 클립이 누락됐다. 쓰기 스레드 등록을 잠금 안에서 하도록 고쳤다.

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

## TX(우분투) 이식 메모

현재는 Windows PC 에서 개발한다. 최종 탑재 대상 TX 는 우분투 x86/x64 다 (MiTx 빌드 환경 `ubuntu:20.04`, 기본 Python 3.8).

**확인된 것**
- 코드 최소 요구 버전: Python 3.8 (`vermin` 정적 분석, 37개 파일, 위반 없음).
- 의존 패키지(OpenCV, onnxruntime, pyserial)와 OCR 모델(ONNX)은 리눅스 x64 를 지원한다.
- 실행 중 외부 네트워크 접속이 없다 (폐쇄망 가능). 예외는 `fetch-models` 하나로, 폐쇄망에서는 `models/` 를 복사한다.

**이식 시 할 일**
1. **장치 연결**: TX 에서는 MiTxEngine(C++)이 Magewell(SDK)과 RelayBoard 시리얼을 이미 점유한다. GHOST 가 직접 열지 말고 MiTxEngine 을 경유하는 HAL 백엔드(VideoSource/HidOutput)를 추가한다.
   - 입력: `TcpServerInsideProtocol` 에 GUI→엔진 키 주입 경로가 있다.
   - 화면: 넘겨받을 경로를 아직 찾지 못했다 (공유 메모리 등 신설 검토).
2. **편집기 원격 접속**: 127.0.0.1 전용을 네트워크 공개로 바꿀 때는 인증·TLS 를 반드시 붙인다. 또는 ATOMS UI 에 통합한다.
3. **설정**: 포트 이름(`/dev/ttyUSB0` 등)을 바꾼다. 캡처 지연·대기시간과 OCR·커서 측정 성능은 TX 에서 다시 잰다.
4. **오프라인 설치 꾸러미**: wheel 묶음 + `models/` + 설치 스크립트.
5. **실제 Ubuntu 20.04 에서 테스트**: 미실시 (WSL2/CI/실장비 중 택1).

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
   - ~~블랙박스 영상 기록~~ (이벤트 전후 클립, 연속 녹화 옵션)
   - 알림 채널 실연동 (Teams/Slack/ATOMS)
5. 무인 운영
   - ~~대기열·예약·장치 자동 복구·보고서·장시간 시험~~
   - 운영 화면 원격 접속 (인증·TLS), 보고서 정기 발송
6. 연동
   - ATOMS 연동 인터페이스
   - TX(C++/엣지 장비) 탑재 전략
