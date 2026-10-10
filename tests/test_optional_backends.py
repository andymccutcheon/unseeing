from __future__ import annotations

import pytest

from unseeing.detectors.gliner import gliner_installed
from unseeing.detectors.ner import ner_available
from unseeing.detectors.presidio import presidio_available
from unseeing.errors import DetectorError
from unseeing.scrubber import Scrubber


def test_ner_missing_raises() -> None:
    if ner_available():
        pytest.skip("spaCy model is installed in this environment")
    with pytest.raises(DetectorError):
        Scrubber(use_ner=True)


def test_gliner_missing_raises() -> None:
    if gliner_installed():
        pytest.skip("GLiNER extra is installed in this environment")
    with pytest.raises(DetectorError):
        Scrubber(use_gliner=True).detect("Ada Lovelace")


def test_presidio_missing_raises() -> None:
    if presidio_available():
        pytest.skip("Presidio is installed in this environment")
    with pytest.raises(DetectorError):
        Scrubber(use_presidio=True)


@pytest.mark.skipif(not gliner_installed(), reason="unseeing[gliner] is not installed")
def test_gliner_detects_person_locally() -> None:
    detections = Scrubber(use_gliner=True, resume=False).detect(
        "Email Jane Doe at jane.doe@example.com about the invoice."
    )
    types = {item.type_name for item in detections}
    assert "EMAIL" in types or "PERSON" in types
