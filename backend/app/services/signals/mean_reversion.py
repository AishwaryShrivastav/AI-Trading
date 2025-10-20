"""Mean reversion strategy using Bollinger Bands."""
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


class MeanReversionStrategy(SignalBase):
    """
    Mean reversion strategy based on:
    - Bollinger Bands (price touches/breaks bands)
    - RSI oversold/overbought
    - Price reversion to mean
    """
    
    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30,
        rsi_overbought: float = 70,
        min_volume_ratio: float = 0.8
    ):
        super().__init__("mean_reversion")
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.min_volume_ratio = min_volume_ratio
    
    async def generate_signals(
        self,
        symbols: List[str],
        market_data: Dict[str, pd.DataFrame],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Generate mean reversion signals."""
        signals = []
        
        for symbol in symbols:
            try:
                df = market_data.get(symbol)
                if df is None or len(df) < self.bb_period + 10:
                    logger.warning(f"Insufficient data for {symbol}")
                    continue
                
                # Calculate indicators
                df = self._calculate_indicators(df.copy())
                
                # Get latest values
                latest = df.iloc[-1]
                previous = df.iloc[-2]
                
                # Check for oversold bounce (BUY)
                oversold_signal = self._check_oversold_bounce(latest, previous)
                if oversold_signal:
                    signal = self._create_signal(symbol, latest, "BUY", oversold_signal)
                    if signal:
                        signals.append(signal)
                        logger.info(f"Generated BUY signal for {symbol} (oversold bounce)")
                
                # Check for overbought reversal (SELL)
                overbought_signal = self._check_overbought_reversal(latest, previous)
                if overbought_signal:
                    signal = self._create_signal(symbol, latest, "SELL", overbought_signal)
                    if signal:
                        signals.append(signal)
                        logger.info(f"Generated SELL signal for {symbol} (overbought reversal)")
                        
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {e}")
                continue
        
        return signals
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators."""
        # Bollinger Bands
        if ta:
            bb = ta.volatility.BollingerBands(
                close=df['close'],
                window=self.bb_period,
                window_dev=self.bb_std
            )
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_middle'] = bb.bollinger_mavg()
            df['bb_lower'] = bb.bollinger_lband()
            df['bb_width'] = bb.bollinger_wband()
        else:
            # Manual Bollinger Bands calculation
            df['bb_middle'] = df['close'].rolling(window=self.bb_period).mean()
            bb_std = df['close'].rolling(window=self.bb_period).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * self.bb_std)
            df['bb_lower'] = df['bb_middle'] - (bb_std * self.bb_std)
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # RSI
        if ta:
            df['rsi'] = ta.momentum.RSIIndicator(
                close=df['close'],
                window=self.rsi_period
            ).rsi()
        else:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
        
        # Volume analysis
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # ATR for stop loss
        if ta:
            df['atr'] = ta.volatility.AverageTrueRange(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                window=14
            ).average_true_range()
        else:
            df['tr'] = df[['high', 'low', 'close']].apply(
                lambda x: max(x['high'] - x['low'],
                            abs(x['high'] - x['close']),
                            abs(x['low'] - x['close'])),
                axis=1
            )
            df['atr'] = df['tr'].rolling(window=14).mean()
        
        # Distance from bands
        df['dist_from_upper'] = (df['bb_upper'] - df['close']) / df['close']
        df['dist_from_lower'] = (df['close'] - df['bb_lower']) / df['close']
        
        return df
    
    def _check_oversold_bounce(self, latest: pd.Series, previous: pd.Series) -> Optional[Dict[str, Any]]:
        """Check for oversold bounce setup (BUY)."""
        # Price touched or crossed lower band
        touched_lower = latest['close'] <= latest['bb_lower'] or previous['close'] <= previous['bb_lower']
        
        # RSI oversold
        rsi_oversold = latest['rsi'] < self.rsi_oversold
        
        # Price starting to bounce (close above open or previous close)
        bouncing = latest['close'] > latest['open'] or latest['close'] > previous['close']
        
        # Not in extremely low volume
        volume_ok = latest['volume_ratio'] >= self.min_volume_ratio
        
        if touched_lower and rsi_oversold and bouncing and volume_ok:
            return {
                "touched_lower_band": True,
                "rsi": latest['rsi'],
                "dist_from_lower": latest['dist_from_lower'],
                "volume_ratio": latest['volume_ratio'],
                "bb_width": latest['bb_width']
            }
        
        return None
    
    def _check_overbought_reversal(self, latest: pd.Series, previous: pd.Series) -> Optional[Dict[str, Any]]:
        """Check for overbought reversal setup (SELL)."""
        # Price touched or crossed upper band
        touched_upper = latest['close'] >= latest['bb_upper'] or previous['close'] >= previous['bb_upper']
        
        # RSI overbought
        rsi_overbought = latest['rsi'] > self.rsi_overbought
        
        # Price starting to reverse (close below open or previous close)
        reversing = latest['close'] < latest['open'] or latest['close'] < previous['close']
        
        # Decent volume
        volume_ok = latest['volume_ratio'] >= self.min_volume_ratio
        
        if touched_upper and rsi_overbought and reversing and volume_ok:
            return {
                "touched_upper_band": True,
                "rsi": latest['rsi'],
                "dist_from_upper": latest['dist_from_upper'],
                "volume_ratio": latest['volume_ratio'],
                "bb_width": latest['bb_width']
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
            
            # Calculate stop loss and take profit
            if trade_type == "BUY":
                # Stop below lower band or 1.5 ATR
                stop_loss = min(latest['bb_lower'], entry_price - (1.5 * atr))
                # Target: middle band (mean reversion)
                take_profit = latest['bb_middle']
            else:  # SELL
                # Stop above upper band or 1.5 ATR
                stop_loss = max(latest['bb_upper'], entry_price + (1.5 * atr))
                # Target: middle band
                take_profit = latest['bb_middle']
            
            # Calculate score
            score = self._calculate_score(latest, signal_data, trade_type)
            
            # Reasoning
            if trade_type == "BUY":
                reasoning = (
                    f"Oversold bounce setup. Price touched lower BB, "
                    f"RSI at {signal_data['rsi']:.1f} (oversold), "
                    f"showing signs of reversal. "
                    f"Target: mean reversion to middle band."
                )
            else:
                reasoning = (
                    f"Overbought reversal setup. Price touched upper BB, "
                    f"RSI at {signal_data['rsi']:.1f} (overbought), "
                    f"showing signs of reversal. "
                    f"Target: mean reversion to middle band."
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
                    "bb_upper": round(latest['bb_upper'], 2),
                    "bb_middle": round(latest['bb_middle'], 2),
                    "bb_lower": round(latest['bb_lower'], 2),
                    "bb_width": round(latest['bb_width'], 4),
                    "rsi": round(latest['rsi'], 2),
                    "atr": round(atr, 2),
                    "volume_ratio": round(signal_data['volume_ratio'], 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error creating signal for {symbol}: {e}")
            return None
    
    def _calculate_score(
        self,
        latest: pd.Series,
        signal_data: Dict[str, Any],
        trade_type: str
    ) -> float:
        """Calculate signal strength score (0.0 to 1.0)."""
        score = 0.5  # Base score
        
        # Extreme RSI
        if trade_type == "BUY" and latest['rsi'] < 25:
            score += 0.15
        elif trade_type == "BUY" and latest['rsi'] < 30:
            score += 0.1
        elif trade_type == "SELL" and latest['rsi'] > 75:
            score += 0.15
        elif trade_type == "SELL" and latest['rsi'] > 70:
            score += 0.1
        
        # Distance from band (further = stronger signal)
        if trade_type == "BUY":
            if signal_data['dist_from_lower'] < 0:  # Below lower band
                score += 0.15
            elif signal_data['dist_from_lower'] < 0.01:  # Very close
                score += 0.1
        else:
            if signal_data['dist_from_upper'] < 0:  # Above upper band
                score += 0.15
            elif signal_data['dist_from_upper'] < 0.01:
                score += 0.1
        
        # BB width (wider bands = more volatile, stronger reversion potential)
        if latest['bb_width'] > 0.1:
            score += 0.1
        
        # Volume confirmation
        if signal_data['volume_ratio'] >= 1.2:
            score += 0.1
        
        return min(1.0, score)

