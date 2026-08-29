from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Razorpay ────────────────────────────────────────────
    razorpay_key_id: str = "rzp_test_placeholder"
    razorpay_key_secret: str = "placeholder"
    razorpay_webhook_secret: str = "placeholder"

    # ── LLM ────────────────────────────────────────────────
    google_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""

    # ── Database ────────────────────────────────────────────
    database_url: str = "sqlite:///./data/autodefend.db"

    # ── Redis ───────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── App behaviour ───────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    # Confidence threshold: below this → RECOMMEND_ACCEPT
    auto_defend_confidence_threshold: float = 0.70

    # Disputes above this paise value need explicit merchant approval
    high_value_threshold_paise: int = 500_000       # Rs.5,000

    # Disputes below this paise value → fully autonomous (no notification window)
    autonomous_max_paise: int = 500_000             # Rs.5,000

    # Use mock data for executors (True = demo mode, False = real APIs)
    use_mock_apis: bool = True

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.
    Import and call: from app.config import get_settings; settings = get_settings()
    """
    return Settings()
