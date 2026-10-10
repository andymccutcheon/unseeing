from __future__ import annotations

from unseeing import Scrubber
from unseeing.types import EntityType

CASES: list[tuple[str, set[str]]] = [
    ("Python 3.10.12 is great", {EntityType.IP_ADDRESS.value}),
    ("See section 3.2.1.4 of the RFC", {EntityType.IP_ADDRESS.value}),
    ("The year 2020-2024 was busy", {EntityType.DATE_OF_BIRTH.value, EntityType.PHONE.value}),
    ("Call me Ishmael", {EntityType.PHONE.value, EntityType.EMAIL.value}),
    ("SSNs are sensitive identifiers", {EntityType.SSN.value}),
    ("I scored 1234567890 points", {EntityType.PHONE.value, EntityType.CREDIT_CARD.value}),
    ("Version 1.2.3 shipped", {EntityType.IP_ADDRESS.value}),
    ("Meeting at 3:00 in room 404", {EntityType.PHONE.value}),
    ("github.com/torvalds/linux is a repository", {EntityType.GITHUB.value}),
    ("January 2020 – June 2022 at work", {EntityType.DATE_OF_BIRTH.value}),
    ("Acme Corp is hiring engineers", {EntityType.PERSON.value}),
    ("The Supreme Court issued an opinion", {EntityType.STREET_ADDRESS.value}),
    ("Copy the file from the Hard Drive", {EntityType.STREET_ADDRESS.value}),
    (
        "A valid card number is required",
        {EntityType.NATIONAL_ID.value, EntityType.CREDIT_CARD.value},
    ),
]


def test_common_false_positives() -> None:
    scrubber = Scrubber()
    for text, forbidden in CASES:
        types = {item.type_name for item in scrubber.detect(text)}
        assert types.isdisjoint(forbidden), f"{text!r} produced {types & forbidden}"
