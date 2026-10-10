import json
import os
import shutil

import pytest

from ghost import config
from ghost.registry import Registry
from ghost.sim import export_templates

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def sim_objects(tmp_path_factory):
    d = tmp_path_factory.mktemp("sim_objects")
    export_templates(Registry(str(d)))
    return str(d)


@pytest.fixture
def cfg(tmp_path, sim_objects):
    """시뮬레이터 설정 (작업 디렉터리의 ghost.json 과 무관하게 tmp 경로 사용)."""
    scen = tmp_path / "scenarios"
    shutil.copytree(os.path.join(ROOT, "scenarios", "sim"), scen)
    p = tmp_path / "ghost.json"
    p.write_text(json.dumps({"paths": {"objects": sim_objects, "scenarios": str(scen),
                                       "runs": str(tmp_path / "runs")}}), encoding="utf-8")
    c = config.load(str(p), sim=True)
    model = os.path.join(ROOT, "models", "korean_PP-OCRv5_mobile_rec")
    if os.path.isdir(model):                         # 받아 둔 한국어 OCR 모델 사용 (없으면 기본 모델)
        c["ocr"]["rec_model"] = model
    return c
