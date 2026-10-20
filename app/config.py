from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    footage_providers: str = "mock"
    tts_provider: str = "mock"
    stt_provider: str = "mock"
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    gemini_api_key: str = ""
    llm_model: str = "gemini-2.0-flash"
    piper_model: str = "models/en_US-lessac-medium.onnx"
    whisper_model: str = "base"
    min_scene_seconds: float = 2.5
    max_audio_seconds: int = 600
    max_audio_mb: int = 200
    max_concurrent_jobs: int = 1
    callback_secret: str = "change-me"
    fallback_enabled: bool = True
    data_dir: str = "data"
    storage_backend: str = "local"
    s3_endpoint: str = "http://localhost:9000"
    s3_public_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "broll"
    api_token: str = ""
    rate_limit_per_min: int = 20


settings = Settings()