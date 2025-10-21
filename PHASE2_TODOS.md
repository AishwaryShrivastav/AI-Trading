# Phase 2 Implementation - Task Checklist

**Status Legend:** ⬜ Not Started | 🟦 In Progress | ✅ Complete | ⚠️ Blocked | ❌ Cancelled

---

## 🧱 STAGE 1: P1.1 - Foundations & Guardrails (Days 1-3)

### Code Implementation

- [ ] ⬜ **1.1.1** Fix `MarketDataCache` import in `backend/app/services/allocator.py:6`
- [ ] ⬜ **1.1.2** Create `backend/app/services/risk_evaluation.py` with `GuardrailSeverity` enum, `RiskWarning`, and `RiskEvaluationResult` dataclasses
- [ ] ⬜ **1.1.3** Create `backend/app/services/ingestion/calendar_feed.py` for NSE earnings calendar
- [ ] ⬜ **1.1.4** Add `EarningsCalendar` model to `backend/app/database.py`
- [ ] ⬜ **1.1.5** Create `backend/app/services/ingestion/nse_master.py` for sector mapping
- [ ] ⬜ **1.1.6** Add `SymbolMaster` model to `backend/app/database.py`
- [ ] ⬜ **1.1.7** Enhance `backend/app/services/risk_checks.py` with all 6 real guardrail methods
- [ ] ⬜ **1.1.8** Update `backend/app/services/trade_card_pipeline_v2.py` to integrate real checks (lines 150-190)
- [ ] ⬜ **1.1.9** Create `backend/app/routers/guardrails.py` with `/check` and `/explain` endpoints
- [ ] ⬜ **1.1.10** Register guardrails router in `backend/app/main.py`
- [ ] ⬜ **1.1.11** Add guardrail CSS styles to `frontend/static/css/styles.css`
- [ ] ⬜ **1.1.12** Enhance `frontend/static/js/app.js` with guardrail chips in `createTradeCardHTML()`
- [ ] ⬜ **1.1.13** Add `showGuardrailDetails()` method to `app.js` with modal

### Database & Migrations

- [ ] ⬜ **1.1.14** Create Alembic migration `001_phase2_guardrails.py`
- [ ] ⬜ **1.1.15** Add table: `earnings_calendar`
- [ ] ⬜ **1.1.16** Add table: `symbol_master`
- [ ] ⬜ **1.1.17** Add indexes: `(symbol, created_at)` on `events`
- [ ] ⬜ **1.1.18** Add indexes: `(symbol, ts)` on `market_data_cache`
- [ ] ⬜ **1.1.19** Ensure `trade_cards_v2` has all 6 guardrail boolean fields
- [ ] ⬜ **1.1.20** Run migration: `alembic upgrade head`

### Configuration

- [ ] ⬜ **1.1.21** Add guardrail config to `env.template`: `REAL_GUARDRAILS`, `ADV_LOOKBACK_DAYS`, `EVENT_BLACKOUT_DAYS`, etc.
- [ ] ⬜ **1.1.22** Update `.env` with guardrail values

### Observability

- [ ] ⬜ **1.1.23** Add metrics to `backend/app/services/metrics.py`: `guardrail_checks_total`, `guardrail_latency_ms`, `blocked_cards_total`, `guardrail_pass_ratio`
- [ ] ⬜ **1.1.24** Integrate metric recording in `risk_checks.py`
- [ ] ⬜ **1.1.25** Create Grafana dashboard for guardrails (JSON config)
- [ ] ⬜ **1.1.26** Configure alert: pass rate < 85%

### Testing

