"""Tests for the Claude/Anthropic provider and LLM factory (Step 1)."""
import pytest

import backend.app.services.llm as llm_pkg
from backend.app.services.llm.anthropic_provider import AnthropicProvider, _extract_json
from backend.app.services.llm.openai_provider import OpenAIProvider


class _FakeSettings:
    def __init__(self, provider, anthropic_key="", openai_key=""):
        self.llm_provider = provider
        self.anthropic_api_key = anthropic_key
        self.anthropic_model = "claude-opus-4-8"
        self.openai_api_key = openai_key
        self.openai_model = "gpt-4-turbo-preview"


def test_extract_json_direct():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = "Here is the result:\n```json\n{\"confidence\": 0.7}\n```\nthanks"
    assert _extract_json(text) == {"confidence": 0.7}


def test_extract_json_embedded_span():
    text = "noise {\"x\": [1, 2]} trailing"
    assert _extract_json(text) == {"x": [1, 2]}


def test_extract_json_raises_on_garbage():
    with pytest.raises(ValueError):
        _extract_json("no json here at all")


def test_factory_selects_anthropic_when_key_present(monkeypatch):
    monkeypatch.setattr(llm_pkg, "get_settings",
                        lambda: _FakeSettings("anthropic", anthropic_key="sk-ant-test"))
    provider = llm_pkg.get_llm_provider()
    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-opus-4-8"


def test_factory_falls_back_to_openai_when_no_anthropic_key(monkeypatch):
    monkeypatch.setattr(llm_pkg, "get_settings",
                        lambda: _FakeSettings("anthropic", anthropic_key="", openai_key="sk-openai"))
    provider = llm_pkg.get_llm_provider()
    assert isinstance(provider, OpenAIProvider)


def test_factory_falls_back_to_anthropic_when_openai_requested_but_missing(monkeypatch):
    monkeypatch.setattr(llm_pkg, "get_settings",
                        lambda: _FakeSettings("openai", anthropic_key="sk-ant", openai_key=""))
    provider = llm_pkg.get_llm_provider()
    assert isinstance(provider, AnthropicProvider)


@pytest.mark.asyncio
async def test_generate_trade_analysis_parses_claude_json(monkeypatch):
    """The provider should call Claude and parse its JSON response."""
    provider = AnthropicProvider(api_key="sk-ant-test")

    class _Block:
        type = "text"
        text = '{"confidence": 0.8, "evidence": "ok", "risks": "low", ' \
               '"suggested_entry": 101, "suggested_sl": 95, "suggested_tp": 115, ' \
               '"horizon_days": 4, "tags": ["momentum"]}'

    class _Resp:
        content = [_Block()]
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 20})()

    async def _fake_create(**kwargs):
        return _Resp()

    monkeypatch.setattr(provider.client.messages, "create", _fake_create)

    result = await provider.generate_trade_analysis(
        signal={"symbol": "RELIANCE", "entry_price": 100},
        market_data={"rsi": 55},
    )
    assert result["confidence"] == 0.8
    assert result["model_version"] == "claude-opus-4-8"
    assert result["usage"]["output_tokens"] == 20
