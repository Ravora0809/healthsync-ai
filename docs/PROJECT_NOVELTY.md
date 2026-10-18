# HEALTHSYNC-AI: project contribution and capstone framing

## Problem addressed
Personal medical records may be scattered across lab PDFs, prescriptions, scanned report images, and vaccination documents. HEALTHSYNC-AI gives one account a private place to collect these files and inspect extracted evidence with source context.

## Core contribution: source-grounded Evidence Engine
Rather than presenting a model-generated summary as an unsupported fact, the prototype stores each extracted candidate with a traceable source anchor:

- uploaded file SHA-256 digest;
- extraction method (`pdf_text` or `tesseract_ocr`);
- page and line position when available;
- exact source-line excerpt;
- candidate field, value, and unit;
- heuristic confidence indicator and explicit human-review status.

The Evidence Engine flags multiple values for the same field in one document, shows repeated fields across a patient's own records, and checks whether the uploaded file still matches its stored hash. It makes the extraction trail inspectable, which is the central explainability/provenance feature of this prototype.

## Architecture
1. React/Vite frontend gathers signup, verification, record, vaccine, and reminder actions.
2. FastAPI validates requests and enforces owner-scoped access with JWT bearer authentication.
3. PostgreSQL stores account metadata, pending signup state, records, audit events, vaccinations, and reminders.
4. Original uploads are stored in a persistent volume, keyed by generated filenames rather than user-supplied paths.
5. PyMuPDF reads searchable PDFs. The bundled Tesseract English model handles scanned PDFs and images.
6. Regex-based field candidate extraction keeps values attached to page/line/excerpt provenance.
7. The Evidence Engine reports review flags and source-to-source comparisons; it does not diagnose.

## What is and is not novel about this prototype
This bundle implements a practical integration of private document organization, hash-based integrity checking, OCR-assisted extraction, and field-level source provenance. It should not be described as blockchain, immutable storage, cryptographic signatures, clinical validation, or an empirically validated diagnostic AI. SHA-256 detects a mismatch only if the stored digest is trusted and protected. The confidence numbers are heuristic, not statistically calibrated.

## Suggested capstone evaluation
- OCR text quality: compare OCR against manually transcribed ground truth using character/word error rate.
- Candidate extraction: precision, recall, and F1 for supported fields against annotated documents.
- Provenance quality: percentage of candidates with a correct source page and matching excerpt.
- Integrity detection: verify unchanged files pass and deliberately altered files fail hash comparison.
- Workflow completion: signup/OTP/login, upload, evidence review, search, vaccination entry, reminder completion.
- Usability: task completion time and participant feedback, using synthetic or appropriately consented de-identified records.

## Safety boundaries
Use synthetic or appropriately de-identified data for testing. OCR mistakes are possible. Candidate values must be reviewed against original reports by a person. Do not use the application to make medical decisions.


## Extended prototype contribution: reviewable record-to-action pipeline

The expanded build connects four steps that are often demonstrated separately: **capture → extraction → provenance-aware review → patient-confirmed action**. A medical/vaccination image is stored as an original artifact; OCR text and an extractive summary are saved with the record; candidate values can be traced back to source excerpts; and a vaccine due date becomes a reminder only after a person confirms or enters it. Deletion/editing is supported so users can correct the structured record rather than treating model output as immutable truth.

A second distinction is adaptive routing: local Tesseract runs first and low-quality pages can be escalated to hosted vision OCR; Hugging Face chat and summaries are enabled by default in this build and may transmit selected medical content to a provider. This is a product/architecture contribution rather than a claim that the underlying OCR or language models are novel. The system is designed to abstain when it lacks evidence, expose the supporting records, and keep a human in control of extracted fields and dates.

## Recommended evaluation

Build a de-identified or synthetic evaluation set with paired source images and corrected text, multiple document types (typed lab reports, prescriptions, low-light phone images, and handwriting), and ground-truth extracted fields. Report character/word error rate for transcription, precision/recall/F1 for supported fields, date accuracy, citation/source-span correctness, unsupported-claim rate, and how often users correct OCR suggestions. Separate results by typed vs handwritten documents; do not present overall average OCR accuracy as proof that handwritten prescriptions are reliable.


## Hugging Face-first, prescription-focused assistant update

