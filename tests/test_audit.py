from __future__ import annotations

from unseeing import Scrubber


def test_audit_never_includes_originals() -> None:
    scrubber = Scrubber(resume=True)
    scrubber.scrub("Ava Chen\nava.chen@example.com\n+1-555-010-0142\n")
    report = scrubber.audit()
    rendered = report.format()
    payload = report.to_dict()
    assert "ava.chen@example.com" not in rendered
    assert "Ava Chen" not in rendered
    assert "+1-555" not in rendered
    assert "EMAIL" in report.counts
    assert payload["total"] == report.total >= 2
    assert "ada" not in str(payload).lower()
