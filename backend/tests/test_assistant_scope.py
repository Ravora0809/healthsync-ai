from app.services.assistant_policy import is_record_question as _is_record_question, requests_new_treatment_advice as _requests_new_treatment_advice


def test_assistant_accepts_record_and_prescription_questions():
    assert _is_record_question("What medicine and dose are written on my latest prescription?")
    assert _is_record_question("Summarize my latest lab report")


def test_assistant_refuses_unrelated_questions():
    assert not _is_record_question("Write me a fantasy story about dragons")
    assert not _is_record_question("How do I fix a React component?")


def test_assistant_flags_new_treatment_advice():
    assert _requests_new_treatment_advice("Should I stop my medicine?")
    assert _requests_new_treatment_advice("Can I take a new medication?")
    assert not _requests_new_treatment_advice("What dose was written on the prescription?")
