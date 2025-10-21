# Phase 2 — P1.1 Guardrails (Production)

## Overview
Production-grade guardrails with 6 checks: liquidity, position size risk, sector exposure, event window, regime info, and catalyst freshness (hot path). Integrated into pipeline with block-on-CRITICAL and idempotent blocked-card marker. Exposed via `/api/guardrails/check` and `/api/guardrails/explain`. Metrics exported on `/metrics`.

## Data sources
- `market_data_cache` for ADV (20-day window)
- `mandates` + `funding_plans` for risk per trade and capital
- `positions_v2` for sector exposure
- `earnings_calendar` or `events` for event window
- `features` for `regime_label`

## Request/Response
POST `/api/guardrails/check`
```json
{
  "symbol": "INFY",
  "account_id": 1,
  "quantity": 100,
  "entry_price": 1500.0,
  "stop_loss": 1450.0,
  "trade_type": "LONG",
  "exchange": "NSE",
  "sector": "IT",
  "event_id": null
}
```
Response:
```json
{
  "liquidity_check": true,
  "position_size_check": true,
  "exposure_check": true,
  "event_window_check": true,
  "regime_check": true,
  "catalyst_freshness_check": true,
  "risk_warnings": [{"type":"WARNING","code":"EVENT_WINDOW_WARNING","message":"Upcoming earnings..."}],
  "passed_all": true,
  "has_critical_failures": false,
  "timestamp": "...",
  "evaluation_duration_ms": 42.0
}
```

GET `/api/guardrails/explain?card_id={id}` returns guardrail booleans and warnings for a card.

## Block policy
- CRITICAL → blocks card creation (and creates BLOCKED card marker to avoid duplicates)
- WARNING/INFO → allowed with warnings surfaced in frontend

## Metrics
- `guardrail_checks_total{check_type,result}`
- `guardrail_evaluation_latency_ms`
- `blocked_cards_total{reason}`

## Environment
```
REAL_GUARDRAILS=true
ADV_LOOKBACK_DAYS=20
TRADE_TO_ADV_RATIO=0.05
CATALYST_FRESHNESS_HOURS=24
EARNINGS_BLACKOUT_DAYS=2
```

## Testing
- Unit tests for each check (liquidity, position size, exposure, event window, catalyst freshness, regime info)
- Contract test for `/api/guardrails/check`
- E2E path: pipeline creates BLOCKED card on CRITICAL (covered indirectly via checks + pipeline integration)

Run:
```
pytest -q tests/test_risk_checks.py tests/test_guardrails_additional.py tests/test_guardrails_more.py
```

## Notes
- Metrics are optional; if `prometheus_client` not present, metrics are no-op.
- Timezone warnings remain (utcnow) for compatibility; can be migrated to aware timestamps later.
