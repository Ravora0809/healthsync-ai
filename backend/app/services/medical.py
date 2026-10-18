"""OCR and source-grounded candidate extraction for HEALTHSYNC-AI.

OCR and extraction are heuristic. They preserve page and excerpt provenance and
must never be treated as a diagnosis or a substitute for human review.
"""
import base64
import difflib
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import fitz
from app.core.config import settings


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ocr_image_with_quality(image):
    """Run local Tesseract OCR and return text plus word-confidence diagnostics.

    Tesseract confidence is a routing signal, not a calibrated probability of correctness.
    """
    import pytesseract
    from pytesseract import Output
    from PIL import ImageOps, ImageFilter

    image = ImageOps.exif_transpose(image.convert("RGB"))
    if max(image.size) < 1800:
        scale = min(2.0, 1800 / max(image.size))
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    gray = ImageOps.autocontrast(ImageOps.grayscale(image)).filter(ImageFilter.MedianFilter(size=3))
    tessdata_dir = settings.tessdata_dir or os.getenv("TESSDATA_DIR")
    config = '--oem 3 --psm 6'
    if tessdata_dir:
        config += f' --tessdata-dir "{tessdata_dir}"'

    text = pytesseract.image_to_string(gray, lang="eng", config=config).strip()
    data = pytesseract.image_to_data(gray, lang="eng", config=config, output_type=Output.DICT)
    if len(text) < 15:
        config_sparse = '--oem 3 --psm 11'
        if tessdata_dir:
            config_sparse += f' --tessdata-dir "{tessdata_dir}"'
        alt = pytesseract.image_to_string(gray, lang="eng", config=config_sparse).strip()
        if len(alt) > len(text):
            text = alt
            data = pytesseract.image_to_data(gray, lang="eng", config=config_sparse, output_type=Output.DICT)

    confidences = []
    recognized_words = []
    for token, raw_conf in zip(data.get("text", []), data.get("conf", [])):
        token = str(token or "").strip()
        if not token:
            continue
        recognized_words.append(token)
        try:
            confidence = float(raw_conf)
        except (TypeError, ValueError):
            continue
        if confidence >= 0:
            confidences.append(confidence)

    mean_confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
    low_ratio = round(sum(value < 50 for value in confidences) / len(confidences), 3) if confidences else None
    quality = {
        "local_mean_word_confidence": mean_confidence,
        "local_low_confidence_word_ratio": low_ratio,
        "local_word_count": len(recognized_words),
        "local_text_characters": len(text),
        "confidence_is_calibrated_probability": False,
    }
    return text, quality


def _ocr_image(image):
    """Backward-compatible text-only wrapper for local OCR."""
    return _ocr_image_with_quality(image)[0]


def _should_escalate_ocr(text: str, quality: dict) -> tuple[bool, str]:
    """Decide whether low-quality local OCR warrants optional hosted OCR."""
    if not (text or "").strip() or len((text or "").strip()) < 15:
        return True, "local OCR returned little or no readable text"
    try:
        threshold = float(os.getenv("OCR_ESCALATION_MIN_CONFIDENCE", "65"))
    except (TypeError, ValueError):
        threshold = 65.0
    threshold = max(0.0, min(100.0, threshold))
    mean_confidence = quality.get("local_mean_word_confidence")
    low_ratio = quality.get("local_low_confidence_word_ratio")
    if mean_confidence is None:
        return True, "local OCR confidence could not be estimated"
    if mean_confidence < threshold:
        return True, f"local mean word confidence {mean_confidence:.1f} is below threshold {threshold:.1f}"
    if low_ratio is not None and low_ratio >= 0.35:
        return True, f"{low_ratio:.0%} of recognized words have low Tesseract confidence"
    return False, "local OCR quality passed the routing threshold"


def _ocr_disagreement_summary(local_text: str, hosted_text: str, max_segments: int = 5) -> dict:
    """Summarize word-level differences without claiming either transcript is correct."""
    local_tokens = re.findall(r"\w+|[^\w\s]", (local_text or "").lower(), flags=re.UNICODE)
    hosted_tokens = re.findall(r"\w+|[^\w\s]", (hosted_text or "").lower(), flags=re.UNICODE)
    if not local_tokens and not hosted_tokens:
        return {"disagreement_ratio": 0.0, "disagreement_segments": []}
    matcher = difflib.SequenceMatcher(a=local_tokens, b=hosted_tokens, autojunk=False)
    ratio = round(1.0 - matcher.ratio(), 4)
    segments = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        segments.append({
            "local": " ".join(local_tokens[i1:i2])[:180],
            "hosted": " ".join(hosted_tokens[j1:j2])[:180],
            "difference_type": tag,
        })
        if len(segments) >= max_segments:
            break
    return {"disagreement_ratio": ratio, "disagreement_segments": segments}


