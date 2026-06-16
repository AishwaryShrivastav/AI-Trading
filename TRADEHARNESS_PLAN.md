# TradeHarness — Canonical Build Plan

> Living document. The AI-Investment repo is being **evolved** (not rebuilt) into TradeHarness:
> a self-learning, multi-strategy, human-in-the-loop AI trading system for Indian markets (Upstox).
> Working style: **plan first → build one slice → validate → review → next slice.**
> Last updated: 2026-06-16.

---

## 1. Guiding principle

**Don't automate, and don't go live, until the brain is right and we've proven it on paper.**

We build the safety net (paper mode) and the Claude brain first, prove strategies on historical
data, harden risk, *then* automate with a scheduler, *then* add Telegram, *then* the learning loop.
Compliance runs as a parallel checklist that only gates the final live step.

---

## 2. Current state (verified 2026-06-16)

Working FastAPI multi-account semi-automated equities trader. **60/60 tests pass**, app imports
clean (75 routes).

| Area | Status |
|---|---|
| Infra: FastAPI + SQLite + Alembic + config + logging + /health + /metrics | ✅ Real |
| Upstox: REST + OAuth + order placement + instrument resolution | ✅ Real (REST only, **live orders only**) |
| Data ingestion: news / NSE / options-chain feeds + manager | ✅ Real (REST polling, no V3 WebSocket) |
| Strategies: momentum + mean-reversion, feature builder, signal generator | ⚠️ 2 of PRD's 6; no backtest |
| AI layer: LLM provider abstraction (`generate_trade_analysis`, `rank_signals`) | ⚠️ OpenAI real; Gemini/HF stubs; **no Claude**; LLM only writes thesis/ranks — does not decide trades |
| Risk engine: 6 guardrails + metrics + allocator + treasury + risk_snapshots | ✅ Strong (most complete part) |
| HIL: trade-card approve/reject API + web frontend + multi-account | ⚠️ Web only, **no Telegram** |
| Reporting: EOD P&L, win-rate, card metrics | ⚠️ No Sharpe / drawdown / per-strategy attribution |
| Scheduler | ❌ Commented out in `main.py` |
| Paper trading | ❌ Missing — live orders only |
| Self-learning / regime classifier / trust scoring / self-reflection | ❌ Missing |
| Compliance: static IP / Algo ID / tax buckets | ❌ Missing |

Rich data model already exists: `accounts, mandates, funding_plans, trade_cards_v2, signals,
meta_labels, features, events, positions_v2, orders_v2, capital_transactions, playbooks,
risk_snapshots, market_data_cache, symbol_master, option_chains, option_strategies`.

---

## 3. Locked decisions

| # | Decision |
|---|---|
| L1 | **AI brain = Claude-first, multi-provider.** Add Anthropic as default orchestrator; keep OpenAI swappable via `LLM_PROVIDER`. Model ids: `claude-opus-4-8` (orchestrator), `claude-haiku-4-5` (specialist agents). |
| L2 | **Working style:** plan first, build step-by-step, validate each step before the next. One slice then review. |
| L3 | **Paper-first.** Live only after compliance + a 2-week paper sprint with ≥2 strategies at Sharpe > 1.0. |
| L4 | **Evolve, don't rebuild.** Reuse the existing risk engine and data model; extend rather than replace. |
| L5 | **Paper mode is architectural** — a `PaperBroker` sibling to `UpstoxBroker` behind the same interface, not a flag. |

---

## 4. Re-sequenced roadmap

> Changes vs the original PRD: **paper-mode + Claude move to the front; compliance moves to the end** —
> because infra/risk/Upstox already exist and compliance only blocks *live* order placement.

