from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_path: str = "./state_shift_logger.sqlite3"

    webhook_shared_secret: str = ""
    admin_token: str = ""

    omi_app_id: str = ""
    omi_api_key: str = ""
    omi_api_base_url: str = "https://api.omi.me"

    notify_threshold: float = 0.55
    log_threshold: float = 0.65
    notification_cooldown_seconds: int = 90

    create_omi_memory_on_explicit_log: bool = True
    create_omi_memory_on_high_confidence: bool = False

    store_raw_audio: bool = False
    raw_audio_dir: str = "./raw_audio"

    retention_days: int = 90


settings = Settings()