- [ ] ⬜ **1.1.27** Create `tests/test_guardrails.py`
- [ ] ⬜ **1.1.28** Test: `TestLiquidityCheck.test_liquidity_pass`
- [ ] ⬜ **1.1.29** Test: `TestLiquidityCheck.test_liquidity_fail`
- [ ] ⬜ **1.1.30** Test: `TestLiquidityCheck.test_liquidity_insufficient_data`
- [ ] ⬜ **1.1.31** Test: `TestPositionSizeCheck.test_position_size_pass`
- [ ] ⬜ **1.1.32** Test: `TestPositionSizeCheck.test_position_size_fail`
- [ ] ⬜ **1.1.33** Test: `TestSectorExposureCheck.test_sector_exposure_pass`
- [ ] ⬜ **1.1.34** Test: `TestSectorExposureCheck.test_sector_exposure_fail`
- [ ] ⬜ **1.1.35** Test: `TestEventWindowCheck.test_event_window_pass`
- [ ] ⬜ **1.1.36** Test: `TestEventWindowCheck.test_event_window_fail`
- [ ] ⬜ **1.1.37** Test: `TestRegimeCheck.test_regime_pass`
- [ ] ⬜ **1.1.38** Test: `TestRegimeCheck.test_regime_fail`
- [ ] ⬜ **1.1.39** Test: `TestCatalystFreshnessCheck.test_catalyst_fresh_pass`
- [ ] ⬜ **1.1.40** Test: `TestCatalystFreshnessCheck.test_catalyst_stale_fail`
- [ ] ⬜ **1.1.41** Test: `TestIntegration.test_all_checks_pass`
- [ ] ⬜ **1.1.42** Test: `TestIntegration.test_critical_failure_blocks`
- [ ] ⬜ **1.1.43** Test: API endpoint `/guardrails/check` with valid input
- [ ] ⬜ **1.1.44** Test: API endpoint `/guardrails/check` with rate limit exceeded
- [ ] ⬜ **1.1.45** Test: API endpoint `/guardrails/explain` returns warnings
- [ ] ⬜ **1.1.46** Test: Frontend renders guardrail chips correctly
- [ ] ⬜ **1.1.47** Run all tests: `pytest tests/test_guardrails.py -v --cov`
- [ ] ⬜ **1.1.48** Verify coverage > 85%

### Documentation

- [ ] ⬜ **1.1.49** Create `PHASE2_P1.1_GUARDRAILS.md` with full documentation
- [ ] ⬜ **1.1.50** Update `README.md` with guardrails overview
- [ ] ⬜ **1.1.51** Update API documentation with new endpoints

### Rollout

- [ ] ⬜ **1.1.52** Deploy with `REAL_GUARDRAILS=false` (Day 1 morning)
- [ ] ⬜ **1.1.53** Run calendar feed ingestion
- [ ] ⬜ **1.1.54** Run NSE master update
- [ ] ⬜ **1.1.55** Enable for test account (Day 2 morning)
- [ ] ⬜ **1.1.56** Monitor metrics for 24 hours
- [ ] ⬜ **1.1.57** Enable globally: `REAL_GUARDRAILS=true` (Day 3)
- [ ] ⬜ **1.1.58** Mark P1.1 complete ✅

---

## 🧮 STAGE 2: P1.2 - Derivatives & Options (Days 4-9)

### Code Implementation

- [ ] ⬜ **1.2.1** Add `OptionChain` model to `backend/app/database.py`
- [ ] ⬜ **1.2.2** Add `OptionStrategy` model to `backend/app/database.py`
- [ ] ⬜ **1.2.3** Create `backend/app/services/ingestion/options_chain_feed.py`
- [ ] ⬜ **1.2.4** Create `backend/app/services/options_engine.py` with `OptionsEngine` class
- [ ] ⬜ **1.2.5** Implement `_generate_iron_condor()` method
- [ ] ⬜ **1.2.6** Implement `_generate_bull_put_spread()` method
- [ ] ⬜ **1.2.7** Implement `_generate_bear_call_spread()` method
- [ ] ⬜ **1.2.8** Implement `_generate_covered_call()` method
- [ ] ⬜ **1.2.9** Implement `_generate_long_straddle()` method
- [ ] ⬜ **1.2.10** Implement `_calculate_pnl_scenarios()` method
- [ ] ⬜ **1.2.11** Add `get_option_chain()` method to `backend/app/services/broker/upstox.py`
- [ ] ⬜ **1.2.12** Add `place_option_strategy()` method to `upstox.py`
- [ ] ⬜ **1.2.13** Add `_get_option_instrument_token()` helper
- [ ] ⬜ **1.2.14** Create `backend/app/routers/options.py`
- [ ] ⬜ **1.2.15** Register options router in `main.py`
- [ ] ⬜ **1.2.16** Create `frontend/static/js/options.js` with `OptionsViewer` class
- [ ] ⬜ **1.2.17** Add Options tab to frontend HTML

