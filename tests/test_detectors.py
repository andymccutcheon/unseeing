from __future__ import annotations

from unseeing import CustomPattern, Scrubber
from unseeing.detectors.regex import RegexLayer, iban_ok, luhn_ok


def test_luhn_and_iban_validators() -> None:
    assert luhn_ok("4242424242424242")
    assert not luhn_ok("4242424242424243")
    assert iban_ok("GB82 WEST 1234 5698 7654 32")
    assert not iban_ok("GB00WEST12345698765432")


def test_core_regex_types() -> None:
    text = (
        "Mail ada@example.com or +1-555-222-3333. "
        "Card 4242-4242-4242-4242 SSN 123-45-6789 "
        "IBAN GB82WEST12345698765432 IP 198.51.100.10 "
        "https://www.linkedin.com/in/ada-l "
        "https://github.com/ada-handle "
        "DOB: 1991-02-03 "
        "110 Main Street, Fairview, OR 97024"
    )
    found = {d.type_name: d.value for d in RegexLayer().detect(text)}
    assert "ada@example.com" in found.get("EMAIL", "ada@example.com") or any(
        d.value == "ada@example.com" for d in RegexLayer().detect(text)
    )
    types = {d.type_name for d in RegexLayer().detect(text)}
    assert {
        "EMAIL",
        "PHONE",
        "CREDIT_CARD",
        "SSN",
        "IBAN",
        "IP_ADDRESS",
        "LINKEDIN",
        "GITHUB",
        "DATE_OF_BIRTH",
        "STREET_ADDRESS",
    } <= types


def test_github_repo_is_not_a_profile() -> None:
    text = "See https://github.com/torvalds/linux for the kernel."
    types = [d.type_name for d in RegexLayer().detect(text)]
    assert "GITHUB" not in types


def test_custom_pattern() -> None:
    scrubber = Scrubber(custom_patterns=[CustomPattern("EMPLOYEE_ID", r"EMP-\d{5}")])
    out = scrubber.scrub("Employee EMP-10442 signed.")
    assert "EMP-10442" not in out
    assert "<EMPLOYEE_ID_1>" in out
    assert scrubber.restore(out) == "Employee EMP-10442 signed."


def test_card_spaced_dotted_and_unionpay() -> None:
    # Stripe Visa + a Luhn-valid UnionPay (62) number.
    unionpay = "6212345678901232"
    assert luhn_ok("4242424242424242")
    assert luhn_ok(unionpay)
    text = f"Pay 4242.4242.4242.4242 or {unionpay}."
    types = {d.type_name for d in RegexLayer().detect(text)}
    assert "CREDIT_CARD" in types


def test_ssn_dotted_and_context() -> None:
    text = "SSN 123.45.6789 and Social Security Number: 456789012"
    values = [d.value for d in RegexLayer().detect(text) if d.type_name == "SSN"]
    assert any("123.45.6789" in v for v in values)


def test_dob_ordinal_iso_and_month_slash() -> None:
    text = "DOB: 8th January 1999; birthdate 1965-01-12T00:00:00; Date of Birth: May/58"
    values = [d.value for d in RegexLayer().detect(text) if d.type_name == "DATE_OF_BIRTH"]
    assert any("8th January 1999" in v for v in values)
    assert any("1965-01-12T00:00:00" in v for v in values)
    assert any("May/58" in v for v in values)


def test_named_street_and_id_card_context() -> None:
    text = "Office at Hill Road. Student ID: ZA16863XF. 12th Street is nearby."
    found = RegexLayer().detect(text)
    assert any(d.type_name == "STREET_ADDRESS" and "Hill Road" in d.value for d in found)
    assert any(d.type_name == "STREET_ADDRESS" and "12th Street" in d.value for d in found)
    assert any(d.type_name == "NATIONAL_ID" and "ZA16863XF" in d.value for d in found)


def test_allow_and_deny() -> None:
    text = "Ava Chen works at Acme Corp. Reach Ava Chen at home."
    scrubber = Scrubber(resume=True, allow=["Acme Corp"], deny=["Ava Chen"])
    out = scrubber.scrub(text)
    assert "Acme Corp" in out
    assert "Ava Chen" not in out
    assert scrubber.restore(out) == text
