# RPA 자동 제어 프레임워크 (rpa_auto)

Magewell 캡처(비전) + 릴레이보드(제어)로 대상 PC(Raspberry Pi)를 **사용자 없이 워크플로우 기반**
으로 자동 제어하는 프레임워크. 화면의 아이콘을 **"클릭 가능한 객체"** 로 인식하고, 클릭으로
새로 나타난 요소를 자동 발견·등록하며, 이를 재실행 가능한 워크플로우로 조립한다.

## 핵심 개념
- **객체(object)** = 클릭 가능한 아이콘/버튼/메뉴항목. 템플릿 이미지 + 메타(클릭점, 서브메뉴 여부 등)로 표현.
- **발견(discovery)** = 트리거 객체를 클릭 → 나타난 패널을 항목 단위로 분할 → 각 항목을 신규 객체로 등록 + 클릭 워크플로우 자동 생성.
- **워크플로우(workflow)** = 재사용 가능한 동작 시퀀스(JSON). 다음 실행에서도 동일하게 재생.
- 계층: 아이콘 클릭 → 서브메뉴 → 서브-서브메뉴 … (예: Menu → Internet → Web Browser).

## 구성 (`rpa_auto/`)
| 파일 | 역할 |
|------|------|
| `engine.py` | `RelayVisionEngine` — connect/원점보정/`find`/`move_to`/`click`/`dismiss`/`key_tap`/`screenshot` |
| `registry.py` | `Registry` — 객체 저장/로드 (`objects/objects.json` + 템플릿 PNG) |
| `workflow.py` | 워크플로우 저장/로드/실행 (`workflows/*.json`) |
| `discover.py` | `discover_submenu` — 클릭 후 나타난 항목 자동 분할·등록·워크플로우 생성 |

데이터: `objects/`(등록된 클릭 객체), `workflows/`(생성/작성된 워크플로우).

## 좌표/정밀도 기반 (앞선 검증)
- 프레임 1920×1080 = 대상 모니터 1:1. 연결 시 `reset_mouse`(홈) 후 캡처 오버스캔을 **자동 원점 보정**(홈 원점 ~48,48).
- 이동은 프레임당 ±127px 개루프 추종, 타깃은 객체 **중심**. 도달 정밀도 ~6px(하드웨어 ±1%).
- 객체 재탐색은 `matchTemplate`(CCOEFF_NORMED)로 매 실행마다 현재 화면에서 위치를 다시 찾음 → 위치가 바뀌어도 견고.

## 워크플로우 형식
```json
{ "name": "launch_web_browser",
  "goal": "Menu > Internet > Web Browser 자동 실행",
  "steps": [
    {"action":"click","object":"menu_btn"}, {"action":"wait","sec":0.6},
    {"action":"click","object":"menu_01"},  {"action":"wait","sec":0.6},
    {"action":"click","object":"internet_02"}, {"action":"wait","sec":1.0} ] }
```
지원 action: `click` / `double` / `click_xy` / `key`(HID) / `wait` / `screenshot` / `expect`.
`click`은 객체 템플릿을 현재 화면에서 찾아 중심 클릭(미검출 시 저장된 클릭 힌트 좌표로 폴백).

## 사용법
```bash
# 발견 데모: Menu 클릭 → 10개 항목 등록 + 워크플로우 생성 → click_menu_01(Internet) 재실행
.venv\Scripts\python.exe demo_autonomous.py

# 최종 데모: Internet 서브메뉴 발견 → launch_web_browser 생성/실행 → 브라우저 자동 기동
.venv\Scripts\python.exe demo_launch_browser.py
```
프로그램적으로:
```python
from rpa_auto.engine import RelayVisionEngine
from rpa_auto.registry import Registry
from rpa_auto import discover, workflow
eng = RelayVisionEngine(); eng.connect(); reg = Registry()
discover.discover_submenu(eng, reg, "menu_btn", "menu")   # 발견 + 워크플로우 생성
workflow.run(eng, reg, workflow.load_workflow("launch_web_browser"))  # 재실행
```

## 검증된 결과 (2026-07-05)
- **발견**: Menu 클릭 → 10개 메뉴 항목(menu_00~09) 자동 등록, 서브메뉴 화살표 정확 감지(00~07=있음, Run/Shutdown=없음). 항목당 클릭 워크플로우 10개 생성.
- **재실행**: `click_menu_01` 워크플로우로 Menu→Internet 재클릭 → 서브메뉴(Pi Store / Raspberry Pi Resources / Web Browser) 재현.
- **최종(자율)**: `launch_web_browser` 워크플로우로 Menu→Internet→Web Browser 클릭 → **브라우저 자동 실행 성공**(사용자 개입 0). 증거: `rpa_demo_20260705/browser_launched.png`.

## 한계 / 향후
- 항목 이름은 현재 인덱스 기반(OCR 미사용). 텍스트 인식(pytesseract 등) 추가 시 "Internet","Web Browser" 등 의미 있는 이름으로 등록 가능.
- 키보드 입력(`key_tap`)은 메뉴 닫기에서 불안정 확인 → 팝업 닫기는 `dismiss()`(빈 바탕화면 클릭, 마우스 기반) 사용. URL 타이핑 등 키보드 자동화는 별도 검증 필요.
- 발견 분할은 좌측 아이콘 열의 그레이 표준편차 기반(색 무관). 아이콘 없는 목록/다른 위젯은 분할 로직 확장 필요.
- 상태 의존: 워크플로우 시작 시 `dismiss()`로 팝업 정리 후 진행 권장.
