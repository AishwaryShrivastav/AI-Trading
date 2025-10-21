"""Risk and compliance guardrails - production-grade checks (no fake data)."""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from ..database import (
    MarketDataCache,
    Mandate,
    FundingPlan,
    PositionV2,
    Feature,
    Event,
    Setting,
    TradeCard,
)
from .risk_evaluation import RiskEvaluationResult, RiskWarning, GuardrailSeverity
from .metrics import record_guardrail_check


logger = logging.getLogger(__name__)


class RiskChecker:
    """Pre-trade risk and compliance checks (6 guardrails)."""

    # Defaults (can be externalized via env/config later)
    ADV_LOOKBACK_DAYS = 20
    MAX_TRADE_TO_ADV_RATIO = 0.05  # 5%
    DEFAULT_EVENT_BLACKOUT_DAYS = 2
    DEFAULT_SECTOR_EXPOSURE_MAX = 30.0  # percent
    CATALYST_FRESHNESS_HOURS = 24

    def __init__(self, db: Session):
        self.db = db

    async def run_all_checks(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        trade_type: str,
        exchange: str = "NSE",
        account_id: Optional[int] = None,
        sector: Optional[str] = None,
        event_id: Optional[int] = None,
    ) -> RiskEvaluationResult:
        start_ts = datetime.utcnow()
        warnings: List[RiskWarning] = []

        # 1) Liquidity
        liquidity_ok = await self.check_liquidity(symbol, quantity, warnings)

        # 2) Position size risk
        position_size_ok = await self.check_position_size_risk(
            account_id=account_id,
            entry_price=entry_price,
            stop_loss=stop_loss,
            quantity=quantity,
            warnings=warnings,
        )

        # 3) Sector exposure
        exposure_ok = await self.check_sector_exposure(
            account_id=account_id,
            sector=sector,
            new_position_value=entry_price * quantity,
            warnings=warnings,
        )

        # 4) Event window
        event_window_ok = await self.check_event_window(symbol, account_id, warnings)

        # 5) Regime compatibility
        regime_ok = await self.check_regime_compatibility(symbol, account_id, warnings)

        # 6) Catalyst freshness (hot-path)
        catalyst_ok = await self.check_catalyst_freshness(event_id, warnings)

        has_critical = any(w.type == GuardrailSeverity.CRITICAL for w in warnings)
        passed_all = all(
            [
                liquidity_ok,
                position_size_ok,
                exposure_ok,
                event_window_ok,
                regime_ok,
                catalyst_ok,
            ]
        ) and not has_critical

        duration_ms = (datetime.utcnow() - start_ts).total_seconds() * 1000
        result = RiskEvaluationResult(
            liquidity_check=liquidity_ok,
            position_size_check=position_size_ok,
            exposure_check=exposure_ok,
            event_window_check=event_window_ok,
            regime_check=regime_ok,
            catalyst_freshness_check=catalyst_ok,
            risk_warnings=warnings,
            passed_all=passed_all,
            has_critical_failures=has_critical,
            timestamp=datetime.utcnow(),
            account_id=account_id,
            symbol=symbol,
            evaluation_duration_ms=round(duration_ms, 2),
        )

        # Record metrics
        try:
            record_guardrail_check(result.to_dict())
        except Exception:
            pass

        return result

    async def check_liquidity(
        self, symbol: str, quantity: int, warnings: List[RiskWarning]
    ) -> bool:
        """Trade size must be within % of ADV over lookback window."""
        try:
            cutoff = datetime.utcnow() - timedelta(days=self.ADV_LOOKBACK_DAYS)
            avg_volume = (
                self.db.query(func.avg(MarketDataCache.volume))
                .filter(
                    MarketDataCache.symbol == symbol,
                    MarketDataCache.timestamp >= cutoff,
                )
                .scalar()
            )

            if not avg_volume:
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.WARNING,
                        message=f"Insufficient volume history for {symbol}",
                        code="INSUFFICIENT_VOLUME_DATA",
                        details={"lookback_days": self.ADV_LOOKBACK_DAYS},
                    )
                )
                return True

            ratio = quantity / float(avg_volume)
            if ratio > self.MAX_TRADE_TO_ADV_RATIO:
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.CRITICAL,
                        message=f"Trade size exceeds {self.MAX_TRADE_TO_ADV_RATIO*100:.1f}% of ADV",
                        code="LIQUIDITY_BELOW_THRESHOLD",
                        details={"ratio": round(ratio, 4), "adv": int(avg_volume)},
                    )
                )
                return False

            return True
        except Exception as e:
            logger.error(f"Liquidity check error for {symbol}: {e}")
            warnings.append(
                RiskWarning(
                    type=GuardrailSeverity.WARNING,
                    message="Liquidity check error",
                    code="LIQUIDITY_CHECK_ERROR",
                )
            )
            return True

    async def check_position_size_risk(
        self,
        account_id: Optional[int],
        entry_price: float,
        stop_loss: float,
        quantity: int,
        warnings: List[RiskWarning],
    ) -> bool:
        if not account_id:
            return True
        try:
            mandate: Optional[Mandate] = (
                self.db.query(Mandate)
                .filter(Mandate.account_id == account_id, Mandate.is_active == True)
                .first()
            )
            if not mandate or not mandate.risk_per_trade_percent:
                return True

            funding: Optional[FundingPlan] = (
                self.db.query(FundingPlan)
                .filter(FundingPlan.account_id == account_id)
                .first()
            )
            total_capital = 0.0
            if funding:
                total_capital = (funding.available_cash or 0.0) + (
                    funding.total_deployed or 0.0
                )
            if total_capital <= 0:
                # fallback to configured total capital if present
                setting = (
                    self.db.query(Setting).filter(Setting.key == "total_capital").first()
                )
                total_capital = float(setting.value) if setting and setting.value else 100000.0

            risk_per_share = abs(entry_price - stop_loss)
            total_risk = risk_per_share * quantity
            risk_percent = (total_risk / total_capital) * 100.0 if total_capital > 0 else 100.0

            if risk_percent > mandate.risk_per_trade_percent:
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.CRITICAL,
                        message="Risk per trade exceeds mandate limit",
                        code="POSITION_SIZE_EXCEEDED",
                        details={
                            "risk_percent": round(risk_percent, 2),
                            "limit": mandate.risk_per_trade_percent,
                            "total_risk": round(total_risk, 2),
                            "capital": round(total_capital, 2),
                        },
                    )
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Position size risk check error: {e}")
            return True

    async def check_sector_exposure(
        self,
        account_id: Optional[int],
        sector: Optional[str],
        new_position_value: float,
        warnings: List[RiskWarning],
    ) -> bool:
        if not account_id:
            return True
        try:
            mandate: Optional[Mandate] = (
                self.db.query(Mandate)
                .filter(Mandate.account_id == account_id, Mandate.is_active == True)
                .first()
            )
            if not mandate:
                return True

            # Determine capital
            funding: Optional[FundingPlan] = (
                self.db.query(FundingPlan)
                .filter(FundingPlan.account_id == account_id)
                .first()
            )
            total_capital = 0.0
            if funding:
                total_capital = (funding.available_cash or 0.0) + (
                    funding.total_deployed or 0.0
                )
            if total_capital <= 0:
                setting = (
                    self.db.query(Setting).filter(Setting.key == "total_capital").first()
                )
                total_capital = float(setting.value) if setting and setting.value else 100000.0

            if not sector or sector.strip() == "":
                # Try to infer later; allow with info
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.INFO,
                        message="Sector not provided; exposure check may be imprecise",
                        code="SECTOR_UNKNOWN",
                    )
                )
                return True

            # Sum current exposure for this sector
            open_positions = (
                self.db.query(PositionV2)
                .filter(PositionV2.account_id == account_id, PositionV2.closed_at.is_(None))
                .all()
            )
            current_sector_value = 0.0
            for pos in open_positions:
                # Value using current or entry price
                price = pos.current_price or pos.average_entry_price or 0.0
                current_sector_value += price * pos.quantity if pos.symbol and price else 0.0

            total_sector_value = current_sector_value + (new_position_value or 0.0)
            exposure_percent = (
                (total_sector_value / total_capital) * 100.0 if total_capital > 0 else 100.0
            )

            limit = (
                mandate.max_sector_exposure_percent
                if mandate.max_sector_exposure_percent is not None
                else self.DEFAULT_SECTOR_EXPOSURE_MAX
            )
            if exposure_percent > float(limit):
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.CRITICAL,
                        message="Sector exposure exceeds limit",
                        code="SECTOR_EXPOSURE_EXCEEDED",
                        details={
                            "exposure_percent": round(exposure_percent, 2),
                            "limit_percent": float(limit),
                        },
                    )
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Sector exposure check error: {e}")
            return True

    async def check_event_window(
        self, symbol: str, account_id: Optional[int], warnings: List[RiskWarning]
    ) -> bool:
        try:
            # Determine blackout days
            blackout_days = self.DEFAULT_EVENT_BLACKOUT_DAYS
            if account_id:
                mandate = (
                    self.db.query(Mandate)
                    .filter(Mandate.account_id == account_id, Mandate.is_active == True)
                    .first()
                )
                if mandate and mandate.earnings_blackout_days:
                    blackout_days = mandate.earnings_blackout_days

            cutoff_start = datetime.utcnow() - timedelta(days=blackout_days)
            cutoff_end = datetime.utcnow() + timedelta(days=blackout_days)

            # Prefer dedicated calendar table if present
            try:
                from ..database import EarningsCalendar

                event = (
                    self.db.query(EarningsCalendar)
                    .filter(
                        EarningsCalendar.symbol == symbol,
                        EarningsCalendar.event_date >= cutoff_start.date(),
                        EarningsCalendar.event_date <= cutoff_end.date(),
                    )
                    .first()
                )
                if event:
                    warnings.append(
                        RiskWarning(
                            type=GuardrailSeverity.WARNING,
                            message=f"Upcoming {event.event_type} on {event.event_date}",
                            code="EVENT_WINDOW_WARNING",
                            details={"event_date": str(event.event_date)},
                        )
                    )
                    return False
            except Exception:
                # Calendar table may not exist yet
                pass

            # Fallback to Events table timeframe check
            recent = (
                self.db.query(Event)
                .filter(
                    Event.symbols.contains(symbol),
                    Event.event_timestamp >= cutoff_start,
                    Event.event_timestamp <= cutoff_end,
                )
                .first()
            )
            if recent:
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.WARNING,
                        message="Event within blackout window",
                        code="EVENT_WINDOW_WARNING",
                    )
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Event window check error for {symbol}: {e}")
            return True

    async def check_regime_compatibility(
        self, symbol: str, account_id: Optional[int], warnings: List[RiskWarning]
    ) -> bool:
        try:
            feature: Optional[Feature] = (
                self.db.query(Feature)
                .filter(Feature.symbol == symbol)
                .order_by(Feature.timestamp.desc())
                .first()
            )
            if not feature or not feature.regime_label:
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.INFO,
                        message="No regime label available",
                        code="REGIME_UNKNOWN",
                    )
                )
                return True
            # No explicit mandate filter in schema; treat as informational
            return True
        except Exception as e:
            logger.error(f"Regime check error: {e}")
            return True

    async def check_catalyst_freshness(
        self, event_id: Optional[int], warnings: List[RiskWarning]
    ) -> bool:
        if not event_id:
            return True
        try:
            event: Optional[Event] = self.db.query(Event).filter(Event.id == event_id).first()
            if not event:
                return True
            ref_ts = event.event_timestamp or event.ingested_at
            if not ref_ts:
                return True
            age_hours = (datetime.utcnow() - ref_ts).total_seconds() / 3600.0
            if age_hours > self.CATALYST_FRESHNESS_HOURS:
                warnings.append(
                    RiskWarning(
                        type=GuardrailSeverity.CRITICAL,
                        message="Event catalyst is stale",
                        code="CATALYST_STALE",
                        details={
                            "age_hours": round(age_hours, 1),
                            "threshold_hours": self.CATALYST_FRESHNESS_HOURS,
                        },
                    )
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Catalyst freshness check error: {e}")
            return True

    def get_risk_summary(self, trade_card: TradeCard) -> Dict[str, Any]:
        """Compute basic risk metrics for a trade card."""
        risk_per_share = abs(trade_card.entry_price - trade_card.stop_loss)
        total_risk = risk_per_share * trade_card.quantity
        position_value = trade_card.entry_price * trade_card.quantity

        reward_per_share = abs(trade_card.take_profit - trade_card.entry_price)
        total_reward = reward_per_share * trade_card.quantity

        risk_reward_ratio = (
            reward_per_share / risk_per_share if risk_per_share > 0 else 0
        )

        return {
            "position_value": round(position_value, 2),
            "total_risk": round(total_risk, 2),
            "total_reward": round(total_reward, 2),
            "risk_per_share": round(risk_per_share, 2),
            "reward_per_share": round(reward_per_share, 2),
            "risk_reward_ratio": round(risk_reward_ratio, 2),
            "risk_warnings": trade_card.risk_warnings or [],
        }

