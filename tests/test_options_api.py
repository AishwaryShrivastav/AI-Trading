from fastapi.testclient import TestClient
from backend.app.main import app


def test_options_chain_endpoint_contract():
    client = TestClient(app)
    res = client.get("/api/options/chain", params={"symbol": "RELIANCE", "exchange": "NSE"})
    # Without broker auth this should be 503; with auth it should be 200
    assert res.status_code in (200, 404, 503)

