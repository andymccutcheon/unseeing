"""User-supplied regex patterns and allow/deny surface forms."""

from __future__ import annotations

import re
from collections.abc import Sequence

from unseeing.types import CustomPattern, DenyItem, Detection, EntityType


class CustomDetector:
    name = "custom"

    def __init__(self, patterns: Sequence[CustomPattern] = ()) -> None:
        self._compiled = [
            (spec, re.compile(spec.pattern, spec.flags)) for spec in patterns if spec.pattern
        ]

    def detect(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        for spec, compiled in self._compiled:
            for match in compiled.finditer(text):
                found.append(
                    Detection(
                        spec.type_name,
                        match.start(),
                        match.end(),
                        match.group(0),
                        source="custom",
                    )
                )
        return found


def deny_detections(text: str, items: Sequence[str | DenyItem]) -> list[Detection]:
    found: list[Detection] = []
    for item in items:
        if isinstance(item, DenyItem):
            value, entity = item.value, item.entity_type
        else:
            value, entity = item, EntityType.PERSON.value
        if len(value) < 2:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(value)}(?!\w)", re.I)
        for match in pattern.finditer(text):
            found.append(
                Detection(entity, match.start(), match.end(), match.group(0), source="deny")
            )
    return found
