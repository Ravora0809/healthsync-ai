# HEALTHSYNC-AI — Complete Full-Stack Capstone Project

**One-command startup:** `docker compose up --build`

This archive includes a dedicated animated public landing page, React/Vite authentication and dashboard, FastAPI backend, PostgreSQL configuration, source files, tests, OCR code, and the English Tesseract `eng.traineddata` OCR model. It does **not** require a `.sh` script or a local Python/Node installation to run the application; Docker Desktop is the only runtime prerequisite.

## Run it in a fresh environment

1. Install and start Docker Desktop.
2. Extract this ZIP and open a terminal in the `healthsync-ai-fresh` folder (the folder containing `docker-compose.yml`).
3. Run:

   ```bash
   docker compose up --build
   ```

4. Wait until the logs report that PostgreSQL is ready and the backend/frontend services have started.
5. Open the app: **http://localhost:5173**
6. The public landing page appears first; choose **Get started** to sign up or **Sign in** for an existing account.
7. Open backend API docs: **http://localhost:8000/docs**

The command builds the backend and frontend images, starts PostgreSQL, waits for health checks, and launches the application. First build requires internet access to fetch base images and package dependencies. The English OCR model is bundled in the ZIP and is copied into the backend image, so it is not downloaded at runtime.

To stop services, press `Ctrl+C`. To keep services running in the background, use `docker compose up --build -d`; view logs using `docker compose logs -f backend`.

## Signup and OTP

- Create an account in the app.
- By default, `OTP_DELIVERY=console` is enabled for local development. The app will explicitly say that email delivery is disabled, and the OTP prints in the backend log. View it with `docker compose logs -f backend`.
- To send real email, create a `.env` file in the project root (same folder as `docker-compose.yml`), set `OTP_DELIVERY=smtp`, and fill `SMTP_USER`, `SMTP_APP_PASSWORD`, and `SMTP_FROM` with your email account and app password. For Gmail, enable 2-Step Verification and create an App Password; do not use your regular account password. Restart with `docker compose up --build -d` after changing `.env`. Then try signup again and check Inbox/Spam. If SMTP fails, signup returns an error instead of falsely claiming the email was sent.
- Enter the six-digit code.
- Only after successful OTP verification is the row inserted into `users` and a JWT returned.
- The default `OTP_DELIVERY=console` is development-only. SMTP settings can be configured in the root `.env` if you need actual email delivery. Never use console delivery in production.

## Features included

- OTP-verified registration with expiry, incorrect-attempt limit, resend cooldown, password hashing, JWT authentication, and protected endpoints.
- Medical document upload for PDF, PNG, JPG/JPEG, WEBP, and TIFF; per-user access isolation; metadata edit/delete; original download; SHA-256 integrity verification; and persistent upload storage.
- OCR for scanned PDFs and images via preprocessed Tesseract by default; optional Hugging Face-hosted vision OCR and Qwen structured extraction are used automatically for low-quality pages when HF_TOKEN is configured. Hugging Face inference avoids separate local model workers. The Qwen LoRA/QLoRA training scaffold is included, but a trained adapter is not bundled. If `LOCAL_QWEN_ADAPTER_DIR` points to a trained local adapter, structured extraction uses that local model first; otherwise the deterministic regex extractor remains the baseline.
- Hugging Face-first vision OCR for difficult handwriting, with OpenRouter as a fallback if configured. AI summaries use the configured Hugging Face chat model first and OpenRouter as fallback. These hosted steps are automatic by default; low-quality page images and OCR text may leave the local machine, so configure tokens only if you accept that data flow.
- Vaccination-card scan/import that stores the original card, suggests a vaccine name/date/dose where detectable, requires user confirmation, supports manual entry/edit/delete, and can create a reminder from a next-due date the user confirms.
- AI health assistant uses Hugging Face first (HF_TOKEN) and OpenRouter only as a configured fallback. It sends only matching uploaded medical-record excerpts, declines when no matching record supports the answer, refuses unrelated questions, and does not diagnose or prescribe.
- Settings page with server-side password change and OpenRouter model configuration status.
- Evidence Engine with explainable value candidates, source page and line, source excerpt, OCR/text extraction method, heuristic confidence indicator, file integrity signal, multi-value flags, and cross-record comparisons/timelines. This is a source traceability engine, not a diagnosis engine.
- Vaccination records, reminders, search over medical records, audit events, and dashboard UI.
- Health and database health endpoints.

