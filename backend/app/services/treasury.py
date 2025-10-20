"""Treasury - Capital choreography and cash management."""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from ..database import Account, FundingPlan, CapitalTransaction, PositionV2
from ..schemas import AccountType

logger = logging.getLogger(__name__)


class Treasury:
    """
    Manages capital across accounts:
    - Tracks deployable cash per account
    - Handles SIP installments
    - Manages lump-sum tranches
    - Proposes inter-account transfers
    - Enforces buffers and carry-forward rules
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def process_sip_installment(
        self,
        account_id: int
    ) -> Dict[str, Any]:
        """
        Process monthly/weekly SIP installment.
        
        Adds SIP amount to available cash if it's time for installment.
        
        Returns:
            Dict with installment info
        """
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if not funding_plan or funding_plan.funding_type != "SIP":
            return {"processed": False, "reason": "Not a SIP account"}
        
        # Check if installment is due
        # Simplified: Add installment (in production, check actual schedule)
        if funding_plan.sip_amount and funding_plan.sip_amount > 0:
            # Add installment
            funding_plan.available_cash += funding_plan.sip_amount
            
            # Record transaction
            transaction = CapitalTransaction(
                account_id=account_id,
                transaction_type="DEPOSIT",
                amount=funding_plan.sip_amount,
                reason=f"SIP installment - {funding_plan.sip_frequency}",
                approved_by="system"
            )
            
            self.db.add(transaction)
            self.db.commit()
            
            logger.info(f"Processed SIP installment: ₹{funding_plan.sip_amount} for account {account_id}")
            
            return {
                "processed": True,
                "amount": funding_plan.sip_amount,
                "new_available_cash": funding_plan.available_cash
            }
        
        return {"processed": False, "reason": "No SIP amount configured"}
    
    async def release_next_tranche(
        self,
        account_id: int
    ) -> Dict[str, Any]:
        """
        Release next tranche for lump-sum accounts.
        
        Returns:
            Dict with tranche info
        """
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if not funding_plan or funding_plan.funding_type not in ["LUMP_SUM", "HYBRID"]:
            return {"released": False, "reason": "Not a lump-sum account"}
        
        if not funding_plan.tranche_plan:
            return {"released": False, "reason": "No tranche plan configured"}
        
        # Find next unreleased tranche
        # Simplified: Release next based on time/conditions
        # In production, track which tranches are released
        
        total_lump_sum = funding_plan.lump_sum_amount or 0
        current_available = funding_plan.available_cash
        
        # For demo, release if available cash is low
        utilization = funding_plan.total_deployed / total_lump_sum if total_lump_sum > 0 else 0
        
        if utilization > 0.8 and current_available < (total_lump_sum * 0.1):
            # Release next tranche (simplified)
            tranche_amount = total_lump_sum * 0.33  # 33% tranche
            
            if funding_plan.available_cash + tranche_amount <= total_lump_sum:
                funding_plan.available_cash += tranche_amount
                
                transaction = CapitalTransaction(
                    account_id=account_id,
                    transaction_type="DEPOSIT",
                    amount=tranche_amount,
                    reason="Tranche release - staged deployment",
                    approved_by="system"
                )
                
                self.db.add(transaction)
                self.db.commit()
                
                logger.info(f"Released tranche: ₹{tranche_amount} for account {account_id}")
                
                return {
                    "released": True,
                    "amount": tranche_amount,
                    "new_available_cash": funding_plan.available_cash
                }
        
        return {"released": False, "reason": "Tranche conditions not met"}
    
    async def get_deployable_cash(
        self,
        account_id: int
    ) -> float:
        """
        Get deployable cash for an account.
        
        Returns:
            Available cash minus emergency buffer
        """
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if not funding_plan:
            return 0.0
        
        # Apply emergency buffer
        total_available = funding_plan.available_cash
        buffer_percent = funding_plan.emergency_buffer_percent or 5.0
        buffer_amount = total_available * (buffer_percent / 100)
        
        deployable = total_available - buffer_amount
        
        return max(0.0, deployable)
    
    async def reserve_cash(
        self,
        account_id: int,
        amount: float
    ) -> bool:
        """
        Reserve cash for pending orders.
        
        Returns:
            True if reservation successful
        """
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if not funding_plan:
            return False
        
        if funding_plan.available_cash >= amount:
            funding_plan.available_cash -= amount
            funding_plan.reserved_cash += amount
            self.db.commit()
            
            logger.info(f"Reserved ₹{amount} for account {account_id}")
            return True
        
        return False
    
    async def release_reservation(
        self,
        account_id: int,
        amount: float
    ):
        """Release reserved cash (order cancelled/rejected)."""
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if funding_plan:
            funding_plan.reserved_cash -= amount
            funding_plan.available_cash += amount
            self.db.commit()
            
            logger.info(f"Released ₹{amount} reservation for account {account_id}")
    
    async def deploy_cash(
        self,
        account_id: int,
        amount: float
    ):
        """Move cash from reserved to deployed (order filled)."""
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if funding_plan:
            funding_plan.reserved_cash -= amount
            funding_plan.total_deployed += amount
            self.db.commit()
            
            logger.info(f"Deployed ₹{amount} for account {account_id}")
    
    async def return_cash(
        self,
        account_id: int,
        amount: float
    ):
        """Return cash from deployed to available (position closed)."""
        funding_plan = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == account_id
        ).first()
        
        if funding_plan:
            funding_plan.total_deployed -= amount
            funding_plan.available_cash += amount
            self.db.commit()
            
            logger.info(f"Returned ₹{amount} to available cash for account {account_id}")
    
    async def propose_inter_account_transfer(
        self,
        from_account_id: int,
        to_account_id: int,
        amount: float,
        reason: str
    ) -> Dict[str, Any]:
        """
        Propose inter-account capital transfer.
        
        Returns:
            Proposal dict requiring user approval
        """
        # Get both accounts
        from_account = self.db.query(Account).filter(Account.id == from_account_id).first()
        to_account = self.db.query(Account).filter(Account.id == to_account_id).first()
        
        if not from_account or not to_account:
            return {"valid": False, "reason": "Account not found"}
        
        # Check available cash
        from_funding = self.db.query(FundingPlan).filter(
            FundingPlan.account_id == from_account_id
        ).first()
        
        if not from_funding or from_funding.available_cash < amount:
            return {
                "valid": False,
                "reason": "Insufficient cash in source account"
            }
        
        return {
            "valid": True,
            "from_account": from_account.name,
            "to_account": to_account.name,
            "amount": amount,
            "reason": reason,
            "requires_approval": True,
            "proposal_type": "INTER_ACCOUNT_TRANSFER"
        }
    
    async def execute_transfer(
        self,
        from_account_id: int,
        to_account_id: int,
        amount: float,
        reason: str,
        approved_by: str
    ) -> bool:
        """
        Execute approved inter-account transfer.
        
        Returns:
            True if successful
        """
        try:
            # Get funding plans
            from_funding = self.db.query(FundingPlan).filter(
                FundingPlan.account_id == from_account_id
            ).first()
            
            to_funding = self.db.query(FundingPlan).filter(
                FundingPlan.account_id == to_account_id
            ).first()
            
            if not from_funding or not to_funding:
                return False
            
            if from_funding.available_cash < amount:
                return False
            
            # Execute transfer
            from_funding.available_cash -= amount
            to_funding.available_cash += amount
            
            # Record transactions
            out_transaction = CapitalTransaction(
                account_id=from_account_id,
                transaction_type="TRANSFER_OUT",
                amount=amount,
                to_account_id=to_account_id,
                reason=reason,
                approved_by=approved_by
            )
            
            in_transaction = CapitalTransaction(
                account_id=to_account_id,
                transaction_type="TRANSFER_IN",
                amount=amount,
                from_account_id=from_account_id,
                reason=reason,
                approved_by=approved_by
            )
            
            self.db.add(out_transaction)
            self.db.add(in_transaction)
            self.db.commit()
            
            logger.info(f"Transferred ₹{amount} from account {from_account_id} to {to_account_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error executing transfer: {e}")
            return False
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get portfolio-wide capital summary.
        
        Returns:
            Aggregated capital across all accounts
        """
        all_funding = self.db.query(FundingPlan).all()
        
        total_available = sum(fp.available_cash for fp in all_funding)
        total_deployed = sum(fp.total_deployed for fp in all_funding)
        total_reserved = sum(fp.reserved_cash for fp in all_funding)
        
        total_capital = total_available + total_deployed + total_reserved
        
        return {
            "total_capital": total_capital,
            "total_available": total_available,
            "total_deployed": total_deployed,
            "total_reserved": total_reserved,
            "utilization_percent": (total_deployed / total_capital * 100) if total_capital > 0 else 0,
            "accounts_count": len(all_funding)
        }