### Database & Migrations

- [ ] ⬜ **1.2.18** Create Alembic migration `002_phase2_options.py`
- [ ] ⬜ **1.2.19** Add table: `option_chains`
- [ ] ⬜ **1.2.20** Add table: `option_strategies`
- [ ] ⬜ **1.2.21** Add indexes on `(symbol, expiry, strike)`
- [ ] ⬜ **1.2.22** Run migration: `alembic upgrade head`

### Configuration

- [ ] ⬜ **1.2.23** Add options config to `env.template`: `OPTIONS_TRADING_ENABLED`, `OPTIONS_CHAIN_CACHE_MINUTES`

### Testing

- [ ] ⬜ **1.2.24** Create `tests/test_options.py`
- [ ] ⬜ **1.2.25** Test: `TestOptionsChainFeed.test_fetch_chain`
- [ ] ⬜ **1.2.26** Test: `TestOptionsChainFeed.test_iv_rank_calculation`
- [ ] ⬜ **1.2.27** Test: `TestOptionsEngine.test_iron_condor_generation`
- [ ] ⬜ **1.2.28** Test: `TestOptionsEngine.test_strategy_ranking`
- [ ] ⬜ **1.2.29** Test: Greeks calculation accuracy
- [ ] ⬜ **1.2.30** Test: P&L scenarios correctness
- [ ] ⬜ **1.2.31** Test: Multi-leg execution (sandbox)
- [ ] ⬜ **1.2.32** Test: API `/api/options/chain`
- [ ] ⬜ **1.2.33** Test: API `/api/options/strategy/generate`
- [ ] ⬜ **1.2.34** Test: API `/api/options/strategy/execute`
- [ ] ⬜ **1.2.35** Test: Frontend options viewer renders chain
- [ ] ⬜ **1.2.36** Run all tests: `pytest tests/test_options.py -v`

### Documentation

- [ ] ⬜ **1.2.37** Create `PHASE2_P1.2_OPTIONS.md`
- [ ] ⬜ **1.2.38** Document all option strategies
- [ ] ⬜ **1.2.39** Document Greeks calculation methodology

### Rollout

- [ ] ⬜ **1.2.40** Deploy with `OPTIONS_TRADING_ENABLED=false` (read-only)
- [ ] ⬜ **1.2.41** Test chain ingestion for 3-5 symbols
- [ ] ⬜ **1.2.42** Verify strategy generation
- [ ] ⬜ **1.2.43** Enable execution in sandbox
- [ ] ⬜ **1.2.44** Monitor for 2 days
- [ ] ⬜ **1.2.45** Enable production: `OPTIONS_TRADING_ENABLED=true`
- [ ] ⬜ **1.2.46** Mark P1.2 complete ✅

---

## 🌐 STAGE 3: P1.3 - Flows & Policy (Days 10-14)

### Code Implementation