## Novelty / capstone framing

The central differentiator is the **source-grounded Evidence Engine**: extracted candidate facts are linked to page/line/excerpt provenance and the uploaded file's SHA-256 digest; users can review multi-value flags and compare repeated fields across their own records. OCR and extraction confidence values are heuristic rather than medically calibrated. The system highlights items for review and does not declare a diagnosis, label a value as clinically normal/abnormal, or recommend treatment.

## Database and file persistence

PostgreSQL data persists in the `healthsync_postgres_data` Compose volume. Uploaded files persist in `healthsync_uploads`. On a new machine, simply running the one command creates empty storage and creates SQL tables from the backend's SQLAlchemy metadata at startup. This clean starter intentionally does not include the broken/old Alembic history from the prior local project.

**Destructive reset** (removes all local PostgreSQL data and uploaded files):

```bash
docker compose down -v
```

Do not run this if you need to keep uploaded records or accounts.

## Ports and configuration

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- PostgreSQL host port: `5433` (inside Compose network it uses `postgres:5432`)

Optional: copy `.env.example` to `.env` in the project root to override defaults. It supports `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `JWT_SECRET`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_APP_PASSWORD`, `SMTP_FROM`, and `OTP_DELIVERY` (`console` or `smtp`). Optional AI variables are `OPENROUTER_API_KEY`, `OPENROUTER_ENDPOINT`, `OPENROUTER_CHAT_MODEL_ID`, `OPENROUTER_SUMMARY_MODEL_ID`, `OPENROUTER_VISION_MODEL_ID`, Hugging Face variables `HF_TOKEN`, `HF_MODEL_ID`, `HF_VISION_MODEL_ID`, `HF_CHAT_ENDPOINT`, and `MAX_UPLOAD_MB`. For local demos defaults are supplied in Compose so you can run the one command immediately. Change the JWT secret and all default credentials before any non-local use; URL-encode reserved characters in credentials used in `DATABASE_URL`.

## Hugging Face setup and OpenRouter fallback

1. Copy `.env.example` to `.env` in the project root (same folder as `docker-compose.yml`).
2. Set `HF_TOKEN=hf_...` using a Hugging Face token that has Inference Providers access. Keep the token server-side; never put it in React code, screenshots, or Git.
3. The default models are configured with `HF_MODEL_ID=Qwen/Qwen3-4B:fastest` and `HF_VISION_MODEL_ID=Qwen/Qwen2.5-VL-3B-Instruct:fastest`. Change them if your account/provider does not support those IDs.
4. Run `docker compose up --build -d backend` and open Settings → **Refresh configuration**.
5. The Medical Records screen automatically runs local OCR first, escalates low-quality pages to hosted Hugging Face vision OCR, and creates an AI summary with Hugging Face. If Hugging Face is unavailable and `OPENROUTER_API_KEY` is configured, OpenRouter is used as fallback; if no model is available, uploads retain a local extractive summary. The assistant uses Hugging Face first and OpenRouter second.

**Data flow:** hosted AI is enabled by default in this build. A low-quality page image may be sent to the configured vision model; OCR text may be sent for summary generation; relevant excerpts from matched medical records may be sent for assistant answers. Review this data flow before uploading sensitive documents. The assistant is restricted to uploaded medical records and prompt/guardrail enforcement is not a guarantee of clinical safety. It is **not fine-tuned on your personal records** and does not recommend medicines or dose changes.

## Validation and limitations

