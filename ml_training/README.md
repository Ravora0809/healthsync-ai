# HEALTHSYNC-AI: Hugging Face inference and Qwen fine-tuning

This project now uses **Hugging Face Inference Providers** for optional hosted vision OCR and structured extraction. Normal uploads use the bundled Tesseract OCR locally. No PaddleOCR process, `MODEL_WORKER_TOKEN`, or second local API server is required. Hosted vision/extraction only runs when the user checks the consent box on upload.

## 1. Configure hosted Hugging Face inference

Create a Hugging Face access token with Inference Providers permission and add it to the root `.env` file (next to `docker-compose.yml`):

```dotenv
HF_TOKEN=hf_your_private_token
HF_CHAT_ENDPOINT=https://router.huggingface.co/v1/chat/completions
HF_VISION_MODEL_ID=Qwen/Qwen2.5-VL-3B-Instruct:fastest
HF_MODEL_ID=Qwen/Qwen3-4B:fastest
```

Keep the token private and never put it in React/Vite. Hosted inference availability, account permissions, rate limits and charges depend on Hugging Face and the selected provider. The API uses the Vision-Language Model for OCR and Qwen for source-linked field extraction. If the hosted request fails, opted-in OCR reports a clear error and the non-opt-in local OCR path remains available. The structured model path falls back to the deterministic regex baseline if the model response cannot be used.

Rebuild/restart after updating `.env`:

```bash
docker compose up --build -d
docker compose logs -f backend
```

In the app upload page, tick **Allow hosted AI processing for uncertain pages** to allow optional remote processing. Local Tesseract runs first; only scanned pages that are actually escalated for low OCR quality are eligible for hosted vision OCR and hosted structured extraction. Searchable PDF text is used directly and does not trigger these calls. If the box is unchecked, OCR and candidate extraction stay on the local baseline and document content is not sent to Hugging Face for OCR/extraction. The `OCR_ESCALATION_MIN_CONFIDENCE` threshold defaults to `65` and can be set in the root `.env`; the low-confidence-word ratio can independently trigger escalation.

## 2. Fine-tune Qwen3-4B with QLoRA

Base model: <https://huggingface.co/Qwen/Qwen3-4B>

Training scaffold: `train_qwen_extractor.py` uses Transformers, TRL, PEFT and 4-bit QLoRA. Use a CUDA GPU (for example a Google Colab T4/A100); the training script intentionally refuses to start without CUDA. The MacBook Air M1 is fine for code and data preparation, but is not the recommended machine to fine-tune Qwen3-4B.

The JSONL files shipped in `data/*.example.jsonl` are **synthetic format examples only** and are too small to train a meaningful model. Build a reviewed, permitted, preferably de-identified dataset; avoid sending real patient records to third-party tools without appropriate authorization. Split by patient/document source, and keep an untouched test set. Each JSONL row follows the chat `messages` format. The assistant answer should contain a JSON object like:

```json
{"candidates":[{"field":"hemoglobin","value":"13.2","unit":"g/dL","source_page":1,"source_line":1,"source_excerpt":"Hemoglobin: 13.2 g/dL"}]}
```

Every source excerpt must literally appear in the input OCR text and must contain the value. Include unclear pages and examples where the correct answer is an empty candidate list. The script requires at least 50 training and 10 validation rows unless you explicitly pass `--allow-small-dataset` for a pipeline smoke test only. Those are technical minimums, not evidence of research quality.

### Run in Google Colab

1. Create a new Colab notebook and choose **Runtime → Change runtime type → T4 GPU** (or a stronger CUDA GPU).
2. Upload the HEALTHSYNC-AI ZIP, unzip it, and `cd` to its project folder in the notebook. Alternatively, clone your private repository.
3. Place your reviewed `train.jsonl` and `validation.jsonl` in `ml_training/data/`. Do not use real identifiable patient data in a notebook unless you have the required authorization and privacy controls.
4. Run:

```bash
%cd /content/healthsync-ai-fresh
!pip install -r ml_training/requirements.txt
!python ml_training/train_qwen_extractor.py \
  --model Qwen/Qwen3-4B \
  --train ml_training/data/train.jsonl \
  --validation ml_training/data/validation.jsonl \
  --output ml_training/output/healthsync-qwen3-extractor
```

Download `ml_training/output/healthsync-qwen3-extractor/` from Colab after training, or upload the adapter to Hugging Face Hub using a private repository. The output is a **LoRA adapter**, not a standalone full model. The app's hosted `HF_MODEL_ID=Qwen/Qwen3-4B:fastest` still calls the base model. To serve the fine-tuned adapter, deploy it on a compatible Hugging Face Inference Endpoint (or merge the adapter and deploy a compatible custom model endpoint), then point `HF_CHAT_ENDPOINT` at that endpoint's chat-completions URL and set `HF_MODEL_ID` as required by the deployment. Merely saving an adapter does not make hosted inference use it.

## 3. Evaluate before claiming results

```bash
python ml_training/evaluate_qwen_extractor.py \
  --model Qwen/Qwen3-4B \
  --adapter ml_training/output/healthsync-qwen3-extractor \
  --data ml_training/data/validation.jsonl
```

Report exact field/value precision, recall and F1, JSON-validity rate, source-support rate, OCR errors and hallucination/rejection rates on a held-out set. These are engineering metrics, not clinical validation. Training completion alone does not establish accuracy.

## Safety and data flow

- OCR and model fields are suggestions, not diagnosis or treatment advice.
- Backend code validates quoted excerpts and values against OCR source text; this does not prove that the OCR text itself is correct.
- Every stored candidate is marked `requires_human_review`.
- The hosted model does not count as fine-tuned until you have trained an adapter and deployed that adapter for inference.


## 4. Use the trained adapter locally in the app (no hosted inference for extraction)

After training and copying the adapter folder onto the backend host, set these values in the root `.env` file:

```dotenv
LOCAL_QWEN_BASE_MODEL_ID=Qwen/Qwen3-4B
LOCAL_QWEN_ADAPTER_DIR=./ml_training/output/healthsync-qwen3-extractor
LOCAL_QWEN_MAX_NEW_TOKENS=700
```

Place the adapter on the host at `ml_training/output/healthsync-qwen3-extractor` (or set `LOCAL_QWEN_ADAPTER_HOST_DIR` to another host directory). For Docker, build with local inference dependencies installed:

```bash
INSTALL_LOCAL_MODEL=true docker compose up --build -d
```

The Docker build installs `backend/requirements-local-model.txt` (`torch`, `transformers`, `peft`, `accelerate`, and `safetensors`), mounts the adapter read-only, and sets `LOCAL_QWEN_ADAPTER_DIR=/app/local_models/healthsync-qwen3-extractor`. For a non-Docker deployment, install that same requirements file in the backend environment and point `LOCAL_QWEN_ADAPTER_DIR` at the adapter directory. Restart the backend. When a valid `adapter_config.json` exists at `LOCAL_QWEN_ADAPTER_DIR`, uploads use the local fine-tuned adapter for structured extraction by default. OCR remains local Tesseract; the app applies the same literal-source-evidence validator to the adapter output. If the adapter is not configured or fails to load, the app retains deterministic regex candidates and reports a warning.

This does not make OpenRouter/Hugging Face-hosted chat, summaries, or optional hosted vision OCR disappear; those separate features remain opt-in. To operate with no hosted provider calls, leave cloud OCR and OpenRouter summary/chat options off and do not configure provider tokens. Local model inference can be slower or require more RAM/VRAM; benchmark on your actual deployment before enabling it for all users.
