# Testing AI Trading System Connections

## Step 1: Add API Credentials

Open the `.env` file and replace the placeholder values:

```bash
# Required Credentials
OPENAI_API_KEY=sk-your-actual-openai-key-here
UPSTOX_API_KEY=your-upstox-api-key
UPSTOX_API_SECRET=your-upstox-api-secret
```

### Where to Get Credentials:

**OpenAI API Key:**
1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-`)
4. Paste it in .env file

**Upstox API Credentials:**
1. Go to https://account.upstox.com/developer/apps
2. Create a new app if you haven't
3. Copy the API Key and API Secret
4. Paste them in .env file

## Step 2: Test Connections

Run the connection test script:

```bash
source venv/bin/activate
python scripts/test_connections.py
```

This will test:
- ✅ OpenAI API connection (sends a test request)
- ✅ Upstox configuration (validates credentials)

## Step 3: Run the Demo

If tests pass, try the demo with mock data:

```bash
python scripts/demo.py
```

This will:
- Generate mock market data for 5 stocks
- Run trading strategies
- Call OpenAI for trade analysis
- Create trade cards

## Step 4: Start the Server

Start the FastAPI server:

```bash
uvicorn backend.app.main:app --reload
```

Then open http://localhost:8000 in your browser.

## Step 5: Complete Upstox OAuth

1. Click "Login with Upstox" in the web interface
2. Grant permissions
3. You'll be redirected back to the app
4. Now you can approve/reject trades and place orders!

## Troubleshooting

**OpenAI Error: Invalid API key**
- Check that your key starts with `sk-`
- Make sure there are no extra spaces
- Verify the key is active in OpenAI dashboard

**Upstox Error: Invalid credentials**
- Verify API Key and Secret from Upstox developer console
- Make sure the redirect URI matches: `http://localhost:8000/api/auth/upstox/callback`

**Database Error**
- Delete `trading.db` and run `python -c "from backend.app.database import init_db; init_db()"`

## What to Expect

**Successful Test Output:**
```
==============================================================
AI TRADING SYSTEM - CONNECTION TEST
==============================================================

==============================================================
TESTING OPENAI CONNECTION
==============================================================

📡 Sending test request to OpenAI...
   Model: gpt-4-turbo-preview
   Test signal: RELIANCE

✅ OpenAI Connection SUCCESS!
   Response received:
   - Confidence: 0.65
   - Evidence: Based on the technical setup...
   - Model: gpt-4-turbo-preview

==============================================================
TESTING UPSTOX CONFIGURATION
==============================================================

✅ Upstox Credentials Configured!
   API Key: abc123xyz...
   API Secret: def456uvw...
   Redirect URI: http://localhost:8000/api/auth/upstox/callback

📝 OAuth URL Generated:
   https://api.upstox.com/v2/login/authorization/dialog?...

💡 Next Steps for Upstox:
   1. Start the server: uvicorn backend.app.main:app --reload
   2. Open http://localhost:8000 in your browser
   3. Click 'Login with Upstox' to complete OAuth
   4. Grant permissions to connect your account

==============================================================
TEST SUMMARY
==============================================================
OpenAI Connection:      ✅ PASS
Upstox Configuration:   ✅ PASS

🎉 ALL TESTS PASSED!

You're ready to run the demo:
   python scripts/demo.py

Or start the server:
   uvicorn backend.app.main:app --reload
==============================================================
```

## Ready to Trade!

Once everything is connected:
1. ✅ OpenAI is analyzing trades
2. ✅ Upstox is ready to execute orders
3. ✅ Database is storing everything
4. ✅ UI is displaying trade cards

Happy trading! 🚀

