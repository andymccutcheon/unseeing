"""Audit reports: what was found, never the original values."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AuditReport:
    """Counts by entity type. Designed to be logged safely."""

    counts: dict[str, int] = field(default_factory=dict)
    total: int = 0
    sources: dict[str, int] = field(default_factory=dict)

    def format(self) -> str:
        if not self.counts:
            return "No PII detected."
        width = max(len(name) for name in self.counts) + 2
        lines = [f"{name:<{width}}{count}" for name, count in sorted(self.counts.items())]
        lines.append(f"{'Total':<{width}}{self.total}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {"counts": dict(self.counts), "total": self.total, "sources": dict(self.sources)}
