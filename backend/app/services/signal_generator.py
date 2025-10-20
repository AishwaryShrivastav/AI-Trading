"""Signal Generator - Creates trading signals from features and events."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from ..database import Signal, MetaLabel, Feature, Event
from ..schemas import Direction

logger = logging.getLogger(__name__)


class SignalGenerator:
    """
    Generates trading signals from features and events.
    
    Creates:
    - Primary signals with edge estimation
    - Triple barrier probabilities (TP/SL hit probabilities)
    - Quality scores via meta-labeling
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def generate_from_features(
        self,
        symbols: List[str],
        lookback_hours: int = 24
    ) -> List[Signal]:
        """
        Generate signals from technical features.
        
        Args:
            symbols: Symbols to generate signals for
            lookback_hours: Only use recent features
            
        Returns:
            List of generated signals
        """
        signals = []
        cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
        
        for symbol in symbols:
            # Get latest features
            feature = self.db.query(Feature).filter(
                Feature.symbol == symbol,
                Feature.timestamp >= cutoff_time
            ).order_by(Feature.timestamp.desc()).first()
            
            if not feature:
                continue
            
            # Generate signal based on features
            signal_data = self._evaluate_features(feature)
            
            if signal_data:
                signal = Signal(
                    symbol=symbol,
                    exchange="NSE",
                    direction=signal_data["direction"],
                    edge=signal_data["edge"],
                    confidence=signal_data["confidence"],
                    horizon_days=signal_data["horizon_days"],
                    tp_probability=signal_data.get("tp_probability", 0.6),
                    sl_probability=signal_data.get("sl_probability", 0.4),
                    quality_score=0.5,  # Will be updated by meta-labeler
                    regime_compatible=True,
                    thesis_bullets=signal_data.get("thesis_bullets", []),
                    model_version="rule_based_v1",
                    generated_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(hours=4),
                    status="ACTIVE"
                )
                
                self.db.add(signal)
                signals.append(signal)
        
        if signals:
            self.db.commit()
            logger.info(f"Generated {len(signals)} signals from features")
        
        return signals
    
    async def generate_from_event(
        self,
        event_id: int
    ) -> Optional[Signal]:
        """
        Generate signal from a specific event.
        
        Args:
            event_id: Event to process
            
        Returns:
            Signal or None
        """
        event = self.db.query(Event).filter(Event.id == event_id).first()
        
        if not event or not event.symbols:
            return None
        
        symbol = event.symbols[0] if isinstance(event.symbols, list) else event.symbols
        
        # Get features for context
        feature = self.db.query(Feature).filter(
            Feature.symbol == symbol
        ).order_by(Feature.timestamp.desc()).first()
        
        # Evaluate event
        signal_data = self._evaluate_event(event, feature)
        
        if not signal_data:
            return None
        
        signal = Signal(
            symbol=symbol,
            exchange="NSE",
            direction=signal_data["direction"],
            edge=signal_data["edge"],
            confidence=signal_data["confidence"],
            horizon_days=signal_data["horizon_days"],
            tp_probability=signal_data.get("tp_probability", 0.65),
            sl_probability=signal_data.get("sl_probability", 0.35),
            quality_score=0.7,  # Events typically higher quality
            regime_compatible=True,
            thesis_bullets=signal_data.get("thesis_bullets", []),
            model_version="event_driven_v1",
            event_id=event_id,
            generated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=2),  # Shorter expiry for events
            status="ACTIVE"
        )
        
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        
        logger.info(f"Generated event signal for {symbol} from event {event_id}")
        return signal
    
    def _evaluate_features(self, feature: Feature) -> Optional[Dict[str, Any]]:
        """Evaluate features to generate signal."""
        # Simple rule-based logic
        
        # Momentum signal
        if feature.momentum_5d and feature.momentum_10d:
            if feature.momentum_5d > 3 and feature.momentum_10d > 2:
                # Strong upward momentum
                if feature.rsi_14 and feature.rsi_14 < 70:  # Not overbought
                    return {
                        "direction": "LONG",
                        "edge": min(feature.momentum_5d, 5.0),
                        "confidence": 0.6,
                        "horizon_days": 5,
                        "thesis_bullets": [
                            f"5-day momentum: {feature.momentum_5d:.1f}%",
                            f"10-day momentum: {feature.momentum_10d:.1f}%",
                            f"RSI: {feature.rsi_14:.1f} (healthy)"
                        ]
                    }
            
            elif feature.momentum_5d < -3 and feature.momentum_10d < -2:
                # Strong downward momentum (SHORT opportunity)
                if feature.rsi_14 and feature.rsi_14 > 30:  # Not oversold
                    return {
                        "direction": "SHORT",
                        "edge": min(abs(feature.momentum_5d), 5.0),
                        "confidence": 0.6,
                        "horizon_days": 5,
                        "thesis_bullets": [
                            f"5-day momentum: {feature.momentum_5d:.1f}%",
                            f"10-day momentum: {feature.momentum_10d:.1f}%",
                            f"RSI: {feature.rsi_14:.1f} (healthy)"
                        ]
                    }
        
        # Mean reversion signal
        if feature.rsi_14:
            if feature.rsi_14 < 30 and feature.momentum_5d and feature.momentum_5d > -1:
                # Oversold with signs of reversal
                return {
                    "direction": "LONG",
                    "edge": 3.0,
                    "confidence": 0.55,
                    "horizon_days": 3,
                    "thesis_bullets": [
                        f"RSI oversold: {feature.rsi_14:.1f}",
                        "Potential mean reversion setup"
                    ]
                }
        
        return None
    
    def _evaluate_event(
        self,
        event: Event,
        feature: Optional[Feature]
    ) -> Optional[Dict[str, Any]]:
        """Evaluate event to generate signal."""
        # Event-driven logic
        
        if event.event_type == "BUYBACK":
            return {
                "direction": "LONG",
                "edge": 5.0,
                "confidence": 0.7,
                "horizon_days": 3,
                "tp_probability": 0.7,
                "sl_probability": 0.3,
                "thesis_bullets": [
                    "Buyback announcement (typically bullish)",
                    "Management shows confidence in stock",
                    "Price support expected"
                ]
            }
        
        elif event.event_type == "EARNINGS" and feature:
            # Earnings momentum continuation
            if feature.momentum_5d and feature.momentum_5d > 2:
                return {
                    "direction": "LONG",
                    "edge": 4.0,
                    "confidence": 0.65,
                    "horizon_days": 2,
                    "thesis_bullets": [
                        "Earnings announcement",
                        f"Strong pre-earnings momentum: {feature.momentum_5d:.1f}%",
                        "Potential beat and continuation"
                    ]
                }
        
        return None
    
    async def apply_meta_label(
        self,
        signal_id: int
    ) -> MetaLabel:
        """
        Apply meta-labeling to assess signal quality.
        
        Args:
            signal_id: Signal to meta-label
            
        Returns:
            MetaLabel object
        """
        signal = self.db.query(Signal).filter(Signal.id == signal_id).first()
        
        if not signal:
            raise ValueError(f"Signal {signal_id} not found")
        
        # Get features
        feature = self.db.query(Feature).filter(
            Feature.symbol == signal.symbol
        ).order_by(Feature.timestamp.desc()).first()
        
        # Simple meta-labeling logic
        # In production, this would be an ML model
        
        regime_score = 0.7 if feature and feature.regime_label == "MED_VOL" else 0.5
        liquidity_score = 0.8 if feature and feature.liquidity_regime == "HIGH" else 0.6
        timing_score = 0.7  # Would check if entry timing is good
        crowding_score = 0.6  # Would check if trade is crowded
        
        quality_score = (regime_score + liquidity_score + timing_score + crowding_score) / 4
        is_trustworthy = quality_score > 0.6
        
        meta_label = MetaLabel(
            signal_id=signal_id,
            is_trustworthy=is_trustworthy,
            quality_score=quality_score,
            regime_score=regime_score,
            liquidity_score=liquidity_score,
            crowding_score=crowding_score,
            timing_score=timing_score,
            rationale=f"Quality: {quality_score:.2f}. Regime: {regime_score:.2f}, Liquidity: {liquidity_score:.2f}",
            model_version="meta_label_v1",
            computed_at=datetime.utcnow()
        )
        
        # Update signal
        signal.quality_score = quality_score
        
        self.db.add(meta_label)
        self.db.commit()
        self.db.refresh(meta_label)
        
        logger.info(f"Applied meta-label to signal {signal_id}: quality={quality_score:.2f}")
        return meta_label

