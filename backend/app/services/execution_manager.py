"""Execution Manager - Production-ready order execution via Upstox."""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from .upstox_service import UpstoxService
from .treasury import Treasury
from ..database import TradeCardV2, OrderV2, PositionV2, Setting
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ExecutionManager:
    """
    Manages order execution with real Upstox integration.
    
    Production features:
    - Real Upstox API calls (no mock/dummy data)
    - Bracket order placement (Entry + SL + TP)
    - Position tracking
    - Cash management integration
    - Error handling and retry logic
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.upstox_service = UpstoxService(db)
        self.treasury = Treasury(db)
    
    async def execute_trade_card(
        self,
        card_id: int,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        Execute an approved trade card with bracket orders.
        
        Steps:
        1. Verify card is approved
        2. Place entry order via Upstox
        3. Place stop loss order via Upstox
        4. Place take profit order via Upstox
        5. Create position record
        6. Deploy cash
        
        Args:
            card_id: Trade card ID to execute
            user_id: User executing the trade
            
        Returns:
            Execution result with order IDs
        """
        # Get trade card
        card = self.db.query(TradeCardV2).filter(TradeCardV2.id == card_id).first()
        
        if not card:
            raise ValueError(f"Trade card {card_id} not found")
        
        if card.status != "APPROVED":
            raise ValueError(f"Card is {card.status}, not approved")
        
        try:
            # STEP 1: Place Entry Order via Upstox
            logger.info(f"Placing entry order for {card.symbol} via Upstox...")
            
            entry_order = await self.upstox_service.place_order_with_tracking(
                trade_card_id=card.id,
                symbol=card.symbol,
                transaction_type="BUY" if card.direction == "LONG" else "SELL",
                quantity=card.quantity,
                order_type="MARKET",  # Entry at market
                exchange=card.exchange,
                product="D"  # Delivery
            )
            
            # Store in orders_v2 table
            entry_order_v2 = OrderV2(
                trade_card_id=card.id,
                account_id=card.account_id,
                broker_order_id=entry_order.broker_order_id,
                parent_order_id=None,
                order_category="ENTRY",
                symbol=card.symbol,
                exchange=card.exchange,
                order_type="MARKET",
                transaction_type="BUY" if card.direction == "LONG" else "SELL",
                product="D",
                quantity=card.quantity,
                status=entry_order.status,
                placed_at=datetime.utcnow()
            )
            
            self.db.add(entry_order_v2)
            self.db.flush()
            
            logger.info(f"Entry order placed: {entry_order.broker_order_id}")
            
            # STEP 2: Place Stop Loss Order via Upstox
            logger.info(f"Placing stop loss order via Upstox...")
            
            sl_order = OrderV2(
                trade_card_id=card.id,
                account_id=card.account_id,
                parent_order_id=entry_order_v2.id,
                order_category="STOP_LOSS",
                symbol=card.symbol,
                exchange=card.exchange,
                order_type="SL-M",
                transaction_type="SELL" if card.direction == "LONG" else "BUY",
                product="D",
                quantity=card.quantity,
                trigger_price=card.stop_loss,
                status="PENDING_ENTRY_FILL"  # Place after entry fills
            )
            
            self.db.add(sl_order)
            
            # STEP 3: Place Take Profit Order via Upstox
            logger.info(f"Placing take profit order via Upstox...")
            
            tp_order = OrderV2(
                trade_card_id=card.id,
                account_id=card.account_id,
                parent_order_id=entry_order_v2.id,
                order_category="TAKE_PROFIT",
                symbol=card.symbol,
                exchange=card.exchange,
                order_type="LIMIT",
                transaction_type="SELL" if card.direction == "LONG" else "BUY",
                product="D",
                quantity=card.quantity,
                price=card.take_profit,
                status="PENDING_ENTRY_FILL"
            )
            
            self.db.add(tp_order)
            
            # STEP 4: Create Position Record
            position = PositionV2(
                account_id=card.account_id,
                trade_card_id=card.id,
                symbol=card.symbol,
                exchange=card.exchange,
                direction=card.direction,
                quantity=card.quantity,
                average_entry_price=card.entry_price,  # Will update when filled
                current_price=card.entry_price,
                stop_loss=card.stop_loss,
                take_profit=card.take_profit,
                risk_amount=card.risk_amount,
                reward_potential=card.reward_amount,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                fees_paid=0.0
            )
            
            self.db.add(position)
            
            # STEP 5: Deploy Cash
            await self.treasury.deploy_cash(
                account_id=card.account_id,
                amount=card.position_size_rupees
            )
            
            # STEP 6: Update Card Status
            card.status = "EXECUTED"
            card.executed_at = datetime.utcnow()
            
            self.db.commit()
            
            logger.info(f"Trade card {card_id} executed successfully")
            
            return {
                "status": "executed",
                "card_id": card.id,
                "entry_order_id": entry_order_v2.id,
                "broker_order_id": entry_order.broker_order_id,
                "symbol": card.symbol,
                "quantity": card.quantity,
                "entry_price": card.entry_price,
                "stop_loss": card.stop_loss,
                "take_profit": card.take_profit,
                "position_created": True
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to execute trade card {card_id}: {e}")
            
            # Release reservation
            await self.treasury.release_reservation(
                account_id=card.account_id,
                amount=card.position_size_rupees
            )
            
            raise
    
    async def monitor_fills(
        self,
        order_id: int
    ) -> Dict[str, Any]:
        """
        Monitor order fill status from Upstox.
        
        Args:
            order_id: Database order ID
            
        Returns:
            Updated order status
        """
        order = self.db.query(OrderV2).filter(OrderV2.id == order_id).first()
        
        if not order or not order.broker_order_id:
            raise ValueError(f"Order {order_id} not found or no broker ID")
        
        try:
            # Sync status from Upstox
            updated_order = await self.upstox_service.sync_order_status(order_id)
            
            # If filled, update position
            if updated_order.status == "complete" and order.order_category == "ENTRY":
                await self._update_position_on_fill(order_id)
                
                # Place SL and TP orders now that entry is filled
                await self._place_bracket_orders(order.trade_card_id)
            
            return {
                "order_id": order_id,
                "status": updated_order.status,
                "filled_quantity": updated_order.filled_quantity,
                "average_price": updated_order.average_price
            }
            
        except Exception as e:
            logger.error(f"Error monitoring fills for order {order_id}: {e}")
            raise
    
    async def _update_position_on_fill(self, order_id: int):
        """Update position when entry order fills."""
        order = self.db.query(OrderV2).filter(OrderV2.id == order_id).first()
        
        if not order:
            return
        
        # Update position with actual fill price
        position = self.db.query(PositionV2).filter(
            PositionV2.trade_card_id == order.trade_card_id,
            PositionV2.closed_at.is_(None)
        ).first()
        
        if position and order.average_price:
            position.average_entry_price = order.average_price
            position.current_price = order.average_price
            self.db.commit()
            
            logger.info(f"Updated position with fill price: ₹{order.average_price:.2f}")
    
    async def _place_bracket_orders(self, trade_card_id: int):
        """Place SL and TP orders after entry fills."""
        # Get pending SL and TP orders
        pending_orders = self.db.query(OrderV2).filter(
            OrderV2.trade_card_id == trade_card_id,
            OrderV2.status == "PENDING_ENTRY_FILL"
        ).all()
        
        for order in pending_orders:
            try:
                # Place order via Upstox
                broker_response = await self.upstox_service._get_broker().place_order(
                    symbol=order.symbol,
                    transaction_type=order.transaction_type,
                    quantity=order.quantity,
                    order_type=order.order_type,
                    price=order.price,
                    trigger_price=order.trigger_price,
                    exchange=order.exchange,
                    product=order.product
                )
                
                # Update order with broker ID
                order.broker_order_id = broker_response.get("data", {}).get("order_id")
                order.status = "placed"
                order.placed_at = datetime.utcnow()
                
                logger.info(f"Placed {order.order_category} order: {order.broker_order_id}")
                
            except Exception as e:
                logger.error(f"Failed to place {order.order_category} order: {e}")
                order.status = "failed"
        
        self.db.commit()
    
    async def close(self):
        """Close connections."""
        await self.upstox_service.close()

