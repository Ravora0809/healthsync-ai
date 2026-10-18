"""Local inference client for HEALTHSYNC-AI's fine-tuned Qwen extractor.

The adapter is optional. If it is not installed/configured, callers should fall back to
source-grounded deterministic extraction. This client never contacts an external endpoint.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.services.model_clients import validate_model_candidates


def local_qwen_extractor_configured() -> bool:
    """Return True only when a real PEFT adapter directory is present."""
    raw_path = str(settings.local_qwen_adapter_dir or "").strip()
    if not raw_path:
        return False
    path = Path(raw_path).expanduser()
    return path.is_dir() and (path / "adapter_config.json").is_file()


def _parse_and_validate_response(pages: list[dict], response: str) -> tuple[list[dict], int]:
    """Parse model JSON and retain only values anchored to literal OCR excerpts."""
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(response or "").strip(), flags=re.I)
    match = re.search(r"\{[\s\S]*\}", clean)
    if not match:
        raise RuntimeError("Local Qwen extractor returned no JSON object.")
    parsed = json.loads(match.group(0))
    raw = parsed.get("candidates", []) if isinstance(parsed, dict) else None
    if not isinstance(raw, list):
        raise RuntimeError("Local Qwen extractor returned an invalid candidates list.")
    return validate_model_candidates(pages, raw, extraction_method="local_qwen_lora_extractor")


@lru_cache(maxsize=1)
def _load_local_model():
    """Load the configured base model and its PEFT adapter once per worker process."""
    if not local_qwen_extractor_configured():
        raise RuntimeError(
            "Local Qwen adapter is not configured. Set LOCAL_QWEN_ADAPTER_DIR to a trained adapter directory."
        )

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    adapter_dir = str(Path(settings.local_qwen_adapter_dir).expanduser().resolve())
    base_id = settings.local_qwen_base_model_id
    if torch.cuda.is_available():
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        device_map = "auto"
    else:
        # CPU mode avoids assuming CUDA exists; inference will be slower for a 4B model.
        dtype = torch.float32
        device_map = {"": "cpu"}

    tokenizer_source = adapter_dir if (Path(adapter_dir) / "tokenizer_config.json").exists() else base_id
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        base_id,
        torch_dtype=dtype,
        device_map=device_map,
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(base_model, adapter_dir, is_trainable=False)
    model.eval()
    return tokenizer, model


def _render_inputs(tokenizer, messages):
    try:
        return tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors="pt", return_dict=True, enable_thinking=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors="pt", return_dict=True,
        )


def local_qwen_extract_candidates(pages: list[dict]) -> tuple[list[dict], int]:
    """Run the project's locally fine-tuned Qwen adapter on OCR text, then validate evidence.

    Use after local OCR. Model outputs are candidates only; no clinical interpretation occurs.
    """
    if not local_qwen_extractor_configured():
        raise RuntimeError("Local Qwen adapter is not configured.")
    if not pages:
        return [], 0

    tokenizer, model = _load_local_model()
    source_pages = [
        {"page": int(page.get("page", 1)), "text": str(page.get("text") or "")[:10000]}
        for page in pages
    ]
    source = json.dumps(source_pages, ensure_ascii=False)
    if len(source) > 22000:
        source = source[:22000]
    system = (
        "You extract only explicit facts from patient-provided medical document OCR text. "
        "Do not diagnose, interpret results, recommend treatment, or infer missing values. "
        "Return only JSON: {\"candidates\":[{\"field\":string,\"value\":string,\"unit\":string,"
        "\"source_page\":integer,\"source_excerpt\":string}]}. "
        "Every value must appear verbatim inside its source_excerpt and every excerpt must come from a supplied page. "
        "Extract only clearly written lab values, dates, medicine names/doses, vaccine details, allergies and follow-up instructions. "
        "Omit uncertain fields; if none are supported return {\"candidates\":[]}. No markdown."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Extract source-supported candidates from these OCR pages:\n" + source},
    ]
    import torch
    encoded = _render_inputs(tokenizer, messages)
    input_device = model.get_input_embeddings().weight.device
    encoded = {key: value.to(input_device) for key, value in encoded.items()}
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            max_new_tokens=max(64, min(int(settings.local_qwen_max_new_tokens), 1400)),
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    prompt_length = encoded["input_ids"].shape[-1]
    response = tokenizer.decode(generated[0][prompt_length:], skip_special_tokens=True)
    return _parse_and_validate_response(pages, response)
