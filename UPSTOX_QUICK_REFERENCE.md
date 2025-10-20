# Upstox API Quick Reference

**Essential commands and endpoints for AI Trading System**

---

## Quick Start

### 1. Initialize Service

```python
from backend.app.services.upstox_service import UpstoxService
from backend.app.database import get_db

# In FastAPI endpoint
service = UpstoxService(db)
```

### 2. Direct Broker Access

```python
from backend.app.services.broker import UpstoxBroker
from backend.app.config import get_settings

settings = get_settings()
broker = UpstoxBroker(
    api_key=settings.upstox_api_key,
    api_secret=settings.upstox_api_secret,
    redirect_uri=settings.upstox_redirect_uri
)
```

---

## Common Operations

### Place Order

```bash
# Via API
curl -X POST http://localhost:8000/api/upstox/order/multi-place \
  -H "Content-Type: application/json" \
  -d '{
    "orders": [{
      "trade_card_id": 1,
      "symbol": "RELIANCE",
      "transaction_type": "BUY",
      "quantity": 10,
      "order_type": "MARKET"
    }]
  }'
```

```python
# Via Service
order = await service.place_order_with_tracking(
    trade_card_id=1,
    symbol="RELIANCE",
    transaction_type="BUY",
    quantity=10,
    order_type="MARKET"
)
```

### Modify Order

```bash
# Via API
curl -X POST http://localhost:8000/api/upstox/order/modify \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": 123,
    "quantity": 15,
    "price": 1450.00
  }'
```

```python
# Via Service
order = await service.modify_order_and_update(
    order_id=123,
    quantity=15,
    price=1450.00
)
```

### Calculate Cost

```bash
# Via API
curl -X POST http://localhost:8000/api/upstox/calculate/brokerage \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "RELIANCE",
    "quantity": 10,
    "transaction_type": "BUY"
  }'
```

```python
# Via Service
cost = await service.calculate_trade_cost(
    symbol="RELIANCE",
    quantity=10,
    transaction_type="BUY"
)
```

### Search Instruments

```bash
# Via API
curl http://localhost:8000/api/upstox/instruments/search?query=RELIANCE&instrument_type=EQ
```

```python
# Via Service
results = await service.search_symbol(
    query="RELIANCE",
    instrument_type="EQ"
)
```

### Sync Positions

```bash
# Via API
curl -X POST http://localhost:8000/api/upstox/positions/sync
```

```python
# Via Service
positions = await service.sync_positions_from_broker()
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upstox/order/modify` | Modify existing order |
| POST | `/api/upstox/order/multi-place` | Place multiple orders |
| GET | `/api/upstox/order/{id}/trades` | Get order executions |
| POST | `/api/upstox/order/sync-all` | Sync all pending orders |
| POST | `/api/upstox/calculate/brokerage` | Calculate trade cost |
| POST | `/api/upstox/calculate/margin` | Calculate margin required |
| POST | `/api/upstox/positions/sync` | Sync positions from broker |
| GET | `/api/upstox/instruments` | Get instrument master |
| GET | `/api/upstox/instruments/search` | Search instruments |
| GET | `/api/upstox/profile` | Get user profile |
| GET | `/api/upstox/account/summary` | Get account summary |

---

## Broker Methods

### Order Management

```python
# Place order
await broker.place_order(symbol, transaction_type, quantity, order_type, price)

# Modify order
await broker.modify_order(order_id, quantity, order_type, price, trigger_price)

# Cancel order
await broker.cancel_order(order_id)

# Get order status
await broker.get_order_status(order_id)

# Get order history
await broker.get_order_history()

# Place multi-order
await broker.place_multi_order(orders)

# Get trades by order
await broker.get_trades_by_order(order_id)
```

### Position Management

```python
# Get positions
await broker.get_positions()

# Get day positions
await broker.get_day_positions()

# Get net positions
await broker.get_net_positions()

# Get holdings
await broker.get_holdings()

# Convert position
await broker.convert_position(instrument_token, transaction_type, quantity, from_product, to_product)
```

### Cost & Margin

```python
# Get brokerage
await broker.get_brokerage(instrument_token, quantity, transaction_type, product)

# Get margin required
await broker.get_margin_required(instruments)

# Get funds
await broker.get_funds()

# Get limits (alias for get_funds)
await broker.get_limits()
```

### Instrument Data

```python
# Get instruments
await broker.get_instruments(exchange, force_refresh)

# Search instrument
await broker.search_instrument(query, instrument_type, exchange)
```

### Market Data

```python
# Get LTP
await broker.get_ltp(symbol, exchange)

# Get OHLCV
await broker.get_ohlcv(symbol, interval, from_date, to_date, exchange)

# Get intraday candles
await broker.get_intraday_candle_data(instrument_key, interval)

# Get market quote
await broker.get_market_quote_full(instrument_keys)

# Get option chain
await broker.get_option_chain(instrument_key, expiry_date)
```

### Account

