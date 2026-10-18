from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.verification import (
    VerifyItemRequest,
    apply_item_verification,
    update_record_verification_status,
)


def sample_data():
    return {
        "candidates": [{"field": "glucose", "value": "120", "unit": "mg/dL", "source_excerpt": "Glucose 120 mg/dL"}],
        "clinical_analysis": {
            "status": "complete",
            "medicines": [{"name_as_written": "Med A", "dose_as_written": "1 tablet", "source_excerpt": "Med A 1 tablet"}],
            "tests_and_results": [],
            "documented_instructions": {"food": [{"text": "after food", "source_excerpt": "after food"}]},
        },
    }


def test_user_can_correct_and_verify_medicine_without_changing_source_excerpt():
    data = sample_data()
    payload = VerifyItemRequest(
        item_type="medicine", index=0, status="user_verified",
        corrected_values={"dose_as_written": "Half tablet"},
        note="Compared with original handwriting",
    )
    item, updated, _clinical, status = apply_item_verification(data, payload)
    assert item["dose_as_written"] == "Half tablet"
    assert item["source_excerpt"] == "Med A 1 tablet"
    assert item["verification_status"] == status == "corrected_and_user_verified"
    assert updated["clinical_analysis"]["medicines"][0]["verification_note"] == "Compared with original handwriting"


def test_marking_candidate_incorrect_is_saved_as_review_not_verified_truth():
    data = sample_data()
    item, updated, _clinical, status = apply_item_verification(
        data, VerifyItemRequest(item_type="candidate", index=0, status="rejected_as_incorrect")
    )
    assert item["verification_status"] == status == "rejected_as_incorrect"
    record = SimpleNamespace(verification_status="pending_review")
    counts = update_record_verification_status(record, updated)
    assert counts["record_status"] == "partially_reviewed"


def test_correction_cannot_rewrite_source_excerpt():
    with pytest.raises(HTTPException) as exc:
        apply_item_verification(
            sample_data(), VerifyItemRequest(item_type="medicine", index=0, corrected_values={"source_excerpt": "fabricated evidence"})
        )
    assert exc.value.status_code == 422


def test_verification_rejects_missing_item_index():
    with pytest.raises(HTTPException) as exc:
        apply_item_verification(sample_data(), VerifyItemRequest(item_type="medicine", index=12))
    assert exc.value.status_code == 404


def test_all_accepted_items_become_reviewed_by_user_not_clinically_verified():
    data = sample_data()
    for payload in [
        VerifyItemRequest(item_type="candidate", index=0),
        VerifyItemRequest(item_type="medicine", index=0),
        VerifyItemRequest(item_type="instruction", section="food", index=0),
    ]:
        apply_item_verification(data, payload)
    record = SimpleNamespace(verification_status="pending_review")
    counts = update_record_verification_status(record, data)
    assert counts == {"total_items": 3, "reviewed_items": 3, "record_status": "reviewed_by_user"}
