"""Session vault: stable placeholder ↔ original mapping."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from unseeing.audit import AuditReport
from unseeing.crypto import decrypt, encrypt
from unseeing.errors import VaultError
from unseeing.restore import Mapping, StreamRestorer, restore_text
from unseeing.surrogates import generate_surrogate
from unseeing.types import placeholder_label

_PLACEHOLDER_IN_TEXT = re.compile(r"[<\(\[]([A-Za-z][A-Za-z0-9]*_\d+)[>\)\]]")


def normalize_value(entity_type: str, value: str) -> str:
    compact = value.strip()
    if entity_type in {"EMAIL", "PERSON", "ORGANIZATION", "LOCATION", "URL", "LINKEDIN", "GITHUB"}:
        return re.sub(r"\s+", " ", compact).casefold()
    if entity_type in {"PHONE", "CREDIT_CARD", "SSN", "IP_ADDRESS"}:
        return "".join(ch for ch in compact if ch.isdigit() or ch in ".:")
    if entity_type == "IBAN":
        return re.sub(r"\s+", "", compact).upper()
    if entity_type == "NATIONAL_ID":
        return re.sub(r"\s+", "", compact).upper()
    return compact.casefold()


class Vault:
    """Holds the reversible map for one session (one resume, or a conversation).

    The same normalized entity always receives the same placeholder. In-memory
    by default; :meth:`save` / :meth:`load` persist JSON, optionally encrypted
    with a password.
    """

    def __init__(self, *, use_surrogates: bool = False) -> None:
        self.use_surrogates = use_surrogates
        self._norm_to_token: dict[tuple[str, str], str] = {}
        self._token_to_original: dict[str, str] = {}
        self._token_to_display: dict[str, str] = {}
        self._token_to_type: dict[str, str] = {}
        self._counts: dict[str, int] = {}
        self._reserved: set[str] = set()

    def __len__(self) -> int:
        return len(self._token_to_original)

    def mappings(self) -> list[Mapping]:
        return [
            Mapping(token, self._token_to_original[token], self._token_to_display[token])
            for token in self._token_to_original
        ]

    def reserve_from(self, text: str) -> None:
        """Avoid colliding with placeholder-like tokens already in the input."""
        for match in _PLACEHOLDER_IN_TEXT.finditer(text):
            token = match.group(1).upper()
            self._reserved.add(token)
            label, _, index = token.rpartition("_")
            if label and index.isdigit():
                self._counts[label] = max(self._counts.get(label, 0), int(index))

    def register(self, entity_type: str, value: str) -> str:
        """Return the display replacement (tag or surrogate) for ``value``."""
        label = placeholder_label(entity_type)
        key = (label, normalize_value(entity_type, value))
        existing = self._norm_to_token.get(key)
        if existing is not None:
            return self._token_to_display[existing]
        token = self._mint(label)
        self._norm_to_token[key] = token
        self._token_to_original[token] = value
        self._token_to_type[token] = entity_type
        display = generate_surrogate(entity_type, value, self._counts[label]) if self.use_surrogates else f"<{token}>"
        self._token_to_display[token] = display
        return display

    def alias(self, entity_type: str, value: str, canonical: str) -> None:
        """Map an extra surface form onto the same token as ``canonical``."""
        label = placeholder_label(entity_type)
        canon_key = (label, normalize_value(entity_type, canonical))
        token = self._norm_to_token.get(canon_key)
        if token is None:
            self.register(entity_type, canonical)
            token = self._norm_to_token[canon_key]
        alias_key = (label, normalize_value(entity_type, value))
        self._norm_to_token[alias_key] = token

    def lookup_display(self, entity_type: str, value: str) -> str | None:
        label = placeholder_label(entity_type)
        token = self._norm_to_token.get((label, normalize_value(entity_type, value)))
        if token is None:
            return None
        return self._token_to_display[token]

    def restore(self, text: str) -> str:
        return restore_text(text, self.mappings())

    def stream_restorer(self) -> StreamRestorer:
        return StreamRestorer(self.mappings())

    def audit(self) -> AuditReport:
        counts: dict[str, int] = {}
        for entity_type in self._token_to_type.values():
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return AuditReport(counts=counts, total=sum(counts.values()))

    def _mint(self, label: str) -> str:
        n = self._counts.get(label, 0) + 1
        while f"{label}_{n}" in self._reserved or f"{label}_{n}" in self._token_to_original:
            n += 1
        self._counts[label] = n
        return f"{label}_{n}"

    def to_payload(self) -> dict[str, object]:
        entries = []
        for token, original in self._token_to_original.items():
            entries.append(
                {
                    "token": token,
                    "original": original,
                    "display": self._token_to_display[token],
                    "entity_type": self._token_to_type[token],
                }
            )
        return {
            "version": 1,
            "use_surrogates": self.use_surrogates,
            "entries": entries,
            "reserved": sorted(self._reserved),
            "counts": self._counts,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> Vault:
        vault = cls(use_surrogates=bool(payload.get("use_surrogates")))
        reserved = payload.get("reserved") or []
        if isinstance(reserved, list):
            vault._reserved = {str(item) for item in reserved}
        counts = payload.get("counts") or {}
        if isinstance(counts, dict):
            vault._counts = {str(k): int(v) for k, v in counts.items()}
        entries = payload.get("entries") or []
        if isinstance(entries, list):
            for raw in entries:
                if not isinstance(raw, dict):
                    continue
                token = str(raw["token"])
                original = str(raw["original"])
                display = str(raw.get("display") or f"<{token}>")
                entity_type = str(raw.get("entity_type") or "CUSTOM")
                vault._token_to_original[token] = original
                vault._token_to_display[token] = display
                vault._token_to_type[token] = entity_type
                label = placeholder_label(entity_type)
                vault._norm_to_token[(label, normalize_value(entity_type, original))] = token
        return vault

    def dumps(self, *, key: str | None = None) -> bytes:
        blob = json.dumps(self.to_payload(), indent=2).encode("utf-8")
        if key:
            return encrypt(blob, key)
        return blob

    @classmethod
    def loads(cls, data: bytes | str, *, key: str | None = None) -> Vault:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if key:
            raw = decrypt(raw, key)
        elif raw.startswith(b"UNSEE1"):
            raise VaultError("vault is encrypted; pass key=...")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultError("vault is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise VaultError("vault payload must be an object")
        return cls.from_payload(payload)

    def save(self, path: str | Path, *, key: str | None = None) -> None:
        Path(path).write_bytes(self.dumps(key=key))

    @classmethod
    def load(cls, path: str | Path, *, key: str | None = None) -> Vault:
        return cls.loads(Path(path).read_bytes(), key=key)

    def originals(self) -> Iterable[str]:
        return self._token_to_original.values()
