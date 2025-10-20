# 🤖 AI Trader: Multi-Account Trading Desk Architecture

**Vision:** A personal, multi-account AI trading desk for Indian equities that ingests live data, researches events, scores opportunities, sizes positions per account goals, requires approval, executes bracket orders, reallocates capital dynamically, and logs everything.

---

## 🎯 System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACE                              │
│  Web Dashboard • Telegram Bot • Approval Queue • Reports            │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────┴────────────────────────────────────────┐
│                      ORCHESTRATION LAYER                             │
│  Hot Path • Decision Engine • Treasury Manager • Risk Monitor       │
└──┬────────┬────────┬────────┬────────┬────────┬────────┬───────────┘
   │        │        │        │        │        │        │
   ▼        ▼        ▼        ▼        ▼        ▼        ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Ingest│ │Resea-│ │Signal│ │Alloc-│ │Judge │ │Exec- │ │Audit │
│tion  │ │rch   │ │Gen   │ │ator  │ │LLM   │ │ution │ │Log   │
└──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘
   │        │        │        │        │        │        │
   └────────┴────────┴────────┴────────┴────────┴────────┴────────┐
                             │                                      │
┌────────────────────────────┴──────────────────────────────────────┤
│                      DATA & STATE LAYER                            │
│  Accounts • Mandates • Positions • Orders • Events • Features      │
└────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────┴──────────────────────────────────────┐
│                     EXTERNAL INTEGRATIONS                          │
│  NSE/BSE • News APIs • Upstox • Market Data • Derivatives         │
└────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Database Schema

### Core Entities

#### 1. Accounts (Logical Buckets)
```sql
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,  -- "SIP—Aggressive (24m)"
    account_type VARCHAR(50),     -- SIP, LUMP_SUM, EVENT_TACTICAL
    status VARCHAR(20),            -- ACTIVE, PAUSED, CLOSED
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(user_id, name)
);
```

