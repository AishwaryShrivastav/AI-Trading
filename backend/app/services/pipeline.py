"""Trade card generation pipeline integrating signals, LLM, and risk checks."""
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import pandas as pd

from ..database import TradeCard, MarketDataCache
from ..config import get_settings
from .signals import MomentumStrategy, MeanReversionStrategy
from .llm import OpenAIProvider, GeminiProvider, HuggingFaceProvider
from .risk_checks import RiskChecker
from .audit import AuditLogger

logger = logging.getLogger(__name__)
settings = get_settings()


class TradeCardPipeline:
    """
    Pipeline for generating trade cards:
    1. Run signal strategies
    2. LLM analysis and ranking
    3. Risk checks
    4. Create trade cards
    """
    
    def __init__(self, db: Session, broker=None):
        self.db = db
        self.broker = broker
        self.settings = settings
        
        # Initialize strategies
        self.strategies = {
            "momentum": MomentumStrategy(),
            "mean_reversion": MeanReversionStrategy()
        }
        
        # Initialize LLM provider
        self.llm = self._get_llm_provider()
        
        # Initialize risk checker and audit logger
        self.risk_checker = RiskChecker(db, broker)
        self.audit_logger = AuditLogger(db)
    
    def _get_llm_provider(self):
        """Get configured LLM provider."""
        provider = self.settings.llm_provider.lower()
        
        if provider == "openai":
            return OpenAIProvider(
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_model
            )
        elif provider == "gemini":
            return GeminiProvider(
                api_key=self.settings.openai_api_key,  # TODO: Add gemini_api_key to settings
                model="gemini-pro"
            )
        elif provider == "huggingface":
            return HuggingFaceProvider(
                api_key=self.settings.openai_api_key,  # TODO: Add hf_api_key to settings
                model="mistralai/Mistral-7B-Instruct-v0.2"
            )
        else:
            logger.warning(f"Unknown LLM provider {provider}, defaulting to OpenAI")
            return OpenAIProvider(
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_model
            )
    
    async def run_pipeline(
        self,
        symbols: List[str],
        strategies: Optional[List[str]] = None,
        max_trade_cards: int = 5
    ) -> Dict[str, Any]:
        """
        Run the full pipeline to generate trade cards.
        
        Args:
            symbols: List of symbols to scan
            strategies: List of strategy names to run (None = all)
            max_trade_cards: Maximum trade cards to generate
            
        Returns:
            Dict with summary and created trade card IDs
        """
        try:
            logger.info(f"Starting pipeline for {len(symbols)} symbols")
            
            # Step 1: Fetch market data
            market_data = await self._fetch_market_data(symbols)
            
            # Step 2: Generate signals from strategies
            signals = await self._generate_signals(symbols, market_data, strategies)
            logger.info(f"Generated {len(signals)} signals")
            
            if not signals:
                return {
                    "signals_generated": 0,
                    "trade_cards_created": 0,
                    "trade_card_ids": []
                }
            
            # Step 3: LLM analysis and ranking
            analyzed_signals = await self._analyze_signals(signals, market_data)
            logger.info(f"Analyzed {len(analyzed_signals)} signals")
            
            # Step 4: Rank and select top signals
            ranked_signals = await self.llm.rank_signals(analyzed_signals, max_trade_cards)
            logger.info(f"Selected top {len(ranked_signals)} signals")
            
            # Step 5: Run risk checks and create trade cards
            trade_card_ids = await self._create_trade_cards(ranked_signals)
            logger.info(f"Created {len(trade_card_ids)} trade cards")
            
            # Log the pipeline run
            self.audit_logger.log_signal_generation(
                strategy="pipeline",
                signals_count=len(signals),
                symbols_scanned=len(symbols),
                trade_cards_created=len(trade_card_ids),
                meta_data={
                    "strategies_run": strategies or list(self.strategies.keys()),
                    "max_trade_cards": max_trade_cards
                }
            )
            
            return {
                "signals_generated": len(signals),
                "analyzed_signals": len(analyzed_signals),
                "trade_cards_created": len(trade_card_ids),
                "trade_card_ids": trade_card_ids
            }
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise
    
    async def _fetch_market_data(
        self,
        symbols: List[str],
        days: int = 100
    ) -> Dict[str, pd.DataFrame]:
        """Fetch market data for symbols."""
        market_data = {}
        
        for symbol in symbols:
            try:
                # Try to get from cache first
                cached_data = self.db.query(MarketDataCache).filter(
                    MarketDataCache.symbol == symbol,
                    MarketDataCache.interval == "1D"
                ).order_by(MarketDataCache.timestamp.desc()).limit(days).all()
                
                if cached_data:
                    df = pd.DataFrame([
                        {
                            "timestamp": d.timestamp,
                            "open": d.open,
                            "high": d.high,
                            "low": d.low,
                            "close": d.close,
                            "volume": d.volume
                        }
                        for d in reversed(cached_data)
                    ])
                    market_data[symbol] = df
                    logger.info(f"Loaded {len(df)} cached candles for {symbol}")
                else:
                    # Fetch from broker if available
                    if self.broker:
                        ohlcv = await self.broker.get_ohlcv(symbol, interval="1day")
                        if ohlcv:
                            df = pd.DataFrame(ohlcv)
                            market_data[symbol] = df
                            logger.info(f"Fetched {len(df)} candles for {symbol}")
                            
                            # Cache the data
                            self._cache_market_data(symbol, ohlcv)
                    else:
                        logger.warning(f"No data available for {symbol}")
                        
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                continue
        
        return market_data
    
    def _cache_market_data(self, symbol: str, ohlcv: List[Dict[str, Any]]):
        """Cache market data in database."""
        try:
            for candle in ohlcv:
                # Check if already exists
                existing = self.db.query(MarketDataCache).filter(
                    MarketDataCache.symbol == symbol,
                    MarketDataCache.timestamp == candle["timestamp"]
                ).first()
                
                if not existing:
                    cache_entry = MarketDataCache(
                        symbol=symbol,
                        interval="1D",
                        timestamp=candle["timestamp"],
                        open=candle["open"],
                        high=candle["high"],
                        low=candle["low"],
                        close=candle["close"],
                        volume=candle["volume"]
                    )
                    self.db.add(cache_entry)
            
            self.db.commit()
        except Exception as e:
            logger.error(f"Error caching market data: {e}")
            self.db.rollback()
    
    async def _generate_signals(
        self,
        symbols: List[str],
        market_data: Dict[str, pd.DataFrame],
        strategies: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Generate signals from strategies."""
        all_signals = []
        
        # Select strategies to run
        strategies_to_run = strategies or list(self.strategies.keys())
        
        for strategy_name in strategies_to_run:
            strategy = self.strategies.get(strategy_name)
            if not strategy:
                logger.warning(f"Strategy {strategy_name} not found")
                continue
            
            try:
                signals = await strategy.generate_signals(symbols, market_data)
                all_signals.extend(signals)
                logger.info(f"{strategy_name} generated {len(signals)} signals")
            except Exception as e:
                logger.error(f"Error in {strategy_name}: {e}")
                continue
        
        return all_signals
    
    async def _analyze_signals(
        self,
        signals: List[Dict[str, Any]],
        market_data: Dict[str, pd.DataFrame]
    ) -> List[Dict[str, Any]]:
        """Run LLM analysis on each signal."""
        analyzed = []
        
        for signal in signals:
            try:
                symbol = signal["symbol"]
                
                # Get market data for this symbol
                symbol_data = market_data.get(symbol, pd.DataFrame())
                
                # Prepare market data summary
                market_summary = self._prepare_market_summary(symbol_data)
                
                # Run LLM analysis
                analysis = await self.llm.generate_trade_analysis(
                    signal=signal,
                    market_data=market_summary,
                    context={}
                )
                
                # Merge signal with analysis
                analyzed_signal = {
                    **signal,
                    "llm_analysis": analysis,
                    "confidence": analysis.get("confidence", 0.5),
                    "evidence": analysis.get("evidence", ""),
                    "risks": analysis.get("risks", ""),
                    "model_version": analysis.get("model_version")
                }
                
                # Update entry/SL/TP if LLM suggests changes
                if "suggested_entry" in analysis:
                    analyzed_signal["entry_price"] = analysis["suggested_entry"]
                if "suggested_sl" in analysis:
                    analyzed_signal["suggested_sl"] = analysis["suggested_sl"]
                if "suggested_tp" in analysis:
                    analyzed_signal["suggested_tp"] = analysis["suggested_tp"]
                
                analyzed.append(analyzed_signal)
                
            except Exception as e:
                logger.error(f"Error analyzing signal for {signal.get('symbol')}: {e}")
                # Include signal anyway with error note
                signal["llm_analysis"] = {"error": str(e)}
                signal["confidence"] = 0.3
                analyzed.append(signal)
        
        return analyzed
    
    def _prepare_market_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Prepare market data summary for LLM."""
        if df.empty:
            return {}
        
        latest = df.iloc[-1]
        
        summary = {
            "latest_close": float(latest["close"]),
            "latest_volume": int(latest["volume"]),
            "latest_timestamp": str(latest["timestamp"]),
        }
        
        # Add recent price action
        if len(df) >= 5:
            recent = df.tail(5)
            summary["recent_closes"] = recent["close"].tolist()
            summary["recent_volumes"] = recent["volume"].tolist()
        
        # Add key levels if indicators are present
        if "ma_fast" in df.columns:
            summary["ma_fast"] = float(latest["ma_fast"])
        if "ma_slow" in df.columns:
            summary["ma_slow"] = float(latest["ma_slow"])
        if "rsi" in df.columns:
            summary["rsi"] = float(latest["rsi"])
        
        return summary
    
    async def _create_trade_cards(
        self,
        ranked_signals: List[Dict[str, Any]]
    ) -> List[int]:
        """Create trade cards from ranked signals with risk checks."""
        trade_card_ids = []
        
        for ranked in ranked_signals:
            try:
                signal = ranked.get("signal", ranked)
                
                # Extract trade details
                symbol = signal["symbol"]
                entry_price = signal.get("entry_price", 0)
                stop_loss = signal.get("suggested_sl", 0)
                take_profit = signal.get("suggested_tp", 0)
                trade_type = signal.get("trade_type", "BUY")
                
                # Calculate quantity based on risk
                quantity = self._calculate_quantity(entry_price, stop_loss)
                
                # Run risk checks
                checks_passed, warnings = await self.risk_checker.run_all_checks(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    trade_type=trade_type
                )
                
                # Create trade card
                trade_card = TradeCard(
                    symbol=symbol,
                    entry_price=entry_price,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    trade_type=trade_type,
                    strategy=signal.get("strategy"),
                    horizon_days=signal.get("llm_analysis", {}).get(
                        "horizon_days",
                        self.settings.default_trade_horizon_days
                    ),
                    confidence=signal.get("confidence", 0.5),
                    evidence=signal.get("evidence", ""),
                    risks=signal.get("risks", ""),
                    status="pending_approval" if checks_passed else "rejected",
                    liquidity_check=checks_passed,
                    position_size_check=checks_passed,
                    exposure_check=checks_passed,
                    event_window_check=True,
                    risk_warnings=warnings,
                    model_version=signal.get("model_version"),
                    rejection_reason=None if checks_passed else "; ".join(warnings)
                )
                
                self.db.add(trade_card)
                self.db.commit()
                self.db.refresh(trade_card)
                
                # Log audit trail
                self.audit_logger.log_trade_card_created(
                    trade_card_id=trade_card.id,
                    trade_card_data={
                        "symbol": symbol,
                        "entry_price": entry_price,
                        "quantity": quantity,
                        "status": trade_card.status
                    },
                    signal_data=signal,
                    llm_analysis=signal.get("llm_analysis", {}),
                    risk_checks={
                        "passed": checks_passed,
                        "warnings": warnings
                    }
                )
                
                trade_card_ids.append(trade_card.id)
                logger.info(
                    f"Created trade card {trade_card.id} for {symbol} "
                    f"(status: {trade_card.status})"
                )
                
            except Exception as e:
                logger.error(f"Error creating trade card: {e}")
                self.db.rollback()
                continue
        
        return trade_card_ids
    
    def _calculate_quantity(self, entry_price: float, stop_loss: float) -> int:
        """Calculate position quantity based on risk management."""
        # Get total capital
        # For now, use a simple calculation
        # Risk 2% of capital on this trade
        capital = 100000  # TODO: Get from broker/settings
        risk_amount = capital * (self.settings.max_capital_risk_percent / 100)
        
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            return 1
        
        quantity = int(risk_amount / risk_per_share)
        return max(1, quantity)

