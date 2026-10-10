"""Unit tests for the held-out eval scorer. Does not download the dataset."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("unseeing_benchmark", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_merge_adjacent_given_and_surname(bench) -> None:
    text = "Hello Ava Chen today"
    gold = [
        bench.Span("PERSON", 6, 9, "Ava"),
        bench.Span("PERSON", 10, 14, "Chen"),
        bench.Span("EMAIL", 20, 28, "x@y.com"),
    ]
    merged = bench.merge_person_spans(gold, text)
    people = [s for s in merged if s.entity_type == "PERSON"]
    assert len(people) == 1
    assert people[0].value == "Ava Chen"
    assert any(s.entity_type == "EMAIL" for s in merged)


def test_overlap_match_is_one_to_one(bench) -> None:
    gold = [bench.Span("EMAIL", 0, 10, "a@b.com")]
    pred = [
        bench.Span("EMAIL", 0, 5, "a@b"),
        bench.Span("EMAIL", 3, 10, "b.com"),
    ]
    pairs, fps, fns = bench.match_entities(gold, pred)
    assert len(pairs) == 1
    assert len(fps) == 1
    assert fns == []


def test_overall_skips_types_with_no_gold(bench) -> None:
    gold = [[bench.Span("EMAIL", 0, 5, "a@b.c")]]
    pred = [
        [
            bench.Span("EMAIL", 0, 5, "a@b.c"),
            bench.Span("URL", 10, 20, "http://x"),
        ]
    ]
    report = bench.score(gold, pred)
    assert report["overall"]["tp"] == 1
    assert report["overall"]["fp"] == 0
    assert "URL" in report["unlabeled_predictions"]
    assert "URL" not in report["by_type"]


def test_linkedin_prediction_counts_as_url(bench) -> None:
    text = "see https://linkedin.com/in/ava"
    pred = bench.pred_spans(
        text,
        [
            type(
                "D",
                (),
                {"type_name": "LINKEDIN", "start": 4, "end": 31, "value": text[4:31]},
            )()
        ],
    )
    assert pred[0].entity_type == "URL"
