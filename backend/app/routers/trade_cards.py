"""Trade card management router."""
from fastapi import APIRouter, Depends, HTTPException, Query
import httpx
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from ..database import get_db, TradeCard, Order, Position
from ..schemas import (
    TradeCardResponse,
    TradeCardApproval,
    TradeCardRejection,
    OrderResponse
)
from ..services.broker import UpstoxBroker, get_broker
from ..services.audit import AuditLogger
from ..services.risk_checks import RiskChecker
from ..config import get_settings

router = APIRouter(prefix="/api/trade-cards", tags=["trade-cards"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/pending", response_model=List[TradeCardResponse])
async def get_pending_trade_cards(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get pending trade cards awaiting approval."""
    trade_cards = db.query(TradeCard).filter(
        TradeCard.status == "pending_approval"
    ).order_by(
        TradeCard.confidence.desc(),
        TradeCard.created_at.desc()
    ).limit(limit).all()
    
    return trade_cards


@router.get("/{trade_card_id}", response_model=TradeCardResponse)
async def get_trade_card(
    trade_card_id: int,
    db: Session = Depends(get_db)
):
    """Get specific trade card by ID."""
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    return trade_card


@router.get("/", response_model=List[TradeCardResponse])
async def get_trade_cards(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get trade cards with optional filters."""
    query = db.query(TradeCard)
    
    if status:
        query = query.filter(TradeCard.status == status)
    
    if symbol:
        query = query.filter(TradeCard.symbol == symbol)
    
    if strategy:
        query = query.filter(TradeCard.strategy == strategy)
    
    trade_cards = query.order_by(TradeCard.created_at.desc()).limit(limit).all()
    
    return trade_cards


async def _approve_paper(trade_card: TradeCard, approval: TradeCardApproval, db: Session) -> Order:
    """Simulate execution of a trade card in paper mode.

    No broker order is placed. A PaperBroker computes a simulated fill (real LTP
    when a token is available, otherwise the card's entry price, plus slippage),
    and we persist an ``Order`` and ``Position`` flagged ``is_paper=True`` so the
    rest of the pipeline (positions, reporting, audit) works unchanged.
    """
    audit_logger = AuditLogger(db)

    snapshot = {
        "id": trade_card.id,
        "symbol": trade_card.symbol,
        "entry_price": trade_card.entry_price,
        "quantity": trade_card.quantity,
        "stop_loss": trade_card.stop_loss,
        "take_profit": trade_card.take_profit,
        "trade_type": trade_card.trade_type,
        "confidence": trade_card.confidence,
        "paper": True,
    }
    audit_logger.log_trade_card_approved(
        trade_card_id=trade_card.id,
        user_id=approval.user_id,
        trade_card_snapshot=snapshot,
        notes=(approval.notes or "") + " [PAPER]",
    )

    trade_card.status = "approved"
    trade_card.approved_at = datetime.utcnow()

    order_quantity = trade_card.quantity
    if approval.quantity and approval.quantity > 0:
        order_quantity = approval.quantity
        trade_card.quantity = order_quantity

    broker = get_broker(db)  # PaperBroker while TRADING_MODE=paper
    order_response = await broker.place_order(
        symbol=trade_card.symbol,
        transaction_type=trade_card.trade_type,
        quantity=order_quantity,
        order_type="LIMIT",
        price=trade_card.entry_price,
        exchange="NSE",
        product="D",
    )
    data = order_response.get("data", {}) if isinstance(order_response, dict) else {}
    broker_order_id = data.get("order_id")
    fill_price = data.get("average_price") or trade_card.entry_price

    order = Order(
        trade_card_id=trade_card.id,
        broker_order_id=broker_order_id,
        symbol=trade_card.symbol,
        exchange="NSE",
        order_type="LIMIT",
        transaction_type=trade_card.trade_type,
        quantity=order_quantity,
        price=trade_card.entry_price,
        status="complete",
        filled_quantity=order_quantity,
        average_price=fill_price,
        is_paper=True,
        filled_at=datetime.utcnow(),
    )
    db.add(order)

    # Open a simulated position (signed quantity by direction).
    direction = (trade_card.trade_type or "BUY").upper()
    signed_qty = order_quantity if direction == "BUY" else -order_quantity
    position = Position(
        symbol=trade_card.symbol,
        exchange="NSE",
        quantity=signed_qty,
        average_price=fill_price,
        current_price=fill_price,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        is_paper=True,
    )
    db.add(position)

    trade_card.status = "executed"
    db.commit()
    db.refresh(order)

    audit_logger.log_order_placed(
        order_id=order.id,
        trade_card_id=trade_card.id,
        order_payload={
            "symbol": trade_card.symbol,
            "quantity": order_quantity,
            "price": fill_price,
            "paper": True,
        },
        broker_response=order_response,
    )
    logger.info(f"[PAPER] Trade card {trade_card.id} executed: {broker_order_id} @ {fill_price}")
    return order


@router.post("/{trade_card_id}/approve", response_model=OrderResponse)
async def approve_trade_card(
    trade_card_id: int,
    approval: TradeCardApproval,
    db: Session = Depends(get_db)
):
    """
    Approve a trade card and place order with broker.
    """
    # Get trade card
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    if trade_card.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Trade card status is {trade_card.status}, cannot approve"
        )
    
    try:
        # ---- Paper trading mode: simulate the fill, never touch the broker ----
        if (get_settings().trading_mode or "paper").lower() == "paper":
            return await _approve_paper(trade_card, approval, db)

        # Initialize services
        audit_logger = AuditLogger(db)

        # Create trade card snapshot for audit
        trade_card_snapshot = {
            "id": trade_card.id,
            "symbol": trade_card.symbol,
            "entry_price": trade_card.entry_price,
            "quantity": trade_card.quantity,
            "stop_loss": trade_card.stop_loss,
            "take_profit": trade_card.take_profit,
            "trade_type": trade_card.trade_type,
            "confidence": trade_card.confidence
        }
        
        # Log approval
        audit_logger.log_trade_card_approved(
            trade_card_id=trade_card.id,
            user_id=approval.user_id,
            trade_card_snapshot=trade_card_snapshot,
            notes=approval.notes
        )
        
        # Update trade card status
        trade_card.status = "approved"
        trade_card.approved_at = datetime.utcnow()
        
        # Initialize broker
        broker = UpstoxBroker(
            api_key=settings.upstox_api_key,
            api_secret=settings.upstox_api_secret,
            redirect_uri=settings.upstox_redirect_uri
        )
        
        # Load tokens from database
        from ..database import Setting
        access_token = db.query(Setting).filter(
            Setting.key == "upstox_access_token"
        ).first()
        refresh_token = db.query(Setting).filter(
            Setting.key == "upstox_refresh_token"
        ).first()
        
        if access_token:
            broker.access_token = access_token.value
        else:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated with broker. Please login first."
            )
        if refresh_token and refresh_token.value:
            broker.refresh_token = refresh_token.value
        
        # Determine quantity (allow override from approval)
        order_quantity = trade_card.quantity
        if approval.quantity and approval.quantity > 0:
            order_quantity = approval.quantity
            # Persist updated quantity on the card for audit consistency
            trade_card.quantity = order_quantity

        # Resolve correct Upstox instrument_key for equity symbol
        instrument_key = None
        try:
            # 1) Prefer local SymbolMaster mapping if available (ISIN)
            from ..database import SymbolMaster
            sym_master = db.query(SymbolMaster).filter(SymbolMaster.symbol == trade_card.symbol).first()
            if sym_master and getattr(sym_master, "isin", None):
                instrument_key = f"NSE_EQ|{sym_master.isin}"

            # 2) If not found, search via Upstox instruments dataset
            if not instrument_key:
                # Try fast search helper
                try:
                    results = await broker.search_instrument(trade_card.symbol, instrument_type="EQ", exchange="NSE")
                    if results:
                        instrument_key = results[0].get("instrument_key") or results[0].get("token") or results[0].get("instrument_token")
                except Exception:
                    pass

            # 3) Fallback: download instruments and match trading_symbol
            if not instrument_key:
                instruments = await broker.get_instruments(exchange="NSE")
                sym_upper = (trade_card.symbol or "").upper()
                candidates = []
                if isinstance(instruments, list):
                    candidates = instruments
                elif isinstance(instruments, dict):
                    for key in ["data", "instruments", "NSE", "nse", "result"]:
                        v = instruments.get(key)
                        if isinstance(v, list):
                            candidates = v
                            break
                    if not candidates:
                        # Some feeds might return a single object; normalize to list
                        candidates = [instruments]
                for inst in candidates:
                    ts = (inst.get("trading_symbol") or inst.get("symbol") or "").upper()
                    if ts == sym_upper:
                        instrument_key = inst.get("instrument_key") or inst.get("token") or inst.get("instrument_token")
                        if instrument_key:
                            break
        except Exception as e:
            logger.warning(f"Failed to resolve instrument key from instruments: {e}")
        
        if not instrument_key:
            # Hard fallback (may not work for all symbols)
            instrument_key = broker._get_instrument_key(trade_card.symbol, "NSE")

        # Compute order parameters from approval or defaults
        desired_order_type = (approval.order_type.value if hasattr(approval.order_type, 'value') else approval.order_type) or "LIMIT"
        desired_order_type = desired_order_type.upper()
        limit_price = approval.price if approval.price and approval.price > 0 else trade_card.entry_price
        trig_price = approval.trigger_price if approval.trigger_price and approval.trigger_price > 0 else None

        # Validate trigger for SL/SL-M
        if desired_order_type in ["SL", "SL-M"] and not trig_price:
            raise HTTPException(status_code=400, detail="trigger_price is required for SL/SL-M orders")

        # If LIMIT price not given or invalid, try LTP
        if desired_order_type == "LIMIT" and (not limit_price or limit_price <= 0):
            try:
                quotes = await broker.get_market_quote_full([instrument_key])
                q = quotes.get(instrument_key, {}) if isinstance(quotes, dict) else {}
                ltp = q.get("last_price") or q.get("ltp") or q.get("last_traded_price")
                if ltp:
                    limit_price = float(ltp)
            except Exception:
                pass

        # Place order with selected type
        try:
            order_response = await broker.place_order(
                symbol=trade_card.symbol,
                transaction_type=trade_card.trade_type,
                quantity=order_quantity,
                order_type=desired_order_type,
                price=limit_price if desired_order_type in ["LIMIT", "SL"] else None,
                trigger_price=trig_price if desired_order_type in ["SL", "SL-M"] else None,
                exchange="NSE",
                product="D",  # Delivery
                instrument_token_override=instrument_key
            )
        except httpx.HTTPStatusError as he:
            if he.response is not None and he.response.status_code == 401:
                # Try token refresh if refresh token available
                if getattr(broker, "refresh_token", None):
                    try:
                        token_data = await broker.refresh_access_token()
                        # Persist new access token
                        if access_token:
                            access_token.value = token_data.get("access_token")
                        else:
                            access_token = Setting(
                                key="upstox_access_token",
                                value=token_data.get("access_token"),
                                description="Upstox access token"
                            )
                            db.add(access_token)
                        # Persist new expiry if provided
                        expires_in = token_data.get("expires_in")
                        if expires_in:
                            expiry_setting = db.query(Setting).filter(
                                Setting.key == "upstox_token_expiry"
                            ).first()
                            expiry_value = (datetime.utcnow() + timedelta(seconds=int(expires_in))).isoformat()
                            if expiry_setting:
                                expiry_setting.value = expiry_value
                            else:
                                expiry_setting = Setting(
                                    key="upstox_token_expiry",
                                    value=expiry_value,
                                    description="Upstox access token expiry (UTC ISO)"
                                )
                                db.add(expiry_setting)
                        db.commit()
                        broker.access_token = token_data.get("access_token")
                        # Retry once
                        order_response = await broker.place_order(
                            symbol=trade_card.symbol,
                            transaction_type=trade_card.trade_type,
                            quantity=order_quantity,
                            order_type="LIMIT",
                            price=trade_card.entry_price,
                            exchange="NSE",
                            product="D",
                            instrument_token_override=instrument_key
                        )
                    except Exception:
                        raise HTTPException(
                            status_code=401,
                            detail="Broker authentication expired. Please login again."
                        )
                else:
                    raise HTTPException(
                        status_code=401,
                        detail="Broker authentication required. Please login."
                    )
            else:
                # Surface broker error details; attempt fallback for price-required errors
                detail = None
                try:
                    detail = he.response.json()
                except Exception:
                    detail = he.response.text if he.response is not None else str(he)

                # Check for specific errors
                try:
                    err_list = (detail or {}).get("errors", []) if isinstance(detail, dict) else []
                    needs_price = any((e.get("errorCode") == "UDAPI1008" or e.get("error_code") == "UDAPI1008") for e in err_list)
                    needs_trigger = any((e.get("errorCode") == "UDAPI1036" or e.get("error_code") == "UDAPI1036") for e in err_list)
                except Exception:
                    needs_price = False
                    needs_trigger = False

                if needs_price and desired_order_type in ["LIMIT", "SL"]:
                    # Fetch LTP and retry as LIMIT with that price (or SL with price)
                    try:
                        quotes = await broker.get_market_quote_full([instrument_key])
                        q = quotes.get(instrument_key, {}) if isinstance(quotes, dict) else {}
                        ltp = q.get("last_price") or q.get("ltp") or q.get("last_traded_price")
                        if not ltp:
                            raise Exception("No LTP available")
                        order_response = await broker.place_order(
                            symbol=trade_card.symbol,
                            transaction_type=trade_card.trade_type,
                            quantity=order_quantity,
                            order_type=desired_order_type,
                            price=float(ltp),
                            exchange="NSE",
                            product="D",
                            instrument_token_override=instrument_key
                        )
                    except Exception:
                        raise HTTPException(status_code=400, detail=str(detail))
                elif needs_trigger:
                    # Do not convert to SL automatically; surface error for user to choose SL/SL-M
                    raise HTTPException(status_code=400, detail=str(detail))
                else:
                    raise HTTPException(status_code=he.response.status_code if he.response else 500, detail=str(detail))
        
        broker_order_id = order_response.get("data", {}).get("order_id")
        
        # Create order record
        order = Order(
            trade_card_id=trade_card.id,
            broker_order_id=broker_order_id,
            symbol=trade_card.symbol,
            exchange="NSE",
            order_type=desired_order_type,
            transaction_type=trade_card.trade_type,
            quantity=order_quantity,
            price=(limit_price if desired_order_type in ["LIMIT", "SL"] else None),
            status="placed"
        )
        
        db.add(order)
        trade_card.status = "executed"
        db.commit()
        db.refresh(order)
        
        # Log order placement
        audit_logger.log_order_placed(
            order_id=order.id,
            trade_card_id=trade_card.id,
            order_payload={
                "symbol": trade_card.symbol,
                "quantity": trade_card.quantity,
                "price": trade_card.entry_price
            },
            broker_response=order_response
        )
        
        logger.info(f"Order placed for trade card {trade_card.id}: {broker_order_id}")
        
        return order
        
    except HTTPException:
        # Propagate explicit HTTP errors (e.g., 401 auth required)
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error approving trade card: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{trade_card_id}/reject")
async def reject_trade_card(
    trade_card_id: int,
    rejection: TradeCardRejection,
    db: Session = Depends(get_db)
):
    """Reject a trade card."""
    # Get trade card
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    if trade_card.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Trade card status is {trade_card.status}, cannot reject"
        )
    
    try:
        # Initialize audit logger
        audit_logger = AuditLogger(db)
        
        # Create snapshot
        trade_card_snapshot = {
            "id": trade_card.id,
            "symbol": trade_card.symbol,
            "confidence": trade_card.confidence
        }
        
        # Log rejection
        audit_logger.log_trade_card_rejected(
            trade_card_id=trade_card.id,
            user_id=rejection.user_id,
            reason=rejection.reason,
            trade_card_snapshot=trade_card_snapshot
        )
        
        # Update trade card
        trade_card.status = "rejected"
        trade_card.rejected_at = datetime.utcnow()
        trade_card.rejection_reason = rejection.reason
        
        db.commit()
        
        logger.info(f"Trade card {trade_card.id} rejected: {rejection.reason}")
        
        return {"status": "rejected", "trade_card_id": trade_card.id}
        
    except Exception as e:
        logger.error(f"Error rejecting trade card: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{trade_card_id}/risk-summary")
async def get_risk_summary(
    trade_card_id: int,
    db: Session = Depends(get_db)
):
    """Get risk summary for a trade card."""
    trade_card = db.query(TradeCard).filter(TradeCard.id == trade_card_id).first()
    
    if not trade_card:
        raise HTTPException(status_code=404, detail="Trade card not found")
    
    risk_checker = RiskChecker(db)
    risk_summary = risk_checker.get_risk_summary(trade_card)
    
    return risk_summary

