"""Source-grounded Evidence Engine helpers."""
from collections import defaultdict


def build_evidence_report(record, other_records: list) -> dict:
    data = record.extracted_data or {}
    candidates = data.get("candidates", [])
    ocr_quality = data.get("ocr_quality", [])
    flags = []
    if not (record.extracted_text or "").strip():
        flags.append({"type": "no_text_extracted", "severity": "review", "message": "No text was extracted; inspect the original document."})
    if not candidates:
        flags.append({"type": "no_candidate_values", "severity": "info", "message": "No values matched the supported extraction patterns."})
    else:
        terminal = {"user_verified", "corrected_and_user_verified", "rejected_as_incorrect"}
        pending_candidates = [item for item in candidates if item.get("verification_status") not in terminal]
        if pending_candidates:
            flags.append({"type": "candidate_values_detected", "severity": "review", "message": f"{len(pending_candidates)} candidate value(s) still need source review."})
        else:
            flags.append({"type": "candidate_values_reviewed", "severity": "info", "message": "All extracted candidate values have a user review status. This is not clinician approval."})

    # Adaptive OCR diagnostics are review cues, not probabilities of correctness.
    for diagnostic in ocr_quality:
        page = diagnostic.get("page")
        if diagnostic.get("review_recommended"):
            flags.append({
                "type": "ocr_quality_review",
                "severity": "review",
                "source_page": page,
                "message": f"OCR quality checks recommend reviewing page {page} against the original document.",
                "reason": diagnostic.get("cloud_escalation_reason"),
                "mean_word_confidence": diagnostic.get("local_mean_word_confidence"),
                "low_confidence_word_ratio": diagnostic.get("local_low_confidence_word_ratio"),
            })
        disagreement = diagnostic.get("disagreement_ratio")
        if disagreement is not None and disagreement > 0.05:
            flags.append({
                "type": "ocr_engine_disagreement",
                "severity": "review",
                "source_page": page,
                "disagreement_ratio": disagreement,
                "disagreement_segments": diagnostic.get("disagreement_segments", []),
                "message": f"Local and hosted OCR readings differ on page {page}; compare the alternate readings with the original.",
            })
        if diagnostic.get("cloud_error"):
            flags.append({
                "type": "optional_ocr_fallback",
                "severity": "review",
                "source_page": page,
                "message": f"Hosted OCR was unavailable on page {page}; local OCR output was retained.",
            })

    # Highlight multiple values for the same field within a single document without deciding which is correct.
    grouped = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.get("field", "unknown")].append(candidate)
    for field, items in grouped.items():
        distinct = {(str(item.get("value")), str(item.get("unit", "")).lower()) for item in items}
        if len(distinct) > 1:
            flags.append({
                "type": "multiple_values_same_field",
                "severity": "review",
                "field": field,
                "message": f"Multiple values or units for {field} appear in this document; verify each against its source page.",
                "evidence_ids": [item.get("evidence_id") for item in items],
            })

    # Cross-record comparison is descriptive, not an interpretation of normal/abnormal health.
    latest_by_field = defaultdict(list)
    for other in other_records:
        for item in (other.extracted_data or {}).get("candidates", []):
            if item.get("verification_status") == "rejected_as_incorrect":
                continue
            if other.id != record.id:
                latest_by_field[item.get("field")].append({
                    "record_id": str(other.id),
                    "record_title": other.title,
                    "record_date": other.record_date.isoformat() if other.record_date else (other.created_at.isoformat() if other.created_at else None),
                    "value": item.get("value"),
                    "unit": item.get("unit", ""),
                    "source_page": item.get("source_page"),
                    "source_excerpt": item.get("source_excerpt"),
                })
    comparisons = []
    for current in candidates:
        history = latest_by_field.get(current.get("field"), [])
        if history:
            comparisons.append({
                "field": current.get("field"),
                "current": {"value": current.get("value"), "unit": current.get("unit", ""), "source_page": current.get("source_page"), "source_excerpt": current.get("source_excerpt")},
                "historical_matches": history[:10],
                "note": "Values are shown for record-to-record comparison only; unit compatibility and clinical significance require human review.",
            })

    return {
        "record_id": str(record.id),
        "record_title": record.title,
        "verification_status": getattr(record, "verification_status", "pending_review"),
        "file_sha256": record.file_sha256,
        "extraction_method": data.get("extraction_method", "unknown"),
        "page_count": data.get("page_count", 0),
        "ocr_quality": ocr_quality,
        "candidate_values": candidates,
        "clinical_analysis": data.get("clinical_analysis"),
        "flags": flags,
        "cross_record_comparisons": comparisons,
        "evidence_traceability": "Each candidate includes its source page, line, excerpt, and extraction method when available.",
        "adaptive_ocr_method": "Local-first OCR with hosted escalation enabled for low-quality pages; reported confidence is a routing heuristic, not calibrated probability.",
        "disclaimer": "Informational document extraction only. Not a diagnosis or treatment recommendation. Confirm values against the original document and consult a qualified clinician for clinical interpretation.",
    }
