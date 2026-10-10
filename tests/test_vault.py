from __future__ import annotations

from pathlib import Path

import pytest

from unseeing import Vault, VaultError, scrub


def test_same_entity_same_placeholder() -> None:
    vault = Vault()
    a = vault.register("EMAIL", "Ada@Example.com")
    b = vault.register("EMAIL", "ada@example.com")
    assert a == b == "<EMAIL_1>"


def test_encrypted_roundtrip(tmp_path: Path) -> None:
    _, vault = scrub("Secret card 4242 4242 4242 4242")
    path = tmp_path / "session.vault"
    vault.save(path, key="correct horse")
    blob = path.read_bytes()
    assert blob.startswith(b"UNSEE1")
    assert b"4242" not in blob
    loaded = Vault.load(path, key="correct horse")
    assert loaded.restore("<CREDIT_CARD_1>") == "4242 4242 4242 4242"
    with pytest.raises(VaultError):
        Vault.load(path, key="wrong")
    with pytest.raises(VaultError):
        Vault.loads(blob)


def test_unencrypted_json_roundtrip(tmp_path: Path) -> None:
    _, vault = scrub("mail me at ada@example.com")
    path = tmp_path / "plain.vault.json"
    vault.save(path)
    loaded = Vault.load(path)
    assert loaded.restore("<EMAIL_1>") == "ada@example.com"


def test_reserve_existing_placeholder() -> None:
    text = "Already has <EMAIL_1> and ada@example.com"
    scrubbed, vault = scrub(text)
    assert "<EMAIL_2>" in scrubbed
    assert vault.restore(scrubbed) == text