- [ ] ⬜ **1.3.1** Add `InstitutionalFlow` model to `database.py`
- [ ] ⬜ **1.3.2** Add `InsiderTrade` model to `database.py`
- [ ] ⬜ **1.3.3** Add `PolicyUpdate` model to `database.py`
- [ ] ⬜ **1.3.4** Create `backend/app/services/ingestion/flows_feed.py`
- [ ] ⬜ **1.3.5** Implement `_scrape_nsdl()` for FPI/DII flows
- [ ] ⬜ **1.3.6** Create `backend/app/services/ingestion/insider_feed.py`
- [ ] ⬜ **1.3.7** Implement `_parse_sast()` for NSE SAST data
- [ ] ⬜ **1.3.8** Implement `_parse_bulk_deals()` for NSE bulk deals
- [ ] ⬜ **1.3.9** Create `backend/app/services/ingestion/policy_feed.py`
- [ ] ⬜ **1.3.10** Implement `_scrape_rbi()` for RBI press releases
- [ ] ⬜ **1.3.11** Implement `_scrape_sebi()` for SEBI announcements
- [ ] ⬜ **1.3.12** Implement `_scrape_pib()` for PIB updates
- [ ] ⬜ **1.3.13** Create `backend/app/services/analyst_agent.py`
- [ ] ⬜ **1.3.14** Implement `analyze_policy()` with LLM
- [ ] ⬜ **1.3.15** Create `backend/app/routers/flows.py`
- [ ] ⬜ **1.3.16** Register flows router in `main.py`
- [ ] ⬜ **1.3.17** Add "Market Pulse" widget to frontend

### Database & Migrations

- [ ] ⬜ **1.3.18** Create Alembic migration `003_phase2_flows_policy.py`
- [ ] ⬜ **1.3.19** Add table: `institutional_flows`
- [ ] ⬜ **1.3.20** Add table: `insider_trades`
- [ ] ⬜ **1.3.21** Add table: `policy_updates`
- [ ] ⬜ **1.3.22** Add indexes on dates and symbols
- [ ] ⬜ **1.3.23** Run migration

### Testing

- [ ] ⬜ **1.3.24** Create `tests/test_flows_policy.py`
- [ ] ⬜ **1.3.25** Test: Flows feed ingestion
- [ ] ⬜ **1.3.26** Test: Insider feed parsing
- [ ] ⬜ **1.3.27** Test: Policy scraping
- [ ] ⬜ **1.3.28** Test: Analyst agent LLM summarization
- [ ] ⬜ **1.3.29** Test: Stance classification accuracy
- [ ] ⬜ **1.3.30** Test: API `/api/flows/daily`
- [ ] ⬜ **1.3.31** Test: API `/api/flows/insider`
- [ ] ⬜ **1.3.32** Test: API `/api/policy/updates`
- [ ] ⬜ **1.3.33** Run tests: `pytest tests/test_flows_policy.py -v`

### Documentation

- [ ] ⬜ **1.3.34** Create `PHASE2_P1.3_FLOWS_POLICY.md`
- [ ] ⬜ **1.3.35** Document data sources and scraping methodology

### Rollout

- [ ] ⬜ **1.3.36** Deploy flows ingestion
- [ ] ⬜ **1.3.37** Run daily for 3 days, verify data quality
- [ ] ⬜ **1.3.38** Deploy analyst agent
- [ ] ⬜ **1.3.39** Analyze 10 sample policies, review outputs
- [ ] ⬜ **1.3.40** Enable frontend widget
- [ ] ⬜ **1.3.41** Mark P1.3 complete ✅

---

## 🧠 STAGE 4: P1.4 - Playbooks v2 + Agents (Days 15-20)

### Code Implementation

