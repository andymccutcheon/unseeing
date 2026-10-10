from __future__ import annotations

from unseeing import Scrubber


def test_header_name_and_first_name_alias() -> None:
    resume = "Ava Chen\nEngineer\nava.chen@example.com\nAva shipped two teams.\n"
    scrubber = Scrubber(resume=True)
    out = scrubber.scrub(resume)
    assert "Ava Chen" not in out
    assert "ava.chen@example.com" not in out
    # Follow-up turn reuses the vault and the first-name alias.
    follow = scrubber.scrub("Should we interview Ava this week?")
    assert "Ava" not in follow
    assert "<PERSON_1>" in follow
    assert "Ava" in scrubber.restore(follow)


def test_orgs_kept_by_default() -> None:
    text = "Ava Chen\nEXPERIENCE\nEngineer at Globex Robotics — 2021\n"
    kept = Scrubber(resume=True).scrub(text)
    assert "Globex Robotics" in kept
    scrubbed = Scrubber(resume=True, scrub_orgs=True).scrub(text)
    assert "Globex Robotics" not in scrubbed
    assert "<ORG_" in scrubbed


def test_school_when_enabled() -> None:
    text = "Priya Nair\nEDUCATION\nUniversity of Springfield, B.S. CS\n"
    out = Scrubber(resume=True, scrub_orgs=True).scrub(text)
    assert "University of Springfield" not in out