This bundle is a development prototype, not a production-certified medical application. OCR can misread values. Candidate matching covers a limited set of common lab labels and requires review. File hashing detects changes relative to the recorded digest but does not itself make an external store immutable. Before production use, add a security review, malware scanning, CSRF strategy if cookie auth is adopted, formal retention/backups, rate limiting, email anti-abuse, stronger operational secrets, audit policies, accessibility review, and applicable privacy/regulatory assessment.

## Project structure

```text
healthsync-ai-fresh/
├── docker-compose.yml
├── README.md
├── LICENSES/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── models/tessdata/eng.traineddata
│   └── app/
│       ├── main.py
│       ├── api/deps.py
│       ├── api/v1/router.py
│       ├── api/v1/endpoints/ (auth, records, evidence, vaccinations, reminders, assistant)
│       ├── core/config.py
│       ├── db/session.py
│       ├── models/models.py
│       └── services/ (OTP, OCR, evidence engine)
├── ml_training/
│   ├── train_qwen_extractor.py
│   ├── evaluate_qwen_extractor.py
│   └── data/*.example.jsonl (synthetic schema examples only)
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    └── src/ (React UI, API client, styles)
```

## Frontend experience

The React/Vite frontend uses Tailwind CSS utility classes and a responsive light theme. The public landing page includes a mobile navigation menu, product overview, feature cards, workflow explanation, privacy and consent principles, and a dedicated section covering lab reports, prescriptions, diagnoses, hospital visits, allergies, medications, vaccination records, reminders, AI-assisted retrieval/summaries, and consent-based sharing. Feature descriptions communicate intended workflows; see the prototype limitations below before treating any feature as production-ready.

### Tailwind CSS not appearing in Docker

The frontend Docker image must include both `postcss.config.js` and `tailwind.config.js` so Vite/PostCSS can compile the `@tailwind` directives and utility classes. They are included in the frontend Dockerfile. After replacing an older project version, rebuild the frontend image without cache:

```bash
docker compose build --no-cache frontend
docker compose up -d
docker compose logs -f frontend
```

If running the frontend directly on your computer instead of Docker, run `cd frontend && npm install && npm run dev`.

## Uploads, handwriting OCR and AI configuration

Local OCR runs without an API key. Tesseract preprocessing works best on well-lit, straight, high-resolution images; messy handwriting and abbreviations can still be misread. For difficult handwriting, copy `.env.example` to `.env` and configure `HF_TOKEN` (with Inference Providers permission) in the project root. With automatic hosted AI enabled, low-quality document pages and OCR text may be sent to Hugging Face. OpenRouter remains an optional fallback. Keep provider keys in the backend `.env`, never in React code or Git. Restart after config changes with `docker compose up --build -d`.

This app does not claim to provide clinical decisions. OCR and model output must be reviewed against the original, and schedules are only reminders for dates a user enters/confirms. AI output is not diagnosis or treatment.
## Hugging Face inference and Qwen fine-tuning

The default Docker app does not launch local model workers and does not require `MODEL_WORKER_TOKEN`. Normal uploads use Tesseract. When OCR quality is low, the backend can automatically use a Hugging Face-hosted vision-language model for OCR and a Qwen chat model for evidence-linked fields. Configure `HF_TOKEN`, `HF_VISION_MODEL_ID`, `HF_MODEL_ID`, and `HF_CHAT_ENDPOINT` in `.env`; see `ml_training/README.md`. The included Qwen3-4B QLoRA script is a training scaffold only. No fine-tuned adapter is bundled, and hosted inference still uses the configured base model until you train and deploy an adapter to a compatible endpoint.

Candidate values are accepted only when the quoted evidence and value appear in source text. This does not prove OCR or clinical correctness; all candidates require human review.


## Novelty: adaptive, source-aware OCR

HEALTHSYNC-AI combines source-linked candidate extraction with a local-first OCR strategy. Local OCR runs first on scanned images; hosted OCR is invoked automatically only for pages with weak local OCR diagnostics. The evidence report surfaces local/hosted transcription disagreements so a person can check the original before relying on extracted values. See [`docs/PROJECT_NOVELTY.md`](docs/PROJECT_NOVELTY.md) for the contribution framing and evaluation protocol.


