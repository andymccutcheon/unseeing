"""Detector protocol and overlap resolution."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from unseeing.types import Detection

PRIORITY: dict[str, int] = {
    "CREDIT_CARD": 100,
    "SSN": 95,
    "IBAN": 94,
    "NATIONAL_ID": 90,
    "CUSTOM": 92,
    "EMAIL": 88,
    "LINKEDIN": 86,
    "GITHUB": 85,
    "DATE_OF_BIRTH": 80,
    "PHONE": 75,
    "IP_ADDRESS": 70,
    "STREET_ADDRESS": 65,
    "URL": 50,
    "PERSON": 45,
    "ORGANIZATION": 40,
    "LOCATION": 35,
}


@runtime_checkable
class Detector(Protocol):
    name: str

    def detect(self, text: str) -> list[Detection]: ...


def resolve_overlaps(detections: list[Detection]) -> list[Detection]:
    """Keep higher-priority (then longer) spans; drop overlaps."""
    ordered = sorted(
        detections,
        key=lambda d: (-PRIORITY.get(d.type_name, 50), -(d.end - d.start), d.start),
    )
    kept: list[Detection] = []
    for item in ordered:
        if item.start >= item.end or item.start < 0:
            continue
        if any(not (item.end <= other.start or item.start >= other.end) for other in kept):
            continue
        kept.append(item)
    return sorted(kept, key=lambda d: d.start)
