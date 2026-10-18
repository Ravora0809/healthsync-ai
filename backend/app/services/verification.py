"""Persistent, source-preserving verification of extracted medical-record facts."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field


class VerifyItemRequest(BaseModel):
    item_type: Literal["medicine", "test", "instruction", "candidate"]
    index: int = Field(ge=0, le=1000)
    section: str | None = None
    status: Literal["user_verified", "rejected_as_incorrect"] = "user_verified"
    corrected_values: dict[str, str | None] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=500)


# The original source excerpt is immutable through this endpoint, preserving evidence provenance.
_EDITABLE_FIELDS = {
    "medicine": {"name_as_written", "strength_as_written", "dose_as_written", "route_as_written",
                 "frequency_as_written", "duration_as_written", "instructions_as_written",
                 "storage_as_written", "indication_as_written"},
    "test": {"name_as_written", "result_as_written", "unit_as_written"},
    "instruction": {"text"},
    "candidate": {"field", "value", "unit"},
}
INSTRUCTION_SECTIONS = {"food", "exercise", "precautions", "temperature", "medicine_storage", "hospital_follow_up"}
TERMINAL_VERIFICATION = {"user_verified", "corrected_and_user_verified", "rejected_as_incorrect"}


def apply_item_verification(data: dict, payload: VerifyItemRequest):
    """Apply one allow-listed review action to an extracted-data object in place."""
    clinical = data.get("clinical_analysis") if isinstance(data.get("clinical_analysis"), dict) else {}
    if payload.item_type == "candidate":
        items = data.get("candidates", [])
    elif payload.item_type == "medicine":
        items = clinical.get("medicines", [])
    elif payload.item_type == "test":
        items = clinical.get("tests_and_results", [])
    else:
        if payload.section not in INSTRUCTION_SECTIONS:
            raise HTTPException(422, "A valid instruction section is required.")
        instructions = clinical.get("documented_instructions", {})
        items = instructions.get(payload.section, []) if isinstance(instructions, dict) else []

    if not isinstance(items, list) or payload.index >= len(items):
        raise HTTPException(404, "Extracted item not found. Run Analyze first and reload the record.")
    item = items[payload.index]
    if not isinstance(item, dict):
        raise HTTPException(422, "This extracted item cannot be verified.")
    if payload.status == "rejected_as_incorrect" and payload.corrected_values:
        raise HTTPException(422, "Do not submit corrections while marking an item incorrect.")

    allowed_fields = _EDITABLE_FIELDS[payload.item_type]
    corrected_keys = []
    for key, value in payload.corrected_values.items():
        if key not in allowed_fields:
            raise HTTPException(422, f"Field '{key}' cannot be edited from this verification form.")
        if value is not None and len(value) > 1000:
            raise HTTPException(422, f"Field '{key}' is too long (maximum 1000 characters).")
        item[key] = value.strip() if isinstance(value, str) else ""
        corrected_keys.append(key)

    saved_status = "corrected_and_user_verified" if corrected_keys and payload.status == "user_verified" else payload.status
    item["verification_status"] = saved_status
    item["verification_note"] = (payload.note or "").strip() or None
    item["verified_at"] = datetime.now(timezone.utc).isoformat()
    return item, data, clinical, saved_status


def update_record_verification_status(record, data: dict) -> dict:
    """Summarize review completion without implying clinician approval."""
    clinical = data.get("clinical_analysis") if isinstance(data.get("clinical_analysis"), dict) else {}
    all_items = []
    all_items.extend(data.get("candidates", []) if isinstance(data.get("candidates", []), list) else [])
    all_items.extend(clinical.get("medicines", []) if isinstance(clinical.get("medicines", []), list) else [])
    all_items.extend(clinical.get("tests_and_results", []) if isinstance(clinical.get("tests_and_results", []), list) else [])
    sections = clinical.get("documented_instructions", {})
    if isinstance(sections, dict):
        for section in INSTRUCTION_SECTIONS:
            if isinstance(sections.get(section), list):
                all_items.extend(sections[section])
    reviewed = sum(1 for item in all_items if isinstance(item, dict) and item.get("verification_status") in TERMINAL_VERIFICATION)
    rejected = any(isinstance(item, dict) and item.get("verification_status") == "rejected_as_incorrect" for item in all_items)
    if all_items and reviewed == len(all_items):
        record.verification_status = "reviewed_with_rejections" if rejected else "reviewed_by_user"
    elif reviewed:
        record.verification_status = "partially_reviewed"
    else:
        record.verification_status = "pending_review"
    return {"total_items": len(all_items), "reviewed_items": reviewed, "record_status": record.verification_status}
