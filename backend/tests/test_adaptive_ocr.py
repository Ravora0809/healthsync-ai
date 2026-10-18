from app.services.medical import _local_then_optional_hosted_ocr, _ocr_disagreement_summary, _should_escalate_ocr
from app.services.evidence import build_evidence_report
from types import SimpleNamespace


def test_empty_or_short_text_requests_escalation():
    escalate, reason = _should_escalate_ocr("", {"local_mean_word_confidence": None})
    assert escalate is True
    assert "little or no readable text" in reason


def test_high_quality_local_ocr_does_not_escalate(monkeypatch):
    monkeypatch.setenv("OCR_ESCALATION_MIN_CONFIDENCE", "65")
    text = "Patient report: Hemoglobin 13.2 g/dL. Date 2026-10-15."
    quality = {
        "local_mean_word_confidence": 88.0,
        "local_low_confidence_word_ratio": 0.05,
    }
    escalate, _ = _should_escalate_ocr(text, quality)
    assert escalate is False


def test_low_confidence_or_many_uncertain_words_escalates(monkeypatch):
    monkeypatch.setenv("OCR_ESCALATION_MIN_CONFIDENCE", "65")
    text = "Patient report: Hemoglobin 13.2 g/dL. Date 2026-10-15."
    low_mean = _should_escalate_ocr(text, {
        "local_mean_word_confidence": 42.0,
        "local_low_confidence_word_ratio": 0.2,
    })
    many_low_words = _should_escalate_ocr(text, {
        "local_mean_word_confidence": 75.0,
        "local_low_confidence_word_ratio": 0.4,
    })
    assert low_mean[0] is True
    assert many_low_words[0] is True


def test_disagreement_summary_is_empty_for_matching_transcripts():
    result = _ocr_disagreement_summary("Hemoglobin 13.2 g/dL", "Hemoglobin 13.2 g/dL")
    assert result["disagreement_ratio"] == 0.0
    assert result["disagreement_segments"] == []


def test_disagreement_summary_exposes_differing_tokens_without_selecting_truth():
    result = _ocr_disagreement_summary("Medicine 10 mg daily", "Medicine 70 mg daily")
    assert result["disagreement_ratio"] > 0
    assert result["disagreement_segments"]
    assert {"local", "hosted", "difference_type"} <= set(result["disagreement_segments"][0])


def test_evidence_report_surfaces_ocr_disagreement():
    record = SimpleNamespace(
        id="record-1", title="Prescription", file_sha256="a" * 64,
        extracted_text="Medicine 10 mg daily", record_date=None, created_at=None,
        extracted_data={
            "candidates": [], "extraction_method": "tesseract_ocr", "page_count": 1,
            "ocr_quality": [{
                "page": 1, "review_recommended": True,
                "local_mean_word_confidence": 41.0,
                "cloud_escalation_reason": "low local confidence",
                "disagreement_ratio": 0.2,
                "disagreement_segments": [{"local": "10", "hosted": "70", "difference_type": "replace"}],
            }],
        },
    )
    report = build_evidence_report(record, [record])
    types = {flag["type"] for flag in report["flags"]}
    assert "ocr_quality_review" in types
    assert "ocr_engine_disagreement" in types
    assert len(report["ocr_quality"]) == 1


def test_hosted_ocr_is_not_called_without_consent(monkeypatch):
    monkeypatch.setattr("app.services.medical._ocr_image_with_quality", lambda image: (
        "uncertain transcription text", {
            "local_mean_word_confidence": 35.0,
            "local_low_confidence_word_ratio": 0.5,
            "local_word_count": 3,
            "local_text_characters": 29,
            "confidence_is_calibrated_probability": False,
        }
    ))
    def should_not_call_hosted(*args, **kwargs):
        raise AssertionError("Hosted OCR must not run without explicit consent")
    monkeypatch.setattr("app.services.medical._selected_ocr", should_not_call_hosted)
    text, method, diagnostic = _local_then_optional_hosted_ocr(
        object(), use_cloud_ocr=False, page_number=1, source_type="image"
    )
    assert text == "uncertain transcription text"
    assert method == "tesseract_ocr"
    assert diagnostic["cloud_escalated"] is False
    assert diagnostic["review_recommended"] is True


def test_opted_in_low_quality_page_escalates_and_keeps_disagreement(monkeypatch):
    monkeypatch.setattr("app.services.medical._ocr_image_with_quality", lambda image: (
        "Medicine 10 mg daily", {
            "local_mean_word_confidence": 35.0,
            "local_low_confidence_word_ratio": 0.5,
            "local_word_count": 4,
            "local_text_characters": 21,
            "confidence_is_calibrated_probability": False,
        }
    ))
    monkeypatch.setattr("app.services.medical._selected_ocr", lambda *args, **kwargs: ("Medicine 70 mg daily", "huggingface_vision_ocr"))
    text, method, diagnostic = _local_then_optional_hosted_ocr(
        object(), use_cloud_ocr=True, page_number=2, source_type="scanned_pdf_page"
    )
    assert text == "Medicine 70 mg daily"
    assert method == "huggingface_vision_ocr"
    assert diagnostic["cloud_escalated"] is True
    assert diagnostic["disagreement_ratio"] > 0
    assert diagnostic["disagreement_segments"]
    assert diagnostic["review_recommended"] is True


def test_hosted_failure_falls_back_to_local_text(monkeypatch):
    monkeypatch.setattr("app.services.medical._ocr_image_with_quality", lambda image: (
        "local transcription", {
            "local_mean_word_confidence": 30.0,
            "local_low_confidence_word_ratio": 0.8,
            "local_word_count": 2,
            "local_text_characters": 20,
            "confidence_is_calibrated_probability": False,
        }
    ))
    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr("app.services.medical._selected_ocr", fail)
    text, method, diagnostic = _local_then_optional_hosted_ocr(
        object(), use_cloud_ocr=True, page_number=1, source_type="image"
    )
    assert text == "local transcription"
    assert method == "tesseract_ocr"
    assert diagnostic["cloud_fallback_used"] is True
    assert "provider unavailable" in diagnostic["cloud_error"]


def test_huggingface_credit_error_falls_back_to_openrouter(monkeypatch):
    from app.services import medical, ai

    monkeypatch.setattr(medical.settings, "hf_token", "hf-test-token")
    monkeypatch.setattr(ai, "openrouter_configured", lambda: True)
    monkeypatch.setattr(
        medical, "_hf_vision_transcribe",
        lambda image: (_ for _ in ()).throw(RuntimeError("Hugging Face vision OCR failed (402): no credits")),
    )
    monkeypatch.setattr(ai, "openrouter_vision_transcribe", lambda image: "Prescription text from OpenRouter")

    text, method = medical._selected_ocr(object(), use_cloud_ocr=True, filename="page-1")
    assert text == "Prescription text from OpenRouter"
    assert method == "openrouter_vision_ocr"


def test_no_hosted_provider_gives_actionable_error(monkeypatch):
    from app.services import medical, ai

    monkeypatch.setattr(medical.settings, "hf_token", "hf-test-token")
    monkeypatch.setattr(ai, "openrouter_configured", lambda: False)
    monkeypatch.setattr(
        medical, "_hf_vision_transcribe",
        lambda image: (_ for _ in ()).throw(RuntimeError("Hugging Face vision OCR failed (402): no credits")),
    )
    try:
        medical._selected_ocr(object(), use_cloud_ocr=True, filename="page-1")
    except RuntimeError as exc:
        assert "Configure OPENROUTER_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected actionable provider error")
