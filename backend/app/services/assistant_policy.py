"""Local server-side scope and safety rules for the record assistant."""
import re

_RECORD_SCOPE_TERMS = {
    "medical", "health record", "my record", "records", "report", "lab", "laboratory", "blood test",
    "result", "prescription", "prescribed", "medicine", "medication", "tablet", "capsule", "drug",
    "dose", "dosage", "strength", "frequency", "pharmacy", "allergy", "allergies", "vaccination",
    "vaccine", "immunization", "hospital", "discharge", "diagnosis", "diagnosed", "clinical", "scan",
    "imaging", "follow-up", "follow up", "doctor", "clinician", "test report", "my health",
}


def is_record_question(question: str) -> bool:
    q = question.casefold()
    return any(term in q for term in _RECORD_SCOPE_TERMS)


def requests_new_treatment_advice(question: str) -> bool:
    q = question.casefold()
    patterns = (
        r"\bshould i (?:take|stop|start|skip|increase|decrease|change|double)\b",
        r"\bcan i (?:take|stop|start|combine|mix)\b",
        r"\b(?:recommend|prescribe) (?:me )?(?:a|some|any)? ?(?:medicine|medication|drug|tablet|treatment)\b",
        r"\bwhat (?:medicine|medication|drug|treatment) should i take\b",
        r"\b(?:diagnose me|what disease do i have|is this cancer|is this diabetes)\b",
        r"\bchange my (?:dose|dosage|medication)\b",
    )
    return any(re.search(pattern, q) for pattern in patterns)
