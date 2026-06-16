"""Tests for the Orchestrator decision brain (Step 2a). LLM is always mocked."""
import pytest

from backend.app.database import SessionLocal
from backend.app.services.orchestrator import Orchestrator


class _FakeLLM:
    """Stand-in for an LLM provider returning a scripted orchestrate result."""
    def __init__(self, result=None, raise_exc=None):
        self._result = result
        self._raise = raise_exc

    async def orchestrate_decisions(self, context):
        if self._raise:
            raise self._raise
        return self._result


def _orch(llm):
    return Orchestrator(db=SessionLocal(), llm=llm)


def _good_result(conviction, risk_flags=None):
    return {
        "market_thesis": "Range-bound; selective longs.",
        "regime_assessment": "ranging",
        "risk_flags": risk_flags or [],
        "trade_recommendations": [
            {"instrument": "RELIANCE", "direction": "LONG", "conviction": conviction,
             "size_pct": 5, "stop_loss": 2850, "reasoning": "EMA cross + volume"}
        ],
        "_usage": {"input_tokens": 1000, "output_tokens": 500},
        "_model": "claude-opus-4-8",
    }


# ----------------------------------------------------------------- tiers
@pytest.mark.asyncio
async def test_high_conviction_no_flags_is_auto():
    orch = _orch(_FakeLLM(_good_result(0.85)))
    out = await orch.decide(["RELIANCE"])
    assert out["fallback"] is False
    assert out["trade_recommendations"][0]["tier"] == "AUTO"
    assert out["tier_counts"]["AUTO"] == 1


@pytest.mark.asyncio
async def test_high_conviction_with_flag_downgrades_to_hil():
    orch = _orch(_FakeLLM(_good_result(0.85, risk_flags=["earnings in 2 days"])))
    out = await orch.decide(["RELIANCE"])
    assert out["trade_recommendations"][0]["tier"] == "HIL"


@pytest.mark.asyncio
async def test_mid_conviction_is_hil():
    orch = _orch(_FakeLLM(_good_result(0.6)))
    out = await orch.decide(["RELIANCE"])
    assert out["trade_recommendations"][0]["tier"] == "HIL"


@pytest.mark.asyncio
async def test_low_conviction_is_skip():
    orch = _orch(_FakeLLM(_good_result(0.3)))
    out = await orch.decide(["RELIANCE"])
    assert out["trade_recommendations"][0]["tier"] == "SKIP"


# ----------------------------------------------------------------- fallback
@pytest.mark.asyncio
async def test_llm_error_falls_back_to_rules():
    orch = _orch(_FakeLLM(raise_exc=RuntimeError("boom")))
    out = await orch.decide(["RELIANCE"])
    assert out["fallback"] is True
    assert out["source"] == "rule_based"
    assert out["fallback_reason"].startswith("llm_error")


@pytest.mark.asyncio
async def test_malformed_json_falls_back_to_rules():
    # trade_recommendations is not a list -> invalid schema
    bad = {"market_thesis": "x", "trade_recommendations": "nope"}
    orch = _orch(_FakeLLM(bad))
    out = await orch.decide(["RELIANCE"])
    assert out["fallback"] is True
    assert out["fallback_reason"] == "invalid_schema"


@pytest.mark.asyncio
async def test_invalid_direction_rejected():
    bad = {
        "market_thesis": "x",
        "trade_recommendations": [
            {"instrument": "X", "direction": "SIDEWAYS", "conviction": 0.8}
        ],
    }
    orch = _orch(_FakeLLM(bad))
    out = await orch.decide(["X"])
    assert out["fallback"] is True


@pytest.mark.asyncio
async def test_fallback_never_auto_executes():
    """Rule-based fallback must keep a human in the loop — never AUTO."""
    orch = _orch(_FakeLLM(raise_exc=RuntimeError("down")))
    # Seed context with a high-confidence signal via monkeypatched assemble.
    orch.assemble_context = lambda symbols, account_id=None: {
        "candidate_signals": [{"symbol": "TCS", "direction": "LONG", "confidence": 0.95}],
        "regime": "unknown",
    }
    out = await orch.decide(["TCS"])
    assert out["fallback"] is True
    assert all(r["tier"] != "AUTO" for r in out["trade_recommendations"])


# ----------------------------------------------------------------- cost cap
@pytest.mark.asyncio
async def test_cost_cap_blocks_llm_and_uses_fallback(monkeypatch):
    orch = _orch(_FakeLLM(_good_result(0.9)))
    monkeypatch.setattr(orch, "_today_cost", lambda: 999.0)  # over the ₹200 cap
    out = await orch.decide(["RELIANCE"])
    assert out["fallback"] is True
    assert out["fallback_reason"] == "cost_cap"


# ----------------------------------------------------------------- validation unit
def test_validate_accepts_clean_and_strips_extras():
    orch = _orch(_FakeLLM(None))
    cleaned = orch._validate(_good_result(0.7))
    assert cleaned is not None
    assert cleaned["trade_recommendations"][0]["instrument"] == "RELIANCE"
    assert "_usage" not in cleaned
