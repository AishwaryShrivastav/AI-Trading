"""Audit logging service."""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from ..database import AuditLog

logger = logging.getLogger(__name__)


class AuditLogger:
    """Service for creating immutable audit logs."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def log(
        self,
        action_type: str,
        user_id: str = "system",
        trade_card_id: Optional[int] = None,
        order_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        meta_data: Optional[Dict[str, Any]] = None,
        model_version: Optional[str] = None,
        strategy_version: Optional[str] = None
    ) -> AuditLog:
        """
        Create an audit log entry.
        
        Args:
            action_type: Type of action (e.g., 'trade_card_created', 'order_placed')
            user_id: User who performed the action
            trade_card_id: Related trade card ID
            order_id: Related order ID
            payload: Full snapshot of relevant data
            meta_data: Additional context (IP, user agent, etc.)
            model_version: LLM model version if applicable
            strategy_version: Strategy version if applicable
            
        Returns:
            Created AuditLog instance
        """
        try:
            audit_log = AuditLog(
                action_type=action_type,
                user_id=user_id,
                trade_card_id=trade_card_id,
                order_id=order_id,
                payload=payload or {},
                meta_data=meta_data or {},
                model_version=model_version,
                strategy_version=strategy_version,
                timestamp=datetime.utcnow()
            )
            
            self.db.add(audit_log)
            self.db.commit()
            self.db.refresh(audit_log)
            
            logger.info(
                f"Audit log created: {action_type} "
                f"(trade_card={trade_card_id}, order={order_id})"
            )
            
            return audit_log
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            self.db.rollback()
            raise
    
    def log_trade_card_created(
        self,
        trade_card_id: int,
        trade_card_data: Dict[str, Any],
        signal_data: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        risk_checks: Dict[str, Any]
    ):
        """Log trade card creation with full context."""
        return self.log(
            action_type="trade_card_created",
            trade_card_id=trade_card_id,
            payload={
                "trade_card": trade_card_data,
                "signal": signal_data,
                "llm_analysis": llm_analysis,
                "risk_checks": risk_checks
            },
            model_version=llm_analysis.get("model_version"),
            strategy_version=signal_data.get("strategy")
        )
    
    def log_trade_card_approved(
        self,
        trade_card_id: int,
        user_id: str,
        trade_card_snapshot: Dict[str, Any],
        notes: Optional[str] = None
    ):
        """Log trade card approval."""
        return self.log(
            action_type="trade_card_approved",
            user_id=user_id,
            trade_card_id=trade_card_id,
            payload={
                "trade_card_snapshot": trade_card_snapshot,
                "notes": notes
            }
        )
    
    def log_trade_card_rejected(
        self,
        trade_card_id: int,
        user_id: str,
        reason: str,
        trade_card_snapshot: Dict[str, Any]
    ):
        """Log trade card rejection."""
        return self.log(
            action_type="trade_card_rejected",
            user_id=user_id,
            trade_card_id=trade_card_id,
            payload={
                "trade_card_snapshot": trade_card_snapshot,
                "reason": reason
            }
        )
    
    def log_order_placed(
        self,
        order_id: int,
        trade_card_id: int,
        order_payload: Dict[str, Any],
        broker_response: Dict[str, Any]
    ):
        """Log order placement."""
        return self.log(
            action_type="order_placed",
            trade_card_id=trade_card_id,
            order_id=order_id,
            payload={
                "order": order_payload,
                "broker_response": broker_response
            }
        )
    
    def log_order_filled(
        self,
        order_id: int,
        trade_card_id: int,
        fill_details: Dict[str, Any]
    ):
        """Log order fill."""
        return self.log(
            action_type="order_filled",
            trade_card_id=trade_card_id,
            order_id=order_id,
            payload=fill_details
        )
    
    def log_signal_generation(
        self,
        strategy: str,
        signals_count: int,
        symbols_scanned: int,
        trade_cards_created: int,
        meta_data: Optional[Dict[str, Any]] = None
    ):
        """Log signal generation run."""
        return self.log(
            action_type="signal_generation",
            payload={
                "strategy": strategy,
                "signals_count": signals_count,
                "symbols_scanned": symbols_scanned,
                "trade_cards_created": trade_cards_created
            },
            meta_data=meta_data,
            strategy_version=strategy
        )
    
    def get_audit_trail(
        self,
        trade_card_id: Optional[int] = None,
        order_id: Optional[int] = None,
        action_type: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        Retrieve audit trail with filters.
        
        Args:
            trade_card_id: Filter by trade card
            order_id: Filter by order
            action_type: Filter by action type
            limit: Maximum records to return
            
        Returns:
            List of AuditLog instances
        """
        query = self.db.query(AuditLog)
        
        if trade_card_id:
            query = query.filter(AuditLog.trade_card_id == trade_card_id)
        
        if order_id:
            query = query.filter(AuditLog.order_id == order_id)
        
        if action_type:
            query = query.filter(AuditLog.action_type == action_type)
        
        return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

