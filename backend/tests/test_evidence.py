from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.evidence import build_evidence_report


def record(record_id, title, candidates, text="source report text"):
    return SimpleNamespace(
        id=record_id,
        title=title,
        file_sha256="a" * 64,
        extracted_text=text,
        extracted_data={"candidates": candidates, "extraction_method": "pdf_text", "page_count": 1},
        record_date=None,
        created_at=datetime.now(timezone.utc),
    )


def test_evidence_keeps_source_provenance_and_comparison():
    current = record("current", "CBC report", [{
        "field": "hemoglobin", "value": "13.2", "unit": "g/dl",
        "evidence_id": "p1-l1-hemoglobin-1", "source_page": 1,
        "source_line": 1, "source_excerpt": "Hemoglobin: 13.2 g/dl",
        "confidence": 0.68, "status": "requires_human_review",
    }])
    older = record("older", "Old CBC", [{
        "field": "hemoglobin", "value": "12.8", "unit": "g/dl",
        "evidence_id": "p1-l1-hemoglobin-1", "source_page": 1,
        "source_line": 1, "source_excerpt": "Hemoglobin: 12.8 g/dl",
        "confidence": 0.68, "status": "requires_human_review",
    }])
    report = build_evidence_report(current, [current, older])
    assert report["candidate_values"][0]["source_excerpt"] == "Hemoglobin: 13.2 g/dl"
    assert len(report["cross_record_comparisons"]) == 1
    assert "Not a diagnosis" in report["disclaimer"]
