"""
backend/app/config.py

Centralized configuration. All values come from environment variables
(see .env.example) -- nothing here is hardcoded to a real secret.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Resolve the project-level .env independently of the current directory.
    # The API and migration commands run from backend/, while the file lives
    # at the repository root.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg2://inventory_user:inventory_pass@localhost:5432/inventory_db"

    # LLM provider selection: auto chooses Gemini when its key is present (or
    # when a legacy GROQ_API_KEY contains a Google AI Studio key), otherwise Groq.
    llm_provider: str = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.5-flash"

    # LLM (Groq, retained for users who still use Groq)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    # Forecasting
    default_forecast_horizon: int = 14

    # Reorder / stockout-risk assumptions
    default_lead_time_days: int = 7
    safety_stock_service_factor: float = 1.65

    # Inventory thresholds
    low_stock_threshold: int = 50

    # Stockout / reorder result cache (Tier A). The inputs are historical and
    # immutable, so a cached risk/reorder row stays correct; the TTL is a
    # safety valve for a future data reload, not a correctness requirement.
    # 0 disables caching entirely (used by tests that mutate the source data).
    risk_cache_ttl_seconds: float = 300.0

    # Redis (for session storage)
    redis_url: str = "redis://localhost:6379/0"

    # App
    environment: str = "development"
    log_level: str = "INFO"
    # Set distinct, private values before exposing the API on a network.
    auth_admin_username: str = ""
    auth_admin_password: str = ""
    auth_token_secret: str = ""
    auth_token_ttl_minutes: int = 60
    cors_allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # Real-time layer (Tier 1 demo). The simulator is OFF by default: it is a
    # demo device, not a data source, and nothing in the analytical path may
    # silently depend on it (see app/models/realtime.py).
    simulator_enabled: bool = False
    simulator_tick_seconds: float = 3.0
    simulator_events_per_tick: int = 3
    # Suppress a repeat alert for the same product at the same severity
    # within this window (an unacknowledged alert stays in the panel until
    # someone acts on it -- no need to re-announce it every tick).
    simulator_alert_cooldown_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
