"""Tests for API endpoints."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import init_db

client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_auth_status():
    """Test auth status endpoint."""
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert "authenticated" in data
    assert "broker" in data


def test_get_pending_trade_cards():
    """Test getting pending trade cards."""
    response = client.get("/api/trade-cards/pending")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_positions():
    """Test getting positions."""
    response = client.get("/api/positions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_orders():
    """Test getting orders."""
    response = client.get("/api/orders")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_strategies():
    """Test listing strategies."""
    response = client.get("/api/signals/strategies")
    assert response.status_code == 200
    data = response.json()
    assert "strategies" in data
    assert len(data["strategies"]) > 0


def test_get_eod_report():
    """Test EOD report endpoint."""
    response = client.get("/api/reports/eod")
    assert response.status_code == 200
    data = response.json()
    assert "date" in data
    assert "total_trades" in data
    assert "total_pnl" in data


def test_get_monthly_report():
    """Test monthly report endpoint."""
    response = client.get("/api/reports/monthly")
    assert response.status_code == 200
    data = response.json()
    assert "month" in data
    assert "total_trades" in data
    assert "win_rate" in data

