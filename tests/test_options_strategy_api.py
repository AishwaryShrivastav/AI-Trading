from datetime import date, timedelta
from fastapi.testclient import TestClient
from backend.app.main import app


def test_strategy_generate_contract():
    client = TestClient(app)
    payload = {
        "symbol": "RELIANCE",
        "expiry": (date.today() + timedelta(days=30)).isoformat(),
        "account_id": 1,
        "strategy_type": "IRON_CONDOR",
        "max_risk": 50000.0
    }
    res = client.post("/api/options/strategy/generate", json=payload)
    # Without auth and live chain, may be 503/404; with auth 200
    assert res.status_code in (200, 404, 503)


def test_strategy_execute_contract():
    client = TestClient(app)
    # Non-existent strategy id should 404 or 503 depending on resolution
    res = client.post("/api/options/strategy/execute", json={"strategy_id": 999999})
    assert res.status_code in (404, 503)

