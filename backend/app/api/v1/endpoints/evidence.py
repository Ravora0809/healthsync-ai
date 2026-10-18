import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, MedicalRecord, AuditEvent
from app.services.evidence import build_evidence_report
from app.services.medical import sha256_file
from app.services.ai import openrouter_configured, openrouter_analyze_medical_record, hf_analyze_medical_record
from app.core.config import settings
from app.services.verification import VerifyItemRequest, apply_item_verification, update_record_verification_status
from pathlib import Path

router = APIRouter(tags=["Evidence Engine"])


@router.post("/analyze/{record_id}")
def analyze(record_id: str, use_openrouter: bool = Query(False), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        rid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(400, "Invalid record ID.")
    record = db.query(MedicalRecord).filter(MedicalRecord.id == rid, MedicalRecord.owner_user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found.")
    others = db.query(MedicalRecord).filter(MedicalRecord.owner_user_id == user.id).all()

    # Clicking Analyze triggers structured extraction, using Hugging Face first and OpenRouter as fallback.
    # Evidence review still succeeds if the hosted model is unavailable or out of credits.
    extracted_data = dict(record.extracted_data or {})
    if not use_openrouter:
        clinical_analysis = {
            "status": "consent_required",
            "message": "Local evidence analysis was completed. Click Analyze again and confirm hosted structured extraction. Hugging Face is tried first with HF_TOKEN; OpenRouter is the fallback if configured. Low-quality original pages may also be sent to hosted vision OCR.",
            "medicines": [], "tests_and_results": [],
            "documented_instructions": {"food": [], "exercise": [], "precautions": [], "temperature": [], "medicine_storage": [], "hospital_follow_up": []},
            "not_specified": ["AI extraction not run because cloud analysis was not approved"],
        }
    elif (settings.hf_token.strip() or openrouter_configured()) and (record.extracted_text or "").strip():
        try:
            # If previous local OCR diagnostics were poor, retry the document pages through the
            # quality-gated adaptive OCR path before asking the text model to structure the results.
            old_data = dict(record.extracted_data or {})
            old_diagnostics = old_data.get("ocr_quality", [])
            needs_vision_retry = any(
                bool(d.get("review_recommended") or d.get("cloud_escalation_needed"))
                and not bool(d.get("cloud_escalated"))
                for d in old_diagnostics if isinstance(d, dict)
            )
            if needs_vision_retry and Path(record.storage_key).is_file():
                from app.services.medical import extract_document, extract_candidates
                refreshed = extract_document(record.storage_key, use_cloud_ocr=True)
                # Keep the refresh only if the OCR text changed or an alternate provider was attempted.
                old_text = record.extracted_text or ""
                new_text = refreshed.get("text") or ""
                old_data["analysis_ocr_retry_attempted"] = True
                refreshed_diagnostics = refreshed.get("ocr_quality", old_diagnostics)
                old_data["ocr_quality"] = refreshed_diagnostics
                old_data["analysis_ocr_retry_used"] = any(d.get("cloud_escalated") for d in refreshed_diagnostics)
                if new_text.strip() and (new_text.strip() != old_text.strip() or old_data["analysis_ocr_retry_used"]):
                    record.extracted_text = new_text
                    old_data["extraction_method"] = refreshed.get("extraction_method", old_data.get("extraction_method"))
                    old_data["page_count"] = refreshed.get("page_count", old_data.get("page_count"))
                    old_data["candidates"] = extract_candidates(refreshed.get("pages", []))
                extracted_data = old_data
                record.extracted_data = extracted_data
            analysis_args = {
                "text": record.extracted_text or "",
                "title": record.title,
                "record_type": record.record_type or "other",
                "date_text": record.record_date.isoformat() if record.record_date else None,
            }
            if settings.hf_token.strip():
                try:
                    clinical_analysis = hf_analyze_medical_record(**analysis_args)
                except Exception as hf_exc:
                    if not openrouter_configured():
                        raise
                    clinical_analysis = openrouter_analyze_medical_record(**analysis_args)
                    clinical_analysis["provider_fallback_reason"] = f"Hugging Face unavailable: {str(hf_exc)[:220]}"
            else:
                clinical_analysis = openrouter_analyze_medical_record(**analysis_args)
            clinical_analysis["analysis_error"] = None
        except Exception as exc:
            clinical_analysis = {
                "status": "unavailable",
                "message": "AI structured extraction could not finish. Existing OCR text and local evidence are retained; retry Analyze or compare with the original.",
                "analysis_error": str(exc)[:400],
                "medicines": [], "tests_and_results": [],
                "documented_instructions": {"food": [], "exercise": [], "precautions": [], "temperature": [], "medicine_storage": [], "hospital_follow_up": []},
                "not_specified": ["medicine details", "diet/food instructions", "exercise instructions", "precautions", "temperature guidance", "medicine storage conditions", "hospital follow-up interval"],
            }
    elif not (settings.hf_token.strip() or openrouter_configured()):
        clinical_analysis = {
            "status": "not_configured",
            "message": "No hosted analysis model is configured. Add HF_TOKEN for Hugging Face (primary), or OPENROUTER_API_KEY as fallback, to the root .env and restart the backend.",
            "medicines": [], "tests_and_results": [],
            "documented_instructions": {"food": [], "exercise": [], "precautions": [], "temperature": [], "medicine_storage": [], "hospital_follow_up": []},
            "not_specified": ["medicine details", "diet/food instructions", "exercise instructions", "precautions", "temperature guidance", "medicine storage conditions", "hospital follow-up interval"],
        }
    else:
        clinical_analysis = {
            "status": "insufficient_text",
            "message": "No readable OCR text is available for AI extraction. Retry OCR or review the original manually.",
            "medicines": [], "tests_and_results": [],
            "documented_instructions": {"food": [], "exercise": [], "precautions": [], "temperature": [], "medicine_storage": [], "hospital_follow_up": []},
            "not_specified": ["medicine details", "diet/food instructions", "exercise instructions", "precautions", "temperature guidance", "medicine storage conditions", "hospital follow-up interval"],
        }
    extracted_data["clinical_analysis"] = clinical_analysis
    record.extracted_data = extracted_data
    db.add(record)
    db.flush()

    report = build_evidence_report(record, others)
    exists = Path(record.storage_key).is_file()
    current_hash = sha256_file(record.storage_key) if exists else None
    report["integrity"] = {
        "file_exists": exists,
        "hash_matches": bool(current_hash and current_hash == record.file_sha256),
        "stored_sha256": record.file_sha256,
        "current_sha256": current_hash,
    }
    if not report["integrity"]["hash_matches"]:
        report["flags"].append({"type": "integrity_mismatch", "severity": "high_review", "message": "The stored file is missing or its hash differs from the original upload. Do not rely on extracted evidence until reviewed."})
    db.add(AuditEvent(owner_user_id=user.id, record_id=record.id, action="evidence_analyzed", details={"candidate_count": len(report["candidate_values"]), "flag_count": len(report["flags"]), "clinical_analysis_status": clinical_analysis.get("status"), "medicine_candidate_count": len(clinical_analysis.get("medicines", []))}))
    db.commit()
    return report


@router.post("/verify/{record_id}")
def verify_item(record_id: str, payload: VerifyItemRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Save the user's review/correction for one extracted fact without changing source evidence."""
    try:
        rid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(400, "Invalid record ID.")
    record = db.query(MedicalRecord).filter(MedicalRecord.id == rid, MedicalRecord.owner_user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found.")
    data = dict(record.extracted_data or {})
    item, data, clinical, saved_status = apply_item_verification(data, payload)
    if payload.item_type != "candidate":
        data["clinical_analysis"] = clinical
    record.extracted_data = data
    counts = update_record_verification_status(record, data)
    db.add(AuditEvent(owner_user_id=user.id, record_id=record.id, action="record_item_verified", details={
        "item_type": payload.item_type, "index": payload.index, "section": payload.section,
        "status": saved_status, "corrected_fields": list(payload.corrected_values.keys()),
    }))
    db.commit()
    return {
        "record_id": str(record.id), "item_type": payload.item_type, "index": payload.index,
        "section": payload.section, "item": item, "verification_status": saved_status,
        "verification_summary": counts,
        "message": "Review saved. This records your comparison with the source; it is not clinical approval."
    }

@router.get("/timeline/{field_name}")
def timeline(field_name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    records = db.query(MedicalRecord).filter(MedicalRecord.owner_user_id == user.id).order_by(MedicalRecord.record_date.asc().nullslast(), MedicalRecord.created_at.asc()).all()
    points = []
    for record in records:
        for candidate in (record.extracted_data or {}).get("candidates", []):
            if candidate.get("field", "").lower() == field_name.lower():
                points.append({
                    "record_id": str(record.id), "record_title": record.title,
                    "date": record.record_date.isoformat() if record.record_date else (record.created_at.isoformat() if record.created_at else None),
                    "value": candidate.get("value"), "unit": candidate.get("unit", ""),
                    "source_page": candidate.get("source_page"),
                    "source_excerpt": candidate.get("source_excerpt"),
                    "file_sha256": record.file_sha256,
                })
    return {"field": field_name, "points": points, "note": "Historical display only. Values and units require human review; this endpoint does not interpret clinical significance."}
