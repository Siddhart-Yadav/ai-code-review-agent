import logging
from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    APP_NAME: str = "AI Code Review Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # API
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/code_review"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/code_review"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 86400  # 24 hours

    # LLM Provider — "gemini", "openai", "anthropic", or "groq"
    LLM_PROVIDER: str = "gemini"

    # Gemini (Vertex AI via ADC, or API key)
    GCP_PROJECT_ID: str = ""
    GCP_REGION: str = "us-east5"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Groq (free tier — Llama 3.3 70B, OpenAI-compatible)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # GitHub
    GITHUB_TOKEN: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY: str = ""

    # LangGraph
    MAX_AGENT_RETRIES: int = 2
    AGENT_TIMEOUT_SECONDS: int = 120

    # Demo mode
    DEMO_MODE: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_llm_config(self) -> "Settings":
        provider = self.LLM_PROVIDER.lower()

        # Auto-detect provider from available API keys
        if provider == "gemini" and not self.GCP_PROJECT_ID and not self.GEMINI_API_KEY:
            if self.GROQ_API_KEY:
                self.LLM_PROVIDER = "groq"
                logger.info("Auto-detected LLM provider: groq")
            elif self.OPENAI_API_KEY:
                self.LLM_PROVIDER = "openai"
                logger.info("Auto-detected LLM provider: openai")
            elif self.ANTHROPIC_API_KEY:
                self.LLM_PROVIDER = "anthropic"
                logger.info("Auto-detected LLM provider: anthropic")
            else:
                self.DEMO_MODE = True
                logger.warning(
                    "No LLM API key configured. Running in demo mode only. "
                    "Set GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
                )

        return self

    @property
    def llm_configured(self) -> bool:
        """Check if any LLM provider is properly configured."""
        provider = self.LLM_PROVIDER.lower()
        if provider == "gemini":
            return bool(self.GCP_PROJECT_ID or self.GEMINI_API_KEY)
        elif provider == "openai":
            return bool(self.OPENAI_API_KEY)
        elif provider == "anthropic":
            return bool(self.ANTHROPIC_API_KEY)
        elif provider == "groq":
            return bool(self.GROQ_API_KEY)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
