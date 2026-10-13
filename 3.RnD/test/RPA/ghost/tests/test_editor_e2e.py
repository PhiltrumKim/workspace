"""시나리오 편집기 브라우저 E2E (설치된 Edge 를 Playwright 로 조작) — 시뮬레이터.
Playwright 또는 Edge 가 없으면 건너뛴다 (개발용: pip install playwright, 브라우저 추가 설치 불필요)."""
import json
import os
import threading

import pytest

from ghost.editor import EditorApp, serve
from ghost.sim import DemoEquipmentApp, SimWorld

sync_api = pytest.importorskip("playwright.sync_api")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
pytestmark = pytest.mark.skipif(not os.path.exists(EDGE), reason="Edge 없음")
OFF = 48


@pytest.fixture
def page_and_app(cfg, tmp_path):
    w = SimWorld(DemoEquipmentApp(run_duration=0.4), offset=(OFF, OFF))
    app = EditorApp(cfg, sim=True, world=w)
    app.open()
    httpd = serve(app, 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/")
        page.wait_for_function("document.querySelector('#conn').textContent.includes('시뮬레이터')")
        page.wait_for_selector("body[data-ready='1']", state="attached")      # 첫 화면 초기화 끝
        yield page, app, w, errors, tmp_path
        browser.close()
    httpd.shutdown()
    app.close()


def drag_on_canvas(page, box):
    """프레임 좌표 box=[x,y,w,h] 를 캔버스 위 드래그로 지정."""
    r = page.locator("#screen").bounding_box()
    sx, sy = r["width"] / 1920, r["height"] / 1080
    x0, y0 = r["x"] + box[0] * sx, r["y"] + box[1] * sy
    page.mouse.move(x0, y0)
    page.mouse.down()
    page.mouse.move(x0 + box[2] * sx, y0 + box[3] * sy, steps=6)
    page.mouse.up()


def test_full_authoring_flow(page_and_app):
    page, app, w, errors, tmp = page_and_app

    # 1) 기존 시나리오 불러오기 → 스텝 목록
    page.select_option("#scen-select", "demo_run_recipe")
    page.wait_for_selector("#steps li.step")
    assert page.locator("#steps li.step").count() == 11      # 10 스텝 + 반복 안의 1

    # 2) 첫 스텝만 실행 → 결과 표시
    page.locator("#steps li.step").nth(0).locator("button[title='이 스텝만 실행']").click()
    page.wait_for_selector("#steps li.step.passed")
    assert w.app.page == "recipe"

    # 3) 화면에서 RCP_A 행을 드래그 → 글자 target 으로 등록 (OCR 이 글자를 미리 채움)
    page.click(".toolbar [data-mode='select']")
    page.wait_for_timeout(400)
    drag_on_canvas(page, [368, 188, 700, 60])
    page.wait_for_selector("#target-form:not([hidden])")
    page.wait_for_function("document.querySelector('#tf-kind-hint').textContent.includes('읽힌 글자')")
    page.click("#target-form [data-kind='text']")
    page.wait_for_selector("#tf-ocr .chip")
    assert "RCP_A" in page.input_value("#tf-text")
    page.fill("#tf-text", "RCP_A")
    page.fill("#tf-name", "e2e_rcp_a")
    page.click("#target-form button[type=submit]")
    page.wait_for_function("document.querySelector('#tf-msg').textContent.includes('등록')")
    assert "e2e_rcp_a" in app.reg and app.reg.get("e2e_rcp_a")["text"] == "RCP_A"

    # 4) 새 시나리오: 클릭(+선택 확인) → 읽기 → 저장
    page.click(".tabs [data-tab='scenario']")
    page.click("#scen-new")
    page.fill("#scen-name", "e2e_flow")
    page.fill("#scen-desc", "편집기 E2E")
    page.click("#step-add")
    page.select_option("#sf-action", "click")
    page.select_option("#f-target", "e2e_rcp_a")
    page.select_option("#f-exp-kind", "visible")
    page.select_option("#f-exp-target", "rcp_a_sel")
    page.click("#sf-try")                                       # 저장 전 시험 실행
    page.wait_for_function("document.querySelector('#sf-msg').textContent.includes('성공')")
    page.click("#sf-save")
    page.wait_for_function("document.querySelectorAll('#steps li.step').length === 1")
    page.click("#step-add")
    page.select_option("#sf-action", "wait")
    page.fill("#f-sec", "0.2")
    page.click("#sf-save")
    page.wait_for_function("document.querySelectorAll('#steps li.step').length === 2")
    page.click("#scen-save")
    page.wait_for_function("document.querySelector('#scen-msg').textContent.includes('저장했습니다')")
    path = os.path.join(app.scen_dir, "e2e_flow.json")
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["steps"][0] == {"action": "click", "target": "e2e_rcp_a",
                                 "expect": {"visible": "rcp_a_sel", "timeout": 3}}

    # 5) 전체 실행 → 성공 표시
    w.app.selected = None
    page.click("#scen-run")
    page.wait_for_function("document.querySelector('#scen-msg').textContent.includes('성공')", timeout=30000)
    assert w.app.selected == "rcp_a"

    # 6) 실행 기록 탭
    page.click(".tabs [data-tab='runs']")
    page.wait_for_selector("#runs li.run")
    page.locator("#runs li.run").first.click()
    page.wait_for_selector("#run-detail .detail-steps div")

    assert errors == [], errors


def test_nested_flow_and_params(page_and_app):
    """중첩 스텝 트리 표시, 실행 값 입력, 조건 분기 안에 스텝 추가·저장."""
    page, app, w, errors, tmp = page_and_app

    # 1) 반복·조건이 있는 시나리오 → 트리로 표시
    page.select_option("#scen-select", "demo_lots")
    page.wait_for_selector("#steps .substeps")
    assert page.locator("#steps > li.step").count() == 6
    assert page.locator("#steps .substeps li.step").count() >= 10
    assert page.input_value("#params-rows tr:nth-child(1) input") == "lots"

    # 2) 실행 → 값 입력 창에서 LOT 목록 변경 → 성공, 반복 안 스텝 결과 표시
    page.click("#scen-run")
    page.wait_for_selector("#run-form:not([hidden])")
    page.fill("#run-p-lots", "LOT-Q1")
    page.click("#run-form button[type=submit]")
    page.wait_for_function("document.querySelector('#scen-msg').textContent.includes('성공')", timeout=60000)
    assert [e for e in w.app.events if e.startswith("DONE")] == ["DONE rcp_b lot=LOT-Q1"]
    assert page.locator("#steps .substeps li.step.passed").count() >= 5

    # 3) 새 시나리오: 조건 분기(계산식) + 그러면 안에 스텝
    page.click("#scen-new")
    page.fill("#scen-name", "e2e_nested")
    page.click("#params-box summary")                     # 파라미터 영역 펼치기 (없으면 접혀 있음)
    page.click("#param-add")
    page.fill("#params-rows tr:nth-child(1) input[aria-label=name]", "n")
    page.fill("#params-rows tr:nth-child(1) input[aria-label=default]", "5")
    page.click("#step-add")
    page.select_option("#sf-action", "if")
    page.select_option("#f-cond-kind", "expr")
    page.fill("#f-cond-expr", "n > 3")
    page.click("#sf-save")
    page.wait_for_selector("#steps .substeps button.add")
    page.locator("#steps .substeps").nth(0).locator("button.add").click()   # '그러면' 안에 추가
    page.wait_for_function("document.querySelector('#step-form-title').textContent.includes('그러면')")
    page.select_option("#sf-action", "set")
    page.fill("#f-set-name", "big")
    page.fill("#f-set-val", "yes ${n}")
    page.click("#sf-save")
    page.wait_for_function("document.querySelectorAll('#steps .substeps li.step').length === 1")
    page.click("#scen-save")
    page.wait_for_function("document.querySelector('#scen-msg').textContent.includes('저장했습니다')")
    with open(os.path.join(app.scen_dir, "e2e_nested.json"), encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["params"] == {"n": {"default": "5"}}
    assert saved["steps"][0]["cond"] == {"expr": "n > 3"}
    assert saved["steps"][0]["then"] == [{"action": "set", "name": "big", "value": "yes ${n}"}]
    assert errors == [], errors


def test_ops_tab(page_and_app):
    page, app, w, errors, tmp = page_and_app
    page.click(".tabs button[data-tab=ops]")
    page.wait_for_function("document.querySelector('#ops-scen').options.length > 0")
    page.select_option("#ops-scen", "demo_lots")
    page.wait_for_selector("#ops-params [data-param=lots]")
    page.fill("#ops-params [data-param=lots]", "LA,LB")
    page.fill("#ops-count", "2")
    page.click("#ops-submit")
    page.wait_for_function("document.querySelector('#ops-msg').textContent.includes('작업 1, 2')")
    page.wait_for_selector("#ops-jobs .job.queued")
    page.click("#ops-jobs .job.queued >> nth=0 >> button:has-text('취소')")   # 최신(2번) 취소
    page.wait_for_selector("#ops-jobs .job.cancelled")
    page.click("#ops-start")
    page.wait_for_selector("#ops-jobs .job.ok", timeout=60000)
    assert "운영 중" in page.text_content("#ops-badge")
    assert "lot_read=LB" in page.text_content("#ops-jobs .job.ok")
    # 예약: 매일 + 요일
    page.click("#ops-sched-box summary")
    page.fill("#sc-name", "아침 점검")
    page.select_option("#sc-scen", "demo_run_recipe")
    page.click("[data-skind=daily]")
    page.fill("#sc-times", "25:00")
    page.click("#sc-save")
    page.wait_for_function("document.querySelector('#sc-msg').textContent.includes('시각 형식')")
    page.fill("#sc-times", "08:00, 20:30")
    page.check("#sc-days label:nth-child(1) input")
    page.click("#sc-save")
    page.wait_for_selector("#ops-scheds .sched")
    assert "월 08:00, 20:30" in page.text_content("#ops-scheds .sched")
    page.wait_for_function("document.querySelector('#rep-table').textContent.includes('demo_lots')")
    page.click("#ops-pause")
    page.wait_for_function("document.querySelector('#ops-badge').textContent.includes('일시정지')")
    shot = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", "_work", "ops_tab.png")
    page.screenshot(path=shot)
    assert not errors, errors


def test_late_run_poll_does_not_overwrite(page_and_app):
    """실행 상태 응답이 늦게 도착해도, 그 사이 바꾼 시나리오의 메시지를 덮어쓰지 않는다 (간헐 실패 원인 회귀)."""
    page, app, w, errors, tmp = page_and_app
    # 서버가 바쁠 때처럼 실행 상태 응답만 2.5초 늦게 도착하게 함 → 요청이 겹쳐 쌓임
    page.evaluate("""() => { const f = window.fetch;
      window.fetch = async (u, o) => { const r = await f(u, o);
        if (String(u) === '/api/run' && (!o || !o.method || o.method === 'GET')) await new Promise((ok) => setTimeout(ok, 2500));
        return r; }; }""")
    page.select_option("#scen-select", "demo_run_recipe")
    page.wait_for_selector("#steps li.step")
    page.click("#scen-run")
    page.wait_for_function("document.querySelector('#scen-msg').textContent.includes('성공')", timeout=90000)
    page.select_option("#scen-select", "ack_alarm")      # 다른 시나리오로 바꿔 저장 (빈 시나리오는 저장 거부)
    page.wait_for_function("document.querySelector('#scen-name').value === 'ack_alarm'")
    page.click("#scen-save")
    page.wait_for_function("document.querySelector('#scen-msg').textContent.includes('저장했습니다')")
    page.wait_for_timeout(4000)                          # 쌓여 있던 응답이 모두 도착할 시간
    assert "저장했습니다" in page.text_content("#scen-msg")
    assert errors == [], errors


def test_scroll_drag_steps_in_form(page_and_app):
    """편집기 폼으로 휠·드래그·스크롤해서 찾기 스텝을 만들고 실행·저장."""
    page, app, w, errors, tmp = page_and_app
    page.click("#scen-new")
    page.fill("#scen-name", "e2e_drag")
    page.click("#step-add")
    page.select_option("#sf-action", "click")
    page.select_option("#f-target", "nav_log")
    page.click("#sf-save")
    page.wait_for_selector("#step-form", state="hidden")
    page.click("#step-add")
    page.select_option("#sf-action", "scroll")
    page.fill("#f-amount", "-6")
    page.select_option("#f-where-sel", "@xy")
    page.fill("#f-where-x", "600")
    page.fill("#f-where-y", "400")
    page.click("#sf-save")
    page.wait_for_selector("#step-form", state="hidden")
    page.click("#step-add")
    page.select_option("#sf-action", "drag")
    page.select_option("#f-target", "@xy")
    page.fill("#f-x", "600")
    page.fill("#f-y", "170")
    page.select_option("#f-to-sel", "@xy")
    page.fill("#f-to-x", "1240")
    page.fill("#f-to-y", "440")
    page.click("#sf-save")
    page.wait_for_selector("#step-form", state="hidden")
    page.wait_for_function("document.querySelectorAll('#steps > li.step').length === 3")
    assert "아래로 6칸" in page.text_content("#steps")
    page.click("#scen-run")
    try:
        page.wait_for_function("/성공|실패/.test(document.querySelector('#scen-msg').textContent)", timeout=60000)
    except Exception:
        print("MSG", page.text_content("#scen-msg")); print("LOGS", [l["msg"] for l in app.logs()["lines"][-25:]]); print("RUN", app.run)
        raise
    assert "성공" in page.text_content("#scen-msg"), (page.text_content("#scen-msg"), app.logs()["lines"][-15:])
    assert w.app.scroll == 18 and w.app.dropped == ["SAMPLE-19"]
    page.click("#scen-save")
    page.wait_for_function("document.querySelector('#scen-msg').textContent.includes('저장했습니다')")
    with open(os.path.join(app.scen_dir, "e2e_drag.json"), encoding="utf-8") as f:
        steps = json.load(f)["steps"]
    assert steps[1] == {"action": "scroll", "amount": -6, "x": 600, "y": 400}
    assert steps[2] == {"action": "drag", "x": 600, "y": 170, "to": [1240, 440]}
    assert errors == [], errors
