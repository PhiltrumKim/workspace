# -*- coding: utf-8 -*-
"""GHOST CLI.

  python -m ghost run scenarios/demo_run_recipe.json --sim     시뮬레이터로 시나리오 실행
  python -m ghost run my.json                                    실장비로 실행
  python -m ghost validate scenarios/*.json                      시나리오 검증
  python -m ghost sim-assets                                     시뮬레이터용 템플릿 생성
  python -m ghost migrate --legacy ../magewell_rpa --out legacy  레거시 workflow/recipe/objects 변환
  python -m ghost probe [--smoke]                                COM 포트/캡처 확인 (+홈잉·커서 실측, 클릭 없음)
  python -m ghost watch rules.json [--duration 60]               화면 상시 감시 (시나리오 없이)
  python -m ghost run my.json --watch rules.json                 실행 중 추가 감시 규칙 적용
  python -m ghost editor [--sim]                                 시나리오 편집기 (http://127.0.0.1:8765)
  python -m ghost fetch-models                                   한국어 OCR 모델 다운로드
  python -m ghost ocr [shot.png] [--region x,y,w,h]              화면 글자/좌표 출력 (target·read 영역 잡기용)
  python -m ghost add-target NAME --text "저장 안 함" [--box ..]   텍스트(OCR) target 등록
  python -m ghost snap shot.png                                  실장비 화면 1장 저장
  python -m ghost add-target NAME --image shot.png --box x,y,w,h 스크린샷에서 target 등록
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

from . import build_device, build_runner, config
from .registry import Registry
from .scenario import model
from .surveillance import load_rules


def _log(msg: str) -> None:
    print(msg, flush=True)


def _cfg(args, sim=False):
    return config.load(args.config, sim=sim)


def cmd_run(args) -> int:
    cfg = _cfg(args, sim=args.sim)
    dev = build_device(cfg, sim=args.sim, log=_log)
    runner = build_runner(cfg, dev, log=_log)
    try:
        sc = model.load(args.scenario, runner.reg)
    except model.ScenarioError as e:
        for err in e.errors:
            _log(f"  ✗ {err}")
        return 2
    if os.path.dirname(os.path.abspath(args.scenario)) not in runner.scenario_dirs:
        runner.scenario_dirs.insert(0, os.path.dirname(os.path.abspath(args.scenario)))
    if args.watch:
        runner.base_watch = load_rules(os.path.abspath(args.watch))
    if args.sim and args.sim_alarm is not None:
        dev.video.world.app.schedule_alarm(args.sim_alarm, "PRESSURE LOW")
    params = {}
    for kv in args.param or []:
        if "=" not in kv:
            _log(f"  ✗ --param 형식은 이름=값: {kv}")
            return 2
        k, v = kv.split("=", 1)
        params[k.strip()] = v
    dev.open(home=not args.no_home)
    try:
        res = runner.run(sc, params)
    except model.ScenarioError as e:
        for err in e.errors:
            _log(f"  ✗ {err}")
        return 2
    except KeyboardInterrupt:
        runner.stop_event.set()
        return 130
    finally:
        dev.close()
    _log(f"블랙박스: {res.run_dir}")
    _log(f"커서 통계: {dev.stats}  gain={[round(g, 3) for g in dev.gain]}")
    if res.watch_events:
        _log(f"감시 이벤트 {len(res.watch_events)}건" + (f", 중단 규칙: {res.aborted_by}" if res.aborted_by else ""))
    return 0 if res.ok else 1


def cmd_watch(args) -> int:
    cfg = _cfg(args, sim=args.sim)
    rules_path = os.path.abspath(args.rules)
    rules = load_rules(rules_path)
    dev = build_device(cfg, sim=args.sim, log=_log)
    runner = build_runner(cfg, dev, log=_log)
    runner.scenario_dirs.insert(0, os.path.dirname(rules_path))
    needs_mouse = any(r.get("action") == "handler" for r in rules)
    if args.sim and args.sim_alarm is not None:
        dev.video.world.app.schedule_alarm(args.sim_alarm, "PRESSURE LOW")
    dev.open(home=needs_mouse)      # 핸들러가 클릭할 수 있으므로 홈잉 (알림만이면 커서를 건드리지 않음)
    try:
        res = runner.watch_only(rules, duration=args.duration, interval=args.interval)
    finally:
        dev.close()
    _log(f"감시 종료: 이벤트 {len(res.watch_events)}건" + (f", 중단 규칙: {res.aborted_by}" if res.aborted_by else ""))
    _log(f"블랙박스: {res.run_dir}")
    return 0 if res.ok else 1


def cmd_validate(args) -> int:
    cfg = _cfg(args, sim=args.sim)
    reg = Registry(config.path(cfg, "objects"))
    bad = 0
    files = [f for pat in args.files for f in (glob.glob(pat) or [pat])]
    for f in files:
        try:
            import json
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "rules" in data and "steps" not in data:   # 감시 규칙 파일
                from .surveillance import validate_rules
                errs = validate_rules(data["rules"], reg)
                if errs:
                    raise model.ScenarioError(errs)
            else:
                model.load(f, reg)
            _log(f"✓ {f}")
        except model.ScenarioError as e:
            bad += 1
            _log(f"✗ {f}")
            for err in e.errors:
                _log(f"    {err}")
    return 1 if bad else 0


def cmd_sim_assets(args) -> int:
    from .sim import export_templates
    cfg = _cfg(args, sim=True)
    out = args.out or config.path(cfg, "objects")
    names = export_templates(Registry(out))
    _log(f"{len(names)}개 템플릿 → {out}: {', '.join(names)}")
    return 0


def cmd_migrate(args) -> int:
    import shutil
    src, out = args.legacy, args.out
    os.makedirs(os.path.join(out, "scenarios"), exist_ok=True)
    obj_src = os.path.join(src, "objects")
    if os.path.isdir(obj_src):
        shutil.copytree(obj_src, os.path.join(out, "objects"), dirs_exist_ok=True)
        _log(f"objects 복사: {obj_src}")
    n = 0
    for sub in ("workflows", "recipes"):
        for f in sorted(glob.glob(os.path.join(src, sub, "*.json"))):
            import json
            with open(f, encoding="utf-8") as fh:
                old = json.load(fh)
            try:
                sc = model.from_legacy(old)
            except model.ScenarioError as e:
                _log(f"✗ {f}: {e}")
                continue
            model.save(sc, os.path.join(out, "scenarios", sc["name"] + ".json"))
            n += 1
    _log(f"{n}개 시나리오 변환 → {os.path.join(out, 'scenarios')}")
    return 0


def cmd_probe(args) -> int:
    cfg = _cfg(args)
    hw = cfg["hardware"]
    try:
        from serial.tools import list_ports
        _log("[serial] " + (", ".join(f"{p.device}({p.description})" for p in list_ports.comports()) or "없음"))
    except ImportError:
        _log("[serial] pyserial 미설치")
    from .hal.capture import CaptureVideo
    cap = CaptureVideo(hw["camera"], hw["width"], hw["height"], hw["backend"])
    try:
        cap.open()
        f = cap.read()
        _log(f"[video] camera {hw['camera']} OK frame={f.shape[1]}x{f.shape[0]} mean={f.mean():.1f}")
    except Exception as e:
        _log(f"[video] camera {hw['camera']} 실패: {e}")
        return 1
    finally:
        cap.close()
    if not args.smoke:
        return 0
    # 스모크: 홈잉 + 커서 실측 + 클릭 없는 이동 검증
    dev = build_device(cfg, log=_log)
    dev.open(home=True)
    try:
        import cv2
        w, h = hw["width"], hw["height"]
        pts = [(w // 2, h // 2), (w // 4, h // 4), (3 * w // 4, h // 2)]
        for p in pts:
            t0 = time.monotonic()
            got = dev.move_to(*p)
            _log(f"[smoke] move_to{p} → {got} measured={dev.measured} ({time.monotonic() - t0:.1f}s)")
        cv2.imwrite(args.out, dev.frame())
        _log(f"[smoke] gain={[round(g, 3) for g in dev.gain]} stats={dev.stats} frame → {args.out}")
    finally:
        dev.close()
    return 0


def cmd_snap(args) -> int:
    import cv2
    from .hal.capture import CaptureVideo
    hw = _cfg(args)["hardware"]
    cap = CaptureVideo(hw["camera"], hw["width"], hw["height"], hw["backend"])
    cap.open()
    try:
        cv2.imwrite(args.out, cap.read())
    finally:
        cap.close()
    _log(f"saved {args.out}")
    return 0


def cmd_add_target(args) -> int:
    import cv2
    cfg = _cfg(args, sim=args.sim)
    reg = Registry(config.path(cfg, "objects"))
    if args.text:                                   # 텍스트(OCR) target: 이미지 없이 등록
        meta = {"match": args.match, "scale": args.scale}
        if args.box:
            meta["region"] = [int(v) for v in args.box.split(",")]
        if args.offset:
            meta["click_offset"] = [int(v) for v in args.offset.split(",")]
        reg.add_text(args.name, args.text, **meta)
        _log(f"텍스트 target '{args.name}' = {args.text!r} 등록 → {reg.root}")
        return 0
    if not (args.image and args.box):
        _log("--image 와 --box 가 필요합니다 (텍스트 target 은 --text)")
        return 2
    img = cv2.imread(args.image)
    if img is None:
        _log(f"이미지 읽기 실패: {args.image}")
        return 1
    x, y, w, h = (int(v) for v in args.box.split(","))
    meta = {"threshold": args.threshold, "hint": [x + w // 2, y + h // 2]}
    if args.color_tol is not None:
        meta["color_tol"] = args.color_tol
    if args.offset:
        meta["click_offset"] = [int(v) for v in args.offset.split(",")]
    reg.add(args.name, img[y:y + h, x:x + w].copy(), **meta)
    _log(f"target '{args.name}' 등록 → {reg.root}")
    return 0


def cmd_editor(args) -> int:
    from .editor import EditorApp, serve
    cfg = _cfg(args, sim=args.sim)
    app = EditorApp(cfg, sim=args.sim)
    _log(f"[편집기] 장치 연결 중 ({'시뮬레이터' if args.sim else '실장비 ' + cfg['hardware']['port']})...")
    app.open()
    httpd = serve(app, args.port)
    _log(f"[편집기] 브라우저에서 여세요: http://127.0.0.1:{args.port}   (종료: Ctrl+C)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        app.close()
    return 0


def cmd_ocr(args) -> int:
    import cv2
    from .vision.ocr import OcrEngine
    cfg = _cfg(args, sim=args.sim)
    if args.image:
        img = cv2.imread(args.image)
        if img is None:
            _log(f"이미지 읽기 실패: {args.image}")
            return 1
    else:
        from .hal.capture import CaptureVideo
        hw = cfg["hardware"]
        cap = CaptureVideo(hw["camera"], hw["width"], hw["height"], hw["backend"])
        cap.open()
        try:
            img = cap.read()
        finally:
            cap.close()
    region = [int(v) for v in args.region.split(",")] if args.region else None
    eng = OcrEngine(cfg, cfg["_base_dir"], _log)
    t0 = time.monotonic()
    hits = eng.read(img, region, args.scale)
    _log(f"[ocr] 모델={eng.model} {len(hits)}개 {time.monotonic() - t0:.2f}s")
    for h in hits:
        x, y, w, hh = h.box
        _log(f"  {h.conf:.2f}  box={x},{y},{w},{hh}  center={h.center}  {h.text!r}")
    return 0


def cmd_fetch_models(args) -> int:
    """한국어 인식 모델(PaddlePaddle korean_PP-OCRv5_mobile_rec, Apache-2.0) 다운로드 + dict.txt 생성."""
    import urllib.request
    import yaml
    from .vision.ocr import KOREAN_MODEL_DIR, KOREAN_MODEL_REPO
    cfg = _cfg(args)
    d = os.path.join(cfg["_base_dir"], KOREAN_MODEL_DIR)
    os.makedirs(d, exist_ok=True)
    for fn in ("inference.onnx", "inference.yml"):
        path = os.path.join(d, fn)
        if os.path.exists(path) and not args.force:
            _log(f"있음: {path}")
            continue
        url = f"https://huggingface.co/{KOREAN_MODEL_REPO}/resolve/main/{fn}"
        _log(f"다운로드: {url}")
        urllib.request.urlretrieve(url, path)
    with open(os.path.join(d, "inference.yml"), encoding="utf-8") as f:
        chars = yaml.safe_load(f)["PostProcess"]["character_dict"]
    with open(os.path.join(d, "dict.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(chars))
    _log(f"완료: {d} (문자 {len(chars)}개)")
    return 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="ghost", description="GHOST GUI 자동화 엔진")
    p.add_argument("--config", help="설정 파일 (기본: ./ghost.json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run", help="시나리오 실행")
    s.add_argument("scenario")
    s.add_argument("--sim", action="store_true", help="시뮬레이터로 실행")
    s.add_argument("--no-home", action="store_true", help="시작 시 홈잉 생략")
    s.add_argument("--watch", help="추가 감시 규칙 파일")
    s.add_argument("--param", action="append", help="시나리오 파라미터 이름=값 (여러 번 지정 가능)")
    s.add_argument("--sim-alarm", type=float, help="(시뮬레이터) N초 뒤 알람 팝업 발생")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("watch", help="화면 상시 감시")
    s.add_argument("rules", help='감시 규칙 파일 {"rules": [...]}')
    s.add_argument("--sim", action="store_true")
    s.add_argument("--duration", type=float, help="감시 시간(초). 생략 시 Ctrl+C 까지")
    s.add_argument("--interval", type=float, help="감시 주기(초)")
    s.add_argument("--sim-alarm", type=float, help="(시뮬레이터) N초 뒤 알람 팝업 발생")
    s.set_defaults(fn=cmd_watch)

    s = sub.add_parser("validate", help="시나리오 검증")
    s.add_argument("files", nargs="+")
    s.add_argument("--sim", action="store_true", help="시뮬레이터 objects 기준으로 target 확인")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("sim-assets", help="시뮬레이터용 템플릿 생성")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_sim_assets)

    s = sub.add_parser("migrate", help="레거시 magewell_rpa 변환")
    s.add_argument("--legacy", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_migrate)

    s = sub.add_parser("probe", help="장비 확인")
    s.add_argument("--smoke", action="store_true", help="홈잉·이동·커서 실측까지 (클릭 없음)")
    s.add_argument("--out", default="probe.png")
    s.set_defaults(fn=cmd_probe)

    s = sub.add_parser("snap", help="화면 1장 저장")
    s.add_argument("out")
    s.set_defaults(fn=cmd_snap)

    s = sub.add_parser("add-target", help="스크린샷 영역을 target 으로 등록")
    s.add_argument("name")
    s.add_argument("--image")
    s.add_argument("--box", help="x,y,w,h (텍스트 target 이면 OCR 탐색 영역)")
    s.add_argument("--text", help="텍스트(OCR) target 으로 등록할 문자열")
    s.add_argument("--match", default=None, help="exact | contains | regex | fuzzy")
    s.add_argument("--scale", type=float, help="OCR 확대 배율 (작은 글씨)")
    s.add_argument("--offset", help="클릭 위치 보정 dx,dy")
    s.add_argument("--threshold", type=float)
    s.add_argument("--color-tol", type=float, help="색 검증 허용치 (배경색으로 상태가 구분되는 target)")
    s.add_argument("--sim", action="store_true")
    s.set_defaults(fn=cmd_add_target)

    s = sub.add_parser("ocr", help="이미지(또는 실장비 화면)의 글자와 좌표 출력")
    s.add_argument("image", nargs="?", help="이미지 파일 (생략 시 실장비 화면 캡처)")
    s.add_argument("--region", help="x,y,w,h")
    s.add_argument("--scale", type=float)
    s.add_argument("--sim", action="store_true")
    s.set_defaults(fn=cmd_ocr)

    s = sub.add_parser("editor", help="시나리오 편집기 (로컬 웹)")
    s.add_argument("--sim", action="store_true", help="시뮬레이터로 실행")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_editor)

    s = sub.add_parser("fetch-models", help="한국어 OCR 인식 모델 다운로드")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_fetch_models)

    args = p.parse_args(argv)
    return args.fn(args)