def _local_then_optional_hosted_ocr(image, *, use_cloud_ocr: bool, page_number: int, source_type: str) -> tuple[str, str, dict]:
    """Run local OCR first; escalate to hosted vision only when enabled and local quality is low."""
    local_text, quality = _ocr_image_with_quality(image)
    should_escalate, reason = _should_escalate_ocr(local_text, quality)
    diagnostic = {
        "page": page_number,
        "source_type": source_type,
        **quality,
        "cloud_escalation_consented": bool(use_cloud_ocr),
        "cloud_escalation_needed": bool(should_escalate),
        "cloud_escalated": False,
        "cloud_escalation_reason": reason if use_cloud_ocr and should_escalate else (
            "hosted OCR is disabled for this request" if not use_cloud_ocr else reason
        ),
        "disagreement_ratio": None,
        "disagreement_segments": [],
        "review_recommended": bool(should_escalate),
        "diagnostic_note": "Tesseract confidence is a routing heuristic, not a calibrated probability. Verify transcription against the original.",
    }
    if not use_cloud_ocr or not should_escalate:
        return local_text, ("tesseract_ocr" if local_text else "no_text"), diagnostic

    try:
        hosted_text, hosted_method = _selected_ocr(image, use_cloud_ocr=True, filename=f"page-{page_number}")
        hosted_text = (hosted_text or "").strip()
        diagnostic["cloud_escalated"] = True
        diagnostic["cloud_method"] = hosted_method
        if hosted_text:
            diagnostic.update(_ocr_disagreement_summary(local_text, hosted_text))
            diagnostic["review_recommended"] = True
            diagnostic["cloud_escalation_reason"] = reason
            # Preserve the hosted reading as a candidate, while retaining bounded disagreement
            # spans to let the reviewer compare what the local engine saw.
            return hosted_text, hosted_method, diagnostic
        diagnostic["cloud_error"] = "Hosted OCR returned empty text; local OCR retained."
        return local_text, ("tesseract_ocr" if local_text else "no_text"), diagnostic
    except Exception as exc:
        # Optional hosted OCR must not make a record upload fail. Keep local output and disclose fallback.
        diagnostic["cloud_error"] = str(exc)[:240]
        diagnostic["cloud_fallback_used"] = True
        diagnostic["review_recommended"] = True
        return local_text, ("tesseract_ocr" if local_text else "no_text"), diagnostic


