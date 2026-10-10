# Contributing to unseeing

Thanks for helping keep prompts empty of people.

## Setup

Python 3.10+ is required. The core package has **no required dependencies**.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Optional extras (`ner`, `gliner`, `presidio`, `openai`, `anthropic`) are not
needed for CI. Tests that need them skip or assert a clear `DetectorError`.
Default ``pip install unseeing`` stays dependency-free.

Do not put real personal data, API keys, or vault passwords in the repository,
fixtures, or CI. Fixtures use reserved/example values only (example.com,
555 numbers, Stripe test cards, Wikipedia IBAN).

## Checks

Run the same checks CI runs:

```bash
ruff check src tests examples scripts
ruff format src tests examples scripts
pytest
```

CI is GitHub Actions (`.github/workflows/ci.yml`) on Python 3.10 and 3.12:
lint, format, pytest, then `python -m build` + `twine check --strict`.

The held-out eval (`scripts/benchmark.py`) downloads a public Hugging Face
dataset and is **not** part of CI. Tune only on the disjoint **dev** sample
(`--split=dev`, seed 20261011, excluding seed 20261010). Then run the
untouched test sample once:

```bash
python3 -m pip install -e ".[ner,gliner]" datasets huggingface_hub 'numpy>=2'
python3 -m spacy download en_core_web_sm
python3 scripts/benchmark.py --split=dev --gap-report
python3 scripts/benchmark.py --latency
```

Do not look at test-set errors while changing detectors. The six resumes in
`tests/fixtures/resumes.json` are a regression fixture only.

## Design notes

- Import, CLI, and PyPI name are all `unseeing`.
- Detection belongs in `unseeing.detectors`. Mapping belongs in
  `unseeing.vault`. Streaming restore belongs in `unseeing.restore`.
- New entity types need a detector, a placeholder label, a fixture example,
  and a false-positive check where relevant.
- Never log original values from `AuditReport`.
- The stable freewhirr hook is `ScrubberProtocol`
  (`scrub_messages` / `restore_message` / `restore_stream`).

## Releasing

Maintainers: see [RELEASING.md](RELEASING.md). Publishing is Trusted
Publishing only — do not add a PyPI API token to GitHub secrets.

## Pull requests

- Small, focused diffs with a short rationale.
- Update the README when you change user-facing behavior.
- Never commit `.env`, vault files, or API keys.
