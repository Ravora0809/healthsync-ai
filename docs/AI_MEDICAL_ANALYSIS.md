# HEALTHSYNC-AI medical-document analysis

## User workflow

1. Upload a supported PDF or image. Local PDF text extraction / Tesseract OCR runs first.
2. In Medical records, click **Analyze**.
3. The consent prompt explains that structured extraction sends extracted OCR text and record metadata to OpenRouter. If stored OCR diagnostics say a scanned page was low quality, the backend may also retry hosted vision OCR (Hugging Face first if configured, then OpenRouter if available). Cancel performs local evidence review only.
4. The backend calls the configured OpenRouter summary model for structured JSON extraction, validates source excerpts against the stored OCR transcription, saves the result under `MedicalRecord.extracted_data.clinical_analysis`, and returns it with the Evidence Engine report.
5. The UI presents medicine fields, lab results, care instructions explicitly present in the transcription, missing topics, ambiguous items, and a separately labelled general-education section.
6. The AI Health Assistant retrieves saved analysis and source excerpts from matching uploaded medical records. It uses Hugging Face first for generated answers, then OpenRouter if configured; otherwise it falls back to source snippets.

## Details displayed

For each medicine: name as written, strength, dose, route, frequency, duration, instructions, storage text, indication written in the document, a separate general common-use description, and source excerpt. Every medicine remains marked for human confirmation. The system does not infer the doctor's reason for prescribing a drug.

For document care instructions, the interface has separate sections for food/diet, exercise, precautions, temperature guidance, medicine storage and hospital follow-up. Only an item with a source excerpt that matches the OCR text is displayed as a documented instruction. Items not found are labelled **Not specified in this document**. Do not infer a numeric temperature threshold, medicine storage temperature or hospital schedule from missing information.

General education is deliberately separate from document instructions. It is model-generated context, not personalized medical advice and not a substitute for the package label, pharmacist or treating clinician.

## Provider settings

The project root `.env` must contain `OPENROUTER_API_KEY`. The extraction currently uses `OPENROUTER_SUMMARY_MODEL_ID` (or `OPENROUTER_CHAT_MODEL_ID` when appropriate). Keep the key in the backend environment only.

The analyze endpoint is `POST /api/v1/evidence/analyze/{record_id}?use_openrouter=true` after the user confirms the separate analysis prompt. This Analyze action uses Hugging Face structured analysis first; OpenRouter is the fallback if configured.

## Limitations and safety

- OCR confidence is not a calibrated probability of correctness.
- Literal excerpt matching can reject real content if OCR is distorted; rejected or blank fields must remain reviewable rather than silently guessed.
- A source match proves only that the words appear in the OCR transcript, not that the medicine was correctly read from the image or is clinically appropriate.
- Model-reported typical uses are general references and do not establish the reason for the individual prescription.
- Food/exercise general education is not individualized. If the record has no instructions for body temperature, medicine storage or follow-up intervals, the product directs the user to the source label/clinician rather than inventing values.
- User-facing extraction is always a draft for human verification, not diagnosis or treatment advice.