| # | Slice | Validation gate |
|---|---|---|
| **0** | Lock this plan | User approves the roadmap ✅ |
| **1** | Paper mode + Claude provider | `LLM_PROVIDER=anthropic` writes a thesis on a sample signal; a trade card executes in PAPER mode (simulated fill → `orders_v2`/`positions_v2`, no Upstox call); 60 tests green + new tests |
| **2** | Orchestrator + specialist agents (L4) ✅ | Pipeline emits validated orchestrator JSON (`market_thesis`, `trade_recommendations[]`, `tier` AUTO/HIL/SKIP, `risk_flags`); malformed JSON → rule-based fallback; per-day Claude cost tracked & capped. **Done (2a+2b+2c), live Claude pending key.** |
| **3** | Strategy expansion + backtest harness (L3) ✅ | Each strategy backtests on history (CAGR/Sharpe/DD/win-rate), forward-bias-safe, results stored. **Done (3a harness + 3b strategies); ORB deferred to live-WebSocket; real backfill needs Upstox token.** |
| **4** | Risk engine extension (L5) ✅ | Drawdown protocol (diagnose→paper→halt→RESUME), VIX circuit breakers, trailing/time SL, net-edge cost-gate — all tested. **Done (4a+4b); profit-separation + VIX feed + 15:10 time-exit execution land with the scheduler.** |
| **5** | Market-aware scheduler (L1/I3) ✅ | Jobs fire on timetable (token refresh, pre-market, signals, 15:10 force-exit, EOD, reflection); holiday calendar + dead-man's switch work |
| **6** | Telegram HIL relay (L6) | Approve a paper trade from phone → executes in paper → shows in journal; HALT/RESUME + escalation tiers work |
| **7** | Self-learning loop + reporting (L7/L8) | EOD job updates rolling strategy trust scores; regime classifier reweights strategies; weekly human-gated self-reflection; Sharpe/drawdown/attribution + Nifty benchmark on dashboard |
| **8** | Paper sprint (2 weeks) | 2 weeks paper data; ≥2 strategies Sharpe > 1.0 |
| **9** | Compliance + live launch (L0/Phase 4) | Static IP registered, Algo IDs mapped, tax buckets + CA export live, capital split; first real trade logged |

---

## 5. Critic refinements surfaced by the real codebase

- **Paper mode is architectural, not a flag** → `PaperBroker` sibling with a realistic fill model. (Step 1)
- **The orchestrator is genuinely new work** — current LLM interface is just thesis+rank; conviction-tier
  decisioning + context assembly is a new interface method. (Step 2)
- **Trust scoring needs new metrics** (Sharpe/drawdown/attribution) and depends on paper history. (Step 7)
- **Compliance de-risked** — only blocks live order placement; everything through Step 8 is paper. (Step 9)
- **`risk_snapshots` already has `daily_max_drawdown` / `portfolio_volatility`** — reuse for Steps 4 & 7.

---

## 6. Progress log

- 2026-06-16 — **Step 5 complete** (pending review): market-aware scheduler.
  `services/nse_calendar.py` (pure: `is_nse_holiday`, `is_market_hours`, `ist_now`,
  2026 NSE holiday set); `services/market_jobs.py` (9 async job functions: 07:55 token
  refresh, 08:30 pre-market, 09:00 morning briefing, 09:15 market open, 11:00/13:00/14:30
  checkpoints → trailing-stop ratchet + risk eval, 15:10 force-exit intraday paper
  positions, 15:30 EOD report, 16:30 Claude EOD reflection; dead-man's switch:
  `job_heartbeat` every 5 min + `check_missed_heartbeat` on startup);
  `services/scheduler.py` (SchedulerService singleton wrapping AsyncIOScheduler IST,
  11 jobs — 10 CronTrigger + 1 IntervalTrigger); `routers/scheduler.py`
  (GET /api/scheduler/status); config: `scheduler_enabled`, `scheduler_watchlist`,
  `heartbeat_max_age_minutes`; `main.py` lifespan wires start/shutdown + startup
  heartbeat check. 20 new tests, 145 total pass.

- 2026-06-16 — **Step 4b complete** (pending review): cost gate + VIX breakers + stop engine.
  `services/cost_model.py` (Indian round-trip costs + `passes_cost_gate` requiring ≥0.5% net edge,
  wired into `run_orchestrated` pre-card); VIX circuit breakers in `RiskGovernor`
  (≥18 size 0.6×, ≥22 pause intraday, ≥28 halt — folded into size-factor/blocks);
  `services/stop_engine.py` (ratchet-only trailing stop +2%/lock-50%, `is_time_exit`,
  `manage_trailing_stops`). 12 tests, 125 total pass. VIX feed + 15:10 force-exit execution land
  with the scheduler (Step 5). **Step 4 fully done.**
