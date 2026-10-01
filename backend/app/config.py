"""
backend/app/config.py

Centralized configuration. All values come from environment variables
(see .env.example) -- nothing here is hardcoded to a real secret.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg2://inventory_user:inventory_pass@localhost:5432/inventory_db"

    # LLM (Groq)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Forecasting
    default_forecast_horizon: int = 14

    # Reorder / stockout-risk assumptions
    default_lead_time_days: int = 7
    safety_stock_service_factor: float = 1.65

    # Inventory thresholds
    low_stock_threshold: int = 50

    # App
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
