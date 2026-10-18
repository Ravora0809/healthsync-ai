# API quick reference

The backend is exposed on `http://localhost:8000`; all application routes use `/api`.

## Authentication
- `POST /api/auth/signup` — `{ "full_name", "email", "password", "confirm_password" }`; creates pending signup only and sends/logs an OTP.
- `POST /api/auth/verify-otp` — `{ "email", "otp" }`; creates the actual account only after valid, unexpired OTP.
- `POST /api/auth/resend-otp` — `{ "email" }`; resend cooldown enforced.
- `POST /api/auth/login` — `{ "email", "password" }`; returns JWT.
- `GET /api/auth/me` — bearer token required.
- `POST /api/auth/change-password` — bearer token required; body: `current_password`, `new_password`, `confirm_password`.

## Medical records (bearer token required)
- `GET /api/medical-records?q=glucose&record_type=lab_report` — list/search the current user's records.
- `POST /api/medical-records` — multipart form with `file`, `title`, optional `record_type`, `provider_name`, `doctor_name`, `record_date`, and `use_cloud_ocr` (default true; hosted escalation only for low-quality pages). Supported files: PDF, PNG, JPG/JPEG, WEBP, TIFF.
- `GET /api/medical-records/{record_id}` — details.
- `PATCH /api/medical-records/{record_id}` — update title/category/provider/doctor/date.
- `GET /api/medical-records/download/{record_id}` — download original file.
- `DELETE /api/medical-records/{record_id}` — delete an owned record and stored file.
- `POST /api/medical-records/{record_id}/verify-integrity` — recompute SHA-256.

## Evidence Engine (bearer token required)
- `POST /api/evidence/analyze/{record_id}` — candidates, provenance, flags, cross-record matches, integrity result.
- `GET /api/evidence/timeline/{field_name}` — extracted candidate values with source anchors across the current user's records.

Supported field labels currently include hemoglobin, glucose, HbA1c, total cholesterol, creatinine, vitamin D, TSH, platelets, and WBC. Candidate extraction is regex-based and limited; absence of a candidate does not mean a result is absent from the document.

## Other routes
- `GET/POST /api/vaccinations`; `PATCH/DELETE /api/vaccinations/{vaccination_id}`
- `POST /api/vaccinations/scan` — store uploaded vaccination card as a medical record and return editable suggestions. Confirm them before creating the vaccination entry.
- `GET/POST /api/reminders`; `PATCH /api/reminders/{reminder_id}/complete`; `DELETE /api/reminders/{reminder_id}`
- `GET /api/assistant/config` — reports whether optional Hugging Face is configured (never returns the secret token).
- `POST /api/assistant/chat` — Hugging Face-first answer generation by default when HF_TOKEN is configured; OpenRouter is fallback. Only relevant retrieved medical-record excerpts are sent to the configured hosted model.

- `GET /api/health`
- `GET /api/health/db`

Open `http://localhost:8000/docs` for interactive Swagger documentation.
