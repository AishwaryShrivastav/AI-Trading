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
| **2** | Orchestrator + specialist agents (L4) | Pipeline emits validated orchestrator JSON (`market_thesis`, `trade_recommendations[]`, `tier` AUTO/HIL/SKIP, `risk_flags`); malformed JSON → rule-based fallback; per-day Claude cost tracked & capped |
| **3** | Strategy expansion + backtest harness (L3) | Each strategy backtests on 2yr history (CAGR/Sharpe/DD/win-rate), forward-bias-safe, results stored; India filters (circuit/liquidity/corp-action/earnings) enforced |
| **4** | Risk engine extension (L5) | Simulated 15% drawdown fires R4 protocol (diagnose→paper→halt→RESUME); VIX circuit breakers, trailing/time SL, profit-separation, cost-gate tested |
| **5** | Market-aware scheduler (L1/I3) | Jobs fire on timetable (token refresh, pre-market, signals, 15:10 force-exit, EOD, reflection); holiday calendar + dead-man's switch work |
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

- 2026-06-16 — Step 0 complete: plan reconciled & locked. Step 1 spec drafted for validation.
- 2026-06-16 — **Step 1 complete** (pending review). Added Claude/Anthropic provider
  (`llm/anthropic_provider.py`) as default brain with graceful OpenAI fallback; added
  `PaperBroker` + `get_broker()` factory; `TRADING_MODE=paper` default; `is_paper` flag on
  orders/positions (v1+v2) + migration 003; paper execution branch in the trade-card approve
  flow (`_approve_paper`); `/health` reports `trading_mode`. Tests: 76 pass (60 original + 16 new:
  paper broker, anthropic provider/factory, paper approval integration). **Live Claude call still
  needs the user's `ANTHROPIC_API_KEY`.**
