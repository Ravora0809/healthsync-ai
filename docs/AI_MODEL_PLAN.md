# HEALTHSYNC-AI model architecture and training plan

## Runtime architecture

1. **Text extraction:** PyMuPDF reads searchable PDF text. Local Tesseract handles scanned PDFs and images by default.
2. **Vision OCR:** Local OCR runs first. If a scanned page is low quality, hosted vision is automatically attempted using `HF_VISION_MODEL_ID` (default `Qwen/Qwen2.5-VL-3B-Instruct:fastest`) when `HF_TOKEN` is configured. OpenRouter is the fallback if configured.
3. **Structured extraction:** For pages that required hosted OCR, the backend may send OCR text to the Hugging Face chat endpoint using `HF_MODEL_ID` (default `Qwen/Qwen3-4B:fastest`) and requests JSON candidate fields. A local evidence validator rejects fields whose quoted excerpt/value is not literally in the provided OCR text. If the hosted model fails, the deterministic regex baseline remains available.
4. **Review:** Every accepted candidate is provisional and must be checked against the original. Source-text matching does not prove OCR correctness or clinical truth.
5. **Summaries / assistant:** Hugging Face is the default primary provider for record summaries and answers. OpenRouter is used as fallback when configured. Only matched uploaded medical-record excerpts are sent for assistant answers.

The main Docker runtime no longer calls a PaddleOCR worker and does not need `MODEL_WORKER_TOKEN`. Hosted model inference depends on Hugging Face token permissions, model/provider availability, network connectivity, and any billing/credits configured with the provider.

## Fine-tuning plan

Base model: <https://huggingface.co/Qwen/Qwen3-4B>

The repository includes a QLoRA script (`ml_training/train_qwen_extractor.py`) using Transformers, TRL and PEFT. It expects a CUDA GPU (e.g. Colab T4/A100) and reviewed JSONL training/validation datasets. The included example rows are synthetic demonstrations and are not sufficient for meaningful training or research claims. A trained adapter is **not** bundled.

The standard hosted call currently uses the base model listed in `HF_MODEL_ID`. Fine-tuning an adapter does not automatically change hosted inference. To use a trained adapter in the running app, deploy the adapter (or merge it into a compatible model) on a Hugging Face Inference Endpoint compatible with the chat-completions API, then configure `HF_CHAT_ENDPOINT` and `HF_MODEL_ID` for that deployed model. Evaluate against a patient/document-separated held-out test set before reporting results.

See `ml_training/README.md` for setup and commands.


## Adaptive OCR routing implemented in the backend

The backend now starts with the local Tesseract path for images and scanned PDF pages. With hosted OCR enabled by default, it escalates only low-quality pages to hosted vision OCR. The default threshold is `OCR_ESCALATION_MIN_CONFIDENCE=65`; escalation also occurs when little/no text is returned or at least 35% of recognized words have Tesseract confidence below 50. A searchable PDF text layer bypasses OCR. The evidence engine stores per-page diagnostics and displays a review flag if OCR quality is low, hosted OCR fails, or the local and hosted readings differ. Hosted structured extraction is also limited to the pages actually escalated and is merged with deterministic candidates instead of replacing them. The threshold is configurable; confidence is a routing heuristic and should not be described as calibrated accuracy.


## Hosted-data disclosure

This build enables hosted AI by default. Low-quality scanned images, extracted OCR text used to generate summaries, and relevant retrieved record excerpts for assistant answers may leave the local machine and be processed by the configured Hugging Face provider, with OpenRouter as a fallback. This is distinct from training: the assistant retrieves each authenticated patient's own saved records at query time; it does not fine-tune a shared model on those records.
