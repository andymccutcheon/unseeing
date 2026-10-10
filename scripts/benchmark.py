#!/usr/bin/env python3
"""Held-out PII detection eval on a public dataset we did not tune on.

Dataset: ai4privacy/pii-masking-400k (Hugging Face)
Filter: language == "en"
Sample: fixed size + seed (see flags)

This script is *not* run in CI. It downloads data and, for the NER config,
needs ``pip install 'unseeing[ner]'`` plus ``python -m spacy download en_core_web_sm``.

    python3 -m pip install -e ".[ner]" datasets huggingface_hub
    python3 -m spacy download en_core_web_sm
    python3 scripts/benchmark.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

# --- label mapping ----------------------------------------------------------

# Dataset labels we score, mapped to unseeing entity types.
# Adjacent GIVENNAME+SURNAME gold spans are merged into one PERSON (see
# merge_person_spans). CITY is LOCATION (NER only in practice).
LABEL_MAP: dict[str, str] = {
    "EMAIL": "EMAIL",
    "TELEPHONENUM": "PHONE",
    "CREDITCARDNUMBER": "CREDIT_CARD",
    "SOCIALNUM": "SSN",
    "IDCARDNUM": "NATIONAL_ID",
    "DATEOFBIRTH": "DATE_OF_BIRTH",
    "STREET": "STREET_ADDRESS",
    "GIVENNAME": "PERSON",
    "SURNAME": "PERSON",
    "CITY": "LOCATION",
    "IPV4": "IP_ADDRESS",
    "IPV6": "IP_ADDRESS",
    "URL": "URL",
    "IBAN": "IBAN",
}

# Predictions of these more-specific types count as the mapped type.
PRED_TYPE_MAP: dict[str, str] = {
    "LINKEDIN": "URL",
    "GITHUB": "URL",
}

IN_SCOPE_TYPES = frozenset(LABEL_MAP.values())

# Present in the dataset; unseeing does not claim these types.
EXCLUDED_LABELS = frozenset(
    {
        "USERNAME",
        "PASSWORD",
        "ACCOUNTNUM",
        "TAXNUM",
        "DRIVERLICENSENUM",
        "BUILDINGNUM",
        "ZIPCODE",
        "MAC",
        "USERAGENT",
        "BITCOINADDRESS",
        "ETHEREUMADDRESS",
        "LITECOINADDRESS",
        "VEHICLEVIN",
        "VEHICLEVRM",
        "PIN",
        "JOBTITLE",
        "HEIGHT",
        "EYECOLOR",
        "TIME",
        "AGE",
        "TITLE",
        "GENDER",
        "SEX",
        "PASSPORTNUM",
    }
)

DATASET_ID = "ai4privacy/pii-masking-400k"
DEFAULT_N = 2000
DEFAULT_SEED = 20261010
# Pinned so `python3 scripts/benchmark.py` reproduces the README tables.
DEFAULT_REVISION = "414d0a3b5798a152588a0828f1c08a5787de10f4"


@dataclass(frozen=True)
class Span:
    entity_type: str
    start: int
    end: int
    value: str


def merge_person_spans(spans: list[Span], text: str) -> list[Span]:
    """Join GIVENNAME + SURNAME that sit next to each other into one PERSON."""
    people = [s for s in spans if s.entity_type == "PERSON"]
    others = [s for s in spans if s.entity_type != "PERSON"]
    people.sort(key=lambda s: (s.start, s.end))
    merged: list[Span] = []
    for span in people:
        if merged and span.start <= merged[-1].end + 2:
            prev = merged[-1]
            end = max(prev.end, span.end)
            merged[-1] = Span("PERSON", prev.start, end, text[prev.start : end])
        else:
            merged.append(span)
    return others + merged


def _mask_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    mask = row.get("privacy_mask") or []
    if isinstance(mask, str):
        try:
            parsed = json.loads(mask)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return list(mask)


def gold_spans(row: dict[str, Any]) -> list[Span]:
    text = row.get("source_text") or ""
    found: list[Span] = []
    for item in _mask_items(row):
        label = item.get("label") or ""
        mapped = LABEL_MAP.get(label)
        if mapped is None:
            continue
        start, end = int(item["start"]), int(item["end"])
        if start >= end or start < 0 or end > len(text):
            continue
        value = item.get("value") or text[start:end]
        found.append(Span(mapped, start, end, value))
    return merge_person_spans(found, text)


def pred_spans(text: str, detections: list[Any]) -> list[Span]:
    found: list[Span] = []
    for detection in detections:
        mapped = PRED_TYPE_MAP.get(detection.type_name, detection.type_name)
        if mapped not in IN_SCOPE_TYPES:
            continue
        found.append(Span(mapped, detection.start, detection.end, detection.value))
    return found


def collect_labels(rows: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    seen: set[str] = set()
    unknown: set[str] = set()
    for row in rows:
        for item in _mask_items(row):
            label = item.get("label") or ""
            if not label:
                continue
            seen.add(label)
            if label not in LABEL_MAP and label not in EXCLUDED_LABELS:
                unknown.add(label)
    return seen, unknown


def overlaps(a: Span, b: Span) -> bool:
    return a.start < b.end and b.start < a.end


def match_entities(
    gold: list[Span], pred: list[Span]
) -> tuple[list[tuple[Span, Span]], list[Span], list[Span]]:
    """1-1 overlap match, same type. Greedy: longer gold first, longer pred first."""
    unused = list(pred)
    pairs: list[tuple[Span, Span]] = []
    fn: list[Span] = []
    for g in sorted(gold, key=lambda s: (s.start - s.end, s.start)):
        candidates = [p for p in unused if p.entity_type == g.entity_type and overlaps(g, p)]
        if not candidates:
            fn.append(g)
            continue
        chosen = max(candidates, key=lambda p: (p.end - p.start, -p.start))
        unused.remove(chosen)
        pairs.append((g, chosen))
    return pairs, unused, fn


def rates(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def score(docs_gold: list[list[Span]], docs_pred: list[list[Span]]) -> dict[str, Any]:
    per: dict[str, Counter[str]] = {}

    def bucket(name: str) -> Counter[str]:
        return per.setdefault(name, Counter())

    for gold, pred in zip(docs_gold, docs_pred, strict=True):
        pairs, fps, fns = match_entities(gold, pred)
        for g, _p in pairs:
            bucket(g.entity_type)["tp"] += 1
        for p in fps:
            bucket(p.entity_type)["fp"] += 1
        for g in fns:
            bucket(g.entity_type)["fn"] += 1

    by_type = {name: rates(c["tp"], c["fp"], c["fn"]) for name, c in sorted(per.items())}
    # Types with no gold in the sample (this 400k public schema is 17 classes
    # and does not label URL / IP / IBAN). Counting those predictions as FP
    # would punish the detector for spans the dataset never annotated.
    gold_types = [name for name, row in by_type.items() if int(row["tp"]) + int(row["fn"]) > 0]
    unlabeled = [name for name in by_type if name not in gold_types]
    overall = rates(0, 0, 0)
    if gold_types:
        overall = rates(
            sum(int(by_type[name]["tp"]) for name in gold_types),
            sum(int(by_type[name]["fp"]) for name in gold_types),
            sum(int(by_type[name]["fn"]) for name in gold_types),
        )
    return {
        "overall": overall,
        "by_type": {name: by_type[name] for name in gold_types},
        "unlabeled_predictions": {name: by_type[name] for name in unlabeled},
        "overall_types": gold_types,
    }


def fmt_row(name: str, row: dict[str, float | int]) -> str:
    return (
        f"| {name} | {row['precision']:.2f} | {row['recall']:.2f} | {row['f1']:.2f} | "
        f"{int(row['tp'])} | {int(row['fp'])} | {int(row['fn'])} |"
    )


def print_table(title: str, report: dict[str, Any]) -> None:
    print(f"\n### {title}\n")
    print("| Type | Precision | Recall | F1 | TP | FP | FN |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    print(fmt_row("**Overall**", report["overall"]))
    for name, row in report["by_type"].items():
        print(fmt_row(name, row))
    unlabeled = report.get("unlabeled_predictions") or {}
    if unlabeled:
        print(
            "\nPredicted but unlabeled in this sample "
            "(omitted from overall; the 400k 17-class gold set does not "
            "include these types):"
        )
        print("| Type | Predictions |")
        print("| --- | ---: |")
        for name, row in unlabeled.items():
            print(f"| {name} | {int(row['fp'])} |")


def load_sample(
    *, n: int, seed: int, revision: str | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from datasets import load_dataset
        from huggingface_hub import dataset_info
    except ImportError as exc:
        raise SystemExit(
            "Need datasets + huggingface_hub (and a NumPy that pyarrow accepts).\n"
            "  python3 -m pip install datasets huggingface_hub 'numpy>=2'\n"
            f"Import failed: {exc}"
        ) from exc

    info = dataset_info(DATASET_ID, revision=revision)
    sha = getattr(info, "sha", None) or revision or "unknown"
    ds = load_dataset(DATASET_ID, split="train", revision=sha)
    english = ds.filter(lambda row: (row.get("language") or "") == "en")
    available = len(english)
    take = min(n, available)
    sampled = english.shuffle(seed=seed).select(range(take))
    rows = [dict(row) for row in sampled]
    seen, unknown = collect_labels(rows)
    meta = {
        "dataset": DATASET_ID,
        "revision": sha,
        "split": "train",
        "language_filter": "en",
        "english_rows_available": available,
        "sample_size": len(rows),
        "seed": seed,
        "sampled_on": date.today().isoformat(),
        "sampled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels_seen_in_sample": sorted(seen),
        "unmapped_labels_in_sample": sorted(unknown),
    }
    return rows, meta


def run_config(rows: list[dict[str, Any]], *, use_ner: bool) -> dict[str, Any]:
    from unseeing import Scrubber

    # One scrubber for the run so spaCy loads once. detect() does not register
    # vault entries, so documents do not leak aliases into later rows.
    scrubber = Scrubber(resume=False, use_ner=use_ner)
    golds: list[list[Span]] = []
    preds: list[list[Span]] = []
    for row in rows:
        text = row.get("source_text") or ""
        golds.append(gold_spans(row))
        preds.append(pred_spans(text, scrubber.detect(text)))
    return score(golds, preds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--revision",
        default=DEFAULT_REVISION,
        help=f"HF dataset git commit (default: {DEFAULT_REVISION})",
    )
    parser.add_argument("--skip-ner", action="store_true")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    rows, meta = load_sample(n=args.n, seed=args.seed, revision=args.revision)
    print("Held-out evaluation (not used to tune detectors)")
    print(json.dumps(meta, indent=2))
    print("\nMatching rule: entity-level, same mapped type, character-span overlap.")
    print("A gold and a prediction match if they overlap and share a type;")
    print("each span is used at most once (greedy, longer gold first).")
    print("Adjacent GIVENNAME+SURNAME gold spans are merged into one PERSON.")
    print("LINKEDIN / GITHUB predictions are scored as URL.")
    print("Excluded dataset labels (unseeing does not claim them):")
    print("  " + ", ".join(sorted(EXCLUDED_LABELS)))
    if meta.get("unmapped_labels_in_sample"):
        print("Unmapped labels in this sample (treated as excluded):")
        print("  " + ", ".join(meta["unmapped_labels_in_sample"]))

    regex_report = run_config(rows, use_ner=False)
    print_table("regex-only (default install, no resume, no NER)", regex_report)

    ner_report: dict[str, Any] | None = None
    if not args.skip_ner:
        try:
            ner_report = run_config(rows, use_ner=True)
        except Exception as exc:  # noqa: BLE001 — report missing extra cleanly
            print(f"\nNER config skipped: {exc}", file=sys.stderr)
        else:
            print_table("regex + unseeing[ner] (spaCy en_core_web_sm)", ner_report)

    payload = {"meta": meta, "regex_only": regex_report, "ner": ner_report}
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
