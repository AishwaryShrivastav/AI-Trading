"""Anthropic (Claude) LLM provider implementation.

Implements the same ``LLMBase`` contract as the OpenAI provider so it is a
drop-in replacement selected via ``LLM_PROVIDER=anthropic``. Per the
TradeHarness plan, Claude is the default orchestrator brain.

The ``anthropic`` package is imported lazily inside ``__init__`` so the rest of
the application (and the test suite) can import this module even when the SDK
or an API key is not present.
"""
import json
import logging
import re
from typing import Dict, List, Any, Optional

from .base import LLMBase

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON object/array from a Claude response.

    Claude has no enforced JSON mode, so the model may wrap JSON in prose or
    markdown code fences. We try direct parse first, then fenced blocks, then
    the first balanced ``{...}``/``[...]`` span.
    """
    if text is None:
        raise ValueError("empty response")
    text = text.strip()

    # 1) Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2) Fenced ```json ... ``` block
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    # 3) First balanced object/array span
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                continue

    raise ValueError("no JSON found in response")


class AnthropicProvider(LLMBase):
    """Claude provider for trade analysis and signal ranking."""

    # Prompts intentionally mirror the OpenAI provider so behaviour is
    # comparable across providers (see openai_provider.py).
    TRADE_ANALYSIS_PROMPT = """You are an expert quantitative analyst specializing in Indian equities swing trading.

Analyze the following trade signal and provide a comprehensive assessment.

**Signal Details:**
{signal}

**Market Data:**
{market_data}

**Additional Context:**
{context}

Respond with ONLY a single JSON object (no prose, no markdown) in this exact shape:
{{
    "confidence": <float between 0.0 and 1.0>,
    "evidence": "<detailed reasoning for the trade setup, key technical/fundamental factors>",
    "risks": "<identified risks including market risks, company-specific risks, event risks>",
    "suggested_entry": <optimal entry price>,
    "suggested_sl": <stop loss price>,
    "suggested_tp": <take profit price>,
    "horizon_days": <expected holding period in days, 1-7>,
    "tags": ["<tag1>", "<tag2>"]
}}

Consider: technical setup quality, risk/reward (min 1:2 preferred), liquidity/volume,
upcoming events (earnings, corporate actions), market/sector sentiment, support/resistance,
and trend alignment across timeframes. Be conservative and honest about uncertainty."""

    RANKING_PROMPT = """You are an expert portfolio manager selecting the best swing trade opportunities.

Review the following trade candidates and rank them by expected risk-adjusted return.

**Candidates:**
{candidates}

Select the top {max_selections} trades. Consider risk/reward, setup quality/conviction,
diversification (avoid single-sector over-concentration), market alignment, and probability
of success.

Respond with ONLY a JSON object (no prose, no markdown) in this exact shape:
{{
    "ranked_signals": [
        {{"rank": 1, "signal": <original signal object>, "confidence": <float>, "justification": "<brief reason>"}}
    ]
}}
"""

    ORCHESTRATOR_PROMPT = """You are the orchestrator brain of an Indian-equities trading system.
You weigh all available evidence and decide what to trade today. You are disciplined,
risk-aware, and honest about uncertainty — when evidence is weak you recommend SKIP.

**Today's decision context:**
{context}

Respond with ONLY a single JSON object (no prose, no markdown):
{{
    "market_thesis": "<2-3 sentence view of today's market>",
    "regime_assessment": "<trending-up | trending-down | ranging | high-volatility + why>",
    "trade_recommendations": [
        {{
            "instrument": "<symbol>",
            "direction": "LONG" | "SHORT",
            "conviction": <float 0.0-1.0>,
            "size_pct": <float, % of capital, <= 10>,
            "stop_loss": <price>,
            "reasoning": "<why this trade, referencing the signals/context>"
        }}
    ],
    "risk_flags": ["<any caution that should lower autonomy, e.g. earnings nearby, high VIX>"]
}}