- [ ] ⬜ **1.4.1** Add new fields to `Playbook` model: `stale_minutes`, `gap_chase_max_percent`, `execution_window_hours`, `min_confidence`, `sector_multipliers`
- [ ] ⬜ **1.4.2** Create `backend/app/services/research_agent.py` with `ResearchAgent` class (fix `__init__` typo)
- [ ] ⬜ **1.4.3** Define `EventAnalysisSchema` using Pydantic
- [ ] ⬜ **1.4.4** Add `event_analyses` table to `database.py`
- [ ] ⬜ **1.4.5** Implement `analyze_event()` method in ResearchAgent
- [ ] ⬜ **1.4.6** Wire ResearchAgent into pipeline (after ingestion, before Judge)
- [ ] ⬜ **1.4.7** Inject research bullets into TradeCard `evidence_links`
- [ ] ⬜ **1.4.8** Enhance `playbook_manager.py` with new override logic
- [ ] ⬜ **1.4.9** Add `exchange` field population in `allocator.py`
- [ ] ⬜ **1.4.10** Wrap risk checks in try/except in pipeline for graceful degradation
- [ ] ⬜ **1.4.11** Add "Research Summary" modal to frontend

### Database & Migrations

- [ ] ⬜ **1.4.12** Create Alembic migration `004_phase2_playbooks_v2.py`
- [ ] ⬜ **1.4.13** Add new fields to `playbooks` table
- [ ] ⬜ **1.4.14** Add table: `event_analyses`
- [ ] ⬜ **1.4.15** Run migration with defaults and backfill

### Testing

- [ ] ⬜ **1.4.16** Create `tests/test_playbooks_agents.py`
- [ ] ⬜ **1.4.17** Test: ResearchAgent generates valid EventAnalysisSchema
- [ ] ⬜ **1.4.18** Test: Playbook overrides modify card SL/TP
- [ ] ⬜ **1.4.19** Test: Playbook overrides change priority
- [ ] ⬜ **1.4.20** Test: Research bullets appear in card evidence
- [ ] ⬜ **1.4.21** Test: Pipeline degrades gracefully on LLM timeout
- [ ] ⬜ **1.4.22** Test: Stale playbooks expire correctly

### Documentation

- [ ] ⬜ **1.4.23** Create `PHASE2_P1.4_PLAYBOOKS_AGENTS.md`
- [ ] ⬜ **1.4.24** Document playbook schema and override rules

### Rollout

- [ ] ⬜ **1.4.25** Deploy with `PLAYBOOKS_V2=false`
- [ ] ⬜ **1.4.26** Test ResearchAgent on 5 events
- [ ] ⬜ **1.4.27** Enable playbooks v2
- [ ] ⬜ **1.4.28** Monitor for stale card cleanup
- [ ] ⬜ **1.4.29** Mark P1.4 complete ✅

---

## 💼 STAGE 5: P2.1 - Portfolio Brain (Days 21-25)

### Code Implementation

- [ ] ⬜ **2.1.1** Create `backend/app/services/portfolio_brain.py`
- [ ] ⬜ **2.1.2** Implement sector exposure calculation
- [ ] ⬜ **2.1.3** Implement beta-weighted portfolio metrics
- [ ] ⬜ **2.1.4** Implement VaR calculation
- [ ] ⬜ **2.1.5** Create `backend/app/services/hedge_engine.py`
- [ ] ⬜ **2.1.6** Implement rotation proposal generation
- [ ] ⬜ **2.1.7** Implement hedge proposal generation
- [ ] ⬜ **2.1.8** Enhance `risk_monitor.py` to compute live β, σ
- [ ] ⬜ **2.1.9** Create `backend/app/routers/portfolio.py`
- [ ] ⬜ **2.1.10** Add frontend Portfolio Overview tab
- [ ] ⬜ **2.1.11** Add React components: `<PortfolioSummary />`, `<HedgeProposalCard />`

### Database & Migrations

- [ ] ⬜ **2.1.12** Create Alembic migration `005_phase2_portfolio_brain.py`
- [ ] ⬜ **2.1.13** Add table: `portfolio_snapshots`
- [ ] ⬜ **2.1.14** Add fields to `mandates`: `target_beta`, `max_sector_exposure`

### Testing

