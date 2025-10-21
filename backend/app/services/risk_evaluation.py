from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class GuardrailSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class RiskWarning:
    type: GuardrailSeverity
    message: str
    code: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "message": self.message,
            "code": self.code,
            "details": self.details or {},
        }


@dataclass
class RiskEvaluationResult:
    liquidity_check: bool
    position_size_check: bool
    exposure_check: bool
    event_window_check: bool
    regime_check: bool
    catalyst_freshness_check: bool

    risk_warnings: List[RiskWarning] = field(default_factory=list)
    passed_all: bool = True
    has_critical_failures: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    account_id: Optional[int] = None
    symbol: Optional[str] = None
    evaluation_duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "liquidity_check": self.liquidity_check,
            "position_size_check": self.position_size_check,
            "exposure_check": self.exposure_check,
            "event_window_check": self.event_window_check,
            "regime_check": self.regime_check,
            "catalyst_freshness_check": self.catalyst_freshness_check,
            "risk_warnings": [w.to_dict() for w in self.risk_warnings],
            "passed_all": self.passed_all,
            "has_critical_failures": self.has_critical_failures,
            "timestamp": self.timestamp.isoformat(),
            "account_id": self.account_id,
            "symbol": self.symbol,
            "evaluation_duration_ms": self.evaluation_duration_ms,
        }
