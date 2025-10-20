"""Production tests for feature engineering and signal generation."""
import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal, MarketDataCache, Feature, Signal
from backend.app.services.feature_builder import FeatureBuilder
from backend.app.services.signal_generator import SignalGenerator


@pytest.fixture
def db():
    """Database session fixture."""
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_market_data(db):
    """Create sample market data."""
    symbol = "TESTSTOCK"
    base_date = datetime.utcnow() - timedelta(days=60)
    
    # Generate 60 days of sample data
    candles = []
    price = 1000.0
    
    for i in range(60):
        # Simulate price movement
        price += (i % 5 - 2) * 10  # Oscillating price
        
        candle = MarketDataCache(
            symbol=symbol,
            exchange="NSE",
            interval="1D",
            timestamp=base_date + timedelta(days=i),
            open=price - 5,
            high=price + 10,
            low=price - 10,
            close=price,
            volume=1000000 + (i % 10) * 100000
        )
        candles.append(candle)
        db.add(candle)
    
    db.commit()
    
    yield symbol
    
    # Cleanup
    db.query(MarketDataCache).filter(MarketDataCache.symbol == symbol).delete()
    db.commit()


class TestFeatureBuilder:
    """Test feature engineering."""
    
    @pytest.mark.asyncio
    async def test_build_features(self, db, sample_market_data):
        """Test building features from market data."""
        symbol = sample_market_data
        builder = FeatureBuilder(db)
        
        feature = await builder.build_features(symbol, exchange="NSE")
        
        assert feature is not None
        assert feature.symbol == symbol
        assert feature.momentum_5d is not None
        assert feature.momentum_10d is not None
        assert feature.momentum_20d is not None
        assert feature.atr_14d is not None
        assert feature.atr_percent is not None
        assert feature.rsi_14 is not None
        assert feature.regime_label in ["LOW_VOL", "MED_VOL", "HIGH_VOL"]
        assert feature.liquidity_regime in ["HIGH", "MEDIUM", "LOW"]
        
        # Cleanup
        db.delete(feature)
        db.commit()
    
    @pytest.mark.asyncio
    async def test_build_features_insufficient_data(self, db):
        """Test handling of insufficient data."""
        builder = FeatureBuilder(db)
        
        # Symbol with no data
        feature = await builder.build_features("NONEXISTENT", exchange="NSE")
        
        assert feature is None


class TestSignalGenerator:
    """Test signal generation."""
    
    @pytest.mark.asyncio
    async def test_generate_from_features(self, db, sample_market_data):
        """Test generating signals from features."""
        symbol = sample_market_data
        
        # First build features
        builder = FeatureBuilder(db)
        feature = await builder.build_features(symbol)
        
        # Generate signals
        generator = SignalGenerator(db)
        signals = await generator.generate_from_features([symbol])
        
        assert isinstance(signals, list)
        # May or may not generate signal depending on conditions
        
        # Cleanup
        db.query(Feature).filter(Feature.symbol == symbol).delete()
        db.query(Signal).filter(Signal.symbol == symbol).delete()
        db.commit()
    
    @pytest.mark.asyncio
    async def test_apply_meta_label(self, db):
        """Test meta-labeling."""
        # Create a test signal
        signal = Signal(
            symbol="TESTSTOCK",
            exchange="NSE",
            direction="LONG",
            edge=3.0,
            confidence=0.6,
            horizon_days=5,
            quality_score=0.5,
            regime_compatible=True,
            status="ACTIVE"
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        
        # Apply meta-label
        generator = SignalGenerator(db)
        meta_label = await generator.apply_meta_label(signal.id)
        
        assert meta_label is not None
        assert meta_label.signal_id == signal.id
        assert meta_label.quality_score is not None
        assert 0 <= meta_label.quality_score <= 1.0
        assert meta_label.is_trustworthy is not None
        
        # Cleanup
        db.delete(meta_label)
        db.delete(signal)
        db.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

