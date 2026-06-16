"""Market regime classifier (TradeHarness Step 7).

Classifies the current market regime from India VIX + recent Nifty price action
and returns per-strategy weight multipliers so the orchestrator can down-weight
strategies that don't suit the current environment.

Regimes:
  TRENDING_UP   — VIX < 18, price above rising SMA
  TRENDING_DOWN — VIX < 18, price below falling SMA
  RANGING       — VIX 18–22, price oscillating in a band
  HIGH_VOL      — VIX ≥ 22 (circuit breakers already fire; extra caution here)
  UNKNOWN       — insufficient data (safe default: moderate weight on all)
"""
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..database import Feature, Setting

logger = logging.getLogger(__name__)

# Regimes
TRENDING_UP   = "TRENDING_UP"
TRENDING_DOWN = "TRENDING_DOWN"
RANGING       = "RANGING"
HIGH_VOL      = "HIGH_VOL"
UNKNOWN       = "UNKNOWN"

# Weight of each strategy per regime.  These are *multipliers* (0–1) applied on
# top of the LLM conviction score.  Strategies not listed default to 0.7.
_REGIME_WEIGHTS: Dict[str, Dict[str, float]] = {
    TRENDING_UP: {
        "momentum_breakout":  1.0,
        "fifty_two_week_high": 0.9,
        "rsi_divergence":     0.7,
        "bollinger_squeeze":  0.5,
        "nifty_etf_baseline": 0.9,
        "orchestrated":       0.9,
    },
    TRENDING_DOWN: {
        "momentum_breakout":  0.3,
        "fifty_two_week_high": 0.2,
        "rsi_divergence":     0.9,
        "bollinger_squeeze":  0.9,
        "nifty_etf_baseline": 0.4,
        "orchestrated":       0.7,
    },
    RANGING: {
        "momentum_breakout":  0.4,
        "fifty_two_week_high": 0.3,
        "rsi_divergence":     1.0,
        "bollinger_squeeze":  1.0,
        "nifty_etf_baseline": 0.6,
        "orchestrated":       0.7,
    },
    HIGH_VOL: {
        "momentum_breakout":  0.2,
        "fifty_two_week_high": 0.2,
        "rsi_divergence":     0.5,
        "bollinger_squeeze":  0.4,
        "nifty_etf_baseline": 0.3,
        "orchestrated":       0.5,
    },
    UNKNOWN: {
        "default": 0.7,
    },
}

_DEFAULT_WEIGHT = 0.7


class RegimeClassifier:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ public

    def classify(self) -> str:
        """Return the current regime string."""
        vix = self._get_vix()
        if vix is not None:
            if vix >= 22:
                return HIGH_VOL
            if vix >= 18:
                return RANGING

        trend = self._detect_trend()
        if trend == "UP":
            return TRENDING_UP
        if trend == "DOWN":
            return TRENDING_DOWN
        return UNKNOWN

    def get_strategy_weight(self, strategy: str, regime: Optional[str] = None) -> float:
        """Return the weight multiplier (0–1) for a strategy in the given regime."""
        regime = regime or self.classify()
        weights = _REGIME_WEIGHTS.get(regime, {})
        return weights.get(strategy, weights.get("default", _DEFAULT_WEIGHT))

    def get_all_weights(self, regime: Optional[str] = None) -> Dict[str, Any]:
        """Return the full weight map and regime for use in the orchestrator context."""
        regime = regime or self.classify()
        weights = _REGIME_WEIGHTS.get(regime, {"default": _DEFAULT_WEIGHT})
        return {
            "regime": regime,
            "strategy_weights": weights,
            "vix": self._get_vix(),
        }

    # ------------------------------------------------------------------ helpers

    def _get_vix(self) -> Optional[float]:
        row = self.db.query(Setting).filter(Setting.key == "india_vix").first()
        try:
            return float(row.value) if row and row.value is not None else None
        except (TypeError, ValueError):
            return None

    def _detect_trend(self) -> Optional[str]:
        """Heuristic: look at recent Nifty50 features for SMA trend.

        Returns 'UP', 'DOWN', or None if no signal data available.
        """
        nifty_syms = ["NIFTY50", "NIFTYBEES", "NIFTYBEES.NSE", "^NSEI"]
        for sym in nifty_syms:
            feature = (
                self.db.query(Feature)
                .filter(Feature.symbol == sym)
                .order_by(Feature.timestamp.desc())
                .first()
            )
            if feature and feature.features:
                feats = feature.features
                sma20 = feats.get("sma_20") or feats.get("sma20")
                sma50 = feats.get("sma_50") or feats.get("sma50")
                price = feats.get("close") or feats.get("price")
                if sma20 and sma50 and price:
                    if float(sma20) > float(sma50) and float(price) > float(sma20):
                        return "UP"
                    if float(sma20) < float(sma50) and float(price) < float(sma20):
                        return "DOWN"
        return None
