from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"
    footage_providers: str = "mock"
    tts_provider: str = "mock"
    stt_provider: str = "mock"
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "broll"
    redis_url: str = "redis://localhost:6379/0"

settings = Settings()