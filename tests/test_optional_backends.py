from __future__ import annotations

import pytest

from unseeing.detectors.ner import ner_available
from unseeing.detectors.presidio import presidio_available
from unseeing.errors import DetectorError
from unseeing.scrubber import Scrubber


def test_ner_missing_raises() -> None:
    if ner_available():
        pytest.skip("spaCy model is installed in this environment")
    with pytest.raises(DetectorError):
        Scrubber(use_ner=True)


def test_presidio_missing_raises() -> None:
    if presidio_available():
        pytest.skip("Presidio is installed in this environment")
    with pytest.raises(DetectorError):
        Scrubber(use_presidio=True)
