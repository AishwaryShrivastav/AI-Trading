"""Advanced Upstox trading endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from ..database import get_db
from ..services.upstox_service import UpstoxService

router = APIRouter(prefix="/api/upstox", tags=["upstox_advanced"])
logger = logging.getLogger(__name__)


# Pydantic Models for Requests
class ModifyOrderRequest(BaseModel):
    """Request model for modifying an order."""
    order_id: int
    quantity: Optional[int] = None
    order_type: Optional[str] = None
    price: Optional[float] = None
    trigger_price: Optional[float] = None


class MultiOrderRequest(BaseModel):
    """Request model for placing multiple orders."""
    orders: List[Dict[str, Any]]


class BrokerageCalculationRequest(BaseModel):
    """Request model for brokerage calculation."""
    symbol: str
    quantity: int
    transaction_type: str
    product: str = "D"
    exchange: str = "NSE"


class MarginCalculationRequest(BaseModel):
    """Request model for margin calculation."""
    orders: List[Dict[str, Any]]


# Endpoints

@router.post("/order/modify")
async def modify_order(
    request: ModifyOrderRequest,
    db: Session = Depends(get_db)
):
    """
    Modify an existing order.
    
    Allows modifying:
    - Quantity
    - Order type (MARKET, LIMIT, SL, SL-M)
    - Price (for LIMIT/SL orders)
    - Trigger price (for SL orders)
    """
    try:
        service = UpstoxService(db)
        
        order = await service.modify_order_and_update(
            order_id=request.order_id,
            quantity=request.quantity,
            order_type=request.order_type,
            price=request.price,
            trigger_price=request.trigger_price
        )
        
        return {
            "status": "success",
            "message": "Order modified successfully",
            "order": {
                "id": order.id,
                "broker_order_id": order.broker_order_id,
                "symbol": order.symbol,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "price": order.price,
                "status": order.status
            }
        }
        
    except Exception as e:
        logger.error(f"Error modifying order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order/multi-place")
async def place_multi_order(
    request: MultiOrderRequest,
    db: Session = Depends(get_db)
):
    """
    Place multiple orders in a single API call.
    
    Each order should contain:
    - trade_card_id: Associated trade card ID
    - symbol: Trading symbol
    - transaction_type: BUY or SELL
    - quantity: Number of shares
    - order_type: MARKET, LIMIT, SL, SL-M (optional)
    - price: Limit price (optional)
    - trigger_price: Trigger price (optional)
    - exchange: Exchange (default NSE)
    - product: D=Delivery, I=Intraday (default D)
    """
    try:
        service = UpstoxService(db)
        
        orders = await service.place_multi_order_with_tracking(request.orders)
        
        return {
            "status": "success",
            "message": f"{len(orders)} orders placed successfully",
            "orders": [
                {
                    "id": o.id,
                    "broker_order_id": o.broker_order_id,
                    "symbol": o.symbol,
                    "quantity": o.quantity,
                    "status": o.status
                }
                for o in orders
            ]
        }
        
    except Exception as e:
        logger.error(f"Error placing multi-order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/order/{order_id}/trades")
async def get_order_trades(
    order_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all trade executions for a specific order.
    
    Useful for partially filled orders or multiple executions.
    Returns details like:
    - Execution time
    - Quantity filled
    - Execution price
    - Trade ID
    """
    try:
        service = UpstoxService(db)
        trades = await service.get_order_trades(order_id)
        
        return {
            "status": "success",
            "order_id": order_id,
            "trades": trades,
            "total_executions": len(trades)
        }
        
    except Exception as e:
        logger.error(f"Error fetching order trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order/sync-all")
async def sync_all_orders(db: Session = Depends(get_db)):
    """
    Sync status for all pending/open orders from broker.
    
    Updates database with latest:
    - Order status
    - Filled quantity
    - Average price
    - Fill timestamps
    """
    try:
        service = UpstoxService(db)
        orders = await service.sync_all_pending_orders()
        
        return {
            "status": "success",
            "message": f"Synced {len(orders)} orders",
            "synced_orders": [
                {
                    "id": o.id,
                    "symbol": o.symbol,
                    "status": o.status,
                    "filled_quantity": o.filled_quantity,
                    "average_price": o.average_price
                }
                for o in orders
            ]
        }
        
    except Exception as e:
        logger.error(f"Error syncing orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/brokerage")