- [ ] ⬜ **2.1.15** Create `tests/test_portfolio_brain.py`
- [ ] ⬜ **2.1.16** Test: Sector exposure calculation
- [ ] ⬜ **2.1.17** Test: Beta calculation
- [ ] ⬜ **2.1.18** Test: VaR calculation
- [ ] ⬜ **2.1.19** Test: Rotation proposals make sense
- [ ] ⬜ **2.1.20** Test: Hedge proposals reduce beta

### Documentation

- [ ] ⬜ **2.1.21** Create `PHASE2_P2.1_PORTFOLIO_BRAIN.md`

### Rollout

- [ ] ⬜ **2.1.22** Deploy read-only dashboard first
- [ ] ⬜ **2.1.23** Validate metrics against manual calculation
- [ ] ⬜ **2.1.24** Enable proposal generation
- [ ] ⬜ **2.1.25** Monitor for 3 days
- [ ] ⬜ **2.1.26** Mark P2.1 complete ✅

---

## 💸 STAGE 6: P2.2 - Treasury Choreography (Days 26-28)

### Code Implementation

- [ ] ⬜ **2.2.1** Extend `treasury.py` with transfer policy methods
- [ ] ⬜ **2.2.2** Implement `propose_transfer()`
- [ ] ⬜ **2.2.3** Implement `approve_transfer()`
- [ ] ⬜ **2.2.4** Add `MOVE_OUT`/`MOVE_IN` ledger event types
- [ ] ⬜ **2.2.5** Implement auto-clawback logic
- [ ] ⬜ **2.2.6** Create `backend/app/routers/treasury.py`
- [ ] ⬜ **2.2.7** Add Treasury tab to frontend
- [ ] ⬜ **2.2.8** Implement double-entry validation

### Database & Migrations

- [ ] ⬜ **2.2.9** Create migration for treasury fields
- [ ] ⬜ **2.2.10** Add `pending_transfers` table

### Testing

- [ ] ⬜ **2.2.11** Create `tests/test_treasury.py`
- [ ] ⬜ **2.2.12** Test: Transfer proposal
- [ ] ⬜ **2.2.13** Test: Transfer approval workflow
- [ ] ⬜ **2.2.14** Test: Double-entry enforcement
- [ ] ⬜ **2.2.15** Test: Auto-clawback triggers
- [ ] ⬜ **2.2.16** Test: Idempotency

### Documentation

- [ ] ⬜ **2.2.17** Create `PHASE2_P2.2_TREASURY.md`

### Rollout

- [ ] ⬜ **2.2.18** Deploy with manual approval only
- [ ] ⬜ **2.2.19** Test with small transfers between test accounts
- [ ] ⬜ **2.2.20** Enable auto-clawback
- [ ] ⬜ **2.2.21** Mark P2.2 complete ✅

---

## 📊 STAGE 7: P3.1 - Learning Loop & Observability (Days 29-32)

### Code Implementation

- [ ] ⬜ **3.1.1** Create `backend/app/services/outcome_analyzer.py`
- [ ] ⬜ **3.1.2** Implement closed trade performance tracking
- [ ] ⬜ **3.1.3** Calculate win rate, Sharpe ratio, max DD
- [ ] ⬜ **3.1.4** Implement quality drift detection
- [ ] ⬜ **3.1.5** Implement adaptive meta-label threshold adjustment
- [ ] ⬜ **3.1.6** Extend `reporting_v2.py` with weekly/monthly summaries
- [ ] ⬜ **3.1.7** Add ROI, exposure, and insights to reports
- [ ] ⬜ **3.1.8** Create `backend/app/services/metrics.py` (if not exists, enhance)
- [ ] ⬜ **3.1.9** Add `/metrics` endpoint (Prometheus format)
- [ ] ⬜ **3.1.10** Create Grafana dashboards (5 dashboards)
- [ ] ⬜ **3.1.11** Configure alert rules (6 alerts)
- [ ] ⬜ **3.1.12** (Optional) Create `backend/app/integrations/telegram_bot.py`

### Database & Migrations

