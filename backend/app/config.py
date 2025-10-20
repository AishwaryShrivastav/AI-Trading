"""Configuration management using pydantic-settings."""
from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # App settings
    app_name: str = "AI Trading System"
    environment: str = "development"
    debug: bool = True
    secret_key: str = "change-this-in-production"
    
    # Database
    database_url: str = "sqlite:///./trading.db"
    
    # Upstox API
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://localhost:8000/api/auth/upstox/callback"
    
    # OpenAI API
    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo-preview"
    
    # LLM Provider
    llm_provider: str = "openai"  # openai, gemini, huggingface
    
    # Risk Parameters
    max_capital_risk_percent: float = 2.0
    min_liquidity_adv: int = 1000000
    max_position_size_percent: float = 10.0
    max_sector_exposure_percent: float = 30.0
    
    # Trading Parameters
    default_trade_horizon_days: int = 3
    earnings_blackout_days: int = 2
    
    # Scheduler
    signal_generation_hour: int = 9
    signal_generation_minute: int = 15
    eod_report_hour: int = 16
    eod_report_minute: int = 0
    
    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:8000,http://localhost:3000"
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/trading.log"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

