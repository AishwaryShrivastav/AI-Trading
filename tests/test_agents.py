"""Tests for specialist agents + orchestrator context enrichment (Step 2b)."""
from datetime import datetime, timedelta

import pytest

from backend.app.database import SessionLocal, Event, Feature
from backend.app.services.agents import NewsAgent, TechnicalAgent, MacroAgent, run_specialist_agents
from backend.app.services.orchestrator import Orchestrator


class _FakeAgentLLM:
    def __init__(self, result=None, raise_exc=None):
        self._result = result or {}
        self._raise = raise_exc
        self.calls = 0

    async def complete_json(self, system, user, max_tokens=1024):
        self.calls += 1
        if self._raise:
            raise self._raise
        return self._result


@pytest.fixture
def seeded_news():
    db = SessionLocal()
    ev = Event(
        source="NEWS_API",
        event_type="EARNINGS",
        priority="HIGH",
        symbols=["RELIANCE"],
        sector="ENERGY",
        normalized_content="Reliance beats Q1 estimates on strong refining margins.",
        event_timestamp=datetime.utcnow() - timedelta(hours=2),
        processing_status="PROCESSED",
    )
    db.add(ev)
    db.commit()
    eid = ev.id
    db.close()
    yield eid
    db = SessionLocal()
    db.query(Event).filter(Event.id == eid).delete()
    db.commit()
    db.close()


@pytest.mark.asyncio
async def test_news_agent_scores_from_events(seeded_news):
    llm = _FakeAgentLLM({"sentiment": {"RELIANCE": {"score": 0.7, "confidence": 0.8}}})
    out = await NewsAgent(SessionLocal(), llm).analyze(["RELIANCE"])
    assert out["events_considered"] >= 1
    assert out["sentiment"]["RELIANCE"]["score"] == 0.7
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_news_agent_no_events_skips_llm():
    llm = _FakeAgentLLM({"sentiment": {"X": {}}})
    out = await NewsAgent(SessionLocal(), llm).analyze(["ZZZNONEXISTENT"])
    assert out["events_considered"] == 0
    assert out["sentiment"] == {}
    assert llm.calls == 0  # no data -> no spend


@pytest.mark.asyncio
async def test_news_agent_degrades_on_llm_error(seeded_news):
    llm = _FakeAgentLLM(raise_exc=RuntimeError("api down"))
    out = await NewsAgent(SessionLocal(), llm).analyze(["RELIANCE"])
    assert out["sentiment"] == {}
    assert "error" in out


@pytest.mark.asyncio
async def test_macro_agent_no_data_returns_unknown():
    llm = _FakeAgentLLM({"regime": "trending-up"})
    out = await MacroAgent(SessionLocal(), llm).analyze(["ZZZNONEXISTENT"])
    assert out["regime"] == "unknown"
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_run_specialist_agents_merged_shape(seeded_news):
    llm = _FakeAgentLLM({"sentiment": {"RELIANCE": {"score": 0.5}}})
    merged = await run_specialist_agents(SessionLocal(), ["RELIANCE"], llm=llm)
    assert "sentiment" in merged
    assert "technical" in merged
    assert "regime" in merged
    assert "sector_rotation" in merged


@pytest.mark.asyncio
async def test_orchestrator_enrichment_populates_context(seeded_news):
    """With agents enabled, decide() enriches context before the LLM decision."""
    captured = {}

    class _DecisionLLM:
        async def orchestrate_decisions(self, context):
            captured.update(context)
            return {
                "market_thesis": "ok", "regime_assessment": "ranging", "risk_flags": [],
                "trade_recommendations": [],
                "_usage": {"input_tokens": 10, "output_tokens": 5}, "_model": "claude-opus-4-8",
            }

    agent_llm = _FakeAgentLLM({"sentiment": {"RELIANCE": {"score": 0.6}}})
    orch = Orchestrator(db=SessionLocal(), llm=_DecisionLLM(), agent_llm=agent_llm)
    await orch.decide(["RELIANCE"])
    assert captured.get("sentiment", {}).get("RELIANCE", {}).get("score") == 0.6


@pytest.mark.asyncio
async def test_orchestrator_enrichment_disabled(monkeypatch, seeded_news):
    captured = {}

    class _DecisionLLM:
        async def orchestrate_decisions(self, context):
            captured.update(context)
            return {"market_thesis": "ok", "trade_recommendations": [], "risk_flags": []}

    agent_llm = _FakeAgentLLM({"sentiment": {"RELIANCE": {"score": 0.6}}})
    orch = Orchestrator(db=SessionLocal(), llm=_DecisionLLM(), agent_llm=agent_llm)
    orch.settings.use_specialist_agents = False
    try:
        await orch.decide(["RELIANCE"])
        assert agent_llm.calls == 0  # agents not run
        assert captured.get("sentiment") == {}  # context left at assemble default
    finally:
        orch.settings.use_specialist_agents = True
