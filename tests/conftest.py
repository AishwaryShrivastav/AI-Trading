"""Shared pytest fixtures and test-session setup."""
import pytest
from backend.app.database import SessionLocal, Setting


@pytest.fixture(autouse=True, scope="session")
def reset_llm_daily_cost():
    """Clear accumulated LLM daily-cost entries so cost-cap logic never triggers in tests.

    The orchestrator stores daily cost in a Setting row keyed 'llm_cost_YYYY-MM-DD'.
    Across many test-suite runs on the same day the value can exceed the cap ($200),
    causing the LLM to fall back to rule-based logic and breaking tests that expect
    a real LLM decision.  Deleting those rows at session start keeps the slate clean.
    """
    db = SessionLocal()
    try:
        rows = db.query(Setting).filter(Setting.key.like("llm_cost_%")).all()
        for row in rows:
            db.delete(row)
        db.commit()
    finally:
        db.close()
    yield
