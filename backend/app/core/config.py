from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    app_name: str = "HEALTHSYNC-AI API"
    environment: str = "development"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://healthsync_user:healthsync_dev_password@localhost:5433/healthsync"
    jwt_secret: str = "local-development-secret-change-this-before-deployment-123456"
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    upload_dir: str = "./storage/medical_records"
    public_app_url: str = ""
    tessdata_dir: str = str(Path(__file__).resolve().parents[2] / "models" / "tessdata")
    max_upload_mb: int = 15
    hf_token: str = ""
    hf_model_id: str = "Qwen/Qwen3-4B:fastest"
    hf_vision_model_id: str = "Qwen/Qwen2.5-VL-3B-Instruct:fastest"
    hf_chat_endpoint: str = "https://router.huggingface.co/v1/chat/completions"
    # Local fine-tuned extractor. When an adapter directory is configured, uploads use it
    # locally by default; no OCR text is sent to an external provider for this step.
    local_qwen_base_model_id: str = "Qwen/Qwen3-4B"
    local_qwen_adapter_dir: str = ""
    local_qwen_max_new_tokens: int = 700
    openrouter_api_key: str = ""
    openrouter_endpoint: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_chat_model_id: str = "openai/gpt-4o-mini"
    openrouter_summary_model_id: str = "openai/gpt-4o-mini"
    openrouter_vision_model_id: str = "google/gemini-2.5-flash"
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_seconds: int = 60
    otp_delivery: str = "console"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_app_password: str = ""
    smtp_from: str = ""
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")
    @property
    def cors_origin_list(self):
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
settings = Settings()
