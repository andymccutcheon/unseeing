"""Command-line interface: scan, scrub, restore, demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from unseeing._version import __version__
from unseeing.scrubber import Scrubber
from unseeing.vault import Vault

_DEMO_RESUME = """\
Ava Chen
Senior Software Engineer
123 Maple Street, Springfield, IL 62704
ava.chen@example.com | +1-555-010-0142
linkedin.com/in/avachen | github.com/avachen
DOB: April 12, 1992

EXPERIENCE
Staff Engineer at Globex Robotics — 2021–2025
- Led matching pipeline work. Contact me at ava.chen@example.com.

EDUCATION
University of Springfield, B.S. Computer Science
"""

_DEMO_MODEL = (
    "<PERSON_1> looks like a strong fit. I would email <EMAIL_1> and "
    "check <GITHUB_1>'s recent work."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="unseeing",
        description="Reversible PII scrubbing for LLM calls.",
    )
    parser.add_argument("--version", action="version", version=f"unseeing {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="Report entity types and counts (never originals).")
    scan.add_argument("file", help="Path to a text file.")
    _add_shared(scan)

    scrub_p = sub.add_parser("scrub", help="Replace PII on stdin or a file; write text to stdout.")
    scrub_p.add_argument("file", nargs="?", help="Input file (default: stdin).")
    scrub_p.add_argument("--vault", help="Write the reversible mapping to this path.")
    scrub_p.add_argument("--key", help="Password for an encrypted vault file.")
    scrub_p.add_argument("--surrogates", action="store_true", help="Use realistic stand-ins.")
    _add_shared(scrub_p)

    restore = sub.add_parser("restore", help="Restore originals using a saved vault.")
    restore.add_argument("file", nargs="?", help="Input file (default: stdin).")
    restore.add_argument("--vault", required=True, help="Vault path from `unseeing scrub --vault`.")
    restore.add_argument("--key", help="Password if the vault is encrypted.")

    sub.add_parser("demo", help="Show a resume scrub + streamed restore.")

    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return _cmd_scan(args)
    if args.cmd == "scrub":
        return _cmd_scrub(args)
    if args.cmd == "restore":
        return _cmd_restore(args)
    if args.cmd == "demo":
        return _cmd_demo()
    parser.error("unknown command")
    return 2


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--resume", action="store_true", help="Enable resume / HR header heuristics.")
    parser.add_argument("--scrub-orgs", action="store_true", help="Also scrub employers and schools.")
    parser.add_argument("--allow", action="append", default=[], help="Never-scrub phrase (repeatable).")


def _read(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def _make_scrubber(args: argparse.Namespace, *, use_surrogates: bool = False) -> Scrubber:
    return Scrubber(
        resume=getattr(args, "resume", False),
        scrub_orgs=getattr(args, "scrub_orgs", False),
        allow=getattr(args, "allow", []) or (),
        use_surrogates=use_surrogates,
    )


def _cmd_scan(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    scrubber = _make_scrubber(args)
    detections = scrubber.detect(text)
    counts: dict[str, int] = {}
    for item in detections:
        counts[item.type_name] = counts.get(item.type_name, 0) + 1
    if not counts:
        print("No PII detected.")
        return 0
    width = max(len(name) for name in counts) + 2
    for name, count in sorted(counts.items()):
        print(f"{name:<{width}}{count}")
    print(f"{'Total':<{width}}{sum(counts.values())}")
    return 0


def _cmd_scrub(args: argparse.Namespace) -> int:
    text = _read(args.file)
    scrubber = _make_scrubber(args, use_surrogates=args.surrogates)
    out = scrubber.scrub(text)
    sys.stdout.write(out)
    if not out.endswith("\n") and text.endswith("\n"):
        sys.stdout.write("\n")
    report = scrubber.audit()
    print(report.format(), file=sys.stderr)
    if args.vault:
        scrubber.vault.save(args.vault, key=args.key or None)
        print(f"vault written to {args.vault}", file=sys.stderr)
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    text = _read(args.file)
    vault = Vault.load(args.vault, key=args.key or None)
    sys.stdout.write(vault.restore(text))
    return 0


def _cmd_demo() -> int:
    scrubber = Scrubber(resume=True)
    scrubbed = scrubber.scrub(_DEMO_RESUME)
    print("=== original (synthetic) ===")
    print(_DEMO_RESUME)
    print("=== scrubbed (this is what the model sees) ===")
    print(scrubbed)
    print("=== audit (safe to log) ===")
    print(scrubber.audit().format())
    print("=== model reply (placeholders, including a split chunk) ===")
    restorer = scrubber.stream_restorer()
    chunks = [_DEMO_MODEL[:22], _DEMO_MODEL[22:]]
    restored = "".join(restorer.feed(chunk) for chunk in chunks) + restorer.flush()
    print(_DEMO_MODEL)
    print("=== restored ===")
    print(restored)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
