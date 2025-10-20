"""Intake Agent - Conversational mandate and funding plan capture using LLM."""
import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from ..schemas import (
    AccountType, Objective, FundingType, SIPFrequency,
    IntakeQuestion, IntakeAnswer, IntakeSessionResponse,
    MandateCreate, FundingPlanCreate
)

logger = logging.getLogger(__name__)


class IntakeAgent:
    """
    Conversational agent that captures trading mandate and funding plan
    through 6-8 targeted questions.
    
    Uses LLM to:
    1. Ask relevant questions based on account type
    2. Validate and interpret answers
    3. Generate a mandate + funding plan
    4. Create a one-paragraph summary for confirmation
    """
    
    # Question templates for different account types
    QUESTIONS = {
        "common": [
            {
                "id": "objective",
                "text": "What's your primary trading objective for this account?",
                "field": "objective",
                "options": ["MAX_PROFIT", "RISK_MINIMIZED", "BALANCED"],
                "validation": "choice",
                "help": "MAX_PROFIT: Aggressive growth, RISK_MINIMIZED: Capital preservation, BALANCED: Moderate approach"
            },
            {
                "id": "risk_per_trade",
                "text": "What's the maximum % of capital you're comfortable risking per trade?",
                "field": "risk_per_trade_percent",
                "validation": "number",
                "default": 1.5,
                "help": "Typical range: 0.5% (conservative) to 2% (aggressive). We recommend 1-1.5%."
            },
            {
                "id": "max_positions",
                "text": "How many open positions would you like to maintain simultaneously?",
                "field": "max_positions",
                "validation": "number",
                "default": 10,
                "help": "More positions = more diversification but requires more monitoring."
            },
            {
                "id": "horizon",
                "text": "What's your preferred holding period for trades (in days)?",
                "field": "horizon",
                "validation": "range",
                "default": "3-7",
                "help": "Enter as min-max days, e.g., '1-7' for swing trading"
            },
            {
                "id": "sector_restrictions",
                "text": "Are there any sectors you want to avoid? (comma-separated, or 'none')",
                "field": "banned_sectors",
                "validation": "list",
                "default": "none",
                "help": "Example: 'banking,pharma' or 'none' for no restrictions"
            },
            {
                "id": "liquidity",
                "text": "What's your minimum liquidity requirement (average daily volume)?",
                "field": "liquidity_floor_adv",
                "validation": "number",
                "default": 1000000,
                "help": "Higher = more liquid stocks. Recommended: 1M+ for smooth entry/exit"
            }
        ],
        "SIP": [
            {
                "id": "sip_amount",
                "text": "How much will you invest per installment?",
                "field": "sip_amount",
                "validation": "number",
                "help": "Enter amount in rupees, e.g., 10000 for ₹10,000"
            },
            {
                "id": "sip_frequency",
                "text": "How often will you invest?",
                "field": "sip_frequency",
                "options": ["MONTHLY", "WEEKLY", "FORTNIGHTLY"],
                "validation": "choice",
                "default": "MONTHLY"
            },
            {
                "id": "sip_duration",
                "text": "For how many months do you plan to continue this SIP?",
                "field": "sip_duration_months",
                "validation": "number",
                "default": 24,
                "help": "Enter number of months, e.g., 24 for 2 years"
            }
        ],
        "LUMP_SUM": [
            {
                "id": "lump_sum_amount",
                "text": "What's the total lump sum amount you're investing?",
                "field": "lump_sum_amount",
                "validation": "number",
                "help": "Enter total amount in rupees"
            },
            {
                "id": "tranche_strategy",
                "text": "How do you want to deploy this capital?",
                "field": "tranche_strategy",
                "options": ["ALL_AT_ONCE", "STAGED_33_33_33", "STAGED_50_50", "CUSTOM"],
                "validation": "choice",
                "default": "STAGED_33_33_33",
                "help": "STAGED deployment reduces timing risk by spreading entries"
            }
        ],
        "EVENT_TACTICAL": [
            {
                "id": "event_capital",
                "text": "How much capital are you allocating for event-driven opportunities?",
                "field": "lump_sum_amount",
                "validation": "number",
                "help": "This capital will be deployed opportunistically on high-conviction events"
            },
            {
                "id": "event_horizon",
                "text": "What's your typical holding period for event trades (in days)?",
                "field": "horizon",
                "validation": "range",
                "default": "1-5",
                "help": "Event trades typically short-term (1-5 days)"
            }
        ]
    }
    
    def __init__(self):
        """Initialize Intake Agent."""
        # Active sessions: {session_id: session_data}
        self.sessions: Dict[str, Dict[str, Any]] = {}
    
    def start_session(
        self,
        account_name: str,
        account_type: AccountType,
        user_id: str = "default_user"
    ) -> IntakeSessionResponse:
        """
        Start a new intake session.
        
        Args:
            account_name: Name for the account (e.g., "SIP—Aggressive (24m)")
            account_type: Type of account (SIP, LUMP_SUM, EVENT_TACTICAL)
            user_id: User identifier
            
        Returns:
            IntakeSessionResponse with first question
        """
        session_id = str(uuid.uuid4())
        
        # Build question list based on account type
        questions = self.QUESTIONS["common"].copy()
        if account_type.value in self.QUESTIONS:
            questions.extend(self.QUESTIONS[account_type.value])
        
        session_data = {
            "session_id": session_id,
            "account_name": account_name,
            "account_type": account_type,
            "user_id": user_id,
            "questions": questions,
            "current_index": 0,
            "answers": {},
            "assumption_log": {},
            "created_at": datetime.utcnow()
        }
        
        self.sessions[session_id] = session_data
        
        # Return first question
        return self._build_response(session_id)
    
    def answer_question(
        self,
        session_id: str,
        answer: IntakeAnswer
    ) -> IntakeSessionResponse:
        """
        Process an answer and return next question or completion.
        
        Args:
            session_id: Active session ID
            answer: User's answer to current question
            
        Returns:
            IntakeSessionResponse with next question or completion status
        """
        if session_id not in self.sessions:
            raise ValueError(f"Invalid session ID: {session_id}")
        
        session = self.sessions[session_id]
        current_q = session["questions"][session["current_index"]]
        
        # Validate and store answer
        validated_answer = self._validate_answer(current_q, answer.answer)
        session["answers"][current_q["field"]] = validated_answer
        
        # Log assumption
        session["assumption_log"][current_q["field"]] = {
            "question": current_q["text"],
            "answer": validated_answer,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Move to next question
        session["current_index"] += 1
        
        return self._build_response(session_id)
    
    def generate_mandate_and_plan(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Generate mandate and funding plan from collected answers.
        
        Args:
            session_id: Completed session ID
            
        Returns:
            Dict with mandate_data, funding_plan_data, and summary
        """
        if session_id not in self.sessions:
            raise ValueError(f"Invalid session ID: {session_id}")
        
        session = self.sessions[session_id]
        answers = session["answers"]
        account_type = session["account_type"]
        
        # Build mandate
        horizon_range = answers.get("horizon", "3-7").split("-")
        mandate_data = {
            "objective": answers.get("objective", "BALANCED"),
            "risk_per_trade_percent": float(answers.get("risk_per_trade_percent", 1.5)),
            "max_positions": int(answers.get("max_positions", 10)),
            "max_sector_exposure_percent": 30.0,  # Standard
            "horizon_min_days": int(horizon_range[0]),
            "horizon_max_days": int(horizon_range[1]) if len(horizon_range) > 1 else int(horizon_range[0]),
            "banned_sectors": self._parse_sectors(answers.get("banned_sectors", "none")),
            "earnings_blackout_days": 2,
            "liquidity_floor_adv": float(answers.get("liquidity_floor_adv", 1000000)),
            "min_market_cap": 100.0,
            "allowed_strategies": ["momentum", "mean_reversion", "event_driven"],
            "sl_multiplier": 2.0,
            "tp_multiplier": 4.0,
            "trailing_stop_enabled": False,
            "assumption_log": session["assumption_log"],
            "summary": self._generate_summary(session)
        }
        
        # Build funding plan
        funding_plan_data = {
            "funding_type": account_type.value
        }
        
        if account_type == AccountType.SIP:
            funding_plan_data.update({
                "sip_amount": float(answers.get("sip_amount", 10000)),
                "sip_frequency": answers.get("sip_frequency", "MONTHLY"),
                "sip_start_date": datetime.utcnow(),
                "sip_duration_months": int(answers.get("sip_duration_months", 24)),
                "carry_forward_enabled": True,
                "max_carry_forward_percent": 20.0,
                "emergency_buffer_percent": 5.0
            })
            # Initialize with first installment
            funding_plan_data["available_cash"] = funding_plan_data["sip_amount"]
        
        elif account_type == AccountType.LUMP_SUM:
            lump_sum = float(answers.get("lump_sum_amount", 100000))
            tranche_strategy = answers.get("tranche_strategy", "STAGED_33_33_33")
            
            funding_plan_data.update({
                "lump_sum_amount": lump_sum,
                "lump_sum_date": datetime.utcnow(),
                "tranche_plan": self._build_tranche_plan(lump_sum, tranche_strategy),
                "carry_forward_enabled": True,
                "max_carry_forward_percent": 20.0,
                "emergency_buffer_percent": 5.0
            })
            # First tranche available immediately
            first_tranche_percent = self._get_first_tranche_percent(tranche_strategy)
            funding_plan_data["available_cash"] = lump_sum * (first_tranche_percent / 100)
        
        elif account_type == AccountType.EVENT_TACTICAL:
            event_capital = float(answers.get("lump_sum_amount", 50000))
            funding_plan_data.update({
                "lump_sum_amount": event_capital,
                "lump_sum_date": datetime.utcnow(),
                "tranche_plan": [{"percent": 100, "trigger": "event_based"}],
                "carry_forward_enabled": True,
                "max_carry_forward_percent": 50.0,  # Higher for event trading
                "emergency_buffer_percent": 10.0
            })
            funding_plan_data["available_cash"] = event_capital
        
        return {
            "mandate_data": mandate_data,
            "funding_plan_data": funding_plan_data,
            "summary": mandate_data["summary"]
        }
    
    def _validate_answer(self, question: Dict[str, Any], answer: Any) -> Any:
        """Validate answer based on question type."""
        validation_type = question.get("validation", "text")
        
        if validation_type == "choice":
            options = question.get("options", [])
            if answer not in options:
                # Try to match case-insensitively
                answer_upper = str(answer).upper()
                for opt in options:
                    if opt.upper() == answer_upper:
                        return opt
                raise ValueError(f"Answer must be one of: {', '.join(options)}")
            return answer
        
        elif validation_type == "number":
            try:
                return float(answer)
            except (ValueError, TypeError):
                raise ValueError("Answer must be a number")
        
        elif validation_type == "range":
            # Expected format: "min-max" or single number
            answer_str = str(answer)
            if "-" in answer_str:
                parts = answer_str.split("-")
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    return answer_str.strip()
            elif answer_str.strip().isdigit():
                return answer_str.strip()
            raise ValueError("Answer must be a range like '3-7' or single number like '5'")
        
        elif validation_type == "list":
            if answer.lower() == "none":
                return []
            return [item.strip() for item in str(answer).split(",") if item.strip()]
        
        elif validation_type == "boolean":
            if isinstance(answer, bool):
                return answer
            answer_lower = str(answer).lower()
            if answer_lower in ["true", "yes", "y", "1"]:
                return True
            elif answer_lower in ["false", "no", "n", "0"]:
                return False
            raise ValueError("Answer must be yes/no or true/false")
        
        # Default: text
        return str(answer)
    
    def _parse_sectors(self, sectors_input: Any) -> List[str]:
        """Parse sectors from user input."""
        if isinstance(sectors_input, list):
            return sectors_input
        if str(sectors_input).lower() == "none":
            return []
        return [s.strip().lower() for s in str(sectors_input).split(",") if s.strip()]
    
    def _build_tranche_plan(self, total: float, strategy: str) -> List[Dict[str, Any]]:
        """Build tranche deployment plan."""
        if strategy == "ALL_AT_ONCE":
            return [{"percent": 100, "trigger": "immediate", "delay_days": 0}]
        elif strategy == "STAGED_33_33_33":
            return [
                {"percent": 33, "trigger": "immediate", "delay_days": 0},
                {"percent": 33, "trigger": "time_based", "delay_days": 7},
                {"percent": 34, "trigger": "time_based", "delay_days": 14}
            ]
        elif strategy == "STAGED_50_50":
            return [
                {"percent": 50, "trigger": "immediate", "delay_days": 0},
                {"percent": 50, "trigger": "time_based", "delay_days": 7}
            ]
        else:  # CUSTOM - default to 33/33/33
            return [
                {"percent": 33, "trigger": "immediate", "delay_days": 0},
                {"percent": 33, "trigger": "time_based", "delay_days": 7},
                {"percent": 34, "trigger": "time_based", "delay_days": 14}
            ]
    
    def _get_first_tranche_percent(self, strategy: str) -> float:
        """Get first tranche percentage from strategy."""
        if strategy == "ALL_AT_ONCE":
            return 100.0
        elif strategy == "STAGED_50_50":
            return 50.0
        else:  # STAGED_33_33_33 or others
            return 33.0
    
    def _generate_summary(self, session: Dict[str, Any]) -> str:
        """Generate one-paragraph summary of the mandate for user confirmation."""
        answers = session["answers"]
        account_type = session["account_type"].value
        account_name = session["account_name"]
        
        objective_map = {
            "MAX_PROFIT": "maximize returns with aggressive positioning",
            "RISK_MINIMIZED": "minimize risk with conservative approach",
            "BALANCED": "balance risk and reward"
        }
        
        objective = answers.get("objective", "BALANCED")
        risk_per_trade = answers.get("risk_per_trade_percent", 1.5)
        max_positions = answers.get("max_positions", 10)
        horizon = answers.get("horizon", "3-7")
        
        summary_parts = [
            f"For your {account_name} ({account_type} account),",
            f"we'll {objective_map.get(objective, 'balance risk and reward')}",
            f"by risking up to {risk_per_trade}% per trade",
            f"across a maximum of {max_positions} positions,",
            f"with a typical holding period of {horizon} days."
        ]
        
        # Add funding details
        if account_type == "SIP":
            sip_amount = answers.get("sip_amount", 10000)
            sip_freq = answers.get("sip_frequency", "MONTHLY")
            sip_duration = answers.get("sip_duration_months", 24)
            summary_parts.append(
                f"You'll invest ₹{sip_amount:,.0f} {sip_freq.lower()}"
                f" for {sip_duration} months."
            )
        elif account_type == "LUMP_SUM":
            lump_sum = answers.get("lump_sum_amount", 100000)
            tranche = answers.get("tranche_strategy", "STAGED_33_33_33")
            if tranche == "ALL_AT_ONCE":
                summary_parts.append(f"Your ₹{lump_sum:,.0f} will be deployed immediately.")
            else:
                summary_parts.append(
                    f"Your ₹{lump_sum:,.0f} will be deployed in tranches"
                    f" to reduce timing risk."
                )
        elif account_type == "EVENT_TACTICAL":
            event_capital = answers.get("lump_sum_amount", 50000)
            summary_parts.append(
                f"Your ₹{event_capital:,.0f} will be deployed opportunistically"
                f" on high-conviction events."
            )
        
        # Add restrictions
        banned_sectors = self._parse_sectors(answers.get("banned_sectors", "none"))
        if banned_sectors:
            summary_parts.append(
                f"We'll avoid {', '.join(banned_sectors)} sectors."
            )
        
        summary_parts.append(
            "All trades will require your explicit approval before execution."
        )
        
        return " ".join(summary_parts)
    
    def _build_response(self, session_id: str) -> IntakeSessionResponse:
        """Build response with current question or completion status."""
        session = self.sessions[session_id]
        questions = session["questions"]
        current_index = session["current_index"]
        
        is_complete = current_index >= len(questions)
        
        if is_complete:
            # Session complete
            return IntakeSessionResponse(
                session_id=session_id,
                account_name=session["account_name"],
                account_type=session["account_type"],
                current_question=IntakeQuestion(
                    question_id="complete",
                    question_text="All questions answered! Review and confirm your mandate.",
                    field_name="complete",
                    validation_type="text"
                ),
                answers_collected=len(session["answers"]),
                total_questions=len(questions),
                is_complete=True
            )
        
        # Build current question
        q = questions[current_index]
        current_question = IntakeQuestion(
            question_id=q["id"],
            question_text=q["text"],
            field_name=q["field"],
            options=q.get("options"),
            validation_type=q.get("validation", "text"),
            default_value=q.get("default")
        )
        
        return IntakeSessionResponse(
            session_id=session_id,
            account_name=session["account_name"],
            account_type=session["account_type"],
            current_question=current_question,
            answers_collected=len(session["answers"]),
            total_questions=len(questions),
            is_complete=False
        )
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data."""
        return self.sessions.get(session_id)
    
    def clear_session(self, session_id: str):
        """Clear completed session."""
        if session_id in self.sessions:
            del self.sessions[session_id]


# Singleton instance
intake_agent = IntakeAgent()

