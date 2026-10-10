"""Fast built-in regex / validator layer. No third-party dependencies."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable

from unseeing.types import Detection, EntityType

# --- validators -------------------------------------------------------------


def luhn_ok(digits: str) -> bool:
    if not digits.isdigit() or not digits:
        return False
    total = 0
    alt = False
    for char in reversed(digits):
        num = ord(char) - 48
        if alt:
            num *= 2
            if num > 9:
                num -= 9
        total += num
        alt = not alt
    return total % 10 == 0


def iban_ok(iban: str) -> bool:
    compact = re.sub(r"\s+", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", compact):
        return False
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


def _card_iin_ok(digits: str) -> bool:
    length = len(digits)
    if length < 13 or length > 19 or len(set(digits)) == 1:
        return False
    prefix2 = int(digits[:2])
    prefix3 = int(digits[:3])
    prefix4 = int(digits[:4])
    if digits[0] == "4" and length in {13, 16, 19}:
        return True
    if 51 <= prefix2 <= 55 and length == 16:
        return True
    if 2221 <= prefix4 <= 2720 and length == 16:
        return True
    if prefix2 in {34, 37} and length == 15:
        return True
    if digits.startswith(("6011", "65", "64")) and length in {16, 19}:
        return True
    if 3528 <= prefix4 <= 3589 and length == 16:
        return True
    # UnionPay
    if digits.startswith("62") and 16 <= length <= 19:
        return True
    # Mir
    if 2200 <= prefix4 <= 2204 and length == 16:
        return True
    # Diners Club
    if prefix2 in {36, 38} and length in {14, 16}:
        return True
    return 300 <= prefix3 <= 305 and length in {14, 16}


def _ssn_parts_ok(area: str, group: str, serial: str) -> bool:
    if area == "000" or area == "666":
        return False
    # 9xx is the ITIN range; still an identifier we claim as SSN-like.
    return group != "00" and serial != "0000"


def _trim_url(value: str) -> str:
    return value.rstrip(".,;:!?)\"'")


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


# --- patterns ---------------------------------------------------------------

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}\b")

_PHONE = re.compile(
    r"""
    (?<!\w)
    (?:
        \+\d{1,3}[\s.-]?(?:\(?\d{1,4}\)?[\s.-]?)?(?:\d[\s.-]?){6,13}\d
        |
        \(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{4}
        |
        \b\d{3}[\s.-]\d{3}[\s.-]\d{4}\b
    )
    (?!\w)
    """,
    re.VERBOSE,
)

_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_WWW = re.compile(r"\bwww\.[A-Za-z0-9.-]+\.[A-Za-z]{2,24}[^\s<>\"']*", re.I)

_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|1?\d{1,2})\b")
_IPV6_LOOSE = re.compile(r"(?:[0-9A-Fa-f]{1,4}:){1,7}[0-9A-Fa-f:]{0,20}")

_CC_GROUPED = re.compile(r"\b(?:\d{4}[\s.\-]){3}\d{4}\b")
_CC_AMEX = re.compile(r"\b\d{4}[\s.\-]\d{6}[\s.\-]\d{5}\b")
_CC_DINERS = re.compile(r"\b\d{4}[\s.\-]\d{6}[\s.\-]\d{4}\b")
_CC_BARE = re.compile(r"\b\d{13,19}\b")

_SSN = re.compile(r"\b(\d{3})[.\-\s](\d{2})[.\-\s](\d{4})\b")
_SSN_CONTEXT = re.compile(
    r"""
    (?:ssn|social\s+security(?:\s+number)?|social\s+(?:insurance\s+)?number)
    \s*[:#]?\s*
    (
        \d{3}[.\-\s]\d{2}[.\-\s]\d{4}
        | \d{3}[.\-\s]\d{3}[.\-\s]\d{3,4}
        | \d{9,10}
    )
    """,
    re.I | re.VERBOSE,
)
_NINO = re.compile(
    r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
    re.I,
)
_SIN = re.compile(r"\b\d{3}[.\-\s]\d{3}[.\-\s]\d{3}\b")
_NATIONAL_ID_CONTEXT = re.compile(
    r"""
    (?<![A-Za-z])
    (?:
        (?:national\s+)?id(?:entity)?(?:\s*card)?(?:\s*(?:number|no\.?)|:)
        | national\s+id
        | nino
        | national\s+insurance(?:\s+number)?
    )
    \s*[:#]?\s*
    ([A-Z0-9][A-Z0-9.\-]{5,16}[A-Z0-9])
    """,
    re.I | re.VERBOSE,
)

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_IBAN_SPACED = re.compile(r"\b[A-Z]{2}\d{2}(?:\s+[A-Z0-9]{4}){2,7}\b")

_STREET = re.compile(
    r"""
    \b\d{1,6}\s+
    (?:[A-Z][A-Za-z0-9.'’\-]*\s+){0,5}
    (?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|
       Court|Ct|Way|Place|Pl|Circle|Cir|Terrace|Ter|Parkway|Pkwy|
       Highway|Hwy|Square|Sq|Close|Crescent|Grove|Hill|Walk|Freeway)\.?
    \b
    """,
    re.VERBOSE | re.I,
)
# Street name + a strong suffix, no house number ("Hill Road", "Kiefer Boulevard").
# Ambiguous suffixes (Court, Drive, Way, Place) are omitted to avoid
# "Supreme Court" / "the only Way".
_STREET_NAMED = re.compile(
    r"""
    \b(?:[A-Z][A-Za-z0-9.'’\-]*\s+){1,4}
    (?:Street|Avenue|Road|Boulevard|Lane|Parkway|Highway|Crescent|Freeway)\.?
    \b
    """,
    re.VERBOSE,
)
_STREET_DRIVE = re.compile(
    r"""
    \b(?:[A-Z][A-Za-z0-9.'’\-]*\s+){2,4}
    (?:Drive|Walk)\.?
    \b
    """,
    re.VERBOSE,
)
_STREET_ORDINAL = re.compile(
    r"""
    \b\d{1,4}(?:st|nd|rd|th)\s+
    (?:Street|Avenue|Road|Boulevard|Lane|Drive|Parkway|Highway)\.?
    \b
    """,
    re.VERBOSE | re.I,
)
_PO_BOX = re.compile(r"\bP\.?\s*O\.?\s*Box\s+\d+\b", re.I)
_CITY_STATE_ZIP = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)"
)
_DOB_DATE = rf"""
    (?:
        \d{{4}}-\d{{2}}-\d{{2}}(?:T\d{{2}}:\d{{2}}:\d{{2}})?
        | \d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}
        | {_MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}
        | \d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\.?\s+\d{{4}}
        | {_MONTH}/\d{{2}}(?:\d{{2}})?
    )
"""
_DOB = re.compile(
    rf"(?:date\s+of\s+birth|d\.?o\.?b\.?|born(?:\s+on)?|birthday|birth\s*date|birthdate)"
    rf"\s*[:\-]?\s*({_DOB_DATE})",
    re.I | re.VERBOSE,
)

_LINKEDIN = re.compile(
    r"(?:https?://(?:[\w-]+\.)?)?linkedin\.com/in/[\w%\-]+/?",
    re.I,
)
_GITHUB_PROFILE = re.compile(
    r"(?:https?://(?:www\.)?)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})(?:/)?(?![\w.-])",
    re.I,
)

_GITHUB_RESERVED = frozenset(
    {
        "about",
        "account",
        "admin",
        "api",
        "apps",
        "blog",
        "codespaces",
        "collections",
        "contact",
        "enterprise",
        "events",
        "explore",
        "features",
        "ghost",
        "gist",
        "integrations",
        "issues",
        "login",
        "logout",
        "marketplace",
        "new",
        "notifications",
        "orgs",
        "organizations",
        "pricing",
        "pulls",
        "search",
        "security",
        "settings",
        "signup",
        "site",
        "sponsors",
        "stars",
        "topics",
        "trending",
        "watchers",
    }
)

_IP_CONTEXT_SKIP = re.compile(
    r"(?:version|ver|v|section|sec|rfc|release|build|python)\s*$",
    re.I,
)


def _span(entity: EntityType, start: int, end: int, text: str, source: str = "regex") -> Detection:
    return Detection(entity, start, end, text[start:end], source=source)


class RegexLayer:
    """Emails, phones, URLs, IPs, cards, IDs, IBAN, addresses, DOB, profiles."""

    name = "regex"

    def __init__(self, *, scrub_urls: bool = True) -> None:
        self.scrub_urls = scrub_urls

    def detect(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        found.extend(self._emails(text))
        found.extend(self._phones(text))
        found.extend(self._linkedin(text))
        found.extend(self._github(text))
        if self.scrub_urls:
            found.extend(self._urls(text))
        found.extend(self._ips(text))
        found.extend(self._cards(text))
        found.extend(self._ssns(text))
        found.extend(self._national_ids(text))
        found.extend(self._ibans(text))
        found.extend(self._addresses(text))
        found.extend(self._dobs(text))
        return found

    def _emails(self, text: str) -> Iterable[Detection]:
        for match in _EMAIL.finditer(text):
            local, _, domain = match.group(0).partition("@")
            if not local or "." not in domain:
                continue
            yield _span(EntityType.EMAIL, match.start(), match.end(), text)

    def _phones(self, text: str) -> Iterable[Detection]:
        for match in _PHONE.finditer(text):
            raw = match.group(0)
            digits = _digits(raw)
            if not 10 <= len(digits) <= 15:
                continue
            if len(digits) >= 13 and _card_iin_ok(digits) and luhn_ok(digits):
                continue
            yield _span(EntityType.PHONE, match.start(), match.end(), text)

    def _linkedin(self, text: str) -> Iterable[Detection]:
        for match in _LINKEDIN.finditer(text):
            end = match.start() + len(_trim_url(match.group(0)))
            yield _span(EntityType.LINKEDIN, match.start(), end, text)

    def _github(self, text: str) -> Iterable[Detection]:
        for match in _GITHUB_PROFILE.finditer(text):
            handle = match.group(1)
            if handle.lower() in _GITHUB_RESERVED:
                continue
            # A following "/repo" means this is not a profile URL.
            after = text[match.end() : match.end() + 1]
            if after == "/" or (
                match.group(0).rstrip("/").count("/") >= 1
                and re.search(r"github\.com/[^/\s]+/[\w.-]+", match.group(0), re.I)
            ):
                continue
            end = match.start() + len(_trim_url(match.group(0)))
            yield _span(EntityType.GITHUB, match.start(), end, text)

    def _urls(self, text: str) -> Iterable[Detection]:
        for pattern in (_URL, _WWW):
            for match in pattern.finditer(text):
                trimmed = _trim_url(match.group(0))
                yield _span(EntityType.URL, match.start(), match.start() + len(trimmed), text)

    def _ips(self, text: str) -> Iterable[Detection]:
        for match in _IPV4.finditer(text):
            prefix = text[: match.start()]
            if _IP_CONTEXT_SKIP.search(prefix[-16:]):
                continue
            candidate = match.group(0)
            try:
                ipaddress.IPv4Address(candidate)
            except ipaddress.AddressValueError:
                continue
            yield _span(EntityType.IP_ADDRESS, match.start(), match.end(), text)
        for match in _IPV6_LOOSE.finditer(text):
            raw = match.group(0)
            for end in range(len(raw), 1, -1):
                piece = raw[:end]
                if piece.endswith(":") and not piece.endswith("::"):
                    continue
                try:
                    ipaddress.IPv6Address(piece)
                except ipaddress.AddressValueError:
                    continue
                yield Detection(
                    EntityType.IP_ADDRESS,
                    match.start(),
                    match.start() + end,
                    piece,
                    source="regex",
                )
                break

    def _cards(self, text: str) -> Iterable[Detection]:
        seen: set[tuple[int, int]] = set()
        for pattern in (_CC_GROUPED, _CC_AMEX, _CC_DINERS, _CC_BARE):
            for match in pattern.finditer(text):
                digits = _digits(match.group(0))
                if not _card_iin_ok(digits) or not luhn_ok(digits):
                    continue
                key = (match.start(), match.end())
                if key in seen:
                    continue
                seen.add(key)
                yield _span(EntityType.CREDIT_CARD, match.start(), match.end(), text)

    def _ssns(self, text: str) -> Iterable[Detection]:
        seen: set[tuple[int, int]] = set()
        for match in _SSN.finditer(text):
            if not _ssn_parts_ok(match.group(1), match.group(2), match.group(3)):
                continue
            key = (match.start(), match.end())
            seen.add(key)
            yield _span(EntityType.SSN, match.start(), match.end(), text)
        for match in _SSN_CONTEXT.finditer(text):
            raw = match.group(1)
            digits = _digits(raw)
            if len(digits) == 9:
                if not _ssn_parts_ok(digits[:3], digits[3:5], digits[5:]):
                    continue
            elif len(digits) == 10:
                pass
            else:
                continue
            start = match.start(1)
            end = match.start(1) + len(raw)
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            yield Detection(EntityType.SSN, start, end, raw, source="regex")

    def _national_ids(self, text: str) -> Iterable[Detection]:
        seen: set[tuple[int, int]] = set()
        for match in _NINO.finditer(text):
            seen.add((match.start(), match.end()))
            yield _span(EntityType.NATIONAL_ID, match.start(), match.end(), text)
        for match in _SIN.finditer(text):
            digits = _digits(match.group(0))
            if len(digits) != 9 or not luhn_ok(digits):
                continue
            # 3-2-4 SSNs are a different pattern; 3-3-3 plus Luhn is SIN-like.
            seen.add((match.start(), match.end()))
            yield _span(EntityType.NATIONAL_ID, match.start(), match.end(), text)
        for match in _NATIONAL_ID_CONTEXT.finditer(text):
            raw = match.group(1).strip(" .,;:")
            compact = re.sub(r"[\s.\-]", "", raw)
            if not 7 <= len(compact) <= 18:
                continue
            if not re.fullmatch(r"[A-Z0-9]+", compact, re.I):
                continue
            if compact.isdigit() and len(compact) in {8, 9} and compact.startswith("19"):
                # Likely a year-ish number, not an ID.
                continue
            start = match.start(1)
            end = start + len(match.group(1))
            # Trim trailing punctuation from the span.
            while end > start and text[end - 1] in " .,;:":
                end -= 1
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            yield Detection(EntityType.NATIONAL_ID, start, end, text[start:end], source="regex")

    def _ibans(self, text: str) -> Iterable[Detection]:
        for pattern in (_IBAN, _IBAN_SPACED):
            for match in pattern.finditer(text):
                raw = match.group(0).rstrip()
                if iban_ok(raw):
                    yield Detection(
                        EntityType.IBAN,
                        match.start(),
                        match.start() + len(raw),
                        raw,
                        source="regex",
                    )

    def _addresses(self, text: str) -> Iterable[Detection]:
        for pattern in (
            _STREET,
            _STREET_NAMED,
            _STREET_DRIVE,
            _STREET_ORDINAL,
            _PO_BOX,
            _CITY_STATE_ZIP,
        ):
            for match in pattern.finditer(text):
                yield _span(EntityType.STREET_ADDRESS, match.start(), match.end(), text)

    def _dobs(self, text: str) -> Iterable[Detection]:
        for match in _DOB.finditer(text):
            yield Detection(
                EntityType.DATE_OF_BIRTH,
                match.start(1),
                match.end(1),
                match.group(1),
                source="regex",
            )
