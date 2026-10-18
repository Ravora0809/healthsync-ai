import json

from app.core.config import settings
from app.services import ai


def test_openrouter_analysis_parses_and_source_checks_document_fields(monkeypatch):
    raw = {
        "document_type": "Prescription",
        "provider": "Dr Example",
        "document_date": "2026-10-01",
        "medicines": [
            {
                "name_as_written": "Exampletab",
                "strength_as_written": "10 mg",
                "dose_as_written": "1 tablet",
                "route_as_written": "oral",
                "frequency_as_written": "once daily",
                "duration_as_written": "5 days",
                "instructions_as_written": "after food",
                "storage_as_written": "",
                "indication_as_written": "",
                "common_uses_general": "General reference only.",
                "source_excerpt": "Exampletab 10 mg - 1 tablet once daily for 5 days after food",
            },
            {
                "name_as_written": "InventedMed",
                "strength_as_written": "20 mg",
                "dose_as_written": "",
                "route_as_written": "",
                "frequency_as_written": "",
                "duration_as_written": "",
                "instructions_as_written": "",
                "storage_as_written": "",
                "indication_as_written": "",
                "common_uses_general": "Unverified generated string",
                "source_excerpt": "InventedMed 20 mg once daily",
            },
        ],
        "tests_and_results": [],
        "documented_instructions": {
            "food": [{"text": "after food", "source_excerpt": "Exampletab 10 mg - 1 tablet once daily for 5 days after food"}],
            "exercise": [{"text": "Exercise daily", "source_excerpt": "exercise every day"}],
            "precautions": [], "temperature": [], "medicine_storage": [], "hospital_follow_up": [],
        },
        "uncertain_items": [],
        "general_education": {"food": "General balanced diet, not patient-specific.", "exercise": "General activity only if cleared by the clinician."},
        "not_specified": ["temperature guidance"],
    }
    monkeypatch.setattr(ai, "openrouter_configured", lambda: True)
    monkeypatch.setattr(ai, "_post_chat", lambda *args, **kwargs: json.dumps(raw))
    result = ai.openrouter_analyze_medical_record(
        text="Exampletab 10 mg - 1 tablet once daily for 5 days after food",
        title="Prescription", record_type="prescription"
    )
    assert result["status"] == "complete"
    assert result["medicines"][0]["source_verified"] is True
    assert result["medicines"][1]["source_verified"] is False
    assert "Not shown" in result["medicines"][1]["common_uses_general"]
    assert len(result["documented_instructions"]["food"]) == 1
    assert result["documented_instructions"]["exercise"] == []
    assert result["general_education"]["food"] == "General balanced diet, not patient-specific."
    assert "exercise instructions" in result["not_specified"]


def test_openrouter_analysis_handles_too_little_text():
    result = ai.openrouter_analyze_medical_record(text="", title="Rx", record_type="prescription")
    assert result["status"] == "insufficient_text"
    assert result["medicines"] == []


def test_json_parser_accepts_fenced_json():
    result = ai._parse_json_object('```json\n{"medicines": []}\n```')
    assert result == {"medicines": []}


def test_huggingface_structured_analysis_uses_hf_chat_client(monkeypatch):
    import json
    from app.core.config import settings
    from app.services import ai, model_clients

    raw = {
        "document_type": "Lab report", "provider": "", "document_date": "",
        "medicines": [], "tests_and_results": [],
        "documented_instructions": {k: [] for k in ("food", "exercise", "precautions", "temperature", "medicine_storage", "hospital_follow_up")},
        "uncertain_items": [], "general_education": {}, "not_specified": [],
    }
    captured = {}
    monkeypatch.setattr(settings, "hf_token", "hf_test_token")
    def fake_hf_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return json.dumps(raw)
    monkeypatch.setattr(model_clients, "hf_chat_completion", fake_hf_chat)
    result = ai.hf_analyze_medical_record(text="Lab report issued 2026-10-01", title="Lab", record_type="lab_report")
    assert result["status"] == "complete"
    assert result["ai_provider"] == "huggingface"
    assert result["model"] == settings.hf_model_id
    assert captured["kwargs"]["model"] == settings.hf_model_id
    assert "OCR transcription" in captured["messages"][1]["content"]