- [ ] ⬜ **3.1.13** Create migration `006_phase2_learning_loop.py`
- [ ] ⬜ **3.1.14** Add table: `outcome_analysis`

### Testing

- [ ] ⬜ **3.1.15** Create `tests/test_outcome_analyzer.py`
- [ ] ⬜ **3.1.16** Test: Closed trade analysis
- [ ] ⬜ **3.1.17** Test: Sharpe ratio calculation
- [ ] ⬜ **3.1.18** Test: Quality drift detection
- [ ] ⬜ **3.1.19** Test: Threshold adjustment
- [ ] ⬜ **3.1.20** Test: Weekly report generation
- [ ] ⬜ **3.1.21** Test: /metrics endpoint format

### Documentation

- [ ] ⬜ **3.1.22** Create `PHASE2_P3.1_LEARNING_LOOP.md`
- [ ] ⬜ **3.1.23** Document all 40+ metrics
- [ ] ⬜ **3.1.24** Document alert rules

### Rollout

- [ ] ⬜ **3.1.25** Deploy metrics endpoint
- [ ] ⬜ **3.1.26** Configure Prometheus scraping
- [ ] ⬜ **3.1.27** Import Grafana dashboards
- [ ] ⬜ **3.1.28** Enable alerts
- [ ] ⬜ **3.1.29** Run outcome analyzer for 7 days
- [ ] ⬜ **3.1.30** Verify adaptive learning works
- [ ] ⬜ **3.1.31** Mark P3.1 complete ✅

---

## 📚 Cross-Cutting Deliverables

### Documentation

- [ ] ⬜ **X.1** Create `PHASE2_TESTING_STRATEGY.md`
- [ ] ⬜ **X.2** Create `PHASE2_AGENT_PROTOCOL.md`
- [ ] ⬜ **X.3** Create `PHASE2_API_REFERENCE.md`
- [ ] ⬜ **X.4** Create `PHASE2_DEPLOYMENT_GUIDE.md`
- [ ] ⬜ **X.5** Update main `README.md` with Phase 2 features
- [ ] ⬜ **X.6** Update `DOCS_INDEX.md` with Phase 2 docs

### Testing

- [ ] ⬜ **X.7** Create `tests/test_integration_e2e.py` (full pipeline)
- [ ] ⬜ **X.8** Create `tests/test_contract_api.py` (schema validation)
- [ ] ⬜ **X.9** Create `tests/test_load.py` (1000 symbols)
- [ ] ⬜ **X.10** Create `tests/test_security.py` (auth, secrets, rate limits)
- [ ] ⬜ **X.11** Run full test suite: `pytest tests/ -v --cov`
- [ ] ⬜ **X.12** Generate coverage report: `coverage html`
- [ ] ⬜ **X.13** Verify coverage > 85%

### Configuration

- [ ] ⬜ **X.14** Update `env.template` with all 40+ Phase 2 variables
- [ ] ⬜ **X.15** Create `.env.production` template
- [ ] ⬜ **X.16** Document all feature flags

### Infrastructure

- [ ] ⬜ **X.17** Setup Prometheus server
- [ ] ⬜ **X.18** Setup Grafana server
- [ ] ⬜ **X.19** (Optional) Setup Redis for rate limiting
- [ ] ⬜ **X.20** (Optional) Migrate to PostgreSQL
- [ ] ⬜ **X.21** Configure backup strategy

### CI/CD

- [ ] ⬜ **X.22** Update GitHub Actions workflow with Phase 2 tests
- [ ] ⬜ **X.23** Add linter checks for new code
- [ ] ⬜ **X.24** Add pre-commit hooks

---

## 🎯 Final Verification Checklist

### Functionality