- 2026-06-16 — **Steps 1–3 merged to `master`** (PR #1). **Step 4a complete** (pending review):
  risk governor / staged drawdown protocol. New `services/risk_governor.py` — tracks peak equity,
  computes true drawdown %, state machine ACTIVE/DERISK/HALTED (persisted in Setting); 8%→DERISK
  (0.5× sizing), 12%→HALTED (block new entries + force paper + heuristic self-diagnosis +
  resume_required, sticky until human RESUME, then 14-day reduced-sizing window). Wired into
  `run_orchestrated` (halt→skip account, derisk→scale qty); new `risk` router
  (GET /state, POST /evaluate, POST /resume). 6 tests, 113 total pass. **Step 4b = net-edge cost
  gate + VIX circuit breakers + trailing/time SL (VIX feed + time-exit land with the scheduler).**

- 2026-06-16 — **Step 3b complete** (pending review): new daily strategies in
  `signals/extra.py` — RSI-divergence, Bollinger-squeeze breakout, 52-week-high breakout,
  Nifty-ETF momentum baseline (all SignalBase, ATR-based SL/TP). Registered in the backtester
  defaults and the v1 pipeline registry. 6 new tests; 107 total pass. e2e backtest drives all 6
  strategies. ORB still deferred (intraday). **Step 3 fully done.**
- 2026-06-16 — **Step 3a complete** (pending review): backtest harness. Data source = Upstox
  historical (per decision). New `services/backtest/` (data_loader: cache + `backfill_from_upstox`;
  engine: forward-bias-safe walk, one-position-at-a-time, SL/TP/max-hold exits + slippage, daily
  equity → CAGR/Sharpe/maxDD/win-rate/avg-hold; runner persists to new `backtest_results` table +
  migration 004). `POST /api/ai-trader/backtest`. 5 tests (forward-bias guard, deterministic-win,
  persistence), 101 total pass. Engine runs off `market_data_cache` (offline-testable); real
  history needs a valid Upstox token to backfill. **Step 3b = new strategies (RSI-divergence,
  Bollinger-squeeze, 52w-high, Nifty-ETF baseline); ORB deferred to live-WebSocket step.**

- 2026-06-16 — Step 0 complete: plan reconciled & locked. Step 1 spec drafted for validation.
- 2026-06-16 — **Step 2c complete** (pending review): orchestrator wired into v2 pipeline.
  Standardized on v2 (multi-account) as canonical. New `services/paper_execution.py`
  (`paper_execute_card_v2` → OrderV2+PositionV2 with is_paper); new
  `TradeCardPipelineV2.run_orchestrated` (allocator sizes, orchestrator tiers, guardrails still
  gate, SKIP→none / HIL→PENDING card / AUTO→create+paper-execute); `POST /api/ai-trader/orchestrate`
  endpoint. 3 integration tests, 96 total pass. **Step 2 fully done.**
- 2026-06-16 — **Step 2b complete** (pending review): specialist agents. Added a generic
  `LLMBase.complete_json` primitive (Anthropic + OpenAI) and `get_agent_llm()` (Haiku-tier);
  new `services/agents.py` with News (event sentiment), Technical (feature posture), Macro
  (regime/sector-rotation) agents that read real DB state and degrade to neutral defaults on
  error/no-data; orchestrator now enriches context via these agents (toggle `use_specialist_agents`,
  skipped under cost cap). 7 new mocked tests, 93 total pass. **Step 2c = wire orchestrator → pipeline
  (AUTO→paper-execute, HIL→pending card), resolving the v1/v2 trade-card split.**
- 2026-06-16 — **Step 2a complete** (pending review): orchestrator decision core. Added
  `LLMBase.orchestrate_decisions` (implemented in Anthropic + OpenAI providers) and a new
  `services/orchestrator.py` — context assembly from DB, strict JSON validation, deterministic
  AUTO/HIL/SKIP tier routing, per-day Claude cost cap (₹200) in the Setting table, and rule-based
  fallback on cost-cap/LLM-error/bad-JSON (fallback never AUTO-executes). 10 new tests (mocked),
  86 total pass. **Not yet wired into the pipeline; specialist News/Technical/Macro agents = Step 2b.**
  Live Claude still blocked on a valid `ANTHROPIC_API_KEY` (provided key returns 401).
- 2026-06-16 — **Step 1 complete** (pending review). Added Claude/Anthropic provider
  (`llm/anthropic_provider.py`) as default brain with graceful OpenAI fallback; added
  `PaperBroker` + `get_broker()` factory; `TRADING_MODE=paper` default; `is_paper` flag on
  orders/positions (v1+v2) + migration 003; paper execution branch in the trade-card approve
  flow (`_approve_paper`); `/health` reports `trading_mode`. Tests: 76 pass (60 original + 16 new:
  paper broker, anthropic provider/factory, paper approval integration). **Live Claude call still
  needs the user's `ANTHROPIC_API_KEY`.**
