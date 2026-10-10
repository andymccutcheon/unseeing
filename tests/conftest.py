from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "resumes.json"


@pytest.fixture(scope="session")
def labeled_documents() -> list[dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return list(payload["documents"])
