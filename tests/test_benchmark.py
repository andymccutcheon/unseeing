"""Regression check on the six synthetic resumes — not a published accuracy claim.

Held-out precision / recall / F1 live in ``scripts/benchmark.py`` and the README.
This file only fails if a labeled fixture entity disappears after a detector change.
"""

from __future__ import annotations

from unseeing import Scrubber
from unseeing.types import EntityType
from unseeing.vault import normalize_value


def _match(detection_value: str, expected_value: str, entity_type: str) -> bool:
    return (
        normalize_value(entity_type, detection_value)
        == normalize_value(entity_type, expected_value)
        or expected_value.casefold() in detection_value.casefold()
    )


def _compatible(detected: str, expected: str) -> bool:
    aliases = {
        EntityType.STREET_ADDRESS.value: {"LOCATION"},
        EntityType.LINKEDIN.value: {"URL"},
        EntityType.GITHUB.value: {"URL"},
    }
    return expected in aliases.get(detected, set())


def _found(detections: list, entity: dict) -> bool:
    expected_type = entity["type"]
    expected_value = entity["value"]
    for detection in detections:
        if detection.type_name != expected_type and not _compatible(
            detection.type_name, expected_type
        ):
            continue
        if _match(detection.value, expected_value, expected_type):
            return True
    return False


def test_fixture_regression_finds_labeled_entities(labeled_documents: list[dict]) -> None:
    missed: list[str] = []
    for doc in labeled_documents:
        resume = doc.get("mode", "resume") == "resume"
        detections = Scrubber(resume=resume).detect(doc["text"])
        for entity in doc["entities"]:
            if not _found(detections, entity):
                missed.append(f"{doc['id']}: {entity['type']} {entity['value']!r}")
    assert missed == [], "fixture regression (not an accuracy claim):\n" + "\n".join(missed)
