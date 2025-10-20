"""OpenAI LLM provider implementation."""
import json
import logging
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from .base import LLMBase

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMBase):
    """OpenAI GPT-4 provider for trade analysis."""
    
    TRADE_ANALYSIS_PROMPT = """You are an expert quantitative analyst specializing in Indian equities swing trading.

Analyze the following trade signal and provide a comprehensive assessment:

**Signal Details:**
{signal}

**Market Data:**
{market_data}

**Additional Context:**
{context}

Provide your analysis in the following JSON format:
{{
    "confidence": <float between 0.0 and 1.0>,
    "evidence": "<detailed reasoning for the trade setup, key technical/fundamental factors>",
    "risks": "<identified risks including market risks, company-specific risks, event risks>",
    "suggested_entry": <optimal entry price>,
    "suggested_sl": <stop loss price>,
    "suggested_tp": <take profit price>,
    "horizon_days": <expected holding period in days, 1-7>,
    "tags": ["<tag1>", "<tag2>", ...]
}}

Consider:
1. Technical setup quality and confirmation
2. Risk/reward ratio (minimum 1:2 preferred)
3. Liquidity and volume patterns
4. Upcoming events (earnings, corporate actions)
5. Market and sector sentiment
6. Support/resistance levels
7. Trend alignment across timeframes

Be conservative and honest about limitations and uncertainties."""
    
    RANKING_PROMPT = """You are an expert portfolio manager selecting the best swing trade opportunities.

Review the following trade candidates and rank them by expected risk-adjusted return:

**Candidates:**
{candidates}

Select the top {max_selections} trades and return them in ranked order (best first) as a JSON array.

For each selected trade, include:
- The original signal data
- Your confidence score (0.0 to 1.0)
- Brief justification for the ranking

Consider:
1. Risk/reward ratio
2. Setup quality and conviction
3. Diversification (avoid over-concentration in single sector)
4. Market environment alignment
5. Probability of success

Return JSON array:
[
    {{
        "rank": 1,
        "signal": <original signal object>,
        "confidence": <float>,
        "justification": "<brief reason>"
    }},
    ...
]
"""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview"):
        super().__init__(api_key, model)
        self.client = AsyncOpenAI(api_key=api_key)
    
    async def generate_trade_analysis(
        self,
        signal: Dict[str, Any],
        market_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive trade analysis using GPT-4."""
        try:
            # Format the prompt
            prompt = self.TRADE_ANALYSIS_PROMPT.format(
                signal=json.dumps(signal, indent=2),
                market_data=json.dumps(market_data, indent=2),
                context=json.dumps(context or {}, indent=2)
            )
            
            # Call OpenAI API with JSON mode
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a quantitative trading analyst. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=2000
            )
            
            # Parse JSON response
            content = response.choices[0].message.content
            analysis = json.loads(content)
            
            # Add metadata
            analysis["model_version"] = self.model
            analysis["timestamp"] = response.created
            
            logger.info(f"Generated trade analysis for {signal.get('symbol', 'unknown')}")
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to generate trade analysis: {e}")
            # Return conservative default analysis on error
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
                "error": str(e)
            }
    
    async def rank_signals(
        self,
        signals: List[Dict[str, Any]],
        max_selections: int = 5
    ) -> List[Dict[str, Any]]:
        """Rank multiple signals and select top opportunities."""
        try:
            if not signals:
                return []
            
            # If we have fewer signals than max, just return all
            if len(signals) <= max_selections:
                return [
                    {
                        "rank": i + 1,
                        "signal": sig,
                        "confidence": sig.get("confidence", 0.5),
                        "justification": "Auto-selected (below max threshold)"
                    }
                    for i, sig in enumerate(signals)
                ]
            
            # Format the prompt
            prompt = self.RANKING_PROMPT.format(
                candidates=json.dumps(signals, indent=2),
                max_selections=max_selections
            )
            
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a portfolio manager. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=3000
            )
            
            # Parse response
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Extract ranked signals (handle different response formats)
            ranked = result.get("ranked_signals", result.get("signals", []))
            
            logger.info(f"Ranked {len(signals)} signals, selected top {len(ranked)}")
            return ranked[:max_selections]
            
        except Exception as e:
            logger.error(f"Failed to rank signals: {e}")
            # Fall back to simple confidence-based ranking
            sorted_signals = sorted(
                signals, 
                key=lambda x: x.get("confidence", 0.5),
                reverse=True
            )
            return [
                {
                    "rank": i + 1,
                    "signal": sig,
                    "confidence": sig.get("confidence", 0.5),
                    "justification": "Fallback ranking by confidence score"
                }
                for i, sig in enumerate(sorted_signals[:max_selections])
            ]