- [ ] ⬜ **V.1** All 6 guardrails pass/fail correctly with real data
- [ ] ⬜ **V.2** Options chain updates every 15 minutes
- [ ] ⬜ **V.3** Option strategies execute correctly (sandbox verified)
- [ ] ⬜ **V.4** FPI/DII flows ingest daily without failure
- [ ] ⬜ **V.5** Policy updates scraped and analyzed
- [ ] ⬜ **V.6** ResearchAgent produces coherent summaries
- [ ] ⬜ **V.7** Playbook overrides apply correctly
- [ ] ⬜ **V.8** Portfolio Brain calculates beta, VaR accurately
- [ ] ⬜ **V.9** Treasury transfers execute with approval
- [ ] ⬜ **V.10** Outcome analyzer shows performance metrics
- [ ] ⬜ **V.11** Adaptive learning adjusts thresholds after 30 days

### Performance

- [ ] ⬜ **V.12** Pipeline E2E latency < 90s for 100 symbols
- [ ] ⬜ **V.13** Guardrail checks < 100ms P95
- [ ] ⬜ **V.14** API response times < 500ms P95
- [ ] ⬜ **V.15** Database queries optimized with indexes
- [ ] ⬜ **V.16** No N+1 query issues

### Observability

- [ ] ⬜ **V.17** All 40+ metrics visible in Prometheus
- [ ] ⬜ **V.18** All 5 Grafana dashboards functional
- [ ] ⬜ **V.19** All 6 alerts configured and tested
- [ ] ⬜ **V.20** Logs structured and searchable

### Security

- [ ] ⬜ **V.21** No API keys or secrets in code
- [ ] ⬜ **V.22** Rate limiting enforced on all public endpoints
- [ ] ⬜ **V.23** Input validation on all API endpoints
- [ ] ⬜ **V.24** SQL injection prevented (ORM only)
- [ ] ⬜ **V.25** XSS prevented in frontend

### Testing

- [ ] ⬜ **V.26** 100+ tests written
- [ ] ⬜ **V.27** All tests passing
- [ ] ⬜ **V.28** Coverage > 85%
- [ ] ⬜ **V.29** E2E tests pass on staging
- [ ] ⬜ **V.30** Load tests pass (1000 symbols)

### Documentation

- [ ] ⬜ **V.31** All 7 stage docs created
- [ ] ⬜ **V.32** All APIs documented
- [ ] ⬜ **V.33** README updated
- [ ] ⬜ **V.34** Deployment guide complete
- [ ] ⬜ **V.35** Runbook for operators created

### Production Readiness

- [ ] ⬜ **V.36** Feature flags tested
- [ ] ⬜ **V.37** Rollback plan documented
- [ ] ⬜ **V.38** Backup strategy in place
- [ ] ⬜ **V.39** Monitoring alerts trigger correctly
- [ ] ⬜ **V.40** Zero critical bugs in staging for 1 week

---

## 📊 Progress Summary

**Total Tasks:** ~290
**Completed:** 0 ⬜
**In Progress:** 0 🟦
**Blocked:** 0 ⚠️
**Cancelled:** 0 ❌

**Overall Progress:** 0%

### By Stage

| Stage | Total Tasks | Complete | Progress % |
|-------|-------------|----------|------------|
| P1.1 Guardrails | 58 | 0 | 0% |
| P1.2 Options | 46 | 0 | 0% |
| P1.3 Flows & Policy | 41 | 0 | 0% |
| P1.4 Playbooks & Agents | 29 | 0 | 0% |
| P2.1 Portfolio Brain | 26 | 0 | 0% |
| P2.2 Treasury | 21 | 0 | 0% |
| P3.1 Learning Loop | 31 | 0 | 0% |
| Cross-Cutting | 24 | 0 | 0% |
| Final Verification | 40 | 0 | 0% |

---

## 🔄 Update Log

| Date | Completed Tasks | Notes |
|------|-----------------|-------|
| 2025-10-22 | Plan created | All 290 tasks defined |
| | | |

---

**Last Updated:** 2025-10-22  
**Next Review:** Start P1.1 execution  
**Status:** ✅ Planning complete, ready for execution

