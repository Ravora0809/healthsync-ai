# HEALTHSYNC-AI: automatic Hugging Face-first record assistant

## What changed

- The Medical Records page no longer has the two AI opt-in checkboxes. OCR escalation and AI summaries are enabled by default. OCR still starts locally and sends only low-quality scanned pages to hosted vision OCR.
- Hugging Face (`HF_TOKEN` + `HF_MODEL_ID`) is the primary hosted model for record summaries and assistant answers. OpenRouter is used as a fallback only when configured.
- The assistant only uses matching uploaded medical records from the signed-in patient's account. It no longer pulls reminders or separately patient-entered vaccine entries into chat context. If no uploaded record matches, it says so rather than answering from unrelated records.
- The assistant prompt requires record-grounded answers, source names, clear uncertainty, and no diagnosis or prescribing. Suggestions must be supported by explicit content in the record. These are guardrails, not a guarantee against all model mistakes.
- If neither hosted provider is usable, uploads keep a local extractive summary, and chat falls back to source snippets.

## Hugging Face setup

In the root `.env` (beside `docker-compose.yml`), set a token with Inference Providers access:  
`HF_TOKEN=hf_your_private_token`  
`HF_MODEL_ID=Qwen/Qwen3-4B:fastest`  
`HF_VISION_MODEL_ID=Qwen/Qwen2.5-VL-3B-Instruct:fastest`  
`HF_CHAT_ENDPOINT=https://router.huggingface.co/v1/chat/completions`

Keep the token on the backend and out of React, Git, and screenshots. Then rebuild the backend: `docker compose up -d --build backend`.

## Important privacy and training distinction

Hosted processing is enabled automatically in this build. Low-quality page images, OCR text for summaries, and relevant record excerpts for AI answers may be transmitted to the configured inference provider. Do not use this setting for records you are not authorized to send to that provider. Local OCR and local extractive summaries remain fallbacks.

Configuring `HF_TOKEN` enables model inference; it does not train or fine-tune the model. Chat uses retrieval-augmented prompting over the current patient's own records (record grounding), rather than training a shared model on private medical documents. The included Qwen LoRA training scaffold must be trained/evaluated separately on properly authorized, preferably de-identified data.

This is not a clinically validated diagnostic system. OCR, AI summaries, and answers can be wrong; verify them against the original documents and ask a clinician/pharmacist about clinical decisions.
