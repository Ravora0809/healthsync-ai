import uuid
from pathlib import Path
from datetime import date
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import User, MedicalRecord, AuditEvent
from app.services.medical import sha256_file, extract_document, extract_candidates, extractive_summary
from app.services.ai import openrouter_configured, openrouter_summarize
from app.services.model_clients import hf_summarize_record

router = APIRouter(tags=["Medical Records"])
allowed = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def out(r):
    return {
        "id": str(r.id), "title": r.title, "record_type": r.record_type,
        "provider_name": r.provider_name, "doctor_name": r.doctor_name,
        "record_date": r.record_date.isoformat() if r.record_date else None,
        "original_filename": r.original_filename, "file_sha256": r.file_sha256,
        "verification_status": r.verification_status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "extracted_data": r.extracted_data or {}, "extracted_text": r.extracted_text,
    }


@router.post("")
async def upload(
    file: UploadFile = File(...), title: str = Form(...),
    record_type: str = Form("other"), provider_name: str | None = Form(None),
    doctor_name: str | None = Form(None), record_date: date | None = Form(None),
    use_cloud_ocr: bool = Form(True), use_openrouter_summary: bool = Form(True),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    filename = Path(file.filename or "upload").name
    extension = Path(filename).suffix.lower()
    if extension not in allowed:
        raise HTTPException(415, "Supported files: PDF, PNG, JPG, JPEG, WEBP, and TIFF.")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(400, "File is empty.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB upload limit.")
    if extension == ".pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(415, "Invalid PDF signature.")
    if extension in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8"):
        raise HTTPException(415, "Invalid JPEG signature.")
    if extension == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(415, "Invalid PNG signature.")
    if extension == ".webp" and (len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP"):
        raise HTTPException(415, "Invalid WEBP signature.")
    if extension in {".tif", ".tiff"} and content[:4] not in {b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"}:
        raise HTTPException(415, "Invalid TIFF signature.")

    folder = Path(settings.upload_dir) / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    storage_path = folder / f"{uuid.uuid4().hex}{extension}"
    storage_path.write_bytes(content)
    try:
        extracted = extract_document(str(storage_path), use_cloud_ocr=use_cloud_ocr)
    except Exception as exc:
        storage_path.unlink(missing_ok=True)
        message = str(exc).casefold()
        if "not configured" in message or "no provider token" in message:
            status = 503
        elif use_cloud_ocr or "model worker" in message or "paddleocr-vl" in message:
            status = 502
        else:
            status = 422
        raise HTTPException(status, f"Document extraction failed: {exc}")

    # The default structured extractor is deterministic and local. If the developer has
    # installed a trained PEFT adapter, prefer that local model without sending OCR text out.
    # Hosted Hugging Face extraction is only considered when no local adapter is configured
    # and the user explicitly opted into hosted processing for this upload.
    candidate_values = extract_candidates(extracted["pages"])
    structured_extraction_method = "regex_baseline"
    extraction_warnings = []
    model_candidate_rejections = 0
    ocr_diagnostics = extracted.get("ocr_quality", [])
    escalated_page_numbers = {
        int(item.get("page", 0))
        for item in ocr_diagnostics
        if item.get("cloud_escalated") and item.get("page") is not None
    }
    escalation_needed = any(item.get("cloud_escalation_needed") for item in ocr_diagnostics)

    try:
        from app.services.local_model_client import local_qwen_extractor_configured, local_qwen_extract_candidates
        local_model_enabled = local_qwen_extractor_configured()
    except Exception:
        local_model_enabled = False

    if local_model_enabled:
        try:
            local_candidates, model_candidate_rejections = local_qwen_extract_candidates(extracted["pages"])
            if local_candidates:
                existing_keys = {
                    (str(item.get("field", "")).casefold(), str(item.get("value", "")).casefold(),
                     str(item.get("unit", "")).casefold(), int(item.get("source_page") or 0))
                    for item in candidate_values
                }
                for item in local_candidates:
                    key = (str(item.get("field", "")).casefold(), str(item.get("value", "")).casefold(),
                           str(item.get("unit", "")).casefold(), int(item.get("source_page") or 0))
                    if key not in existing_keys:
                        candidate_values.append(item)
                        existing_keys.add(key)
                structured_extraction_method = "local_qwen_lora_extractor"
            else:
                extraction_warnings.append("Local Qwen returned no evidence-validated fields; deterministic candidates were retained.")
        except Exception as exc:
            extraction_warnings.append(f"Local Qwen extractor unavailable; deterministic candidates retained ({str(exc)[:240]}).")
    elif use_cloud_ocr and settings.hf_token and escalated_page_numbers:
        try:
            from app.services.model_clients import hf_extract_candidates
            pages_for_model = [
                page for page in extracted["pages"]
                if int(page.get("page", 0)) in escalated_page_numbers
            ]
            model_candidates, model_candidate_rejections = hf_extract_candidates(pages_for_model)
            if model_candidates:
                existing_keys = {
                    (str(item.get("field", "")).casefold(), str(item.get("value", "")).casefold(),
                     str(item.get("unit", "")).casefold(), int(item.get("source_page") or 0))
                    for item in candidate_values
                }
                for item in model_candidates:
                    key = (str(item.get("field", "")).casefold(), str(item.get("value", "")).casefold(),
                           str(item.get("unit", "")).casefold(), int(item.get("source_page") or 0))
                    if key not in existing_keys:
                        candidate_values.append(item)
                        existing_keys.add(key)
                structured_extraction_method = "huggingface_qwen_extractor"
            else:
                extraction_warnings.append("Hugging Face returned no evidence-validated fields for escalated pages; deterministic candidates retained.")
        except Exception as exc:
            extraction_warnings.append(f"Hugging Face extractor unavailable; deterministic candidates retained ({str(exc)[:240]}).")
    elif use_cloud_ocr and not escalated_page_numbers and not escalation_needed:
        extraction_warnings.append("Hosted structured extraction was skipped because local OCR diagnostics did not require escalation; deterministic candidates were retained.")
    elif use_cloud_ocr and not escalated_page_numbers and escalation_needed:
        extraction_warnings.append("A low-quality page required hosted OCR, but no hosted transcript was available; local OCR and deterministic candidates were retained.")
    summary_method = "extractive"
    stored_summary = extractive_summary(extracted["text"], candidate_values)
    if use_openrouter_summary:
        # Prefer Hugging Face for summarization, then use OpenRouter as a fallback.
        # If hosted models are unavailable or OCR text is too short, keep the local summary.
        summary_errors = []
        if len((extracted["text"] or "").strip()) < 15:
            summary_errors.append("Too little readable OCR text for a hosted summary; a local extractive summary was saved.")
        elif settings.hf_token.strip():
            try:
                stored_summary = hf_summarize_record(
                    extracted["text"], title=title.strip() or filename,
                    record_type=record_type, filename=filename,
                )
                summary_method = "huggingface_ai"
            except RuntimeError as exc:
                summary_errors.append(f"Hugging Face summary unavailable: {str(exc)[:220]}")
        if summary_method == "extractive" and len((extracted["text"] or "").strip()) >= 15 and openrouter_configured():
            try:
                stored_summary = openrouter_summarize(
                    extracted["text"], title=title.strip() or filename,
                    record_type=record_type, filename=filename,
                )
                summary_method = "openrouter_ai"
            except RuntimeError as exc:
                summary_errors.append(f"OpenRouter summary unavailable: {str(exc)[:220]}")
        if summary_method == "extractive":
            if len((extracted["text"] or "").strip()) >= 15 and not settings.hf_token.strip() and not openrouter_configured():
                summary_errors.append("No hosted summary model configured; a local extractive summary was saved. Configure HF_TOKEN for Hugging Face AI.")
            extraction_warnings.extend(summary_errors)
    record = MedicalRecord(
        owner_user_id=user.id, title=title.strip() or filename,
        record_type=record_type, provider_name=provider_name, doctor_name=doctor_name,
        record_date=record_date, storage_key=str(storage_path), original_filename=filename,
        file_sha256=sha256_file(str(storage_path)), extracted_text=extracted["text"],
        extracted_data={
            "candidates": candidate_values,
            "extraction_method": extracted["extraction_method"],
            "page_count": extracted["page_count"],
            "ocr_quality": extracted.get("ocr_quality", []),
            "summary": stored_summary,
            "summary_method": summary_method,
            "structured_extraction_method": structured_extraction_method,
            "model_candidate_rejections": model_candidate_rejections,
            "extraction_warnings": extraction_warnings,
        }, verification_status="pending_review",
    )
    try:
        db.add(record)
        db.flush()
        db.add(AuditEvent(owner_user_id=user.id, record_id=record.id, action="record_uploaded", details={"filename": filename, "sha256": record.file_sha256}))
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        raise HTTPException(500, "Could not save the uploaded record.")
    return out(record)


@router.get("")
def listing(q: str | None = None, record_type: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(MedicalRecord).filter(MedicalRecord.owner_user_id == user.id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(MedicalRecord.title.ilike(term), MedicalRecord.original_filename.ilike(term), MedicalRecord.provider_name.ilike(term), MedicalRecord.extracted_text.ilike(term)))
    if record_type and record_type != "all":
        query = query.filter(MedicalRecord.record_type == record_type)
    return [out(r) for r in query.order_by(MedicalRecord.created_at.desc()).all()]


@router.get("/{record_id}")
def get_record(record_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        rid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(400, "Invalid record ID.")
    record = db.query(MedicalRecord).filter(MedicalRecord.id == rid, MedicalRecord.owner_user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found.")
    return out(record)


@router.delete("/{record_id}", status_code=204)
def delete(record_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        rid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(400, "Invalid record ID.")
    record = db.query(MedicalRecord).filter(MedicalRecord.id == rid, MedicalRecord.owner_user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found.")
    Path(record.storage_key).unlink(missing_ok=True)
    db.add(AuditEvent(owner_user_id=user.id, record_id=record.id, action="record_deleted", details={"filename": record.original_filename}))
    db.delete(record)
    db.commit()
    return None


@router.post("/{record_id}/verify-integrity")
def integrity(record_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        rid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(400, "Invalid record ID.")
    record = db.query(MedicalRecord).filter(MedicalRecord.id == rid, MedicalRecord.owner_user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found.")
    exists = Path(record.storage_key).is_file()
    current = sha256_file(record.storage_key) if exists else None
    return {"record_id": str(record.id), "file_exists": exists, "hash_matches": bool(current and current == record.file_sha256), "stored_sha256": record.file_sha256, "current_sha256": current}


class RecordUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    record_type: str | None = Field(default=None, max_length=40)
    provider_name: str | None = Field(default=None, max_length=200)
    doctor_name: str | None = Field(default=None, max_length=200)
    record_date: date | None = None


@router.patch("/{record_id}")
def update_record(record_id: str, p: RecordUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        rid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(400, "Invalid record ID.")
    record = db.query(MedicalRecord).filter(MedicalRecord.id == rid, MedicalRecord.owner_user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found.")
    changes = p.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
        if not changes["title"]:
            raise HTTPException(422, "Title cannot be blank.")
    for key, value in changes.items():
        setattr(record, key, value)
    db.add(AuditEvent(owner_user_id=user.id, record_id=record.id, action="record_metadata_updated", details={"fields": sorted(changes.keys())}))
    db.commit()
    db.refresh(record)
    return out(record)


@router.get("/download/{record_id}")
def download_record(record_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        rid = uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(400, "Invalid record ID.")
    record = db.query(MedicalRecord).filter(MedicalRecord.id == rid, MedicalRecord.owner_user_id == user.id).first()
    if not record:
        raise HTTPException(404, "Record not found.")
    storage_path = Path(record.storage_key)
    if not storage_path.is_file():
        raise HTTPException(404, "The stored original file could not be found.")
    media_types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff"}
    return FileResponse(storage_path, media_type=media_types.get(storage_path.suffix.lower(), "application/octet-stream"), filename=record.original_filename)
