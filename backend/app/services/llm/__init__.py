"""LLM provider services."""
import logging

from .base import LLMBase
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .huggingface_provider import HuggingFaceProvider
from .anthropic_provider import AnthropicProvider
from ...config import get_settings

logger = logging.getLogger(__name__)

__all__ = [
    "LLMBase",
    "OpenAIProvider",
    "GeminiProvider",
    "HuggingFaceProvider",
    "AnthropicProvider",
    "get_llm_provider",
    "get_agent_llm",
]


def _openai(settings) -> LLMBase:
    if not settings.openai_api_key:
        raise ValueError(
            "No LLM provider available: set ANTHROPIC_API_KEY (preferred) or OPENAI_API_KEY in .env"
        )
    return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)


def _anthropic(settings) -> LLMBase:
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)


def get_llm_provider() -> LLMBase:
    """Get the configured LLM provider.

    Per the TradeHarness plan the brain is Claude-first: ``anthropic`` is the
    default. If the requested provider has no key configured we fall back to
    whichever provider does have a key (Anthropic preferred, then OpenAI) so the
    app and test suite keep working in partially-configured environments.
    """
    settings = get_settings()
    provider_name = (settings.llm_provider or "anthropic").lower()

    if provider_name == "anthropic":
        if settings.anthropic_api_key:
            return _anthropic(settings)
        logger.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY missing; falling back to OpenAI.")
        return _openai(settings)

    if provider_name == "openai":
        if settings.openai_api_key:
            return _openai(settings)
        if settings.anthropic_api_key:
            logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY missing; falling back to Anthropic.")
            return _anthropic(settings)
        return _openai(settings)  # raises with guidance

    # gemini / huggingface are stubs — fall back to the best configured provider.
    logger.warning(
        f"{provider_name} is not yet implemented. Falling back to the best configured provider."
    )
    if settings.anthropic_api_key:
        return _anthropic(settings)
    return _openai(settings)


def get_agent_llm() -> LLMBase:
    """Cheaper provider for high-frequency specialist agents (Haiku-tier).

    Uses the Anthropic agent model when a key is present; otherwise falls back
    to the default provider so agents still function.
    """
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_agent_model,
        )
    return get_llm_provider()
