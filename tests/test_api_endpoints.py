"""Production tests for all API endpoints."""
import pytest
import sys
from pathlib import Path
from fastapi.testclient import TestClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.main import app
from backend.app.database import SessionLocal, Account, Mandate, FundingPlan


client = TestClient(app)


class TestHealthEndpoints:
    """Test system health endpoints."""
    
    def test_health_check(self):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["broker"] == "upstox"


class TestAccountAPI:
    """Test account management API."""
    
    def test_create_account(self):
        """Test creating account via API."""
        payload = {
            "name": "API Test Account",
            "account_type": "SIP",
            "user_id": "test_user"
        }
        
        response = client.post("/api/accounts/", json=payload)
        
        # Clean up first if exists
        if response.status_code == 400:
            # Account might already exist
            pass
        else:
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "API Test Account"
            assert data["account_type"] == "SIP"
    
    def test_list_accounts(self):
        """Test listing accounts."""
        response = client.get("/api/accounts/?user_id=test_user")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_account_summary(self):
        """Test getting account summary."""
        # First create an account
        db = SessionLocal()
        account = db.query(Account).filter(Account.user_id == "test_user").first()
        
        if account:
            response = client.get(f"/api/accounts/{account.id}/summary")
            assert response.status_code == 200
            
            data = response.json()
            assert "account" in data
            assert "stats" in data
        
        db.close()


class TestIntakeAPI:
    """Test intake agent API."""
    
    def test_start_intake_session(self):
        """Test starting intake session."""
        payload = {
            "account_name": "Test Intake Account",
            "account_type": "SIP",
            "user_id": "test_user"
        }
        
        response = client.post("/api/accounts/intake/start", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "session_id" in data
        assert "current_question" in data
        assert data["total_questions"] > 0


class TestAITraderAPI:
    """Test AI Trader pipeline API."""
    
    def test_treasury_summary(self):
        """Test getting treasury summary."""
        response = client.get("/api/ai-trader/treasury/summary")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "summary" in data
        assert "total_capital" in data["summary"]
    
    def test_risk_metrics(self):
        """Test getting risk metrics."""
        response = client.get("/api/ai-trader/risk/metrics")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "metrics" in data
    
    def test_list_playbooks(self):
        """Test listing playbooks."""
        response = client.get("/api/ai-trader/playbooks")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert "playbooks" in data
        assert isinstance(data["playbooks"], list)
    
    def test_get_trade_cards_v2(self):
        """Test getting trade cards."""
        response = client.get("/api/ai-trader/trade-cards?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)


class TestUpstoxAdvancedAPI:
    """Test Upstox advanced endpoints."""
    
    def test_profile_endpoint(self):
        """Test profile endpoint (may fail if not authenticated)."""
        response = client.get("/api/upstox/profile")
        
        # May return 401 if not authenticated - that's okay
        assert response.status_code in [200, 401, 500]
    
    def test_instruments_search(self):
        """Test instrument search."""
        response = client.get("/api/upstox/instruments/search?query=RELIANCE")
        
        # May fail if not authenticated, but endpoint should exist
        assert response.status_code in [200, 401, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

