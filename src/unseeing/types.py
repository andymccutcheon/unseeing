"""Shared types for detections, policy, and messages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    """Built-in entity labels used in placeholders and audit reports."""

    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    URL = "URL"
    IP_ADDRESS = "IP_ADDRESS"
    CREDIT_CARD = "CREDIT_CARD"
    SSN = "SSN"
    NATIONAL_ID = "NATIONAL_ID"
    IBAN = "IBAN"
    STREET_ADDRESS = "STREET_ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    LINKEDIN = "LINKEDIN"
    GITHUB = "GITHUB"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    CUSTOM = "CUSTOM"


# Placeholder labels are short, stable, and typed: <EMAIL_1>, <DOB_2>, <IP_1>.
PLACEHOLDER_LABELS: dict[str, str] = {
    EntityType.IP_ADDRESS.value: "IP",
    EntityType.STREET_ADDRESS.value: "ADDRESS",
    EntityType.DATE_OF_BIRTH.value: "DOB",
    EntityType.ORGANIZATION.value: "ORG",
    EntityType.LOCATION.value: "LOCATION",
}


def placeholder_label(entity_type: EntityType | str) -> str:
    name = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
    return PLACEHOLDER_LABELS.get(name, name)


@dataclass(frozen=True, slots=True)
class Detection:
    """A single detected span. ``value`` is the original surface form."""

    entity_type: EntityType | str
    start: int
    end: int
    value: str
    source: str = "regex"
    confidence: float = 1.0

    @property
    def type_name(self) -> str:
        if isinstance(self.entity_type, EntityType):
            return self.entity_type.value
        return str(self.entity_type)

    @property
    def label(self) -> str:
        return placeholder_label(self.type_name)


@dataclass(frozen=True, slots=True)
class CustomPattern:
    """A user-supplied regex that produces typed placeholders."""

    name: str
    pattern: str
    entity_type: str | None = None
    flags: int = 0

    @property
    def type_name(self) -> str:
        return self.entity_type or self.name


@dataclass(frozen=True, slots=True)
class DenyItem:
    """Always-scrub surface form, treated as ``entity_type`` (default PERSON)."""

    value: str
    entity_type: str = EntityType.PERSON.value


# JSON-like chat messages. Integrations accept these or SDK objects.
Message = dict[str, Any]
