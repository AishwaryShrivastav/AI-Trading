"""Positions and orders router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from ..database import get_db, Position, Order
from ..schemas import PositionResponse, OrderResponse
from ..services.broker import UpstoxBroker
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["trading"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(db: Session = Depends(get_db)):
    """Get current positions."""
    positions = db.query(Position).filter(
        Position.closed_at.is_(None)
    ).all()
    
    return positions


@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get order history."""
    orders = db.query(Order).order_by(
        Order.placed_at.desc()
    ).limit(limit).all()
    
    return orders


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """Get specific order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order


@router.post("/orders/{order_id}/refresh")
async def refresh_order_status(
    order_id: int,
    db: Session = Depends(get_db)
):
    """Refresh order status from broker."""
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    try:
        # Initialize broker
        broker = UpstoxBroker(
            api_key=settings.upstox_api_key,
            api_secret=settings.upstox_api_secret,
            redirect_uri=settings.upstox_redirect_uri
        )
        
        # Load token
        from ..database import Setting
        access_token = db.query(Setting).filter(
            Setting.key == "upstox_access_token"
        ).first()
        
        if access_token:
            broker.access_token = access_token.value
        else:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Get order status from broker
        broker_status = await broker.get_order_status(order.broker_order_id)
        
        # Update order
        order.status = broker_status.get("status", order.status)
        order.filled_quantity = broker_status.get("filled_quantity", order.filled_quantity)
        order.average_price = broker_status.get("average_price", order.average_price)
        
        if order.status == "complete" and not order.filled_at:
            from datetime import datetime
            order.filled_at = datetime.utcnow()
        
        db.commit()
        db.refresh(order)
        
        return order
        
    except Exception as e:
        logger.error(f"Error refreshing order status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/funds")
async def get_funds(db: Session = Depends(get_db)):
    """Get account funds from broker."""
    try:
        broker = UpstoxBroker(
            api_key=settings.upstox_api_key,
            api_secret=settings.upstox_api_secret,
            redirect_uri=settings.upstox_redirect_uri
        )
        
        from ..database import Setting
        access_token = db.query(Setting).filter(
            Setting.key == "upstox_access_token"
        ).first()
        
        if access_token:
            broker.access_token = access_token.value
        else:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        funds = await broker.get_funds()
        
        return funds
        
    except Exception as e:
        logger.error(f"Error fetching funds: {e}")
        raise HTTPException(status_code=500, detail=str(e))