async def calculate_brokerage(
    request: BrokerageCalculationRequest,
    db: Session = Depends(get_db)
):
    """
    Calculate brokerage and charges for a potential trade.
    
    Returns complete cost breakdown:
    - Base cost (price × quantity)
    - Brokerage charges
    - Transaction charges
    - STT (Securities Transaction Tax)
    - GST (Goods and Services Tax)
    - Stamp duty
    - Total cost
    """
    try:
        service = UpstoxService(db)
        
        cost_breakdown = await service.calculate_trade_cost(
            symbol=request.symbol,
            quantity=request.quantity,
            transaction_type=request.transaction_type,
            product=request.product,
            exchange=request.exchange
        )
        
        return {
            "status": "success",
            "cost_breakdown": cost_breakdown
        }
        
    except Exception as e:
        logger.error(f"Error calculating brokerage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/margin")
async def calculate_margin(
    request: MarginCalculationRequest,
    db: Session = Depends(get_db)
):
    """
    Calculate margin required for one or more orders.
    
    Helps determine:
    - Total margin required
    - Available margin sufficient or not
    - Leverage available
    - Per-order margin breakdown
    """
    try:
        service = UpstoxService(db)
        
        margin_data = await service.calculate_margin_for_orders(request.orders)
        
        return {
            "status": "success",
            "margin_data": margin_data
        }
        
    except Exception as e:
        logger.error(f"Error calculating margin: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/sync")
async def sync_positions(db: Session = Depends(get_db)):
    """
    Sync positions from broker to database.
    
    Updates:
    - Current positions
    - Quantities
    - Average prices
    - P&L (realized and unrealized)
    - Closes positions that are squared off
    """
    try:
        service = UpstoxService(db)
        positions = await service.sync_positions_from_broker()
        
        return {
            "status": "success",
            "message": f"Synced {len(positions)} positions",
            "positions": [
                {
                    "id": p.id,
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "average_price": p.average_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl
                }
                for p in positions
            ]
        }
        
    except Exception as e:
        logger.error(f"Error syncing positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instruments")
async def get_instruments(
    exchange: Optional[str] = Query(None, description="NSE, BSE, MCX or None for all"),
    db: Session = Depends(get_db)
):
    """
    Get instrument master data.
    
    Fetches all tradable instruments with details:
    - Trading symbol
    - Instrument name
    - Instrument type (EQ, FUT, OPT, etc.)
    - Lot size
    - Tick size
    - Expiry date (for F&O)
    - Strike price (for options)
    
    Data is cached for 12 hours to improve performance.
    """
    try:
        service = UpstoxService(db)
        instruments = await service.get_instruments_cached(exchange=exchange)
        
        return {
            "status": "success",
            "exchange": exchange or "all",
            "count": len(instruments),
            "instruments": instruments[:1000]  # Limit response size
        }
        
    except Exception as e:
        logger.error(f"Error fetching instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instruments/search")
async def search_instruments(
    query: str = Query(..., description="Symbol or name to search"),
    instrument_type: Optional[str] = Query(None, description="EQ, FUT, OPT, etc."),
    exchange: Optional[str] = Query(None, description="NSE, BSE, MCX"),
    db: Session = Depends(get_db)
):
    """
    Search for instruments by symbol or name.
    
    Examples:
    - query=RELIANCE → Returns RELIANCE instruments
    - query=NIFTY → Returns NIFTY index and derivatives
    - query=RELIANCE, instrument_type=EQ → Returns only RELIANCE equity
    - query=BANK, exchange=NSE → Returns NSE instruments with BANK in name
    
    Returns up to 50 matching results.
    """
    try:
        service = UpstoxService(db)
        results = await service.search_symbol(
            query=query,
            instrument_type=instrument_type,
            exchange=exchange
        )
        
        return {
            "status": "success",
            "query": query,
            "filters": {
                "instrument_type": instrument_type,
                "exchange": exchange
            },
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error searching instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile")
async def get_profile(db: Session = Depends(get_db)):
    """
    Get user profile information from broker.
    
    Returns:
    - User ID
    - Client code
    - Account type
    - Email
    - Mobile number
    - Enabled exchanges
    - Enabled products
    """
    try:
        service = UpstoxService(db)
        profile = await service.get_profile()
        
        return {
            "status": "success",
            "profile": profile
        }
        
    except Exception as e:
        logger.error(f"Error fetching profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account/summary")
async def get_account_summary(db: Session = Depends(get_db)):
    """
    Get comprehensive account summary.
    
    Includes:
    - User profile
    - Available funds and margins
    - Open positions count
    - Recent orders
    - Account statistics
    
    One-stop endpoint for dashboard display.
    """
    try:
        service = UpstoxService(db)
        summary = await service.get_account_summary()
        
        return {
            "status": "success",
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error fetching account summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

