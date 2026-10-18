from app.services.model_clients import validate_model_candidates


def test_qwen_candidate_is_kept_only_when_evidence_and_value_are_literal():
    pages = [{"page": 1, "text": "Hemoglobin: 13.2 g/dL\nGlucose: 94 mg/dL", "method": "paddleocr_vl_1_6"}]
    predictions = [
        {"field": "hemoglobin", "value": "13.2", "unit": "g/dL", "source_page": 1, "source_excerpt": "Hemoglobin: 13.2 g/dL"},
        {"field": "glucose", "value": "120", "unit": "mg/dL", "source_page": 1, "source_excerpt": "Glucose: 94 mg/dL"},
        {"field": "diagnosis", "value": "diabetes", "unit": "", "source_page": 1, "source_excerpt": "Not present in this page"},
    ]
    accepted, rejected = validate_model_candidates(pages, predictions)
    assert len(accepted) == 1
    assert rejected == 2
    assert accepted[0]["value"] == "13.2"
    assert accepted[0]["source_line"] == 1
    assert accepted[0]["status"] == "requires_human_review"
    assert accepted[0]["confidence_type"] == "not_calibrated"
    assert accepted[0]["extraction_method"] == "huggingface_qwen_extractor"


def test_candidate_validator_does_not_invent_page_numbers():
    pages = [{"page": 1, "text": "TSH: 2.4 mIU/L", "method": "pdf_text"}]
    accepted, rejected = validate_model_candidates(pages, [
        {"field": "tsh", "value": "2.4", "unit": "mIU/L", "source_page": 4, "source_excerpt": "TSH: 2.4 mIU/L"}
    ])
    assert accepted == []
    assert rejected == 1


def test_hosted_hf_candidates_are_evidence_validated_and_not_mislabeled_finetuned(monkeypatch):
    import json
    from app.core.config import settings
    from app.services import model_clients

    body = {
        "choices": [{
            "message": {
                "content": json.dumps({"candidates": [
                    {"field": "hemoglobin", "value": "13.2", "unit": "g/dL", "source_page": 1,
                     "source_excerpt": "Hemoglobin: 13.2 g/dL"},
                    {"field": "glucose", "value": "120", "unit": "mg/dL", "source_page": 1,
                     "source_excerpt": "Glucose: 94 mg/dL"},
                ]})
            }
        }]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(body).encode("utf-8")

    monkeypatch.setattr(settings, "hf_token", "hf_test_token")
    monkeypatch.setattr(model_clients.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    accepted, rejected = model_clients.hf_extract_candidates([
        {"page": 1, "text": "Hemoglobin: 13.2 g/dL\nGlucose: 94 mg/dL", "method": "pdf_text"}
    ])
    assert len(accepted) == 1
    assert rejected == 1
    assert accepted[0]["value"] == "13.2"
    assert accepted[0]["extraction_method"] == "huggingface_qwen_extractor"
    assert accepted[0]["status"] == "requires_human_review"


def test_local_adapter_config_requires_existing_peft_adapter(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services.local_model_client import local_qwen_extractor_configured

    monkeypatch.setattr(settings, "local_qwen_adapter_dir", str(tmp_path))
    assert local_qwen_extractor_configured() is False
    (tmp_path / "adapter_config.json").write_text("{}", encoding="utf-8")
    assert local_qwen_extractor_configured() is True


def test_local_qwen_response_is_source_validated():
    import json
    from app.services.local_model_client import _parse_and_validate_response

    pages = [{"page": 1, "text": "Hemoglobin: 13.2 g/dL"}]
    response = json.dumps({"candidates": [
        {"field": "hemoglobin", "value": "13.2", "unit": "g/dL",
         "source_page": 1, "source_excerpt": "Hemoglobin: 13.2 g/dL"},
        {"field": "glucose", "value": "120", "unit": "mg/dL",
         "source_page": 1, "source_excerpt": "Hemoglobin: 13.2 g/dL"},
    ]})
    accepted, rejected = _parse_and_validate_response(pages, response)
    assert len(accepted) == 1
    assert rejected == 1
    assert accepted[0]["extraction_method"] == "local_qwen_lora_extractor"


def test_hf_chat_completion_uses_server_token_and_returns_chat_answer(monkeypatch):
    import json
    from app.core.config import settings
    from app.services import model_clients

    body = {"choices": [{"message": {"content": "The report states hemoglobin is 13.2 g/dL."}}]}
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(body).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(settings, "hf_token", "hf_test_private_token")
    monkeypatch.setattr(settings, "hf_model_id", "Qwen/Qwen3-4B:fastest")
    monkeypatch.setattr(model_clients.urllib.request, "urlopen", fake_urlopen)
    answer = model_clients.hf_chat_completion(
        [{"role": "user", "content": "What does my report say?"}], max_tokens=120, temperature=0.0
    )
    assert answer == "The report states hemoglobin is 13.2 g/dL."
    assert captured["url"] == settings.hf_chat_endpoint
    assert captured["auth"] == "Bearer hf_test_private_token"
    assert captured["body"]["model"] == "Qwen/Qwen3-4B:fastest"
    assert captured["timeout"] == 75


def test_hf_chat_completion_requires_token(monkeypatch):
    import pytest
    from app.core.config import settings
    from app.services.model_clients import hf_chat_completion

    monkeypatch.setattr(settings, "hf_token", "")
    with pytest.raises(RuntimeError, match="HF_TOKEN is not configured"):
        hf_chat_completion([{"role": "user", "content": "hello"}])
