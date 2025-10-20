"""Verify Upstox configuration and provide fix instructions."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.config import get_settings

settings = get_settings()

print("\n" + "=" * 70)
print("UPSTOX CONFIGURATION VERIFICATION")
print("=" * 70)

print("\n📋 Your Current Configuration:")
print(f"  Client ID (API Key): {settings.upstox_api_key}")
print(f"  Redirect URI: {settings.upstox_redirect_uri}")

print("\n" + "=" * 70)
print("REQUIRED UPSTOX DASHBOARD SETTINGS")
print("=" * 70)

print("\n1. Go to: https://account.upstox.com/developer/apps")
print("\n2. Select your app (or create one)")

print("\n3. In the app settings, set EXACTLY:")
print("\n   📌 Redirect URI:")
print(f"   {settings.upstox_redirect_uri}")
print("\n   ⚠️  IMPORTANT:")
print("      - Must be EXACT match (case-sensitive)")
print("      - No trailing slash")
print("      - No extra spaces")
print("      - Include http:// (not https:// for localhost)")

print("\n4. Verify Client ID matches:")
print(f"   {settings.upstox_api_key}")

print("\n" + "=" * 70)
print("COMMON ISSUES & FIXES")
print("=" * 70)

print("\n❌ Issue: Redirect URI mismatch")
print("   Fix: Copy EXACTLY from above into Upstox dashboard")

print("\n❌ Issue: Client ID incorrect")
print("   Fix: Copy from Upstox dashboard to .env file")
print(f"        Update UPSTOX_API_KEY in .env")

print("\n❌ Issue: Using https:// instead of http://")
print("   Fix: Use http://localhost:8000 (not https)")

print("\n❌ Issue: Extra slash at end")
print("   Fix: Remove trailing slash from redirect URI")

print("\n" + "=" * 70)
print("AFTER UPDATING UPSTOX DASHBOARD")
print("=" * 70)

print("\n1. Save changes in Upstox dashboard")
print("2. Wait 1-2 minutes for changes to propagate")
print("3. Restart the server:")
print("   pkill -f uvicorn")
print("   uvicorn backend.app.main:app --reload")
print("4. Try login again at http://localhost:8000")

print("\n" + "=" * 70)
print("ALTERNATIVE: Use Upstox's Default Redirect URI")
print("=" * 70)

print("\nIf you want to use a different redirect URI:")
print("1. Set it in Upstox dashboard")
print("2. Update .env file:")
print("   UPSTOX_REDIRECT_URI=your-chosen-uri")
print("3. Restart server")

print("\n" + "=" * 70)
print("TESTING THE FIX")
print("=" * 70)

print("\nAfter fixing:")
print("1. Open http://localhost:8000")
print("2. Click 'Login with Upstox'")
print("3. Should redirect to Upstox login page")
print("4. After login, redirects back to your app")
print("5. Check for 'Authenticated' status")

print("\n" + "=" * 70 + "\n")