### Use your fine-tuned model without sending OCR text to OpenRouter/Hugging Face

The project is local-first by default: Tesseract OCR, regex-based candidate extraction, extractive summaries, hashing/integrity checks, and record retrieval run locally. The enhanced version can also load your trained Qwen LoRA adapter in the backend. After training and copying the adapter to `ml_training/output/healthsync-qwen3-extractor`, run:

```bash
INSTALL_LOCAL_MODEL=true docker compose up --build -d
```

Set `LOCAL_QWEN_ADAPTER_HOST_DIR` if your adapter lives elsewhere. Verify `local_qwen_configured: true` in `GET /api/assistant/config` (after login) before expecting adapter inference. Hosted Hugging Face is primary for chat/summaries/low-quality vision OCR by default; OpenRouter is only a fallback when configured. For no-hosted-inference development, run without provider tokens and remember the UI will use local fallbacks, while visible notices still describe the default hosted-AI behavior. The adapter is not bundled and must be trained first.

## Reminder notifications and email

The frontend notification bell shows reminders that are due today or overdue. Opening the bell marks the displayed items as seen for this browser/account; the unread badge then clears. Vaccination next-due dates create linked reminder entries, so they appear in the same notification list.

To send reminder emails, configure `SMTP_HOST`, `SMTP_PORT=465`, `SMTP_USER`, `SMTP_APP_PASSWORD`, and optionally `SMTP_FROM` in the project root `.env`. The backend checks due reminders once per minute and sends one email per reminder due date, logging successful sends in `audit_events`. Email is disabled when SMTP credentials are missing. The API container must remain running for scheduled email delivery. For production, use a durable worker/scheduler and migrate the audit-based send ledger to a dedicated notification table.

### Hosted OCR provider fallback

Local Tesseract runs first. Hosted vision OCR is attempted automatically only when the page is flagged for review. The backend tries Hugging Face first if `HF_TOKEN` is configured. If that request fails (including HTTP 402 for exhausted Hugging Face credits), it tries OpenRouter if `OPENROUTER_API_KEY` is configured. If both hosted providers are unavailable, the upload keeps the local Tesseract text and reports a review warning.

To enable the OpenRouter fallback, put `OPENROUTER_API_KEY=your_key` in the **project-root** `.env` file (next to `docker-compose.yml`), then rebuild/restart the backend with `docker compose up --build -d backend`. Keep API keys server-side; never put them in frontend variables. OpenRouter may also require available credits depending on the selected model.

## Structured prescription and care extraction

Click **Analyze** on a saved record to run the Evidence Engine and, after confirmation, send the OCR transcription to Hugging Face first for structured extraction; OpenRouter is the fallback if configured. The report displays medicine names as written, strength/dose/route/frequency/duration, tests/results, any food/exercise/precaution/temperature/storage/follow-up instructions actually found in the document, source excerpts, uncertainty flags, and a separately labelled general-education section. Low-confidence scanned pages can be retried through hosted vision OCR after the same confirmation. Results are saved to the record and become available as context to the AI Health Assistant.

Configure `OPENROUTER_API_KEY` in the project-root `.env`. The Analyze confirmation describes when page images may be sent to a hosted vision provider. Cancel runs local evidence review only. Not-specified fields are never filled with invented medication doses, storage temperatures, or follow-up schedules. See [`docs/AI_MEDICAL_ANALYSIS.md`](docs/AI_MEDICAL_ANALYSIS.md) for workflow, provider settings and limitations.

### Verify extracted information

The Evidence Engine includes per-item verification controls for medicine fields, test results, care instructions, and rule-based candidates. Users can confirm a value against the original, correct its transcription while retaining the source excerpt, or mark it incorrect. The saved state is user review—not clinician approval. See [`docs/VERIFYING_EXTRACTED_INFORMATION.md`](docs/VERIFYING_EXTRACTED_INFORMATION.md).
