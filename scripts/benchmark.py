#!/usr/bin/env python3
"""Held-out PII detection eval on a public dataset we did not tune on.

Dataset: ai4privacy/pii-masking-400k (Hugging Face)
Filter: language == "en"
Sample: fixed size + seed (see flags)

This script is *not* run in CI. It downloads data and, for the NER config,
needs ``pip install 'unseeing[ner]'`` plus ``python -m spacy download en_core_web_sm``.
GLiNER needs ``pip install 'unseeing[gliner]'`` (ONNX Runtime; downloads the
PII-small ONNX graph on first use). Tune only on ``--split=dev``.

    python3 -m pip install -e ".[ner,gliner]" datasets huggingface_hub
    python3 -m spacy download en_core_web_sm
    python3 scripts/benchmark.py --split=dev --gap-report --skip-ner --skip-gliner
    python3 scripts/benchmark.py --latency
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
DEFAULT_DEV_SEED = 20261011
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


def _row_uid(row: dict[str, Any]) -> str:
    uid = row.get("uid")
    if uid is None:
        uid = row.get("id")
    return str(uid) if uid is not None else ""


def _hf_english(revision: str | None):
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
    return english, sha


def load_sample(
    *,
    n: int,
    seed: int,
    revision: str | None,
    exclude_seed: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    english, sha = _hf_english(revision)
    available = len(english)
    blocked: set[str] = set()
    if exclude_seed is not None:
        held_out = english.shuffle(seed=exclude_seed).select(range(min(n, available)))
        blocked = {_row_uid(row) for row in held_out if _row_uid(row)}
    shuffled = english.shuffle(seed=seed)
    rows: list[dict[str, Any]] = []
    for row in shuffled:
        item = dict(row)
        if blocked and _row_uid(item) in blocked:
            continue
        rows.append(item)
        if len(rows) >= n:
            break
    seen, unknown = collect_labels(rows)
    meta = {
        "dataset": DATASET_ID,
        "revision": sha,
        "split": "train",
        "language_filter": "en",
        "english_rows_available": available,
        "sample_size": len(rows),
        "seed": seed,
        "exclude_seed": exclude_seed,
        "disjoint_from_seed": exclude_seed,
        "sampled_on": date.today().isoformat(),
        "sampled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels_seen_in_sample": sorted(seen),
        "unmapped_labels_in_sample": sorted(unknown),
    }
    return rows, meta


def run_config(
    rows: list[dict[str, Any]],
    *,
    use_ner: bool = False,
    use_gliner: bool = False,
) -> dict[str, Any]:
    from unseeing import Scrubber

    # One scrubber for the run so spaCy / GLiNER load once. detect() does not
    # register vault entries, so documents do not leak aliases into later rows.
    scrubber = Scrubber(resume=False, use_ner=use_ner, use_gliner=use_gliner)
    golds: list[list[Span]] = []
    preds: list[list[Span]] = []
    for row in rows:
        text = row.get("source_text") or ""
        golds.append(gold_spans(row))
        preds.append(pred_spans(text, scrubber.detect(text)))
    return score(golds, preds)


def measure_gliner_latency(rows: list[dict[str, Any]], *, limit: int = 80) -> dict[str, float]:
    import time

    from unseeing import Scrubber

    sample = rows[: min(limit, len(rows))]
    scrubber = Scrubber(resume=False, use_gliner=True)
    # Warm the ONNX session so download / compile is not in the timed window.
    scrubber.detect(sample[0].get("source_text") or "Ada Lovelace")
    chars = 0
    started = time.perf_counter()
    for row in sample:
        text = row.get("source_text") or ""
        chars += len(text)
        scrubber.detect(text)
    elapsed = time.perf_counter() - started
    per_1k = (elapsed / chars) * 1000 if chars else 0.0
    return {
        "docs": float(len(sample)),
        "chars": float(chars),
        "seconds": elapsed,
        "ms_per_1k_chars": per_1k * 1000,
    }


def print_gap_report(rows: list[dict[str, Any]], report: dict[str, Any]) -> None:
    """DEV-only: format cues for missed gold, no test-set access."""
    from unseeing import Scrubber

    target = {
        "CREDIT_CARD",
        "DATE_OF_BIRTH",
        "NATIONAL_ID",
        "SSN",
        "STREET_ADDRESS",
    }
    scrubber = Scrubber(resume=False)
    print("\n### Dev gap report (regex-only; not the held-out test sample)\n")
    buckets: dict[str, list[str]] = {name: [] for name in target}
    for row in rows:
        text = row.get("source_text") or ""
        gold = gold_spans(row)
        pred = pred_spans(text, scrubber.detect(text))
        _pairs, _fps, fns = match_entities(gold, pred)
        for span in fns:
            if span.entity_type in target and len(buckets[span.entity_type]) < 12:
                buckets[span.entity_type].append(span.value)
    for name, examples in buckets.items():
        stats = report.get("by_type", {}).get(name, {})
        print(
            f"{name}: tp={stats.get('tp', 0)} fp={stats.get('fp', 0)} "
            f"fn={stats.get('fn', 0)}  examples={examples}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--split",
        choices=("test", "dev"),
        default="test",
        help="test = held-out seed 20261010; dev = disjoint seed 20261011",
    )
    parser.add_argument("--dev-seed", type=int, default=DEFAULT_DEV_SEED)
    parser.add_argument(
        "--revision",
        default=DEFAULT_REVISION,
        help=f"HF dataset git commit (default: {DEFAULT_REVISION})",
    )
    parser.add_argument("--skip-ner", action="store_true")
    parser.add_argument("--skip-gliner", action="store_true")
    parser.add_argument("--gap-report", action="store_true")
    parser.add_argument("--latency", action="store_true")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    if args.split == "dev":
        seed = args.dev_seed
        exclude_seed = DEFAULT_SEED
        banner = "DEV sample (disjoint from held-out test; used for tuning only)"
    else:
        seed = args.seed
        exclude_seed = None
        banner = "Held-out TEST evaluation (not used to tune detectors)"
        if args.gap_report:
            raise SystemExit("--gap-report is allowed on --split=dev only")

    rows, meta = load_sample(n=args.n, seed=seed, revision=args.revision, exclude_seed=exclude_seed)
    meta["eval_split"] = args.split
    print(banner)
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

    regex_report = run_config(rows, use_ner=False, use_gliner=False)
    print_table("regex-only (default install, no resume, no NER)", regex_report)
    if args.gap_report:
        print_gap_report(rows, regex_report)

    ner_report: dict[str, Any] | None = None
    if not args.skip_ner:
        try:
            ner_report = run_config(rows, use_ner=True)
        except Exception as exc:  # noqa: BLE001 — report missing extra cleanly
            print(f"\nNER config skipped: {exc}", file=sys.stderr)
        else:
            print_table("regex + unseeing[ner] (spaCy en_core_web_sm)", ner_report)

    gliner_report: dict[str, Any] | None = None
    latency: dict[str, float] | None = None
    if not args.skip_gliner:
        try:
            gliner_report = run_config(rows, use_gliner=True)
        except Exception as exc:  # noqa: BLE001
            print(f"\nGLiNER config skipped: {exc}", file=sys.stderr)
        else:
            print_table(
                "regex + unseeing[gliner] (knowledgator/gliner-pii-small-v1.0 ONNX)",
                gliner_report,
            )
            if args.latency:
                try:
                    latency = measure_gliner_latency(rows)
                    print("\nGLiNER CPU latency (warm):")
                    print(json.dumps(latency, indent=2))
                except Exception as exc:  # noqa: BLE001
                    print(f"\nGLiNER latency skipped: {exc}", file=sys.stderr)

    payload = {
        "meta": meta,
        "regex_only": regex_report,
        "ner": ner_report,
        "gliner": gliner_report,
        "gliner_latency": latency,
    }
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
