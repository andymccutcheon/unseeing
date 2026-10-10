from __future__ import annotations

from unseeing import Scrubber


def test_each_labeled_document_roundtrips(labeled_documents: list[dict]) -> None:
    for doc in labeled_documents:
        scrubber = Scrubber(resume=doc.get("mode") == "resume")
        out = scrubber.scrub(doc["text"])
        for entity in doc["entities"]:
            assert entity["value"] not in out, f"{doc['id']} leaked {entity['type']}"
        assert scrubber.restore(out) == doc["text"]
