# AI Trading System MVP

A semi-automated Indian equities trading tool focused on swing/event-driven trades (1-7 days) with AI-powered signal generation, LLM-based trade analysis, and mandatory manual approval.

## Features

- 🤖 **AI Signal Engine**: Momentum and mean reversion strategies with technical indicators
- 🧠 **LLM Judge**: Trade card generation with evidence, risks, and confidence scoring
- ✅ **Manual Approval**: Review and approve every trade before execution
- 📊 **Upstox Integration**: Real-time market data and order execution
- 🛡️ **Risk Guardrails**: Pre-trade checks for liquidity, position sizing, and exposure limits
- 📝 **Audit Trail**: Comprehensive logging of all decisions and actions
- 📈 **Reports**: Daily EOD and monthly performance summaries

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (HTML/JS)                      │
│            Trade Cards • Dashboard • Reports                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
┌──────────────────────────┴──────────────────────────────────┐
│                   FastAPI Backend                            │
├──────────────────────────────────────────────────────────────┤
│  Signal Engine  │  LLM Judge  │  Risk Checks  │  Audit Log  │
├──────────────────────────────────────────────────────────────┤
│              Broker Abstraction Layer                        │
│                  (Upstox API)                                │
├──────────────────────────────────────────────────────────────┤
│                   SQLite Database                            │
└──────────────────────────────────────────────────────────────┘
```

## Project Structure

```
AI-Investment/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI application
│   │   ├── config.py               # Configuration management
│   │   ├── database.py             # Database setup and models
│   │   ├── schemas.py              # Pydantic schemas
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py            # Authentication endpoints
│   │   │   ├── trade_cards.py     # Trade card management
│   │   │   ├── positions.py       # Position queries
│   │   │   └── reports.py         # Report generation
│   │   └── services/
│   │       ├── broker/
│   │       │   ├── __init__.py
│   │       │   ├── base.py        # Abstract broker interface
│   │       │   └── upstox.py      # Upstox implementation
│   │       ├── llm/
│   │       │   ├── __init__.py
│   │       │   ├── base.py        # Abstract LLM interface
│   │       │   ├── openai_provider.py
│   │       │   ├── gemini_provider.py
│   │       │   └── huggingface_provider.py
│   │       ├── signals/
│   │       │   ├── __init__.py
│   │       │   ├── base.py        # Abstract signal interface
│   │       │   ├── momentum.py    # Momentum strategy
│   │       │   └── mean_reversion.py
│   │       ├── risk_checks.py     # Risk validation
│   │       ├── audit.py           # Audit logging
│   │       └── pipeline.py        # Trade card generation pipeline
│   └── alembic/                   # Database migrations
├── frontend/
│   ├── index.html                 # Main UI
│   ├── static/
│   │   ├── css/
│   │   │   └── styles.css
│   │   └── js/
│   │       ├── app.js
│   │       └── api.js
├── scripts/
│   ├── signal_generator.py        # Daily signal generation
│   ├── eod_report.py             # End-of-day reports
│   └── demo.py                    # Demo with mock data
├── tests/
│   ├── test_strategies.py
│   ├── test_risk_checks.py
│   └── test_api.py
├── logs/                          # Application logs
├── .env.example                   # Environment variables template
├── .env                          # Your local environment (git-ignored)
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## Setup Instructions

### 1. Prerequisites

- Python 3.10 or higher
- Upstox trading account with API access
- OpenAI API key (or other LLM provider)

### 2. Installation

```bash
# Clone or navigate to the project directory
cd AI-Investment

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

### 3. Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

**Required configuration:**
- `UPSTOX_API_KEY` and `UPSTOX_API_SECRET` from [Upstox Developer Console](https://account.upstox.com/developer/apps)
- `OPENAI_API_KEY` from [OpenAI Platform](https://platform.openai.com/api-keys)
- Adjust risk parameters as needed

### 4. Database Setup

```bash
# Initialize database
python -c "from backend.app.database import init_db; init_db()"
```

### 5. Running the Application

```bash
# Start the FastAPI server
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# Access the application
# Frontend: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### 6. Background Jobs

```bash
# Run signal generation manually
python scripts/signal_generator.py

# Run EOD report
python scripts/eod_report.py

# For automated scheduling, the app uses APScheduler (runs in the main process)
```

## Usage Workflow

1. **Authentication**: Log in with Upstox OAuth
2. **Signal Generation**: Automated daily at 9:15 AM or manual trigger
3. **Review Trade Cards**: View AI-generated trade opportunities in the dashboard
4. **Approve/Reject**: Click to approve or reject each trade
5. **Execution**: Approved trades are sent to Upstox for execution
6. **Monitoring**: Track positions and P&L in real-time
7. **Reports**: Review daily and monthly performance reports

## API Endpoints

### Authentication
- `GET /api/auth/upstox/login` - Initiate Upstox OAuth flow
- `POST /api/auth/upstox/callback` - OAuth callback handler

### Trade Cards
- `GET /api/trade-cards/pending` - Get pending trade cards
- `GET /api/trade-cards/{id}` - Get specific trade card
- `POST /api/trade-cards/{id}/approve` - Approve and execute
- `POST /api/trade-cards/{id}/reject` - Reject with reason

### Trading
- `GET /api/positions` - Get current positions
- `GET /api/orders` - Get order history
- `POST /api/signals/run` - Manually trigger signal generation

### Reports
- `GET /api/reports/eod?date=YYYY-MM-DD` - Get EOD report
- `GET /api/reports/monthly?month=YYYY-MM` - Get monthly report

## Risk Management

The system enforces multiple risk guardrails:

1. **Liquidity Check**: Minimum average daily volume requirement
2. **Position Sizing**: Max 2% of capital at risk per trade
3. **Exposure Limits**: Max position size and sector exposure
4. **Event Windows**: Avoids trading around earnings/corporate actions
5. **Margin Check**: Validates sufficient funds before order placement

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend

# Run specific test file
pytest tests/test_strategies.py
```

## Deployment

### Option 1: Railway

```bash
# Install Railway CLI
npm i -g @railway/cli

# Deploy
railway login
railway init
railway up
```

### Option 2: Render

1. Create new Web Service
2. Connect repository
3. Set environment variables
4. Deploy

### Option 3: DigitalOcean

```bash
# Use App Platform or deploy on Droplet with:
gunicorn backend.app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Security Considerations

- ⚠️ **Never commit `.env` file** - Contains sensitive API keys
- 🔒 **Use HTTPS in production** - Protect API communication
- 🔑 **Rotate API keys regularly** - Minimize exposure risk
- 👤 **Implement user authentication** - For multi-user deployments
- 📊 **Monitor audit logs** - Track all system actions

## Compliance Notes

- ✅ **Manual approval required** - No unattended auto-trading
- ✅ **Full audit trail** - All decisions logged with timestamps
- ✅ **Risk guardrails** - Pre-trade compliance checks
- ✅ **Transparent decisions** - LLM evidence and reasoning captured

## Troubleshooting

### Database Issues
```bash
# Reset database
rm trading.db
python -c "from backend.app.database import init_db; init_db()"
```

### Upstox Connection
- Verify API credentials in `.env`
- Check redirect URI matches Upstox app settings
- Ensure market is open for live data

### LLM Errors
- Verify API key is valid
- Check rate limits and quotas
- Review logs in `logs/trading.log`

## Future Enhancements

- [ ] Add more brokers (Dhan, Fyers, Zerodha)
- [ ] Telegram/Slack notifications
- [ ] Advanced strategies (ML-based, sentiment analysis)
- [ ] Portfolio optimization
- [ ] Backtesting framework
- [ ] MCP assistant integration

## License

MIT License - See LICENSE file for details

## Disclaimer

**This software is for educational purposes only. Trading involves substantial risk of loss. Use at your own risk. The authors are not responsible for any financial losses incurred through the use of this system.**

## Support

For questions or issues, please open an issue on GitHub or contact the maintainers.

# AI-Trading