#### 2. Mandates (Per-Account Rules)
```sql
CREATE TABLE mandates (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    version INTEGER DEFAULT 1,
    
    -- Objective
    objective VARCHAR(50),         -- MAX_PROFIT, RISK_MINIMIZED, BALANCED
    
    -- Risk Parameters
    risk_per_trade_percent FLOAT,  -- e.g., 1.5%
    max_positions INTEGER,         -- e.g., 10
    max_sector_exposure_percent FLOAT,  -- e.g., 30%
    
    -- Trading Parameters
    horizon_min_days INTEGER,      -- e.g., 1
    horizon_max_days INTEGER,      -- e.g., 7
    
    -- Restrictions
    banned_sectors JSON,           -- ["banking", "pharma"]
    earnings_blackout_days INTEGER, -- e.g., 2
    liquidity_floor_adv FLOAT,     -- Minimum avg daily volume
    min_market_cap FLOAT,          -- Minimum market cap
    
    -- Preferences
    allowed_strategies JSON,       -- ["momentum", "mean_reversion", "event_driven"]
    sl_multiplier FLOAT,           -- ATR multiplier for stop loss
    tp_multiplier FLOAT,           -- ATR multiplier for take profit
    trailing_stop_enabled BOOLEAN,
    
    -- Metadata
    assumption_log JSON,           -- What Intake Agent captured
    summary TEXT,                  -- One-paragraph mandate summary
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

#### 3. Funding Plans (Capital Management)
```sql
CREATE TABLE funding_plans (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    
    -- Funding Type
    funding_type VARCHAR(50),      -- SIP, LUMP_SUM, HYBRID
    
    -- SIP Parameters
    sip_amount FLOAT,              -- Monthly SIP amount
    sip_frequency VARCHAR(20),     -- MONTHLY, WEEKLY
    sip_start_date DATE,
    sip_duration_months INTEGER,
    
    -- Lump Sum Parameters
    lump_sum_amount FLOAT,
    lump_sum_date DATE,
    tranche_plan JSON,             -- [{"percent": 33, "trigger": "immediate"}, ...]
    
    -- Capital Rules
    carry_forward_enabled BOOLEAN,
    max_carry_forward_percent FLOAT,
    emergency_buffer_percent FLOAT,
    
    -- Current State
    total_deployed FLOAT,
    available_cash FLOAT,
    reserved_cash FLOAT,
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

#### 4. Capital Transactions
```sql
CREATE TABLE capital_transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    transaction_type VARCHAR(50),  -- DEPOSIT, WITHDRAWAL, TRANSFER_IN, TRANSFER_OUT
    amount FLOAT NOT NULL,
    from_account_id INTEGER,       -- For inter-account transfers
    to_account_id INTEGER,
    reason TEXT,
    timestamp TIMESTAMP,
    approved_by VARCHAR(50),
    
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

#### 5. Event Feeds (Ingestion)
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    
    -- Source
    source VARCHAR(100),           -- NSE_FILING, BSE_ANNOUNCEMENT, NEWS_API, etc.
    source_url TEXT,
    artifact_url TEXT,             -- Link to original PDF/page
    
    -- Content
    raw_content TEXT,
    normalized_content TEXT,
    
    -- Classification
    event_type VARCHAR(50),        -- BUYBACK, EARNINGS, GUIDANCE, PENALTY, POLICY
    priority VARCHAR(20),          -- HIGH, MEDIUM, LOW
    
    -- Linking
    symbols JSON,                  -- Affected tickers
    sector VARCHAR(50),
    
    -- Timing
    event_timestamp TIMESTAMP,
    ingested_at TIMESTAMP,
    processed_at TIMESTAMP,
    
    -- Features
    features JSON,                 -- Extracted features
    
    -- Status
    processing_status VARCHAR(20), -- PENDING, PROCESSED, FAILED
    
    UNIQUE(source, source_url, event_timestamp)
);
```

#### 6. Event Tags (NLP Output)
```sql
CREATE TABLE event_tags (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL,
    
    -- Entities
    entities JSON,                 -- Extracted entities
    tickers JSON,                  -- Linked tickers
    
    -- Classification
    event_type VARCHAR(50),
    stance VARCHAR(20),            -- BULLISH, BEARISH, NEUTRAL
    confidence FLOAT,              -- 0.0 to 1.0
    
    -- Analysis
    rationale TEXT,                -- 1-2 line explanation
    impact_score FLOAT,            -- Expected impact
    
    -- Provenance
    model_version VARCHAR(50),
    tagged_at TIMESTAMP,
    
    FOREIGN KEY (event_id) REFERENCES events(id)
);
```

#### 7. Features (Technical + Derivatives)
```sql
CREATE TABLE features (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(10),
    timestamp TIMESTAMP NOT NULL,
    
    -- Momentum
    momentum_5d FLOAT,
    momentum_10d FLOAT,
    momentum_20d FLOAT,
    
    -- Volatility
    atr_percent FLOAT,
    atr_14d FLOAT,
    
    -- Oscillators
    rsi_14 FLOAT,
    
    -- Gaps
    gap_percent FLOAT,
    gap_filled BOOLEAN,
    
    -- Derivatives
    iv_rank FLOAT,                 -- Implied Volatility rank
    pcr FLOAT,                     -- Put-Call Ratio
    pcr_delta FLOAT,
    oi_change_percent FLOAT,       -- Open Interest change
    futures_basis FLOAT,
    
    -- Regime
    regime_label VARCHAR(20),      -- LOW_VOL, MED_VOL, HIGH_VOL
    liquidity_regime VARCHAR(20),  -- HIGH, MEDIUM, LOW
    
    -- Flows
    fpi_flow_5d FLOAT,
    dii_flow_5d FLOAT,
    
    -- Provenance
    data_source VARCHAR(50),
    
    UNIQUE(symbol, exchange, timestamp)
);
```

#### 8. Signals (Primary Signal Output)
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(10),
    
    -- Signal
    direction VARCHAR(10),         -- LONG, SHORT
    edge FLOAT,                    -- Expected move %
    confidence FLOAT,              -- 0.0 to 1.0
    horizon_days INTEGER,
    
    -- Triple Barrier
    tp_probability FLOAT,          -- Probability of hitting TP
    sl_probability FLOAT,          -- Probability of hitting SL
    
    -- Quality
    quality_score FLOAT,           -- Meta-label output
    regime_compatible BOOLEAN,
    
    -- Thesis
    thesis_bullets JSON,           -- Key points
    
    -- Provenance
    model_version VARCHAR(50),
    feature_snapshot_id INTEGER,
    event_id INTEGER,              -- Triggering event if any
    
    generated_at TIMESTAMP,
    expires_at TIMESTAMP,
    status VARCHAR(20),            -- ACTIVE, EXPIRED, ACTED_ON
    
    FOREIGN KEY (event_id) REFERENCES events(id)
);
```

#### 9. Meta Labels (Signal Quality)
```sql
CREATE TABLE meta_labels (
    id INTEGER PRIMARY KEY,
    signal_id INTEGER NOT NULL,
    
    -- Assessment
    is_trustworthy BOOLEAN,
    quality_score FLOAT,
    
    -- Factors
    regime_score FLOAT,
    liquidity_score FLOAT,
    crowding_score FLOAT,
    timing_score FLOAT,
    
    -- Explanation
    rationale TEXT,
    
    -- Provenance
    model_version VARCHAR(50),
    computed_at TIMESTAMP,
    
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);
```

#### 10. Playbooks (Event Strategies)
```sql
CREATE TABLE playbooks (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    regime_match JSON,             -- {"volatility": ["LOW", "MED"], "liquidity": ["HIGH"]}
    
    -- Tactical Overrides
    priority_boost FLOAT,
    tranche_plan JSON,             -- [{"percent": 50, "delay": 0}, ...]
    acceptable_gap_chase_percent FLOAT,
    sl_multiplier_override FLOAT,
    tp_multiplier_override FLOAT,
    
    -- Restrictions
    pause_smallcap BOOLEAN,
    pause_duration_hours INTEGER,
    rotate_exposure_sectors JSON,
    
    -- Configuration
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    UNIQUE(name)
);
```

#### 11. Enhanced Trade Cards (Multi-Account)
```sql
CREATE TABLE trade_cards_v2 (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    signal_id INTEGER,
    
    -- Basic Info
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(10),
    direction VARCHAR(10),         -- LONG, SHORT
    
    -- Sizing
    entry_price FLOAT NOT NULL,
    quantity INTEGER NOT NULL,
    position_size_rupees FLOAT,
    
    -- Brackets
    stop_loss FLOAT NOT NULL,
    take_profit FLOAT NOT NULL,
    trailing_stop_config JSON,
    
    -- Tranche Plan
    tranche_config JSON,           -- [{"percent": 33, "trigger": "immediate"}, ...]
    
    -- Thesis
    strategy VARCHAR(50),
    thesis TEXT,                   -- LLM-generated explanation
    evidence_links JSON,           -- Links to events, features
    confidence FLOAT,
    edge FLOAT,
    horizon_days INTEGER,
    
    -- Risk Assessment
    risk_amount FLOAT,
    reward_amount FLOAT,
    risk_reward_ratio FLOAT,
    risks TEXT,                    -- LLM-identified risks
    
    -- Guardrails
    liquidity_check BOOLEAN,
    position_size_check BOOLEAN,
    exposure_check BOOLEAN,
    event_window_check BOOLEAN,
    regime_check BOOLEAN,
    catalyst_freshness_check BOOLEAN,
    risk_warnings JSON,
    
    -- Playbook
    playbook_id INTEGER,
    playbook_overrides JSON,
    
    -- Status
    status VARCHAR(20),            -- PENDING, APPROVED, REJECTED, EXECUTED, FILLED, CLOSED
    priority INTEGER,              -- For hot path
    
    -- LLM Metadata
    model_version VARCHAR(50),
    judge_rationale TEXT,
    
    -- Timestamps
    created_at TIMESTAMP,
    approved_at TIMESTAMP,
    rejected_at TIMESTAMP,
    executed_at TIMESTAMP,
    
    -- Approval
    approved_by VARCHAR(50),
    rejection_reason TEXT,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (signal_id) REFERENCES signals(id),
    FOREIGN KEY (playbook_id) REFERENCES playbooks(id)
);
```

#### 12. Enhanced Orders (Bracket Support)
```sql
CREATE TABLE orders_v2 (
    id INTEGER PRIMARY KEY,
    trade_card_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    
    -- Order Details
    broker_order_id VARCHAR(100),
    parent_order_id INTEGER,       -- For bracket orders
    order_category VARCHAR(20),    -- ENTRY, STOP_LOSS, TAKE_PROFIT, TRAIL
    
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(10),
    order_type VARCHAR(20),
    transaction_type VARCHAR(10),
    product VARCHAR(10),
    
    quantity INTEGER NOT NULL,
    price FLOAT,
    trigger_price FLOAT,
    
    -- Execution
    status VARCHAR(20),
    status_message TEXT,
    filled_quantity INTEGER DEFAULT 0,
    average_price FLOAT,
    
    -- Timestamps
    placed_at TIMESTAMP,
    updated_at TIMESTAMP,
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    
    FOREIGN KEY (trade_card_id) REFERENCES trade_cards_v2(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (parent_order_id) REFERENCES orders_v2(id)
);
```

#### 13. Enhanced Positions (Per-Account)
```sql
CREATE TABLE positions_v2 (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    trade_card_id INTEGER,
    
    symbol VARCHAR(20) NOT NULL,
    exchange VARCHAR(10),
    direction VARCHAR(10),         -- LONG, SHORT
    
    -- Position Details
    quantity INTEGER NOT NULL,
    average_entry_price FLOAT NOT NULL,
    current_price FLOAT,
    
    -- Active Brackets
    stop_loss FLOAT,
    take_profit FLOAT,
    trailing_stop_config JSON,
    
    -- P&L
    unrealized_pnl FLOAT,
    realized_pnl FLOAT,
    fees_paid FLOAT,
    
    -- Risk Metrics
    risk_amount FLOAT,
    reward_potential FLOAT,
    
    -- Timestamps
    opened_at TIMESTAMP,
    updated_at TIMESTAMP,
    closed_at TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (trade_card_id) REFERENCES trade_cards_v2(id)
);
```

#### 14. Risk Snapshots (Real-time Monitoring)
```sql
CREATE TABLE risk_snapshots (
    id INTEGER PRIMARY KEY,
    account_id INTEGER,            -- NULL for portfolio-wide
    
    -- Current State
    total_open_risk FLOAT,
    total_unrealized_pnl FLOAT,
    open_positions_count INTEGER,
    
    -- Daily Metrics
    daily_new_risk FLOAT,
    daily_realized_pnl FLOAT,
    daily_max_drawdown FLOAT,
    
    -- Volatility
    portfolio_volatility FLOAT,
    volatility_target FLOAT,
    
    -- Sector Exposure
    sector_exposures JSON,         -- {"banking": 25.5, "it": 15.2}
    
    -- Kill Switch Status
    kill_switches_active JSON,
    
    timestamp TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

#### 15. Kill Switches (Circuit Breakers)
```sql
CREATE TABLE kill_switches (
    id INTEGER PRIMARY KEY,
    account_id INTEGER,            -- NULL for portfolio-wide
    
    -- Configuration
    switch_type VARCHAR(50),       -- MAX_DAILY_LOSS, MAX_DRAWDOWN, VOL_SPIKE, etc.
    threshold_value FLOAT,
    threshold_type VARCHAR(20),    -- ABSOLUTE, PERCENTAGE
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_triggered BOOLEAN DEFAULT FALSE,
    triggered_at TIMESTAMP,
    triggered_value FLOAT,
    
    -- Actions
    action_on_trigger JSON,        -- {"pause_new_entries": true, "close_all": false}
    auto_reset_minutes INTEGER,
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

#### 16. Enhanced Audit Logs
```sql
CREATE TABLE audit_logs_v2 (
    id INTEGER PRIMARY KEY,
    
    -- Action
    action_type VARCHAR(50) NOT NULL,
    action_category VARCHAR(50),   -- INGESTION, SIGNAL, ALLOCATION, EXECUTION, etc.
    
    -- Context
    user_id VARCHAR(50),
    account_id INTEGER,
    trade_card_id INTEGER,
    order_id INTEGER,
    event_id INTEGER,
    signal_id INTEGER,
    
    -- Data
    payload JSON NOT NULL,         -- Full snapshot
    meta_data JSON,                -- Additional context
    
    -- Provenance
    model_version VARCHAR(50),
    strategy_version VARCHAR(50),
    service_name VARCHAR(100),
    
    -- Timing
    timestamp TIMESTAMP NOT NULL,
    latency_ms INTEGER,            -- For hot path monitoring
    
    -- Evidence
    artifact_links JSON,           -- Links to source documents
    checksum VARCHAR(64),          -- SHA-256 of payload
    
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
```

---

## 🔄 Data Flow Architecture

### 1. Ingestion Pipeline

```
External Sources
    ├─→ NSE/BSE Filings → PDF Extractor → Text Normalizer
    ├─→ News APIs → Deduplicator → Text Normalizer
    ├─→ Live Prices → WebSocket → Price Cache
    ├─→ Derivatives → API Poller → Feature Cache
    ├─→ Flows (FPI/DII) → API Scraper → Flow Cache
    └─→ Macro Stats → RSS/API → Macro Cache
                ↓
         Event Queue (Priority Sorted)
                ↓
         NLP Tagger → Event Tags
                ↓
         Feature Builder → Features Table
```

### 2. Signal Generation Pipeline

```
New Event / Periodic Refresh
    ↓
Feature Snapshot (Technical + Derivatives + Event)
    ↓
Primary Signal Model
    ├─→ Edge Estimation
    ├─→ Triple Barrier Probabilities
    └─→ Horizon Estimation
    ↓
Meta-Label Model
    ├─→ Regime Compatibility
    ├─→ Liquidity Assessment
    ├─→ Crowding Analysis
    └─→ Quality Score
    ↓
Candidate List (Symbol, Direction, Edge, Quality)
```

### 3. Allocation Pipeline (Per Account)

```
Candidate List
    ↓
Mandate Filtering
    ├─→ Horizon Match
    ├─→ Liquidity Floor
    ├─→ Sector Bans
    ├─→ Earnings Blackout
    └─→ Strategy Whitelist
    ↓
Quality Ranking (per objective)
    ├─→ MAX_PROFIT: Edge × Quality
    ├─→ RISK_MINIMIZED: (Edge × Quality) / Volatility
    └─→ BALANCED: Weighted combination
    ↓
Position Sizing
    ├─→ Volatility-targeted base
    ├─→ Kelly-lite cap
    ├─→ Risk per trade ≤ cap
    ├─→ Max positions limit
    └─→ Sector caps
    ↓
Bracket Calculation
    ├─→ Entry price
    ├─→ Stop Loss (ATR-bounded)
    ├─→ Take Profit (RR target)
    └─→ Trailing rules
    ↓
Deployable Cash Check
    └─→ SIP installment + carry-forward OR tranche availability
    ↓
Ready for Judge
```

### 4. Judge & Trade Card Generation

```
Top N Candidates per Account
    ↓
LLM Judge (ChatGPT)
    ├─→ Thesis generation
    ├─→ Evidence compilation
    ├─→ Risk assessment
    ├─→ Confidence scoring
    └─→ Structured JSON output
    ↓
Guardrail Checklist
    ├─→ Liquidity OK
    ├─→ Not in banned window
    ├─→ Risk within cap
    ├─→ Regime compatible
    ├─→ Not overbought/overskewed
    └─→ Catalyst fresh
    ↓
Trade Card Created (PENDING status)
    ↓
Approval Queue
```

### 5. Execution Pipeline

```
User Approval
    ↓
Bracket Order Creation
    ├─→ Entry Order (MARKET/LIMIT)
    ├─→ Stop Loss Order (SL)
    └─→ Take Profit Order (LIMIT)
    ↓
Upstox Execution
    ├─→ Place orders
    ├─→ Subscribe to fills
    └─→ Confirm back
    ↓
Position Tracking
    ├─→ Update position
    ├─→ Monitor price
    ├─→ Trail stop if enabled
    └─→ Partial exits per playbook
```

### 6. Intraday Management

```
Price Update (Every 5s)
    ↓
Position Evaluation
    ├─→ Check SL hit
    ├─→ Check TP hit
    ├─→ Evaluate trailing
    ├─→ Check playbook rules
    └─→ Check kill switches
    ↓
Action Required?
    ├─→ Yes → Generate Alert/Proposal → User Approval
    └─→ No → Continue monitoring
```

---

## 🎯 Component Responsibilities

### 1. Intake Agent (Account Setup)
- **Purpose:** Capture mandate and funding plan through conversational interface
- **Tech:** FastAPI endpoint + LLM (GPT-4)
- **Input:** User responses to 6-8 questions
- **Output:** Mandate + Funding Plan + Summary
- **Storage:** `mandates`, `funding_plans` tables

### 2. Ingestion Workers
- **Purpose:** Continuously ingest from external feeds
- **Tech:** AsyncIO workers, schedulers, WebSockets
- **Feeds:**
  - NSE/BSE filings (PDFs)
  - News APIs (NewsAPI, GDELT, RSS)
  - Live prices (Upstox WebSocket)
  - Derivatives (Option chain, IV, PCR)
  - Flows (FPI/DII data)
  - Macro (RBI, SEBI, PIB)
- **Output:** `events` table

### 3. NLP Tagger
- **Purpose:** Extract entities, classify events, assess stance
- **Tech:** Transformers (FinBERT, custom model) or LLM
- **Input:** Event text
- **Output:** `event_tags` table

### 4. Feature Builder
- **Purpose:** Compute technical and derivative features
- **Tech:** pandas, ta-lib, custom calculators
- **Input:** Price data, derivatives data
- **Output:** `features` table

### 5. Signal Generator
- **Purpose:** Generate primary signals with edge estimation
- **Tech:** ML model (LightGBM, XGBoost) or rule-based
- **Input:** Feature snapshots
- **Output:** `signals` table

### 6. Meta-Labeler
- **Purpose:** Assess signal quality and trustworthiness
- **Tech:** ML classifier (trained on historical outcomes)
- **Input:** Signal + regime + liquidity + crowding
- **Output:** `meta_labels` table

### 7. Playbook Manager
- **Purpose:** Apply tactical overrides based on event + regime
- **Tech:** Rule engine
- **Input:** Event type, regime label
- **Output:** Playbook overrides applied to sizing/brackets

### 8. Allocator (Per-Account)
- **Purpose:** Filter, rank, size positions per mandate
- **Tech:** Python service with account-specific logic
- **Input:** Candidate list, mandate, funding plan
- **Output:** Sized opportunities ready for judge

### 9. Judge (LLM)
- **Purpose:** Generate explainable trade cards
- **Tech:** OpenAI GPT-4 with structured output
- **Input:** Signal + features + event + mandate
- **Output:** `trade_cards_v2` with thesis, evidence, risks

### 10. Treasury Manager
- **Purpose:** Manage deployable cash, inter-account transfers
- **Tech:** Python service
- **Input:** Funding plans, current positions, proposals
- **Output:** Cash availability, transfer proposals

### 11. Execution Manager
- **Purpose:** Place bracket orders, monitor fills
- **Tech:** UpstoxBroker integration
- **Input:** Approved trade cards
- **Output:** `orders_v2`, `positions_v2` updates

### 12. Risk Monitor
- **Purpose:** Real-time risk tracking, kill switches
- **Tech:** Background loop (every 1-5 seconds)
- **Input:** Positions, prices, volatility
- **Output:** `risk_snapshots`, kill switch triggers

### 13. Hot Path Orchestrator
- **Purpose:** Fast-track breaking news to cards
- **Tech:** Priority queue + warmed models
- **Target:** Headline → Cards in seconds
- **Components:** All of the above in fast mode

### 14. Report Generator
- **Purpose:** EOD and monthly reports
- **Tech:** Scheduled jobs (APScheduler)
- **Input:** Audit logs, positions, orders
- **Output:** PDF/Markdown reports

---

## 🚀 Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
**Goal:** Multi-account structure, basic ingestion, single-path flow

**Tasks:**
- [x] Design architecture and schemas
- [ ] Extend database with new tables
- [ ] Build Intake Agent for mandates
- [ ] Create account CRUD APIs
- [ ] Basic ingestion (NSE filings, news)
- [ ] Simple feature builder
- [ ] Paper trading flow end-to-end

**Deliverable:** Demo with 2 accounts, manual signals → cards → approval

### Phase 2: Intelligence (Weeks 3-4)
**Goal:** Signal generation, meta-labeling, playbooks

**Tasks:**
- [ ] Build NLP tagger
- [ ] Implement signal generator (rule-based first)
- [ ] Add meta-labeler (simple classifier)
- [ ] Create playbook system
- [ ] Enhance Judge with playbook context
- [ ] Measure precision/recall

**Deliverable:** Automated signal → card with measurable uplift

### Phase 3: Allocation (Weeks 5-6)
**Goal:** Per-account allocation, funding patterns

**Tasks:**
- [ ] Build allocator with mandate filtering
- [ ] Implement position sizing logic
- [ ] Add SIP/lump-sum funding logic
- [ ] Create treasury module
- [ ] Inter-account transfer proposals
- [ ] Per-account approval queues

**Deliverable:** Multiple accounts with independent allocation

### Phase 4: Execution (Weeks 7-8)
**Goal:** Bracket orders, intraday management

**Tasks:**
- [ ] Bracket order execution
- [ ] Stop loss and take profit tracking
- [ ] Trailing stop logic
- [ ] Partial exits
- [ ] Gap handling
- [ ] Fill monitoring

**Deliverable:** Live execution with brackets and trails

### Phase 5: Risk & Hot Path (Weeks 9-10)
**Goal:** Real-time risk, kill switches, fast response

**Tasks:**
- [ ] Risk monitoring service
- [ ] Kill switch implementation
- [ ] Hot path optimization
- [ ] Latency SLOs
- [ ] Fallback mechanisms
- [ ] Alert system

**Deliverable:** Sub-5-second hot path, active kill switches

### Phase 6: Treasury (Weeks 11-12)
**Goal:** Capital choreography, inter-account moves

**Tasks:**
- [ ] Advanced treasury logic
- [ ] Cash staging for tranches
- [ ] Inter-account proposals
- [ ] Buffer management
- [ ] Auto-return logic

**Deliverable:** Dynamic capital allocation across accounts

### Phase 7: Polish (Weeks 13-14)
**Goal:** Audit, reporting, UI

**Tasks:**
- [ ] Timeline UI for audit trail
- [ ] EOD report automation
- [ ] Monthly report generation
- [ ] Drift detection
- [ ] Performance attribution
- [ ] Telegram bot integration

**Deliverable:** Production-ready system with full reporting

---

## 📋 Technology Stack

### Backend Services
- **Framework:** FastAPI (async)
- **Database:** PostgreSQL (production) / SQLite (dev)
- **ORM:** SQLAlchemy
- **Task Queue:** Celery + Redis
- **Scheduler:** APScheduler
- **WebSocket:** python-socketio
- **ML:** scikit-learn, LightGBM
- **NLP:** Transformers, sentence-transformers
- **LLM:** OpenAI GPT-4

### Data Processing
- **Time Series:** pandas, numpy
- **Technical Analysis:** ta, pandas-ta
- **PDF Parsing:** PyPDF2, pdfplumber
- **Web Scraping:** BeautifulSoup, scrapy

### External APIs
- **Broker:** Upstox API v2/v3
- **Market Data:** Upstox, NSE, BSE
- **News:** NewsAPI, GDELT, RSS feeds
- **Derivatives:** NSE Option Chain API

### Frontend (Future)
- **Dashboard:** React + Tailwind
- **Charts:** Plotly, TradingView
- **Notifications:** Telegram Bot API

---

## 🎯 Success Metrics

### Process Metrics
- **Hot Path Latency:** Headline → Card < 5 seconds
- **Approval Clarity:** > 90% users understand thesis
- **Rule Breach Detection:** 100% caught, 0 undetected

### Quality Metrics
- **Meta-Label Precision:** > 70% (prefer precision over recall)
- **Hit Rate:** > 55% of trades reach TP before SL
- **False Positive Rate:** < 20%

### Risk Metrics
- **Portfolio Volatility:** Within ±10% of target
- **Max Drawdown:** Within mandate limits
- **Daily Loss Limit:** Never breached

### P&L Metrics (Long-term)
- **SIP Accounts:** Steady compounding, low drawdowns
- **Lump-Sum Accounts:** Controlled rotations, event alpha
- **Sharpe Ratio:** > 1.5 (aspirational)

### Auditability
- **Reconstruction Time:** Any trade explained in < 3 clicks
- **Evidence Links:** 100% of cards have source links
- **Compliance:** Pass annual audit review

---

## 🔐 Security & Compliance

### Data Security
- Encrypted storage for API keys
- Environment variables for secrets
- Access control per account
- Audit logs immutable

### Compliance
- Manual approval required
- No unattended auto-trading
- Full audit trail
- Evidence preservation

### Risk Controls
- Hard limits on position sizes
- Kill switches with auto-triggers
- Banned windows enforced
- Inter-account moves require approval

---

## 📚 Next Steps

**Immediate Action:** Start with Phase 1

1. ✅ Create architecture document (this file)
2. [ ] Extend database schema
3. [ ] Build Intake Agent
4. [ ] Implement account CRUD
5. [ ] Add basic ingestion
6. [ ] Create simple feature builder
7. [ ] End-to-end demo

**Let's begin building!** 🚀

