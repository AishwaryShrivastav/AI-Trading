"""Feature Builder - Technical and derivative features for signals."""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from ..database import MarketDataCache, Feature

logger = logging.getLogger(__name__)


class FeatureBuilder:
    """
    Builds technical and derivative features for signal generation.
    
    Features computed:
    - Momentum (5d, 10d, 20d)
    - Volatility (ATR%, ATR_14d)
    - Oscillators (RSI_14)
    - Gaps
    - Derivatives (IV rank, PCR, OI changes)
    - Regime labels
    - Flow data
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def build_features(
        self,
        symbol: str,
        exchange: str = "NSE",
        lookback_days: int = 60
    ) -> Optional[Feature]:
        """
        Build complete feature set for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
            lookback_days: Days of historical data to use
            
        Returns:
            Feature object or None if insufficient data
        """
        try:
            # Get historical data
            candles = self.db.query(MarketDataCache).filter(
                MarketDataCache.symbol == symbol,
                MarketDataCache.exchange == exchange,
                MarketDataCache.interval == "1D"
            ).order_by(MarketDataCache.timestamp.desc()).limit(lookback_days).all()
            
            if len(candles) < 20:
                logger.warning(f"Insufficient data for {symbol}: {len(candles)} candles")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume
                }
                for c in reversed(candles)  # Oldest to newest
            ])
            
            # Compute features
            features_dict = {}
            
            # Momentum
            features_dict["momentum_5d"] = self._calculate_momentum(df, 5)
            features_dict["momentum_10d"] = self._calculate_momentum(df, 10)
            features_dict["momentum_20d"] = self._calculate_momentum(df, 20)
            
            # Volatility
            atr_14 = self._calculate_atr(df, 14)
            features_dict["atr_14d"] = atr_14
            features_dict["atr_percent"] = (atr_14 / df["close"].iloc[-1]) * 100 if df["close"].iloc[-1] > 0 else 0
            
            # RSI
            features_dict["rsi_14"] = self._calculate_rsi(df, 14)
            
            # Gap
            if len(df) >= 2:
                prev_close = df["close"].iloc[-2]
                curr_open = df["open"].iloc[-1]
                features_dict["gap_percent"] = ((curr_open - prev_close) / prev_close) * 100 if prev_close > 0 else 0
                # Check if gap filled
                if features_dict["gap_percent"] > 0:
                    features_dict["gap_filled"] = df["low"].iloc[-1] <= prev_close
                elif features_dict["gap_percent"] < 0:
                    features_dict["gap_filled"] = df["high"].iloc[-1] >= prev_close
                else:
                    features_dict["gap_filled"] = True
            else:
                features_dict["gap_percent"] = 0
                features_dict["gap_filled"] = True
            
            # Regime classification
            features_dict["regime_label"] = self._classify_regime(features_dict["atr_percent"])
            features_dict["liquidity_regime"] = self._classify_liquidity(df)
            
            # Derivatives features (optional - enhance with NSE Option Chain API)
            # Production: Integrate with NSE derivatives API for:
            # - IV Rank, PCR, OI changes, Futures basis
            # Currently these are optional and set to None
            features_dict["iv_rank"] = None
            features_dict["pcr"] = None
            features_dict["pcr_delta"] = None
            features_dict["oi_change_percent"] = None
            features_dict["futures_basis"] = None
            
            # Flow features (optional - enhance with FPI/DII data sources)
            # Production: Integrate with NSE/BSE flow data or third-party providers
            # Currently these are optional and set to None
            features_dict["fpi_flow_5d"] = None
            features_dict["dii_flow_5d"] = None
            
            # Create or update feature
            feature = Feature(
                symbol=symbol,
                exchange=exchange,
                timestamp=datetime.utcnow(),
                data_source="MARKET_DATA",
                **features_dict
            )
            
            self.db.add(feature)
            self.db.commit()
            self.db.refresh(feature)
            
            logger.info(f"Built features for {symbol}")
            return feature
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error building features for {symbol}: {e}")
            return None
    
    async def build_features_batch(
        self,
        symbols: List[str],
        exchange: str = "NSE"
    ) -> List[Feature]:
        """Build features for multiple symbols."""
        features = []
        
        for symbol in symbols:
            feature = await self.build_features(symbol, exchange)
            if feature:
                features.append(feature)
        
        return features
    
    def _calculate_momentum(self, df: pd.DataFrame, period: int) -> float:
        """Calculate momentum as % change over period."""
        if len(df) < period + 1:
            return 0.0
        
        current_price = df["close"].iloc[-1]
        past_price = df["close"].iloc[-(period + 1)]
        
        if past_price > 0:
            return ((current_price - past_price) / past_price) * 100
        return 0.0
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range."""
        if len(df) < period + 1:
            return 0.0
        
        df = df.copy()
        df["tr"] = df.apply(
            lambda row: max(
                row["high"] - row["low"],
                abs(row["high"] - df["close"].shift(1).loc[row.name]) if pd.notna(df["close"].shift(1).loc[row.name]) else row["high"] - row["low"],
                abs(row["low"] - df["close"].shift(1).loc[row.name]) if pd.notna(df["close"].shift(1).loc[row.name]) else row["high"] - row["low"]
            ),
            axis=1
        )
        
        atr = df["tr"].rolling(window=period).mean().iloc[-1]
        return float(atr) if pd.notna(atr) else 0.0
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(df) < period + 1:
            return 50.0  # Neutral
        
        df = df.copy()
        df["change"] = df["close"].diff()
        
        gains = df["change"].clip(lower=0)
        losses = -df["change"].clip(upper=0)
        
        avg_gain = gains.rolling(window=period).mean().iloc[-1]
        avg_loss = losses.rolling(window=period).mean().iloc[-1]
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi) if pd.notna(rsi) else 50.0
    
    def _classify_regime(self, atr_percent: float) -> str:
        """Classify volatility regime."""
        if atr_percent > 3.0:
            return "HIGH_VOL"
        elif atr_percent > 1.5:
            return "MED_VOL"
        else:
            return "LOW_VOL"
    
    def _classify_liquidity(self, df: pd.DataFrame) -> str:
        """Classify liquidity regime based on volume."""
        if len(df) < 20:
            return "MEDIUM"
        
        avg_volume = df["volume"].rolling(window=20).mean().iloc[-1]
        recent_volume = df["volume"].iloc[-5:].mean()
        
        ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        if ratio > 1.5:
            return "HIGH"
        elif ratio > 0.8:
            return "MEDIUM"
        else:
            return "LOW"

