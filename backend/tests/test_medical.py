from app.services.medical import extract_candidates


def test_candidate_has_traceability():
    candidates = extract_candidates([{
        "page": 2,
        "text": "Hemoglobin: 13.2 g/dl\nGlucose: 94 mg/dl",
        "method": "pdf_text",
    }])
    assert len(candidates) == 2
    assert candidates[0]["field"] == "hemoglobin"
    assert candidates[0]["source_page"] == 2
    assert candidates[0]["source_excerpt"] == "Hemoglobin: 13.2 g/dl"
    assert candidates[0]["status"] == "requires_human_review"


def test_candidate_is_not_a_diagnosis():
    candidates = extract_candidates([{"page": 1, "text": "HbA1c: 6.1 %", "method": "tesseract_ocr"}])
    assert candidates[0]["field"] == "hba1c"
    assert candidates[0]["confidence"] < 1.0
    assert candidates[0]["status"] == "requires_human_review"
