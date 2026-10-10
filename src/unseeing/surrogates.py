"""Deterministic Faker-style stand-ins for models that behave worse with tags."""

from __future__ import annotations

import hashlib

from unseeing.types import EntityType, placeholder_label

_FIRST = (
    "Jordan",
    "Riley",
    "Avery",
    "Quinn",
    "Morgan",
    "Casey",
    "Reese",
    "Skyler",
    "Cameron",
    "Harper",
    "Rowan",
    "Finley",
    "Elliot",
    "Parker",
    "Drew",
    "Sage",
    "Alex",
    "Jamie",
    "Taylor",
    "Blake",
)
_LAST = (
    "Blake",
    "Hayes",
    "Morgan",
    "Reed",
    "Sloan",
    "Walsh",
    "Bennett",
    "Carson",
    "Ellis",
    "Farrell",
    "Griffith",
    "Hale",
    "Ingram",
    "Keene",
    "Lang",
    "Nolan",
    "Porter",
    "Quincy",
    "Shaw",
    "Vance",
)
_STREETS = ("Oak", "Maple", "Pine", "Cedar", "Willow", "Harbor", "Summit", "Lake")
_CITIES = ("Springfield", "Fairview", "Madison", "Georgetown", "Franklin", "Clinton")
_STATES = ("IL", "OH", "OR", "MN", "WI", "CO")
_TLDS = ("example.com", "example.org", "example.net")


def _pick(value: str, entity_type: str, items: tuple[str, ...], salt: int = 0) -> str:
    digest = hashlib.sha256(f"{entity_type}:{salt}:{value.casefold()}".encode()).digest()
    return items[int.from_bytes(digest[:8], "big") % len(items)]


def generate_surrogate(entity_type: str, value: str, index: int) -> str:
    """Stable fake value for ``(entity_type, value)``. ``index`` breaks collisions."""
    label = placeholder_label(entity_type)
    kind = entity_type if entity_type in {e.value for e in EntityType} else label
    if kind in {EntityType.PERSON.value, "PERSON"}:
        first = _pick(value, kind, _FIRST, index)
        last = _pick(value, kind, _LAST, index + 17)
        return f"{first} {last}"
    if kind in {EntityType.EMAIL.value, "EMAIL"}:
        first = _pick(value, kind, _FIRST, index).lower()
        last = _pick(value, kind, _LAST, index + 3).lower()
        domain = _pick(value, kind, _TLDS, index)
        return f"{first}.{last}{index}@{domain}"
    if kind in {EntityType.PHONE.value, "PHONE"}:
        return f"+1-555-01{index:02d}-{1000 + (index % 9000):04d}"[:16]
    if kind in {EntityType.CREDIT_CARD.value, "CREDIT_CARD"}:
        # 5555... is reserved-looking; keep a Luhn-valid Visa test-shaped number.
        base = f"4111{index:04d}1111{index:04d}"[:15]
        return _luhn_complete(base)
    if kind in {EntityType.SSN.value, "SSN"}:
        return f"{200 + index:03d}-{10 + index % 80:02d}-{1000 + index:04d}"
    if kind in {EntityType.IBAN.value, "IBAN"}:
        return f"GB82WEST12345698765{index:03d}"[:22]
    if kind in {EntityType.STREET_ADDRESS.value, "STREET_ADDRESS", "ADDRESS"}:
        street = _pick(value, kind, _STREETS, index)
        city = _pick(value, kind, _CITIES, index)
        state = _pick(value, kind, _STATES, index)
        return f"{100 + index} {street} Street, {city}, {state} {60000 + index:05d}"
    if kind in {EntityType.DATE_OF_BIRTH.value, "DATE_OF_BIRTH", "DOB"}:
        return f"{1970 + index % 30:04d}-{(index % 12) + 1:02d}-{(index % 28) + 1:02d}"
    if kind in {EntityType.IP_ADDRESS.value, "IP_ADDRESS", "IP"}:
        return f"203.0.113.{(index % 250) + 1}"
    if kind in {EntityType.URL.value, "URL"}:
        return f"https://example.com/p/{index}"
    if kind in {EntityType.LINKEDIN.value, "LINKEDIN"}:
        return f"https://www.linkedin.com/in/example-user-{index}"
    if kind in {EntityType.GITHUB.value, "GITHUB"}:
        return f"https://github.com/example-user-{index}"
    if kind in {EntityType.ORGANIZATION.value, "ORGANIZATION", "ORG"}:
        return f"Example { _pick(value, kind, _LAST, index)} Group"
    if kind in {EntityType.LOCATION.value, "LOCATION"}:
        return _pick(value, kind, _CITIES, index)
    if kind in {EntityType.NATIONAL_ID.value, "NATIONAL_ID"}:
        return f"AB {10 + index:02d} {20 + index:02d} {30 + index:02d} C"
    return f"Example-{label}-{index}"


def _luhn_complete(digits15: str) -> str:
    digits15 = "".join(ch for ch in digits15 if ch.isdigit())[:15].ljust(15, "0")
    for last in range(10):
        candidate = digits15 + str(last)
        total = 0
        alt = False
        for char in reversed(candidate):
            num = ord(char) - 48
            if alt:
                num *= 2
                if num > 9:
                    num -= 9
            total += num
            alt = not alt
        if total % 10 == 0:
            return candidate
    return digits15 + "0"
