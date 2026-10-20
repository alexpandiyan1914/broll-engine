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
    data_dir: str = "data"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "broll"
    redis_url: str = "redis://localhost:6379/0"
    whisper_model: str = "base"
    min_scene_seconds: float = 2.5
    max_concurrent_jobs: int = 1
    callback_secret: str = "change-me"
    max_audio_mb: int = 200


settings = Settings()