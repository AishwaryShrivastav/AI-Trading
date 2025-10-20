"""LLM provider services."""
from .base import LLMBase
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .huggingface_provider import HuggingFaceProvider
from ...config import get_settings

__all__ = ["LLMBase", "OpenAIProvider", "GeminiProvider", "HuggingFaceProvider", "get_llm_provider"]


def get_llm_provider() -> LLMBase:
    """
    Get configured LLM provider based on settings.
    
    Returns:
        Instance of configured LLM provider
    
    Note: Only OpenAI is production-ready. Others are placeholders.
    """
    settings = get_settings()
    provider_name = settings.llm_provider.lower()
    
    # Only OpenAI is production-ready
    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in .env")
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )
    elif provider_name in ["gemini", "huggingface"]:
        # Gracefully fallback to OpenAI with warning
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"{provider_name} is not yet implemented. "
            f"Falling back to OpenAI. Set LLM_PROVIDER=openai in .env to remove this warning."
        )
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in .env")
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )
    else:
        # Default to OpenAI
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in .env")
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )

