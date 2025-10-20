# AI Trading System - Quick Start Guide

## Overview

This is a semi-automated Indian equities trading system with AI-powered signal generation, LLM-based trade analysis, and mandatory manual approval workflow.

## Prerequisites

- Python 3.10 or higher
- Upstox trading account with API access
- OpenAI API key

## Installation

### 1. Set up Python environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
# Copy template
cp env.template .env

# Edit .env and add your credentials
nano .env  # or use your preferred editor
```

**Required credentials:**
- `UPSTOX_API_KEY` - From Upstox Developer Console
- `UPSTOX_API_SECRET` - From Upstox Developer Console  
- `OPENAI_API_KEY` - From OpenAI Platform

### 3. Initialize database

```bash
python -c "from backend.app.database import init_db; init_db()"
```

## Quick Demo

Run the demo script with mock data to test the system:

```bash
python scripts/demo.py
```

This will:
1. Generate mock market data for 5 stocks
2. Run signal generation strategies
3. Create trade cards with LLM analysis
4. Show you what the system produces

## Running the Application

### Option 1: Using the run script (recommended)

```bash
chmod +x run.sh
./run.sh
```

### Option 2: Direct uvicorn command

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Access the application

Open your browser and navigate to:
- **Frontend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Usage Workflow

### 1. Authenticate with Upstox

1. Click "Login with Upstox" in the UI
2. Complete OAuth flow
3. Return to the app (authenticated)

### 2. Generate Signals

Click "Generate Signals" button to:
- Scan stocks using momentum and mean reversion strategies
- Analyze signals with LLM (GPT-4)
- Apply risk guardrails
- Create pending trade cards

### 3. Review Trade Cards

Review each trade card showing:
- Symbol and entry/exit prices
- Position size and risk metrics
- LLM confidence score and evidence
- Risk warnings if any

### 4. Approve or Reject

- **Approve**: Places order with broker
- **Reject**: Dismisses the trade with reason

### 5. Monitor

Track positions, orders, and P&L in the dashboard

## Manual Signal Generation

```bash
python scripts/signal_generator.py
```

## Generate EOD Report

```bash
# Today's report
python scripts/eod_report.py

# Specific date
python scripts/eod_report.py 2025-01-15
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend

# Run specific test file
pytest tests/test_strategies.py
```

## Project Structure

```
AI-Investment/
├── backend/              # FastAPI backend
│   └── app/
│       ├── main.py       # Application entry
│       ├── config.py     # Settings
│       ├── database.py   # Models
│       ├── schemas.py    # Pydantic schemas
│       ├── routers/      # API endpoints
│       └── services/     # Business logic
│           ├── broker/   # Upstox integration
│           ├── llm/      # OpenAI/Gemini/HF
│           └── signals/  # Trading strategies
├── frontend/             # HTML/CSS/JS UI
│   ├── index.html
│   └── static/
├── scripts/              # Background jobs
│   ├── signal_generator.py
│   ├── eod_report.py
│   └── demo.py
├── tests/                # Test suite
└── logs/                 # Application logs
```

## Configuration

Key settings in `.env`:

### Risk Parameters
- `MAX_CAPITAL_RISK_PERCENT=2.0` - Max % of capital at risk per trade
- `MIN_LIQUIDITY_ADV=1000000` - Minimum average daily volume
- `MAX_POSITION_SIZE_PERCENT=10.0` - Max % in single position
- `MAX_SECTOR_EXPOSURE_PERCENT=30.0` - Max % in single sector

### Trading Parameters
- `DEFAULT_TRADE_HORIZON_DAYS=3` - Default holding period
- `EARNINGS_BLACKOUT_DAYS=2` - Days to avoid around earnings

### LLM Settings
- `LLM_PROVIDER=openai` - Choose: openai, gemini, huggingface
- `OPENAI_MODEL=gpt-4-turbo-preview` - Model to use

## Troubleshooting

### Database Issues
```bash
# Reset database
rm trading.db
python -c "from backend.app.database import init_db; init_db()"
```

### Authentication Issues
- Verify API credentials in `.env`
- Check redirect URI matches Upstox app settings
- Ensure you're using the correct Upstox environment (sandbox vs production)

### LLM Errors
- Verify OpenAI API key is valid
- Check rate limits and quotas
- Review logs in `logs/trading.log`

### No Signals Generated
- Market may not have setups matching criteria
- Try adjusting strategy parameters
- Check if sufficient market data is available

## Development

### Adding a New Strategy

1. Create file in `backend/app/services/signals/`
2. Inherit from `SignalBase`
3. Implement `generate_signals()` method
4. Register in `pipeline.py`

### Adding a New Broker

1. Create file in `backend/app/services/broker/`
2. Inherit from `BrokerBase`
3. Implement all abstract methods
4. Add configuration in `config.py`

### Adding a New LLM Provider

1. Create file in `backend/app/services/llm/`
2. Inherit from `LLMBase`
3. Implement `generate_trade_analysis()` and `rank_signals()`
4. Add to provider factory in `pipeline.py`

## Security Notes

- Never commit `.env` file
- Use HTTPS in production
- Rotate API keys regularly
- Enable authentication for multi-user deployments

## Support & Issues

- Check logs: `tail -f logs/trading.log`
- Review API docs: http://localhost:8000/docs
- See main README.md for detailed documentation

## Next Steps

1. ✅ Run demo to validate setup
2. ✅ Configure API credentials
3. ✅ Authenticate with broker
4. ✅ Generate first signals
5. ✅ Review and approve trades
6. 📊 Monitor performance
7. 📈 Iterate and improve strategies

---

**Disclaimer**: This software is for educational purposes only. Trading involves substantial risk of loss. Use at your own risk.

