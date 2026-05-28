from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Telegram
    telegram_bot_token: str = ""
    webhook_base_url: str = "http://localhost:8000"
    ngrok_auth_token: str = ""

    # LLM
    llm_provider: str = "grok"
    grok_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_model: str = "grok-3"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # Database
    database_url: str = "sqlite+aiosqlite:///./classroom_companion.db"
    test_database_url: str = "sqlite+aiosqlite:///./test_classroom_companion.db"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    # Scheduler
    reminder_check_interval_minutes: int = 60
    reminder_daily_hour: int = 9
    reminder_daily_minute: int = 0
    escalation_days_before_deadline: int = 2

    # Local Dev
    local_dev: bool = True
    seed_db: bool = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
