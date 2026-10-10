from __future__ import annotations

from pathlib import Path

from unseeing.cli import main


def test_scan_and_scrub_and_restore(tmp_path: Path, capsys) -> None:
    path = tmp_path / "note.txt"
    path.write_text("Write to ada@example.com please\n", encoding="utf-8")
    assert main(["scan", str(path)]) == 0
    scanned = capsys.readouterr()
    assert "EMAIL" in scanned.out
    assert "ada@example.com" not in scanned.out

    vault = tmp_path / "map.vault"
    assert main(["scrub", str(path), "--vault", str(vault)]) == 0
    scrubbed = capsys.readouterr()
    assert "ada@example.com" not in scrubbed.out
    assert "<EMAIL_1>" in scrubbed.out
    assert "EMAIL" in scrubbed.err

    out_path = tmp_path / "scrubbed.txt"
    out_path.write_text(scrubbed.out, encoding="utf-8")
    assert main(["restore", str(out_path), "--vault", str(vault)]) == 0
    restored = capsys.readouterr()
    assert "ada@example.com" in restored.out


def test_demo(capsys) -> None:
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "scrubbed" in out.lower()
    assert "ava.chen@example.com" in out
    assert "<EMAIL_1>" in out or "EMAIL" in out


def test_version(capsys) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "0.1.0" in capsys.readouterr().out