Rules: only recommend instruments present in the candidate signals. Be conservative on
conviction. If the context is thin or conflicting, return an empty trade_recommendations list."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-8"):
        super().__init__(api_key, model)
        # Lazy import so the module is importable without the SDK installed.
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate_trade_analysis(
        self,
        signal: Dict[str, Any],
        market_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate comprehensive trade analysis using Claude."""
        try:
            prompt = self.TRADE_ANALYSIS_PROMPT.format(
                signal=json.dumps(signal, indent=2, default=str),
                market_data=json.dumps(market_data, indent=2, default=str),
                context=json.dumps(context or {}, indent=2, default=str),
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.3,
                system="You are a quantitative trading analyst. Always respond with a single valid JSON object and nothing else.",
                messages=[{"role": "user", "content": prompt}],
            )

            content = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            analysis = _extract_json(content)

            analysis["model_version"] = self.model
            usage = getattr(response, "usage", None)
            if usage is not None:
                analysis["usage"] = {
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                }

            logger.info(f"Generated trade analysis for {signal.get('symbol', 'unknown')} via {self.model}")
            return analysis

        except Exception as e:
            logger.error(f"Failed to generate trade analysis: {e}")
            return {
                "confidence": 0.3,
                "evidence": f"Error in LLM analysis: {str(e)}. Manual review required.",
                "risks": "Unable to perform automated analysis. High uncertainty.",
                "suggested_entry": signal.get("entry_price", 0),
                "suggested_sl": signal.get("suggested_sl", 0),
                "suggested_tp": signal.get("suggested_tp", 0),
                "horizon_days": 3,
                "tags": ["error", "manual_review_required"],
                "model_version": self.model,
                "error": str(e),
            }

    async def orchestrate_decisions(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Make today's trading decisions from the assembled context."""
        prompt = self.ORCHESTRATOR_PROMPT.format(
            context=json.dumps(context, indent=2, default=str)
        )
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=3000,
            temperature=0.2,
            system="You are a disciplined trading orchestrator. Always respond with a single valid JSON object and nothing else.",
            messages=[{"role": "user", "content": prompt}],
        )
        content = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        result = _extract_json(content)
        if not isinstance(result, dict):
            raise ValueError("orchestrator response was not a JSON object")

        usage = getattr(response, "usage", None)
        if usage is not None:
            result["_usage"] = {
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
            }
        result["_model"] = self.model
        return result

    async def rank_signals(
        self,
        signals: List[Dict[str, Any]],
        max_selections: int = 5,
    ) -> List[Dict[str, Any]]:
        """Rank multiple signals and select top opportunities using Claude."""
        try:
            if not signals:
                return []

            if len(signals) <= max_selections:
                return [
                    {
                        "rank": i + 1,
                        "signal": sig,
                        "confidence": sig.get("confidence", 0.5),
                        "justification": "Auto-selected (below max threshold)",
                    }
                    for i, sig in enumerate(signals)
                ]

            prompt = self.RANKING_PROMPT.format(
                candidates=json.dumps(signals, indent=2, default=str),
                max_selections=max_selections,
            )

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                temperature=0.2,
                system="You are a portfolio manager. Always respond with a single valid JSON object and nothing else.",
                messages=[{"role": "user", "content": prompt}],
            )

            content = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            result = _extract_json(content)

            ranked = result.get("ranked_signals", result.get("signals", [])) if isinstance(result, dict) else result

            logger.info(f"Ranked {len(signals)} signals, selected top {len(ranked)} via {self.model}")
            return ranked[:max_selections]

        except Exception as e:
            logger.error(f"Failed to rank signals: {e}")
            sorted_signals = sorted(signals, key=lambda x: x.get("confidence", 0.5), reverse=True)
            return [
                {
                    "rank": i + 1,
                    "signal": sig,
                    "confidence": sig.get("confidence", 0.5),
                    "justification": "Fallback ranking by confidence score",
                }
                for i, sig in enumerate(sorted_signals[:max_selections])
            ]
