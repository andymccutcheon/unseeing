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


def score_documents(documents: list[dict]) -> dict[str, object]:
    """Score unique (type, normalized value) pairs, not repeated spans."""
    per_type: dict[str, dict[str, int]] = {}
    total = {"tp": 0, "fp": 0, "fn": 0}

    def bucket(name: str) -> dict[str, int]:
        return per_type.setdefault(name, {"tp": 0, "fp": 0, "fn": 0})

    for doc in documents:
        resume = doc.get("mode", "resume") == "resume"
        scrubber = Scrubber(resume=resume)
        detections = scrubber.detect(doc["text"])
        gold = {(entity["type"], entity["value"]) for entity in doc["entities"]}
        pred = {(detection.type_name, detection.value) for detection in detections}
        used_pred: set[tuple[str, str]] = set()
        for entity_type, expected in gold:
            hit = None
            for detected_type, detected_value in pred:
                if (detected_type, detected_value) in used_pred:
                    continue
                if detected_type != entity_type and not _compatible(detected_type, entity_type):
                    continue
                if _match(detected_value, expected, entity_type):
                    hit = (detected_type, detected_value)
                    break
            target = bucket(entity_type)
            if hit is None:
                target["fn"] += 1
                total["fn"] += 1
            else:
                used_pred.add(hit)
                target["tp"] += 1
                total["tp"] += 1
        for detected_type, detected_value in pred:
            if (detected_type, detected_value) in used_pred:
                continue
            bucket(detected_type)["fp"] += 1
            total["fp"] += 1

    def rates(row: dict[str, int]) -> dict[str, float]:
        prec = row["tp"] / (row["tp"] + row["fp"]) if row["tp"] + row["fp"] else 1.0
        rec = row["tp"] / (row["tp"] + row["fn"]) if row["tp"] + row["fn"] else 1.0
        return {"precision": prec, "recall": rec, **row}

    return {
        "overall": rates(total),
        "by_type": {name: rates(row) for name, row in sorted(per_type.items())},
    }


def _compatible(detected: str, expected: str) -> bool:
    aliases = {
        EntityType.STREET_ADDRESS.value: {"LOCATION"},
        EntityType.LINKEDIN.value: {"URL"},
        EntityType.GITHUB.value: {"URL"},
    }
    return expected in aliases.get(detected, set())


def test_fixture_precision_recall(labeled_documents: list[dict]) -> None:
    report = score_documents(labeled_documents)
    overall = report["overall"]
    assert overall["recall"] >= 0.85
    assert overall["precision"] >= 0.80
    # Core identifiers should be essentially exact on the synthetic set.
    for key in ("EMAIL", "PHONE", "SSN", "IBAN", "CREDIT_CARD"):
        if key in report["by_type"]:
            assert report["by_type"][key]["recall"] == 1.0
            assert report["by_type"][key]["precision"] == 1.0