The prototype separates three external-AI actions: vision transcription for difficult handwriting (image input), AI-written summaries (OCR text input), and record-grounded assistant answers (retrieved record excerpts plus the question). Hugging Face is primary and OpenRouter is a fallback; these actions are enabled by default in this build and provider credentials remain backend-only. The assistant adds a server-side topic scope check and refuses direct requests for new diagnoses, medication recommendations, or dose changes. This improves application scope and data-flow clarity, but is not model fine-tuning and does not prove clinical accuracy.

## Novelty assessment

The broad concept of AI-assisted personal health records, OCR, reminders, summarization, and secure sharing is not by itself a strong research novelty claim; comparable systems and papers exist. A more defensible project contribution is an evaluated **Provenance-Aware Prescription-to-Action workflow**: preserve the uploaded source and hash, store a transcription with uncertain spans marked, extract candidate medicine fields with page/line/excerpt provenance, make a human verify/correct them, and only then enable patient-managed reminders or structured history. Novelty should be demonstrated with measurable results—handwriting versus printed word-error rate, medication-name/strength/date field F1, provenance correctness, unsupported-summary claims, human correction rate, and reminder-task completion—against a Tesseract-only baseline. Until those experiments are run, describe this as a system-design contribution or prototype contribution, not a proven novel AI model.


## Implemented novelty module: quality-gated adaptive OCR escalation

The current code revision adds an **adaptive local-first OCR path** to make uncertainty visible and reduce unnecessary external processing:

1. Searchable PDF text is used directly where a usable text layer exists.
2. For image pages and scanned PDF pages, local Tesseract runs first and emits word-confidence diagnostics.
3. Hosted vision OCR is attempted only when the user has explicitly opted in and the local OCR text is short, its mean word confidence falls below `OCR_ESCALATION_MIN_CONFIDENCE` (default `65`), or the share of low-confidence words is at least 35%.
4. When both readings are available, the system stores a bounded word-level disagreement summary (not a declaration that either model is correct), the escalation reason, local confidence diagnostics, and fallback errors. Hosted structured extraction is also restricted to pages that were successfully escalated, and its candidates are merged with deterministic candidates rather than replacing them. The evidence report emits review flags for low-quality pages and OCR disagreement.
5. If hosted OCR is unavailable, the upload retains the local transcript and records a fallback warning instead of failing solely because the optional hosted provider is unavailable.

Set `OCR_ESCALATION_MIN_CONFIDENCE` in the backend environment to tune the routing threshold. Tesseract confidence is used only as a routing heuristic; it is **not** a calibrated probability of correctness. All extracted candidates remain subject to human review.

### How to demonstrate this contribution

On the same held-out document set, compare (A) local Tesseract only, (B) hosted vision OCR on every eligible page when enabled, and (C) the adaptive local-first strategy. Report CER/WER for transcription; field precision/recall/F1; page-level escalation rate; number of hosted calls; local-vs-hosted disagreement rate; and the percentage of disagreement flags that reviewers judge genuinely ambiguous. Stratify by searchable PDF, printed scan, phone photo, and handwriting. Use patient/document-separated splits and synthetic or authorized de-identified documents. Report measured outcomes only; this is an implemented system-design contribution, not a claim of proven clinical accuracy or a novel base model.


## Local fine-tuned model integration (current code revision)

A trained Qwen3 LoRA/QLoRA adapter can now be loaded by `backend/app/services/local_model_client.py`. If `LOCAL_QWEN_ADAPTER_DIR` points to an adapter containing `adapter_config.json`, uploads run the local adapter on OCR text for evidence-linked structured candidate extraction before considering hosted structured extraction. Candidate values are still passed through the source-excerpt validator; the adapter does not diagnose and it is not automatically accurate merely because it is fine-tuned. The adapter weights are not included in this repository. Set `INSTALL_LOCAL_MODEL=true` when building Docker to install optional local-inference dependencies, and mount the trained adapter directory as described in `ml_training/README.md`.

The app can still fall back to local Tesseract OCR, deterministic candidates, extractive summaries, file hashing, evidence reports, and local record retrieval when hosted providers are unavailable. Hugging Face is the primary hosted model by default and OpenRouter is fallback; hosted processing can transmit record content and is visibly disclosed in the app. To substantiate a model contribution, benchmark the actual trained adapter against the regex baseline and hosted base model using held-out, document-separated data, source-span accuracy, field precision/recall/F1, JSON validity, rejection rate, latency, and memory use.