def _hf_vision_transcribe(image) -> str:
    """Call Hugging Face vision OCR only. Provider fallback is handled by _selected_ocr."""
    if not settings.hf_token:
        raise RuntimeError("HF_TOKEN is not configured.")
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    body = {
        "model": settings.hf_vision_model_id,
        "temperature": 0.0,
        "max_tokens": 1800,
        "messages": [
            {"role": "system", "content": "You transcribe medical documents faithfully. Do not diagnose or infer values. Preserve uncertain words as [unclear], retain labels, numbers, units, dates and handwriting as literally as possible. Output transcription only."},
            {"role": "user", "content": [
                {"type": "text", "text": "Transcribe all readable text in this medical report, lab report, prescription, or vaccination card. Do not invent missing values. Mark uncertain handwriting as [unclear]."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
            ]},
        ],
    }
    req = urllib.request.Request(
        settings.hf_chat_endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.hf_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Hugging Face vision OCR failed ({exc.code}): {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Hugging Face vision OCR failed: {exc}") from exc



def _selected_ocr(image, *, use_cloud_ocr: bool, filename: str) -> tuple[str, str]:
    """Default to bundled Tesseract; use hosted vision only when enabled by the caller.

    The upload endpoint enables hosted escalation by default but only on low-quality pages.
    The previous local PaddleOCR worker path is intentionally not called here. This avoids
    failing an upload because a separately launched worker or its auth token is missing.
    """
    if use_cloud_ocr:
        from app.services.ai import openrouter_configured, openrouter_vision_transcribe

        hf_error = None
        if settings.hf_token:
            try:
                text = _hf_vision_transcribe(image)
                if text:
                    return text, "huggingface_vision_ocr"
                hf_error = "Hugging Face returned empty text."
            except Exception as exc:
                hf_error = str(exc)

        # If HF has no credits or is otherwise unavailable, retry using OpenRouter
        # when a server-side key is configured. No API key is exposed to the frontend.
        if openrouter_configured():
            try:
                text = openrouter_vision_transcribe(image)
                if text:
                    return text, "openrouter_vision_ocr"
                raise RuntimeError("OpenRouter vision OCR returned empty text.")
            except Exception as exc:
                if hf_error:
                    raise RuntimeError(
                        f"Hugging Face vision OCR failed ({hf_error}); OpenRouter fallback also failed ({exc})."
                    ) from exc
                raise

        if hf_error:
            raise RuntimeError(
                f"Hugging Face vision OCR failed ({hf_error}). Configure OPENROUTER_API_KEY for hosted fallback, "
                "or disable hosted OCR to use local Tesseract only."
            )
        raise RuntimeError(
            "Hosted vision OCR is not configured. Set HF_TOKEN or OPENROUTER_API_KEY in the root .env, "
            "then restart Docker Compose."
        )
    return _ocr_image(image), "tesseract_ocr"


def extract_document(path: str, use_cloud_ocr: bool = False) -> dict:
    """Extract page by page using local OCR first and enabled quality-based hosted escalation.

    Searchable PDF text is preferred. Hosted vision OCR is attempted only when the user opted
    in and local OCR diagnostics indicate a low-quality transcription. Hosted failure falls back
    to local output and is reported in `ocr_quality` rather than aborting the upload.
    """
    from PIL import Image, ImageOps
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    pages: list[dict] = []
    ocr_quality: list[dict] = []

    if suffix == ".pdf":
        with fitz.open(path) as pdf:
            if not 1 <= pdf.page_count <= 20:
                raise RuntimeError("PDF must contain between 1 and 20 pages for this prototype.")
            for index, page in enumerate(pdf, start=1):
                page_text = page.get_text("text").strip()
                if len(page_text) >= 20:
                    method = "pdf_text"
                    diagnostic = {
                        "page": index,
                        "source_type": "searchable_pdf_text_layer",
                        "local_mean_word_confidence": None,
                        "local_low_confidence_word_ratio": None,
                        "local_word_count": len(page_text.split()),
                        "local_text_characters": len(page_text),
                        "confidence_is_calibrated_probability": False,
                        "cloud_escalation_consented": bool(use_cloud_ocr),
                        "cloud_escalated": False,
                        "cloud_escalation_reason": "searchable PDF text layer used; OCR skipped",
                        "disagreement_ratio": None,
                        "disagreement_segments": [],
                        "review_recommended": False,
                        "diagnostic_note": "Text-layer extraction does not verify semantic correctness; review important fields against the document.",
                    }
                else:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes("png")))
                    try:
                        page_text, method, diagnostic = _local_then_optional_hosted_ocr(
                            image, use_cloud_ocr=use_cloud_ocr, page_number=index, source_type="scanned_pdf_page"
                        )
                    finally:
                        image.close()
                pages.append({"page": index, "text": page_text[:30000], "method": method})
                ocr_quality.append(diagnostic)
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                if image.width * image.height > 25_000_000:
                    raise RuntimeError("Image dimensions exceed the 25-megapixel processing limit.")
                page_text, method, diagnostic = _local_then_optional_hosted_ocr(
                    image, use_cloud_ocr=use_cloud_ocr, page_number=1, source_type="image"
                )
            pages.append({"page": 1, "text": page_text[:30000], "method": method})
            ocr_quality.append(diagnostic)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("Image OCR failed. Check the bundled Tesseract model and file format.") from exc
    else:
        raise ValueError("Unsupported document type. Upload PDF, PNG, JPG, JPEG, WEBP, or TIFF.")

    text = "\n\n".join(p["text"] for p in pages if p["text"]).strip()[:100000]
    methods = sorted({p["method"] for p in pages})
    overall_method = methods[0] if len(methods) == 1 else ("mixed" if methods else "no_text")
    return {
        "text": text,
        "pages": pages,
        "page_count": len(pages),
        "extraction_method": overall_method,
        "ocr_quality": ocr_quality,
    }


# Conservative patterns: field/value evidence only. No diagnosis or clinical classification.
_PATTERNS = [
    ("hemoglobin", r"(?i)\b(?:haemoglobin|hemoglobin|hb)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(g/dl|g/l)?"),
    ("glucose", r"(?i)\b(?:blood glucose|fasting glucose|fasting sugar|glucose)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(mg/dl|mmol/l)?"),
    ("hba1c", r"(?i)\b(?:hba1c|glycated haemoglobin|glycated hemoglobin)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(%)?"),
    ("cholesterol", r"(?i)\b(?:total cholesterol|cholesterol)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(mg/dl|mmol/l)?"),
    ("creatinine", r"(?i)\bcreatinine\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(mg/dl|umol/l|µmol/l)?"),
    ("vitamin_d", r"(?i)\bvitamin\s*d(?:\s*25-?oh)?\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(ng/ml|nmol/l)?"),
    ("tsh", r"(?i)\b(?:tsh|thyroid stimulating hormone)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(miu/l|uiu/ml)?"),
    ("platelets", r"(?i)\bplatelets?\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:10\^?3/?ul|x10\^?3/?ul|thousand/µl)?"),
    ("wbc", r"(?i)\b(?:wbc|white blood cells?)\b\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:10\^?3/?ul|x10\^?3/?ul)?"),
]


def extract_candidates(pages: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for page in pages:
        for line_number, line in enumerate((page.get("text") or "").splitlines(), start=1):
            clean_line = " ".join(line.split())
            if not clean_line:
                continue
            for field, pattern in _PATTERNS:
                for match in re.finditer(pattern, clean_line):
                    value = match.group(1)
                    unit = (match.group(2) or "").strip()
                    # Avoid identical duplicate matches for the same field/line.
                    if any(c["field"] == field and c["source_page"] == page["page"] and c["source_excerpt"] == clean_line for c in candidates):
                        continue
                    candidates.append({
                        "evidence_id": f"p{page['page']}-l{line_number}-{field}-{len(candidates)+1}",
                        "field": field,
                        "value": value,
                        "unit": unit,
                        "source_page": page["page"],
                        "source_line": line_number,
                        "source_excerpt": clean_line[:500],
                        # Heuristic traceability indicator, not a calibrated probability.
                        "confidence": 0.68 if page.get("method") == "pdf_text" else 0.52,
                        "extraction_method": page.get("method", "unknown"),
                        "status": "requires_human_review",
                    })
    return candidates


def extract_text(path: str) -> str:
    """Backward-compatible convenience wrapper."""
    return extract_document(path)["text"]


def candidates(text: str) -> list[dict]:
    """Compatibility wrapper for text-only candidate extraction."""
    return extract_candidates([{"page": 1, "text": text, "method": "pdf_text"}])


def extractive_summary(text: str, candidates: list[dict] | None = None, max_lines: int = 8) -> str:
    """Create a conservative, stored extractive summary without inventing clinical meaning."""
    lines = [" ".join(line.split()).strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if len(line) >= 4]
    if not lines:
        return "No readable text was extracted. Open the original file and review it manually."
    terms = re.compile(r"(?i)(patient|name|date|report|result|impression|diagnosis|prescription|medicine|medication|dose|vaccine|vaccination|allergy|hemoglobin|glucose|hba1c|cholesterol|creatinine|platelets|wbc|tsh|vitamin|mg/dl|mmol/l|mg|mcg|ml)\b")
    preferred = [line for line in lines if terms.search(line)]
    selected = []
    for line in (preferred + lines):
        if line not in selected:
            selected.append(line)
        if len(selected) >= max_lines:
            break
    summary = "\n".join(f"• {line[:280]}" for line in selected)
    if candidates:
        summary += "\n\nValues detected for review: " + "; ".join(
            f"{c.get('field')}: {c.get('value')} {c.get('unit') or ''} (page {c.get('source_page')})" for c in candidates[:12]
        )
    summary += "\n\nExtractive summary only: compare every value, unit and date with the original document. This is not a diagnosis."
    return summary[:5000]
