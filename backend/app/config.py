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

    # Anthropic (Claude) API — default orchestrator brain per TradeHarness plan
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"  # orchestrator (heavy reasoning)
    anthropic_agent_model: str = "claude-haiku-4-5"  # specialist agents (cheap, high-freq)

    # LLM Provider — anthropic (default when key present), openai, gemini, huggingface
    llm_provider: str = "anthropic"

    # Trading mode — paper (simulated fills, safe) or live (real Upstox orders)
    trading_mode: str = "paper"  # paper | live
    paper_slippage_bps: float = 5.0  # simulated slippage in basis points

    # Orchestrator (Claude brain) cost control
    daily_llm_cost_cap_inr: float = 200.0  # hard daily cap; rule-based fallback beyond
    auto_execute_conviction: float = 0.75  # >= this and no risk flags -> AUTO
    hil_min_conviction: float = 0.50  # >= this -> HIL, below -> SKIP
    use_specialist_agents: bool = True  # enrich orchestrator context via News/Technical/Macro agents

    # Risk governor — staged drawdown protocol (Step 4)
    drawdown_derisk_pct: float = 8.0   # halve position sizes beyond this drawdown
    drawdown_halt_pct: float = 12.0    # halt new entries + paper + self-diagnose
    derisk_capital_factor: float = 0.5  # size multiplier in DERISK state
    post_resume_derisk_days: int = 14   # reduced sizing window after RESUME
    post_resume_capital_factor: float = 0.5

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

