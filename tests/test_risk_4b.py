"""Tests for Step 4b: cost gate, VIX breakers, trailing/time stop-loss."""
import pytest

from backend.app.database import SessionLocal, Setting, PositionV2
from backend.app.services.cost_model import passes_cost_gate, cost_pct
from backend.app.services.stop_engine import trailing_stop, is_time_exit, manage_trailing_stops
from backend.app.services.risk_governor import RiskGovernor
from datetime import datetime


# ----------------------------------------------------------------- cost gate
def test_cost_gate_rejects_tiny_target():
    # 0.2% target can't beat round-trip costs.
    gate = passes_cost_gate(entry=100.0, take_profit=100.2, quantity=100, min_net_edge_pct=0.5)
    assert gate["passed"] is False
    assert gate["net_edge_pct"] < 0.5


def test_cost_gate_passes_wide_target():
    # 8% target comfortably clears costs.
    gate = passes_cost_gate(entry=100.0, take_profit=108.0, quantity=100, min_net_edge_pct=0.5)
    assert gate["passed"] is True
    assert gate["reward_pct"] > gate["cost_pct"]


def test_intraday_cheaper_than_delivery():
    assert cost_pct(100, 105, 100, "intraday") < cost_pct(100, 105, 100, "delivery")


def test_cost_gate_invalid_inputs():
    assert passes_cost_gate(entry=0, take_profit=10, quantity=10)["passed"] is False


# ----------------------------------------------------------------- VIX breakers
def _clear_vix_state():
    db = SessionLocal()
    db.query(Setting).filter(Setting.key.in_(["india_vix", "system_state", "equity_peak"])).delete(
        synchronize_session=False
    )
    db.commit(); db.close()


@pytest.fixture
def clean_vix():
    _clear_vix_state()
    yield
    _clear_vix_state()


def test_vix_assessment_levels(clean_vix):
    gov = RiskGovernor(SessionLocal())
    assert gov.vix_assessment(12)["size_factor"] == 1.0
    assert gov.vix_assessment(19)["size_factor"] == gov.settings.vix_derisk_factor
    assert gov.vix_assessment(23)["block_intraday"] is True
    assert gov.vix_assessment(30)["block_all"] is True
    assert gov.vix_assessment(30)["size_factor"] == 0.0


def test_vix_folds_into_size_factor_and_block(clean_vix):
    gov = RiskGovernor(SessionLocal())
    gov._set("india_vix", 19.0)  # derisk factor 0.6, ACTIVE drawdown -> 1.0
    assert gov.position_size_factor() == pytest.approx(gov.settings.vix_derisk_factor)
    gov._set("india_vix", 30.0)
    assert gov.blocks_new_entries() is True


# ----------------------------------------------------------------- trailing stop
def test_trailing_inactive_below_activation():
    # +1% gain, activation at +2% -> stop unchanged.
    assert trailing_stop(100, 101, "LONG", current_sl=95, activate_pct=2.0) == 95


def test_trailing_locks_half_gain_long():
    # +10% gain, lock 50% -> stop at 105.
    assert trailing_stop(100, 110, "LONG", current_sl=95, activate_pct=2.0, lock_fraction=0.5) == 105


def test_trailing_ratchet_only_long():
    # A lower current price must not loosen an already-raised stop.
    assert trailing_stop(100, 103, "LONG", current_sl=105, activate_pct=2.0, lock_fraction=0.5) == 105


def test_trailing_short_side():
    # Short from 100, price 90 (+10% in our favour), lock 50% -> stop at 95.
    assert trailing_stop(100, 90, "SHORT", current_sl=105, lock_fraction=0.5) == 95


def test_is_time_exit():
    assert is_time_exit(datetime(2026, 6, 16, 15, 10)) is True
    assert is_time_exit(datetime(2026, 6, 16, 15, 9)) is False
    assert is_time_exit(datetime(2026, 6, 16, 9, 30)) is False


# ----------------------------------------------------------------- DB ratchet
@pytest.fixture
def paper_pos():
    db = SessionLocal()
    p = PositionV2(
        account_id=999999, symbol="TRAILT", exchange="NSE", direction="LONG",
        quantity=10, average_entry_price=100.0, current_price=110.0, stop_loss=95.0,
        is_paper=True,
    )
    db.add(p); db.commit(); pid = p.id; db.close()
    yield pid
    db = SessionLocal()
    db.query(PositionV2).filter(PositionV2.id == pid).delete()
    db.commit(); db.close()


def test_manage_trailing_stops_ratchets(paper_pos):
    db = SessionLocal()
    updates = manage_trailing_stops(db)
    moved = [u for u in updates if u["position_id"] == paper_pos]
    assert len(moved) == 1
    assert moved[0]["new_sl"] == 105.0  # 50% of the +10 gain locked
    db.close()
