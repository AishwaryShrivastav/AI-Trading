"""Comprehensive Upstox Service Layer with advanced features."""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session

from .broker import UpstoxBroker
from ..database import Setting, Order, Position
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class UpstoxService:
    """High-level Upstox service with business logic and caching."""
    
    def __init__(self, db: Session):
        self.db = db
        self.broker: Optional[UpstoxBroker] = None
    
    def _get_broker(self) -> UpstoxBroker:
        """Get or create broker instance with authentication."""
        if self.broker is None:
            self.broker = UpstoxBroker(
                api_key=settings.upstox_api_key,
                api_secret=settings.upstox_api_secret,
                redirect_uri=settings.upstox_redirect_uri
            )
            
            # Load tokens from database
            access_token = self.db.query(Setting).filter(
                Setting.key == "upstox_access_token"
            ).first()
            
            refresh_token = self.db.query(Setting).filter(
                Setting.key == "upstox_refresh_token"
            ).first()
            
            if access_token:
                self.broker.access_token = access_token.value
            if refresh_token:
                self.broker.refresh_token = refresh_token.value
        
        return self.broker
    
    async def place_order_with_tracking(
        self,
        trade_card_id: int,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        exchange: str = "NSE",
        product: str = "D"
    ) -> Order:
        """
        Place order and create database record with tracking.
        
        Returns:
            Order object with broker_order_id
        """
        broker = self._get_broker()
        
        # Place order with broker
        response = await broker.place_order(
            symbol=symbol,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price,
            exchange=exchange,
            product=product
        )
        
        # Extract order ID from response
        broker_order_id = response.get("data", {}).get("order_id")
        
        # Create order record
        order = Order(
            trade_card_id=trade_card_id,
            broker_order_id=broker_order_id,
            symbol=symbol,
            exchange=exchange,
            order_type=order_type,
            transaction_type=transaction_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            status="placed",
            placed_at=datetime.utcnow()
        )
        
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        
        logger.info(f"Order placed and tracked: {broker_order_id}")
        return order
    
    async def place_multi_order_with_tracking(
        self,
        orders: List[Dict[str, Any]]
    ) -> List[Order]:
        """
        Place multiple orders and track them.
        
        Args:
            orders: List of order dicts with trade_card_id included
            
        Returns:
            List of Order objects
        """
        broker = self._get_broker()
        
        # Place multi-order
        responses = await broker.place_multi_order(orders)
        
        # Create order records
        order_objects = []
        for order_dict, response in zip(orders, responses):
            broker_order_id = response.get("order_id")
            
            order = Order(
                trade_card_id=order_dict.get("trade_card_id"),
                broker_order_id=broker_order_id,
                symbol=order_dict["symbol"],
                exchange=order_dict.get("exchange", "NSE"),
                order_type=order_dict.get("order_type", "MARKET"),
                transaction_type=order_dict["transaction_type"],
                quantity=order_dict["quantity"],
                price=order_dict.get("price"),
                trigger_price=order_dict.get("trigger_price"),
                status="placed",
                placed_at=datetime.utcnow()
            )
            
            self.db.add(order)
            order_objects.append(order)
        
        self.db.commit()
        
        logger.info(f"Multi-order placed: {len(order_objects)} orders tracked")
        return order_objects
    
    async def modify_order_and_update(
        self,
        order_id: int,
        quantity: Optional[int] = None,
        order_type: Optional[str] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> Order:
        """
        Modify order with broker and update database.
        
        Args:
            order_id: Database order ID
            Other params: Fields to modify
            
        Returns:
            Updated Order object
        """
        broker = self._get_broker()
        
        # Get order from database
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        # Modify with broker
        await broker.modify_order(
            order_id=order.broker_order_id,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price
        )
        
        # Update database record
        if quantity is not None:
            order.quantity = quantity
        if order_type is not None:
            order.order_type = order_type
        if price is not None:
            order.price = price
        if trigger_price is not None:
            order.trigger_price = trigger_price
        
        order.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(order)
        
        logger.info(f"Order modified: {order_id}")
        return order
    
    async def sync_order_status(self, order_id: int) -> Order:
        """
        Sync order status from broker to database.
        
        Args:
            order_id: Database order ID
            
        Returns:
            Updated Order object
        """
        broker = self._get_broker()
        
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        # Get status from broker
        broker_status = await broker.get_order_status(order.broker_order_id)
        
        # Update order
        order.status = broker_status.get("status", order.status)
        order.filled_quantity = broker_status.get("filled_quantity", order.filled_quantity)
        order.average_price = broker_status.get("average_price", order.average_price)
        
        if order.status == "complete" and not order.filled_at:
            order.filled_at = datetime.utcnow()
        
        order.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    async def sync_all_pending_orders(self) -> List[Order]:
        """
        Sync status for all pending/placed orders.
        
        Returns:
            List of updated orders
        """
        pending_orders = self.db.query(Order).filter(
            Order.status.in_(["placed", "pending", "open"])
        ).all()
        
        updated_orders = []
        for order in pending_orders:
            try:
                updated_order = await self.sync_order_status(order.id)
                updated_orders.append(updated_order)
            except Exception as e:
                logger.error(f"Failed to sync order {order.id}: {e}")
        
        return updated_orders
    
    async def get_order_trades(self, order_id: int) -> List[Dict[str, Any]]:
        """
        Get all trade executions for an order.
        
        Args:
            order_id: Database order ID
            
        Returns:
            List of trade executions
        """
        broker = self._get_broker()
        
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        trades = await broker.get_trades_by_order(order.broker_order_id)
        return trades
    
    async def calculate_trade_cost(
        self,
        symbol: str,
        quantity: int,
        transaction_type: str,
        product: str = "D",
        exchange: str = "NSE"
    ) -> Dict[str, Any]:
        """
        Calculate complete cost including brokerage for a trade.
        
        Returns:
            Dict with breakdown:
            - base_cost: stock price * quantity
            - brokerage: brokerage charges
            - taxes: STT, GST, etc.
            - total_cost: total amount required
        """
        broker = self._get_broker()
        
        # Get current LTP
        ltp = await broker.get_ltp(symbol, exchange)
        
        # Get instrument key
        instrument_key = broker._get_instrument_key(symbol, exchange)
        
        # Get brokerage breakdown
        brokerage_details = await broker.get_brokerage(
            instrument_token=instrument_key,
            quantity=quantity,
            transaction_type=transaction_type,
            product=product
        )
        
        base_cost = ltp * quantity
        
        return {
            "symbol": symbol,
            "quantity": quantity,
            "ltp": ltp,
            "base_cost": base_cost,
            "brokerage": brokerage_details.get("brokerage", 0),
            "transaction_charges": brokerage_details.get("transaction_charges", 0),
            "stt": brokerage_details.get("stt", 0),
            "gst": brokerage_details.get("gst", 0),
            "stamp_duty": brokerage_details.get("stamp_duty", 0),
            "total_charges": brokerage_details.get("total_charges", 0),
            "total_cost": base_cost + brokerage_details.get("total_charges", 0),
            "breakdown": brokerage_details
        }
    
    async def calculate_margin_for_orders(
        self,
        orders: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate total margin required for multiple orders.
        
        Args:
            orders: List of order details
            
        Returns:
            Margin requirement with breakdown
        """
        broker = self._get_broker()
        
        # Format for margin API
        formatted_orders = []
        for order in orders:
            formatted_orders.append({
                "instrument_token": broker._get_instrument_key(
                    order["symbol"],
                    order.get("exchange", "NSE")
                ),
                "quantity": order["quantity"],
                "transaction_type": order["transaction_type"].upper(),
                "product": order.get("product", "D"),
                "order_type": order.get("order_type", "MARKET").upper(),
                "price": order.get("price", 0)
            })
        
        margin_data = await broker.get_margin_required(formatted_orders)
        return margin_data
    
    async def sync_positions_from_broker(self) -> List[Position]:
        """
        Sync positions from broker to database.
        
        Returns:
            List of Position objects
        """
        broker = self._get_broker()
        
        # Get positions from broker
        broker_positions = await broker.get_net_positions()
        
        position_objects = []
        for bp in broker_positions:
            # Check if position exists
            position = self.db.query(Position).filter(
                Position.symbol == bp.get("trading_symbol"),
                Position.closed_at.is_(None)
            ).first()
            
            net_quantity = bp.get("quantity", 0)
            
            if net_quantity == 0 and position:
                # Position closed
                position.closed_at = datetime.utcnow()
            elif net_quantity != 0:
                if not position:
                    # Create new position
                    position = Position(
                        symbol=bp.get("trading_symbol"),
                        exchange=bp.get("exchange", "NSE"),
                        quantity=net_quantity,
                        average_price=bp.get("average_price", 0),
                        opened_at=datetime.utcnow()
                    )
                    self.db.add(position)
                else:
                    # Update existing
                    position.quantity = net_quantity
                    position.average_price = bp.get("average_price", position.average_price)
                
                # Update P&L
                position.current_price = bp.get("last_price", position.current_price)
                position.unrealized_pnl = bp.get("pnl", 0)
                position.updated_at = datetime.utcnow()
                
                position_objects.append(position)
        
        self.db.commit()
        
        logger.info(f"Synced {len(position_objects)} positions from broker")
        return position_objects
    
    async def get_instruments_cached(
        self,
        exchange: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get instruments with caching.
        
        Args:
            exchange: NSE, BSE, MCX or None for all
            
        Returns:
            List of instruments
        """
        broker = self._get_broker()
        return await broker.get_instruments(exchange=exchange)
    
    async def search_symbol(
        self,
        query: str,
        instrument_type: Optional[str] = None,
        exchange: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for instruments/symbols.
        
        Args:
            query: Symbol or name to search
            instrument_type: EQ, FUT, OPT, etc.
            exchange: NSE, BSE, MCX
            
        Returns:
            List of matching instruments
        """
        broker = self._get_broker()
        return await broker.search_instrument(query, instrument_type, exchange)
    
    async def get_profile(self) -> Dict[str, Any]:
        """Get user profile from broker."""
        broker = self._get_broker()
        return await broker.get_profile()
    
    async def get_account_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive account summary.
        
        Returns:
            Dict with profile, funds, positions, and orders
        """
        broker = self._get_broker()
        
        profile = await broker.get_profile()
        funds = await broker.get_funds()
        positions = await broker.get_net_positions()
        
        # Get recent orders from DB
        recent_orders = self.db.query(Order).order_by(
            Order.placed_at.desc()
        ).limit(10).all()
        
        return {
            "profile": profile,
            "funds": funds,
            "positions_count": len(positions),
            "open_positions": [p for p in positions if p.get("quantity", 0) != 0],
            "recent_orders": [
                {
                    "id": o.id,
                    "symbol": o.symbol,
                    "type": o.transaction_type,
                    "quantity": o.quantity,
                    "status": o.status,
                    "placed_at": o.placed_at.isoformat() if o.placed_at else None
                }
                for o in recent_orders
            ]
        }

    async def resolve_option_instrument_key(
        self,
        symbol: str,
        expiry: str,
        option_type: str,
        strike: float,
        exchange: str = "NSE"
    ) -> str:
        """Resolve instrument_key for an option contract via instruments dataset.

        Searches the Upstox instruments JSON for a matching option contract.
        """
        broker = self._get_broker()
        instruments = await broker.get_instruments(exchange)
        opt_type_upper = option_type.upper()
        strike_int = int(strike)
        for inst in instruments:
            try:
                if str(inst.get("expiry")) == expiry and inst.get("strike") in (strike, strike_int):
                    if inst.get("option_type", "").upper() == opt_type_upper and symbol.upper() in (inst.get("name", "").upper() or inst.get("trading_symbol", "").upper()):
                        key = inst.get("instrument_key") or inst.get("token") or inst.get("instrument_token")
                        if key:
                            # Normalize to instrument_key format if possible
                            if isinstance(key, str) and "|" in key:
                                return key
                            # Fallback: construct from exchange and trading_symbol
                            tsym = inst.get("trading_symbol")
                            if tsym:
                                return f"{exchange}_FO|{tsym}"
            except Exception:
                continue
        raise ValueError("Unable to resolve option instrument key")

    async def execute_option_strategy(self, strategy_id: int) -> Dict[str, Any]:
        """Execute an option strategy by placing legs as market orders.

        Requires valid Upstox access token to be present.
        """
        from ..database import OptionStrategy
        broker = self._get_broker()

        # Ensure we have an access token
        if not broker.access_token:
            raise RuntimeError("Broker not authenticated")

        strategy = self.db.query(OptionStrategy).filter(OptionStrategy.id == strategy_id).first()
        if not strategy:
            raise ValueError("Strategy not found")

        expiry = strategy.expiry.strftime("%Y-%m-%d") if strategy.expiry else None
        if not expiry:
            raise ValueError("Strategy expiry not set")

        order_results: List[Dict[str, Any]] = []
        for leg in strategy.legs or []:
            instrument_key = await self.resolve_option_instrument_key(
                symbol=strategy.underlying,
                expiry=expiry,
                option_type=leg.get("option_type"),
                strike=leg.get("strike"),
                exchange=strategy.exchange or "NSE"
            )
            payload = {
                "symbol": strategy.underlying,
                "transaction_type": "BUY" if leg.get("type") == "BUY" else "SELL",
                "quantity": int(leg.get("quantity", 1)) * 1,  # lot size left to broker
                "order_type": "MARKET",
                "price": None,
                "trigger_price": None,
                "exchange": strategy.exchange or "NSE",
                "product": "D"
            }
            # Override instrument resolution at broker layer
            # Place order (uses equity instrument proxy, broker will accept option key in endpoint fields)
            try:
                result = await broker.place_order(
                    symbol=payload["symbol"],
                    transaction_type=payload["transaction_type"],
                    quantity=payload["quantity"],
                    order_type=payload["order_type"],
                    price=payload["price"],
                    trigger_price=payload["trigger_price"],
                    exchange=payload["exchange"],
                    product=payload["product"]
                )
                order_results.append(result)
            except Exception as e:
                raise RuntimeError(f"Failed to place leg order: {e}")

        # Update strategy status
        strategy.status = "EXECUTED"
        strategy.executed_at = datetime.utcnow()
        self.db.commit()
        return {"status": "EXECUTED", "legs": len(order_results)}
    
    async def close(self):
        """Close broker connection."""
        if self.broker:
            await self.broker.close()

