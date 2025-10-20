"""Test script to verify AI (OpenAI) and Upstox connections."""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from backend.app.config import get_settings
from backend.app.services.llm.openai_provider import OpenAIProvider
from backend.app.services.broker.upstox import UpstoxBroker

settings = get_settings()


async def test_openai_connection():
    """Test OpenAI API connection."""
    print("\n" + "=" * 60)
    print("TESTING OPENAI CONNECTION")
    print("=" * 60)
    
    if not settings.openai_api_key or settings.openai_api_key == "your-openai-api-key":
        print("❌ OpenAI API key not configured")
        print("   Please add OPENAI_API_KEY to your .env file")
        return False
    
    try:
        # Initialize OpenAI provider
        llm = OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )
        
        # Test with a simple signal
        test_signal = {
            "symbol": "RELIANCE",
            "strategy": "test",
            "entry_price": 2500.0,
            "suggested_sl": 2450.0,
            "suggested_tp": 2600.0,
            "trade_type": "BUY",
            "score": 0.7
        }
        
        test_market_data = {
            "latest_close": 2500.0,
            "latest_volume": 1000000
        }
        
        print("\n📡 Sending test request to OpenAI...")
        print(f"   Model: {settings.openai_model}")
        print(f"   Test signal: {test_signal['symbol']}")
        
        # Make API call
        analysis = await llm.generate_trade_analysis(
            signal=test_signal,
            market_data=test_market_data,
            context={}
        )
        
        print("\n✅ OpenAI Connection SUCCESS!")
        print(f"   Response received:")
        print(f"   - Confidence: {analysis.get('confidence', 0):.2f}")
        print(f"   - Evidence: {analysis.get('evidence', '')[:100]}...")
        print(f"   - Model: {analysis.get('model_version', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ OpenAI Connection FAILED: {e}")
        print("   Check your API key and network connection")
        return False


async def test_upstox_configuration():
    """Test Upstox configuration (not full auth since that requires OAuth)."""
    print("\n" + "=" * 60)
    print("TESTING UPSTOX CONFIGURATION")
    print("=" * 60)
    
    if not settings.upstox_api_key or settings.upstox_api_key == "your-upstox-api-key":
        print("❌ Upstox API key not configured")
        print("   Please add UPSTOX_API_KEY to your .env file")
        return False
    
    if not settings.upstox_api_secret or settings.upstox_api_secret == "your-upstox-api-secret":
        print("❌ Upstox API secret not configured")
        print("   Please add UPSTOX_API_SECRET to your .env file")
        return False
    
    try:
        # Initialize Upstox broker
        broker = UpstoxBroker(
            api_key=settings.upstox_api_key,
            api_secret=settings.upstox_api_secret,
            redirect_uri=settings.upstox_redirect_uri
        )
        
        print("\n✅ Upstox Credentials Configured!")
        print(f"   API Key: {settings.upstox_api_key[:10]}...")
        print(f"   API Secret: {settings.upstox_api_secret[:10]}...")
        print(f"   Redirect URI: {settings.upstox_redirect_uri}")
        
        # Generate auth URL
        auth_url = broker.get_auth_url()
        print(f"\n📝 OAuth URL Generated:")
        print(f"   {auth_url}")
        
        print("\n💡 Next Steps for Upstox:")
        print("   1. Start the server: uvicorn backend.app.main:app --reload")
        print("   2. Open http://localhost:8000 in your browser")
        print("   3. Click 'Login with Upstox' to complete OAuth")
        print("   4. Grant permissions to connect your account")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Upstox Configuration FAILED: {e}")
        return False


async def main():
    """Run all connection tests."""
    print("\n" + "=" * 60)
    print("AI TRADING SYSTEM - CONNECTION TEST")
    print("=" * 60)
    
    # Test OpenAI
    openai_ok = await test_openai_connection()
    
    # Test Upstox configuration
    upstox_ok = await test_upstox_configuration()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"OpenAI Connection:      {'✅ PASS' if openai_ok else '❌ FAIL'}")
    print(f"Upstox Configuration:   {'✅ PASS' if upstox_ok else '❌ FAIL'}")
    
    if openai_ok and upstox_ok:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYou're ready to run the demo:")
        print("   python scripts/demo.py")
        print("\nOr start the server:")
        print("   uvicorn backend.app.main:app --reload")
    else:
        print("\n⚠️  Please fix the failed tests and try again")
    
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)

