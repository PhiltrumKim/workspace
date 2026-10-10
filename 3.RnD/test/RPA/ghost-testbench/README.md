# GTB-3000 Analyzer Console (GHOST Test Bench)

GHOST 를 시험하기 위한 **가상 분석 장비 SW**다. 실제 장비 SW 에서 자동화가 어려운 요소를 일부러 모았다.
모든 조작과 상태 변화를 **정답 로그(CSV)** 로 남겨, GHOST 실행 결과와 대조해 성공률을 수치로 잴 수 있다.

## 대상 PC 에 설치

`dist/` 폴더의 두 파일만 복사한다 (USB 등). 설치 과정은 없다.

```
GTB3000.exe          단일 실행 파일 (약 55KB)
GTB3000.exe.config   런타임 선택: XP/7 은 .NET 3.5, 10/11 은 .NET 3.5 가 없으면 .NET 4.x
```

| OS | 필요 런타임 |
|---|---|
| Windows 7 | 기본 내장 .NET 3.5 — 그대로 실행 |
| Windows 10/11 | 기본 .NET 4.x 로 실행 (config 파일 필요) |
| Windows XP | .NET 3.5 설치 필요 |

로그인: `operator / 1234` 또는 `engineer / 5678`

## 화면과 시험 요소

| 탭·요소 | GHOST 가 시험받는 것 |
|---|---|
| 로그인 창 | 글자 입력, 실패 메시지 창 |
| 메뉴바·툴바·상태줄 | 메뉴 탐색, 상태 글자 판독 |
| Recipe: 레시피 표 30행 (스크롤·선택 강조·더블클릭) | 표 안 항목 찾기, 선택 상태(색) |
| Recipe: 파라미터 (LOT 입력·콤보·숫자 입력·체크박스·비활성 버튼) | 다양한 컨트롤 조작, 활성/비활성 판별 |
| 확인 창 (불러오기·중단·종료) | 예/아니오 대화상자 처리 |
| Run Monitor: 상태 램프 4개 (회색·초록·노랑·빨강) | 색으로 상태 판별 (`color_tol`) |
| Run Monitor: 7세그먼트 측정값, 진행률, 메시지 목록 | 변하는 수치 판독 (`vote`), 완료 대기 |
| 알람 창 (모달, 무작위) / 경고 배너 (6초 후 사라짐) | 감시 규칙, 처리 후 계속, 탐지율 |
| 측정 완료 창 | 완료 확인 |
| Results: 결과 표 (OK/NG 색) + CSV 저장 창 | 여러 값 판독, Windows 저장 대화상자 |
| Alarm Log | 알람 기록 판독 |
| Settings | 실행 중 난이도 변경 |

시작 조건이 맞지 않으면 시작을 거부하고 이유를 띄운다 (레시피 미로드, LOT 미입력, 파라미터 미적용).
실패 상황 시나리오도 시험할 수 있다.

## 난이도·스타일 (명령줄 또는 Settings 탭)

```
GTB3000.exe /alarm=2 /warn=3 /delay=800 /freeze=20 /freezesec=5 /randompos /timescale=0.5 /style=flat /seed=42
```

| 옵션 | 의미 |
|---|---|
| `/alarm=N` | 측정 중 분당 알람(모달 창) 기대 횟수 |
| `/warn=N` | 측정 중 분당 경고(배너) 기대 횟수 |
| `/delay=ms` | 버튼 응답 지연. "처리 중" 표시와 대기 커서 (느린 장비 SW) |
| `/freeze=%` `/freezesec=s` | Start 시 화면 멈춤 확률과 시간 (화면 멈춤 감시 시험) |
| `/randompos` | 시작할 때 창 위치를 무작위로 (좌표 의존 시나리오 검출) |
| `/smallfont` | 작은 글꼴 (OCR 난이도) |
| `/timescale=x` | 측정 시간 배율 |
| `/seed=n` | 난수 고정 (재현 가능한 시험) |
| `/style=` | `native`(OS 기본) · `classic`(고전 입체) · `flat`(Windows 10/11 평면) · `dark` |
| `/user=operator` | 로그인 창 생략 |
| `/tab=n` | 시작 탭 |

**Windows 버전별 모양**
- WinForms 는 OS 기본 컨트롤을 쓰므로, 실행한 OS 의 모양(XP Luna / 7 Aero / 10·11)으로 그려진다.
- 한 대의 PC 에서는 `/style` 로 고전·평면·다크 모양을 흉내 낸다. 그림 대상은 스타일이 바뀌면 깨지고 글자(OCR) 대상은 유지되는지를 시험할 수 있다.

## 정답 로그

실행 파일 옆 `logs/gtb_YYYYMMDD_HHMMSS.csv` (UTF-8, `time,event,detail`).

| event | detail |
|---|---|
| app_start | 난이도 설정 |
| login / login_fail / login_auto | 사용자 |
| tab | 탭 이름 |
| recipe_select / recipe_load / recipe_load_cancel | 레시피 ID |
| params_apply | lot, sample, temp, repeat, autocal, raw |
| start_rejected | no_recipe / no_lot / params_not_applied |
| run_start / run_pause / run_resume / run_stop | 레시피·LOT·회차 |
| freeze | 멈춤 시간 |
| warning | 경고 코드 |
| alarm_raised / alarm_ack / alarm_abort | 알람 코드 |
| cycle_done | recipe, lot, cycle, **value**, unit, judge — 판독 정답 |
| run_complete / complete_ack | 마지막 값 |
| export / export_cancel / results_clear | 파일 경로·행 수 |
| exit / exit_cancel / app_exit | |

GHOST 블랙박스(`events.jsonl`)와 대조하면 다음 지표를 계산할 수 있다:
- 판독 정확도: `cycle_done.value` 와 GHOST `read` 값
- 알람 탐지율: `alarm_raised` 와 GHOST 감시 `appeared`
- 무인 수행 성공률: 시나리오 성공과 `run_complete`

## 빌드

Windows 에 기본으로 들어 있는 .NET 3.5 C# 컴파일러로 빌드한다 (추가 설치 불필요). C# 3 문법만 쓴다.

```
build.cmd        → dist\GTB3000.exe, dist\GTB3000.exe.config
tools\shot.ps1   → 스타일별 창 캡처 (개발 확인용)
```
