"""Indian equity cost model + net-edge gate (TradeHarness Step 4b).

Estimates the all-in round-trip cost of a trade (brokerage, STT, exchange
transaction charges, GST, SEBI fee, stamp duty, slippage) and gates trades whose
expected move to target does not beat those costs by ``min_net_edge_pct``.

Rates are approximations of the NSE equity regime (configurable); the goal is a
conservative floor so the system never trades itself into negative net returns.
"""
from dataclasses import dataclass
from typing import Any, Dict

# Default rate card (fractions of turnover unless noted).
BROKERAGE_PCT = 0.0003     # 0.03% per executed order
BROKERAGE_MAX = 20.0       # ₹20 per order cap
STT_DELIVERY = 0.001       # 0.1% on buy + sell (delivery)
STT_INTRADAY_SELL = 0.00025  # 0.025% on sell side (intraday)
EXCH_TXN_PCT = 0.0000297   # NSE transaction charge
SEBI_PCT = 0.000001        # SEBI turnover fee
STAMP_BUY_PCT = 0.00015    # stamp duty on buy side
GST_PCT = 0.18             # GST on (brokerage + exchange txn)


@dataclass
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_txn: float
    gst: float
    sebi: float
    stamp: float
    slippage: float
    total: float

    def to_dict(self) -> Dict[str, Any]:
        return {k: round(v, 2) for k, v in self.__dict__.items()}


def round_trip_cost(
    entry: float,
    exit_price: float,
    quantity: int,
    segment: str = "delivery",
    slippage_bps: float = 5.0,
) -> CostBreakdown:
    """All-in cost (INR) of entering and exiting one position."""
    buy_val = entry * quantity
    sell_val = exit_price * quantity
    turnover = buy_val + sell_val

    brokerage = min(BROKERAGE_PCT * buy_val, BROKERAGE_MAX) + min(BROKERAGE_PCT * sell_val, BROKERAGE_MAX)
    if segment == "intraday":
        stt = STT_INTRADAY_SELL * sell_val
    else:
        stt = STT_DELIVERY * turnover
    exch = EXCH_TXN_PCT * turnover
    gst = GST_PCT * (brokerage + exch)
    sebi = SEBI_PCT * turnover
    stamp = STAMP_BUY_PCT * buy_val
    slippage = (slippage_bps / 10_000.0) * turnover  # entry + exit slip approximated on turnover

    total = brokerage + stt + exch + gst + sebi + stamp + slippage
    return CostBreakdown(brokerage, stt, exch, gst, sebi, stamp, slippage, total)


def cost_pct(entry: float, exit_price: float, quantity: int, segment: str = "delivery",
             slippage_bps: float = 5.0) -> float:
    """Round-trip cost as a percentage of entry notional."""
    notional = entry * quantity
    if notional <= 0:
        return float("inf")
    return round_trip_cost(entry, exit_price, quantity, segment, slippage_bps).total / notional * 100.0


def passes_cost_gate(
    entry: float,
    take_profit: float,
    quantity: int,
    side: str = "BUY",
    segment: str = "delivery",
    min_net_edge_pct: float = 0.5,
    slippage_bps: float = 5.0,
) -> Dict[str, Any]:
    """Does the expected move to target beat round-trip costs by the min edge?

    Returns a dict with ``passed`` plus the breakdown (reward%, cost%, net edge%).
    """
    if not entry or entry <= 0 or not quantity or quantity <= 0:
        return {"passed": False, "reason": "invalid_inputs", "reward_pct": 0, "cost_pct": 0, "net_edge_pct": 0}

    reward_pct = abs(take_profit - entry) / entry * 100.0
    c_pct = cost_pct(entry, take_profit, quantity, segment, slippage_bps)
    net_edge = reward_pct - c_pct
    return {
        "passed": net_edge >= min_net_edge_pct,
        "reward_pct": round(reward_pct, 3),
        "cost_pct": round(c_pct, 3),
        "net_edge_pct": round(net_edge, 3),
        "min_net_edge_pct": min_net_edge_pct,
        "segment": segment,
    }
