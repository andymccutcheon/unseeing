"""Resume- and HR-aware heuristics for names, employers, and schools."""

from __future__ import annotations

import re

from unseeing.types import Detection, EntityType

_SECTION = re.compile(
    r"^(?:experience|work experience|employment|education|skills|summary|"
    r"objective|profile|projects|certifications|awards|publications|"
    r"references|technical skills|professional experience|work history|"
    r"academic background|contact|about)$",
    re.I,
)

_NAME_LINE = re.compile(
    r"""^
    (?:(?:Dr|Mr|Mrs|Ms|Mx|Prof)\.?\s+)?
    [A-Z][A-Za-z'’\-]+
    (?:\s+[A-Z]\.?)?
    (?:\s+[A-Z][A-Za-z'’\-]+){1,3}
    (?:,?\s+(?:Jr|Sr|III|IV|PhD|MD)\.?)?
    $
    """,
    re.VERBOSE,
)

_NAME_LABELED = re.compile(
    r"^(?:name|candidate|applicant)\s*[:\-]\s*(.+)$",
    re.I,
)

_TITLE_WORDS = re.compile(
    r"\b(engineer|manager|developer|designer|analyst|director|consultant|"
    r"specialist|intern|lead|architect|scientist|officer|president|"
    r"founder|researcher|programmer|administrator|coordinator|recruiter|"
    r"teacher|professor|attorney|lawyer|nurse|physician)\b",
    re.I,
)

_NOT_NAMES = frozenset(
    {
        "curriculum vitae",
        "resume",
        "cover letter",
        "references",
        "work history",
        "work experience",
        "technical skills",
        "new york",
        "san francisco",
        "los angeles",
        "united states",
        "united kingdom",
        "software engineer",
        "data scientist",
        "product manager",
    }
)

_SCHOOL_HINT = re.compile(
    r"\b(University|College|Institute|School|Academy|Polytechnic|Université)\b"
)

_TITLE_AT_ORG = re.compile(
    r"(?:^|[\s,;])(?:at|@)\s+([A-Z][\w&.'’\- ]{1,60}?)(?=\s*[—\-|(\d,]|$)",
)

_COMPANY_LINE = re.compile(
    r"^([A-Z][\w&.'’\-]+(?:\s+[A-Z][\w&.'’\-]+){0,5})\s*[—\-|,:]\s+\S+",
)


def _line_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        spans.append((start, start + len(body), body.strip()))
        start += len(line)
    return spans


def _is_name_line(line: str) -> bool:
    if not line or line.casefold() in _NOT_NAMES:
        return False
    if _TITLE_WORDS.search(line):
        return False
    if "@" in line or "http" in line.casefold() or "linkedin" in line.casefold():
        return False
    return bool(_NAME_LINE.match(line))


def detect_resume(text: str, *, scrub_orgs: bool = False) -> list[Detection]:
    """Header names plus optional employer / school names."""
    found: list[Detection] = []
    lines = _line_spans(text)
    header_end = len(lines)
    for index, (_start, _end, line) in enumerate(lines):
        if line and _SECTION.match(line):
            header_end = index
            break

    for start, end, line in lines[:header_end]:
        labeled = _NAME_LABELED.match(line)
        if labeled:
            name = labeled.group(1).strip()
            rel = line.find(name)
            found.append(
                Detection(EntityType.PERSON, start + rel, start + rel + len(name), name, source="resume")
            )
            break
        if _is_name_line(line):
            # Use the raw slice so offsets stay exact.
            raw = text[start:end]
            found.append(Detection(EntityType.PERSON, start, end, raw, source="resume"))
            break

    if not scrub_orgs:
        return found

    section = ""
    for start, end, line in lines:
        if line and _SECTION.match(line):
            section = line.casefold()
            continue
        if not line:
            continue
        if section in {"experience", "work experience", "employment", "professional experience", "work history"}:
            found.extend(_org_from_line(start, line, EntityType.ORGANIZATION))
        elif section in {"education", "academic background"}:
            found.extend(_school_from_line(start, line))
    return found


def _org_from_line(start: int, line: str, entity: EntityType) -> list[Detection]:
    found: list[Detection] = []
    match = _TITLE_AT_ORG.search(line)
    if match:
        name = match.group(1).strip(" ,;—-")
        if _plausible_org(name):
            rel = match.start(1)
            found.append(Detection(entity, start + rel, start + rel + len(name), name, source="resume"))
            return found
    match = _COMPANY_LINE.match(line)
    if match and not _TITLE_WORDS.search(match.group(1)):
        name = match.group(1).strip()
        if _plausible_org(name):
            rel = match.start(1)
            found.append(Detection(entity, start + rel, start + rel + len(name), name, source="resume"))
    return found


def _school_from_line(start: int, line: str) -> list[Detection]:
    if not _SCHOOL_HINT.search(line):
        return []
    # Take the school-ish phrase up to a comma or em-dash.
    match = re.search(
        r"([A-Z][^,\n—|]{2,60}?(?:University|College|Institute|School|Academy|Polytechnic|Université)[^,\n—|]{0,20})",
        line,
    )
    if not match:
        return []
    name = match.group(1).strip()
    rel = match.start(1)
    return [Detection(EntityType.ORGANIZATION, start + rel, start + rel + len(name), name, source="resume")]


def _plausible_org(name: str) -> bool:
    if len(name) < 2 or len(name) > 80:
        return False
    if name.casefold() in _NOT_NAMES:
        return False
    return True


def person_aliases(full_name: str) -> list[str]:
    """First and last tokens for consistent pseudonyms inside a document."""
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p and p not in {".", ","}]
    aliases: list[str] = []
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        if len(re.sub(r"[^A-Za-z]", "", first)) > 2:
            aliases.append(first)
        if len(re.sub(r"[^A-Za-z]", "", last)) > 3:
            aliases.append(last)
    return aliases
