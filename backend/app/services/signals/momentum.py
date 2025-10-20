"""Momentum trading strategy using MA crossovers and RSI."""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
import logging
from .base import SignalBase

logger = logging.getLogger(__name__)

try:
    import ta
except ImportError:
    logger.warning("ta library not installed. Some indicators may not work.")
    ta = None


class MomentumStrategy(SignalBase):
    """
    Momentum strategy based on:
    - 20/50 day moving average crossover
    - RSI confirmation (not overbought/oversold)
    - Volume confirmation (above average)
    """
    
    def __init__(
        self,
        fast_ma: int = 20,
        slow_ma: int = 50,
        rsi_period: int = 14,
        rsi_overbought: float = 70,
        rsi_oversold: float = 30,
        volume_ma: int = 20,
        min_volume_ratio: float = 1.2
    ):
        super().__init__("momentum")
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.volume_ma = volume_ma
        self.min_volume_ratio = min_volume_ratio
    
    async def generate_signals(
        self,
        symbols: List[str],
        market_data: Dict[str, pd.DataFrame],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Generate momentum signals."""
        signals = []
        
        for symbol in symbols:
            try:
                df = market_data.get(symbol)
                if df is None or len(df) < self.slow_ma + 10:
                    logger.warning(f"Insufficient data for {symbol}")
                    continue
                
                # Calculate indicators
                df = self._calculate_indicators(df.copy())
                
                # Get latest values
                latest = df.iloc[-1]
                previous = df.iloc[-2]
                
                # Check for bullish momentum
                bullish_signal = self._check_bullish_momentum(latest, previous)
                if bullish_signal:
                    signal = self._create_signal(symbol, latest, "BUY", bullish_signal)
                    if signal:
                        signals.append(signal)
                        logger.info(f"Generated BUY signal for {symbol}")
                
                # Check for bearish momentum
                bearish_signal = self._check_bearish_momentum(latest, previous)
                if bearish_signal:
                    signal = self._create_signal(symbol, latest, "SELL", bearish_signal)
                    if signal:
                        signals.append(signal)
                        logger.info(f"Generated SELL signal for {symbol}")
                        
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                continue
        
        return signals
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators."""
        # Moving averages
        df['ma_fast'] = df['close'].rolling(window=self.fast_ma).mean()
        df['ma_slow'] = df['close'].rolling(window=self.slow_ma).mean()
        
        # RSI
        if ta:
            df['rsi'] = ta.momentum.RSIIndicator(
                close=df['close'], 
                window=self.rsi_period
            ).rsi()
        else:
            # Simple RSI calculation
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
        
        # Volume analysis
        df['volume_ma'] = df['volume'].rolling(window=self.volume_ma).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # ATR for stop loss calculation
        if ta:
            df['atr'] = ta.volatility.AverageTrueRange(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                window=14
            ).average_true_range()
        else:
            # Simple ATR approximation
            df['tr'] = df[['high', 'low', 'close']].apply(
                lambda x: max(x['high'] - x['low'], 
                            abs(x['high'] - x['close']), 
                            abs(x['low'] - x['close'])),
                axis=1
            )
            df['atr'] = df['tr'].rolling(window=14).mean()
        
        return df
    
    def _check_bullish_momentum(self, latest: pd.Series, previous: pd.Series) -> Optional[Dict[str, Any]]:
        """Check for bullish momentum setup."""
        # MA crossover: fast crosses above slow
        ma_crossover = (
            latest['ma_fast'] > latest['ma_slow'] and
            previous['ma_fast'] <= previous['ma_slow']
        )
        
        # RSI confirmation: not overbought
        rsi_ok = latest['rsi'] < self.rsi_overbought and latest['rsi'] > self.rsi_oversold
        
        # Volume confirmation
        volume_ok = latest['volume_ratio'] >= self.min_volume_ratio
        
        # Price above both MAs (strength confirmation)
        price_above_mas = latest['close'] > latest['ma_fast'] and latest['close'] > latest['ma_slow']
        
        if ma_crossover and rsi_ok and volume_ok:
            return {
                "ma_crossover": True,
                "rsi": latest['rsi'],
                "volume_ratio": latest['volume_ratio'],
                "strength": "strong" if price_above_mas else "moderate"
            }
        
        return None
    
    def _check_bearish_momentum(self, latest: pd.Series, previous: pd.Series) -> Optional[Dict[str, Any]]:
        """Check for bearish momentum setup."""
        # MA crossover: fast crosses below slow
        ma_crossover = (
            latest['ma_fast'] < latest['ma_slow'] and
            previous['ma_fast'] >= previous['ma_slow']
        )
        
        # RSI confirmation: not oversold
        rsi_ok = latest['rsi'] > self.rsi_oversold and latest['rsi'] < self.rsi_overbought
        
        # Volume confirmation
        volume_ok = latest['volume_ratio'] >= self.min_volume_ratio
        
        # Price below both MAs (weakness confirmation)
        price_below_mas = latest['close'] < latest['ma_fast'] and latest['close'] < latest['ma_slow']
        
        if ma_crossover and rsi_ok and volume_ok:
            return {
                "ma_crossover": True,
                "rsi": latest['rsi'],
                "volume_ratio": latest['volume_ratio'],
                "strength": "strong" if price_below_mas else "moderate"
            }
        
        return None
    
    def _create_signal(
        self,
        symbol: str,
        latest: pd.Series,
        trade_type: str,
        signal_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create a signal dictionary."""
        try:
            entry_price = latest['close']
            atr = latest['atr']
            
            # Calculate stop loss and take profit based on ATR
            if trade_type == "BUY":
                stop_loss = entry_price - (2 * atr)  # 2 ATR stop
                take_profit = entry_price + (4 * atr)  # 4 ATR target (1:2 R:R)
            else:  # SELL
                stop_loss = entry_price + (2 * atr)
                take_profit = entry_price - (4 * atr)
            
            # Calculate signal strength/score
            score = self._calculate_score(latest, signal_data)
            
            # Reasoning
            reasoning = (
                f"MA Crossover detected ({self.fast_ma}/{self.slow_ma}). "
                f"RSI at {signal_data['rsi']:.1f} (neutral zone). "
                f"Volume {signal_data['volume_ratio']:.1f}x average. "
                f"Setup strength: {signal_data['strength']}."
            )
            
            return {
                "symbol": symbol,
                "strategy": self.name,
                "score": score,
                "entry_price": round(entry_price, 2),
                "suggested_sl": round(stop_loss, 2),
                "suggested_tp": round(take_profit, 2),
                "trade_type": trade_type,
                "reasoning": reasoning,
                "metadata": {
                    "ma_fast": round(latest['ma_fast'], 2),
                    "ma_slow": round(latest['ma_slow'], 2),
                    "rsi": round(latest['rsi'], 2),
                    "atr": round(atr, 2),
                    "volume_ratio": round(signal_data['volume_ratio'], 2),
                    "strength": signal_data['strength']
                }
            }
            
        except Exception as e:
            logger.error(f"Error creating signal for {symbol}: {e}")
            return None
    
    def _calculate_score(self, latest: pd.Series, signal_data: Dict[str, Any]) -> float:
        """Calculate signal strength score (0.0 to 1.0)."""
        score = 0.5  # Base score
        
        # RSI in optimal range
        if 40 <= latest['rsi'] <= 60:
            score += 0.1
        
        # Strong volume
        if signal_data['volume_ratio'] >= 1.5:
            score += 0.15
        elif signal_data['volume_ratio'] >= 1.2:
            score += 0.1
        
        # Strength confirmation
        if signal_data['strength'] == "strong":
            score += 0.15
        else:
            score += 0.05
        
        # Distance from MA (closer is better for entry)
        ma_distance = abs(latest['close'] - latest['ma_fast']) / latest['close']
        if ma_distance < 0.01:  # Within 1%
            score += 0.1
        
        return min(1.0, score)

