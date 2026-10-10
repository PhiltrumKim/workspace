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
    assert page.locator("#steps li.step").count() == 9

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