```python
# Get profile
await broker.get_profile()

# Get trade history
await broker.get_trade_history(page_number, page_size)
```

---

## Service Methods

### Order Management

```python
# Place with tracking
await service.place_order_with_tracking(trade_card_id, symbol, transaction_type, quantity, order_type, price)

# Place multi with tracking
await service.place_multi_order_with_tracking(orders)

# Modify and update
await service.modify_order_and_update(order_id, quantity, order_type, price)

# Sync order status
await service.sync_order_status(order_id)

# Sync all pending
await service.sync_all_pending_orders()

# Get order trades
await service.get_order_trades(order_id)
```

### Cost & Position

```python
# Calculate trade cost
await service.calculate_trade_cost(symbol, quantity, transaction_type, product, exchange)

# Calculate margin
await service.calculate_margin_for_orders(orders)

# Sync positions
await service.sync_positions_from_broker()
```

### Instruments & Account

```python
# Get instruments cached
await service.get_instruments_cached(exchange)

# Search symbol
await service.search_symbol(query, instrument_type, exchange)

# Get profile
await service.get_profile()

# Get account summary
await service.get_account_summary()
```

---

## Order Types & Products

### Order Types

- `MARKET` - Execute at market price (immediate)
- `LIMIT` - Execute at specific price or better
- `SL` - Stop Loss: Trigger at price, then limit order
- `SL-M` - Stop Loss Market: Trigger at price, then market order

### Product Types

- `D` - Delivery (held overnight)
- `I` - Intraday (square off same day)
- `M` - Margin (leveraged position)

### Transaction Types

- `BUY` - Buy/long position
- `SELL` - Sell/short position

### Validity

- `DAY` - Valid for current day only
- `IOC` - Immediate or Cancel

---

## Response Formats

### Success Response

```json
{
  "status": "success",
  "data": { ... }
}
```

### Error Response

```json
{
  "status": "error",
  "errors": [
    {
      "error_code": "UDAPI100068",
      "message": "Error message",
      "property_path": null,
      "invalid_value": null
    }
  ]
}
```

---

## Environment Variables

```bash
# Upstox credentials
UPSTOX_API_KEY=your-api-key
UPSTOX_API_SECRET=your-api-secret
UPSTOX_REDIRECT_URI=http://localhost:8000/api/auth/upstox/callback
```

---

## Testing

### Start Server

```bash
uvicorn backend.app.main:app --reload
```

### Access API Docs

```
http://localhost:8000/docs
```

### Test Authentication

1. Go to: http://localhost:8000/api/auth/upstox/login
2. Authorize with Upstox
3. Redirected back with tokens stored

### Test Endpoints

Use Swagger UI at `/docs` or:

```bash
# Health check
curl http://localhost:8000/health

# Search instruments
curl "http://localhost:8000/api/upstox/instruments/search?query=RELIANCE"

# Get account summary
curl http://localhost:8000/api/upstox/account/summary
```

---

## Common Patterns

### Pattern 1: Calculate Before Trading

```python
# Always calculate cost first
cost = await service.calculate_trade_cost(symbol, quantity, "BUY")

# Check if sufficient funds
if cost["total_cost"] > available_margin:
    return "Insufficient funds"

# Then place order
order = await service.place_order_with_tracking(...)
```

### Pattern 2: Batch Operations

```python
# Instead of multiple single orders
for trade in trades:
    await broker.place_order(...)  # Slow, multiple API calls

# Use multi-order
await service.place_multi_order_with_tracking(trades)  # Fast, single API call
```

### Pattern 3: Monitor & Sync

```python
# Sync all pending orders periodically
orders = await service.sync_all_pending_orders()

# Sync positions
positions = await service.sync_positions_from_broker()
```

### Pattern 4: Search & Trade

```python
# Search for instrument
results = await service.search_symbol("RELIANCE", "EQ")
symbol = results[0]["trading_symbol"]

# Get current price
ltp = await broker.get_ltp(symbol)

# Calculate cost
cost = await service.calculate_trade_cost(symbol, quantity, "BUY")

# Place order
order = await service.place_order_with_tracking(...)
```

---

## Error Handling

```python
from httpx import HTTPStatusError

try:
    order = await broker.place_order(...)
except HTTPStatusError as e:
    if e.response.status_code == 401:
        await broker.refresh_access_token()
    elif e.response.status_code == 429:
        # Rate limit - wait and retry
        await asyncio.sleep(1)
    else:
        logger.error(f"API error: {e}")
        raise
```

---

## Rate Limits

- Order placement: 10 requests/sec
- Market data: 25 requests/sec
- Order details: 10 requests/sec

**Tip:** Use multi-order API and caching to stay within limits.

---

## Useful Links

- [Full Integration Guide](UPSTOX_INTEGRATION_GUIDE.md)
- [Main Documentation](DOCUMENTATION.md)
- [Quick Start](QUICKSTART.md)
- [Upstox API Docs](https://upstox.com/developer/api-documentation)

---

**Quick Reference v2.0.0**  
**Last Updated:** October 20, 2025

